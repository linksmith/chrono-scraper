#!/bin/bash
# Cost Monitoring and Scaling Decision Framework
# For Chrono Scraper v2 on Hetzner Cloud

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TERRAFORM_DIR="${PROJECT_ROOT}/infrastructure/terraform"
MONITORING_LOG="/tmp/cost-monitoring.log"

# Cost thresholds (EUR)
BUDGET_LIMIT=50
WARNING_THRESHOLD=40
CRITICAL_THRESHOLD=45

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1" >> "$MONITORING_LOG"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SUCCESS] $1" >> "$MONITORING_LOG"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WARNING] $1" >> "$MONITORING_LOG"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" >> "$MONITORING_LOG"
}

log_critical() {
    echo -e "${RED}[CRITICAL]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [CRITICAL] $1" >> "$MONITORING_LOG"
}

# Get current infrastructure costs
get_current_costs() {
    local costs_json
    
    if [[ -f "${TERRAFORM_DIR}/terraform-outputs.json" ]]; then
        costs_json=$(cat "${TERRAFORM_DIR}/terraform-outputs.json")
    else
        cd "${TERRAFORM_DIR}"
        costs_json=$(terraform output -json monthly_cost_estimate 2>/dev/null || echo "{}")
    fi
    
    echo "$costs_json"
}

# Calculate total monthly cost
calculate_total_cost() {
    local costs_json="$1"
    
    if [[ "$costs_json" == "{}" ]]; then
        echo "0.00"
        return
    fi
    
    local total
    total=$(echo "$costs_json" | jq -r '.value.total_estimated // "0.00"' 2>/dev/null || echo "0.00")
    echo "$total"
}

# Get cost breakdown
show_cost_breakdown() {
    log_info "Current Infrastructure Cost Breakdown"
    echo "====================================="
    
    local costs_json
    costs_json=$(get_current_costs)
    
    if [[ "$costs_json" == "{}" ]]; then
        log_error "No cost information available. Ensure infrastructure is deployed."
        return 1
    fi
    
    echo
    echo "Monthly Costs (EUR, excluding VAT):"
    echo "-----------------------------------"
    
    local server_cost volume_cost lb_cost floating_ip_cost backup_cost
    server_cost=$(echo "$costs_json" | jq -r '.value.server.cost // "0.00"')
    volume_cost=$(echo "$costs_json" | jq -r '.value.volume.cost // "0.00"')
    lb_cost=$(echo "$costs_json" | jq -r '.value.load_balancer.cost // "0.00"')
    floating_ip_cost=$(echo "$costs_json" | jq -r '.value.floating_ip // "0.00"')
    backup_cost=$(echo "$costs_json" | jq -r '.value.backup // "0.00"')
    
    printf "%-20s €%s\n" "Server:" "$server_cost"
    printf "%-20s €%s\n" "Storage Volume:" "$volume_cost"
    printf "%-20s €%s\n" "Load Balancer:" "$lb_cost"
    printf "%-20s €%s\n" "Floating IP:" "$floating_ip_cost"
    printf "%-20s €%s\n" "Backups:" "$backup_cost"
    printf "%-20s €%s\n" "Snapshots (est):" "2.00"
    echo "-----------------------------------"
    
    local total_cost
    total_cost=$(calculate_total_cost "$costs_json")
    printf "%-20s €%s\n" "TOTAL:" "$total_cost"
    
    local remaining_budget
    remaining_budget=$(echo "$costs_json" | jq -r '.value.budget_remaining // "0.00"')
    printf "%-20s €%s\n" "Budget Remaining:" "$remaining_budget"
    
    echo
    
    # Cost alerts
    check_cost_alerts "$total_cost"
}

# Check cost alerts
check_cost_alerts() {
    local total_cost="$1"
    local cost_num
    cost_num=$(echo "$total_cost" | sed 's/€//' | tr -d ' ')
    
    if (( $(echo "$cost_num >= $CRITICAL_THRESHOLD" | bc -l) )); then
        log_critical "Cost alert: €$cost_num exceeds critical threshold of €$CRITICAL_THRESHOLD"
        echo "⚠️  IMMEDIATE ACTION REQUIRED: Review and optimize resources"
    elif (( $(echo "$cost_num >= $WARNING_THRESHOLD" | bc -l) )); then
        log_warning "Cost alert: €$cost_num exceeds warning threshold of €$WARNING_THRESHOLD"
        echo "💡 Consider optimizing resources or reviewing usage patterns"
    else
        log_success "Costs within acceptable limits: €$cost_num (Budget: €$BUDGET_LIMIT)"
    fi
}

# Get server performance metrics
get_performance_metrics() {
    local server_ip
    
    # Get server IP from Terraform outputs
    if [[ -f "${TERRAFORM_DIR}/terraform-outputs.json" ]]; then
        server_ip=$(jq -r '.server_info.value.ipv4_address' "${TERRAFORM_DIR}/terraform-outputs.json")
    else
        log_error "Cannot determine server IP. Ensure infrastructure is deployed."
        return 1
    fi
    
    if [[ -z "$server_ip" || "$server_ip" == "null" ]]; then
        log_error "Invalid server IP. Check Terraform outputs."
        return 1
    fi
    
    log_info "Collecting performance metrics from $server_ip..."
    
    # Test SSH connection
    if ! ssh -p 2222 -o ConnectTimeout=10 -o StrictHostKeyChecking=no ubuntu@"$server_ip" "exit" 2>/dev/null; then
        log_error "Cannot connect to server via SSH"
        return 1
    fi
    
    # Collect metrics
    ssh -p 2222 -o StrictHostKeyChecking=no ubuntu@"$server_ip" '
        echo "=== SYSTEM METRICS ==="
        
        # CPU usage
        echo "CPU Usage:"
        top -bn1 | grep "Cpu(s)" | awk "{print \"  Current: \" \$2 \" \$4}"
        
        # Memory usage
        echo "Memory Usage:"
        free -h | grep -E "^Mem:" | awk "{printf \"  Used: %s/%s (%.1f%%)\n\", \$3, \$2, (\$3/\$2)*100}"
        
        # Disk usage
        echo "Disk Usage:"
        df -h / | tail -1 | awk "{printf \"  Root: %s/%s (%s used)\n\", \$3, \$2, \$5}"
        df -h /mnt/data 2>/dev/null | tail -1 | awk "{printf \"  Data: %s/%s (%s used)\n\", \$3, \$2, \$5}" || echo "  Data volume not mounted"
        
        # Load average
        echo "Load Average:"
        uptime | awk -F"load average:" "{print \"  \" \$2}"
        
        echo
        echo "=== DOCKER METRICS ==="
        
        # Container resource usage
        if command -v docker >/dev/null 2>&1; then
            echo "Container Resource Usage:"
            docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null || echo "  Docker not running or no containers"
            
            # Container status
            echo
            echo "Container Status:"
            if cd /opt/chrono-scraper 2>/dev/null; then
                docker-compose -f infrastructure/docker-compose.production.yml ps 2>/dev/null || echo "  Application not deployed"
            else
                echo "  Application directory not found"
            fi
        else
            echo "  Docker not installed"
        fi
        
        echo
        echo "=== APPLICATION METRICS ==="
        
        # Check application health
        if curl -f -s -m 5 http://localhost/api/v1/health >/dev/null 2>&1; then
            echo "Application Health: OK"
        else
            echo "Application Health: FAILED"
        fi
        
        # Check service endpoints
        services=("postgres:5432" "redis:6379" "meilisearch:7700" "firecrawl-api:3002")
        echo "Service Connectivity:"
        for service in "${services[@]}"; do
            host=${service%:*}
            port=${service#*:}
            if timeout 3 bash -c "</dev/tcp/$host/$port" >/dev/null 2>&1; then
                echo "  $service: OK"
            else
                echo "  $service: FAILED"
            fi
        done
    '
}

# Scaling decision framework
analyze_scaling_needs() {
    log_info "Analyzing scaling requirements..."
    
    local server_ip
    
    # Get server IP
    if [[ -f "${TERRAFORM_DIR}/terraform-outputs.json" ]]; then
        server_ip=$(jq -r '.server_info.value.ipv4_address' "${TERRAFORM_DIR}/terraform-outputs.json")
    else
        log_error "Cannot determine server IP for scaling analysis"
        return 1
    fi
    
    # Get current metrics
    local metrics_output
    metrics_output=$(ssh -p 2222 -o StrictHostKeyChecking=no ubuntu@"$server_ip" '
        # Get CPU usage (remove % symbol)
        cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk "{print \$2}" | sed "s/%us,//")
        
        # Get memory usage percentage
        mem_usage=$(free | grep Mem | awk "{printf \"%.1f\", (\$3/\$2) * 100.0}")
        
        # Get disk usage percentage (remove % symbol)
        disk_usage=$(df -h / | tail -1 | awk "{print \$5}" | sed "s/%//")
        
        # Get load average (1 minute)
        load_avg=$(uptime | awk -F"load average:" "{print \$2}" | awk -F"," "{print \$1}" | tr -d " ")
        
        # Count running containers
        container_count=$(docker ps -q | wc -l 2>/dev/null || echo "0")
        
        # Check if application is responding
        if curl -f -s -m 5 http://localhost/api/v1/health >/dev/null 2>&1; then
            app_health="healthy"
        else
            app_health="unhealthy"
        fi
        
        echo "$cpu_usage,$mem_usage,$disk_usage,$load_avg,$container_count,$app_health"
    ')
    
    # Parse metrics
    IFS=',' read -r cpu_usage mem_usage disk_usage load_avg container_count app_health <<< "$metrics_output"
    
    echo
    log_info "Current Performance Metrics:"
    echo "==========================="
    printf "%-20s %s%%\n" "CPU Usage:" "$cpu_usage"
    printf "%-20s %s%%\n" "Memory Usage:" "$mem_usage"
    printf "%-20s %s%%\n" "Disk Usage:" "$disk_usage"
    printf "%-20s %s\n" "Load Average:" "$load_avg"
    printf "%-20s %s\n" "Containers:" "$container_count"
    printf "%-20s %s\n" "App Health:" "$app_health"
    
    echo
    log_info "Scaling Recommendations:"
    echo "======================="
    
    # Scaling decision logic
    local scale_needed=false
    local recommendations=()
    
    # CPU scaling triggers
    if (( $(echo "$cpu_usage > 80" | bc -l) )); then
        recommendations+=("🔴 HIGH CPU: $cpu_usage% > 80% - Consider upgrading to CX42 (8 vCPU)")
        scale_needed=true
    elif (( $(echo "$cpu_usage > 70" | bc -l) )); then
        recommendations+=("🟡 MODERATE CPU: $cpu_usage% > 70% - Monitor closely")
    fi
    
    # Memory scaling triggers
    if (( $(echo "$mem_usage > 85" | bc -l) )); then
        recommendations+=("🔴 HIGH MEMORY: $mem_usage% > 85% - Upgrade to CX42 (16 GB RAM)")
        scale_needed=true
    elif (( $(echo "$mem_usage > 75" | bc -l) )); then
        recommendations+=("🟡 MODERATE MEMORY: $mem_usage% > 75% - Consider optimization")
    fi
    
    # Disk scaling triggers
    if (( $(echo "$disk_usage > 90" | bc -l) )); then
        recommendations+=("🔴 DISK FULL: $disk_usage% > 90% - Increase volume size immediately")
        scale_needed=true
    elif (( $(echo "$disk_usage > 80" | bc -l) )); then
        recommendations+=("🟡 DISK WARNING: $disk_usage% > 80% - Plan volume expansion")
    fi
    
    # Load average check (assuming 4 vCPU system)
    if (( $(echo "$load_avg > 4.0" | bc -l) )); then
        recommendations+=("🔴 HIGH LOAD: Load average $load_avg > 4.0 - System overloaded")
        scale_needed=true
    elif (( $(echo "$load_avg > 3.0" | bc -l) )); then
        recommendations+=("🟡 MODERATE LOAD: Load average $load_avg > 3.0 - Monitor performance")
    fi
    
    # Application health check
    if [[ "$app_health" != "healthy" ]]; then
        recommendations+=("🔴 APP UNHEALTHY: Application not responding - Investigate immediately")
        scale_needed=true
    fi
    
    # Display recommendations
    if [[ ${#recommendations[@]} -eq 0 ]]; then
        log_success "✅ System operating within normal parameters"
        echo "   Current configuration is sufficient for current load"
    else
        for rec in "${recommendations[@]}"; do
            echo "   $rec"
        done
    fi
    
    echo
    
    # Scaling options and costs
    if [[ "$scale_needed" == "true" ]]; then
        show_scaling_options
    else
        log_info "💡 Next scaling trigger points:"
        echo "   - CPU usage >80% consistently"
        echo "   - Memory usage >85%"
        echo "   - Disk usage >90%"
        echo "   - Load average >4.0"
        echo "   - Response times >1s average"
    fi
}

# Show scaling options with costs
show_scaling_options() {
    echo
    log_info "Available Scaling Options:"
    echo "========================="
    
    echo
    echo "📈 VERTICAL SCALING (Single Server):"
    echo "------------------------------------"
    echo "Current: CX32 (4 vCPU, 8 GB RAM) - €6.80/month"
    echo
    echo "Upgrade Options:"
    echo "• CX42 (8 vCPU, 16 GB RAM) - €16.40/month (+€9.60)"
    echo "  - Doubles CPU and RAM capacity"
    echo "  - Total cost: ~€35/month (€15 under budget)"
    echo "  - Best for: CPU/memory bottlenecks"
    echo
    echo "• CX52 (16 vCPU, 32 GB RAM) - €32.40/month (+€25.60)"
    echo "  - 4x CPU, 4x RAM capacity"
    echo "  - Total cost: ~€48/month (€2 under budget)"
    echo "  - Best for: Heavy workloads, many concurrent users"
    echo
    
    echo "📊 HORIZONTAL SCALING (Multi-Server):"
    echo "-------------------------------------"
    echo "Split services across multiple servers:"
    echo
    echo "Option 1: Database Separation (~€50/month total)"
    echo "• Web Server (CX42): Frontend + Backend - €16.40"
    echo "• Database Server (CX32): PostgreSQL + Redis - €6.80"
    echo "• Worker Server (CX32): Celery + Firecrawl - €6.80"
    echo "• Infrastructure: Load balancers, volumes, etc. - €20"
    echo "  - Better fault tolerance"
    echo "  - Independent scaling of components"
    echo
    echo "Option 2: ARM-based Cost Optimization (~€45/month total)"
    echo "• Main Server (CAX41): 16 vCPU ARM, 32 GB RAM - €26.38"
    echo "• Worker Server (CAX21): 4 vCPU ARM, 8 GB RAM - €6.49"
    echo "• Infrastructure costs - €12"
    echo "  - Better price/performance ratio"
    echo "  - Energy efficient"
    echo
    
    echo "🔧 OPTIMIZATION BEFORE SCALING:"
    echo "-------------------------------"
    echo "Consider these optimizations first:"
    echo "• Container resource limits tuning"
    echo "• Database query optimization"
    echo "• Redis cache optimization"
    echo "• Static asset CDN (Cloudflare)"
    echo "• Connection pooling optimization"
    echo "• Background task queue optimization"
    echo
    
    echo "💰 COST IMPACT ANALYSIS:"
    echo "------------------------"
    local current_cost
    if [[ -f "${TERRAFORM_DIR}/terraform-outputs.json" ]]; then
        current_cost=$(jq -r '.monthly_cost_estimate.value.total_estimated' "${TERRAFORM_DIR}/terraform-outputs.json")
    else
        current_cost="25.85"
    fi
    
    echo "Current monthly cost: €$current_cost"
    echo "Budget limit: €$BUDGET_LIMIT"
    echo "Available budget: €$(echo "$BUDGET_LIMIT - $current_cost" | bc)"
    echo
    
    echo "🎯 RECOMMENDED NEXT STEPS:"
    echo "-------------------------"
    echo "1. Monitor metrics for 24-48 hours to confirm trends"
    echo "2. Implement container resource optimizations"
    echo "3. If issues persist, upgrade to CX42 for €9.60/month more"
    echo "4. Consider horizontal scaling when approaching €45/month total"
    echo "5. Plan multi-region deployment at €100+/month budget"
}

# Generate scaling report
generate_scaling_report() {
    local report_file="/tmp/chrono-scraper-scaling-report-$(date +%Y%m%d_%H%M%S).txt"
    
    log_info "Generating comprehensive scaling report..."
    
    {
        echo "Chrono Scraper v2 - Scaling Analysis Report"
        echo "==========================================="
        echo "Generated: $(date)"
        echo
        
        echo "COST ANALYSIS:"
        echo "-------------"
        show_cost_breakdown
        
        echo
        echo "PERFORMANCE METRICS:"
        echo "-------------------"
        get_performance_metrics
        
        echo
        echo "SCALING RECOMMENDATIONS:"
        echo "-----------------------"
        analyze_scaling_needs
        
    } | tee "$report_file"
    
    log_success "Report saved to: $report_file"
    
    # Optionally email report (if configured)
    if [[ -n "${ALERT_EMAIL:-}" ]]; then
        log_info "Sending report to $ALERT_EMAIL..."
        mail -s "Chrono Scraper Scaling Report - $(date +%Y-%m-%d)" "$ALERT_EMAIL" < "$report_file" || log_warning "Failed to send email report"
    fi
}

# Set up monitoring alerts
setup_monitoring_alerts() {
    log_info "Setting up automated monitoring alerts..."
    
    local cron_file="/tmp/chrono-scraper-monitoring-cron"
    
    cat > "$cron_file" << 'EOF'
# Chrono Scraper v2 Cost and Performance Monitoring
# Run cost check every 6 hours
0 */6 * * * /path/to/cost-monitor.sh check-costs >> /var/log/chrono-scraper-monitoring.log 2>&1

# Run performance check every hour
0 * * * * /path/to/cost-monitor.sh check-performance >> /var/log/chrono-scraper-monitoring.log 2>&1

# Generate daily scaling report
0 8 * * * /path/to/cost-monitor.sh scaling-report >> /var/log/chrono-scraper-monitoring.log 2>&1

# Weekly cost optimization check
0 9 * * 1 /path/to/cost-monitor.sh optimization-check >> /var/log/chrono-scraper-monitoring.log 2>&1
EOF

    echo "Cron configuration saved to: $cron_file"
    echo "To install, run: crontab $cron_file"
    
    log_success "Monitoring alerts configured"
}

# Main script logic
main() {
    local command="${1:-help}"
    
    case "$command" in
        "costs"|"cost-breakdown")
            show_cost_breakdown
            ;;
        "metrics"|"performance")
            get_performance_metrics
            ;;
        "scaling"|"scaling-analysis")
            analyze_scaling_needs
            ;;
        "report"|"scaling-report")
            generate_scaling_report
            ;;
        "check-costs")
            local costs_json
            costs_json=$(get_current_costs)
            local total_cost
            total_cost=$(calculate_total_cost "$costs_json")
            check_cost_alerts "$total_cost"
            ;;
        "check-performance")
            # Quick performance check for automated monitoring
            get_performance_metrics | grep -E "(CPU|Memory|Disk|Load|Health):" || true
            ;;
        "optimization-check")
            log_info "Running optimization check..."
            show_cost_breakdown
            analyze_scaling_needs
            ;;
        "setup-alerts")
            setup_monitoring_alerts
            ;;
        "help"|*)
            echo "Chrono Scraper v2 - Cost Monitoring and Scaling Framework"
            echo "========================================================="
            echo
            echo "Usage: $0 [command]"
            echo
            echo "Commands:"
            echo "  costs              - Show detailed cost breakdown"
            echo "  metrics           - Show current performance metrics"
            echo "  scaling           - Analyze scaling needs and recommendations"
            echo "  report            - Generate comprehensive scaling report"
            echo "  check-costs       - Quick cost check (for automated monitoring)"
            echo "  check-performance - Quick performance check (for automated monitoring)"
            echo "  optimization-check - Weekly optimization analysis"
            echo "  setup-alerts      - Configure automated monitoring alerts"
            echo "  help              - Show this help message"
            echo
            echo "Environment Variables:"
            echo "  BUDGET_LIMIT      - Monthly budget limit in EUR (default: 50)"
            echo "  WARNING_THRESHOLD - Warning threshold in EUR (default: 40)"
            echo "  CRITICAL_THRESHOLD- Critical threshold in EUR (default: 45)"
            echo "  ALERT_EMAIL       - Email for reports (optional)"
            echo
            echo "Examples:"
            echo "  $0 costs          # Show current costs"
            echo "  $0 scaling        # Analyze if scaling is needed"
            echo "  $0 report         # Generate full report"
            echo
            echo "Scaling Triggers:"
            echo "• CPU usage >80% consistently"
            echo "• Memory usage >85%"
            echo "• Disk usage >90%"
            echo "• Load average >4.0 (for CX32)"
            echo "• Response times >1s average"
            echo "• Queue backlog >100 jobs"
            ;;
    esac
}

# Run main function
main "$@"