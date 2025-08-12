"""
User service functions
"""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from fastapi import HTTPException, status

from app.models.user import User, UserCreate, UserUpdate
from app.core.security import (
    get_password_hash, 
    verify_password, 
    generate_email_verification_token,
    generate_password_reset_token
)


class UserService:
    """User service class"""
    
    @staticmethod
    async def create_user(db: AsyncSession, user_create: UserCreate) -> User:
        """Create a new user"""
        # Check if user already exists
        result = await db.execute(select(User).where(User.email == user_create.email))
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Create user
        user = User(
            email=user_create.email,
            full_name=user_create.full_name,
            hashed_password=get_password_hash(user_create.password),
            institutional_email=user_create.institutional_email,
            linkedin_profile=user_create.linkedin_profile,
            research_interests=user_create.research_interests,
            academic_affiliation=user_create.academic_affiliation,
            email_verification_token=generate_email_verification_token(user_create.email)
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        return user
    
    @staticmethod
    async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password"""
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        
        if not verify_password(password, user.hashed_password):
            return None
        
        # Update login stats
        user.last_login = datetime.utcnow()
        user.login_count += 1
        db.add(user)
        await db.commit()
        
        return user
    
    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """Get user by ID"""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email"""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def update_user(db: AsyncSession, user: User, user_update: UserUpdate) -> User:
        """Update user information"""
        update_data = user_update.model_dump(exclude_unset=True)
        
        # Handle password update separately
        if "password" in update_data:
            password = update_data.pop("password")
            user.hashed_password = get_password_hash(password)
        
        # Update other fields
        for field, value in update_data.items():
            setattr(user, field, value)
        
        user.updated_at = datetime.utcnow()
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        return user
    
    @staticmethod
    async def verify_email(db: AsyncSession, token: str) -> bool:
        """Verify user email with token"""
        from app.core.security import verify_email_verification_token
        
        email = verify_email_verification_token(token)
        if not email:
            return False
        
        result = await db.execute(
            select(User).where(
                User.email == email,
                User.email_verification_token == token
            )
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return False
        
        # Mark as verified
        user.is_verified = True
        user.email_verification_token = None
        user.updated_at = datetime.utcnow()
        
        db.add(user)
        await db.commit()
        
        return True
    
    @staticmethod
    async def request_password_reset(db: AsyncSession, email: str) -> bool:
        """Request password reset for user"""
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if not user:
            # Don't reveal that user doesn't exist
            return True
        
        # Generate reset token
        reset_token = generate_password_reset_token(email)
        user.password_reset_token = reset_token
        user.password_reset_expires = datetime.utcnow() + timedelta(hours=24)
        user.updated_at = datetime.utcnow()
        
        db.add(user)
        await db.commit()
        
        # TODO: Send email with reset token
        
        return True
    
    @staticmethod
    async def reset_password(db: AsyncSession, token: str, new_password: str) -> bool:
        """Reset user password with token"""
        from app.core.security import verify_password_reset_token
        
        email = verify_password_reset_token(token)
        if not email:
            return False
        
        result = await db.execute(
            select(User).where(
                User.email == email,
                User.password_reset_token == token,
                User.password_reset_expires > datetime.utcnow()
            )
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return False
        
        # Update password
        user.hashed_password = get_password_hash(new_password)
        user.password_reset_token = None
        user.password_reset_expires = None
        user.updated_at = datetime.utcnow()
        
        db.add(user)
        await db.commit()
        
        return True
    
    @staticmethod
    async def approve_user(db: AsyncSession, user_id: int, approved_by_id: int) -> bool:
        """Approve a user account"""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            return False
        
        user.approval_status = "approved"
        user.approval_date = datetime.utcnow()
        user.approved_by_id = approved_by_id
        user.updated_at = datetime.utcnow()
        
        db.add(user)
        await db.commit()
        
        return True
    
    @staticmethod
    async def reject_user(db: AsyncSession, user_id: int, approved_by_id: int) -> bool:
        """Reject a user account"""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            return False
        
        user.approval_status = "rejected"
        user.approval_date = datetime.utcnow()
        user.approved_by_id = approved_by_id
        user.updated_at = datetime.utcnow()
        
        db.add(user)
        await db.commit()
        
        return True