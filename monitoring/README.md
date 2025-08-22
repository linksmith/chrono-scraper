# Chrono Scraper Shared Pages Monitoring Stack

This monitoring stack provides comprehensive observability for the Chrono Scraper shared pages architecture, including metrics collection, visualization, and alerting.

## Quick Start

### 1. Start the Main Application
```bash
# Start the main Chrono Scraper application first
cd /path/to/chrono-scraper-fastapi-2
docker compose up -d
```

### 2. Start the Monitoring Stack
```bash
# Start the monitoring stack
cd monitoring
docker compose -f docker-compose.monitoring.yml up -d
```

### 3. Access Monitoring Services

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3001 | admin / admin_password_change_me |
| Prometheus | http://localhost:9090 | No auth |
| AlertManager | http://localhost:9093 | No auth |
| Node Exporter | http://localhost:9100 | No auth |

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Application   │    │   Prometheus    │    │     Grafana     │
│   (Backend)     │────│   (Metrics)     │────│ (Visualization) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         │              │  AlertManager   │              │
         └──────────────│   (Alerting)    │──────────────┘
                        └─────────────────┘
```

## Monitoring Components

### 1. Metrics Collection
- **Backend API**: Custom Prometheus metrics via `/api/v1/monitoring/*/prometheus` endpoints
- **Node Exporter**: System-level metrics (CPU, memory, disk)
- **Postgres Exporter**: Database metrics
- **Redis Exporter**: Cache metrics

### 2. Key Metrics Tracked

#### Shared Pages Architecture
- `chrono_shared_pages_total`: Total number of shared pages
- `chrono_cdx_deduplication_rate_percent`: CDX deduplication efficiency
- `chrono_sharing_efficiency_percent`: Page sharing efficiency
- `chrono_processing_backlog`: Processing queue backlog
- `chrono_error_rate_24h_percent`: 24-hour error rate

#### Performance Metrics
- `chrono_avg_processing_time_seconds`: Average page processing time
- `chrono_sample_query_time_seconds`: Database query performance
- API response time percentiles
- Resource utilization (CPU, memory, disk)

#### Business Metrics
- `chrono_api_reduction_percentage_30d`: API call savings over 30 days
- `chrono_storage_efficiency_percentage_30d`: Storage efficiency
- `chrono_wayback_calls_saved_30d`: Estimated Wayback API calls saved

### 3. Dashboards

#### Shared Pages Overview
**File**: `grafana/dashboards/shared-pages-overview.json`

Provides high-level view of:
- Architecture health status
- Core metrics and trends
- Recent activity
- Processing pipeline status

#### Performance Dashboard
**File**: `grafana/dashboards/shared-pages-performance.json`

Focuses on:
- API response times
- Database performance
- Processing throughput
- Resource utilization
- Active alerts

#### Business Metrics Dashboard
**File**: `grafana/dashboards/shared-pages-business-metrics.json`

Tracks:
- Cost savings metrics
- User adoption
- Efficiency trends
- ROI indicators

### 4. Alerting Rules

#### Critical Alerts
- **CDX Deduplication Critical**: Rate < 50%
- **Processing Backlog Critical**: > 1000 unprocessed pages
- **High Error Rate**: > 20% errors in 24h
- **System Health Failed**: Core components unhealthy

#### Warning Alerts
- **Low Deduplication**: Rate < 60%
- **Growing Backlog**: > 500 unprocessed pages
- **Elevated Errors**: > 10% errors in 24h
- **Performance Degradation**: Response times > 2s

## Configuration

### 1. Prometheus Configuration
**File**: `prometheus/prometheus.yml`

Scrapes metrics from:
- Backend API (`backend:8000`)
- Health checks
- System exporters
- Third-party services

### 2. Alert Rules
**Files**:
- `prometheus/shared_pages_alerts.yml`: Shared pages specific alerts
- `prometheus/performance_alerts.yml`: Performance and system alerts

### 3. AlertManager
**File**: `alertmanager/alertmanager.yml`

Configured for:
- Email notifications
- Slack integration (configure webhook)
- Severity-based routing
- Alert grouping and inhibition

## API Endpoints

### Monitoring Endpoints

```bash
# Get shared pages metrics
curl http://localhost:8000/api/v1/monitoring/shared-pages/metrics

# Get health status
curl http://localhost:8000/api/v1/monitoring/shared-pages/health

# Get business metrics
curl http://localhost:8000/api/v1/monitoring/shared-pages/business-metrics?days=30

# Get performance metrics with timing
curl http://localhost:8000/api/v1/monitoring/shared-pages/performance
```

### Prometheus Metrics Endpoints

```bash
# Shared pages Prometheus metrics
curl http://localhost:8000/api/v1/monitoring/shared-pages/prometheus

# Health check metrics
curl http://localhost:8000/api/v1/monitoring/health/prometheus

# Business metrics
curl http://localhost:8000/api/v1/monitoring/business/prometheus?days=30
```

## Troubleshooting

### 1. Common Issues

#### Metrics Not Appearing
```bash
# Check if backend is exposing metrics
curl http://localhost:8000/api/v1/monitoring/prometheus/metrics

# Check Prometheus targets
# Go to http://localhost:9090/targets

# Check backend logs
docker compose logs backend
```

#### Grafana Connection Issues
```bash
# Check if Prometheus is accessible from Grafana
docker compose exec grafana curl http://prometheus:9090/api/v1/label/__name__/values

# Check Grafana logs
docker compose -f docker-compose.monitoring.yml logs grafana
```

#### Alerts Not Firing
```bash
# Check AlertManager configuration
curl http://localhost:9093/api/v1/status

# Check alert rules in Prometheus
# Go to http://localhost:9090/alerts

# Test alert rules
docker compose exec prometheus promtool query instant 'chrono_cdx_deduplication_rate_percent < 50'
```

### 2. Performance Optimization

#### Reduce Metrics Cardinality
- Limit label dimensions
- Use recording rules for complex queries
- Implement metric retention policies

#### Optimize Query Performance
- Use appropriate time ranges
- Implement caching for frequently accessed metrics
- Consider downsampling for long-term storage

### 3. Scaling Considerations

#### High-Volume Environments
```yaml
# Add to prometheus.yml for high-volume scraping
global:
  scrape_interval: 60s  # Increase interval
  evaluation_interval: 60s

scrape_configs:
  - job_name: 'shared-pages-metrics'
    scrape_interval: 120s  # Less frequent for heavy endpoints
    scrape_timeout: 30s
```

## Maintenance

### Daily Tasks
1. Review dashboard metrics
2. Check alert status
3. Monitor system resources
4. Verify backup completion

### Weekly Tasks
1. Analyze performance trends
2. Review alert effectiveness
3. Update dashboard configurations
4. Clean old metrics data

### Monthly Tasks
1. Review monitoring stack performance
2. Update alert thresholds
3. Capacity planning review
4. Documentation updates

## Security Considerations

### 1. Access Control
- Change default Grafana credentials
- Implement authentication for Prometheus/AlertManager
- Use HTTPS in production
- Restrict network access

### 2. Data Protection
- Encrypt metrics in transit
- Secure backup storage
- Implement data retention policies
- Monitor access logs

## Production Deployment

### 1. Environment Variables
```bash
# Set in production environment
export GRAFANA_ADMIN_PASSWORD="secure_password"
export SMTP_PASSWORD="your_smtp_password"
export SLACK_WEBHOOK_URL="your_slack_webhook"
```

### 2. Volume Management
```bash
# Create persistent volumes for production
docker volume create prometheus_data
docker volume create grafana_data
docker volume create alertmanager_data
```

### 3. High Availability
Consider deploying:
- Multiple Prometheus instances
- Grafana clustering
- External AlertManager
- Load balancers

## Support and Documentation

### Additional Resources
- [Shared Pages Monitoring Guide](./SHARED_PAGES_MONITORING_GUIDE.md)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [AlertManager Documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)

### Getting Help
1. Check application logs
2. Review monitoring documentation
3. Consult troubleshooting guides
4. Contact operations team

---

This monitoring stack provides comprehensive observability for the shared pages architecture, enabling proactive issue detection and resolution while tracking business impact and performance metrics.