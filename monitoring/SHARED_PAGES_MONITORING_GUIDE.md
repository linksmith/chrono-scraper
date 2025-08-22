# Shared Pages Architecture Monitoring Guide

## Overview

This guide provides comprehensive monitoring and alerting for the Chrono Scraper shared pages architecture. The monitoring system tracks performance, health, business metrics, and provides alerting for critical issues.

## Architecture Components

### 1. Monitoring Services
- **MonitoringService**: Core metrics collection and health checks
- **PrometheusMetricsService**: Prometheus metrics generation
- **API Endpoints**: RESTful monitoring endpoints

### 2. Metrics Collection
- **Prometheus**: Time-series metrics collection
- **Grafana**: Visualization and dashboards
- **Alertmanager**: Alert routing and notifications

### 3. Key Tables Monitored
- `pages_v2`: Shared pages table
- `project_pages`: Project-page associations
- `cdx_page_registry`: CDX deduplication registry

## Key Metrics

### Core Architecture Metrics

| Metric | Description | Target Value | Critical Threshold |
|--------|-------------|--------------|-------------------|
| `chrono_shared_pages_total` | Total shared pages | Growing | N/A |
| `chrono_project_associations_total` | Total project associations | Growing | N/A |
| `chrono_cdx_registry_total` | Total CDX registry entries | Growing | N/A |
| `chrono_cdx_deduplication_rate_percent` | CDX deduplication efficiency | 60-80% | <50% |
| `chrono_sharing_efficiency_percent` | Page sharing efficiency | >40% | <20% |

### Performance Metrics

| Metric | Description | Target Value | Critical Threshold |
|--------|-------------|--------------|-------------------|
| `chrono_avg_processing_time_seconds` | Average page processing time | <60s | >300s |
| `chrono_processing_backlog` | Unprocessed pages count | <100 | >1000 |
| `chrono_indexing_backlog` | Unindexed pages count | <50 | >500 |
| `chrono_error_rate_24h_percent` | 24h error rate | <5% | >20% |
| `chrono_stuck_pages` | Pages stuck in processing | <10 | >50 |

### Business Impact Metrics

| Metric | Description | Target Value | Critical Threshold |
|--------|-------------|--------------|-------------------|
| `chrono_api_reduction_percentage_30d` | API call reduction | >50% | <30% |
| `chrono_storage_efficiency_percentage_30d` | Storage efficiency | >20% | <10% |
| `chrono_wayback_calls_saved_30d` | Estimated API calls saved | Growing | Declining |

## Health Checks

### 1. Component Health
```bash
# Check overall shared pages health
curl http://localhost:8000/api/v1/monitoring/shared-pages/health

# Check detailed system health
curl http://localhost:8000/api/v1/monitoring/health/detailed
```

### 2. Database Health
- Table accessibility checks
- Constraint violation detection
- Orphaned record identification

### 3. Processing Pipeline Health
- Backlog monitoring
- Stuck page detection
- Error rate tracking

## Dashboards

### 1. Shared Pages Overview
**File**: `monitoring/grafana/dashboards/shared-pages-overview.json`

**Key Panels**:
- Architecture health status
- CDX deduplication rate
- Page sharing efficiency
- Processing time trends
- Recent activity metrics

### 2. Performance Dashboard
**File**: `monitoring/grafana/dashboards/shared-pages-performance.json`

**Key Panels**:
- API response times
- Database query performance
- Processing throughput
- Resource utilization
- Alert summaries

### 3. Business Metrics Dashboard
**File**: `monitoring/grafana/dashboards/shared-pages-business-metrics.json`

**Key Panels**:
- API call reduction
- Storage efficiency
- User adoption metrics
- Cost savings summary

## Alerting Rules

### Critical Alerts

#### 1. CDX Deduplication Critical
**Trigger**: Deduplication rate < 50%
**Severity**: Critical
**Action**: Investigate CDX processing pipeline immediately

#### 2. Processing Backlog Critical
**Trigger**: Backlog > 1000 unprocessed pages
**Severity**: Critical
**Action**: Scale processing workers or investigate bottlenecks

#### 3. High Error Rate
**Trigger**: Error rate > 20% in 24h
**Severity**: Critical
**Action**: Review error logs, investigate root cause

### Warning Alerts

#### 1. Low Deduplication Efficiency
**Trigger**: Deduplication rate < 60%
**Severity**: Warning
**Action**: Monitor trend, investigate if declining

#### 2. Processing Backlog Growing
**Trigger**: Backlog > 500 pages
**Severity**: Warning
**Action**: Monitor processing capacity

#### 3. Elevated Error Rate
**Trigger**: Error rate > 10% in 24h
**Severity**: Warning
**Action**: Review error patterns

## API Endpoints

### Monitoring Endpoints

```bash
# Core metrics
GET /api/v1/monitoring/shared-pages/metrics

# Health check
GET /api/v1/monitoring/shared-pages/health

# Business metrics
GET /api/v1/monitoring/shared-pages/business-metrics?days=30

# Performance metrics
GET /api/v1/monitoring/shared-pages/performance
```

### Prometheus Endpoints

```bash
# Shared pages metrics
GET /api/v1/monitoring/shared-pages/prometheus

# Health metrics
GET /api/v1/monitoring/health/prometheus

# Business metrics
GET /api/v1/monitoring/business/prometheus?days=30
```

## Troubleshooting Runbooks

### 1. Low Deduplication Rate

**Symptoms**: CDX deduplication rate below 60%

**Investigation Steps**:
1. Check CDX registry table health
2. Verify CDX processing service status
3. Analyze recent CDX entries patterns
4. Check for data quality issues

**Remediation**:
```bash
# Check CDX service health
curl http://localhost:8000/api/v1/monitoring/shared-pages/health

# Investigate CDX processing
docker compose logs cdx_processor

# Manual CDX cleanup if needed
docker compose exec backend python scripts/cleanup_cdx_registry.py
```

### 2. High Processing Backlog

**Symptoms**: Processing backlog > 500 pages

**Investigation Steps**:
1. Check processing service health
2. Monitor resource utilization
3. Identify processing bottlenecks
4. Check for stuck processes

**Remediation**:
```bash
# Scale processing workers
docker compose up --scale celery_worker=3

# Restart processing services
docker compose restart celery_worker

# Check worker status
docker compose exec backend celery -A app.tasks.celery_app inspect active
```

### 3. High Error Rate

**Symptoms**: Error rate > 10% in 24h

**Investigation Steps**:
1. Analyze error logs
2. Identify common error patterns
3. Check service connectivity
4. Verify data integrity

**Remediation**:
```bash
# Check recent errors
docker compose logs backend | grep ERROR | tail -50

# Check service connectivity
curl http://localhost:7700/health  # Meilisearch
curl http://localhost:6379/ping    # Redis

# Database connectivity
docker compose exec postgres pg_isready
```

### 4. Poor API Performance

**Symptoms**: API response times > 2s

**Investigation Steps**:
1. Check database query performance
2. Monitor connection pool usage
3. Analyze slow queries
4. Check cache hit rates

**Remediation**:
```bash
# Check database performance
docker compose exec postgres pg_stat_activity

# Monitor slow queries
docker compose exec postgres pg_stat_statements

# Restart services if needed
docker compose restart backend
```

## Maintenance Tasks

### Daily Tasks
1. Review dashboard metrics
2. Check alert status
3. Monitor error rates
4. Verify backup completion

### Weekly Tasks
1. Analyze performance trends
2. Review capacity planning metrics
3. Clean up old metrics data
4. Update alert thresholds if needed

### Monthly Tasks
1. Review business metrics trends
2. Update monitoring documentation
3. Perform monitoring system health check
4. Plan capacity scaling if needed

## Emergency Procedures

### 1. System-Wide Failure

**Immediate Actions**:
1. Check overall system health
2. Verify database connectivity
3. Restart critical services
4. Enable emergency fallback mode

```bash
# Emergency restart
docker compose restart backend meilisearch redis postgres

# Check system status
curl http://localhost:8000/api/v1/monitoring/health/detailed
```

### 2. Data Corruption Detection

**Immediate Actions**:
1. Stop processing services
2. Enable read-only mode
3. Initiate backup restoration
4. Notify operations team

```bash
# Stop processing
docker compose stop celery_worker

# Enable maintenance mode
docker compose exec backend python scripts/enable_maintenance_mode.py
```

### 3. Performance Degradation

**Immediate Actions**:
1. Scale processing workers
2. Enable cache warming
3. Optimize database queries
4. Monitor resource usage

```bash
# Emergency scaling
docker compose up --scale celery_worker=5 --scale backend=2

# Cache warming
docker compose exec backend python scripts/warm_cache.py
```

## Configuration

### Prometheus Configuration
**File**: `monitoring/prometheus/prometheus.yml`

Key scrape targets:
- Backend API metrics
- Shared pages specific metrics
- Health check metrics
- Business metrics

### Alert Rules
**Files**:
- `monitoring/prometheus/shared_pages_alerts.yml`
- `monitoring/prometheus/performance_alerts.yml`

### Grafana Dashboards
**Directory**: `monitoring/grafana/dashboards/`

Import dashboards into Grafana for visualization.

## Best Practices

### 1. Monitoring Strategy
- Monitor business impact, not just technical metrics
- Use appropriate alert thresholds
- Implement gradual alerting (warning → critical)
- Regular review and tuning of alerts

### 2. Response Procedures
- Document all incident responses
- Maintain runbooks for common issues
- Regular training on monitoring tools
- Post-incident reviews and improvements

### 3. Capacity Planning
- Monitor growth trends
- Plan for traffic spikes
- Regular load testing
- Proactive scaling decisions

## Support Contacts

### Operations Team
- Primary: ops-team@chrono-scraper.com
- Secondary: dev-team@chrono-scraper.com

### Escalation Procedures
1. Level 1: Operations team response
2. Level 2: Development team involvement
3. Level 3: Architecture team consultation
4. Level 4: Emergency vendor support

---

This monitoring guide ensures comprehensive visibility into the shared pages architecture performance and provides clear procedures for maintaining optimal system health.