#!/usr/bin/env python3
"""
Simple diagnostic script to check current scraping configuration
"""
import sys
sys.path.insert(0, '/opt/app')

import os
from app.core.config import settings

def main():
    """Diagnose current scraping configuration"""
    print("=" * 60)
    print("🔍 SCRAPING CONFIGURATION DIAGNOSIS")
    print("=" * 60)
    
    print("\n📋 Current Configuration:")
    print(f"FIRECRAWL_V2_BATCH_ONLY: {getattr(settings, 'FIRECRAWL_V2_BATCH_ONLY', 'Not set')}")
    print(f"FIRECRAWL_V2_BATCH_ENABLED: {getattr(settings, 'FIRECRAWL_V2_BATCH_ENABLED', 'Not set')}")
    print(f"USE_INTELLIGENT_EXTRACTION_ONLY: {getattr(settings, 'USE_INTELLIGENT_EXTRACTION_ONLY', 'Not set')}")
    print(f"INTELLIGENT_EXTRACTION_CONCURRENCY: {getattr(settings, 'INTELLIGENT_EXTRACTION_CONCURRENCY', 'Not set')}")
    
    print("\n📋 Environment Variables:")
    print(f"V2_BATCH_ONLY: {os.getenv('V2_BATCH_ONLY', 'Not set')}")
    print(f"USE_INDIVIDUAL_EXTRACTION: {os.getenv('USE_INDIVIDUAL_EXTRACTION', 'Not set')}")
    print(f"FIRECRAWL_V2_BATCH_ONLY: {os.getenv('FIRECRAWL_V2_BATCH_ONLY', 'Not set')}")
    print(f"USE_INTELLIGENT_EXTRACTION_ONLY: {os.getenv('USE_INTELLIGENT_EXTRACTION_ONLY', 'Not set')}")
    
    print("\n🚨 Issue Analysis:")
    
    v2_batch_only = getattr(settings, 'FIRECRAWL_V2_BATCH_ONLY', False)
    v2_batch_enabled = getattr(settings, 'FIRECRAWL_V2_BATCH_ENABLED', True)
    use_intelligent_only = getattr(settings, 'USE_INTELLIGENT_EXTRACTION_ONLY', False)
    
    if v2_batch_only:
        print("❌ PROBLEM: FIRECRAWL_V2_BATCH_ONLY is True - this forces V2 batch processing")
        print("   This will cause 'Connection refused' errors since Firecrawl services are removed")
    
    if v2_batch_enabled and not use_intelligent_only:
        print("⚠️  WARNING: V2 batch is enabled but intelligent extraction is not enabled")
        print("   The system may attempt V2 batch processing first")
    
    if not use_intelligent_only:
        print("❌ PROBLEM: USE_INTELLIGENT_EXTRACTION_ONLY is False")
        print("   This means the system won't bypass Firecrawl entirely")
    
    print("\n💡 Recommended Fix:")
    print("Set these environment variables:")
    print("   FIRECRAWL_V2_BATCH_ONLY=false")
    print("   USE_INTELLIGENT_EXTRACTION_ONLY=true")
    print("   V2_BATCH_ONLY=false")
    
    print("\n🔧 Testing Firecrawl V2 Client Import:")
    try:
        from app.services.firecrawl_v2_client import FirecrawlV2Client
        print("✅ FirecrawlV2Client import successful")
        
        # Try to create client (this would connect if services were available)
        try:
            fc = FirecrawlV2Client()
            print("✅ FirecrawlV2Client instance created")
            print("🚨 WARNING: If V2 batch is attempted, it WILL fail with connection errors")
        except Exception as e:
            print(f"❌ FirecrawlV2Client instantiation failed: {e}")
            
    except ImportError as e:
        print(f"❌ FirecrawlV2Client import failed: {e}")
    
    print("\n🔧 Testing Robust Extraction System:")
    try:
        from app.services.robust_content_extractor import get_robust_extractor
        extractor = get_robust_extractor()
        print("✅ Robust content extractor initialized successfully")
        print("✅ Individual URL processing system is available")
    except Exception as e:
        print(f"❌ Robust content extractor failed: {e}")
    
    print("\n" + "=" * 60)
    
    if v2_batch_only or (v2_batch_enabled and not use_intelligent_only):
        print("🚨 CONCLUSION: Configuration will cause V2 batch connection errors")
        return 1
    else:
        print("✅ CONCLUSION: Configuration should work with individual processing")
        return 0

if __name__ == "__main__":
    sys.exit(main())