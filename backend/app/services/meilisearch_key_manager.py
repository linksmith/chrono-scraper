"""
Meilisearch Key Manager for Secure Multi-Tenancy

This service manages API keys and tenant tokens for Meilisearch, providing secure 
project isolation while supporting sharing and public access patterns.

Architecture:
- Master Key: Admin operations only (index creation/deletion)
- Project Owner Keys: Full search access for project owners
- Project Share Keys: Time-limited JWT tenant tokens for shared users
- Public Access Keys: Read-only keys for public projects
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import asyncio
import jwt

try:
    import meilisearch_python_async as meilisearch
    from meilisearch_python_async.errors import MeilisearchApiError, MeilisearchError
    MEILISEARCH_AVAILABLE = True
except ImportError:
    MEILISEARCH_AVAILABLE = False

from ..core.config import settings
from ..models.project import Project
from ..models.sharing import ProjectShare, SharePermission

logger = logging.getLogger(__name__)


class MeilisearchKeyException(Exception):
    """Exception for Meilisearch key management operations"""
    pass


class MeilisearchKeyManager:
    """
    Manages Meilisearch API keys for multi-tenant security
    
    This service implements a 4-tier key architecture:
    1. Master Key (Admin Level): Index management only
    2. Project Owner Keys: Full access for project owners
    3. Project Share Keys: Limited access via JWT tenant tokens
    4. Public Access Keys: Read-only for public projects
    """
    
    def __init__(self):
        """Initialize the key manager with master key access"""
        if not MEILISEARCH_AVAILABLE:
            logger.warning("Meilisearch not available, using mock key manager")
            
        self.host = settings.MEILISEARCH_HOST or "http://localhost:7700"
        self.master_key = settings.MEILISEARCH_MASTER_KEY
        self._admin_client = None
        self._connected = False
        
        # Configuration from settings
        self.key_rotation_days = getattr(settings, 'MEILISEARCH_KEY_ROTATION_DAYS', 90)
        self.tenant_token_expire_hours = getattr(settings, 'MEILISEARCH_TENANT_TOKEN_EXPIRE_HOURS', 24)
        self.public_key_rate_limit = getattr(settings, 'MEILISEARCH_PUBLIC_KEY_RATE_LIMIT', 1000)
    
    async def _get_admin_client(self) -> meilisearch.Client:
        """Get admin client with master key (for key management only)"""
        if not MEILISEARCH_AVAILABLE:
            raise MeilisearchKeyException("Meilisearch client not available")
            
        if not self._admin_client or not self._connected:
            try:
                self._admin_client = meilisearch.Client(
                    url=self.host,
                    api_key=self.master_key
                )
                
                # Test connection
                health = await self._admin_client.health()
                self._connected = True
                logger.debug(f"Admin client connected to Meilisearch: {health}")
                
            except Exception as e:
                logger.error(f"Failed to connect admin client to Meilisearch: {str(e)}")
                raise MeilisearchKeyException(f"Admin connection failed: {str(e)}")
        
        return self._admin_client
    
    async def create_project_key(self, project: Project) -> Dict[str, str]:
        """
        Create dedicated search key for project with full access to project index
        
        Args:
            project: Project instance to create key for
            
        Returns:
            Dict containing 'key' and 'uid' for the created API key
        """
        if not MEILISEARCH_AVAILABLE:
            logger.info(f"Mock: Created project key for project {project.id}")
            return {
                "key": f"mock_project_key_{project.id}",
                "uid": f"mock_project_uid_{project.id}"
            }
        
        try:
            client = await self._get_admin_client()
            index_name = f"project_{project.id}"
            
            # Define key configuration for project owner
            key_config = {
                "actions": ["search", "documents.get"],
                "indexes": [index_name],
                "expiresAt": self._calculate_key_expiration(),
                "name": f"project_owner_{project.id}",
                "description": f"Search key for project: {project.name} (Owner Access)"
            }
            
            # Create the API key
            key_response = await client.create_key(key_config)
            
            logger.info(f"Created project search key for project {project.id}")
            
            return {
                "key": key_response["key"],
                "uid": key_response["uid"]
            }
            
        except MeilisearchApiError as e:
            logger.error(f"Failed to create project key for {project.id}: {str(e)}")
            raise MeilisearchKeyException(f"Project key creation failed: {str(e)}")
    
    async def rotate_project_key(self, project: Project) -> Dict[str, str]:
        """
        Rotate project's search key for security
        
        Args:
            project: Project instance to rotate key for
            
        Returns:
            Dict containing new 'key' and 'uid'
        """
        if not MEILISEARCH_AVAILABLE:
            logger.info(f"Mock: Rotated project key for project {project.id}")
            return {
                "key": f"mock_rotated_key_{project.id}_{int(datetime.utcnow().timestamp())}",
                "uid": f"mock_rotated_uid_{project.id}_{int(datetime.utcnow().timestamp())}"
            }
        
        try:
            # Revoke old key if it exists
            if project.index_search_key_uid:
                await self.revoke_project_key(project)
            
            # Create new key
            new_key_data = await self.create_project_key(project)
            
            logger.info(f"Rotated project search key for project {project.id}")
            return new_key_data
            
        except Exception as e:
            logger.error(f"Failed to rotate project key for {project.id}: {str(e)}")
            raise MeilisearchKeyException(f"Project key rotation failed: {str(e)}")
    
    async def revoke_project_key(self, project: Project) -> bool:
        """
        Revoke project's search key
        
        Args:
            project: Project instance to revoke key for
            
        Returns:
            True if successfully revoked, False if key didn't exist
        """
        if not MEILISEARCH_AVAILABLE:
            logger.info(f"Mock: Revoked project key for project {project.id}")
            return True
        
        if not project.index_search_key_uid:
            logger.warning(f"No key UID to revoke for project {project.id}")
            return False
        
        try:
            client = await self._get_admin_client()
            await client.delete_key(project.index_search_key_uid)
            
            logger.info(f"Revoked project search key for project {project.id}")
            return True
            
        except MeilisearchApiError as e:
            if e.code == "api_key_not_found":
                logger.warning(f"Key already deleted for project {project.id}")
                return False
            else:
                logger.error(f"Failed to revoke project key for {project.id}: {str(e)}")
                raise MeilisearchKeyException(f"Project key revocation failed: {str(e)}")
    
    async def create_tenant_token(self, project: Project, share: ProjectShare) -> str:
        """
        Create JWT tenant token for shared access with permission-based filtering
        
        Args:
            project: Project being shared
            share: ProjectShare configuration with permissions and expiration
            
        Returns:
            JWT tenant token string
        """
        if not MEILISEARCH_AVAILABLE:
            logger.info(f"Mock: Created tenant token for project {project.id}")
            return f"mock_tenant_token_{project.id}_{share.id}"
        
        if not project.index_search_key_uid:
            raise MeilisearchKeyException(f"Project {project.id} has no search key for tenant token creation")
        
        try:
            index_name = f"project_{project.id}"
            
            # Build search rules with permission-based filtering
            search_rules = {
                index_name: self._build_permission_filter(share.permission)
            }
            
            # Calculate expiration
            expires_at = share.expires_at
            if not expires_at:
                expires_at = datetime.utcnow() + timedelta(hours=self.tenant_token_expire_hours)
            
            # Generate tenant token (JWT)
            tenant_token = self._generate_jwt_token(
                search_rules=search_rules,
                api_key_uid=project.index_search_key_uid,
                expires_at=expires_at
            )
            
            logger.info(f"Created tenant token for project {project.id} with {share.permission.value} permissions")
            return tenant_token
            
        except Exception as e:
            logger.error(f"Failed to create tenant token for project {project.id}: {str(e)}")
            raise MeilisearchKeyException(f"Tenant token creation failed: {str(e)}")
    
    async def create_public_key(self, project: Project) -> Dict[str, str]:
        """
        Create public search key for public projects (read-only, rate-limited)
        
        Args:
            project: Project to create public key for
            
        Returns:
            Dict containing 'key' and 'uid' for the public search key
        """
        if not MEILISEARCH_AVAILABLE:
            logger.info(f"Mock: Created public key for project {project.id}")
            return {
                "key": f"mock_public_key_{project.id}",
                "uid": f"mock_public_uid_{project.id}"
            }
        
        try:
            client = await self._get_admin_client()
            index_name = f"project_{project.id}"
            
            # Define key configuration for public access
            key_config = {
                "actions": ["search"],
                "indexes": [index_name],
                "expiresAt": None,  # Permanent for public access
                "name": f"public_search_project_{project.id}",
                "description": f"Public search access for project: {project.name}"
            }
            
            # Create the public API key
            key_response = await client.create_key(key_config)
            
            logger.info(f"Created public search key for project {project.id}")
            
            return {
                "key": key_response["key"],
                "uid": key_response["uid"]
            }
            
        except MeilisearchApiError as e:
            logger.error(f"Failed to create public key for {project.id}: {str(e)}")
            raise MeilisearchKeyException(f"Public key creation failed: {str(e)}")
    
    async def cleanup_expired_tokens(self) -> int:
        """
        Remove expired tenant tokens and revoke expired keys
        
        Returns:
            Number of keys cleaned up
        """
        if not MEILISEARCH_AVAILABLE:
            logger.info("Mock: Cleaned up expired tokens")
            return 0
        
        try:
            client = await self._get_admin_client()
            
            # Get all keys
            keys_response = await client.get_keys()
            keys = keys_response.get("results", [])
            
            cleanup_count = 0
            current_time = datetime.utcnow()
            
            for key_info in keys:
                expires_at = key_info.get("expiresAt")
                if expires_at:
                    try:
                        # Parse expiration date (ISO format)
                        expiry_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                        
                        # Check if expired
                        if expiry_date < current_time:
                            await client.delete_key(key_info["uid"])
                            cleanup_count += 1
                            logger.info(f"Cleaned up expired key: {key_info['name']}")
                            
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse expiration date for key {key_info['uid']}: {e}")
            
            logger.info(f"Cleaned up {cleanup_count} expired keys")
            return cleanup_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired tokens: {str(e)}")
            raise MeilisearchKeyException(f"Token cleanup failed: {str(e)}")
    
    def _build_permission_filter(self, permission: SharePermission) -> Dict[str, Any]:
        """
        Build Meilisearch filter based on sharing permissions
        
        Args:
            permission: SharePermission level
            
        Returns:
            Dictionary with filter configuration for the permission level
        """
        filter_config = {}
        
        if permission == SharePermission.READ:
            # Full read access - no additional filtering
            pass
        elif permission == SharePermission.LIMITED:
            # Limited access - hide irrelevant pages
            filter_config["filter"] = "review_status != 'irrelevant'"
        elif permission == SharePermission.RESTRICTED:
            # Restricted access - only show reviewed and relevant content
            filter_config["filter"] = "review_status = 'relevant'"
        
        return filter_config
    
    def _generate_jwt_token(self, search_rules: Dict[str, Any], api_key_uid: str, expires_at: datetime) -> str:
        """
        Generate JWT tenant token for Meilisearch
        
        Args:
            search_rules: Dictionary defining search rules and filters
            api_key_uid: UID of the API key to base the token on
            expires_at: Expiration datetime for the token
            
        Returns:
            JWT token string
        """
        # Prepare JWT payload according to Meilisearch tenant token specification
        payload = {
            "searchRules": search_rules,
            "apiKeyUid": api_key_uid,
            "exp": int(expires_at.timestamp())
        }
        
        # Generate JWT using the master key as secret
        token = jwt.encode(payload, self.master_key, algorithm="HS256")
        
        return token
    
    def _calculate_key_expiration(self) -> str:
        """
        Calculate expiration date for API keys
        
        Returns:
            ISO format expiration date string
        """
        expiry_date = datetime.utcnow() + timedelta(days=self.key_rotation_days)
        return expiry_date.isoformat() + 'Z'
    
    async def get_key_status(self, key_uid: str) -> Dict[str, Any]:
        """
        Get status information for a specific API key
        
        Args:
            key_uid: UID of the key to check
            
        Returns:
            Dictionary with key status information
        """
        if not MEILISEARCH_AVAILABLE:
            return {"status": "mock", "expires_at": None, "actions": ["search"]}
        
        try:
            client = await self._get_admin_client()
            key_info = await client.get_key(key_uid)
            
            return {
                "status": "active",
                "name": key_info.get("name"),
                "description": key_info.get("description"),
                "actions": key_info.get("actions", []),
                "indexes": key_info.get("indexes", []),
                "expires_at": key_info.get("expiresAt"),
                "created_at": key_info.get("createdAt"),
                "updated_at": key_info.get("updatedAt")
            }
            
        except MeilisearchApiError as e:
            if e.code == "api_key_not_found":
                return {"status": "not_found"}
            else:
                logger.error(f"Failed to get key status for {key_uid}: {str(e)}")
                raise MeilisearchKeyException(f"Key status check failed: {str(e)}")
    
    async def list_project_keys(self, project_id: int) -> List[Dict[str, Any]]:
        """
        List all API keys associated with a project
        
        Args:
            project_id: ID of the project
            
        Returns:
            List of dictionaries with key information
        """
        if not MEILISEARCH_AVAILABLE:
            return [{"name": f"mock_key_project_{project_id}", "type": "mock"}]
        
        try:
            client = await self._get_admin_client()
            keys_response = await client.get_keys()
            keys = keys_response.get("results", [])
            
            # Filter keys for this project
            project_keys = []
            for key_info in keys:
                key_name = key_info.get("name", "")
                indexes = key_info.get("indexes", [])
                project_index = f"project_{project_id}"
                
                # Check if key is associated with this project
                if (project_index in indexes or 
                    f"project_{project_id}" in key_name or
                    f"public_search_project_{project_id}" in key_name):
                    
                    project_keys.append({
                        "uid": key_info["uid"],
                        "name": key_info["name"],
                        "description": key_info.get("description"),
                        "actions": key_info.get("actions", []),
                        "expires_at": key_info.get("expiresAt"),
                        "created_at": key_info.get("createdAt")
                    })
            
            return project_keys
            
        except Exception as e:
            logger.error(f"Failed to list keys for project {project_id}: {str(e)}")
            raise MeilisearchKeyException(f"Key listing failed: {str(e)}")
    
    async def close(self):
        """Close admin client connection"""
        if self._admin_client and self._connected:
            await self._admin_client.aclose()
            self._connected = False


# Global key manager instance
meilisearch_key_manager = MeilisearchKeyManager()


# Convenience functions for common operations
async def create_project_search_key(project: Project) -> Dict[str, str]:
    """Create a dedicated search key for a project"""
    return await meilisearch_key_manager.create_project_key(project)


async def create_share_token(project: Project, share: ProjectShare) -> str:
    """Create a tenant token for shared project access"""
    return await meilisearch_key_manager.create_tenant_token(project, share)


async def cleanup_expired_meilisearch_keys() -> int:
    """Clean up expired API keys and tokens"""
    return await meilisearch_key_manager.cleanup_expired_tokens()