# Chrono Scraper v2 Scaling Strategy

## Executive Summary

This document outlines a comprehensive scaling strategy for Chrono Scraper v2, starting from a single Hetzner CX32 server (€25.85/month) and scaling to a distributed infrastructure supporting enterprise workloads (€200+/month).

## Scaling Phases Overview

### Phase 0: Development (Current)
- **Infrastructure:** Local Docker Compose
- **Cost:** €0
- **Users:** 1-5 developers
- **Focus:** Feature development and testing

### Phase 1: Initial Production
- **Infrastructure:** Single Hetzner CX32 (4 vCPU, 8GB RAM, 80GB NVMe)
- **Cost:** €25.85/month
- **Users:** 0-100 active users
- **Revenue Target:** €0-500/month
- **Focus:** MVP validation, initial user acquisition

### Phase 2: Service Separation
- **Infrastructure:** 2x Hetzner CX22 (2 vCPU, 4GB RAM each)
- **Cost:** €31.90/month
- **Users:** 100-500 active users  
- **Revenue Target:** €500-2000/month
- **Focus:** Performance optimization, reliability

### Phase 3: Horizontal Scaling
- **Infrastructure:** 1x CX32 + 2x CX22 + 1x CPX21
- **Cost:** €65.35/month
- **Users:** 500-2000 active users
- **Revenue Target:** €2000-5000/month
- **Focus:** High availability, load distribution

### Phase 4: Multi-Region
- **Infrastructure:** 3x CX32 + 2x CX41 + CDN
- **Cost:** €150-200/month
- **Users:** 2000-10000 active users
- **Revenue Target:** €5000-15000/month
- **Focus:** Global distribution, enterprise features

### Phase 5: Enterprise
- **Infrastructure:** Kubernetes cluster + managed services
- **Cost:** €200+/month
- **Users:** 10000+ active users
- **Revenue Target:** €15000+/month
- **Focus:** Auto-scaling, compliance, SLAs

## Scaling Triggers Matrix

| Metric | Phase 1→2 | Phase 2→3 | Phase 3→4 | Phase 4→5 |
|--------|-----------|-----------|-----------|-----------|
| **CPU Usage (7-day avg)** | >70% | >75% | >80% | >85% |
| **Memory Usage** | >6GB | >85% | >85% | >90% |
| **Active Users** | >100 | >500 | >2000 | >10000 |
| **Concurrent Scrapes** | >10 | >50 | >200 | >1000 |
| **Database Size** | >20GB | >50GB | >200GB | >1TB |
| **API Requests/min** | >100 | >500 | >2000 | >10000 |
| **Revenue/month** | >€500 | >€2000 | >€5000 | >€15000 |
| **Response Time p95** | >2s | >1.5s | >1s | >500ms |
| **Error Rate** | >1% | >0.5% | >0.1% | >0.05% |

## Phase 1: Single Server Deployment

### Architecture
```
Hetzner CX32 (4 vCPU, 8GB RAM, 80GB NVMe)
├── Nginx (Reverse Proxy + Static Files)
├── Docker Swarm (Single Node)
│   ├── Backend API (1GB RAM)
│   ├── Frontend (512MB RAM)
│   ├── PostgreSQL (2GB RAM)
│   ├── Redis (512MB RAM)
│   ├── Meilisearch (1GB RAM)
│   ├── Celery Workers (2x 512MB)
│   └── Firecrawl Services (1.5GB RAM)
└── Monitoring (Prometheus + Grafana)
```

### Resource Allocation
- **System + Docker:** 1GB RAM
- **Application Services:** 3.5GB RAM
- **Database/Cache:** 2.5GB RAM
- **Buffer/Burst:** 1GB RAM

### Deployment Script
See `scripts/deploy/phase1_single_server.sh`

### Monitoring Setup
- Prometheus metrics collection
- Grafana dashboards
- Alert rules for scaling triggers
- Automated health checks

## Phase 2: Initial Service Separation

### Migration Trigger Decision
When 3+ of these conditions are met:
- CPU usage >70% for 7 consecutive days
- Memory usage consistently >6GB
- Active users >100
- Database size >20GB
- Revenue >€500/month

### Architecture
```
Server 1: CX22 (Application Layer)
├── Nginx
├── Backend API
├── Frontend
└── Celery Workers

Server 2: CX22 (Data Layer)
├── PostgreSQL (Primary)
├── Redis
├── Meilisearch
└── PostgreSQL Backup
```

### Migration Procedure
1. **Pre-Migration (T-7 days)**
   - Set up monitoring on new servers
   - Configure networking between servers
   - Test connectivity and performance

2. **Data Migration (T-1 day)**
   - Create PostgreSQL replica on Server 2
   - Sync Meilisearch indexes
   - Configure Redis persistence

3. **Cutover (Maintenance Window)**
   - Put application in maintenance mode
   - Final data sync
   - Update connection strings
   - Switch DNS
   - Verify functionality
   - Remove maintenance mode

4. **Post-Migration**
   - Monitor performance metrics
   - Optimize configurations
   - Update backup procedures

### Rollback Plan
- Keep Phase 1 server running for 48 hours
- Maintain database replication
- One-command rollback script ready

## Phase 3: Horizontal Scaling

### Architecture
```
Load Balancer: CPX21
├── Backend Servers (2x CX22)
│   ├── Backend API instances
│   └── Celery Workers
├── Frontend Server (CX22)
│   └── SvelteKit + Nginx
└── Database Server (CX32)
    ├── PostgreSQL Primary
    ├── PostgreSQL Replica
    ├── Redis Cluster
    └── Meilisearch
```

### Key Changes
- Introduction of load balancing (HAProxy)
- Stateless backend with session management in Redis
- Database replication for read scaling
- Distributed Celery workers

### Scaling Automation
- Auto-scaling based on metrics
- Blue-green deployments
- Rolling updates for zero downtime
- Automated health checks and failover

## Phase 4: Multi-Region Distribution

### Architecture
```
Global Load Balancer (Cloudflare)
├── EU Region (Frankfurt)
│   ├── Application Cluster
│   └── Database Primary
├── US Region (Virginia)
│   ├── Application Cluster
│   └── Database Replica
└── CDN (Static Assets)
```

### Data Strategy
- Primary database in EU (GDPR compliance)
- Read replicas in other regions
- Cross-region replication <100ms
- Geo-routing for lowest latency

### Cost Optimization
- Reserved instances for predictable workloads
- Spot instances for batch processing
- CDN for static assets
- Database connection pooling

## Phase 5: Enterprise Kubernetes

### Migration to Kubernetes
- Managed Kubernetes (Hetzner Cloud or DO)
- Helm charts for deployments
- GitOps with ArgoCD
- Service mesh (Istio/Linkerd)

### Enterprise Features
- Multi-tenancy support
- RBAC and SSO integration
- Compliance certifications
- 99.9% SLA guarantee
- 24/7 support

## Automated Scaling Tools

### Scaling Decision Tool
See `scripts/scaling/scaling_decision.py`
- Analyzes current metrics
- Recommends scaling actions
- Estimates costs
- Generates migration plan

### Migration Automation
See `scripts/scaling/migrate_phase.sh`
- Automated backup procedures
- Service migration scripts
- Data synchronization
- Health check validation
- Rollback capabilities

## Cost Analysis by Phase

| Phase | Monthly Cost | Cost per User | Infrastructure | Key Benefits |
|-------|--------------|---------------|----------------|--------------|
| 1 | €25.85 | €0.26-2.58 | 1x CX32 | Simple, low cost |
| 2 | €31.90 | €0.06-0.32 | 2x CX22 | Better isolation |
| 3 | €65.35 | €0.03-0.13 | Mixed fleet | High availability |
| 4 | €150-200 | €0.02-0.10 | Multi-region | Global reach |
| 5 | €200+ | €0.02-0.05 | Kubernetes | Auto-scaling |

## Performance Expectations

### Phase 1 Performance
- **API Response Time:** <500ms p50, <2s p95
- **Concurrent Users:** Up to 50
- **Scraping Throughput:** 10 pages/second
- **Search Latency:** <100ms
- **Uptime:** 99.5%

### Phase 5 Performance
- **API Response Time:** <50ms p50, <200ms p95
- **Concurrent Users:** 10,000+
- **Scraping Throughput:** 1000+ pages/second
- **Search Latency:** <20ms
- **Uptime:** 99.99%

## Risk Mitigation

### Backup Strategy
- **Phase 1-2:** Daily snapshots, 7-day retention
- **Phase 3-4:** Hourly snapshots, 30-day retention
- **Phase 5:** Continuous replication, 90-day retention

### Disaster Recovery
- **RTO (Recovery Time Objective):**
  - Phase 1-2: 4 hours
  - Phase 3-4: 1 hour
  - Phase 5: 15 minutes

- **RPO (Recovery Point Objective):**
  - Phase 1-2: 24 hours
  - Phase 3-4: 1 hour
  - Phase 5: 5 minutes

### Security Considerations
- TLS everywhere (Let's Encrypt)
- Network isolation between services
- Regular security updates
- Intrusion detection (Fail2ban)
- DDoS protection (Cloudflare in Phase 4+)

## Implementation Timeline

### Month 1-3: Phase 1
- Deploy to single CX32 server
- Set up monitoring and alerting
- Establish backup procedures
- Document operational procedures

### Month 4-6: Prepare Phase 2
- Develop migration scripts
- Test service separation locally
- Plan maintenance windows
- Train team on new procedures

### Month 7-12: Scale as Needed
- Monitor scaling triggers
- Execute migrations based on metrics
- Optimize based on real usage
- Refine automation tools

## Operational Procedures

### Daily Operations
- Monitor dashboard (5 min)
- Check alert queue
- Review performance metrics
- Verify backup completion

### Weekly Operations
- Analyze scaling metrics
- Review cost optimization
- Update capacity planning
- Security patches

### Monthly Operations
- Scaling decision review
- Cost analysis
- Performance optimization
- Disaster recovery test

## Success Metrics

### Technical KPIs
- API response time <95th percentile target
- Uptime percentage
- Error rate <0.1%
- Database query time <100ms
- Cache hit ratio >90%

### Business KPIs
- Cost per user trending down
- Revenue per infrastructure € >20
- User satisfaction score >4.5
- Support ticket volume <5% users

## Conclusion

This scaling strategy provides a clear path from a €25.85/month single server to a distributed enterprise infrastructure. The key principles are:

1. **Start small:** Validate the business before scaling infrastructure
2. **Scale based on metrics:** Use data-driven triggers, not assumptions
3. **Automate everything:** Reduce human error and operational burden
4. **Maintain simplicity:** Don't over-engineer for imaginary scale
5. **Preserve performance:** Each scaling phase should improve user experience
6. **Control costs:** Infrastructure should scale linearly with revenue

The automated tools and clear procedures ensure smooth transitions between phases with minimal risk and downtime.