"""
Two-Factor Authentication (2FA) implementation for admin users
Supports TOTP (Time-based One-Time Password) and backup codes
"""
import secrets
import base64
import io
import qrcode
from typing import Optional, List, Tuple, Dict, TYPE_CHECKING
from datetime import datetime, timedelta, timezone
import pyotp
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from passlib.context import CryptContext

from app.core.config import settings

if TYPE_CHECKING:
    from app.models.user import User

# Local password context to avoid circular imports
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """Hash a password"""
    return _pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password"""
    return _pwd_context.verify(plain_password, hashed_password)


class TwoFactorAuth:
    """
    Two-Factor Authentication manager supporting:
    - TOTP (Google Authenticator, Authy, etc.)
    - Backup codes
    - SMS verification (optional)
    - Email verification codes
    """
    
    def __init__(self):
        self.issuer = settings.MFA_ISSUER_NAME
        self.algorithm = settings.MFA_TOTP_ALGORITHM
        self.digits = settings.MFA_TOTP_DIGITS
        self.interval = settings.MFA_TOTP_INTERVAL
    
    async def generate_secret(self, user_email: str) -> Tuple[str, str, str]:
        """
        Generate a new TOTP secret for user
        Returns: (secret, provisioning_uri, qr_code_base64)
        """
        # Generate random secret
        secret = pyotp.random_base32()
        
        # Create TOTP instance
        totp = pyotp.TOTP(
            secret,
            issuer=self.issuer,
            digits=self.digits,
            interval=self.interval,
            digest=self._get_digest_func()
        )
        
        # Generate provisioning URI for QR code
        provisioning_uri = totp.provisioning_uri(
            name=user_email,
            issuer_name=self.issuer
        )
        
        # Generate QR code
        qr_code_base64 = self._generate_qr_code(provisioning_uri)
        
        return secret, provisioning_uri, qr_code_base64
    
    def _get_digest_func(self):
        """Get digest function based on algorithm setting"""
        import hashlib
        algorithm_map = {
            "SHA1": hashlib.sha1,
            "SHA256": hashlib.sha256,
            "SHA512": hashlib.sha512
        }
        return algorithm_map.get(self.algorithm, hashlib.sha256)
    
    def _generate_qr_code(self, data: str) -> str:
        """Generate QR code as base64 encoded image"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return base64.b64encode(buffer.getvalue()).decode()
    
    def verify_totp(self, secret: str, token: str, window: int = 1) -> bool:
        """
        Verify TOTP token
        Args:
            secret: User's TOTP secret
            token: 6-digit token from authenticator app
            window: Time window tolerance (default 1 = ±30 seconds)
        """
        if not secret or not token:
            return False
        
        try:
            totp = pyotp.TOTP(
                secret,
                issuer=self.issuer,
                digits=self.digits,
                interval=self.interval,
                digest=self._get_digest_func()
            )
            
            # Verify with time window tolerance
            return totp.verify(token, valid_window=window)
        except Exception as e:
            print(f"TOTP verification error: {e}")
            return False
    
    def generate_backup_codes(self, count: int = None) -> List[str]:
        """Generate backup codes for account recovery"""
        count = count or settings.MFA_BACKUP_CODES_COUNT
        codes = []
        
        for _ in range(count):
            # Generate 8-character alphanumeric codes
            code = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8))
            # Format as XXXX-XXXX for readability
            formatted_code = f"{code[:4]}-{code[4:]}"
            codes.append(formatted_code)
        
        return codes
    
    def hash_backup_code(self, code: str) -> str:
        """Hash backup code for storage"""
        # Remove formatting
        clean_code = code.replace('-', '').upper()
        return get_password_hash(clean_code)
    
    def verify_backup_code(self, code: str, hashed_code: str) -> bool:
        """Verify backup code against hash"""
        # Remove formatting
        clean_code = code.replace('-', '').upper()
        return verify_password(clean_code, hashed_code)
    
    async def generate_email_code(self) -> Tuple[str, datetime]:
        """
        Generate email verification code
        Returns: (code, expiry_time)
        """
        # Generate 6-digit numeric code
        code = ''.join(secrets.choice('0123456789') for _ in range(6))
        expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
        
        return code, expiry
    
    async def generate_sms_code(self) -> Tuple[str, datetime]:
        """
        Generate SMS verification code
        Returns: (code, expiry_time)
        """
        # Generate 6-digit numeric code
        code = ''.join(secrets.choice('0123456789') for _ in range(6))
        expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        return code, expiry


class TwoFactorService:
    """Service for managing 2FA operations with database"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.auth = TwoFactorAuth()
    
    async def enable_2fa(self, user_id: int) -> Dict[str, any]:
        """Enable 2FA for user and return setup data"""
        # Import User model dynamically to avoid circular imports
        from app.models.user import User
        
        # Get user
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError("User not found")
        
        # Generate secret and QR code
        secret, provisioning_uri, qr_code = await self.auth.generate_secret(user.email)
        
        # Generate backup codes
        backup_codes = self.auth.generate_backup_codes()
        hashed_backup_codes = [self.auth.hash_backup_code(code) for code in backup_codes]
        
        # Store in user model (you'll need to add these fields)
        user.mfa_secret = secret
        user.mfa_backup_codes = hashed_backup_codes
        user.mfa_enabled = False  # Will be enabled after first successful verification
        user.mfa_enabled_at = None
        
        await self.db.commit()
        
        return {
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "qr_code": qr_code,
            "backup_codes": backup_codes,
            "instructions": self._get_setup_instructions()
        }
    
    async def verify_and_enable_2fa(self, user_id: int, token: str) -> bool:
        """Verify token and enable 2FA if successful"""
        # Import User model dynamically to avoid circular imports
        from app.models.user import User
        
        # Get user
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user or not user.mfa_secret:
            return False
        
        # Verify token
        if self.auth.verify_totp(user.mfa_secret, token):
            # Enable 2FA
            user.mfa_enabled = True
            user.mfa_enabled_at = datetime.now(timezone.utc)
            await self.db.commit()
            return True
        
        return False
    
    async def disable_2fa(self, user_id: int, password: str) -> bool:
        """Disable 2FA for user (requires password verification)"""
        # Import User model dynamically to avoid circular imports
        from app.models.user import User
        
        # Get user
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return False
        
        # Verify password
        if not verify_password(password, user.hashed_password):
            return False
        
        # Disable 2FA
        user.mfa_enabled = False
        user.mfa_secret = None
        user.mfa_backup_codes = []
        user.mfa_enabled_at = None
        
        await self.db.commit()
        return True
    
    async def verify_2fa_token(self, user_id: int, token: str) -> Tuple[bool, str]:
        """
        Verify 2FA token for user
        Returns: (success, method_used)
        """
        # Import User model dynamically to avoid circular imports
        from app.models.user import User
        
        # Get user
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user or not user.mfa_enabled:
            return False, "not_enabled"
        
        # Try TOTP verification first
        if user.mfa_secret and self.auth.verify_totp(user.mfa_secret, token):
            # Update last used time
            user.mfa_last_used = datetime.now(timezone.utc)
            await self.db.commit()
            return True, "totp"
        
        # Try backup code verification
        if user.mfa_backup_codes:
            for i, hashed_code in enumerate(user.mfa_backup_codes):
                if self.auth.verify_backup_code(token, hashed_code):
                    # Remove used backup code
                    user.mfa_backup_codes.pop(i)
                    user.mfa_last_used = datetime.now(timezone.utc)
                    await self.db.commit()
                    return True, "backup_code"
        
        # Try email code if exists and not expired
        if hasattr(user, 'mfa_email_code') and user.mfa_email_code:
            if user.mfa_email_code_expiry > datetime.now(timezone.utc):
                if token == user.mfa_email_code:
                    # Clear used code
                    user.mfa_email_code = None
                    user.mfa_email_code_expiry = None
                    user.mfa_last_used = datetime.now(timezone.utc)
                    await self.db.commit()
                    return True, "email"
        
        return False, "invalid"
    
    async def regenerate_backup_codes(self, user_id: int, password: str) -> Optional[List[str]]:
        """Regenerate backup codes (requires password)"""
        # Import User model dynamically to avoid circular imports
        from app.models.user import User
        
        # Get user
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user or not user.mfa_enabled:
            return None
        
        # Verify password
        if not verify_password(password, user.hashed_password):
            return None
        
        # Generate new backup codes
        backup_codes = self.auth.generate_backup_codes()
        hashed_backup_codes = [self.auth.hash_backup_code(code) for code in backup_codes]
        
        # Update user
        user.mfa_backup_codes = hashed_backup_codes
        await self.db.commit()
        
        return backup_codes
    
    async def send_email_code(self, user_id: int) -> bool:
        """Send 2FA code via email"""
        if not settings.MFA_EMAIL_ENABLED:
            return False
        
        # Import User model dynamically to avoid circular imports
        from app.models.user import User
        
        # Get user
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user or not user.mfa_enabled:
            return False
        
        # Generate code
        code, expiry = await self.auth.generate_email_code()
        
        # Store in user model
        user.mfa_email_code = code
        user.mfa_email_code_expiry = expiry
        await self.db.commit()
        
        # Send email (integrate with your email service)
        # await send_2fa_email(user.email, code)
        
        return True
    
    async def check_2fa_required(self, user_id: int) -> bool:
        """Check if 2FA is required for user"""
        # Import User model dynamically to avoid circular imports
        from app.models.user import User
        
        # Get user
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return False
        
        # Check if user is admin/superuser
        if user.is_superuser and settings.ADMIN_REQUIRE_2FA:
            return True
        
        # Check if 2FA is enabled for user
        return user.mfa_enabled if hasattr(user, 'mfa_enabled') else False
    
    def _get_setup_instructions(self) -> Dict[str, str]:
        """Get 2FA setup instructions"""
        return {
            "step1": "Install an authenticator app on your phone (Google Authenticator, Authy, Microsoft Authenticator)",
            "step2": "Scan the QR code with your authenticator app",
            "step3": "Enter the 6-digit code from your app to verify",
            "step4": "Save the backup codes in a secure location",
            "warning": "If you lose access to your authenticator app and backup codes, you will be locked out of your account"
        }


class TwoFactorMiddleware:
    """Middleware to enforce 2FA for admin users"""
    
    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
    
    async def __call__(self, request, call_next):
        """Check 2FA requirement for admin routes"""
        # Only check admin routes
        if request.url.path.startswith("/admin") or request.url.path.startswith("/api/v1/admin"):
            # Check if user is authenticated
            if hasattr(request.state, "user") and request.state.user:
                user = request.state.user
                
                # Check if 2FA is required but not completed
                if user.is_superuser and settings.ADMIN_REQUIRE_2FA:
                    # Check session for 2FA verification
                    if not getattr(request.state, "mfa_verified", False):
                        # Allow access to 2FA verification endpoints
                        if not request.url.path.endswith("/2fa/verify"):
                            from fastapi import HTTPException
                            raise HTTPException(
                                status_code=401,
                                detail="2FA verification required",
                                headers={"X-2FA-Required": "true"}
                            )
        
        response = await call_next(request)
        return response