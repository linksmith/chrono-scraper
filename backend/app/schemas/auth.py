"""
Authentication schemas for Chrono Scraper
"""
from typing import Optional
from pydantic import BaseModel, EmailStr


class Token(BaseModel):
    """JWT Token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: int
    email: str


class TokenData(BaseModel):
    """Token data for JWT validation"""
    user_id: Optional[int] = None


class LoginRequest(BaseModel):
    """User login request"""
    email: EmailStr
    password: str
    remember_me: bool = False


class OAuth2LoginRequest(BaseModel):
    """OAuth2 login request"""
    provider: str
    redirect_uri: Optional[str] = None


class OAuth2LoginResponse(BaseModel):
    """OAuth2 login response"""
    authorization_url: str
    state: str


class OAuth2CallbackRequest(BaseModel):
    """OAuth2 callback request"""
    provider: str
    code: str
    state: str


class PasswordResetRequest(BaseModel):
    """Password reset request"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation"""
    token: str
    new_password: str


class EmailVerificationRequest(BaseModel):
    """Email verification request"""
    email: EmailStr


class EmailVerificationConfirm(BaseModel):
    """Email verification confirmation"""
    token: str


class SessionInfo(BaseModel):
    """Session information"""
    session_id: str
    user_id: int
    email: str
    created_at: str
    expires_at: str
    is_active: bool


class LoginResponse(BaseModel):
    """Login response with user and token info"""
    access_token: str
    token_type: str
    expires_in: int
    user: dict  # UserRead from user schemas
    session_id: str