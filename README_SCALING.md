# Chrono Scraper v2 - Scaling Guide

This guide provides step-by-step instructions for scaling Chrono Scraper v2 from a single server deployment to a distributed enterprise infrastructure.

## Quick Start

### 1. Analyze Current State
```bash
# Get scaling recommendation
make scaling-analyze

# View real-time metrics dashboard
make scaling-dashboard

# Check current costs
make cost-current
```

### 2. Deploy to Production (Phase 1)
```bash
# Dry run deployment
make deploy-phase1-dry-run DOMAIN=your-domain.com EMAIL=admin@your-domain.com

# Actual deployment
make deploy-phase1 DOMAIN=your-domain.com EMAIL=admin@your-domain.com
```

### 3. Monitor and Scale
```bash
# Monitor scaling metrics
make scaling-metrics

# When ready to scale
make migrate-phase-1-to-2
```

## Scaling Phases Overview

### Phase 1: Single Server (€25.85/month)
- **Infrastructure**: 1x Hetzner CX32 (4 vCPU, 8GB RAM)
- **Capacity**: 0-100 users
- **Use Case**: MVP validation, initial user acquisition
- **Deployment**: `make deploy-phase1`

### Phase 2: Service Separation (€31.90/month)
- **Infrastructure**: 2x Hetzner CX22 (application + database separation)
- **Capacity**: 100-500 users
- **Use Case**: Performance optimization, reliability improvement
- **Migration**: `make migrate-phase-1-to-2`

### Phase 3: Horizontal Scaling (€65.35/month)
- **Infrastructure**: Load balancer + multiple application servers
- **Capacity**: 500-2000 users
- **Use Case**: High availability, load distribution
- **Migration**: `make migrate-phase-2-to-3`

### Phase 4: Multi-Region (€150-200/month)
- **Infrastructure**: Global distribution, CDN, cross-region replication
- **Capacity**: 2000-10000 users
- **Use Case**: Global reach, enterprise features

### Phase 5: Enterprise Kubernetes (€200+/month)
- **Infrastructure**: Auto-scaling K8s cluster
- **Capacity**: 10000+ users
- **Use Case**: Enterprise compliance, SLAs, auto-scaling

## Scaling Decision Matrix

| Metric | Phase 1→2 | Phase 2→3 | Phase 3→4 | Phase 4→5 |
|--------|-----------|-----------|-----------|-----------|
| CPU Usage (7-day avg) | >70% | >75% | >80% | >85% |
| Memory Usage | >75% | >85% | >85% | >90% |
| Active Users | >100 | >500 | >2000 | >10000 |
| Database Size | >20GB | >50GB | >200GB | >1TB |
| Monthly Revenue | >€500 | >€2000 | >€5000 | >€15000 |

## Available Commands

### Analysis and Monitoring
```bash
make scaling-analyze              # Analyze scaling needs
make scaling-analyze-json         # JSON output for automation
make scaling-report              # Comprehensive report
make scaling-dashboard           # Real-time dashboard
make scaling-metrics             # Current metrics
make scaling-thresholds          # View trigger thresholds
```

### Cost Optimization
```bash
make cost-optimize               # Analyze cost optimization
make cost-optimize-report        # Generate cost report
make cost-current               # Current cost breakdown
make cost-projection            # Cost projections by phase
```

### Migration and Deployment
```bash
make deploy-phase1              # Deploy Phase 1 production
make deploy-phase1-dry-run      # Test Phase 1 deployment
make migrate-phase-1-to-2       # Scale to Phase 2
make migrate-phase-2-to-3       # Scale to Phase 3
```

### Backup and Recovery
```bash
make backup-pre-scaling         # Create backup before scaling
make backup-restore BACKUP_DIR=path/to/backup  # Restore backup
```

## Automated Scaling Tools

### 1. Scaling Decision Tool
Analyzes current metrics and provides scaling recommendations:

```bash
# Basic analysis
python3 scripts/scaling/scaling_decision.py --current-phase=1

# Generate report
python3 scripts/scaling/scaling_decision.py --current-phase=1 --output=report.txt

# JSON output for automation
python3 scripts/scaling/scaling_decision.py --current-phase=1 --format=json
```

**Features:**
- Real-time metrics collection
- Business-driven scaling triggers
- Cost-benefit analysis
- Migration complexity assessment
- Rollback planning

### 2. Cost Optimizer
Analyzes resource usage and identifies cost savings:

```bash
# Analyze cost optimization opportunities
python3 scripts/scaling/cost_optimizer.py

# Generate detailed report
python3 scripts/scaling/cost_optimizer.py --output=cost_report.txt --format=text
```

**Optimizations Identified:**
- Under-utilized resources
- Server consolidation opportunities
- Reserved instance savings
- Spot instance opportunities for batch workloads
- Memory and CPU right-sizing

### 3. Migration Automation
Automated migration scripts with safety checks:

```bash
# Dry run migration
./scripts/scaling/migrate_phase.sh --from 1 --to 2 --dry-run

# Execute migration with rollback capability
./scripts/scaling/migrate_phase.sh --from 1 --to 2

# Force migration (skip confirmations)
./scripts/scaling/migrate_phase.sh --from 1 --to 2 --force
```

**Safety Features:**
- Comprehensive pre-migration backups
- Health checks and validation
- Automatic rollback on failure
- Manual rollback procedures
- Progress monitoring and logging

### 4. Real-time Scaling Dashboard
Web-based dashboard for monitoring scaling metrics:

```bash
# Start dashboard on http://localhost:8080
make scaling-dashboard

# Start in background
make scaling-dashboard-bg
```

**Dashboard Features:**
- Real-time metrics visualization
- Scaling recommendations
- Cost projections
- Historical trends
- WebSocket-based updates

## Production Deployment

### Prerequisites
1. **Hetzner Cloud Account**: Sign up and get API token
2. **Domain Name**: Configure DNS to point to your server
3. **Email Account**: For SSL certificates and notifications

### Step 1: Environment Setup
```bash
# Set required environment variables
export HCLOUD_TOKEN="your-hetzner-api-token"
export DOMAIN="your-domain.com"
export EMAIL="admin@your-domain.com"
```

### Step 2: Deploy Phase 1
```bash
# Test deployment (dry run)
make deploy-phase1-dry-run DOMAIN=$DOMAIN EMAIL=$EMAIL

# Deploy to production
make deploy-phase1 DOMAIN=$DOMAIN EMAIL=$EMAIL
```

### Step 3: Post-Deployment
```bash
# Verify deployment
curl https://$DOMAIN/api/v1/health

# Check service status
make status

# Monitor resources
make scaling-dashboard
```

## Monitoring and Alerting

### Key Metrics to Monitor
- **CPU Usage**: 7-day average, peak usage patterns
- **Memory Usage**: Current usage, growth trends
- **Database Size**: Growth rate, query performance
- **Active Users**: 30-day active, growth rate
- **API Performance**: Response times, error rates
- **Queue Length**: Celery task backlogs
- **Cost Metrics**: Monthly spend, cost per user

### Setting Up Alerts
```bash
# In your monitoring system (e.g., Grafana), set up alerts for:
# - CPU usage > 70% for 5 minutes (warning)
# - Memory usage > 85% for 5 minutes (critical)  
# - Error rate > 1% for 5 minutes (warning)
# - Queue length > 100 for 10 minutes (warning)
# - Monthly cost increase > 20% (warning)
```

## Scaling Best Practices

### 1. Gradual Scaling
- Scale one phase at a time
- Monitor performance after each scaling event
- Allow 24-48 hours for performance stabilization
- Keep previous infrastructure running during transitions

### 2. Data-Driven Decisions
- Use automated scaling analysis tools
- Consider business metrics (revenue, user growth) alongside technical metrics
- Factor in seasonal patterns and growth projections
- Review scaling decisions monthly

### 3. Cost Optimization
- Regularly review and optimize resource allocation
- Use cost optimization tools to identify savings
- Consider reserved instances for predictable workloads
- Implement spot instances for batch processing

### 4. Risk Management
- Always create backups before scaling operations
- Test scaling procedures in staging environment
- Have rollback plans ready
- Monitor key performance indicators closely
- Communicate with users about potential maintenance windows

## Troubleshooting

### Migration Failures
```bash
# Check migration logs
tail -f migration.log

# Rollback to previous phase
make backup-restore BACKUP_DIR=backups/20241127_143022_pre_scaling

# Verify rollback success
make status
curl https://$DOMAIN/api/v1/health
```

### Performance Issues After Scaling
```bash
# Check resource usage
make resource-stats

# Analyze cost optimizations
make cost-optimize

# Monitor specific services
docker stats --no-stream

# Check application logs
make logs-backend
```

### Cost Overruns
```bash
# Generate cost optimization report
make cost-optimize-report

# Review current spending
make cost-current

# Analyze resource efficiency
python3 scripts/scaling/cost_optimizer.py --format=json
```

## Support and Resources

### Documentation
- [Scaling Strategy](SCALING_STRATEGY.md) - Comprehensive scaling documentation
- [CLAUDE.md](CLAUDE.md) - Project architecture and commands
- [Hetzner Cloud Documentation](https://docs.hetzner.com/cloud/)

### Tools and Scripts
- `scripts/scaling/scaling_decision.py` - Scaling analysis tool
- `scripts/scaling/cost_optimizer.py` - Cost optimization analyzer
- `scripts/scaling/migrate_phase.sh` - Automated migration script
- `scripts/deploy/phase1_single_server.sh` - Production deployment script
- `scripts/monitoring/scaling_dashboard.py` - Real-time monitoring dashboard

### Getting Help
1. **Check Logs**: Use `make logs` to review service logs
2. **Run Health Checks**: Use `make status` for service status
3. **Review Metrics**: Use `make scaling-metrics` for current state
4. **Generate Reports**: Use `make scaling-report` for detailed analysis

## Example Scaling Timeline

### Months 1-3: Phase 1 Validation
- Deploy single server infrastructure
- Onboard initial users (0-50)
- Monitor resource usage and costs
- Establish baseline performance metrics

### Months 4-6: Growth and Optimization
- Scale to 50-100 users
- Monitor scaling triggers
- Optimize resource allocation
- Prepare for Phase 2 migration

### Months 7-12: Scaling Based on Demand
- Execute Phase 2 migration when triggers are met
- Scale to 100-500 users
- Implement advanced monitoring
- Consider Phase 3 preparation

### Year 2+: Continuous Scaling
- Scale based on business growth
- Implement enterprise features
- Multi-region deployment
- Advanced cost optimization

This scaling strategy provides a clear path from startup to enterprise scale while maintaining cost efficiency and operational simplicity.