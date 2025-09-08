#!/usr/bin/env python3
"""
Quick domain investigation to understand historical presence of hetstoerwoud.nl
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def investigate_domain():
    """Investigate the historical presence of hetstoerwoud.nl"""
    
    logger.info("="*60)
    logger.info("DOMAIN HISTORICAL INVESTIGATION")
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
    
    # Create CDX client
    cdx = cdx_toolkit.CDXFetcher(source='cc')
    cdx.session = session
    
    domain = "hetstoerwoud.nl"
    
    # 1. Check each year separately to see when domain first appeared
    years_to_check = list(range(2008, 2026))  # From 2008 to 2025
    
    domain_history = {}
    
    for year in years_to_check:
        logger.info(f"\n🔍 Checking {year} for {domain}...")
        
        try:
            from_ts = f"{year}0101"
            to_ts = f"{year}1231"
            
            # Quick check - just get first few records
            records_found = []
            count = 0
            
            for record in cdx.iter(
                url=f"*.{domain}/*",
                from_ts=from_ts,
                to_ts=to_ts,
                limit=10  # Just check if ANY records exist
            ):
                records_found.append(record)
                count += 1
                if count >= 5:  # Stop after 5 records
                    break
            
            if records_found:
                logger.info(f"   ✅ Found {len(records_found)} records in {year}")
                
                # Show sample URLs from this year
                urls = [r.get('url', '') for r in records_found[:3]]
                for url in urls:
                    timestamp = next((r.get('timestamp', '') for r in records_found if r.get('url') == url), '')
                    logger.info(f"      {url} [{timestamp}]")
                
                domain_history[year] = len(records_found)
            else:
                logger.info(f"   ❌ No records found in {year}")
                domain_history[year] = 0
                
        except Exception as e:
            logger.error(f"   ❌ Error checking {year}: {e}")
            domain_history[year] = 0
        
        # Small delay between years
        await asyncio.sleep(1)
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("DOMAIN HISTORY SUMMARY")
    logger.info("="*60)
    
    active_years = {year: count for year, count in domain_history.items() if count > 0}
    
    if active_years:
        first_year = min(active_years.keys())
        last_year = max(active_years.keys())
        
        logger.info(f"\n📅 Domain first appeared in Common Crawl: {first_year}")
        logger.info(f"📅 Most recent activity: {last_year}")
        logger.info(f"🗓️  Active years: {len(active_years)} out of {len(years_to_check)} checked")
        
        logger.info(f"\n📊 Records by year:")
        for year in sorted(active_years.keys()):
            count = active_years[year]
            logger.info(f"   {year}: {count} records (sample)")
        
        total_estimate = sum(active_years.values()) * 20  # Rough estimate since we only sampled
        logger.info(f"\n📈 Estimated total historical records: ~{total_estimate}")
        
    else:
        logger.info("\n⚠️ No historical records found for this domain")
        logger.info("This could mean:")
        logger.info("  - Domain is very new (post-2024)")
        logger.info("  - Domain was not regularly crawled by Common Crawl")
        logger.info("  - Connection/proxy issues preventing access")
    
    logger.info("="*60)


if __name__ == "__main__":
    asyncio.run(investigate_domain())