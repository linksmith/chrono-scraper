#!/usr/bin/env python3
"""
Test script for simplified scraping without complex dependencies
"""
import sys
sys.path.insert(0, '/app')

def test_manual_cdx_and_pages():
    """Test CDX discovery and page creation manually"""
    import asyncio
    from app.tasks.firecrawl_scraping import get_sync_session
    from app.models.project import Domain, ScrapeSession, Page
    from app.models.project import ScrapeSessionStatus, DomainStatus
    
    domain_id = 26
    
    print(f"Testing manual CDX discovery and page creation for domain {domain_id}")
    
    # Get domain info
    with get_sync_session() as db:
        domain = db.get(Domain, domain_id)
        if not domain:
            print(f"❌ Domain {domain_id} not found")
            return
            
        print(f"✅ Domain found: {domain.domain_name}")
        
        # Create a test scrape session
        scrape_session = ScrapeSession(
            project_id=domain.project_id,
            session_name=f"Manual test - {domain.domain_name}",
            status=ScrapeSessionStatus.PENDING,
            total_urls=0,
            completed_urls=0,
            failed_urls=0,
            cancelled_urls=0
        )
        
        db.add(scrape_session)
        db.commit()
        db.refresh(scrape_session)
        
        print(f"✅ Created test scrape session: {scrape_session.id}")
        
        # Test CDX discovery manually
        print("🔍 Testing CDX API directly...")
        
        async def test_cdx():
            try:
                from app.services.wayback_machine import CDXAPIClient
                
                async with CDXAPIClient() as client:
                    page_count = await client.get_page_count(
                        domain.domain_name, "20200101", "20241231"
                    )
                    print(f"📊 CDX pages available: {page_count}")
                    
                    if page_count > 0:
                        records, stats = await client.fetch_cdx_records(
                            domain_name=domain.domain_name,
                            from_date="20200101",
                            to_date="20241231",
                            max_pages=1
                        )
                        print(f"📄 Records found: {len(records)}")
                        print(f"📈 Stats: {stats}")
                        
                        return records[:3]  # Return first 3 for testing
                    
                return []
                
            except Exception as e:
                print(f"❌ CDX API failed: {str(e)}")
                import traceback
                traceback.print_exc()
                return []
        
        # Run CDX discovery
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            test_records = loop.run_until_complete(test_cdx())
        finally:
            loop.close()
        
        if test_records:
            print(f"\n🚀 Testing Firecrawl extraction on {len(test_records)} records...")
            
            # Test Firecrawl extraction
            pages_created = 0
            
            for i, record in enumerate(test_records):
                print(f"  Testing record {i+1}: {record.original_url}")
                
                async def test_firecrawl_extraction(cdx_record):
                    try:
                        from app.services.firecrawl_extractor import get_firecrawl_extractor
                        
                        extractor = get_firecrawl_extractor()
                        
                        # Test health first
                        health = await extractor.health_check()
                        if health.get('firecrawl_service') != 'healthy':
                            print(f"    ⚠️ Firecrawl service not healthy: {health}")
                            return None
                        
                        # Extract content
                        extracted_content = await extractor.extract_content(cdx_record)
                        
                        if extracted_content.text and len(extracted_content.text.strip()) > 50:
                            return {
                                'title': extracted_content.title,
                                'text': extracted_content.text,
                                'word_count': extracted_content.word_count,
                                'extraction_method': extracted_content.extraction_method
                            }
                        else:
                            print(f"    ⚠️ Minimal content extracted")
                            return None
                            
                    except Exception as e:
                        print(f"    ❌ Firecrawl extraction failed: {str(e)}")
                        return None
                
                # Test extraction
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    content = loop.run_until_complete(test_firecrawl_extraction(record))
                finally:
                    loop.close()
                
                if content:
                    print(f"    ✅ Content extracted: {content['word_count']} words")
                    
                    # Create page in database
                    page = Page(
                        domain_id=domain.id,
                        original_url=record.original_url,
                        wayback_url=record.wayback_url,
                        title=content['title'],
                        content=content['text'],
                        extracted_text=content['text'],
                        unix_timestamp=int(record.timestamp),
                        mime_type=record.mime_type,
                        status_code=int(record.status_code),
                        word_count=content['word_count'],
                        character_count=len(content['text']),
                        content_length=record.content_length_bytes,
                        capture_date=record.capture_date,
                        scraped_at=scrape_session.created_at,
                        processed=True,
                        indexed=False
                    )
                    
                    db.add(page)
                    pages_created += 1
                else:
                    print(f"    ❌ Content extraction failed or returned minimal content")
            
            # Commit all pages
            db.commit()
            
            # Update statistics
            domain.total_pages = len(test_records)
            domain.scraped_pages = pages_created
            scrape_session.total_urls = len(test_records)
            scrape_session.completed_urls = pages_created
            scrape_session.failed_urls = len(test_records) - pages_created
            scrape_session.status = ScrapeSessionStatus.COMPLETED
            
            db.commit()
            
            print(f"\n🎉 Manual test completed!")
            print(f"   📄 Total records: {len(test_records)}")
            print(f"   ✅ Pages created: {pages_created}")
            print(f"   ❌ Pages failed: {len(test_records) - pages_created}")
            
            return True
        else:
            print("❌ No CDX records found for testing")
            return False

if __name__ == "__main__":
    try:
        test_manual_cdx_and_pages()
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()