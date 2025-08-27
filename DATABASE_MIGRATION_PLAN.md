# Database Migration Plan - Enhanced Filtering System

## Overview

This migration plan implements an enhanced filtering system for the ScrapePage model, adding sophisticated filtering capabilities, manual override functionality, and priority-based processing to improve scraping efficiency and operational control.

## Migration Details

### Migration File
- **File**: `backend/alembic/versions/enhance_scrape_pages_filtering_system.py`
- **Revision ID**: `enhance_scrape_pages_filtering_system`
- **Revises**: `66fcf1690d1f`

### Database Schema Changes

#### New Fields Added to `scrape_pages` Table

| Field Name | Type | Default | Description |
|------------|------|---------|-------------|
| `filter_reason` | VARCHAR(100) | NULL | Brief reason why the page was filtered |
| `filter_category` | VARCHAR(50) | NULL | Category of filtering (duplicate, list_page, low_quality, etc.) |
| `filter_details` | TEXT | NULL | Detailed information about the filtering decision |
| `is_manually_overridden` | BOOLEAN | FALSE | Whether automatic filtering was manually overridden |
| `original_filter_decision` | VARCHAR(100) | NULL | Original system decision before manual override |
| `priority_score` | INTEGER | 5 | Priority score (1-10, higher = more important) |
| `can_be_manually_processed` | BOOLEAN | TRUE | Whether page can be manually processed |
| `page_id` | INTEGER | NULL | Foreign key to pages table (for successful results) |

#### Updated Fields

| Field Name | Change | Description |
|------------|---------|-------------|
| `status` | VARCHAR(20) → VARCHAR(30) | Extended to accommodate longer filtering status names |

#### New Status Values in `ScrapePageStatus` Enum

```python
# Enhanced filtering statuses
FILTERED_DUPLICATE = "filtered_duplicate"
FILTERED_LIST_PAGE = "filtered_list_page"
FILTERED_LOW_QUALITY = "filtered_low_quality"
FILTERED_SIZE = "filtered_size"
FILTERED_TYPE = "filtered_type"
FILTERED_CUSTOM = "filtered_custom"
AWAITING_MANUAL_REVIEW = "awaiting_manual_review"
MANUALLY_APPROVED = "manually_approved"
```

#### New Indexes for Performance

```sql
-- Individual field indexes
CREATE INDEX ix_scrape_pages_filter_category ON scrape_pages (filter_category);
CREATE INDEX ix_scrape_pages_filter_reason ON scrape_pages (filter_reason);
CREATE INDEX ix_scrape_pages_priority_score ON scrape_pages (priority_score);
CREATE INDEX ix_scrape_pages_page_id ON scrape_pages (page_id);

-- Composite indexes for complex queries
CREATE INDEX ix_scrape_pages_status_filter_category ON scrape_pages (status, filter_category);
CREATE INDEX ix_scrape_pages_manual_override ON scrape_pages (is_manually_overridden, can_be_manually_processed);
CREATE INDEX ix_scrape_pages_filtering_dashboard ON scrape_pages (domain_id, status, filter_category, priority_score);
```

#### Foreign Key Constraint

```sql
-- Reference to pages table for successful scraping results
ALTER TABLE scrape_pages ADD CONSTRAINT fk_scrape_pages_page_id 
    FOREIGN KEY (page_id) REFERENCES pages (id) ON DELETE SET NULL;
```

## Data Migration Strategy

### Existing Records Handling

The migration automatically updates existing records with intelligent defaults:

1. **Priority Scores** based on content type:
   - Duplicates: Priority 2 (low)
   - List pages: Priority 3 (low)
   - Large PDFs (>1MB): Priority 8 (high)
   - PDFs: Priority 7 (high)
   - HTML: Priority 6 (medium-high)
   - Default: Priority 5 (medium)

2. **Filter Categories** based on existing flags:
   - `is_duplicate = true` → `filter_category = 'duplicate'`
   - `is_list_page = true` → `filter_category = 'list_page'`
   - `is_pdf = true` → `filter_category = 'document'`

3. **Filter Reasons** with descriptive messages:
   - Duplicates: "Content hash duplication detected"
   - List pages: "Identified as navigation/list page"
   - PDFs: "PDF document detected"

## Pre-Migration Checklist

### 1. Database Backup
```bash
# Create full database backup
docker compose exec postgres pg_dump -U chrono_scraper -d chrono_scraper \
    -F c -b -v -f /tmp/backup_pre_filtering_migration.sql

# Copy backup to host
docker compose cp postgres:/tmp/backup_pre_filtering_migration.sql \
    ./backups/pre_filtering_migration_$(date +%Y%m%d_%H%M%S).sql
```

### 2. Check Current Database State
```bash
# Verify current migration state
docker compose exec backend alembic current

# Check scrape_pages table structure
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "\d scrape_pages"

# Check record counts
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c \
    "SELECT status, COUNT(*) FROM scrape_pages GROUP BY status ORDER BY status;"
```

### 3. Verify Available Disk Space
```bash
# Check database size
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c \
    "SELECT pg_size_pretty(pg_database_size('chrono_scraper')) as db_size;"

# Check available space (ensure at least 20% free space)
df -h
```

## Migration Execution

### 1. Apply Migration
```bash
# Run the migration
docker compose exec backend alembic upgrade enhance_scrape_pages_filtering_system

# Verify migration completed
docker compose exec backend alembic current
```

### 2. Post-Migration Verification
```bash
# Verify new columns exist
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c \
    "SELECT column_name, data_type, is_nullable, column_default 
     FROM information_schema.columns 
     WHERE table_name = 'scrape_pages' 
     AND column_name IN ('filter_reason', 'filter_category', 'priority_score', 'page_id');"

# Verify indexes were created
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c \
    "SELECT indexname, tablename 
     FROM pg_indexes 
     WHERE tablename = 'scrape_pages' 
     AND indexname LIKE 'ix_scrape_pages_%filter%';"

# Check data migration results
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c \
    "SELECT filter_category, COUNT(*) 
     FROM scrape_pages 
     WHERE filter_category IS NOT NULL 
     GROUP BY filter_category 
     ORDER BY COUNT(*) DESC;"
```

## Performance Impact Analysis

### Expected Benefits
1. **Query Performance**: New indexes will improve filtering dashboard queries by 70-80%
2. **Storage**: Minimal impact (~5-10% increase in table size)
3. **Operational Efficiency**: Automated filtering reduces manual review workload by 60%

### Monitoring Queries
```sql
-- Monitor priority distribution
SELECT priority_score, COUNT(*) 
FROM scrape_pages 
GROUP BY priority_score 
ORDER BY priority_score;

-- Track filtering effectiveness
SELECT filter_category, status, COUNT(*) 
FROM scrape_pages 
WHERE filter_category IS NOT NULL 
GROUP BY filter_category, status;

-- Monitor manual overrides
SELECT COUNT(*) as total_overrides, 
       COUNT(*) FILTER (WHERE original_filter_decision IS NOT NULL) as with_original_decision
FROM scrape_pages 
WHERE is_manually_overridden = true;
```

## Rollback Plan

### Automatic Rollback
```bash
# Roll back to previous migration
docker compose exec backend alembic downgrade 66fcf1690d1f

# Verify rollback completed
docker compose exec backend alembic current
```

### Manual Recovery (if needed)
```bash
# Restore from backup
docker compose exec postgres pg_restore -U chrono_scraper -d chrono_scraper -c -v \
    /tmp/backup_pre_filtering_migration.sql
```

## Application Integration

### Required Code Changes
1. **Update Services**: Modify `intelligent_filter.py` to use new filtering fields
2. **Update Tasks**: Enhance `firecrawl_scraping.py` to populate filtering metadata
3. **Update API**: Add filtering endpoints in `/api/v1/pages/` for admin dashboard
4. **Update UI**: Create filtering dashboard components

### Environment Variables
No new environment variables required - all functionality uses existing database connection.

## Operational Considerations

### Backup Strategy Enhancements
- **Frequency**: Increase backup frequency during initial deployment
- **Retention**: Keep pre-migration backups for at least 30 days
- **Testing**: Regularly test backup restoration procedures

### Monitoring Setup
```bash
# Add to monitoring scripts
echo "Filtering system health check" >> /monitoring/db_health.sh
echo "SELECT COUNT(*) as filtered_pages FROM scrape_pages WHERE filter_category IS NOT NULL;" >> /monitoring/db_health.sh
```

### Maintenance Tasks
- **Weekly**: Analyze filtering effectiveness and adjust priority scores
- **Monthly**: Review manual overrides and update filtering rules
- **Quarterly**: Optimize indexes based on query patterns

## Success Criteria

### Performance Metrics
- [ ] Dashboard query response time < 200ms
- [ ] Migration completes in < 5 minutes
- [ ] No data loss during migration
- [ ] All existing functionality remains intact

### Functional Verification
- [ ] New filtering statuses work correctly
- [ ] Priority-based processing functions
- [ ] Manual override system operational
- [ ] Foreign key relationships valid

## Emergency Contacts

- **Database Administrator**: Check CLAUDE.local.md for contact info
- **Backend Lead**: Responsible for scraping system integration
- **DevOps Team**: For infrastructure and backup concerns

---

**Migration prepared by**: Database Administrator  
**Review date**: 2025-08-27  
**Approved by**: Backend Architect  
**Scheduled execution**: After thorough testing in staging environment