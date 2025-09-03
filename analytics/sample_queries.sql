-- Sample Analytical Queries for Chrono Scraper DuckDB Analytics System
-- Demonstrates optimal query patterns and expected performance improvements

-- =============================================================================
-- 1. TIME-SERIES ANALYSIS QUERIES
-- =============================================================================

-- Daily scraping volume trends with source comparison
SELECT 
    archive_date,
    source,
    COUNT(*) as total_records,
    COUNT(DISTINCT domain) as unique_domains,
    SUM(content_length) / 1024 / 1024 as total_content_mb,
    AVG(quality_score) as avg_quality_score,
    COUNT(CASE WHEN is_high_value_content THEN 1 END) as high_value_count
FROM cdx_records
WHERE archive_date >= '2024-01-01' 
  AND archive_date <= '2024-01-31'
GROUP BY archive_date, source
ORDER BY archive_date, source;

-- Expected performance: 50x faster than PostgreSQL due to:
-- - Partition pruning (January 2024 only)
-- - Columnar aggregations
-- - Dictionary compression on source/domain fields

-- Hourly processing performance with pipeline stage analysis
SELECT 
    DATE_TRUNC('hour', event_timestamp) as processing_hour,
    pipeline_stage,
    COUNT(*) as events_count,
    AVG(duration_ms) as avg_duration_ms,
    SUM(items_processed) as total_items,
    SUM(success_count) / NULLIF(SUM(success_count + failure_count), 0) as success_rate
FROM events
WHERE event_date >= CURRENT_DATE - 7
  AND event_type = 'pipeline_stage'
GROUP BY DATE_TRUNC('hour', event_timestamp), pipeline_stage
ORDER BY processing_hour DESC, pipeline_stage;

-- Expected performance: 20x faster due to hourly partitioning and event type filtering

-- =============================================================================
-- 2. DOMAIN ANALYTICS QUERIES  
-- =============================================================================

-- Top performing domains by content quality and volume
WITH domain_stats AS (
    SELECT 
        domain,
        domain_category,
        COUNT(*) as total_pages,
        AVG(quality_score) as avg_quality,
        AVG(content_length) as avg_size,
        COUNT(CASE WHEN is_high_value_content THEN 1 END) as high_value_pages,
        AVG(total_processing_time_ms) as avg_processing_time
    FROM cdx_records c
    INNER JOIN content_analytics ca ON c.record_id = ca.cdx_record_id
    WHERE c.archive_date >= '2024-01-01'
      AND ca.processing_date >= '2024-01-01'
    GROUP BY domain, domain_category
)
SELECT 
    domain,
    domain_category,
    total_pages,
    ROUND(avg_quality, 3) as avg_quality,
    ROUND(avg_size / 1024.0, 1) as avg_size_kb,
    high_value_pages,
    ROUND(high_value_pages * 100.0 / total_pages, 1) as high_value_percentage,
    ROUND(avg_processing_time, 1) as avg_processing_ms
FROM domain_stats
WHERE total_pages >= 100  -- Filter for meaningful sample sizes
ORDER BY avg_quality DESC, high_value_percentage DESC
LIMIT 50;

-- Expected performance: 15x faster due to optimized joins and columnar aggregations

-- Government vs commercial domain comparison
SELECT 
    CASE 
        WHEN is_government_domain THEN 'Government'
        WHEN is_educational_domain THEN 'Educational'
        WHEN is_nonprofit_domain THEN 'Non-profit'
        ELSE 'Commercial'
    END as domain_type,
    COUNT(*) as total_records,
    AVG(quality_score) as avg_quality,
    AVG(content_length) as avg_content_size,
    AVG(word_count) as avg_word_count,
    COUNT(DISTINCT domain) as unique_domains
FROM cdx_records c
INNER JOIN content_analytics ca ON c.record_id = ca.cdx_record_id
WHERE c.archive_date >= '2024-01-01'
  AND ca.extraction_status = 'success'
GROUP BY 
    CASE 
        WHEN is_government_domain THEN 'Government'
        WHEN is_educational_domain THEN 'Educational'
        WHEN is_nonprofit_domain THEN 'Non-profit'
        ELSE 'Commercial'
    END
ORDER BY avg_quality DESC;

-- =============================================================================
-- 3. CONTENT QUALITY AND EXTRACTION ANALYTICS
-- =============================================================================

-- Extraction method effectiveness comparison
SELECT 
    extraction_method,
    extraction_status,
    COUNT(*) as total_attempts,
    ROUND(AVG(extraction_confidence), 3) as avg_confidence,
    ROUND(AVG(content_quality_score), 3) as avg_quality,
    ROUND(AVG(extraction_time_ms), 1) as avg_extraction_time,
    ROUND(AVG(word_count), 1) as avg_word_count,
    COUNT(CASE WHEN has_meaningful_content THEN 1 END) as meaningful_content_count
FROM content_analytics
WHERE processing_date >= '2024-01-01'
GROUP BY extraction_method, extraction_status
ORDER BY extraction_method, extraction_status;

-- Content quality distribution analysis
WITH quality_buckets AS (
    SELECT 
        CASE 
            WHEN content_quality_score >= 0.9 THEN 'Excellent (0.9-1.0)'
            WHEN content_quality_score >= 0.7 THEN 'Good (0.7-0.9)'
            WHEN content_quality_score >= 0.5 THEN 'Average (0.5-0.7)'
            WHEN content_quality_score >= 0.3 THEN 'Poor (0.3-0.5)'
            ELSE 'Very Poor (0.0-0.3)'
        END as quality_bucket,
        content_category,
        COUNT(*) as page_count,
        AVG(word_count) as avg_words,
        AVG(entities_extracted) as avg_entities
    FROM content_analytics
    WHERE processing_date >= '2024-01-01'
      AND content_quality_score IS NOT NULL
    GROUP BY 
        CASE 
            WHEN content_quality_score >= 0.9 THEN 'Excellent (0.9-1.0)'
            WHEN content_quality_score >= 0.7 THEN 'Good (0.7-0.9)'
            WHEN content_quality_score >= 0.5 THEN 'Average (0.5-0.7)'
            WHEN content_quality_score >= 0.3 THEN 'Poor (0.3-0.5)'
            ELSE 'Very Poor (0.0-0.3)'
        END,
        content_category
)
SELECT 
    quality_bucket,
    content_category,
    page_count,
    ROUND(page_count * 100.0 / SUM(page_count) OVER (PARTITION BY content_category), 2) as percentage_of_category,
    ROUND(avg_words, 0) as avg_words,
    ROUND(avg_entities, 1) as avg_entities
FROM quality_buckets
ORDER BY content_category, quality_bucket;

-- =============================================================================
-- 4. PROJECT PERFORMANCE ANALYTICS
-- =============================================================================

-- Project ROI and cost analysis
SELECT 
    p.project_name,
    pa.user_email,
    SUM(pa.total_pages_processed) as total_pages,
    ROUND(AVG(pa.avg_content_quality_score), 3) as avg_quality,
    ROUND(SUM(pa.estimated_processing_cost_usd), 2) as total_cost_usd,
    ROUND(SUM(pa.total_pages_processed) / NULLIF(SUM(pa.estimated_processing_cost_usd), 0), 0) as pages_per_dollar,
    ROUND(AVG(pa.pages_per_minute), 1) as avg_processing_rate,
    ROUND(AVG(pa.error_rate) * 100, 1) as avg_error_rate_pct
FROM project_analytics pa
WHERE pa.analytics_date >= '2024-01-01'
  AND pa.aggregation_level = 'project'
GROUP BY p.project_name, pa.user_email
HAVING SUM(pa.total_pages_processed) > 1000  -- Meaningful projects only
ORDER BY pages_per_dollar DESC, total_pages DESC
LIMIT 25;

-- User productivity and engagement metrics
WITH user_monthly_stats AS (
    SELECT 
        user_id,
        user_email,
        DATE_TRUNC('month', analytics_date) as analytics_month,
        COUNT(DISTINCT project_id) as active_projects,
        SUM(total_pages_processed) as monthly_pages,
        SUM(manual_reviews) as monthly_reviews,
        SUM(starred_pages) as monthly_starred,
        AVG(avg_content_quality_score) as avg_quality
    FROM project_analytics
    WHERE analytics_date >= '2024-01-01'
      AND aggregation_level = 'project'
    GROUP BY user_id, user_email, DATE_TRUNC('month', analytics_date)
)
SELECT 
    user_email,
    COUNT(DISTINCT analytics_month) as active_months,
    ROUND(AVG(active_projects), 1) as avg_monthly_projects,
    SUM(monthly_pages) as total_pages_processed,
    ROUND(AVG(monthly_pages), 0) as avg_monthly_pages,
    SUM(monthly_reviews) as total_manual_reviews,
    ROUND(AVG(avg_quality), 3) as user_avg_quality,
    ROUND(SUM(monthly_reviews) * 100.0 / NULLIF(SUM(monthly_pages), 0), 2) as review_rate_pct
FROM user_monthly_stats
GROUP BY user_email
ORDER BY total_pages_processed DESC
LIMIT 20;

-- =============================================================================
-- 5. SYSTEM PERFORMANCE AND RELIABILITY
-- =============================================================================

-- System performance trends and bottlenecks
SELECT 
    event_date,
    source_component,
    COUNT(CASE WHEN event_severity = 'error' THEN 1 END) as error_count,
    COUNT(CASE WHEN event_severity = 'critical' THEN 1 END) as critical_count,
    AVG(duration_ms) as avg_response_time,
    AVG(memory_usage_mb) as avg_memory_usage,
    AVG(cpu_usage_percent) as avg_cpu_usage,
    COUNT(CASE WHEN alert_triggered THEN 1 END) as alerts_triggered
FROM events
WHERE event_date >= CURRENT_DATE - 30
  AND event_type IN ('system_metric', 'performance')
GROUP BY event_date, source_component
ORDER BY event_date DESC, source_component;

-- Pipeline bottleneck analysis
WITH stage_performance AS (
    SELECT 
        pipeline_stage,
        COUNT(*) as total_executions,
        AVG(duration_ms) as avg_duration,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_duration,
        AVG(success_count / NULLIF(success_count + failure_count, 0)) as success_rate,
        SUM(items_processed) as total_items_processed
    FROM events
    WHERE event_date >= CURRENT_DATE - 7
      AND event_type = 'pipeline_stage'
      AND pipeline_stage IS NOT NULL
    GROUP BY pipeline_stage
)
SELECT 
    pipeline_stage,
    total_executions,
    ROUND(avg_duration, 1) as avg_duration_ms,
    ROUND(p95_duration, 1) as p95_duration_ms,
    ROUND(success_rate * 100, 1) as success_rate_pct,
    total_items_processed,
    ROUND(total_items_processed / NULLIF(avg_duration / 1000.0, 0), 0) as items_per_second
FROM stage_performance
ORDER BY p95_duration_ms DESC;

-- =============================================================================
-- 6. ADVANCED ANALYTICS QUERIES
-- =============================================================================

-- Content discovery patterns and seasonal trends
SELECT 
    EXTRACT(hour FROM archive_timestamp) as hour_of_day,
    EXTRACT(dow FROM archive_date) as day_of_week,  -- 0=Sunday, 6=Saturday
    COUNT(*) as content_discovered,
    AVG(quality_score) as avg_quality,
    COUNT(CASE WHEN is_high_value_content THEN 1 END) as high_value_discoveries
FROM cdx_records
WHERE archive_date >= '2024-01-01'
  AND archive_date <= '2024-12-31'
GROUP BY EXTRACT(hour FROM archive_timestamp), EXTRACT(dow FROM archive_date)
ORDER BY day_of_week, hour_of_day;

-- Cross-domain content similarity analysis
WITH domain_content_profile AS (
    SELECT 
        c.domain,
        AVG(ca.word_count) as avg_word_count,
        AVG(ca.entities_extracted) as avg_entities,
        AVG(ca.readability_score) as avg_readability,
        STRING_AGG(DISTINCT ca.language, ', ' ORDER BY ca.language) as languages_found,
        COUNT(*) as total_pages
    FROM cdx_records c
    INNER JOIN content_analytics ca ON c.record_id = ca.cdx_record_id
    WHERE c.archive_date >= '2024-01-01'
      AND ca.extraction_status = 'success'
    GROUP BY c.domain
    HAVING COUNT(*) >= 50  -- Domains with sufficient data
)
SELECT 
    d1.domain as domain_1,
    d2.domain as domain_2,
    ABS(d1.avg_word_count - d2.avg_word_count) as word_count_diff,
    ABS(d1.avg_entities - d2.avg_entities) as entity_diff,
    ABS(d1.avg_readability - d2.avg_readability) as readability_diff,
    -- Simple similarity score (lower is more similar)
    (ABS(d1.avg_word_count - d2.avg_word_count) / 1000.0 + 
     ABS(d1.avg_entities - d2.avg_entities) + 
     ABS(d1.avg_readability - d2.avg_readability)) as similarity_score
FROM domain_content_profile d1
CROSS JOIN domain_content_profile d2
WHERE d1.domain < d2.domain  -- Avoid duplicate pairs
  AND d1.total_pages >= 100 
  AND d2.total_pages >= 100
ORDER BY similarity_score ASC
LIMIT 20;

-- Intelligent filtering effectiveness analysis
SELECT 
    filter_category,
    filter_decision,
    COUNT(*) as total_decisions,
    AVG(filter_confidence) as avg_confidence,
    COUNT(CASE WHEN manual_override THEN 1 END) as manual_overrides,
    ROUND(COUNT(CASE WHEN manual_override THEN 1 END) * 100.0 / COUNT(*), 2) as override_rate_pct,
    -- Measure filter accuracy based on quality scores of overridden content
    AVG(CASE WHEN manual_override THEN content_quality_score END) as avg_overridden_quality,
    AVG(CASE WHEN NOT manual_override THEN content_quality_score END) as avg_accepted_quality
FROM content_analytics
WHERE processing_date >= '2024-01-01'
  AND intelligent_filter_applied = TRUE
  AND filter_category IS NOT NULL
GROUP BY filter_category, filter_decision
ORDER BY total_decisions DESC;

-- Expected Performance Summary:
-- - Time-range queries: 10-50x faster due to partition pruning
-- - Aggregation queries: 5-20x faster due to columnar storage  
-- - Join queries: 3-8x faster due to optimized data layout
-- - Complex analytics: 5-15x faster due to efficient compression and indexing