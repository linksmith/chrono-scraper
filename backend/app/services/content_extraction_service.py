"""
Unified Content Extraction Service

This service provides a unified interface for content extraction,
replacing the legacy Firecrawl implementation with the intelligent
extraction system for better performance and reliability.
"""
import asyncio
import logging
import time
from typing import Optional, Dict, Any

from .intelligent_content_extractor import get_intelligent_extractor
from .wayback_machine import CDXRecord
from ..models.extraction_data import ExtractedContent
from ..core.config import settings

logger = logging.getLogger(__name__)


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

    async def _fetch_html(self, cdx_record: CDXRecord, content_url: str) -> str:
        """
        Fetch HTML content from a CDX record URL.

        Tries Common Crawl WARC first (if applicable), then falls back to HTTP
        with proxy/stealth headers. Returns the raw HTML string.
        """
        html_content: Optional[str] = None

        # For Common Crawl records, fetch the HTML straight from the WARC file on
        # data.commoncrawl.org (public CDN, no proxy needed). This is the correct
        # source for a CC capture — not a live/Wayback fetch of the URL.
        if getattr(cdx_record, 'is_common_crawl', False) and (
            getattr(cdx_record, 'warc_filename', None) is not None and
            getattr(cdx_record, 'warc_offset', None) is not None and
            getattr(cdx_record, 'warc_length', None) is not None
        ):
            try:
                from .common_crawl_direct_service import CommonCrawlDirectService
                async with CommonCrawlDirectService() as cc_service:
                    html_via_cc = await cc_service.fetch_warc_html(
                        cdx_record.warc_filename,
                        cdx_record.warc_offset,
                        cdx_record.warc_length,
                    )
                    if html_via_cc:
                        html_content = html_via_cc
                        logger.info(f"Fetched HTML from Common Crawl WARC ({len(html_via_cc)} chars)")
            except Exception as cc_err:
                logger.warning(f"Common Crawl WARC fetch failed: {cc_err}")
            # A CC capture must come from its WARC; don't fall back to fetching the
            # live URL (that returns current/blocked content, not the archived page).
            if html_content is None:
                raise Exception(f"Common Crawl WARC fetch returned no HTML for {content_url}")

        # Fallback: fetch via HTTP (Wayback or direct) with proxy
        if html_content is None:
            import httpx
            from app.services.flaresolverr_service import (
                get_flaresolverr_service,
                looks_like_challenge,
                is_browser_error_page,
            )
            fs = get_flaresolverr_service()
            flaresolverr_primary = (
                str(getattr(settings, 'EGRESS_PROVIDER', '')).lower() == 'mullvad' and fs.enabled
            )

            if flaresolverr_primary:
                # Rotating VPN egress: plain GETs over rotating exits first,
                # FlareSolverr only as the escalation path (see method docstring).
                html_content = await self._fetch_via_rotating_egress(content_url)
            else:
                proxy_server = getattr(settings, 'PROXY_SERVER', None)
                proxy_username = getattr(settings, 'PROXY_USERNAME', None)
                proxy_password = getattr(settings, 'PROXY_PASSWORD', None)
                proxy_url = None
                if proxy_server:
                    if proxy_username and proxy_password:
                        proxy_url = f"http://{proxy_username}:{proxy_password}@{proxy_server.replace('http://', '')}"
                    else:
                        proxy_url = proxy_server if proxy_server.startswith('http') else f"http://{proxy_server}"
                timeout_config = httpx.Timeout(connect=60.0, read=180.0, write=30.0, pool=10.0)
                from app.services.stealth_headers import get_stealth_headers
                stealth_hdrs = get_stealth_headers()
                stealth_hdrs["Cache-Control"] = "max-age=0"
                client_kwargs: Dict[str, Any] = {
                    "timeout": timeout_config,
                    "follow_redirects": True,
                    "limits": httpx.Limits(max_keepalive_connections=5, max_connections=10),
                    "headers": stealth_hdrs,
                }
                if proxy_url:
                    client_kwargs["proxy"] = proxy_url
                if "web.archive.org" in content_url:
                    client_kwargs["headers"]["Referer"] = "https://web.archive.org/"
                async with httpx.AsyncClient(**client_kwargs) as client:
                    resp = await client.get(content_url)
                    body = resp.text
                    # Escalate to FlareSolverr when the direct fetch is blocked or
                    # served a challenge; never store a block/challenge body as content.
                    if resp.status_code != 200 or looks_like_challenge(resp.status_code, body):
                        if fs.enabled:
                            logger.info(
                                f"Direct fetch blocked (HTTP {resp.status_code}); "
                                f"retrying via FlareSolverr: {content_url}"
                            )
                            solved = await fs.fetch(content_url, proxy_url=proxy_url)
                            if solved:
                                html_content = solved
                            else:
                                raise Exception(f"Blocked/challenge and FlareSolverr failed for {content_url}")
                        else:
                            raise Exception(f"HTTP {resp.status_code}: {body[:300]}")
                    elif is_browser_error_page(body):
                        raise Exception(f"Archive returned an error page for {content_url}")
                    else:
                        html_content = body
                logger.info(f"HTML content retrieved via HTTP: {len(html_content)} characters")

        return html_content or ""

    async def _fetch_via_rotating_egress(self, content_url: str) -> str:
        """
        Fast path for archive fetches over the rotating VPN exit pool.

        Wayback blocks by per-IP rate limiting (429/403), not JS challenges, so
        a plain GET through a fresh exit is ~10-20x cheaper than a FlareSolverr
        browser navigation. Try direct fetches over rotating exits first; park
        exits that block or stall, and escalate to FlareSolverr only after the
        direct attempts are exhausted. Raises when everything fails so a block
        page is never stored as content.
        """
        import httpx
        from app.services.flaresolverr_service import (
            get_flaresolverr_service,
            looks_like_challenge,
            is_browser_error_page,
        )
        from app.services.egress_rotation import (
            egress_proxy_candidates,
            mark_exit_blocked,
            mark_exit_ok,
        )
        from app.services.stealth_headers import get_stealth_headers

        direct_tries = max(1, int(getattr(settings, 'DIRECT_FETCH_MAX_TRIES', 3)))
        read_timeout = float(getattr(settings, 'DIRECT_FETCH_READ_TIMEOUT', 30.0))
        timeout_config = httpx.Timeout(connect=10.0, read=read_timeout, write=15.0, pool=10.0)

        candidates = await egress_proxy_candidates(max_candidates=direct_tries)
        if not candidates:
            candidates = [None]

        last_error = "no exits available"
        for attempt, proxy_url in enumerate(candidates, start=1):
            headers = get_stealth_headers()
            headers["Cache-Control"] = "max-age=0"
            if "web.archive.org" in content_url:
                headers["Referer"] = "https://web.archive.org/"
            client_kwargs: Dict[str, Any] = {
                "timeout": timeout_config,
                "follow_redirects": True,
                "headers": headers,
            }
            if proxy_url:
                client_kwargs["proxy"] = proxy_url
            try:
                async with httpx.AsyncClient(**client_kwargs) as client:
                    resp = await client.get(content_url)
                body = resp.text
                blocked = resp.status_code in (403, 429, 503) or looks_like_challenge(
                    resp.status_code, body
                )
                if resp.status_code == 200 and not blocked:
                    if is_browser_error_page(body):
                        raise Exception(f"Archive returned an error page for {content_url}")
                    await mark_exit_ok(proxy_url)
                    logger.info(
                        f"HTML via direct fetch (exit {attempt}/{len(candidates)}): {len(body)} chars"
                    )
                    return body
                if blocked:
                    await mark_exit_blocked(proxy_url)
                    last_error = f"HTTP {resp.status_code}"
                    logger.info(
                        f"Direct fetch blocked (HTTP {resp.status_code}) on exit "
                        f"{attempt}/{len(candidates)} for {content_url}; rotating"
                    )
                    continue
                # Non-block failure (404, other 5xx from the archive itself):
                # rotating exits won't change the answer — fail the page now.
                raise Exception(f"HTTP {resp.status_code}: {body[:300]}")
            except httpx.TimeoutException:
                await mark_exit_blocked(proxy_url)
                last_error = "timeout"
                logger.info(
                    f"Direct fetch timed out on exit {attempt}/{len(candidates)} "
                    f"for {content_url}; rotating"
                )
                continue
            except httpx.TransportError as exc:
                await mark_exit_blocked(proxy_url)
                last_error = str(exc) or type(exc).__name__
                logger.info(
                    f"Direct fetch transport error on exit {attempt}/{len(candidates)} "
                    f"for {content_url}: {last_error}; rotating"
                )
                continue

        # Every direct attempt was blocked or stalled — escalate to the browser
        # with a generous budget (a killed navigation just re-burns an exit).
        fs = get_flaresolverr_service()
        if fs.enabled:
            budget_ms = int(getattr(settings, 'FLARESOLVERR_CONTENT_TIMEOUT_MS', 55000))
            logger.info(f"Escalating to FlareSolverr after {len(candidates)} direct tries: {content_url}")
            solved = await fs.fetch_rotating(content_url, max_tries=2, max_timeout_ms=budget_ms)
            if solved:
                return solved
        raise Exception(
            f"All rotating exits blocked/failed for {content_url} (last: {last_error})"
        )

    async def extract_content(self, cdx_record: CDXRecord) -> ExtractedContent:
        """
        Extract content from a CDX record using intelligent extraction

        Args:
            cdx_record: CDX record containing URL and metadata

        Returns:
            ExtractedContent with extraction results
        """
        start_time = time.time()
        content_url = cdx_record.content_url

        self.metrics['total_requests'] += 1

        try:
            logger.info(f"Starting intelligent extraction for {content_url}")

            async with self.extraction_semaphore:
                html_content = await self._fetch_html(cdx_record, content_url)

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
                result.error = f"Extraction failed or returned minimal content: {', '.join(failure_reason)}"

            return result

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
                html_content = await self._fetch_html(cdx_record, content_url)

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
