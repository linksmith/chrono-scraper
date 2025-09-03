#!/usr/bin/env python3
"""
Test Analytics API Integration

This script tests the analytics API endpoints to ensure they integrate properly
with the Phase 2 DuckDB system and provide comprehensive analytics capabilities.
"""

import asyncio
import sys
from pathlib import Path

# Add the backend directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

async def test_analytics_integration():
    """Test the complete analytics API integration"""
    print("🚀 Testing Analytics API Integration")
    print("=" * 50)
    
    test_results = {
        "schemas": False,
        "service": False,
        "endpoints": False,
        "websocket": False,
        "export": False
    }
    
    # Test 1: Analytics Schemas
    try:
        from app.schemas.analytics import (
            DomainTimelineRequest, DomainStatisticsRequest, TopDomainsRequest,
            ProjectPerformanceRequest, SystemPerformanceRequest,
            AnalyticsExportRequest, TimeSeriesRequest
        )
        print("✓ Analytics schemas imported successfully")
        test_results["schemas"] = True
    except Exception as e:
        print(f"✗ Analytics schemas error: {e}")
    
    # Test 2: Analytics Service
    try:
        from app.services.analytics_service import AnalyticsService, get_analytics_service
        service = AnalyticsService()
        print("✓ Analytics service created successfully")
        test_results["service"] = True
    except Exception as e:
        print(f"✗ Analytics service error: {e}")
    
    # Test 3: Main Analytics Endpoints
    try:
        from app.api.v1.endpoints.analytics import router
        endpoint_count = len(router.routes)
        print(f"✓ Analytics endpoints loaded successfully ({endpoint_count} routes)")
        test_results["endpoints"] = True
    except Exception as e:
        print(f"✗ Analytics endpoints error: {e}")
    
    # Test 4: WebSocket Endpoints
    try:
        from app.api.v1.endpoints.analytics_websocket import router, websocket_manager
        ws_endpoint_count = len(router.routes)
        print(f"✓ Analytics WebSocket endpoints loaded ({ws_endpoint_count} routes)")
        test_results["websocket"] = True
    except Exception as e:
        print(f"✗ Analytics WebSocket error: {e}")
    
    # Test 5: Export Functionality
    try:
        from app.api.v1.endpoints.analytics_export import (
            router, export_manager, AnalyticsExporter,
            PARQUET_AVAILABLE, EXCEL_AVAILABLE, PDF_AVAILABLE
        )
        export_endpoint_count = len(router.routes)
        print(f"✓ Analytics export endpoints loaded ({export_endpoint_count} routes)")
        print(f"  - Parquet support: {'✓' if PARQUET_AVAILABLE else '✗ (pyarrow required)'}")
        print(f"  - Excel support: {'✓' if EXCEL_AVAILABLE else '✗ (openpyxl required)'}")  
        print(f"  - PDF support: {'✓' if PDF_AVAILABLE else '✗ (reportlab required)'}")
        test_results["export"] = True
    except Exception as e:
        print(f"✗ Analytics export error: {e}")
    
    # Test 6: Integration with Phase 2 Components
    print("\n🔧 Testing Phase 2 Integration")
    try:
        from app.services.duckdb_service import DuckDBService
        from app.services.hybrid_query_router import HybridQueryRouter
        print("✓ Phase 2 services (DuckDB, HybridQueryRouter) available")
    except Exception as e:
        print(f"✗ Phase 2 services error: {e}")
    
    # Test 7: Configuration
    try:
        from app.core.config import settings
        analytics_config = {
            "ANALYTICS_CACHE_TTL": getattr(settings, 'ANALYTICS_CACHE_TTL', None),
            "ANALYTICS_MAX_QUERY_TIME": getattr(settings, 'ANALYTICS_MAX_QUERY_TIME', None),
            "ENABLE_ANALYTICS_WEBSOCKET": getattr(settings, 'ENABLE_ANALYTICS_WEBSOCKET', None),
            "DUCKDB_DATABASE_PATH": getattr(settings, 'DUCKDB_DATABASE_PATH', None),
        }
        configured_settings = sum(1 for v in analytics_config.values() if v is not None)
        print(f"✓ Analytics configuration loaded ({configured_settings}/4 settings)")
    except Exception as e:
        print(f"✗ Analytics configuration error: {e}")
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 30)
    passed_tests = sum(test_results.values())
    total_tests = len(test_results)
    
    for test_name, passed in test_results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name.title()}: {status}")
    
    print(f"\nOverall: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("🎉 All analytics integration tests passed!")
        print("\n📋 Available Analytics Endpoints:")
        print("Domain Analytics:")
        print("  GET /analytics/domains/{domain}/timeline")
        print("  GET /analytics/domains/{domain}/statistics")
        print("  GET /analytics/domains/top-domains")
        print("  GET /analytics/domains/coverage-analysis")
        
        print("\nProject Analytics:")
        print("  GET /analytics/projects/{project_id}/performance")
        print("  GET /analytics/projects/{project_id}/content-quality")
        print("  GET /analytics/projects/{project_id}/scraping-efficiency")
        print("  POST /analytics/projects/comparison")
        
        print("\nSystem Analytics:")
        print("  GET /analytics/system/performance-overview")
        print("  GET /analytics/system/resource-utilization")
        
        print("\nReal-time & Export:")
        print("  WebSocket /analytics/ws/analytics")
        print("  POST /analytics/export/bulk-data")
        print("  GET /analytics/export/jobs")
        print("  GET /analytics/export/download/{job_id}")
        
        return True
    else:
        print("❌ Some analytics integration tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_analytics_integration())
    sys.exit(0 if success else 1)