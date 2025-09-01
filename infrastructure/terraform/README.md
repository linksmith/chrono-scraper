# Hetzner Cloud Infrastructure for Chrono Scraper v2

This directory contains Terraform configuration for deploying Chrono Scraper v2 to Hetzner Cloud with a strict €50/month budget constraint.

## Quick Start

### 1. Prerequisites

```bash
# Install Terraform
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo apt-key add -
sudo apt-add-repository "deb [arch=$(dpkg --print-architecture)] https://apt.releases.hashicorp.com $(lsb_release -cs) main"
sudo apt update && sudo apt install terraform

# Verify installation
terraform version

# Install Hetzner CLI (optional but helpful)
wget https://github.com/hetznercloud/cli/releases/latest/download/hcloud-linux-amd64.tar.gz
tar -xzf hcloud-linux-amd64.tar.gz
sudo mv hcloud /usr/local/bin/
```

### 2. Setup Credentials

```bash
# Copy example variables
cp terraform.tfvars.example terraform.tfvars

# Edit with your actual values
nano terraform.tfvars
```

Required credentials:
- **Hetzner Cloud API Token**: Get from [Hetzner Console](https://console.hetzner.cloud/projects)
- **SSH Public Key**: Your SSH public key for server access
- **Cloudflare API Token**: Optional but recommended for DNS management

### 3. Deploy Infrastructure

```bash
# Initialize Terraform
terraform init

# Plan deployment (review changes)
terraform plan

# Deploy infrastructure
terraform apply

# Note the outputs - you'll need these for application deployment
```

### 4. Access Your Server

```bash
# SSH to the server (check terraform outputs for exact command)
ssh -p 2222 ubuntu@<server-ip>

# The server is pre-configured with:
# - Docker and Docker Compose
# - Firewall (UFW) with minimal open ports
# - Fail2ban for intrusion detection
# - Automated backup scripts
# - System monitoring
```

## Architecture Overview

### Single Server Configuration (€25.85/month)

**Hardware**: Hetzner CX32
- 4 vCPU (Intel)
- 8 GB RAM
- 80 GB NVMe SSD + 100 GB additional volume
- 20 TB traffic included

**Services**:
- **Load Balancer**: €4.90/month (SSL termination, future scaling)
- **Floating IP**: €1.19/month (zero-downtime deployments)
- **Backups**: €1.36/month (automated daily backups)
- **Total**: €25.85/month (€24.15 budget remaining)

### Resource Allocation

```yaml
Container Resource Limits:
  postgres: 1.5GB RAM, 1.0 CPU
  redis: 512MB RAM, 0.5 CPU  
  meilisearch: 1GB RAM, 0.5 CPU
  backend: 1GB RAM, 1.0 CPU
  celery_worker: 1GB RAM, 1.0 CPU
  firecrawl-playwright: 1.5GB RAM, 1.0 CPU
  firecrawl-api: 512MB RAM, 0.5 CPU
  frontend: 256MB RAM, 0.5 CPU
  traefik: 128MB RAM, 0.25 CPU

Total: ~7.4GB RAM, ~6 vCPUs (with burst capability)
System Reserved: 600MB RAM for OS
```

## Cost Analysis

### Monthly Cost Breakdown

| Service | Cost (EUR/month) | Purpose |
|---------|------------------|---------|
| CX32 Server | €6.80 | Main application server |
| 100GB Volume | €9.60 | Additional storage |
| Load Balancer | €4.90 | SSL termination & scaling |
| Floating IP | €1.19 | Zero-downtime deployments |
| Backups | €1.36 | Automated daily backups |
| Snapshots | €2.00 | Recovery snapshots |
| **Total** | **€25.85** | **€24.15 under budget** |

### Alternative Configurations

#### Ultra Budget (€18.75/month)
```hcl
server_type = "cx22"           # €3.79
additional_volume_size = 50     # €4.80  
load_balancer_type = "lb11"    # €4.90
backup_enabled = true          # €0.76
floating_ip = true             # €1.19
snapshots_estimate             # €2.00
# Total: €17.44/month
```

#### ARM Optimized (€23.58/month)
```hcl
server_type = "cax21"          # €6.49 (ARM-based, better value)
additional_volume_size = 100    # €9.60
load_balancer_type = "lb11"    # €4.90
backup_enabled = true          # €1.30
floating_ip = true             # €1.19
# Total: €23.48/month
```

## Performance Expectations

### Single Server Capacity
- **Concurrent Users**: 50-100 active sessions
- **Daily Users**: 500-1,000 unique visitors
- **Scraping Jobs**: 5-10 concurrent sessions
- **Database**: Up to 1M pages stored efficiently
- **Search Performance**: Sub-200ms queries
- **Response Times**: <500ms average

### Bottleneck Analysis
1. **First bottleneck**: Firecrawl Playwright (memory-intensive browser automation)
2. **Second bottleneck**: Database connections under heavy load
3. **Third bottleneck**: CPU during multiple concurrent scraping sessions

## Scaling Strategy

### Phase 1: Vertical Scaling (€30-50/month)
When CPU consistently >80% or memory >85%:
```hcl
server_type = "cx42"  # Upgrade to 8 vCPU, 16 GB RAM (€16.40/month)
```

### Phase 2: Horizontal Scaling (€50-85/month)
When single server reaches limits:

```yaml
Web Server (CX42):     €16.40/month
- Frontend + Backend + Redis

Database Server (CX32): €6.80/month  
- PostgreSQL + Backups

Worker Server (CX32):   €6.80/month
- Celery + Firecrawl services

Infrastructure:         €25/month
- Load balancers, volumes, backups
```

### Phase 3: Multi-Region (€150+/month)
For global user base:
- Primary: EU (Nuremberg) 
- Secondary: US (Ashburn)
- Database replication
- CDN integration

## Security Features

### Server Hardening
- SSH on custom port (2222) with key-only authentication
- UFW firewall with minimal open ports (80, 443, 2222)
- Fail2ban for intrusion detection
- Automatic security updates
- Root login disabled

### Application Security
- SSL certificates via Let's Encrypt (automatic renewal)
- HSTS headers with 1-year max-age
- Security headers (CSP, X-Frame-Options, etc.)
- Rate limiting via Traefik
- Container isolation with resource limits

### Access Control
- Basic authentication for admin interfaces (Traefik, Flower)
- Network isolation between containers
- Database only accessible from application containers
- SSH access restricted by IP (configurable)

## Monitoring & Alerting

### Built-in Monitoring
- **System metrics**: CPU, memory, disk usage (every 5 minutes)
- **Container health**: Docker health checks for all services
- **Application health**: API endpoint monitoring
- **Log aggregation**: Centralized logging in `/mnt/data/logs/`

### Alert Thresholds
```yaml
Critical Alerts:
  - CPU >95% for >10 minutes
  - Memory >95% for >5 minutes  
  - Disk >90% full
  - Service down >5 minutes

Warning Alerts:
  - CPU >80% for >15 minutes
  - Memory >85% for >10 minutes
  - Response time >1s average
  - Error rate >5%
```

### Available Integrations
- **Email alerts**: Configure `alert_email` in terraform.tfvars
- **Slack notifications**: Set `slack_webhook_url` for team alerts
- **Uptime monitoring**: UptimeRobot free tier integration
- **External monitoring**: Datadog, New Relic compatible

## Backup & Recovery

### Automated Backups (Daily at 2:00 AM UTC)
- **PostgreSQL dumps**: Compressed SQL exports
- **Meilisearch data**: Search index exports  
- **Application data**: File system snapshots
- **Retention**: 7 days local, 30 days external (optional)

### Disaster Recovery
- **RTO** (Recovery Time Objective): 15 minutes
- **RPO** (Recovery Point Objective): 1 hour
- **Backup verification**: Automated restore tests
- **Geographic redundancy**: External S3-compatible storage

### Manual Recovery Commands
```bash
# Restore database from backup
docker exec postgres psql -U chrono_scraper -d chrono_scraper < /mnt/data/backups/postgres_YYYYMMDD.sql

# Restore Meilisearch data
curl -X POST 'http://localhost:7700/dumps/YYYYMMDD/import' -H 'Authorization: Bearer master-key'

# Server snapshot restore via Hetzner Console
hcloud server rebuild chrono-scraper-production-main --image ubuntu-22.04
```

## Deployment Workflow

### Initial Deployment
```bash
# 1. Deploy infrastructure
terraform apply

# 2. SSH to server
ssh -p 2222 ubuntu@<server-ip>

# 3. Clone repository
cd /opt
sudo git clone https://github.com/yourusername/chrono-scraper-fastapi-2.git chrono-scraper
sudo chown -R ubuntu:ubuntu chrono-scraper
cd chrono-scraper

# 4. Configure environment
cp .env.example .env.production
nano .env.production  # Add production secrets

# 5. Deploy application
docker-compose -f infrastructure/docker-compose.production.yml up -d

# 6. Setup SSL certificates
sudo certbot --nginx -d chronoscraper.com -d api.chronoscraper.com
```

### CI/CD Integration
Example GitHub Actions workflow:
```yaml
name: Deploy to Production
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy to server
        uses: appleboy/ssh-action@v0.1.5
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ubuntu
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          port: 2222
          script: |
            cd /opt/chrono-scraper
            git pull origin main
            docker-compose -f infrastructure/docker-compose.production.yml up -d --build
```

## Troubleshooting

### Common Issues

#### High Memory Usage
```bash
# Check container memory usage
docker stats --no-stream

# Restart memory-heavy services
docker-compose restart firecrawl-playwright celery_worker

# Clear cache if needed
docker exec redis redis-cli FLUSHDB
```

#### Database Connection Issues
```bash
# Check PostgreSQL status
docker exec postgres pg_isready -U chrono_scraper

# View database logs
docker logs postgres

# Restart database
docker-compose restart postgres
```

#### SSL Certificate Issues
```bash
# Renew certificates manually
sudo certbot renew --dry-run

# Check certificate status
sudo certbot certificates

# Force renewal
sudo certbot renew --force-renewal
```

### Performance Optimization

#### Database Tuning
```sql
-- Check slow queries
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC LIMIT 10;

-- Analyze table statistics  
ANALYZE;

-- Vacuum full if needed (during maintenance window)
VACUUM FULL;
```

#### Container Optimization
```bash
# Clean unused Docker resources
docker system prune -af
docker volume prune -f

# Optimize image sizes
docker-compose build --no-cache

# Monitor resource usage
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

## Support & Documentation

### Key Files
- `main.tf`: Core infrastructure definitions
- `variables.tf`: Configurable parameters
- `outputs.tf`: Deployment information
- `cloud-init.yml`: Server initialization script
- `terraform.tfvars.example`: Configuration template

### Helpful Commands
```bash
# View infrastructure state
terraform show

# Plan configuration changes
terraform plan

# Update infrastructure
terraform apply

# Destroy infrastructure (careful!)
terraform destroy

# SSH with port forwarding (for local debugging)
ssh -p 2222 -L 5432:localhost:5432 -L 6379:localhost:6379 ubuntu@<server-ip>
```

### Getting Help
- **Hetzner Docs**: https://docs.hetzner.com/cloud/
- **Terraform Registry**: https://registry.terraform.io/providers/hetznercloud/hcloud/
- **Discord/Slack**: Join project community channels
- **GitHub Issues**: Report bugs and feature requests

This infrastructure setup provides a solid foundation for production deployment of Chrono Scraper v2 while maintaining strict budget constraints and offering clear scaling paths as your business grows.