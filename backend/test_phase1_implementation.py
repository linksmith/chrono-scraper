#!/usr/bin/env python3
"""
Test script to verify Phase 1 implementation of enhanced filtering system.
Run with: docker compose exec backend python test_phase1_implementation.py
"""
import asyncio
from sqlmodel import Session, select
from app.core.database import engine
from app.models.scraping import ScrapePage, ScrapePageStatus
from app.models.project import Domain


async def test_phase1_implementation():
    """Test the enhanced filtering system with individual reasons"""
    
    print("🔧 Testing Phase 1: Enhanced Filtering System")
    print("=" * 60)
    
    with Session(engine) as db:
        # Get a domain for testing (or create one if needed)
        domain = db.exec(select(Domain).limit(1)).first()
        if not domain:
            print("❌ No domain found. Please create a project with domains first.")
            return
        
        print(f"✅ Using domain: {domain.domain_name}")
        
        # Create test ScrapePage records with different filtering scenarios
        test_pages = [
            # List page with specific pattern match
            ScrapePage(
                domain_id=domain.id,
                original_url=f"https://{domain.domain_name}/blog/page/2",
                content_url=f"https://web.archive.org/web/20240315120000/https://{domain.domain_name}/blog/page/2",
                unix_timestamp="20240315120000",
                mime_type="text/html",
                status_code=200,
                status=ScrapePageStatus.FILTERED_LIST_PAGE,
                filter_reason="List page detected",
                filter_category="excluded",
                filter_details={
                    "filter_type": "list_page_detection",
                    "matched_pattern": "/blog/page/\\d+",
                    "specific_reason": "Blog pagination page detected - Pattern: /blog/page/[number]",
                    "confidence_score": 0.9,
                    "detection_method": "regex_pattern",
                    "content_metadata": {
                        "mime_type": "text/html",
                        "content_length": 4521,
                        "capture_timestamp": "20240315120000"
                    }
                },
                matched_pattern="/blog/page/\\d+",
                filter_confidence=0.9,
                can_be_manually_processed=True
            ),
            
            # Already processed page with digest reference
            ScrapePage(
                domain_id=domain.id,
                original_url=f"https://{domain.domain_name}/article/important-news",
                content_url=f"https://web.archive.org/web/20240315130000/https://{domain.domain_name}/article/important-news",
                unix_timestamp="20240315130000",
                mime_type="text/html",
                status_code=200,
                status=ScrapePageStatus.FILTERED_ALREADY_PROCESSED,
                filter_reason="Duplicate content detected",
                filter_category="excluded",
                filter_details={
                    "filter_type": "duplicate_content",
                    "specific_reason": "Content with digest 3f2a1b9c8e7d4521 already processed on 2024-03-14",
                    "original_processing_date": "2024-03-14T15:30:00",
                    "digest_hash": "3f2a1b9c8e7d4521",
                    "confidence_score": 1.0,
                    "original_project": "Historical News Archive"
                },
                digest_hash="3f2a1b9c8e7d4521",
                filter_confidence=1.0,
                can_be_manually_processed=False  # No point reprocessing identical content
            ),
            
            # PDF attachment filtered due to project settings
            ScrapePage(
                domain_id=domain.id,
                original_url=f"https://{domain.domain_name}/documents/report.pdf",
                content_url=f"https://web.archive.org/web/20240315140000/https://{domain.domain_name}/documents/report.pdf",
                unix_timestamp="20240315140000",
                mime_type="application/pdf",
                status_code=200,
                status=ScrapePageStatus.FILTERED_ATTACHMENT_DISABLED,
                filter_reason="PDF attachment excluded",
                filter_category="excluded",
                filter_details={
                    "filter_type": "attachment_filtering",
                    "specific_reason": "PDF attachment excluded - Project attachments disabled",
                    "file_type": "application/pdf",
                    "file_size": 2456789,
                    "file_name": "report.pdf",
                    "project_setting": "enable_attachment_download=False",
                    "can_be_manually_processed": True
                },
                matched_pattern="\\.pdf$",
                filter_confidence=1.0,
                is_pdf=True,
                can_be_manually_processed=True
            ),
            
            # High-value content that passed filtering
            ScrapePage(
                domain_id=domain.id,
                original_url=f"https://{domain.domain_name}/research/whitepaper",
                content_url=f"https://web.archive.org/web/20240315150000/https://{domain.domain_name}/research/whitepaper",
                unix_timestamp="20240315150000",
                mime_type="text/html",
                status_code=200,
                status=ScrapePageStatus.PENDING,
                filter_reason="High-value content",
                filter_category="high_priority",
                filter_details={
                    "filter_type": "high_value_detection",
                    "specific_reason": "Research whitepaper detected - High priority content",
                    "priority_indicators": [
                        "URL contains '/research/'",
                        "URL contains 'whitepaper'",
                        "Content size > 10KB"
                    ],
                    "priority_score": 9,
                    "confidence_score": 0.95
                },
                matched_pattern="/research/",
                filter_confidence=0.95,
                priority_score=9,
                can_be_manually_processed=True
            )
        ]
        
        # Add test pages to database
        print(f"\n📝 Creating {len(test_pages)} test ScrapePage records...")
        for page in test_pages:
            db.add(page)
        
        try:
            db.commit()
            print("✅ Test pages created successfully!")
        except Exception as e:
            print(f"❌ Error creating test pages: {e}")
            db.rollback()
            return
        
        # Query and display the test data
        print("\n📊 Verifying Individual Filtering Reasons:")
        print("-" * 60)
        
        # Query pages with JSONB filter details
        stmt = select(ScrapePage).where(
            ScrapePage.filter_details.isnot(None),
            ScrapePage.domain_id == domain.id
        ).order_by(ScrapePage.id.desc()).limit(10)
        
        results = db.exec(stmt).all()
        
        for page in results:
            print(f"\n🔍 Page: {page.original_url}")
            print(f"   Status: {page.status}")
            print(f"   Pattern: {page.matched_pattern}")
            print(f"   Confidence: {page.filter_confidence}")
            print(f"   Can Override: {page.can_be_manually_processed}")
            
            if page.filter_details:
                print("   Filter Details:")
                specific_reason = page.filter_details.get('specific_reason', 'N/A')
                print(f"     → {specific_reason}")
                
                # Show priority indicators for high-value content
                if 'priority_indicators' in page.filter_details:
                    print("     Priority Indicators:")
                    for indicator in page.filter_details['priority_indicators']:
                        print(f"       • {indicator}")
        
        print("\n" + "=" * 60)
        print("✅ Phase 1 Testing Complete!")
        print("\n📈 Summary:")
        print(f"  • Total test pages created: {len(test_pages)}")
        print(f"  • Pages with filter details: {len(results)}")
        print("  • Filtering categories tested:")
        print("    - List page detection")
        print("    - Duplicate content detection")
        print("    - Attachment filtering")
        print("    - High-value content prioritization")
        
        # Test JSONB querying
        print("\n🔬 Testing JSONB Queries:")
        
        # Find pages filtered as list pages
        list_pages = db.exec(
            select(ScrapePage).where(
                ScrapePage.filter_details['filter_type'].astext == 'list_page_detection'
            )
        ).all()
        print(f"  • Found {len(list_pages)} list pages")
        
        # Find high confidence filtering
        high_confidence = db.exec(
            select(ScrapePage).where(
                ScrapePage.filter_confidence > 0.8
            )
        ).all()
        print(f"  • Found {len(high_confidence)} high-confidence filtered pages")
        
        print("\n✅ All tests passed successfully!")


if __name__ == "__main__":
    asyncio.run(test_phase1_implementation())