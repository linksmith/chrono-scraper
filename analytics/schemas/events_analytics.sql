-- Time-Series Events Parquet Schema for DuckDB
-- Optimized for event-driven analytics, system monitoring, and behavioral analysis
-- High-frequency event storage with efficient compression

CREATE TABLE events (
    -- Primary identifiers
    event_id VARCHAR PRIMARY KEY,              -- Unique event identifier
    event_type VARCHAR NOT NULL,               -- Event category
    event_subtype VARCHAR,                     -- Event subcategory
    
    -- Time-series fields (partition key - hourly partitions for high volume)
    event_date DATE NOT NULL,                  -- Event date (partition key)
    event_hour TINYINT NOT NULL,               -- Hour (0-23) for sub-partitioning
    event_timestamp TIMESTAMP NOT NULL,       -- Precise event timestamp
    event_year SMALLINT NOT NULL,
    event_month TINYINT NOT NULL,
    event_week TINYINT NOT NULL,
    event_day_of_week TINYINT NOT NULL,       -- For weekly pattern analysis
    
    -- Entity relationships
    user_id INTEGER,                           -- User associated with event
    project_id INTEGER,                        -- Project associated with event
    domain_id INTEGER,                         -- Domain associated with event
    scrape_session_id BIGINT,                  -- Scrape session associated with event
    page_id VARCHAR,                           -- PageV2 ID associated with event
    scrape_page_id BIGINT,                     -- ScrapePage ID associated with event
    
    -- Event context
    source_component VARCHAR,                  -- Component generating event
    source_module VARCHAR,                     -- Module/service name
    source_version VARCHAR,                    -- Component version
    environment VARCHAR DEFAULT 'production',  -- Environment (dev, staging, prod)
    
    -- Event data and metadata
    event_data JSON,                           -- Structured event data
    event_message VARCHAR,                     -- Human-readable message
    event_severity VARCHAR DEFAULT 'info',    -- debug, info, warning, error, critical
    event_status VARCHAR,                      -- Event outcome status
    
    -- Performance and metrics
    duration_ms INTEGER,                       -- Event duration if applicable
    memory_usage_mb FLOAT,                     -- Memory usage during event
    cpu_usage_percent FLOAT,                   -- CPU usage during event
    network_bytes_in BIGINT,                   -- Network bytes received
    network_bytes_out BIGINT,                  -- Network bytes sent
    
    -- Error tracking
    error_code VARCHAR,                        -- Error code if applicable
    error_category VARCHAR,                    -- Error classification
    error_message VARCHAR,                     -- Error description
    error_stack_trace VARCHAR,                 -- Technical error details
    is_retryable BOOLEAN,                      -- Whether error is retryable
    
    -- User behavior events
    user_action VARCHAR,                       -- User action type
    session_id VARCHAR,                        -- User session ID
    ip_address VARCHAR,                        -- Client IP (hashed for privacy)
    user_agent VARCHAR,                        -- Client user agent
    referrer_url VARCHAR,                      -- Referrer page
    
    -- System resource events
    system_metric_name VARCHAR,                -- System metric name
    metric_value DOUBLE,                       -- Numeric metric value
    metric_unit VARCHAR,                       -- Metric unit (bytes, ms, percent)
    threshold_exceeded BOOLEAN DEFAULT FALSE, -- Whether threshold was exceeded
    alert_triggered BOOLEAN DEFAULT FALSE,    -- Whether alert was triggered
    
    -- Processing pipeline events
    pipeline_stage VARCHAR,                    -- Processing stage
    pipeline_status VARCHAR,                   -- Stage status
    input_size_bytes BIGINT,                   -- Input data size
    output_size_bytes BIGINT,                  -- Output data size
    items_processed INTEGER,                   -- Number of items processed
    success_count INTEGER DEFAULT 0,          -- Successful operations
    failure_count INTEGER DEFAULT 0,          -- Failed operations
    
    -- Content and quality events
    content_type VARCHAR,                      -- Content type being processed
    quality_score FLOAT,                       -- Quality score if applicable
    confidence_score FLOAT,                    -- Confidence score if applicable
    extraction_method VARCHAR,                 -- Extraction method used
    filter_decision VARCHAR,                   -- Filtering decision
    
    -- Archive and CDX events
    archive_source VARCHAR,                    -- Archive source
    cdx_page_number INTEGER,                   -- CDX pagination
    cdx_results_count INTEGER,                 -- Results in CDX page
    wayback_response_time_ms INTEGER,          -- Wayback API response time
    common_crawl_response_time_ms INTEGER,     -- Common Crawl response time
    
    -- Business intelligence events
    feature_used VARCHAR,                      -- Feature/functionality used
    feature_context JSON,                      -- Feature usage context
    conversion_funnel_stage VARCHAR,           -- User journey stage
    ab_test_variant VARCHAR,                   -- A/B test variant
    experiment_id VARCHAR,                     -- Experiment identifier
    
    -- Compliance and audit events
    data_classification VARCHAR,               -- Data sensitivity level
    retention_policy VARCHAR,                  -- Data retention policy
    privacy_flag BOOLEAN DEFAULT FALSE,       -- Contains personal data
    compliance_checked BOOLEAN DEFAULT FALSE, -- Compliance verification done
    audit_trail JSON,                          -- Audit trail data
    
    -- Geolocation (for user events)
    country_code VARCHAR,                      -- ISO country code
    region_code VARCHAR,                       -- Region/state code
    city_name VARCHAR,                         -- City name
    timezone VARCHAR,                          -- User timezone
    
    -- Custom dimensions (extensible)
    dimension_1 VARCHAR,                       -- Custom dimension 1
    dimension_2 VARCHAR,                       -- Custom dimension 2
    dimension_3 VARCHAR,                       -- Custom dimension 3
    tag_1 VARCHAR,                             -- Custom tag 1
    tag_2 VARCHAR,                             -- Custom tag 2
    tag_3 VARCHAR,                             -- Custom tag 3
    
    -- Event correlation
    correlation_id VARCHAR,                    -- For correlating related events
    parent_event_id VARCHAR,                   -- Parent event if applicable
    trace_id VARCHAR,                          -- Distributed tracing ID
    span_id VARCHAR,                           -- Span ID for distributed tracing
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
)
PARTITION BY (event_date, event_hour);

-- Indexes for high-performance queries
CREATE INDEX idx_events_type_timestamp ON events (event_type, event_timestamp);
CREATE INDEX idx_events_user_timestamp ON events (user_id, event_timestamp) WHERE user_id IS NOT NULL;
CREATE INDEX idx_events_project_timestamp ON events (project_id, event_timestamp) WHERE project_id IS NOT NULL;
CREATE INDEX idx_events_severity_timestamp ON events (event_severity, event_timestamp);
CREATE INDEX idx_events_correlation ON events (correlation_id, event_timestamp) WHERE correlation_id IS NOT NULL;
CREATE INDEX idx_events_session_timestamp ON events (scrape_session_id, event_timestamp) WHERE scrape_session_id IS NOT NULL;

-- System performance events view
CREATE VIEW system_performance_events AS
SELECT 
    event_date,
    event_hour,
    source_component,
    COUNT(*) as event_count,
    AVG(duration_ms) as avg_duration_ms,
    AVG(memory_usage_mb) as avg_memory_usage,
    AVG(cpu_usage_percent) as avg_cpu_usage,
    COUNT(CASE WHEN event_severity = 'error' THEN 1 END) as error_count,
    COUNT(CASE WHEN alert_triggered THEN 1 END) as alerts_triggered
FROM events 
WHERE event_type IN ('system_metric', 'performance', 'resource_usage')
GROUP BY event_date, event_hour, source_component;

-- User activity events view
CREATE VIEW user_activity_events AS
SELECT 
    event_date,
    user_id,
    COUNT(*) as total_events,
    COUNT(DISTINCT session_id) as unique_sessions,
    COUNT(DISTINCT user_action) as unique_actions,
    MIN(event_timestamp) as first_activity,
    MAX(event_timestamp) as last_activity,
    COUNT(CASE WHEN event_type = 'search' THEN 1 END) as search_events,
    COUNT(CASE WHEN event_type = 'page_view' THEN 1 END) as page_views,
    COUNT(CASE WHEN event_type = 'user_interaction' THEN 1 END) as interactions
FROM events 
WHERE event_type IN ('user_interaction', 'page_view', 'search', 'feature_usage')
  AND user_id IS NOT NULL
GROUP BY event_date, user_id;

-- Scraping pipeline events view
CREATE VIEW scraping_pipeline_events AS
SELECT 
    event_date,
    event_hour,
    pipeline_stage,
    pipeline_status,
    COUNT(*) as event_count,
    SUM(items_processed) as total_items_processed,
    SUM(success_count) as total_successes,
    SUM(failure_count) as total_failures,
    AVG(duration_ms) as avg_stage_duration,
    SUM(input_size_bytes) as total_input_bytes,
    SUM(output_size_bytes) as total_output_bytes
FROM events 
WHERE event_type = 'pipeline_stage'
  AND pipeline_stage IS NOT NULL
GROUP BY event_date, event_hour, pipeline_stage, pipeline_status;

-- Error analysis events view
CREATE VIEW error_analysis_events AS
SELECT 
    event_date,
    error_category,
    error_code,
    source_component,
    COUNT(*) as error_count,
    COUNT(CASE WHEN is_retryable THEN 1 END) as retryable_errors,
    COUNT(DISTINCT user_id) as affected_users,
    COUNT(DISTINCT project_id) as affected_projects,
    MIN(event_timestamp) as first_occurrence,
    MAX(event_timestamp) as last_occurrence
FROM events 
WHERE event_severity IN ('error', 'critical')
  AND error_category IS NOT NULL
GROUP BY event_date, error_category, error_code, source_component;