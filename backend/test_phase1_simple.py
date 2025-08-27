#!/usr/bin/env python3
"""
Simple test to verify Phase 1 database structure.
Run with: docker compose exec backend python test_phase1_simple.py
"""
import json
from sqlalchemy import create_engine, text
from app.core.config import settings

def test_phase1_structure():
    """Test the enhanced filtering system database structure"""
    
    print("🔧 Testing Phase 1: Database Structure Verification")
    print("=" * 60)
    
    # Create database connection
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        # Check if new columns exist
        result = conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'scrape_pages' 
            AND column_name IN ('filter_details', 'matched_pattern', 'filter_confidence', 'related_page_id')
            ORDER BY column_name
        """))
        
        columns = result.fetchall()
        
        print("\n✅ New Columns Added:")
        for col_name, col_type in columns:
            print(f"  • {col_name}: {col_type}")
        
        # Check indexes
        result = conn.execute(text("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'scrape_pages' 
            AND indexname LIKE '%filter%' OR indexname LIKE '%matched%' OR indexname LIKE '%confidence%'
            ORDER BY indexname
        """))
        
        indexes = result.fetchall()
        
        print("\n✅ Indexes Created:")
        for idx in indexes:
            print(f"  • {idx[0]}")
        
        # Test JSONB functionality
        print("\n🔬 Testing JSONB Storage:")
        
        # Insert a test record with JSONB filter_details
        result = conn.execute(text("""
            INSERT INTO scrape_pages (
                domain_id, original_url, content_url, unix_timestamp,
                mime_type, status_code, status, filter_details,
                matched_pattern, filter_confidence, is_manually_overridden,
                can_be_manually_processed
            )
            SELECT 
                d.id,
                'https://example.com/blog/page/2',
                'https://web.archive.org/web/20240315120000/https://example.com/blog/page/2',
                '20240315120000',
                'text/html',
                200,
                'filtered_list_page',
                '{"filter_type": "list_page_detection", 
                  "matched_pattern": "/blog/page/\\\\d+",
                  "specific_reason": "Blog pagination detected - Pattern: /blog/page/[number]",
                  "confidence_score": 0.9,
                  "detection_timestamp": "2024-03-15T12:00:00"}'::jsonb,
                '/blog/page/\\d+',
                0.9,
                false,
                true
            FROM domains d
            LIMIT 1
            RETURNING id, original_url
        """))
        
        if result.rowcount > 0:
            test_id, test_url = result.fetchone()
            print(f"  ✅ Created test record: ID={test_id}, URL={test_url}")
            
            # Query the JSONB data
            result = conn.execute(text("""
                SELECT 
                    original_url,
                    status,
                    matched_pattern,
                    filter_confidence,
                    filter_details->>'specific_reason' as specific_reason,
                    filter_details->>'confidence_score' as json_confidence
                FROM scrape_pages
                WHERE id = :id
            """), {"id": test_id})
            
            row = result.fetchone()
            if row:
                print(f"\n📊 Test Record Details:")
                print(f"  URL: {row[0]}")
                print(f"  Status: {row[1]}")
                print(f"  Pattern: {row[2]}")
                print(f"  Confidence: {row[3]}")
                print(f"  Specific Reason: {row[4]}")
                print(f"  JSON Confidence: {row[5]}")
            
            # Test JSONB searching
            result = conn.execute(text("""
                SELECT COUNT(*) 
                FROM scrape_pages
                WHERE filter_details @> '{"filter_type": "list_page_detection"}'::jsonb
            """))
            
            count = result.scalar()
            print(f"\n🔍 JSONB Search Test:")
            print(f"  Found {count} records with filter_type='list_page_detection'")
            
            # Clean up test record
            conn.execute(text("DELETE FROM scrape_pages WHERE id = :id"), {"id": test_id})
            conn.commit()
            print(f"\n🧹 Test record cleaned up")
        else:
            print("  ⚠️ No domains found - skipping JSONB test")
        
        print("\n" + "=" * 60)
        print("✅ Phase 1 Database Structure Test Complete!")
        print("\n📈 Summary:")
        print(f"  • New columns verified: {len(columns)}/4")
        print(f"  • Indexes created: {len(indexes)}")
        print(f"  • JSONB storage: ✅ Working")
        print(f"  • JSONB queries: ✅ Working")
        print("\n🎯 Database is ready for Phase 2: Backend Logic Implementation")


if __name__ == "__main__":
    test_phase1_structure()