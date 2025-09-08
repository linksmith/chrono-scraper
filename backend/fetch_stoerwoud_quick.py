#!/usr/bin/env python3
"""
Quick fetcher for hetstoerwoud.nl - fetches recent pages only for testing.
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

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def quick_fetch_stoerwoud():
    """Quick fetch of recent hetstoerwoud.nl pages"""
    
    logger.info("="*60)
    logger.info("QUICK HETSTOERWOUD.NL FETCHER")
    logger.info("="*60)
    
    # Create output directory
    output_dir = Path("/app/stoerwoud")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Import services
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
    
    logger.info("Fetching CDX records for hetstoerwoud.nl (2024 only)...")
    
    records = []
    saved_count = 0
    
    try:
        # Query for 2024 data only (much faster)
        for record in cdx.iter(
            url="*.hetstoerwoud.nl/*",
            from_ts="202401",
            to_ts="202412",
            filter=["status:200", "mime:text/html"],
            limit=50  # Limit to 50 records for quick test
        ):
            records.append(record)
            logger.info(f"  Found: {record['url']} [{record['timestamp']}]")
            
            if len(records) >= 50:
                break
    
    except Exception as e:
        logger.error(f"CDX fetch error: {e}")
    
    logger.info(f"\nFound {len(records)} CDX records")
    
    if not records:
        logger.warning("No records found!")
        return
    
    # Process each record
    logger.info("\nFetching HTML content...")
    
    for i, record in enumerate(records[:10], 1):  # Process first 10 for quick test
        try:
            url = record['url']
            timestamp = record['timestamp']
            
            logger.info(f"\n[{i}/10] Processing {url}")
            
            # Create filename
            parsed = urlparse(url)
            path = parsed.path.strip('/') or 'index'
            slug = slugify(path, separator='_')
            filename = f"{slug}_{timestamp}.html"
            filepath = output_dir / filename
            
            # Skip if already exists
            if filepath.exists():
                logger.info(f"  Already exists: {filename}")
                continue
            
            # Try to fetch WARC content
            try:
                # Fetch from S3
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
                            html_start = content_str.find('<html')
                        
                        if html_start != -1:
                            html_content = content_str[html_start:]
                            
                            # Find HTML end
                            html_end = html_content.find('</html>')
                            if html_end != -1:
                                html_content = html_content[:html_end + 7]
                            
                            # Save file
                            with open(filepath, 'w', encoding='utf-8') as f:
                                f.write(html_content)
                            
                            saved_count += 1
                            logger.info(f"  ✅ Saved: {filename} ({len(html_content)} bytes)")
                        else:
                            logger.warning(f"  ⚠️ No HTML found in WARC")
                    else:
                        logger.warning(f"  ❌ S3 fetch failed: HTTP {response.status_code}")
                        
            except Exception as e:
                logger.error(f"  ❌ Fetch error: {e}")
                
            # Small delay
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"  ❌ Processing error: {e}")
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info(f"SUMMARY: Saved {saved_count} HTML files to {output_dir}")
    
    # List saved files
    saved_files = list(output_dir.glob("*.html"))
    if saved_files:
        logger.info(f"\nSaved files:")
        for f in saved_files[:10]:
            size = f.stat().st_size
            logger.info(f"  - {f.name} ({size} bytes)")
    
    # Create manifest
    manifest = {
        "domain": "hetstoerwoud.nl",
        "fetch_date": datetime.now().isoformat(),
        "files": [
            {
                "filename": f.name,
                "size": f.stat().st_size
            }
            for f in saved_files
        ]
    }
    
    manifest_file = output_dir / "manifest.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    logger.info(f"\nManifest saved to: {manifest_file}")
    logger.info("="*60)


if __name__ == "__main__":
    asyncio.run(quick_fetch_stoerwoud())