#!/usr/bin/env python3
"""
Test script for ArchiveServiceRouter functionality.
This script validates the basic functionality of the intelligent archive routing system.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from app.services.archive_service_router import (
    ArchiveServiceRouter,
    RoutingConfig,
    ArchiveSourceConfig,
    FallbackStrategy,
    query_archive_unified,
    create_routing_config_from_project
)
from app.models.project import ArchiveSource

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_wayback_machine_only():
    """Test querying with Wayback Machine only"""
    logger.info("=" * 60)
    logger.info("Testing Wayback Machine only configuration")
    logger.info("=" * 60)
    
    project_config = {
        'archive_source': ArchiveSource.WAYBACK_MACHINE,
        'fallback_enabled': False,
        'archive_config': {
            'wayback_machine': {
                'max_pages': 2
            }
        }
    }
    
    try:
        records, stats = await query_archive_unified(
            domain="example.com",
            from_date="20240101",
            to_date="20240131",
            project_config=project_config
        )
        
        logger.info(f"✅ Wayback Machine test successful: {len(records)} records retrieved")
        logger.info(f"Stats: {stats}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Wayback Machine test failed: {e}")
        return False


async def test_hybrid_mode_with_fallback():
    """Test hybrid mode with fallback enabled"""
    logger.info("=" * 60)
    logger.info("Testing Hybrid mode with fallback")
    logger.info("=" * 60)
    
    project_config = {
        'archive_source': ArchiveSource.HYBRID,
        'fallback_enabled': True,
        'archive_config': {
            'fallback_strategy': 'immediate',
            'fallback_delay_seconds': 0.5,
            'wayback_machine': {
                'max_pages': 1
            },
            'common_crawl': {
                'max_pages': 1  
            }
        }
    }
    
    try:
        records, stats = await query_archive_unified(
            domain="example.com",
            from_date="20240101", 
            to_date="20240131",
            project_config=project_config
        )
        
        logger.info(f"✅ Hybrid mode test successful: {len(records)} records retrieved")
        logger.info(f"Primary source: {stats.get('primary_source', 'unknown')}")
        logger.info(f"Successful source: {stats.get('successful_source', 'unknown')}")
        logger.info(f"Fallback used: {stats.get('fallback_used', False)}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Hybrid mode test failed: {e}")
        return False


async def test_router_metrics_and_health():
    """Test router metrics and health monitoring"""
    logger.info("=" * 60)
    logger.info("Testing Router Metrics and Health Monitoring")
    logger.info("=" * 60)
    
    # Create custom routing config
    config = RoutingConfig(
        fallback_strategy=FallbackStrategy.CIRCUIT_BREAKER,
        fallback_delay_seconds=1.0
    )
    
    router = ArchiveServiceRouter(config)
    
    try:
        # Get initial health status
        health_before = router.get_health_status()
        logger.info(f"Initial health status: {health_before['overall_status']}")
        
        # Perform a query to generate metrics
        project_config = {
            'archive_source': ArchiveSource.WAYBACK_MACHINE,
            'fallback_enabled': True
        }
        
        records, stats = await router.query_archive(
            domain="example.com",
            from_date="20240101",
            to_date="20240115",  # Smaller date range for faster testing
            project_config=project_config
        )
        
        # Get performance metrics
        metrics = router.get_performance_metrics()
        logger.info(f"✅ Performance metrics generated:")
        logger.info(f"  Total queries: {metrics['overall']['total_queries']}")
        logger.info(f"  Average success rate: {metrics['overall']['avg_success_rate']}%")
        
        # Get updated health status
        health_after = router.get_health_status()
        logger.info(f"Updated health status: {health_after['overall_status']}")
        
        # Display source-specific metrics
        for source, source_metrics in metrics['sources'].items():
            logger.info(f"  {source}: {source_metrics['success_rate']}% success rate, "
                       f"{source_metrics['total_queries']} queries")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Metrics test failed: {e}")
        return False


async def test_routing_config_creation():
    """Test routing config creation from project settings"""
    logger.info("=" * 60)
    logger.info("Testing Routing Config Creation")  
    logger.info("=" * 60)
    
    try:
        # Test creating config for Wayback Machine only
        config1 = create_routing_config_from_project(
            archive_source=ArchiveSource.WAYBACK_MACHINE,
            fallback_enabled=False,
            archive_config={
                'wayback_machine': {
                    'timeout_seconds': 90,
                    'max_pages': 5
                }
            }
        )
        
        assert config1.wayback_config.timeout_seconds == 90
        assert config1.wayback_config.max_pages == 5
        assert not config1.common_crawl_config.enabled
        
        # Test hybrid config
        config2 = create_routing_config_from_project(
            archive_source=ArchiveSource.HYBRID,
            fallback_enabled=True,
            archive_config={
                'fallback_strategy': 'immediate',
                'fallback_delay_seconds': 2.0
            }
        )
        
        assert config2.fallback_strategy == FallbackStrategy.IMMEDIATE
        assert config2.fallback_delay_seconds == 2.0
        assert config2.wayback_config.enabled
        assert config2.common_crawl_config.enabled
        
        logger.info("✅ Routing config creation tests passed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Routing config test failed: {e}")
        return False


async def main():
    """Run all tests"""
    logger.info("🚀 Starting ArchiveServiceRouter Test Suite")
    logger.info(f"Test started at: {datetime.now().isoformat()}")
    
    tests = [
        ("Wayback Machine Only", test_wayback_machine_only),
        ("Hybrid Mode with Fallback", test_hybrid_mode_with_fallback), 
        ("Router Metrics and Health", test_router_metrics_and_health),
        ("Routing Config Creation", test_routing_config_creation)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        logger.info(f"\n🧪 Running: {test_name}")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
        
        # Small delay between tests
        await asyncio.sleep(1)
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status} - {test_name}")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        logger.info("🎉 All tests passed! ArchiveServiceRouter is working correctly.")
    else:
        logger.warning(f"⚠️  {total-passed} test(s) failed. Review logs for details.")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)