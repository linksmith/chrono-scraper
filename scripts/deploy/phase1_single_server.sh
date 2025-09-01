#!/bin/bash
set -euo pipefail

# Chrono Scraper v2 - Phase 1 Production Deployment Script
# Deploys to single Hetzner CX32 server with monitoring and backup

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SERVER_TYPE="cx32"
SERVER_NAME="chrono-prod-01"
SERVER_LOCATION="fsn1"  # Falkenstein, Germany
DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-admin@chrono-scraper.com}"
HCLOUD_TOKEN="${HCLOUD_TOKEN:-}"
DRY_RUN=false
SKIP_SERVER_CREATION=false

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy Chrono Scraper v2 to Phase 1 production (single server)

OPTIONS:
    --domain DOMAIN       Domain name for the application
    --email EMAIL         Email for Let's Encrypt certificates  
    --dry-run            Show what would be done
    --skip-server        Skip server creation (use existing server)
    --help               Show this help

ENVIRONMENT VARIABLES:
    HCLOUD_TOKEN         Required: Hetzner Cloud API token
    DOMAIN               Application domain name
    EMAIL                Admin email address

EXAMPLES:
    $0 --domain app.chrono-scraper.com --email admin@company.com
    $0 --skip-server --domain localhost  # Use existing server
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --domain)
                DOMAIN="$2"
                shift 2
                ;;
            --email)
                EMAIL="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --skip-server)
                SKIP_SERVER_CREATION=true
                shift
                ;;
            --help)
                usage
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
}

validate_prerequisites() {
    log "Validating prerequisites..."
    
    # Check required tools
    local tools=("docker" "docker-compose" "git" "curl" "ssh")
    if [[ "$SKIP_SERVER_CREATION" == "false" ]]; then
        tools+=("hcloud")
    fi
    
    for tool in "${tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            error "Required tool missing: $tool"
            exit 1
        fi
    done
    
    # Check Hetzner Cloud token
    if [[ "$SKIP_SERVER_CREATION" == "false" ]] && [[ -z "$HCLOUD_TOKEN" ]]; then
        error "HCLOUD_TOKEN environment variable required"
        exit 1
    fi
    
    # Validate domain
    if [[ -z "$DOMAIN" ]]; then
        error "Domain must be specified with --domain"
        exit 1
    fi
    
    # Check SSH key
    if [[ ! -f ~/.ssh/id_rsa.pub ]]; then
        error "SSH public key not found at ~/.ssh/id_rsa.pub"
        exit 1
    fi
    
    success "Prerequisites validated"
}

create_cloud_init() {
    local cloud_init_file="/tmp/chrono-cloud-init.yml"
    
    cat > "$cloud_init_file" << 'EOF'
#cloud-config
users:
  - name: chrono
    groups: sudo, docker
    shell: /bin/bash
    sudo: ['ALL=(ALL) NOPASSWD:ALL']
    ssh_authorized_keys:
      - SSH_PUBLIC_KEY_PLACEHOLDER

packages:
  - docker.io
  - docker-compose
  - git
  - curl
  - htop
  - fail2ban
  - ufw
  - certbot
  - python3-certbot-nginx

package_update: true
package_upgrade: true

runcmd:
  # Configure firewall
  - ufw --force enable
  - ufw allow ssh
  - ufw allow 80/tcp
  - ufw allow 443/tcp
  - ufw allow 8000/tcp  # API during setup
  
  # Configure fail2ban
  - systemctl enable fail2ban
  - systemctl start fail2ban
  
  # Configure Docker
  - systemctl enable docker
  - systemctl start docker
  - usermod -aG docker chrono
  
  # Create application directory
  - mkdir -p /opt/chrono-scraper
  - chown chrono:chrono /opt/chrono-scraper
  
  # Install docker-compose (latest version)
  - curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
  - chmod +x /usr/local/bin/docker-compose
  
  # Set up log rotation for Docker
  - echo '{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}' > /etc/docker/daemon.json
  - systemctl restart docker
  
write_files:
  - path: /etc/fail2ban/jail.local
    content: |
      [sshd]
      enabled = true
      port = ssh
      filter = sshd
      logpath = /var/log/auth.log
      maxretry = 3
      bantime = 3600
      
  - path: /etc/cron.d/certbot
    content: |
      0 12 * * * root test -x /usr/bin/certbot -a \! -d /run/systemd/system && perl -e 'sleep int(rand(43200))' && certbot -q renew
EOF
    
    # Replace SSH key placeholder
    local ssh_key=$(cat ~/.ssh/id_rsa.pub)
    sed -i "s|SSH_PUBLIC_KEY_PLACEHOLDER|$ssh_key|" "$cloud_init_file"
    
    echo "$cloud_init_file"
}

create_server() {
    if [[ "$SKIP_SERVER_CREATION" == "true" ]]; then
        log "Skipping server creation"
        return 0
    fi
    
    log "Creating Hetzner Cloud server: $SERVER_NAME ($SERVER_TYPE)"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would create server with:"
        log "  - Type: $SERVER_TYPE (4 vCPU, 8GB RAM, 80GB NVMe)"
        log "  - Location: $SERVER_LOCATION"
        log "  - Image: ubuntu-22.04"
        return 0
    fi
    
    # Create cloud-init configuration
    local cloud_init_file=$(create_cloud_init)
    
    # Create server
    hcloud server create \
        --name "$SERVER_NAME" \
        --type "$SERVER_TYPE" \
        --location "$SERVER_LOCATION" \
        --image ubuntu-22.04 \
        --ssh-key-file ~/.ssh/id_rsa.pub \
        --user-data-from-file "$cloud_init_file"
    
    # Wait for server to be ready
    log "Waiting for server to initialize..."
    local max_wait=300  # 5 minutes
    local waited=0
    
    while [[ $waited -lt $max_wait ]]; do
        if hcloud server describe "$SERVER_NAME" --output json | jq -r '.status' | grep -q "running"; then
            break
        fi
        sleep 10
        waited=$((waited + 10))
    done
    
    if [[ $waited -ge $max_wait ]]; then
        error "Server creation timeout"
        exit 1
    fi
    
    # Get server IP
    local server_ip=$(hcloud server describe "$SERVER_NAME" --output json | jq -r '.public_net.ipv4.ip')
    log "Server created with IP: $server_ip"
    
    # Update DNS (manual step for now)
    warn "Please update your DNS to point $DOMAIN to $server_ip"
    read -p "Press Enter when DNS is configured..."
    
    # Wait for SSH to be available
    log "Waiting for SSH access..."
    while ! ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no chrono@"$server_ip" "echo 'SSH ready'" &>/dev/null; do
        sleep 10
    done
    
    success "Server ready: $server_ip"
    echo "$server_ip" > /tmp/server_ip
    
    # Clean up
    rm -f "$cloud_init_file"
}

deploy_application() {
    local server_ip
    if [[ "$SKIP_SERVER_CREATION" == "true" ]]; then
        if [[ "$DOMAIN" == "localhost" ]]; then
            server_ip="localhost"
        else
            read -p "Enter server IP address: " server_ip
        fi
    else
        server_ip=$(cat /tmp/server_ip)
    fi
    
    log "Deploying application to $server_ip"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would deploy application to server"
        return 0
    fi
    
    # Create production environment file
    create_production_env
    
    if [[ "$server_ip" == "localhost" ]]; then
        # Local deployment
        deploy_locally
    else
        # Remote deployment
        deploy_remotely "$server_ip"
    fi
}

create_production_env() {
    log "Creating production environment configuration..."
    
    local prod_env_file="$PROJECT_DIR/.env.production"
    
    cat > "$prod_env_file" << EOF
# Chrono Scraper v2 - Phase 1 Production Configuration
NODE_ENV=production
ENVIRONMENT=production

# Application
FRONTEND_URL=https://$DOMAIN
API_BASE_URL=https://$DOMAIN/api/v1
SECRET_KEY=$(openssl rand -hex 32)
ADMIN_EMAIL=$EMAIL

# Database
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=chrono_scraper
POSTGRES_PASSWORD=$(openssl rand -base64 32)
POSTGRES_DB=chrono_scraper

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=$(openssl rand -base64 32)

# Meilisearch
MEILISEARCH_HOST=http://meilisearch:7700
MEILISEARCH_MASTER_KEY=$(openssl rand -base64 32)

# Celery
CELERY_BROKER_URL=redis://:\${REDIS_PASSWORD}@redis:6379/0
CELERY_RESULT_BACKEND=redis://:\${REDIS_PASSWORD}@redis:6379/0

# Email (configure based on your provider)
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
EMAIL_FROM=noreply@$DOMAIN

# Firecrawl (local)
FIRECRAWL_LOCAL_URL=http://firecrawl-api:3002
FIRECRAWL_API_KEY=local-development-key

# Monitoring
SENTRY_DSN=
PROMETHEUS_ENABLED=true

# Resource limits (Phase 1 optimized)
DATABASE_MAX_CONNECTIONS=20
REDIS_MAX_MEMORY=512mb
CELERY_WORKER_PROCESSES=2
CELERY_WORKER_CONCURRENCY=4

# Security
CORS_ORIGINS=["https://$DOMAIN"]
ALLOWED_HOSTS=["$DOMAIN"]
SECURE_COOKIES=true
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
EOF
    
    success "Production environment created: $prod_env_file"
}

deploy_locally() {
    log "Deploying locally..."
    
    cd "$PROJECT_DIR"
    
    # Copy production environment
    cp .env.production .env
    
    # Pull latest images and build
    docker-compose -f docker-compose.production.yml pull
    docker-compose -f docker-compose.production.yml build
    
    # Start services
    docker-compose -f docker-compose.production.yml up -d
    
    # Wait for services to be healthy
    log "Waiting for services to be healthy..."
    sleep 60
    
    # Run database migrations
    docker-compose -f docker-compose.production.yml exec -T backend alembic upgrade head
    
    # Create superuser
    docker-compose -f docker-compose.production.yml exec -T backend python -c "
import asyncio
from app.core.database import get_db
from app.models.user import User
from app.core.security import get_password_hash
from sqlmodel import select

async def create_superuser():
    async for db in get_db():
        stmt = select(User).where(User.email == '$EMAIL')
        result = await db.execute(stmt)
        if not result.scalar_one_or_none():
            user = User(
                email='$EMAIL',
                full_name='System Administrator',
                hashed_password=get_password_hash('$(openssl rand -base64 12)'),
                is_superuser=True,
                is_verified=True,
                is_active=True,
                approval_status='approved'
            )
            db.add(user)
            await db.commit()
            print(f'Superuser created: {user.email}')
        break

asyncio.run(create_superuser())
"
    
    success "Local deployment completed"
}

deploy_remotely() {
    local server_ip="$1"
    
    log "Deploying to remote server: $server_ip"
    
    # Copy application files
    log "Copying application files..."
    rsync -avz --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
        "$PROJECT_DIR/" chrono@"$server_ip":/opt/chrono-scraper/
    
    # Copy production environment
    scp "$PROJECT_DIR/.env.production" chrono@"$server_ip":/opt/chrono-scraper/.env
    
    # Deploy on remote server
    ssh chrono@"$server_ip" << 'REMOTE_SCRIPT'
        cd /opt/chrono-scraper
        
        # Pull latest images and build
        docker-compose -f docker-compose.production.yml pull
        docker-compose -f docker-compose.production.yml build
        
        # Start services
        docker-compose -f docker-compose.production.yml up -d
        
        # Wait for services
        sleep 60
        
        # Run migrations
        docker-compose -f docker-compose.production.yml exec -T backend alembic upgrade head
REMOTE_SCRIPT
    
    success "Remote deployment completed"
}

create_production_compose() {
    log "Creating production Docker Compose configuration..."
    
    cat > "$PROJECT_DIR/docker-compose.production.yml" << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 30s
      timeout: 10s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "--no-auth-warning", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 30s
      timeout: 10s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 512M

  meilisearch:
    image: getmeili/meilisearch:v1.5
    environment:
      MEILI_MASTER_KEY: ${MEILISEARCH_MASTER_KEY}
      MEILI_ENV: production
      MEILI_NO_ANALYTICS: true
    volumes:
      - meilisearch_data:/meili_data
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G

  firecrawl-api:
    image: mendableai/firecrawl:latest
    environment:
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379
      USE_DB_AUTHENTICATION: true
    depends_on:
      - redis
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M

  backend:
    build: 
      context: ./backend
      dockerfile: Dockerfile.production
    environment:
      - POSTGRES_HOST=postgres
      - REDIS_HOST=redis
      - MEILISEARCH_HOST=http://meilisearch:7700
      - FIRECRAWL_LOCAL_URL=http://firecrawl-api:3002
    env_file:
      - .env
    depends_on:
      - postgres
      - redis
      - meilisearch
      - firecrawl-api
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 1G

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.production
    environment:
      - NODE_ENV=production
      - API_BASE_URL=http://backend:8000/api/v1
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M

  celery-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile.production
    command: celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
    environment:
      - POSTGRES_HOST=postgres
      - REDIS_HOST=redis
      - MEILISEARCH_HOST=http://meilisearch:7700
      - FIRECRAWL_LOCAL_URL=http://firecrawl-api:3002
    env_file:
      - .env
    depends_on:
      - postgres
      - redis
      - backend
    restart: unless-stopped
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 512M

  celery-beat:
    build:
      context: ./backend
      dockerfile: Dockerfile.production
    command: celery -A app.tasks.celery_app beat --loglevel=info
    environment:
      - POSTGRES_HOST=postgres
      - REDIS_HOST=redis
    env_file:
      - .env
    depends_on:
      - postgres
      - redis
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/production.conf:/etc/nginx/conf.d/default.conf
      - ./nginx/ssl:/etc/nginx/ssl
      - /etc/letsencrypt:/etc/letsencrypt
    depends_on:
      - backend
      - frontend
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M

  grafana:
    image: grafana/grafana:latest
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana-dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana-datasources:/etc/grafana/provisioning/datasources
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M

volumes:
  postgres_data:
  redis_data:
  meilisearch_data:
  prometheus_data:
  grafana_data:
EOF
    
    success "Production Docker Compose configuration created"
}

setup_monitoring() {
    log "Setting up monitoring and alerting..."
    
    # Create monitoring directory
    mkdir -p "$PROJECT_DIR/monitoring"
    
    # Prometheus configuration
    cat > "$PROJECT_DIR/monitoring/prometheus.yml" << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'backend'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/api/v1/metrics'

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres:5432']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']

rule_files:
  - "alert_rules.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']
EOF
    
    # Basic alert rules
    cat > "$PROJECT_DIR/monitoring/alert_rules.yml" << 'EOF'
groups:
  - name: chrono_scraper_alerts
    rules:
      - alert: HighCPUUsage
        expr: cpu_usage_percent > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage detected"
          
      - alert: HighMemoryUsage
        expr: memory_usage_percent > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage detected"
          
      - alert: ApplicationDown
        expr: up{job="backend"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Application is down"
EOF
    
    success "Monitoring configuration created"
}

setup_nginx() {
    log "Setting up Nginx configuration..."
    
    mkdir -p "$PROJECT_DIR/nginx"
    
    cat > "$PROJECT_DIR/nginx/production.conf" << EOF
upstream backend_api {
    server backend:8000;
}

upstream frontend_app {
    server frontend:5173;
}

# HTTP redirect to HTTPS
server {
    listen 80;
    server_name $DOMAIN;
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name $DOMAIN;
    
    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
    
    # API routes
    location /api/ {
        proxy_pass http://backend_api;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # WebSocket for real-time updates
    location /ws/ {
        proxy_pass http://backend_api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Frontend application
    location / {
        proxy_pass http://frontend_app;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Static files (if serving directly)
    location /static/ {
        alias /var/www/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF
    
    success "Nginx configuration created"
}

setup_ssl() {
    if [[ "$DOMAIN" == "localhost" ]]; then
        log "Skipping SSL setup for localhost"
        return 0
    fi
    
    log "Setting up SSL certificates with Let's Encrypt..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would obtain SSL certificate for $DOMAIN"
        return 0
    fi
    
    # This would be handled by the server's certbot
    warn "SSL certificate setup must be completed on the server after deployment"
    log "Run: certbot --nginx -d $DOMAIN"
}

main() {
    parse_args "$@"
    
    log "Starting Chrono Scraper v2 Phase 1 deployment"
    log "Target domain: $DOMAIN"
    log "Admin email: $EMAIL"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        warn "DRY RUN MODE - No changes will be made"
    fi
    
    # Execute deployment steps
    validate_prerequisites
    create_production_compose
    setup_monitoring
    setup_nginx
    create_server
    deploy_application
    setup_ssl
    
    success "Phase 1 deployment completed!"
    
    cat << EOF

🎉 Chrono Scraper v2 is now deployed in Phase 1 configuration!

📊 Dashboard URLs:
   Application: https://$DOMAIN
   Monitoring: https://$DOMAIN:9090 (Prometheus)
   Metrics: https://$DOMAIN:3000 (Grafana)

🔧 Next Steps:
   1. Complete SSL certificate setup (if not using localhost)
   2. Configure email settings in .env file
   3. Set up DNS monitoring and alerts
   4. Run initial data backup: make backup
   5. Monitor resource usage: make monitor

📈 Scaling:
   When ready to scale, run: ./scripts/scaling/scaling_decision.py
   
🆘 Support:
   Logs: docker-compose -f docker-compose.production.yml logs -f
   Health: curl https://$DOMAIN/api/v1/health
   Backup: See SCALING_STRATEGY.md for procedures

EOF
}

main "$@"