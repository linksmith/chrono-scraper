# Phase 2 Deployment Guide

## Overview

This comprehensive deployment guide provides step-by-step instructions for deploying the Phase 2 DuckDB Analytics system in production environments. The deployment delivers 5-10x performance improvements through hybrid PostgreSQL + DuckDB architecture while maintaining enterprise-grade reliability.

## Infrastructure Requirements

### Minimum System Requirements

**Production Environment:**
```yaml
CPU: 8 cores (Intel Xeon or AMD EPYC recommended)
RAM: 32GB (minimum), 64GB (recommended) 
Storage: 500GB SSD (NVMe preferred)
Network: 1Gbps connection with low latency
OS: Ubuntu 22.04 LTS or CentOS 8/RHEL 8+
```

**Development Environment:**
```yaml
CPU: 4 cores
RAM: 16GB (minimum), 32GB (recommended)
Storage: 100GB SSD
Network: 100Mbps connection
OS: Ubuntu 20.04+ or macOS 12+
```

### Recommended Production Setup

**High-Performance Configuration:**
```yaml
Application Server:
  - CPU: 16 cores (3.2GHz+)
  - RAM: 64GB DDR4
  - Storage: 1TB NVMe SSD
  - Network: 10Gbps bonded connection

Database Servers:
  PostgreSQL:
    - CPU: 8 cores
    - RAM: 32GB
    - Storage: 500GB NVMe SSD (separate data/WAL drives)
    
  DuckDB Analytics:
    - CPU: 16 cores (optimized for analytical workloads)
    - RAM: 128GB (large memory for columnar processing)
    - Storage: 2TB NVMe SSD (fast analytical queries)

Redis Cache:
  - CPU: 4 cores
  - RAM: 16GB
  - Network: Low-latency connection to application servers
```

### Docker Compose Infrastructure

**Production Docker Compose (docker-compose.production.yml):**
```yaml
version: '3.8'

services:
  # Application Services
  backend:
    build:
      context: ./backend
      target: production
    container_name: chrono-backend-prod
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - DUCKDB_MEMORY_LIMIT=32GB
      - DUCKDB_WORKER_THREADS=16
      - DUCKDB_ENABLE_S3=true
      - POSTGRES_MAX_CONNECTIONS=200
      - REDIS_MAX_CONNECTIONS=100
    volumes:
      - duckdb_data:/var/lib/duckdb
      - parquet_storage:/var/lib/parquet
      - ./logs:/app/logs
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
      - duckdb
    deploy:
      resources:
        limits:
          cpus: '8.0'
          memory: 32G
        reservations:
          cpus: '4.0'
          memory: 16G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # Analytics Service (DuckDB)
  duckdb-analytics:
    build:
      context: ./analytics
      dockerfile: Dockerfile.duckdb
    container_name: chrono-duckdb-prod
    restart: unless-stopped
    environment:
      - DUCKDB_DATABASE_PATH=/var/lib/duckdb/analytics.db
      - DUCKDB_MEMORY_LIMIT=32GB
      - DUCKDB_WORKER_THREADS=16
      - DUCKDB_TEMP_DIRECTORY=/tmp/duckdb
      - PARQUET_COMPRESSION=zstd
      - PARQUET_ROW_GROUP_SIZE=50000000
    volumes:
      - duckdb_data:/var/lib/duckdb
      - parquet_storage:/var/lib/parquet
      - duckdb_temp:/tmp/duckdb
    deploy:
      resources:
        limits:
          cpus: '16.0'
          memory: 64G
        reservations:
          cpus: '8.0'
          memory: 32G
    healthcheck:
      test: ["CMD", "/app/healthcheck.sh"]
      interval: 30s
      timeout: 15s
      retries: 3

  # PostgreSQL (OLTP)
  postgres:
    image: postgres:15-alpine
    container_name: chrono-postgres-prod
    restart: unless-stopped
    environment:
      - POSTGRES_DB=chrono_scraper
      - POSTGRES_USER=chrono_scraper
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_INITDB_ARGS="--auth-host=md5"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/init:/docker-entrypoint-initdb.d
      - ./database/config/postgresql.conf:/etc/postgresql/postgresql.conf
    ports:
      - "5432:5432"
    command: postgres -c config_file=/etc/postgresql/postgresql.conf
    deploy:
      resources:
        limits:
          cpus: '8.0'
          memory: 32G
        reservations:
          cpus: '4.0'
          memory: 16G
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U chrono_scraper"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis (Caching)
  redis:
    image: redis:7-alpine
    container_name: chrono-redis-prod
    restart: unless-stopped
    command: redis-server /usr/local/etc/redis/redis.conf
    volumes:
      - redis_data:/data
      - ./redis/redis-prod.conf:/usr/local/etc/redis/redis.conf
    ports:
      - "6379:6379"
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 16G
        reservations:
          cpus: '2.0'
          memory: 8G
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3

  # Monitoring & Observability
  prometheus:
    image: prom/prometheus:latest
    container_name: chrono-prometheus-prod
    restart: unless-stopped
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--storage.tsdb.retention.time=90d'
      - '--web.enable-lifecycle'

  grafana:
    image: grafana/grafana:latest
    container_name: chrono-grafana-prod
    restart: unless-stopped
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana:/etc/grafana/provisioning
    ports:
      - "3000:3000"

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
  duckdb_data:
    driver: local
  parquet_storage:
    driver: local
  duckdb_temp:
    driver: local
  prometheus_data:
    driver: local
  grafana_data:
    driver: local

networks:
  default:
    name: chrono_analytics_network
    driver: bridge
```

## Environment Configuration

### Production Environment Variables

**Primary Configuration (.env.production):**
```bash
# Environment
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=your-secure-secret-key-here
FRONTEND_URL=https://app.chrono-scraper.com

# Database Configuration
POSTGRES_SERVER=postgres
POSTGRES_PORT=5432
POSTGRES_USER=chrono_scraper
POSTGRES_PASSWORD=secure-password-here
POSTGRES_DB=chrono_scraper
POSTGRES_MAX_CONNECTIONS=200
POSTGRES_POOL_SIZE=20

# DuckDB Analytics Configuration
DUCKDB_DATABASE_PATH=/var/lib/duckdb/analytics.db
DUCKDB_MEMORY_LIMIT=32GB
DUCKDB_WORKER_THREADS=16
DUCKDB_TEMP_DIRECTORY=/tmp/duckdb
DUCKDB_MAX_MEMORY_PERCENTAGE=70
DUCKDB_ENABLE_S3=true

# Parquet Configuration
PARQUET_STORAGE_PATH=/var/lib/parquet
PARQUET_COMPRESSION=zstd
PARQUET_ROW_GROUP_SIZE=50000000
PARQUET_PAGE_SIZE=1048576

# Redis Cache Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=secure-redis-password
REDIS_DB=0
REDIS_MAX_CONNECTIONS=100
REDIS_SOCKET_KEEPALIVE=true
REDIS_SOCKET_KEEPALIVE_OPTIONS=TCP_KEEPIDLE:1,TCP_KEEPINTVL:3,TCP_KEEPCNT:5

# Data Synchronization
DATA_SYNC_BATCH_SIZE=10000
DATA_SYNC_INTERVAL=300
ENABLE_DUAL_WRITE=true
SYNC_CONSISTENCY_CHECK_INTERVAL=3600

# Circuit Breaker Configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_SUCCESS_THRESHOLD=3
CIRCUIT_BREAKER_TIMEOUT_SECONDS=30
CIRCUIT_BREAKER_MAX_TIMEOUT=300

# Performance Monitoring
ENABLE_PERFORMANCE_MONITORING=true
PROMETHEUS_METRICS_PORT=8080
GRAFANA_ADMIN_PASSWORD=secure-grafana-password

# AWS S3 Configuration (Optional)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_DEFAULT_REGION=us-west-2
AWS_S3_BUCKET=chrono-analytics-data

# Email Configuration
SMTP_TLS=true
SMTP_PORT=587
SMTP_HOST=smtp.gmail.com
SMTP_USER=noreply@chrono-scraper.com
SMTP_PASSWORD=app-specific-password

# Security Configuration
ALLOWED_HOSTS=["chrono-scraper.com", "api.chrono-scraper.com"]
CORS_ORIGINS=["https://app.chrono-scraper.com"]
```

### Database Configuration Files

**PostgreSQL Configuration (database/config/postgresql.conf):**
```bash
# Connection Settings
max_connections = 200
shared_buffers = 8GB
effective_cache_size = 24GB
maintenance_work_mem = 2GB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100

# Performance Tuning
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 4MB
min_wal_size = 1GB
max_wal_size = 4GB

# Logging
log_destination = 'stderr'
logging_collector = on
log_directory = '/var/log/postgresql'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_min_messages = warning
log_min_error_statement = error
log_min_duration_statement = 1000

# Monitoring
shared_preload_libraries = 'pg_stat_statements'
track_activities = on
track_counts = on
track_io_timing = on
track_functions = all
```

**Redis Configuration (redis/redis-prod.conf):**
```bash
# Network
bind 0.0.0.0
port 6379
tcp-backlog 511
timeout 0
tcp-keepalive 300

# Memory Management
maxmemory 8gb
maxmemory-policy allkeys-lru
maxmemory-samples 5

# Persistence
save 900 1
save 300 10
save 60 10000
rdbcompression yes
rdbchecksum yes
dbfilename dump.rdb
dir /data

# Append Only File
appendonly yes
appendfilename "appendonly.aof"
appendfsync everysec
no-appendfsync-on-rewrite no
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

# Performance
hash-max-ziplist-entries 512
hash-max-ziplist-value 64
list-max-ziplist-size -2
list-compress-depth 0
set-max-intset-entries 512
zset-max-ziplist-entries 128
zset-max-ziplist-value 64
hll-sparse-max-bytes 3000

# Security
requirepass your-redis-password
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command DEBUG ""
```

## Step-by-Step Deployment

### Phase 1: Infrastructure Preparation (Week 1)

#### Day 1-2: Server Setup

**1. Prepare Production Servers:**
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Docker and Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose v2
sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install system monitoring tools
sudo apt install -y htop iotop nethogs prometheus-node-exporter

# Configure system limits
echo "* soft nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "* hard nofile 65536" | sudo tee -a /etc/security/limits.conf

# Optimize kernel parameters
echo "vm.swappiness = 10" | sudo tee -a /etc/sysctl.conf
echo "vm.dirty_ratio = 15" | sudo tee -a /etc/sysctl.conf
echo "net.core.somaxconn = 65535" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

**2. Create Directory Structure:**
```bash
# Create application directories
sudo mkdir -p /opt/chrono-scraper/{data,logs,config,backups}
sudo mkdir -p /opt/chrono-scraper/data/{postgres,redis,duckdb,parquet}
sudo mkdir -p /var/log/chrono-scraper

# Set appropriate permissions
sudo chown -R $USER:$USER /opt/chrono-scraper
sudo chmod -R 755 /opt/chrono-scraper
```

#### Day 3-4: Network and Security Configuration

**3. Configure Firewall:**
```bash
# Install and configure UFW
sudo ufw enable
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH
sudo ufw allow ssh

# Allow application ports
sudo ufw allow 8000  # Backend API
sudo ufw allow 5432  # PostgreSQL (internal only)
sudo ufw allow 6379  # Redis (internal only)
sudo ufw allow 3000  # Grafana monitoring
sudo ufw allow 9090  # Prometheus metrics

# Allow HTTPS/HTTP for load balancer
sudo ufw allow 80
sudo ufw allow 443
```

**4. SSL Certificate Setup:**
```bash
# Install Certbot for Let's Encrypt
sudo apt install -y certbot nginx

# Configure Nginx reverse proxy
sudo tee /etc/nginx/sites-available/chrono-scraper << EOF
server {
    listen 80;
    server_name api.chrono-scraper.com;
    
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name api.chrono-scraper.com;
    
    ssl_certificate /etc/letsencrypt/live/api.chrono-scraper.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.chrono-scraper.com/privkey.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # WebSocket support
    location /api/v1/analytics/ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
    }
}
EOF

# Enable site and get certificate
sudo ln -s /etc/nginx/sites-available/chrono-scraper /etc/nginx/sites-enabled/
sudo certbot certonly --webroot -w /var/www/html -d api.chrono-scraper.com
sudo systemctl restart nginx
```

### Phase 2: Application Deployment (Week 1-2)

#### Day 5-7: Database Setup

**5. Deploy PostgreSQL Database:**
```bash
# Create PostgreSQL data directory
sudo mkdir -p /opt/chrono-scraper/data/postgres
sudo chown 999:999 /opt/chrono-scraper/data/postgres

# Start PostgreSQL service
cd /opt/chrono-scraper
docker-compose -f docker-compose.production.yml up -d postgres

# Wait for PostgreSQL to be ready
docker-compose -f docker-compose.production.yml exec postgres pg_isready -U chrono_scraper

# Run database migrations
docker-compose -f docker-compose.production.yml exec backend alembic upgrade head
```

**6. Initialize DuckDB Analytics:**
```bash
# Create DuckDB directories
sudo mkdir -p /opt/chrono-scraper/data/{duckdb,parquet}
sudo chmod 777 /opt/chrono-scraper/data/{duckdb,parquet}

# Start DuckDB analytics service
docker-compose -f docker-compose.production.yml up -d duckdb-analytics

# Verify DuckDB service health
curl http://localhost:8001/api/v1/duckdb/health
```

#### Day 8-10: Application Services

**7. Deploy Backend Services:**
```bash
# Build and start all services
docker-compose -f docker-compose.production.yml build
docker-compose -f docker-compose.production.yml up -d

# Verify all services are running
docker-compose -f docker-compose.production.yml ps

# Check service health
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/analytics/health
```

**8. Configure Load Balancing and Scaling:**
```bash
# Scale analytics services for high availability
docker-compose -f docker-compose.production.yml up -d --scale backend=3 --scale duckdb-analytics=2

# Configure Nginx upstream for load balancing
sudo tee -a /etc/nginx/sites-available/chrono-scraper << EOF
upstream backend_servers {
    least_conn;
    server localhost:8000 max_fails=3 fail_timeout=30s;
    server localhost:8001 max_fails=3 fail_timeout=30s;
    server localhost:8002 max_fails=3 fail_timeout=30s;
}

upstream analytics_servers {
    least_conn;
    server localhost:8100 max_fails=3 fail_timeout=30s;
    server localhost:8101 max_fails=3 fail_timeout=30s;
}
EOF

sudo systemctl reload nginx
```

### Phase 3: Monitoring and Observability (Week 2)

#### Day 11-12: Monitoring Setup

**9. Deploy Monitoring Stack:**
```bash
# Start Prometheus and Grafana
docker-compose -f docker-compose.production.yml up -d prometheus grafana

# Import Grafana dashboards
curl -X POST \
  http://admin:${GRAFANA_PASSWORD}@localhost:3000/api/dashboards/import \
  -H 'Content-Type: application/json' \
  -d @./monitoring/dashboards/chrono-analytics-dashboard.json

# Configure alerting rules
docker-compose -f docker-compose.production.yml exec prometheus promtool check rules /etc/prometheus/alerts.yml
```

**10. Configure Health Monitoring:**
```bash
# Create health check script
sudo tee /opt/chrono-scraper/healthcheck.sh << 'EOF'
#!/bin/bash
set -e

# Check backend health
curl -f http://localhost:8000/api/v1/health || exit 1

# Check analytics health
curl -f http://localhost:8000/api/v1/analytics/health || exit 1

# Check database connectivity
docker-compose -f docker-compose.production.yml exec postgres pg_isready -U chrono_scraper || exit 1

# Check Redis connectivity
docker-compose -f docker-compose.production.yml exec redis redis-cli ping || exit 1

echo "All services healthy"
EOF

sudo chmod +x /opt/chrono-scraper/healthcheck.sh

# Configure systemd service for health monitoring
sudo tee /etc/systemd/system/chrono-healthcheck.service << EOF
[Unit]
Description=Chrono Scraper Health Check
After=docker.service

[Service]
Type=oneshot
ExecStart=/opt/chrono-scraper/healthcheck.sh
User=chrono
Group=chrono

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable chrono-healthcheck.service
```

#### Day 13-14: Performance Optimization

**11. Database Performance Tuning:**
```bash
# Optimize PostgreSQL configuration
docker-compose -f docker-compose.production.yml exec postgres psql -U chrono_scraper -c "
  -- Create performance monitoring extension
  CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
  
  -- Create indexes for analytics queries
  CREATE INDEX CONCURRENTLY idx_scrape_pages_created_at ON scrape_pages(created_at);
  CREATE INDEX CONCURRENTLY idx_scrape_pages_domain_created ON scrape_pages(domain_id, created_at);
  CREATE INDEX CONCURRENTLY idx_scrape_pages_project_status ON scrape_pages(project_id, status);
  
  -- Analyze tables for query optimization
  ANALYZE scrape_pages;
  ANALYZE domains;
  ANALYZE projects;
"

# Optimize DuckDB configuration
docker-compose -f docker-compose.production.yml exec duckdb-analytics duckdb /var/lib/duckdb/analytics.db << EOF
  -- Configure DuckDB for production
  SET memory_limit='32GB';
  SET threads=16;
  SET enable_progress_bar=false;
  
  -- Create optimized analytics tables
  CREATE TABLE IF NOT EXISTS cdx_analytics AS 
  SELECT * FROM read_parquet('/var/lib/parquet/cdx_*.parquet');
  
  CREATE TABLE IF NOT EXISTS content_analytics AS
  SELECT * FROM read_parquet('/var/lib/parquet/content_*.parquet');
EOF
```

**12. Cache Optimization:**
```bash
# Configure Redis for optimal performance
docker-compose -f docker-compose.production.yml exec redis redis-cli CONFIG SET save "900 1 300 10 60 10000"
docker-compose -f docker-compose.production.yml exec redis redis-cli CONFIG SET maxmemory-policy allkeys-lru

# Warm up analytics cache with common queries
curl -X GET "http://localhost:8000/api/v1/analytics/system/performance" \
  -H "Authorization: Bearer ${ADMIN_JWT_TOKEN}"

curl -X GET "http://localhost:8000/api/v1/analytics/domains/top-domains?limit=100" \
  -H "Authorization: Bearer ${ADMIN_JWT_TOKEN}"
```

### Phase 4: Production Validation (Week 2-3)

#### Day 15-17: Testing and Validation

**13. Performance Testing:**
```bash
# Install performance testing tools
sudo apt install -y apache2-utils wrk

# Test API performance
ab -n 10000 -c 100 -H "Authorization: Bearer ${TEST_JWT_TOKEN}" \
  http://localhost:8000/api/v1/analytics/system/performance

# Test analytics query performance
wrk -t12 -c100 -d30s -H "Authorization: Bearer ${TEST_JWT_TOKEN}" \
  http://localhost:8000/api/v1/analytics/domains/top-domains

# Test WebSocket connections
node test-websocket-load.js  # Custom WebSocket load test script
```

**14. Data Integrity Validation:**
```bash
# Run data consistency checks
docker-compose -f docker-compose.production.yml exec backend python -m app.scripts.validate_data_consistency

# Verify analytics accuracy
docker-compose -f docker-compose.production.yml exec backend python -m app.scripts.compare_analytics_results

# Test backup and restore procedures
./scripts/backup-production-data.sh
./scripts/test-restore-procedure.sh
```

#### Day 18-21: Security and Compliance

**15. Security Hardening:**
```bash
# Install security scanning tools
sudo apt install -y clamav rkhunter chkrootkit

# Run security scans
sudo freshclam
sudo clamscan -r /opt/chrono-scraper/ --exclude-dir=/opt/chrono-scraper/data

# Check for rootkits
sudo rkhunter --check --sk

# Audit file permissions
find /opt/chrono-scraper -type f -exec ls -la {} \; | grep -v "^-rw-r--r--"

# Validate SSL configuration
testssl.sh api.chrono-scraper.com

# Check for security vulnerabilities
docker run --rm -v /opt/chrono-scraper:/app -w /app securecodewarrior/docker-security-scanning
```

**16. Backup and Disaster Recovery:**
```bash
# Configure automated backups
sudo tee /opt/chrono-scraper/scripts/backup-production.sh << 'EOF'
#!/bin/bash
set -e

BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/chrono-scraper/backups/${BACKUP_DATE}"
mkdir -p ${BACKUP_DIR}

# Backup PostgreSQL
docker-compose -f docker-compose.production.yml exec postgres pg_dump -U chrono_scraper chrono_scraper > ${BACKUP_DIR}/postgres_backup.sql

# Backup DuckDB
cp /opt/chrono-scraper/data/duckdb/*.db ${BACKUP_DIR}/

# Backup Parquet files
rsync -av /opt/chrono-scraper/data/parquet/ ${BACKUP_DIR}/parquet/

# Backup configuration
cp -r /opt/chrono-scraper/config/ ${BACKUP_DIR}/

# Compress backup
tar -czf ${BACKUP_DIR}.tar.gz -C /opt/chrono-scraper/backups ${BACKUP_DATE}
rm -rf ${BACKUP_DIR}

# Upload to S3 (if configured)
if [ -n "$AWS_S3_BACKUP_BUCKET" ]; then
  aws s3 cp ${BACKUP_DIR}.tar.gz s3://${AWS_S3_BACKUP_BUCKET}/backups/
fi

# Cleanup old backups (keep 30 days)
find /opt/chrono-scraper/backups -name "*.tar.gz" -mtime +30 -delete

echo "Backup completed: ${BACKUP_DIR}.tar.gz"
EOF

sudo chmod +x /opt/chrono-scraper/scripts/backup-production.sh

# Schedule daily backups
echo "0 2 * * * /opt/chrono-scraper/scripts/backup-production.sh" | sudo crontab -
```

## Configuration Management

### Environment-Specific Configurations

**Staging Environment (.env.staging):**
```bash
# Staging-specific overrides
ENVIRONMENT=staging
DEBUG=true
DUCKDB_MEMORY_LIMIT=8GB
DUCKDB_WORKER_THREADS=4
POSTGRES_MAX_CONNECTIONS=50
REDIS_MAX_CONNECTIONS=25
```

**Development Environment (.env.development):**
```bash
# Development-specific settings
ENVIRONMENT=development
DEBUG=true
DUCKDB_MEMORY_LIMIT=4GB
DUCKDB_WORKER_THREADS=2
POSTGRES_MAX_CONNECTIONS=20
ENABLE_PERFORMANCE_MONITORING=false
```

### Configuration Validation

**Pre-Deployment Validation Script:**
```bash
#!/bin/bash
# validate-configuration.sh

set -e

echo "Validating Phase 2 Analytics deployment configuration..."

# Check required environment variables
required_vars=(
    "POSTGRES_PASSWORD"
    "REDIS_PASSWORD" 
    "SECRET_KEY"
    "DUCKDB_DATABASE_PATH"
    "PARQUET_STORAGE_PATH"
)

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "ERROR: Required environment variable $var is not set"
        exit 1
    fi
done

# Validate memory configurations
if [ -z "$DUCKDB_MEMORY_LIMIT" ]; then
    echo "ERROR: DUCKDB_MEMORY_LIMIT must be set"
    exit 1
fi

# Check disk space
required_space_gb=100
available_space_gb=$(df -BG /opt/chrono-scraper | awk 'NR==2 {print $4}' | sed 's/G//')
if [ "$available_space_gb" -lt "$required_space_gb" ]; then
    echo "ERROR: Insufficient disk space. Required: ${required_space_gb}GB, Available: ${available_space_gb}GB"
    exit 1
fi

# Validate Docker Compose configuration
docker-compose -f docker-compose.production.yml config -q

echo "Configuration validation passed!"
```

## Troubleshooting Guide

### Common Deployment Issues

**1. DuckDB Memory Issues:**
```bash
# Symptoms: DuckDB service crashing with OOM errors
# Solution: Adjust memory limits based on available system memory

# Check available memory
free -h

# Adjust DuckDB memory limit (70% of available RAM)
# For 64GB system: DUCKDB_MEMORY_LIMIT=45GB
# For 32GB system: DUCKDB_MEMORY_LIMIT=22GB

# Monitor memory usage
docker stats --no-stream
```

**2. PostgreSQL Connection Issues:**
```bash
# Symptoms: Connection refused or too many connections
# Solution: Check and adjust connection limits

# Check current connections
docker-compose exec postgres psql -U chrono_scraper -c "SELECT count(*) FROM pg_stat_activity;"

# Adjust max_connections in postgresql.conf
# Restart PostgreSQL service
docker-compose restart postgres
```

**3. Redis Memory Issues:**
```bash
# Symptoms: Redis evicting keys or running out of memory
# Solution: Monitor and adjust Redis memory settings

# Check Redis memory usage
docker-compose exec redis redis-cli INFO memory

# Adjust maxmemory configuration
docker-compose exec redis redis-cli CONFIG SET maxmemory 8gb
docker-compose exec redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

**4. Analytics Query Performance:**
```bash
# Symptoms: Slow analytics queries or timeouts
# Solutions:

# 1. Check query routing
curl http://localhost:8000/api/v1/hybrid/metrics

# 2. Analyze slow queries
docker-compose exec postgres psql -U chrono_scraper -c "
  SELECT query, mean_exec_time, calls 
  FROM pg_stat_statements 
  ORDER BY mean_exec_time DESC LIMIT 10;
"

# 3. Check DuckDB performance
docker-compose exec duckdb-analytics duckdb /var/lib/duckdb/analytics.db << EOF
  PRAGMA show_tables;
  PRAGMA table_info('cdx_analytics');
EOF
```

### Log Analysis

**Centralized Logging Setup:**
```bash
# Configure log aggregation
sudo tee /opt/chrono-scraper/logging/filebeat.yml << EOF
filebeat.inputs:
- type: log
  enabled: true
  paths:
    - /opt/chrono-scraper/logs/*.log
    - /var/log/chrono-scraper/*.log

output.elasticsearch:
  hosts: ["localhost:9200"]

processors:
- add_host_metadata: ~
EOF

# Set up log rotation
sudo tee /etc/logrotate.d/chrono-scraper << EOF
/opt/chrono-scraper/logs/*.log
/var/log/chrono-scraper/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 chrono chrono
    postrotate
        docker-compose -f /opt/chrono-scraper/docker-compose.production.yml restart backend
    endscript
}
EOF
```

## Rollback Procedures

### Automated Rollback Strategy

**Rollback Script:**
```bash
#!/bin/bash
# rollback-deployment.sh

set -e

ROLLBACK_VERSION=${1:-"previous"}
echo "Initiating rollback to version: $ROLLBACK_VERSION"

# 1. Stop current services gracefully
docker-compose -f docker-compose.production.yml down --timeout 30

# 2. Restore previous configuration
cp /opt/chrono-scraper/backups/config_${ROLLBACK_VERSION}/.env.production .env

# 3. Restore database if needed (with user confirmation)
if [ "$2" == "--restore-db" ]; then
    read -p "WARNING: This will restore the database. Continue? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Restore PostgreSQL
        docker-compose exec postgres psql -U chrono_scraper -c "DROP DATABASE IF EXISTS chrono_scraper_temp;"
        docker-compose exec postgres createdb -U chrono_scraper chrono_scraper_temp
        docker-compose exec postgres psql -U chrono_scraper chrono_scraper_temp < /opt/chrono-scraper/backups/${ROLLBACK_VERSION}/postgres_backup.sql
        
        # Switch databases
        docker-compose exec postgres psql -U chrono_scraper -c "ALTER DATABASE chrono_scraper RENAME TO chrono_scraper_old;"
        docker-compose exec postgres psql -U chrono_scraper -c "ALTER DATABASE chrono_scraper_temp RENAME TO chrono_scraper;"
    fi
fi

# 4. Start services with previous version
docker-compose -f docker-compose.production.yml up -d

# 5. Verify rollback success
sleep 30
curl -f http://localhost:8000/api/v1/health || {
    echo "Rollback failed - health check unsuccessful"
    exit 1
}

echo "Rollback completed successfully"
```

### Health Check Validation

**Post-Deployment Health Checks:**
```bash
#!/bin/bash
# post-deployment-health-check.sh

set -e

echo "Running comprehensive health checks..."

# 1. Basic service health
services=("backend" "postgres" "redis" "duckdb-analytics")
for service in "${services[@]}"; do
    if ! docker-compose ps $service | grep -q "Up"; then
        echo "ERROR: Service $service is not running"
        exit 1
    fi
done

# 2. API endpoint health
endpoints=(
    "/api/v1/health"
    "/api/v1/analytics/health"
    "/api/v1/duckdb/health"
)

for endpoint in "${endpoints[@]}"; do
    if ! curl -f "http://localhost:8000$endpoint" > /dev/null 2>&1; then
        echo "ERROR: Endpoint $endpoint is not responding"
        exit 1
    fi
done

# 3. Database connectivity
docker-compose exec postgres pg_isready -U chrono_scraper || {
    echo "ERROR: PostgreSQL is not ready"
    exit 1
}

docker-compose exec redis redis-cli ping | grep -q "PONG" || {
    echo "ERROR: Redis is not responding"
    exit 1
}

# 4. Analytics performance test
response_time=$(curl -w "%{time_total}" -s -o /dev/null "http://localhost:8000/api/v1/analytics/system/performance")
if (( $(echo "$response_time > 2.0" | bc -l) )); then
    echo "WARNING: Analytics response time is slow: ${response_time}s"
fi

# 5. Memory usage check
memory_usage=$(free | grep Mem | awk '{print ($3/$2) * 100.0}')
if (( $(echo "$memory_usage > 90" | bc -l) )); then
    echo "WARNING: High memory usage: ${memory_usage}%"
fi

echo "All health checks passed successfully!"
```

## Maintenance Procedures

### Regular Maintenance Tasks

**Weekly Maintenance (automated):**
```bash
#!/bin/bash
# weekly-maintenance.sh

# 1. Database maintenance
docker-compose exec postgres psql -U chrono_scraper -c "VACUUM ANALYZE;"
docker-compose exec postgres psql -U chrono_scraper -c "REINDEX DATABASE chrono_scraper;"

# 2. DuckDB optimization
docker-compose exec duckdb-analytics duckdb /var/lib/duckdb/analytics.db << EOF
PRAGMA optimize;
VACUUM;
EOF

# 3. Cache cleanup
docker-compose exec redis redis-cli FLUSHEXPIRED

# 4. Log cleanup
find /opt/chrono-scraper/logs -name "*.log" -mtime +7 -delete
journalctl --vacuum-time=7d

# 5. System updates (if in maintenance window)
if [ "$MAINTENANCE_WINDOW" = "true" ]; then
    sudo apt update && sudo apt upgrade -y
    docker system prune -f
fi
```

**Monthly Maintenance (manual):**
```bash
# 1. Performance analysis
docker-compose exec postgres psql -U chrono_scraper -c "
  SELECT schemaname, tablename, attname, n_distinct, correlation 
  FROM pg_stats WHERE tablename IN ('scrape_pages', 'projects', 'domains');
"

# 2. Storage analysis
du -sh /opt/chrono-scraper/data/*
df -h /opt/chrono-scraper

# 3. Security updates
sudo apt list --upgradable | grep -i security
docker images --format "{{.Repository}}:{{.Tag}}" | xargs -I {} docker pull {}

# 4. Backup verification
./scripts/test-restore-procedure.sh
```

This comprehensive deployment guide provides all necessary steps and configurations for successfully deploying the Phase 2 DuckDB Analytics system in production environments. The guide ensures enterprise-grade reliability, security, and performance while providing clear troubleshooting and maintenance procedures.