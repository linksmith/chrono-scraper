# Chrono Scraper v2 - Hetzner CX32 Resource Optimization Guide

## Overview

This guide provides comprehensive resource allocation strategies for running Chrono Scraper v2 on a single Hetzner CX32 server (4 vCPU, 8GB RAM) within a €50/month budget constraint. The optimization focuses on production stability, performance bottleneck identification, and graceful degradation under memory pressure.

## Server Specifications

### Hetzner CX32
- **CPU**: 4 vCPU cores (Intel/AMD)
- **Memory**: 8GB RAM
- **Storage**: 80GB NVMe SSD
- **Network**: 20TB traffic, 1Gbps connection
- **Cost**: ~€50/month

### Available Resources (after OS overhead)
- **Usable RAM**: ~7GB (1GB reserved for OS)
- **Usable CPU**: ~3.5 cores (0.5 cores reserved for OS)

## Resource Allocation Strategy

### Memory Distribution (Total: 7GB)

| Service | Allocation | Percentage | Priority | Notes |
|---------|------------|------------|----------|--------|
| PostgreSQL | 1.2GB | 17% | CRITICAL | Database with optimized buffers |
| Celery Worker | 1.5GB | 21% | HIGH | Background task processing |
| Firecrawl Playwright | 1.8GB | 26% | BROWSER | Memory-intensive browser automation |
| Backend API | 800MB | 11% | CRITICAL | FastAPI application server |
| Firecrawl Worker | 800MB | 11% | SCALABLE | Processing worker |
| Meilisearch | 600MB | 9% | IMPORTANT | Search engine |
| Firecrawl API | 600MB | 9% | IMPORTANT | API service |
| Redis | 400MB | 6% | CRITICAL | Cache and message queue |
| Frontend | 400MB | 6% | MINIMAL | SvelteKit development server |
| Utilities | 400MB | 6% | OPTIONAL | Beat scheduler, Flower, Mailpit |
| **Buffer** | **500MB** | **7%** | **SAFETY** | **Emergency buffer** |

### CPU Distribution (Total: 3.5 cores)

| Service | Reserved | Burst | Total | Notes |
|---------|----------|--------|-------|--------|
| PostgreSQL | 1.0 | +0.5 | 1.5 | Database operations |
| Celery Worker | 1.0 | +1.0 | 2.0 | High-load processing |
| Firecrawl Playwright | 0.75 | +0.75 | 1.5 | Browser automation |
| Backend API | 0.75 | +0.5 | 1.25 | API requests |
| Other Services | 0.5 | - | 0.5 | Shared allocation |

## Service Tier Architecture

### Tier 1: Critical Services (Never Stop)
- **PostgreSQL**: Core data persistence
- **Redis**: Essential caching and queues
- **Backend API**: Main application interface

### Tier 2: Important Services (Scale Down Under Pressure)
- **Meilisearch**: Search functionality (can degrade)
- **Celery Worker**: Background processing (reduce concurrency)

### Tier 3: Browser Automation (Memory Intensive)
- **Firecrawl Playwright**: Heavy browser processes
- **Firecrawl API**: API coordination
- **Firecrawl Worker**: Processing coordination

### Tier 4: Frontend Services (Development)
- **SvelteKit Frontend**: Development server (use reverse proxy in production)

### Tier 5: Utilities (First to Stop)
- **Celery Beat**: Task scheduling
- **Flower**: Monitoring dashboard
- **Mailpit**: Email testing (development only)

## Performance Thresholds

### Memory Pressure Levels

| Level | Threshold | Action | Recovery Time |
|-------|-----------|--------|---------------|
| **Optimal** | <75% | Normal operation | - |
| **Warning** | 85% (6.0GB) | Scale down Tier 5 services | 3 minutes |
| **Critical** | 92% (6.5GB) | Emergency scale down | Immediate |
| **Emergency** | >95% | Stop all non-critical services | Immediate |

### CPU Load Levels

| Level | Threshold | Action | Recovery Time |
|-------|-----------|--------|---------------|
| **Optimal** | <60% | Normal operation | - |
| **Warning** | 80% | Reduce worker concurrency | 2 minutes |
| **Critical** | 90% | Aggressive scaling | Immediate |

## Scaling Strategies

### Scale-Down Sequence (Memory Pressure)

1. **Level 1**: Stop Tier 5 utilities (Flower, Mailpit, Beat)
2. **Level 2**: Stop Frontend services
3. **Level 3**: Stop Firecrawl Worker, reduce Playwright sessions
4. **Level 4**: Stop Firecrawl services entirely
5. **Level 5**: Reduce Celery Worker concurrency
6. **Emergency**: Keep only PostgreSQL, Redis, Backend

### Scale-Up Sequence (Resource Recovery)

1. **Minimal**: PostgreSQL + Redis + Backend
2. **Essential**: + Meilisearch + Celery Worker
3. **Standard**: + Firecrawl API + Playwright + Frontend
4. **Full**: + Firecrawl Worker + utilities
5. **Development**: + all development tools

## Configuration Files

### Docker Compose Optimization
- **Main file**: `docker-compose.hetzner-cx32.yml`
- Memory limits and CPU constraints for each service
- Health checks with appropriate timeouts
- Restart policies optimized for stability

### Memory-Optimized Firecrawl Configuration
- **File**: `firecrawl-memory-config.env`
- Browser automation with minimal memory footprint
- Aggressive garbage collection
- Limited concurrent sessions

### Resource Monitoring
- **Script**: `scripts/monitor-resources-hetzner.sh`
- Real-time memory and CPU monitoring
- Automated alerts and scaling suggestions
- Performance metrics collection

## Deployment Guide

### Initial Setup

```bash
# 1. Initialize optimized environment
make -f Makefile.hetzner init-hetzner

# 2. Start services with resource monitoring
make -f Makefile.hetzner up-hetzner
make -f Makefile.hetzner monitor-continuous

# 3. Start automated scaling daemon
make -f Makefile.hetzner start-auto-scaler
```

### Daily Operations

```bash
# Check system status
make -f Makefile.hetzner status-hetzner

# Monitor resource usage
make -f Makefile.hetzner monitor

# Scale down under pressure
make -f Makefile.hetzner scale-down LEVEL=utilities

# Emergency memory management
make -f Makefile.hetzner emergency-stop
```

### Maintenance Operations

```bash
# Optimize performance
make -f Makefile.hetzner optimize-performance

# Clear caches to free memory
make -f Makefile.hetzner clear-caches

# Run health checks
make -f Makefile.hetzner health-check

# Backup current state
make -f Makefile.hetzner backup-state
```

## Monitoring and Alerting

### Automated Monitoring
- **Daemon**: `scripts/auto-scaler.sh`
- Monitors resource usage every 30 seconds
- Automatic scaling based on thresholds
- Email/webhook alerts for critical situations

### Manual Monitoring
- **Real-time**: `make monitor-continuous`
- **Single check**: `make monitor`
- **Resource stats**: `make resource-stats`

### Key Metrics to Watch

1. **Memory Usage**: Critical at 92% (6.5GB)
2. **CPU Load**: Warning at 80% (2.8 cores)
3. **Container Health**: Any unhealthy critical services
4. **Disk Usage**: Warning at 85% capacity
5. **Database Connections**: Monitor connection pool

## Performance Optimization

### Database Optimization (PostgreSQL)
```sql
-- Optimized settings for 8GB system
shared_buffers = 256MB
effective_cache_size = 800MB
work_mem = 16MB
maintenance_work_mem = 64MB
max_connections = 50
```

### Redis Configuration
```bash
maxmemory 300mb
maxmemory-policy allkeys-lru
save 900 1 300 10 60 10000
```

### Browser Automation (Firecrawl)
- Maximum 1 concurrent session
- Disabled media loading
- Aggressive garbage collection
- Memory limit: 1.8GB with automatic restart

## Troubleshooting Guide

### High Memory Usage
1. Check container memory stats: `make resource-stats`
2. Identify memory-heavy containers
3. Scale down non-critical services: `make scale-down LEVEL=utilities`
4. Clear caches: `make clear-caches`
5. Restart memory-heavy services if needed

### High CPU Usage
1. Check system load: `uptime`
2. Reduce Celery worker concurrency
3. Limit Firecrawl browser sessions
4. Check for runaway processes: `docker stats`

### Service Health Issues
1. Run health check: `make health-check`
2. Check container logs: `make logs-hetzner`
3. Restart unhealthy services
4. Verify resource allocation

### Memory Leaks
- Monitor trends with continuous monitoring
- Set up automatic container restarts
- Use memory limits to prevent system crashes
- Regular health checks and cleanup

## Cost Optimization

### Resource Efficiency
- **Single Server**: All services on one Hetzner CX32
- **Shared Resources**: Optimized resource sharing
- **Auto-scaling**: Automatic resource management
- **Efficient Storage**: NVMe SSD for performance

### Operational Efficiency
- **Automated Monitoring**: Reduces manual intervention
- **Graceful Degradation**: Maintains core functionality
- **Backup Strategies**: Quick recovery capabilities
- **Performance Optimization**: Maximizes hardware utilization

## Production Checklist

### Before Deployment
- [ ] Configure environment variables in `.env`
- [ ] Set up monitoring and alerting
- [ ] Test scaling operations
- [ ] Verify backup procedures
- [ ] Configure SSL/TLS termination

### After Deployment
- [ ] Start auto-scaler daemon
- [ ] Verify all health checks
- [ ] Test emergency scaling procedures
- [ ] Monitor performance metrics
- [ ] Set up log rotation

### Weekly Maintenance
- [ ] Review performance metrics
- [ ] Clean up Docker resources
- [ ] Rotate log files
- [ ] Test backup and restore
- [ ] Update scaling thresholds if needed

## Advanced Configuration

### Custom Scaling Policies
```bash
# Create custom auto-scaler config
sudo mkdir -p /etc/chrono-scraper
sudo tee /etc/chrono-scraper/auto-scaler.conf << EOF
MEMORY_WARNING_THRESHOLD=80
MEMORY_CRITICAL_THRESHOLD=90
ENABLE_AGGRESSIVE_SCALING=true
MAX_SCALE_ACTIONS_PER_HOUR=15
EOF
```

### Webhook Alerts
```bash
# Add webhook URL to auto-scaler config
echo "WEBHOOK_URL=https://your-webhook-url.com/alerts" >> /etc/chrono-scraper/auto-scaler.conf
```

### Performance Tuning
```bash
# Custom PostgreSQL tuning
echo "POSTGRES_WORK_MEM=24MB" >> .env
echo "POSTGRES_SHARED_BUFFERS=320MB" >> .env

# Custom Redis tuning
echo "REDIS_MAXMEMORY=350mb" >> .env
```

## Conclusion

This optimization guide provides a comprehensive strategy for running Chrono Scraper v2 efficiently on a Hetzner CX32 server. The key principles are:

1. **Tiered Service Architecture**: Critical services are protected while non-essential services can be scaled down
2. **Proactive Monitoring**: Automated resource monitoring with predictive scaling
3. **Graceful Degradation**: System maintains core functionality under pressure
4. **Resource Efficiency**: Optimized allocation based on service priorities
5. **Operational Simplicity**: Automated operations reduce manual intervention

By following these guidelines, you can achieve stable, performant operation within the €50/month budget constraint while maintaining the full functionality of the Chrono Scraper platform.