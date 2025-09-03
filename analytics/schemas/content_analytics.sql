-- Content Analytics Parquet Schema for DuckDB
-- Optimized for content extraction metrics, quality analysis, and processing performance
-- Partitioned by processing date for optimal query performance

CREATE TABLE content_analytics (
    -- Primary identifiers
    content_id VARCHAR PRIMARY KEY,             -- Unique identifier for content record
    page_id VARCHAR,                            -- Reference to PageV2.id (UUID)
    scrape_page_id BIGINT,                      -- Reference to ScrapePage.id
    cdx_record_id VARCHAR,                      -- Reference to CDX record
    
    -- Source information
    original_url VARCHAR NOT NULL,              -- Original URL
    content_url VARCHAR,                        -- Archive/content URL
    domain VARCHAR NOT NULL,                    -- Domain for grouping
    
    -- Time-series fields (partition key)
    processing_date DATE NOT NULL,              -- Date when content was processed
    processing_timestamp TIMESTAMP NOT NULL,   -- Precise processing time
    processing_year SMALLINT NOT NULL,
    processing_month TINYINT NOT NULL,
    processing_week TINYINT NOT NULL,           -- Week of year for weekly aggregations
    
    -- Content characteristics
    mime_type VARCHAR,                          -- Original MIME type
    content_type VARCHAR,                       -- Processed content type
    content_category VARCHAR,                   -- html, pdf, image, document, etc.
    original_size_bytes BIGINT,                 -- Original content size
    compressed_size_bytes BIGINT,              -- Compressed size if applicable
    
    -- Content extraction metrics
    extraction_method VARCHAR NOT NULL,        -- 'firecrawl', 'intelligent', 'fallback'
    extraction_status VARCHAR NOT NULL,        -- 'success', 'failed', 'partial'
    extraction_confidence FLOAT,               -- Confidence score (0-1)
    extraction_time_ms INTEGER,                -- Time to extract content
    extraction_error_type VARCHAR,             -- Error category if failed
    extraction_retry_count TINYINT DEFAULT 0,  -- Number of retries
    
    -- Content quality metrics
    title_extracted BOOLEAN DEFAULT FALSE,     -- Whether title was extracted
    text_content_length INTEGER,               -- Length of extracted text
    markdown_content_length INTEGER,           -- Length of markdown content
    word_count INTEGER,                        -- Word count
    paragraph_count INTEGER,                   -- Number of paragraphs
    language VARCHAR,                          -- Detected language
    language_confidence FLOAT,                 -- Language detection confidence
    
    -- Quality scoring
    content_quality_score FLOAT,               -- Overall quality score (0-1)
    readability_score FLOAT,                   -- Text readability score
    information_density FLOAT,                 -- Information per word ratio
    structural_completeness FLOAT,             -- HTML structure completeness
    
    -- Entity extraction metrics
    entities_extracted INTEGER DEFAULT 0,      -- Number of entities found
    person_entities INTEGER DEFAULT 0,         -- Number of person entities
    organization_entities INTEGER DEFAULT 0,   -- Number of organization entities
    location_entities INTEGER DEFAULT 0,       -- Number of location entities
    date_entities INTEGER DEFAULT 0,           -- Number of date entities
    avg_entity_confidence FLOAT,               -- Average entity confidence
    
    -- Content analysis flags
    is_list_page BOOLEAN DEFAULT FALSE,        -- Detected as list/index page
    is_duplicate_content BOOLEAN DEFAULT FALSE, -- Duplicate content detected
    has_meaningful_content BOOLEAN DEFAULT TRUE, -- Contains meaningful content
    is_machine_generated BOOLEAN DEFAULT FALSE, -- Machine-generated content
    contains_personal_info BOOLEAN DEFAULT FALSE, -- Contains PII
    
    -- Processing performance metrics
    fetch_time_ms INTEGER,                     -- Time to fetch content
    parse_time_ms INTEGER,                     -- Time to parse HTML/content
    nlp_processing_time_ms INTEGER,            -- Time for NLP processing
    indexing_time_ms INTEGER,                  -- Time to index content
    total_processing_time_ms INTEGER,          -- Total end-to-end time
    
    -- Resource usage metrics
    memory_usage_mb FLOAT,                     -- Peak memory usage
    cpu_time_ms INTEGER,                       -- CPU time consumed
    network_bytes_transferred BIGINT,          -- Network data transfer
    
    -- Content classification
    content_topics VARCHAR[],                  -- Detected topics (array)
    content_sentiment FLOAT,                   -- Sentiment score (-1 to 1)
    content_formality FLOAT,                   -- Formality score (0-1)
    technical_complexity FLOAT,                -- Technical complexity score
    
    -- Filtering and decision tracking
    intelligent_filter_applied BOOLEAN DEFAULT FALSE,
    filter_decision VARCHAR,                   -- 'include', 'exclude', 'manual_review'
    filter_reason VARCHAR,                     -- Specific filter reason
    filter_confidence FLOAT,                   -- Filter decision confidence
    manual_override BOOLEAN DEFAULT FALSE,     -- Manual override applied
    
    -- Error tracking
    error_message VARCHAR,                     -- Error message if processing failed
    error_category VARCHAR,                    -- Error classification
    error_stack_trace VARCHAR,                 -- Technical error details
    is_recoverable_error BOOLEAN,              -- Whether error is recoverable
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
)
PARTITION BY (processing_date);

-- Indexes for analytical queries
CREATE INDEX idx_content_domain_date ON content_analytics (domain, processing_date);
CREATE INDEX idx_content_method_status ON content_analytics (extraction_method, extraction_status);
CREATE INDEX idx_content_quality_score ON content_analytics (content_quality_score, processing_date);
CREATE INDEX idx_content_category_date ON content_analytics (content_category, processing_date);
CREATE INDEX idx_content_language ON content_analytics (language, processing_date);

-- Performance analytics view
CREATE VIEW content_performance_stats AS
SELECT 
    processing_date,
    extraction_method,
    extraction_status,
    COUNT(*) as total_processed,
    AVG(extraction_time_ms) as avg_extraction_time,
    AVG(content_quality_score) as avg_quality_score,
    AVG(total_processing_time_ms) as avg_total_time,
    SUM(CASE WHEN extraction_status = 'success' THEN 1 ELSE 0 END) / COUNT(*) as success_rate,
    AVG(word_count) as avg_word_count,
    AVG(entities_extracted) as avg_entities_extracted
FROM content_analytics 
GROUP BY processing_date, extraction_method, extraction_status;

-- Quality metrics view
CREATE VIEW content_quality_trends AS
SELECT 
    processing_date,
    content_category,
    AVG(content_quality_score) as avg_quality,
    AVG(readability_score) as avg_readability,
    AVG(information_density) as avg_info_density,
    COUNT(CASE WHEN has_meaningful_content THEN 1 END) as meaningful_content_count,
    COUNT(CASE WHEN is_duplicate_content THEN 1 END) as duplicate_content_count
FROM content_analytics 
GROUP BY processing_date, content_category;