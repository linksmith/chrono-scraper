#!/bin/bash

# Chrono Scraper Shared Pages Monitoring Setup Script
# This script sets up the complete monitoring stack for the shared pages architecture

set -e

echo "🚀 Setting up Chrono Scraper Shared Pages Monitoring Stack..."

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[SETUP]${NC} $1"
}

# Check if Docker and Docker Compose are installed
print_header "Checking prerequisites..."
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

print_status "Docker and Docker Compose are installed."

# Check if main application is running
print_header "Checking main application status..."
if ! docker compose ps | grep -q "chrono-scraper"; then
    print_warning "Main Chrono Scraper application doesn't appear to be running."
    echo "Please start the main application first with: docker compose up -d"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    print_status "Main application is running."
fi

# Create monitoring directories if they don't exist
print_header "Creating monitoring directories..."
mkdir -p grafana/dashboards
mkdir -p grafana/provisioning/dashboards
mkdir -p grafana/provisioning/datasources
mkdir -p loki
mkdir -p alertmanager

print_status "Monitoring directories created."

# Create Grafana provisioning configuration
print_header "Setting up Grafana provisioning..."

cat > grafana/provisioning/dashboards/dashboard.yml << EOF
apiVersion: 1

providers:
  - name: 'default'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
EOF

cat > grafana/provisioning/datasources/datasource.yml << EOF
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    editable: true
EOF

print_status "Grafana provisioning configured."

# Create Loki configuration
print_header "Setting up Loki configuration..."

cat > loki/loki-config.yml << EOF
auth_enabled: false

server:
  http_listen_port: 3100

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    instance_addr: 127.0.0.1
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

ruler:
  alertmanager_url: http://alertmanager:9093

analytics:
  reporting_enabled: false
EOF

cat > loki/promtail-config.yml << EOF
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: containers
    static_configs:
      - targets:
          - localhost
        labels:
          job: containerlogs
          __path__: /var/lib/docker/containers/*/*log

    pipeline_stages:
      - json:
          expressions:
            output: log
            stream: stream
            attrs:
      - json:
          expressions:
            tag:
          source: attrs
      - regex:
          expression: (?P<container_name>(?:[^|]*))\|
          source: tag
      - timestamp:
          format: RFC3339Nano
          source: time
      - labels:
          stream:
          container_name:
      - output:
          source: output
EOF

print_status "Loki configuration created."

# Set up permissions for monitoring directories
print_header "Setting up permissions..."
chmod +r grafana/provisioning/dashboards/dashboard.yml
chmod +r grafana/provisioning/datasources/datasource.yml
chmod +r loki/loki-config.yml
chmod +r loki/promtail-config.yml

print_status "Permissions configured."

# Validate Prometheus configuration
print_header "Validating Prometheus configuration..."
if command -v promtool &> /dev/null; then
    promtool check config prometheus/prometheus.yml
    promtool check rules prometheus/shared_pages_alerts.yml
    promtool check rules prometheus/performance_alerts.yml
    print_status "Prometheus configuration is valid."
else
    print_warning "Promtool not found. Skipping validation."
fi

# Create environment file for monitoring stack
print_header "Creating environment configuration..."
cat > .env.monitoring << EOF
# Grafana Configuration
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=admin_password_change_me
GF_USERS_ALLOW_SIGN_UP=false

# SMTP Configuration (update these for production)
SMTP_HOST=localhost
SMTP_PORT=587
SMTP_USER=alerts@chrono-scraper.com
SMTP_PASSWORD=your_smtp_password

# Slack Configuration (update for production)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
EOF

print_status "Environment configuration created."

# Start the monitoring stack
print_header "Starting monitoring stack..."
if docker compose -f docker-compose.monitoring.yml up -d; then
    print_status "Monitoring stack started successfully!"
else
    print_error "Failed to start monitoring stack."
    exit 1
fi

# Wait for services to be ready
print_header "Waiting for services to be ready..."
sleep 10

# Check service health
print_header "Checking service health..."

check_service() {
    local service_name=$1
    local url=$2
    local expected_status=${3:-200}
    
    if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "$expected_status"; then
        print_status "$service_name is healthy"
        return 0
    else
        print_warning "$service_name is not responding correctly"
        return 1
    fi
}

# Wait a bit more for all services to fully start
sleep 20

# Health checks
print_status "Performing health checks..."

check_service "Prometheus" "http://localhost:9090/-/healthy"
check_service "Grafana" "http://localhost:3001/api/health"
check_service "AlertManager" "http://localhost:9093/-/healthy"
check_service "Node Exporter" "http://localhost:9100/metrics" "200"

# Check if backend metrics are available
if curl -s "http://localhost:8000/api/v1/monitoring/health" > /dev/null; then
    print_status "Backend monitoring endpoints are accessible"
else
    print_warning "Backend monitoring endpoints are not accessible"
    print_warning "Make sure the main application is running"
fi

# Import Grafana dashboards
print_header "Importing Grafana dashboards..."
sleep 5  # Wait for Grafana to be fully ready

import_dashboard() {
    local dashboard_file=$1
    local dashboard_name=$2
    
    if [ -f "$dashboard_file" ]; then
        print_status "Dashboard files are in place for: $dashboard_name"
    else
        print_warning "Dashboard file not found: $dashboard_file"
    fi
}

import_dashboard "grafana/dashboards/shared-pages-overview.json" "Shared Pages Overview"
import_dashboard "grafana/dashboards/shared-pages-performance.json" "Shared Pages Performance"
import_dashboard "grafana/dashboards/shared-pages-business-metrics.json" "Shared Pages Business Metrics"

# Final status report
print_header "Setup complete! 🎉"
echo
echo "📊 Monitoring Services:"
echo "  • Grafana:       http://localhost:3001 (admin/admin_password_change_me)"
echo "  • Prometheus:    http://localhost:9090"
echo "  • AlertManager:  http://localhost:9093"
echo "  • Node Exporter: http://localhost:9100"
echo
echo "🔍 Key Monitoring URLs:"
echo "  • Shared Pages Health:  http://localhost:8000/api/v1/monitoring/shared-pages/health"
echo "  • Shared Pages Metrics: http://localhost:8000/api/v1/monitoring/shared-pages/metrics"
echo "  • Prometheus Metrics:   http://localhost:8000/api/v1/monitoring/shared-pages/prometheus"
echo
echo "📈 Grafana Dashboards (will be available after first login):"
echo "  • Shared Pages Overview"
echo "  • Shared Pages Performance"
echo "  • Shared Pages Business Metrics"
echo
echo "⚠️  Important Notes:"
echo "  • Change default Grafana password in production"
echo "  • Configure SMTP settings in alertmanager.yml"
echo "  • Set up Slack webhook URL for alerts"
echo "  • Review alert thresholds for your environment"
echo
echo "📚 Documentation:"
echo "  • Monitoring Guide: ./SHARED_PAGES_MONITORING_GUIDE.md"
echo "  • Setup README: ./README.md"
echo
print_status "Monitoring stack is ready for use!"

# Offer to show logs
echo
read -p "Do you want to view the monitoring stack logs? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker compose -f docker-compose.monitoring.yml logs -f
fi