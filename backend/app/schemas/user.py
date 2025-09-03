"""
User schemas - keeping for compatibility and additional schemas
"""
from pydantic import BaseModel, EmailStr


class Message(BaseModel):
    """Generic message schema"""
    message: str


class UserLogin(BaseModel):
    """User login schema"""
    email: EmailStr
    password: str


class PasswordReset(BaseModel):
    """Password reset schema"""
    token: str
    new_password: str


class EmailVerification(BaseModel):
    """Email verification schema"""
    token: str