# CLAUDE.local.md - Sensitive Information & Local Testing

This file contains sensitive information for local development and testing. **DO NOT COMMIT THIS FILE.**

## Development Credentials

### Test User Credentials
- **Playwright Test User**: `playwright@test.com` / `TestPassword123!` (verified & approved for testing)
- **Superuser**: `admin@chrono-scraper.com` / `changeme` (created automatically)
- **Test User**: `test@example.com` / `testpassword` (created via seed script)

### Database Connection
- **Development**: `postgresql://chrono_scraper:chrono_scraper_dev@localhost:5435/chrono_scraper`

## Playwright Testing - Quick Setup

### Pre-configured Test User
- **Email**: `playwright@test.com` 
- **Password**: `TestPassword123!`
- **Status**: Email verified, approved, and ready for testing
- **Note**: Use UI login (http://localhost:5173/auth/login) - API direct login may have authentication flow differences

## Database Commands

### Create Persistent Test User (Direct Database Creation)
```bash
# Create verified and approved test user directly in database
docker compose exec backend python -c "
import asyncio
from app.core.database import get_db
from app.models.user import User
from app.core.security import get_password_hash
from sqlmodel import select

async def create_test_user():
    async for db in get_db():
        # Check if user already exists
        stmt = select(User).where(User.email == 'playwright@test.com')
        result = await db.execute(stmt)
        existing_user = result.scalar_one_or_none()
        
        if not existing_user:
            user = User(
                email='playwright@test.com',
                full_name='Playwright Test User',
                hashed_password=get_password_hash('TestPassword123!'),
                is_verified=True,
                is_active=True,
                approval_status='approved',
                data_handling_agreement=True,
                ethics_agreement=True,
                research_interests='Automated testing',
                research_purpose='Application testing',
                expected_usage='Testing functionality'
            )
            db.add(user)
            await db.commit()
            print(f'Created test user: {user.email}')
        else:
            print(f'Test user already exists: {existing_user.email}')
        break

asyncio.run(create_test_user())
"
```

### Database User Management Commands
```bash
# Check test user status
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "SELECT email, is_verified, approval_status, is_active FROM users WHERE email = 'playwright@test.com';"

# Approve user if needed
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "UPDATE users SET approval_status = 'approved', approval_date = NOW() WHERE email = 'playwright@test.com';"

# Check any user status
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "SELECT email, is_verified, approval_status, is_active FROM users WHERE email = 'EMAIL_HERE';"

# Direct database access
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper
```

## Test User Creation (Full Flow)

### Method 1: Create New Test User via Frontend
1. **Register new user via frontend:**
   ```
   Email: playwright-test@example.com
   Password: TestPassword123!
   Full Name: Playwright Test User
   Research Interests: Testing application functionality
   ```

2. **Check Mailpit for verification email:**
   - Navigate to: http://localhost:8025
   - Find verification email
   - Click "Verify Email" link

3. **Approve user in database:**
   ```bash
   docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "UPDATE users SET approval_status = 'approved', approval_date = NOW() WHERE email = 'playwright-test@example.com';"
   ```

## Authentication Requirements
- Users must be **both verified AND approved** to login successfully
- **Email verification**: `is_verified = true`
- **Manual approval**: `approval_status = 'approved'` 
- **Active status**: `is_active = true`

## Email Testing with Mailpit
- **Mailpit URL**: http://localhost:8025
- All development emails are captured here
- Use for email verification testing during full registration flow

## Testing Key Pages

### Library Page (`/library`)
- Statistics dashboard (Starred Items, Saved Searches, Collections, Total Items)
- Tab navigation (Starred, Saved Searches, Collections, Recent)
- Search functionality
- Empty state messaging

### Entities Page (`/entities`)
- Entity statistics dashboard (Total Entities, Persons, Organizations, Avg Confidence)
- Advanced filtering system (Entity Type, Status, Confidence level)
- Search functionality
- Create/Link entity actions