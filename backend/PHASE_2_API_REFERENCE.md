# Phase 2 DuckDB Analytics API Reference

## 📚 Complete API Documentation

The Phase 2 Analytics API provides comprehensive endpoints for high-performance analytical operations, real-time monitoring, and data export capabilities. All endpoints are built on the DuckDB analytics engine with intelligent query routing and multi-level caching.

## 🔐 Authentication & Authorization

### Authentication Requirements
All analytics endpoints require Bearer token authentication:

```bash
# Obtain access token
POST /api/v1/auth/login
{
  "email": "user@example.com",
  "password": "password"
}

# Use token in requests
Authorization: Bearer <access_token>
```

### Rate Limiting
- **Standard endpoints**: 100 requests/minute per user
- **Export endpoints**: 10 requests/minute per user  
- **WebSocket connections**: 5 concurrent connections per user

## 🏷️ Common Request/Response Patterns

### Standard Request Headers
```http
Content-Type: application/json
Authorization: Bearer <token>
Accept: application/json
User-Agent: ChromoScraper-Client/1.0
```

### Standard Response Format
```json
{
  "data": { ... },           // Response payload
  "success": true,           // Operation success indicator
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_time": 0.156,   // Query execution time in seconds
  "database_used": "duckdb", // Database that processed the query
  "cache_hit": false,        // Whether result was served from cache
  "metadata": {
    "query_type": "analytics",
    "routing_reason": "Complex aggregation detected"
  }
}
```

### Standard Error Response
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid date range provided",
    "details": {
      "start_date": ["Date must not be in the future"],
      "end_date": ["End date must be after start date"]
    },
    "suggestions": [
      "Check that start_date < end_date",
      "Ensure dates are in ISO format (YYYY-MM-DD)"
    ]
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

## 🌐 Domain Analytics Endpoints

### 1. Get Domain Timeline Analytics

Retrieve domain scraping activity over time with configurable granularity.

**Endpoint**: `GET /api/v1/analytics/domains/{domain}/timeline`

**Parameters**:
- `domain` (path): Target domain name (e.g., `example.com`)
- `granularity` (query): Time granularity - `minute`, `hour`, `day`, `week`, `month`, `quarter`, `year`
- `start_date` (query, optional): Start date (ISO format: `2024-01-01T00:00:00Z`)
- `end_date` (query, optional): End date (ISO format: `2024-01-31T23:59:59Z`)
- `include_subdomains` (query): Include subdomain data (default: `false`)
- `use_cache` (query): Use cached results (default: `true`)

**Example Request**:
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/analytics/domains/example.com/timeline?granularity=day&start_date=2024-01-01T00:00:00Z&end_date=2024-01-31T23:59:59Z" \
  -H "Authorization: Bearer <token>" \
  -H "Accept: application/json"
```

**Example Response**:
```json
{
  "success": true,
  "data": [
    {
      "timestamp": "2024-01-01T00:00:00Z",
      "pages_scraped": 1247,
      "pages_successful": 1198,
      "pages_failed": 49,
      "success_rate": 96.07,
      "error_rate": 3.93,
      "avg_response_time": 2.34,
      "content_size_mb": 45.6,
      "unique_urls": 1205,
      "duplicate_rate": 3.37
    },
    {
      "timestamp": "2024-01-02T00:00:00Z",
      "pages_scraped": 1356,
      "pages_successful": 1289,
      "pages_failed": 67,
      "success_rate": 95.06,
      "error_rate": 4.94,
      "avg_response_time": 2.67,
      "content_size_mb": 52.3,
      "unique_urls": 1298,
      "duplicate_rate": 4.27
    }
  ],
  "summary": {
    "total_pages": 38567,
    "success_rate": 95.8,
    "avg_error_rate": 4.2,
    "total_content_mb": 1423.7,
    "time_span_days": 31
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_time": 0.234,
  "database_used": "duckdb",
  "cache_hit": false
}
```

### 2. Get Domain Statistics

Comprehensive domain metrics and performance indicators.

**Endpoint**: `GET /api/v1/analytics/domains/{domain}/statistics`

**Parameters**:
- `domain` (path): Target domain name
- `start_date` (query, optional): Analysis start date
- `end_date` (query, optional): Analysis end date
- `include_historical` (query): Include historical comparison (default: `true`)

**Example Response**:
```json
{
  "success": true,
  "data": {
    "domain_info": {
      "domain": "example.com",
      "first_scraped": "2023-05-15T09:22:00Z",
      "last_scraped": "2024-01-15T10:15:00Z",
      "total_days_active": 245
    },
    "scraping_metrics": {
      "total_pages": 45623,
      "successful_pages": 43789,
      "failed_pages": 1834,
      "success_rate": 95.98,
      "avg_response_time": 2.45,
      "median_response_time": 1.89,
      "p95_response_time": 5.67
    },
    "content_metrics": {
      "total_content_mb": 1678.9,
      "avg_content_size_kb": 37.6,
      "unique_urls": 42156,
      "duplicate_rate": 7.59,
      "content_types": {
        "text/html": 89.4,
        "application/pdf": 6.7,
        "text/plain": 2.1,
        "other": 1.8
      }
    },
    "quality_metrics": {
      "avg_quality_score": 7.8,
      "high_quality_pages": 78.9,
      "medium_quality_pages": 18.4,
      "low_quality_pages": 2.7,
      "extraction_success_rate": 94.2
    },
    "error_analysis": {
      "top_error_types": [
        {"error": "timeout", "count": 456, "percentage": 24.8},
        {"error": "404_not_found", "count": 378, "percentage": 20.6},
        {"error": "connection_error", "count": 234, "percentage": 12.8}
      ],
      "error_trend": "decreasing"
    },
    "performance_trends": {
      "response_time_trend": "stable",
      "success_rate_trend": "improving",
      "content_size_trend": "increasing"
    }
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_time": 0.456,
  "database_used": "duckdb"
}
```

### 3. Get Top Domains

Retrieve top-performing domains by various metrics.

**Endpoint**: `GET /api/v1/analytics/domains/top-domains`

**Parameters**:
- `metric` (query): Ranking metric - `pages_scraped`, `success_rate`, `content_size`, `response_time`
- `limit` (query): Number of domains to return (default: 20, max: 100)
- `time_period` (query): Time period - `7d`, `30d`, `90d`, `1y` (default: `30d`)
- `min_pages` (query): Minimum pages threshold (default: 100)

**Example Request**:
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/analytics/domains/top-domains?metric=success_rate&limit=10&time_period=30d" \
  -H "Authorization: Bearer <token>"
```

**Example Response**:
```json
{
  "success": true,
  "data": [
    {
      "rank": 1,
      "domain": "example.com",
      "pages_scraped": 45623,
      "success_rate": 98.45,
      "avg_response_time": 1.23,
      "total_content_mb": 1234.5,
      "quality_score": 8.7,
      "last_scraped": "2024-01-15T09:45:00Z"
    },
    {
      "rank": 2,
      "domain": "another-domain.org",
      "pages_scraped": 32456,
      "success_rate": 97.89,
      "avg_response_time": 1.67,
      "total_content_mb": 987.6,
      "quality_score": 8.4,
      "last_scraped": "2024-01-15T10:12:00Z"
    }
  ],
  "metadata": {
    "ranking_metric": "success_rate",
    "time_period": "30d",
    "total_domains": 1247,
    "min_pages_threshold": 100
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_time": 0.145,
  "database_used": "duckdb"
}
```

---

## 📊 Project Analytics Endpoints

### 4. Get Project Performance

Comprehensive project performance metrics and analysis.

**Endpoint**: `GET /api/v1/analytics/projects/{project_id}/performance`

**Parameters**:
- `project_id` (path): Project UUID
- `start_date` (query, optional): Analysis start date
- `end_date` (query, optional): Analysis end date
- `granularity` (query): Time granularity (default: `day`)
- `include_domains` (query): Include per-domain breakdown (default: `true`)

**Example Response**:
```json
{
  "success": true,
  "data": {
    "project_info": {
      "project_id": "550e8400-e29b-41d4-a716-446655440000",
      "project_name": "News Site Analysis",
      "created_at": "2023-08-15T14:30:00Z",
      "domains_count": 12,
      "active_domains": 8
    },
    "overall_metrics": {
      "total_pages": 156789,
      "successful_pages": 149234,
      "success_rate": 95.18,
      "total_content_gb": 5.67,
      "avg_pages_per_day": 1247,
      "scraping_efficiency": 87.3
    },
    "performance_timeline": [
      {
        "date": "2024-01-01",
        "pages_scraped": 1456,
        "success_rate": 96.2,
        "avg_response_time": 2.1,
        "content_mb": 67.8
      }
    ],
    "domain_performance": [
      {
        "domain": "example.com",
        "pages_scraped": 45623,
        "success_rate": 96.8,
        "avg_response_time": 1.89,
        "content_share_percent": 29.1
      }
    ],
    "quality_metrics": {
      "avg_extraction_score": 8.2,
      "high_quality_pages_percent": 76.4,
      "content_completeness": 91.7,
      "entity_extraction_rate": 83.9
    }
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_time": 0.567,
  "database_used": "duckdb"
}
```

### 5. Project Content Quality Analysis

Detailed analysis of content quality metrics for a specific project.

**Endpoint**: `GET /api/v1/analytics/projects/{project_id}/content-quality`

**Parameters**:
- `project_id` (path): Project UUID
- `quality_threshold` (query): Quality score threshold (default: 7.0)
- `include_samples` (query): Include sample pages for each quality category (default: `false`)

**Example Response**:
```json
{
  "success": true,
  "data": {
    "quality_distribution": {
      "high_quality": {
        "count": 34567,
        "percentage": 76.4,
        "avg_score": 8.7,
        "score_range": "8.0-10.0"
      },
      "medium_quality": {
        "count": 8945,
        "percentage": 19.8,
        "avg_score": 6.2,
        "score_range": "5.0-7.9"
      },
      "low_quality": {
        "count": 1723,
        "percentage": 3.8,
        "avg_score": 3.1,
        "score_range": "0.0-4.9"
      }
    },
    "quality_factors": {
      "content_completeness": 89.4,
      "structure_quality": 85.7,
      "text_coherence": 91.2,
      "metadata_presence": 76.8,
      "media_quality": 68.9
    },
    "improvement_suggestions": [
      "Increase metadata extraction coverage",
      "Improve media content processing",
      "Focus on structured content sources"
    ],
    "quality_trends": {
      "7_day_trend": "improving",
      "30_day_trend": "stable",
      "quality_score_change": 0.3
    }
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_time": 0.234,
  "database_used": "duckdb"
}
```

### 6. Project Comparison Analysis

Compare performance metrics across multiple projects.

**Endpoint**: `POST /api/v1/analytics/projects/comparison`

**Request Body**:
```json
{
  "project_ids": [
    "550e8400-e29b-41d4-a716-446655440000",
    "550e8400-e29b-41d4-a716-446655440001"
  ],
  "metrics": [
    "success_rate",
    "response_time", 
    "content_quality",
    "scraping_efficiency"
  ],
  "time_period": "30d"
}
```

**Example Response**:
```json
{
  "success": true,
  "data": {
    "comparison_matrix": [
      {
        "project_id": "550e8400-e29b-41d4-a716-446655440000",
        "project_name": "News Analysis",
        "success_rate": 96.8,
        "avg_response_time": 1.89,
        "content_quality": 8.2,
        "scraping_efficiency": 87.3,
        "rank_success_rate": 1,
        "rank_response_time": 2,
        "rank_content_quality": 1,
        "rank_efficiency": 1
      },
      {
        "project_id": "550e8400-e29b-41d4-a716-446655440001", 
        "project_name": "E-commerce Research",
        "success_rate": 94.2,
        "avg_response_time": 1.45,
        "content_quality": 7.6,
        "scraping_efficiency": 82.1,
        "rank_success_rate": 2,
        "rank_response_time": 1,
        "rank_content_quality": 2,
        "rank_efficiency": 2
      }
    ],
    "summary": {
      "best_performing_project": "550e8400-e29b-41d4-a716-446655440000",
      "fastest_project": "550e8400-e29b-41d4-a716-446655440001",
      "highest_quality_project": "550e8400-e29b-41d4-a716-446655440000"
    }
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_time": 0.445,
  "database_used": "duckdb"
}
```

---

## 📈 Content Analytics Endpoints

### 7. Content Quality Distribution

Analyze content quality distribution across the system.

**Endpoint**: `GET /api/v1/analytics/content/quality-distribution`

**Parameters**:
- `scope` (query): Analysis scope - `global`, `project`, `domain`
- `scope_id` (query): ID for project/domain scope
- `granularity` (query): Time granularity for trends
- `quality_bands` (query): Number of quality bands (default: 5)

**Example Response**:
```json
{
  "success": true,
  "data": {
    "distribution": [
      {
        "quality_band": "Excellent (9.0-10.0)",
        "count": 23456,
        "percentage": 34.2,
        "avg_score": 9.4
      },
      {
        "quality_band": "Good (7.0-8.9)",
        "count": 18902,
        "percentage": 27.6,
        "avg_score": 7.8
      },
      {
        "quality_band": "Fair (5.0-6.9)",
        "count": 15634,
        "percentage": 22.8,
        "avg_score": 5.9
      },
      {
        "quality_band": "Poor (3.0-4.9)",
        "count": 8234,
        "percentage": 12.0,
        "avg_score": 3.7
      },
      {
        "quality_band": "Very Poor (0.0-2.9)",
        "count": 2341,
        "percentage": 3.4,
        "avg_score": 1.8
      }
    ],
    "statistics": {
      "total_pages": 68567,
      "mean_quality": 7.2,
      "median_quality": 7.8,
      "std_deviation": 2.1,
      "skewness": -0.3
    },
    "trends": [
      {
        "date": "2024-01-01",
        "avg_quality": 7.1,
        "high_quality_percent": 58.9
      },
      {
        "date": "2024-01-02", 
        "avg_quality": 7.3,
        "high_quality_percent": 61.2
      }
    ]
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_time": 0.189,
  "database_used": "duckdb"
}
```

### 8. Language Analysis

Analyze language distribution and characteristics of scraped content.

**Endpoint**: `GET /api/v1/analytics/content/language-analysis`

**Example Response**:
```json
{
  "success": true,
  "data": {
    "language_distribution": [
      {
        "language": "en",
        "language_name": "English", 
        "count": 45623,
        "percentage": 67.8,
        "avg_quality": 8.1,
        "avg_content_size": 4521
      },
      {
        "language": "es",
        "language_name": "Spanish",
        "count": 12456,
        "percentage": 18.5,
        "avg_quality": 7.6,
        "avg_content_size": 3876
      },
      {
        "language": "fr", 
        "language_name": "French",
        "count": 5234,
        "percentage": 7.8,
        "avg_quality": 7.9,
        "avg_content_size": 4123
      }
    ],
    "multilingual_analysis": {
      "multilingual_pages": 2134,
      "multilingual_percentage": 3.2,
      "avg_languages_per_page": 1.1,
      "dominant_language_confidence": 94.7
    },
    "quality_by_language": {
      "highest_quality_language": "en",
      "lowest_quality_language": "other",
      "quality_variance": 1.3
    }
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_time": 0.123,
  "database_used": "duckdb"
}
```

---

## 🖥️ System Analytics Endpoints

### 9. System Performance Overview

Comprehensive system-wide performance metrics and health indicators.

**Endpoint**: `GET /api/v1/analytics/system/performance-overview`

**Example Response**:
```json
{
  "success": true,
  "data": {
    "system_health": {
      "overall_status": "healthy",
      "uptime_hours": 2456.7,
      "last_restart": "2024-01-10T03:15:00Z",
      "health_score": 94.2
    },
    "database_performance": {
      "postgresql": {
        "status": "healthy",
        "avg_response_time": 0.045,
        "active_connections": 23,
        "max_connections": 100,
        "query_throughput": 2345.6,
        "cpu_usage": 45.2,
        "memory_usage": 67.8
      },
      "duckdb": {
        "status": "healthy", 
        "avg_response_time": 0.234,
        "active_connections": 8,
        "max_connections": 32,
        "query_throughput": 456.7,
        "cpu_usage": 23.4,
        "memory_usage": 34.2
      }
    },
    "api_performance": {
      "requests_per_minute": 1247,
      "avg_response_time": 0.156,
      "p95_response_time": 0.445,
      "error_rate": 0.34,
      "cache_hit_rate": 87.6
    },
    "scraping_performance": {
      "active_scraping_jobs": 12,
      "pages_per_minute": 234.5,
      "success_rate": 96.8,
      "avg_extraction_time": 1.89,
      "queue_depth": 156
    },
    "resource_utilization": {
      "cpu_usage": 34.5,
      "memory_usage": 56.7,
      "disk_usage": 67.8,
      "network_io": {
        "incoming_mbps": 12.3,
        "outgoing_mbps": 8.9
      }
    }
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_time": 0.234,
  "database_used": "postgresql"
}
```

### 10. Error Analysis

Comprehensive error pattern analysis and troubleshooting insights.

**Endpoint**: `GET /api/v1/analytics/system/error-analysis`

**Parameters**:
- `time_period` (query): Analysis time period (default: `7d`)
- `error_threshold` (query): Minimum error count to include (default: 10)
- `group_by` (query): Group errors by `type`, `domain`, `project` (default: `type`)

**Example Response**:
```json
{
  "success": true,
  "data": {
    "error_summary": {
      "total_errors": 2346,
      "error_rate": 3.45,
      "most_common_error": "timeout",
      "error_trend": "decreasing"
    },
    "error_breakdown": [
      {
        "error_type": "timeout",
        "count": 567,
        "percentage": 24.2,
        "avg_duration": 30.0,
        "affected_domains": 23,
        "trend": "stable",
        "resolution_suggestions": [
          "Increase timeout settings",
          "Check network connectivity",
          "Review target site performance"
        ]
      },
      {
        "error_type": "404_not_found",
        "count": 423,
        "percentage": 18.0,
        "affected_domains": 45,
        "trend": "decreasing",
        "resolution_suggestions": [
          "Update URL patterns",
          "Check for moved content",
          "Review crawling strategy"
        ]
      }
    ],
    "domain_error_analysis": [
      {
        "domain": "problematic-site.com",
        "error_count": 234,
        "error_rate": 45.6,
        "primary_error": "connection_error",
        "status": "investigation_needed"
      }
    ],
    "temporal_analysis": {
      "peak_error_hours": [14, 15, 16],
      "error_by_day_of_week": {
        "monday": 12.3,
        "tuesday": 11.8,
        "wednesday": 13.1
      }
    }
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_time": 0.345,
  "database_used": "duckdb"
}
```

---

## ⏱️ Time Series Analytics Endpoints

### 11. Time Series Data

Flexible time series analytics with forecasting capabilities.

**Endpoint**: `GET /api/v1/analytics/time-series/{metric}`

**Parameters**:
- `metric` (path): Metric name - `pages_scraped`, `success_rate`, `response_time`, `content_size`
- `granularity` (query): Time granularity
- `aggregation` (query): Aggregation function - `sum`, `avg`, `min`, `max`, `count`
- `forecast_periods` (query): Number of periods to forecast (optional)
- `include_confidence_intervals` (query): Include forecast confidence intervals

**Example Request**:
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/analytics/time-series/pages_scraped?granularity=hour&aggregation=sum&forecast_periods=24" \
  -H "Authorization: Bearer <token>"
```

**Example Response**:
```json
{
  "success": true,
  "data": {
    "metric": "pages_scraped",
    "aggregation": "sum",
    "granularity": "hour",
    "time_series": [
      {
        "timestamp": "2024-01-15T00:00:00Z",
        "value": 1234,
        "type": "actual"
      },
      {
        "timestamp": "2024-01-15T01:00:00Z", 
        "value": 1567,
        "type": "actual"
      }
    ],
    "forecast": [
      {
        "timestamp": "2024-01-16T00:00:00Z",
        "value": 1345,
        "confidence_lower": 1123,
        "confidence_upper": 1567,
        "type": "forecast"
      }
    ],
    "statistics": {
      "min": 456,
      "max": 2345,
      "mean": 1234.5,
      "std_dev": 234.6,
      "trend": "increasing",
      "seasonality_detected": true
    },
    "forecast_accuracy": {
      "model_type": "ARIMA",
      "mae": 123.4,
      "rmse": 156.7,
      "mape": 8.9
    }
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_time": 0.567,
  "database_used": "duckdb"
}
```

---

## 🔄 Real-Time WebSocket API

### WebSocket Connection

Connect to real-time analytics updates via WebSocket.

**Endpoint**: `ws://localhost:8000/api/v1/analytics/ws`

**Authentication**: Include JWT token in connection header or query parameter.

**Connection Example**:
```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/analytics/ws', [], {
  headers: {
    'Authorization': 'Bearer <token>'
  }
});

// Alternative: Token in query parameter
const ws = new WebSocket('ws://localhost:8000/api/v1/analytics/ws?token=<token>');
```

### Subscription Management

Subscribe to specific analytics channels for targeted updates.

**Subscribe to Channel**:
```json
{
  "action": "subscribe",
  "channel": "project_performance",
  "params": {
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "update_interval": 30
  }
}
```

**Available Channels**:
- `system_health`: System-wide health metrics (5-second updates)
- `project_performance`: Project-specific metrics (30-second updates)  
- `scraping_progress`: Real-time scraping progress (10-second updates)
- `domain_statistics`: Domain performance updates (60-second updates)
- `error_monitoring`: Error events and alerts (real-time)

**Unsubscribe from Channel**:
```json
{
  "action": "unsubscribe", 
  "channel": "project_performance"
}
```

### Real-Time Message Format

**System Health Update**:
```json
{
  "channel": "system_health",
  "timestamp": "2024-01-15T10:30:15Z",
  "data": {
    "system_status": "healthy",
    "cpu_usage": 34.5,
    "memory_usage": 56.7,
    "active_connections": 145,
    "queries_per_second": 23.4,
    "cache_hit_rate": 89.2
  }
}
```

**Scraping Progress Update**:
```json
{
  "channel": "scraping_progress",
  "timestamp": "2024-01-15T10:30:15Z",
  "data": {
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "domain": "example.com",
    "pages_completed": 1234,
    "pages_total": 5000,
    "progress_percentage": 24.68,
    "current_success_rate": 96.8,
    "estimated_completion": "2024-01-15T12:45:00Z"
  }
}
```

---

## 📤 Export Functionality

### 12. Bulk Data Export

Request export of analytics data in various formats.

**Endpoint**: `POST /api/v1/analytics/export/bulk-data`

**Request Body**:
```json
{
  "export_type": "project_analytics",
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "start_date": "2024-01-01T00:00:00Z",
  "end_date": "2024-01-31T23:59:59Z",
  "format": "excel",
  "include_charts": true,
  "include_summary": true,
  "custom_fields": [
    "domain_performance",
    "quality_metrics",
    "error_analysis"
  ]
}
```

**Supported Formats**:
- `json`: JSON format (always available)
- `csv`: CSV format (always available)
- `excel`: Excel workbook with multiple sheets (requires openpyxl)
- `parquet`: High-performance columnar format (requires pyarrow)
- `pdf`: Professional report format (requires reportlab)

**Example Response**:
```json
{
  "success": true,
  "data": {
    "job_id": "export-550e8400-e29b-41d4-a716-446655440001",
    "status": "queued",
    "estimated_completion": "2024-01-15T10:35:00Z",
    "download_url": null,
    "expires_at": "2024-01-17T10:30:00Z"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 13. Export Job Status

Check the status of an export job.

**Endpoint**: `GET /api/v1/analytics/export/jobs/{job_id}`

**Example Response**:
```json
{
  "success": true,
  "data": {
    "job_id": "export-550e8400-e29b-41d4-a716-446655440001",
    "status": "completed",
    "progress_percentage": 100,
    "created_at": "2024-01-15T10:30:00Z",
    "completed_at": "2024-01-15T10:33:45Z",
    "file_size_mb": 12.4,
    "download_url": "/api/v1/analytics/export/download/export-550e8400-e29b-41d4-a716-446655440001",
    "expires_at": "2024-01-17T10:30:00Z",
    "format": "excel",
    "record_count": 45623
  },
  "timestamp": "2024-01-15T10:34:00Z"
}
```

### 14. Download Export File

Download a completed export file.

**Endpoint**: `GET /api/v1/analytics/export/download/{job_id}`

**Response**: Stream of the export file with appropriate headers.

```http
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="project_analytics_2024-01-15.xlsx"
Content-Length: 13001245
```

---

## 🔧 Configuration & Health Endpoints

### 15. Analytics Configuration

Get current analytics system configuration.

**Endpoint**: `GET /api/v1/analytics/config`

**Example Response**:
```json
{
  "success": true,
  "data": {
    "duckdb_config": {
      "memory_limit": "8GB",
      "worker_threads": 16,
      "extensions_loaded": ["parquet", "httpfs", "json", "s3"]
    },
    "caching_config": {
      "l1_cache_ttl": 300,
      "l2_cache_ttl": 1800,
      "cache_size_mb": 1024
    },
    "performance_config": {
      "query_timeout": 30,
      "max_result_size": 1000000,
      "pagination_size": 1000
    },
    "circuit_breaker_config": {
      "postgresql_threshold": 5,
      "duckdb_threshold": 3,
      "timeout_seconds": 30
    }
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 16. Health Check

Comprehensive health check for analytics system components.

**Endpoint**: `GET /api/v1/analytics/health`

**Example Response**:
```json
{
  "success": true,
  "data": {
    "overall_status": "healthy",
    "components": {
      "duckdb": {
        "status": "healthy",
        "response_time": 0.023,
        "memory_usage": "2.3GB",
        "active_connections": 5
      },
      "postgresql": {
        "status": "healthy", 
        "response_time": 0.012,
        "active_connections": 23,
        "pool_utilization": 0.46
      },
      "redis_cache": {
        "status": "healthy",
        "hit_rate": 87.6,
        "memory_usage": "512MB",
        "connected_clients": 15
      },
      "query_router": {
        "status": "healthy",
        "routing_accuracy": 95.4,
        "avg_routing_time": 0.003
      }
    },
    "circuit_breakers": {
      "duckdb": "closed",
      "postgresql": "closed"
    },
    "performance_metrics": {
      "queries_per_second": 45.6,
      "avg_response_time": 0.156,
      "cache_hit_rate": 87.6,
      "error_rate": 0.34
    }
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "execution_time": 0.045
}
```

---

## 🛠️ SDK & Integration Examples

### Python SDK Usage

```python
import httpx
from datetime import datetime, timedelta

class ChronoScraperAnalytics:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.client = httpx.AsyncClient(
            headers={'Authorization': f'Bearer {token}'}
        )
    
    async def get_project_performance(self, project_id: str, days: int = 30):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        response = await self.client.get(
            f'{self.base_url}/api/v1/analytics/projects/{project_id}/performance',
            params={
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        )
        response.raise_for_status()
        return response.json()

# Usage
analytics = ChronoScraperAnalytics('https://api.chrono-scraper.com', 'your-token')
performance = await analytics.get_project_performance('550e8400-e29b-41d4-a716-446655440000')
```

### JavaScript/TypeScript SDK

```typescript
interface AnalyticsConfig {
  baseUrl: string;
  token: string;
}

class ChronoScraperAnalyticsClient {
  private baseUrl: string;
  private headers: Record<string, string>;

  constructor(config: AnalyticsConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, '');
    this.headers = {
      'Authorization': `Bearer ${config.token}`,
      'Content-Type': 'application/json'
    };
  }

  async getDomainTimeline(
    domain: string, 
    options: {
      granularity?: 'day' | 'hour' | 'week';
      startDate?: Date;
      endDate?: Date;
    } = {}
  ) {
    const params = new URLSearchParams();
    if (options.granularity) params.set('granularity', options.granularity);
    if (options.startDate) params.set('start_date', options.startDate.toISOString());
    if (options.endDate) params.set('end_date', options.endDate.toISOString());

    const response = await fetch(
      `${this.baseUrl}/api/v1/analytics/domains/${domain}/timeline?${params}`,
      { headers: this.headers }
    );

    if (!response.ok) {
      throw new Error(`Analytics API error: ${response.status}`);
    }

    return response.json();
  }

  // WebSocket connection for real-time updates
  connectWebSocket(): WebSocket {
    const ws = new WebSocket(
      `ws://${this.baseUrl.replace(/^https?:\/\//, '')}/api/v1/analytics/ws`,
      [], 
      { headers: { Authorization: this.headers.Authorization } }
    );
    
    return ws;
  }
}

// Usage
const client = new ChronoScraperAnalyticsClient({
  baseUrl: 'https://api.chrono-scraper.com',
  token: 'your-token-here'
});

const timeline = await client.getDomainTimeline('example.com', {
  granularity: 'day',
  startDate: new Date('2024-01-01'),
  endDate: new Date('2024-01-31')
});
```

---

## 🚨 Error Handling & Troubleshooting

### Common Error Codes

| Error Code | Description | Typical Cause | Resolution |
|------------|-------------|---------------|------------|
| `VALIDATION_ERROR` | Request validation failed | Invalid parameters | Check request format and parameter values |
| `QUERY_TIMEOUT` | Analytics query timed out | Complex query or system overload | Reduce date range or add filters |
| `CIRCUIT_BREAKER_OPEN` | Service circuit breaker is open | Database unavailable | Wait for recovery or check service status |
| `RATE_LIMIT_EXCEEDED` | Too many requests | Exceeded rate limits | Implement exponential backoff |
| `INSUFFICIENT_PERMISSIONS` | Access denied | User lacks required permissions | Check user roles and permissions |
| `DATA_NOT_FOUND` | Requested data not found | Invalid project/domain ID | Verify resource exists and access rights |
| `EXPORT_FAILED` | Export generation failed | Large dataset or system resources | Try smaller date range or different format |

### Troubleshooting Guide

#### Slow Query Performance
1. Check database circuit breaker status via `/analytics/health`
2. Verify cache hit rates - should be >80%
3. Consider reducing date ranges for large queries
4. Use appropriate granularity (hour/day vs minute)

#### WebSocket Connection Issues
1. Verify authentication token validity
2. Check firewall/proxy WebSocket support  
3. Monitor connection count limits (5 per user)
4. Implement reconnection logic with exponential backoff

#### Export Failures
1. Verify required dependencies are installed (openpyxl, pyarrow, reportlab)
2. Check available disk space for temporary files
3. Reduce export scope (date range, fields) for large datasets
4. Monitor export job status regularly

---

This comprehensive API reference provides all the information needed to integrate with the Phase 2 DuckDB Analytics system, offering both powerful analytical capabilities and production-ready reliability features.