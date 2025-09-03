#!/usr/bin/env python3
"""
Simple Monitoring Systems Test

Tests core monitoring functionality without complex dependencies.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_basic_monitoring():
    """Test basic monitoring functionality"""
    
    logger.info("=" * 80)
    logger.info("TESTING CORE MONITORING SYSTEMS")
    logger.info("=" * 80)
    
    results = {
        'database_connection': False,
        'monitoring_service': False,
        'health_checks': False,
        'metrics_collection': False
    }
    
    # 1. Test Database Connection
    logger.info("\n💾 TESTING DATABASE CONNECTION")
    try:
        from app.core.database import get_db
        
        async for db in get_db():
            result = await db.execute("SELECT version(), current_timestamp")
            version_info = result.first()
            logger.info(f"✅ Database connected: PostgreSQL {version_info[0][:30]}...")
            logger.info(f"✅ Current time: {version_info[1]}")
            results['database_connection'] = True
            break
            
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
    
    # 2. Test Monitoring Service
    logger.info("\n📊 TESTING MONITORING SERVICE")
    try:
        from app.services.monitoring import MonitoringService
        
        async for db in get_db():
            # Test basic monitoring functionality
            overview = await MonitoringService.get_system_overview(db)
            logger.info("✅ System overview collected:")
            logger.info(f"   • Users: {overview['totals']['users']}")
            logger.info(f"   • Projects: {overview['totals']['projects']}")
            logger.info(f"   • Pages: {overview['totals']['pages']}")
            
            results['monitoring_service'] = True
            break
            
    except Exception as e:
        logger.error(f"❌ Monitoring service failed: {e}")
    
    # 3. Test Health Checks
    logger.info("\n🩺 TESTING HEALTH CHECKS")
    try:
        async for db in get_db():
            health = await MonitoringService.get_system_health(db)
            logger.info(f"✅ System health status: {health['overall']}")
            
            issues = health.get('issues', [])
            if issues:
                logger.warning(f"⚠️  Health issues found: {len(issues)}")
                for issue in issues[:3]:  # Show first 3 issues
                    logger.warning(f"   • {issue}")
            else:
                logger.info("✅ No health issues detected")
            
            results['health_checks'] = True
            break
            
    except Exception as e:
        logger.error(f"❌ Health checks failed: {e}")
    
    # 4. Test Metrics Collection
    logger.info("\n📈 TESTING METRICS COLLECTION")
    try:
        async for db in get_db():
            # Test shared pages metrics
            shared_metrics = await MonitoringService.get_shared_pages_metrics(db)
            logger.info("✅ Shared pages metrics:")
            logger.info(f"   • Total shared pages: {shared_metrics['core_metrics']['total_shared_pages']}")
            logger.info(f"   • Deduplication rate: {shared_metrics['deduplication_metrics']['deduplication_rate_percent']}%")
            
            # Test usage trends
            trends = await MonitoringService.get_usage_trends(db, days=7)
            logger.info(f"✅ Usage trends collected for {trends['period_days']} days")
            
            results['metrics_collection'] = True
            break
            
    except Exception as e:
        logger.error(f"❌ Metrics collection failed: {e}")
    
    # 5. Test API Health Endpoint
    logger.info("\n🌐 TESTING API HEALTH ENDPOINT")
    try:
        import httpx
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:8000/api/v1/health")
            
            if response.status_code == 200:
                health_data = response.json()
                logger.info(f"✅ API health endpoint: {health_data.get('status', 'unknown')}")
            else:
                logger.warning(f"⚠️  API health endpoint returned: {response.status_code}")
                
    except Exception as e:
        logger.info(f"⚠️  API health test skipped: {e}")
    
    # Generate Summary
    logger.info("\n" + "=" * 80)
    logger.info("MONITORING TEST SUMMARY")
    logger.info("=" * 80)
    
    successful = sum(1 for v in results.values() if v)
    total = len(results)
    
    logger.info(f"✅ Tests Passed: {successful}/{total}")
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status} {test_name.replace('_', ' ').title()}")
    
    if successful == total:
        logger.info("\n🎉 ALL MONITORING TESTS PASSED!")
        logger.info("\nMonitoring systems are operational and ready for use.")
        logger.info("\nAvailable endpoints:")
        logger.info("• GET /api/v1/health - Basic health check")
        logger.info("• GET /api/v1/monitoring/system/health - Detailed system health")
        logger.info("• GET /api/v1/monitoring/system/overview - System overview")
        logger.info("• GET /api/v1/monitoring/shared-pages/metrics - Shared pages metrics")
    else:
        logger.warning(f"\n⚠️  {total - successful} tests failed")
        logger.warning("Some monitoring functionality may be limited")
    
    return successful, total


async def test_database_performance():
    """Test database performance and indexes"""
    logger.info("\n💽 TESTING DATABASE PERFORMANCE")
    
    try:
        from app.core.database import get_db
        
        async for db in get_db():
            # Test query performance
            import time
            start_time = time.time()
            
            result = await db.execute("""
                SELECT 
                    schemaname,
                    tablename,
                    indexname,
                    idx_scan as scans
                FROM pg_stat_user_indexes 
                WHERE idx_scan > 0
                ORDER BY idx_scan DESC
                LIMIT 10
            """)
            
            query_time = (time.time() - start_time) * 1000
            
            indexes = result.fetchall()
            logger.info(f"✅ Index usage query completed in {query_time:.2f}ms")
            logger.info(f"✅ Found {len(indexes)} active indexes")
            
            if indexes:
                logger.info("📊 Top used indexes:")
                for idx in indexes[:5]:
                    logger.info(f"   • {idx.tablename}.{idx.indexname}: {idx.scans} scans")
            
            # Test connection pool
            pool_stats = await db.execute("""
                SELECT 
                    count(*) as total_connections,
                    count(*) FILTER (WHERE state = 'active') as active_connections,
                    count(*) FILTER (WHERE state = 'idle') as idle_connections
                FROM pg_stat_activity 
                WHERE datname = current_database()
            """)
            
            pool_info = pool_stats.first()
            logger.info(f"✅ Connection pool: {pool_info.total_connections} total, {pool_info.active_connections} active")
            
            break
            
    except Exception as e:
        logger.error(f"❌ Database performance test failed: {e}")


async def main():
    """Main test function"""
    try:
        # Run basic monitoring tests
        successful, total = await test_basic_monitoring()
        
        # Run database performance tests
        await test_database_performance()
        
        logger.info(f"\n🏁 Testing completed at: {datetime.now(timezone.utc)}")
        
        # Return exit code based on results
        success_rate = successful / total
        if success_rate >= 0.8:
            return 0  # Success
        elif success_rate >= 0.5:
            return 1  # Partial success
        else:
            return 2  # Failure
            
    except Exception as e:
        logger.error(f"Fatal test error: {e}")
        return 3


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    logger.info(f"\nExiting with code: {exit_code}")
    sys.exit(exit_code)