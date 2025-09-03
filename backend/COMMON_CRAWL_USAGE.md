# CommonCrawlService Usage Guide

## Overview

The `CommonCrawlService` is a drop-in replacement for the existing `CDXAPIClient` from `wayback_machine.py`. It provides the same interface and functionality while querying Common Crawl instead of the Wayback Machine CDX API.

## Key Features

- **Interface Compatibility**: Same method signatures as `CDXAPIClient`
- **Circuit Breaker Protection**: Built-in fault tolerance and retry logic
- **Async/Await Support**: Fully asynchronous with FastAPI patterns
- **Filtering Integration**: Works with existing filter classes
- **Rate Limiting**: Respectful to Common Crawl infrastructure

## Basic Usage

### Simple Query (Recommended)

```python
from app.services.common_crawl_service import fetch_common_crawl_pages_simple

# Fetch records from Common Crawl
records = await fetch_common_crawl_pages_simple(
    domain_name="example.com",
    from_date="20240101", 
    to_date="20241231",
    match_type="domain",
    max_pages=5,
    include_attachments=True
)

for record in records:
    print(f"URL: {record.original_url}")
    print(f"Date: {record.capture_date}")
    print(f"Content: {record.content_url}")
```

### Advanced Usage with Full Filtering

```python
from app.services.common_crawl_service import CommonCrawlService

async with CommonCrawlService() as client:
    records, stats = await client.fetch_cdx_records(
        domain_name="example.com",
        from_date="20240101",
        to_date="20241231", 
        match_type="domain",
        min_size=1000,
        max_size=1024*1024*10,  # 10MB
        filter_list_pages=True,
        include_attachments=False
    )
    
    print(f"Total records: {stats['total_records']}")
    print(f"Final count: {stats['final_count']}")
    print(f"Filtered out: {stats['list_filtered']} list pages")
```

### Direct Class Usage

```python
from app.services.common_crawl_service import CommonCrawlService

async with CommonCrawlService() as client:
    # Get estimated page count
    page_count = await client.get_page_count("example.com", "20240101", "20241231")
    
    # Fetch simple records  
    records, stats = await client.fetch_cdx_records_simple(
        "example.com", "20240101", "20241231", max_pages=3
    )
```

## Drop-in Replacement

To use Common Crawl instead of Wayback Machine, simply replace imports:

**Before (Wayback Machine):**
```python
from app.services.wayback_machine import fetch_cdx_pages_simple, CDXAPIClient
```

**After (Common Crawl):**
```python
from app.services.common_crawl_service import fetch_common_crawl_pages_simple, CommonCrawlService
```

## Method Compatibility

| Wayback Machine Method | Common Crawl Equivalent | Notes |
|------------------------|--------------------------|-------|
| `CDXAPIClient()` | `CommonCrawlService()` | Same interface |
| `fetch_cdx_pages_simple()` | `fetch_common_crawl_pages_simple()` | Same parameters |
| `get_cdx_page_count()` | `get_common_crawl_page_count()` | Estimates only |
| `fetch_cdx_records()` | `fetch_cdx_records()` | Full compatibility |

## Configuration

The service uses the same configuration as Wayback Machine:

```python
# In .env or settings
WAYBACK_MACHINE_TIMEOUT=180
WAYBACK_MACHINE_MAX_RETRIES=5
```

## Important Differences from Wayback Machine

1. **Page Count Estimation**: Common Crawl doesn't provide exact page counts, so `get_page_count()` returns estimates
2. **Resume Keys**: Not supported by Common Crawl (`use_resume_key` parameter ignored)
3. **Data Coverage**: Common Crawl has different temporal coverage than Wayback Machine
4. **Rate Limits**: Common Crawl has different rate limiting behavior

## Circuit Breaker Integration

The service includes circuit breaker protection:

```python
from app.services.common_crawl_service import get_common_crawl_breaker

# Check circuit breaker status
breaker = get_common_crawl_breaker()
status = breaker.get_status()
print(f"Circuit state: {status['state']}")
print(f"Success rate: {status['metrics']['success_rate']}%")
```

## Error Handling

```python
from app.services.common_crawl_service import CommonCrawlException

try:
    records = await fetch_common_crawl_pages_simple("example.com", "20240101", "20241231")
except CommonCrawlException as e:
    logger.error(f"Common Crawl error: {e}")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
```

## Performance Considerations

- Common Crawl queries can be slower than Wayback Machine
- Use `max_pages` parameter to limit resource usage
- Consider using the simple methods for better performance
- The service includes automatic rate limiting and respectful delays

## Integration with Existing Code

The service is designed to work with all existing filtering and processing code:

```python
from app.services.wayback_machine import StaticAssetFilter, ListPageFilter
from app.services.common_crawl_service import CommonCrawlService

async with CommonCrawlService() as client:
    # Fetch raw records
    records, _ = await client.fetch_cdx_records_simple("example.com", "20240101", "20241231")
    
    # Apply existing filters
    filtered_records, _ = StaticAssetFilter.filter_static_assets(records)
    filtered_records, _ = ListPageFilter.filter_records(filtered_records)
    
    # Process with existing extraction pipeline
    # ... (same code as Wayback Machine)
```