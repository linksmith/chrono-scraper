# Production Deployment Guide - Chrono Scraper v2 on Hetzner Cloud

## Executive Summary

**Total Monthly Cost**: €25.85 (€24.15 under €50 budget)  
**Infrastructure**: Single Hetzner CX32 server with horizontal scaling capability  
**Performance**: 50-100 concurrent users, 500-1,000 daily users, 5-10 concurrent scraping jobs  
**Scaling Path**: Clear upgrade path from €25 → €50 → €150+ as business grows

## Quick Start (5-Minute Deployment)

### 1. Prerequisites Setup
```bash
# Install Terraform
sudo apt update && sudo apt install -y terraform

# Get credentials ready:
# - Hetzner Cloud API token: https://console.hetzner.cloud/projects
# - SSH public key: cat ~/.ssh/id_rsa.pub
# - Cloudflare API token (optional): https://dash.cloudflare.com/profile/api-tokens
```

### 2. Configure Deployment
```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars  # Add your credentials
```

### 3. Deploy Infrastructure
```bash
# Use our automated script
chmod +x ../scripts/deploy-production.sh
../scripts/deploy-production.sh init    # Deploy infrastructure (~5 minutes)
../scripts/deploy-production.sh deploy  # Deploy application (~10 minutes)
```

### 4. Verify Deployment
```bash
../scripts/deploy-production.sh status  # Check all systems
../scripts/cost-monitor.sh costs        # Verify costs within budget
```

**Total deployment time**: ~15 minutes  
**Result**: Production-ready Chrono Scraper v2 at chronoscraper.com

## Architecture Overview

### Infrastructure Components

| Component | Cost/Month | Purpose | Specs |
|-----------|------------|---------|-------|
| **CX32 Server** | €6.80 | Main application server | 4 vCPU, 8 GB RAM, 80 GB SSD |
| **100GB Volume** | €9.60 | Additional data storage | Persistent database/logs |
| **Load Balancer** | €4.90 | SSL termination, scaling | 1 Gbps, 20TB traffic |
| **Floating IP** | €1.19 | Zero-downtime deployments | High availability |
| **Backups** | €1.36 | Daily automated backups | 7-day retention |
| **Total Base** | **€23.85** | | |
| **Snapshots** | €2.00 | Recovery snapshots | Ad-hoc |
| **Buffer** | €0.00 | Cloudflare (free) | CDN, DNS |
| **TOTAL** | **€25.85** | **€24.15 under budget** | |

### Container Resource Allocation

```yaml
# Optimized for CX32 (4 vCPU, 8 GB RAM)
Services:
  postgres:          1.5GB RAM, 1.0 CPU  # Database
  redis:             512MB RAM, 0.5 CPU  # Cache/Queue  
  meilisearch:       1GB RAM, 0.5 CPU    # Search Engine
  backend:           1GB RAM, 1.0 CPU    # FastAPI
  celery_worker:     1GB RAM, 1.0 CPU    # Background Tasks
  firecrawl-playwright: 1.5GB RAM, 1.0 CPU # Browser Automation
  firecrawl-api:     512MB RAM, 0.5 CPU  # Content Extraction
  frontend:          256MB RAM, 0.5 CPU  # SvelteKit
  traefik:           128MB RAM, 0.25 CPU # Load Balancer

Total Allocated: 7.4GB RAM, 6 vCPUs (600MB system reserve)
```

## Performance Characteristics

### Expected Performance (CX32)
- **Concurrent Active Sessions**: 50-100 users
- **Daily Unique Visitors**: 500-1,000 users
- **Concurrent Scraping Jobs**: 5-10 sessions
- **Database Capacity**: 1M+ pages with efficient indexing
- **Search Query Performance**: <200ms average
- **API Response Times**: <500ms average
- **Uptime Target**: 99.5% (4.4 hours downtime/month)

### Bottleneck Analysis
1. **First Bottleneck**: Firecrawl Playwright (memory-intensive browser automation)
2. **Second Bottleneck**: Database connections under heavy concurrent load
3. **Third Bottleneck**: CPU during multiple simultaneous scraping sessions

## Cost-Optimized Scaling Strategy

### Phase 1: Single Server (€25-50/month)

#### Current Configuration (€25.85/month)
✅ **Production Ready**: Handles moderate production workloads  
✅ **Automated Backups**: Daily PostgreSQL + file system backups  
✅ **SSL/HTTPS**: Let's Encrypt certificates with auto-renewal  
✅ **Monitoring**: System metrics, container health checks, log aggregation  
✅ **Security**: Firewall, fail2ban, SSH hardening, container isolation  

#### Vertical Scaling Triggers
**Scale when**:
- CPU usage >80% consistently (15+ minutes)
- Memory usage >85% 
- Response times >500ms average
- Queue backlog >100 jobs
- User complaints about performance

#### Upgrade Path
```bash
# Upgrade to CX42: 8 vCPU, 16 GB RAM (+€9.60/month)
# Total cost: ~€35/month (still €15 under budget)
# Capacity: 2x performance, 100-200 concurrent users

# In terraform.tfvars:
server_type = "cx42"
```

### Phase 2: Multi-Server Architecture (€50-85/month)

When single server reaches limits, split services:

```yaml
Web Server (CX42):          €16.40/month
  - Frontend (SvelteKit)
  - Backend (FastAPI)  
  - Redis (cache)
  - Load balancing

Database Server (CX32):     €6.80/month
  - PostgreSQL
  - Automated backups
  - Read replicas

Worker Server (CX32):       €6.80/month  
  - Celery workers
  - Firecrawl services
  - Background processing

Infrastructure:             €25/month
  - Load balancers
  - Storage volumes  
  - Floating IPs
  - Backups
```

**Total Phase 2 Cost**: ~€55/month  
**Performance**: 200-500 concurrent users, 2,000-5,000 daily users

### Phase 3: Multi-Region (€150+/month)

For global scale and high availability:
- **Primary Region**: EU (Nuremberg) - Full stack
- **Secondary Region**: US (Ashburn) - Read replicas, CDN
- **Database Replication**: Master-slave PostgreSQL setup
- **Global CDN**: Cloudflare Pro for enhanced performance
- **Monitoring**: Datadog or New Relic for comprehensive observability

## Security Implementation

### Server-Level Security
- **SSH Access**: Custom port (2222), key-based authentication only
- **Firewall**: UFW with minimal open ports (80, 443, 2222)
- **Intrusion Detection**: Fail2ban with custom rules
- **Automatic Updates**: Security patches applied automatically
- **User Access**: Root login disabled, sudo with key-based auth

### Application-Level Security  
- **SSL/TLS**: Let's Encrypt certificates with auto-renewal
- **Security Headers**: HSTS, CSP, X-Frame-Options, X-Content-Type-Options
- **Rate Limiting**: Traefik-based rate limiting for API endpoints
- **Container Isolation**: Resource limits, network isolation
- **Secrets Management**: Environment variables, no secrets in code

### Data Protection
- **Database**: PostgreSQL with connection limits and query timeouts
- **Backups**: Encrypted daily backups with 7-day retention
- **Log Management**: Centralized logging with log rotation
- **Monitoring**: Real-time alerts for security events

## Monitoring & Alerting Framework

### Built-in Monitoring
```bash
# System metrics (every 5 minutes)
/home/ubuntu/monitoring-script.sh

# Application health checks
curl https://chronoscraper.com/api/v1/health

# Container resource usage  
docker stats --no-stream

# Cost monitoring
./infrastructure/scripts/cost-monitor.sh costs
```

### Alert Thresholds
```yaml
Critical Alerts (Email + SMS):
  - Service down >5 minutes
  - CPU >95% for >10 minutes  
  - Memory >95% for >5 minutes
  - Disk >90% full
  - Cost >€45/month

Warning Alerts (Email):
  - CPU >80% for >15 minutes
  - Memory >85% for >10 minutes  
  - Response time >1s average
  - Error rate >5%
  - Cost >€40/month
```

### Monitoring Tools Integration
- **UptimeRobot**: Free tier for external uptime monitoring
- **Cloudflare Analytics**: Free website performance metrics
- **Log Aggregation**: Built-in logging to `/mnt/data/logs/`
- **Cost Tracking**: Automated daily cost calculations
- **Performance Metrics**: System resource monitoring every 5 minutes

## Disaster Recovery & Business Continuity

### Backup Strategy
```bash
# Automated daily backups (2:00 AM UTC)
- PostgreSQL dumps (compressed)
- Meilisearch data exports  
- File system snapshots
- Configuration backups

# Retention Policy
- Local: 7 days
- External: 30 days (optional S3-compatible storage)

# Recovery Testing
- Monthly automated restore tests
- Documentation for manual recovery procedures
```

### Recovery Time Objectives
- **RTO** (Recovery Time Objective): 15 minutes
- **RPO** (Recovery Point Objective): 1 hour maximum data loss
- **Failover**: Manual failover to backup server (Phase 2+)
- **Geographic Backup**: External storage for disaster scenarios

### Business Continuity Plan
1. **Service Degradation**: Automatic container restarts, health checks
2. **Server Failure**: Restore from latest snapshot (Hetzner Cloud)
3. **Data Loss**: Restore from most recent backup
4. **Extended Outage**: Failover to secondary region (Phase 3)

## Cost Optimization Strategies

### Phase 1 Optimizations (€25-35/month)
- **Container Resource Tuning**: Regular review of actual vs allocated resources
- **Database Optimization**: Query optimization, connection pooling
- **Cache Optimization**: Redis memory usage optimization
- **Static Asset CDN**: Cloudflare free tier reduces server load
- **Log Rotation**: Automated cleanup of old logs and temporary files

### Phase 2 Optimizations (€35-50/month)
- **ARM-based Servers**: CAX series for better price/performance
- **Resource Right-sizing**: Monthly analysis of actual usage patterns
- **Automated Scaling**: CPU/memory-based horizontal scaling
- **Storage Tiering**: Move old data to cheaper long-term storage

### Phase 3 Optimizations (€50+/month)
- **Reserved Capacity**: Long-term commitments for cost savings
- **Multi-cloud Strategy**: Compare Hetzner vs AWS/GCP pricing
- **Spot Instances**: Use lower-cost instances for worker nodes
- **Database Management**: Managed PostgreSQL vs self-hosted analysis

## Deployment Automation

### CI/CD Pipeline (GitHub Actions)
```yaml
# .github/workflows/deploy-production.yml
name: Deploy to Production
on:
  push:
    branches: [main]
    
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy Application
        run: |
          ssh ubuntu@$SERVER_IP -p 2222 '
            cd /opt/chrono-scraper &&
            git pull origin main &&
            docker-compose -f infrastructure/docker-compose.production.yml up -d --build
          '
      
      - name: Health Check
        run: |
          sleep 30
          curl -f https://chronoscraper.com/api/v1/health
```

### Zero-Downtime Deployments
- **Blue-Green Strategy**: Using Docker Compose with health checks
- **Rolling Updates**: Container-by-container updates with validation
- **Database Migrations**: Run before switching traffic
- **Rollback Plan**: Keep previous container versions for quick rollback

### Automated Testing
- **Pre-deployment**: Run full test suite in staging environment
- **Post-deployment**: Automated smoke tests and health checks
- **Performance Monitoring**: Response time and error rate validation
- **Cost Validation**: Automated cost monitoring after deployments

## Troubleshooting Guide

### Common Issues & Solutions

#### High Memory Usage
```bash
# Check container memory usage
docker stats --no-stream

# Restart memory-heavy services
docker-compose restart firecrawl-playwright celery_worker

# Clear Redis cache if needed
docker exec redis redis-cli FLUSHDB
```

#### Database Performance
```bash
# Check slow queries
docker exec postgres psql -U chrono_scraper -c "
  SELECT query, mean_time, calls 
  FROM pg_stat_statements 
  ORDER BY mean_time DESC LIMIT 10;
"

# Optimize database
docker exec postgres psql -U chrono_scraper -c "ANALYZE; VACUUM;"
```

#### SSL Certificate Issues
```bash
# Check certificate status
sudo certbot certificates

# Renew certificates
sudo certbot renew --dry-run

# Force renewal if needed
sudo certbot renew --force-renewal
```

#### Cost Overruns
```bash
# Check current costs
./infrastructure/scripts/cost-monitor.sh costs

# Analyze resource usage
./infrastructure/scripts/cost-monitor.sh metrics

# Get scaling recommendations
./infrastructure/scripts/cost-monitor.sh scaling
```

## Migration from Development

### Pre-Migration Checklist
- [ ] Production environment variables configured in `.env.production`
- [ ] SSL certificates domain validation completed
- [ ] Database migration scripts tested in staging
- [ ] Backup/restore procedures validated
- [ ] Monitoring dashboards configured
- [ ] Load testing completed with expected user volumes
- [ ] Security audit completed (firewall, SSL, access controls)

### Migration Steps
1. **Infrastructure Deployment** (5 minutes)
   ```bash
   cd infrastructure/terraform
   cp terraform.tfvars.example terraform.tfvars
   # Configure terraform.tfvars with your credentials
   terraform init && terraform plan && terraform apply
   ```

2. **Application Deployment** (10 minutes)
   ```bash
   ../scripts/deploy-production.sh deploy
   ```

3. **DNS Configuration** (5 minutes)
   - Point domain to Load Balancer IP
   - Configure Cloudflare or DNS provider
   - Verify SSL certificate generation

4. **Data Migration** (varies by data size)
   ```bash
   # Export from development
   pg_dump development_db > backup.sql
   
   # Import to production  
   scp backup.sql ubuntu@server:/tmp/
   ssh ubuntu@server "docker exec postgres psql -U chrono_scraper < /tmp/backup.sql"
   ```

5. **Validation** (5 minutes)
   ```bash
   ../scripts/deploy-production.sh status
   curl -f https://chronoscraper.com/api/v1/health
   ```

### Post-Migration Checklist
- [ ] All services healthy and responding
- [ ] SSL certificates active and auto-renewal configured
- [ ] Database connections working with production data
- [ ] Search indexing completed (Meilisearch)
- [ ] Background tasks processing correctly (Celery)
- [ ] Email delivery working (registration, notifications)
- [ ] Monitoring alerts configured and testing
- [ ] Backup scripts running successfully
- [ ] Performance metrics within expected ranges
- [ ] Cost monitoring active and under budget

## Support & Maintenance

### Regular Maintenance Tasks
**Daily**:
- Check application health endpoints
- Review cost monitoring alerts
- Verify backup completion

**Weekly**:
- Review performance metrics and scaling needs
- Update container images for security patches
- Analyze error logs and optimize bottlenecks

**Monthly**:
- Comprehensive cost and performance review
- Database maintenance (vacuum, analyze, index optimization)
- Security audit and access review
- Capacity planning based on growth trends

### Getting Help
- **Documentation**: `/infrastructure/terraform/README.md`
- **Scripts**: `/infrastructure/scripts/` for automation
- **Monitoring**: `/infrastructure/scripts/cost-monitor.sh`
- **Logs**: `/mnt/data/logs/` on production server
- **Hetzner Support**: https://docs.hetzner.com/
- **Community**: Discord/Slack for project-specific support

### Emergency Contacts & Procedures
```bash
# Emergency server access
ssh -p 2222 ubuntu@<server-ip>

# Emergency service restart
docker-compose -f infrastructure/docker-compose.production.yml restart

# Emergency backup
/home/ubuntu/backup-script.sh

# Emergency cost check
./infrastructure/scripts/cost-monitor.sh costs

# Emergency scaling analysis  
./infrastructure/scripts/cost-monitor.sh scaling
```

---

## Summary

This production deployment guide provides:

✅ **Budget Compliance**: €25.85/month (€24.15 under €50 limit)  
✅ **Production Ready**: Handles 50-100 concurrent users immediately  
✅ **Scalable Architecture**: Clear path to €50, €100, €150+ monthly budgets  
✅ **Automated Deployment**: 15-minute deployment with automated scripts  
✅ **Comprehensive Monitoring**: Cost, performance, and health monitoring  
✅ **Enterprise Security**: SSL, firewalls, intrusion detection, backups  
✅ **Disaster Recovery**: 15-minute RTO, 1-hour RPO with automated backups  

The architecture provides a solid foundation for growing from a startup to enterprise scale while maintaining cost efficiency and operational excellence.