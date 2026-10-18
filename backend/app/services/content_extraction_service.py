"""
Unified Content Extraction Service

This service provides a unified interface for content extraction,
replacing the legacy Firecrawl implementation with the intelligent
extraction system for better performance and reliability.
"""
import asyncio
import html as html_lib
import logging
import re
import time
from typing import Optional, Dict, Any, Mapping, Tuple

import httpx

from . import egress_rotation as egress
from .archive_fetch_errors import (
    ArchiveBlockPage,
    ArchiveConnectionError,
    ArchiveFetchError,
    ArchiveHTTPError,
    ArchiveRateLimited,
)
from .archive_rate_limiter import get_archive_rate_limiter, parse_retry_after
from .intelligent_content_extractor import get_intelligent_extractor
from .wayback_machine import CDXRecord
from ..models.extraction_data import ExtractedContent
from ..core.config import settings

logger = logging.getLogger(__name__)

# Prefix of ExtractedContent.error when a successful fetch yielded too little text. Callers
# use it to tell a thin page (skipped, final) from a failed fetch (retried later).
MINIMAL_CONTENT_ERROR = "Extraction failed or returned minimal content"


# --------------------------------------------------------------------------
# Wayback response classification (runs BEFORE any extraction so an archive
# error/block page is never stored as page content)
# --------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)

# Phrases archive.org serves when it throttles an IP (checked against the title,
# or against the whole text of a short page).
_RATE_LIMIT_TITLES = ("429", "too many requests", "rate limit", "503 service", "service unavailable")
_RATE_LIMIT_PHRASES = (
    "too many requests",
    "rate limit",
    "you have sent too many",
    "you are being rate limited",
)
_NOT_ARCHIVED_PHRASES = (
    "wayback machine has not archived that url",
    "this url has not been archived",
)
_EXCLUDED_PHRASES = (
    "has been excluded from the wayback machine",
    "blocked by the site owner",
    "page cannot be displayed due to robots.txt",
)
_BLANK_TITLES = ("new tab", "about:blank")
_IA_MARKERS = ("internet archive", "web.archive.org", "wayback machine")


def _visible_text(markup: str) -> str:
    text = _SCRIPT_STYLE_RE.sub(" ", markup)
    text = _TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def detect_block_page(body: Optional[str], url: Optional[str] = None) -> Optional[ArchiveFetchError]:
    """
    Return the typed error for a Wayback body that is an error/block/blank page
    rather than a capture, or None if it looks like real content.

    Matches IA's 429 HTML ("Too Many Requests"), blank / about:blank / "New Tab"
    bodies, tiny bodies carrying only IA branding, "Hrm. The Wayback Machine has
    not archived that URL." and excluded-URL pages. Binary-looking bodies (PDF)
    are never flagged.
    """
    if body is None or not body.strip():
        return ArchiveBlockPage("Archive returned an empty body", url=url)
    stripped = body.strip()
    if stripped.startswith("%PDF"):
        return None

    lowered = stripped[:20000].lower()
    title_match = _TITLE_RE.search(stripped[:20000])
    title = html_lib.unescape(title_match.group(1)).strip().lower() if title_match else ""
    visible = _visible_text(stripped[:20000])
    visible_lower = visible.lower()
    short = len(visible) < 600

    if lowered == "about:blank" or (title in _BLANK_TITLES and len(visible) < 100):
        return ArchiveBlockPage(f"Blank page served by archive (title {title or 'about:blank'!r})", url=url)

    if len(stripped) < 30000:
        if any(p in visible_lower for p in _NOT_ARCHIVED_PHRASES) or title.startswith("hrm"):
            err = ArchiveBlockPage("Wayback Machine has not archived that URL (Hrm. page)", url=url)
            err.retryable = False
            return err
        if any(p in visible_lower for p in _EXCLUDED_PHRASES):
            err = ArchiveBlockPage("URL excluded from the Wayback Machine", url=url)
            err.retryable = False
            return err

    if any(t in title for t in _RATE_LIMIT_TITLES) or (short and any(p in visible_lower for p in _RATE_LIMIT_PHRASES)):
        return ArchiveRateLimited("Archive served a rate-limit page (Too Many Requests)", url=url, status_code=429)

    if len(visible) < 200 and any(m in lowered for m in _IA_MARKERS):
        return ArchiveBlockPage(f"Tiny archive error page: {visible[:100]!r}", url=url)

    if not visible and len(stripped) < 2048 and not re.search(r"<(img|iframe|frameset|embed|object|video)\b", lowered):
        return ArchiveBlockPage("Archive returned a blank HTML skeleton", url=url)

    return None


def check_wayback_response(
    url: str, status_code: int, headers: Mapping[str, str], body: Optional[str]
) -> None:
    """
    Raise the matching typed error unless this is a usable capture:

    * 429 / 503, or a rate-limit page   -> ArchiveRateLimited (retry_after from Retry-After)
    * 404 / 410 / other 4xx             -> ArchiveHTTPError (final)
    * 5xx / stray 3xx                   -> ArchiveHTTPError (5xx retryable)
    * 200 with an error/blank body      -> ArchiveBlockPage / ArchiveRateLimited
    """
    if status_code in (429, 503):
        raise ArchiveRateLimited(
            f"Archive rate limited the request (HTTP {status_code})",
            url=url, status_code=status_code,
            retry_after=parse_retry_after(headers.get("Retry-After")),
        )
    if status_code >= 500:
        err = ArchiveHTTPError(f"Archive server error (HTTP {status_code})", url=url, status_code=status_code)
        err.retryable = True
        raise err
    if status_code >= 300:
        raise ArchiveHTTPError(f"Archive returned HTTP {status_code}", url=url, status_code=status_code)
    block = detect_block_page(body, url)
    if block is not None:
        block.status_code = status_code
        raise block


class ContentExtractionService:
    """
    Unified content extraction service using intelligent extraction strategies

    This replaces the FirecrawlExtractor with direct use of the robust
    extraction system which provides:
    - 99.9% faster extraction (0.017s vs 15.25s)
    - Multiple fallback strategies (trafilatura, newspaper3k, beautifulsoup)
    - Circuit breaker patterns for resilience
    - Built-in caching and retry mechanisms
    """

    def __init__(self):
        self.intelligent_extractor = get_intelligent_extractor()
        self.extraction_semaphore = asyncio.Semaphore(
            getattr(settings, 'INTELLIGENT_EXTRACTION_CONCURRENCY', 50)
        )

        # Metrics tracking
        self.metrics = {
            'total_requests': 0,
            'successful_extractions': 0,
            'failed_extractions': 0,
            'total_processing_time': 0.0
        }

        logger.info(f"Initialized unified content extraction service with "
                   f"concurrency limit: {self.extraction_semaphore._value}")

    async def _fetch_html(self, cdx_record: CDXRecord, content_url: str) -> Tuple[str, float]:
        """
        Fetch the raw HTML for a CDX record. Returns ``(html, fetch_seconds)``.

        * Common Crawl: straight from the WARC on data.commoncrawl.org (public CDN,
          no proxy, no limiter, no FlareSolverr).
        * Wayback (web.archive.org): exactly one request through the shared limiter
          (see ``_fetch_wayback_html``).
        * anything else: live-web fallback (``_fetch_live_html``).

        Archive failures raise ArchiveFetchError subclasses carrying ``fetch_time``
        (seconds spent on the HTTP request, when one was made).
        """
        started = time.monotonic()

        if getattr(cdx_record, 'is_common_crawl', False) and (
            getattr(cdx_record, 'warc_filename', None) is not None and
            getattr(cdx_record, 'warc_offset', None) is not None and
            getattr(cdx_record, 'warc_length', None) is not None
        ):
            html_content: Optional[str] = None
            try:
                from .common_crawl_direct_service import CommonCrawlDirectService
                async with CommonCrawlDirectService() as cc_service:
                    html_content = await cc_service.fetch_warc_html(
                        cdx_record.warc_filename,
                        cdx_record.warc_offset,
                        cdx_record.warc_length,
                    )
                    if html_content:
                        logger.info(f"Fetched HTML from Common Crawl WARC ({len(html_content)} chars)")
            except Exception as cc_err:
                logger.warning(f"Common Crawl WARC fetch failed: {cc_err}")
            # A CC capture must come from its WARC; don't fall back to fetching the
            # live URL (that returns current/blocked content, not the archived page).
            if not html_content:
                raise Exception(f"Common Crawl WARC fetch returned no HTML for {content_url}")
            return html_content, time.monotonic() - started

        if "web.archive.org" in content_url:
            return await self._fetch_wayback_html(content_url)

        html_content = await self._fetch_live_html(content_url)
        return html_content, time.monotonic() - started

    async def _fetch_wayback_html(self, content_url: str) -> Tuple[str, float]:
        """
        One request per page through the single global Wayback limiter (Redis token
        bucket + AIMD + in-flight cap + global pause, shared with the CDX client).
        No inline retry: a 429/503 pauses all Wayback traffic and is raised as
        ArchiveRateLimited, a limiter refusal as ArchiveDeferred (nothing was sent),
        so the caller re-queues later.
        """
        limiter = get_archive_rate_limiter()
        lease = await limiter.acquire("content")
        try:
            return await self._get_snapshot(content_url, lease)
        finally:
            await limiter.release(lease)

    async def _get_snapshot(self, content_url: str, lease) -> Tuple[str, float]:
        timeout = httpx.Timeout(
            connect=10.0, read=float(settings.DIRECT_FETCH_READ_TIMEOUT), write=15.0, pool=10.0
        )
        client_kwargs: Dict[str, Any] = {
            "timeout": timeout, "follow_redirects": True, "max_redirects": 5,
            **egress.wayback_client_kwargs(),
        }

        started = time.monotonic()

        def fail(exc: ArchiveFetchError) -> ArchiveFetchError:
            exc.fetch_time = time.monotonic() - started  # type: ignore[attr-defined]
            return exc

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.get(content_url)
        except httpx.TooManyRedirects as exc:
            raise fail(ArchiveHTTPError(f"Redirect loop for {content_url}", url=content_url)) from exc
        except httpx.TransportError as exc:
            verdict = await lease.connection_failed(exc)
            raise fail(ArchiveConnectionError(
                f"{type(exc).__name__} fetching {content_url} ({verdict})",
                url=content_url,
            )) from exc

        fetch_seconds = time.monotonic() - started
        try:
            check_wayback_response(content_url, resp.status_code, resp.headers, resp.text)
        except ArchiveRateLimited as exc:
            logger.warning(
                f"Wayback rate limited: HTTP {resp.status_code} "
                f"({exc}), Retry-After={exc.retry_after}: {content_url}"
            )
            exc.retry_after = await lease.rate_limited(exc.retry_after)
            raise fail(exc) from None
        except ArchiveFetchError as exc:
            raise fail(exc) from None

        await lease.success()
        logger.info(
            f"Wayback snapshot: HTTP {resp.status_code}, "
            f"{len(resp.text)} chars in {fetch_seconds:.2f}s"
        )
        return resp.text, fetch_seconds

    async def _fetch_live_html(self, content_url: str) -> str:
        """
        Live-web fetch for non-archive URLs (not paced: this is not archive.org).
        FlareSolverr is only consulted here, and only when FLARESOLVERR_ENABLED.
        """
        from app.services.flaresolverr_service import (
            get_flaresolverr_service,
            looks_like_challenge,
            is_browser_error_page,
        )
        from app.services.stealth_headers import get_stealth_headers

        proxy_server = getattr(settings, 'PROXY_SERVER', None)
        proxy_username = getattr(settings, 'PROXY_USERNAME', None)
        proxy_password = getattr(settings, 'PROXY_PASSWORD', None)
        proxy_url = None
        if proxy_server:
            if proxy_username and proxy_password:
                proxy_url = f"http://{proxy_username}:{proxy_password}@{proxy_server.replace('http://', '')}"
            else:
                proxy_url = proxy_server if proxy_server.startswith('http') else f"http://{proxy_server}"
        stealth_hdrs = get_stealth_headers()
        stealth_hdrs["Cache-Control"] = "max-age=0"
        client_kwargs: Dict[str, Any] = {
            "timeout": httpx.Timeout(connect=60.0, read=180.0, write=30.0, pool=10.0),
            "follow_redirects": True,
            "limits": httpx.Limits(max_keepalive_connections=5, max_connections=10),
            "headers": stealth_hdrs,
        }
        if proxy_url:
            client_kwargs["proxy"] = proxy_url
        fs = get_flaresolverr_service()
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.get(content_url)
        except httpx.TransportError as exc:
            raise ArchiveConnectionError(
                f"{type(exc).__name__} fetching {content_url}", url=content_url
            ) from exc
        body = resp.text
        if resp.status_code != 200 or looks_like_challenge(resp.status_code, body):
            if fs.enabled:
                logger.info(f"Direct fetch blocked (HTTP {resp.status_code}); retrying via FlareSolverr: {content_url}")
                solved = await fs.fetch(content_url, proxy_url=proxy_url)
                if solved:
                    return solved
            raise ArchiveHTTPError(
                f"HTTP {resp.status_code} fetching {content_url}", url=content_url, status_code=resp.status_code
            )
        if is_browser_error_page(body):
            raise ArchiveBlockPage(f"Error page returned for {content_url}", url=content_url)
        logger.info(f"HTML content retrieved via HTTP: {len(body)} characters")
        return body

    async def extract_content(self, cdx_record: CDXRecord) -> ExtractedContent:
        """
        Extract content from a CDX record using intelligent extraction

        Args:
            cdx_record: CDX record containing URL and metadata

        Returns:
            ExtractedContent with extraction results; ``result.fetch_time`` is the
            seconds spent on the HTTP request (excluding limiter waits).

        Raises:
            ArchiveFetchError subclasses (ArchiveRateLimited, ArchiveConnectionError,
            ArchiveHTTPError, ArchiveBlockPage) when the content could not be fetched;
            the exception carries ``fetch_time`` when a request was made. Extraction
            problems are still reported through ``result.error`` as before.
        """
        start_time = time.time()
        content_url = cdx_record.content_url

        self.metrics['total_requests'] += 1

        try:
            logger.info(f"Starting intelligent extraction for {content_url}")

            async with self.extraction_semaphore:
                html_content, fetch_seconds = await self._fetch_html(cdx_record, content_url)

                # Extract content using intelligent extractor
                logger.info("Starting intelligent content extraction")
                extraction_start = time.time()
                extraction_result = self.intelligent_extractor.extract(html_content, content_url)
                extraction_time = time.time() - extraction_start

                logger.info(f"Intelligent extraction completed in {extraction_time:.3f}s: "
                           f"method={extraction_result.extraction_method}, "
                           f"word_count={extraction_result.word_count}, "
                           f"confidence={extraction_result.confidence_score:.3f}")

                # Log extraction result details
                if extraction_result.text:
                    logger.debug(f"Extracted text preview: {extraction_result.text[:200]}")
                else:
                    logger.warning("No text content extracted from HTML")

                # Convert to ExtractedContent format
                result = ExtractedContent(
                    title=extraction_result.title,
                    text=extraction_result.text,
                    markdown=extraction_result.markdown,
                    html=extraction_result.html,
                    word_count=extraction_result.word_count,
                    extraction_method=f"intelligent_{extraction_result.extraction_method}",
                    extraction_time=extraction_result.processing_time,
                    meta_description=extraction_result.metadata.description,
                    author=extraction_result.metadata.author,
                    language=extraction_result.metadata.language,
                    published_date=extraction_result.metadata.publication_date,
                    source_url=content_url
                )

            # Update result with CDX metadata
            processing_time = time.time() - start_time
            result.url = cdx_record.original_url
            result.content_url = content_url
            result.timestamp = cdx_record.timestamp
            result.extraction_time = processing_time
            result.fetch_time = fetch_seconds

            # Update metrics
            self.metrics['total_processing_time'] += processing_time

            # Validate extraction results
            min_word_count = 50
            if result.text and result.word_count > min_word_count:
                self.metrics['successful_extractions'] += 1
                logger.info(f"✓ Extraction succeeded for {cdx_record.original_url}: "
                           f"{result.word_count} words using {result.extraction_method} "
                           f"in {processing_time:.3f}s")
            else:
                self.metrics['failed_extractions'] += 1
                failure_reason = []
                if not result.text:
                    failure_reason.append("no text content")
                if result.word_count <= min_word_count:
                    failure_reason.append(f"insufficient word count ({result.word_count} ≤ {min_word_count})")

                logger.error(f"✗ Extraction failed for {cdx_record.original_url}: "
                            f"{', '.join(failure_reason)}. "
                            f"Method: {result.extraction_method}, "
                            f"Title: {result.title[:100] if result.title else 'None'}, "
                            f"Content preview: {result.text[:200] if result.text else 'None'}")

                # Set error information
                result.error = f"{MINIMAL_CONTENT_ERROR}: {', '.join(failure_reason)}"

            return result

        except ArchiveFetchError as e:
            # Typed fetch failure (rate limit / connection / HTTP / block page): the
            # caller records it honestly and re-queues; never turn it into "content".
            self.metrics['failed_extractions'] += 1
            self.metrics['total_processing_time'] += time.time() - start_time
            logger.warning(
                f"Fetch failed for {cdx_record.original_url}: {type(e).__name__}: {e} "
                f"(retryable={e.retryable}, retry_after={e.retry_after})"
            )
            raise

        except Exception as e:
            self.metrics['failed_extractions'] += 1
            processing_time = time.time() - start_time
            self.metrics['total_processing_time'] += processing_time

            # Log detailed error information
            error_type = type(e).__name__
            logger.error(f"✗ Intelligent extraction failed for {cdx_record.original_url} "
                        f"after {processing_time:.3f}s: {error_type}: {e}")

            # Log stack trace for debugging
            import traceback
            logger.debug(f"Full stack trace:\n{traceback.format_exc()}")

            # Provide specific error categorization
            error_category = "unknown_error"
            if "timeout" in str(e).lower():
                error_category = "timeout_error"
            elif "connection" in str(e).lower():
                error_category = "connection_error"
            elif "proxy" in str(e).lower():
                error_category = "proxy_error"
            elif "http" in str(e).lower():
                error_category = "http_error"

            # Return minimal content for complete failures
            return ExtractedContent(
                title="Extraction Failed",
                text=f"Content extraction failed ({error_category}): {str(e)}",
                markdown="",
                html="",
                word_count=0,
                extraction_method=f"extraction_failed_{error_category}",
                extraction_time=processing_time,
                url=cdx_record.original_url,
                content_url=content_url,
                timestamp=cdx_record.timestamp,
                error=f"{error_type}: {str(e)}"
            )

    async def extract_content_with_escalation(
        self, cdx_record: CDXRecord, retry_count: int = 0
    ) -> ExtractedContent:
        """
        Extract content with progressive escalation strategy.

        For retry_count < 2: uses normal extract_content() (precision mode).
        For retry_count >= 2: uses extract_with_recall() with lower word threshold.

        This allows non-article pages (business sites, daycares, etc.) to be
        captured on later retries when precision-mode trafilatura strips too much.
        """
        if retry_count < 2:
            return await self.extract_content(cdx_record)

        # Escalation: use recall mode with lower thresholds
        start_time = time.time()
        content_url = cdx_record.content_url

        self.metrics['total_requests'] += 1

        try:
            logger.info(f"Starting escalated extraction (retry #{retry_count}) for {content_url}")

            async with self.extraction_semaphore:
                html_content, fetch_seconds = await self._fetch_html(cdx_record, content_url)

                # Use recall-mode extraction
                extraction_start = time.time()
                extraction_result = self.intelligent_extractor.extract_with_recall(
                    html_content, content_url
                )
                extraction_time = time.time() - extraction_start

                logger.info(f"Escalated extraction completed in {extraction_time:.3f}s: "
                           f"method={extraction_result.extraction_method}, "
                           f"word_count={extraction_result.word_count}, "
                           f"confidence={extraction_result.confidence_score:.3f}")

                result = ExtractedContent(
                    title=extraction_result.title,
                    text=extraction_result.text,
                    markdown=extraction_result.markdown,
                    html=extraction_result.html,
                    word_count=extraction_result.word_count,
                    extraction_method=f"escalated_{extraction_result.extraction_method}",
                    extraction_time=extraction_result.processing_time,
                    meta_description=extraction_result.metadata.description,
                    author=extraction_result.metadata.author,
                    language=extraction_result.metadata.language,
                    published_date=extraction_result.metadata.publication_date,
                    source_url=content_url
                )

            # Update result with CDX metadata
            processing_time = time.time() - start_time
            result.url = cdx_record.original_url
            result.content_url = content_url
            result.timestamp = cdx_record.timestamp
            result.extraction_time = processing_time
            result.fetch_time = fetch_seconds

            self.metrics['total_processing_time'] += processing_time

            # Lower threshold for escalated extraction: 20 words minimum
            min_word_count = 20
            if result.text and result.word_count > min_word_count:
                self.metrics['successful_extractions'] += 1
                logger.info(f"✓ Escalated extraction succeeded for {cdx_record.original_url}: "
                           f"{result.word_count} words using {result.extraction_method}")
            else:
                self.metrics['failed_extractions'] += 1
                failure_reason = []
                if not result.text:
                    failure_reason.append("no text content")
                if result.word_count <= min_word_count:
                    failure_reason.append(f"insufficient word count ({result.word_count} ≤ {min_word_count})")
                result.error = f"Escalated extraction insufficient: {', '.join(failure_reason)}"
                logger.warning(f"✗ Escalated extraction insufficient for {cdx_record.original_url}: "
                              f"{', '.join(failure_reason)}")

            return result

        except ArchiveFetchError as e:
            # Typed fetch failure (rate limit / connection / HTTP / block page): the
            # caller records it honestly and re-queues; never turn it into "content".
            self.metrics['failed_extractions'] += 1
            self.metrics['total_processing_time'] += time.time() - start_time
            logger.warning(
                f"Fetch failed for {cdx_record.original_url}: {type(e).__name__}: {e} "
                f"(retryable={e.retryable}, retry_after={e.retry_after})"
            )
            raise

        except Exception as e:
            self.metrics['failed_extractions'] += 1
            processing_time = time.time() - start_time
            self.metrics['total_processing_time'] += processing_time

            error_type = type(e).__name__
            logger.error(f"✗ Escalated extraction failed for {cdx_record.original_url}: "
                        f"{error_type}: {e}")

            error_category = "unknown_error"
            if "timeout" in str(e).lower():
                error_category = "timeout_error"
            elif "connection" in str(e).lower():
                error_category = "connection_error"
            elif "proxy" in str(e).lower():
                error_category = "proxy_error"
            elif "http" in str(e).lower():
                error_category = "http_error"

            return ExtractedContent(
                title="Extraction Failed",
                text=f"Escalated extraction failed ({error_category}): {str(e)}",
                markdown="",
                html="",
                word_count=0,
                extraction_method=f"escalated_failed_{error_category}",
                extraction_time=processing_time,
                url=cdx_record.original_url,
                content_url=content_url,
                timestamp=cdx_record.timestamp,
                error=f"{error_type}: {str(e)}"
            )

    async def extract_content_batch(self, cdx_records: list) -> list:
        """
        Extract content from multiple CDX records in parallel

        Args:
            cdx_records: List of CDX records to process

        Returns:
            List of ExtractedContent objects
        """
        tasks = [self.extract_content(record) for record in cdx_records]
        return await asyncio.gather(*tasks, return_exceptions=False)

    def get_metrics(self) -> Dict[str, Any]:
        """Get extraction service metrics"""
        avg_time = (self.metrics['total_processing_time'] / self.metrics['total_requests']
                   if self.metrics['total_requests'] > 0 else 0)

        success_rate = (self.metrics['successful_extractions'] / self.metrics['total_requests']
                       if self.metrics['total_requests'] > 0 else 0)

        return {
            'total_requests': self.metrics['total_requests'],
            'successful_extractions': self.metrics['successful_extractions'],
            'failed_extractions': self.metrics['failed_extractions'],
            'success_rate': success_rate,
            'average_processing_time': avg_time,
            'total_processing_time': self.metrics['total_processing_time']
        }

    async def health_check(self) -> Dict[str, str]:
        """Check health of the extraction service"""
        try:
            # Test extraction with a simple HTML snippet
            test_html = "<html><body><h1>Test</h1><p>Test content</p></body></html>"
            test_url = "http://example.com/test"

            # Use the instance's intelligent extractor for health check
            result = self.intelligent_extractor.extract(test_html, test_url)

            if result and result.text:
                return {
                    'content_extraction': 'healthy',
                    'available_extractors': len(self.intelligent_extractor.extractors),
                    'status': 'operational'
                }
            else:
                return {
                    'content_extraction': 'degraded',
                    'status': 'partial'
                }

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'content_extraction': 'unhealthy',
                'error': str(e),
                'status': 'failed'
            }


# Global instance
_content_extraction_service = None

def get_content_extraction_service() -> ContentExtractionService:
    """Get global content extraction service instance"""
    global _content_extraction_service
    if _content_extraction_service is None:
        _content_extraction_service = ContentExtractionService()
    return _content_extraction_service


# Compatibility aliases for smooth migration
def get_firecrawl_extractor():
    """
    Compatibility alias for legacy code
    Returns the unified content extraction service
    """
    logger.warning("get_firecrawl_extractor() is deprecated. "
                  "Use get_content_extraction_service() instead.")
    return get_content_extraction_service()


# For backward compatibility with imports
FirecrawlExtractor = ContentExtractionService
