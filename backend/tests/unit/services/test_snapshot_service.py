import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from typing import Dict, Any, List

from backend.zfs_operations.services.snapshot_service import SnapshotService
from backend.zfs_operations.core.entities.snapshot import Snapshot
from backend.zfs_operations.core.value_objects.size_value import SizeValue
from backend.zfs_operations.core.exceptions.zfs_exceptions import (
    SnapshotException,
    SnapshotNotFoundError,
    SnapshotExistsError
)
from backend.zfs_operations.core.exceptions.validation_exceptions import ValidationException
from backend.zfs_operations.core.result import Result
from backend.zfs_operations.core.interfaces.command_executor import CommandResult


class TestSnapshotService:
    """Test suite for SnapshotService."""
    
    @pytest.fixture
    def mock_executor(self):
        """Create mock command executor."""
        executor = Mock()
        executor.execute_zfs = AsyncMock()
        executor.execute_system = AsyncMock()
        return executor
    
    @pytest.fixture
    def mock_validator(self):
        """Create mock security validator."""
        validator = Mock()
        validator.validate_dataset_name = Mock(side_effect=lambda x: x)
        validator.validate_snapshot_name = Mock(side_effect=lambda x: x)
        validator.validate_zfs_command = Mock(side_effect=lambda cmd, args: args)
        return validator
    
    @pytest.fixture
    def mock_logger(self):
        """Create mock logger."""
        logger = Mock()
        logger.info = Mock()
        logger.error = Mock()
        logger.warning = Mock()
        logger.debug = Mock()
        return logger
    
    @pytest.fixture
    def snapshot_service(self, mock_executor, mock_validator, mock_logger):
        """Create SnapshotService instance with mocks."""
        return SnapshotService(
            executor=mock_executor,
            validator=mock_validator,
            logger=mock_logger
        )
    
    @pytest.fixture
    def sample_snapshot(self):
        """Create sample snapshot for testing."""
        return Snapshot(
            name="pool1/dataset1@snap1",
            dataset="pool1/dataset1",
            creation_time=datetime.now(),
            size=SizeValue(1000000),
            properties={
                "type": "snapshot",
                "creation": "1640995200"
            }
        )
    
    # Test create_snapshot
    
    @pytest.mark.asyncio
    async def test_create_snapshot_success(self, snapshot_service, mock_executor, sample_snapshot):
        """Test successful snapshot creation."""
        # Mock successful ZFS command execution
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        # Mock get_snapshot to return the created snapshot
        with patch.object(snapshot_service, 'get_snapshot') as mock_get:
            mock_get.return_value = Result.success(sample_snapshot)
            
            result = await snapshot_service.create_snapshot("pool1/dataset1", "snap1", recursive=False)
            
            assert result.is_success
            assert result.value.name == "pool1/dataset1@snap1"
            mock_executor.execute_zfs.assert_called_once_with("snapshot", "pool1/dataset1", "snap1")
    
    @pytest.mark.asyncio
    async def test_create_snapshot_recursive(self, snapshot_service, mock_executor, sample_snapshot):
        """Test recursive snapshot creation."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        with patch.object(snapshot_service, 'get_snapshot') as mock_get:
            mock_get.return_value = Result.success(sample_snapshot)
            
            result = await snapshot_service.create_snapshot("pool1/dataset1@snap1", recursive=True)
            
            assert result.is_success
            mock_executor.execute_zfs.assert_called_once_with("snapshot", "-r", "pool1/dataset1@snap1")
    
    @pytest.mark.asyncio
    async def test_create_snapshot_validation_error(self, snapshot_service, mock_validator):
        """Test snapshot creation with validation error."""
        # Mock validation to fail
        mock_validator.validate_snapshot_name.side_effect = ValidationException("Invalid snapshot name")
        
        result = await snapshot_service.create_snapshot("invalid@snap", recursive=False)
        
        assert result.is_failure
        assert isinstance(result.error, ValidationException)
        assert "Invalid snapshot name" in str(result.error)
    
    @pytest.mark.asyncio
    async def test_create_snapshot_already_exists(self, snapshot_service, mock_executor):
        """Test snapshot creation when snapshot already exists."""
        # Mock ZFS command to fail with "already exists" error
        mock_executor.execute_zfs.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="snapshot already exists"
        )
        
        result = await snapshot_service.create_snapshot("pool1/dataset1@existing", recursive=False)
        
        assert result.is_failure
        assert isinstance(result.error, SnapshotExistsError)
    
    @pytest.mark.asyncio
    async def test_create_snapshot_command_failure(self, snapshot_service, mock_executor):
        """Test snapshot creation with command failure."""
        # Mock ZFS command to fail
        mock_executor.execute_zfs.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="permission denied"
        )
        
        result = await snapshot_service.create_snapshot("pool1/dataset1@snap1", recursive=False)
        
        assert result.is_failure
        assert isinstance(result.error, SnapshotException)
        assert "permission denied" in str(result.error)
    
    # Test delete_snapshot
    
    @pytest.mark.asyncio
    async def test_delete_snapshot_success(self, snapshot_service, mock_executor):
        """Test successful snapshot deletion."""
        # Mock successful ZFS command execution
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await snapshot_service.delete_snapshot("pool1/dataset1@snap1")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zfs.assert_called_once_with("destroy", "pool1/dataset1@snap1")
    
    @pytest.mark.asyncio
    async def test_delete_snapshot_not_found(self, snapshot_service, mock_executor):
        """Test deletion of non-existent snapshot."""
        # Mock ZFS command to fail with "not found" error
        mock_executor.execute_zfs.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="snapshot does not exist"
        )
        
        result = await snapshot_service.delete_snapshot("pool1/dataset1@nonexistent")
        
        assert result.is_failure
        assert isinstance(result.error, SnapshotNotFoundError)
    
    # Test list_snapshots
    
    @pytest.mark.asyncio
    async def test_list_snapshots_success(self, snapshot_service, mock_executor):
        """Test successful snapshot listing."""
        # Mock ZFS list command output
        zfs_output = """pool1/dataset1@snap1\t1000000\t1640995200\tsnapshot
pool1/dataset1@snap2\t2000000\t1640995300\tsnapshot"""
        
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=zfs_output,
            stderr=""
        )
        
        result = await snapshot_service.list_snapshots()
        
        assert result.is_success
        assert len(result.value) == 2
        assert result.value[0].name == "pool1/dataset1@snap1"
        assert result.value[1].name == "pool1/dataset1@snap2"
        mock_executor.execute_zfs.assert_called_once_with(
            "list", "-H", "-t", "snapshot", "-o", "name,used,creation,type"
        )
    
    @pytest.mark.asyncio
    async def test_list_snapshots_with_dataset_filter(self, snapshot_service, mock_executor):
        """Test snapshot listing with dataset filter."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="pool1/dataset1@snap1\t1000000\t1640995200\tsnapshot",
            stderr=""
        )
        
        result = await snapshot_service.list_snapshots(dataset_name="pool1/dataset1")
        
        assert result.is_success
        assert len(result.value) == 1
        mock_executor.execute_zfs.assert_called_once_with(
            "list", "-H", "-t", "snapshot", "-o", "name,used,creation,type", "-r", "pool1/dataset1"
        )
    
    @pytest.mark.asyncio
    async def test_list_snapshots_empty_result(self, snapshot_service, mock_executor):
        """Test snapshot listing with empty result."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await snapshot_service.list_snapshots()
        
        assert result.is_success
        assert len(result.value) == 0
    
    # Test get_snapshot
    
    @pytest.mark.asyncio
    async def test_get_snapshot_success(self, snapshot_service, mock_executor):
        """Test successful snapshot retrieval."""
        # Mock ZFS get command output
        zfs_output = "pool1/dataset1@snap1\t1000000\t1640995200\tsnapshot"
        
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=zfs_output,
            stderr=""
        )
        
        result = await snapshot_service.get_snapshot("pool1/dataset1@snap1")
        
        assert result.is_success
        assert result.value.name == "pool1/dataset1@snap1"
        assert result.value.size.bytes == 1000000
        mock_executor.execute_zfs.assert_called_once_with(
            "list", "-H", "-t", "snapshot", "-o", "name,used,creation,type", "pool1/dataset1@snap1"
        )
    
    @pytest.mark.asyncio
    async def test_get_snapshot_not_found(self, snapshot_service, mock_executor):
        """Test retrieval of non-existent snapshot."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="snapshot does not exist"
        )
        
        result = await snapshot_service.get_snapshot("pool1/dataset1@nonexistent")
        
        assert result.is_failure
        assert isinstance(result.error, SnapshotNotFoundError)
    
    # Test rollback_to_snapshot
    
    @pytest.mark.asyncio
    async def test_rollback_to_snapshot_success(self, snapshot_service, mock_executor):
        """Test successful snapshot rollback."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await snapshot_service.rollback_to_snapshot("pool1/dataset1@snap1")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zfs.assert_called_once_with("rollback", "pool1/dataset1@snap1")
    
    @pytest.mark.asyncio
    async def test_rollback_to_snapshot_force(self, snapshot_service, mock_executor):
        """Test forced snapshot rollback."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await snapshot_service.rollback_to_snapshot("pool1/dataset1@snap1", force=True)
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zfs.assert_called_once_with("rollback", "-f", "pool1/dataset1@snap1")
    
    # Test clone_snapshot
    
    @pytest.mark.asyncio
    async def test_clone_snapshot_success(self, snapshot_service, mock_executor):
        """Test successful snapshot cloning."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await snapshot_service.clone_snapshot("pool1/dataset1@snap1", "pool1/clone1")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zfs.assert_called_once_with(
            "clone", "pool1/dataset1@snap1", "pool1/clone1"
        )
    
    @pytest.mark.asyncio
    async def test_clone_snapshot_with_properties(self, snapshot_service, mock_executor):
        """Test snapshot cloning with properties."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        properties = {"compression": "gzip", "quota": "1G"}
        result = await snapshot_service.clone_snapshot(
            "pool1/dataset1@snap1", 
            "pool1/clone1", 
            properties=properties
        )
        
        assert result.is_success
        mock_executor.execute_zfs.assert_called_once_with(
            "clone", "-o", "compression=gzip", "-o", "quota=1G", 
            "pool1/dataset1@snap1", "pool1/clone1"
        )
    
    # Test send_snapshot
    
    @pytest.mark.asyncio
    async def test_send_snapshot_success(self, snapshot_service, mock_executor):
        """Test successful snapshot send."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="stream data here",
            stderr=""
        )
        
        result = await snapshot_service.send_snapshot("pool1/dataset1@snap1")
        
        assert result.is_success
        assert "stream data here" in result.value
        mock_executor.execute_zfs.assert_called_once_with("send", "pool1/dataset1@snap1")
    
    @pytest.mark.asyncio
    async def test_send_snapshot_incremental(self, snapshot_service, mock_executor):
        """Test incremental snapshot send."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="incremental stream data",
            stderr=""
        )
        
        result = await snapshot_service.send_snapshot(
            "pool1/dataset1@snap2", 
            incremental_base="pool1/dataset1@snap1"
        )
        
        assert result.is_success
        mock_executor.execute_zfs.assert_called_once_with(
            "send", "-i", "pool1/dataset1@snap1", "pool1/dataset1@snap2"
        )
    
    # Test receive_snapshot
    
    @pytest.mark.asyncio
    async def test_receive_snapshot_success(self, snapshot_service, mock_executor):
        """Test successful snapshot receive."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        stream_data = "zfs stream data"
        result = await snapshot_service.receive_snapshot("pool1/dataset_restore", stream_data)
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zfs.assert_called_once_with("receive", "pool1/dataset_restore")
    
    @pytest.mark.asyncio
    async def test_receive_snapshot_force(self, snapshot_service, mock_executor):
        """Test forced snapshot receive."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        stream_data = "zfs stream data"
        result = await snapshot_service.receive_snapshot(
            "pool1/dataset_restore", 
            stream_data, 
            force=True
        )
        
        assert result.is_success
        mock_executor.execute_zfs.assert_called_once_with("receive", "-F", "pool1/dataset_restore")
    
    # Test retention policy operations
    
    @pytest.mark.asyncio
    async def test_apply_retention_policy_success(self, snapshot_service, mock_executor):
        """Test successful retention policy application."""
        # Mock listing snapshots
        old_time = datetime.now() - timedelta(days=8)
        recent_time = datetime.now() - timedelta(days=2)
        
        zfs_output = f"""pool1/dataset1@old_snap\t1000000\t{int(old_time.timestamp())}\tsnapshot
pool1/dataset1@recent_snap\t2000000\t{int(recent_time.timestamp())}\tsnapshot"""
        
        mock_executor.execute_zfs.side_effect = [
            # First call: list snapshots
            CommandResult(success=True, returncode=0, stdout=zfs_output, stderr=""),
            # Second call: delete old snapshot
            CommandResult(success=True, returncode=0, stdout="", stderr="")
        ]
        
        retention_policy = {
            "keep_days": 7,
            "keep_count": 10
        }
        
        result = await snapshot_service.apply_retention_policy("pool1/dataset1", retention_policy)
        
        assert result.is_success
        assert len(result.value) == 1  # One snapshot deleted
        assert result.value[0] == "pool1/dataset1@old_snap"
        
        # Verify calls
        assert mock_executor.execute_zfs.call_count == 2
        # Second call should be the delete
        mock_executor.execute_zfs.assert_any_call("destroy", "pool1/dataset1@old_snap")
    
    @pytest.mark.asyncio
    async def test_apply_retention_policy_keep_count(self, snapshot_service, mock_executor):
        """Test retention policy with keep count limit."""
        # Create many snapshots to test count-based retention
        snapshots = []
        for i in range(15):
            time_offset = datetime.now() - timedelta(days=i)
            snapshots.append(f"pool1/dataset1@snap{i}\t1000000\t{int(time_offset.timestamp())}\tsnapshot")
        
        zfs_output = "\n".join(snapshots)
        
        # Mock list call and delete calls
        mock_calls = [
            CommandResult(success=True, returncode=0, stdout=zfs_output, stderr="")
        ]
        # Add delete calls for old snapshots (should keep only 10)
        for i in range(5):  # Should delete 5 oldest (10-14)
            mock_calls.append(CommandResult(success=True, returncode=0, stdout="", stderr=""))
        
        mock_executor.execute_zfs.side_effect = mock_calls
        
        retention_policy = {
            "keep_days": 365,  # Keep all by days
            "keep_count": 10   # But limit by count
        }
        
        result = await snapshot_service.apply_retention_policy("pool1/dataset1", retention_policy)
        
        assert result.is_success
        assert len(result.value) == 5  # 5 snapshots deleted
        
        # Verify delete calls for oldest snapshots
        assert mock_executor.execute_zfs.call_count == 6  # 1 list + 5 deletes
    
    @pytest.mark.asyncio
    async def test_apply_retention_policy_no_deletions(self, snapshot_service, mock_executor):
        """Test retention policy when no deletions are needed."""
        # Recent snapshots only
        recent_time = datetime.now() - timedelta(days=2)
        zfs_output = f"pool1/dataset1@recent_snap\t1000000\t{int(recent_time.timestamp())}\tsnapshot"
        
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True, returncode=0, stdout=zfs_output, stderr=""
        )
        
        retention_policy = {
            "keep_days": 7,
            "keep_count": 10
        }
        
        result = await snapshot_service.apply_retention_policy("pool1/dataset1", retention_policy)
        
        assert result.is_success
        assert len(result.value) == 0  # No snapshots deleted
        
        # Only list call, no delete calls
        assert mock_executor.execute_zfs.call_count == 1
    
    # Test get_snapshot_diff
    
    @pytest.mark.asyncio
    async def test_get_snapshot_diff_success(self, snapshot_service, mock_executor):
        """Test successful snapshot diff."""
        diff_output = """M\t/pool1/dataset1/file1.txt
+\t/pool1/dataset1/file2.txt
-\t/pool1/dataset1/file3.txt"""
        
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=diff_output,
            stderr=""
        )
        
        result = await snapshot_service.get_snapshot_diff(
            "pool1/dataset1@snap1", 
            "pool1/dataset1@snap2"
        )
        
        assert result.is_success
        assert len(result.value) == 3
        assert "file1.txt" in result.value[0]["path"]
        assert result.value[0]["change_type"] == "M"
        mock_executor.execute_zfs.assert_called_once_with(
            "diff", "pool1/dataset1@snap1", "pool1/dataset1@snap2"
        )
    
    # Test error handling and edge cases
    
    @pytest.mark.asyncio
    async def test_unexpected_error_handling(self, snapshot_service, mock_executor):
        """Test handling of unexpected errors."""
        # Mock executor to raise exception
        mock_executor.execute_zfs.side_effect = Exception("Unexpected error")
        
        result = await snapshot_service.get_snapshot("pool1/dataset1@snap1")
        
        assert result.is_failure
        assert isinstance(result.error, SnapshotException)
        assert "Unexpected error" in str(result.error)
    
    @pytest.mark.asyncio
    async def test_malformed_zfs_output(self, snapshot_service, mock_executor):
        """Test handling of malformed ZFS output."""
        # Mock ZFS command with malformed output
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="invalid\toutput",  # Missing required fields
            stderr=""
        )
        
        result = await snapshot_service.list_snapshots()
        
        assert result.is_failure
        assert isinstance(result.error, SnapshotException)
    
    # Test validation integration
    
    @pytest.mark.asyncio
    async def test_snapshot_name_validation_integration(self, snapshot_service, mock_validator):
        """Test integration with snapshot name validation."""
        # Mock validator to be called
        mock_validator.validate_snapshot_name = Mock(return_value="pool1/dataset1@snap1")
        
        # Mock executor for successful creation
        mock_executor = Mock()
        mock_executor.execute_zfs = AsyncMock(return_value=CommandResult(
            success=True, returncode=0, stdout="", stderr=""
        ))
        snapshot_service._executor = mock_executor
        
        # Mock get_snapshot for post-creation verification
        with patch.object(snapshot_service, 'get_snapshot') as mock_get:
            mock_get.return_value = Result.success(Mock())
            
            await snapshot_service.create_snapshot("pool1/dataset1@snap1", recursive=False)
            
            # Verify validation was called
            mock_validator.validate_snapshot_name.assert_called_with("pool1/dataset1@snap1")
    
    @pytest.mark.asyncio
    async def test_logger_integration(self, snapshot_service, mock_logger, mock_executor):
        """Test integration with logger."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        await snapshot_service.delete_snapshot("pool1/dataset1@snap1")
        
        # Verify logger was called
        mock_logger.info.assert_called()
        assert any("Deleting snapshot" in str(call) for call in mock_logger.info.call_args_list)
    
    # Test concurrent operations
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, snapshot_service, mock_executor):
        """Test concurrent snapshot operations."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        # Create multiple concurrent operations
        tasks = [
            snapshot_service.delete_snapshot(f"pool1/dataset1@snap{i}")
            for i in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All operations should succeed
        assert all(result.is_success for result in results)
        assert mock_executor.execute_zfs.call_count == 5
    
    # Test data integrity
    
    @pytest.mark.asyncio
    async def test_snapshot_data_integrity(self, snapshot_service, mock_executor):
        """Test snapshot data integrity checks."""
        # Test that timestamp parsing works correctly
        creation_timestamp = 1640995200  # Known timestamp
        zfs_output = f"pool1/dataset1@snap1\t1000000\t{creation_timestamp}\tsnapshot"
        
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=zfs_output,
            stderr=""
        )
        
        result = await snapshot_service.get_snapshot("pool1/dataset1@snap1")
        
        assert result.is_success
        snapshot = result.value
        assert snapshot.creation_time.timestamp() == creation_timestamp
        assert snapshot.dataset == "pool1/dataset1"
        assert snapshot.name == "pool1/dataset1@snap1" 