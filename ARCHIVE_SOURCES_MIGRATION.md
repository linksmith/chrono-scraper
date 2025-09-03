# Archive Sources Migration Guide

## Table of Contents
- [Overview](#overview)
- [Backward Compatibility](#backward-compatibility)
- [Upgrading from Single Archive](#upgrading-from-single-archive)
- [Database Migration](#database-migration)
- [Configuration Migration](#configuration-migration)
- [Testing the Migration](#testing-the-migration)
- [Rollback Procedures](#rollback-procedures)
- [Performance Impact](#performance-impact)
- [Troubleshooting Migration Issues](#troubleshooting-migration-issues)

## Overview

The Archive Sources feature introduces multi-archive support to Chrono Scraper, allowing projects to use Wayback Machine, Common Crawl, or Hybrid mode with intelligent fallback. This migration guide covers upgrading from the previous single-archive system to the new multi-archive system.

### What's New

- **Multiple Archive Sources**: Choose between Wayback Machine, Common Crawl, or Hybrid mode
- **Intelligent Fallback**: Automatic switching between sources on failures
- **Circuit Breaker Protection**: Prevents repeated failed attempts
- **Performance Monitoring**: Track success rates and response times per source
- **Project-Level Configuration**: Each project can have different archive preferences

### Migration Timeline

The migration is designed to be **non-breaking** and **zero-downtime**:

1. **Database schema update** (automatic with Alembic)
2. **Existing projects** continue working unchanged
3. **New projects** can use enhanced archive source options
4. **Optional migration** to Hybrid mode for better reliability

## Backward Compatibility

### Existing Projects

**All existing projects will continue to work exactly as before:**

- Existing projects retain `archive_source = "wayback_machine"`
- All existing scraping behavior is preserved
- No changes to CDX record format or processing
- Existing project configurations remain valid

### API Compatibility

**All existing API endpoints remain unchanged:**

- Project creation API accepts old format
- Project queries return same data structure
- Scraping endpoints work identically
- No breaking changes to client applications

### Code Compatibility

**Existing code continues to work:**

```python
# This code continues to work unchanged
from app.services.wayback_machine import CDXAPIClient

async with CDXAPIClient() as client:
    records, stats = await client.fetch_cdx_records_simple(
        domain_name="example.com",
        from_date="20240101", 
        to_date="20240131"
    )
```

**New code can use enhanced features:**

```python
# New archive router with fallback support
from app.services.archive_service_router import ArchiveServiceRouter

router = ArchiveServiceRouter()
records, stats = await router.query_archive(
    domain="example.com",
    from_date="20240101",
    to_date="20240131",
    project_config={
        "archive_source": "hybrid",
        "fallback_enabled": True
    }
)
```

## Upgrading from Single Archive

### System-Wide Upgrade

#### 1. Update Environment Configuration

Add new environment variables to your `.env` file:

```bash
# New archive source defaults
ARCHIVE_DEFAULT_SOURCE=hybrid
ARCHIVE_DEFAULT_FALLBACK_ENABLED=true

# Common Crawl configuration
COMMON_CRAWL_TIMEOUT=180
COMMON_CRAWL_MAX_RETRIES=5
COMMON_CRAWL_PAGE_SIZE=5000

# Circuit breaker settings
WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
COMMON_CRAWL_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5

# Fallback configuration
ARCHIVE_FALLBACK_DELAY=1.0
ARCHIVE_FALLBACK_MAX_DELAY=30.0
```

#### 2. Update Docker Compose Configuration

Add the new environment variables to `docker-compose.yml`:

```yaml
services:
  backend:
    environment:
      # Existing Wayback Machine settings (unchanged)
      - WAYBACK_MACHINE_TIMEOUT=120
      - WAYBACK_MACHINE_MAX_RETRIES=3
      - WAYBACK_MACHINE_PAGE_SIZE=5000
      
      # New archive source settings
      - ARCHIVE_DEFAULT_SOURCE=hybrid
      - COMMON_CRAWL_TIMEOUT=180
      - COMMON_CRAWL_MAX_RETRIES=5
      - WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
      - ARCHIVE_FALLBACK_DELAY=1.0
```

#### 3. Install New Dependencies

The Common Crawl service requires `cdx_toolkit`:

```bash
# This is already included in requirements.txt
pip install cdx_toolkit
```

Or rebuild your Docker containers:

```bash
docker compose build backend
```

### Project-Level Migration

#### Option 1: Keep Existing Behavior (Recommended for Stability)

Existing projects automatically continue using only Wayback Machine:

- No action required
- Identical behavior to previous version
- No fallback or circuit breaker features

#### Option 2: Migrate to Hybrid Mode (Recommended for Reliability)

Manually migrate projects to use Hybrid mode for better reliability:

```python
# Migration script to enable hybrid mode for existing projects
async def migrate_projects_to_hybrid():
    async with get_db() as db:
        # Get all projects currently using wayback_machine
        stmt = select(Project).where(Project.archive_source == "wayback_machine")
        result = await db.execute(stmt)
        projects = result.scalars().all()
        
        for project in projects:
            # Migrate to hybrid mode with fallback enabled
            project.archive_source = ArchiveSource.HYBRID
            project.fallback_enabled = True
            
            # Optional: Set project-specific configuration
            project.archive_config = {
                "fallback_strategy": "circuit_breaker",
                "wayback_machine": {
                    "priority": 1,  # Primary source
                    "timeout_seconds": 120
                },
                "common_crawl": {
                    "priority": 2,  # Fallback source
                    "timeout_seconds": 180
                }
            }
            
            db.add(project)
        
        await db.commit()
        print(f"Migrated {len(projects)} projects to hybrid mode")
```

Run the migration:

```bash
docker compose exec backend python -c "
import asyncio
from app.core.database import get_db
from app.models.project import Project, ArchiveSource
from sqlmodel import select

async def migrate_projects():
    async for db in get_db():
        stmt = select(Project).where(Project.archive_source == 'wayback_machine')
        result = await db.execute(stmt)
        projects = result.scalars().all()
        
        updated = 0
        for project in projects:
            project.archive_source = ArchiveSource.HYBRID
            project.fallback_enabled = True
            db.add(project)
            updated += 1
        
        await db.commit()
        print(f'✓ Migrated {updated} projects to hybrid mode')
        break

asyncio.run(migrate_projects())
"
```

#### Option 3: Selective Migration

Migrate only specific projects based on criteria:

```sql
-- Migrate large projects to hybrid mode (SQL approach)
UPDATE projects 
SET archive_source = 'hybrid', 
    fallback_enabled = true,
    archive_config = '{"fallback_strategy": "circuit_breaker"}'
WHERE archive_source = 'wayback_machine'
  AND (
    -- Large projects that would benefit from reliability
    (SELECT COUNT(*) FROM domains WHERE domains.project_id = projects.id) > 10
    OR
    -- Projects with recent scraping activity
    updated_at > NOW() - INTERVAL '30 days'
  );
```

## Database Migration

### Automatic Schema Migration

The database schema is automatically updated when you run migrations:

```bash
# Run Alembic migration
docker compose exec backend alembic upgrade head
```

### Migration Details

The migration adds the following columns to the `projects` table:

```sql
-- Archive source configuration (new columns)
ALTER TABLE projects ADD COLUMN archive_source VARCHAR(20) 
    DEFAULT 'wayback_machine' NOT NULL;
    
ALTER TABLE projects ADD COLUMN fallback_enabled BOOLEAN 
    DEFAULT true NOT NULL;
    
ALTER TABLE projects ADD COLUMN archive_config JSON 
    DEFAULT '{}' NOT NULL;

-- Create index for performance
CREATE INDEX ix_projects_archive_source ON projects(archive_source);
```

### Data Migration Validation

Verify the migration completed successfully:

```bash
# Check schema changes
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
\d projects
"

# Check data migration
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
SELECT archive_source, fallback_enabled, COUNT(*) as count
FROM projects 
GROUP BY archive_source, fallback_enabled;
"
```

Expected output:
```
 archive_source  | fallback_enabled | count 
-----------------+------------------+-------
 wayback_machine | t                |    XX
(1 row)
```

### Rollback Schema (If Needed)

If you need to rollback the schema changes:

```bash
# Rollback to previous migration
docker compose exec backend alembic downgrade -1

# Or rollback to specific revision
docker compose exec backend alembic downgrade <previous_revision>
```

**Warning**: Rolling back will remove archive source configuration data.

## Configuration Migration

### Environment Variable Migration

#### Before (Single Archive)
```bash
# Only Wayback Machine configuration
WAYBACK_MACHINE_TIMEOUT=120
WAYBACK_MACHINE_MAX_RETRIES=3
WAYBACK_MACHINE_PAGE_SIZE=5000
```

#### After (Multi-Archive)
```bash
# Existing Wayback Machine configuration (unchanged)
WAYBACK_MACHINE_TIMEOUT=120
WAYBACK_MACHINE_MAX_RETRIES=3
WAYBACK_MACHINE_PAGE_SIZE=5000

# New archive source defaults
ARCHIVE_DEFAULT_SOURCE=hybrid
ARCHIVE_DEFAULT_FALLBACK_ENABLED=true

# New Common Crawl configuration  
COMMON_CRAWL_TIMEOUT=180
COMMON_CRAWL_MAX_RETRIES=5
COMMON_CRAWL_PAGE_SIZE=5000

# New circuit breaker configuration
WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
COMMON_CRAWL_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5

# New fallback configuration
ARCHIVE_FALLBACK_DELAY=1.0
ARCHIVE_FALLBACK_MAX_DELAY=30.0
```

### Configuration Validation Script

```python
#!/usr/bin/env python
"""Validate archive source configuration migration"""

import os
import sys
from app.core.config import settings
from app.services.archive_service_router import RoutingConfig

def validate_migration():
    print("🔍 Validating Archive Sources Migration...")
    
    # Check if new configuration exists
    missing_configs = []
    
    expected_vars = [
        'ARCHIVE_DEFAULT_SOURCE',
        'COMMON_CRAWL_TIMEOUT', 
        'WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD',
        'ARCHIVE_FALLBACK_DELAY'
    ]
    
    for var in expected_vars:
        if not hasattr(settings, var):
            missing_configs.append(var)
    
    if missing_configs:
        print("❌ Missing configuration variables:")
        for var in missing_configs:
            print(f"  - {var}")
        return False
    
    # Test router initialization
    try:
        router = RoutingConfig()
        print("✓ Archive router configuration is valid")
    except Exception as e:
        print(f"❌ Archive router configuration failed: {e}")
        return False
    
    # Test database connectivity
    try:
        from app.models.project import ArchiveSource
        print(f"✓ Archive source enum available: {list(ArchiveSource)}")
    except Exception as e:
        print(f"❌ Archive source enum failed: {e}")
        return False
    
    print("✅ Archive sources migration validation completed successfully")
    return True

if __name__ == "__main__":
    success = validate_migration()
    sys.exit(0 if success else 1)
```

## Testing the Migration

### Pre-Migration Testing

Before deploying the migration, test in a staging environment:

```bash
# 1. Backup your database
docker compose exec postgres pg_dump -U chrono_scraper chrono_scraper > backup_pre_migration.sql

# 2. Run migration in staging
docker compose exec backend alembic upgrade head

# 3. Test existing functionality
docker compose exec backend pytest tests/test_wayback_machine.py -v

# 4. Test new functionality
docker compose exec backend pytest tests/test_archive_service_router.py -v
```

### Post-Migration Testing

After deploying the migration:

#### 1. Test Existing Projects

```python
# Test that existing projects still work
async def test_existing_project():
    async for db in get_db():
        # Get an existing project
        stmt = select(Project).limit(1)
        result = await db.execute(stmt)
        project = result.scalar_one_or_none()
        
        if project:
            print(f"Testing project: {project.name}")
            print(f"Archive source: {project.archive_source}")
            print(f"Fallback enabled: {project.fallback_enabled}")
            
            # Test scraping still works
            from app.tasks.firecrawl_scraping import test_project_scraping
            success = await test_project_scraping(project.id)
            print(f"Scraping test: {'✓ PASSED' if success else '❌ FAILED'}")
        break
```

#### 2. Test New Archive Sources

```python
# Test Common Crawl functionality
async def test_common_crawl():
    from app.services.common_crawl_service import CommonCrawlService
    
    try:
        async with CommonCrawlService() as service:
            records, stats = await service.fetch_cdx_records_simple(
                domain_name="example.com",
                from_date="20240101",
                to_date="20240131"
            )
            print(f"✓ Common Crawl: Retrieved {len(records)} records")
    except Exception as e:
        print(f"❌ Common Crawl failed: {e}")
```

#### 3. Test Hybrid Mode

```python
# Test hybrid mode with fallback
async def test_hybrid_mode():
    from app.services.archive_service_router import ArchiveServiceRouter
    
    router = ArchiveServiceRouter()
    
    try:
        records, stats = await router.query_archive(
            domain="example.com",
            from_date="20240101",
            to_date="20240131",
            project_config={
                "archive_source": "hybrid",
                "fallback_enabled": True
            }
        )
        
        print(f"✓ Hybrid mode: Retrieved {len(records)} records")
        print(f"  Primary source: {stats.get('primary_source')}")
        print(f"  Successful source: {stats.get('successful_source')}")
        print(f"  Fallback used: {stats.get('fallback_used', False)}")
        
    except Exception as e:
        print(f"❌ Hybrid mode failed: {e}")
```

### Integration Testing

Test the complete scraping pipeline with new archive sources:

```bash
# Run comprehensive integration tests
docker compose exec backend pytest tests/test_archive_pipeline_e2e.py -v
docker compose exec backend pytest tests/test_project_api_archive_sources.py -v
```

### Performance Testing

Compare performance before and after migration:

```python
# Performance comparison script
import time
import asyncio
from app.services.wayback_machine import CDXAPIClient
from app.services.archive_service_router import ArchiveServiceRouter

async def performance_comparison():
    domain = "example.com"
    from_date = "20240101"
    to_date = "20240131"
    
    # Test original Wayback Machine client
    print("Testing original Wayback Machine client...")
    start_time = time.time()
    async with CDXAPIClient() as client:
        records_wb, stats_wb = await client.fetch_cdx_records_simple(
            domain_name=domain, from_date=from_date, to_date=to_date
        )
    wb_duration = time.time() - start_time
    
    # Test new archive router
    print("Testing new archive router (Wayback Machine)...")
    router = ArchiveServiceRouter()
    start_time = time.time()
    records_router, stats_router = await router.query_archive(
        domain=domain, from_date=from_date, to_date=to_date,
        project_config={"archive_source": "wayback_machine"}
    )
    router_duration = time.time() - start_time
    
    # Compare results
    print(f"\nPerformance Comparison:")
    print(f"Original client: {len(records_wb)} records in {wb_duration:.2f}s")
    print(f"Archive router:  {len(records_router)} records in {router_duration:.2f}s")
    print(f"Overhead: {((router_duration - wb_duration) / wb_duration * 100):.1f}%")
```

## Rollback Procedures

### When to Rollback

Consider rollback if you experience:
- Significant performance degradation
- Archive connectivity issues
- Data inconsistencies
- Critical application errors

### Database Rollback

#### 1. Rollback Schema Changes

```bash
# Rollback to previous migration
docker compose exec backend alembic downgrade -1

# Verify rollback
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "
\d projects
"
```

#### 2. Restore from Backup (If Needed)

```bash
# Stop the application
docker compose down

# Restore database backup
docker compose up -d postgres
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper < backup_pre_migration.sql

# Restart application
docker compose up -d
```

### Configuration Rollback

#### 1. Remove New Environment Variables

Remove archive source variables from `.env`:

```bash
# Comment out or remove new variables
# ARCHIVE_DEFAULT_SOURCE=hybrid
# COMMON_CRAWL_TIMEOUT=180
# WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
# ARCHIVE_FALLBACK_DELAY=1.0
```

#### 2. Restart Services

```bash
docker compose restart backend celery_worker
```

### Code Rollback

If you've updated code to use the new archive router, revert to the original client:

```python
# Revert from new archive router
from app.services.archive_service_router import ArchiveServiceRouter
router = ArchiveServiceRouter()
records, stats = await router.query_archive(...)

# Back to original client
from app.services.wayback_machine import CDXAPIClient
async with CDXAPIClient() as client:
    records, stats = await client.fetch_cdx_records_simple(...)
```

### Validation After Rollback

```bash
# Test that original functionality works
docker compose exec backend pytest tests/test_wayback_machine.py -v

# Verify projects work
docker compose exec backend python -c "
import asyncio
from app.core.database import get_db
from app.models.project import Project
from sqlmodel import select

async def test_rollback():
    async for db in get_db():
        stmt = select(Project).limit(1)
        result = await db.execute(stmt)
        project = result.scalar_one_or_none()
        if project:
            print(f'✓ Project {project.name} is accessible')
            # Archive source column should not exist after rollback
            if hasattr(project, 'archive_source'):
                print('❌ Rollback incomplete - archive_source still exists')
            else:
                print('✓ Rollback successful - archive_source removed')
        break

asyncio.run(test_rollback())
"
```

## Performance Impact

### Expected Performance Changes

#### Memory Usage
- **Baseline increase**: ~15MB for archive router and circuit breakers
- **Per-project overhead**: ~3MB for metrics and configuration
- **Per-query overhead**: ~6KB for routing and metrics

#### CPU Usage
- **Routing logic**: <1% additional CPU per query
- **Circuit breaker logic**: <0.1% additional CPU per query
- **Metrics collection**: <0.5% additional CPU per query

#### Network Usage
- **Single source mode**: No additional network usage
- **Hybrid mode**: Potential 2x network usage during fallback events
- **Health checks**: Minimal periodic health check traffic

### Performance Monitoring

Monitor these metrics during and after migration:

```python
# Performance monitoring script
async def monitor_performance():
    from app.services.archive_service_router import ArchiveServiceRouter
    
    router = ArchiveServiceRouter()
    
    # Get performance metrics
    metrics = router.get_performance_metrics()
    
    print("Archive Source Performance:")
    for source, data in metrics["sources"].items():
        print(f"  {source}:")
        print(f"    Success rate: {data['success_rate']:.1f}%")
        print(f"    Avg response time: {data['avg_response_time']:.2f}s")
        print(f"    Total queries: {data['total_queries']}")
    
    # Get health status
    health = router.get_health_status()
    print(f"\nOverall health: {health['overall_status']}")
```

Run monitoring regularly:

```bash
# Monitor performance every hour
*/60 * * * * docker compose exec backend python /path/to/monitor_performance.py
```

## Troubleshooting Migration Issues

### Common Migration Problems

#### 1. Migration Fails with Schema Error

**Error:**
```
sqlalchemy.exc.OperationalError: (psycopg2.errors.DuplicateColumn) 
column "archive_source" of relation "projects" already exists
```

**Solution:**
```bash
# Check current migration state
docker compose exec backend alembic current

# Check migration history
docker compose exec backend alembic history

# If already migrated, mark as complete
docker compose exec backend alembic stamp head
```

#### 2. New Archive Sources Not Working

**Error:**
```
ModuleNotFoundError: No module named 'cdx_toolkit'
```

**Solution:**
```bash
# Rebuild backend container with new dependencies
docker compose build backend

# Or install directly
docker compose exec backend pip install cdx_toolkit
```

#### 3. Configuration Not Loading

**Error:**
```
AttributeError: 'Settings' object has no attribute 'ARCHIVE_DEFAULT_SOURCE'
```

**Solution:**
```bash
# Restart backend to reload environment
docker compose restart backend

# Verify environment variables
docker compose exec backend env | grep ARCHIVE
```

#### 4. Circuit Breakers Stuck Open

**Error:**
```
ERROR: Circuit breaker open for wayback_machine
```

**Solution:**
```python
# Reset circuit breakers
docker compose exec backend python -c "
from app.services.circuit_breaker import circuit_registry
for name, breaker in circuit_registry.breakers.items():
    breaker.reset()
    print(f'Reset {name} circuit breaker')
"
```

#### 5. Performance Degradation

**Symptoms:**
- Slower query responses
- Higher memory usage
- Increased CPU usage

**Solutions:**

```bash
# Reduce metrics collection
ARCHIVE_METRICS_HISTORY_SIZE=100
ARCHIVE_METRICS_ENABLED=false

# Optimize timeouts
WAYBACK_MACHINE_TIMEOUT=60
COMMON_CRAWL_TIMEOUT=90

# Reduce thread pools
COMMON_CRAWL_THREAD_POOL_SIZE=2
```

### Migration Validation Checklist

Use this checklist to validate successful migration:

```
□ Database schema updated successfully
□ Existing projects still work unchanged  
□ New environment variables loaded
□ Archive router initializes correctly
□ Common Crawl service connects
□ Circuit breakers operational
□ Metrics collection working
□ Performance within acceptable range
□ No errors in application logs
□ Health endpoints return success
```

### Getting Help

If you encounter issues not covered in this guide:

1. **Check application logs**:
   ```bash
   docker compose logs -f backend | grep -i archive
   ```

2. **Enable debug logging**:
   ```bash
   ARCHIVE_LOG_LEVEL=DEBUG
   docker compose restart backend
   ```

3. **Run diagnostic script**:
   ```bash
   docker compose exec backend python -c "
   from app.services.archive_service_router import ArchiveServiceRouter
   router = ArchiveServiceRouter()
   print('Health:', router.get_health_status())
   print('Metrics:', router.get_performance_metrics())
   "
   ```

4. **Test individual components**:
   ```bash
   # Test Wayback Machine
   docker compose exec backend pytest tests/test_wayback_machine.py -v
   
   # Test Common Crawl
   docker compose exec backend pytest tests/test_common_crawl_service.py -v
   
   # Test Archive Router
   docker compose exec backend pytest tests/test_archive_service_router.py -v
   ```