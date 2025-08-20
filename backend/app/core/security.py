"""
Security utilities for password hashing, secure tokens, and API keys
"""
from datetime import datetime, timedelta
from typing import Optional
import secrets
import hashlib
import hmac
from passlib.context import CryptContext
from fastapi import HTTPException, status

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials"
)




def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash a password
    """
    return pwd_context.hash(password)




def generate_password_reset_token(email: str) -> tuple[str, datetime]:
    """
    Generate secure password reset token
    """
    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)
    return token, expires


def verify_password_reset_token(token: str, stored_token: str, expires_at: datetime, email: str) -> bool:
    """
    Verify password reset token
    """
    if datetime.utcnow() > expires_at:
        return False
    return hmac.compare_digest(token, stored_token)


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key and return (key, hash)
    """
    # Generate random key
    key = f"cs_{secrets.token_urlsafe(32)}"
    
    # Hash the key for storage
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    
    return key, key_hash


def verify_api_key(key: str, stored_hash: str) -> bool:
    """
    Verify API key against stored hash
    """
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return hmac.compare_digest(key_hash, stored_hash)


def get_api_key_prefix(key: str) -> str:
    """
    Get the first 8 characters of API key for identification
    """
    return key[:8] if len(key) > 8 else key


def generate_email_verification_token(email: str) -> tuple[str, datetime]:
    """
    Generate secure email verification token
    """
    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)
    return token, expires


def verify_email_verification_token(token: str, stored_token: str, expires_at: datetime) -> bool:
    """
    Verify email verification token
    """
    if datetime.utcnow() > expires_at:
        return False
    return hmac.compare_digest(token, stored_token)