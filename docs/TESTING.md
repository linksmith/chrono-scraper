# Testing Documentation

This document provides comprehensive information about testing the Chrono Scraper application.

## Overview

The testing strategy covers multiple layers:
- **Backend Unit Tests**: FastAPI endpoints, models, services
- **Frontend Unit Tests**: Svelte components, stores, utilities
- **Integration Tests**: API flows, database interactions
- **End-to-End Tests**: Complete user workflows with Playwright
- **Security Tests**: Vulnerability scanning, security best practices
- **Performance Tests**: Load testing, response times

## Quick Start

### Prerequisites
```bash
# Install dependencies
make install-dev

# Or install manually
cd backend && pip install -r requirements.txt
cd frontend && npm install
npx playwright install
```

### Running Tests

```bash
# Run all tests
make test

# Run specific test suites
make test-backend
make test-frontend
make test-e2e
make test-security

# Run with Docker (recommended)
make test-docker

# Or use our new Docker-native scripts
./run-all-tests.sh        # Complete test suite
./run-e2e-tests.sh        # E2E tests only with service startup

# Individual Docker test services
docker compose -f docker-compose.test.yml up test-frontend --abort-on-container-exit
docker compose -f docker-compose.test.yml up test-backend --abort-on-container-exit
```

## Test Structure

### Backend Tests (`backend/tests/`)
```
tests/
├── conftest.py              # Test configuration and fixtures
├── test_auth.py             # Authentication tests
├── test_models.py           # Database model tests
├── test_services.py         # Service layer tests
├── test_endpoints/          # API endpoint tests
│   ├── test_auth_endpoints.py
│   ├── test_project_endpoints.py
│   └── ...
├── test_integration/        # Integration tests
│   ├── test_auth_flow.py
│   └── ...
├── test_security/           # Security tests
└── test_performance/        # Performance tests
```

### Frontend Tests (`frontend/src/tests/`)
```
tests/
├── setup.ts                # Test setup and configuration
├── components/              # Component tests
│   ├── auth/
│   │   └── LoginForm.test.ts
│   └── ...
├── stores/                  # Store tests
│   ├── auth.test.ts
│   └── ...
└── utils/                   # Utility tests
```

### E2E Tests (`frontend/tests/e2e/`)
```
e2e/
├── auth.spec.ts            # Authentication flows
├── projects.spec.ts        # Project management
├── search.spec.ts          # Search functionality
└── dashboard.spec.ts       # Dashboard interactions
```

## Test Configuration

### Backend Configuration (`backend/pytest.ini`)
- Coverage threshold: 80%
- Test markers for categorization
- Report formats: HTML, XML, terminal

### Frontend Configuration (`frontend/vitest.config.ts`)
- JSDOM environment
- Coverage reporting
- Global test setup

### E2E Configuration 
- **Local**: `frontend/playwright.config.ts` - Standard configuration for local development
- **Docker**: `frontend/playwright.config.docker.ts` - Docker-optimized configuration with Microsoft's Playwright image
- Multi-browser testing (Chromium, Firefox, Safari)
- Mobile viewport testing
- Video/screenshot on failure
- Docker-compatible browser launching with proper security flags

## Running Tests

### Local Development

#### Backend Tests
```bash
# All backend tests
cd backend && pytest

# Specific test file
cd backend && pytest tests/test_auth.py

# With coverage
cd backend && pytest --cov=app --cov-report=html

# Watch mode
cd backend && pytest-watch

# Debug mode
cd backend && pytest -s --pdb tests/test_auth.py::TestUserLogin::test_login_valid_credentials
```

#### Frontend Tests
```bash
# All frontend tests
cd frontend && npm test

# Watch mode
cd frontend && npm test -- --watch

# Coverage
cd frontend && npm test -- --coverage

# Specific test
cd frontend && npm test -- auth.test.ts
```

#### E2E Tests
```bash
# All E2E tests
cd frontend && npm run test:e2e

# Specific browser
cd frontend && npx playwright test --project=chromium

# Debug mode
cd frontend && npx playwright test --debug

# UI mode
cd frontend && npx playwright test --ui
```

### Docker Testing

#### Full Test Suite
```bash
# Run all tests in Docker
make test-docker

# E2E tests in Docker
make test-docker-e2e
```

#### Individual Services
```bash
# Start test services
docker-compose -f docker-compose.test.yml up -d

# Run backend tests
docker-compose -f docker-compose.test.yml exec test-backend pytest

# Run frontend tests
docker-compose -f docker-compose.test.yml exec test-frontend npm test

# Cleanup
docker-compose -f docker-compose.test.yml down
```

## CI/CD Integration

### GitHub Actions Pipeline (`.github/workflows/test.yml`)

The pipeline includes:
1. **Backend Tests** - Unit, integration, security tests
2. **Frontend Tests** - Component, store, build tests
3. **E2E Tests** - Full user workflow testing
4. **Security Scans** - Bandit, Safety, npm audit
5. **Performance Tests** - Load testing with Locust
6. **Quality Gate** - Coverage and test result validation

### Quality Gates
- Backend coverage ≥ 80%
- Frontend coverage ≥ 80%
- All E2E tests pass
- No high-severity security vulnerabilities
- Performance thresholds met

## Test Data Management

### Test Database
```bash
# Reset test database
make db-test-reset

# Seed test data
make seed-test-data
```

### Fixtures and Mocks
- **Backend**: SQLModel fixtures, mock external APIs
- **Frontend**: Mock stores, API responses
- **E2E**: Test user accounts, sample projects

## Writing Tests

### Backend Test Example
```python
def test_create_project(client: TestClient, auth_headers: dict):
    """Test project creation endpoint."""
    project_data = {
        "name": "Test Project",
        "description": "A test project",
        "config": {"urls": ["https://example.com"]}
    }
    
    response = client.post(
        "/api/v1/projects/",
        json=project_data,
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Project"
```

### Frontend Test Example
```typescript
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import LoginForm from '../LoginForm.svelte';

describe('LoginForm', () => {
  it('validates required fields', async () => {
    render(LoginForm);
    
    const submitButton = screen.getByRole('button', { name: /sign in/i });
    await fireEvent.click(submitButton);
    
    expect(screen.getByText(/email is required/i)).toBeInTheDocument();
  });
});
```

### E2E Test Example
```typescript
import { test, expect } from '@playwright/test';

test('user can login and create project', async ({ page }) => {
  // Login
  await page.goto('/auth/login');
  await page.fill('[data-testid="email-input"]', 'test@example.com');
  await page.fill('[data-testid="password-input"]', 'password123');
  await page.click('[data-testid="login-button"]');
  
  // Create project
  await page.click('[data-testid="nav-projects"]');
  await page.click('[data-testid="create-project-button"]');
  await page.fill('[data-testid="project-name-input"]', 'New Project');
  await page.click('[data-testid="create-project-submit"]');
  
  // Verify creation
  await expect(page.locator('[data-testid="success-message"]')).toBeVisible();
});
```

## Best Practices

### General
- Write descriptive test names
- Use the AAA pattern (Arrange, Act, Assert)
- Keep tests independent and isolated
- Mock external dependencies

### Backend
- Use fixtures for test data
- Test both success and error cases
- Validate HTTP status codes and response structure
- Test authentication and authorization

### Frontend
- Use data-testid attributes for reliable selectors
- Test user interactions, not implementation details
- Mock API calls and external dependencies
- Test accessibility and keyboard navigation

### E2E
- Test critical user paths
- Use page object models for complex flows
- Handle async operations properly
- Take screenshots/videos on failure

## Performance Testing

### Load Testing with Locust
```python
from locust import HttpUser, task, between

class ApiUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def get_projects(self):
        self.client.get("/api/v1/projects/", headers=self.auth_headers)
```

### Performance Metrics
- API response times < 500ms
- Database queries optimized
- Frontend bundle size < 1MB
- Page load times < 2s

## Security Testing

### Automated Scans
- **Bandit**: Python security linting
- **Safety**: Dependency vulnerability checking
- **npm audit**: Node.js dependency scanning

### Manual Testing
- Authentication bypass attempts
- SQL injection testing
- XSS vulnerability testing
- CSRF protection validation

## Debugging Tests

### Backend Debugging
```bash
# Run with debugger
pytest -s --pdb tests/test_auth.py

# Verbose output
pytest -v -s tests/

# Run specific test
pytest tests/test_auth.py::TestUserLogin::test_login_valid_credentials
```

### Frontend Debugging
```bash
# Debug mode
npm test -- --reporter=verbose

# Watch mode with coverage
npm test -- --watch --coverage
```

### E2E Debugging
```bash
# Debug mode (opens browser)
npx playwright test --debug

# Headed mode
npx playwright test --headed

# Trace viewer
npx playwright show-trace trace.zip
```

## Coverage Reports

### Viewing Coverage
```bash
# Generate reports
make coverage

# View in browser
open backend/htmlcov/index.html
open frontend/coverage/index.html
```

### Coverage Targets
- Overall coverage: ≥ 80%
- Critical paths: ≥ 95%
- New code: 100%

## Troubleshooting

### Common Issues

#### Tests Failing in CI but Passing Locally
- Check environment variables
- Verify service dependencies
- Review timing issues

#### Database Connection Errors
```bash
# Check database status
docker-compose ps postgres

# Reset test database
make db-test-reset
```

#### Frontend Test Timeouts
- Increase timeout values
- Check for async operation completion
- Verify mock configurations

#### E2E Test Flakiness
- Add explicit waits
- Use retry mechanisms
- Check for race conditions

### Getting Help
- Check test logs: `make logs`
- Review CI output
- Consult team documentation
- Create GitHub issues for persistent problems

## Contributing

### Adding New Tests
1. Follow existing test structure
2. Add appropriate markers/categories
3. Update documentation
4. Ensure tests pass in CI

### Test Maintenance
- Regular test review and cleanup
- Update mocks when APIs change
- Maintain test data fixtures
- Monitor test execution times

This comprehensive testing framework ensures the reliability, security, and performance of the Chrono Scraper application across all layers of the architecture.