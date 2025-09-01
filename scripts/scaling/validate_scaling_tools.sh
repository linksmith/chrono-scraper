#!/bin/bash
set -euo pipefail

# Validation script for scaling tools
# Tests that all scaling components are properly configured

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local test_name="$1"
    local test_command="$2"
    
    log "Testing: $test_name"
    
    if eval "$test_command" >/dev/null 2>&1; then
        success "$test_name"
        ((TESTS_PASSED++))
    else
        error "$test_name"
        ((TESTS_FAILED++))
    fi
}

log "🧪 Validating Chrono Scraper v2 Scaling Tools"
echo

# Test 1: Check required Python packages
log "Testing Python dependencies..."
run_test "psutil package" "python3 -c 'import psutil'"
run_test "docker package" "python3 -c 'import docker'"
run_test "requests package" "python3 -c 'import requests'"
run_test "asyncio package" "python3 -c 'import asyncio'"
run_test "asyncpg package" "python3 -c 'import asyncpg'" || warning "asyncpg not available - database metrics will be limited"
run_test "redis package" "python3 -c 'import redis'" || warning "redis package not available - cache metrics will be limited"

echo

# Test 2: Check script files exist and are executable
log "Testing script files..."
run_test "scaling_decision.py exists" "test -f '$SCRIPT_DIR/scaling_decision.py'"
run_test "scaling_decision.py executable" "test -x '$SCRIPT_DIR/scaling_decision.py'"
run_test "cost_optimizer.py exists" "test -f '$SCRIPT_DIR/cost_optimizer.py'"  
run_test "cost_optimizer.py executable" "test -x '$SCRIPT_DIR/cost_optimizer.py'"
run_test "migrate_phase.sh exists" "test -f '$SCRIPT_DIR/migrate_phase.sh'"
run_test "migrate_phase.sh executable" "test -x '$SCRIPT_DIR/migrate_phase.sh'"

echo

# Test 3: Check deployment scripts
log "Testing deployment scripts..."
run_test "phase1_single_server.sh exists" "test -f '$SCRIPT_DIR/../deploy/phase1_single_server.sh'"
run_test "phase1_single_server.sh executable" "test -x '$SCRIPT_DIR/../deploy/phase1_single_server.sh'"

echo

# Test 4: Check monitoring scripts
log "Testing monitoring scripts..."
run_test "scaling_dashboard.py exists" "test -f '$SCRIPT_DIR/../monitoring/scaling_dashboard.py'"
run_test "scaling_dashboard.py executable" "test -x '$SCRIPT_DIR/../monitoring/scaling_dashboard.py'"

echo

# Test 5: Test basic script functionality (dry run)
log "Testing script functionality..."

# Test scaling decision tool
if python3 "$SCRIPT_DIR/scaling_decision.py" --help >/dev/null 2>&1; then
    success "scaling_decision.py help works"
    ((TESTS_PASSED++))
else
    error "scaling_decision.py help failed"
    ((TESTS_FAILED++))
fi

# Test cost optimizer
if python3 "$SCRIPT_DIR/cost_optimizer.py" --help >/dev/null 2>&1; then
    success "cost_optimizer.py help works"
    ((TESTS_PASSED++))
else
    error "cost_optimizer.py help failed"
    ((TESTS_FAILED++))
fi

# Test migration script
if "$SCRIPT_DIR/migrate_phase.sh" --help >/dev/null 2>&1; then
    success "migrate_phase.sh help works"
    ((TESTS_PASSED++))
else
    error "migrate_phase.sh help failed"
    ((TESTS_FAILED++))
fi

echo

# Test 6: Check required external tools
log "Testing external dependencies..."
run_test "docker command" "command -v docker"
run_test "docker compose command" "command -v docker && docker compose version"
run_test "curl command" "command -v curl"
run_test "jq command" "command -v jq" || warning "jq not found - JSON processing will be limited"
run_test "psql command" "command -v psql" || warning "psql not found - database operations will be limited"

echo

# Test 7: Check Docker environment
log "Testing Docker environment..."
if docker info >/dev/null 2>&1; then
    success "Docker daemon is running"
    ((TESTS_PASSED++))
else
    error "Docker daemon is not running or accessible"
    ((TESTS_FAILED++))
fi

if docker compose ps >/dev/null 2>&1; then
    success "Docker Compose is functional"
    ((TESTS_PASSED++))
else
    warning "Docker Compose not running - some tests may be limited"
    ((TESTS_FAILED++))
fi

echo

# Test 8: Check environment configuration
log "Testing environment configuration..."
if test -f "$PROJECT_DIR/.env"; then
    success ".env file exists"
    ((TESTS_PASSED++))
else
    warning ".env file not found - create from .env.example"
    ((TESTS_FAILED++))
fi

if test -f "$PROJECT_DIR/docker-compose.yml"; then
    success "docker-compose.yml exists"
    ((TESTS_PASSED++))
else
    error "docker-compose.yml not found"
    ((TESTS_FAILED++))
fi

echo

# Test 9: Test Makefile targets
log "Testing Makefile targets..."
cd "$PROJECT_DIR"

# Test if Makefile has scaling targets
if grep -q "scaling-analyze:" Makefile; then
    success "Makefile has scaling targets"
    ((TESTS_PASSED++))
else
    error "Makefile missing scaling targets"
    ((TESTS_FAILED++))
fi

if grep -q "cost-optimize:" Makefile; then
    success "Makefile has cost optimization targets"
    ((TESTS_PASSED++))
else
    error "Makefile missing cost optimization targets"
    ((TESTS_FAILED++))
fi

echo

# Test 10: Simulate scaling analysis (if services are running)
log "Testing scaling analysis (if services available)..."
if curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; then
    log "Backend is running - testing metrics collection"
    
    if python3 "$SCRIPT_DIR/scaling_decision.py" --current-phase=1 --format=json >/dev/null 2>&1; then
        success "Scaling analysis with live metrics works"
        ((TESTS_PASSED++))
    else
        warning "Scaling analysis failed - check dependencies"
        ((TESTS_FAILED++))
    fi
else
    warning "Backend not running - skipping live metrics test"
    warning "Start services with 'make up' to test live metrics"
fi

echo

# Summary
log "🏁 Test Summary"
echo
success "Tests passed: $TESTS_PASSED"
if [ $TESTS_FAILED -gt 0 ]; then
    error "Tests failed: $TESTS_FAILED"
    echo
    warning "Some scaling tools may not work properly. Check the failed tests above."
else
    echo
    success "🎉 All tests passed! Scaling tools are ready to use."
fi

echo
log "Next steps:"
echo "  1. Start services: make up"
echo "  2. Run scaling analysis: make scaling-analyze"
echo "  3. View scaling dashboard: make scaling-dashboard"
echo "  4. Check current costs: make cost-current"

# Exit with error code if any tests failed
exit $TESTS_FAILED