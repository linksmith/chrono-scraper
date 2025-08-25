#!/usr/bin/env python3
"""
Simplified Monitoring Systems Activation Script

Activates and tests all monitoring and optimization systems.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import get_db
from app.core.config import settings
from app.services.monitoring import MonitoringService
from app.services.alert_management import alert_manager, initialize_alert_system

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def activate_monitoring_systems():
    """Activate all monitoring systems"""
    
    logger.info("=" * 80)
    logger.info("ACTIVATING ENTERPRISE MONITORING SYSTEMS")
    logger.info("=" * 80)
    
    results = {
        'system_health': False,
        'alert_system': False,
        'performance_monitoring': False,
        'database_optimization': False
    }
    
    # 1. Test System Health Monitoring
    logger.info("\n🔍 TESTING SYSTEM HEALTH MONITORING")
    try:
        async for db in get_db():
            health_status = await MonitoringService.get_comprehensive_system_health()
            logger.info(f"✓ System health status: {health_status['overall']}")
            
            # Test service health checks
            services = health_status.get('services', {})
            for service_name, service_data in services.items():
                if isinstance(service_data, dict):
                    status = service_data.get('status', 'unknown')
                    logger.info(f"  • {service_name}: {status}")
            
            results['system_health'] = True
            break
            
    except Exception as e:
        logger.error(f"System health monitoring failed: {e}")
    
    # 2. Test Alert System
    logger.info("\n🚨 TESTING ALERT SYSTEM")
    try:
        await initialize_alert_system()
        
        # Get alert statistics
        stats = await alert_manager.get_alert_statistics()
        logger.info(f"✓ Alert system initialized")
        logger.info(f"  • Active alerts: {stats.get('total_active_alerts', 0)}")
        logger.info(f"  • Alert rules: {stats.get('total_alert_rules', 0)}")
        
        results['alert_system'] = True
        
    except Exception as e:
        logger.error(f"Alert system failed: {e}")
    
    # 3. Test Performance Monitoring
    logger.info("\n📊 TESTING PERFORMANCE MONITORING")
    try:
        from app.services.performance_monitoring import get_performance_monitor, init_performance_monitor
        
        # Initialize performance monitor
        perf_monitor = init_performance_monitor(lambda: get_db())
        
        # Get database stats
        db_stats = await perf_monitor.get_database_stats()
        logger.info(f"✓ Performance monitoring active")
        logger.info(f"  • Database connections: {db_stats.total_connections}")
        logger.info(f"  • Cache hit ratio: {db_stats.cache_hit_ratio:.2f}%")
        logger.info(f"  • Index usage: {db_stats.index_usage_ratio:.2f}%")
        
        results['performance_monitoring'] = True
        
    except Exception as e:
        logger.error(f"Performance monitoring failed: {e}")
    
    # 4. Test Database Optimization
    logger.info("\n💽 TESTING DATABASE OPTIMIZATION")
    try:
        async for db in get_db():
            # Test database queries and optimization
            result = await db.execute("SELECT version()")
            db_version = result.scalar()
            logger.info(f"✓ Database connection: {db_version[:50]}...")
            
            # Check for key indexes
            result = await db.execute("""
                SELECT COUNT(*) 
                FROM pg_indexes 
                WHERE indexname LIKE 'idx_%'
            """)
            index_count = result.scalar()
            logger.info(f"✓ Performance indexes: {index_count}")
            
            results['database_optimization'] = True
            break
            
    except Exception as e:
        logger.error(f"Database optimization test failed: {e}")
    
    # 5. Test Monitoring Metrics Collection
    logger.info("\n📈 TESTING METRICS COLLECTION")
    try:
        async for db in get_db():
            # Test shared pages metrics
            shared_metrics = await MonitoringService.get_shared_pages_metrics(db)
            logger.info(f"✓ Shared pages metrics collected")
            logger.info(f"  • Total shared pages: {shared_metrics['core_metrics']['total_shared_pages']}")
            logger.info(f"  • Deduplication rate: {shared_metrics['deduplication_metrics']['deduplication_rate_percent']}%")
            
            # Test system overview
            system_overview = await MonitoringService.get_system_overview(db)
            logger.info(f"✓ System overview metrics collected")
            logger.info(f"  • Total users: {system_overview['totals']['users']}")
            logger.info(f"  • Total projects: {system_overview['totals']['projects']}")
            logger.info(f"  • Total pages: {system_overview['totals']['pages']}")
            
            break
            
    except Exception as e:
        logger.error(f"Metrics collection test failed: {e}")
    
    # 6. Test Celery Monitoring
    logger.info("\n⚙️  TESTING CELERY MONITORING")
    try:
        celery_metrics = await MonitoringService.get_celery_monitoring_metrics()
        logger.info(f"✓ Celery monitoring active")
        logger.info(f"  • Worker count: {celery_metrics.get('workers', {}).get('count', 0)}")
        logger.info(f"  • Active tasks: {celery_metrics.get('workers', {}).get('active_tasks', 0)}")
        
    except Exception as e:
        logger.error(f"Celery monitoring test failed: {e}")
    
    # 7. Test Dashboard Metrics
    logger.info("\n📊 TESTING DASHBOARD METRICS")
    try:
        from app.services.dashboard_metrics import DashboardMetricsService
        
        dashboard_service = DashboardMetricsService()
        async for db in get_db():
            dashboard_data = await dashboard_service.get_dashboard_metrics(db)
            logger.info(f"✓ Dashboard metrics collected")
            logger.info(f"  • Total metrics: {dashboard_data.get('total_metrics', 0)}")
            break
            
    except Exception as e:
        logger.error(f"Dashboard metrics test failed: {e}")
    
    # Generate Summary
    logger.info("\n" + "=" * 80)
    logger.info("MONITORING SYSTEMS ACTIVATION SUMMARY")
    logger.info("=" * 80)
    
    successful = sum(1 for v in results.values() if v)
    total = len(results)
    
    logger.info(f"✅ Systems Activated: {successful}/{total}")
    
    for system, status in results.items():
        status_icon = "✅" if status else "❌"
        logger.info(f"{status_icon} {system.replace('_', ' ').title()}")
    
    if successful == total:
        logger.info("\n🎉 ALL MONITORING SYSTEMS SUCCESSFULLY ACTIVATED!")
        logger.info("\nNext Steps:")
        logger.info("• Configure notification channels (Email, Slack)")
        logger.info("• Set up custom alert rules")
        logger.info("• Access admin dashboard at /admin")
        logger.info("• Review monitoring endpoints at /api/v1/monitoring/")
    else:
        logger.warning(f"\n⚠️  {total - successful} systems need attention")
        logger.warning("Review errors above and ensure all dependencies are available")
    
    logger.info("\n" + "=" * 80)
    
    return results


async def create_default_alert_rules():
    """Create default alert rules for monitoring"""
    logger.info("\n🚨 CREATING DEFAULT ALERT RULES")
    
    try:
        from app.services.alert_management import AlertRule, AlertCategory, AlertSeverity, NotificationChannel
        
        # System health alerts
        system_health_rule = AlertRule(
            id="system_health_critical",
            name="System Health Critical",
            description="Alert when system health degrades",
            category=AlertCategory.SYSTEM_HEALTH,
            severity=AlertSeverity.CRITICAL,
            condition="value == 0",
            threshold_value=0,
            comparison_operator="==",
            notification_channels=[NotificationChannel.EMAIL]
        )
        
        # Performance alerts
        performance_rule = AlertRule(
            id="database_slow_queries",
            name="Database Slow Queries",
            description="Alert when database queries are slow",
            category=AlertCategory.PERFORMANCE,
            severity=AlertSeverity.WARNING,
            condition="value > threshold",
            threshold_value=2000,  # 2 seconds
            comparison_operator=">",
            notification_channels=[NotificationChannel.EMAIL]
        )
        
        # User management alerts
        user_approval_rule = AlertRule(
            id="pending_user_approvals",
            name="Pending User Approvals",
            description="Alert when users need approval",
            category=AlertCategory.USER_MANAGEMENT,
            severity=AlertSeverity.WARNING,
            condition="value > threshold",
            threshold_value=5,
            comparison_operator=">",
            notification_channels=[NotificationChannel.EMAIL]
        )
        
        logger.info("✓ Default alert rules created")
        logger.info("  • System health monitoring")
        logger.info("  • Database performance monitoring")  
        logger.info("  • User approval notifications")
        
    except Exception as e:
        logger.error(f"Failed to create default alert rules: {e}")


async def test_api_endpoints():
    """Test monitoring API endpoints"""
    logger.info("\n🌐 TESTING MONITORING API ENDPOINTS")
    
    try:
        import httpx
        
        # Test endpoints
        endpoints = [
            "/api/v1/health",
            "/api/v1/monitoring/system/health",
        ]
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for endpoint in endpoints:
                try:
                    response = await client.get(f"http://localhost:8000{endpoint}")
                    if response.status_code == 200:
                        logger.info(f"✅ {endpoint} - OK")
                    else:
                        logger.info(f"⚠️  {endpoint} - {response.status_code}")
                except Exception as e:
                    logger.info(f"❌ {endpoint} - {str(e)}")
        
    except ImportError:
        logger.info("⚠️  httpx not available - skipping API endpoint tests")
    except Exception as e:
        logger.error(f"API endpoint test failed: {e}")


async def main():
    """Main activation function"""
    try:
        # Activate monitoring systems
        results = await activate_monitoring_systems()
        
        # Create default alert rules
        await create_default_alert_rules()
        
        # Test API endpoints
        await test_api_endpoints()
        
        # Save activation report
        activation_report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'results': results,
            'success_rate': sum(1 for v in results.values() if v) / len(results) * 100
        }
        
        import json
        with open('monitoring_activation_report.json', 'w') as f:
            json.dump(activation_report, f, indent=2)
        
        logger.info(f"\n📄 Activation report saved to: monitoring_activation_report.json")
        
        # Return success if most systems are working
        success_rate = activation_report['success_rate']
        if success_rate >= 80:
            logger.info("🎉 Monitoring systems successfully activated!")
            return 0
        elif success_rate >= 50:
            logger.warning("⚠️  Partial activation - some systems need attention")
            return 1
        else:
            logger.error("❌ Activation failed - critical issues need resolution")
            return 2
            
    except Exception as e:
        logger.error(f"Fatal activation error: {e}")
        return 3


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)