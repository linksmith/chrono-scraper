#!/bin/bash
# Production Deployment Script for Chrono Scraper v2 on Hetzner Cloud
# Usage: ./deploy-production.sh [init|deploy|update|status|backup|restore]

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TERRAFORM_DIR="${PROJECT_ROOT}/infrastructure/terraform"
COMPOSE_FILE="${PROJECT_ROOT}/infrastructure/docker-compose.production.yml"
ENV_FILE="${PROJECT_ROOT}/.env.production"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check required tools
    local tools=("terraform" "ssh" "scp" "curl" "jq")
    for tool in "${tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            log_error "$tool is not installed. Please install it first."
            exit 1
        fi
    done
    
    # Check Terraform configuration
    if [[ ! -f "${TERRAFORM_DIR}/terraform.tfvars" ]]; then
        log_error "terraform.tfvars not found. Please copy and configure terraform.tfvars.example"
        exit 1
    fi
    
    # Check environment file
    if [[ ! -f "${ENV_FILE}" ]]; then
        log_warning ".env.production not found. Will use .env.example as template."
    fi
    
    log_success "Prerequisites check completed"
}

# Initialize infrastructure
init_infrastructure() {
    log_info "Initializing Hetzner Cloud infrastructure..."
    
    cd "${TERRAFORM_DIR}"
    
    # Initialize Terraform
    terraform init
    
    # Validate configuration
    terraform validate
    
    # Plan deployment
    log_info "Planning infrastructure deployment..."
    terraform plan -out=tfplan
    
    # Confirm deployment
    echo
    log_warning "Review the plan above. Continue with deployment? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        log_info "Deployment cancelled."
        exit 0
    fi
    
    # Apply infrastructure
    log_info "Deploying infrastructure to Hetzner Cloud..."
    terraform apply tfplan
    
    # Save outputs
    terraform output -json > "${PROJECT_ROOT}/infrastructure/terraform-outputs.json"
    
    log_success "Infrastructure deployment completed!"
    
    # Display connection information
    display_connection_info
    
    # Wait for server initialization
    log_info "Waiting for server initialization (cloud-init)..."
    sleep 60
    
    # Test SSH connection
    test_ssh_connection
}

# Deploy application
deploy_application() {
    log_info "Deploying Chrono Scraper v2 application..."
    
    # Get server information
    local server_ip
    server_ip=$(get_server_ip)
    
    if [[ -z "$server_ip" ]]; then
        log_error "Could not determine server IP. Ensure infrastructure is deployed."
        exit 1
    fi
    
    # Test SSH connection
    test_ssh_connection
    
    # Create application directory on server
    log_info "Setting up application directory on server..."
    ssh -p 2222 -o StrictHostKeyChecking=no ubuntu@"$server_ip" "
        sudo mkdir -p /opt/chrono-scraper
        sudo chown ubuntu:ubuntu /opt/chrono-scraper
    "
    
    # Upload application files
    log_info "Uploading application files..."
    rsync -avz --exclude='*.git' --exclude='node_modules' --exclude='__pycache__' \
          -e 'ssh -p 2222 -o StrictHostKeyChecking=no' \
          "${PROJECT_ROOT}/" ubuntu@"$server_ip":/opt/chrono-scraper/
    
    # Upload environment file
    if [[ -f "${ENV_FILE}" ]]; then
        log_info "Uploading production environment file..."
        scp -P 2222 -o StrictHostKeyChecking=no "${ENV_FILE}" ubuntu@"$server_ip":/opt/chrono-scraper/.env
    else
        log_warning "No .env.production found. Using .env.example as template."
        scp -P 2222 -o StrictHostKeyChecking=no "${PROJECT_ROOT}/.env.example" ubuntu@"$server_ip":/opt/chrono-scraper/.env
    fi
    
    # Deploy application
    log_info "Starting application containers..."
    ssh -p 2222 -o StrictHostKeyChecking=no ubuntu@"$server_ip" "
        cd /opt/chrono-scraper
        
        # Make sure data directories exist
        sudo mkdir -p /mnt/data/{postgres,redis,meilisearch,logs,letsencrypt,backups}
        sudo chown -R ubuntu:ubuntu /mnt/data
        
        # Start application
        docker-compose -f infrastructure/docker-compose.production.yml up -d
        
        # Wait for services to start
        echo 'Waiting for services to start...'
        sleep 30
        
        # Check service health
        docker-compose -f infrastructure/docker-compose.production.yml ps
    "
    
    # Wait for application startup
    log_info "Waiting for application to fully start..."
    sleep 60
    
    # Test application health
    test_application_health "$server_ip"
    
    # Setup SSL certificates
    setup_ssl_certificates "$server_ip"
    
    log_success "Application deployment completed!"
    display_application_info
}

# Update application
update_application() {
    log_info "Updating Chrono Scraper v2 application..."
    
    local server_ip
    server_ip=$(get_server_ip)
    
    if [[ -z "$server_ip" ]]; then
        log_error "Could not determine server IP. Ensure infrastructure is deployed."
        exit 1
    fi
    
    # Create backup before update
    log_info "Creating backup before update..."
    ssh -p 2222 -o StrictHostKeyChecking=no ubuntu@"$server_ip" "/home/ubuntu/backup-script.sh"
    
    # Upload updated files
    log_info "Uploading updated application files..."
    rsync -avz --exclude='*.git' --exclude='node_modules' --exclude='__pycache__' \
          -e 'ssh -p 2222 -o StrictHostKeyChecking=no' \
          "${PROJECT_ROOT}/" ubuntu@"$server_ip":/opt/chrono-scraper/
    
    # Update application
    ssh -p 2222 -o StrictHostKeyChecking=no ubuntu@"$server_ip" "
        cd /opt/chrono-scraper
        
        # Pull latest images and rebuild
        docker-compose -f infrastructure/docker-compose.production.yml pull
        docker-compose -f infrastructure/docker-compose.production.yml up -d --build
        
        # Clean up old images
        docker image prune -f
    "
    
    # Test application health
    sleep 30
    test_application_health "$server_ip"
    
    log_success "Application update completed!"
}

# Display deployment status
show_status() {
    log_info "Checking deployment status..."
    
    # Check if Terraform state exists
    if [[ ! -f "${TERRAFORM_DIR}/terraform.tfstate" ]]; then
        log_warning "No Terraform state found. Infrastructure not deployed."
        return 1
    fi
    
    local server_ip
    server_ip=$(get_server_ip)
    
    if [[ -z "$server_ip" ]]; then
        log_error "Could not determine server IP from Terraform state."
        return 1
    fi
    
    echo
    log_info "Infrastructure Status:"
    echo "===================="
    
    # Display Terraform outputs
    cd "${TERRAFORM_DIR}"
    if [[ -f "terraform-outputs.json" ]]; then
        echo "Server IP: $(jq -r '.server_info.value.ipv4_address' terraform-outputs.json)"
        echo "Load Balancer IP: $(jq -r '.load_balancer_info.value.ipv4' terraform-outputs.json)"
        echo "Monthly Cost: $(jq -r '.monthly_cost_estimate.value.total_estimated' terraform-outputs.json) EUR"
        echo "Budget Remaining: $(jq -r '.monthly_cost_estimate.value.budget_remaining' terraform-outputs.json) EUR"
    fi
    
    echo
    log_info "Application Status:"
    echo "=================="
    
    # Test SSH connection
    if ssh -p 2222 -o ConnectTimeout=5 -o StrictHostKeyChecking=no ubuntu@"$server_ip" "exit" 2>/dev/null; then
        log_success "SSH connection: OK"
        
        # Check application health
        if test_application_health "$server_ip" > /dev/null 2>&1; then
            log_success "Application health: OK"
        else
            log_error "Application health: FAILED"
        fi
        
        # Check container status
        echo
        log_info "Container Status:"
        ssh -p 2222 -o StrictHostKeyChecking=no ubuntu@"$server_ip" "
            cd /opt/chrono-scraper 2>/dev/null && docker-compose -f infrastructure/docker-compose.production.yml ps || echo 'Application not deployed'
        "
        
        # Check system resources
        echo
        log_info "System Resources:"
        ssh -p 2222 -o StrictHostKeyChecking=no ubuntu@"$server_ip" "
            echo 'CPU and Memory:'
            free -h
            echo
            echo 'Disk Usage:'
            df -h /mnt/data
            echo
            echo 'Container Resources:'
            docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' 2>/dev/null || echo 'Docker not running'
        "
    else
        log_error "SSH connection: FAILED"
    fi
}

# Backup data
backup_data() {
    log_info "Creating backup of application data..."
    
    local server_ip
    server_ip=$(get_server_ip)
    
    if [[ -z "$server_ip" ]]; then
        log_error "Could not determine server IP."
        exit 1
    fi
    
    # Run backup script on server
    ssh -p 2222 -o StrictHostKeyChecking=no ubuntu@"$server_ip" "
        /home/ubuntu/backup-script.sh
        echo 'Latest backups:'
        ls -la /mnt/data/backups/ | tail -5
    "
    
    # Optionally download backups locally
    echo
    log_info "Download backups to local machine? (y/N)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        local backup_dir="${PROJECT_ROOT}/backups/$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$backup_dir"
        
        log_info "Downloading backups to: $backup_dir"
        scp -P 2222 -o StrictHostKeyChecking=no ubuntu@"$server_ip":/mnt/data/backups/* "$backup_dir/"
        
        log_success "Backups downloaded successfully!"
    fi
}

# Helper functions
get_server_ip() {
    if [[ -f "${TERRAFORM_DIR}/terraform-outputs.json" ]]; then
        jq -r '.server_info.value.ipv4_address' "${TERRAFORM_DIR}/terraform-outputs.json"
    else
        cd "${TERRAFORM_DIR}"
        terraform output -json server_info 2>/dev/null | jq -r '.ipv4_address' || echo ""
    fi
}

test_ssh_connection() {
    local server_ip
    server_ip=$(get_server_ip)
    
    if [[ -z "$server_ip" ]]; then
        log_error "No server IP available for SSH test."
        return 1
    fi
    
    log_info "Testing SSH connection to $server_ip:2222..."
    
    local retries=5
    local count=0
    
    while [[ $count -lt $retries ]]; do
        if ssh -p 2222 -o ConnectTimeout=10 -o StrictHostKeyChecking=no ubuntu@"$server_ip" "echo 'SSH connection successful'" 2>/dev/null; then
            log_success "SSH connection established"
            return 0
        fi
        
        ((count++))
        log_info "SSH attempt $count/$retries failed. Retrying in 10 seconds..."
        sleep 10
    done
    
    log_error "SSH connection failed after $retries attempts"
    return 1
}

test_application_health() {
    local server_ip="$1"
    local health_url="http://$server_ip/api/v1/health"
    
    log_info "Testing application health at $health_url..."
    
    local retries=5
    local count=0
    
    while [[ $count -lt $retries ]]; do
        if curl -f -s -m 10 "$health_url" > /dev/null 2>&1; then
            log_success "Application health check passed"
            return 0
        fi
        
        ((count++))
        log_info "Health check $count/$retries failed. Retrying in 15 seconds..."
        sleep 15
    done
    
    log_error "Application health check failed after $retries attempts"
    return 1
}

setup_ssl_certificates() {
    local server_ip="$1"
    
    log_info "Setting up SSL certificates..."
    
    # Get domain from Terraform outputs
    local domain
    if [[ -f "${TERRAFORM_DIR}/terraform-outputs.json" ]]; then
        domain=$(jq -r '.application_urls.value.main_app' "${TERRAFORM_DIR}/terraform-outputs.json" | sed 's|https://||')
    else
        log_warning "Could not determine domain from Terraform outputs. Using chronoscraper.com"
        domain="chronoscraper.com"
    fi
    
    ssh -p 2222 -o StrictHostKeyChecking=no ubuntu@"$server_ip" "
        # Install certbot nginx plugin if not present
        sudo apt-get update -qq
        sudo apt-get install -y python3-certbot-nginx
        
        # Generate certificates
        sudo certbot --nginx --non-interactive --agree-tos --email admin@$domain \
            -d $domain -d www.$domain -d api.$domain \
            --redirect --hsts --staple-ocsp
        
        # Setup auto-renewal
        sudo systemctl enable certbot.timer
        sudo systemctl start certbot.timer
    " || log_warning "SSL setup failed. You may need to configure certificates manually."
}

display_connection_info() {
    echo
    log_success "Infrastructure deployed successfully!"
    echo "======================================"
    
    if [[ -f "${TERRAFORM_DIR}/terraform-outputs.json" ]]; then
        echo "SSH Command: $(jq -r '.ssh_connection_command.value' "${TERRAFORM_DIR}/terraform-outputs.json")"
        echo "Server IP: $(jq -r '.server_info.value.ipv4_address' "${TERRAFORM_DIR}/terraform-outputs.json")"
        echo "Load Balancer IP: $(jq -r '.load_balancer_info.value.ipv4' "${TERRAFORM_DIR}/terraform-outputs.json")"
        echo
        echo "Monthly Cost Estimate: $(jq -r '.monthly_cost_estimate.value.total_estimated' "${TERRAFORM_DIR}/terraform-outputs.json") EUR"
        echo "Budget Remaining: $(jq -r '.monthly_cost_estimate.value.budget_remaining' "${TERRAFORM_DIR}/terraform-outputs.json") EUR"
    fi
    
    echo
    echo "Next steps:"
    echo "1. Wait for server initialization (cloud-init takes ~3-5 minutes)"
    echo "2. Run: $0 deploy"
    echo "3. Configure DNS to point to the Load Balancer IP"
}

display_application_info() {
    echo
    log_success "Application deployed successfully!"
    echo "====================================="
    
    if [[ -f "${TERRAFORM_DIR}/terraform-outputs.json" ]]; then
        echo "Application URL: $(jq -r '.application_urls.value.main_app' "${TERRAFORM_DIR}/terraform-outputs.json")"
        echo "API Endpoint: $(jq -r '.application_urls.value.api_endpoint' "${TERRAFORM_DIR}/terraform-outputs.json")"
        echo "Health Check: $(jq -r '.application_urls.value.health_check' "${TERRAFORM_DIR}/terraform-outputs.json")"
    fi
    
    echo
    echo "Management URLs:"
    echo "- Traefik Dashboard: https://traefik.chronoscraper.com"
    echo "- Flower (Celery): https://flower.chronoscraper.com"
    echo
    echo "Monitoring:"
    echo "- System logs: tail -f /mnt/data/logs/system-monitoring.log"
    echo "- Application logs: docker-compose logs -f"
    echo "- Backup status: tail -f /mnt/data/logs/backup.log"
}

# Main script logic
main() {
    local command="${1:-help}"
    
    case "$command" in
        "init")
            check_prerequisites
            init_infrastructure
            ;;
        "deploy")
            check_prerequisites
            deploy_application
            ;;
        "update")
            check_prerequisites
            update_application
            ;;
        "status")
            show_status
            ;;
        "backup")
            backup_data
            ;;
        "help"|*)
            echo "Chrono Scraper v2 Production Deployment Script"
            echo "=============================================="
            echo
            echo "Usage: $0 [command]"
            echo
            echo "Commands:"
            echo "  init     - Initialize and deploy Hetzner Cloud infrastructure"
            echo "  deploy   - Deploy application to existing infrastructure"
            echo "  update   - Update application with latest changes"
            echo "  status   - Show deployment status and health"
            echo "  backup   - Create and optionally download backups"
            echo "  help     - Show this help message"
            echo
            echo "Prerequisites:"
            echo "- Terraform installed and configured"
            echo "- terraform.tfvars configured with your credentials"
            echo "- SSH key configured for server access"
            echo
            echo "Example workflow:"
            echo "1. Configure terraform.tfvars with your Hetzner and Cloudflare credentials"
            echo "2. Run: $0 init    # Deploy infrastructure"
            echo "3. Run: $0 deploy  # Deploy application"
            echo "4. Run: $0 status  # Check deployment status"
            ;;
    esac
}

# Run main function
main "$@"