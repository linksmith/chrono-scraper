# Hetzner Cloud Production Architecture for Chrono Scraper v2

## Executive Summary

**Budget Target**: €50/month maximum
**Recommended Configuration**: Single CX32 server (€6.80/month) + additional services
**Total Monthly Cost**: €47.80/month
**Scaling Path**: Clear horizontal scaling strategy to €150+ as business grows

## Phase 1: Minimum Viable Production (€47.80/month)

### Core Infrastructure

#### Primary Server: Hetzner CX32
- **Cost**: €6.80/month
- **Specs**: 4 vCPU, 8 GB RAM, 80 GB NVMe SSD, 20 TB traffic
- **Location**: Nuremberg or Helsinki (EU)
- **OS**: Ubuntu 22.04 LTS

#### Storage & Backup
- **Additional Volume**: 100 GB SSD - €9.60/month
- **Backup**: 20% of server cost - €1.36/month
- **Snapshot**: On-demand - ~€2/month

#### Load Balancer & Networking
- **Hetzner Load Balancer**: €4.90/month (for SSL termination and future scaling)
- **Floating IP**: €1.19/month (for zero-downtime deployments)

#### DNS & Monitoring
- **Cloudflare DNS**: Free
- **Basic monitoring**: Built into Hetzner Console - Free
- **Uptime monitoring**: UptimeRobot free tier

### Monthly Cost Breakdown
```
CX32 Server:           €6.80
100GB Volume:          €9.60
Backup:               €1.36
Load Balancer:        €4.90
Floating IP:          €1.19
Snapshots (avg):      €2.00
Domain & CDN:         €0.00 (Cloudflare free)
External monitoring:  €0.00 (UptimeRobot free)
-----------------------------------------
TOTAL:               €25.85/month
BUFFER:              €24.15/month
```

## Container Resource Allocation (CX32: 4 vCPU, 8 GB RAM)

### Docker Compose Resource Limits

```yaml
# Optimized for single-server production
services:
  postgres:
    deploy:
      resources:
        limits:
          memory: 1.5G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'

  redis:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'

  meilisearch:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.5'
        reservations:
          memory: 512M
          cpus: '0.25'

  backend:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
        reservations:
          memory: 512M
          cpus: '0.5'

  frontend:
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.5'
        reservations:
          memory: 128M
          cpus: '0.25'

  celery_worker:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
        reservations:
          memory: 512M
          cpus: '0.5'

  firecrawl-api:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'

  firecrawl-playwright:
    deploy:
      resources:
        limits:
          memory: 1.5G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'

  traefik:
    deploy:
      resources:
        limits:
          memory: 128M
          cpus: '0.25'
        reservations:
          memory: 64M
          cpus: '0.1'
```

### Resource Summary
- **Total RAM allocation**: ~7.4GB (leaves 600MB for system)
- **Total CPU allocation**: ~6 vCPUs with burst capability
- **Storage**: 80GB SSD + 100GB additional volume

## Performance Expectations

### User Load Capacity (Single Server)
- **Concurrent Users**: 50-100 active sessions
- **Daily Users**: 500-1,000 unique users
- **Scraping Jobs**: 5-10 concurrent scraping sessions
- **Database**: Up to 1M pages stored efficiently
- **Search Performance**: Sub-200ms search queries

### Bottleneck Analysis
1. **First bottleneck**: Firecrawl Playwright (memory-intensive)
2. **Second bottleneck**: Database connections under heavy load
3. **Third bottleneck**: CPU during multiple concurrent scrapes

## High Availability Setup

### Single Server Resilience
- **Automated backups**: Daily PostgreSQL + file backups
- **Health checks**: All containers monitored with restart policies
- **Persistent volumes**: Database and search data survive container restarts
- **Graceful shutdowns**: Proper signal handling for zero-data-loss

### Disaster Recovery
- **RTO** (Recovery Time Objective): 15 minutes
- **RPO** (Recovery Point Objective): 1 hour
- **Backup locations**: Hetzner + external S3-compatible storage

## Phase 2: Horizontal Scaling (€85-150/month)

### When to Scale
**Scaling Triggers**:
- CPU usage consistently >80%
- Memory usage >85%
- Response times >500ms
- Queue backlog >100 jobs
- User complaints about performance

### Scaling Strategy

#### Step 1: Database Separation (€150/month total)
```
Production Server (CX42):     €16.40/month
- Frontend + Backend + Redis
- 8 vCPU, 16 GB RAM, 160 GB SSD

Database Server (CX32):       €6.80/month
- PostgreSQL + Backups
- 4 vCPU, 8 GB RAM, 80 GB SSD

Worker Server (CX32):         €6.80/month
- Celery + Firecrawl services
- 4 vCPU, 8 GB RAM, 80 GB SSD

Infrastructure costs:         €25/month
(LB, volumes, backups, IPs)
```

#### Step 2: Multi-Region Setup (€250+/month)
- Primary region: EU (Nuremberg)
- Secondary region: US (Ashburn, VA)
- Database replication and CDN

## Security Configuration

### Server Hardening
```bash
# SSH Configuration
- Disable root login
- Key-based authentication only
- Custom SSH port
- Fail2ban for intrusion detection

# Firewall Rules
- Only ports 80, 443, and custom SSH open
- Internal container communication only
- VPC isolation when scaling
```

### SSL/TLS
- **Let's Encrypt**: Free SSL certificates via Traefik
- **HSTS**: Enabled with 1-year max-age
- **Security Headers**: CSP, X-Frame-Options, etc.

## Monitoring & Alerting

### Key Metrics
- **System**: CPU, memory, disk usage, network I/O
- **Application**: Response times, error rates, queue lengths
- **Business**: User registrations, scraping success rates

### Alerting Thresholds
```yaml
Critical (PagerDuty):
  - Service down >5 minutes
  - CPU >95% for >10 minutes
  - Memory >95% for >5 minutes
  - Disk >90% full

Warning (Slack):
  - CPU >80% for >15 minutes
  - Memory >85% for >10 minutes
  - Response time >1s average
  - Error rate >5%
```

## Deployment Strategy

### Zero-Downtime Deployments
1. **Blue-Green Strategy**: Using Docker Compose + Floating IP
2. **Health Checks**: Automated readiness and liveness probes
3. **Rollback Plan**: Previous container versions maintained
4. **Database Migrations**: Run before switching traffic

### CI/CD Pipeline (GitHub Actions)
```yaml
stages:
  - test (run on PR)
  - build (create container images)
  - deploy-staging (automatic)
  - deploy-production (manual approval)
```

## Cost Optimization Strategies

### Phase 1 Optimizations
1. **Reserved Instances**: Not available on Hetzner, pay hourly
2. **Resource Right-sizing**: Monthly review of actual usage
3. **Cleanup Automation**: Old backups, logs, temp files
4. **CDN Usage**: Cloudflare free tier for static assets

### Scaling Cost Management
1. **Auto-scaling**: Implement CPU/memory-based scaling
2. **Spot Instances**: Use CAX series for worker nodes (cheaper)
3. **Storage Tiering**: Move old data to cheaper storage
4. **Database Optimization**: Query optimization, indexing

## Migration Path from Development

### Pre-Migration Checklist
- [ ] Production environment variables configured
- [ ] SSL certificates ready
- [ ] Database migration scripts tested
- [ ] Backup/restore procedures validated
- [ ] Monitoring dashboards configured
- [ ] Load testing completed

### Migration Steps
1. **Server Provisioning**: Create Hetzner resources
2. **Security Setup**: SSH keys, firewall, users
3. **Docker Setup**: Install Docker Compose
4. **Application Deployment**: Deploy containers
5. **Database Migration**: Import production data
6. **DNS Cutover**: Point domain to new server
7. **Monitoring**: Verify all services healthy

## Future Architecture Considerations

### Technology Upgrades
- **ARM Migration**: Consider CAX series for better price/performance
- **Kubernetes**: When managing >5 servers becomes complex
- **Managed Services**: PostgreSQL managed service at scale
- **Microservices**: Split monolithic backend when team grows

### Geographic Expansion
- **Multi-region**: US East, EU West, Asia Pacific
- **CDN**: Upgrade to Cloudflare Pro for better performance
- **Database Replication**: Read replicas in each region

This architecture provides a solid foundation for production deployment while maintaining strict budget constraints and offering clear scaling paths as the business grows.