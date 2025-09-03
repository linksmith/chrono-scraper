# Archive Sources Technical Documentation

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [Components](#components)
- [API Integration](#api-integration)
- [Database Schema](#database-schema)
- [Performance Characteristics](#performance-characteristics)
- [Configuration System](#configuration-system)
- [Error Handling](#error-handling)
- [Circuit Breaker Implementation](#circuit-breaker-implementation)
- [Development Guide](#development-guide)
- [Testing Strategies](#testing-strategies)
- [Monitoring and Observability](#monitoring-and-observability)

## Architecture Overview

The archive sources feature implements a comprehensive multi-archive system with intelligent routing, automatic fallback, and performance monitoring. The architecture follows a strategy pattern with circuit breaker integration for resilience.

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Archive Service Router                   │
│                                                             │
│  ┌─────────────────┐ ┌─────────────────┐ ┌──────────────┐  │
│  │ Routing Config  │ │ Fallback Logic  │ │ Metrics      │  │
│  └─────────────────┘ └─────────────────┘ └──────────────┘  │
│                                                             │
│  ┌─────────────────┐ ┌─────────────────┐                  │
│  │ Wayback Machine │ │ Common Crawl    │                  │
│  │ Strategy        │ │ Strategy        │                  │
│  └─────────────────┘ └─────────────────┘                  │
│                                                             │
│  ┌─────────────────┐ ┌─────────────────┐                  │
│  │ Circuit Breaker │ │ Circuit Breaker │                  │
│  │ (Wayback)       │ │ (Common Crawl)  │                  │
│  └─────────────────┘ └─────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    CDX Data Sources                         │
│                                                             │
│  ┌─────────────────┐           ┌─────────────────────────┐  │
│  │ Internet Archive│           │ Common Crawl            │  │
│  │ CDX API         │           │ CDX API                 │  │
│  │                 │           │ (via cdx_toolkit)       │  │
│  │ 522 prone       │           │ Monthly snapshots       │  │
│  │ Comprehensive   │           │ Fast & reliable         │  │
│  └─────────────────┘           └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Unified Interface**: Single API that abstracts archive source complexity
2. **Intelligent Routing**: Source selection based on health, performance, and configuration
3. **Graceful Degradation**: Automatic fallback with circuit breaker protection
4. **Performance Monitoring**: Comprehensive metrics for optimization
5. **Configuration Flexibility**: Project-level and system-level configuration options

## Components

### ArchiveServiceRouter

The central component that orchestrates queries across multiple archive sources.

**Key Features**:
- Intelligent source selection based on priority and health
- Automatic fallback with exponential backoff
- Circuit breaker integration
- Performance metrics tracking
- Project configuration support

**File**: `backend/app/services/archive_service_router.py`

```python
class ArchiveServiceRouter:
    """
    Intelligent router for archive services with fallback logic.
    Provides unified interface to CDX data from multiple sources.
    """
    
    async def query_archive(
        self,
        domain: str,
        from_date: str,
        to_date: str,
        project_config: Optional[Dict[str, Any]] = None,
        match_type: str = "domain",
        url_path: Optional[str] = None
    ) -> Tuple[List[CDXRecord], Dict[str, Any]]:
        """Main entry point for unified archive queries"""
```

### Archive Source Strategies

Each archive source implements the `ArchiveSourceStrategy` abstract base class:

#### WaybackMachineStrategy

**Implementation**: Uses existing `CDXAPIClient` with circuit breaker protection
**Error Handling**: Specifically handles 522 timeout errors
**Performance**: Variable response times, comprehensive coverage

```python
class WaybackMachineStrategy(ArchiveSourceStrategy):
    def is_retriable_error(self, error: Exception) -> bool:
        """Check if Wayback Machine error is retriable"""
        if isinstance(error, CDXAPIException):
            error_msg = str(error).lower()
            return any(retriable in error_msg for retriable in [
                "522", "timeout", "connection", "503", "502"
            ])
        return isinstance(error, (TimeoutError, ConnectionError))
```

#### CommonCrawlStrategy

**Implementation**: Uses `cdx_toolkit` library with async wrapper
**Error Handling**: Handles rate limiting and connection timeouts
**Performance**: Generally faster and more reliable than Wayback Machine

```python
class CommonCrawlStrategy(ArchiveSourceStrategy):
    async def query_archive(self, domain: str, from_date: str, 
                          to_date: str, match_type: str = "domain", 
                          url_path: Optional[str] = None
                         ) -> Tuple[List[CDXRecord], Dict[str, int]]:
        """Query Common Crawl CDX API"""
        async def _execute_query():
            async with CommonCrawlService() as service:
                return await service.fetch_cdx_records_simple(
                    domain_name=domain, from_date=from_date,
                    to_date=to_date, match_type=match_type,
                    url_path=url_path, page_size=self.config.page_size,
                    max_pages=self.config.max_pages,
                    include_attachments=self.config.include_attachments
                )
        return await self.circuit_breaker.execute(_execute_query)
```

### CommonCrawlService

New service implementing Common Crawl API access with `cdx_toolkit`.

**Key Features**:
- Compatible interface with existing `CDXAPIClient`
- Thread pool executor for async compatibility
- Proper rate limiting and timeout handling
- CDX record format conversion

**File**: `backend/app/services/common_crawl_service.py`

### Configuration Classes

#### RoutingConfig
Central configuration for routing behavior:
```python
@dataclass
class RoutingConfig:
    fallback_strategy: FallbackStrategy = FallbackStrategy.CIRCUIT_BREAKER
    fallback_delay_seconds: float = 1.0
    exponential_backoff: bool = True
    max_fallback_delay: float = 30.0
    wayback_config: ArchiveSourceConfig = field(default_factory=ArchiveSourceConfig)
    common_crawl_config: ArchiveSourceConfig = field(default_factory=ArchiveSourceConfig)
```

#### ArchiveSourceConfig
Per-source configuration:
```python
@dataclass
class ArchiveSourceConfig:
    enabled: bool = True
    timeout_seconds: int = 120
    max_retries: int = 3
    page_size: int = 5000
    max_pages: Optional[int] = None
    include_attachments: bool = True
    priority: int = 1  # Lower numbers = higher priority
    custom_settings: Dict[str, Any] = field(default_factory=dict)
```

## API Integration

### Project Model Updates

The `Project` model now includes archive source configuration:

```python
class Project(ProjectBase, table=True):
    # Archive Source Configuration
    archive_source: ArchiveSource = Field(
        default=ArchiveSource.WAYBACK_MACHINE, 
        sa_column=Column(String(20))
    )
    fallback_enabled: bool = Field(default=True)
    archive_config: Dict[str, Any] = Field(
        default_factory=dict, 
        sa_column=Column(JSON)
    )
```

### Archive Source Enum

```python
class ArchiveSource(str, Enum):
    """Archive source enumeration"""
    WAYBACK_MACHINE = "wayback_machine"
    COMMON_CRAWL = "common_crawl"
    HYBRID = "hybrid"
```

### Project Creation API

The project creation endpoint now accepts archive source parameters:

```python
# POST /api/v1/projects/
{
    "name": "Research Project",
    "description": "Historical analysis",
    "archive_source": "hybrid",
    "fallback_enabled": true,
    "archive_config": {
        "fallback_strategy": "circuit_breaker",
        "wayback_machine": {
            "timeout_seconds": 120,
            "page_size": 5000
        },
        "common_crawl": {
            "timeout_seconds": 180,
            "page_size": 5000
        }
    }
}
```

### Integration Points

#### Scraping Tasks
The scraping system integrates archive source routing through the project configuration:

```python
# In firecrawl_scraping.py
async def scrape_domain_batch(project_id: int, domain_id: int):
    project = await get_project(project_id)
    
    # Create router with project configuration
    router = ArchiveServiceRouter()
    
    # Query with project-specific archive settings
    cdx_records, stats = await router.query_archive(
        domain=domain.domain_name,
        from_date=session.from_date,
        to_date=session.to_date,
        project_config={
            'archive_source': project.archive_source,
            'fallback_enabled': project.fallback_enabled,
            'archive_config': project.archive_config
        }
    )
```

#### CDX Record Compatibility
All archive sources return standardized `CDXRecord` objects:

```python
@dataclass
class CDXRecord:
    timestamp: str          # Format: YYYYMMDDHHMMSS
    original_url: str       # Original captured URL
    mime_type: str          # MIME type (text/html, application/pdf)
    status_code: str        # HTTP status code
    digest: str             # Content digest/hash
    length: str             # Content length in bytes
```

## Database Schema

### Migration Changes

New fields added to the `projects` table:

```sql
-- Add archive source configuration
ALTER TABLE projects ADD COLUMN archive_source VARCHAR(20) 
    DEFAULT 'wayback_machine' NOT NULL;
ALTER TABLE projects ADD COLUMN fallback_enabled BOOLEAN 
    DEFAULT true NOT NULL;
ALTER TABLE projects ADD COLUMN archive_config JSON 
    DEFAULT '{}';
```

### Backward Compatibility

Existing projects automatically get default values:
- `archive_source`: "wayback_machine" (maintains existing behavior)  
- `fallback_enabled`: `true` (enables fallback for reliability)
- `archive_config`: `{}` (empty configuration uses system defaults)

## Performance Characteristics

### Query Performance Comparison

| Archive Source | Avg Response Time | Reliability | Coverage Period | Update Frequency |
|----------------|-------------------|-------------|-----------------|------------------|
| Wayback Machine | 5-30 seconds | Variable (522 errors) | 1996-present | Continuous |
| Common Crawl | 2-15 seconds | High | 2010-present | Monthly |
| Hybrid Mode | 5-30s primary, +1-2s fallback | Very High | Combined | Combined |

### Resource Usage

#### Memory Usage
- **Base System**: ~200MB baseline
- **Archive Router**: +10MB for metrics and caching
- **Circuit Breakers**: +2MB for state tracking
- **Per-Query Overhead**: ~1KB for metrics tracking

#### Network Usage
- **Single Source**: 1x API calls to chosen archive
- **Hybrid Mode**: 1x API calls + minimal overhead for health checks
- **Fallback Events**: 2x API calls when primary source fails

#### Performance Optimizations

1. **Circuit Breaker**: Prevents repeated failed attempts
2. **Intelligent Routing**: Routes to healthiest available source
3. **Connection Reuse**: HTTP connection pooling within sessions
4. **Async Processing**: Non-blocking I/O for all API calls

### Scaling Considerations

#### Horizontal Scaling
- **Stateless Design**: Router instances are stateless and can be scaled
- **Shared Circuit Breakers**: Use Redis-based circuit breaker for multi-instance deployments
- **Metrics Aggregation**: Consider centralized metrics collection for large deployments

#### Vertical Scaling  
- **CPU**: Minimal CPU overhead for routing logic
- **Memory**: Linear growth with metrics history size
- **I/O**: Network I/O bound, benefits from faster network connections

## Configuration System

### Environment Variables

```bash
# Archive source defaults
ARCHIVE_DEFAULT_SOURCE=hybrid
ARCHIVE_DEFAULT_FALLBACK_ENABLED=true

# Common Crawl specific
COMMON_CRAWL_TIMEOUT=180
COMMON_CRAWL_MAX_RETRIES=5
COMMON_CRAWL_PAGE_SIZE=5000

# Wayback Machine (existing)
WAYBACK_MACHINE_TIMEOUT=120
WAYBACK_MACHINE_MAX_RETRIES=3
WAYBACK_MACHINE_PAGE_SIZE=5000

# Circuit breaker settings
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_SUCCESS_THRESHOLD=3
CIRCUIT_BREAKER_TIMEOUT_SECONDS=90
```

### Configuration Hierarchy

1. **System Defaults**: Hard-coded reasonable defaults
2. **Environment Variables**: System-wide configuration
3. **Project Configuration**: Project-specific overrides
4. **Runtime Configuration**: Dynamic adjustments based on performance

### Dynamic Configuration

The system supports runtime configuration adjustments:

```python
# Adjust timeout for slow networks
router.config.wayback_config.timeout_seconds = 300

# Disable source temporarily
router.config.common_crawl_config.enabled = False

# Change fallback strategy
router.config.fallback_strategy = FallbackStrategy.IMMEDIATE
```

## Error Handling

### Error Classification

#### Retriable Errors
- **522 Connection timeout**: Wayback Machine server overload
- **503 Service unavailable**: Temporary service issues
- **Connection timeout**: Network connectivity issues
- **Rate limiting**: API rate limit exceeded (with backoff)

#### Non-Retriable Errors
- **404 Not found**: Domain/URL doesn't exist in archive
- **400 Bad request**: Invalid query parameters
- **403 Forbidden**: Access denied (unlikely with public APIs)
- **500 Internal server error**: Persistent server issues

### Fallback Logic

```python
def _should_attempt_fallback(self, error: Exception, 
                           strategy: ArchiveSourceStrategy,
                           fallback_available: bool) -> bool:
    """Determine if fallback should be attempted"""
    if not fallback_available:
        return False
    
    if self.config.fallback_strategy == FallbackStrategy.IMMEDIATE:
        return True
    elif self.config.fallback_strategy == FallbackStrategy.RETRY_THEN_FALLBACK:
        return (not strategy.is_retriable_error(error) or 
               isinstance(error, CircuitBreakerOpenException))
    elif self.config.fallback_strategy == FallbackStrategy.CIRCUIT_BREAKER:
        return isinstance(error, CircuitBreakerOpenException)
    
    return False
```

### Error Propagation

The system provides detailed error information while maintaining a clean interface:

```python
try:
    records, stats = await router.query_archive(domain, from_date, to_date)
except AllSourcesFailedException as e:
    # All configured sources failed
    logger.error(f"Complete archive failure: {e}")
    # stats contain detailed failure information
except ArchiveServiceRouterException as e:
    # Router-specific error
    logger.error(f"Archive router error: {e}")
```

## Circuit Breaker Implementation

### Circuit Breaker States

1. **Closed**: Normal operation, requests pass through
2. **Open**: Failures exceeded threshold, requests are blocked
3. **Half-Open**: Testing if service has recovered

### Configuration

```python
CircuitBreakerConfig(
    failure_threshold=5,        # Failures before opening
    success_threshold=3,        # Successes to close circuit
    timeout_seconds=90,         # Time before retry
    max_timeout_seconds=600,    # Maximum timeout
    exponential_backoff=True,   # Exponential timeout increase
    sliding_window_size=10      # Window for failure rate calculation
)
```

### Integration with Routing

```python
# Circuit breaker automatically integrates with strategies
async def query_archive(self, domain, from_date, to_date):
    try:
        return await self.circuit_breaker.execute(query_function)
    except CircuitBreakerOpenException:
        # Automatically triggers fallback logic
        logger.info("Circuit breaker open, attempting fallback")
        raise
```

### Monitoring

Circuit breaker states are exposed through health endpoints:

```python
def get_health_status(self) -> Dict[str, Any]:
    return {
        "circuit_breakers": {
            "wayback_machine": self.wayback_breaker.get_status(),
            "common_crawl": self.common_crawl_breaker.get_status()
        }
    }
```

## Development Guide

### Adding New Archive Sources

1. **Create Strategy Class**:
```python
class NewArchiveStrategy(ArchiveSourceStrategy):
    async def query_archive(self, domain, from_date, to_date, 
                          match_type="domain", url_path=None):
        # Implement archive-specific logic
        pass
    
    def is_retriable_error(self, error):
        # Define what errors are worth retrying
        pass
    
    def get_error_type(self, error):
        # Classify errors for metrics
        pass
```

2. **Update Enum**:
```python
class ArchiveSource(str, Enum):
    WAYBACK_MACHINE = "wayback_machine"
    COMMON_CRAWL = "common_crawl"
    NEW_ARCHIVE = "new_archive"
    HYBRID = "hybrid"
```

3. **Register Strategy**:
```python
def _init_source_strategies(self):
    self.strategies = {
        "wayback_machine": WaybackMachineStrategy(...),
        "common_crawl": CommonCrawlStrategy(...),
        "new_archive": NewArchiveStrategy(...),
    }
```

4. **Update Configuration**:
```python
@dataclass
class RoutingConfig:
    wayback_config: ArchiveSourceConfig = field(default_factory=ArchiveSourceConfig)
    common_crawl_config: ArchiveSourceConfig = field(default_factory=ArchiveSourceConfig)
    new_archive_config: ArchiveSourceConfig = field(default_factory=ArchiveSourceConfig)
```

### Local Development Setup

```bash
# Install additional dependencies for Common Crawl
pip install cdx_toolkit

# Run tests
pytest tests/test_archive_service_router.py -v
pytest tests/test_common_crawl_service.py -v

# Test integration
pytest tests/test_archive_pipeline_e2e.py -v
```

### Debugging

```python
# Enable detailed logging
logging.getLogger('app.services.archive_service_router').setLevel(logging.DEBUG)
logging.getLogger('app.services.common_crawl_service').setLevel(logging.DEBUG)

# Monitor metrics
router = ArchiveServiceRouter()
metrics = router.get_performance_metrics()
print(json.dumps(metrics, indent=2))

# Check circuit breaker status
health = router.get_health_status()
print(f"Health status: {health['overall_status']}")
```

## Testing Strategies

### Unit Tests

```python
# Test router configuration
def test_routing_config_priority():
    config = RoutingConfig()
    config.wayback_config.priority = 2
    config.common_crawl_config.priority = 1
    
    router = ArchiveServiceRouter(config)
    order = router._determine_source_order(ArchiveSource.HYBRID)
    assert order == ["common_crawl", "wayback_machine"]

# Test fallback logic
@pytest.mark.asyncio
async def test_fallback_on_522_error():
    router = ArchiveServiceRouter()
    
    # Mock Wayback Machine failure
    with patch.object(router.strategies["wayback_machine"], 
                     "query_archive") as mock_wb:
        mock_wb.side_effect = CDXAPIException("522 Connection timeout")
        
        # Mock Common Crawl success
        with patch.object(router.strategies["common_crawl"], 
                         "query_archive") as mock_cc:
            mock_cc.return_value = ([], {})
            
            records, stats = await router.query_archive(
                "example.com", "20240101", "20240131",
                project_config={"archive_source": "hybrid"}
            )
            
            assert stats["fallback_used"] is True
            assert stats["successful_source"] == "common_crawl"
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_archive_sources_integration():
    """Test actual archive source integration"""
    router = ArchiveServiceRouter()
    
    # Test with real domain
    records, stats = await router.query_archive(
        "example.com", "20240101", "20240131",
        project_config={"archive_source": "hybrid"}
    )
    
    assert len(records) > 0
    assert stats["total_records"] > 0
    assert stats["successful_source"] in ["wayback_machine", "common_crawl"]
```

### Performance Tests

```python
@pytest.mark.performance
async def test_archive_performance():
    """Test performance characteristics"""
    router = ArchiveServiceRouter()
    
    start_time = time.time()
    records, stats = await router.query_archive(
        "example.com", "20240101", "20240131"
    )
    duration = time.time() - start_time
    
    # Performance assertions
    assert duration < 60  # Should complete within 60 seconds
    assert stats["total_duration"] < 60
    
    # Metrics validation
    metrics = router.get_performance_metrics()
    assert metrics["overall"]["total_queries"] > 0
```

### Mock Strategies

For testing, create mock strategies that simulate various failure scenarios:

```python
class MockFailingStrategy(ArchiveSourceStrategy):
    def __init__(self, failure_type="timeout"):
        self.failure_type = failure_type
    
    async def query_archive(self, *args, **kwargs):
        if self.failure_type == "522":
            raise CDXAPIException("522 Connection timeout")
        elif self.failure_type == "timeout":
            raise TimeoutError("Request timeout")
        elif self.failure_type == "rate_limit":
            raise CommonCrawlAPIException("Rate limit exceeded")
        else:
            raise Exception(f"Unknown failure: {self.failure_type}")
```

## Monitoring and Observability

### Metrics Collection

The system collects comprehensive metrics for monitoring:

```python
@dataclass
class ArchiveSourceMetrics:
    source_name: str
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    total_records: int = 0
    avg_response_time: float = 0.0
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    error_counts: Dict[str, int] = field(default_factory=dict)
    
    @property
    def success_rate(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return (self.successful_queries / self.total_queries) * 100.0
```

### Health Check Integration

```python
# Health endpoint returns archive source status
GET /api/v1/health

{
    "archive_sources": {
        "overall_status": "healthy",
        "sources": {
            "wayback_machine": {
                "healthy": true,
                "circuit_breaker_state": "closed",
                "success_rate": 95.2,
                "last_success": "2024-01-15T10:30:00Z"
            },
            "common_crawl": {
                "healthy": true,
                "circuit_breaker_state": "closed", 
                "success_rate": 98.7,
                "last_success": "2024-01-15T10:29:45Z"
            }
        }
    }
}
```

### Logging

Structured logging for observability:

```python
logger.info("Archive query started", extra={
    "domain": domain,
    "from_date": from_date,
    "to_date": to_date,
    "archive_source": archive_source,
    "fallback_enabled": fallback_enabled
})

logger.warning("Archive source failed", extra={
    "source": source_name,
    "error_type": error_type,
    "error_message": str(error),
    "duration": query_metrics.duration_seconds,
    "fallback_available": bool(remaining_sources)
})

logger.info("Archive query completed", extra={
    "successful_source": successful_source,
    "fallback_used": fallback_used,
    "total_duration": total_duration,
    "records_retrieved": len(records)
})
```

### Prometheus Metrics

Export metrics for Prometheus monitoring:

```python
from prometheus_client import Counter, Histogram, Gauge

# Archive source metrics
archive_queries_total = Counter(
    'archive_queries_total',
    'Total archive queries',
    ['source', 'status']
)

archive_query_duration = Histogram(
    'archive_query_duration_seconds',
    'Archive query duration',
    ['source']
)

archive_source_health = Gauge(
    'archive_source_health',
    'Archive source health (1=healthy, 0=unhealthy)',
    ['source']
)
```

### Dashboard Integration

Key metrics for monitoring dashboards:

1. **Success Rates**: Per-source success rates over time
2. **Response Times**: Average and percentile response times
3. **Error Rates**: Error frequency and types
4. **Circuit Breaker States**: Current state of each circuit breaker
5. **Fallback Frequency**: How often fallback is triggered
6. **Query Volume**: Queries per minute/hour by source

### Alerting

Recommended alerts:

```yaml
# High error rate alert
- alert: ArchiveSourceHighErrorRate
  expr: archive_queries_total{status="failed"} / archive_queries_total > 0.1
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High error rate for archive source {{ $labels.source }}"

# Circuit breaker open alert  
- alert: ArchiveSourceCircuitBreakerOpen
  expr: archive_source_health == 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "Archive source {{ $labels.source }} circuit breaker is open"

# Slow response alert
- alert: ArchiveSourceSlowResponse
  expr: archive_query_duration_seconds{quantile="0.95"} > 60
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Archive source {{ $labels.source }} responding slowly"
```