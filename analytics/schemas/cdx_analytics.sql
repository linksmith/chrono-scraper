-- CDX Analytics Parquet Schema for DuckDB
-- Optimized for time-series analysis, domain analytics, and content patterns
-- Partitioned by date for optimal performance

CREATE TABLE cdx_records (
    -- Primary identifiers (optimized for dictionary compression)
    record_id VARCHAR PRIMARY KEY,              -- Unique identifier for CDX record
    original_url VARCHAR NOT NULL,              -- Original website URL (dictionary compressed)
    domain VARCHAR NOT NULL,                    -- Extracted domain for analytics
    subdomain VARCHAR,                          -- Subdomain for pattern analysis
    url_path VARCHAR,                           -- URL path for content analysis
    url_params VARCHAR,                         -- Query parameters
    
    -- Time-series fields (optimized for date partitioning)
    archive_date DATE NOT NULL,                 -- Derived date from timestamp (partition key)
    archive_timestamp BIGINT NOT NULL,          -- Unix timestamp for precise queries
    archive_year SMALLINT NOT NULL,             -- Year for yearly aggregations
    archive_month TINYINT NOT NULL,             -- Month (1-12) for monthly patterns
    archive_day TINYINT NOT NULL,               -- Day of month
    archive_hour TINYINT NOT NULL,              -- Hour (0-23) for daily patterns
    archive_weekday TINYINT NOT NULL,           -- Day of week (0-6) for weekly patterns
    
    -- Archive source information
    source VARCHAR NOT NULL,                    -- 'WAYBACK_MACHINE' or 'COMMON_CRAWL'
    warc_filename VARCHAR,                      -- Common Crawl WARC file
    warc_offset BIGINT,                         -- WARC record offset
    warc_length INTEGER,                        -- WARC record length
    
    -- Content characteristics (optimized for analytics)
    mime_type VARCHAR,                          -- Content MIME type
    content_category VARCHAR,                   -- Derived category (html, pdf, image, etc.)
    status_code SMALLINT,                       -- HTTP status code
    content_length BIGINT,                      -- Content size in bytes
    content_size_category VARCHAR,              -- Size category (tiny, small, medium, large, huge)
    digest_hash VARCHAR,                        -- Content digest for deduplication
    
    -- URL pattern analysis fields
    url_depth TINYINT,                          -- Number of path segments
    has_query_params BOOLEAN,                   -- Whether URL has parameters
    file_extension VARCHAR,                     -- File extension if present
    is_root_page BOOLEAN,                       -- Whether URL is domain root
    is_list_page_pattern BOOLEAN,               -- Matches list page patterns
    url_language VARCHAR,                       -- Detected language from URL
    
    -- Domain analytics fields
    domain_tld VARCHAR,                         -- Top-level domain (.com, .gov, .org)
    domain_category VARCHAR,                    -- Government, educational, commercial, etc.
    domain_trust_score FLOAT,                  -- Domain authority/trust score
    is_government_domain BOOLEAN,               -- .gov or similar
    is_educational_domain BOOLEAN,              -- .edu or similar
    is_nonprofit_domain BOOLEAN,                -- .org or similar
    
    -- Processing metadata
    processing_date DATE NOT NULL,              -- When record was processed
    processing_batch_id VARCHAR,                -- Batch processing identifier
    quality_score FLOAT,                        -- Content quality score (0-1)
    priority_score INTEGER,                     -- Content priority score
    
    -- Filtering and classification
    filter_reason VARCHAR,                      -- Why content was filtered (if applicable)
    filter_category VARCHAR,                    -- Filter category
    is_duplicate BOOLEAN DEFAULT FALSE,         -- Duplicate content flag
    is_high_value_content BOOLEAN DEFAULT FALSE, -- High-value content flag
    extraction_confidence FLOAT,               -- Confidence in content extraction
    
    -- Performance metrics
    fetch_time_ms INTEGER,                      -- Time to fetch content (milliseconds)
    extraction_time_ms INTEGER,                -- Time to extract content
    total_processing_time_ms INTEGER,           -- Total processing time
    
    -- Timestamps for analytics
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
)
PARTITION BY (archive_date);

-- Indexes for common query patterns
CREATE INDEX idx_cdx_domain_date ON cdx_records (domain, archive_date);
CREATE INDEX idx_cdx_source_date ON cdx_records (source, archive_date);
CREATE INDEX idx_cdx_content_category ON cdx_records (content_category, archive_date);
CREATE INDEX idx_cdx_domain_category ON cdx_records (domain_category, archive_date);
CREATE INDEX idx_cdx_quality_score ON cdx_records (quality_score, archive_date);

-- Statistics views for common analytics
CREATE VIEW cdx_daily_stats AS
SELECT 
    archive_date,
    source,
    COUNT(*) as total_records,
    COUNT(DISTINCT domain) as unique_domains,
    AVG(content_length) as avg_content_size,
    AVG(quality_score) as avg_quality_score,
    SUM(CASE WHEN is_high_value_content THEN 1 ELSE 0 END) as high_value_pages,
    AVG(total_processing_time_ms) as avg_processing_time
FROM cdx_records 
GROUP BY archive_date, source;