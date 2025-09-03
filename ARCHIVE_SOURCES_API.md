# Archive Sources API Reference

## Table of Contents
- [Overview](#overview)
- [Project Creation API](#project-creation-api)
- [Archive Source Configuration Schema](#archive-source-configuration-schema)
- [Health Check Endpoints](#health-check-endpoints)
- [Metrics Endpoints](#metrics-endpoints)
- [Response Formats](#response-formats)
- [Error Handling](#error-handling)
- [Code Examples](#code-examples)
- [SDK Usage](#sdk-usage)

## Overview

The Archive Sources API provides comprehensive control over multi-archive functionality in Chrono Scraper. This API allows you to configure archive source preferences, monitor health, and retrieve performance metrics.

### Base URL
```
https://your-instance.com/api/v1
```

### Authentication
All endpoints require Bearer token authentication:
```
Authorization: Bearer <your_token>
```

### Archive Source Types
- `wayback_machine` - Internet Archive's Wayback Machine
- `common_crawl` - Common Crawl dataset
- `hybrid` - Intelligent routing with automatic fallback

## Project Creation API

### Create Project with Archive Source Configuration

Create a new project with specific archive source preferences.

**Endpoint:**
```
POST /api/v1/projects/
```

**Request Headers:**
```
Content-Type: application/json
Authorization: Bearer <token>
```

**Basic Request Body:**
```json
{
  "name": "Historical Analysis Project",
  "description": "Research project focusing on government websites",
  "archive_source": "hybrid",
  "fallback_enabled": true,
  "domains": [
    {
      "domain_name": "example.gov",
      "match_type": "domain",
      "from_date": "2020-01-01",
      "to_date": "2024-01-01"
    }
  ]
}
```

**Advanced Request Body:**
```json
{
  "name": "Performance Optimized Project",
  "description": "High-performance scraping with custom configuration",
  "archive_source": "hybrid",
  "fallback_enabled": true,
  "archive_config": {
    "fallback_strategy": "circuit_breaker",
    "fallback_delay_seconds": 1.5,
    "exponential_backoff": true,
    "max_fallback_delay": 60.0,
    "wayback_machine": {
      "enabled": true,
      "timeout_seconds": 120,
      "max_retries": 3,
      "page_size": 5000,
      "max_pages": 100,
      "include_attachments": true,
      "priority": 1
    },
    "common_crawl": {
      "enabled": true,
      "timeout_seconds": 180,
      "max_retries": 5,
      "page_size": 5000,
      "max_pages": 200,
      "include_attachments": true,
      "priority": 2
    }
  },
  "domains": [
    {
      "domain_name": "example.com",
      "match_type": "domain",
      "from_date": "2023-01-01",
      "to_date": "2024-01-01"
    }
  ]
}
```

**Success Response (201 Created):**
```json
{
  "id": 123,
  "name": "Historical Analysis Project",
  "description": "Research project focusing on government websites",
  "archive_source": "hybrid",
  "fallback_enabled": true,
  "archive_config": {
    "fallback_strategy": "circuit_breaker",
    "fallback_delay_seconds": 1.0,
    "exponential_backoff": true,
    "wayback_machine": {
      "enabled": true,
      "priority": 1
    },
    "common_crawl": {
      "enabled": true,
      "priority": 2
    }
  },
  "status": "no_index",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z",
  "domains": [
    {
      "id": 456,
      "domain_name": "example.gov",
      "match_type": "domain",
      "from_date": "2020-01-01",
      "to_date": "2024-01-01",
      "status": "active"
    }
  ]
}
```

**Error Response (400 Bad Request):**
```json
{
  "error": "validation_error",
  "detail": [
    {
      "field": "archive_source",
      "message": "Invalid archive source. Must be one of: wayback_machine, common_crawl, hybrid",
      "code": "invalid_choice"
    }
  ]
}
```

### Update Project Archive Configuration

Update archive source settings for an existing project.

**Endpoint:**
```
PATCH /api/v1/projects/{project_id}
```

**Request Body:**
```json
{
  "archive_source": "common_crawl",
  "fallback_enabled": false,
  "archive_config": {
    "common_crawl": {
      "timeout_seconds": 90,
      "max_retries": 3,
      "page_size": 10000
    }
  }
}
```

**Success Response (200 OK):**
```json
{
  "id": 123,
  "name": "Historical Analysis Project",
  "archive_source": "common_crawl",
  "fallback_enabled": false,
  "archive_config": {
    "common_crawl": {
      "timeout_seconds": 90,
      "max_retries": 3,
      "page_size": 10000
    }
  },
  "updated_at": "2024-01-15T14:22:33Z"
}
```

## Archive Source Configuration Schema

### ArchiveSource Enum
```json
{
  "type": "string",
  "enum": ["wayback_machine", "common_crawl", "hybrid"],
  "description": "Primary archive source for the project"
}
```

### FallbackStrategy Enum
```json
{
  "type": "string", 
  "enum": ["immediate", "retry_then_fallback", "circuit_breaker"],
  "description": "Strategy for handling fallback between sources"
}
```

### ArchiveConfig Schema

**Full Configuration Schema:**
```json
{
  "type": "object",
  "properties": {
    "fallback_strategy": {
      "$ref": "#/definitions/FallbackStrategy"
    },
    "fallback_delay_seconds": {
      "type": "number",
      "minimum": 0,
      "maximum": 300,
      "default": 1.0,
      "description": "Delay in seconds before attempting fallback"
    },
    "exponential_backoff": {
      "type": "boolean",
      "default": true,
      "description": "Use exponential backoff for multiple fallback attempts"
    },
    "max_fallback_delay": {
      "type": "number",
      "minimum": 1,
      "maximum": 3600,
      "default": 30.0,
      "description": "Maximum delay for exponential backoff"
    },
    "wayback_machine": {
      "$ref": "#/definitions/SourceConfig"
    },
    "common_crawl": {
      "$ref": "#/definitions/SourceConfig"
    }
  },
  "additionalProperties": false
}
```

**SourceConfig Schema:**
```json
{
  "type": "object",
  "properties": {
    "enabled": {
      "type": "boolean",
      "default": true,
      "description": "Whether this source is enabled"
    },
    "timeout_seconds": {
      "type": "integer",
      "minimum": 10,
      "maximum": 600,
      "description": "Request timeout in seconds"
    },
    "max_retries": {
      "type": "integer",
      "minimum": 0,
      "maximum": 10,
      "description": "Maximum number of retry attempts"
    },
    "page_size": {
      "type": "integer",
      "minimum": 100,
      "maximum": 50000,
      "description": "Number of CDX records per page"
    },
    "max_pages": {
      "type": "integer",
      "minimum": 0,
      "description": "Maximum pages to fetch (0 = unlimited)"
    },
    "include_attachments": {
      "type": "boolean",
      "default": true,
      "description": "Include PDF and document attachments"
    },
    "priority": {
      "type": "integer",
      "minimum": 1,
      "maximum": 100,
      "description": "Source priority (lower numbers = higher priority)"
    }
  },
  "additionalProperties": false
}
```

### Configuration Validation Rules

1. **Archive Source Validation:**
   - Must be one of: `wayback_machine`, `common_crawl`, `hybrid`
   - `hybrid` requires `fallback_enabled` to be `true`

2. **Timeout Validation:**
   - Wayback Machine: 10-600 seconds (recommended: 120)
   - Common Crawl: 10-600 seconds (recommended: 180)

3. **Page Size Validation:**
   - Minimum: 100 records
   - Maximum: 50,000 records
   - Recommended: 5,000 records

4. **Priority Validation:**
   - Lower numbers indicate higher priority
   - Default: Wayback Machine (1), Common Crawl (2)

## Health Check Endpoints

### General Health Check

**Endpoint:**
```
GET /api/v1/health
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "services": {
    "database": "healthy",
    "redis": "healthy",
    "meilisearch": "healthy",
    "archive_sources": "healthy"
  },
  "version": "2.0.0"
}
```

### Archive Sources Health Check

**Endpoint:**
```
GET /api/v1/health/archive-sources
```

**Response (200 OK - Healthy):**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "sources": {
    "wayback_machine": {
      "healthy": true,
      "circuit_breaker_state": "closed",
      "success_rate": 95.2,
      "last_success": "2024-01-15T10:29:45Z"
    },
    "common_crawl": {
      "healthy": true,
      "circuit_breaker_state": "closed",
      "success_rate": 98.7,
      "last_success": "2024-01-15T10:29:30Z"
    }
  },
  "details": {
    "wayback_machine": {
      "available": true,
      "circuit_breaker": "closed",
      "last_success": "2024-01-15T10:29:45Z"
    },
    "common_crawl": {
      "available": true,
      "circuit_breaker": "closed", 
      "last_success": "2024-01-15T10:29:30Z"
    }
  }
}
```

**Response (200 OK - Degraded):**
```json
{
  "status": "degraded",
  "timestamp": "2024-01-15T10:30:00Z",
  "sources": {
    "wayback_machine": {
      "healthy": false,
      "circuit_breaker_state": "open",
      "success_rate": 45.3,
      "last_success": "2024-01-15T09:15:22Z"
    },
    "common_crawl": {
      "healthy": true,
      "circuit_breaker_state": "closed",
      "success_rate": 97.1,
      "last_success": "2024-01-15T10:29:55Z"
    }
  }
}
```

**Response (503 Service Unavailable - Unhealthy):**
```json
{
  "status": "unhealthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "sources": {
    "wayback_machine": {
      "healthy": false,
      "circuit_breaker_state": "open",
      "success_rate": 12.5,
      "last_success": "2024-01-15T08:45:10Z"
    },
    "common_crawl": {
      "healthy": false,
      "circuit_breaker_state": "open",
      "success_rate": 8.3,
      "last_success": "2024-01-15T08:30:33Z"
    }
  },
  "error": "All archive sources are unhealthy"
}
```

## Metrics Endpoints

### Performance Metrics

**Endpoint:**
```
GET /api/v1/metrics/archive-sources
```

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200 OK):**
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "sources": {
    "wayback_machine": {
      "total_queries": 1247,
      "successful_queries": 1186,
      "failed_queries": 61,
      "success_rate": 95.1,
      "avg_response_time": 18.42,
      "total_records": 2847392,
      "is_healthy": true,
      "last_success_time": "2024-01-15T10:29:45Z",
      "last_failure_time": "2024-01-15T09:33:12Z",
      "error_counts": {
        "wayback_522_timeout": 45,
        "wayback_connection_error": 12,
        "wayback_timeout": 4
      }
    },
    "common_crawl": {
      "total_queries": 823,
      "successful_queries": 812,
      "failed_queries": 11,
      "success_rate": 98.7,
      "avg_response_time": 12.33,
      "total_records": 1934521,
      "is_healthy": true,
      "last_success_time": "2024-01-15T10:29:30Z",
      "last_failure_time": "2024-01-15T07:22:18Z",
      "error_counts": {
        "common_crawl_rate_limit": 7,
        "common_crawl_timeout": 3,
        "common_crawl_connection_error": 1
      }
    }
  },
  "overall": {
    "total_queries": 2070,
    "avg_success_rate": 96.9,
    "query_history_size": 1000
  },
  "circuit_breakers": {
    "wayback_machine": {
      "state": "closed",
      "failure_count": 0,
      "success_count": 5,
      "last_failure_time": null,
      "next_attempt_time": null
    },
    "common_crawl": {
      "state": "closed", 
      "failure_count": 0,
      "success_count": 8,
      "last_failure_time": null,
      "next_attempt_time": null
    }
  },
  "config": {
    "fallback_strategy": "circuit_breaker",
    "fallback_delay_seconds": 1.0,
    "exponential_backoff": true
  }
}
```

### Reset Metrics

**Endpoint:**
```
POST /api/v1/metrics/archive-sources/reset
```

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200 OK):**
```json
{
  "message": "Archive source metrics have been reset",
  "timestamp": "2024-01-15T10:35:22Z",
  "reset_stats": {
    "queries_cleared": 2070,
    "history_cleared": 1000,
    "sources_reset": ["wayback_machine", "common_crawl"]
  }
}
```

## Response Formats

### Scraping Statistics Response

When scraping completes, statistics include archive source information:

```json
{
  "scrape_session": {
    "id": 789,
    "status": "completed",
    "total_pages": 1234,
    "successful_pages": 1189,
    "failed_pages": 45,
    "duration_seconds": 3600.5
  },
  "archive_source_stats": {
    "primary_source": "wayback_machine",
    "successful_source": "wayback_machine", 
    "fallback_used": false,
    "total_duration": 2847.3,
    "attempts": [
      {
        "source": "wayback_machine",
        "success": true,
        "duration": 2847.3,
        "records": 1234,
        "pages_fetched": 3
      }
    ]
  },
  "cdx_stats": {
    "total_records": 1234,
    "final_count": 1189,
    "filtered_out": 45,
    "fetched_pages": 3,
    "resume_key": null
  }
}
```

### Fallback Event Response

When fallback occurs during scraping:

```json
{
  "archive_source_stats": {
    "primary_source": "wayback_machine",
    "successful_source": "common_crawl",
    "fallback_used": true,
    "total_duration": 3245.7,
    "attempts": [
      {
        "source": "wayback_machine",
        "success": false,
        "error_type": "wayback_522_timeout",
        "error": "522 Connection timeout",
        "duration": 122.4
      },
      {
        "source": "common_crawl", 
        "success": true,
        "duration": 3123.3,
        "records": 1156,
        "pages_fetched": 2
      }
    ]
  }
}
```

## Error Handling

### Error Response Format

All API errors follow a consistent format:

```json
{
  "error": "error_code",
  "message": "Human-readable error description",
  "detail": "Additional error details or validation errors",
  "timestamp": "2024-01-15T10:30:00Z",
  "request_id": "req-123e4567-e89b-12d3-a456-426614174000"
}
```

### Archive Source Specific Errors

#### Invalid Archive Source
```json
{
  "error": "invalid_archive_source",
  "message": "Invalid archive source specified",
  "detail": {
    "field": "archive_source",
    "value": "invalid_source",
    "valid_options": ["wayback_machine", "common_crawl", "hybrid"]
  }
}
```

#### Configuration Validation Error
```json
{
  "error": "archive_config_validation_error",
  "message": "Archive configuration validation failed",
  "detail": [
    {
      "field": "archive_config.wayback_machine.timeout_seconds",
      "message": "Value must be between 10 and 600",
      "code": "value_range_error"
    },
    {
      "field": "archive_config.fallback_delay_seconds",
      "message": "Must be a positive number",
      "code": "positive_number_required"
    }
  ]
}
```

#### Archive Sources Unavailable
```json
{
  "error": "archive_sources_unavailable",
  "message": "All configured archive sources are currently unavailable",
  "detail": {
    "sources": {
      "wayback_machine": {
        "status": "circuit_breaker_open",
        "last_error": "522 Connection timeout",
        "next_retry": "2024-01-15T10:35:00Z"
      },
      "common_crawl": {
        "status": "circuit_breaker_open", 
        "last_error": "Rate limit exceeded",
        "next_retry": "2024-01-15T10:33:00Z"
      }
    }
  }
}
```

## Code Examples

### cURL Examples

#### Create Project with Archive Configuration
```bash
curl -X POST "https://api.chrono-scraper.com/api/v1/projects/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Project",
    "archive_source": "hybrid",
    "fallback_enabled": true,
    "domains": [
      {
        "domain_name": "example.com",
        "match_type": "domain",
        "from_date": "2024-01-01",
        "to_date": "2024-01-31"
      }
    ]
  }'
```

#### Check Archive Sources Health
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/health/archive-sources" \
  -H "Authorization: Bearer $TOKEN"
```

#### Get Performance Metrics
```bash
curl -X GET "https://api.chrono-scraper.com/api/v1/metrics/archive-sources" \
  -H "Authorization: Bearer $TOKEN"
```

### Python Examples

#### Using requests library
```python
import requests
import json

# Configuration
API_BASE = "https://api.chrono-scraper.com/api/v1"
TOKEN = "your_bearer_token_here"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Create project with hybrid archive mode
project_data = {
    "name": "Python API Example",
    "description": "Test project using Python API",
    "archive_source": "hybrid",
    "fallback_enabled": True,
    "archive_config": {
        "fallback_strategy": "circuit_breaker",
        "fallback_delay_seconds": 1.5,
        "wayback_machine": {
            "timeout_seconds": 120,
            "priority": 1
        },
        "common_crawl": {
            "timeout_seconds": 180,
            "priority": 2
        }
    },
    "domains": [
        {
            "domain_name": "example.com",
            "match_type": "domain", 
            "from_date": "2024-01-01",
            "to_date": "2024-01-31"
        }
    ]
}

# Create project
response = requests.post(
    f"{API_BASE}/projects/",
    headers=headers,
    json=project_data
)

if response.status_code == 201:
    project = response.json()
    print(f"Created project: {project['id']}")
    
    # Check archive sources health
    health_response = requests.get(
        f"{API_BASE}/health/archive-sources",
        headers=headers
    )
    
    if health_response.status_code == 200:
        health = health_response.json()
        print(f"Archive health: {health['status']}")
        
        for source, data in health['sources'].items():
            print(f"  {source}: {data['circuit_breaker_state']} "
                  f"({data['success_rate']:.1f}% success)")
    
    # Get performance metrics
    metrics_response = requests.get(
        f"{API_BASE}/metrics/archive-sources",
        headers=headers
    )
    
    if metrics_response.status_code == 200:
        metrics = metrics_response.json()
        print(f"\nPerformance metrics:")
        
        for source, data in metrics['sources'].items():
            print(f"  {source}:")
            print(f"    Queries: {data['total_queries']}")
            print(f"    Success rate: {data['success_rate']:.1f}%")
            print(f"    Avg response: {data['avg_response_time']:.1f}s")

else:
    print(f"Error creating project: {response.status_code}")
    print(response.json())
```

#### Using aiohttp for async operations
```python
import asyncio
import aiohttp
import json

async def create_project_async():
    API_BASE = "https://api.chrono-scraper.com/api/v1"
    TOKEN = "your_bearer_token_here"
    
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    
    project_data = {
        "name": "Async API Example",
        "archive_source": "hybrid",
        "fallback_enabled": True,
        "domains": [
            {
                "domain_name": "example.com",
                "match_type": "domain",
                "from_date": "2024-01-01",
                "to_date": "2024-01-31"
            }
        ]
    }
    
    async with aiohttp.ClientSession() as session:
        # Create project
        async with session.post(
            f"{API_BASE}/projects/",
            headers=headers,
            json=project_data
        ) as response:
            
            if response.status == 201:
                project = await response.json()
                print(f"Created project: {project['id']}")
                
                # Monitor health and metrics concurrently
                health_task = monitor_health(session, headers, API_BASE)
                metrics_task = get_metrics(session, headers, API_BASE)
                
                health, metrics = await asyncio.gather(health_task, metrics_task)
                
                print(f"Health: {health['status']}")
                print(f"Total queries: {metrics['overall']['total_queries']}")
                
            else:
                error = await response.json()
                print(f"Error: {error}")

async def monitor_health(session, headers, api_base):
    async with session.get(
        f"{api_base}/health/archive-sources",
        headers=headers
    ) as response:
        return await response.json()

async def get_metrics(session, headers, api_base):
    async with session.get(
        f"{api_base}/metrics/archive-sources", 
        headers=headers
    ) as response:
        return await response.json()

# Run async example
asyncio.run(create_project_async())
```

### JavaScript Examples

#### Using fetch API
```javascript
const API_BASE = 'https://api.chrono-scraper.com/api/v1';
const TOKEN = 'your_bearer_token_here';

const headers = {
  'Authorization': `Bearer ${TOKEN}`,
  'Content-Type': 'application/json'
};

// Create project with archive source configuration
async function createProject() {
  const projectData = {
    name: 'JavaScript API Example',
    description: 'Test project using JavaScript API',
    archive_source: 'hybrid',
    fallback_enabled: true,
    archive_config: {
      fallback_strategy: 'circuit_breaker',
      fallback_delay_seconds: 1.0,
      wayback_machine: {
        timeout_seconds: 120,
        max_retries: 3,
        priority: 1
      },
      common_crawl: {
        timeout_seconds: 180,
        max_retries: 5,
        priority: 2
      }
    },
    domains: [
      {
        domain_name: 'example.com',
        match_type: 'domain',
        from_date: '2024-01-01',
        to_date: '2024-01-31'
      }
    ]
  };

  try {
    const response = await fetch(`${API_BASE}/projects/`, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify(projectData)
    });

    if (response.ok) {
      const project = await response.json();
      console.log('Created project:', project.id);
      
      // Monitor archive sources
      await monitorArchiveSources();
      
      return project;
    } else {
      const error = await response.json();
      console.error('Error creating project:', error);
    }
  } catch (error) {
    console.error('Request failed:', error);
  }
}

// Monitor archive source health and metrics
async function monitorArchiveSources() {
  try {
    // Get health status
    const healthResponse = await fetch(`${API_BASE}/health/archive-sources`, {
      headers: headers
    });
    
    if (healthResponse.ok) {
      const health = await healthResponse.json();
      console.log('Archive health:', health.status);
      
      Object.entries(health.sources).forEach(([source, data]) => {
        console.log(`  ${source}: ${data.circuit_breaker_state} (${data.success_rate}% success)`);
      });
    }
    
    // Get performance metrics
    const metricsResponse = await fetch(`${API_BASE}/metrics/archive-sources`, {
      headers: headers
    });
    
    if (metricsResponse.ok) {
      const metrics = await metricsResponse.json();
      console.log('\nPerformance metrics:');
      
      Object.entries(metrics.sources).forEach(([source, data]) => {
        console.log(`  ${source}:`);
        console.log(`    Queries: ${data.total_queries}`);
        console.log(`    Success rate: ${data.success_rate}%`);
        console.log(`    Avg response: ${data.avg_response_time}s`);
      });
    }
    
  } catch (error) {
    console.error('Monitoring failed:', error);
  }
}

// Run the example
createProject();
```

## SDK Usage

### Official Python SDK

If using the official Chrono Scraper Python SDK:

```python
from chrono_scraper_client import ChronoScraperClient
from chrono_scraper_client.models import (
    ProjectCreate, 
    ArchiveSource, 
    ArchiveConfig,
    SourceConfig
)

# Initialize client
client = ChronoScraperClient(
    base_url="https://api.chrono-scraper.com/api/v1",
    token="your_bearer_token_here"
)

# Create archive configuration
archive_config = ArchiveConfig(
    fallback_strategy="circuit_breaker",
    fallback_delay_seconds=1.5,
    wayback_machine=SourceConfig(
        timeout_seconds=120,
        max_retries=3,
        priority=1
    ),
    common_crawl=SourceConfig(
        timeout_seconds=180,
        max_retries=5,
        priority=2
    )
)

# Create project
project_data = ProjectCreate(
    name="SDK Example Project",
    description="Using official Python SDK",
    archive_source=ArchiveSource.HYBRID,
    fallback_enabled=True,
    archive_config=archive_config,
    domains=[
        {
            "domain_name": "example.com",
            "match_type": "domain",
            "from_date": "2024-01-01",
            "to_date": "2024-01-31"
        }
    ]
)

# Create the project
project = client.projects.create(project_data)
print(f"Created project: {project.id}")

# Monitor archive sources
health = client.health.get_archive_sources()
print(f"Archive health: {health.status}")

metrics = client.metrics.get_archive_sources()
print(f"Total queries: {metrics.overall.total_queries}")

# Update project archive configuration
updated_config = ArchiveConfig(
    fallback_strategy="immediate",
    fallback_delay_seconds=0.5
)

updated_project = client.projects.update(
    project.id, 
    archive_config=updated_config
)
```

### TypeScript/Node.js SDK

```typescript
import { ChronoScraperClient, ArchiveSource, FallbackStrategy } from '@chrono-scraper/client';

// Initialize client
const client = new ChronoScraperClient({
  baseUrl: 'https://api.chrono-scraper.com/api/v1',
  token: 'your_bearer_token_here'
});

// Create project with archive configuration
const project = await client.projects.create({
  name: 'TypeScript SDK Example',
  description: 'Using TypeScript SDK',
  archiveSource: ArchiveSource.HYBRID,
  fallbackEnabled: true,
  archiveConfig: {
    fallbackStrategy: FallbackStrategy.CIRCUIT_BREAKER,
    fallbackDelaySeconds: 1.0,
    waybackMachine: {
      timeoutSeconds: 120,
      maxRetries: 3,
      priority: 1
    },
    commonCrawl: {
      timeoutSeconds: 180,
      maxRetries: 5,
      priority: 2
    }
  },
  domains: [
    {
      domainName: 'example.com',
      matchType: 'domain',
      fromDate: '2024-01-01',
      toDate: '2024-01-31'
    }
  ]
});

console.log('Created project:', project.id);

// Monitor health
const health = await client.health.getArchiveSources();
console.log('Archive health:', health.status);

// Get metrics
const metrics = await client.metrics.getArchiveSources();
console.log('Performance metrics:', {
  totalQueries: metrics.overall.totalQueries,
  avgSuccessRate: metrics.overall.avgSuccessRate
});

// Update configuration
await client.projects.update(project.id, {
  archiveConfig: {
    fallbackStrategy: FallbackStrategy.IMMEDIATE
  }
});
```

This comprehensive API reference provides complete documentation for integrating with the Archive Sources feature in Chrono Scraper, including detailed schemas, examples, and best practices for different programming languages and use cases.