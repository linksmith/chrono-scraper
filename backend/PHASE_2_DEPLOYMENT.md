# Phase 2 DuckDB Analytics System - Deployment Guide

## 🚀 Complete Deployment Documentation

This comprehensive deployment guide covers infrastructure requirements, step-by-step deployment procedures, configuration management, and production hardening for the Phase 2 DuckDB analytics system.

## 📋 Prerequisites & System Requirements

### Hardware Requirements

#### Minimum System Requirements (Development/Testing)
```yaml
CPU: 4 cores (8 threads recommended)
Memory: 16GB RAM minimum
Storage: 100GB SSD (500GB recommended)
Network: 1 Gbps network connection
OS: Ubuntu 20.04+ / CentOS 8+ / RHEL 8+
```

#### Production System Requirements
```yaml
CPU: 8 cores minimum (16+ recommended for high load)
Memory: 32GB RAM minimum (64GB+ recommended)
Storage: 
  - System: 50GB SSD
  - PostgreSQL: 200GB+ SSD (depends on data volume)
  - DuckDB: 500GB+ SSD (columnar storage)
  - Logs: 50GB SSD
  - Backups: 3x data volume capacity
Network: 10 Gbps network (minimum 1 Gbps)
```

#### Scaling Recommendations
```yaml
Small Scale (< 1M pages):
  CPU: 8 cores, Memory: 32GB, Storage: 500GB

Medium Scale (1M - 10M pages):
  CPU: 16 cores, Memory: 64GB, Storage: 2TB

Large Scale (10M+ pages):  
  CPU: 32+ cores, Memory: 128GB+, Storage: 5TB+
  Consider horizontal scaling with multiple nodes
```

### Software Dependencies

#### Required Software Stack
```yaml
Operating System:
  - Ubuntu 20.04 LTS or later (recommended)
  - CentOS 8+ / RHEL 8+
  - Docker Desktop (for development)

Container Runtime:
  - Docker 20.10+ (required)
  - Docker Compose 2.0+ (required)

Optional (Production):
  - Kubernetes 1.21+ (for orchestration)
  - Nginx (reverse proxy)
  - Prometheus + Grafana (monitoring)
```

#### Python Dependencies (if running outside containers)
```yaml
Python: 3.11+
Key packages:
  - fastapi>=0.104.0
  - sqlalchemy>=2.0.0
  - duckdb>=0.9.0
  - redis>=4.5.0
  - celery>=5.3.0
  - psycopg2-binary>=2.9.0
```

### Network Requirements

#### Port Configuration
```yaml
External Ports (Internet-facing):
  - 443: HTTPS (production)
  - 80: HTTP redirect to HTTPS

Internal Ports (application services):
  - 8000: FastAPI application
  - 5432: PostgreSQL database
  - 6379: Redis cache
  - 7700: Meilisearch
  - 3002: Firecrawl API
  - 5555: Celery Flower monitoring

Monitoring Ports:
  - 9090: Prometheus metrics
  - 3000: Grafana dashboards
  - 9093: AlertManager
```

#### Security Groups / Firewall Rules
```yaml
Inbound Rules:
  - Port 443: 0.0.0.0/0 (HTTPS traffic)
  - Port 80: 0.0.0.0/0 (HTTP redirect)
  - Port 22: <admin_ip>/32 (SSH admin access)
  - Ports 8000-9999: <internal_network>/24 (service communication)

Outbound Rules:
  - Port 443: 0.0.0.0/0 (HTTPS for APIs)
  - Port 80: 0.0.0.0/0 (HTTP for updates)
  - Port 53: 0.0.0.0/0 (DNS resolution)
```

## 🛠️ Step-by-Step Deployment Process

### Step 1: System Preparation

#### 1.1 Update System and Install Dependencies
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y \
    curl \
    wget \
    git \
    unzip \
    htop \
    nginx \
    certbot \
    python3-certbot-nginx

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installations
docker --version
docker-compose --version
```

#### 1.2 Create Application Directory Structure
```bash
# Create application directory
sudo mkdir -p /opt/chrono-scraper
sudo chown $USER:$USER /opt/chrono-scraper
cd /opt/chrono-scraper

# Create data directories with proper permissions
mkdir -p {data/postgresql,data/duckdb,data/redis,data/meilisearch,logs,backups,exports}
sudo chown -R 999:999 data/postgresql  # PostgreSQL container user
sudo chown -R 1000:1000 data/duckdb    # DuckDB service user
```

#### 1.3 Configure System Limits and Optimization
```bash
# Configure system limits for high performance
sudo tee -a /etc/security/limits.conf << EOF
*                soft    nofile          65536
*                hard    nofile          65536
*                soft    nproc           32768
*                hard    nproc           32768
EOF

# Configure kernel parameters for database performance
sudo tee -a /etc/sysctl.conf << EOF
# Database optimizations
vm.swappiness = 10
vm.overcommit_memory = 2
vm.overcommit_ratio = 80
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5

# Network optimizations
net.core.somaxconn = 65536
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_max_syn_backlog = 65536
EOF

# Apply kernel parameters
sudo sysctl -p
```

### Step 2: Source Code Deployment

#### 2.1 Clone Repository and Configure
```bash
# Clone the repository
git clone https://github.com/your-org/chrono-scraper-fastapi-2.git
cd chrono-scraper-fastapi-2

# Checkout stable release (replace with latest stable tag)
git checkout v2.1.0

# Verify Phase 2 components are present
ls -la backend/app/services/duckdb_service.py
ls -la backend/app/services/hybrid_query_router.py
ls -la backend/app/services/data_sync_service.py
```

#### 2.2 Environment Configuration
```bash
# Copy environment template
cp .env.example .env

# Generate secure secrets
export SECRET_KEY=$(openssl rand -hex 32)
export JWT_SECRET_KEY=$(openssl rand -hex 32)
export POSTGRES_PASSWORD=$(openssl rand -base64 32)
export REDIS_PASSWORD=$(openssl rand -base64 32)
```

#### 2.3 Production Environment File (.env)
```bash
# Create production environment configuration
cat > .env << EOF
# Environment
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=${SECRET_KEY}
JWT_SECRET_KEY=${JWT_SECRET_KEY}

# Database Configuration
DATABASE_URL=postgresql://chrono_scraper:${POSTGRES_PASSWORD}@postgres:5432/chrono_scraper
POSTGRES_USER=chrono_scraper
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=chrono_scraper
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# DuckDB Analytics Configuration
DUCKDB_DATABASE_PATH=/app/data/analytics/chrono_analytics.duckdb
DUCKDB_MEMORY_LIMIT=16GB
DUCKDB_WORKER_THREADS=16
DUCKDB_TEMP_DIRECTORY=/tmp/duckdb
DUCKDB_MAX_MEMORY_PERCENTAGE=75
DUCKDB_ENABLE_S3=true

# Redis Configuration  
REDIS_URL=redis://default:${REDIS_PASSWORD}@redis:6379/0
REDIS_PASSWORD=${REDIS_PASSWORD}

# Analytics Configuration
ANALYTICS_CACHE_TTL=300
ANALYTICS_LONG_CACHE_TTL=1800
ANALYTICS_MAX_QUERY_TIME=30
ANALYTICS_PAGINATION_SIZE=1000
ENABLE_ANALYTICS_WEBSOCKET=true
ANALYTICS_RATE_LIMIT=100
ANALYTICS_EXPORT_TTL_HOURS=48

# Circuit Breaker Configuration
POSTGRESQL_CIRCUIT_BREAKER_THRESHOLD=5
POSTGRESQL_CIRCUIT_BREAKER_TIMEOUT=60
DUCKDB_CIRCUIT_BREAKER_THRESHOLD=3
DUCKDB_CIRCUIT_BREAKER_TIMEOUT=30

# Monitoring Configuration
ENABLE_PROMETHEUS_METRICS=true
METRICS_PORT=9090
LOG_LEVEL=INFO
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project

# External Services
FRONTEND_URL=https://your-domain.com
BACKEND_URL=https://api.your-domain.com

# Email Configuration (Production)
MAILGUN_API_KEY=your-mailgun-api-key
MAILGUN_DOMAIN=mg.your-domain.com
MAILGUN_FROM_EMAIL=noreply@your-domain.com

# Security Configuration
ALLOWED_HOSTS=your-domain.com,api.your-domain.com
CORS_ORIGINS=https://your-domain.com
CSRF_TRUSTED_ORIGINS=https://your-domain.com

# SSL Configuration
SSL_CERT_PATH=/etc/ssl/certs/your-domain.crt
SSL_KEY_PATH=/etc/ssl/private/your-domain.key
EOF
```

### Step 3: Production Docker Compose Configuration

#### 3.1 Production Docker Compose File
```bash
# Create production docker-compose file
cat > docker-compose.production.yml << 'EOF'
version: '3.8'

services:
  # FastAPI Application
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: chrono-backend
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data/duckdb:/app/data/analytics
      - ./logs:/app/logs
      - ./exports:/app/exports
      - ./backups:/app/backups
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      duckdb-init:
        condition: service_completed_successfully
    ports:
      - "8000:8000"
    networks:
      - chrono-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'
        reservations:
          memory: 2G
          cpus: '1.0'

  # PostgreSQL Database
  postgres:
    image: postgres:15
    container_name: chrono-postgres
    restart: unless-stopped
    env_file: .env
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - ./data/postgresql:/var/lib/postgresql/data
      - ./config/postgresql.conf:/etc/postgresql/postgresql.conf
      - ./logs/postgresql:/var/log/postgresql
    ports:
      - "5432:5432"
    networks:
      - chrono-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 8G
          cpus: '2.0'
        reservations:
          memory: 4G
          cpus: '1.0'

  # DuckDB Analytics Service Initialization
  duckdb-init:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: chrono-duckdb-init
    env_file: .env
    volumes:
      - ./data/duckdb:/app/data/analytics
    command: ["python", "-c", "
      import asyncio;
      from app.services.duckdb_service import duckdb_service;
      async def init(): await duckdb_service.initialize();
      asyncio.run(init())
    "]
    networks:
      - chrono-network
    deploy:
      resources:
        limits:
          memory: 16G
          cpus: '4.0'
        reservations:
          memory: 8G
          cpus: '2.0'

  # Redis Cache
  redis:
    image: redis:7-alpine
    container_name: chrono-redis
    restart: unless-stopped
    env_file: .env
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 2gb --maxmemory-policy allkeys-lru
    volumes:
      - ./data/redis:/data
    ports:
      - "6379:6379"
    networks:
      - chrono-network
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'

  # Celery Worker
  celery-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: chrono-celery-worker
    restart: unless-stopped
    env_file: .env
    command: celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
    volumes:
      - ./data/duckdb:/app/data/analytics
      - ./logs:/app/logs
      - ./exports:/app/exports
    depends_on:
      - redis
      - postgres
    networks:
      - chrono-network
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'
        reservations:
          memory: 2G
          cpus: '1.0'

  # Celery Beat Scheduler
  celery-beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: chrono-celery-beat
    restart: unless-stopped
    env_file: .env
    command: celery -A app.tasks.celery_app beat --loglevel=info
    volumes:
      - ./logs:/app/logs
    depends_on:
      - redis
      - postgres
    networks:
      - chrono-network
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.5'
        reservations:
          memory: 512M
          cpus: '0.25'

  # Celery Flower Monitoring
  celery-flower:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: chrono-celery-flower
    restart: unless-stopped
    env_file: .env
    command: celery -A app.tasks.celery_app flower --port=5555
    ports:
      - "5555:5555"
    depends_on:
      - redis
    networks:
      - chrono-network
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'

  # Prometheus Metrics
  prometheus:
    image: prom/prometheus:latest
    container_name: chrono-prometheus
    restart: unless-stopped
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml
      - ./data/prometheus:/prometheus
    ports:
      - "9090:9090"
    networks:
      - chrono-network
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--storage.tsdb.retention.time=30d'
      - '--web.enable-lifecycle'

  # Grafana Dashboard
  grafana:
    image: grafana/grafana:latest
    container_name: chrono-grafana
    restart: unless-stopped
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD}
    volumes:
      - ./data/grafana:/var/lib/grafana
      - ./config/grafana:/etc/grafana/provisioning
    ports:
      - "3000:3000"
    networks:
      - chrono-network
    depends_on:
      - prometheus

  # Nginx Reverse Proxy
  nginx:
    image: nginx:alpine
    container_name: chrono-nginx
    restart: unless-stopped
    volumes:
      - ./config/nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/ssl
      - ./logs/nginx:/var/log/nginx
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - backend
    networks:
      - chrono-network

networks:
  chrono-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16

volumes:
  postgres-data:
  duckdb-data:
  redis-data:
  prometheus-data:
  grafana-data:
EOF
```

### Step 4: Configuration Files

#### 4.1 PostgreSQL Configuration
```bash
# Create PostgreSQL configuration directory
mkdir -p config

# Create optimized PostgreSQL configuration
cat > config/postgresql.conf << 'EOF'
# PostgreSQL Production Configuration for Analytics Workload

# Connection Settings
max_connections = 200
shared_buffers = 4GB
work_mem = 64MB
maintenance_work_mem = 512MB
effective_cache_size = 12GB

# Write-Ahead Logging
wal_buffers = 64MB
checkpoint_completion_target = 0.9
checkpoint_timeout = 15min
max_wal_size = 4GB
min_wal_size = 1GB

# Query Performance
effective_io_concurrency = 200
random_page_cost = 1.1
seq_page_cost = 1.0
cpu_tuple_cost = 0.01
cpu_index_tuple_cost = 0.005

# Logging
logging_collector = on
log_directory = '/var/log/postgresql'
log_filename = 'postgresql-%Y-%m-%d.log'
log_min_duration_statement = 1000
log_checkpoints = on
log_lock_waits = on

# Background Writer
bgwriter_delay = 200ms
bgwriter_lru_maxpages = 100
bgwriter_lru_multiplier = 2.0

# Autovacuum
autovacuum = on
autovacuum_max_workers = 4
autovacuum_naptime = 30s
EOF
```

#### 4.2 Nginx Configuration
```bash
# Create Nginx configuration
cat > config/nginx.conf << 'EOF'
events {
    worker_connections 1024;
    use epoll;
    multi_accept on;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;
    
    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                   '$status $body_bytes_sent "$http_referer" '
                   '"$http_user_agent" "$http_x_forwarded_for" '
                   'rt=$request_time uct="$upstream_connect_time" '
                   'uht="$upstream_header_time" urt="$upstream_response_time"';
    
    access_log /var/log/nginx/access.log main;
    error_log  /var/log/nginx/error.log warn;
    
    # Performance
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 100M;
    
    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript 
               application/javascript application/xml+rss 
               application/json application/xml;
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/m;
    limit_req_zone $binary_remote_addr zone=export:10m rate=10r/m;
    
    upstream backend {
        server backend:8000 max_fails=3 fail_timeout=30s;
        keepalive 32;
    }
    
    # HTTP to HTTPS redirect
    server {
        listen 80;
        server_name your-domain.com api.your-domain.com;
        return 301 https://$server_name$request_uri;
    }
    
    # Main application server
    server {
        listen 443 ssl http2;
        server_name your-domain.com;
        
        ssl_certificate /etc/ssl/certs/your-domain.crt;
        ssl_certificate_key /etc/ssl/private/your-domain.key;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
        ssl_prefer_server_ciphers off;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;
        
        # Security headers
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;
        add_header X-XSS-Protection "1; mode=block";
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";
        
        location / {
            # Serve frontend static files or proxy to frontend service
            root /var/www/html;
            try_files $uri $uri/ /index.html;
        }
    }
    
    # API server
    server {
        listen 443 ssl http2;
        server_name api.your-domain.com;
        
        ssl_certificate /etc/ssl/certs/your-domain.crt;
        ssl_certificate_key /etc/ssl/private/your-domain.key;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
        ssl_prefer_server_ciphers off;
        
        # API endpoints
        location /api/v1/analytics/export/ {
            limit_req zone=export burst=5 nodelay;
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
        }
        
        location /api/v1/analytics/ {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 60s;
        }
        
        location / {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # WebSocket support
        location /api/v1/analytics/ws {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
EOF
```

#### 4.3 Prometheus Configuration
```bash
# Create Prometheus configuration
cat > config/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "rules/*.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093

scrape_configs:
  - job_name: 'chrono-scraper'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: /metrics
    scrape_interval: 15s
    
  - job_name: 'postgres-exporter'
    static_configs:
      - targets: ['postgres-exporter:9187']
      
  - job_name: 'redis-exporter'
    static_configs:
      - targets: ['redis-exporter:9121']
      
  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']
EOF
```

### Step 5: SSL Certificate Setup

#### 5.1 Let's Encrypt SSL Certificates
```bash
# Create SSL directory
mkdir -p ssl

# Generate SSL certificates using certbot
sudo certbot --nginx -d your-domain.com -d api.your-domain.com

# Copy certificates to ssl directory
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ssl/your-domain.crt
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ssl/your-domain.key
sudo chown $USER:$USER ssl/*

# Setup automatic certificate renewal
echo "0 12 * * * /usr/bin/certbot renew --quiet" | sudo crontab -
```

### Step 6: Database Initialization

#### 6.1 Initialize PostgreSQL Database
```bash
# Start PostgreSQL first
docker-compose -f docker-compose.production.yml up -d postgres
sleep 30

# Run database migrations
docker-compose -f docker-compose.production.yml run --rm backend alembic upgrade head

# Create initial superuser
docker-compose -f docker-compose.production.yml run --rm backend python -c "
import asyncio
from app.core.init_db import init_db
asyncio.run(init_db())
"
```

#### 6.2 Initialize DuckDB Analytics Database
```bash
# Initialize DuckDB service
docker-compose -f docker-compose.production.yml run --rm duckdb-init

# Verify DuckDB initialization
docker-compose -f docker-compose.production.yml run --rm backend python -c "
import asyncio
from app.services.duckdb_service import get_service_health
async def check(): print(await get_service_health())
asyncio.run(check())
"
```

### Step 7: Service Deployment

#### 7.1 Deploy All Services
```bash
# Build and start all services
docker-compose -f docker-compose.production.yml build --no-cache
docker-compose -f docker-compose.production.yml up -d

# Verify all services are running
docker-compose -f docker-compose.production.yml ps

# Check service health
curl -f http://localhost:8000/api/v1/health
curl -f http://localhost:8000/api/v1/analytics/health
```

#### 7.2 Service Verification Commands
```bash
# Verify database connections
docker-compose exec backend python -c "
import asyncio
from app.core.database import test_db_connection
asyncio.run(test_db_connection())
"

# Verify DuckDB service
docker-compose exec backend python -c "
import asyncio  
from app.services.duckdb_service import duckdb_service
async def test():
    await duckdb_service.initialize()
    result = await duckdb_service.execute_query('SELECT 1 as test')
    print(f'DuckDB test result: {result.data}')
asyncio.run(test())
"

# Verify Redis connection
docker-compose exec backend python -c "
import redis
r = redis.from_url('${REDIS_URL}')
print(f'Redis ping: {r.ping()}')
"

# Test analytics endpoints
curl -X GET "http://localhost:8000/api/v1/analytics/system/performance-overview" \
  -H "Authorization: Bearer <token>"
```

## 🔧 Configuration Management

### Environment-Specific Configuration

#### Development Configuration
```yaml
# docker-compose.yml (for development)
services:
  backend:
    environment:
      - ENVIRONMENT=development
      - DEBUG=true
      - LOG_LEVEL=DEBUG
      - DUCKDB_MEMORY_LIMIT=4GB
      - DUCKDB_WORKER_THREADS=4
    volumes:
      - ./backend:/app  # Live code mounting for development
```

#### Staging Configuration  
```yaml
# docker-compose.staging.yml
services:
  backend:
    environment:
      - ENVIRONMENT=staging
      - DEBUG=false
      - LOG_LEVEL=INFO
      - DUCKDB_MEMORY_LIMIT=8GB
      - DUCKDB_WORKER_THREADS=8
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
```

#### Production Configuration Validation
```bash
# Create configuration validation script
cat > scripts/validate_config.py << 'EOF'
#!/usr/bin/env python3
import os
import sys
from pathlib import Path

def validate_config():
    """Validate production configuration"""
    errors = []
    
    # Required environment variables
    required_vars = [
        'SECRET_KEY', 'JWT_SECRET_KEY', 'DATABASE_URL',
        'REDIS_URL', 'DUCKDB_DATABASE_PATH'
    ]
    
    for var in required_vars:
        if not os.getenv(var):
            errors.append(f"Missing required environment variable: {var}")
    
    # Check file paths
    required_paths = [
        os.getenv('DUCKDB_DATABASE_PATH', '').replace('/app', '.'),
        'data/postgresql',
        'data/redis',
        'logs',
        'ssl'
    ]
    
    for path in required_paths:
        if path and not Path(path).parent.exists():
            errors.append(f"Required directory does not exist: {path}")
    
    # Validate SSL certificates
    ssl_cert = os.getenv('SSL_CERT_PATH', 'ssl/your-domain.crt')
    ssl_key = os.getenv('SSL_KEY_PATH', 'ssl/your-domain.key')
    
    if not Path(ssl_cert).exists():
        errors.append(f"SSL certificate not found: {ssl_cert}")
    if not Path(ssl_key).exists():
        errors.append(f"SSL private key not found: {ssl_key}")
    
    if errors:
        print("Configuration validation failed:")
        for error in errors:
            print(f"  ❌ {error}")
        sys.exit(1)
    else:
        print("✅ Configuration validation passed")

if __name__ == "__main__":
    validate_config()
EOF

chmod +x scripts/validate_config.py
python scripts/validate_config.py
```

## 🚀 Production Hardening

### Security Hardening

#### 1. Container Security
```bash
# Create non-root user in containers
cat >> backend/Dockerfile << 'EOF'
# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser
EOF
```

#### 2. Network Security
```bash
# Configure firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw --force enable

# Configure fail2ban for SSH protection
sudo apt install fail2ban -y
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

#### 3. System Hardening
```bash
# Disable unnecessary services
sudo systemctl disable bluetooth
sudo systemctl disable cups
sudo systemctl disable avahi-daemon

# Configure automatic security updates
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure -plow unattended-upgrades

# Set up log rotation
sudo cat > /etc/logrotate.d/chrono-scraper << 'EOF'
/opt/chrono-scraper/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    postrotate
        docker-compose -f /opt/chrono-scraper/docker-compose.production.yml restart backend
    endscript
}
EOF
```

### Performance Optimization

#### 1. Docker Performance Tuning
```yaml
# Add to docker-compose.production.yml
services:
  backend:
    ulimits:
      nofile:
        soft: 65536
        hard: 65536
      nproc: 32768
    security_opt:
      - no-new-privileges:true
    tmpfs:
      - /tmp:noexec,nosuid,size=1g
```

#### 2. Database Performance Tuning
```bash
# PostgreSQL tuning script
cat > scripts/tune_postgresql.sql << 'EOF'
-- Performance monitoring queries
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Create indexes for analytics queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pages_created_at ON pages(created_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pages_project_id_status ON pages(project_id, status);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_scrape_pages_domain_id ON scrape_pages(domain_id);

-- Update table statistics
ANALYZE;

-- Check slow queries
SELECT query, calls, total_time, mean_time, rows
FROM pg_stat_statements 
ORDER BY total_time DESC 
LIMIT 10;
EOF

# Apply tuning
docker-compose exec postgres psql -U chrono_scraper -d chrono_scraper -f /scripts/tune_postgresql.sql
```

## 📊 Monitoring & Alerting Setup

### Monitoring Stack Deployment

#### 1. Extended Monitoring Stack
```yaml
# Add to docker-compose.production.yml
services:
  # PostgreSQL Exporter
  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:latest
    container_name: chrono-postgres-exporter
    environment:
      DATA_SOURCE_NAME: "postgresql://chrono_scraper:${POSTGRES_PASSWORD}@postgres:5432/chrono_scraper?sslmode=disable"
    ports:
      - "9187:9187"
    depends_on:
      - postgres
    networks:
      - chrono-network

  # Redis Exporter  
  redis-exporter:
    image: oliver006/redis_exporter:latest
    container_name: chrono-redis-exporter
    environment:
      REDIS_ADDR: "redis://default:${REDIS_PASSWORD}@redis:6379"
    ports:
      - "9121:9121"
    depends_on:
      - redis
    networks:
      - chrono-network

  # Node Exporter
  node-exporter:
    image: prom/node-exporter:latest
    container_name: chrono-node-exporter
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--path.rootfs=/rootfs'
      - '--collector.filesystem.ignored-mount-points=^/(sys|proc|dev|host|etc)($$|/)'
    ports:
      - "9100:9100"
    networks:
      - chrono-network

  # Alert Manager
  alertmanager:
    image: prom/alertmanager:latest
    container_name: chrono-alertmanager
    volumes:
      - ./config/alertmanager.yml:/etc/alertmanager/alertmanager.yml
    ports:
      - "9093:9093"
    networks:
      - chrono-network
```

#### 2. Alert Manager Configuration
```bash
# Create AlertManager configuration
cat > config/alertmanager.yml << 'EOF'
global:
  smtp_smarthost: 'localhost:587'
  smtp_from: 'alerts@your-domain.com'

route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'web.hook'

receivers:
- name: 'web.hook'
  email_configs:
  - to: 'admin@your-domain.com'
    subject: 'Chrono Scraper Alert: {{ .GroupLabels.alertname }}'
    body: |
      {{ range .Alerts }}
      Alert: {{ .Annotations.summary }}
      Description: {{ .Annotations.description }}
      {{ end }}

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'dev', 'instance']
EOF
```

#### 3. Prometheus Alert Rules
```bash
# Create alert rules
mkdir -p config/rules
cat > config/rules/alerts.yml << 'EOF'
groups:
- name: chrono-scraper-alerts
  rules:
  
  # System Alerts
  - alert: HighCPUUsage
    expr: node_cpu_seconds_total{mode!="idle"} > 80
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High CPU usage detected"
      description: "CPU usage is above 80% for more than 5 minutes"

  - alert: HighMemoryUsage
    expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes > 0.85
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High memory usage detected"
      description: "Memory usage is above 85% for more than 5 minutes"

  # Application Alerts
  - alert: BackendDown
    expr: up{job="chrono-scraper"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Backend service is down"
      description: "The Chrono Scraper backend service is not responding"

  - alert: DatabaseConnectionFailure
    expr: pg_up == 0
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "Database connection failed"
      description: "PostgreSQL database is not accessible"

  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High error rate detected"
      description: "HTTP 5xx error rate is above 10% for more than 5 minutes"

  - alert: SlowAnalyticsQueries
    expr: histogram_quantile(0.95, rate(duckdb_query_duration_seconds_bucket[5m])) > 10
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Slow analytics queries detected"
      description: "95th percentile of DuckDB query duration is above 10 seconds"
EOF
```

## 🔄 Backup & Recovery

### Automated Backup Strategy

#### 1. Database Backup Script
```bash
# Create backup script
mkdir -p scripts
cat > scripts/backup.sh << 'EOF'
#!/bin/bash
set -e

BACKUP_DIR="/opt/chrono-scraper/backups"
DATE=$(date +"%Y%m%d_%H%M%S")
RETENTION_DAYS=30

# PostgreSQL Backup
echo "Creating PostgreSQL backup..."
docker-compose exec -T postgres pg_dump -U chrono_scraper chrono_scraper | gzip > "${BACKUP_DIR}/postgresql_${DATE}.sql.gz"

# DuckDB Backup
echo "Creating DuckDB backup..."
tar -czf "${BACKUP_DIR}/duckdb_${DATE}.tar.gz" -C data duckdb/

# Redis Backup
echo "Creating Redis backup..."
docker-compose exec -T redis redis-cli -a "${REDIS_PASSWORD}" --rdb /data/dump.rdb
cp data/redis/dump.rdb "${BACKUP_DIR}/redis_${DATE}.rdb"

# Configuration Backup
echo "Creating configuration backup..."
tar -czf "${BACKUP_DIR}/config_${DATE}.tar.gz" .env config/ ssl/

# Cleanup old backups
echo "Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "*.gz" -mtime +${RETENTION_DAYS} -delete
find "${BACKUP_DIR}" -name "*.rdb" -mtime +${RETENTION_DAYS} -delete

# Upload to S3 (optional)
if [[ -n "${AWS_S3_BACKUP_BUCKET}" ]]; then
    echo "Uploading backups to S3..."
    aws s3 sync "${BACKUP_DIR}" "s3://${AWS_S3_BACKUP_BUCKET}/chrono-scraper-backups/"
fi

echo "Backup completed successfully: ${DATE}"
EOF

chmod +x scripts/backup.sh
```

#### 2. Restore Script
```bash
# Create restore script
cat > scripts/restore.sh << 'EOF'
#!/bin/bash
set -e

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <backup_date> <component>"
    echo "Components: postgresql, duckdb, redis, config, all"
    exit 1
fi

BACKUP_DATE=$1
COMPONENT=$2
BACKUP_DIR="/opt/chrono-scraper/backups"

case $COMPONENT in
    postgresql)
        echo "Restoring PostgreSQL backup from ${BACKUP_DATE}..."
        zcat "${BACKUP_DIR}/postgresql_${BACKUP_DATE}.sql.gz" | docker-compose exec -T postgres psql -U chrono_scraper -d chrono_scraper
        ;;
    duckdb)
        echo "Restoring DuckDB backup from ${BACKUP_DATE}..."
        rm -rf data/duckdb/*
        tar -xzf "${BACKUP_DIR}/duckdb_${BACKUP_DATE}.tar.gz" -C data/
        ;;
    redis)
        echo "Restoring Redis backup from ${BACKUP_DATE}..."
        docker-compose stop redis
        cp "${BACKUP_DIR}/redis_${BACKUP_DATE}.rdb" data/redis/dump.rdb
        docker-compose start redis
        ;;
    config)
        echo "Restoring configuration backup from ${BACKUP_DATE}..."
        tar -xzf "${BACKUP_DIR}/config_${BACKUP_DATE}.tar.gz"
        ;;
    all)
        echo "Restoring all components from ${BACKUP_DATE}..."
        $0 $BACKUP_DATE postgresql
        $0 $BACKUP_DATE duckdb
        $0 $BACKUP_DATE redis
        $0 $BACKUP_DATE config
        ;;
    *)
        echo "Invalid component: $COMPONENT"
        exit 1
        ;;
esac

echo "Restore completed successfully"
EOF

chmod +x scripts/restore.sh
```

#### 3. Backup Automation
```bash
# Add backup job to crontab
echo "0 2 * * * /opt/chrono-scraper/scripts/backup.sh" | crontab -

# Create systemd service for backups (alternative to cron)
sudo cat > /etc/systemd/system/chrono-backup.service << 'EOF'
[Unit]
Description=Chrono Scraper Backup Service
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/opt/chrono-scraper/scripts/backup.sh
User=chrono
Group=chrono
WorkingDirectory=/opt/chrono-scraper

[Install]
WantedBy=multi-user.target
EOF

sudo cat > /etc/systemd/system/chrono-backup.timer << 'EOF'
[Unit]
Description=Run Chrono Scraper backup daily
Requires=chrono-backup.service

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=1800

[Install]
WantedBy=timers.target
EOF

sudo systemctl enable chrono-backup.timer
sudo systemctl start chrono-backup.timer
```

## 🔍 Troubleshooting & Maintenance

### Common Deployment Issues

#### 1. Service Health Check Script
```bash
# Create comprehensive health check script
cat > scripts/health_check.sh << 'EOF'
#!/bin/bash

echo "=== Chrono Scraper Health Check ==="
echo "Timestamp: $(date)"
echo

# Check Docker services
echo "🔍 Checking Docker services..."
docker-compose -f docker-compose.production.yml ps

echo
echo "🔍 Checking service endpoints..."

# Backend health check
if curl -f -s http://localhost:8000/api/v1/health > /dev/null; then
    echo "✅ Backend API: Healthy"
else
    echo "❌ Backend API: Unhealthy"
fi

# Analytics health check
if curl -f -s http://localhost:8000/api/v1/analytics/health > /dev/null; then
    echo "✅ Analytics API: Healthy"
else
    echo "❌ Analytics API: Unhealthy"
fi

# Database connections
echo
echo "🔍 Testing database connections..."
docker-compose exec -T postgres pg_isready -U chrono_scraper -d chrono_scraper
docker-compose exec -T redis redis-cli -a "${REDIS_PASSWORD}" ping

echo
echo "🔍 System resources..."
echo "CPU Usage: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | awk -F'%' '{print $1}')%"
echo "Memory Usage: $(free | grep Mem | awk '{printf("%.1f%%", $3/$2 * 100.0)}')"
echo "Disk Usage: $(df -h / | awk 'NR==2 {print $5}')"

echo
echo "🔍 Recent errors..."
docker-compose logs --tail=10 backend | grep -i error || echo "No recent errors found"

echo
echo "=== Health Check Complete ==="
EOF

chmod +x scripts/health_check.sh
```

#### 2. Performance Monitoring Script
```bash
# Create performance monitoring script
cat > scripts/performance_monitor.sh << 'EOF'
#!/bin/bash

echo "=== Performance Monitoring Report ==="
echo "Generated: $(date)"
echo

# Container resource usage
echo "🐳 Container Resource Usage:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

echo
echo "📊 Database Performance:"

# PostgreSQL stats
echo "PostgreSQL connections:"
docker-compose exec -T postgres psql -U chrono_scraper -d chrono_scraper -c "
    SELECT state, count(*) 
    FROM pg_stat_activity 
    WHERE datname = 'chrono_scraper' 
    GROUP BY state;
" 2>/dev/null || echo "Could not connect to PostgreSQL"

# DuckDB performance (if accessible)
echo
echo "🦆 DuckDB Performance:"
echo "Memory usage and query metrics available via /api/v1/analytics/health endpoint"

# Redis stats
echo
echo "📦 Redis Statistics:"
docker-compose exec -T redis redis-cli -a "${REDIS_PASSWORD}" info memory 2>/dev/null | grep used_memory_human || echo "Could not connect to Redis"

echo
echo "=== Performance Report Complete ==="
EOF

chmod +x scripts/performance_monitor.sh
```

### Maintenance Procedures

#### 1. Update Deployment Script
```bash
# Create update deployment script
cat > scripts/update.sh << 'EOF'
#!/bin/bash
set -e

echo "=== Chrono Scraper Update Procedure ==="

# Create backup before update
echo "🔄 Creating backup before update..."
./scripts/backup.sh

# Pull latest changes
echo "📥 Pulling latest code changes..."
git fetch origin
git checkout main
git pull origin main

# Update environment if needed
echo "🔧 Checking environment configuration..."
if [[ -f .env.example ]]; then
    echo "Please review .env.example for any new configuration options"
fi

# Rebuild containers
echo "🏗️ Rebuilding containers..."
docker-compose -f docker-compose.production.yml build --no-cache

# Run database migrations
echo "📊 Running database migrations..."
docker-compose -f docker-compose.production.yml run --rm backend alembic upgrade head

# Restart services with zero-downtime
echo "🔄 Restarting services..."
docker-compose -f docker-compose.production.yml up -d --force-recreate

# Health check
echo "🏥 Running health checks..."
sleep 30
./scripts/health_check.sh

echo "✅ Update completed successfully"
EOF

chmod +x scripts/update.sh
```

#### 2. Log Management
```bash
# Create log management script
cat > scripts/manage_logs.sh << 'EOF'
#!/bin/bash

ACTION=${1:-"rotate"}
RETENTION_DAYS=${2:-30}

case $ACTION in
    rotate)
        echo "Rotating logs older than ${RETENTION_DAYS} days..."
        find logs/ -name "*.log" -mtime +${RETENTION_DAYS} -exec gzip {} \;
        find logs/ -name "*.log.gz" -mtime +90 -delete
        ;;
    clean)
        echo "Cleaning up old log files..."
        find logs/ -name "*.log.gz" -mtime +${RETENTION_DAYS} -delete
        ;;
    analyze)
        echo "=== Log Analysis Report ==="
        echo "Log sizes:"
        du -sh logs/*
        echo
        echo "Recent error patterns:"
        grep -h "ERROR" logs/*.log 2>/dev/null | tail -20 || echo "No recent errors"
        ;;
    *)
        echo "Usage: $0 {rotate|clean|analyze} [retention_days]"
        exit 1
        ;;
esac
EOF

chmod +x scripts/manage_logs.sh
```

---

## 🎯 Deployment Validation Checklist

### Pre-Deployment Validation
- [ ] Hardware requirements met
- [ ] All required software installed
- [ ] Environment configuration validated
- [ ] SSL certificates installed
- [ ] Firewall rules configured
- [ ] Backup storage configured

### Deployment Validation
- [ ] All containers start successfully
- [ ] Database connections established
- [ ] DuckDB service initialized
- [ ] All health endpoints return 200
- [ ] SSL certificates valid
- [ ] Analytics API endpoints functional
- [ ] WebSocket connections working
- [ ] Export functionality tested

### Post-Deployment Validation
- [ ] Monitoring alerts configured
- [ ] Backup automation working
- [ ] Log rotation configured
- [ ] Performance metrics collecting
- [ ] Security hardening applied
- [ ] Documentation updated

### Production Readiness Checklist
- [ ] Load testing completed
- [ ] Security audit performed
- [ ] Disaster recovery tested
- [ ] Monitoring dashboards configured
- [ ] Team trained on operations
- [ ] Support procedures documented

---

This comprehensive deployment guide provides everything needed for a successful Phase 2 DuckDB analytics system deployment, from initial setup through production hardening and ongoing maintenance procedures.