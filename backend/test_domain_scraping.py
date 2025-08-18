#!/usr/bin/env python3
"""
Test script to trigger scraping for a specific domain
"""
import sys
sys.path.insert(0, '/app')

from app.tasks.firecrawl_scraping import start_domain_scrape_simple, scrape_domain_with_firecrawl

def test_domain_scraping():
    """Test Firecrawl-only scraping for domain 26 (hetstoerwoud.nl)"""
    domain_id = 26
    
    print(f"Starting Firecrawl-only scraping for domain {domain_id}...")
    
    try:
        # Use the simplified task that handles session creation
        task_id = start_domain_scrape_simple.delay(domain_id)
        result = task_id  # For compatibility
        
        print(f"✅ Scraping task started with ID: {result.id}")
        print(f"You can monitor progress at: http://localhost:5555")
        print(f"Task ID: {result.id}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to start scraping: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_domain_scraping()