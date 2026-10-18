"""
Direct Common Crawl index processing service.
Bypasses CDX API entirely by downloading and processing index files directly.
"""
import asyncio
import gzip
import json
import logging
import re
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from urllib.parse import urlparse
import aiohttp
import aiofiles
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

from ..services.wayback_machine import (
    CDXRecord, WaybackMachineException, StaticAssetFilter
)

logger = logging.getLogger(__name__)


class DirectCommonCrawlException(WaybackMachineException):
    """Exception for direct Common Crawl processing"""
    pass


class CommonCrawlDirectService:
    """
    Direct Common Crawl index processing service.
    Downloads and processes index files directly, bypassing the CDX API.
    """
    
    CC_INDEX_BASE_URL = "https://data.commoncrawl.org"
    CC_CRAWL_LIST_URL = f"{CC_INDEX_BASE_URL}/crawl-data/CC-MAIN-2024-33/cc-index.paths.gz"
    
    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = Path(cache_dir or "/tmp/cc_direct_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Session for HTTP requests
        self.session = None
        
        logger.info(f"Initialized DirectCommonCrawlService with cache: {self.cache_dir}")
    
    async def __aenter__(self):
        from app.core.config import settings
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        timeout = aiohttp.ClientTimeout(total=600)  # 10 minute timeout
        proxy = None
        try:
            if settings.PROXY_SERVER and settings.PROXY_USERNAME and settings.PROXY_PASSWORD:
                server = settings.PROXY_SERVER
                if not server.startswith("http"):
                    server = f"http://{server}"
                proxy = f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{server.replace('http://','').replace('https://','')}"
        except Exception:
            proxy = None
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'Chrono-Scraper/2.0 Research Platform (+academic-research)',
                'Accept-Encoding': 'gzip, deflate'
            }
        )
        # Store proxy for use per-request
        self._proxy_url = proxy
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError, DirectCommonCrawlException)),
        before_sleep=before_sleep_log(logger, logging.INFO)
    )
    async def _download_file(self, url: str, local_path: Path) -> bool:
        """Download a file with retry logic"""
        try:
            logger.info(f"Downloading {url} to {local_path}")

            async def attempt_download(use_proxy: bool) -> bool:
                kwargs = {}
                if use_proxy and getattr(self, "_proxy_url", None):
                    kwargs["proxy"] = self._proxy_url

                # Prefer HTTPS when not using proxy
                req_url = url
                if not use_proxy:
                    req_url = url.replace("http://", "https://")

                async with self.session.get(req_url, **kwargs) as response:
                    if response.status != 200:
                        raise DirectCommonCrawlException(f"HTTP {response.status}")

                    expected = response.content_length
                    bytes_written = 0
                    async with aiofiles.open(local_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(64 * 1024):
                            bytes_written += len(chunk)
                            await f.write(chunk)

                    # Validate content length when provided
                    if expected is not None and bytes_written != expected:
                        # Remove incomplete file
                        try:
                            local_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        raise DirectCommonCrawlException(
                            f"Content length mismatch: expected {expected}, got {bytes_written}"
                        )
                    # Quick gzip integrity probe: try opening and reading a small chunk
                    try:
                        with gzip.open(local_path, 'rb') as gz:
                            _ = gz.read(1024)
                    except Exception as gz_err:
                        try:
                            local_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        raise DirectCommonCrawlException(f"Corrupt gzip after download: {gz_err}")

                    return True

            # Try via proxy first, then fall back to direct (no proxy) on failure
            try:
                return await attempt_download(use_proxy=True)
            except Exception as proxy_err:
                logger.warning(f"Proxy download failed for {url}: {proxy_err}; retrying without proxy")
                # Fallback to direct
                return await attempt_download(use_proxy=False)
                    
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            raise DirectCommonCrawlException(f"Download failed: {e}") from e
    
    async def _get_available_crawls(self) -> List[str]:
        """Get list of available Common Crawl datasets"""
        try:
            # For this implementation, we'll use a recent crawl
            # In production, you'd parse the actual crawl list
            recent_crawls = [
                "CC-MAIN-2024-33",  # August 2024
                "CC-MAIN-2024-30",  # July 2024
                "CC-MAIN-2024-26",  # June 2024
                "CC-MAIN-2024-22",  # May 2024
                "CC-MAIN-2024-18",  # April 2024
            ]
            
            logger.info(f"Using {len(recent_crawls)} recent crawl datasets")
            return recent_crawls
            
        except Exception as e:
            logger.error(f"Error getting crawl list: {e}")
            return ["CC-MAIN-2024-33"]  # Fallback to recent crawl
    
    def _build_index_url(self, crawl_id: str, segment: int = 0) -> str:
        """Build URL for a specific index file"""
        # Common Crawl index files are named like: cdx-00000.gz, cdx-00001.gz, etc.
        # Use http for proxy to avoid HTTPS CONNECT issues; fall back to https when not via proxy in downloader
        return f"{self.CC_INDEX_BASE_URL.replace('https://','http://')}/cc-index/collections/{crawl_id}/indexes/cdx-{segment:05d}.gz"
    
    def _parse_cdx_line(self, line: str) -> Optional[CDXRecord]:
        """Parse a CDX line into a CDXRecord object"""
        try:
            parts = line.strip().split(' ')
            # Common Crawl cc-index format typically: urlkey timestamp original mimetype statuscode digest length offset filename
            if len(parts) < 9:
                return None

            url_key, timestamp, original_url, mime_type, status_code, digest, length, offset, filename = parts[:9]
            
            # Basic filtering - only HTML and PDF
            if mime_type not in ['text/html', 'application/pdf']:
                return None
            
            # Only successful responses
            if not status_code.startswith('2'):
                return None
            
            # Build CDXRecord with WARC fields so downstream can fetch via S3 Range
            return CDXRecord(
                timestamp=timestamp,
                original_url=original_url,
                mime_type=mime_type,
                status_code=status_code,
                digest=digest,
                length=length or '0',
                warc_filename=filename,
                warc_offset=int(offset) if offset.isdigit() else None,
                warc_length=int(length) if (length or '').isdigit() else None,
            )
            
        except Exception as e:
            logger.debug(f"Failed to parse CDX line: {e}")
            return None
    
    def _matches_domain(self, record: CDXRecord, domain_pattern: str, match_type: str) -> bool:
        """Check if a record matches the domain pattern"""
        try:
            parsed_url = urlparse(record.original_url)
            domain = parsed_url.netloc.lower()
            
            if match_type == "exact":
                return domain == domain_pattern.lower()
            elif match_type == "domain":
                return domain.endswith(domain_pattern.lower())
            elif match_type == "prefix":
                return record.original_url.lower().startswith(domain_pattern.lower())
            elif match_type == "glob":
                # Convert glob pattern to regex
                pattern = domain_pattern.replace('*', '.*').replace('?', '.')
                return re.match(pattern.lower(), domain)
            
            return False
            
        except Exception as e:
            logger.debug(f"Error matching domain: {e}")
            return False
    
    def _filter_by_date_range(self, record: CDXRecord, from_date: str, to_date: str) -> bool:
        """Filter records by date range"""
        try:
            record_date = record.timestamp[:8]  # YYYYMMDD
            return from_date <= record_date <= to_date
        except Exception:
            return True  # Include if date parsing fails
    
    async def _process_index_file(self, crawl_id: str, segment: int, 
                                domain_pattern: str, match_type: str,
                                from_date: str, to_date: str) -> List[CDXRecord]:
        """Process a single index file for matching records"""
        index_url = self._build_index_url(crawl_id, segment)
        cache_file = self.cache_dir / f"{crawl_id}-{segment:05d}.gz"
        
        try:
            # Download if not cached
            if not cache_file.exists():
                success = await self._download_file(index_url, cache_file)
                if not success:
                    return []
            
            # Process the compressed file
            matching_records = []
            
            logger.info(f"Processing index file: {cache_file}")
            
            # Process the compressed file directly
            # Decompress and process line by line
            try:
                with gzip.open(cache_file, 'rt', encoding='utf-8') as gz_file:
                    for line_num, line in enumerate(gz_file):
                        if line_num % 100000 == 0 and line_num > 0:
                            logger.info(f"Processed {line_num} lines, found {len(matching_records)} matches")
                        
                        record = self._parse_cdx_line(line)
                        if not record:
                            continue
                        
                        # Apply filters
                        if not self._matches_domain(record, domain_pattern, match_type):
                            continue
                        
                        if not self._filter_by_date_range(record, from_date, to_date):
                            continue
                        
                        matching_records.append(record)
                        
                        # Limit results to prevent memory issues
                        if len(matching_records) >= 10000:  # Max 10k records per segment
                            logger.info(f"Reached 10k limit for segment {segment}")
                            break
            except Exception as gz_err:
                logger.error(f"Gzip processing error for {cache_file}: {gz_err}; re-downloading without proxy")
                # Delete and re-download (will try proxy then fall back to direct inside downloader)
                try:
                    cache_file.unlink(missing_ok=True)
                except Exception:
                    pass
                # Force a fresh download
                success = await self._download_file(index_url, cache_file)
                if not success:
                    return []
                # Retry processing once
                with gzip.open(cache_file, 'rt', encoding='utf-8') as gz_file:
                    for line_num, line in enumerate(gz_file):
                        if line_num % 100000 == 0 and line_num > 0:
                            logger.info(f"Processed {line_num} lines, found {len(matching_records)} matches")
                        record = self._parse_cdx_line(line)
                        if not record:
                            continue
                        if not self._matches_domain(record, domain_pattern, match_type):
                            continue
                        if not self._filter_by_date_range(record, from_date, to_date):
                            continue
                        matching_records.append(record)
                        if len(matching_records) >= 10000:
                            logger.info(f"Reached 10k limit for segment {segment}")
                            break
            
            logger.info(f"Found {len(matching_records)} matching records in segment {segment}")
            return matching_records
            
        except Exception as e:
            logger.error(f"Error processing index file {index_url}: {e}")
            return []
    
    # Common Crawl CDX Index API. Returns CDX records for a domain directly as
    # NDJSON — the correct, fast lookup (the old raw-shard download approach read
    # arbitrary index segments, not the shard holding the target domain, so it
    # returned 0 for any specific domain and took minutes).
    CC_COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"
    _collinfo_cache: Optional[list] = None

    async def _get_collinfo(self) -> list:
        if CommonCrawlDirectService._collinfo_cache is not None:
            return CommonCrawlDirectService._collinfo_cache
        # CC index/CDN is not rate-limited and doesn't block datacenter IPs, so
        # query it directly (a VPN proxy only slows these large reads down).
        async with self.session.get(self.CC_COLLINFO_URL, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            resp.raise_for_status()
            CommonCrawlDirectService._collinfo_cache = await resp.json(content_type=None)
        return CommonCrawlDirectService._collinfo_cache

    @staticmethod
    def _collection_year(collection_id: str) -> Optional[int]:
        m = re.search(r"CC-MAIN-(\d{4})", collection_id or "")
        return int(m.group(1)) if m else None

    @staticmethod
    def _collection_window(col: dict) -> Optional[Tuple[str, str]]:
        """(YYYYMMDD start, YYYYMMDD end) of a crawl from collinfo's from/to, if present."""
        try:
            return col["from"][:10].replace("-", ""), col["to"][:10].replace("-", "")
        except (KeyError, TypeError, AttributeError):
            return None

    async def _collections_for_range(self, from_date: str, to_date: str, cap: Optional[int] = None) -> list:
        """
        Every crawl whose capture window overlaps [from_date, to_date], newest first.

        A crawl only contains captures made while it ran, so a crawl outside the
        window can be skipped without losing records. Crawls without from/to in
        collinfo fall back to a year overlap test. ``cap`` is an optional hard limit.
        """
        info = await self._get_collinfo()
        fd, td = (from_date or "")[:8] or "00000000", (to_date or "")[:8] or "99999999"
        selected = []
        for col in info:
            window = self._collection_window(col)
            if window:
                if window[0] <= td and window[1] >= fd:
                    selected.append(col)
                continue
            year = self._collection_year(col.get("id", ""))
            if year is not None and fd[:4] <= str(year) <= td[:4]:
                selected.append(col)
        selected.sort(key=lambda c: (self._collection_window(c) or ("", ""))[0], reverse=True)
        return selected[:cap] if cap else selected

    async def _get_index_text(self, cdx_api: str, params: list) -> Optional[str]:
        """
        GET one CC index API request, politely retrying 429/5xx/timeouts with
        exponential backoff (honouring Retry-After). Returns None when the query
        has no captures (404); raises DirectCommonCrawlException once retries are spent.
        """
        from app.core.config import settings
        max_tries = max(1, int(settings.CC_INDEX_MAX_RETRIES))
        last_error = "unknown error"
        for attempt in range(1, max_tries + 1):
            delay = min(60.0, 2.0 ** attempt)
            try:
                async with self.session.get(cdx_api, params=params,
                                            timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status == 200:
                        return await resp.text()
                    if resp.status == 404:
                        return None  # CC answers 404 when a query has no captures
                    last_error = f"HTTP {resp.status}"
                    if resp.status in (429, 500, 502, 503, 504):
                        retry_after = resp.headers.get("Retry-After", "")
                        if retry_after.isdigit():
                            delay = min(120.0, float(retry_after))
                    else:
                        raise DirectCommonCrawlException(f"CC index {cdx_api}: HTTP {resp.status}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            if attempt < max_tries:
                logger.info(f"CC index {cdx_api} {last_error}; retry {attempt}/{max_tries - 1} in {delay:.0f}s")
                await asyncio.sleep(delay)
        raise DirectCommonCrawlException(f"CC index {cdx_api} failed after {max_tries} tries: {last_error}")

    @staticmethod
    def _index_params(query_url: str, match_type: str, from_date: str, to_date: str,
                      include_attachments: bool) -> list:
        mime_filter = "~mime:(text/html|application/pdf)" if include_attachments else "mime:text/html"
        return [
            ("url", query_url),
            ("matchType", match_type),
            ("output", "json"),
            ("from", from_date),
            ("to", to_date),
            ("filter", mime_filter),
            ("filter", "=status:200"),
        ]

    @staticmethod
    def _record_from_index_line(line: str) -> Optional[CDXRecord]:
        try:
            d = json.loads(line)
        except Exception:
            return None
        if not isinstance(d, dict) or not d.get("url"):
            return None  # e.g. {"message": "No Captures found ..."}
        return CDXRecord.from_common_crawl_response({
            "timestamp": d.get("timestamp", ""),
            "url": d.get("url", ""),
            "mimetype": d.get("mime", d.get("mime-detected", "")),
            "statuscode": d.get("status", ""),
            "digest": d.get("digest", ""),
            "length": d.get("length", ""),
            "filename": d.get("filename"),
            "offset": int(d["offset"]) if d.get("offset") else None,
            "warc_length": int(d["length"]) if d.get("length") else None,
        })

    async def _query_index_api(self, cdx_api: str, query_url: str, match_type: str,
                               from_date: str, to_date: str, limit: int,
                               include_attachments: bool = False) -> List[CDXRecord]:
        """All matching records of one crawl, following the index API's page numbering."""
        params = self._index_params(query_url, match_type, from_date, to_date, include_attachments)
        head = await self._get_index_text(cdx_api, params + [("showNumPages", "true")])
        if head is None:
            return []
        try:
            num_pages = int(json.loads(head).get("pages", 0))
        except (ValueError, AttributeError):
            raise DirectCommonCrawlException(f"CC index {cdx_api}: unreadable page count: {head[:120]!r}")

        records: List[CDXRecord] = []
        for page in range(num_pages):
            text = await self._get_index_text(cdx_api, params + [("page", str(page))])
            if text is None:
                continue
            for line in text.splitlines():
                rec = self._record_from_index_line(line) if line else None
                if rec:
                    records.append(rec)
            if len(records) >= limit:
                break
        return records[:limit]

    async def fetch_warc_html(self, filename: str, offset, length) -> Optional[str]:
        """
        Fetch a single record's HTML from a Common Crawl WARC file via an HTTP
        range request, straight from data.commoncrawl.org.

        CC's WARC store is a public, un-rate-limited CDN, so this goes direct (no
        Mullvad/FlareSolverr) — the VPN would only slow the range read and the CDN
        never blocks datacenter IPs. Each CC WARC record is individually gzipped
        and contains WARC headers + the HTTP response; we return the HTML body.
        """
        if not filename or offset is None or length is None:
            return None
        import io
        s3_url = f"{self.CC_INDEX_BASE_URL}/{filename}"
        try:
            start = int(offset)
            end = start + int(length) - 1
        except (TypeError, ValueError):
            return None
        headers = {"Range": f"bytes={start}-{end}"}
        try:
            async with self.session.get(s3_url, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status not in (200, 206):
                    logger.debug(f"WARC fetch {s3_url} -> HTTP {resp.status}")
                    return None
                raw = await resp.read()
        except Exception as exc:
            logger.warning(f"WARC fetch failed for {filename}: {exc}")
            return None

        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
                data = gz.read()
        except Exception:
            data = raw

        text = data.decode("utf-8", errors="ignore")
        # The record is WARC headers + HTTP headers + body; slice from the HTML.
        for marker in ("<!DOCTYPE", "<!doctype", "<html", "<HTML"):
            idx = text.find(marker)
            if idx != -1:
                html = text[idx:]
                end_idx = html.lower().rfind("</html>")
                return html[: end_idx + 7] if end_idx != -1 else html
        return None

    async def fetch_cdx_records_simple(self, domain_name: str, from_date: str, to_date: str,
                                     match_type: str = "domain", url_path: Optional[str] = None,
                                     page_size: int = None, max_pages: Optional[int] = None,
                                     include_attachments: bool = True) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """
        Fetch CDX records via the Common Crawl CDX Index API, querying every crawl
        that overlaps the date range (bounded by CC_INDEX_PARALLELISM) and paging
        through each crawl's results. ``page_size`` is the record cap (default
        DISCOVERY_MAX_RECORDS); ``max_pages`` is accepted for interface compatibility.
        Raises DirectCommonCrawlException if the index could not be queried at all.
        """
        from app.core.config import settings
        started = time.monotonic()
        logger.info(f"Starting Common Crawl index-API lookup for {domain_name} ({from_date}..{to_date})")

        stats = {"total_pages": 0, "fetched_pages": 0, "total_records": 0, "final_count": 0,
                 "failed_collections": 0}

        try:
            collections = [c for c in await self._collections_for_range(from_date, to_date) if c.get("cdx-api")]
            max_records = page_size or settings.DISCOVERY_MAX_RECORDS
            # For prefix matches, query the specific URL path; otherwise the domain.
            query_url = url_path if (match_type == "prefix" and url_path) else domain_name
            cc_match = "prefix" if match_type == "prefix" else "domain"
            sem = asyncio.Semaphore(max(1, int(settings.CC_INDEX_PARALLELISM)))

            async def query_collection(col: dict) -> Tuple[dict, Optional[List[CDXRecord]]]:
                async with sem:
                    try:
                        recs = await self._query_index_api(
                            col["cdx-api"], query_url, cc_match, from_date, to_date,
                            max_records, include_attachments,
                        )
                        logger.info(f"CC {col.get('id')}: {len(recs)} records for {domain_name}")
                        return col, recs
                    except Exception as exc:
                        logger.warning(f"CC {col.get('id')} failed for {domain_name}: {exc}")
                        return col, None

            results = await asyncio.gather(*(query_collection(c) for c in collections))
            if collections and all(recs is None for _, recs in results):
                raise DirectCommonCrawlException(
                    f"Common Crawl index unavailable: all {len(collections)} crawl queries failed for {domain_name}"
                )

            # Newest crawl first; a (url, timestamp) pair is unique across crawls.
            all_records: List[CDXRecord] = []
            seen = set()
            for col, recs in results:
                if recs is None:
                    stats["failed_collections"] += 1
                    continue
                stats["fetched_pages"] += 1
                for rec in recs:
                    key = (rec.original_url, rec.timestamp)
                    if key not in seen:
                        seen.add(key)
                        all_records.append(rec)
            if len(all_records) > max_records:
                all_records = all_records[:max_records]

            filtered_records, _ = StaticAssetFilter.filter_static_assets(all_records)
            stats.update({
                "total_pages": len(collections),
                "total_records": len(all_records),
                "final_count": len(filtered_records),
            })
            logger.info(
                f"CC index-API lookup for {domain_name}: {len(filtered_records)} records from "
                f"{stats['fetched_pages']}/{len(collections)} crawls "
                f"({stats['failed_collections']} failed) in {time.monotonic() - started:.1f}s"
            )
            return filtered_records, stats

        except Exception as e:
            logger.error(f"Common Crawl index-API lookup failed for {domain_name}: {e}")
            raise


# Export for use in other modules
__all__ = [
    'CommonCrawlDirectService',
    'DirectCommonCrawlException'
]