#!/bin/bash

# Full Backup Script for Chrono Scraper
# Creates comprehensive backups of all data and configurations

set -e

# Configuration
PROJECT_NAME="chrono-scraper"
BACKUP_BASE="/var/backups/${PROJECT_NAME}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_BASE}/${TIMESTAMP}"
LOG_FILE="/var/log/${PROJECT_NAME}-backup.log"

# Load environment
if [ -f .env.production ]; then
    export $(grep -v '^#' .env.production | xargs)
fi

# Functions
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a ${LOG_FILE}
}

# Create backup directory
mkdir -p ${BACKUP_DIR}
log "Starting full backup to ${BACKUP_DIR}"

# 1. Backup PostgreSQL database
if docker ps | grep -q chrono-postgres; then
    log "Backing up PostgreSQL database..."
    docker exec chrono-postgres pg_dumpall -U ${POSTGRES_USER} | gzip > ${BACKUP_DIR}/postgres_full.sql.gz
    log "Database backup completed"
fi

# 2. Backup Docker volumes
log "Backing up Docker volumes..."

# PostgreSQL data
if docker volume ls | grep -q postgres_data; then
    docker run --rm -v chrono-scraper_postgres_data:/data -v ${BACKUP_DIR}:/backup alpine \
        tar czf /backup/postgres_data.tar.gz -C /data .
fi

# Redis data
if docker volume ls | grep -q redis_data; then
    docker run --rm -v chrono-scraper_redis_data:/data -v ${BACKUP_DIR}:/backup alpine \
        tar czf /backup/redis_data.tar.gz -C /data .
fi

# Meilisearch data
if docker volume ls | grep -q meilisearch_data; then
    docker run --rm -v chrono-scraper_meilisearch_data:/data -v ${BACKUP_DIR}:/backup alpine \
        tar czf /backup/meilisearch_data.tar.gz -C /data .
fi

# Traefik certificates
if docker volume ls | grep -q letsencrypt; then
    docker run --rm -v letsencrypt:/data -v ${BACKUP_DIR}:/backup alpine \
        tar czf /backup/letsencrypt.tar.gz -C /data .
fi

log "Volume backups completed"

# 3. Backup configuration files
log "Backing up configuration files..."
tar czf ${BACKUP_DIR}/configs.tar.gz \
    .env.production \
    docker-compose.production.yml \
    docker-compose.traefik.yml \
    traefik/ \
    2>/dev/null || true

# 4. Create metadata file
cat > ${BACKUP_DIR}/backup_info.txt << EOF
Backup Timestamp: ${TIMESTAMP}
Hostname: $(hostname)
Docker Version: $(docker --version)
Services Running: $(docker ps --format "table {{.Names}}" | tail -n +2 | tr '\n' ' ')
Backup Size: $(du -sh ${BACKUP_DIR} | cut -f1)
EOF

# 5. Compress entire backup
log "Compressing backup..."
cd ${BACKUP_BASE}
tar czf ${PROJECT_NAME}_full_${TIMESTAMP}.tar.gz ${TIMESTAMP}/
rm -rf ${TIMESTAMP}

# 6. Upload to S3 (optional)
if [ ! -z "${AWS_S3_BACKUP_BUCKET}" ]; then
    log "Uploading to S3..."
    aws s3 cp ${BACKUP_BASE}/${PROJECT_NAME}_full_${TIMESTAMP}.tar.gz \
        s3://${AWS_S3_BACKUP_BUCKET}/backups/ \
        --storage-class GLACIER_IR
fi

# 7. Clean old backups (keep last 30 days of full backups)
log "Cleaning old backups..."
find ${BACKUP_BASE} -name "${PROJECT_NAME}_full_*.tar.gz" -mtime +30 -delete

# 8. Send notification
BACKUP_SIZE=$(du -sh ${BACKUP_BASE}/${PROJECT_NAME}_full_${TIMESTAMP}.tar.gz | cut -f1)
log "Backup completed successfully! Size: ${BACKUP_SIZE}"

# Send email notification (optional)
if [ ! -z "${BACKUP_NOTIFICATION_EMAIL}" ]; then
    echo "Full backup completed successfully. Size: ${BACKUP_SIZE}" | \
        mail -s "Chrono Scraper: Backup Completed" ${BACKUP_NOTIFICATION_EMAIL}
fi

exit 0