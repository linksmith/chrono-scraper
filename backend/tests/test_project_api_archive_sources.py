"""
API tests for project creation and management with archive source configurations.

Tests cover:
- Archive source validation (valid/invalid values)
- Field mapping (archive_source, fallback_enabled, archive_config)
- Default behavior and backward compatibility
- Error responses for invalid data
- Project CRUD operations with archive configurations
- Archive configuration persistence and retrieval
"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import select
from typing import Dict, Any

from app.models.project import Project, ArchiveSource
from app.models.user import User


class TestProjectArchiveSourceAPI:
    """Test suite for project API with archive source functionality"""

    @pytest.fixture
    def project_data_base(self):
        """Base project data for testing"""
        return {
            "name": "Test Archive Project",
            "description": "Project for testing archive source configurations",
            "process_documents": True,
            "enable_attachment_download": True
        }

    def test_create_project_default_archive_source(self, client: TestClient, auth_headers):
        """Test creating project with default archive source (Wayback Machine)"""
        project_data = {
            "name": "Default Archive Project", 
            "description": "Project with default archive settings"
        }
        
        response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # Should default to Wayback Machine
        assert data["archive_source"] == ArchiveSource.WAYBACK_MACHINE.value
        assert data["fallback_enabled"] == True  # Default fallback enabled
        assert data["archive_config"] == {}  # Default empty config

    def test_create_project_wayback_machine_source(self, client: TestClient, auth_headers, project_data_base):
        """Test creating project with explicit Wayback Machine source"""
        project_data = {
            **project_data_base,
            "archive_source": ArchiveSource.WAYBACK_MACHINE.value,
            "fallback_enabled": True,
            "archive_config": {
                "wayback_machine": {
                    "timeout_seconds": 120,
                    "page_size": 1000,
                    "max_pages": 10
                }
            }
        }
        
        response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["archive_source"] == ArchiveSource.WAYBACK_MACHINE.value
        assert data["fallback_enabled"] == True
        assert data["archive_config"]["wayback_machine"]["timeout_seconds"] == 120
        assert data["archive_config"]["wayback_machine"]["page_size"] == 1000

    def test_create_project_common_crawl_source(self, client: TestClient, auth_headers, project_data_base):
        """Test creating project with Common Crawl source"""
        project_data = {
            **project_data_base,
            "archive_source": ArchiveSource.COMMON_CRAWL.value,
            "fallback_enabled": False,
            "archive_config": {
                "common_crawl": {
                    "timeout_seconds": 180,
                    "page_size": 5000,
                    "max_retries": 8
                }
            }
        }
        
        response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["archive_source"] == ArchiveSource.COMMON_CRAWL.value
        assert data["fallback_enabled"] == False
        assert data["archive_config"]["common_crawl"]["timeout_seconds"] == 180
        assert data["archive_config"]["common_crawl"]["max_retries"] == 8

    def test_create_project_hybrid_source(self, client: TestClient, auth_headers, project_data_base):
        """Test creating project with hybrid archive source"""
        project_data = {
            **project_data_base,
            "archive_source": ArchiveSource.HYBRID.value,
            "fallback_enabled": True,
            "archive_config": {
                "wayback_machine": {
                    "timeout_seconds": 90,
                    "priority": 1
                },
                "common_crawl": {
                    "timeout_seconds": 150,
                    "priority": 2
                },
                "fallback_strategy": "circuit_breaker",
                "fallback_delay_seconds": 2.0
            }
        }
        
        response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        
        assert data["archive_source"] == ArchiveSource.HYBRID.value
        assert data["fallback_enabled"] == True
        assert data["archive_config"]["fallback_strategy"] == "circuit_breaker"
        assert data["archive_config"]["fallback_delay_seconds"] == 2.0
        assert data["archive_config"]["wayback_machine"]["priority"] == 1
        assert data["archive_config"]["common_crawl"]["priority"] == 2

    def test_create_project_invalid_archive_source(self, client: TestClient, auth_headers, project_data_base):
        """Test creating project with invalid archive source"""
        project_data = {
            **project_data_base,
            "archive_source": "invalid_source"
        }
        
        response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422
        error_data = response.json()
        
        # Should contain validation error for archive_source field
        assert "detail" in error_data
        error_details = error_data["detail"]
        assert any("archive_source" in str(error).lower() for error in error_details)

    def test_create_project_invalid_fallback_enabled_type(self, client: TestClient, auth_headers, project_data_base):
        """Test creating project with invalid fallback_enabled type"""
        project_data = {
            **project_data_base,
            "fallback_enabled": "not_a_boolean"
        }
        
        response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422
        error_data = response.json()
        
        # Should contain validation error for fallback_enabled field
        assert "detail" in error_data

    def test_create_project_complex_archive_config(self, client: TestClient, auth_headers, project_data_base):
        """Test creating project with complex archive configuration"""
        project_data = {
            **project_data_base,
            "archive_source": ArchiveSource.HYBRID.value,
            "archive_config": {
                "wayback_machine": {
                    "timeout_seconds": 60,
                    "max_retries": 5,
                    "page_size": 2000,
                    "max_pages": 20,
                    "include_attachments": True,
                    "priority": 1,
                    "custom_settings": {
                        "user_agent": "CustomBot/1.0",
                        "rate_limit_per_second": 2
                    }
                },
                "common_crawl": {
                    "timeout_seconds": 120,
                    "max_retries": 8,
                    "page_size": 5000,
                    "max_pages": 50,
                    "include_attachments": False,
                    "priority": 2,
                    "custom_settings": {
                        "collections": ["CC-MAIN-2024-10", "CC-MAIN-2024-22"]
                    }
                },
                "fallback_strategy": "retry_then_fallback",
                "fallback_delay_seconds": 5.0,
                "exponential_backoff": True,
                "max_fallback_delay": 30.0
            }
        }
        
        response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify all configuration is preserved
        config = data["archive_config"]
        wb_config = config["wayback_machine"]
        cc_config = config["common_crawl"]
        
        assert wb_config["timeout_seconds"] == 60
        assert wb_config["max_retries"] == 5
        assert wb_config["custom_settings"]["user_agent"] == "CustomBot/1.0"
        
        assert cc_config["timeout_seconds"] == 120
        assert cc_config["max_retries"] == 8
        assert cc_config["custom_settings"]["collections"] == ["CC-MAIN-2024-10", "CC-MAIN-2024-22"]
        
        assert config["fallback_strategy"] == "retry_then_fallback"
        assert config["exponential_backoff"] == True

    def test_update_project_archive_source(self, client: TestClient, auth_headers, test_project):
        """Test updating project archive source configuration"""
        update_data = {
            "archive_source": ArchiveSource.COMMON_CRAWL.value,
            "fallback_enabled": False,
            "archive_config": {
                "common_crawl": {
                    "timeout_seconds": 200,
                    "page_size": 3000
                }
            }
        }
        
        response = client.put(
            f"/api/v1/projects/{test_project.id}",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["archive_source"] == ArchiveSource.COMMON_CRAWL.value
        assert data["fallback_enabled"] == False
        assert data["archive_config"]["common_crawl"]["timeout_seconds"] == 200

    def test_update_project_partial_archive_config(self, client: TestClient, auth_headers, test_project):
        """Test partial update of archive configuration"""
        # First, set initial config
        initial_update = {
            "archive_source": ArchiveSource.HYBRID.value,
            "archive_config": {
                "wayback_machine": {"timeout_seconds": 60, "page_size": 1000},
                "common_crawl": {"timeout_seconds": 120, "page_size": 2000},
                "fallback_strategy": "immediate"
            }
        }
        
        response = client.put(
            f"/api/v1/projects/{test_project.id}",
            json=initial_update,
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Then, partial update
        partial_update = {
            "archive_config": {
                "wayback_machine": {"timeout_seconds": 90},  # Only update timeout
                "fallback_strategy": "circuit_breaker"  # Update strategy
            }
        }
        
        response = client.put(
            f"/api/v1/projects/{test_project.id}",
            json=partial_update,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should merge configurations appropriately
        wb_config = data["archive_config"].get("wayback_machine", {})
        cc_config = data["archive_config"].get("common_crawl", {})
        
        # Updated field
        assert wb_config.get("timeout_seconds") == 90
        # Preserved field (or may be overwritten depending on implementation)
        # This depends on whether the API does deep merge or replacement
        
        assert data["archive_config"]["fallback_strategy"] == "circuit_breaker"

    def test_get_project_with_archive_config(self, client: TestClient, auth_headers):
        """Test retrieving project with archive configuration"""
        # Create project with archive config
        project_data = {
            "name": "Archive Config Test",
            "archive_source": ArchiveSource.HYBRID.value,
            "fallback_enabled": True,
            "archive_config": {
                "wayback_machine": {"timeout_seconds": 75},
                "common_crawl": {"max_retries": 6}
            }
        }
        
        create_response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]
        
        # Retrieve project
        get_response = client.get(
            f"/api/v1/projects/{project_id}",
            headers=auth_headers
        )
        
        assert get_response.status_code == 200
        data = get_response.json()
        
        assert data["archive_source"] == ArchiveSource.HYBRID.value
        assert data["fallback_enabled"] == True
        assert data["archive_config"]["wayback_machine"]["timeout_seconds"] == 75
        assert data["archive_config"]["common_crawl"]["max_retries"] == 6

    def test_list_projects_includes_archive_config(self, client: TestClient, auth_headers):
        """Test that project listing includes archive configurations"""
        # Create multiple projects with different configs
        projects_data = [
            {
                "name": "Wayback Project",
                "archive_source": ArchiveSource.WAYBACK_MACHINE.value,
                "fallback_enabled": False
            },
            {
                "name": "Common Crawl Project", 
                "archive_source": ArchiveSource.COMMON_CRAWL.value,
                "fallback_enabled": True
            },
            {
                "name": "Hybrid Project",
                "archive_source": ArchiveSource.HYBRID.value,
                "archive_config": {"fallback_strategy": "immediate"}
            }
        ]
        
        created_ids = []
        for project_data in projects_data:
            response = client.post(
                "/api/v1/projects/",
                json=project_data,
                headers=auth_headers
            )
            assert response.status_code == 201
            created_ids.append(response.json()["id"])
        
        # List projects
        list_response = client.get(
            "/api/v1/projects/",
            headers=auth_headers
        )
        
        assert list_response.status_code == 200
        projects = list_response.json()
        
        # Find our created projects
        created_projects = [p for p in projects if p["id"] in created_ids]
        assert len(created_projects) == 3
        
        # Verify archive configurations are included
        wayback_project = next(p for p in created_projects if p["name"] == "Wayback Project")
        assert wayback_project["archive_source"] == ArchiveSource.WAYBACK_MACHINE.value
        assert wayback_project["fallback_enabled"] == False
        
        hybrid_project = next(p for p in created_projects if p["name"] == "Hybrid Project")
        assert hybrid_project["archive_source"] == ArchiveSource.HYBRID.value
        assert hybrid_project["archive_config"]["fallback_strategy"] == "immediate"

    def test_archive_config_validation_empty_object(self, client: TestClient, auth_headers, project_data_base):
        """Test that empty archive_config object is accepted"""
        project_data = {
            **project_data_base,
            "archive_config": {}
        }
        
        response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["archive_config"] == {}

    def test_archive_config_validation_null_values(self, client: TestClient, auth_headers, project_data_base):
        """Test archive_config with null values"""
        project_data = {
            **project_data_base,
            "archive_config": {
                "wayback_machine": {
                    "timeout_seconds": None,  # Null value
                    "page_size": 1000
                }
            }
        }
        
        response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        
        # Should accept null values (implementation may filter them out)
        assert response.status_code == 201
        data = response.json()
        
        # Verify the structure (null handling depends on implementation)
        assert "wayback_machine" in data["archive_config"]

    def test_backward_compatibility_existing_projects(self, client: TestClient, auth_headers):
        """Test backward compatibility for projects created before archive source feature"""
        # Create project without archive source fields (simulating old project)
        project_data = {
            "name": "Legacy Project",
            "description": "Project created before archive source feature"
        }
        
        response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # Should have default values
        assert data["archive_source"] == ArchiveSource.WAYBACK_MACHINE.value
        assert data["fallback_enabled"] == True
        assert data["archive_config"] == {}

    def test_delete_project_with_archive_config(self, client: TestClient, auth_headers):
        """Test deleting project with archive configuration"""
        # Create project with archive config
        project_data = {
            "name": "Project to Delete",
            "archive_source": ArchiveSource.HYBRID.value,
            "archive_config": {"wayback_machine": {"timeout_seconds": 60}}
        }
        
        create_response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]
        
        # Delete project
        delete_response = client.delete(
            f"/api/v1/projects/{project_id}",
            headers=auth_headers
        )
        
        assert delete_response.status_code == 204
        
        # Verify deletion
        get_response = client.get(
            f"/api/v1/projects/{project_id}",
            headers=auth_headers
        )
        assert get_response.status_code == 404


class TestProjectArchiveSourceValidation:
    """Test suite for archive source validation and error handling"""

    def test_archive_source_enum_validation(self, client: TestClient, auth_headers):
        """Test validation of archive source enum values"""
        valid_sources = [
            ArchiveSource.WAYBACK_MACHINE.value,
            ArchiveSource.COMMON_CRAWL.value,
            ArchiveSource.HYBRID.value
        ]
        
        for source in valid_sources:
            project_data = {
                "name": f"Test {source}",
                "archive_source": source
            }
            
            response = client.post(
                "/api/v1/projects/",
                json=project_data,
                headers=auth_headers
            )
            
            assert response.status_code == 201, f"Failed for valid source: {source}"
            assert response.json()["archive_source"] == source

    def test_invalid_archive_source_values(self, client: TestClient, auth_headers):
        """Test rejection of invalid archive source values"""
        invalid_sources = [
            "invalid",
            "archive_org",
            "google_cache",
            123,
            None,
            "",
            "WAYBACK_MACHINE"  # Wrong case
        ]
        
        for invalid_source in invalid_sources:
            project_data = {
                "name": f"Test Invalid {invalid_source}",
                "archive_source": invalid_source
            }
            
            response = client.post(
                "/api/v1/projects/",
                json=project_data,
                headers=auth_headers
            )
            
            assert response.status_code == 422, f"Should reject invalid source: {invalid_source}"

    def test_archive_config_json_validation(self, client: TestClient, auth_headers):
        """Test validation of archive_config JSON structure"""
        # Test various JSON structures
        test_cases = [
            # Valid complex structure
            {
                "config": {
                    "wayback_machine": {"timeout": 60},
                    "common_crawl": {"retries": 5},
                    "fallback_strategy": "immediate"
                },
                "should_pass": True
            },
            # Valid empty object
            {
                "config": {},
                "should_pass": True  
            },
            # Valid nested structure
            {
                "config": {
                    "wayback_machine": {
                        "timeout_seconds": 120,
                        "custom_settings": {
                            "nested": {"deeply": {"nested": "value"}}
                        }
                    }
                },
                "should_pass": True
            },
            # Valid array in config
            {
                "config": {
                    "common_crawl": {
                        "collections": ["CC-MAIN-2024-10", "CC-MAIN-2024-22"]
                    }
                },
                "should_pass": True
            }
        ]
        
        for i, test_case in enumerate(test_cases):
            project_data = {
                "name": f"JSON Test {i}",
                "archive_config": test_case["config"]
            }
            
            response = client.post(
                "/api/v1/projects/",
                json=project_data,
                headers=auth_headers
            )
            
            if test_case["should_pass"]:
                assert response.status_code == 201, f"Case {i} should pass: {test_case}"
            else:
                assert response.status_code == 422, f"Case {i} should fail: {test_case}"

    def test_fallback_enabled_validation(self, client: TestClient, auth_headers):
        """Test fallback_enabled field validation"""
        valid_values = [True, False]
        invalid_values = ["true", "false", 1, 0, "yes", "no", None]
        
        # Test valid boolean values
        for value in valid_values:
            project_data = {
                "name": f"Fallback Test {value}",
                "fallback_enabled": value
            }
            
            response = client.post(
                "/api/v1/projects/",
                json=project_data,
                headers=auth_headers
            )
            
            assert response.status_code == 201, f"Should accept valid boolean: {value}"
            assert response.json()["fallback_enabled"] == value
        
        # Test invalid values
        for value in invalid_values:
            project_data = {
                "name": f"Invalid Fallback {value}",
                "fallback_enabled": value
            }
            
            response = client.post(
                "/api/v1/projects/",
                json=project_data,
                headers=auth_headers
            )
            
            assert response.status_code == 422, f"Should reject invalid boolean: {value}"


class TestProjectArchiveSourcePersistence:
    """Test suite for archive source configuration persistence"""

    @pytest.mark.asyncio
    async def test_database_persistence(self, app, test_project):
        """Test that archive configurations are properly persisted to database"""
        from app.core.database import get_db
        
        # Update project with archive configuration
        async for db in get_db():
            project = await db.get(Project, test_project.id)
            
            # Set archive configuration
            project.archive_source = ArchiveSource.HYBRID
            project.fallback_enabled = False
            project.archive_config = {
                "wayback_machine": {"timeout_seconds": 100},
                "common_crawl": {"max_retries": 7},
                "fallback_strategy": "retry_then_fallback"
            }
            
            await db.commit()
            await db.refresh(project)
            
            # Verify persistence
            assert project.archive_source == ArchiveSource.HYBRID
            assert project.fallback_enabled == False
            assert project.archive_config["wayback_machine"]["timeout_seconds"] == 100
            assert project.archive_config["common_crawl"]["max_retries"] == 7
            assert project.archive_config["fallback_strategy"] == "retry_then_fallback"
            break

    @pytest.mark.asyncio
    async def test_json_field_serialization(self, app, test_project):
        """Test JSON field serialization/deserialization"""
        from app.core.database import get_db
        
        complex_config = {
            "wayback_machine": {
                "timeout_seconds": 120,
                "custom_headers": {
                    "User-Agent": "CustomBot/1.0",
                    "Accept": "text/html,application/xhtml+xml"
                },
                "retry_codes": [502, 503, 522],
                "enabled_features": {
                    "compression": True,
                    "cookies": False,
                    "javascript": None
                }
            },
            "common_crawl": {
                "collections": [
                    "CC-MAIN-2024-10",
                    "CC-MAIN-2024-22"
                ],
                "filters": {
                    "mime_types": ["text/html", "application/pdf"],
                    "status_codes": [200, 301, 302]
                }
            },
            "routing": {
                "fallback_strategy": "circuit_breaker",
                "priorities": [1, 2],
                "weights": {"primary": 0.8, "fallback": 0.2}
            }
        }
        
        async for db in get_db():
            project = await db.get(Project, test_project.id)
            project.archive_config = complex_config
            
            await db.commit()
            await db.refresh(project)
            
            # Verify complex structure is preserved
            saved_config = project.archive_config
            
            assert saved_config["wayback_machine"]["timeout_seconds"] == 120
            assert saved_config["wayback_machine"]["custom_headers"]["User-Agent"] == "CustomBot/1.0"
            assert saved_config["wayback_machine"]["retry_codes"] == [502, 503, 522]
            assert saved_config["wayback_machine"]["enabled_features"]["compression"] == True
            assert saved_config["wayback_machine"]["enabled_features"]["javascript"] is None
            
            assert saved_config["common_crawl"]["collections"] == ["CC-MAIN-2024-10", "CC-MAIN-2024-22"]
            assert saved_config["common_crawl"]["filters"]["mime_types"] == ["text/html", "application/pdf"]
            
            assert saved_config["routing"]["fallback_strategy"] == "circuit_breaker"
            assert saved_config["routing"]["weights"]["primary"] == 0.8
            break

    def test_archive_config_update_scenarios(self, client: TestClient, auth_headers):
        """Test various archive config update scenarios"""
        # Create initial project
        initial_data = {
            "name": "Config Update Test",
            "archive_source": ArchiveSource.WAYBACK_MACHINE.value,
            "archive_config": {
                "wayback_machine": {
                    "timeout_seconds": 60,
                    "page_size": 1000,
                    "max_retries": 3
                }
            }
        }
        
        create_response = client.post(
            "/api/v1/projects/",
            json=initial_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]
        
        # Test 1: Add Common Crawl config (switch to hybrid)
        update1 = {
            "archive_source": ArchiveSource.HYBRID.value,
            "archive_config": {
                "wayback_machine": {
                    "timeout_seconds": 90,  # Updated
                    "page_size": 1000,      # Unchanged
                    "max_retries": 3        # Unchanged
                },
                "common_crawl": {           # New section
                    "timeout_seconds": 180,
                    "page_size": 5000
                }
            }
        }
        
        response1 = client.put(f"/api/v1/projects/{project_id}", json=update1, headers=auth_headers)
        assert response1.status_code == 200
        data1 = response1.json()
        
        assert data1["archive_source"] == ArchiveSource.HYBRID.value
        assert data1["archive_config"]["wayback_machine"]["timeout_seconds"] == 90
        assert data1["archive_config"]["common_crawl"]["timeout_seconds"] == 180
        
        # Test 2: Remove section (update to Common Crawl only)
        update2 = {
            "archive_source": ArchiveSource.COMMON_CRAWL.value,
            "archive_config": {
                "common_crawl": {
                    "timeout_seconds": 200,  # Updated
                    "max_retries": 10        # New field
                }
                # wayback_machine section removed
            }
        }
        
        response2 = client.put(f"/api/v1/projects/{project_id}", json=update2, headers=auth_headers)
        assert response2.status_code == 200
        data2 = response2.json()
        
        assert data2["archive_source"] == ArchiveSource.COMMON_CRAWL.value
        assert data2["archive_config"]["common_crawl"]["timeout_seconds"] == 200
        assert data2["archive_config"]["common_crawl"]["max_retries"] == 10
        # Wayback section should be removed (or preserved, depending on implementation)

    def test_concurrent_updates_archive_config(self, client: TestClient, auth_headers):
        """Test concurrent updates to archive configuration"""
        # Create project
        project_data = {
            "name": "Concurrent Update Test",
            "archive_config": {"initial": "config"}
        }
        
        create_response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]
        
        # Simulate concurrent updates (simplified test)
        update1 = {
            "archive_config": {
                "wayback_machine": {"timeout_seconds": 100}
            }
        }
        
        update2 = {
            "archive_config": {
                "common_crawl": {"max_retries": 5}
            }
        }
        
        # Apply updates sequentially (real concurrency would require threading/async)
        response1 = client.put(f"/api/v1/projects/{project_id}", json=update1, headers=auth_headers)
        response2 = client.put(f"/api/v1/projects/{project_id}", json=update2, headers=auth_headers)
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Final state depends on implementation (last write wins vs merge)
        final_response = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
        assert final_response.status_code == 200
        final_data = final_response.json()
        
        # At least one of the updates should be preserved
        config = final_data["archive_config"]
        has_wayback = "wayback_machine" in config
        has_common_crawl = "common_crawl" in config
        assert has_wayback or has_common_crawl


if __name__ == "__main__":
    pytest.main([__file__, "-v"])