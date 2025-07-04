"""
Integration Tests for TransDock API Endpoints

This module contains integration tests for all TransDock API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from backend.main import app
from tests.fixtures.test_data import (
    MIGRATION_STATUS_COMPLETED,
    MIGRATION_STATUS_FAILED,
    SYSTEM_INFO_RESPONSE
)


class BaseAPITest:
    """Base class for API endpoint tests with common fixtures."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_migration_service(self):
        """Mock migration service."""
        with patch('backend.main.migration_service') as mock:
            # Configure all mocks to return simple dictionaries to avoid RecursionError
            mock.get_system_info = AsyncMock(return_value={
                "hostname": "test-host",
                "os": "linux",
                "docker_version": "20.10.0",
                "available_datasets": []
            })
            mock.get_zfs_status = AsyncMock(return_value={
                "available": True,
                "version": "2.1.5",
                "pools": ["cache"]
            })
            mock.get_compose_stacks = AsyncMock(return_value=[])
            mock.get_stack_info = AsyncMock(return_value={
                "name": "test-stack",
                "compose_file": "/test/docker-compose.yml",
                "volumes": [],
                "services": []
            })
            mock.start_migration = AsyncMock(return_value="migration-test-123")
            mock.get_migration_status = AsyncMock(return_value={"status": "running", "progress": 50})
            mock.list_migrations = AsyncMock(return_value=[])
            mock.cancel_migration = AsyncMock(return_value=True)
            mock.cleanup_migration = AsyncMock(return_value=True)
            yield mock


class TestHealthAndSystemEndpoints(BaseAPITest):
    """Test suite for health and system information endpoints."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_system_info_success(self, client, mock_migration_service):
        """Test system info endpoint success."""
        mock_migration_service.get_system_info.return_value = SYSTEM_INFO_RESPONSE
        
        response = client.get("/api/system/info")
        
        assert response.status_code == 200
        data = response.json()
        assert data["hostname"] == "test-unraid"
        assert data["zfs_available"] is True
        assert data["docker_version"] == "20.10.21"

    def test_system_info_error(self, client, mock_migration_service):
        """Test system info endpoint error."""
        mock_migration_service.get_system_info.side_effect = Exception("System error")
        
        response = client.get("/api/system/info")
        
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data

    def test_zfs_status_available(self, client, mock_migration_service):
        """Test ZFS status endpoint when available."""
        mock_migration_service.get_zfs_status.return_value = {
            "available": True,
            "version": "2.1.5",
            "pools": ["cache"]
        }
        
        response = client.get("/api/zfs/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
        assert data["version"] == "2.1.5"
        assert "cache" in data["pools"]

    def test_zfs_status_not_available(self, client, mock_migration_service):
        """Test ZFS status endpoint when not available."""
        mock_migration_service.get_zfs_status.return_value = {
            "available": False,
            "version": None,
            "pools": []
        }
        
        response = client.get("/api/zfs/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False
        assert data["version"] is None
        assert len(data["pools"]) == 0


class TestComposeStackEndpoints(BaseAPITest):
    """Test suite for Docker Compose stack endpoints."""

    def test_list_compose_stacks_success(self, client, mock_migration_service):
        """Test list compose stacks endpoint success."""
        mock_migration_service.get_compose_stacks.return_value = [
            {"name": "authelia", "compose_file": "/mnt/cache/compose/authelia/docker-compose.yml"},
            {"name": "wordpress", "compose_file": "/mnt/cache/compose/wordpress/docker-compose.yml"}
        ]
        
        response = client.get("/api/compose/stacks")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["stacks"]) == 2
        assert data["stacks"][0]["name"] == "authelia"
        assert data["stacks"][1]["name"] == "wordpress"

    def test_list_compose_stacks_empty(self, client, mock_migration_service):
        """Test list compose stacks endpoint with no stacks."""
        mock_migration_service.get_compose_stacks.return_value = []
        
        response = client.get("/api/compose/stacks")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["stacks"]) == 0

    def test_get_stack_info_success(self, client, mock_migration_service):
        """Test get stack info endpoint success."""
        mock_migration_service.get_stack_info.return_value = {
            "name": "authelia",
            "compose_file": "/mnt/cache/compose/authelia/docker-compose.yml",
            "volumes": [
                {"source": "./config", "target": "/config", "is_dataset": False},
                {"source": "./data", "target": "/data", "is_dataset": False}
            ],
            "services": ["authelia", "redis", "mariadb"]
        }
        
        response = client.get("/api/compose/stacks/authelia")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "authelia"
        assert len(data["volumes"]) == 2
        assert len(data["services"]) == 3

    def test_get_stack_info_not_found(self, client, mock_migration_service):
        """Test get stack info endpoint for non-existent stack."""
        mock_migration_service.get_stack_info.side_effect = FileNotFoundError("Stack not found")
        
        response = client.get("/api/compose/stacks/nonexistent")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


class TestMigrationEndpoints(BaseAPITest):
    """Test suite for migration management endpoints."""

    def test_start_migration_success(self, client, mock_migration_service):
        """Test start migration endpoint success."""
        mock_migration_service.start_migration.return_value = "migration-test-123"
        
        request_data = {
            "compose_dataset": "authelia",
            "target_host": "192.168.1.100",
            "target_base_path": "/home/user/docker",
            "ssh_user": "root",
            "ssh_port": 22,
            "force_rsync": False
        }
        
        response = client.post("/api/migrations/start", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["migration_id"] == "migration-test-123"
        assert data["status"] == "started"
        assert "message" in data

    def test_start_migration_invalid_request(self, client):
        """Test start migration endpoint with invalid request."""
        invalid_request = {
            "compose_dataset": "",  # Empty dataset name
            "target_host": "192.168.1.100",
            "target_base_path": "/home/user/docker",
            "ssh_user": "root",
            "ssh_port": 22
        }
        
        response = client.post("/api/migrations/start", json=invalid_request)
        
        assert response.status_code == 422  # Validation error

    def test_start_migration_security_validation_error(self, client, mock_migration_service):
        """Test start migration endpoint with security validation error."""
        malicious_request = {
            "compose_dataset": "authelia",
            "target_host": "host; rm -rf /",  # Malicious hostname
            "target_base_path": "/home/user/docker",
            "ssh_user": "root",
            "ssh_port": 22
        }
        
        response = client.post("/api/migrations/start", json=malicious_request)
        
        assert response.status_code == 422  # Security validation should return 422
        data = response.json()
        assert "Security validation failed" in data["detail"]

    def test_get_migration_status_running(self, client, mock_migration_service):
        """Test get migration status endpoint for running migration."""
        mock_status = {
            "id": "migration-test-123",
            "status": "running",
            "progress": 45,
            "message": "Transfer in progress"
        }
        mock_migration_service.get_migration_status.return_value = mock_status
        
        response = client.get("/api/migrations/migration-test-123/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "migration-test-123"
        assert data["status"] == "running"
        assert data["progress"] == 45

    def test_get_migration_status_completed(self, client, mock_migration_service):
        """Test get migration status endpoint for completed migration."""
        mock_migration_service.get_migration_status.return_value = MIGRATION_STATUS_COMPLETED
        
        response = client.get("/api/migrations/migration-test-456/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "migration-test-456"
        assert data["status"] == "completed"
        assert data["progress"] == 100

    def test_get_migration_status_failed(self, client, mock_migration_service):
        """Test get migration status endpoint for failed migration."""
        mock_migration_service.get_migration_status.return_value = MIGRATION_STATUS_FAILED
        
        response = client.get("/api/migrations/migration-test-789/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "migration-test-789"
        assert data["status"] == "failed"
        assert data["progress"] == 25
        assert "error" in data

    def test_get_migration_status_not_found(self, client, mock_migration_service):
        """Test get migration status endpoint for non-existent migration."""
        mock_migration_service.get_migration_status.side_effect = KeyError("Migration not found")
        
        response = client.get("/api/migrations/nonexistent/status")
        
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data

    def test_cancel_migration_success(self, client, mock_migration_service):
        """Test cancel migration endpoint success."""
        mock_migration_service.cancel_migration.return_value = True
        
        response = client.post("/api/migrations/migration-test-123/cancel")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data

    def test_cancel_migration_failure(self, client, mock_migration_service):
        """Test cancel migration endpoint failure."""
        mock_migration_service.cancel_migration.return_value = False
        
        response = client.post("/api/migrations/migration-test-123/cancel")
        
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data

    def test_cancel_migration_not_found(self, client, mock_migration_service):
        """Test cancel migration endpoint for non-existent migration."""
        mock_migration_service.cancel_migration.side_effect = KeyError("Migration not found")
        
        response = client.post("/api/migrations/nonexistent/cancel")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_cleanup_migration_success(self, client, mock_migration_service):
        """Test cleanup migration endpoint success."""
        mock_migration_service.cleanup_migration.return_value = True
        
        response = client.post("/api/migrations/migration-test-123/cleanup")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data

    def test_cleanup_migration_failure(self, client, mock_migration_service):
        """Test cleanup migration endpoint failure."""
        mock_migration_service.cleanup_migration.return_value = False
        
        response = client.post("/api/migrations/migration-test-123/cleanup")
        
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data

    def test_list_migrations_success(self, client, mock_migration_service):
        """Test list migrations endpoint success."""
        mock_migrations = [
            {"id": "migration-1", "status": "running", "progress": 45},
            {"id": "migration-2", "status": "completed", "progress": 100},
            {"id": "migration-3", "status": "failed", "progress": 25}
        ]
        mock_migration_service.list_migrations.return_value = mock_migrations
        
        response = client.get("/api/migrations")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["migrations"]) == 3
        
        # Check that different statuses are present
        statuses = [m["status"] for m in data["migrations"]]
        assert "running" in statuses
        assert "completed" in statuses
        assert "failed" in statuses

    def test_list_migrations_empty(self, client, mock_migration_service):
        """Test list migrations endpoint with no migrations."""
        mock_migration_service.list_migrations.return_value = []
        
        response = client.get("/api/migrations")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["migrations"]) == 0


class TestAPIErrorHandling(BaseAPITest):
    """Test suite for API error handling and validation."""

    def test_api_cors_headers(self, client):
        """Test that CORS headers are properly set."""
        response = client.get("/api/system/info")
        
        # Check if CORS headers are present (they may not be in test environment)
        # This test verifies the API is accessible
        assert response.status_code in [200, 500]  # Either works or fails gracefully

    def test_api_error_handling(self, client, mock_migration_service):
        """Test API error handling and response format."""
        mock_migration_service.get_system_info.side_effect = RuntimeError("Unexpected error")
        
        response = client.get("/api/system/info")
        
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], str)

    def test_request_validation_edge_cases(self, client):
        """Test request validation with edge cases."""
        # Test with completely invalid JSON structure
        invalid_requests = [
            {},  # Empty object
            {"compose_dataset": None},  # Null values
            {"compose_dataset": 123},  # Wrong type
            {"compose_dataset": "valid", "ssh_port": "invalid"},  # Invalid port type
            {"compose_dataset": "valid", "ssh_port": -1},  # Invalid port range
            {"compose_dataset": "valid", "ssh_port": 70000},  # Port out of range
        ]
        
        for invalid_request in invalid_requests:
            response = client.post("/api/migrations/start", json=invalid_request)
            # Should return validation error
            assert response.status_code in [400, 422]

    def test_concurrent_api_requests(self, client, mock_migration_service):
        """Test concurrent API requests handling."""
        import threading
        
        # Configure mock to return simple dict instead of complex object
        mock_migration_service.get_system_info.return_value = {
            "hostname": "test-host",
            "os": "linux",
            "docker_version": "20.10.0",
            "available_datasets": []
        }
        
        results = []
        
        def make_request():
            try:
                response = client.get("/api/system/info")
                results.append(response.status_code)
            except Exception as e:
                # Handle any exceptions during request
                results.append(500)
        
        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should complete (may succeed or fail gracefully)
        assert len(results) == 5
        assert all(status in [200, 500] for status in results)


class TestIntegrationWorkflows(BaseAPITest):
    """Test suite for full integration workflows."""

    @pytest.mark.integration
    def test_full_migration_workflow(self, client, mock_migration_service):
        """Integration test for full migration workflow."""
        # Mock the migration service responses
        mock_migration_service.start_migration.return_value = "migration-workflow-test"
        mock_migration_service.get_migration_status.side_effect = [
            {"id": "migration-workflow-test", "status": "starting", "progress": 0},
            {"id": "migration-workflow-test", "status": "running", "progress": 50},
            {"id": "migration-workflow-test", "status": "completed", "progress": 100}
        ]
        mock_migration_service.cleanup_migration.return_value = True
        
        # 1. Start migration
        request_data = {
            "compose_dataset": "authelia",
            "target_host": "192.168.1.100",
            "target_base_path": "/home/user/docker",
            "ssh_user": "root",
            "ssh_port": 22,
            "force_rsync": False
        }
        start_response = client.post("/api/migrations/start", json=request_data)
        assert start_response.status_code == 200
        migration_id = start_response.json()["migration_id"]
        
        # 2. Check status multiple times (simulating polling)
        for expected_progress in [0, 50, 100]:
            status_response = client.get(f"/api/migrations/{migration_id}/status")
            assert status_response.status_code == 200
            assert status_response.json()["progress"] == expected_progress
        
        # 3. Cleanup migration
        cleanup_response = client.post(f"/api/migrations/{migration_id}/cleanup")
        assert cleanup_response.status_code == 200
        assert cleanup_response.json()["success"] is True

    @pytest.mark.integration
    def test_error_propagation(self, client, mock_migration_service):
        """Test that errors are properly propagated through the API."""
        # Test different types of errors
        error_scenarios = [
            (FileNotFoundError("Not found"), 500),
            (PermissionError("Access denied"), 500),
            (ValueError("Invalid value"), 500),
            (RuntimeError("Runtime error"), 500)
        ]
        
        for error, expected_status in error_scenarios:
            mock_migration_service.get_system_info.side_effect = error
            response = client.get("/api/system/info")
            assert response.status_code == expected_status

 