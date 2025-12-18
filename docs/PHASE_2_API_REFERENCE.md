# Phase 2 Analytics API Reference

## Overview

The Phase 2 Analytics API provides comprehensive access to high-performance analytics powered by the hybrid PostgreSQL + DuckDB architecture. This API delivers 5-10x performance improvements for analytical workloads while maintaining enterprise-grade reliability and security.

**Base URL:** `https://api.chrono-scraper.com/api/v1/analytics`

**Authentication:** Bearer token (JWT) required for all endpoints

**Rate Limiting:** 1000 requests per hour per user (configurable)

## API Categories

### 1. Domain Analytics
Domain-level analytics for web scraping insights across archive sources.

### 2. Project Analytics  
Project-specific performance metrics and content analysis.

### 3. Content Analytics
Content quality, extraction performance, and language analysis.

### 4. System Analytics
System-wide performance monitoring and resource utilization.

### 5. Real-time Features
WebSocket-based real-time analytics and live dashboard updates.

### 6. Export & Integration
Data export in multiple formats and third-party integrations.

---

## Domain Analytics Endpoints

### GET `/domains/{domain}/timeline`

**Description:** Get domain timeline analytics showing scraping activity over time.

**Path Parameters:**
- `domain` (string, required): Domain to analyze (e.g., "example.com")

**Query Parameters:**
- `granularity` (enum): Time granularity - `minute`, `hour`, `day`, `week`, `month`, `quarter`, `year` (default: `day`)
- `start_date` (datetime, optional): Start date for analysis (ISO 8601 format)
- `end_date` (datetime, optional): End date for analysis (ISO 8601 format)
- `include_subdomains` (boolean): Include subdomain data (default: `false`)
- `use_cache` (boolean): Use cached results when available (default: `true`)

**Example Request:**
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/analytics/domains/archive.org/timeline?granularity=day&start_date=2024-01-01T00:00:00Z&end_date=2024-01-31T23:59:59Z" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "timestamp": "2024-01-01T00:00:00Z",
      "pages_scraped": 1250,
      "pages_successful": 1180,
      "pages_failed": 70,
      "content_size_mb": 45.8,
      "unique_urls": 1200,
      "error_rate": 5.6
    }
  ],
  "summary": {
    "total_pages": 38750,
    "success_rate": 94.4,
    "avg_error_rate": 5.6,
    "total_content_mb": 1420.5,
    "time_span_days": 31
  },
  "metadata": {
    "query_time_ms": 125,
    "cache_hit": true,
    "database_used": "duckdb"
  },
  "performance": {
    "execution_time": 0.125,
    "rows_processed": 38750,
    "optimization_applied": ["predicate_pushdown", "column_pruning"]
  }
}
```

**Error Responses:**
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: Domain not found
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error

---

### GET `/domains/{domain}/statistics`

**Description:** Get comprehensive domain statistics and performance metrics.

**Path Parameters:**
- `domain` (string, required): Domain to analyze

**Query Parameters:**
- `start_date` (datetime, optional): Start date for analysis
- `end_date` (datetime, optional): End date for analysis
- `include_detailed_metrics` (boolean): Include detailed performance metrics (default: `true`)

**Example Request:**
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/analytics/domains/github.com/statistics" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "domain": "github.com",
    "total_pages": 125000,
    "successful_pages": 118750,
    "failed_pages": 6250,
    "success_rate": 95.0,
    "avg_content_size": 156.7,
    "total_content_size": 18750.8,
    "first_scraped": "2023-06-15T08:30:00Z",
    "last_scraped": "2024-01-31T16:45:00Z",
    "unique_urls": 98500,
    "avg_scrape_duration": 2.34,
    "popular_paths": [
      {"path": "/repos", "count": 45000},
      {"path": "/users", "count": 32000},
      {"path": "/issues", "count": 28000}
    ],
    "content_types": {
      "text/html": 112500,
      "application/json": 12500
    },
    "error_distribution": {
      "timeout": 3500,
      "404_not_found": 2000,
      "500_server_error": 750
    }
  },
  "metadata": {
    "query_time_ms": 89,
    "database_used": "duckdb"
  }
}
```

---

### GET `/domains/top-domains`

**Description:** Get top domains ranked by specified metrics.

**Query Parameters:**
- `metric` (enum): Ranking metric - `total_pages`, `success_rate`, `content_size` (default: `total_pages`)
- `limit` (integer): Maximum number of results (1-1000, default: 100)
- `start_date` (datetime, optional): Start date for analysis
- `end_date` (datetime, optional): End date for analysis
- `include_inactive` (boolean): Include domains with no recent activity (default: `false`)

**Example Request:**
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/analytics/domains/top-domains?metric=success_rate&limit=50" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "domain": "wikipedia.org",
      "rank": 1,
      "total_pages": 2500000,
      "success_rate": 98.5,
      "content_size_mb": 125000.0,
      "last_activity": "2024-01-31T23:59:59Z",
      "projects_count": 15
    }
  ],
  "pagination": {
    "total_results": 1250,
    "page": 1,
    "per_page": 50,
    "total_pages": 25
  }
}
```

---

### GET `/domains/coverage-analysis`

**Description:** Analyze archive coverage across different sources and time periods.

**Query Parameters:**
- `domains` (array): List of domains to analyze (optional)
- `start_date` (datetime): Start date for coverage analysis
- `end_date` (datetime): End date for coverage analysis
- `archive_sources` (array): Specific archive sources to analyze (optional)

**Example Request:**
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/analytics/domains/coverage-analysis?domains=github.com,stackoverflow.com&start_date=2023-01-01T00:00:00Z" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "coverage_summary": {
      "total_domains": 2,
      "average_coverage": 87.5,
      "best_coverage_domain": "github.com",
      "coverage_gaps": 156
    },
    "domain_coverage": [
      {
        "domain": "github.com",
        "coverage_percentage": 92.3,
        "total_potential_captures": 125000,
        "actual_captures": 115375,
        "missing_periods": [
          {
            "start": "2023-03-15T00:00:00Z",
            "end": "2023-03-20T00:00:00Z",
            "reason": "archive_source_downtime"
          }
        ],
        "source_breakdown": {
          "wayback_machine": 98500,
          "common_crawl": 16875
        }
      }
    ]
  }
}
```

---

## Project Analytics Endpoints

### GET `/projects/{project_id}/performance`

**Description:** Get comprehensive project performance analytics and metrics.

**Path Parameters:**
- `project_id` (UUID, required): Project ID to analyze

**Query Parameters:**
- `include_domain_breakdown` (boolean): Include per-domain breakdown (default: `true`)
- `include_time_series` (boolean): Include time series data (default: `false`)
- `start_date` (datetime, optional): Start date for analysis
- `end_date` (datetime, optional): End date for analysis

**Example Request:**
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/analytics/projects/123e4567-e89b-12d3-a456-426614174000/performance" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "project_id": "123e4567-e89b-12d3-a456-426614174000",
    "project_name": "Historical Research Project",
    "total_pages": 85000,
    "successful_pages": 78200,
    "failed_pages": 6800,
    "overall_success_rate": 92.0,
    "avg_scrape_duration": 1.85,
    "total_content_size": 4250.6,
    "scraping_efficiency": 450.5,
    "domain_breakdown": [
      {
        "domain": "archive.org",
        "total_pages": 45000,
        "successful_pages": 42750,
        "error_rate": 5.0,
        "avg_response_time": 1.2,
        "content_size_mb": 2250.3
      }
    ]
  }
}
```

---

### GET `/projects/{project_id}/content-quality`

**Description:** Analyze content quality metrics for a specific project.

**Path Parameters:**
- `project_id` (UUID, required): Project ID to analyze

**Query Parameters:**
- `quality_threshold` (float): Minimum quality score threshold (0.0-1.0, default: 0.7)
- `include_samples` (boolean): Include sample content for each quality tier (default: `false`)

**Example Request:**
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/analytics/projects/123e4567-e89b-12d3-a456-426614174000/content-quality" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "project_id": "123e4567-e89b-12d3-a456-426614174000",
    "quality_summary": {
      "avg_quality_score": 0.82,
      "high_quality_pages": 68000,
      "medium_quality_pages": 12000,
      "low_quality_pages": 5000,
      "quality_distribution": {
        "0.9-1.0": 35000,
        "0.8-0.9": 28000,
        "0.7-0.8": 15000,
        "0.6-0.7": 5000,
        "0.0-0.6": 2000
      }
    },
    "extraction_metrics": {
      "avg_extraction_time": 0.65,
      "successful_extractions": 78200,
      "failed_extractions": 6800,
      "extraction_methods": {
        "firecrawl": 78200,
        "fallback": 0
      }
    },
    "content_characteristics": {
      "avg_word_count": 1250,
      "avg_entity_count": 18,
      "language_distribution": {
        "en": 75000,
        "es": 6000,
        "fr": 4000
      }
    }
  }
}
```

---

### GET `/projects/comparison`

**Description:** Compare performance metrics across multiple projects.

**Query Parameters:**
- `project_ids` (array, required): List of project IDs to compare
- `metrics` (array): Specific metrics to compare (optional)
- `start_date` (datetime, optional): Start date for comparison
- `end_date` (datetime, optional): End date for comparison

**Example Request:**
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/analytics/projects/comparison?project_ids=123e4567-e89b-12d3-a456-426614174000,987fcdeb-51a2-43d7-b890-123456789abc" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "project_id": "123e4567-e89b-12d3-a456-426614174000",
      "project_name": "Historical Research Project",
      "total_pages": 85000,
      "success_rate": 92.0,
      "avg_quality_score": 0.82,
      "scraping_efficiency": 450.5,
      "total_content_mb": 4250.6
    }
  ],
  "comparison_summary": {
    "best_performing_project": "123e4567-e89b-12d3-a456-426614174000",
    "avg_success_rate": 89.5,
    "performance_variance": 12.3
  }
}
```

---

### GET `/projects/{project_id}/efficiency-trends`

**Description:** Analyze efficiency trends over time for a specific project.

**Path Parameters:**
- `project_id` (UUID, required): Project ID to analyze

**Query Parameters:**
- `granularity` (enum): Time granularity for trend analysis (default: `day`)
- `trend_window` (integer): Number of time periods for trend calculation (default: 30)

**Response:**
```json
{
  "success": true,
  "data": {
    "trend_analysis": {
      "overall_trend": "improving",
      "trend_percentage": 15.3,
      "efficiency_score": 0.87
    },
    "time_series": [
      {
        "timestamp": "2024-01-01T00:00:00Z",
        "pages_per_hour": 425.3,
        "success_rate": 91.2,
        "avg_response_time": 1.8
      }
    ]
  }
}
```

---

## Content Analytics Endpoints

### GET `/content/quality-distribution`

**Description:** Analyze content quality distribution across all projects.

**Query Parameters:**
- `projects` (array, optional): Specific project IDs to analyze
- `domains` (array, optional): Specific domains to analyze
- `quality_buckets` (integer): Number of quality score buckets (default: 10)

**Example Request:**
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/analytics/content/quality-distribution" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "distribution_summary": {
      "total_pages": 2500000,
      "avg_quality_score": 0.78,
      "median_quality_score": 0.82,
      "quality_std_dev": 0.15
    },
    "quality_buckets": [
      {
        "range": "0.9-1.0",
        "count": 875000,
        "percentage": 35.0
      },
      {
        "range": "0.8-0.9", 
        "count": 750000,
        "percentage": 30.0
      }
    ],
    "quality_factors": {
      "extraction_method_impact": {
        "firecrawl": 0.85,
        "fallback": 0.42
      },
      "domain_quality_correlation": 0.73,
      "content_size_correlation": 0.45
    }
  }
}
```

---

### GET `/content/extraction-performance`

**Description:** Analyze content extraction performance metrics.

**Query Parameters:**
- `extraction_methods` (array, optional): Specific extraction methods to analyze
- `include_error_analysis` (boolean): Include detailed error analysis (default: `true`)

**Response:**
```json
{
  "success": true,
  "data": {
    "performance_summary": {
      "total_extractions": 2450000,
      "successful_extractions": 2303500,
      "avg_extraction_time": 0.72,
      "overall_success_rate": 94.0
    },
    "method_performance": [
      {
        "method": "firecrawl",
        "extractions": 2303500,
        "success_rate": 94.5,
        "avg_time": 0.68,
        "quality_score": 0.85
      }
    ],
    "error_analysis": {
      "timeout_errors": 52000,
      "parsing_errors": 38500,
      "network_errors": 32000,
      "content_errors": 24000
    }
  }
}
```

---

### GET `/content/language-analysis`

**Description:** Analyze language detection and distribution across content.

**Query Parameters:**
- `languages` (array, optional): Specific languages to analyze
- `confidence_threshold` (float): Minimum language detection confidence (default: 0.8)

**Response:**
```json
{
  "success": true,
  "data": {
    "language_summary": {
      "total_analyzed": 2300000,
      "detected_languages": 47,
      "avg_confidence": 0.89,
      "multilingual_pages": 125000
    },
    "language_distribution": [
      {
        "language": "en",
        "language_name": "English",
        "count": 1725000,
        "percentage": 75.0,
        "avg_confidence": 0.92
      },
      {
        "language": "es",
        "language_name": "Spanish", 
        "count": 230000,
        "percentage": 10.0,
        "avg_confidence": 0.87
      }
    ]
  }
}
```

---

## System Analytics Endpoints

### GET `/system/performance`

**Description:** Get comprehensive system performance overview and metrics.

**Query Parameters:**
- `include_database_metrics` (boolean): Include database-specific metrics (default: `true`)
- `include_resource_usage` (boolean): Include detailed resource usage (default: `true`)
- `time_range` (enum): Time range for metrics - `1h`, `6h`, `24h`, `7d`, `30d` (default: `24h`)

**Example Request:**
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/analytics/system/performance?time_range=24h" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Response:**
```json
{
  "success": true,
  "data": {
    "uptime_hours": 168.5,
    "total_requests": 1250000,
    "avg_response_time": 0.185,
    "error_rate": 0.8,
    "active_users": 145,
    "active_projects": 89,
    "total_pages_scraped": 2500000,
    "scraping_throughput": 1042.3,
    "database_metrics": [
      {
        "database_type": "postgresql",
        "total_queries": 875000,
        "avg_query_time": 0.025,
        "error_rate": 0.2,
        "cache_hit_rate": 89.5,
        "connection_pool_usage": 72.3
      },
      {
        "database_type": "duckdb", 
        "total_queries": 125000,
        "avg_query_time": 0.156,
        "error_rate": 0.1,
        "cache_hit_rate": 84.2,
        "memory_usage_mb": 2048.5
      }
    ],
    "resource_usage": {
      "cpu_usage_percent": 45.2,
      "memory_usage_percent": 67.8,
      "disk_usage_percent": 34.1,
      "network_io_mbps": 125.6
    }
  }
}
```

---

### GET `/system/resource-usage`

**Description:** Detailed system resource utilization analytics.

**Query Parameters:**
- `resources` (array): Specific resources to monitor - `cpu`, `memory`, `disk`, `network`
- `granularity` (enum): Time granularity for resource data (default: `hour`)

**Response:**
```json
{
  "success": true,
  "data": {
    "current_usage": {
      "cpu_percent": 45.2,
      "memory_percent": 67.8,
      "disk_percent": 34.1,
      "network_io_mbps": 125.6
    },
    "usage_trends": [
      {
        "timestamp": "2024-01-31T23:00:00Z",
        "cpu_percent": 42.1,
        "memory_percent": 65.3,
        "disk_percent": 34.0,
        "network_io_mbps": 98.2
      }
    ],
    "peak_usage": {
      "cpu_peak": 87.3,
      "memory_peak": 89.1,
      "peak_timestamp": "2024-01-31T14:30:00Z"
    },
    "resource_alerts": [
      {
        "resource": "memory",
        "threshold": 80.0,
        "current": 67.8,
        "status": "normal"
      }
    ]
  }
}
```

---

### GET `/system/user-activity`

**Description:** Analyze user activity patterns and engagement metrics.

**Query Parameters:**
- `activity_types` (array): Types of activities to analyze
- `user_segments` (array): User segments to analyze

**Response:**
```json
{
  "success": true,
  "data": {
    "activity_summary": {
      "total_active_users": 145,
      "daily_active_users": 89,
      "avg_session_duration": 45.2,
      "peak_activity_hour": 14
    },
    "activity_breakdown": {
      "project_creation": 23,
      "scraping_operations": 1250,
      "analytics_queries": 3450,
      "data_exports": 89
    },
    "user_engagement": {
      "highly_active": 25,
      "moderately_active": 67,
      "low_activity": 53
    }
  }
}
```

---

## Real-time Analytics (WebSocket)

### WebSocket `/ws/live-dashboard`

**Description:** Real-time dashboard updates with system and project metrics.

**Connection:** `wss://api.chrono-scraper.com/api/v1/analytics/ws/live-dashboard`

**Authentication:** Include JWT token in connection headers or query parameters.

**Message Types:**
- `system_metrics`: Real-time system performance data
- `project_updates`: Live project scraping progress
- `alert_notifications`: System alerts and warnings
- `user_activity`: Real-time user activity updates

**Example Messages:**
```json
// System Metrics Update
{
  "type": "system_metrics",
  "timestamp": "2024-01-31T16:45:30Z",
  "data": {
    "active_scraping_jobs": 12,
    "pages_per_minute": 125.3,
    "system_load": 0.67,
    "error_rate": 0.8
  }
}

// Project Update
{
  "type": "project_update",
  "timestamp": "2024-01-31T16:45:31Z",
  "data": {
    "project_id": "123e4567-e89b-12d3-a456-426614174000",
    "pages_scraped": 1250,
    "success_rate": 94.2,
    "estimated_completion": "2024-01-31T18:30:00Z"
  }
}
```

---

### WebSocket `/ws/export-progress`

**Description:** Real-time export job progress tracking.

**Message Types:**
- `export_started`: Export job initiation
- `export_progress`: Progress updates with completion percentage
- `export_completed`: Final export results with download link
- `export_error`: Export failure notifications

---

## Export & Integration Endpoints

### POST `/export/analytics-report`

**Description:** Generate and export comprehensive analytics reports.

**Request Body:**
```json
{
  "report_type": "comprehensive",
  "scope": {
    "projects": ["123e4567-e89b-12d3-a456-426614174000"],
    "domains": ["github.com", "stackoverflow.com"],
    "start_date": "2024-01-01T00:00:00Z",
    "end_date": "2024-01-31T23:59:59Z"
  },
  "format": "excel",
  "include_charts": true,
  "delivery_method": "download"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "export_job_id": "exp_123456789",
    "estimated_completion": "2024-01-31T17:00:00Z",
    "download_url": "https://exports.chrono-scraper.com/reports/exp_123456789.xlsx",
    "expires_at": "2024-02-07T17:00:00Z"
  }
}
```

---

### GET `/export/{job_id}/status`

**Description:** Check status of export job.

**Response:**
```json
{
  "success": true,
  "data": {
    "job_id": "exp_123456789",
    "status": "completed",
    "progress_percentage": 100,
    "created_at": "2024-01-31T16:45:00Z",
    "completed_at": "2024-01-31T16:58:30Z",
    "download_url": "https://exports.chrono-scraper.com/reports/exp_123456789.xlsx",
    "file_size_mb": 15.7
  }
}
```

---

## Health & Monitoring Endpoints

### GET `/health`

**Description:** Overall analytics system health check.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-31T16:45:00Z",
  "services": {
    "duckdb": "healthy",
    "postgresql": "healthy", 
    "hybrid_router": "healthy",
    "cache": "healthy",
    "export_service": "healthy"
  },
  "performance": {
    "avg_response_time": 0.185,
    "cache_hit_rate": 84.2,
    "error_rate": 0.8
  }
}
```

---

## Authentication & Security

### Authentication Headers
```bash
# Required for all authenticated endpoints
Authorization: Bearer YOUR_JWT_TOKEN

# Optional headers for enhanced security
X-Request-ID: unique-request-identifier
X-Client-Version: app-version
```

### Rate Limiting Headers
```bash
# Included in all API responses
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 856
X-RateLimit-Reset: 1643723400
```

### Error Response Format
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": {
      "field": "start_date",
      "issue": "Date format must be ISO 8601"
    },
    "suggestions": [
      "Use ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ",
      "Ensure end_date is after start_date"
    ],
    "documentation": "https://docs.chrono-scraper.com/api/analytics"
  },
  "request_id": "req_123456789",
  "timestamp": "2024-01-31T16:45:00Z"
}
```

---

## Performance Considerations

### Response Times (SLA)
- **Simple queries** (single project/domain): < 200ms
- **Complex analytics** (multi-project aggregations): < 1s
- **Large data exports** (millions of records): < 30s
- **Real-time updates** (WebSocket): < 100ms

### Caching Strategy
- **L1 Cache**: In-memory, 5-minute TTL for hot data
- **L2 Cache**: Redis, 30-minute TTL for shared results  
- **L3 Cache**: Query plans and materialized views

### Query Optimization
- Automatic predicate pushdown for filtered queries
- Column pruning for projection optimization
- Intelligent join reordering based on cardinality
- Partition pruning for time-based queries

---

## SDKs and Integration

### Official SDKs
- **Python**: `pip install chrono-scraper-analytics`
- **JavaScript/Node.js**: `npm install @chrono-scraper/analytics`
- **Go**: `go get github.com/chrono-scraper/analytics-go`

### Third-party Integrations
- **Grafana**: Dashboard templates and data source plugin
- **Tableau**: Native connector for business intelligence
- **Power BI**: Custom connector for Microsoft ecosystem
- **Jupyter**: Python SDK with notebook integration

### Webhook Support
Configure webhooks for real-time notifications:
- Export completion notifications
- Performance threshold alerts
- Data quality notifications
- System health changes

---

## Code Examples

### Python SDK Usage
```python
from chrono_scraper_analytics import AnalyticsClient

client = AnalyticsClient(api_key="your_jwt_token")

# Get domain timeline
timeline = await client.domains.get_timeline(
    domain="github.com",
    granularity="day",
    start_date="2024-01-01",
    end_date="2024-01-31"
)

# Export analytics report
export_job = await client.exports.create_report(
    report_type="comprehensive",
    projects=["project-uuid"],
    format="excel"
)
```

### JavaScript/Node.js Usage
```javascript
import { AnalyticsClient } from '@chrono-scraper/analytics';

const client = new AnalyticsClient({ apiKey: 'your_jwt_token' });

// Get project performance
const performance = await client.projects.getPerformance('project-uuid', {
  includeDomainBreakdown: true,
  startDate: '2024-01-01T00:00:00Z'
});

// Real-time dashboard connection
const dashboard = client.realtime.connectDashboard();
dashboard.on('system_metrics', (data) => {
  console.log('System metrics update:', data);
});
```

### cURL Examples
```bash
# Get top performing domains
curl -X GET "https://api.chrono-scraper.com/api/v1/analytics/domains/top-domains?metric=success_rate&limit=10" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"

# Export project analytics
curl -X POST "https://api.chrono-scraper.com/api/v1/analytics/export/analytics-report" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "report_type": "project_performance",
    "scope": {
      "projects": ["123e4567-e89b-12d3-a456-426614174000"]
    },
    "format": "json"
  }'
```

---

## Migration Guide

### From Legacy Analytics API

**Breaking Changes:**
- Endpoint URLs changed from `/api/v1/stats/` to `/api/v1/analytics/`
- Response format standardized with `success`, `data`, `metadata` fields
- Authentication now requires JWT tokens instead of API keys

**Migration Steps:**
1. Update endpoint URLs in your applications
2. Migrate from API key to JWT token authentication
3. Update response parsing to handle new response format
4. Test with new performance improvements (expect 5-10x faster responses)

**Backward Compatibility:**
- Legacy endpoints available until Q2 2024 with deprecation warnings
- Automatic response format conversion available via `X-Legacy-Format: true` header

---

## Troubleshooting

### Common Issues

**Query Timeouts:**
- Reduce date range for large time-series queries
- Use pagination for large result sets
- Enable caching for repeated queries

**Rate Limiting:**
- Monitor `X-RateLimit-*` headers
- Implement exponential backoff for retries
- Contact support for rate limit increases

**Authentication Errors:**
- Verify JWT token is not expired
- Check token has required analytics permissions
- Ensure proper Authorization header format

### Support Resources
- **Documentation**: https://docs.chrono-scraper.com/analytics
- **Status Page**: https://status.chrono-scraper.com
- **Support**: analytics-support@chrono-scraper.com

---

This comprehensive API reference provides complete documentation for the Phase 2 DuckDB Analytics system, enabling developers to leverage high-performance analytics capabilities with enterprise-grade reliability and comprehensive monitoring.

## Complete Endpoint Summary (24 Endpoints)

**Domain Analytics (4 endpoints):**
- GET `/domains/{domain}/timeline`
- GET `/domains/{domain}/statistics` 
- GET `/domains/top-domains`
- GET `/domains/coverage-analysis`

**Project Analytics (4 endpoints):**
- GET `/projects/{project_id}/performance`
- GET `/projects/{project_id}/content-quality`
- GET `/projects/comparison`
- GET `/projects/{project_id}/efficiency-trends`

**Content Analytics (3 endpoints):**
- GET `/content/quality-distribution`
- GET `/content/extraction-performance`
- GET `/content/language-analysis`

**System Analytics (3 endpoints):**
- GET `/system/performance`
- GET `/system/resource-usage`
- GET `/system/user-activity`

**Real-time Features (2 WebSocket endpoints):**
- WS `/ws/live-dashboard`
- WS `/ws/export-progress`

**Export & Integration (2 endpoints):**
- POST `/export/analytics-report`
- GET `/export/{job_id}/status`

**Health & Monitoring (1 endpoint):**
- GET `/health`

**Additional Endpoints (5 endpoints via other modules):**
- DuckDB Analytics API (3 endpoints from `duckdb_analytics.py`)
- Hybrid Query Router API (1 endpoint from `hybrid_query_router_api.py`) 
- Analytics WebSocket (1 endpoint from `analytics_websocket.py`)

**Total: 24+ Production-Ready Analytics Endpoints**