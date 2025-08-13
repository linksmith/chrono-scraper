#!/bin/bash

# Complete test suite runner
echo "🧪 Starting Complete Test Suite"

# Track overall success
OVERALL_SUCCESS=true

echo ""
echo "=================================="
echo "📱 Running Frontend Tests"
echo "=================================="
docker compose -f docker-compose.test.yml up test-frontend --abort-on-container-exit
FRONTEND_EXIT=$?
if [ $FRONTEND_EXIT -ne 0 ]; then
    echo "❌ Frontend tests failed"
    OVERALL_SUCCESS=false
else
    echo "✅ Frontend tests passed"
fi

echo ""
echo "=================================="
echo "🖥️  Running Backend Tests" 
echo "=================================="
docker compose -f docker-compose.test.yml up test-backend --abort-on-container-exit
BACKEND_EXIT=$?
if [ $BACKEND_EXIT -ne 0 ]; then
    echo "❌ Backend tests failed"
    OVERALL_SUCCESS=false
else
    echo "✅ Backend tests passed"
fi

echo ""
echo "=================================="
echo "🎭 Running E2E Tests"
echo "=================================="
./run-e2e-tests.sh
E2E_EXIT=$?
if [ $E2E_EXIT -ne 0 ]; then
    echo "❌ E2E tests failed"
    OVERALL_SUCCESS=false
else
    echo "✅ E2E tests passed"
fi

echo ""
echo "=================================="
echo "📊 Test Results Summary"
echo "=================================="
echo "Frontend Tests: $([ $FRONTEND_EXIT -eq 0 ] && echo "✅ PASS" || echo "❌ FAIL")"
echo "Backend Tests:  $([ $BACKEND_EXIT -eq 0 ] && echo "✅ PASS" || echo "❌ FAIL")"
echo "E2E Tests:      $([ $E2E_EXIT -eq 0 ] && echo "✅ PASS" || echo "❌ FAIL")"
echo ""

if [ "$OVERALL_SUCCESS" = true ]; then
    echo "🎉 All tests passed!"
    exit 0
else
    echo "💥 Some tests failed!"
    exit 1
fi