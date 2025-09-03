# Archive Sources Monitoring and Troubleshooting

## Table of Contents
- [Key Metrics](#key-metrics)
- [Monitoring Setup](#monitoring-setup)
- [Health Check Integration](#health-check-integration)
- [Performance Monitoring](#performance-monitoring)
- [Alerting](#alerting)
- [Common Issues](#common-issues)
- [Log Analysis](#log-analysis)
- [Diagnostic Tools](#diagnostic-tools)
- [Dashboard Configuration](#dashboard-configuration)
- [Incident Response](#incident-response)

## Key Metrics

### Archive Source Performance Metrics

Monitor these critical metrics for each archive source:

#### Success Rate Metrics
```
archive_queries_total{source="wayback_machine", status="success"}
archive_queries_total{source="wayback_machine", status="failed"}
archive_queries_total{source="common_crawl", status="success"}  
archive_queries_total{source="common_crawl", status="failed"}
```

**Thresholds:**
- **Healthy**: Success rate > 95%
- **Warning**: Success rate 80-95%
- **Critical**: Success rate < 80%

#### Response Time Metrics
```
archive_query_duration_seconds{source="wayback_machine"}
archive_query_duration_seconds{source="common_crawl"}
```

**Thresholds:**
- **Good**: p95 < 30 seconds
- **Acceptable**: p95 30-60 seconds  
- **Poor**: p95 > 60 seconds

#### Circuit Breaker Metrics
```
circuit_breaker_state{source="wayback_machine"} # 0=closed, 1=open, 2=half_open
circuit_breaker_state{source="common_crawl"}
circuit_breaker_failure_count{source="wayback_machine"}
circuit_breaker_failure_count{source="common_crawl"}
```

#### Fallback Metrics
```
archive_fallback_events_total{from_source="wayback_machine", to_source="common_crawl"}
archive_fallback_events_total{from_source="common_crawl", to_source="wayback_machine"}
archive_fallback_success_rate{from_source="wayback_machine"}
```

### Error Classification Metrics

Track specific error types for targeted troubleshooting:

```
archive_errors_total{source="wayback_machine", error_type="522_timeout"}
archive_errors_total{source="wayback_machine", error_type="503_unavailable"}
archive_errors_total{source="wayback_machine", error_type="connection_timeout"}
archive_errors_total{source="common_crawl", error_type="rate_limit"}
archive_errors_total{source="common_crawl", error_type="connection_error"}
```

### Resource Usage Metrics

Monitor resource consumption of archive source functionality:

```
archive_router_memory_usage_bytes
archive_router_cpu_usage_percent
archive_active_connections{source="wayback_machine"}
archive_active_connections{source="common_crawl"}
```

## Monitoring Setup

### Prometheus Configuration

Add archive source metrics to your `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "archive_source_rules.yml"

scrape_configs:
  - job_name: 'chrono-scraper'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s
    scrape_timeout: 10s
    
    metric_relabel_configs:
      # Keep only archive source metrics
      - source_labels: [__name__]
        regex: 'archive_.*|circuit_breaker_.*'
        action: keep
```

### Grafana Dashboard Configuration

Create a comprehensive Grafana dashboard for archive sources:

```json
{
  "dashboard": {
    "title": "Archive Sources Monitoring",
    "panels": [
      {
        "title": "Archive Source Success Rates",
        "type": "stat",
        "targets": [
          {
            "expr": "rate(archive_queries_total{status=\"success\"}[5m]) / rate(archive_queries_total[5m]) * 100",
            "legendFormat": "{{source}} Success Rate"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "thresholds": {
              "steps": [
                {"color": "red", "value": 0},
                {"color": "yellow", "value": 80},
                {"color": "green", "value": 95}
              ]
            }
          }
        }
      },
      {
        "title": "Query Response Times",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(archive_query_duration_seconds_bucket[5m]))",
            "legendFormat": "{{source}} p95"
          },
          {
            "expr": "histogram_quantile(0.50, rate(archive_query_duration_seconds_bucket[5m]))",
            "legendFormat": "{{source}} p50"
          }
        ]
      },
      {
        "title": "Circuit Breaker States",
        "type": "stat",
        "targets": [
          {
            "expr": "circuit_breaker_state",
            "legendFormat": "{{source}}"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "mappings": [
              {"options": {"0": {"text": "CLOSED", "color": "green"}}},
              {"options": {"1": {"text": "OPEN", "color": "red"}}},
              {"options": {"2": {"text": "HALF_OPEN", "color": "yellow"}}}
            ]
          }
        }
      },
      {
        "title": "Fallback Events",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(archive_fallback_events_total[5m])",
            "legendFormat": "{{from_source}} → {{to_source}}"
          }
        ]
      }
    ]
  }
}
```

### Application Metrics Export

Ensure your application exports archive source metrics:

```python
# In your FastAPI app
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import FastAPI

app = FastAPI()

# Archive source metrics
archive_queries_total = Counter(
    'archive_queries_total',
    'Total archive queries by source and status',
    ['source', 'status']
)

archive_query_duration = Histogram(
    'archive_query_duration_seconds',
    'Archive query duration in seconds',
    ['source'],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

circuit_breaker_state = Gauge(
    'circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half_open)',
    ['source']
)

@app.get("/metrics")
async def get_metrics():
    return Response(generate_latest(), media_type="text/plain")
```

## Health Check Integration

### Archive Source Health Endpoint

Implement comprehensive health checks for archive sources:

```python
@app.get("/api/v1/health/archive-sources")
async def archive_sources_health():
    """Detailed health check for archive sources"""
    
    router = ArchiveServiceRouter()
    health_status = router.get_health_status()
    
    # Determine HTTP status code
    if health_status["overall_status"] == "healthy":
        status_code = 200
    elif health_status["overall_status"] == "degraded":
        status_code = 200  # Still functional
    else:
        status_code = 503  # Service unavailable
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": health_status["overall_status"],
            "timestamp": health_status["timestamp"],
            "sources": health_status["sources"],
            "details": {
                "wayback_machine": {
                    "available": health_status["sources"]["wayback_machine"]["healthy"],
                    "circuit_breaker": health_status["sources"]["wayback_machine"]["circuit_breaker_state"],
                    "last_success": health_status["sources"]["wayback_machine"]["last_success"]
                },
                "common_crawl": {
                    "available": health_status["sources"]["common_crawl"]["healthy"],
                    "circuit_breaker": health_status["sources"]["common_crawl"]["circuit_breaker_state"],
                    "last_success": health_status["sources"]["common_crawl"]["last_success"]
                }
            }
        }
    )
```

### Load Balancer Integration

Configure load balancers to use archive source health:

#### HAProxy Configuration
```haproxy
backend chrono_backend
    balance roundrobin
    option httpchk GET /api/v1/health/archive-sources
    http-check expect status 200
    
    server backend1 backend1:8000 check inter 30s fall 3 rise 2
    server backend2 backend2:8000 check inter 30s fall 3 rise 2
    server backend3 backend3:8000 check inter 30s fall 3 rise 2
```

#### NGINX Configuration  
```nginx
upstream chrono_backend {
    server backend1:8000 max_fails=2 fail_timeout=30s;
    server backend2:8000 max_fails=2 fail_timeout=30s;
}

location /health {
    access_log off;
    proxy_pass http://chrono_backend/api/v1/health/archive-sources;
    proxy_set_header Host $host;
}
```

### Kubernetes Health Probes

Configure Kubernetes readiness and liveness probes:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chrono-scraper-backend
spec:
  template:
    spec:
      containers:
      - name: backend
        image: chrono-scraper:latest
        ports:
        - containerPort: 8000
        
        # Liveness probe - restart if unhealthy
        livenessProbe:
          httpGet:
            path: /api/v1/health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 30
          timeoutSeconds: 10
          failureThreshold: 3
        
        # Readiness probe - remove from service if degraded
        readinessProbe:
          httpGet:
            path: /api/v1/health/archive-sources
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 15
          timeoutSeconds: 5
          failureThreshold: 2
          successThreshold: 2
```

## Performance Monitoring

### Response Time Analysis

Monitor archive source response times to identify performance issues:

```python
# Performance monitoring script
import asyncio
import time
from app.services.archive_service_router import ArchiveServiceRouter

async def performance_monitor():
    """Monitor archive source performance"""
    
    router = ArchiveServiceRouter()
    test_domain = "example.com"
    test_dates = ("20240101", "20240131")
    
    # Test each source individually
    for source in ["wayback_machine", "common_crawl"]:
        try:
            start_time = time.time()
            
            records, stats = await router.query_archive(
                domain=test_domain,
                from_date=test_dates[0],
                to_date=test_dates[1],
                project_config={"archive_source": source, "fallback_enabled": False}
            )
            
            duration = time.time() - start_time
            
            print(f"{source}:")
            print(f"  Response time: {duration:.2f}s")
            print(f"  Records: {len(records)}")
            print(f"  Success: {stats.get('successful_source') == source}")
            
        except Exception as e:
            print(f"{source}: ERROR - {e}")
    
    # Test hybrid mode
    try:
        start_time = time.time()
        
        records, stats = await router.query_archive(
            domain=test_domain,
            from_date=test_dates[0],
            to_date=test_dates[1],
            project_config={"archive_source": "hybrid", "fallback_enabled": True}
        )
        
        duration = time.time() - start_time
        
        print(f"hybrid:")
        print(f"  Response time: {duration:.2f}s")
        print(f"  Records: {len(records)}")
        print(f"  Primary source: {stats.get('primary_source')}")
        print(f"  Successful source: {stats.get('successful_source')}")
        print(f"  Fallback used: {stats.get('fallback_used', False)}")
        
    except Exception as e:
        print(f"hybrid: ERROR - {e}")

if __name__ == "__main__":
    asyncio.run(performance_monitor())
```

Run performance monitoring regularly:

```bash
# Add to crontab for hourly monitoring
0 * * * * docker compose exec backend python /scripts/performance_monitor.py >> /logs/archive_performance.log 2>&1
```

### Resource Usage Monitoring

Track memory and CPU usage of archive source components:

```python
# Resource usage monitoring
import psutil
import gc
from app.services.archive_service_router import ArchiveServiceRouter

def monitor_resource_usage():
    """Monitor resource usage of archive components"""
    
    process = psutil.Process()
    initial_memory = process.memory_info().rss
    
    # Create router and measure memory impact
    router = ArchiveServiceRouter()
    post_init_memory = process.memory_info().rss
    
    print(f"Memory usage:")
    print(f"  Initial: {initial_memory / 1024 / 1024:.1f} MB")
    print(f"  Post-init: {post_init_memory / 1024 / 1024:.1f} MB")
    print(f"  Router overhead: {(post_init_memory - initial_memory) / 1024 / 1024:.1f} MB")
    
    # Get performance metrics
    metrics = router.get_performance_metrics()
    
    print(f"\nMetrics memory usage:")
    print(f"  Query history size: {metrics['overall']['query_history_size']}")
    print(f"  Total queries tracked: {metrics['overall']['total_queries']}")
    
    # Force garbage collection and measure
    gc.collect()
    post_gc_memory = process.memory_info().rss
    print(f"  Post-GC: {post_gc_memory / 1024 / 1024:.1f} MB")
    
    return {
        "memory_mb": post_gc_memory / 1024 / 1024,
        "router_overhead_mb": (post_init_memory - initial_memory) / 1024 / 1024,
        "metrics": metrics
    }
```

## Alerting

### Alert Rules Configuration

Create Prometheus alert rules for archive sources:

```yaml
# archive_source_rules.yml
groups:
  - name: archive_sources
    rules:
    
    # High error rate alerts
    - alert: ArchiveSourceHighErrorRate
      expr: >
        (
          rate(archive_queries_total{status="failed"}[5m]) /
          rate(archive_queries_total[5m])
        ) * 100 > 20
      for: 5m
      labels:
        severity: warning
        service: chrono-scraper
        component: archive-sources
      annotations:
        summary: "High error rate for archive source {{ $labels.source }}"
        description: "Archive source {{ $labels.source }} has {{ $value }}% error rate over the last 5 minutes"
        runbook_url: "https://docs.chrono-scraper.com/troubleshooting/archive-sources#high-error-rate"

    - alert: ArchiveSourceVeryHighErrorRate  
      expr: >
        (
          rate(archive_queries_total{status="failed"}[5m]) /
          rate(archive_queries_total[5m])
        ) * 100 > 50
      for: 2m
      labels:
        severity: critical
        service: chrono-scraper
        component: archive-sources
      annotations:
        summary: "Very high error rate for archive source {{ $labels.source }}"
        description: "Archive source {{ $labels.source }} has {{ $value }}% error rate over the last 2 minutes"
        runbook_url: "https://docs.chrono-scraper.com/troubleshooting/archive-sources#very-high-error-rate"

    # Circuit breaker alerts
    - alert: CircuitBreakerOpen
      expr: circuit_breaker_state == 1
      for: 1m
      labels:
        severity: critical
        service: chrono-scraper
        component: archive-sources
      annotations:
        summary: "Circuit breaker open for {{ $labels.source }}"
        description: "Circuit breaker for {{ $labels.source }} has been open for over 1 minute"
        runbook_url: "https://docs.chrono-scraper.com/troubleshooting/archive-sources#circuit-breaker-open"

    # Response time alerts
    - alert: ArchiveSourceSlowResponse
      expr: >
        histogram_quantile(0.95, rate(archive_query_duration_seconds_bucket[5m])) > 60
      for: 10m
      labels:
        severity: warning
        service: chrono-scraper
        component: archive-sources
      annotations:
        summary: "Slow response time for archive source {{ $labels.source }}"
        description: "Archive source {{ $labels.source }} 95th percentile response time is {{ $value }}s"
        runbook_url: "https://docs.chrono-scraper.com/troubleshooting/archive-sources#slow-response"

    # Fallback frequency alerts
    - alert: HighFallbackRate
      expr: rate(archive_fallback_events_total[5m]) > 0.1
      for: 5m
      labels:
        severity: warning
        service: chrono-scraper
        component: archive-sources
      annotations:
        summary: "High fallback rate between archive sources"
        description: "Archive sources are falling back at {{ $value }} events per second"
        runbook_url: "https://docs.chrono-scraper.com/troubleshooting/archive-sources#high-fallback-rate"

    # No queries alert (possible issue with scraping)
    - alert: NoArchiveQueries
      expr: rate(archive_queries_total[10m]) == 0
      for: 30m
      labels:
        severity: warning
        service: chrono-scraper
        component: archive-sources
      annotations:
        summary: "No archive queries detected"
        description: "No archive source queries have been made in the last 30 minutes"
        runbook_url: "https://docs.chrono-scraper.com/troubleshooting/archive-sources#no-queries"
```

### Slack/Teams Integration

Configure alert manager to send notifications:

```yaml
# alertmanager.yml
global:
  slack_api_url: 'YOUR_SLACK_WEBHOOK_URL'

route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'web.hook'
  routes:
  - match:
      service: chrono-scraper
    receiver: 'chrono-alerts'

receivers:
- name: 'chrono-alerts'
  slack_configs:
  - channel: '#chrono-scraper-alerts'
    title: 'Archive Sources Alert'
    text: |
      {{ range .Alerts }}
      *Alert:* {{ .Annotations.summary }}
      *Description:* {{ .Annotations.description }}
      *Runbook:* {{ .Annotations.runbook_url }}
      *Severity:* {{ .Labels.severity }}
      {{ end }}
```

### PagerDuty Integration

For critical alerts, integrate with PagerDuty:

```yaml
receivers:
- name: 'chrono-critical'
  pagerduty_configs:
  - service_key: 'YOUR_PAGERDUTY_SERVICE_KEY'
    description: '{{ .GroupLabels.alertname }}: {{ .Annotations.summary }}'
    details:
      firing: '{{ .Alerts.Firing | len }}'
      resolved: '{{ .Alerts.Resolved | len }}'
      
routes:
- match:
    severity: critical
  receiver: 'chrono-critical'
  continue: true
```

## Common Issues

### 1. 522 Connection Timeout Errors (Wayback Machine)

**Symptoms:**
- Frequent "522 Connection timeout" errors in logs
- Wayback Machine circuit breaker opens frequently
- Automatic fallback to Common Crawl

**Causes:**
- Wayback Machine server overload
- Network connectivity issues
- Large query timeouts

**Troubleshooting Steps:**

1. **Check Error Frequency:**
   ```bash
   # Check logs for 522 errors
   docker compose logs backend | grep -i "522" | tail -20
   ```

2. **Monitor Circuit Breaker:**
   ```python
   # Check circuit breaker status
   from app.services.circuit_breaker import get_wayback_machine_breaker
   breaker = get_wayback_machine_breaker()
   status = breaker.get_status()
   print(f"State: {status['state']}")
   print(f"Failure count: {status['failure_count']}")
   ```

3. **Test Direct Connectivity:**
   ```bash
   # Test Wayback Machine API directly
   curl -I "https://web.archive.org/cdx/search/cdx?url=example.com&output=json&limit=1"
   ```

**Solutions:**

1. **Adjust Timeouts:**
   ```bash
   # Increase timeout values
   WAYBACK_MACHINE_TIMEOUT=180
   WAYBACK_CIRCUIT_BREAKER_TIMEOUT=300
   ```

2. **Enable Hybrid Mode:**
   - Switch existing projects to hybrid mode for automatic fallback
   - Use Common Crawl as primary source during peak hours

3. **Implement Retry Logic:**
   ```bash
   # More aggressive retries
   WAYBACK_MACHINE_MAX_RETRIES=5
   WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD=7
   ```

### 2. Common Crawl Rate Limiting

**Symptoms:**
- "Rate limit exceeded" errors from Common Crawl
- Slower than expected responses
- Circuit breaker activation

**Troubleshooting Steps:**

1. **Check Rate Limit Headers:**
   ```python
   # Monitor Common Crawl responses
   import aiohttp
   async with aiohttp.ClientSession() as session:
       async with session.get("https://index.commoncrawl.org/CC-MAIN-2024-10-cdx") as response:
           print(f"Rate limit headers: {dict(response.headers)}")
   ```

2. **Review Query Patterns:**
   ```bash
   # Analyze query frequency
   docker compose logs backend | grep -i "common_crawl" | grep -c "$(date '+%Y-%m-%d %H')"
   ```

**Solutions:**

1. **Implement Backoff:**
   ```bash
   # Increase delays between requests
   ARCHIVE_FALLBACK_DELAY=2.0
   ARCHIVE_FALLBACK_MAX_DELAY=60.0
   ```

2. **Reduce Concurrency:**
   ```bash
   # Limit concurrent requests
   COMMON_CRAWL_THREAD_POOL_SIZE=2
   CELERY_WORKER_CONCURRENCY=2
   ```

### 3. Circuit Breaker Stuck Open

**Symptoms:**
- Circuit breaker remains open longer than expected
- No automatic recovery
- All requests to affected source fail

**Troubleshooting Steps:**

1. **Check Circuit Breaker Configuration:**
   ```python
   from app.services.circuit_breaker import circuit_registry
   for name, breaker in circuit_registry.breakers.items():
       status = breaker.get_status()
       print(f"{name}: {status}")
   ```

2. **Review Failure Patterns:**
   ```bash
   # Check recent failures
   docker compose logs backend | grep -i "circuit.*open" | tail -10
   ```

**Solutions:**

1. **Manual Reset:**
   ```python
   # Reset specific circuit breaker
   from app.services.circuit_breaker import get_wayback_machine_breaker
   breaker = get_wayback_machine_breaker()
   breaker.reset()
   ```

2. **Adjust Thresholds:**
   ```bash
   # More lenient circuit breaker
   WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD=10
   WAYBACK_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2
   ```

### 4. High Memory Usage

**Symptoms:**
- Increasing memory usage over time
- Out of memory errors
- Slow performance

**Troubleshooting Steps:**

1. **Monitor Memory Usage:**
   ```bash
   # Check container memory usage
   docker stats chrono_backend
   ```

2. **Check Metrics History Size:**
   ```python
   from app.services.archive_service_router import ArchiveServiceRouter
   router = ArchiveServiceRouter()
   metrics = router.get_performance_metrics()
   print(f"Query history size: {metrics['overall']['query_history_size']}")
   ```

**Solutions:**

1. **Reduce Metrics Collection:**
   ```bash
   # Limit metrics history
   ARCHIVE_METRICS_HISTORY_SIZE=100
   ```

2. **Disable Metrics in Production:**
   ```bash
   # For memory-constrained environments
   ARCHIVE_METRICS_ENABLED=false
   ```

3. **Implement Metrics Cleanup:**
   ```python
   # Regular cleanup of old metrics
   router.reset_metrics()  # Clear all metrics
   ```

### 5. Poor Performance

**Symptoms:**
- Slow archive queries (>60 seconds)
- High CPU usage
- User complaints about responsiveness

**Troubleshooting Steps:**

1. **Profile Query Performance:**
   ```python
   import cProfile
   import asyncio
   from app.services.archive_service_router import ArchiveServiceRouter
   
   async def profile_query():
       router = ArchiveServiceRouter()
       records, stats = await router.query_archive(
           "example.com", "20240101", "20240131"
       )
       return len(records)
   
   # Profile the query
   cProfile.run("asyncio.run(profile_query())")
   ```

2. **Analyze Response Times by Source:**
   ```python
   router = ArchiveServiceRouter()
   metrics = router.get_performance_metrics()
   
   for source, data in metrics["sources"].items():
       print(f"{source}: {data['avg_response_time']:.2f}s average")
   ```

**Solutions:**

1. **Switch to Faster Source:**
   ```bash
   # Use Common Crawl for better performance
   ARCHIVE_DEFAULT_SOURCE=common_crawl
   ```

2. **Optimize Query Parameters:**
   ```bash
   # Smaller page sizes for faster responses
   WAYBACK_MACHINE_PAGE_SIZE=2000
   COMMON_CRAWL_PAGE_SIZE=2000
   ```

3. **Enable Immediate Fallback:**
   ```bash
   # Faster fallback for better user experience
   ARCHIVE_DEFAULT_FALLBACK_STRATEGY=immediate
   ARCHIVE_FALLBACK_DELAY=0.5
   ```

## Log Analysis

### Log Message Patterns

#### Successful Queries
```
INFO - Archive query for example.com using source order: ['wayback_machine', 'common_crawl']
INFO - Querying wayback_machine for domain example.com (primary)
INFO - Successfully retrieved 1234 records from wayback_machine in 15.23s
```

#### Fallback Events
```
WARNING - Query failed for wayback_machine: wayback_522_timeout - 522 Connection timeout
INFO - Attempting fallback to common_crawl after 1.0s delay
INFO - Querying common_crawl for domain example.com (fallback)
INFO - Successfully retrieved 1156 records from common_crawl in 8.45s
```

#### Circuit Breaker Events
```
WARNING - Circuit breaker for wayback_machine exceeded failure threshold (5/5)
INFO - Circuit breaker for wayback_machine opened, timeout: 90s
ERROR - Circuit breaker open for wayback_machine
INFO - Circuit breaker for wayback_machine attempting half-open test
INFO - Circuit breaker for wayback_machine closed after successful test
```

### Log Analysis Scripts

#### Error Pattern Analysis
```bash
#!/bin/bash
# analyze_archive_errors.sh

LOG_FILE="/var/log/chrono-scraper/backend.log"
DATE=$(date '+%Y-%m-%d')

echo "Archive Source Error Analysis for $DATE"
echo "=========================================="

echo "522 Timeout Errors:"
grep "$DATE" "$LOG_FILE" | grep -i "522" | wc -l

echo "Rate Limit Errors:"  
grep "$DATE" "$LOG_FILE" | grep -i "rate limit" | wc -l

echo "Connection Errors:"
grep "$DATE" "$LOG_FILE" | grep -i "connection.*error\|connection.*timeout" | wc -l

echo "Circuit Breaker Events:"
grep "$DATE" "$LOG_FILE" | grep -i "circuit breaker.*open" | wc -l

echo "Fallback Events:"
grep "$DATE" "$LOG_FILE" | grep -i "attempting fallback" | wc -l
```

#### Performance Analysis
```bash
#!/bin/bash
# analyze_archive_performance.sh

LOG_FILE="/var/log/chrono-scraper/backend.log"
DATE=$(date '+%Y-%m-%d')

echo "Archive Source Performance Analysis for $DATE"
echo "=============================================="

# Extract response times
grep "$DATE" "$LOG_FILE" | \
grep "Successfully retrieved.*records.*in.*s" | \
sed -E 's/.*in ([0-9.]+)s$/\1/' | \
awk '{
    count++
    sum += $1
    if ($1 > max) max = $1
    if (min == "" || $1 < min) min = $1
}
END {
    if (count > 0) {
        printf "Response Time Statistics:\n"
        printf "  Count: %d\n", count
        printf "  Average: %.2fs\n", sum/count
        printf "  Min: %.2fs\n", min
        printf "  Max: %.2fs\n", max
    }
}'
```

### Structured Logging Analysis

Use structured logging for better analysis:

```python
import structlog
import json

logger = structlog.get_logger(__name__)

# In archive query function
logger.info(
    "archive_query_started",
    domain=domain,
    from_date=from_date,
    to_date=to_date,
    archive_source=archive_source,
    fallback_enabled=fallback_enabled
)

logger.info(
    "archive_query_completed", 
    domain=domain,
    successful_source=successful_source,
    fallback_used=fallback_used,
    records_count=len(records),
    duration_seconds=duration,
    attempts=len(stats.get('attempts', []))
)
```

Analyze structured logs with jq:

```bash
# Parse JSON logs for archive source metrics
cat backend.log | jq -r 'select(.event == "archive_query_completed") | [.domain, .successful_source, .duration_seconds, .records_count] | @csv'

# Calculate average response time by source
cat backend.log | jq -r 'select(.event == "archive_query_completed") | "\(.successful_source) \(.duration_seconds)"' | awk '
{
    source = $1
    duration = $2
    count[source]++
    sum[source] += duration
}
END {
    for (s in count) {
        printf "%s: %.2fs average (%d queries)\n", s, sum[s]/count[s], count[s]
    }
}'
```

## Diagnostic Tools

### Archive Source Health Check Tool

```python
#!/usr/bin/env python
"""
Comprehensive archive source diagnostic tool
"""

import asyncio
import json
import sys
from datetime import datetime
from app.services.archive_service_router import ArchiveServiceRouter
from app.services.wayback_machine import CDXAPIClient
from app.services.common_crawl_service import CommonCrawlService

async def diagnose_archive_sources():
    """Run comprehensive diagnostics on archive sources"""
    
    print("🔍 Archive Sources Diagnostic Tool")
    print("=" * 50)
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "tests": [],
        "overall_status": "unknown"
    }
    
    # Test 1: Individual source connectivity
    print("\n1. Testing Individual Source Connectivity")
    print("-" * 40)
    
    # Test Wayback Machine
    try:
        async with CDXAPIClient() as client:
            records, stats = await client.fetch_cdx_records_simple(
                domain_name="example.com",
                from_date="20240101",
                to_date="20240131",
                page_size=10
            )
        
        wb_result = {
            "source": "wayback_machine",
            "status": "success",
            "records": len(records),
            "response_time": stats.get("total_duration", 0),
            "error": None
        }
        print("✓ Wayback Machine: Connected successfully")
        
    except Exception as e:
        wb_result = {
            "source": "wayback_machine", 
            "status": "failed",
            "records": 0,
            "response_time": 0,
            "error": str(e)
        }
        print(f"❌ Wayback Machine: {e}")
    
    results["tests"].append(wb_result)
    
    # Test Common Crawl
    try:
        async with CommonCrawlService() as service:
            records, stats = await service.fetch_cdx_records_simple(
                domain_name="example.com",
                from_date="20240101", 
                to_date="20240131",
                page_size=10
            )
        
        cc_result = {
            "source": "common_crawl",
            "status": "success", 
            "records": len(records),
            "response_time": stats.get("total_duration", 0),
            "error": None
        }
        print("✓ Common Crawl: Connected successfully")
        
    except Exception as e:
        cc_result = {
            "source": "common_crawl",
            "status": "failed",
            "records": 0,
            "response_time": 0,
            "error": str(e)
        }
        print(f"❌ Common Crawl: {e}")
    
    results["tests"].append(cc_result)
    
    # Test 2: Archive router functionality
    print("\n2. Testing Archive Router")
    print("-" * 40)
    
    try:
        router = ArchiveServiceRouter()
        
        # Test hybrid mode
        records, stats = await router.query_archive(
            domain="example.com",
            from_date="20240101",
            to_date="20240131", 
            project_config={"archive_source": "hybrid", "fallback_enabled": True}
        )
        
        router_result = {
            "test": "archive_router_hybrid",
            "status": "success",
            "records": len(records),
            "successful_source": stats.get("successful_source"),
            "fallback_used": stats.get("fallback_used", False),
            "total_duration": stats.get("total_duration", 0),
            "error": None
        }
        print(f"✓ Archive Router: Retrieved {len(records)} records")
        print(f"  Source: {stats.get('successful_source')}")
        print(f"  Fallback: {stats.get('fallback_used', False)}")
        
    except Exception as e:
        router_result = {
            "test": "archive_router_hybrid",
            "status": "failed",
            "records": 0,
            "successful_source": None,
            "fallback_used": False,
            "total_duration": 0,
            "error": str(e)
        }
        print(f"❌ Archive Router: {e}")
    
    results["tests"].append(router_result)
    
    # Test 3: Circuit breaker status
    print("\n3. Circuit Breaker Status")
    print("-" * 40)
    
    try:
        health_status = router.get_health_status()
        cb_status = {
            "test": "circuit_breakers",
            "status": "success",
            "wayback_state": health_status["sources"]["wayback_machine"]["circuit_breaker_state"],
            "common_crawl_state": health_status["sources"]["common_crawl"]["circuit_breaker_state"],
            "overall_health": health_status["overall_status"],
            "error": None
        }
        
        print(f"✓ Circuit Breakers:")
        print(f"  Wayback Machine: {cb_status['wayback_state']}")
        print(f"  Common Crawl: {cb_status['common_crawl_state']}")
        print(f"  Overall Health: {cb_status['overall_health']}")
        
    except Exception as e:
        cb_status = {
            "test": "circuit_breakers",
            "status": "failed",
            "error": str(e)
        }
        print(f"❌ Circuit Breakers: {e}")
    
    results["tests"].append(cb_status)
    
    # Test 4: Performance metrics
    print("\n4. Performance Metrics")
    print("-" * 40)
    
    try:
        metrics = router.get_performance_metrics()
        perf_result = {
            "test": "performance_metrics",
            "status": "success", 
            "sources": {}
        }
        
        for source, data in metrics["sources"].items():
            perf_result["sources"][source] = {
                "total_queries": data["total_queries"],
                "success_rate": data["success_rate"],
                "avg_response_time": data["avg_response_time"],
                "is_healthy": data["is_healthy"]
            }
            
            print(f"✓ {source}:")
            print(f"    Queries: {data['total_queries']}")
            print(f"    Success Rate: {data['success_rate']:.1f}%")
            print(f"    Avg Response: {data['avg_response_time']:.2f}s")
            print(f"    Healthy: {data['is_healthy']}")
        
    except Exception as e:
        perf_result = {
            "test": "performance_metrics",
            "status": "failed",
            "error": str(e)
        }
        print(f"❌ Performance Metrics: {e}")
    
    results["tests"].append(perf_result)
    
    # Determine overall status
    failed_tests = [t for t in results["tests"] if t.get("status") == "failed"]
    if not failed_tests:
        results["overall_status"] = "healthy"
    elif len(failed_tests) < len(results["tests"]):
        results["overall_status"] = "degraded"
    else:
        results["overall_status"] = "unhealthy"
    
    print(f"\n🏁 Overall Status: {results['overall_status'].upper()}")
    
    # Save results to file
    with open(f"/tmp/archive_diagnostics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    return results["overall_status"] == "healthy"

if __name__ == "__main__":
    success = asyncio.run(diagnose_archive_sources())
    sys.exit(0 if success else 1)
```

### Network Connectivity Test Tool

```bash
#!/bin/bash
# test_archive_connectivity.sh

echo "🌐 Archive Source Network Connectivity Test"
echo "==========================================="

# Test Wayback Machine
echo "Testing Wayback Machine..."
echo "CDX API:"
curl -s -I "https://web.archive.org/cdx/search/cdx?url=example.com&output=json&limit=1" | head -1
echo "Main Site:"
curl -s -I "https://web.archive.org" | head -1

echo ""

# Test Common Crawl  
echo "Testing Common Crawl..."
echo "Index API:"
curl -s -I "https://index.commoncrawl.org/CC-MAIN-2024-10-cdx?url=example.com&output=json&limit=1" | head -1
echo "Main Site:"
curl -s -I "https://commoncrawl.org" | head -1

echo ""

# Test DNS resolution
echo "DNS Resolution:"
nslookup web.archive.org | grep -A2 "Name:"
nslookup index.commoncrawl.org | grep -A2 "Name:"

echo ""

# Test with timeout
echo "Connection Speed Test:"
time curl -s -o /dev/null "https://web.archive.org/cdx/search/cdx?url=example.com&output=json&limit=10" && echo "Wayback Machine: OK" || echo "Wayback Machine: SLOW/FAILED"

time curl -s -o /dev/null "https://index.commoncrawl.org/CC-MAIN-2024-10-cdx?url=example.com&output=json&limit=10" && echo "Common Crawl: OK" || echo "Common Crawl: SLOW/FAILED"
```

## Dashboard Configuration

### Grafana Dashboard JSON

Complete Grafana dashboard configuration for archive sources:

```json
{
  "dashboard": {
    "id": null,
    "title": "Archive Sources Monitoring",
    "tags": ["chrono-scraper", "archive-sources"],
    "style": "dark",
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "Archive Source Success Rates",
        "type": "stat",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "min": 0,
            "max": 100,
            "thresholds": {
              "steps": [
                {"color": "red", "value": 0},
                {"color": "yellow", "value": 80},
                {"color": "green", "value": 95}
              ]
            }
          }
        },
        "options": {
          "orientation": "horizontal",
          "reduceOptions": {"calcs": ["lastNotNull"]},
          "textMode": "auto"
        },
        "targets": [
          {
            "expr": "rate(archive_queries_total{status=\"success\"}[5m]) / rate(archive_queries_total[5m]) * 100",
            "legendFormat": "{{source}}"
          }
        ]
      },
      {
        "id": 2,
        "title": "Query Response Times",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
        "xAxis": {"show": true},
        "yAxis": {"unit": "s", "min": 0},
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(archive_query_duration_seconds_bucket[5m]))",
            "legendFormat": "{{source}} p95"
          },
          {
            "expr": "histogram_quantile(0.50, rate(archive_query_duration_seconds_bucket[5m]))",
            "legendFormat": "{{source}} p50"
          }
        ]
      },
      {
        "id": 3,
        "title": "Circuit Breaker States", 
        "type": "stat",
        "gridPos": {"h": 4, "w": 8, "x": 0, "y": 8},
        "fieldConfig": {
          "defaults": {
            "mappings": [
              {"options": {"0": {"text": "CLOSED", "color": "green"}}},
              {"options": {"1": {"text": "OPEN", "color": "red"}}},
              {"options": {"2": {"text": "HALF_OPEN", "color": "yellow"}}}
            ]
          }
        },
        "targets": [
          {
            "expr": "circuit_breaker_state",
            "legendFormat": "{{source}}"
          }
        ]
      },
      {
        "id": 4,
        "title": "Error Rate by Type",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 8, "y": 8},
        "yAxis": {"unit": "reqps"},
        "targets": [
          {
            "expr": "rate(archive_errors_total[5m])",
            "legendFormat": "{{source}} - {{error_type}}"
          }
        ]
      },
      {
        "id": 5,
        "title": "Fallback Events",
        "type": "graph", 
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 16},
        "yAxis": {"unit": "ops"},
        "targets": [
          {
            "expr": "rate(archive_fallback_events_total[5m])",
            "legendFormat": "{{from_source}} → {{to_source}}"
          }
        ]
      },
      {
        "id": 6,
        "title": "Query Volume",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 16},
        "yAxis": {"unit": "reqps"},
        "targets": [
          {
            "expr": "rate(archive_queries_total[5m])",
            "legendFormat": "{{source}} - {{status}}"
          }
        ]
      }
    ],
    "time": {"from": "now-1h", "to": "now"},
    "refresh": "30s"
  }
}
```

## Incident Response

### Incident Response Playbook

#### Severity Levels

1. **Critical (P1)**: All archive sources failing
2. **High (P2)**: Single archive source down, no fallback
3. **Medium (P3)**: Degraded performance, fallbacks working
4. **Low (P4)**: Minor issues, monitoring alerts only

#### Response Procedures

##### P1 - All Archive Sources Failing

**Immediate Actions (0-15 minutes):**
1. Check overall system health and network connectivity
2. Verify external archive service status pages
3. Review recent deployments or configuration changes
4. Enable maintenance mode if necessary

**Investigation Steps (15-60 minutes):**
1. Run diagnostic tool: `docker compose exec backend python /scripts/diagnose_archive_sources.py`
2. Check application logs for error patterns
3. Verify DNS resolution for archive domains
4. Test direct API connectivity with curl

**Resolution Steps:**
1. If network issue: Fix connectivity, restart services
2. If configuration issue: Rollback configuration, restart
3. If external service issue: Wait for service recovery, monitor
4. If code issue: Rollback deployment, investigate

##### P2 - Single Archive Source Down

**Immediate Actions (0-30 minutes):**
1. Verify fallback is working correctly
2. Check if circuit breaker is functioning
3. Monitor fallback success rates

**Investigation Steps:**
1. Focus diagnostics on failing source
2. Check source-specific error patterns
3. Test individual source connectivity

**Resolution Steps:**
1. Adjust circuit breaker thresholds if needed
2. Switch default source to working alternative
3. Monitor for automatic recovery

##### P3 - Performance Degradation

**Investigation Steps (within 1 hour):**
1. Analyze response time trends
2. Check for resource constraints (CPU, memory, network)
3. Review query patterns and volumes

**Resolution Steps:**
1. Optimize query parameters (page sizes, timeouts)
2. Implement additional fallback strategies
3. Scale resources if needed

### Post-Incident Review

After resolving incidents, conduct post-incident reviews:

#### Review Template

```markdown
# Archive Sources Incident Review

**Incident ID:** ASI-YYYY-MM-DD-NNN
**Date:** YYYY-MM-DD
**Duration:** X hours Y minutes
**Severity:** P1/P2/P3/P4

## Summary
Brief description of what happened and impact.

## Timeline
- **HH:MM** - Issue detected
- **HH:MM** - Investigation started
- **HH:MM** - Root cause identified
- **HH:MM** - Resolution implemented
- **HH:MM** - Service fully restored

## Root Cause
Detailed explanation of the root cause.

## Impact Assessment
- **Users Affected:** Number/percentage of users impacted
- **Projects Affected:** Number of projects unable to scrape
- **Data Loss:** Any data loss or corruption
- **SLA Impact:** Effect on service level agreements

## Resolution
Steps taken to resolve the issue.

## Action Items
- [ ] Improve monitoring for early detection
- [ ] Update documentation
- [ ] Implement preventive measures
- [ ] Review and update alerting thresholds

## Lessons Learned
Key takeaways and improvements for future incidents.
```

This comprehensive monitoring and troubleshooting guide provides the foundation for maintaining reliable archive source operations in production environments.