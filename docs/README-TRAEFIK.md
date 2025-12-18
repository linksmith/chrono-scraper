# Traefik Production Deployment Guide

This guide explains how to deploy Chrono Scraper with Traefik as a reverse proxy, including automatic SSL certificates from Let's Encrypt.

## Architecture

The production setup uses:
- **Traefik**: Reverse proxy with automatic SSL/TLS termination
- **Let's Encrypt**: Free SSL certificates with auto-renewal
- **Docker Networks**: Secure internal communication between services
- **Health Checks**: Automated monitoring and recovery

## Prerequisites

1. A server with Docker and Docker Compose installed
2. Domain name pointing to your server:
   - `chronoscraper.com` → Your server IP
   - `api.chronoscraper.com` → Your server IP  
   - `traefik.chronoscraper.com` → Your server IP (optional, for dashboard)
3. Ports 80 and 443 open in firewall
4. At least 4GB RAM and 20GB disk space

## Quick Start

### 1. Configure Environment

```bash
# Copy production environment template
cp .env.production.example .env.production

# Edit with your actual values
nano .env.production
```

**Critical variables to update:**
- All passwords (POSTGRES_PASSWORD, SECRET_KEY, etc.)
- Email configuration (MAILGUN_API_KEY or SMTP settings)
- LLM API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY)
- LETSENCRYPT_EMAIL (for SSL notifications)

### 2. Deploy

```bash
# Run the deployment script
sudo ./scripts/deploy-production.sh
```

The script will:
- Create Docker networks
- Build and start all services
- Obtain SSL certificates
- Run database migrations
- Set up automated backups
- Configure health monitoring

### 3. Manual Deployment (Alternative)

If you prefer manual deployment:

```bash
# Create Docker network
docker network create traefik-public

# Start Traefik
docker compose -f docker-compose.traefik.yml up -d

# Start application
docker compose -f docker-compose.production.yml up -d

# Run migrations
docker compose -f docker-compose.production.yml exec backend alembic upgrade head
```

## Configuration Details

### Traefik Configuration

Main configuration: `traefik/traefik.yml`
- HTTP → HTTPS redirect
- Let's Encrypt integration
- Rate limiting
- Security headers
- Prometheus metrics

### Middleware

Configuration: `traefik/config/middleware.yml`
- CORS for API
- Compression
- Authentication for dashboard
- Custom rate limits

### Service Labels

Each service in `docker-compose.production.yml` has Traefik labels:
- Router rules (domain matching)
- TLS configuration
- Middleware chains
- Health checks

## Security Features

### SSL/TLS
- Automatic certificate generation via Let's Encrypt
- Auto-renewal before expiry
- Strong cipher suites
- HSTS headers

### Rate Limiting
- Global: 100 req/min per IP
- API: 30 req/min per IP
- Configurable per endpoint

### Security Headers
- X-Frame-Options: SAMEORIGIN
- X-Content-Type-Options: nosniff
- X-XSS-Protection: 1; mode=block
- Referrer-Policy: strict-origin-when-cross-origin
- Custom CSP policies

### Network Isolation
- `traefik-public`: External-facing network
- `chrono-internal`: Internal services only
- Database not exposed externally

## Monitoring

### Health Checks
All services have health check endpoints:
- Backend: `/api/v1/health`
- Frontend: `/health`
- Traefik: `/ping`

### Logs
```bash
# View all logs
docker compose -f docker-compose.production.yml logs -f

# Traefik logs
docker compose -f docker-compose.traefik.yml logs -f

# Specific service
docker compose -f docker-compose.production.yml logs -f backend
```

### Metrics
Prometheus metrics available at:
- `https://traefik.chronoscraper.com/metrics`

## Backup & Recovery

### Automated Backups
Daily database backups and weekly full backups are configured via cron.

### Manual Backup
```bash
sudo ./scripts/backup-full.sh
```

### Restore from Backup
```bash
sudo ./scripts/restore-backup.sh /var/backups/chrono-scraper/backup_file.tar.gz
```

## Maintenance

### Update Application
```bash
# Pull latest code
git pull

# Rebuild and restart
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d
```

### Renew Certificates (Manual)
Certificates auto-renew, but to force renewal:
```bash
docker exec traefik traefik renew --cert
```

### Scale Services
```bash
# Scale backend workers
docker compose -f docker-compose.production.yml up -d --scale celery_worker=4
```

## Troubleshooting

### SSL Certificate Issues
```bash
# Check certificate status
docker exec traefik cat /letsencrypt/acme.json | jq

# Use staging server for testing
# Edit traefik/traefik.yml and uncomment staging caServer
```

### Service Not Accessible
```bash
# Check service health
docker ps --format "table {{.Names}}\t{{.Status}}"

# Check Traefik routing
docker exec traefik traefik show routers

# Check network connectivity
docker network inspect traefik-public
```

### High Load
```bash
# Check resource usage
docker stats

# Increase rate limits in traefik/config/middleware.yml
# Scale services as needed
```

## Production Checklist

- [ ] Update all passwords in `.env.production`
- [ ] Configure email service (Mailgun or SMTP)
- [ ] Set up DNS records for all domains
- [ ] Configure firewall (ports 80, 443)
- [ ] Enable automated backups
- [ ] Set up monitoring alerts
- [ ] Test SSL certificates
- [ ] Verify health checks working
- [ ] Document admin credentials
- [ ] Set up log rotation

## Support

For issues or questions:
1. Check logs: `docker compose logs -f`
2. Review Traefik dashboard: `https://traefik.chronoscraper.com`
3. Check service health: `docker ps`
4. Review this documentation

## Advanced Configuration

### Custom Domain
To use a different domain, update:
1. `.env.production` - DOMAIN variables
2. `docker-compose.production.yml` - Traefik labels
3. DNS records

### Multiple Environments
You can run staging and production on same server:
```bash
# Use different compose files and networks
docker compose -f docker-compose.staging.yml up -d
```

### CDN Integration
Add CDN (CloudFlare, Fastly) by:
1. Pointing CDN to your server
2. Configuring SSL mode to "Full (strict)"
3. Setting up page rules for caching