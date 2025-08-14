#!/bin/bash

# Production Deployment Script for Chrono Scraper with Traefik
# This script deploys the application with SSL certificates via Let's Encrypt

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DOMAIN="chronoscraper.com"
PROJECT_NAME="chrono-scraper"
BACKUP_DIR="/var/backups/${PROJECT_NAME}"
LOG_FILE="/var/log/${PROJECT_NAME}-deploy.log"

# Functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a ${LOG_FILE}
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a ${LOG_FILE}
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a ${LOG_FILE}
}

# Check if running as root or with sudo
if [[ $EUID -ne 0 ]]; then
   error "This script must be run as root or with sudo"
fi

log "Starting production deployment for ${DOMAIN}"

# 1. Check prerequisites
log "Checking prerequisites..."

# Check Docker
if ! command -v docker &> /dev/null; then
    error "Docker is not installed. Please install Docker first."
fi

# Check Docker Compose
if ! command -v docker compose &> /dev/null; then
    error "Docker Compose is not installed. Please install Docker Compose first."
fi

# Check if .env.production exists
if [ ! -f .env.production ]; then
    error ".env.production file not found. Please create it from .env.production.example"
fi

# 2. Load environment variables
log "Loading environment variables..."
export $(grep -v '^#' .env.production | xargs)

# 3. Validate critical environment variables
log "Validating configuration..."
required_vars=(
    "POSTGRES_PASSWORD"
    "SECRET_KEY"
    "JWT_SECRET_KEY"
    "MEILISEARCH_MASTER_KEY"
    "MAILGUN_API_KEY"
    "LETSENCRYPT_EMAIL"
)

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ] || [[ "${!var}" == *"CHANGE_THIS"* ]]; then
        error "Please set ${var} in .env.production file"
    fi
done

# 4. Create required directories
log "Creating required directories..."
mkdir -p ${BACKUP_DIR}
mkdir -p /var/log/${PROJECT_NAME}
mkdir -p traefik/logs

# 5. Create Docker network for Traefik
log "Creating Docker network..."
docker network create traefik-public 2>/dev/null || true

# 6. Backup existing data (if any)
if [ -d "${BACKUP_DIR}" ]; then
    log "Creating backup of existing data..."
    timestamp=$(date +%Y%m%d_%H%M%S)
    backup_file="${BACKUP_DIR}/backup_${timestamp}.tar.gz"
    
    # Backup database if running
    if docker ps | grep -q chrono-postgres; then
        log "Backing up PostgreSQL database..."
        docker exec chrono-postgres pg_dump -U ${POSTGRES_USER} ${POSTGRES_DB} > ${BACKUP_DIR}/db_${timestamp}.sql
    fi
    
    # Backup volumes
    log "Backing up Docker volumes..."
    docker run --rm -v chrono-scraper_postgres_data:/data -v ${BACKUP_DIR}:/backup alpine tar czf /backup/postgres_data_${timestamp}.tar.gz -C /data .
    docker run --rm -v chrono-scraper_meilisearch_data:/data -v ${BACKUP_DIR}:/backup alpine tar czf /backup/meilisearch_data_${timestamp}.tar.gz -C /data .
fi

# 7. Stop existing services (if running)
if docker compose -f docker-compose.production.yml ps --quiet 2>/dev/null; then
    log "Stopping existing services..."
    docker compose -f docker-compose.production.yml down
fi

# 8. Build images
log "Building Docker images..."
docker compose -f docker-compose.production.yml build --no-cache

# 9. Start Traefik first
log "Starting Traefik reverse proxy..."
docker compose -f docker-compose.traefik.yml up -d

# Wait for Traefik to be ready
log "Waiting for Traefik to be ready..."
sleep 10

# Check Traefik health
if ! docker exec traefik traefik healthcheck --ping; then
    error "Traefik failed to start properly"
fi

# 10. Start application services
log "Starting application services..."
docker compose -f docker-compose.production.yml up -d

# 11. Wait for services to be healthy
log "Waiting for services to be healthy..."
services=("chrono-backend" "chrono-frontend" "chrono-postgres" "chrono-redis" "chrono-meilisearch")
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    all_healthy=true
    for service in "${services[@]}"; do
        if ! docker ps | grep -q "${service}.*healthy"; then
            all_healthy=false
            break
        fi
    done
    
    if $all_healthy; then
        log "All services are healthy!"
        break
    fi
    
    attempt=$((attempt + 1))
    if [ $attempt -eq $max_attempts ]; then
        error "Services failed to become healthy after ${max_attempts} attempts"
    fi
    
    echo -n "."
    sleep 10
done

# 12. Run database migrations
log "Running database migrations..."
docker compose -f docker-compose.production.yml exec -T backend alembic upgrade head

# 13. Initialize Meilisearch indexes
log "Initializing Meilisearch indexes..."
docker compose -f docker-compose.production.yml exec -T backend python -c "
from app.services.meilisearch_service import MeilisearchService
import asyncio

async def init():
    service = MeilisearchService()
    await service.initialize_indexes()
    print('Meilisearch indexes initialized')

asyncio.run(init())
"

# 14. Create superuser (optional)
read -p "Do you want to create a superuser account? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log "Creating superuser..."
    docker compose -f docker-compose.production.yml exec backend python -c "
from app.models.user import User
from app.core.database import get_db
from app.core.auth import get_password_hash
import asyncio

async def create_superuser():
    email = input('Email: ')
    password = input('Password: ')
    
    async for db in get_db():
        user = User(
            email=email,
            hashed_password=get_password_hash(password),
            is_active=True,
            is_superuser=True,
            is_verified=True,
            is_professional=True
        )
        db.add(user)
        await db.commit()
        print(f'Superuser {email} created successfully')

asyncio.run(create_superuser())
"
fi

# 15. SSL Certificate check
log "Checking SSL certificates..."
max_cert_attempts=10
cert_attempt=0

while [ $cert_attempt -lt $max_cert_attempts ]; do
    if docker exec traefik cat /letsencrypt/acme.json 2>/dev/null | grep -q "${DOMAIN}"; then
        log "SSL certificates obtained successfully!"
        break
    fi
    
    cert_attempt=$((cert_attempt + 1))
    if [ $cert_attempt -eq $max_cert_attempts ]; then
        warning "SSL certificates not yet obtained. Please check Traefik logs."
    fi
    
    echo -n "."
    sleep 10
done

# 16. Set up cron jobs for backups
log "Setting up automated backups..."
cat > /etc/cron.d/${PROJECT_NAME}-backup << EOF
# Daily database backup at 3 AM
0 3 * * * root docker exec chrono-postgres pg_dump -U ${POSTGRES_USER} ${POSTGRES_DB} | gzip > ${BACKUP_DIR}/db_\$(date +\%Y\%m\%d).sql.gz

# Weekly full backup on Sunday at 4 AM
0 4 * * 0 root ${PWD}/scripts/backup-full.sh

# Clean old backups (keep last 30 days)
0 5 * * * root find ${BACKUP_DIR} -name "*.gz" -mtime +30 -delete
EOF

# 17. Set up monitoring
log "Setting up monitoring..."
cat > /usr/local/bin/${PROJECT_NAME}-health-check.sh << 'EOF'
#!/bin/bash
# Health check script for Chrono Scraper

SERVICES=("chrono-backend" "chrono-frontend" "chrono-postgres" "chrono-redis" "chrono-meilisearch" "traefik")
ALERT_EMAIL="${LETSENCRYPT_EMAIL}"

for service in "${SERVICES[@]}"; do
    if ! docker ps | grep -q "${service}.*healthy"; then
        echo "Service ${service} is unhealthy" | mail -s "Chrono Scraper Alert: ${service} unhealthy" ${ALERT_EMAIL}
        # Attempt to restart the service
        docker restart ${service}
    fi
done

# Check SSL certificate expiry
cert_expiry=$(docker exec traefik sh -c 'openssl x509 -enddate -noout -in /letsencrypt/certificates/$(ls /letsencrypt/certificates/ | head -1)' 2>/dev/null | cut -d= -f2)
if [ ! -z "$cert_expiry" ]; then
    expiry_epoch=$(date -d "${cert_expiry}" +%s)
    current_epoch=$(date +%s)
    days_until_expiry=$(( ($expiry_epoch - $current_epoch) / 86400 ))
    
    if [ $days_until_expiry -lt 7 ]; then
        echo "SSL certificate expires in ${days_until_expiry} days" | mail -s "Chrono Scraper Alert: SSL Certificate Expiry Warning" ${ALERT_EMAIL}
    fi
fi
EOF

chmod +x /usr/local/bin/${PROJECT_NAME}-health-check.sh

# Add health check to cron
echo "*/5 * * * * root /usr/local/bin/${PROJECT_NAME}-health-check.sh" >> /etc/cron.d/${PROJECT_NAME}-backup

# 18. Display status
log "Deployment completed successfully!"
echo
echo "=================================================================================="
echo "                        CHRONO SCRAPER DEPLOYMENT COMPLETE                        "
echo "=================================================================================="
echo
echo "Access your application at:"
echo "  - Frontend: https://${DOMAIN}"
echo "  - API: https://api.${DOMAIN}"
echo "  - API Docs: https://api.${DOMAIN}/docs"
echo "  - Traefik Dashboard: https://traefik.${DOMAIN} (requires authentication)"
echo
echo "Service Status:"
docker compose -f docker-compose.production.yml ps
echo
echo "To view logs:"
echo "  - All services: docker compose -f docker-compose.production.yml logs -f"
echo "  - Specific service: docker compose -f docker-compose.production.yml logs -f [service_name]"
echo "  - Traefik: docker compose -f docker-compose.traefik.yml logs -f"
echo
echo "To stop services:"
echo "  - docker compose -f docker-compose.production.yml down"
echo "  - docker compose -f docker-compose.traefik.yml down"
echo
echo "Backup location: ${BACKUP_DIR}"
echo "Log file: ${LOG_FILE}"
echo
warning "IMPORTANT: Please ensure all CHANGE_THIS values in .env.production are updated!"
warning "IMPORTANT: Update Traefik dashboard password in traefik/config/middleware.yml"
echo "=================================================================================="