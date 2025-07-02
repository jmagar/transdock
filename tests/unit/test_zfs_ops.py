"""
Unit Tests for ZFS Operations Module

This module contains tests for ZFS operations with mocked system calls.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, Mock
from backend.zfs_ops import ZFSOperations
from tests.fixtures.test_data import MOCK_COMMAND_OUTPUTS, ZFS_DATASETS, ZFS_SNAPSHOTS


class TestZFSOperations:
    """Test suite for ZFS operations."""

    @pytest.fixture
    def zfs_ops(self):
        """Create ZFS operations instance."""
        return ZFSOperations()

    @pytest.mark.asyncio
    async def test_is_available_true(self, zfs_ops, mock_subprocess):
        """Test ZFS availability detection when ZFS is available."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "zfs-2.1.5"
        
        result = await zfs_ops.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_available_false(self, zfs_ops, mock_subprocess):
        """Test ZFS availability detection when ZFS is not available."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "command not found"
        
        result = await zfs_ops.is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_is_dataset_exists(self, zfs_ops, mock_subprocess):
        """Test dataset existence check."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "cache/compose"
        
        result = await zfs_ops.is_dataset("cache/compose")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_dataset_not_exists(self, zfs_ops, mock_subprocess):
        """Test dataset existence check when dataset doesn't exist."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "dataset does not exist"
        
        result = await zfs_ops.is_dataset("nonexistent/dataset")
        assert result is False

    @pytest.mark.asyncio
    async def test_create_dataset_success(self, zfs_ops, mock_subprocess):
        """Test successful dataset creation."""
        mock_subprocess.return_value.returncode = 0
        
        result = await zfs_ops.create_dataset("cache/test-dataset")
        assert result is True
        
        # Verify the correct command was called
        args, kwargs = mock_subprocess.call_args
        assert "zfs" in args[0][0]
        assert "create" in args[0]
        assert "cache/test-dataset" in args[0]

    @pytest.mark.asyncio
    async def test_create_dataset_failure(self, zfs_ops, mock_subprocess):
        """Test dataset creation failure."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "dataset already exists"
        
        result = await zfs_ops.create_dataset("cache/existing-dataset")
        assert result is False

    @pytest.mark.asyncio
    async def test_create_snapshot_success(self, zfs_ops, mock_subprocess):
        """Test successful snapshot creation."""
        mock_subprocess.return_value.returncode = 0
        
        result = await zfs_ops.create_snapshot("cache/compose@test-snapshot")
        assert result is True
        
        # Verify the correct command was called
        args, kwargs = mock_subprocess.call_args
        assert "zfs" in args[0][0]
        assert "snapshot" in args[0]
        assert "cache/compose@test-snapshot" in args[0]

    @pytest.mark.asyncio
    async def test_create_snapshot_failure(self, zfs_ops, mock_subprocess):
        """Test snapshot creation failure."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "dataset does not exist"
        
        result = await zfs_ops.create_snapshot("nonexistent/dataset@snapshot")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_snapshot_success(self, zfs_ops, mock_subprocess, mock_ssh_client):
        """Test successful snapshot send."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = MOCK_COMMAND_OUTPUTS['zfs_send_test']
        
        result = await zfs_ops.send_snapshot(
            snapshot="cache/compose@test",
            target_host="192.168.1.100",
            ssh_user="root",
            target_dataset="tank/compose"
        )
        
        assert result is True

    @pytest.mark.asyncio
    async def test_send_snapshot_failure(self, zfs_ops, mock_subprocess, mock_ssh_client):
        """Test snapshot send failure."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "cannot send snapshot"
        
        result = await zfs_ops.send_snapshot(
            snapshot="cache/compose@test",
            target_host="192.168.1.100", 
            ssh_user="root",
            target_dataset="tank/compose"
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_cleanup_snapshot_success(self, zfs_ops, mock_subprocess):
        """Test successful snapshot cleanup."""
        mock_subprocess.return_value.returncode = 0
        
        result = await zfs_ops.cleanup_snapshot("cache/compose@test-snapshot")
        assert result is True
        
        # Verify the correct command was called
        args, kwargs = mock_subprocess.call_args
        assert "zfs" in args[0][0]
        assert "destroy" in args[0]
        assert "cache/compose@test-snapshot" in args[0]

    @pytest.mark.asyncio
    async def test_cleanup_snapshot_failure(self, zfs_ops, mock_subprocess):
        """Test snapshot cleanup failure."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "snapshot does not exist"
        
        result = await zfs_ops.cleanup_snapshot("nonexistent@snapshot")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_datasets(self, zfs_ops, mock_subprocess):
        """Test getting list of datasets."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = MOCK_COMMAND_OUTPUTS['zfs_list']
        
        result = await zfs_ops.get_datasets()
        assert isinstance(result, list)
        assert len(result) > 0
        assert any("cache/compose" in dataset for dataset in result)

    @pytest.mark.asyncio
    async def test_get_datasets_empty(self, zfs_ops, mock_subprocess):
        """Test getting datasets when none exist."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = ""
        
        result = await zfs_ops.get_datasets()
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_safe_run_zfs_command_valid(self, zfs_ops, mock_subprocess):
        """Test safe ZFS command execution with valid command."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "success"
        mock_subprocess.return_value.stderr = ""
        
        returncode, stdout, stderr = await zfs_ops.safe_run_zfs_command("list", "cache")
        
        assert returncode == 0
        assert stdout == "success"
        assert stderr == ""

    @pytest.mark.asyncio
    async def test_safe_run_zfs_command_invalid(self, zfs_ops):
        """Test safe ZFS command execution with invalid command."""
        with pytest.raises(Exception):  # Should raise security validation error
            await zfs_ops.safe_run_zfs_command("list; rm -rf /", "cache")

    @pytest.mark.asyncio
    async def test_run_command_success(self, zfs_ops, mock_subprocess):
        """Test generic command execution success."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "command output"
        mock_subprocess.return_value.stderr = ""
        
        returncode, stdout, stderr = await zfs_ops.run_command(["echo", "test"])
        
        assert returncode == 0
        assert stdout == "command output"
        assert stderr == ""

    @pytest.mark.asyncio
    async def test_run_command_failure(self, zfs_ops, mock_subprocess):
        """Test generic command execution failure."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stdout = ""
        mock_subprocess.return_value.stderr = "command failed"
        
        returncode, stdout, stderr = await zfs_ops.run_command(["false"])
        
        assert returncode == 1
        assert stdout == ""
        assert stderr == "command failed"

    @pytest.mark.zfs
    async def test_integration_create_snapshot_and_cleanup(self, zfs_ops, mock_subprocess):
        """Integration test for creating and cleaning up snapshots."""
        # Mock successful snapshot creation
        mock_subprocess.return_value.returncode = 0
        
        # Create snapshot
        create_result = await zfs_ops.create_snapshot("cache/test@integration")
        assert create_result is True
        
        # Cleanup snapshot  
        cleanup_result = await zfs_ops.cleanup_snapshot("cache/test@integration")
        assert cleanup_result is True
        
        # Verify both commands were called
        assert mock_subprocess.call_count == 2

    @pytest.mark.zfs
    async def test_error_handling_invalid_dataset_names(self, zfs_ops):
        """Test error handling for invalid dataset names."""
        invalid_datasets = [
            "",
            "dataset; rm -rf /",
            "dataset`rm -rf /`",
            "dataset$(rm -rf /)",
            "../../../etc/passwd"
        ]
        
        for invalid_dataset in invalid_datasets:
            with pytest.raises(Exception):  # Should raise validation error
                await zfs_ops.create_dataset(invalid_dataset)

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, zfs_ops, mock_subprocess):
        """Test concurrent ZFS operations."""
        import asyncio
        
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "success"
        
        # Run multiple operations concurrently
        tasks = [
            zfs_ops.is_dataset(f"cache/test{i}")
            for i in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(result is True for result in results)
        assert mock_subprocess.call_count == 5

    @pytest.mark.asyncio
    async def test_command_timeout_handling(self, zfs_ops):
        """Test handling of command timeouts."""
        with patch('asyncio.create_subprocess_exec') as mock_create:
            # Mock a process that times out
            mock_process = Mock()
            mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
            mock_process.returncode = None
            mock_create.return_value = mock_process
            
            # This should handle the timeout gracefully
            returncode, stdout, stderr = await zfs_ops.run_command(["sleep", "30"])
            
            # Should return error state
            assert returncode != 0 