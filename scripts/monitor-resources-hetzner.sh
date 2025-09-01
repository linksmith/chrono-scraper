#!/bin/bash

# Enhanced Performance monitoring script for Chrono Scraper on Hetzner CX32
# Optimized for 8GB RAM, 4 vCPU constraint with memory pressure alerts
# Usage: ./scripts/monitor-resources-hetzner.sh [--continuous] [--interval=10] [--alerts]

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Alert symbols
ALERT_CRITICAL='🚨'
ALERT_WARNING='⚠️'
ALERT_INFO='ℹ️'
ALERT_SUCCESS='✅'

# Default values
CONTINUOUS=false
INTERVAL=10
ALERTS_ENABLED=false
OUTPUT_FILE=""
LOG_FILE="/tmp/chrono-monitor.log"

# Hetzner CX32 system limits
TOTAL_RAM_MB=8192
TOTAL_CPU_CORES=4
AVAILABLE_RAM_MB=7168  # After OS overhead
AVAILABLE_CPU_CORES=3.5  # After OS overhead

# Monitoring thresholds
MEMORY_WARNING_THRESHOLD=85  # 85% of available RAM (6GB)
MEMORY_CRITICAL_THRESHOLD=92 # 92% of available RAM (6.5GB)
CPU_WARNING_THRESHOLD=80     # 80% of available CPU (2.8 cores)
CPU_CRITICAL_THRESHOLD=90    # 90% of available CPU (3.15 cores)

# Container tier definitions for scaling decisions
TIER1_CRITICAL=("chrono_postgres" "chrono_redis" "chrono_backend")
TIER2_IMPORTANT=("chrono_meilisearch" "chrono_celery_worker")
TIER3_BROWSER=("chrono_firecrawl_playwright" "chrono_firecrawl_api" "chrono_firecrawl_worker")
TIER4_FRONTEND=("chrono_frontend")
TIER5_UTILITIES=("chrono_celery_beat" "chrono_flower" "chrono_mailpit")

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --continuous)
            CONTINUOUS=true
            shift
            ;;
        --interval=*)
            INTERVAL="${1#*=}"
            shift
            ;;
        --alerts)
            ALERTS_ENABLED=true
            shift
            ;;
        --output=*)
            OUTPUT_FILE="${1#*=}"
            shift
            ;;
        --help)
            echo "Usage: $0 [--continuous] [--interval=10] [--alerts] [--output=file.log]"
            echo "  --continuous    Run monitoring continuously"
            echo "  --interval=N    Update interval in seconds (default: 10)"
            echo "  --alerts        Enable memory pressure alerts and scaling suggestions"
            echo "  --output=FILE   Log output to file"
            echo ""
            echo "Monitoring Thresholds for Hetzner CX32 (8GB RAM, 4 vCPU):"
            echo "  Memory Warning:  ${MEMORY_WARNING_THRESHOLD}% ($(($AVAILABLE_RAM_MB * $MEMORY_WARNING_THRESHOLD / 100))MB)"
            echo "  Memory Critical: ${MEMORY_CRITICAL_THRESHOLD}% ($(($AVAILABLE_RAM_MB * $MEMORY_CRITICAL_THRESHOLD / 100))MB)"
            echo "  CPU Warning:     ${CPU_WARNING_THRESHOLD}%"
            echo "  CPU Critical:    ${CPU_CRITICAL_THRESHOLD}%"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Function to log output
log_output() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    if [[ -n "$OUTPUT_FILE" ]]; then
        echo "[$timestamp] $message" | tee -a "$OUTPUT_FILE"
    else
        echo -e "$message"
    fi
    
    # Always log to monitoring log for alerts
    echo "[$timestamp] $message" >> "$LOG_FILE"
}

# Function to send alert (could be extended to webhook, email, etc.)
send_alert() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case "$level" in
        "CRITICAL")
            log_output "${RED}${ALERT_CRITICAL} CRITICAL ALERT: $message${NC}"
            ;;
        "WARNING")
            log_output "${YELLOW}${ALERT_WARNING} WARNING: $message${NC}"
            ;;
        "INFO")
            log_output "${BLUE}${ALERT_INFO} INFO: $message${NC}"
            ;;
        "SUCCESS")
            log_output "${GREEN}${ALERT_SUCCESS} SUCCESS: $message${NC}"
            ;;
    esac
    
    # Log alert to system log
    logger -t chrono-monitor "[$level] $message"
}

# Function to get timestamp
timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

# Function to check if docker compose is running
check_docker_compose() {
    if ! docker compose ps >/dev/null 2>&1; then
        send_alert "CRITICAL" "Docker Compose services are not running"
        exit 1
    fi
}

# Function to calculate memory usage percentage
get_memory_percentage() {
    local used_mb=$1
    local total_mb=$2
    echo $(( (used_mb * 100) / total_mb ))
}

# Function to get container memory in MB
get_container_memory_mb() {
    local container_name=$1
    local memory_str=$(docker stats --no-stream --format "{{.MemUsage}}" "$container_name" 2>/dev/null | head -1)
    if [[ -n "$memory_str" ]]; then
        # Extract just the used memory (before the '/')
        local used=$(echo "$memory_str" | cut -d'/' -f1)
        # Convert to MB
        if [[ "$used" =~ ([0-9.]+)([KMGT]iB|[KMGT]B) ]]; then
            local value=${BASH_REMATCH[1]}
            local unit=${BASH_REMATCH[2]}
            case "$unit" in
                "KiB"|"KB") echo $(( ${value%.*} / 1024 ));;
                "MiB"|"MB") echo ${value%.*};;
                "GiB"|"GB") echo $(( ${value%.*} * 1024 ));;
                "TiB"|"TB") echo $(( ${value%.*} * 1024 * 1024 ));;
                *) echo 0;;
            esac
        else
            echo 0
        fi
    else
        echo 0
    fi
}

# Function to get system memory usage
get_system_memory_status() {
    local memory_info=$(free -m | grep "Mem:")
    local total_mem=$(echo $memory_info | awk '{print $2}')
    local used_mem=$(echo $memory_info | awk '{print $3}')
    local available_mem=$(echo $memory_info | awk '{print $7}')
    
    local memory_percent=$(get_memory_percentage $used_mem $total_mem)
    
    echo "$used_mem $total_mem $available_mem $memory_percent"
}

# Function to get CPU load percentage
get_cpu_load() {
    local load_1min=$(uptime | grep -o 'load average.*' | cut -d' ' -f3 | tr -d ',')
    # Convert load to percentage based on available cores
    local cpu_percent=$(echo "$load_1min * 100 / $AVAILABLE_CPU_CORES" | bc -l | cut -d'.' -f1)
    echo "$cpu_percent"
}

# Function to get container resource stats with health status
get_container_stats_detailed() {
    log_output "\n${BLUE}=== Container Resource Usage ===${NC}"
    
    local total_container_memory=0
    local total_container_cpu=0.0
    local container_count=0
    local unhealthy_containers=()
    
    # Table header
    printf "%-25s %-10s %-15s %-10s %-10s %-10s\n" "Container" "Status" "Memory" "Memory%" "CPU%" "Health"
    printf "%-25s %-10s %-15s %-10s %-10s %-10s\n" "------------------------" "--------" "-------------" "--------" "-------" "--------"
    
    for tier_name in "TIER1_CRITICAL" "TIER2_IMPORTANT" "TIER3_BROWSER" "TIER4_FRONTEND" "TIER5_UTILITIES"; do
        local -n tier_array=$tier_name
        
        for container in "${tier_array[@]}"; do
            if docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
                local stats=$(docker stats --no-stream --format "{{.Container}} {{.CPUPerc}} {{.MemUsage}}" "$container" 2>/dev/null | head -1)
                
                if [[ -n "$stats" ]]; then
                    local container_name=$(echo "$stats" | awk '{print $1}')
                    local cpu_percent=$(echo "$stats" | awk '{print $2}' | tr -d '%')
                    local mem_usage=$(echo "$stats" | awk '{print $3}')
                    local mem_percent=$(echo "$stats" | awk '{print $4}' | tr -d '%' | tr -d '()')
                    
                    # Get health status
                    local health_status=$(docker inspect --format="{{.State.Health.Status}}" "$container" 2>/dev/null || echo "none")
                    if [[ "$health_status" == "none" ]]; then
                        health_status=$(docker inspect --format="{{.State.Status}}" "$container" 2>/dev/null || echo "unknown")
                    fi
                    
                    # Color code based on health and resource usage
                    local status_color="$GREEN"
                    local status_symbol="✅"
                    
                    if [[ "$health_status" =~ unhealthy|exited|dead ]]; then
                        status_color="$RED"
                        status_symbol="❌"
                        unhealthy_containers+=("$container")
                    elif [[ "${mem_percent%.*}" -gt 90 ]] || [[ "${cpu_percent%.*}" -gt 90 ]]; then
                        status_color="$YELLOW"
                        status_symbol="⚠️"
                    fi
                    
                    printf "${status_color}%-25s${NC} ${status_color}%-10s${NC} %-15s %-10s %-10s ${status_color}%-10s${NC}\n" \
                        "${container:7}" \
                        "${status_symbol}" \
                        "$mem_usage" \
                        "${mem_percent}%" \
                        "${cpu_percent}%" \
                        "$health_status"
                    
                    # Accumulate totals
                    if [[ "$cpu_percent" =~ ^[0-9.]+$ ]]; then
                        total_container_cpu=$(echo "$total_container_cpu + $cpu_percent" | bc -l)
                    fi
                    container_count=$((container_count + 1))
                else
                    printf "${RED}%-25s %-10s %-15s %-10s %-10s %-10s${NC}\n" \
                        "${container:7}" "❌" "OFFLINE" "N/A" "N/A" "stopped"
                fi
            fi
        done
    done
    
    # Alert on unhealthy containers
    if [[ ${#unhealthy_containers[@]} -gt 0 ]] && [[ "$ALERTS_ENABLED" == "true" ]]; then
        send_alert "WARNING" "Unhealthy containers detected: ${unhealthy_containers[*]}"
    fi
    
    log_output "\n${CYAN}Total running containers: ${container_count}${NC}"
    log_output "${CYAN}Combined container CPU usage: ${total_container_cpu%.*}%${NC}"
}

# Function to analyze system performance and suggest optimizations
analyze_performance() {
    local memory_status=($(get_system_memory_status))
    local used_mem=${memory_status[0]}
    local total_mem=${memory_status[1]}
    local available_mem=${memory_status[2]}
    local memory_percent=${memory_status[3]}
    
    local cpu_percent=$(get_cpu_load)
    
    log_output "\n${BLUE}=== Performance Analysis ===${NC}"
    
    # Memory analysis
    if [[ $memory_percent -ge $MEMORY_CRITICAL_THRESHOLD ]]; then
        send_alert "CRITICAL" "Memory usage critical: ${memory_percent}% (${used_mem}MB/${total_mem}MB)"
        log_output "${RED}${ALERT_CRITICAL} IMMEDIATE ACTION REQUIRED:${NC}"
        log_output "  1. Stop Tier 5 services (Flower, Mailpit): docker compose stop flower mailpit"
        log_output "  2. Reduce Celery worker concurrency: docker compose restart celery_worker"
        log_output "  3. Consider stopping Firecrawl services temporarily"
        log_output "  4. Scale down browser automation: MAX_CONCURRENT_SESSIONS=1"
    elif [[ $memory_percent -ge $MEMORY_WARNING_THRESHOLD ]]; then
        send_alert "WARNING" "Memory usage high: ${memory_percent}% (${used_mem}MB/${total_mem}MB)"
        log_output "${YELLOW}${ALERT_WARNING} OPTIMIZATION RECOMMENDED:${NC}"
        log_output "  1. Monitor Firecrawl Playwright memory usage closely"
        log_output "  2. Consider reducing browser concurrent sessions"
        log_output "  3. Clear Redis cache: docker compose exec redis redis-cli FLUSHDB"
        log_output "  4. Review active Celery tasks: make flower (http://localhost:5555)"
    else
        log_output "${GREEN}${ALERT_SUCCESS} Memory usage optimal: ${memory_percent}% (${used_mem}MB/${total_mem}MB)${NC}"
    fi
    
    # CPU analysis
    if [[ ${cpu_percent%.*} -ge $CPU_CRITICAL_THRESHOLD ]]; then
        send_alert "CRITICAL" "CPU usage critical: ${cpu_percent}%"
        log_output "${RED}${ALERT_CRITICAL} CPU OVERLOAD DETECTED:${NC}"
        log_output "  1. Reduce Celery worker concurrency to 2"
        log_output "  2. Limit Firecrawl browser sessions to 1"
        log_output "  3. Check for runaway processes: docker stats"
    elif [[ ${cpu_percent%.*} -ge $CPU_WARNING_THRESHOLD ]]; then
        send_alert "WARNING" "CPU usage high: ${cpu_percent}%"
        log_output "${YELLOW}${ALERT_WARNING} CPU OPTIMIZATION NEEDED:${NC}"
        log_output "  1. Monitor task queue length"
        log_output "  2. Consider scaling back concurrent operations"
    else
        log_output "${GREEN}${ALERT_SUCCESS} CPU usage optimal: ${cpu_percent}%${NC}"
    fi
    
    # Resource availability
    local memory_free_mb=$available_mem
    local memory_free_percent=$(( (memory_free_mb * 100) / total_mem ))
    
    log_output "\n${CYAN}=== Resource Availability ===${NC}"
    log_output "Available memory: ${GREEN}${memory_free_mb}MB (${memory_free_percent}%)${NC}"
    log_output "Memory buffer: ${GREEN}$(( AVAILABLE_RAM_MB - used_mem ))MB${NC}"
    
    if [[ $memory_free_mb -lt 512 ]]; then
        send_alert "WARNING" "Low memory buffer: only ${memory_free_mb}MB available"
    fi
}

# Function to get database performance metrics with memory awareness
get_db_metrics() {
    log_output "\n${BLUE}=== Database Performance ===${NC}"
    
    # Get database size
    local db_size
    db_size=$(docker compose exec -T postgres psql -U chrono_scraper -d chrono_scraper -t -c "
        SELECT pg_size_pretty(pg_database_size('chrono_scraper'));
    " 2>/dev/null | xargs)
    
    log_output "Database size: ${GREEN}${db_size}${NC}"
    
    # Get connection count
    local connections
    connections=$(docker compose exec -T postgres psql -U chrono_scraper -d chrono_scraper -t -c "
        SELECT count(*) FROM pg_stat_activity WHERE datname = 'chrono_scraper';
    " 2>/dev/null | xargs)
    
    # Connection pool optimization for low memory
    if [[ $connections -gt 30 ]]; then
        log_output "Active connections: ${YELLOW}${connections}/50${NC} ${ALERT_WARNING} High connection count"
        if [[ "$ALERTS_ENABLED" == "true" ]]; then
            send_alert "WARNING" "High database connection count: ${connections}/50"
        fi
    else
        log_output "Active connections: ${GREEN}${connections}/50${NC}"
    fi
    
    # Check for slow queries
    local slow_queries
    slow_queries=$(docker compose exec -T postgres psql -U chrono_scraper -d chrono_scraper -t -c "
        SELECT count(*) FROM pg_stat_activity 
        WHERE datname = 'chrono_scraper' AND state = 'active' 
        AND now() - query_start > interval '10 seconds';
    " 2>/dev/null | xargs)
    
    if [[ $slow_queries -gt 0 ]]; then
        log_output "Slow queries (>10s): ${YELLOW}${slow_queries}${NC}"
        if [[ "$ALERTS_ENABLED" == "true" ]]; then
            send_alert "WARNING" "Slow queries detected: ${slow_queries} queries running >10s"
        fi
    else
        log_output "Slow queries (>10s): ${GREEN}0${NC}"
    fi
    
    # Database memory usage
    local shared_buffers
    shared_buffers=$(docker compose exec -T postgres psql -U chrono_scraper -d chrono_scraper -t -c "
        SHOW shared_buffers;
    " 2>/dev/null | xargs)
    log_output "Shared buffers: ${GREEN}${shared_buffers}${NC}"
}

# Function to get Redis metrics with memory pressure awareness
get_redis_metrics() {
    log_output "\n${BLUE}=== Redis Performance ===${NC}"
    
    local redis_info
    redis_info=$(docker compose exec -T redis redis-cli info memory 2>/dev/null)
    
    if [[ $? -eq 0 ]]; then
        local used_memory
        used_memory=$(echo "$redis_info" | grep "used_memory_human:" | cut -d: -f2 | tr -d '\r')
        local max_memory
        max_memory=$(echo "$redis_info" | grep "maxmemory_human:" | cut -d: -f2 | tr -d '\r')
        
        log_output "Redis memory: ${GREEN}${used_memory}${NC} / ${GREEN}${max_memory:-300MB}${NC}"
        
        local connected_clients
        connected_clients=$(docker compose exec -T redis redis-cli info clients 2>/dev/null | grep "connected_clients:" | cut -d: -f2 | tr -d '\r')
        log_output "Connected clients: ${GREEN}${connected_clients}${NC}"
        
        local keyspace
        keyspace=$(docker compose exec -T redis redis-cli dbsize 2>/dev/null | tr -d '\r')
        log_output "Total keys: ${GREEN}${keyspace}${NC}"
        
        # Check memory pressure
        local used_memory_peak
        used_memory_peak=$(echo "$redis_info" | grep "used_memory_peak_human:" | cut -d: -f2 | tr -d '\r')
        log_output "Peak memory usage: ${CYAN}${used_memory_peak}${NC}"
        
    else
        log_output "${YELLOW}Redis metrics unavailable${NC}"
    fi
}

# Function to get API and service health with response time monitoring
get_api_metrics() {
    log_output "\n${BLUE}=== Service Health & Response Times ===${NC}"
    
    local services=(
        "http://localhost:8000/health|Backend API|CRITICAL"
        "http://localhost:7700/health|Meilisearch|IMPORTANT"
        "http://localhost:3002/health|Firecrawl API|BROWSER"
        "http://localhost:3000/health|Firecrawl Playwright|BROWSER"
        "http://localhost:5173|Frontend|FRONTEND"
        "http://localhost:5555|Flower|UTILITY"
    )
    
    local unhealthy_services=()
    
    for service in "${services[@]}"; do
        local url=$(echo $service | cut -d'|' -f1)
        local name=$(echo $service | cut -d'|' -f2)
        local tier=$(echo $service | cut -d'|' -f3)
        
        local start_time end_time response_time
        start_time=$(date +%s%N)
        
        local status_code
        status_code=$(timeout 10 curl -w "%{http_code}" -s -o /dev/null "$url" 2>/dev/null || echo "000")
        
        if [[ "$status_code" == "200" ]]; then
            end_time=$(date +%s%N)
            response_time=$(((end_time - start_time) / 1000000))
            
            if [[ $response_time -lt 200 ]]; then
                log_output "${name}: ${GREEN}${response_time}ms${NC} [$tier]"
            elif [[ $response_time -lt 1000 ]]; then
                log_output "${name}: ${YELLOW}${response_time}ms${NC} [$tier]"
            else
                log_output "${name}: ${RED}${response_time}ms${NC} [$tier]"
                if [[ "$tier" == "CRITICAL" ]] && [[ "$ALERTS_ENABLED" == "true" ]]; then
                    send_alert "WARNING" "${name} slow response: ${response_time}ms"
                fi
            fi
        else
            log_output "${name}: ${RED}FAILED (${status_code})${NC} [$tier]"
            unhealthy_services+=("$name")
        fi
    done
    
    if [[ ${#unhealthy_services[@]} -gt 0 ]] && [[ "$ALERTS_ENABLED" == "true" ]]; then
        send_alert "WARNING" "Unhealthy services: ${unhealthy_services[*]}"
    fi
}

# Function to provide scaling recommendations
provide_scaling_recommendations() {
    local memory_status=($(get_system_memory_status))
    local memory_percent=${memory_status[3]}
    local cpu_percent=$(get_cpu_load)
    
    log_output "\n${PURPLE}=== Scaling Recommendations ===${NC}"
    
    if [[ $memory_percent -ge $MEMORY_CRITICAL_THRESHOLD ]] || [[ ${cpu_percent%.*} -ge $CPU_CRITICAL_THRESHOLD ]]; then
        log_output "${RED}${ALERT_CRITICAL} CRITICAL - Immediate scaling required:${NC}"
        log_output "1. ${YELLOW}Emergency shutdown sequence:${NC}"
        log_output "   make down && docker compose -f docker-compose.hetzner-cx32.yml up -d --scale firecrawl-worker=0 --scale flower=0"
        log_output "2. ${YELLOW}Restart with minimal services:${NC}"
        log_output "   docker compose -f docker-compose.hetzner-cx32.yml up -d postgres redis backend"
        log_output "3. ${YELLOW}Gradually add services:${NC}"
        log_output "   docker compose -f docker-compose.hetzner-cx32.yml up -d meilisearch celery_worker"
    elif [[ $memory_percent -ge $MEMORY_WARNING_THRESHOLD ]] || [[ ${cpu_percent%.*} -ge $CPU_WARNING_THRESHOLD ]]; then
        log_output "${YELLOW}${ALERT_WARNING} WARNING - Optimization recommended:${NC}"
        log_output "1. ${CYAN}Reduce browser automation:${NC}"
        log_output "   docker compose exec firecrawl-api sh -c 'export MAX_CONCURRENT_SESSIONS=1'"
        log_output "2. ${CYAN}Scale down worker concurrency:${NC}"
        log_output "   docker compose stop celery_worker && docker compose up -d celery_worker"
        log_output "3. ${CYAN}Clear caches:${NC}"
        log_output "   docker compose exec redis redis-cli FLUSHDB"
    else
        log_output "${GREEN}${ALERT_SUCCESS} System performing well - no scaling needed${NC}"
        log_output "Current capacity utilization:"
        log_output "  Memory: ${memory_percent}% (${MEMORY_WARNING_THRESHOLD}% warning threshold)"
        log_output "  CPU: ${cpu_percent%.*}% (${CPU_WARNING_THRESHOLD}% warning threshold)"
    fi
}

# Function to display comprehensive monitoring report
show_monitoring_report() {
    clear
    log_output "${PURPLE}=================================================================${NC}"
    log_output "${PURPLE}  Chrono Scraper Performance Monitor - Hetzner CX32 Optimized${NC}"
    log_output "${PURPLE}  $(timestamp) | RAM: ${AVAILABLE_RAM_MB}MB | CPU: ${AVAILABLE_CPU_CORES} cores${NC}"
    log_output "${PURPLE}=================================================================${NC}"
    
    get_container_stats_detailed
    analyze_performance
    get_db_metrics
    get_redis_metrics
    get_api_metrics
    
    if [[ "$ALERTS_ENABLED" == "true" ]]; then
        provide_scaling_recommendations
    fi
    
    log_output "\n${PURPLE}=================================================================${NC}"
    if [[ "$CONTINUOUS" == "true" ]]; then
        log_output "${CYAN}Continuous monitoring active (${INTERVAL}s interval) | Press Ctrl+C to stop${NC}"
    fi
    if [[ "$ALERTS_ENABLED" == "true" ]]; then
        log_output "${CYAN}Alerts enabled | Log file: ${LOG_FILE}${NC}"
    fi
    log_output "${PURPLE}=================================================================${NC}"
}

# Function to cleanup on exit
cleanup() {
    log_output "\n${GREEN}Monitoring stopped gracefully.${NC}"
    if [[ "$ALERTS_ENABLED" == "true" ]]; then
        send_alert "INFO" "Resource monitoring stopped"
    fi
    exit 0
}

# Main execution function
main() {
    # Check if Docker Compose is running
    check_docker_compose
    
    # Create monitoring log directory
    mkdir -p "$(dirname "$LOG_FILE")"
    
    if [[ "$ALERTS_ENABLED" == "true" ]]; then
        send_alert "INFO" "Resource monitoring started for Hetzner CX32"
        log_output "${GREEN}Alerts enabled - thresholds: Memory ${MEMORY_WARNING_THRESHOLD}%/${MEMORY_CRITICAL_THRESHOLD}%, CPU ${CPU_WARNING_THRESHOLD}%/${CPU_CRITICAL_THRESHOLD}%${NC}"
    fi
    
    if [[ "$CONTINUOUS" == "true" ]]; then
        log_output "${GREEN}Starting continuous monitoring (interval: ${INTERVAL}s)${NC}"
        log_output "${CYAN}Output file: ${OUTPUT_FILE:-stdout}${NC}"
        
        # Trap signals for graceful shutdown
        trap cleanup INT TERM
        
        while true; do
            show_monitoring_report
            sleep "$INTERVAL"
        done
    else
        show_monitoring_report
    fi
}

# Ensure bc is available for calculations
if ! command -v bc >/dev/null 2>&1; then
    log_output "${YELLOW}Warning: bc (basic calculator) not found. CPU calculations may be inaccurate.${NC}"
    log_output "Install with: sudo apt-get install bc"
fi

# Run the main function
main