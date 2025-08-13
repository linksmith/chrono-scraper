#!/bin/bash

# Script to run complete E2E tests with all services
echo "🚀 Starting Complete E2E Test Suite"

# Start the test services (backend, frontend, databases)
echo "📦 Starting backend and frontend services..."
docker compose -f docker-compose.test.yml up -d test-backend test-frontend

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check if services are responsive
echo "🔍 Checking service health..."
curl -f http://localhost:8001/health || echo "⚠️  Backend health check failed"
curl -f http://localhost:5174 || echo "⚠️  Frontend health check failed"

# Run E2E tests
echo "🎭 Running Playwright E2E tests..."
docker compose -f docker-compose.test.yml --profile e2e up test-e2e --abort-on-container-exit

# Store exit code
E2E_EXIT_CODE=$?

# Cleanup
echo "🧹 Cleaning up services..."
docker compose -f docker-compose.test.yml down

# Exit with the same code as E2E tests
exit $E2E_EXIT_CODE