"""
Redis-based session storage for persistent authentication
"""
import json
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import redis.asyncio as redis
from pydantic import BaseModel

from app.core.config import settings


class SessionData(BaseModel):
    """Session data structure"""
    user_id: int
    email: str
    username: str
    is_active: bool
    is_verified: bool
    is_admin: bool
    is_superuser: bool
    approval_status: str
    created_at: datetime
    last_activity: datetime


class SessionStore:
    """Redis-based session storage service"""
    
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.session_prefix = "session:"
        self.default_ttl = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Convert to seconds
    
    async def get_redis(self) -> redis.Redis:
        """Get Redis connection"""
        if self.redis is None:
            self.redis = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
        return self.redis
    
    async def close(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
    
    def generate_session_id(self) -> str:
        """Generate a secure session ID"""
        return f"sess_{secrets.token_urlsafe(32)}"
    
    async def create_session(
        self, 
        user_data: Dict[str, Any], 
        ttl_seconds: Optional[int] = None
    ) -> str:
        """
        Create a new session and return session ID
        """
        session_id = self.generate_session_id()
        redis_client = await self.get_redis()
        
        # Prepare session data
        session_data = SessionData(
            user_id=user_data["id"],
            email=user_data["email"],
            username=user_data["username"],
            is_active=user_data["is_active"],
            is_verified=user_data["is_verified"],
            is_admin=user_data.get("is_admin", False),
            is_superuser=user_data.get("is_superuser", False),
            approval_status=user_data.get("approval_status", "pending"),
            created_at=datetime.utcnow(),
            last_activity=datetime.utcnow()
        )
        
        # Store in Redis with TTL
        key = f"{self.session_prefix}{session_id}"
        ttl = ttl_seconds or self.default_ttl
        
        await redis_client.setex(
            key,
            ttl,
            session_data.model_dump_json()
        )
        
        return session_id
    
    async def get_session(self, session_id: str) -> Optional[SessionData]:
        """
        Get session data by session ID
        """
        if not session_id or not session_id.startswith("sess_"):
            return None
        
        redis_client = await self.get_redis()
        key = f"{self.session_prefix}{session_id}"
        
        session_json = await redis_client.get(key)
        if not session_json:
            return None
        
        try:
            session_data = SessionData.model_validate_json(session_json)
            
            # Update last activity
            session_data.last_activity = datetime.utcnow()
            await redis_client.setex(
                key,
                self.default_ttl,
                session_data.model_dump_json()
            )
            
            return session_data
        except Exception:
            # Invalid session data, delete it
            await redis_client.delete(key)
            return None
    
    async def update_session(
        self, 
        session_id: str, 
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update session data
        """
        session_data = await self.get_session(session_id)
        if not session_data:
            return False
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(session_data, key):
                setattr(session_data, key, value)
        
        session_data.last_activity = datetime.utcnow()
        
        # Save back to Redis
        redis_client = await self.get_redis()
        redis_key = f"{self.session_prefix}{session_id}"
        
        await redis_client.setex(
            redis_key,
            self.default_ttl,
            session_data.model_dump_json()
        )
        
        return True
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session
        """
        if not session_id:
            return False
        
        redis_client = await self.get_redis()
        key = f"{self.session_prefix}{session_id}"
        
        result = await redis_client.delete(key)
        return result > 0
    
    async def extend_session(
        self, 
        session_id: str, 
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Extend session TTL
        """
        redis_client = await self.get_redis()
        key = f"{self.session_prefix}{session_id}"
        
        # Check if session exists
        if not await redis_client.exists(key):
            return False
        
        # Extend TTL
        ttl = ttl_seconds or self.default_ttl
        await redis_client.expire(key, ttl)
        
        return True
    
    async def get_user_sessions(self, user_id: int) -> list[str]:
        """
        Get all session IDs for a user
        """
        redis_client = await self.get_redis()
        pattern = f"{self.session_prefix}*"
        
        session_ids = []
        async for key in redis_client.scan_iter(match=pattern):
            session_json = await redis_client.get(key)
            if session_json:
                try:
                    session_data = SessionData.model_validate_json(session_json)
                    if session_data.user_id == user_id:
                        session_id = key.replace(self.session_prefix, "")
                        session_ids.append(session_id)
                except Exception:
                    continue
        
        return session_ids
    
    async def delete_user_sessions(self, user_id: int) -> int:
        """
        Delete all sessions for a user (useful for logout all devices)
        """
        session_ids = await self.get_user_sessions(user_id)
        
        deleted_count = 0
        for session_id in session_ids:
            if await self.delete_session(session_id):
                deleted_count += 1
        
        return deleted_count
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Cleanup expired sessions (Redis handles this automatically with TTL,
        but this can be used for additional cleanup if needed)
        """
        redis_client = await self.get_redis()
        pattern = f"{self.session_prefix}*"
        
        cleaned_count = 0
        async for key in redis_client.scan_iter(match=pattern):
            ttl = await redis_client.ttl(key)
            if ttl == -2:  # Key doesn't exist
                cleaned_count += 1
        
        return cleaned_count


# Global session store instance
session_store = SessionStore()


async def get_session_store() -> SessionStore:
    """Dependency to get session store"""
    return session_store