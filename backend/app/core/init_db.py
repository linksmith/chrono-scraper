"""
Database initialization functions
"""
import asyncio
from sqlmodel import select

from app.core.database import AsyncSessionLocal, init_db as init_database
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User
from app.services.rbac import RBACService, DefaultRole


async def create_superuser() -> None:
    """Create the first superuser"""
    try:
        async with AsyncSessionLocal() as session:
            # Check if superuser already exists
            result = await session.execute(
                select(User).where(User.email == settings.FIRST_SUPERUSER)
            )
            user = result.scalar_one_or_none()
            
            if user:
                print(f"Superuser {settings.FIRST_SUPERUSER} already exists")
                return
            
            # Create superuser
            user = User(
                email=settings.FIRST_SUPERUSER,
                hashed_password=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
                full_name="System Administrator",
                is_superuser=True,
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            print(f"Superuser {settings.FIRST_SUPERUSER} created successfully")
            
            # Try to assign super admin role, but don't fail if RBAC isn't ready
            try:
                await RBACService.assign_default_role_to_user(session, user, DefaultRole.SUPER_ADMIN)
                print("Super admin role assigned successfully")
            except Exception as rbac_error:
                print(f"Warning: Could not assign super admin role: {rbac_error}")
                print("You can assign roles manually later")
                
    except Exception as e:
        print(f"Error creating superuser: {e}")
        print("Please check your database configuration and try again")


async def seed_database() -> None:
    """Seed database with sample data"""
    async with AsyncSessionLocal() as session:
        # Create sample users for testing
        test_users = [
            {
                "email": "test@example.com",
                "password": "testpassword",
                "full_name": "Test User",
                "is_verified": True,
                "approval_status": "approved"
            },
            {
                "email": "pending@example.com", 
                "password": "testpassword",
                "full_name": "Pending User",
                "is_verified": True,
                "approval_status": "pending"
            }
        ]
        
        for user_data in test_users:
            # Check if user exists
            result = await session.execute(
                select(User).where(User.email == user_data["email"])
            )
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                continue
            
            # Create user
            password = user_data.pop("password")
            user = User(
                **user_data,
                hashed_password=get_password_hash(password)
            )
            
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            # Assign researcher role to test users
            await RBACService.assign_default_role_to_user(session, user, DefaultRole.RESEARCHER)
        
        print("Sample users created successfully")


async def init_db() -> None:
    """Initialize database tables"""
    await init_database()
    
    # Initialize RBAC system
    async with AsyncSessionLocal() as session:
        await RBACService.initialize_default_roles(session)
    print("RBAC system initialized")
    
    await create_superuser()
    print("Database tables initialized and superuser created")


def run_create_superuser():
    """CLI function to create superuser"""
    asyncio.run(create_superuser())


def run_seed_database():
    """CLI function to seed database"""
    asyncio.run(seed_database())


def run_init_db():
    """CLI function to initialize database"""
    asyncio.run(init_db())