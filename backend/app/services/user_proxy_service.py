"""
Service for handling user-specific proxy configurations
"""
import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User
from ..core.config import settings

logger = logging.getLogger(__name__)


class UserProxyService:
    """Service for managing user-specific proxy configurations"""
    
    @staticmethod
    def build_proxy_config(user: User) -> Optional[Dict[str, Any]]:
        """
        Build proxy configuration from user's stored credentials
        
        Args:
            user: User object with proxy credentials
            
        Returns:
            Dictionary with proxy configuration or None if no proxy configured
        """
        if not user.proxy_server or not user.proxy_username or not user.proxy_password:
            logger.debug(f"User {user.id} has incomplete proxy configuration, using system defaults")
            return None
            
        proxy_config = {
            "server": user.proxy_server,
            "username": user.proxy_username,
            "password": user.proxy_password,
            "enabled": True
        }
        
        logger.info(f"Built user-specific proxy config for user {user.id}")
        return proxy_config
    
    @staticmethod
    def get_firecrawl_proxy_env(user: User) -> Dict[str, str]:
        """
        Get environment variables for Firecrawl proxy configuration based on user settings
        
        Args:
            user: User object with proxy credentials
            
        Returns:
            Dictionary of environment variables for Firecrawl
        """
        if not user.proxy_server or not user.proxy_username or not user.proxy_password:
            # Fall back to system proxy settings
            return {
                "PROXY_SERVER": getattr(settings, "FIRECRAWL_PROXY_SERVER", ""),
                "PROXY_USERNAME": getattr(settings, "FIRECRAWL_PROXY_USERNAME", ""), 
                "PROXY_PASSWORD": getattr(settings, "FIRECRAWL_PROXY_PASSWORD", "")
            }
        
        return {
            "PROXY_SERVER": user.proxy_server,
            "PROXY_USERNAME": user.proxy_username,
            "PROXY_PASSWORD": user.proxy_password
        }
    
    @staticmethod
    def has_user_proxy(user: User) -> bool:
        """
        Check if user has complete proxy configuration
        
        Args:
            user: User object to check
            
        Returns:
            True if user has complete proxy configuration, False otherwise
        """
        return bool(
            user.proxy_server and 
            user.proxy_username and 
            user.proxy_password
        )
    
    @staticmethod
    def validate_proxy_config(server: str, username: str, password: str) -> bool:
        """
        Validate proxy configuration format
        
        Args:
            server: Proxy server URL
            username: Proxy username
            password: Proxy password
            
        Returns:
            True if configuration is valid, False otherwise
        """
        if not server or not username or not password:
            return False
            
        # Basic URL validation for server
        if not (server.startswith('http://') or server.startswith('https://')):
            return False
            
        return True