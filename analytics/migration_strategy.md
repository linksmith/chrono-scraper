# PostgreSQL to DuckDB Migration Strategy

## Overview
This document provides a comprehensive migration strategy for moving Chrono Scraper analytics from PostgreSQL to DuckDB with Parquet storage, targeting 5-10x performance improvements.

## Migration Phases

### Phase 1: Infrastructure Setup and Historical Data Migration (2-3 weeks)

#### 1.1 DuckDB Environment Setup
```python
# analytics/setup/duckdb_setup.py
import duckdb
import os
from pathlib import Path

def setup_duckdb_environment():
    """Initialize DuckDB analytics environment"""
    
    # Create directory structure
    analytics_path = Path("/analytics")
    data_path = analytics_path / "data"
    schemas_path = analytics_path / "schemas"
    scripts_path = analytics_path / "scripts"
    
    for path in [data_path, schemas_path, scripts_path]:
        path.mkdir(parents=True, exist_ok=True)
    
    # Initialize DuckDB connection with optimized settings
    conn = duckdb.connect('/analytics/chrono_analytics.db')
    
    # Configure for analytical workload
    conn.execute("""
        SET memory_limit='16GB';
        SET threads=8;
        SET max_memory='75%';
        SET enable_profiling='true';
        SET enable_progress_bar='true';
    """)
    
    # Create schemas
    conn.execute("CREATE SCHEMA IF NOT EXISTS analytics;")
    conn.execute("CREATE SCHEMA IF NOT EXISTS staging;")
    
    return conn

def create_external_tables(conn):
    """Create external Parquet tables"""
    
    # CDX Records external table
    conn.execute("""
        CREATE OR REPLACE TABLE analytics.cdx_records AS 
        SELECT * FROM read_parquet('/analytics/data/cdx_records/**/*.parquet',
                                  hive_partitioning=true);
    """)
    
    # Content Analytics external table  
    conn.execute("""
        CREATE OR REPLACE TABLE analytics.content_analytics AS
        SELECT * FROM read_parquet('/analytics/data/content_analytics/**/*.parquet',
                                  hive_partitioning=true);
    """)
    
    # Project Analytics external table
    conn.execute("""
        CREATE OR REPLACE TABLE analytics.project_analytics AS
        SELECT * FROM read_parquet('/analytics/data/project_analytics/**/*.parquet', 
                                  hive_partitioning=true);
    """)
    
    # Events external table
    conn.execute("""
        CREATE OR REPLACE TABLE analytics.events AS
        SELECT * FROM read_parquet('/analytics/data/events/**/*.parquet',
                                  hive_partitioning=true);
    """)
```

#### 1.2 Historical Data Migration Script
```python
# analytics/migration/historical_migration.py
import asyncio
import asyncpg
import duckdb
import pandas as pd
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Any

class HistoricalMigration:
    def __init__(self, postgres_dsn: str, duckdb_path: str):
        self.postgres_dsn = postgres_dsn
        self.duckdb_path = duckdb_path
        self.logger = logging.getLogger(__name__)
        
    async def migrate_cdx_records(self, start_date: datetime, end_date: datetime):
        """Migrate CDX records from PostgreSQL to Parquet"""
        
        # Connect to PostgreSQL
        pg_conn = await asyncpg.connect(self.postgres_dsn)
        
        # Connect to DuckDB
        duck_conn = duckdb.connect(self.duckdb_path)
        
        try:
            # Process in monthly chunks to manage memory
            current_date = start_date
            while current_date <= end_date:
                next_month = current_date.replace(day=1) + timedelta(days=32)
                next_month = next_month.replace(day=1)
                
                self.logger.info(f"Migrating CDX records for {current_date.strftime('%Y-%m')}")
                
                # Extract from PostgreSQL
                query = """
                SELECT 
                    -- Generate record_id
                    md5(original_url || unix_timestamp::text) as record_id,
                    original_url,
                    SPLIT_PART(original_url, '/', 3) as domain,
                    CASE 
                        WHEN SPLIT_PART(original_url, '/', 3) LIKE '%.%'
                        THEN SPLIT_PART(SPLIT_PART(original_url, '/', 3), '.', 1)
                        ELSE NULL
                    END as subdomain,
                    SPLIT_PART(original_url, '?', 1) as url_path,
                    CASE WHEN original_url LIKE '%?%' 
                         THEN SUBSTRING(original_url FROM POSITION('?' IN original_url) + 1)
                         ELSE NULL 
                    END as url_params,
                    
                    -- Time fields
                    DATE(TO_TIMESTAMP(unix_timestamp::bigint)) as archive_date,
                    unix_timestamp::bigint as archive_timestamp,
                    EXTRACT(year FROM TO_TIMESTAMP(unix_timestamp::bigint))::smallint as archive_year,
                    EXTRACT(month FROM TO_TIMESTAMP(unix_timestamp::bigint))::smallint as archive_month,
                    EXTRACT(day FROM TO_TIMESTAMP(unix_timestamp::bigint))::smallint as archive_day,
                    EXTRACT(hour FROM TO_TIMESTAMP(unix_timestamp::bigint))::smallint as archive_hour,
                    EXTRACT(dow FROM TO_TIMESTAMP(unix_timestamp::bigint))::smallint as archive_weekday,
                    
                    -- Source information
                    'WAYBACK_MACHINE' as source,  -- Assuming Wayback for historical data
                    NULL as warc_filename,
                    NULL::bigint as warc_offset,
                    NULL::integer as warc_length,
                    
                    -- Content fields
                    mime_type,
                    CASE 
                        WHEN mime_type LIKE 'text/html%' THEN 'html'
                        WHEN mime_type LIKE 'application/pdf%' THEN 'pdf'
                        WHEN mime_type LIKE 'image/%' THEN 'image'
                        ELSE 'other'
                    END as content_category,
                    status_code::smallint,
                    content_length::bigint,
                    CASE 
                        WHEN content_length < 1024 THEN 'tiny'
                        WHEN content_length < 10240 THEN 'small'
                        WHEN content_length < 102400 THEN 'medium'
                        WHEN content_length < 1048576 THEN 'large'
                        ELSE 'huge'
                    END as content_size_category,
                    digest_hash,
                    
                    -- URL analysis
                    (LENGTH(original_url) - LENGTH(REPLACE(original_url, '/', '')))::smallint as url_depth,
                    (original_url LIKE '%?%') as has_query_params,
                    CASE 
                        WHEN original_url ~ '\.[a-zA-Z0-9]+$' 
                        THEN SUBSTRING(original_url FROM '\.([a-zA-Z0-9]+)$')
                        ELSE NULL
                    END as file_extension,
                    (SPLIT_PART(original_url, '/', 4) = '' OR SPLIT_PART(original_url, '/', 4) IS NULL) as is_root_page,
                    is_list_page as is_list_page_pattern,
                    
                    -- Domain classification
                    SPLIT_PART(SPLIT_PART(original_url, '/', 3), '.', -1) as domain_tld,
                    CASE 
                        WHEN original_url LIKE '%.gov%' THEN 'government'
                        WHEN original_url LIKE '%.edu%' THEN 'educational'
                        WHEN original_url LIKE '%.org%' THEN 'nonprofit'
                        ELSE 'commercial'
                    END as domain_category,
                    (original_url LIKE '%.gov%') as is_government_domain,
                    (original_url LIKE '%.edu%') as is_educational_domain,
                    (original_url LIKE '%.org%') as is_nonprofit_domain,
                    
                    -- Processing metadata
                    CURRENT_DATE as processing_date,
                    'historical_migration' as processing_batch_id,
                    COALESCE(priority_score::float / 10.0, 0.5) as quality_score,
                    COALESCE(priority_score, 5) as priority_score,
                    
                    -- Filtering information
                    CASE 
                        WHEN status = 'FILTERED_LIST_PAGE' THEN 'list_page'
                        WHEN status = 'FILTERED_ALREADY_PROCESSED' THEN 'duplicate'
                        WHEN status = 'SKIPPED' THEN 'skipped'
                        ELSE NULL
                    END as filter_reason,
                    is_duplicate,
                    (priority_score > 7) as is_high_value_content,
                    
                    -- Performance metrics (estimated from historical data)
                    fetch_time as fetch_time_ms,
                    extraction_time as extraction_time_ms,
                    total_processing_time as total_processing_time_ms,
                    
                    -- Timestamps
                    created_at,
                    updated_at
                    
                FROM scrape_pages
                WHERE created_at >= $1 AND created_at < $2
                ORDER BY created_at
                """
                
                records = await pg_conn.fetch(query, current_date, next_month)
                
                if records:
                    # Convert to DataFrame
                    df = pd.DataFrame(records)
                    
                    # Write to Parquet with partitioning
                    output_path = f"/analytics/data/cdx_records/year={current_date.year}/month={current_date.month:02d}/"
                    os.makedirs(output_path, exist_ok=True)
                    
                    parquet_file = f"{output_path}/cdx_records_{current_date.strftime('%Y_%m')}.parquet"
                    df.to_parquet(
                        parquet_file,
                        compression='snappy',
                        index=False,
                        partition_cols=None  # Already partitioned by directory structure
                    )
                    
                    self.logger.info(f"Migrated {len(records)} CDX records for {current_date.strftime('%Y-%m')}")
                
                current_date = next_month
                
        finally:
            await pg_conn.close()
            duck_conn.close()
    
    async def migrate_content_analytics(self, start_date: datetime, end_date: datetime):
        """Migrate content analytics from PostgreSQL"""
        
        pg_conn = await asyncpg.connect(self.postgres_dsn)
        
        try:
            query = """
            SELECT 
                -- Primary identifiers
                md5(sp.original_url || sp.unix_timestamp) as content_id,
                NULL as page_id,  -- Will be populated in Phase 2
                sp.id as scrape_page_id,
                md5(sp.original_url || sp.unix_timestamp) as cdx_record_id,
                
                -- Source information
                sp.original_url,
                sp.content_url,
                SPLIT_PART(sp.original_url, '/', 3) as domain,
                
                -- Time fields
                DATE(sp.created_at) as processing_date,
                sp.created_at as processing_timestamp,
                EXTRACT(year FROM sp.created_at)::smallint as processing_year,
                EXTRACT(month FROM sp.created_at)::smallint as processing_month,
                EXTRACT(week FROM sp.created_at)::smallint as processing_week,
                
                -- Content characteristics
                sp.mime_type,
                sp.mime_type as content_type,
                CASE 
                    WHEN sp.mime_type LIKE 'text/html%' THEN 'html'
                    WHEN sp.mime_type LIKE 'application/pdf%' THEN 'pdf'
                    ELSE 'other'
                END as content_category,
                sp.content_length as original_size_bytes,
                NULL::bigint as compressed_size_bytes,
                
                -- Extraction metrics
                COALESCE(sp.extraction_method, 'unknown') as extraction_method,
                CASE 
                    WHEN sp.status IN ('COMPLETED') THEN 'success'
                    WHEN sp.status IN ('FAILED') THEN 'failed'
                    ELSE 'partial'
                END as extraction_status,
                0.8 as extraction_confidence,  -- Default confidence
                sp.extraction_time as extraction_time_ms,
                sp.error_type as extraction_error_type,
                sp.retry_count as extraction_retry_count,
                
                -- Content quality
                (sp.title IS NOT NULL) as title_extracted,
                LENGTH(sp.extracted_text) as text_content_length,
                LENGTH(sp.markdown_content) as markdown_content_length,
                -- Estimate word count
                CASE 
                    WHEN sp.extracted_text IS NOT NULL 
                    THEN (LENGTH(sp.extracted_text) - LENGTH(REPLACE(sp.extracted_text, ' ', '')) + 1)
                    ELSE 0
                END as word_count,
                -- Estimate paragraph count
                CASE 
                    WHEN sp.extracted_text IS NOT NULL
                    THEN (LENGTH(sp.extracted_text) - LENGTH(REPLACE(sp.extracted_text, E'\n', '')) + 1)
                    ELSE 0
                END as paragraph_count,
                
                'en' as language,  -- Default to English
                0.9 as language_confidence,
                
                -- Quality scores
                COALESCE(sp.priority_score::float / 10.0, 0.5) as content_quality_score,
                0.7 as readability_score,  -- Default score
                0.6 as information_density,
                0.8 as structural_completeness,
                
                -- Processing flags
                sp.is_list_page,
                sp.is_duplicate as is_duplicate_content,
                (LENGTH(sp.extracted_text) > 100) as has_meaningful_content,
                FALSE as is_machine_generated,
                FALSE as contains_personal_info,
                
                -- Performance metrics
                sp.fetch_time as fetch_time_ms,
                sp.extraction_time as parse_time_ms,
                NULL::integer as nlp_processing_time_ms,
                NULL::integer as indexing_time_ms,
                sp.total_processing_time as total_processing_time_ms,
                
                -- Error tracking
                sp.error_message,
                sp.error_type as error_category,
                NULL as error_stack_trace,
                (sp.retry_count < sp.max_retries) as is_recoverable_error,
                
                -- Timestamps
                sp.created_at,
                sp.updated_at
                
            FROM scrape_pages sp
            WHERE sp.created_at >= $1 AND sp.created_at < $2
            ORDER BY sp.created_at
            """
            
            current_date = start_date
            while current_date <= end_date:
                next_month = current_date.replace(day=1) + timedelta(days=32)
                next_month = next_month.replace(day=1)
                
                self.logger.info(f"Migrating content analytics for {current_date.strftime('%Y-%m')}")
                
                records = await pg_conn.fetch(query, current_date, next_month)
                
                if records:
                    df = pd.DataFrame(records)
                    
                    output_path = f"/analytics/data/content_analytics/year={current_date.year}/month={current_date.month:02d}/"
                    os.makedirs(output_path, exist_ok=True)
                    
                    parquet_file = f"{output_path}/content_analytics_{current_date.strftime('%Y_%m')}.parquet"
                    df.to_parquet(parquet_file, compression='snappy', index=False)
                    
                    self.logger.info(f"Migrated {len(records)} content analytics records")
                
                current_date = next_month
                
        finally:
            await pg_conn.close()

# Usage
async def run_historical_migration():
    migration = HistoricalMigration(
        postgres_dsn="postgresql://user:pass@localhost:5432/chrono_scraper",
        duckdb_path="/analytics/chrono_analytics.db"
    )
    
    # Migrate last 12 months of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    await migration.migrate_cdx_records(start_date, end_date)
    await migration.migrate_content_analytics(start_date, end_date)
```

### Phase 2: Real-time Data Pipeline Setup (1-2 weeks)

#### 2.1 Streaming ETL Pipeline
```python
# analytics/streaming/realtime_etl.py
import asyncio
import asyncpg
import duckdb
from datetime import datetime, timedelta
import json
from typing import Dict, Any, List

class RealTimeETL:
    def __init__(self, postgres_dsn: str, duckdb_path: str):
        self.postgres_dsn = postgres_dsn
        self.duckdb_path = duckdb_path
        self.last_sync_time = datetime.now() - timedelta(hours=1)
        
    async def sync_new_records(self):
        """Sync new records from PostgreSQL to Parquet"""
        
        pg_conn = await asyncpg.connect(self.postgres_dsn)
        duck_conn = duckdb.connect(self.duckdb_path)
        
        try:
            # Get new scrape_pages records
            new_records = await self.extract_new_scrape_pages(pg_conn)
            
            if new_records:
                # Transform to CDX and Content Analytics format
                cdx_records = self.transform_to_cdx_records(new_records)
                content_records = self.transform_to_content_analytics(new_records)
                
                # Load to Parquet
                await self.load_to_parquet(cdx_records, 'cdx_records')
                await self.load_to_parquet(content_records, 'content_analytics')
                
                self.last_sync_time = datetime.now()
                
        finally:
            await pg_conn.close()
            duck_conn.close()
    
    async def extract_new_scrape_pages(self, pg_conn) -> List[Dict]:
        """Extract new records from PostgreSQL"""
        
        query = """
        SELECT 
            sp.*,
            d.name as domain_name,
            p.name as project_name,
            u.email as user_email
        FROM scrape_pages sp
        JOIN domains d ON sp.domain_id = d.id
        JOIN projects p ON d.project_id = p.id
        JOIN users u ON p.user_id = u.id
        WHERE sp.updated_at > $1
        ORDER BY sp.updated_at
        """
        
        records = await pg_conn.fetch(query, self.last_sync_time)
        return [dict(record) for record in records]
    
    def transform_to_cdx_records(self, records: List[Dict]) -> List[Dict]:
        """Transform scrape_pages to CDX records format"""
        
        cdx_records = []
        for record in records:
            cdx_record = {
                'record_id': f"{record['original_url']}_{record['unix_timestamp']}",
                'original_url': record['original_url'],
                'domain': record['domain_name'],
                'archive_date': datetime.fromtimestamp(int(record['unix_timestamp'])).date(),
                'archive_timestamp': int(record['unix_timestamp']),
                'source': 'WAYBACK_MACHINE',
                'mime_type': record['mime_type'],
                'status_code': record['status_code'],
                'content_length': record['content_length'],
                'digest_hash': record['digest_hash'],
                'quality_score': record.get('priority_score', 5) / 10.0,
                'is_high_value_content': record.get('priority_score', 5) > 7,
                'processing_date': datetime.now().date(),
                'created_at': record['created_at'],
                'updated_at': record['updated_at']
            }
            cdx_records.append(cdx_record)
        
        return cdx_records
    
    async def load_to_parquet(self, records: List[Dict], table_name: str):
        """Load records to partitioned Parquet files"""
        
        if not records:
            return
            
        df = pd.DataFrame(records)
        
        # Group by partition key
        if table_name == 'cdx_records':
            partition_col = 'archive_date'
        else:
            partition_col = 'processing_date'
        
        for date_group, group_df in df.groupby(df[partition_col]):
            date_obj = pd.to_datetime(date_group).date()
            
            output_path = f"/analytics/data/{table_name}/year={date_obj.year}/month={date_obj.month:02d}/day={date_obj.day:02d}/"
            os.makedirs(output_path, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            parquet_file = f"{output_path}/{table_name}_{timestamp}.parquet"
            
            group_df.to_parquet(parquet_file, compression='snappy', index=False)

# Scheduled job for real-time sync
async def run_realtime_sync():
    etl = RealTimeETL(
        postgres_dsn=os.getenv("POSTGRES_DSN"),
        duckdb_path="/analytics/chrono_analytics.db"
    )
    
    while True:
        try:
            await etl.sync_new_records()
            await asyncio.sleep(300)  # Sync every 5 minutes
        except Exception as e:
            logging.error(f"ETL sync error: {e}")
            await asyncio.sleep(60)  # Wait 1 minute on error
```

#### 2.2 Event Streaming Pipeline
```python
# analytics/streaming/event_pipeline.py
from typing import Dict, Any
import json
import asyncio
from datetime import datetime

class EventStreamingPipeline:
    def __init__(self, duckdb_path: str):
        self.duckdb_path = duckdb_path
        self.event_buffer = []
        self.buffer_size = 1000
        
    async def capture_system_event(self, event_type: str, event_data: Dict[str, Any]):
        """Capture system events for analytics"""
        
        event = {
            'event_id': f"{datetime.now().isoformat()}_{event_type}_{hash(str(event_data))}",
            'event_type': event_type,
            'event_timestamp': datetime.now(),
            'event_date': datetime.now().date(),
            'event_hour': datetime.now().hour,
            'event_data': json.dumps(event_data),
            'source_component': event_data.get('source', 'unknown'),
            'created_at': datetime.now()
        }
        
        self.event_buffer.append(event)
        
        if len(self.event_buffer) >= self.buffer_size:
            await self.flush_events()
    
    async def flush_events(self):
        """Flush buffered events to Parquet"""
        
        if not self.event_buffer:
            return
            
        df = pd.DataFrame(self.event_buffer)
        
        # Group by hour for partitioning
        for (date, hour), group_df in df.groupby([df['event_date'], df['event_hour']]):
            output_path = f"/analytics/data/events/year={date.year}/month={date.month:02d}/day={date.day:02d}/hour={hour:02d}/"
            os.makedirs(output_path, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            parquet_file = f"{output_path}/events_{timestamp}.parquet"
            
            group_df.to_parquet(parquet_file, compression='snappy', index=False)
        
        self.event_buffer.clear()

# Integration with existing FastAPI app
from app.middleware.audit_middleware import AuditMiddleware

class AnalyticsEventCapture:
    def __init__(self):
        self.pipeline = EventStreamingPipeline("/analytics/chrono_analytics.db")
    
    async def capture_scraping_event(self, scrape_page_id: int, status: str, processing_time: float):
        """Capture scraping pipeline events"""
        
        event_data = {
            'scrape_page_id': scrape_page_id,
            'pipeline_stage': 'content_extraction',
            'pipeline_status': status,
            'duration_ms': processing_time * 1000,
            'source': 'firecrawl_extractor'
        }
        
        await self.pipeline.capture_system_event('pipeline_stage', event_data)
    
    async def capture_user_interaction(self, user_id: int, action: str, context: Dict):
        """Capture user interaction events"""
        
        event_data = {
            'user_id': user_id,
            'user_action': action,
            'feature_context': context,
            'source': 'web_interface'
        }
        
        await self.pipeline.capture_system_event('user_interaction', event_data)
```

### Phase 3: Analytics Dashboard and API (2-3 weeks)

#### 3.1 DuckDB Analytics Service
```python
# analytics/services/analytics_service.py
import duckdb
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import pandas as pd

class AnalyticsService:
    def __init__(self, duckdb_path: str):
        self.duckdb_path = duckdb_path
        
    def get_connection(self) -> duckdb.DuckDBPyConnection:
        """Get optimized DuckDB connection"""
        
        conn = duckdb.connect(self.duckdb_path, read_only=True)
        
        # Optimize for analytical queries
        conn.execute("""
            SET memory_limit='8GB';
            SET threads=4;
            SET enable_profiling='query_tree_optimizer';
            PRAGMA enable_checkpoint_on_shutdown;
        """)
        
        return conn
    
    async def get_scraping_performance_metrics(self, 
                                             start_date: datetime, 
                                             end_date: datetime,
                                             project_id: Optional[int] = None) -> Dict[str, Any]:
        """Get comprehensive scraping performance metrics"""
        
        conn = self.get_connection()
        
        try:
            # Base filter clause
            filter_clause = "WHERE analytics_date BETWEEN ? AND ?"
            params = [start_date.date(), end_date.date()]
            
            if project_id:
                filter_clause += " AND project_id = ?"
                params.append(project_id)
            
            query = f"""
            SELECT 
                COUNT(*) as total_sessions,
                SUM(total_pages_processed) as total_pages,
                AVG(pages_per_minute) as avg_processing_rate,
                AVG(avg_content_quality_score) as avg_quality,
                AVG(error_rate) * 100 as avg_error_rate,
                SUM(estimated_processing_cost_usd) as total_cost,
                COUNT(DISTINCT domain_id) as unique_domains,
                AVG(avg_processing_time_ms) as avg_processing_time
            FROM project_analytics
            {filter_clause}
            AND aggregation_level = 'project'
            """
            
            result = conn.execute(query, params).fetchone()
            
            # Get daily trends
            trend_query = f"""
            SELECT 
                analytics_date,
                SUM(total_pages_processed) as daily_pages,
                AVG(pages_per_minute) as daily_rate,
                AVG(avg_content_quality_score) as daily_quality
            FROM project_analytics
            {filter_clause}
            AND aggregation_level = 'project'
            GROUP BY analytics_date
            ORDER BY analytics_date
            """
            
            trends = conn.execute(trend_query, params).fetchdf()
            
            return {
                'summary': {
                    'total_sessions': result[0],
                    'total_pages': result[1],
                    'avg_processing_rate': round(result[2], 2),
                    'avg_quality': round(result[3], 3),
                    'avg_error_rate': round(result[4], 2),
                    'total_cost': round(result[5], 2),
                    'unique_domains': result[6],
                    'avg_processing_time': round(result[7], 1)
                },
                'daily_trends': trends.to_dict('records')
            }
            
        finally:
            conn.close()
    
    async def get_domain_analysis(self, 
                                 start_date: datetime, 
                                 end_date: datetime,
                                 limit: int = 50) -> List[Dict[str, Any]]:
        """Get domain performance analysis"""
        
        conn = self.get_connection()
        
        try:
            query = """
            SELECT 
                c.domain,
                c.domain_category,
                COUNT(*) as total_records,
                AVG(c.quality_score) as avg_quality,
                AVG(c.content_length) as avg_content_size,
                COUNT(CASE WHEN c.is_high_value_content THEN 1 END) as high_value_count,
                COUNT(DISTINCT DATE_TRUNC('month', c.archive_date)) as active_months,
                AVG(ca.extraction_time_ms) as avg_extraction_time
            FROM cdx_records c
            LEFT JOIN content_analytics ca ON c.record_id = ca.cdx_record_id
            WHERE c.archive_date BETWEEN ? AND ?
            GROUP BY c.domain, c.domain_category
            HAVING COUNT(*) >= 10
            ORDER BY avg_quality DESC, high_value_count DESC
            LIMIT ?
            """
            
            result = conn.execute(query, [start_date.date(), end_date.date(), limit]).fetchdf()
            return result.to_dict('records')
            
        finally:
            conn.close()
    
    async def get_content_quality_distribution(self, 
                                             start_date: datetime, 
                                             end_date: datetime) -> Dict[str, Any]:
        """Get content quality score distribution"""
        
        conn = self.get_connection()
        
        try:
            query = """
            WITH quality_buckets AS (
                SELECT 
                    CASE 
                        WHEN content_quality_score >= 0.9 THEN 'Excellent (0.9-1.0)'
                        WHEN content_quality_score >= 0.7 THEN 'Good (0.7-0.9)'
                        WHEN content_quality_score >= 0.5 THEN 'Average (0.5-0.7)'
                        WHEN content_quality_score >= 0.3 THEN 'Poor (0.3-0.5)'
                        ELSE 'Very Poor (0.0-0.3)'
                    END as quality_bucket,
                    COUNT(*) as count,
                    AVG(word_count) as avg_words
                FROM content_analytics
                WHERE processing_date BETWEEN ? AND ?
                  AND content_quality_score IS NOT NULL
                GROUP BY 
                    CASE 
                        WHEN content_quality_score >= 0.9 THEN 'Excellent (0.9-1.0)'
                        WHEN content_quality_score >= 0.7 THEN 'Good (0.7-0.9)'
                        WHEN content_quality_score >= 0.5 THEN 'Average (0.5-0.7)'
                        WHEN content_quality_score >= 0.3 THEN 'Poor (0.3-0.5)'
                        ELSE 'Very Poor (0.0-0.3)'
                    END
            )
            SELECT 
                quality_bucket,
                count,
                ROUND(count * 100.0 / SUM(count) OVER (), 2) as percentage,
                ROUND(avg_words, 0) as avg_words
            FROM quality_buckets
            ORDER BY 
                CASE quality_bucket
                    WHEN 'Excellent (0.9-1.0)' THEN 1
                    WHEN 'Good (0.7-0.9)' THEN 2  
                    WHEN 'Average (0.5-0.7)' THEN 3
                    WHEN 'Poor (0.3-0.5)' THEN 4
                    ELSE 5
                END
            """
            
            result = conn.execute(query, [start_date.date(), end_date.date()]).fetchdf()
            
            return {
                'distribution': result.to_dict('records'),
                'total_analyzed': result['count'].sum()
            }
            
        finally:
            conn.close()
```

#### 3.2 Analytics REST API
```python
# analytics/api/analytics_endpoints.py
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from .analytics_service import AnalyticsService

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])

def get_analytics_service() -> AnalyticsService:
    return AnalyticsService("/analytics/chrono_analytics.db")

@router.get("/performance/summary")
async def get_performance_summary(
    start_date: datetime = Query(..., description="Start date for analysis"),
    end_date: datetime = Query(..., description="End date for analysis"), 
    project_id: Optional[int] = Query(None, description="Filter by project ID"),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """Get scraping performance summary with trends"""
    
    return await analytics_service.get_scraping_performance_metrics(
        start_date, end_date, project_id
    )

@router.get("/domains/analysis")
async def get_domain_analysis(
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    limit: int = Query(50, ge=1, le=200),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
) -> List[Dict[str, Any]]:
    """Get domain performance analysis"""
    
    return await analytics_service.get_domain_analysis(start_date, end_date, limit)

@router.get("/content/quality-distribution")
async def get_content_quality_distribution(
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """Get content quality score distribution"""
    
    return await analytics_service.get_content_quality_distribution(start_date, end_date)

@router.get("/system/performance")
async def get_system_performance(
    hours_back: int = Query(24, ge=1, le=168),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """Get system performance metrics"""
    
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours_back)
    
    # Implementation would query events table for system metrics
    conn = analytics_service.get_connection()
    
    try:
        query = """
        SELECT 
            DATE_TRUNC('hour', event_timestamp) as hour,
            source_component,
            COUNT(CASE WHEN event_severity = 'error' THEN 1 END) as error_count,
            AVG(duration_ms) as avg_response_time,
            AVG(memory_usage_mb) as avg_memory,
            AVG(cpu_usage_percent) as avg_cpu
        FROM events
        WHERE event_timestamp BETWEEN ? AND ?
          AND event_type IN ('system_metric', 'performance')
        GROUP BY DATE_TRUNC('hour', event_timestamp), source_component
        ORDER BY hour DESC
        """
        
        result = conn.execute(query, [start_time, end_time]).fetchdf()
        
        return {
            'performance_metrics': result.to_dict('records'),
            'time_range': {
                'start': start_time.isoformat(),
                'end': end_time.isoformat()
            }
        }
        
    finally:
        conn.close()
```

## Migration Timeline and Milestones

### Week 1-3: Phase 1 - Historical Data Migration
- **Day 1-2:** Environment setup and schema creation
- **Day 3-7:** Historical data migration (12+ months)
- **Day 8-14:** Data validation and quality checks
- **Day 15-21:** Performance optimization and indexing

### Week 4-5: Phase 2 - Real-time Pipeline
- **Day 1-3:** Streaming ETL development
- **Day 4-7:** Event capture pipeline
- **Day 8-10:** Integration with existing services
- **Day 11-14:** Testing and validation

### Week 6-8: Phase 3 - Analytics Platform
- **Day 1-7:** Analytics service development
- **Day 8-14:** REST API development
- **Day 15-21:** Dashboard development and testing

## Performance Validation

### Expected Performance Improvements
1. **Query Response Times:**
   - Time-range queries: 10-50x faster
   - Aggregation queries: 5-20x faster
   - Complex analytics: 5-15x faster

2. **Storage Efficiency:**
   - 70-90% reduction in storage size
   - 80-95% reduction in I/O operations

3. **Operational Benefits:**
   - 3-5x more concurrent analytical queries
   - 10x faster backup/restore operations
   - 50-80% reduction in resource usage

### Success Criteria
- All historical data migrated successfully (100% data integrity)
- Real-time sync latency < 5 minutes
- Analytical query response times < 10 seconds (95th percentile)
- Storage cost reduction > 60%
- Zero data loss during migration

## Rollback Strategy

### Rollback Triggers
- Data integrity issues
- Performance degradation
- System stability problems

### Rollback Process
1. **Immediate:** Switch read traffic back to PostgreSQL
2. **Data sync:** Ensure PostgreSQL has latest data
3. **Service restart:** Restart services with PostgreSQL configuration
4. **Investigation:** Analyze issues and plan remediation

This comprehensive migration strategy ensures a smooth transition to DuckDB while maintaining data integrity and achieving the target performance improvements.