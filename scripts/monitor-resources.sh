#!/bin/bash

# Performance monitoring script for Chrono Scraper
# Usage: ./scripts/monitor-resources.sh [--continuous] [--interval=5]

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
CONTINUOUS=false
INTERVAL=5
OUTPUT_FILE=""

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
        --output=*)
            OUTPUT_FILE="${1#*=}"
            shift
            ;;
        --help)
            echo "Usage: $0 [--continuous] [--interval=5] [--output=file.log]"
            echo "  --continuous    Run monitoring continuously"
            echo "  --interval=N    Update interval in seconds (default: 5)"
            echo "  --output=FILE   Log output to file"
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
    if [[ -n "$OUTPUT_FILE" ]]; then
        echo "$1" | tee -a "$OUTPUT_FILE"
    else
        echo -e "$1"
    fi
}

# Function to get timestamp
timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

# Function to check if docker compose is running
check_docker_compose() {
    if ! docker compose ps >/dev/null 2>&1; then
        log_output "${RED}Error: Docker Compose services are not running${NC}"
        exit 1
    fi
}

# Function to get container stats
get_container_stats() {
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}"
}

# Function to get database performance metrics
get_db_metrics() {
    log_output "${BLUE}=== Database Performance ===${NC}"
    
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
    
    log_output "Active connections: ${GREEN}${connections}/100${NC}"
    
    # Get slow queries (if any)
    local slow_queries
    slow_queries=$(docker compose exec -T postgres psql -U chrono_scraper -d chrono_scraper -t -c "
        SELECT count(*) FROM pg_stat_activity 
        WHERE datname = 'chrono_scraper' AND state = 'active' 
        AND now() - query_start > interval '5 seconds';
    " 2>/dev/null | xargs)
    
    if [[ $slow_queries -gt 0 ]]; then
        log_output "Slow queries (>5s): ${YELLOW}${slow_queries}${NC}"
    else
        log_output "Slow queries (>5s): ${GREEN}0${NC}"
    fi
}

# Function to get Redis metrics
get_redis_metrics() {
    log_output "\n${BLUE}=== Redis Performance ===${NC}"
    
    # Get Redis info
    local redis_info
    redis_info=$(docker compose exec -T redis redis-cli info memory 2>/dev/null)
    
    if [[ $? -eq 0 ]]; then
        local used_memory
        used_memory=$(echo "$redis_info" | grep "used_memory_human:" | cut -d: -f2 | tr -d '\r')
        log_output "Redis memory used: ${GREEN}${used_memory}${NC}"
        
        local connected_clients
        connected_clients=$(docker compose exec -T redis redis-cli info clients 2>/dev/null | grep "connected_clients:" | cut -d: -f2 | tr -d '\r')
        log_output "Connected clients: ${GREEN}${connected_clients}${NC}"
        
        # Check keyspace
        local keyspace
        keyspace=$(docker compose exec -T redis redis-cli dbsize 2>/dev/null | tr -d '\r')
        log_output "Total keys: ${GREEN}${keyspace}${NC}"
    else
        log_output "${YELLOW}Redis metrics unavailable${NC}"
    fi
}

# Function to get API performance metrics
get_api_metrics() {
    log_output "\n${BLUE}=== API Performance ===${NC}"
    
    # Test API response time
    local start_time end_time response_time
    start_time=$(date +%s%N)
    
    if curl -f -s http://localhost:8000/health >/dev/null 2>&1; then
        end_time=$(date +%s%N)
        response_time=$(((end_time - start_time) / 1000000))
        
        if [[ $response_time -lt 100 ]]; then
            log_output "API health check: ${GREEN}${response_time}ms${NC}"
        elif [[ $response_time -lt 500 ]]; then
            log_output "API health check: ${YELLOW}${response_time}ms${NC}"
        else
            log_output "API health check: ${RED}${response_time}ms${NC}"
        fi
    else
        log_output "API health check: ${RED}FAILED${NC}"
    fi
    
    # Check Meilisearch
    if curl -f -s http://localhost:7700/health >/dev/null 2>&1; then
        log_output "Meilisearch: ${GREEN}HEALTHY${NC}"
    else
        log_output "Meilisearch: ${RED}UNHEALTHY${NC}"
    fi
    
    # Check Firecrawl
    if curl -f -s http://localhost:3002/health >/dev/null 2>&1; then
        log_output "Firecrawl API: ${GREEN}HEALTHY${NC}"
    else
        log_output "Firecrawl API: ${RED}UNHEALTHY${NC}"
    fi
}

# Function to get system metrics
get_system_metrics() {
    log_output "\n${BLUE}=== System Resources ===${NC}"
    
    # Get system load
    local load_avg
    load_avg=$(uptime | grep -o 'load average.*' | cut -d' ' -f3- | tr -d ',')
    log_output "Load average: ${GREEN}${load_avg}${NC}"
    
    # Get memory usage
    local memory_info
    memory_info=$(free -h | grep "Mem:")
    local total_mem used_mem available_mem
    total_mem=$(echo $memory_info | awk '{print $2}')
    used_mem=$(echo $memory_info | awk '{print $3}')
    available_mem=$(echo $memory_info | awk '{print $7}')
    
    log_output "System memory: ${used_mem}/${total_mem} used, ${available_mem} available"
    
    # Get disk usage
    local disk_usage
    disk_usage=$(df -h / | tail -1 | awk '{print $5}' | tr -d '%')
    if [[ $disk_usage -gt 80 ]]; then
        log_output "Disk usage: ${RED}${disk_usage}%${NC}"
    elif [[ $disk_usage -gt 60 ]]; then
        log_output "Disk usage: ${YELLOW}${disk_usage}%${NC}"
    else
        log_output "Disk usage: ${GREEN}${disk_usage}%${NC}"
    fi
}

# Function to display full monitoring report
show_monitoring_report() {
    clear
    log_output "${PURPLE}=================================================${NC}"
    log_output "${PURPLE}  Chrono Scraper Performance Monitor${NC}"
    log_output "${PURPLE}  $(timestamp)${NC}"
    log_output "${PURPLE}=================================================${NC}"
    
    # Container stats
    log_output "\n${BLUE}=== Container Resources ===${NC}"
    get_container_stats
    
    # Individual service metrics
    get_system_metrics
    get_db_metrics
    get_redis_metrics
    get_api_metrics
    
    log_output "\n${PURPLE}=================================================${NC}"
    log_output "${CYAN}Press Ctrl+C to stop monitoring${NC}"
    log_output "${PURPLE}=================================================${NC}"
}

# Main execution
main() {
    # Check if Docker Compose is running
    check_docker_compose
    
    if [[ "$CONTINUOUS" == "true" ]]; then
        log_output "${GREEN}Starting continuous monitoring (interval: ${INTERVAL}s)${NC}"
        log_output "${CYAN}Output file: ${OUTPUT_FILE:-stdout}${NC}"
        
        # Trap Ctrl+C
        trap 'log_output "\n${GREEN}Monitoring stopped.${NC}"; exit 0' INT
        
        while true; do
            show_monitoring_report
            sleep "$INTERVAL"
        done
    else
        show_monitoring_report
    fi
}

# Run the main function
main