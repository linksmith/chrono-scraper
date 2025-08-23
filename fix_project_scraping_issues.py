#!/usr/bin/env python3
"""
Script to identify and fix common issues preventing project scraping from working.

This script checks for and fixes common problems:
1. Celery workers not running
2. Redis connection issues  
3. Database connection issues
4. Invalid domain configurations
5. Missing or incorrect environment variables
"""
import asyncio
import logging
import sys
import os
import subprocess
from datetime import datetime

# Add the backend directory to the path
sys.path.append('/home/bizon/Development/chrono-scraper-fastapi-2/backend')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_environment():
    """Check if required environment variables are set"""
    logger.info("=== CHECKING ENVIRONMENT ===")
    
    required_vars = [
        'DATABASE_URL',
        'REDIS_HOST', 
        'WAYBACK_MACHINE_CDX_URL',
        'SECRET_KEY'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
        else:
            # Don't log full values for security
            if var in ['DATABASE_URL', 'SECRET_KEY']:
                logger.info(f"✅ {var}: [SET]")
            else:
                logger.info(f"✅ {var}: {os.getenv(var)}")
    
    if missing_vars:
        logger.error(f"❌ Missing environment variables: {missing_vars}")
        logger.info("Make sure your .env file contains all required variables")
        return False
    
    logger.info("✅ All required environment variables are set")
    return True

def check_docker_services():
    """Check if required Docker services are running"""
    logger.info("\n=== CHECKING DOCKER SERVICES ===")
    
    try:
        # Check if docker compose is available
        result = subprocess.run(['docker', 'compose', 'ps', '--format', 'json'], 
                              capture_output=True, text=True, cwd='/home/bizon/Development/chrono-scraper-fastapi-2')
        
        if result.returncode != 0:
            logger.error("❌ Docker compose not available or not running")
            logger.info("Run: cd /home/bizon/Development/chrono-scraper-fastapi-2 && docker compose up -d")
            return False
            
        import json
        services = []
        for line in result.stdout.strip().split('\n'):
            if line:
                services.append(json.loads(line))
        
        required_services = ['backend', 'celery_worker', 'redis', 'postgres', 'meilisearch']
        running_services = []
        
        for service in services:
            service_name = service.get('Service', '')
            state = service.get('State', '')
            
            if service_name in required_services:
                if state == 'running':
                    logger.info(f"✅ {service_name}: running")
                    running_services.append(service_name)
                else:
                    logger.warning(f"⚠️ {service_name}: {state}")
        
        missing_services = set(required_services) - set(running_services)
        if missing_services:
            logger.error(f"❌ Services not running: {missing_services}")
            logger.info("Run: cd /home/bizon/Development/chrono-scraper-fastapi-2 && docker compose up -d")
            return False
            
        logger.info("✅ All required Docker services are running")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error checking Docker services: {str(e)}")
        return False

async def check_database_connection():
    """Check database connectivity and basic queries"""
    logger.info("\n=== CHECKING DATABASE CONNECTION ===")
    
    try:
        from app.core.database import get_db
        from app.models.user import User
        from sqlmodel import select
        
        async with get_db().__anext__() as db:
            # Test basic query
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            
            if user:
                logger.info(f"✅ Database connected - found user: {user.email}")
            else:
                logger.warning("⚠️ Database connected but no users found")
                logger.info("You may need to create a user for testing")
                
        return True
        
    except Exception as e:
        logger.error(f"❌ Database connection failed: {str(e)}")
        return False

def check_redis_connection():
    """Check Redis connectivity"""
    logger.info("\n=== CHECKING REDIS CONNECTION ===")
    
    try:
        import redis
        from app.core.config import settings
        
        redis_client = redis.Redis(host=settings.REDIS_HOST, port=6379, decode_responses=True)
        
        # Test basic operations
        test_key = f"healthcheck_{datetime.now().timestamp()}"
        redis_client.set(test_key, "test_value", ex=10)  # Expire in 10 seconds
        value = redis_client.get(test_key)
        
        if value == "test_value":
            logger.info("✅ Redis connection working")
            redis_client.delete(test_key)  # Clean up
            return True
        else:
            logger.error("❌ Redis connection failed - couldn't retrieve test value")
            return False
            
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {str(e)}")
        return False

def check_celery_workers():
    """Check if Celery workers are active and responsive"""
    logger.info("\n=== CHECKING CELERY WORKERS ===")
    
    try:
        from app.tasks.celery_app import celery_app
        
        # Check worker status
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        
        if not stats:
            logger.error("❌ No Celery workers responding")
            logger.info("Make sure celery_worker service is running:")
            logger.info("  docker compose ps celery_worker") 
            logger.info("  docker compose logs celery_worker")
            return False
        
        worker_count = len(stats)
        logger.info(f"✅ Found {worker_count} active Celery workers")
        
        for worker_name, worker_stats in stats.items():
            pool_size = worker_stats.get('pool', {}).get('max-concurrency', 'unknown')
            logger.info(f"  - {worker_name}: {pool_size} worker processes")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Celery worker check failed: {str(e)}")
        return False

async def check_wayback_machine_api():
    """Check Wayback Machine CDX API connectivity"""
    logger.info("\n=== CHECKING WAYBACK MACHINE CDX API ===")
    
    try:
        from app.services.wayback_machine import CDXAPIClient
        
        async with CDXAPIClient() as cdx_client:
            # Test with a well-known domain that should have archived data
            page_count = await cdx_client.get_page_count(
                domain_name="example.com",
                from_date="20230101",
                to_date="20231231",
                match_type="domain",
                min_size=1000,
                include_attachments=False
            )
            
        if page_count > 0:
            logger.info(f"✅ Wayback Machine CDX API working - example.com has {page_count} pages")
            return True
        else:
            logger.warning("⚠️ Wayback Machine CDX API responded but returned 0 pages")
            logger.info("This could indicate API rate limiting or temporary issues")
            return False
            
    except Exception as e:
        logger.error(f"❌ Wayback Machine CDX API check failed: {str(e)}")
        return False

async def fix_common_domain_issues():
    """Find and fix common domain configuration issues"""
    logger.info("\n=== CHECKING FOR DOMAIN CONFIGURATION ISSUES ===")
    
    try:
        from app.core.database import get_db
        from app.models.project import Domain, DomainStatus
        from sqlmodel import select
        
        async with get_db().__anext__() as db:
            # Find domains that might have issues
            result = await db.execute(select(Domain))
            domains = result.scalars().all()
            
            if not domains:
                logger.info("ℹ️ No domains found in database")
                return True
                
            logger.info(f"Found {len(domains)} domains to check")
            
            fixed_count = 0
            for domain in domains:
                issues = []
                
                # Check if domain is active
                if not getattr(domain, 'active', True):
                    issues.append("Domain is marked as inactive")
                
                # Check if domain status is appropriate
                if domain.status not in [DomainStatus.ACTIVE, DomainStatus.COMPLETED]:
                    issues.append(f"Domain status is {domain.status}")
                
                # Check for valid domain name
                if not domain.domain_name or '.' not in domain.domain_name:
                    issues.append("Invalid domain name")
                
                # Check URL path for prefix matches
                if hasattr(domain.match_type, 'value'):
                    match_type_val = domain.match_type.value
                elif isinstance(domain.match_type, str):
                    match_type_val = domain.match_type
                else:
                    match_type_val = str(domain.match_type)
                    
                if match_type_val == "prefix" and not domain.url_path:
                    issues.append("PREFIX match type requires url_path")
                
                if issues:
                    logger.warning(f"⚠️ Domain {domain.id} ({domain.domain_name}) has issues:")
                    for issue in issues:
                        logger.warning(f"    - {issue}")
                    
                    # Auto-fix some issues
                    if "Domain is marked as inactive" in issues:
                        domain.active = True
                        fixed_count += 1
                        logger.info(f"    ✅ Fixed: Set domain to active")
                    
                    if f"Domain status is {domain.status}" in issues and domain.status == DomainStatus.ERROR:
                        domain.status = DomainStatus.ACTIVE
                        fixed_count += 1
                        logger.info(f"    ✅ Fixed: Reset domain status to ACTIVE")
                
                else:
                    logger.info(f"✅ Domain {domain.id} ({domain.domain_name}) looks good")
            
            if fixed_count > 0:
                await db.commit()
                logger.info(f"✅ Fixed {fixed_count} domain issues")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Error checking domains: {str(e)}")
        return False

async def run_comprehensive_check():
    """Run all checks and report results"""
    logger.info("🔍 CHRONO SCRAPER - COMPREHENSIVE HEALTH CHECK")
    logger.info("=" * 60)
    
    checks = [
        ("Environment Variables", check_environment),
        ("Docker Services", check_docker_services), 
        ("Database Connection", check_database_connection),
        ("Redis Connection", check_redis_connection),
        ("Celery Workers", check_celery_workers),
        ("Wayback Machine API", check_wayback_machine_api),
        ("Domain Configuration", fix_common_domain_issues)
    ]
    
    results = []
    
    for check_name, check_func in checks:
        try:
            if asyncio.iscoroutinefunction(check_func):
                result = await check_func()
            else:
                result = check_func()
            results.append((check_name, result))
        except Exception as e:
            logger.error(f"❌ {check_name} check crashed: {str(e)}")
            results.append((check_name, False))
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("🎯 HEALTH CHECK SUMMARY")
    logger.info("=" * 60)
    
    passed = 0
    failed = 0
    
    for check_name, result in results:
        if result:
            logger.info(f"✅ {check_name}")
            passed += 1
        else:
            logger.error(f"❌ {check_name}")
            failed += 1
    
    logger.info(f"\nTotal: {passed} passed, {failed} failed")
    
    if failed == 0:
        logger.info("🎉 All checks passed! Your system should be ready for scraping.")
        logger.info("\nNext steps:")
        logger.info("1. Create a test project using: python debug_project_creation.py")  
        logger.info("2. Or debug an existing project: python debug_project_scraping.py debug <project_id>")
    else:
        logger.warning(f"⚠️ {failed} checks failed. Please fix these issues before proceeding.")
        logger.info("\nCommon fixes:")
        logger.info("- Ensure all Docker services are running: docker compose up -d")
        logger.info("- Check your .env file has all required variables")
        logger.info("- Restart services if needed: docker compose restart")

async def main():
    """Main function"""
    
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        # Quick check - just essential services
        logger.info("🏃 QUICK HEALTH CHECK")
        logger.info("=" * 30)
        
        essential_checks = [
            ("Environment", check_environment),
            ("Database", check_database_connection),
            ("Redis", check_redis_connection),
            ("Celery", check_celery_workers)
        ]
        
        all_good = True
        for check_name, check_func in essential_checks:
            try:
                if asyncio.iscoroutinefunction(check_func):
                    result = await check_func()
                else:
                    result = check_func()
                    
                if not result:
                    all_good = False
            except Exception as e:
                logger.error(f"❌ {check_name} check failed: {str(e)}")
                all_good = False
        
        if all_good:
            logger.info("✅ Essential services are running!")
        else:
            logger.error("❌ Some essential services have issues")
    else:
        # Full comprehensive check
        await run_comprehensive_check()

if __name__ == "__main__":
    asyncio.run(main())