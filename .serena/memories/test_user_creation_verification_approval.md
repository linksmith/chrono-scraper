# Test User Creation, Verification and Approval Instructions

## Quick Test User Setup for Playwright Testing

### Method 1: Create New Test User (Full Flow)
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

### Method 2: Create Persistent Test User (Direct Database)
```bash
# Create verified and approved test user directly
docker compose exec backend python -c "
import asyncio
from app.core.database import get_db
from app.models.user import User
from app.core.security import get_password_hash
from sqlmodel import Session

async def create_test_user():
    async for db in get_db():
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
        break

asyncio.run(create_test_user())
"
```

### Login Credentials for Testing
- **Email:** `playwright@test.com`
- **Password:** `TestPassword123!`

### Authentication Requirements
- Users must be **both verified AND approved** to login
- `is_verified = true` (email verification)
- `approval_status = 'approved'` (manual approval)
- `is_active = true` (account active)

### Mailpit Access
- **URL:** http://localhost:8025
- All development emails are captured here
- Use for email verification testing

### Database User Status Check
```bash
docker compose exec postgres psql -U chrono_scraper -d chrono_scraper -c "SELECT email, is_verified, approval_status, is_active FROM users WHERE email = 'playwright@test.com';"
```