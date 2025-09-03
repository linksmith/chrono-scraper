# DuckDB Parquet Partitioning Strategy and Performance Recommendations

## Overview
This document outlines the comprehensive partitioning strategy and performance optimizations for the Chrono Scraper DuckDB analytics system. The strategy is designed to deliver 5-10x performance improvements over PostgreSQL for analytical workloads.

## Partitioning Strategy by Table

### 1. CDX Records (`cdx_records.parquet`)
**Partition Key:** `archive_date` (daily partitions)
**Sub-partitioning:** By `source` (Wayback Machine vs Common Crawl)

```sql
-- Partition structure
/analytics/data/cdx_records/
  year=2024/
    month=01/
      day=01/
        source=wayback_machine/
        source=common_crawl/
      day=02/
        source=wayback_machine/
        source=common_crawl/
```

**Rationale:**
- Daily partitions optimize for time-range queries (most common pattern)
- Source sub-partitioning enables efficient archive source comparisons
- Partition pruning eliminates 90%+ of data for typical queries
- Optimal partition size: 1-10M records per partition

### 2. Content Analytics (`content_analytics.parquet`)
**Partition Key:** `processing_date` (daily partitions)
**Sub-partitioning:** By `extraction_method` (firecrawl, intelligent, fallback)

```sql
-- Partition structure
/analytics/data/content_analytics/
  year=2024/
    month=01/
      day=01/
        method=firecrawl/
        method=intelligent/
        method=fallback/
```

**Rationale:**
- Processing date aligns with operational queries and monitoring
- Extraction method sub-partitioning enables method effectiveness analysis
- Supports both real-time monitoring and historical analysis

### 3. Project Analytics (`project_analytics.parquet`)
**Partition Key:** `analytics_date` (daily partitions)
**Sub-partitioning:** By `aggregation_level` (project, domain, session)

```sql
-- Partition structure
/analytics/data/project_analytics/
  year=2024/
    month=01/
      day=01/
        level=project/
        level=domain/
        level=session/
```

**Rationale:**
- Aggregation level partitioning enables efficient drill-down queries
- Daily partitions support both operational dashboards and trend analysis
- Separate aggregation levels prevent query complexity

### 4. Events (`events.parquet`)
**Partition Key:** `event_date` + `event_hour` (hourly partitions)
**Sub-partitioning:** By `event_type` (user_interaction, system_metric, pipeline_stage, etc.)

```sql
-- Partition structure
/analytics/data/events/
  year=2024/
    month=01/
      day=01/
        hour=00/
          type=user_interaction/
          type=system_metric/
          type=pipeline_stage/
        hour=01/
          type=user_interaction/
          type=system_metric/
          type=pipeline_stage/
```

**Rationale:**
- Hourly partitions handle high-frequency event ingestion
- Event type sub-partitioning optimizes for specific analytics use cases
- Enables efficient retention policies and data lifecycle management

## Performance Optimizations

### 1. Column Store Optimizations

#### Data Type Selection
```sql
-- Optimized data types for compression and performance
SMALLINT     -- For years (2024) vs INTEGER saves 50% space
TINYINT      -- For months (1-12), hours (0-23), days (1-31)
BIGINT       -- For timestamps and large counts
VARCHAR      -- For strings (dictionary compression)
FLOAT        -- For scores and ratios
BOOLEAN      -- For flags
```

#### Column Ordering Strategy
```sql
-- Order columns by query frequency and cardinality
-- 1. Time columns (most frequently filtered)
-- 2. Entity IDs (for joins)  
-- 3. Categorical columns (for grouping)
-- 4. Numeric metrics (for aggregation)
-- 5. Text fields (least frequently accessed)
```

### 2. Compression Configuration

#### Parquet Compression Settings
```python
# Recommended Parquet write settings
parquet_settings = {
    'compression': 'snappy',           # Best balance of speed vs size
    'compression_level': 6,            # Optimal compression level
    'page_size': 1024 * 1024,         # 1MB pages for columnar efficiency
    'row_group_size': 50 * 1024 * 1024, # 50MB row groups
    'dictionary_encoding': True,       # Enable dictionary compression
    'use_dictionary': True,
    'write_statistics': True,          # Enable column statistics
    'use_deprecated_int96_timestamps': False
}
```

#### Column-Specific Compression
```sql
-- String columns with high repetition
VARCHAR columns -> Dictionary encoding (90% compression)
-- Timestamp columns  
TIMESTAMP columns -> Delta encoding + bit packing
-- Numeric columns with ranges
INTEGER columns -> Delta encoding + bit packing
-- Boolean columns
BOOLEAN columns -> Bit packing (8:1 compression)
```

### 3. Index Strategy

#### Clustered Indexes (Primary Sort Order)
```sql
-- CDX Records: Optimize for time-range + domain queries
CLUSTER BY (archive_date, domain, archive_timestamp)

-- Content Analytics: Optimize for processing date + method
CLUSTER BY (processing_date, extraction_method, content_id)

-- Project Analytics: Optimize for project + date queries  
CLUSTER BY (project_id, analytics_date, domain_id)

-- Events: Optimize for time-range + type queries
CLUSTER BY (event_date, event_hour, event_type, event_timestamp)
```

#### Secondary Indexes
```sql
-- Create indexes for common query patterns
CREATE INDEX CONCURRENTLY ON cdx_records 
  USING btree (domain, archive_date) 
  WHERE archive_date >= '2024-01-01';

-- Partial indexes for active data
CREATE INDEX CONCURRENTLY ON project_analytics 
  USING btree (user_id, analytics_date)
  WHERE analytics_date >= current_date - interval '90 days';
```

### 4. Query Optimization Patterns

#### Partition Pruning
```sql
-- Always include partition keys in WHERE clauses
SELECT * FROM cdx_records 
WHERE archive_date BETWEEN '2024-01-01' AND '2024-01-31'  -- Prunes to Jan 2024
  AND source = 'wayback_machine';                          -- Sub-partition pruning

-- Avoid functions on partition keys
-- BAD: WHERE EXTRACT(year FROM archive_date) = 2024
-- GOOD: WHERE archive_date >= '2024-01-01' AND archive_date < '2025-01-01'
```

#### Projection Pushdown
```sql
-- Select only required columns for massive performance gains
SELECT domain, COUNT(*), AVG(content_length)  -- Only these columns read
FROM cdx_records
WHERE archive_date = '2024-01-15'
GROUP BY domain;

-- Avoid SELECT * on wide tables
```

#### Predicate Pushdown
```sql
-- Push filters down to Parquet file level
SELECT * FROM content_analytics
WHERE processing_date = '2024-01-15'      -- Partition filter
  AND extraction_method = 'firecrawl'     -- Sub-partition filter  
  AND content_quality_score > 0.8;       -- Column filter (pushed to Parquet)
```

### 5. Memory and Resource Configuration

#### DuckDB Settings for Analytics Workload
```sql
-- Configure DuckDB for analytical performance
SET memory_limit='16GB';                    -- Adjust based on available RAM
SET threads=8;                              -- Match CPU cores
SET max_memory='75%';                       -- Use 75% of available memory
SET enable_profiling='true';                -- Enable query profiling
SET enable_progress_bar='true';             -- Show progress for long queries
SET preserved_identifier_case='false';      -- Case-insensitive identifiers
```

#### Connection Pool Settings
```python
# DuckDB connection configuration
connection_config = {
    'memory_limit': '16GB',
    'threads': 8,
    'max_memory': '75%',
    'enable_object_cache': True,
    'enable_http_metadata_cache': True,
    'http_timeout': 30000,  # 30 seconds
    'enable_external_access': True,
    'allow_unsigned_extensions': True
}
```

## Storage Layout Optimization

### 1. File Organization
```
/analytics/data/
├── cdx_records/
│   ├── year=2024/month=01/day=01/source=wayback_machine/
│   │   ├── part-00000-uuid.parquet (target: 50-100MB each)
│   │   ├── part-00001-uuid.parquet
│   │   └── ...
│   └── year=2024/month=01/day=01/source=common_crawl/
│       ├── part-00000-uuid.parquet
│       └── ...
├── content_analytics/
├── project_analytics/
└── events/
```

### 2. File Size Optimization
- **Target file size:** 50-100MB per Parquet file
- **Row group size:** 50MB (optimal for columnar access)
- **Page size:** 1MB (balance between compression and seek performance)
- **Files per partition:** 10-50 files (avoid small file problem)

### 3. Compaction Strategy
```sql
-- Regular compaction to optimize file sizes
-- Run daily/weekly depending on ingestion rate
COPY (
  SELECT * FROM cdx_records 
  WHERE archive_date = '2024-01-15'
) TO '/analytics/data/cdx_records/year=2024/month=01/day=15/compacted.parquet'
(FORMAT PARQUET, COMPRESSION 'snappy', ROW_GROUP_SIZE 52428800);
```

## Data Lifecycle Management

### 1. Retention Policies
```sql
-- Automated retention based on data age and access patterns
-- Hot data: 0-90 days (full resolution)
-- Warm data: 91-365 days (daily aggregates)  
-- Cold data: 365+ days (weekly/monthly aggregates)

-- Example retention implementation
DELETE FROM events 
WHERE event_date < current_date - interval '2 years'
  AND event_type NOT IN ('critical_error', 'security_event');
```

### 2. Archival Strategy
```python
# Archive old partitions to cheaper storage
def archive_partition(table_name, partition_date):
    # Move to S3/GCS cold storage
    source_path = f"/analytics/data/{table_name}/year={partition_date.year}/month={partition_date.month}/day={partition_date.day}/"
    archive_path = f"s3://analytics-archive/{table_name}/{partition_date.isoformat()}/"
    
    # Compress and move
    compress_and_move(source_path, archive_path)
    
    # Update metadata
    update_catalog(table_name, partition_date, archive_path)
```

## Expected Performance Improvements

### 1. Query Performance Gains
- **Time-range queries:** 10-50x faster due to partition pruning
- **Aggregation queries:** 5-20x faster due to columnar storage
- **Analytics dashboards:** 3-15x faster due to optimized data layout
- **Complex joins:** 2-8x faster due to better compression and caching

### 2. Storage Efficiency
- **Compression ratio:** 70-90% reduction in storage size
- **I/O reduction:** 80-95% reduction in data read for analytical queries
- **Network transfer:** 85-95% reduction for remote queries

### 3. Operational Benefits
- **Backup/restore:** 10x faster due to smaller data size
- **Data transfer:** 5-10x faster between environments
- **Query concurrency:** 3-5x more concurrent analytical queries
- **Resource utilization:** 50-80% reduction in memory and CPU usage

## Monitoring and Maintenance

### 1. Performance Monitoring
```sql
-- Query performance monitoring
SELECT 
    query_text,
    avg(execution_time_ms) as avg_execution_time,
    count(*) as query_count,
    sum(rows_scanned) as total_rows_scanned,
    sum(bytes_scanned) as total_bytes_scanned
FROM query_log 
WHERE log_date >= current_date - 7
GROUP BY query_text
ORDER BY avg_execution_time DESC
LIMIT 10;
```

### 2. Partition Health Checks
```sql
-- Partition size and health monitoring
SELECT 
    table_name,
    partition_key,
    file_count,
    total_size_mb,
    avg_file_size_mb,
    compression_ratio
FROM partition_stats
WHERE total_size_mb > 1000  -- Large partitions
   OR avg_file_size_mb < 10; -- Small file problem
```

This partitioning strategy and optimization approach should deliver the target 5-10x performance improvements while maintaining data governance and operational efficiency.