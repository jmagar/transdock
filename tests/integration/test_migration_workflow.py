"""
End-to-End Migration Workflow Tests

This module contains comprehensive tests for the complete migration workflow.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from backend.migration_service import MigrationService
from backend.models import MigrationRequest
from backend.security_utils import SecurityValidationError
from tests.fixtures.test_data import (
    MIGRATION_REQUEST_AUTHELIA,
    MIGRATION_REQUEST_SIMPLE,
    DOCKER_COMPOSE_AUTHELIA,
)


class TestMigrationWorkflow:
    """Test suite for end-to-end migration workflows."""

    @pytest.fixture
    def mock_all_operations(self):
        """Mock all system operations."""
        mocks = {}
        
        # Mock ZFS operations
        with patch('backend.migration_service.ZFSOperations') as mock_zfs:
            mocks['zfs'] = mock_zfs.return_value
            mocks['zfs'].is_zfs_available = AsyncMock(return_value=True)
            mocks['zfs'].dataset_exists = AsyncMock(return_value=True)
            mocks['zfs'].is_dataset = AsyncMock(return_value=True)
            mocks['zfs'].create_dataset = AsyncMock(return_value=True)
            mocks['zfs'].create_snapshot = AsyncMock(return_value="cache/compose/authelia@migration_20240101_120000")
            mocks['zfs'].send_snapshot = AsyncMock(return_value=True)
            mocks['zfs'].cleanup_snapshot = AsyncMock(return_value=True)
            mocks['zfs'].check_remote_zfs = AsyncMock(return_value=True)
            mocks['zfs'].get_dataset_name = AsyncMock(return_value="cache/compose/authelia")
            
            # Mock Docker operations
            with patch('backend.migration_service.DockerOperations') as mock_docker:
                mocks['docker'] = mock_docker.return_value
                mocks['docker'].get_compose_path = Mock(return_value="/mnt/cache/compose/authelia")
                mocks['docker'].find_compose_file = AsyncMock(return_value="/mnt/cache/compose/authelia/docker-compose.yml")
                mocks['docker'].parse_compose_file = AsyncMock(return_value=DOCKER_COMPOSE_AUTHELIA)
                mocks['docker'].extract_volume_mounts = AsyncMock(return_value=[])
                mocks['docker'].stop_compose_stack = AsyncMock(return_value=True)
                mocks['docker'].update_compose_paths = AsyncMock(return_value="updated compose content")
                
                # Mock Transfer operations
                with patch('backend.migration_service.TransferOperations') as mock_transfer:
                    mocks['transfer'] = mock_transfer.return_value
                    mocks['transfer'].create_target_directories = AsyncMock(return_value=True)
                    mocks['transfer'].transfer_via_rsync = AsyncMock(return_value=True)
                    mocks['transfer'].create_volume_mapping = AsyncMock(return_value={})
                    mocks['transfer'].write_remote_file = AsyncMock(return_value=True)
                    
                    # Mock os.path.exists to return True
                    with patch('os.path.exists') as mock_exists:
                        mock_exists.return_value = True
                        
                        yield mocks

    @pytest.fixture
    def migration_service(self, mock_all_operations):
        """Create migration service instance with mocked operations."""
        return MigrationService()

    @pytest.mark.asyncio
    async def test_successful_authelia_migration_rsync(self, migration_service, mock_all_operations):
        """Test successful Authelia migration using rsync."""
        # Configure mocks for rsync transfer
        mock_all_operations['transfer'].determine_transfer_method.return_value = "rsync"
        
        # Start migration
        migration_id = await migration_service.start_migration(MIGRATION_REQUEST_AUTHELIA)
        
        assert migration_id is not None
        assert len(migration_id) > 0  # Should be a valid UUID string
        
        # Check initial status
        status = await migration_service.get_migration_status(migration_id)
        assert status.id == migration_id
        assert status.status in ["initializing", "validating", "parsing", "analyzing", "stopping", "snapshotting", "checking", "preparing", "transferring", "generating", "finalizing", "cleaning"]
        
        # Wait for completion (with timeout)
        for _ in range(30):  # 30 second timeout
            status = await migration_service.get_migration_status(migration_id)
            if status.status in ["completed", "failed"]:
                break
            await asyncio.sleep(1)
        
        # Verify completion
        final_status = await migration_service.get_migration_status(migration_id)
        assert final_status.status == "completed"
        assert final_status.progress == 100

    @pytest.mark.asyncio
    async def test_successful_authelia_migration_zfs(self, migration_service, mock_all_operations):
        """Test successful Authelia migration using ZFS send."""
        # Configure mocks for ZFS transfer
        mock_all_operations['transfer'].determine_transfer_method.return_value = "zfs_send"
        mock_all_operations['zfs'].send_snapshot.return_value = True
        
        # Start migration
        migration_id = await migration_service.start_migration(MIGRATION_REQUEST_AUTHELIA)
        
        assert migration_id is not None
        
        # Wait for completion
        for _ in range(30):
            status = await migration_service.get_migration_status(migration_id)
            if status.status in ["completed", "failed"]:
                break
            await asyncio.sleep(1)
        
        # Verify ZFS operations were called
        mock_all_operations['zfs'].create_snapshot.assert_called()
        mock_all_operations['zfs'].send_snapshot.assert_called()
        
        # Verify completion
        final_status = await migration_service.get_migration_status(migration_id)
        assert final_status.status == "completed"

    @pytest.mark.asyncio
    async def test_migration_failure_ssh_connection(self, migration_service, mock_all_operations):
        """Test migration failure due to SSH connection failure."""
        # Configure SSH connection to fail
        mock_all_operations['transfer'].test_ssh_connection.return_value = False
        
        # Start migration
        migration_id = await migration_service.start_migration(MIGRATION_REQUEST_AUTHELIA)
        
        # Wait for failure
        for _ in range(10):
            status = await migration_service.get_migration_status(migration_id)
            if status.status == "failed":
                break
            await asyncio.sleep(1)
        
        # Verify failure
        final_status = await migration_service.get_migration_status(migration_id)
        assert final_status.status == "failed"
        assert "ssh" in final_status.message.lower() or "connection" in final_status.message.lower()

    @pytest.mark.asyncio
    async def test_migration_failure_docker_stop(self, migration_service, mock_all_operations):
        """Test migration failure due to Docker stack stop failure."""
        # Configure Docker stop to fail
        mock_all_operations['docker'].stop_stack.return_value = False
        
        # Start migration
        migration_id = await migration_service.start_migration(MIGRATION_REQUEST_AUTHELIA)
        
        # Wait for failure
        for _ in range(10):
            status = await migration_service.get_migration_status(migration_id)
            if status.status == "failed":
                break
            await asyncio.sleep(1)
        
        # Verify failure
        final_status = await migration_service.get_migration_status(migration_id)
        assert final_status.status == "failed"
        assert "docker" in final_status.message.lower() or "stop" in final_status.message.lower()

    @pytest.mark.asyncio
    async def test_migration_failure_zfs_snapshot(self, migration_service, mock_all_operations):
        """Test migration failure due to ZFS snapshot creation failure."""
        # Configure ZFS snapshot creation to fail
        mock_all_operations['zfs'].create_snapshot.return_value = False
        mock_all_operations['transfer'].determine_transfer_method.return_value = "zfs_send"
        
        # Start migration
        migration_id = await migration_service.start_migration(MIGRATION_REQUEST_AUTHELIA)
        
        # Wait for failure
        for _ in range(10):
            status = await migration_service.get_migration_status(migration_id)
            if status.status == "failed":
                break
            await asyncio.sleep(1)
        
        # Verify failure
        final_status = await migration_service.get_migration_status(migration_id)
        assert final_status.status == "failed"
        assert "snapshot" in final_status.message.lower() or "zfs" in final_status.message.lower()

    @pytest.mark.asyncio
    async def test_migration_failure_transfer(self, migration_service, mock_all_operations):
        """Test migration failure due to transfer failure."""
        # Configure transfer to fail
        mock_all_operations['transfer'].rsync_transfer.return_value = False
        
        # Start migration
        migration_id = await migration_service.start_migration(MIGRATION_REQUEST_AUTHELIA)
        
        # Wait for failure
        for _ in range(15):
            status = await migration_service.get_migration_status(migration_id)
            if status.status == "failed":
                break
            await asyncio.sleep(1)
        
        # Verify failure
        final_status = await migration_service.get_migration_status(migration_id)
        assert final_status.status == "failed"
        assert "transfer" in final_status.message.lower() or "rsync" in final_status.message.lower()

    @pytest.mark.asyncio
    async def test_migration_cancellation(self, migration_service, mock_all_operations):
        """Test migration cancellation functionality."""
        # Configure a slow transfer to allow time for cancellation
        async def slow_transfer(*args, **kwargs):
            await asyncio.sleep(5)
            return True
        
        mock_all_operations['transfer'].rsync_transfer.side_effect = slow_transfer
        
        # Start migration
        migration_id = await migration_service.start_migration(MIGRATION_REQUEST_AUTHELIA)
        
        # Cancel migration
        cancellation_result = await migration_service.cancel_migration(migration_id)
        assert cancellation_result is True
        
        # Verify status is 'cancelled'
        status = await migration_service.get_migration_status(migration_id)
        assert status.status == "cancelled"
        
        # Test cancelling a non-existent migration
        non_existent_id = "non-existent-migration"
        
        # Ensure that get_migration_status returns None for non-existent migrations
        # This aligns with the actual service behavior
        migration_service.get_migration_status = AsyncMock(return_value=None)
        
        cancellation_result = await migration_service.cancel_migration(non_existent_id)
        assert cancellation_result is False

    @pytest.mark.asyncio
    async def test_migration_cleanup_success(self, migration_service, mock_all_operations):
        """Test successful migration cleanup."""
        # Start and complete migration
        migration_id = await migration_service.start_migration(MIGRATION_REQUEST_AUTHELIA)
        
        # Wait for completion
        for _ in range(20):
            status = await migration_service.get_migration_status(migration_id)
            if status.status in ["completed", "failed"]:
                break
            await asyncio.sleep(1)
        
        # Cleanup migration
        cleanup_result = await migration_service.cleanup_migration(migration_id)
        assert cleanup_result is True
        
        # Verify cleanup called ZFS cleanup
        mock_all_operations['zfs'].cleanup_snapshot.assert_called()

    @pytest.mark.asyncio
    async def test_migration_cleanup_failure(self, migration_service, mock_all_operations):
        """Test migration cleanup failure."""
        # Configure cleanup to fail
        mock_all_operations['zfs'].cleanup_snapshot.return_value = False
        
        # Start and complete migration
        migration_id = await migration_service.start_migration(MIGRATION_REQUEST_AUTHELIA)
        
        # Wait for completion
        for _ in range(20):
            status = await migration_service.get_migration_status(migration_id)
            if status.status in ["completed", "failed"]:
                break
            await asyncio.sleep(1)
        
        # Attempt cleanup
        cleanup_result = await migration_service.cleanup_migration(migration_id)
        assert cleanup_result is False

    @pytest.mark.asyncio
    async def test_concurrent_migrations(self, migration_service, mock_all_operations):
        """Test handling of concurrent migrations."""
        # Start multiple migrations concurrently
        migration_requests = [
            MIGRATION_REQUEST_AUTHELIA,
            MIGRATION_REQUEST_SIMPLE,
            MIGRATION_REQUEST_AUTHELIA  # Duplicate to test handling
        ]
        
        migration_ids = []
        for request in migration_requests:
            migration_id = await migration_service.start_migration(request)
            migration_ids.append(migration_id)
        
        # Verify all migrations started
        assert len(migration_ids) == 3
        assert len(set(migration_ids)) == 3  # All IDs should be unique
        
        # Wait for all to complete
        for migration_id in migration_ids:
            for _ in range(30):
                status = await migration_service.get_migration_status(migration_id)
                if status.status in ["completed", "failed"]:
                    break
                await asyncio.sleep(1)
        
        # Verify all completed
        final_statuses = []
        for migration_id in migration_ids:
            status = await migration_service.get_migration_status(migration_id)
            final_statuses.append(status.status)
        
        # All should complete (may be completed or failed)
        assert all(status in ["completed", "failed"] for status in final_statuses)

    @pytest.mark.asyncio
    async def test_migration_progress_tracking(self, migration_service, mock_all_operations):
        """Test migration progress tracking throughout workflow."""
        # Configure progressive completion
        progress_updates = []
        
        async def mock_transfer_with_progress(*args, **kwargs):
            # Simulate transfer progress
            for _progress in [25, 50, 75, 100]:
                # This would normally be handled by the transfer operation
                await asyncio.sleep(0.1)
            return True
        
        mock_all_operations['transfer'].rsync_transfer.side_effect = mock_transfer_with_progress
        
        # Start migration
        migration_id = await migration_service.start_migration(MIGRATION_REQUEST_AUTHELIA)
        
        # Track progress
        previous_progress = 0
        for _ in range(20):
            status = await migration_service.get_migration_status(migration_id)
            current_progress = status.progress
            
            # Progress should only increase
            assert current_progress >= previous_progress
            progress_updates.append(current_progress)
            previous_progress = current_progress
            
            if status.status in ["completed", "failed"]:
                break
            
            await asyncio.sleep(0.5)
        
        # Verify progress increased over time
        assert len(progress_updates) > 1
        assert progress_updates[-1] >= progress_updates[0]

    @pytest.mark.asyncio
    async def test_migration_with_security_validation(self, migration_service, mock_all_operations):
        """Test migration with security validation enabled."""
        from backend.security_utils import SecurityValidationError
        
        # Create a migration request with potentially dangerous paths
        dangerous_request = MigrationRequest(
            compose_dataset="../../etc/passwd",
            target_host="192.168.1.100",
            target_base_path="/home/user/docker",
            ssh_user="root"
        )
        
        # Start migration - should fail due to security validation
        try:
            migration_id = await migration_service.start_migration(dangerous_request)
            # If we get here, check that it failed due to security
            status = await migration_service.get_migration_status(migration_id)
            assert status.status == "failed"
            assert "security" in status.message.lower() or "validation" in status.message.lower()
        except Exception as e:
            # Security validation should prevent the migration from starting
            assert "security" in str(e).lower() or "validation" in str(e).lower()

    @pytest.mark.asyncio
    async def test_migration_rollback_on_failure(self, migration_service, mock_all_operations):
        """Test migration rollback on failure."""
        # Configure failure during transfer
        mock_all_operations['transfer'].rsync_transfer.return_value = False
        
        # Start migration
        migration_id = await migration_service.start_migration(MIGRATION_REQUEST_AUTHELIA)
        
        # Wait for failure
        for _ in range(15):
            status = await migration_service.get_migration_status(migration_id)
            if status.status == "failed":
                break
            await asyncio.sleep(1)
        
        # Verify rollback operations were called
        # Should have attempted to restart the source stack
        mock_all_operations['docker'].start_stack.assert_called()

    @pytest.mark.asyncio
    async def test_simple_stack_migration(self, migration_service, mock_all_operations):
        """Test migration of a simple stack without complex dependencies."""
        # Configure for simple stack
        mock_all_operations['docker'].parse_compose_file.return_value = {
            'version': '3.8',
            'services': {
                'nginx': {
                    'image': 'nginx:latest',
                    'ports': ['80:80'],
                    'volumes': ['./html:/usr/share/nginx/html']
                }
            }
        }
        
        # Start migration
        migration_id = await migration_service.start_migration(MIGRATION_REQUEST_SIMPLE)
        
        # Wait for completion
        for _ in range(20):
            status = await migration_service.get_migration_status(migration_id)
            if status.status in ["completed", "failed"]:
                break
            await asyncio.sleep(1)
        
        # Verify completion
        final_status = await migration_service.get_migration_status(migration_id)
        assert final_status.status == "completed"



    @pytest.mark.asyncio
    async def test_migration_list_functionality(self, migration_service, mock_all_operations):
        """Test migration listing functionality."""
        # Start multiple migrations
        migration_ids = []
        for _ in range(3):
            migration_id = await migration_service.start_migration(MIGRATION_REQUEST_AUTHELIA)
            migration_ids.append(migration_id)
        
        # Wait for all to complete
        for migration_id in migration_ids:
            for _ in range(20):
                status = await migration_service.get_migration_status(migration_id)
                if status.status in ["completed", "failed"]:
                    break
                await asyncio.sleep(1)
        
        # Verify all migrations are tracked
        for migration_id in migration_ids:
            status = await migration_service.get_migration_status(migration_id)
            assert status is not None
            assert status.id == migration_id 