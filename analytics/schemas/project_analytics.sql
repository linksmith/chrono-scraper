-- Project Analytics Parquet Schema for DuckDB
-- Optimized for project-level aggregated metrics and performance tracking
-- Partitioned by date for time-series analysis

CREATE TABLE project_analytics (
    -- Primary identifiers
    analytics_id VARCHAR PRIMARY KEY,          -- Unique analytics record ID
    project_id INTEGER NOT NULL,               -- Reference to projects.id
    domain_id INTEGER,                         -- Reference to domains.id (nullable for project-level)
    scrape_session_id BIGINT,                  -- Reference to scrape session
    user_id INTEGER NOT NULL,                  -- Reference to users.id
    
    -- Time-series fields (partition key)
    analytics_date DATE NOT NULL,              -- Date of analytics snapshot
    analytics_timestamp TIMESTAMP NOT NULL,   -- Precise timestamp
    analytics_year SMALLINT NOT NULL,
    analytics_month TINYINT NOT NULL,
    analytics_week TINYINT NOT NULL,
    
    -- Project metadata
    project_name VARCHAR NOT NULL,             -- Project name for grouping
    project_status VARCHAR,                    -- Project status
    user_email VARCHAR,                        -- User email for user analytics
    user_organization VARCHAR,                 -- User organization
    
    -- Domain-specific metrics (nullable for project-level aggregates)
    domain_name VARCHAR,                       -- Domain being analyzed
    domain_status VARCHAR,                     -- Domain status
    domain_match_type VARCHAR,                 -- exact, prefix, domain, regex
    
    -- Scraping performance metrics
    total_pages_discovered INTEGER DEFAULT 0,  -- Total pages found in CDX
    total_pages_processed INTEGER DEFAULT 0,   -- Total pages processed
    total_pages_successful INTEGER DEFAULT 0,  -- Successfully processed pages
    total_pages_failed INTEGER DEFAULT 0,      -- Failed processing pages
    total_pages_skipped INTEGER DEFAULT 0,     -- Skipped/filtered pages
    total_pages_duplicates INTEGER DEFAULT 0,  -- Duplicate pages found
    
    -- Content statistics
    total_content_size_bytes BIGINT DEFAULT 0, -- Total content size
    avg_content_size_bytes INTEGER DEFAULT 0,  -- Average content size
    total_word_count BIGINT DEFAULT 0,         -- Total words extracted
    avg_word_count INTEGER DEFAULT 0,          -- Average words per page
    unique_domains_scraped INTEGER DEFAULT 0,  -- Number of unique domains
    
    -- Quality metrics
    avg_content_quality_score FLOAT,          -- Average quality score
    avg_extraction_confidence FLOAT,          -- Average extraction confidence
    high_quality_pages_count INTEGER DEFAULT 0, -- Pages with quality > 0.8
    low_quality_pages_count INTEGER DEFAULT 0,  -- Pages with quality < 0.3
    
    -- Processing performance
    total_processing_time_ms BIGINT DEFAULT 0, -- Total processing time
    avg_processing_time_ms INTEGER DEFAULT 0,  -- Average processing time per page
    avg_fetch_time_ms INTEGER DEFAULT 0,       -- Average fetch time
    avg_extraction_time_ms INTEGER DEFAULT 0,  -- Average extraction time
    pages_per_minute FLOAT DEFAULT 0,          -- Processing rate
    
    -- Resource utilization
    avg_memory_usage_mb FLOAT DEFAULT 0,       -- Average memory usage
    peak_memory_usage_mb FLOAT DEFAULT 0,      -- Peak memory usage
    total_cpu_time_ms BIGINT DEFAULT 0,        -- Total CPU time consumed
    total_network_bytes BIGINT DEFAULT 0,      -- Total network transfer
    
    -- Error and retry analysis
    error_rate FLOAT DEFAULT 0,                -- Percentage of failed pages
    avg_retry_count FLOAT DEFAULT 0,           -- Average retries per page
    most_common_error_type VARCHAR,            -- Most frequent error
    recoverable_errors INTEGER DEFAULT 0,      -- Count of recoverable errors
    unrecoverable_errors INTEGER DEFAULT 0,    -- Count of fatal errors
    
    -- Content analysis metrics
    total_entities_extracted INTEGER DEFAULT 0, -- Total entities found
    avg_entities_per_page FLOAT DEFAULT 0,     -- Average entities per page
    person_entities INTEGER DEFAULT 0,         -- Person entities
    organization_entities INTEGER DEFAULT 0,   -- Organization entities
    location_entities INTEGER DEFAULT 0,       -- Location entities
    unique_languages INTEGER DEFAULT 0,        -- Number of unique languages
    primary_language VARCHAR,                  -- Most common language
    
    -- Filtering effectiveness
    intelligent_filter_applied INTEGER DEFAULT 0, -- Pages where filter applied
    filter_accuracy FLOAT DEFAULT 0,           -- Filter accuracy rate
    manual_overrides INTEGER DEFAULT 0,        -- Manual override count
    list_pages_filtered INTEGER DEFAULT 0,     -- List pages filtered out
    duplicate_pages_filtered INTEGER DEFAULT 0, -- Duplicates filtered
    
    -- Archive source performance
    wayback_pages INTEGER DEFAULT 0,           -- Pages from Wayback Machine
    common_crawl_pages INTEGER DEFAULT 0,      -- Pages from Common Crawl
    wayback_success_rate FLOAT DEFAULT 0,      -- Wayback success rate
    common_crawl_success_rate FLOAT DEFAULT 0, -- Common Crawl success rate
    
    -- User activity metrics
    user_interactions INTEGER DEFAULT 0,       -- User interactions count
    manual_reviews INTEGER DEFAULT 0,          -- Manual reviews performed
    starred_pages INTEGER DEFAULT 0,           -- Pages starred by user
    shared_pages INTEGER DEFAULT 0,            -- Pages shared
    search_queries INTEGER DEFAULT 0,          -- Search queries performed
    
    -- Project configuration impact
    attachment_download_enabled BOOLEAN,       -- Whether attachments enabled
    langextract_enabled BOOLEAN,               -- Whether LangExtract enabled
    langextract_provider VARCHAR,              -- LLM provider used
    archive_source VARCHAR,                    -- Primary archive source
    incremental_scraping_enabled BOOLEAN,      -- Incremental mode enabled
    
    -- Cost estimation and usage
    estimated_processing_cost_usd DECIMAL(10,4), -- Estimated processing cost
    langextract_cost_usd DECIMAL(10,4),        -- LangExtract costs
    storage_cost_usd DECIMAL(10,4),            -- Storage costs
    api_calls_made INTEGER DEFAULT 0,          -- Total API calls
    
    -- Time-based analysis
    scraping_session_duration_minutes INTEGER, -- Session duration
    time_to_first_result_minutes INTEGER,      -- Time to first successful page
    peak_processing_hour TINYINT,              -- Hour of peak processing
    processing_day_of_week TINYINT,            -- Day when processing occurred
    
    -- Aggregation metadata
    aggregation_level VARCHAR NOT NULL,        -- 'project', 'domain', 'session'
    data_freshness_hours INTEGER DEFAULT 0,    -- Hours since data was last updated
    is_complete_snapshot BOOLEAN DEFAULT TRUE, -- Whether data is complete
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
)
PARTITION BY (analytics_date);

-- Indexes for analytical queries
CREATE INDEX idx_project_analytics_project_date ON project_analytics (project_id, analytics_date);
CREATE INDEX idx_project_analytics_user_date ON project_analytics (user_id, analytics_date);
CREATE INDEX idx_project_analytics_domain_date ON project_analytics (domain_id, analytics_date) WHERE domain_id IS NOT NULL;
CREATE INDEX idx_project_analytics_aggregation_level ON project_analytics (aggregation_level, analytics_date);
CREATE INDEX idx_project_analytics_project_status ON project_analytics (project_status, analytics_date);

-- Project performance summary view
CREATE VIEW project_performance_summary AS
SELECT 
    analytics_date,
    project_id,
    project_name,
    SUM(total_pages_processed) as total_pages,
    AVG(pages_per_minute) as avg_processing_rate,
    AVG(avg_content_quality_score) as avg_quality,
    SUM(total_processing_time_ms) / 1000 / 60 as total_processing_minutes,
    AVG(error_rate) as avg_error_rate,
    SUM(estimated_processing_cost_usd) as total_cost,
    COUNT(DISTINCT domain_id) as active_domains
FROM project_analytics 
WHERE aggregation_level = 'project'
GROUP BY analytics_date, project_id, project_name;

-- User productivity metrics view
CREATE VIEW user_productivity_metrics AS
SELECT 
    analytics_date,
    user_id,
    user_email,
    COUNT(DISTINCT project_id) as active_projects,
    SUM(total_pages_processed) as total_pages_processed,
    SUM(manual_reviews) as total_manual_reviews,
    SUM(starred_pages) as total_starred_pages,
    AVG(avg_content_quality_score) as avg_content_quality,
    SUM(estimated_processing_cost_usd) as total_usage_cost
FROM project_analytics 
GROUP BY analytics_date, user_id, user_email;

-- Domain performance comparison view
CREATE VIEW domain_performance_comparison AS
SELECT 
    analytics_date,
    domain_name,
    AVG(pages_per_minute) as avg_processing_rate,
    AVG(error_rate) as avg_error_rate,
    AVG(avg_content_quality_score) as avg_quality_score,
    AVG(wayback_success_rate) as wayback_success_rate,
    AVG(common_crawl_success_rate) as cc_success_rate,
    COUNT(DISTINCT project_id) as projects_using_domain
FROM project_analytics 
WHERE aggregation_level = 'domain' AND domain_name IS NOT NULL
GROUP BY analytics_date, domain_name;