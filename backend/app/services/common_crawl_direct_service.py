"""
Direct Common Crawl index processing service.
Bypasses CDX API entirely by downloading and processing index files directly.
"""
import asyncio
import gzip
import logging
import re
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
    
    async def fetch_cdx_records_simple(self, domain_name: str, from_date: str, to_date: str,
                                     match_type: str = "domain", url_path: Optional[str] = None,
                                     page_size: int = None, max_pages: Optional[int] = None,
                                     include_attachments: bool = True) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """
        Fetch CDX records by processing index files directly.
        Compatible interface with CommonCrawlService.
        """
        logger.info(f"Starting direct Common Crawl processing for {domain_name}")
        
        stats = {
            "total_pages": 0,
            "fetched_pages": 0,
            "total_records": 0,
            "final_count": 0
        }
        
        try:
            # Get available crawls
            crawls = await self._get_available_crawls()
            
            all_records = []
            max_records = page_size or 5000
            
            # Process crawls until we have enough records
            for crawl_id in crawls:
                logger.info(f"Processing crawl: {crawl_id}")
                
                # Process first few segments (index files are large)
                segments_to_process = min(max_pages or 3, 5)  # Limit segments
                
                for segment in range(segments_to_process):
                    if len(all_records) >= max_records:
                        break
                    
                    segment_records = await self._process_index_file(
                        crawl_id, segment, domain_name, match_type, from_date, to_date
                    )
                    
                    all_records.extend(segment_records)
                    stats["fetched_pages"] += 1
                    
                    # Respect politeness - delay between segments
                    await asyncio.sleep(2)
                
                if len(all_records) >= max_records:
                    break
            
            # Limit results
            if len(all_records) > max_records:
                all_records = all_records[:max_records]
            
            # Apply additional filtering
            filtered_records, static_assets_filtered = StaticAssetFilter.filter_static_assets(
                all_records
            )
            
            stats.update({
                "total_pages": len(crawls),
                "total_records": len(all_records),
                "final_count": len(filtered_records)
            })
            
            logger.info(f"Direct processing complete: {len(filtered_records)} records "
                       f"from {stats['fetched_pages']} segments")
            
            return filtered_records, stats
            
        except Exception as e:
            logger.error(f"Direct Common Crawl processing failed for {domain_name}: {e}")
            return [], stats


# Export for use in other modules
__all__ = [
    'CommonCrawlDirectService',
    'DirectCommonCrawlException'
]