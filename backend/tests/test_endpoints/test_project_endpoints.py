"""
Tests for project API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.user import User
from app.models.project import Project


class TestProjectEndpoints:
    """Test project API endpoints."""

    def test_create_project(self, client: TestClient, auth_headers: dict):
        """Test project creation endpoint."""
        project_data = {
            "name": "Test Project",
            "description": "A project for testing",
            "config": {
                "urls": ["https://example.com"],
                "schedule": "0 */6 * * *"
            }
        }
        
        response = client.post(
            "/api/v1/projects/",
            json=project_data,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["description"] == "A project for testing"
        assert data["config"]["urls"] == ["https://example.com"]
        assert "id" in data
        assert "created_at" in data

    def test_create_project_unauthorized(self, client: TestClient):
        """Test project creation without authentication."""
        project_data = {
            "name": "Unauthorized Project",
            "description": "Should fail"
        }
        
        response = client.post("/api/v1/projects/", json=project_data)
        assert response.status_code == 401

    def test_create_project_invalid_data(self, client: TestClient, auth_headers: dict):
        """Test project creation with invalid data."""
        # Missing required name field
        response = client.post(
            "/api/v1/projects/",
            json={"description": "Missing name"},
            headers=auth_headers
        )
        assert response.status_code == 422

        # Invalid config format
        response = client.post(
            "/api/v1/projects/",
            json={
                "name": "Invalid Config",
                "config": "should_be_object"
            },
            headers=auth_headers
        )
        assert response.status_code == 422

    def test_list_projects(self, client: TestClient, auth_headers: dict, test_project: Project):
        """Test listing user projects."""
        response = client.get("/api/v1/projects/", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        
        # Check that our test project is in the list
        project_names = [project["name"] for project in data]
        assert test_project.name in project_names

    def test_list_projects_unauthorized(self, client: TestClient):
        """Test listing projects without authentication."""
        response = client.get("/api/v1/projects/")
        assert response.status_code == 401

    def test_get_project_by_id(self, client: TestClient, auth_headers: dict, test_project: Project):
        """Test retrieving a specific project."""
        response = client.get(
            f"/api/v1/projects/{test_project.id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_project.id
        assert data["name"] == test_project.name
        assert data["description"] == test_project.description

    def test_get_project_not_found(self, client: TestClient, auth_headers: dict):
        """Test retrieving non-existent project."""
        response = client.get("/api/v1/projects/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_get_project_unauthorized(self, client: TestClient, test_project: Project):
        """Test retrieving project without authentication."""
        response = client.get(f"/api/v1/projects/{test_project.id}")
        assert response.status_code == 401

    def test_update_project(self, client: TestClient, auth_headers: dict, test_project: Project):
        """Test updating a project."""
        update_data = {
            "name": "Updated Project Name",
            "description": "Updated description",
            "config": {
                "urls": ["https://updated-example.com"],
                "schedule": "0 */12 * * *"
            }
        }
        
        response = client.put(
            f"/api/v1/projects/{test_project.id}",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Project Name"
        assert data["description"] == "Updated description"
        assert data["config"]["urls"] == ["https://updated-example.com"]

    def test_update_project_partial(self, client: TestClient, auth_headers: dict, test_project: Project):
        """Test partial project update."""
        update_data = {"name": "Partially Updated Name"}
        
        response = client.put(
            f"/api/v1/projects/{test_project.id}",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Partially Updated Name"
        # Original description should remain
        assert data["description"] == test_project.description

    def test_update_project_not_found(self, client: TestClient, auth_headers: dict):
        """Test updating non-existent project."""
        response = client.put(
            "/api/v1/projects/99999",
            json={"name": "Non-existent"},
            headers=auth_headers
        )
        assert response.status_code == 404

    def test_update_project_unauthorized(self, client: TestClient, test_project: Project):
        """Test updating project without authentication."""
        response = client.put(
            f"/api/v1/projects/{test_project.id}",
            json={"name": "Unauthorized Update"}
        )
        assert response.status_code == 401

    def test_delete_project(self, client: TestClient, auth_headers: dict, session: Session, test_user: User):
        """Test deleting a project."""
        # Create a project specifically for deletion
        project = Project(
            name="To Delete",
            description="Project to be deleted",
            owner_id=test_user.id
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        
        response = client.delete(
            f"/api/v1/projects/{project.id}",
            headers=auth_headers
        )
        
        assert response.status_code == 204

        # Verify project is deleted
        get_response = client.get(
            f"/api/v1/projects/{project.id}",
            headers=auth_headers
        )
        assert get_response.status_code == 404

    def test_delete_project_not_found(self, client: TestClient, auth_headers: dict):
        """Test deleting non-existent project."""
        response = client.delete("/api/v1/projects/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_project_unauthorized(self, client: TestClient, test_project: Project):
        """Test deleting project without authentication."""
        response = client.delete(f"/api/v1/projects/{test_project.id}")
        assert response.status_code == 401


class TestProjectConfigurationEndpoints:
    """Test project configuration endpoints."""

    def test_get_project_config(self, client: TestClient, auth_headers: dict, test_project: Project):
        """Test retrieving project configuration."""
        response = client.get(
            f"/api/v1/projects/{test_project.id}/config",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data == test_project.config

    def test_update_project_config(self, client: TestClient, auth_headers: dict, test_project: Project):
        """Test updating project configuration."""
        new_config = {
            "urls": ["https://new-example.com", "https://another-site.com"],
            "schedule": "0 */8 * * *",
            "filters": {
                "include": ["article", "blog"],
                "exclude": ["advertisement"]
            }
        }
        
        response = client.put(
            f"/api/v1/projects/{test_project.id}/config",
            json=new_config,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["urls"] == new_config["urls"]
        assert data["schedule"] == new_config["schedule"]
        assert data["filters"] == new_config["filters"]

    def test_validate_project_config(self, client: TestClient, auth_headers: dict, test_project: Project):
        """Test project configuration validation."""
        invalid_config = {
            "urls": "should_be_array",  # Invalid: should be array
            "schedule": "invalid_cron"  # Invalid: not a valid cron expression
        }
        
        response = client.put(
            f"/api/v1/projects/{test_project.id}/config",
            json=invalid_config,
            headers=auth_headers
        )
        
        assert response.status_code == 422


class TestProjectExecutionEndpoints:
    """Test project execution endpoints."""

    def test_start_project_execution(self, client: TestClient, auth_headers: dict, test_project: Project):
        """Test starting project execution."""
        response = client.post(
            f"/api/v1/projects/{test_project.id}/execute",
            headers=auth_headers
        )
        
        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert "status" in data
        assert data["status"] == "started"

    def test_get_project_execution_status(self, client: TestClient, auth_headers: dict, test_project: Project):
        """Test retrieving project execution status."""
        # First start execution
        start_response = client.post(
            f"/api/v1/projects/{test_project.id}/execute",
            headers=auth_headers
        )
        task_id = start_response.json()["task_id"]
        
        # Then check status
        response = client.get(
            f"/api/v1/projects/{test_project.id}/status",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "task_id" in data

    def test_stop_project_execution(self, client: TestClient, auth_headers: dict, test_project: Project):
        """Test stopping project execution."""
        # First start execution
        client.post(
            f"/api/v1/projects/{test_project.id}/execute",
            headers=auth_headers
        )
        
        # Then stop it
        response = client.post(
            f"/api/v1/projects/{test_project.id}/stop",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"

    def test_get_project_results(self, client: TestClient, auth_headers: dict, test_project: Project):
        """Test retrieving project execution results."""
        response = client.get(
            f"/api/v1/projects/{test_project.id}/results",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Results structure depends on implementation
        # but should at least be a valid response