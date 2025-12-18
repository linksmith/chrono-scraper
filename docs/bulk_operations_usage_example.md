# Bulk Operations API Usage Examples

This document provides examples of how to use the new bulk operations endpoints for the Phase 3 Enhanced Filtering System API.

## Endpoints

- `POST /api/v1/projects/{project_id}/scrape-pages/manual-processing/bulk/preview` - Preview bulk operation
- `POST /api/v1/projects/{project_id}/scrape-pages/manual-processing/bulk` - Execute bulk operation

## 1. Preview Bulk Operation

Before executing a bulk operation, use the preview endpoint to see what would be affected:

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/manual-processing/bulk/preview" \
-H "Authorization: Bearer YOUR_JWT_TOKEN" \
-H "Content-Type: application/json" \
-d '{
  "filters": {
    "filter_by": "filtered",
    "priority_min": 3,
    "priority_max": 7,
    "limit": 1000
  },
  "action": "mark_for_processing",
  "max_pages": 500,
  "reason": "Re-evaluating filtered pages with medium priority",
  "dry_run": true
}'
```

**Response:**
```json
{
  "action": "mark_for_processing",
  "total_pages_affected": 234,
  "pages_by_status": {
    "filtered_list_page": 156,
    "filtered_low_priority": 78
  },
  "pages_by_domain": {
    "1": 123,
    "2": 111
  },
  "estimated_processing_time_minutes": 4.68,
  "sample_pages": [...],
  "warnings": [],
  "blocked_page_ids": [],
  "blocked_reasons": {}
}
```

## 2. Execute Bulk Operations

### Mark Filtered Pages for Manual Processing

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/manual-processing/bulk" \
-H "Authorization: Bearer YOUR_JWT_TOKEN" \
-H "Content-Type: application/json" \
-d '{
  "filters": {
    "filter_by": "filtered",
    "priority_min": 5,
    "created_after": "2024-01-01T00:00:00Z"
  },
  "action": "mark_for_processing",
  "max_pages": 100,
  "reason": "High-priority pages need manual review",
  "priority_override": 8,
  "batch_size": 50
}'
```

### Approve All Manually Reviewed Pages

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/manual-processing/bulk" \
-H "Authorization: Bearer YOUR_JWT_TOKEN" \
-H "Content-Type: application/json" \
-d '{
  "filters": {
    "filter_by": "manual_review"
  },
  "action": "approve_all",
  "max_pages": 1000,
  "reason": "Batch approval after manual review",
  "batch_size": 100
}'
```

### Retry Failed Pages

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/manual-processing/bulk" \
-H "Authorization: Bearer YOUR_JWT_TOKEN" \
-H "Content-Type: application/json" \
-d '{
  "filters": {
    "filter_by": "failed",
    "created_after": "2024-01-15T00:00:00Z"
  },
  "action": "retry",
  "max_pages": 200,
  "reason": "Retry recent failures after system fix",
  "force_reprocess": true
}'
```

### Skip Low Priority Pages

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/manual-processing/bulk" \
-H "Authorization: Bearer YOUR_JWT_TOKEN" \
-H "Content-Type: application/json" \
-d '{
  "filters": {
    "priority_max": 3,
    "filter_by": "pending"
  },
  "action": "skip_all",
  "max_pages": 500,
  "reason": "Skipping low-priority pages to focus on important content"
}'
```

### Update Priority Scores

```bash
curl -X POST "http://localhost:8000/api/v1/projects/123/scrape-pages/manual-processing/bulk" \
-H "Authorization: Bearer YOUR_JWT_TOKEN" \
-H "Content-Type: application/json" \
-d '{
  "filters": {
    "domain_id": 5,
    "is_pdf": true
  },
  "action": "update_priority",
  "max_pages": 1000,
  "reason": "Increasing priority for PDF documents from important domain",
  "priority_override": 9
}'
```

## 3. Response Format

All bulk operations return a `BulkOperationResult`:

```json
{
  "operation_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "mark_for_processing",
  "status": "completed",
  "total_requested": 234,
  "total_processed": 230,
  "successful_count": 225,
  "failed_count": 5,
  "skipped_count": 4,
  "successful_page_ids": [1, 2, 3, ...],
  "failed_page_ids": [456, 789],
  "failed_reasons": {
    "456": "Page already in completed status",
    "789": "Database constraint violation"
  },
  "task_ids": ["task-123", "task-456"],
  "started_at": "2024-01-15T10:00:00Z",
  "completed_at": "2024-01-15T10:02:30Z",
  "duration_seconds": 150.5,
  "dry_run": false,
  "reason": "Re-evaluating filtered pages with medium priority",
  "filters_used": {...}
}
```

## 4. Available Actions

- **`mark_for_processing`**: Mark filtered pages for manual review
- **`approve_all`**: Approve pages awaiting manual review for processing
- **`skip_all`**: Skip pages and mark them as manually skipped
- **`retry`**: Retry failed pages by resetting their status to pending
- **`reset_status`**: Reset pages to a specific status
- **`update_priority`**: Update priority scores for pages
- **`delete`**: Delete pages (destructive operation, limited to 1000 pages)

## 5. Safety Features

- **Max Pages Limit**: Prevent operations on too many pages at once
- **Dry Run Mode**: Preview operations without making changes
- **Batch Processing**: Process pages in configurable batches
- **Progress Tracking**: Real-time WebSocket notifications
- **Transaction Safety**: Rollback on errors
- **Audit Trails**: All operations logged with reasons

## 6. WebSocket Notifications

Operations send real-time updates via WebSocket:

```json
{
  "type": "bulk_operation_completed",
  "operation_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "mark_for_processing",
  "successful_count": 225,
  "failed_count": 5,
  "task_ids": ["task-123", "task-456"],
  "timestamp": "2024-01-15T10:02:30Z"
}
```

## 7. Error Handling

The API includes comprehensive error handling:

- **400 Bad Request**: Invalid filters or request parameters
- **404 Not Found**: Project not found or access denied
- **500 Internal Server Error**: Server-side processing errors

Failed operations include detailed error messages and affected page IDs for troubleshooting.