#!/usr/bin/env python3
"""
Complete historical fetcher for hetstoerwoud.nl - gets ALL pages from ALL time periods.
Fetches every single page Common Crawl has ever archived for this domain.
"""

import asyncio
import logging
import sys
import os
from pathlib import Path
from datetime import datetime
import json
import gzip
import io
from slugify import slugify
from urllib.parse import urlparse
from typing import List, Dict, Set, Optional
import time

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('fetch_stoerwoud_complete.log')
    ]
)
logger = logging.getLogger(__name__)


class CompleteStoerwoudFetcher:
    """Fetches ALL historical HTML content from hetstoerwoud.nl via Common Crawl"""
    
    def __init__(self, output_dir: str = "/app/stoerwoud"):
        self.output_dir = Path(output_dir)
        self.domain = "hetstoerwoud.nl"
        self.all_records = []
        self.unique_urls = {}  # URL -> list of timestamps
        self.stats = {
            "total_cdx_records": 0,
            "unique_urls": 0,
            "successfully_downloaded": 0,
            "failed_downloads": 0,
            "earliest_date": None,
            "latest_date": None,
            "year_coverage": {}
        }
        
    def setup_output_directory(self):
        """Create output directory if it doesn't exist"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory ready: {self.output_dir}")
        
    async def fetch_all_cdx_records(self) -> List:
        """Fetch ALL CDX records for hetstoerwoud.nl from Common Crawl's entire history"""
        
        logger.info("="*60)
        logger.info("FETCHING COMPLETE HISTORICAL ARCHIVE")
        logger.info("="*60)
        
        import cdx_toolkit
        import requests
        from app.core.config import settings
        
        # Setup proxy
        proxy_url = f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{settings.PROXY_SERVER.replace('http://', '')}"
        
        session = requests.Session()
        session.proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Create CDX client
        cdx = cdx_toolkit.CDXFetcher(source='cc')
        cdx.session = session
        
        logger.info(f"Querying ALL Common Crawl indexes for {self.domain}")
        logger.info("This will search from 2008 to present...")
        
        all_records = []
        
        try:
            # Query with explicit date range to get EVERYTHING from 2008 onwards
            # Common Crawl started in 2008, so this gets all historical data
            logger.info("Starting comprehensive CDX query (2008-present)...")
            
            count = 0
            for record in cdx.iter(
                url=f"*.{self.domain}/*",  # Get all subdomains and paths
                from_ts="20080101",  # Start from 2008 when Common Crawl began
                to_ts="20991231",    # Far future date to get everything
                filter=["status:200"],  # Only successful responses
                collapse=None,  # Don't collapse - we want all versions
                limit=10000  # High limit to get everything
            ):
                all_records.append(record)
                count += 1
                
                # Log progress
                if count % 100 == 0:
                    logger.info(f"  Retrieved {count} records so far...")
                
                # Process the record to track unique URLs and dates
                url = record.get('url', '')
                timestamp = record.get('timestamp', '')
                
                if url not in self.unique_urls:
                    self.unique_urls[url] = []
                self.unique_urls[url].append(timestamp)
                
                # Track year coverage
                if timestamp and len(timestamp) >= 4:
                    year = timestamp[:4]
                    self.stats["year_coverage"][year] = self.stats["year_coverage"].get(year, 0) + 1
                
                # Update earliest/latest dates
                if timestamp:
                    if not self.stats["earliest_date"] or timestamp < self.stats["earliest_date"]:
                        self.stats["earliest_date"] = timestamp
                    if not self.stats["latest_date"] or timestamp > self.stats["latest_date"]:
                        self.stats["latest_date"] = timestamp
                
                # Add small delay every 500 records to be respectful
                if count % 500 == 0:
                    await asyncio.sleep(2)
                    
        except Exception as e:
            logger.error(f"Error during CDX fetch: {e}")
        
        logger.info(f"\n✅ Retrieved {len(all_records)} total CDX records")
        logger.info(f"   Unique URLs found: {len(self.unique_urls)}")
        
        if self.stats["earliest_date"] and self.stats["latest_date"]:
            logger.info(f"   Date range: {self.stats['earliest_date'][:8]} to {self.stats['latest_date'][:8]}")
        
        # Show year coverage
        if self.stats["year_coverage"]:
            logger.info("\n📊 Year Coverage:")
            for year in sorted(self.stats["year_coverage"].keys()):
                count = self.stats["year_coverage"][year]
                logger.info(f"   {year}: {count} captures")
        
        # Show URL diversity
        logger.info(f"\n📝 URL Diversity:")
        sample_urls = list(self.unique_urls.keys())[:10]
        for url in sample_urls:
            capture_count = len(self.unique_urls[url])
            logger.info(f"   {url}: {capture_count} captures")
        
        if len(self.unique_urls) > 10:
            logger.info(f"   ... and {len(self.unique_urls) - 10} more unique URLs")
        
        self.all_records = all_records
        self.stats["total_cdx_records"] = len(all_records)
        self.stats["unique_urls"] = len(self.unique_urls)
        
        return all_records
    
    def create_filename(self, url: str, timestamp: str) -> str:
        """Create a filename from URL and timestamp"""
        parsed = urlparse(url)
        
        # Include subdomain if present
        host_parts = parsed.netloc.replace('www.', '').replace('.', '_')
        
        # Handle path
        path = parsed.path.strip('/')
        if not path:
            path = "index"
        
        # Slugify the complete URL structure
        full_slug = slugify(f"{host_parts}_{path}", separator='_')
        
        # Add query params if present
        if parsed.query:
            query_slug = slugify(parsed.query, separator='_')[:30]  # Limit query length
            full_slug = f"{full_slug}_{query_slug}"
        
        # Add timestamp
        filename = f"{full_slug}_{timestamp}.html"
        
        return filename
    
    async def fetch_html_content(self, record) -> Optional[str]:
        """Fetch actual HTML content for a CDX record"""
        import requests
        from app.core.config import settings
        import gzip
        import io
        
        try:
            # Setup proxy session
            proxy_url = f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{settings.PROXY_SERVER.replace('http://', '')}"
            
            session = requests.Session()
            session.proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            # Try to fetch from S3
            if 'filename' in record and 'offset' in record and 'length' in record:
                s3_url = f"https://data.commoncrawl.org/{record['filename']}"
                offset = int(record['offset'])
                length = int(record['length'])
                
                headers = {'Range': f'bytes={offset}-{offset+length-1}'}
                response = session.get(s3_url, headers=headers, timeout=30)
                
                if response.status_code in [200, 206]:
                    # Extract HTML from WARC
                    warc_data = response.content
                    
                    # Try to decompress
                    try:
                        with gzip.GzipFile(fileobj=io.BytesIO(warc_data)) as gz:
                            decompressed = gz.read()
                    except:
                        decompressed = warc_data
                    
                    # Convert to string and find HTML
                    content_str = decompressed.decode('utf-8', errors='ignore')
                    
                    # Find HTML start
                    html_start = content_str.find('<!DOCTYPE')
                    if html_start == -1:
                        html_start = content_str.find('<!doctype')
                    if html_start == -1:
                        html_start = content_str.find('<html')
                    if html_start == -1:
                        html_start = content_str.find('<HTML')
                    
                    if html_start != -1:
                        html_content = content_str[html_start:]
                        
                        # Find HTML end
                        html_end = html_content.find('</html>')
                        if html_end == -1:
                            html_end = html_content.find('</HTML>')
                        
                        if html_end != -1:
                            html_content = html_content[:html_end + 7]
                        
                        return html_content
                    
            return None
            
        except Exception as e:
            logger.debug(f"Failed to fetch HTML: {e}")
            return None
    
    async def process_all_records(self):
        """Process all CDX records and download HTML"""
        
        if not self.all_records:
            logger.warning("No records to process!")
            return
        
        logger.info("\n" + "="*60)
        logger.info(f"PROCESSING {len(self.all_records)} RECORDS")
        logger.info("="*60)
        
        # Filter for HTML content
        html_records = [
            r for r in self.all_records 
            if r.get('mime', '').lower() in ['text/html', 'text/htm', ''] or 
               'html' in r.get('mime', '').lower()
        ]
        
        logger.info(f"Found {len(html_records)} HTML records to process")
        
        # Process records in batches to avoid overwhelming
        batch_size = 50
        total_saved = 0
        
        for i in range(0, len(html_records), batch_size):
            batch = html_records[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(html_records) + batch_size - 1) // batch_size
            
            logger.info(f"\n📦 Processing batch {batch_num}/{total_batches}")
            
            for j, record in enumerate(batch, 1):
                try:
                    url = record.get('url', '')
                    timestamp = record.get('timestamp', '')
                    
                    # Create filename
                    filename = self.create_filename(url, timestamp)
                    filepath = self.output_dir / filename
                    
                    # Skip if already exists
                    if filepath.exists():
                        logger.debug(f"  [{j}] Already exists: {filename}")
                        continue
                    
                    logger.info(f"  [{j}] Fetching: {url} [{timestamp[:8]}]")
                    
                    # Fetch HTML content
                    html_content = await self.fetch_html_content(record)
                    
                    if html_content:
                        # Save file
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                        
                        total_saved += 1
                        self.stats["successfully_downloaded"] += 1
                        logger.info(f"      ✅ Saved: {filename} ({len(html_content)} bytes)")
                    else:
                        self.stats["failed_downloads"] += 1
                        logger.debug(f"      ❌ No HTML content retrieved")
                    
                    # Small delay between downloads
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"  Error processing record: {e}")
                    self.stats["failed_downloads"] += 1
            
            # Pause between batches
            if i + batch_size < len(html_records):
                logger.info(f"  Pausing before next batch... (saved {total_saved} files so far)")
                await asyncio.sleep(5)
        
        logger.info(f"\n✅ Total files saved: {total_saved}")
    
    async def run(self):
        """Main execution flow"""
        start_time = time.time()
        
        logger.info("\n" + "="*60)
        logger.info("COMPLETE HISTORICAL FETCHER FOR HETSTOERWOUD.NL")
        logger.info("="*60)
        
        # Setup
        self.setup_output_directory()
        
        # Fetch ALL CDX records
        await self.fetch_all_cdx_records()
        
        # Process and download all HTML
        await self.process_all_records()
        
        # Generate comprehensive report
        self.generate_report()
        
        elapsed = time.time() - start_time
        logger.info(f"\n⏱️ Total execution time: {elapsed:.2f} seconds")
    
    def generate_report(self):
        """Generate comprehensive report of the fetching operation"""
        
        # Count saved files
        saved_files = list(self.output_dir.glob("*.html"))
        
        # Group files by year
        files_by_year = {}
        for f in saved_files:
            # Extract timestamp from filename (last part before .html)
            parts = f.stem.split('_')
            if parts:
                timestamp = parts[-1]
                if len(timestamp) >= 4:
                    year = timestamp[:4]
                    if year not in files_by_year:
                        files_by_year[year] = []
                    files_by_year[year].append(f.name)
        
        # Create detailed report
        report = {
            "domain": self.domain,
            "fetch_date": datetime.now().isoformat(),
            "statistics": {
                "total_cdx_records": self.stats["total_cdx_records"],
                "unique_urls": self.stats["unique_urls"],
                "successfully_downloaded": self.stats["successfully_downloaded"],
                "failed_downloads": self.stats["failed_downloads"],
                "total_files_saved": len(saved_files),
                "earliest_capture": self.stats["earliest_date"],
                "latest_capture": self.stats["latest_date"]
            },
            "year_coverage": self.stats["year_coverage"],
            "files_by_year": {year: len(files) for year, files in files_by_year.items()},
            "sample_files": [
                {
                    "filename": f.name,
                    "size": f.stat().st_size
                }
                for f in saved_files[:20]  # First 20 files as sample
            ]
        }
        
        # Save report
        report_file = self.output_dir / "complete_archive_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Print summary
        logger.info("\n" + "="*60)
        logger.info("FINAL SUMMARY")
        logger.info("="*60)
        
        logger.info(f"\n📊 Archive Statistics:")
        logger.info(f"   Total CDX records found: {self.stats['total_cdx_records']}")
        logger.info(f"   Unique URLs: {self.stats['unique_urls']}")
        logger.info(f"   Files saved: {len(saved_files)}")
        logger.info(f"   Failed downloads: {self.stats['failed_downloads']}")
        
        if self.stats["earliest_date"] and self.stats["latest_date"]:
            logger.info(f"\n📅 Date Coverage:")
            logger.info(f"   Earliest: {self.stats['earliest_date'][:8]}")
            logger.info(f"   Latest: {self.stats['latest_date'][:8]}")
        
        if files_by_year:
            logger.info(f"\n📁 Files by Year:")
            for year in sorted(files_by_year.keys()):
                logger.info(f"   {year}: {len(files_by_year[year])} files")
        
        logger.info(f"\n📄 Report saved to: {report_file}")
        logger.info("="*60)


async def main():
    """Main entry point"""
    fetcher = CompleteStoerwoudFetcher()
    
    try:
        await fetcher.run()
    except KeyboardInterrupt:
        logger.info("\n\n⚠️ Fetch interrupted by user")
    except Exception as e:
        logger.error(f"\n\n❌ Unexpected error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())