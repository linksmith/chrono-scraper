#!/bin/bash

# Intelligent Content Extraction Performance Test Suite
# Tests the optimized system's ability to handle 50+ pages/second with 10-25 concurrent extractions
# Post-Firecrawl removal performance validation

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
CONCURRENT_EXTRACTIONS=${1:-15}  # Default 15 concurrent extractions
TEST_DURATION=${2:-300}          # Default 5 minutes
TARGET_PAGES_PER_SECOND=${3:-50} # Target throughput
MAX_RESPONSE_TIME=${4:-45}       # Max acceptable response time (seconds)
TEST_URLS_COUNT=${5:-100}        # Number of test URLs to use

# Test configuration
API_BASE_URL="http://localhost:8000"
TEST_PROJECT_ID=""
TEST_DOMAIN_ID=""
RESULTS_DIR="/tmp/intelligent-extraction-tests"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEST_LOG="$RESULTS_DIR/performance_test_$TIMESTAMP.log"

# Test URLs for various extraction scenarios
TEST_URLS=(
    # News articles
    "https://web.archive.org/web/20240101120000/https://www.bbc.com/news/world"
    "https://web.archive.org/web/20240101120000/https://www.reuters.com/world/"
    "https://web.archive.org/web/20240101120000/https://www.cnn.com/world"
    # Academic papers
    "https://web.archive.org/web/20240101120000/https://arxiv.org/abs/2301.00001"
    "https://web.archive.org/web/20240101120000/https://www.nature.com/articles/"
    # Government sites
    "https://web.archive.org/web/20240101120000/https://www.whitehouse.gov/briefing-room/"
    "https://web.archive.org/web/20240101120000/https://www.gov.uk/government/news"
    # Technical documentation
    "https://web.archive.org/web/20240101120000/https://docs.python.org/3/"
    "https://web.archive.org/web/20240101120000/https://kubernetes.io/docs/"
    # Blog posts
    "https://web.archive.org/web/20240101120000/https://blog.google.com/"
    "https://web.archive.org/web/20240101120000/https://engineering.fb.com/"
)

# Performance metrics
declare -A METRICS
METRICS[total_requests]=0
METRICS[successful_extractions]=0
METRICS[failed_extractions]=0
METRICS[total_response_time]=0
METRICS[min_response_time]=999999
METRICS[max_response_time]=0
METRICS[timeouts]=0
METRICS[circuit_breaker_triggers]=0
METRICS[memory_recycling_events]=0

# Helper functions
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$TEST_LOG"
}

log_color() {
    echo -e "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$TEST_LOG"
}

setup_test_environment() {
    log_color "${BLUE}🔧 Setting up test environment...${NC}"
    
    # Create results directory
    mkdir -p "$RESULTS_DIR"
    
    # Check if services are running
    if ! curl -s "$API_BASE_URL/health" > /dev/null; then
        log_color "${RED}❌ Backend API not accessible at $API_BASE_URL${NC}"
        exit 1
    fi
    
    # Create test project for performance testing
    log "Creating test project..."
    local project_response=$(curl -s -X POST "$API_BASE_URL/api/v1/projects/" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -d '{
            "name": "Performance Test Project '$TIMESTAMP'",
            "description": "Automated performance testing for intelligent extraction",
            "research_goals": "Performance validation",
            "domains": ["test-performance.com"]
        }' || echo '{}')
    
    TEST_PROJECT_ID=$(echo "$project_response" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
    
    if [[ -z "$TEST_PROJECT_ID" ]]; then
        log_color "${YELLOW}⚠️  Could not create test project, using existing project${NC}"
        TEST_PROJECT_ID="test-project-id"
    else
        log "Created test project: $TEST_PROJECT_ID"
    fi
}

generate_test_urls() {
    log "Generating $TEST_URLS_COUNT test URLs..."
    
    local test_urls_file="$RESULTS_DIR/test_urls_$TIMESTAMP.txt"
    
    # Generate variations of test URLs with different timestamps
    for i in $(seq 1 $TEST_URLS_COUNT); do
        local base_url=${TEST_URLS[$((i % ${#TEST_URLS[@]}))]}
        local timestamp=$((20240101000000 + RANDOM % 10000000))
        echo "${base_url/20240101120000/$timestamp}" >> "$test_urls_file"
    done
    
    echo "$test_urls_file"
}

get_jwt_token() {
    # Attempt to get JWT token for API calls
    local login_response=$(curl -s -X POST "$API_BASE_URL/api/v1/auth/login" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=playwright@test.com&password=TestPassword123!" || echo '{}')
    
    JWT_TOKEN=$(echo "$login_response" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
    
    if [[ -z "$JWT_TOKEN" ]]; then
        log_color "${YELLOW}⚠️  Could not obtain JWT token, some tests may fail${NC}"
        JWT_TOKEN="dummy-token"
    fi
}

start_extraction_task() {
    local url=$1
    local task_id=$2
    
    local start_time=$(date +%s.%3N)
    
    # Submit extraction task via API
    local response=$(curl -s -w "%{http_code}" -X POST \
        "$API_BASE_URL/api/v1/projects/$TEST_PROJECT_ID/extract" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -d "{\"url\": \"$url\", \"use_intelligent_extraction\": true}" \
        --max-time $MAX_RESPONSE_TIME || echo "000")
    
    local end_time=$(date +%s.%3N)
    local response_time=$(echo "$end_time - $start_time" | bc)
    local http_code="${response: -3}"
    local response_body="${response%???}"
    
    # Update metrics
    METRICS[total_requests]=$((METRICS[total_requests] + 1))
    METRICS[total_response_time]=$(echo "${METRICS[total_response_time]} + $response_time" | bc)
    
    # Check if response time is min/max
    if (( $(echo "$response_time < ${METRICS[min_response_time]}" | bc -l) )); then
        METRICS[min_response_time]=$response_time
    fi
    if (( $(echo "$response_time > ${METRICS[max_response_time]}" | bc -l) )); then
        METRICS[max_response_time]=$response_time
    fi
    
    # Classify response
    if [[ "$http_code" == "200" || "$http_code" == "201" || "$http_code" == "202" ]]; then
        METRICS[successful_extractions]=$((METRICS[successful_extractions] + 1))
        echo "$task_id,SUCCESS,$response_time,$http_code" >> "$RESULTS_DIR/task_results_$TIMESTAMP.csv"
    elif [[ "$http_code" == "000" ]]; then
        METRICS[timeouts]=$((METRICS[timeouts] + 1))
        METRICS[failed_extractions]=$((METRICS[failed_extractions] + 1))
        echo "$task_id,TIMEOUT,$response_time,000" >> "$RESULTS_DIR/task_results_$TIMESTAMP.csv"
    elif [[ "$http_code" == "503" ]]; then
        METRICS[circuit_breaker_triggers]=$((METRICS[circuit_breaker_triggers] + 1))
        METRICS[failed_extractions]=$((METRICS[failed_extractions] + 1))
        echo "$task_id,CIRCUIT_BREAKER,$response_time,$http_code" >> "$RESULTS_DIR/task_results_$TIMESTAMP.csv"
    else
        METRICS[failed_extractions]=$((METRICS[failed_extractions] + 1))
        echo "$task_id,FAILED,$response_time,$http_code" >> "$RESULTS_DIR/task_results_$TIMESTAMP.csv"
    fi
    
    log "Task $task_id: $http_code (${response_time}s)"
}

monitor_system_resources() {
    local monitoring_duration=$1
    local interval=5
    local resource_log="$RESULTS_DIR/resources_$TIMESTAMP.log"
    
    log_color "${BLUE}📊 Starting system resource monitoring for ${monitoring_duration}s...${NC}"
    
    echo "timestamp,celery_worker_cpu,celery_worker_memory,backend_cpu,backend_memory,postgres_cpu,postgres_memory,redis_memory,total_system_memory" > "$resource_log"
    
    local end_time=$(($(date +%s) + monitoring_duration))
    
    while [[ $(date +%s) -lt $end_time ]]; do
        local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        
        # Get container stats
        local celery_cpu=$(docker stats --no-stream chrono_celery_worker --format "{{.CPUPerc}}" | sed 's/%//')
        local celery_mem=$(docker stats --no-stream chrono_celery_worker --format "{{.MemUsage}}" | sed 's/\/.*//' | sed 's/MiB//')
        local backend_cpu=$(docker stats --no-stream chrono_backend --format "{{.CPUPerc}}" | sed 's/%//')
        local backend_mem=$(docker stats --no-stream chrono_backend --format "{{.MemUsage}}" | sed 's/\/.*//' | sed 's/MiB//')
        local postgres_cpu=$(docker stats --no-stream chrono_postgres --format "{{.CPUPerc}}" | sed 's/%//')
        local postgres_mem=$(docker stats --no-stream chrono_postgres --format "{{.MemUsage}}" | sed 's/\/.*//' | sed 's/MiB//')
        local redis_mem=$(docker stats --no-stream chrono_redis --format "{{.MemUsage}}" | sed 's/\/.*//' | sed 's/MiB//')
        
        # System memory
        local system_mem=$(free | grep Mem | awk '{printf "%.1f", ($3/$2)*100}')
        
        echo "$timestamp,$celery_cpu,$celery_mem,$backend_cpu,$backend_mem,$postgres_cpu,$postgres_mem,$redis_mem,$system_mem" >> "$resource_log"
        
        sleep $interval
    done
    
    log "Resource monitoring completed"
}

run_concurrent_extraction_test() {
    log_color "${GREEN}🚀 Starting concurrent extraction performance test${NC}"
    log "Configuration: $CONCURRENT_EXTRACTIONS concurrent extractions, ${TEST_DURATION}s duration"
    
    # Generate test URLs
    local test_urls_file=$(generate_test_urls)
    
    # Create CSV header for results
    echo "task_id,status,response_time,http_code" > "$RESULTS_DIR/task_results_$TIMESTAMP.csv"
    
    # Start resource monitoring in background
    monitor_system_resources $TEST_DURATION &
    local monitor_pid=$!
    
    local start_time=$(date +%s)
    local end_time=$((start_time + TEST_DURATION))
    local task_counter=0
    local active_tasks=0
    
    log "Test running from $(date -d @$start_time) to $(date -d @$end_time)"
    
    while [[ $(date +%s) -lt $end_time ]]; do
        # Launch new tasks up to concurrency limit
        while [[ $active_tasks -lt $CONCURRENT_EXTRACTIONS && $(date +%s) -lt $end_time ]]; do
            local url=$(sed -n "$((task_counter % TEST_URLS_COUNT + 1))p" "$test_urls_file")
            task_counter=$((task_counter + 1))
            active_tasks=$((active_tasks + 1))
            
            # Start extraction task in background
            (
                start_extraction_task "$url" "$task_counter"
                # Signal task completion
                echo $$ > "$RESULTS_DIR/completed_$task_counter.tmp"
            ) &
        done
        
        # Check for completed tasks
        for completed_file in "$RESULTS_DIR"/completed_*.tmp; do
            if [[ -f "$completed_file" ]]; then
                active_tasks=$((active_tasks - 1))
                rm "$completed_file"
            fi
        done
        
        # Brief sleep to prevent busy waiting
        sleep 0.1
    done
    
    # Wait for remaining tasks to complete
    log "Waiting for remaining tasks to complete..."
    wait
    
    # Stop resource monitoring
    kill $monitor_pid 2>/dev/null || true
    
    # Cleanup
    rm -f "$RESULTS_DIR"/completed_*.tmp
    
    log "Concurrent extraction test completed"
}

calculate_performance_metrics() {
    log_color "${BLUE}📈 Calculating performance metrics...${NC}"
    
    # Calculate averages and rates
    local avg_response_time=0
    local success_rate=0
    local pages_per_second=0
    local efficiency_score=0
    
    if [[ ${METRICS[total_requests]} -gt 0 ]]; then
        avg_response_time=$(echo "scale=2; ${METRICS[total_response_time]} / ${METRICS[total_requests]}" | bc)
        success_rate=$(echo "scale=2; ${METRICS[successful_extractions]} * 100 / ${METRICS[total_requests]}" | bc)
        pages_per_second=$(echo "scale=2; ${METRICS[successful_extractions]} / $TEST_DURATION" | bc)
    fi
    
    # Calculate efficiency score (pages/second per CPU core used)
    local avg_cpu_usage=$(awk -F',' 'NR>1 {sum+=$2+$4+$6} END {printf "%.1f", sum/(NR-1)}' "$RESULTS_DIR/resources_$TIMESTAMP.log")
    if [[ -n "$avg_cpu_usage" && $(echo "$avg_cpu_usage > 0" | bc -l) -eq 1 ]]; then
        efficiency_score=$(echo "scale=2; $pages_per_second / ($avg_cpu_usage / 100)" | bc)
    fi
    
    # Generate performance report
    local report_file="$RESULTS_DIR/performance_report_$TIMESTAMP.md"
    
    cat > "$report_file" << EOF
# Intelligent Content Extraction Performance Test Report

**Test Configuration:**
- Concurrent Extractions: $CONCURRENT_EXTRACTIONS
- Test Duration: ${TEST_DURATION}s
- Target Throughput: $TARGET_PAGES_PER_SECOND pages/second
- Max Response Time: ${MAX_RESPONSE_TIME}s
- Test URLs: $TEST_URLS_COUNT

## Performance Results

### Extraction Metrics
- **Total Requests:** ${METRICS[total_requests]}
- **Successful Extractions:** ${METRICS[successful_extractions]}
- **Failed Extractions:** ${METRICS[failed_extractions]}
- **Timeouts:** ${METRICS[timeouts]}
- **Circuit Breaker Triggers:** ${METRICS[circuit_breaker_triggers]}

### Response Time Metrics
- **Average Response Time:** ${avg_response_time}s
- **Minimum Response Time:** ${METRICS[min_response_time]}s
- **Maximum Response Time:** ${METRICS[max_response_time]}s

### Throughput Metrics
- **Success Rate:** ${success_rate}%
- **Pages per Second:** ${pages_per_second}
- **Efficiency Score:** ${efficiency_score} pages/second/CPU%

### Resource Utilization
- **Average CPU Usage:** ${avg_cpu_usage}%
- **Peak Memory Usage:** $(awk -F',' 'NR>1 {if ($3>max) max=$3} END {print max"MB"}' "$RESULTS_DIR/resources_$TIMESTAMP.log")

## Performance Assessment

EOF

    # Performance assessment
    local assessment="PASS"
    local issues=()
    
    if (( $(echo "$pages_per_second < $TARGET_PAGES_PER_SECOND" | bc -l) )); then
        assessment="FAIL"
        issues+=("Throughput below target: ${pages_per_second}/${TARGET_PAGES_PER_SECOND} pages/second")
    fi
    
    if (( $(echo "$success_rate < 90" | bc -l) )); then
        assessment="FAIL"
        issues+=("Success rate below 90%: ${success_rate}%")
    fi
    
    if (( $(echo "$avg_response_time > $MAX_RESPONSE_TIME" | bc -l) )); then
        assessment="FAIL"
        issues+=("Average response time exceeds limit: ${avg_response_time}s > ${MAX_RESPONSE_TIME}s")
    fi
    
    if [[ ${METRICS[circuit_breaker_triggers]} -gt $((METRICS[total_requests] / 10)) ]]; then
        assessment="FAIL"
        issues+=("Excessive circuit breaker triggers: ${METRICS[circuit_breaker_triggers]}")
    fi
    
    echo "**Overall Assessment:** $assessment" >> "$report_file"
    echo "" >> "$report_file"
    
    if [[ ${#issues[@]} -gt 0 ]]; then
        echo "**Issues Identified:**" >> "$report_file"
        for issue in "${issues[@]}"; do
            echo "- $issue" >> "$report_file"
        done
        echo "" >> "$report_file"
    fi
    
    # Display results
    log_color "${WHITE}===============================================${NC}"
    log_color "${WHITE}INTELLIGENT EXTRACTION PERFORMANCE RESULTS${NC}"
    log_color "${WHITE}===============================================${NC}"
    log_color "${BLUE}Total Requests:${NC} ${METRICS[total_requests]}"
    log_color "${BLUE}Successful Extractions:${NC} ${METRICS[successful_extractions]}"
    log_color "${BLUE}Success Rate:${NC} ${success_rate}%"
    log_color "${BLUE}Pages per Second:${NC} ${pages_per_second}"
    log_color "${BLUE}Average Response Time:${NC} ${avg_response_time}s"
    log_color "${BLUE}Efficiency Score:${NC} ${efficiency_score}"
    
    if [[ "$assessment" == "PASS" ]]; then
        log_color "${GREEN}✅ PERFORMANCE TEST PASSED${NC}"
    else
        log_color "${RED}❌ PERFORMANCE TEST FAILED${NC}"
        for issue in "${issues[@]}"; do
            log_color "${RED}  - $issue${NC}"
        done
    fi
    
    log_color "${CYAN}📄 Full report: $report_file${NC}"
    log_color "${CYAN}📊 Resource data: $RESULTS_DIR/resources_$TIMESTAMP.log${NC}"
    log_color "${CYAN}📋 Task results: $RESULTS_DIR/task_results_$TIMESTAMP.csv${NC}"
    
    return $([[ "$assessment" == "PASS" ]] && echo 0 || echo 1)
}

cleanup_test_environment() {
    log "Cleaning up test environment..."
    
    # Delete test project if created
    if [[ -n "$TEST_PROJECT_ID" && "$TEST_PROJECT_ID" != "test-project-id" ]]; then
        curl -s -X DELETE "$API_BASE_URL/api/v1/projects/$TEST_PROJECT_ID" \
            -H "Authorization: Bearer $JWT_TOKEN" > /dev/null || true
    fi
    
    log "Cleanup completed"
}

main() {
    log_color "${CYAN}🧠 Starting Intelligent Content Extraction Performance Test${NC}"
    log_color "${CYAN}Target: $TARGET_PAGES_PER_SECOND pages/second with $CONCURRENT_EXTRACTIONS concurrent extractions${NC}"
    
    # Setup
    setup_test_environment
    get_jwt_token
    
    # Run test
    run_concurrent_extraction_test
    
    # Analyze results
    if calculate_performance_metrics; then
        cleanup_test_environment
        exit 0
    else
        cleanup_test_environment
        exit 1
    fi
}

# Handle script interruption
trap 'log_color "${YELLOW}Test interrupted by user${NC}"; cleanup_test_environment; exit 130' INT TERM

# Validate dependencies
if ! command -v bc &> /dev/null; then
    log_color "${RED}❌ bc calculator not found - install with: sudo apt-get install bc${NC}"
    exit 1
fi

if ! command -v curl &> /dev/null; then
    log_color "${RED}❌ curl not found - install with: sudo apt-get install curl${NC}"
    exit 1
fi

# Run main test
main

# Usage examples:
# ./test-intelligent-extraction-performance.sh                    # Default: 15 concurrent, 5min duration, 50 pages/s target
# ./test-intelligent-extraction-performance.sh 20 600 75         # 20 concurrent, 10min duration, 75 pages/s target
# ./test-intelligent-extraction-performance.sh 10 300 40 60 200  # Custom configuration with 200 test URLs