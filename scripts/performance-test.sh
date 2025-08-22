#!/bin/bash

# Performance testing script for Chrono Scraper optimization validation
# Usage: ./scripts/performance-test.sh [--load-test] [--concurrent=10]

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
LOAD_TEST=false
CONCURRENT_USERS=10
TEST_DURATION=60

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --load-test)
            LOAD_TEST=true
            shift
            ;;
        --concurrent=*)
            CONCURRENT_USERS="${1#*=}"
            shift
            ;;
        --duration=*)
            TEST_DURATION="${1#*=}"
            shift
            ;;
        --help)
            echo "Usage: $0 [--load-test] [--concurrent=10] [--duration=60]"
            echo "  --load-test        Run load testing with concurrent users"
            echo "  --concurrent=N     Number of concurrent users (default: 10)"
            echo "  --duration=N       Test duration in seconds (default: 60)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Function to log output with colors
log_output() {
    echo -e "$1"
}

# Function to get timestamp
timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

# Function to check service availability
check_services() {
    log_output "${BLUE}=== Checking Service Availability ===${NC}"
    
    local services=(
        "http://localhost:8000/health|Backend API"
        "http://localhost:7700/health|Meilisearch"
        "http://localhost:3002/health|Firecrawl API"
        "http://localhost:5173|Frontend"
    )
    
    local all_healthy=true
    
    for service in "${services[@]}"; do
        local url=$(echo $service | cut -d'|' -f1)
        local name=$(echo $service | cut -d'|' -f2)
        
        if curl -f -s "$url" >/dev/null 2>&1; then
            log_output "✅ ${name}: ${GREEN}HEALTHY${NC}"
        else
            log_output "❌ ${name}: ${RED}UNHEALTHY${NC}"
            all_healthy=false
        fi
    done
    
    if [[ "$all_healthy" == "false" ]]; then
        log_output "${RED}Some services are unhealthy. Please check your setup.${NC}"
        exit 1
    fi
}

# Function to test API response times
test_api_performance() {
    log_output "\n${BLUE}=== API Performance Test ===${NC}"
    
    local endpoints=(
        "/health|Health Check"
        "/api/v1/auth/me|Auth Check"
        "/api/v1/projects/?limit=10|Projects List"
    )
    
    for endpoint in "${endpoints[@]}"; do
        local path=$(echo $endpoint | cut -d'|' -f1)
        local name=$(echo $endpoint | cut -d'|' -f2)
        local url="http://localhost:8000$path"
        
        log_output "\nTesting: ${name}"
        
        # Test response time
        local start_time end_time response_time
        start_time=$(date +%s%N)
        
        local status_code
        status_code=$(curl -w "%{http_code}" -s -o /dev/null "$url" 2>/dev/null || echo "000")
        
        end_time=$(date +%s%N)
        response_time=$(((end_time - start_time) / 1000000))
        
        if [[ "$status_code" == "200" ]]; then
            if [[ $response_time -lt 100 ]]; then
                log_output "  Response time: ${GREEN}${response_time}ms${NC} (Status: $status_code)"
            elif [[ $response_time -lt 500 ]]; then
                log_output "  Response time: ${YELLOW}${response_time}ms${NC} (Status: $status_code)"
            else
                log_output "  Response time: ${RED}${response_time}ms${NC} (Status: $status_code)"
            fi
        else
            log_output "  ${RED}Failed${NC} (Status: $status_code)"
        fi
    done
}

# Function to test database query performance
test_database_performance() {
    log_output "\n${BLUE}=== Database Performance Test ===${NC}"
    
    # Test basic query performance
    log_output "Testing database query performance..."
    
    local start_time end_time query_time
    start_time=$(date +%s%N)
    
    # Test a simple count query
    docker compose exec -T postgres psql -U chrono_scraper -d chrono_scraper -c "
        SELECT COUNT(*) FROM projects;
    " >/dev/null 2>&1
    
    end_time=$(date +%s%N)
    query_time=$(((end_time - start_time) / 1000000))
    
    if [[ $query_time -lt 50 ]]; then
        log_output "  Projects count query: ${GREEN}${query_time}ms${NC}"
    elif [[ $query_time -lt 200 ]]; then
        log_output "  Projects count query: ${YELLOW}${query_time}ms${NC}"
    else
        log_output "  Projects count query: ${RED}${query_time}ms${NC}"
    fi
    
    # Test a more complex query with joins
    start_time=$(date +%s%N)
    
    docker compose exec -T postgres psql -U chrono_scraper -d chrono_scraper -c "
        SELECT p.id, COUNT(d.id) as domain_count, COUNT(pg.id) as page_count
        FROM projects p
        LEFT JOIN domains d ON d.project_id = p.id
        LEFT JOIN pages pg ON pg.domain_id = d.id
        GROUP BY p.id
        LIMIT 10;
    " >/dev/null 2>&1
    
    end_time=$(date +%s%N)
    query_time=$(((end_time - start_time) / 1000000))
    
    if [[ $query_time -lt 100 ]]; then
        log_output "  Complex join query: ${GREEN}${query_time}ms${NC}"
    elif [[ $query_time -lt 500 ]]; then
        log_output "  Complex join query: ${YELLOW}${query_time}ms${NC}"
    else
        log_output "  Complex join query: ${RED}${query_time}ms${NC}"
    fi
}

# Function to test cache performance
test_cache_performance() {
    log_output "\n${BLUE}=== Cache Performance Test ===${NC}"
    
    # Test Redis response time
    local start_time end_time cache_time
    start_time=$(date +%s%N)
    
    docker compose exec -T redis redis-cli ping >/dev/null 2>&1
    
    end_time=$(date +%s%N)
    cache_time=$(((end_time - start_time) / 1000000))
    
    if [[ $cache_time -lt 10 ]]; then
        log_output "  Redis ping: ${GREEN}${cache_time}ms${NC}"
    elif [[ $cache_time -lt 50 ]]; then
        log_output "  Redis ping: ${YELLOW}${cache_time}ms${NC}"
    else
        log_output "  Redis ping: ${RED}${cache_time}ms${NC}"
    fi
    
    # Test cache set/get performance
    start_time=$(date +%s%N)
    
    docker compose exec -T redis redis-cli set test_key "test_value" >/dev/null 2>&1
    docker compose exec -T redis redis-cli get test_key >/dev/null 2>&1
    docker compose exec -T redis redis-cli del test_key >/dev/null 2>&1
    
    end_time=$(date +%s%N)
    cache_time=$(((end_time - start_time) / 1000000))
    
    if [[ $cache_time -lt 20 ]]; then
        log_output "  Set/Get/Del operations: ${GREEN}${cache_time}ms${NC}"
    elif [[ $cache_time -lt 100 ]]; then
        log_output "  Set/Get/Del operations: ${YELLOW}${cache_time}ms${NC}"
    else
        log_output "  Set/Get/Del operations: ${RED}${cache_time}ms${NC}"
    fi
}

# Function to run load testing with Apache Bench
run_load_test() {
    log_output "\n${BLUE}=== Load Testing ===${NC}"
    
    # Check if Apache Bench is available
    if ! command -v ab >/dev/null 2>&1; then
        log_output "${YELLOW}Apache Bench (ab) not found. Skipping load test.${NC}"
        log_output "Install with: sudo apt-get install apache2-utils"
        return
    fi
    
    log_output "Running load test with ${CONCURRENT_USERS} concurrent users for ${TEST_DURATION} seconds..."
    
    # Test the health endpoint
    local total_requests=$((CONCURRENT_USERS * TEST_DURATION / 2))
    
    log_output "\nTesting /health endpoint:"
    ab -n $total_requests -c $CONCURRENT_USERS -t $TEST_DURATION -q http://localhost:8000/health > /tmp/ab_health.log 2>&1
    
    # Parse results
    local requests_per_sec
    requests_per_sec=$(grep "Requests per second" /tmp/ab_health.log | awk '{print $4}')
    
    local mean_time
    mean_time=$(grep "Time per request" /tmp/ab_health.log | head -1 | awk '{print $4}')
    
    local failed_requests
    failed_requests=$(grep "Failed requests" /tmp/ab_health.log | awk '{print $3}')
    
    if [[ -n "$requests_per_sec" ]]; then
        log_output "  Requests per second: ${GREEN}${requests_per_sec}${NC}"
        log_output "  Mean response time: ${GREEN}${mean_time}ms${NC}"
        log_output "  Failed requests: ${GREEN}${failed_requests}${NC}"
    else
        log_output "  ${RED}Load test failed${NC}"
    fi
    
    # Clean up
    rm -f /tmp/ab_health.log
}

# Function to generate performance report
generate_report() {
    log_output "\n${PURPLE}=== Performance Summary ===${NC}"
    log_output "Test completed at: $(timestamp)"
    
    # Get current resource usage
    log_output "\nCurrent resource usage:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | head -6
    
    # Memory usage breakdown
    log_output "\nMemory usage breakdown:"
    local total_memory
    total_memory=$(free -m | grep "Mem:" | awk '{print $2}')
    local used_memory
    used_memory=$(free -m | grep "Mem:" | awk '{print $3}')
    local memory_percent
    memory_percent=$((used_memory * 100 / total_memory))
    
    if [[ $memory_percent -lt 70 ]]; then
        log_output "  System memory: ${GREEN}${used_memory}MB/${total_memory}MB (${memory_percent}%)${NC}"
    elif [[ $memory_percent -lt 85 ]]; then
        log_output "  System memory: ${YELLOW}${used_memory}MB/${total_memory}MB (${memory_percent}%)${NC}"
    else
        log_output "  System memory: ${RED}${used_memory}MB/${total_memory}MB (${memory_percent}%)${NC}"
    fi
    
    # Recommendations
    log_output "\n${CYAN}=== Optimization Recommendations ===${NC}"
    
    if [[ $memory_percent -gt 85 ]]; then
        log_output "⚠️  High memory usage detected. Consider scaling down services or adding more RAM."
    fi
    
    log_output "✅ Performance testing completed successfully!"
    log_output "📊 Use './scripts/monitor-resources.sh --continuous' for ongoing monitoring"
}

# Main execution
main() {
    log_output "${PURPLE}=================================================${NC}"
    log_output "${PURPLE}  Chrono Scraper Performance Test${NC}"
    log_output "${PURPLE}  $(timestamp)${NC}"
    log_output "${PURPLE}=================================================${NC}"
    
    # Run tests
    check_services
    test_api_performance
    test_database_performance
    test_cache_performance
    
    if [[ "$LOAD_TEST" == "true" ]]; then
        run_load_test
    fi
    
    generate_report
}

# Run the main function
main