# Archive Sources Configuration Guide

## Table of Contents
- [Environment Variables](#environment-variables)
- [System Configuration](#system-configuration)
- [Project-Level Configuration](#project-level-configuration)
- [Deployment Considerations](#deployment-considerations)
- [Performance Tuning](#performance-tuning)
- [Security Configuration](#security-configuration)
- [High Availability Setup](#high-availability-setup)
- [Troubleshooting Configuration Issues](#troubleshooting-configuration-issues)

## Environment Variables

### Archive Source Defaults

Set system-wide defaults for new projects:

```bash
# Default archive source for new projects
ARCHIVE_DEFAULT_SOURCE=hybrid

# Default fallback behavior
ARCHIVE_DEFAULT_FALLBACK_ENABLED=true

# Default fallback strategy
ARCHIVE_DEFAULT_FALLBACK_STRATEGY=circuit_breaker
```

**Values:**
- `ARCHIVE_DEFAULT_SOURCE`: `wayback_machine`, `common_crawl`, `hybrid`
- `ARCHIVE_DEFAULT_FALLBACK_ENABLED`: `true`, `false`
- `ARCHIVE_DEFAULT_FALLBACK_STRATEGY`: `immediate`, `retry_then_fallback`, `circuit_breaker`

### Wayback Machine Configuration

Configure Wayback Machine specific settings:

```bash
# Connection timeout (seconds)
WAYBACK_MACHINE_TIMEOUT=120

# Maximum retry attempts
WAYBACK_MACHINE_MAX_RETRIES=3

# CDX records per page
WAYBACK_MACHINE_PAGE_SIZE=5000

# Maximum pages to fetch (0=unlimited)
WAYBACK_MACHINE_MAX_PAGES=0

# Include PDF and document attachments
WAYBACK_MACHINE_INCLUDE_ATTACHMENTS=true

# User agent for requests
WAYBACK_MACHINE_USER_AGENT="Chrono-Scraper/2.0 (Research Tool)"
```

**Recommended Values by Environment:**

| Environment | Timeout | Max Retries | Page Size | Max Pages |
|-------------|---------|-------------|-----------|-----------|
| Development | 60 | 2 | 1000 | 10 |
| Staging | 120 | 3 | 5000 | 0 |
| Production | 120 | 3 | 5000 | 0 |

### Common Crawl Configuration

Configure Common Crawl specific settings:

```bash
# Connection timeout (seconds) - longer for Common Crawl
COMMON_CRAWL_TIMEOUT=180

# Maximum retry attempts
COMMON_CRAWL_MAX_RETRIES=5

# CDX records per page
COMMON_CRAWL_PAGE_SIZE=5000

# Maximum pages to fetch (0=unlimited)
COMMON_CRAWL_MAX_PAGES=0

# Include PDF and document attachments
COMMON_CRAWL_INCLUDE_ATTACHMENTS=true

# Thread pool size for cdx_toolkit
COMMON_CRAWL_THREAD_POOL_SIZE=4

# Maximum timeout for cdx_toolkit operations
COMMON_CRAWL_CDX_TOOLKIT_TIMEOUT=300
```

**Performance Tuning:**
- **Higher timeout values** for Common Crawl due to potentially slower responses
- **More retries** as Common Crawl is generally more reliable
- **Larger thread pool** for better concurrency with cdx_toolkit

### Circuit Breaker Configuration

Configure circuit breaker behavior for each archive source:

```bash
# Wayback Machine circuit breaker
WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
WAYBACK_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=3
WAYBACK_CIRCUIT_BREAKER_TIMEOUT=90
WAYBACK_CIRCUIT_BREAKER_MAX_TIMEOUT=600
WAYBACK_CIRCUIT_BREAKER_EXPONENTIAL_BACKOFF=true

# Common Crawl circuit breaker
COMMON_CRAWL_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
COMMON_CRAWL_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=3
COMMON_CRAWL_CIRCUIT_BREAKER_TIMEOUT=90
COMMON_CRAWL_CIRCUIT_BREAKER_MAX_TIMEOUT=600
COMMON_CRAWL_CIRCUIT_BREAKER_EXPONENTIAL_BACKOFF=true
```

**Configuration Guidelines:**
- **Failure Threshold**: Number of consecutive failures before opening circuit
- **Success Threshold**: Number of consecutive successes to close circuit  
- **Timeout**: Initial timeout before retrying failed service
- **Max Timeout**: Maximum timeout with exponential backoff
- **Exponential Backoff**: Whether to increase timeout on repeated failures

### Fallback Configuration

Configure fallback behavior between archive sources:

```bash
# Fallback delay between source attempts (seconds)
ARCHIVE_FALLBACK_DELAY=1.0

# Use exponential backoff for multiple fallbacks
ARCHIVE_FALLBACK_EXPONENTIAL_BACKOFF=true

# Maximum fallback delay (seconds)
ARCHIVE_FALLBACK_MAX_DELAY=30.0

# Enable metrics collection for routing decisions
ARCHIVE_METRICS_ENABLED=true

# Maximum query history to keep for metrics
ARCHIVE_METRICS_HISTORY_SIZE=1000
```

## System Configuration

### Docker Compose Configuration

Add environment variables to your `docker-compose.yml`:

```yaml
services:
  backend:
    environment:
      # Archive source defaults
      - ARCHIVE_DEFAULT_SOURCE=hybrid
      - ARCHIVE_DEFAULT_FALLBACK_ENABLED=true
      
      # Wayback Machine settings
      - WAYBACK_MACHINE_TIMEOUT=120
      - WAYBACK_MACHINE_MAX_RETRIES=3
      - WAYBACK_MACHINE_PAGE_SIZE=5000
      
      # Common Crawl settings  
      - COMMON_CRAWL_TIMEOUT=180
      - COMMON_CRAWL_MAX_RETRIES=5
      - COMMON_CRAWL_PAGE_SIZE=5000
      - COMMON_CRAWL_THREAD_POOL_SIZE=4
      
      # Circuit breaker settings
      - WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
      - COMMON_CRAWL_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
      
      # Fallback settings
      - ARCHIVE_FALLBACK_DELAY=1.0
      - ARCHIVE_FALLBACK_MAX_DELAY=30.0
```

### .env File Configuration

Create a `.env` file with archive source settings:

```bash
# Archive Sources Configuration
ARCHIVE_DEFAULT_SOURCE=hybrid
ARCHIVE_DEFAULT_FALLBACK_ENABLED=true
ARCHIVE_DEFAULT_FALLBACK_STRATEGY=circuit_breaker

# Wayback Machine
WAYBACK_MACHINE_TIMEOUT=120
WAYBACK_MACHINE_MAX_RETRIES=3
WAYBACK_MACHINE_PAGE_SIZE=5000
WAYBACK_MACHINE_MAX_PAGES=0
WAYBACK_MACHINE_INCLUDE_ATTACHMENTS=true

# Common Crawl  
COMMON_CRAWL_TIMEOUT=180
COMMON_CRAWL_MAX_RETRIES=5
COMMON_CRAWL_PAGE_SIZE=5000
COMMON_CRAWL_MAX_PAGES=0
COMMON_CRAWL_INCLUDE_ATTACHMENTS=true
COMMON_CRAWL_THREAD_POOL_SIZE=4

# Circuit Breakers
WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
WAYBACK_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=3
WAYBACK_CIRCUIT_BREAKER_TIMEOUT=90

COMMON_CRAWL_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
COMMON_CRAWL_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=3
COMMON_CRAWL_CIRCUIT_BREAKER_TIMEOUT=90

# Fallback Configuration
ARCHIVE_FALLBACK_DELAY=1.0
ARCHIVE_FALLBACK_EXPONENTIAL_BACKOFF=true
ARCHIVE_FALLBACK_MAX_DELAY=30.0

# Metrics
ARCHIVE_METRICS_ENABLED=true
ARCHIVE_METRICS_HISTORY_SIZE=1000
```

### Configuration Loading

The system loads configuration in this order (later overrides earlier):

1. **Hard-coded defaults** in Python classes
2. **Environment variables** from system/container
3. **Project-specific configuration** from database
4. **Runtime adjustments** based on performance metrics

## Project-Level Configuration

Projects can override system defaults with specific archive source configurations:

### Basic Project Configuration

When creating a project, specify archive source preferences:

```json
{
  "name": "Historical Analysis Project",
  "description": "Research project focusing on government websites",
  "archive_source": "wayback_machine",
  "fallback_enabled": true,
  "domains": [
    {
      "domain_name": "whitehouse.gov",
      "match_type": "domain"
    }
  ]
}
```

### Advanced Project Configuration

For fine-grained control, use the `archive_config` field:

```json
{
  "name": "Performance Critical Project", 
  "archive_source": "hybrid",
  "fallback_enabled": true,
  "archive_config": {
    "fallback_strategy": "immediate",
    "fallback_delay_seconds": 0.5,
    "exponential_backoff": false,
    "max_fallback_delay": 10.0,
    
    "wayback_machine": {
      "timeout_seconds": 60,
      "max_retries": 2,
      "page_size": 2000,
      "max_pages": 20,
      "include_attachments": false,
      "priority": 2
    },
    
    "common_crawl": {
      "timeout_seconds": 120,
      "max_retries": 3,
      "page_size": 5000,
      "max_pages": 50,
      "include_attachments": true,
      "priority": 1
    }
  }
}
```

### Configuration Templates

Create reusable configuration templates for common scenarios:

#### Historical Research Template
```json
{
  "archive_source": "wayback_machine",
  "fallback_enabled": true,
  "archive_config": {
    "wayback_machine": {
      "timeout_seconds": 180,
      "max_retries": 5,
      "page_size": 5000,
      "include_attachments": true
    }
  }
}
```

#### Performance-First Template
```json
{
  "archive_source": "common_crawl",
  "fallback_enabled": true,
  "archive_config": {
    "common_crawl": {
      "timeout_seconds": 90,
      "max_retries": 3,
      "page_size": 10000
    },
    "fallback_strategy": "immediate"
  }
}
```

#### Maximum Reliability Template  
```json
{
  "archive_source": "hybrid",
  "fallback_enabled": true,
  "archive_config": {
    "fallback_strategy": "circuit_breaker",
    "fallback_delay_seconds": 2.0,
    "wayback_machine": {
      "priority": 1,
      "timeout_seconds": 120,
      "max_retries": 3
    },
    "common_crawl": {
      "priority": 2,
      "timeout_seconds": 180,
      "max_retries": 5
    }
  }
}
```

## Deployment Considerations

### Resource Requirements

#### Memory Requirements

| Component | Base Memory | Per-Project | Per-Query |
|-----------|-------------|-------------|-----------|
| Archive Router | 10MB | 1MB | 5KB |
| Circuit Breakers | 2MB | 0.1MB | 0.1KB |
| Metrics Storage | 5MB | 2MB | 1KB |
| **Total Overhead** | **17MB** | **3.1MB** | **6.1KB** |

#### CPU Requirements

Archive source routing adds minimal CPU overhead:
- **Routing Logic**: <1% CPU per query
- **Metrics Collection**: <0.5% CPU per query
- **Circuit Breaker Logic**: <0.1% CPU per query

#### Network Requirements

- **Outbound HTTPS**: Access to archive APIs
  - Wayback Machine: `web.archive.org:443`
  - Common Crawl: `commoncrawl.org:443` and `index.commoncrawl.org:443`
- **No inbound requirements** for archive functionality
- **Bandwidth**: Variable based on query volume and result sizes

### Container Configuration

#### Production Container Limits

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'
    environment:
      # Conservative timeouts for production stability
      - WAYBACK_MACHINE_TIMEOUT=90
      - COMMON_CRAWL_TIMEOUT=150
      
      # Aggressive circuit breakers for fast failure
      - WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD=3
      - COMMON_CRAWL_CIRCUIT_BREAKER_FAILURE_THRESHOLD=3
      
      # Quick fallback for user responsiveness
      - ARCHIVE_FALLBACK_DELAY=0.5
```

#### Development Container Configuration

```yaml
services:
  backend:
    environment:
      # Longer timeouts for debugging
      - WAYBACK_MACHINE_TIMEOUT=300
      - COMMON_CRAWL_TIMEOUT=300
      
      # More lenient circuit breakers
      - WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD=10
      - COMMON_CRAWL_CIRCUIT_BREAKER_FAILURE_THRESHOLD=10
      
      # Immediate fallback for testing
      - ARCHIVE_FALLBACK_DELAY=0.1
      - ARCHIVE_DEFAULT_FALLBACK_STRATEGY=immediate
```

### Network Configuration

#### Firewall Rules

Ensure outbound access to archive APIs:

```bash
# Allow HTTPS to Wayback Machine
iptables -A OUTPUT -p tcp -d web.archive.org --dport 443 -j ACCEPT

# Allow HTTPS to Common Crawl
iptables -A OUTPUT -p tcp -d commoncrawl.org --dport 443 -j ACCEPT
iptables -A OUTPUT -p tcp -d index.commoncrawl.org --dport 443 -j ACCEPT

# Allow DNS resolution
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
```

#### Proxy Configuration

If using a corporate proxy, configure HTTP client settings:

```bash
# HTTP proxy settings
HTTP_PROXY=http://proxy.company.com:8080
HTTPS_PROXY=http://proxy.company.com:8080
NO_PROXY=localhost,127.0.0.1

# Archive-specific proxy settings (optional)
WAYBACK_MACHINE_PROXY=http://proxy.company.com:8080
COMMON_CRAWL_PROXY=http://proxy.company.com:8080
```

## Performance Tuning

### Archive Source Optimization

#### Wayback Machine Optimization

```bash
# Optimize for reliability over speed
WAYBACK_MACHINE_TIMEOUT=150          # Longer timeout
WAYBACK_MACHINE_MAX_RETRIES=5        # More retries  
WAYBACK_MACHINE_PAGE_SIZE=2000       # Smaller pages to reduce timeout risk

# Circuit breaker for 522 errors
WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD=3
WAYBACK_CIRCUIT_BREAKER_TIMEOUT=120  # 2 minute timeout for 522 errors
```

#### Common Crawl Optimization

```bash
# Optimize for performance
COMMON_CRAWL_TIMEOUT=90              # Shorter timeout
COMMON_CRAWL_MAX_RETRIES=3           # Fewer retries needed
COMMON_CRAWL_PAGE_SIZE=10000         # Larger pages for efficiency

# More lenient circuit breaker
COMMON_CRAWL_CIRCUIT_BREAKER_FAILURE_THRESHOLD=7
COMMON_CRAWL_CIRCUIT_BREAKER_TIMEOUT=60
```

### Fallback Strategy Optimization

#### For Maximum Speed
```bash
ARCHIVE_DEFAULT_FALLBACK_STRATEGY=immediate
ARCHIVE_FALLBACK_DELAY=0.5
ARCHIVE_FALLBACK_EXPONENTIAL_BACKOFF=false
```

#### For Maximum Reliability
```bash
ARCHIVE_DEFAULT_FALLBACK_STRATEGY=circuit_breaker
ARCHIVE_FALLBACK_DELAY=2.0
ARCHIVE_FALLBACK_EXPONENTIAL_BACKOFF=true
ARCHIVE_FALLBACK_MAX_DELAY=60.0
```

#### For Balanced Performance
```bash
ARCHIVE_DEFAULT_FALLBACK_STRATEGY=retry_then_fallback
ARCHIVE_FALLBACK_DELAY=1.0
ARCHIVE_FALLBACK_EXPONENTIAL_BACKOFF=true
ARCHIVE_FALLBACK_MAX_DELAY=30.0
```

### Memory Optimization

#### Metrics History Tuning

```bash
# Reduce memory usage
ARCHIVE_METRICS_HISTORY_SIZE=100     # Keep fewer historical metrics

# Disable metrics in memory-constrained environments
ARCHIVE_METRICS_ENABLED=false
```

#### Connection Pool Tuning

```bash
# Optimize HTTP connection pools
COMMON_CRAWL_THREAD_POOL_SIZE=2      # Reduce for memory-constrained systems
WAYBACK_MACHINE_CONNECTION_POOL_SIZE=5
COMMON_CRAWL_CONNECTION_POOL_SIZE=5
```

### Monitoring-Based Optimization

Enable detailed metrics to inform optimization decisions:

```bash
# Enable comprehensive metrics
ARCHIVE_METRICS_ENABLED=true
ARCHIVE_METRICS_HISTORY_SIZE=1000

# Enable performance logging
ARCHIVE_PERFORMANCE_LOGGING=true
ARCHIVE_LOG_LEVEL=INFO
```

Review metrics regularly and adjust configuration based on:
- **Success rates** by source
- **Average response times** 
- **Error patterns** and frequency
- **Circuit breaker activation** frequency

## Security Configuration

### API Key Management

While current archive sources don't require API keys, prepare for future sources that might:

```bash
# Future-proofing for authenticated archive sources
ARCHIVE_API_KEYS_VAULT_PATH=/secrets/archive-keys
ARCHIVE_API_KEY_ROTATION_INTERVAL=30d

# If using HashiCorp Vault
VAULT_ADDR=https://vault.company.com
VAULT_TOKEN_PATH=/var/secrets/vault-token
```

### Access Control

#### Network Security

```bash
# Restrict archive access to specific network interfaces
ARCHIVE_BIND_INTERFACE=eth0
ARCHIVE_ALLOWED_NETWORKS=10.0.0.0/8,172.16.0.0/12

# Enable request signing (future feature)
ARCHIVE_REQUEST_SIGNING=true
ARCHIVE_SIGNING_KEY_PATH=/secrets/archive-signing.key
```

#### User Agent and Rate Limiting

```bash
# Responsible usage configuration
WAYBACK_MACHINE_USER_AGENT="Chrono-Scraper/2.0 (Contact: admin@yourorg.com)"
COMMON_CRAWL_USER_AGENT="Chrono-Scraper/2.0 (Contact: admin@yourorg.com)"

# Built-in rate limiting
ARCHIVE_RATE_LIMIT_REQUESTS_PER_MINUTE=30
ARCHIVE_RATE_LIMIT_BURST_SIZE=10
```

### Audit and Compliance

```bash
# Enable audit logging
ARCHIVE_AUDIT_LOGGING=true
ARCHIVE_AUDIT_LOG_PATH=/logs/archive-audit.log
ARCHIVE_AUDIT_LOG_RETENTION=90d

# Compliance settings
ARCHIVE_DATA_RETENTION_POLICY=365d
ARCHIVE_USAGE_REPORTING=true
ARCHIVE_GDPR_COMPLIANCE=true
```

## High Availability Setup

### Multi-Instance Configuration

For high availability deployments, configure shared state management:

#### Redis-Based Circuit Breaker State

```bash
# Shared circuit breaker state
CIRCUIT_BREAKER_BACKEND=redis
CIRCUIT_BREAKER_REDIS_URL=redis://redis-cluster:6379/1
CIRCUIT_BREAKER_REDIS_KEY_PREFIX=chrono:circuit_breakers

# Circuit breaker clustering
CIRCUIT_BREAKER_CLUSTER_MODE=true
CIRCUIT_BREAKER_CLUSTER_SYNC_INTERVAL=10s
```

#### Database-Backed Metrics

```bash
# Store metrics in database for persistence
ARCHIVE_METRICS_BACKEND=postgres
ARCHIVE_METRICS_TABLE_PREFIX=archive_metrics
ARCHIVE_METRICS_RETENTION_DAYS=30
```

### Load Balancer Configuration

Configure load balancers to handle archive source health:

#### HAProxy Configuration
```haproxy
backend chrono_backend
    balance roundrobin
    option httpchk GET /api/v1/health
    http-check expect status 200
    
    # Health check includes archive source status
    http-check send-state
    
    server backend1 backend1:8000 check inter 30s
    server backend2 backend2:8000 check inter 30s
    server backend3 backend3:8000 check inter 30s
```

#### NGINX Configuration
```nginx
upstream chrono_backend {
    server backend1:8000 max_fails=3 fail_timeout=30s;
    server backend2:8000 max_fails=3 fail_timeout=30s;
    server backend3:8000 max_fails=3 fail_timeout=30s;
}

location /health {
    proxy_pass http://chrono_backend/api/v1/health;
    proxy_set_header Host $host;
    health_check interval=30s fails=3 passes=2;
}
```

### Disaster Recovery

#### Configuration Backup

```bash
# Backup environment configuration
ARCHIVE_CONFIG_BACKUP_ENABLED=true
ARCHIVE_CONFIG_BACKUP_S3_BUCKET=chrono-config-backups
ARCHIVE_CONFIG_BACKUP_INTERVAL=daily
```

#### Metrics Export

```bash
# Export metrics for disaster recovery
ARCHIVE_METRICS_EXPORT_ENABLED=true
ARCHIVE_METRICS_EXPORT_FORMAT=prometheus
ARCHIVE_METRICS_EXPORT_INTERVAL=hourly
ARCHIVE_METRICS_EXPORT_S3_BUCKET=chrono-metrics-backups
```

## Troubleshooting Configuration Issues

### Common Configuration Problems

#### 1. Archive Sources Not Responding

**Symptoms:**
```
ERROR: All configured archive sources failed
ERROR: Circuit breaker open for wayback_machine
```

**Diagnosis:**
```bash
# Check network connectivity
curl -I https://web.archive.org
curl -I https://index.commoncrawl.org

# Check configuration
docker compose exec backend python -c "
from app.services.archive_service_router import ArchiveServiceRouter
router = ArchiveServiceRouter()
print(router.get_health_status())
"
```

**Solutions:**
- Verify network access to archive APIs
- Check if corporate firewall blocks archive domains
- Increase timeout values for slow networks
- Enable fallback mode if using single source

#### 2. High Memory Usage

**Symptoms:**
```
WARNING: High memory usage in archive router
ERROR: Out of memory during archive query
```

**Diagnosis:**
```bash
# Check metrics history size
grep ARCHIVE_METRICS_HISTORY_SIZE .env

# Monitor memory usage
docker stats chrono_backend
```

**Solutions:**
```bash
# Reduce metrics history
ARCHIVE_METRICS_HISTORY_SIZE=100

# Disable metrics in memory-constrained environments
ARCHIVE_METRICS_ENABLED=false

# Reduce thread pool sizes
COMMON_CRAWL_THREAD_POOL_SIZE=2
```

#### 3. Slow Performance

**Symptoms:**
```
WARNING: Archive query taking longer than expected
WARNING: Circuit breaker timeout reached
```

**Diagnosis:**
```bash
# Check current timeouts
env | grep -i timeout

# Check performance metrics
docker compose exec backend python -c "
from app.services.archive_service_router import ArchiveServiceRouter
router = ArchiveServiceRouter()
metrics = router.get_performance_metrics()
for source, data in metrics['sources'].items():
    print(f'{source}: {data[\"avg_response_time\"]}s avg, {data[\"success_rate\"]}% success')
"
```

**Solutions:**
- Switch to Common Crawl for better performance
- Reduce page sizes to avoid timeouts
- Enable immediate fallback strategy
- Increase timeout values for slow networks

#### 4. Circuit Breaker Stuck Open

**Symptoms:**
```
ERROR: Circuit breaker open for common_crawl
WARNING: No available archive sources
```

**Diagnosis:**
```bash
# Check circuit breaker status
docker compose exec backend python -c "
from app.services.circuit_breaker import circuit_registry
for name, breaker in circuit_registry.breakers.items():
    status = breaker.get_status()
    print(f'{name}: {status[\"state\"]} (failures: {status[\"failure_count\"]})')
"
```

**Solutions:**
- Wait for automatic recovery timeout
- Manually reset circuit breaker
- Adjust failure thresholds
- Check underlying network issues

### Configuration Validation

#### Validate Environment Variables

```python
#!/usr/bin/env python
"""Validate archive source configuration"""

import os
from app.services.archive_service_router import RoutingConfig
from app.core.config import settings

def validate_config():
    errors = []
    warnings = []
    
    # Check required settings
    if not hasattr(settings, 'WAYBACK_MACHINE_TIMEOUT'):
        errors.append("WAYBACK_MACHINE_TIMEOUT not configured")
    
    # Check timeout ranges
    if settings.WAYBACK_MACHINE_TIMEOUT and settings.WAYBACK_MACHINE_TIMEOUT < 30:
        warnings.append("WAYBACK_MACHINE_TIMEOUT is very low")
    
    # Check circuit breaker settings
    if settings.WAYBACK_CIRCUIT_BREAKER_FAILURE_THRESHOLD > 10:
        warnings.append("Circuit breaker failure threshold is high")
    
    # Create test router to validate configuration
    try:
        router = RoutingConfig()
        print("✓ Routing configuration is valid")
    except Exception as e:
        errors.append(f"Invalid routing configuration: {e}")
    
    # Report results
    if errors:
        print("❌ Configuration Errors:")
        for error in errors:
            print(f"  - {error}")
    
    if warnings:
        print("⚠️ Configuration Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    
    if not errors and not warnings:
        print("✓ Archive source configuration is optimal")
    
    return len(errors) == 0

if __name__ == "__main__":
    import sys
    valid = validate_config()
    sys.exit(0 if valid else 1)
```

#### Test Configuration

```bash
# Test archive source connectivity
docker compose exec backend python -c "
import asyncio
from app.services.archive_service_router import ArchiveServiceRouter

async def test_connectivity():
    router = ArchiveServiceRouter()
    try:
        records, stats = await router.query_archive(
            'example.com', '20240101', '20240131'
        )
        print(f'✓ Successfully retrieved {len(records)} records')
        print(f'✓ Primary source: {stats.get(\"successful_source\")}')
        if stats.get('fallback_used'):
            print('⚠️ Fallback was used')
    except Exception as e:
        print(f'❌ Archive connectivity test failed: {e}')

asyncio.run(test_connectivity())
"
```

### Debug Mode Configuration

Enable debug mode for detailed troubleshooting:

```bash
# Enable debug logging
ARCHIVE_DEBUG_MODE=true
ARCHIVE_LOG_LEVEL=DEBUG

# Enable request/response logging
ARCHIVE_LOG_REQUESTS=true
ARCHIVE_LOG_RESPONSES=true

# Enable performance profiling
ARCHIVE_PROFILE_QUERIES=true
ARCHIVE_PROFILE_OUTPUT_DIR=/tmp/archive_profiles
```