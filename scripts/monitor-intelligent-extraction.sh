#!/bin/bash

# Intelligent Content Extraction Performance Monitor
# Monitors resource usage, extraction performance, and system health
# Optimized for post-Firecrawl removal intelligent extraction system

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Configuration
CONTINUOUS=${1:-false}
REFRESH_INTERVAL=${2:-5}
LOG_FILE="/tmp/intelligent-extraction-monitor.log"

# Helper functions
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
    echo -e "$1"
}

get_container_stats() {
    local container=$1
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}" | grep "$container" || echo "Container not found"
}

get_container_memory_mb() {
    local container=$1
    docker stats --no-stream --format "{{.MemUsage}}" "$container" 2>/dev/null | sed 's/\/.*//' | sed 's/MiB//' | sed 's/GiB/*1024/' | bc 2>/dev/null || echo "0"
}

get_container_cpu() {
    local container=$1
    docker stats --no-stream --format "{{.CPUPerc}}" "$container" 2>/dev/null | sed 's/%//' || echo "0"
}

check_service_health() {
    local service=$1
    local url=$2
    local timeout=${3:-5}
    
    if curl -s --max-time "$timeout" "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${RED}❌${NC}"
    fi
}

get_extraction_metrics() {
    # Get metrics from backend API
    local backend_response=$(curl -s --max-time 3 "http://localhost:8000/api/v1/monitoring/extraction-metrics" 2>/dev/null || echo '{}')
    
    # Parse JSON response (basic parsing)
    local active_extractions=$(echo "$backend_response" | grep -o '"active_extractions":[0-9]*' | cut -d':' -f2 || echo "0")
    local completed_extractions=$(echo "$backend_response" | grep -o '"completed_extractions":[0-9]*' | cut -d':' -f2 || echo "0")
    local failed_extractions=$(echo "$backend_response" | grep -o '"failed_extractions":[0-9]*' | cut -d':' -f2 || echo "0")
    local avg_extraction_time=$(echo "$backend_response" | grep -o '"avg_extraction_time":[0-9.]*' | cut -d':' -f2 || echo "0")
    local extraction_success_rate=$(echo "$backend_response" | grep -o '"extraction_success_rate":[0-9.]*' | cut -d':' -f2 || echo "0")
    
    echo "$active_extractions,$completed_extractions,$failed_extractions,$avg_extraction_time,$extraction_success_rate"
}

get_celery_metrics() {
    # Get Celery metrics
    local celery_inspect=$(docker compose exec -T celery_worker celery -A app.tasks.celery_app inspect active 2>/dev/null || echo '{}')
    local active_tasks=$(echo "$celery_inspect" | grep -c '"name":' || echo "0")
    
    local queue_length=$(docker compose exec -T redis redis-cli llen celery 2>/dev/null || echo "0")
    
    echo "$active_tasks,$queue_length"
}

get_database_metrics() {
    # Database size and connection count
    local db_size=$(docker compose exec -T postgres psql -U chrono_scraper -d chrono_scraper -t -c "SELECT pg_size_pretty(pg_database_size('chrono_scraper'));" 2>/dev/null | tr -d '[:space:]' || echo "0")
    local db_connections=$(docker compose exec -T postgres psql -U chrono_scraper -d chrono_scraper -t -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null | tr -d '[:space:]' || echo "0")
    
    echo "$db_size,$db_connections"
}

get_redis_metrics() {
    # Redis memory usage and key count
    local redis_memory=$(docker compose exec -T redis redis-cli info memory 2>/dev/null | grep "used_memory_human:" | cut -d':' -f2 | tr -d '\r' || echo "0")
    local redis_keys=$(docker compose exec -T redis redis-cli dbsize 2>/dev/null || echo "0")
    
    echo "$redis_memory,$redis_keys"
}

display_header() {
    clear
    echo -e "${WHITE}=================================================================${NC}"
    echo -e "${WHITE}🧠 INTELLIGENT CONTENT EXTRACTION PERFORMANCE MONITOR${NC}"
    echo -e "${WHITE}=================================================================${NC}"
    echo -e "${CYAN}Post-Firecrawl Optimization Monitor - $(date)${NC}"
    echo -e "${WHITE}=================================================================${NC}"
    echo ""
}

display_system_overview() {
    echo -e "${WHITE}📊 SYSTEM RESOURCE OVERVIEW${NC}"
    echo -e "${WHITE}─────────────────────────────${NC}"
    
    # System resources
    local total_memory=$(free -h | grep Mem | awk '{print $2}')
    local used_memory=$(free -h | grep Mem | awk '{print $3}')
    local memory_percent=$(free | grep Mem | awk '{printf "%.1f", ($3/$2)*100}')
    
    local cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
    local load_avg=$(uptime | awk -F'load average:' '{print $2}' | sed 's/^[ \t]*//')
    
    echo -e "${BLUE}Memory Usage:${NC} $used_memory / $total_memory (${memory_percent}%)"
    echo -e "${BLUE}CPU Usage:${NC} ${cpu_usage}%"
    echo -e "${BLUE}Load Average:${NC} $load_avg"
    echo ""
}

display_container_resources() {
    echo -e "${WHITE}🐳 CONTAINER RESOURCE USAGE${NC}"
    echo -e "${WHITE}─────────────────────────────${NC}"
    
    # Key containers for intelligent extraction
    local containers=("chrono_celery_worker" "chrono_backend" "chrono_postgres" "chrono_meilisearch" "chrono_redis")
    local container_names=("Celery Worker" "Backend API" "PostgreSQL" "Meilisearch" "Redis Cache")
    
    printf "%-15s %-10s %-15s %-10s %-15s %-15s\n" "Service" "CPU" "Memory" "Mem%" "Network I/O" "Block I/O"
    printf "%-15s %-10s %-15s %-10s %-15s %-15s\n" "───────" "───" "──────" "────" "──────────" "─────────"
    
    for i in "${!containers[@]}"; do
        local container="${containers[i]}"
        local name="${container_names[i]}"
        local stats=$(get_container_stats "$container")
        
        if [[ "$stats" != "Container not found" ]]; then
            echo "$stats" | tail -n +2 | while read line; do
                local cpu=$(echo "$line" | awk '{print $2}')
                local memory=$(echo "$line" | awk '{print $3}')
                local mem_percent=$(echo "$line" | awk '{print $4}')
                local net_io=$(echo "$line" | awk '{print $5}')
                local block_io=$(echo "$line" | awk '{print $6}')
                
                # Color coding based on usage
                local cpu_color=$GREEN
                [[ $(echo "$cpu" | sed 's/%//') > 80 ]] && cpu_color=$RED
                [[ $(echo "$cpu" | sed 's/%//') > 60 ]] && cpu_color=$YELLOW
                
                local mem_color=$GREEN
                [[ $(echo "$mem_percent" | sed 's/%//') > 80 ]] && mem_color=$RED
                [[ $(echo "$mem_percent" | sed 's/%//') > 60 ]] && mem_color=$YELLOW
                
                printf "%-15s ${cpu_color}%-10s${NC} %-15s ${mem_color}%-10s${NC} %-15s %-15s\n" \
                    "$name" "$cpu" "$memory" "$mem_percent" "$net_io" "$block_io"
            done
        else
            printf "%-15s ${RED}%-10s${NC} %-15s %-10s %-15s %-15s\n" "$name" "DOWN" "─" "─" "─" "─"
        fi
    done
    echo ""
}

display_service_health() {
    echo -e "${WHITE}🏥 SERVICE HEALTH STATUS${NC}"
    echo -e "${WHITE}─────────────────────────${NC}"
    
    local backend_health=$(check_service_health "Backend API" "http://localhost:8000/health")
    local frontend_health=$(check_service_health "Frontend" "http://localhost:5173")
    local meilisearch_health=$(check_service_health "Meilisearch" "http://localhost:7700/health")
    local flower_health=$(check_service_health "Flower" "http://localhost:5555")
    local mailpit_health=$(check_service_health "Mailpit" "http://localhost:8025")
    
    printf "%-20s %s\n" "Backend API" "$backend_health"
    printf "%-20s %s\n" "Frontend" "$frontend_health"
    printf "%-20s %s\n" "Meilisearch" "$meilisearch_health"
    printf "%-20s %s\n" "Flower Monitor" "$flower_health"
    printf "%-20s %s\n" "Mailpit" "$mailpit_health"
    echo ""
}

display_extraction_performance() {
    echo -e "${WHITE}🧠 INTELLIGENT EXTRACTION PERFORMANCE${NC}"
    echo -e "${WHITE}────────────────────────────────────────${NC}"
    
    local metrics=$(get_extraction_metrics)
    IFS=',' read -r active completed failed avg_time success_rate <<< "$metrics"
    
    # Color coding for performance metrics
    local active_color=$GREEN
    [[ $active -gt 20 ]] && active_color=$YELLOW
    [[ $active -gt 25 ]] && active_color=$RED
    
    local success_color=$GREEN
    [[ $(echo "$success_rate < 0.9" | bc -l) -eq 1 ]] && success_color=$YELLOW
    [[ $(echo "$success_rate < 0.8" | bc -l) -eq 1 ]] && success_color=$RED
    
    echo -e "${BLUE}Active Extractions:${NC} ${active_color}$active${NC}/25 max"
    echo -e "${BLUE}Completed Today:${NC} $completed"
    echo -e "${BLUE}Failed Today:${NC} $failed"
    echo -e "${BLUE}Avg Extraction Time:${NC} ${avg_time}s"
    echo -e "${BLUE}Success Rate:${NC} ${success_color}$(echo "scale=1; $success_rate * 100" | bc)%${NC}"
    echo ""
    
    # Archive.org rate limiting compliance
    local archive_requests_minute=$(docker compose exec -T redis redis-cli get "archive_requests_last_minute" 2>/dev/null || echo "0")
    local rate_limit_color=$GREEN
    [[ $archive_requests_minute -gt 12 ]] && rate_limit_color=$YELLOW
    [[ $archive_requests_minute -gt 15 ]] && rate_limit_color=$RED
    
    echo -e "${BLUE}Archive.org Requests/min:${NC} ${rate_limit_color}$archive_requests_minute${NC}/15 limit"
}

display_celery_performance() {
    echo -e "${WHITE}⚙️  CELERY WORKER PERFORMANCE${NC}"
    echo -e "${WHITE}──────────────────────────────${NC}"
    
    local celery_metrics=$(get_celery_metrics)
    IFS=',' read -r active_tasks queue_length <<< "$celery_metrics"
    
    local queue_color=$GREEN
    [[ $queue_length -gt 100 ]] && queue_color=$YELLOW
    [[ $queue_length -gt 200 ]] && queue_color=$RED
    
    echo -e "${BLUE}Active Tasks:${NC} $active_tasks"
    echo -e "${BLUE}Queue Length:${NC} ${queue_color}$queue_length${NC}"
    
    # Worker memory recycling status
    local worker_memory=$(get_container_memory_mb "chrono_celery_worker")
    local memory_color=$GREEN
    [[ $(echo "$worker_memory > 2500" | bc -l) -eq 1 ]] && memory_color=$YELLOW
    [[ $(echo "$worker_memory > 2800" | bc -l) -eq 1 ]] && memory_color=$RED
    
    echo -e "${BLUE}Worker Memory:${NC} ${memory_color}${worker_memory}MB${NC}/3000MB limit"
    echo ""
}

display_database_performance() {
    echo -e "${WHITE}🗄️  DATABASE & CACHE PERFORMANCE${NC}"
    echo -e "${WHITE}──────────────────────────────────${NC}"
    
    local db_metrics=$(get_database_metrics)
    IFS=',' read -r db_size db_connections <<< "$db_metrics"
    
    local redis_metrics=$(get_redis_metrics)
    IFS=',' read -r redis_memory redis_keys <<< "$redis_metrics"
    
    local conn_color=$GREEN
    [[ $db_connections -gt 100 ]] && conn_color=$YELLOW
    [[ $db_connections -gt 120 ]] && conn_color=$RED
    
    echo -e "${BLUE}Database Size:${NC} $db_size"
    echo -e "${BLUE}DB Connections:${NC} ${conn_color}$db_connections${NC}/150 max"
    echo -e "${BLUE}Redis Memory:${NC} $redis_memory"
    echo -e "${BLUE}Cached Keys:${NC} $redis_keys"
    echo ""
}

display_optimization_recommendations() {
    echo -e "${WHITE}💡 OPTIMIZATION RECOMMENDATIONS${NC}"
    echo -e "${WHITE}──────────────────────────────────${NC}"
    
    local recommendations=()
    
    # Check memory usage
    local celery_memory=$(get_container_memory_mb "chrono_celery_worker")
    if [[ $(echo "$celery_memory > 2800" | bc -l) -eq 1 ]]; then
        recommendations+=("${YELLOW}⚠️  Celery worker memory high - consider reducing concurrency${NC}")
    fi
    
    # Check CPU usage
    local celery_cpu=$(get_container_cpu "chrono_celery_worker" | sed 's/%//')
    if [[ $(echo "$celery_cpu > 85" | bc -l) -eq 1 ]]; then
        recommendations+=("${YELLOW}⚠️  Celery worker CPU high - consider scaling horizontally${NC}")
    fi
    
    # Check extraction queue
    local queue_length=$(docker compose exec -T redis redis-cli llen celery 2>/dev/null || echo "0")
    if [[ $queue_length -gt 150 ]]; then
        recommendations+=("${RED}🚨 High extraction queue - consider adding more workers${NC}")
    fi
    
    # Check Archive.org rate limiting
    local archive_requests=$(docker compose exec -T redis redis-cli get "archive_requests_last_minute" 2>/dev/null || echo "0")
    if [[ $archive_requests -gt 14 ]]; then
        recommendations+=("${RED}🚨 Archive.org rate limit near - throttle requests${NC}")
    fi
    
    if [[ ${#recommendations[@]} -eq 0 ]]; then
        echo -e "${GREEN}✅ System performance optimal - no recommendations${NC}"
    else
        for rec in "${recommendations[@]}"; do
            echo -e "$rec"
        done
    fi
    echo ""
}

display_footer() {
    echo -e "${WHITE}=================================================================${NC}"
    echo -e "${CYAN}Press Ctrl+C to stop monitoring | Refresh every ${REFRESH_INTERVAL}s${NC}"
    echo -e "${WHITE}=================================================================${NC}"
}

main_monitor() {
    # Initialize log file
    echo "Starting Intelligent Extraction Monitor - $(date)" > "$LOG_FILE"
    
    if [[ "$CONTINUOUS" == "true" ]]; then
        log "${GREEN}Starting continuous monitoring (refresh: ${REFRESH_INTERVAL}s)${NC}"
        
        while true; do
            display_header
            display_system_overview
            display_container_resources
            display_service_health
            display_extraction_performance
            display_celery_performance
            display_database_performance
            display_optimization_recommendations
            display_footer
            
            sleep "$REFRESH_INTERVAL"
        done
    else
        display_header
        display_system_overview
        display_container_resources
        display_service_health
        display_extraction_performance
        display_celery_performance
        display_database_performance
        display_optimization_recommendations
        
        log "${GREEN}Single monitoring run completed${NC}"
    fi
}

# Handle script termination
trap 'log "${YELLOW}Monitoring stopped${NC}"; exit 0' INT TERM

# Check if Docker Compose is available
if ! command -v docker &> /dev/null || ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker or Docker Compose not available${NC}"
    exit 1
fi

# Check if bc is available for calculations
if ! command -v bc &> /dev/null; then
    echo -e "${YELLOW}⚠️  Installing bc for calculations...${NC}"
    sudo apt-get update && sudo apt-get install -y bc
fi

# Start monitoring
main_monitor

# Usage examples:
# ./monitor-intelligent-extraction.sh                    # Single run
# ./monitor-intelligent-extraction.sh true               # Continuous with 5s refresh
# ./monitor-intelligent-extraction.sh true 10           # Continuous with 10s refresh