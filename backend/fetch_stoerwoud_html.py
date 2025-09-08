#!/usr/bin/env python3
"""
Fetch all HTML pages from hetstoerwoud.nl domain using Common Crawl proxy service.
Saves HTML files to stoerwoud directory with slugged URLs and timestamps.
"""

import asyncio
import logging
import sys
import os
import re
import gzip
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import json
from urllib.parse import urlparse
from slugify import slugify

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('fetch_stoerwoud.log')
    ]
)
logger = logging.getLogger(__name__)


class StoerwoudFetcher:
    """Fetches and saves HTML content from hetstoerwoud.nl via Common Crawl"""
    
    def __init__(self, output_dir: str = "/app/stoerwoud"):
        self.output_dir = Path(output_dir)
        self.domain = "hetstoerwoud.nl"
        self.stats = {
            "total_cdx_records": 0,
            "html_pages_found": 0,
            "successfully_downloaded": 0,
            "failed_downloads": 0,
            "saved_files": []
        }
        
    def setup_output_directory(self):
        """Create output directory if it doesn't exist"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory ready: {self.output_dir}")
        
    def create_filename(self, url: str, timestamp: str) -> str:
        """
        Create a filename from URL and timestamp.
        Example: https://hetstoerwoud.nl/about/team -> about_team_20240315120000.html
        """
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        
        # Handle homepage
        if not path:
            path = "index"
        
        # Slugify the path
        slug = slugify(path, separator='_')
        
        # Add query params if present
        if parsed.query:
            query_slug = slugify(parsed.query, separator='_')
            slug = f"{slug}_{query_slug}"
        
        # Add timestamp
        filename = f"{slug}_{timestamp}.html"
        
        return filename
    
    async def fetch_cdx_records(self) -> List:
        """Fetch all CDX records for hetstoerwoud.nl from Common Crawl"""
        from app.services.smartproxy_common_crawl_service import SmartproxyCommonCrawlService
        
        logger.info(f"Fetching CDX records for {self.domain}")
        
        all_records = []
        
        try:
            async with SmartproxyCommonCrawlService() as service:
                # Fetch records with a broad date range
                # Common Crawl has data from 2008 to present
                from_date = "20080101"  # Start from 2008
                to_date = "20251231"    # Through end of 2025
                
                logger.info(f"Date range: {from_date} - {to_date}")
                
                records, stats = await service.fetch_cdx_records_simple(
                    domain_name=self.domain,
                    from_date=from_date,
                    to_date=to_date,
                    match_type="domain",
                    page_size=1000,  # Larger batch
                    max_pages=10,     # Get more pages
                    include_attachments=False  # HTML only
                )
                
                all_records.extend(records)
                
                logger.info(f"Fetched {len(records)} CDX records")
                logger.info(f"Stats: {json.dumps(stats, indent=2)}")
                
                self.stats["total_cdx_records"] = len(records)
                
                # Filter for HTML content
                html_records = [
                    r for r in records 
                    if r.mimetype and ('html' in r.mimetype.lower() or not r.mimetype)
                ]
                
                self.stats["html_pages_found"] = len(html_records)
                logger.info(f"Found {len(html_records)} HTML pages")
                
                return html_records
                
        except Exception as e:
            logger.error(f"Failed to fetch CDX records: {e}")
            return []
    
    async def fetch_html_content_via_cdx(self, record) -> Optional[str]:
        """Fetch actual HTML content for a CDX record using cdx_toolkit"""
        import cdx_toolkit
        import requests
        from app.core.config import settings
        
        try:
            # Setup proxy session
            proxy_url = f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{settings.PROXY_SERVER.replace('http://', '')}"
            
            session = requests.Session()
            session.proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            # Create CDX client with proxy
            cdx = cdx_toolkit.CDXFetcher(source='cc')
            cdx.session = session
            
            # Try to fetch the WARC record content
            # First, we need to get the raw CDX record data
            logger.debug(f"Fetching content for {record.original_url}")
            
            # Method 1: Direct S3 fetch with decompression
            if hasattr(record, 'filename') and hasattr(record, 'offset') and hasattr(record, 'length'):
                filename = record.filename
                offset = int(record.offset)
                length = int(record.length)
                
                # Construct S3 URL
                s3_url = f"https://data.commoncrawl.org/{filename}"
                
                # Fetch with range header
                headers = {
                    'Range': f'bytes={offset}-{offset+length-1}'
                }
                
                response = session.get(s3_url, headers=headers, timeout=30)
                
                if response.status_code in [200, 206]:
                    # Parse WARC record
                    content = response.content
                    
                    # Try to extract HTML from WARC
                    html = self.extract_html_from_warc(content)
                    if html:
                        return html
                    
            # Method 2: Try Common Crawl Index API as fallback
            # Query for the specific URL and timestamp
            query_url = f"https://index.commoncrawl.org/CC-MAIN-2024-10-index?url={record.original_url}&output=json"
            
            response = session.get(query_url, timeout=30)
            if response.status_code == 200:
                lines = response.text.strip().split('\n')
                for line in lines:
                    try:
                        cdx_data = json.loads(line)
                        if cdx_data.get('timestamp') == record.timestamp:
                            # Found matching record, fetch from S3
                            s3_url = f"https://data.commoncrawl.org/{cdx_data['filename']}"
                            offset = int(cdx_data['offset'])
                            length = int(cdx_data['length'])
                            
                            headers = {'Range': f'bytes={offset}-{offset+length-1}'}
                            s3_response = session.get(s3_url, headers=headers, timeout=30)
                            
                            if s3_response.status_code in [200, 206]:
                                html = self.extract_html_from_warc(s3_response.content)
                                if html:
                                    return html
                    except json.JSONDecodeError:
                        continue
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch HTML content: {e}")
            return None
    
    def extract_html_from_warc(self, warc_content: bytes) -> Optional[str]:
        """Extract HTML from WARC record content"""
        try:
            # Try to decompress if gzipped
            try:
                decompressed = gzip.decompress(warc_content)
            except:
                decompressed = warc_content
            
            # Convert to string
            content_str = decompressed.decode('utf-8', errors='ignore')
            
            # Find HTML content (after WARC headers)
            # WARC format has headers, then two newlines, then HTTP response
            parts = content_str.split('\r\n\r\n', 2)
            
            if len(parts) >= 3:
                # Third part should be HTML after HTTP headers
                html_content = parts[2]
                
                # Basic validation - check if it looks like HTML
                if '<html' in html_content.lower() or '<!doctype' in html_content.lower():
                    return html_content
                    
            # Alternative: Look for HTML markers
            html_start = content_str.find('<!DOCTYPE')
            if html_start == -1:
                html_start = content_str.find('<html')
            
            if html_start != -1:
                return content_str[html_start:]
            
            return None
            
        except Exception as e:
            logger.debug(f"Failed to extract HTML from WARC: {e}")
            return None
    
    async def fetch_html_via_extraction(self, url: str, timestamp: str) -> Optional[str]:
        """Fetch HTML using intelligent extraction service as fallback"""
        from app.services.content_extraction_service import ContentExtractionService
        
        try:
            service = ContentExtractionService()
            
            # Create archive URL (Common Crawl doesn't use typical archive URLs)
            # We'll try to fetch directly if possible
            extracted = await service.extract_content_intelligent(url)
            
            if extracted and extracted.html_content:
                return extracted.html_content
            elif extracted and extracted.main_content:
                # Wrap text content in basic HTML
                return f"""<!DOCTYPE html>
<html>
<head>
    <title>{extracted.title or 'Retrieved from Common Crawl'}</title>
    <meta charset="utf-8">
</head>
<body>
    <h1>{extracted.title or url}</h1>
    <div class="content">
        {extracted.main_content}
    </div>
</body>
</html>"""
            
            return None
            
        except Exception as e:
            logger.debug(f"Extraction service failed: {e}")
            return None
    
    async def save_html_file(self, url: str, timestamp: str, html_content: str) -> bool:
        """Save HTML content to file"""
        try:
            filename = self.create_filename(url, timestamp)
            filepath = self.output_dir / filename
            
            # Write HTML content
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"✅ Saved: {filename} ({len(html_content)} bytes)")
            
            self.stats["saved_files"].append({
                "url": url,
                "timestamp": timestamp,
                "filename": filename,
                "size": len(html_content)
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save file: {e}")
            return False
    
    async def process_record(self, record) -> bool:
        """Process a single CDX record - fetch and save HTML"""
        url = record.original_url
        timestamp = record.timestamp
        
        logger.info(f"\nProcessing: {url} [{timestamp}]")
        
        try:
            # Try to fetch HTML content
            html_content = await self.fetch_html_content_via_cdx(record)
            
            # Fallback to extraction service if needed
            if not html_content:
                logger.info("  Trying extraction service fallback...")
                html_content = await self.fetch_html_via_extraction(url, timestamp)
            
            if html_content:
                # Save to file
                success = await self.save_html_file(url, timestamp, html_content)
                if success:
                    self.stats["successfully_downloaded"] += 1
                    return True
                else:
                    self.stats["failed_downloads"] += 1
                    return False
            else:
                logger.warning(f"  ❌ No HTML content retrieved")
                self.stats["failed_downloads"] += 1
                return False
                
        except Exception as e:
            logger.error(f"  ❌ Processing failed: {e}")
            self.stats["failed_downloads"] += 1
            return False
    
    async def run(self):
        """Main execution flow"""
        logger.info("\n" + "="*60)
        logger.info("HETSTOERWOUD.NL HTML FETCHER")
        logger.info("="*60)
        
        # Setup
        self.setup_output_directory()
        
        # Fetch CDX records
        records = await self.fetch_cdx_records()
        
        if not records:
            logger.error("No CDX records found. Exiting.")
            return
        
        # Process each record
        logger.info(f"\nProcessing {len(records)} HTML pages...")
        
        for i, record in enumerate(records, 1):
            logger.info(f"\n[{i}/{len(records)}]")
            await self.process_record(record)
            
            # Add delay to be respectful
            await asyncio.sleep(2)
            
            # Progress update every 10 records
            if i % 10 == 0:
                logger.info(f"\nProgress: {i}/{len(records)} processed")
                logger.info(f"  Successfully downloaded: {self.stats['successfully_downloaded']}")
                logger.info(f"  Failed: {self.stats['failed_downloads']}")
        
        # Final summary
        self.print_summary()
    
    def print_summary(self):
        """Print final summary of the fetching operation"""
        logger.info("\n" + "="*60)
        logger.info("FETCH SUMMARY")
        logger.info("="*60)
        
        logger.info(f"\nStatistics:")
        logger.info(f"  Total CDX records: {self.stats['total_cdx_records']}")
        logger.info(f"  HTML pages found: {self.stats['html_pages_found']}")
        logger.info(f"  Successfully downloaded: {self.stats['successfully_downloaded']}")
        logger.info(f"  Failed downloads: {self.stats['failed_downloads']}")
        
        if self.stats["saved_files"]:
            logger.info(f"\nSaved {len(self.stats['saved_files'])} files to {self.output_dir}")
            
            # Show sample files
            logger.info("\nSample saved files:")
            for file_info in self.stats["saved_files"][:5]:
                logger.info(f"  - {file_info['filename']} ({file_info['size']} bytes)")
            
            # Save manifest
            manifest_file = self.output_dir / "manifest.json"
            with open(manifest_file, 'w') as f:
                json.dump(self.stats["saved_files"], f, indent=2)
            logger.info(f"\nManifest saved to: {manifest_file}")
        
        logger.info("\n" + "="*60)


async def main():
    """Main entry point"""
    fetcher = StoerwoudFetcher()
    
    try:
        await fetcher.run()
    except KeyboardInterrupt:
        logger.info("\n\n⚠️ Fetch interrupted by user")
    except Exception as e:
        logger.error(f"\n\n❌ Unexpected error: {e}", exc_info=True)
    
    logger.info("\nLog saved to: fetch_stoerwoud.log")


if __name__ == "__main__":
    # Check if running in Docker
    if not os.path.exists("/app"):
        logger.error("This script must be run inside the Docker container")
        logger.error("Use: docker compose exec backend python fetch_stoerwoud_html.py")
        sys.exit(1)
    
    asyncio.run(main())