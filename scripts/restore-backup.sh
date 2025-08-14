#!/bin/bash

# Restore Script for Chrono Scraper
# Restores from full backup created by backup-full.sh

set -e

# Configuration
PROJECT_NAME="chrono-scraper"
BACKUP_BASE="/var/backups/${PROJECT_NAME}"
LOG_FILE="/var/log/${PROJECT_NAME}-restore.log"

# Functions
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a ${LOG_FILE}
}

error() {
    echo "[ERROR] $1" | tee -a ${LOG_FILE}
    exit 1
}

# Check arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    echo "Available backups:"
    ls -lh ${BACKUP_BASE}/${PROJECT_NAME}_full_*.tar.gz 2>/dev/null || echo "No backups found"
    exit 1
fi

BACKUP_FILE=$1

if [ ! -f "${BACKUP_FILE}" ]; then
    error "Backup file not found: ${BACKUP_FILE}"
fi

# Confirmation
echo "WARNING: This will restore from backup and overwrite existing data!"
read -p "Are you sure you want to continue? (yes/no) " -r
if [[ ! $REPLY == "yes" ]]; then
    echo "Restore cancelled"
    exit 0
fi

log "Starting restore from ${BACKUP_FILE}"

# Create temporary directory
TEMP_DIR=$(mktemp -d)
log "Extracting backup to ${TEMP_DIR}"

# Extract backup
tar xzf ${BACKUP_FILE} -C ${TEMP_DIR}
BACKUP_DIR=$(find ${TEMP_DIR} -maxdepth 1 -type d | tail -1)

# Stop services
log "Stopping services..."
docker compose -f docker-compose.production.yml down

# Restore configuration files
if [ -f "${BACKUP_DIR}/configs.tar.gz" ]; then
    log "Restoring configuration files..."
    tar xzf ${BACKUP_DIR}/configs.tar.gz -C .
fi

# Load environment
if [ -f .env.production ]; then
    export $(grep -v '^#' .env.production | xargs)
fi

# Restore Docker volumes
log "Restoring Docker volumes..."

# PostgreSQL data
if [ -f "${BACKUP_DIR}/postgres_data.tar.gz" ]; then
    log "Restoring PostgreSQL data..."
    docker volume create chrono-scraper_postgres_data 2>/dev/null || true
    docker run --rm -v chrono-scraper_postgres_data:/data -v ${BACKUP_DIR}:/backup alpine \
        sh -c "rm -rf /data/* && tar xzf /backup/postgres_data.tar.gz -C /data"
fi

# Redis data
if [ -f "${BACKUP_DIR}/redis_data.tar.gz" ]; then
    log "Restoring Redis data..."
    docker volume create chrono-scraper_redis_data 2>/dev/null || true
    docker run --rm -v chrono-scraper_redis_data:/data -v ${BACKUP_DIR}:/backup alpine \
        sh -c "rm -rf /data/* && tar xzf /backup/redis_data.tar.gz -C /data"
fi

# Meilisearch data
if [ -f "${BACKUP_DIR}/meilisearch_data.tar.gz" ]; then
    log "Restoring Meilisearch data..."
    docker volume create chrono-scraper_meilisearch_data 2>/dev/null || true
    docker run --rm -v chrono-scraper_meilisearch_data:/data -v ${BACKUP_DIR}:/backup alpine \
        sh -c "rm -rf /data/* && tar xzf /backup/meilisearch_data.tar.gz -C /data"
fi

# Traefik certificates
if [ -f "${BACKUP_DIR}/letsencrypt.tar.gz" ]; then
    log "Restoring SSL certificates..."
    docker volume create letsencrypt 2>/dev/null || true
    docker run --rm -v letsencrypt:/data -v ${BACKUP_DIR}:/backup alpine \
        sh -c "rm -rf /data/* && tar xzf /backup/letsencrypt.tar.gz -C /data"
fi

# Alternative: Restore from SQL dump if available
if [ -f "${BACKUP_DIR}/postgres_full.sql.gz" ]; then
    log "Found SQL dump, preparing to restore..."
    
    # Start only PostgreSQL
    docker compose -f docker-compose.production.yml up -d postgres
    
    # Wait for PostgreSQL to be ready
    sleep 10
    
    # Restore database
    log "Restoring database from SQL dump..."
    gunzip -c ${BACKUP_DIR}/postgres_full.sql.gz | \
        docker exec -i chrono-postgres psql -U ${POSTGRES_USER}
fi

# Clean up temporary directory
rm -rf ${TEMP_DIR}

# Start services
log "Starting services..."
docker compose -f docker-compose.traefik.yml up -d
sleep 5
docker compose -f docker-compose.production.yml up -d

# Wait for services to be healthy
log "Waiting for services to be healthy..."
sleep 30

# Verify services
log "Verifying services..."
docker compose -f docker-compose.production.yml ps

log "Restore completed successfully!"
echo
echo "Please verify that all services are running correctly:"
echo "  - Frontend: https://chronoscraper.com"
echo "  - API: https://api.chronoscraper.com"
echo "  - Check logs: docker compose -f docker-compose.production.yml logs -f"

exit 0