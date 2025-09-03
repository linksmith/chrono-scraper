"""
Service for handling user-specific scraping with proxy configuration
"""
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User
from ..services.user_proxy_service import UserProxyService
from ..services.content_extraction_service import ContentExtractionService

logger = logging.getLogger(__name__)


class UserScrapingService:
    """Service for user-specific scraping with proxy configuration"""
    
    @staticmethod
    async def get_user_content_extractor(user: User) -> ContentExtractionService:
        """
        Get a ContentExtractionService for the user
        
        Note: User-specific proxy settings are no longer needed with intelligent extraction
        as it fetches content directly from web.archive.org which doesn't require proxies.
        
        Args:
            user: User object (kept for compatibility)
            
        Returns:
            ContentExtractionService instance
        """
        from ..services.content_extraction_service import get_content_extraction_service
        
        # Log if user had proxy settings (for migration awareness)
        if UserProxyService.has_user_proxy(user):
            logger.info(f"User {user.id} has proxy settings which are no longer needed "
                       "with intelligent extraction (fetches from web.archive.org directly)")
        
        return get_content_extraction_service()
    
    @staticmethod
    async def get_user_firecrawl_extractor(user: User) -> ContentExtractionService:
        """
        Compatibility alias for legacy code
        
        Args:
            user: User object
            
        Returns:
            ContentExtractionService instance
        """
        logger.warning("get_user_firecrawl_extractor() is deprecated. "
                      "Use get_user_content_extractor() instead.")
        return await UserScrapingService.get_user_content_extractor(user)
    
    @staticmethod
    def get_user_proxy_status(user: User) -> dict:
        """
        Get user proxy configuration status
        
        Args:
            user: User object to check
            
        Returns:
            Dictionary with proxy status information
        """
        has_proxy = UserProxyService.has_user_proxy(user)
        
        status = {
            "has_proxy_configured": has_proxy,
            "proxy_server": user.proxy_server if has_proxy else None,
            "proxy_username": user.proxy_username if has_proxy else None,
            "using_system_proxy": not has_proxy
        }
        
        return status