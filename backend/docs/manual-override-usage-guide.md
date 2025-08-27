# Manual Override API Usage Guide

This guide provides comprehensive examples and usage patterns for the Manual Override API endpoints, including curl examples, authentication setup, and common workflows.

## Table of Contents

1. [Authentication Setup](#authentication-setup)
2. [Manual Processing Examples](#manual-processing-examples)
3. [Manual Skip Examples](#manual-skip-examples)
4. [Enhanced Filtering Examples](#enhanced-filtering-examples)
5. [Bulk Operations Examples](#bulk-operations-examples)
6. [Error Handling](#error-handling)
7. [Best Practices](#best-practices)
8. [Rate Limiting](#rate-limiting)
9. [Monitoring and Tracking](#monitoring-and-tracking)

## Authentication Setup

All manual override endpoints require JWT Bearer authentication. First, obtain a token:

```bash
# Login to get JWT token
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your-email@example.com",
    "password": "your-password"
  }'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

Use the `access_token` in all subsequent requests:
```bash
export JWT_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

## Manual Processing Examples

### Basic Manual Process

Force processing of a page that was filtered out:

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/456/manual-process" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "priority_level": 8,
    "processing_notes": "Contains important historical data despite being flagged as low quality",
    "force_reprocess": false
  }'
```

Response:
```json
{
  "message": "Page successfully queued for manual processing",
  "scrape_page_id": 456,
  "original_status": "filtered_low_quality",
  "new_status": "pending",
  "priority_level": 8,
  "estimated_processing_time": "2-5 minutes",
  "task_id": "task_abc123",
  "is_manually_overridden": true
}
```

### Manual Process with High Priority

For urgent content that needs immediate processing:

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/789/manual-process" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "priority_level": 10,
    "processing_notes": "Urgent: Contains time-sensitive information needed for investigation",
    "force_reprocess": true
  }'
```

### Manual Process Without Body

Minimal request using default priority:

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/456/manual-process" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

## Manual Skip Examples

### Basic Manual Skip

Skip a page that would normally be processed:

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/789/manual-skip" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "skip_reason": "sensitive_content",
    "skip_notes": "Contains personal information that should not be processed",
    "permanent_skip": true
  }'
```

Response:
```json
{
  "message": "Page successfully marked as manually skipped",
  "scrape_page_id": 789,
  "original_status": "pending",
  "new_status": "skipped",
  "skip_reason": "sensitive_content",
  "permanent_skip": true,
  "is_manually_overridden": true
}
```

### Skip with Different Reasons

```bash
# Skip due to technical issues
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/101/manual-skip" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "skip_reason": "technical_issues",
    "skip_notes": "Page causes extraction service to timeout repeatedly",
    "permanent_skip": false
  }'

# Skip low-value content
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/102/manual-skip" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "skip_reason": "low_value",
    "skip_notes": "Advertisement page with no meaningful content",
    "permanent_skip": true
  }'

# Skip duplicate content
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/103/manual-skip" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "skip_reason": "duplicate_manual",
    "skip_notes": "Manual review identified this as duplicate of page 87",
    "permanent_skip": true
  }'
```

## Enhanced Filtering Examples

### Get Filtered Pages Awaiting Manual Review

Find pages that were filtered but can be manually processed:

```bash
curl -X GET "http://localhost:8000/api/v1/projects/123/scrape-pages?status_filter=filtered_low_quality&can_be_manually_processed=true&limit=50" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

### Filter by Manual Override Status

Get pages that have been manually overridden:

```bash
curl -X GET "http://localhost:8000/api/v1/projects/123/scrape-pages?manual_override_status=overridden&sort_by=priority_score&sort_order=desc" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

### Filter by Multiple Criteria

Complex filtering for review workflow:

```bash
curl -X GET "http://localhost:8000/api/v1/projects/123/scrape-pages?filter_category=low_quality&priority_level=8&status_filter=filtered_low_quality&limit=25&skip=0" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

Response format:
```json
{
  "scrape_pages": [
    {
      "id": 456,
      "domain_id": 789,
      "domain_name": "example.com",
      "original_url": "https://example.com/important-doc",
      "status": "filtered_low_quality",
      "filter_reason": "Content length too small",
      "filter_category": "low_quality",
      "priority_score": 8,
      "can_be_manually_processed": true,
      "is_manually_overridden": false,
      "created_at": "2023-01-01T12:00:00Z"
    }
  ],
  "pagination": {
    "total": 150,
    "skip": 0,
    "limit": 25,
    "has_more": true
  },
  "filters_applied": {
    "filter_category": "low_quality",
    "priority_level": 8,
    "total_filtered": 150
  }
}
```

## Bulk Operations Examples

### Bulk Manual Process

Process multiple filtered pages at once:

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/bulk-actions" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "manual_process",
    "page_ids": [101, 102, 103, 104, 105],
    "parameters": {
      "priority_level": 8,
      "notes": "High-priority pages identified for manual processing"
    }
  }'
```

Response:
```json
{
  "message": "Bulk action completed successfully",
  "action": "manual_process",
  "total_requested": 5,
  "successful_updates": 5,
  "failed_updates": 0,
  "results": [
    {
      "scrape_page_id": 101,
      "success": true,
      "old_status": "filtered_low_quality",
      "new_status": "pending",
      "message": "Successfully queued for manual processing"
    },
    {
      "scrape_page_id": 102,
      "success": true,
      "old_status": "filtered_duplicate",
      "new_status": "pending",
      "message": "Successfully queued for manual processing"
    }
  ],
  "processing_time_ms": 1250
}
```

### Bulk Manual Skip

Skip multiple pages simultaneously:

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/bulk-actions" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "manual_skip",
    "page_ids": [201, 202, 203],
    "parameters": {
      "skip_reason": "sensitive_content",
      "notes": "Batch identified as containing personal information",
      "permanent_skip": true
    }
  }'
```

### Bulk Priority Update

Update priority for multiple pages:

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/bulk-actions" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "update_priority",
    "page_ids": [301, 302, 303, 304],
    "parameters": {
      "priority_level": 9,
      "notes": "Urgent processing required for investigation"
    }
  }'
```

### Bulk Reset Status

Reset pages to a specific status:

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/bulk-actions" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "reset_status",
    "page_ids": [401, 402, 403],
    "parameters": {
      "reset_to_status": "awaiting_manual_review",
      "notes": "Resetting for manual review after system update"
    }
  }'
```

## Error Handling

### Common Error Responses

#### Page Not Found
```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/999999/manual-process" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

Response:
```json
{
  "message": "Scrape page not found",
  "error_code": "SCRAPE_PAGE_NOT_FOUND"
}
```

#### Invalid Status Filter
```bash
curl -X GET "http://localhost:8000/api/v1/projects/123/scrape-pages?status_filter=invalid_status" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

Response:
```json
{
  "message": "Invalid status filter value",
  "error_code": "INVALID_PARAMETER",
  "details": {
    "parameter": "status_filter",
    "valid_values": ["pending", "in_progress", "completed", "failed", "skipped", "filtered_duplicate", "filtered_list_page", "filtered_low_quality", "filtered_size", "filtered_type", "filtered_custom", "awaiting_manual_review", "manually_approved"]
  }
}
```

#### Validation Error
```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/bulk-actions" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "manual_process",
    "page_ids": []
  }'
```

Response:
```json
{
  "message": "Request validation failed",
  "errors": [
    {
      "field": "page_ids",
      "message": "At least one page ID is required",
      "value": []
    }
  ]
}
```

#### Rate Limit Exceeded
```json
{
  "message": "Rate limit exceeded. Try again in 60 seconds.",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "details": {
    "limit": 10,
    "window": 60,
    "retry_after": 45
  }
}
```

## Best Practices

### 1. Check Page Eligibility First

Before attempting manual processing, verify the page can be processed:

```bash
# Get page details to check can_be_manually_processed flag
curl -X GET "http://localhost:8000/api/v1/projects/123/scrape-pages?page_ids=456&limit=1" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

### 2. Use Appropriate Priority Levels

- **Priority 1-3**: Low priority, background processing
- **Priority 4-6**: Normal priority (default: 5)
- **Priority 7-8**: High priority, expedited processing
- **Priority 9-10**: Urgent priority, immediate processing

### 3. Provide Meaningful Notes

Always include processing or skip notes for audit trails:

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/456/manual-process" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "priority_level": 8,
    "processing_notes": "Manual review identified important historical context that automated filter missed due to OCR quality issues in original document"
  }'
```

### 4. Batch Operations Efficiently

Group similar operations to minimize API calls:

```bash
# Good: Process all low-quality filtered pages in one batch
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/bulk-actions" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "manual_process",
    "page_ids": [101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
    "parameters": {
      "priority_level": 7,
      "notes": "Batch processing of filtered pages after manual review identified them as valuable content"
    }
  }'
```

### 5. Monitor Bulk Operation Results

Always check the results array for partial failures:

```json
{
  "successful_updates": 8,
  "failed_updates": 2,
  "results": [
    {
      "scrape_page_id": 105,
      "success": false,
      "error": "Page is already in progress",
      "message": "Cannot override page that is currently being processed"
    }
  ]
}
```

## Rate Limiting

### Standard Endpoints
- **Rate Limit**: 100 requests per minute
- **Headers**: Check `X-RateLimit-*` headers in responses

### Bulk Operations
- **Rate Limit**: 10 requests per minute
- **Batch Size**: Maximum 500 page IDs per request

### Handling Rate Limits

```bash
# Check rate limit headers
curl -I -X GET "http://localhost:8000/api/v1/projects/123/scrape-pages" \
  -H "Authorization: Bearer $JWT_TOKEN"

# Response headers:
# X-RateLimit-Limit: 100
# X-RateLimit-Remaining: 95
# X-RateLimit-Reset: 1672531200
```

## Monitoring and Tracking

### Track Processing Progress

Use the task_id returned from manual processing to monitor progress:

```bash
# Get task status (if task monitoring endpoint exists)
curl -X GET "http://localhost:8000/api/v1/tasks/task_abc123/status" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

### Monitor Project Statistics

Check overall project progress:

```bash
curl -X GET "http://localhost:8000/api/v1/projects/123/stats" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

### Filter Effectiveness Analysis

Analyze filtering patterns to improve automated rules:

```bash
# Get count of each filter category
curl -X GET "http://localhost:8000/api/v1/projects/123/scrape-pages?filter_category=low_quality&limit=0" \
  -H "Authorization: Bearer $JWT_TOKEN"

curl -X GET "http://localhost:8000/api/v1/projects/123/scrape-pages?filter_category=duplicate&limit=0" \
  -H "Authorization: Bearer $JWT_TOKEN"

curl -X GET "http://localhost:8000/api/v1/projects/123/scrape-pages?filter_category=list_page&limit=0" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

## Advanced Workflows

### Workflow 1: Review and Process Low-Quality Pages

```bash
#!/bin/bash
PROJECT_ID=123
JWT_TOKEN="your-jwt-token-here"

echo "=== Finding low-quality filtered pages ==="
PAGES=$(curl -s -X GET "http://localhost:8000/api/v1/projects/${PROJECT_ID}/scrape-pages?status_filter=filtered_low_quality&can_be_manually_processed=true&limit=100" \
  -H "Authorization: Bearer $JWT_TOKEN" | jq -r '.scrape_pages[] | select(.content_length > 1000) | .id')

echo "Found pages: $PAGES"

# Convert to array for bulk processing
PAGE_IDS=$(echo $PAGES | tr ' ' ',' | sed 's/,$//')

if [ ! -z "$PAGE_IDS" ]; then
    echo "=== Processing pages in bulk ==="
    curl -X POST "http://localhost:8000/api/v1/projects/${PROJECT_ID}/scrape-pages/bulk-actions" \
      -H "Authorization: Bearer $JWT_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{
        \"action\": \"manual_process\",
        \"page_ids\": [$PAGE_IDS],
        \"parameters\": {
          \"priority_level\": 7,
          \"notes\": \"Bulk processing of low-quality pages with sufficient content length\"
        }
      }"
fi
```

### Workflow 2: Cleanup and Skip Problematic Pages

```bash
#!/bin/bash
PROJECT_ID=123
JWT_TOKEN="your-jwt-token-here"

echo "=== Finding failed pages with high retry count ==="
FAILED_PAGES=$(curl -s -X GET "http://localhost:8000/api/v1/projects/${PROJECT_ID}/scrape-pages?status_filter=failed&limit=1000" \
  -H "Authorization: Bearer $JWT_TOKEN" | jq -r '.scrape_pages[] | select(.retry_count >= 3) | .id')

if [ ! -z "$FAILED_PAGES" ]; then
    PAGE_IDS=$(echo $FAILED_PAGES | tr ' ' ',' | sed 's/,$//')
    
    echo "=== Skipping problematic pages ==="
    curl -X POST "http://localhost:8000/api/v1/projects/${PROJECT_ID}/scrape-pages/bulk-actions" \
      -H "Authorization: Bearer $JWT_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{
        \"action\": \"manual_skip\",
        \"page_ids\": [$PAGE_IDS],
        \"parameters\": {
          \"skip_reason\": \"technical_issues\",
          \"notes\": \"Pages with 3+ failed attempts - likely technical issues\",
          \"permanent_skip\": true
        }
      }"
fi
```

This completes the comprehensive usage guide for the Manual Override API endpoints. The guide includes practical examples, error handling, and advanced workflows that demonstrate how to effectively use these endpoints in real-world scenarios.