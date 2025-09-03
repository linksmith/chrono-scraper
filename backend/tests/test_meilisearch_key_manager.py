"""
Unit Tests for MeilisearchKeyManager

This module provides comprehensive unit tests for the secure multi-tenant
Meilisearch key management system, covering key lifecycle, tenant tokens,
and security operations.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
import jwt

from app.services.meilisearch_key_manager import (
    MeilisearchKeyManager, 
    MeilisearchKeyException,
    meilisearch_key_manager
)
from app.models.project import Project
from app.models.sharing import ProjectShare, SharePermission
from app.core.config import settings


@pytest.fixture
def mock_project():
    """Create a mock project for testing"""
    project = Mock(spec=Project)
    project.id = 123
    project.name = "Test Project"
    project.index_search_key = None
    project.index_search_key_uid = None
    return project


@pytest.fixture
def mock_project_with_key():
    """Create a mock project with existing search key"""
    project = Mock(spec=Project)
    project.id = 456
    project.name = "Test Project With Key"
    project.index_search_key = "test_search_key_456"
    project.index_search_key_uid = "test_key_uid_456"
    return project


@pytest.fixture
def mock_project_share():
    """Create a mock project share for testing"""
    share = Mock(spec=ProjectShare)
    share.id = 789
    share.permission = SharePermission.LIMITED
    share.expires_at = datetime.utcnow() + timedelta(hours=24)
    return share


@pytest.fixture
def key_manager():
    """Create a MeilisearchKeyManager instance for testing"""
    return MeilisearchKeyManager()


class TestMeilisearchKeyManagerInit:
    """Test MeilisearchKeyManager initialization"""
    
    def test_init_with_default_settings(self):
        """Test initialization with default settings"""
        manager = MeilisearchKeyManager()
        
        assert manager.host == settings.MEILISEARCH_HOST
        assert manager.master_key == settings.MEILISEARCH_MASTER_KEY
        assert not manager._connected
        assert manager.key_rotation_days == getattr(settings, 'MEILISEARCH_KEY_ROTATION_DAYS', 90)
        assert manager.tenant_token_expire_hours == getattr(settings, 'MEILISEARCH_TENANT_TOKEN_EXPIRE_HOURS', 24)
    
    def test_init_without_meilisearch_available(self):
        """Test initialization when meilisearch library is not available"""
        with patch('app.services.meilisearch_key_manager.MEILISEARCH_AVAILABLE', False):
            manager = MeilisearchKeyManager()
            assert manager.host == settings.MEILISEARCH_HOST


class TestMeilisearchKeyManagerConnection:
    """Test MeilisearchKeyManager connection management"""
    
    @pytest.mark.asyncio
    async def test_get_admin_client_success(self, key_manager):
        """Test successful admin client connection"""
        mock_client = AsyncMock()
        mock_client.health.return_value = {"status": "available"}
        
        with patch('app.services.meilisearch_key_manager.meilisearch.Client', return_value=mock_client):
            client = await key_manager._get_admin_client()
            
            assert client == mock_client
            assert key_manager._connected
            mock_client.health.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_admin_client_connection_failure(self, key_manager):
        """Test admin client connection failure"""
        with patch('app.services.meilisearch_key_manager.meilisearch.Client', side_effect=Exception("Connection failed")):
            with pytest.raises(MeilisearchKeyException) as exc_info:
                await key_manager._get_admin_client()
            
            assert "Admin connection failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_admin_client_without_meilisearch(self, key_manager):
        """Test admin client when Meilisearch is not available"""
        with patch('app.services.meilisearch_key_manager.MEILISEARCH_AVAILABLE', False):
            with pytest.raises(MeilisearchKeyException) as exc_info:
                await key_manager._get_admin_client()
            
            assert "Meilisearch client not available" in str(exc_info.value)


class TestProjectKeyManagement:
    """Test project key creation, rotation, and revocation"""
    
    @pytest.mark.asyncio
    async def test_create_project_key_success(self, key_manager, mock_project):
        """Test successful project key creation"""
        mock_client = AsyncMock()
        mock_key_response = {
            "key": "test_project_key_123",
            "uid": "test_key_uid_123"
        }
        mock_client.create_key.return_value = mock_key_response
        
        with patch.object(key_manager, '_get_admin_client', return_value=mock_client):
            result = await key_manager.create_project_key(mock_project)
            
            assert result["key"] == "test_project_key_123"
            assert result["uid"] == "test_key_uid_123"
            
            # Verify create_key was called with correct parameters
            mock_client.create_key.assert_called_once()
            call_args = mock_client.create_key.call_args[0][0]
            assert call_args["actions"] == ["search", "documents.get"]
            assert call_args["indexes"] == ["project_123"]
            assert "project_owner_123" in call_args["name"]
    
    @pytest.mark.asyncio
    async def test_create_project_key_without_meilisearch(self, key_manager, mock_project):
        """Test project key creation without Meilisearch available"""
        with patch('app.services.meilisearch_key_manager.MEILISEARCH_AVAILABLE', False):
            result = await key_manager.create_project_key(mock_project)
            
            assert result["key"] == "mock_project_key_123"
            assert result["uid"] == "mock_project_uid_123"
    
    @pytest.mark.asyncio
    async def test_create_project_key_meilisearch_error(self, key_manager, mock_project):
        """Test project key creation with Meilisearch error"""
        mock_client = AsyncMock()
        mock_client.create_key.side_effect = Exception("Meilisearch error")
        
        with patch.object(key_manager, '_get_admin_client', return_value=mock_client):
            with pytest.raises(MeilisearchKeyException) as exc_info:
                await key_manager.create_project_key(mock_project)
            
            assert "Project key creation failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_rotate_project_key_success(self, key_manager, mock_project_with_key):
        """Test successful project key rotation"""
        mock_client = AsyncMock()
        new_key_data = {
            "key": "new_rotated_key_456",
            "uid": "new_key_uid_456"
        }
        
        with patch.object(key_manager, '_get_admin_client', return_value=mock_client):
            with patch.object(key_manager, 'revoke_project_key', return_value=True):
                with patch.object(key_manager, 'create_project_key', return_value=new_key_data):
                    result = await key_manager.rotate_project_key(mock_project_with_key)
                    
                    assert result == new_key_data
    
    @pytest.mark.asyncio
    async def test_revoke_project_key_success(self, key_manager, mock_project_with_key):
        """Test successful project key revocation"""
        mock_client = AsyncMock()
        
        with patch.object(key_manager, '_get_admin_client', return_value=mock_client):
            result = await key_manager.revoke_project_key(mock_project_with_key)
            
            assert result is True
            mock_client.delete_key.assert_called_once_with("test_key_uid_456")
    
    @pytest.mark.asyncio
    async def test_revoke_project_key_no_uid(self, key_manager, mock_project):
        """Test project key revocation when no UID exists"""
        result = await key_manager.revoke_project_key(mock_project)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_revoke_project_key_not_found(self, key_manager, mock_project_with_key):
        """Test project key revocation when key not found"""
        mock_client = AsyncMock()
        mock_error = Mock()
        mock_error.code = "api_key_not_found"
        mock_client.delete_key.side_effect = mock_error
        
        with patch.object(key_manager, '_get_admin_client', return_value=mock_client):
            with patch('app.services.meilisearch_key_manager.MeilisearchApiError', mock_error.__class__):
                result = await key_manager.revoke_project_key(mock_project_with_key)
                assert result is False


class TestTenantTokens:
    """Test JWT tenant token generation and validation"""
    
    @pytest.mark.asyncio
    async def test_create_tenant_token_success(self, key_manager, mock_project_with_key, mock_project_share):
        """Test successful tenant token creation"""
        with patch('app.services.meilisearch_key_manager.MEILISEARCH_AVAILABLE', True):
            result = await key_manager.create_tenant_token(mock_project_with_key, mock_project_share)
            
            assert isinstance(result, str)
            
            # Decode and verify JWT token
            decoded = jwt.decode(result, settings.MEILISEARCH_MASTER_KEY, algorithms=["HS256"])
            assert "searchRules" in decoded
            assert "apiKeyUid" in decoded
            assert "exp" in decoded
            assert decoded["apiKeyUid"] == "test_key_uid_456"
    
    @pytest.mark.asyncio
    async def test_create_tenant_token_no_project_key(self, key_manager, mock_project, mock_project_share):
        """Test tenant token creation when project has no key"""
        with pytest.raises(MeilisearchKeyException) as exc_info:
            await key_manager.create_tenant_token(mock_project, mock_project_share)
        
        assert "has no search key" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_tenant_token_without_meilisearch(self, key_manager, mock_project_with_key, mock_project_share):
        """Test tenant token creation without Meilisearch available"""
        with patch('app.services.meilisearch_key_manager.MEILISEARCH_AVAILABLE', False):
            result = await key_manager.create_tenant_token(mock_project_with_key, mock_project_share)
            
            assert result == "mock_tenant_token_456_789"
    
    def test_build_permission_filter_read(self, key_manager):
        """Test permission filter for READ access"""
        share = Mock()
        share.permission = SharePermission.READ
        
        result = key_manager._build_permission_filter(share.permission)
        assert result == {}
    
    def test_build_permission_filter_limited(self, key_manager):
        """Test permission filter for LIMITED access"""
        share = Mock()
        share.permission = SharePermission.LIMITED
        
        result = key_manager._build_permission_filter(share.permission)
        assert result["filter"] == "review_status != 'irrelevant'"
    
    def test_build_permission_filter_restricted(self, key_manager):
        """Test permission filter for RESTRICTED access"""
        share = Mock()
        share.permission = SharePermission.RESTRICTED
        
        result = key_manager._build_permission_filter(share.permission)
        assert result["filter"] == "review_status = 'relevant'"
    
    def test_generate_jwt_token(self, key_manager):
        """Test JWT token generation"""
        search_rules = {"project_123": {"filter": "test_filter"}}
        api_key_uid = "test_uid"
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        token = key_manager._generate_jwt_token(search_rules, api_key_uid, expires_at)
        
        # Verify token can be decoded
        decoded = jwt.decode(token, settings.MEILISEARCH_MASTER_KEY, algorithms=["HS256"])
        assert decoded["searchRules"] == search_rules
        assert decoded["apiKeyUid"] == api_key_uid
        assert decoded["exp"] == int(expires_at.timestamp())


class TestPublicKeys:
    """Test public key creation and management"""
    
    @pytest.mark.asyncio
    async def test_create_public_key_success(self, key_manager, mock_project):
        """Test successful public key creation"""
        mock_client = AsyncMock()
        mock_key_response = {
            "key": "public_key_123",
            "uid": "public_uid_123"
        }
        mock_client.create_key.return_value = mock_key_response
        
        with patch.object(key_manager, '_get_admin_client', return_value=mock_client):
            result = await key_manager.create_public_key(mock_project)
            
            assert result["key"] == "public_key_123"
            assert result["uid"] == "public_uid_123"
            
            # Verify create_key was called with correct parameters
            mock_client.create_key.assert_called_once()
            call_args = mock_client.create_key.call_args[0][0]
            assert call_args["actions"] == ["search"]
            assert call_args["indexes"] == ["project_123"]
            assert call_args["expiresAt"] is None  # Permanent for public access
    
    @pytest.mark.asyncio
    async def test_create_public_key_without_meilisearch(self, key_manager, mock_project):
        """Test public key creation without Meilisearch available"""
        with patch('app.services.meilisearch_key_manager.MEILISEARCH_AVAILABLE', False):
            result = await key_manager.create_public_key(mock_project)
            
            assert result["key"] == "mock_public_key_123"
            assert result["uid"] == "mock_public_uid_123"


class TestKeyCleanup:
    """Test key cleanup and maintenance operations"""
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_tokens_success(self, key_manager):
        """Test successful cleanup of expired tokens"""
        mock_client = AsyncMock()
        mock_keys_response = {
            "results": [
                {
                    "uid": "expired_key_1",
                    "name": "expired_key",
                    "expiresAt": (datetime.utcnow() - timedelta(hours=1)).isoformat() + 'Z'
                },
                {
                    "uid": "active_key_1", 
                    "name": "active_key",
                    "expiresAt": (datetime.utcnow() + timedelta(hours=1)).isoformat() + 'Z'
                },
                {
                    "uid": "permanent_key_1",
                    "name": "permanent_key",
                    "expiresAt": None
                }
            ]
        }
        mock_client.get_keys.return_value = mock_keys_response
        
        with patch.object(key_manager, '_get_admin_client', return_value=mock_client):
            result = await key_manager.cleanup_expired_tokens()
            
            assert result == 1  # Only one expired key should be deleted
            mock_client.delete_key.assert_called_once_with("expired_key_1")
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_tokens_without_meilisearch(self, key_manager):
        """Test cleanup without Meilisearch available"""
        with patch('app.services.meilisearch_key_manager.MEILISEARCH_AVAILABLE', False):
            result = await key_manager.cleanup_expired_tokens()
            assert result == 0
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_tokens_parse_error(self, key_manager):
        """Test cleanup with date parsing errors"""
        mock_client = AsyncMock()
        mock_keys_response = {
            "results": [
                {
                    "uid": "malformed_date_key",
                    "name": "malformed_key",
                    "expiresAt": "invalid_date_format"
                }
            ]
        }
        mock_client.get_keys.return_value = mock_keys_response
        
        with patch.object(key_manager, '_get_admin_client', return_value=mock_client):
            result = await key_manager.cleanup_expired_tokens()
            
            assert result == 0  # No keys cleaned due to parse error
            mock_client.delete_key.assert_not_called()


class TestKeyStatus:
    """Test key status and monitoring operations"""
    
    @pytest.mark.asyncio
    async def test_get_key_status_success(self, key_manager):
        """Test successful key status retrieval"""
        mock_client = AsyncMock()
        mock_key_info = {
            "name": "test_key",
            "description": "Test key description",
            "actions": ["search", "documents.get"],
            "indexes": ["project_123"],
            "expiresAt": "2024-12-31T23:59:59Z",
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-01T00:00:00Z"
        }
        mock_client.get_key.return_value = mock_key_info
        
        with patch.object(key_manager, '_get_admin_client', return_value=mock_client):
            result = await key_manager.get_key_status("test_key_uid")
            
            assert result["status"] == "active"
            assert result["name"] == "test_key"
            assert result["actions"] == ["search", "documents.get"]
    
    @pytest.mark.asyncio
    async def test_get_key_status_not_found(self, key_manager):
        """Test key status when key is not found"""
        mock_client = AsyncMock()
        mock_error = Mock()
        mock_error.code = "api_key_not_found"
        mock_client.get_key.side_effect = mock_error
        
        with patch.object(key_manager, '_get_admin_client', return_value=mock_client):
            with patch('app.services.meilisearch_key_manager.MeilisearchApiError', mock_error.__class__):
                result = await key_manager.get_key_status("nonexistent_key_uid")
                
                assert result["status"] == "not_found"
    
    @pytest.mark.asyncio
    async def test_get_key_status_without_meilisearch(self, key_manager):
        """Test key status without Meilisearch available"""
        with patch('app.services.meilisearch_key_manager.MEILISEARCH_AVAILABLE', False):
            result = await key_manager.get_key_status("test_key_uid")
            
            assert result["status"] == "mock"
    
    @pytest.mark.asyncio
    async def test_list_project_keys_success(self, key_manager):
        """Test successful project key listing"""
        mock_client = AsyncMock()
        mock_keys_response = {
            "results": [
                {
                    "uid": "key_1",
                    "name": "project_owner_123",
                    "description": "Owner key for project 123",
                    "actions": ["search", "documents.get"],
                    "indexes": ["project_123"],
                    "expiresAt": "2024-12-31T23:59:59Z",
                    "createdAt": "2024-01-01T00:00:00Z"
                },
                {
                    "uid": "key_2",
                    "name": "public_search_project_123",
                    "description": "Public key for project 123",
                    "actions": ["search"],
                    "indexes": ["project_123"],
                    "expiresAt": None,
                    "createdAt": "2024-01-01T00:00:00Z"
                },
                {
                    "uid": "key_3",
                    "name": "other_project_456",
                    "description": "Key for different project",
                    "actions": ["search"],
                    "indexes": ["project_456"],
                    "expiresAt": None,
                    "createdAt": "2024-01-01T00:00:00Z"
                }
            ]
        }
        mock_client.get_keys.return_value = mock_keys_response
        
        with patch.object(key_manager, '_get_admin_client', return_value=mock_client):
            result = await key_manager.list_project_keys(123)
            
            assert len(result) == 2  # Only keys for project 123
            assert result[0]["name"] == "project_owner_123"
            assert result[1]["name"] == "public_search_project_123"
    
    @pytest.mark.asyncio
    async def test_list_project_keys_without_meilisearch(self, key_manager):
        """Test project key listing without Meilisearch available"""
        with patch('app.services.meilisearch_key_manager.MEILISEARCH_AVAILABLE', False):
            result = await key_manager.list_project_keys(123)
            
            assert len(result) == 1
            assert result[0]["name"] == "mock_key_project_123"


class TestUtilityMethods:
    """Test utility and helper methods"""
    
    def test_calculate_key_expiration(self, key_manager):
        """Test key expiration calculation"""
        with patch('app.services.meilisearch_key_manager.datetime') as mock_dt:
            mock_now = datetime(2024, 1, 1, 12, 0, 0)
            mock_dt.utcnow.return_value = mock_now
            
            result = key_manager._calculate_key_expiration()
            
            expected_date = mock_now + timedelta(days=key_manager.key_rotation_days)
            expected_iso = expected_date.isoformat() + 'Z'
            assert result == expected_iso
    
    @pytest.mark.asyncio
    async def test_close_connection(self, key_manager):
        """Test connection closure"""
        mock_client = AsyncMock()
        key_manager._admin_client = mock_client
        key_manager._connected = True
        
        await key_manager.close()
        
        mock_client.aclose.assert_called_once()
        assert not key_manager._connected


class TestConvenienceFunctions:
    """Test module-level convenience functions"""
    
    @pytest.mark.asyncio
    async def test_create_project_search_key(self, mock_project):
        """Test convenience function for creating project search key"""
        expected_result = {"key": "test_key", "uid": "test_uid"}
        
        with patch.object(meilisearch_key_manager, 'create_project_key', return_value=expected_result) as mock_create:
            from app.services.meilisearch_key_manager import create_project_search_key
            
            result = await create_project_search_key(mock_project)
            
            assert result == expected_result
            mock_create.assert_called_once_with(mock_project)
    
    @pytest.mark.asyncio
    async def test_create_share_token(self, mock_project_with_key, mock_project_share):
        """Test convenience function for creating share token"""
        expected_token = "jwt_tenant_token"
        
        with patch.object(meilisearch_key_manager, 'create_tenant_token', return_value=expected_token) as mock_create:
            from app.services.meilisearch_key_manager import create_share_token
            
            result = await create_share_token(mock_project_with_key, mock_project_share)
            
            assert result == expected_token
            mock_create.assert_called_once_with(mock_project_with_key, mock_project_share)
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_meilisearch_keys(self):
        """Test convenience function for cleanup"""
        expected_count = 5
        
        with patch.object(meilisearch_key_manager, 'cleanup_expired_tokens', return_value=expected_count) as mock_cleanup:
            from app.services.meilisearch_key_manager import cleanup_expired_meilisearch_keys
            
            result = await cleanup_expired_meilisearch_keys()
            
            assert result == expected_count
            mock_cleanup.assert_called_once()


# Integration test helpers
@pytest.mark.asyncio
async def test_full_key_lifecycle():
    """Integration test for complete key lifecycle"""
    key_manager = MeilisearchKeyManager()
    mock_project = Mock(spec=Project)
    mock_project.id = 999
    mock_project.name = "Lifecycle Test Project"
    mock_project.index_search_key = None
    mock_project.index_search_key_uid = None
    
    # Mock the entire Meilisearch client interaction
    with patch('app.services.meilisearch_key_manager.MEILISEARCH_AVAILABLE', False):
        # Test key creation
        key_data = await key_manager.create_project_key(mock_project)
        assert "key" in key_data
        assert "uid" in key_data
        
        # Update project with key data
        mock_project.index_search_key = key_data["key"]
        mock_project.index_search_key_uid = key_data["uid"]
        
        # Test key rotation
        new_key_data = await key_manager.rotate_project_key(mock_project)
        assert new_key_data["key"] != key_data["key"]
        assert new_key_data["uid"] != key_data["uid"]
        
        # Test key revocation
        revoked = await key_manager.revoke_project_key(mock_project)
        assert revoked is True
        
        # Test cleanup
        cleanup_count = await key_manager.cleanup_expired_tokens()
        assert isinstance(cleanup_count, int)