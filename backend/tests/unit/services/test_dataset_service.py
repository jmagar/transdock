import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from backend.zfs_operations.services.dataset_service import DatasetService
from backend.zfs_operations.core.entities.dataset import Dataset
from backend.zfs_operations.core.value_objects.dataset_name import DatasetName
from backend.zfs_operations.core.value_objects.size_value import SizeValue
from backend.zfs_operations.core.exceptions.zfs_exceptions import (
    DatasetException,
    DatasetNotFoundError,
    DatasetExistsError
)
from backend.zfs_operations.core.exceptions.validation_exceptions import ValidationException
from backend.zfs_operations.core.result import Result
from backend.zfs_operations.core.interfaces.command_executor import CommandResult


class TestDatasetService:
    """Test suite for DatasetService."""
    
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
    def dataset_service(self, mock_executor, mock_validator, mock_logger):
        """Create DatasetService instance with mocks."""
        return DatasetService(
            executor=mock_executor,
            validator=mock_validator,
            logger=mock_logger
        )
    
    @pytest.fixture
    def sample_dataset(self):
        """Create sample dataset for testing."""
        return Dataset(
            name=DatasetName("pool1/dataset1"),
            pool="pool1",
            size=SizeValue(1000000),
            used=SizeValue(500000),
            available=SizeValue(500000),
            properties={
                "compression": "lz4",
                "checksum": "sha256"
            }
        )
    
    # Test create_dataset
    
    @pytest.mark.asyncio
    async def test_create_dataset_success(self, dataset_service, mock_executor, sample_dataset):
        """Test successful dataset creation."""
        # Mock successful ZFS command execution
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        # Mock get_dataset to return the created dataset
        with patch.object(dataset_service, 'get_dataset') as mock_get:
            mock_get.return_value = Result.success(sample_dataset)
            
            result = await dataset_service.create_dataset("pool1/dataset1", {"compression": "lz4"})
            
            assert result.is_success
            assert result.value.name.value == "pool1/dataset1"
            mock_executor.execute_zfs.assert_called_once_with(
                "create", "-o", "compression=lz4", "pool1/dataset1"
            )
    
    @pytest.mark.asyncio
    async def test_create_dataset_validation_error(self, dataset_service, mock_validator):
        """Test dataset creation with validation error."""
        # Mock validation to fail
        mock_validator.validate_dataset_name.side_effect = ValidationException("Invalid name")
        
        result = await dataset_service.create_dataset("invalid/name", {})
        
        assert result.is_failure
        assert isinstance(result.error, ValidationException)
        assert "Invalid name" in str(result.error)
    
    @pytest.mark.asyncio
    async def test_create_dataset_already_exists(self, dataset_service, mock_executor):
        """Test dataset creation when dataset already exists."""
        # Mock ZFS command to fail with "already exists" error
        mock_executor.execute_zfs.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="dataset already exists"
        )
        
        result = await dataset_service.create_dataset("pool1/existing", {})
        
        assert result.is_failure
        assert isinstance(result.error, DatasetExistsError)
    
    @pytest.mark.asyncio
    async def test_create_dataset_command_failure(self, dataset_service, mock_executor):
        """Test dataset creation with command failure."""
        # Mock ZFS command to fail
        mock_executor.execute_zfs.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="permission denied"
        )
        
        result = await dataset_service.create_dataset("pool1/dataset1", {})
        
        assert result.is_failure
        assert isinstance(result.error, DatasetException)
        assert "permission denied" in str(result.error)
    
    # Test delete_dataset
    
    @pytest.mark.asyncio
    async def test_delete_dataset_success(self, dataset_service, mock_executor):
        """Test successful dataset deletion."""
        # Mock successful ZFS command execution
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await dataset_service.delete_dataset("pool1/dataset1", recursive=False)
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zfs.assert_called_once_with("destroy", "pool1/dataset1")
    
    @pytest.mark.asyncio
    async def test_delete_dataset_recursive(self, dataset_service, mock_executor):
        """Test recursive dataset deletion."""
        # Mock successful ZFS command execution
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await dataset_service.delete_dataset("pool1/dataset1", recursive=True)
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zfs.assert_called_once_with("destroy", "-r", "pool1/dataset1")
    
    @pytest.mark.asyncio
    async def test_delete_dataset_not_found(self, dataset_service, mock_executor):
        """Test deletion of non-existent dataset."""
        # Mock ZFS command to fail with "not found" error
        mock_executor.execute_zfs.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="dataset does not exist"
        )
        
        result = await dataset_service.delete_dataset("pool1/nonexistent", recursive=False)
        
        assert result.is_failure
        assert isinstance(result.error, DatasetNotFoundError)
    
    # Test list_datasets
    
    @pytest.mark.asyncio
    async def test_list_datasets_success(self, dataset_service, mock_executor):
        """Test successful dataset listing."""
        # Mock ZFS list command output
        zfs_output = """pool1/dataset1\t1000000\t500000\t500000\tlz4\tsha256
pool1/dataset2\t2000000\t1000000\t1000000\tgzip\tsha256"""
        
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=zfs_output,
            stderr=""
        )
        
        result = await dataset_service.list_datasets()
        
        assert result.is_success
        assert len(result.value) == 2
        assert result.value[0].name.value == "pool1/dataset1"
        assert result.value[1].name.value == "pool1/dataset2"
        mock_executor.execute_zfs.assert_called_once_with(
            "list", "-H", "-o", "name,used,avail,refer,compression,checksum"
        )
    
    @pytest.mark.asyncio
    async def test_list_datasets_with_pool_filter(self, dataset_service, mock_executor):
        """Test dataset listing with pool filter."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="pool1/dataset1\t1000000\t500000\t500000\tlz4\tsha256",
            stderr=""
        )
        
        result = await dataset_service.list_datasets(pool_name="pool1")
        
        assert result.is_success
        assert len(result.value) == 1
        mock_executor.execute_zfs.assert_called_once_with(
            "list", "-H", "-o", "name,used,avail,refer,compression,checksum", "-r", "pool1"
        )
    
    @pytest.mark.asyncio
    async def test_list_datasets_empty_result(self, dataset_service, mock_executor):
        """Test dataset listing with empty result."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await dataset_service.list_datasets()
        
        assert result.is_success
        assert len(result.value) == 0
    
    # Test get_dataset
    
    @pytest.mark.asyncio
    async def test_get_dataset_success(self, dataset_service, mock_executor):
        """Test successful dataset retrieval."""
        # Mock ZFS get command output
        zfs_output = "pool1/dataset1\t1000000\t500000\t500000\tlz4\tsha256"
        
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=zfs_output,
            stderr=""
        )
        
        result = await dataset_service.get_dataset("pool1/dataset1")
        
        assert result.is_success
        assert result.value.name.value == "pool1/dataset1"
        assert result.value.size.bytes == 1000000
        mock_executor.execute_zfs.assert_called_once_with(
            "list", "-H", "-o", "name,used,avail,refer,compression,checksum", "pool1/dataset1"
        )
    
    @pytest.mark.asyncio
    async def test_get_dataset_not_found(self, dataset_service, mock_executor):
        """Test retrieval of non-existent dataset."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="dataset does not exist"
        )
        
        result = await dataset_service.get_dataset("pool1/nonexistent")
        
        assert result.is_failure
        assert isinstance(result.error, DatasetNotFoundError)
    
    # Test get_dataset_properties
    
    @pytest.mark.asyncio
    async def test_get_dataset_properties_success(self, dataset_service, mock_executor):
        """Test successful dataset properties retrieval."""
        # Mock ZFS get command output
        zfs_output = """pool1/dataset1\tcompression\tlz4\tlocal
pool1/dataset1\tchecksum\tsha256\tlocal
pool1/dataset1\tquota\tnone\tdefault"""
        
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=zfs_output,
            stderr=""
        )
        
        result = await dataset_service.get_dataset_properties("pool1/dataset1")
        
        assert result.is_success
        assert result.value["compression"] == "lz4"
        assert result.value["checksum"] == "sha256"
        assert result.value["quota"] == "none"
    
    # Test set_dataset_property
    
    @pytest.mark.asyncio
    async def test_set_dataset_property_success(self, dataset_service, mock_executor, mock_validator):
        """Test successful dataset property setting."""
        # Mock property validation
        mock_validator.validate_zfs_property = Mock(return_value=("compression", "gzip"))
        
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await dataset_service.set_dataset_property("pool1/dataset1", "compression", "gzip")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zfs.assert_called_once_with(
            "set", "compression=gzip", "pool1/dataset1"
        )
    
    @pytest.mark.asyncio
    async def test_set_dataset_property_validation_error(self, dataset_service, mock_validator):
        """Test dataset property setting with validation error."""
        # Mock property validation to fail
        mock_validator.validate_zfs_property = Mock(side_effect=ValidationException("Invalid property"))
        
        result = await dataset_service.set_dataset_property("pool1/dataset1", "invalid", "value")
        
        assert result.is_failure
        assert isinstance(result.error, ValidationException)
    
    # Test mount_dataset
    
    @pytest.mark.asyncio
    async def test_mount_dataset_success(self, dataset_service, mock_executor):
        """Test successful dataset mounting."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await dataset_service.mount_dataset("pool1/dataset1")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zfs.assert_called_once_with("mount", "pool1/dataset1")
    
    @pytest.mark.asyncio
    async def test_mount_dataset_with_mountpoint(self, dataset_service, mock_executor):
        """Test dataset mounting with specific mountpoint."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await dataset_service.mount_dataset("pool1/dataset1", "/custom/mount")
        
        assert result.is_success
        assert result.value is True
        # Should first set mountpoint property, then mount
        assert mock_executor.execute_zfs.call_count == 2
    
    # Test unmount_dataset
    
    @pytest.mark.asyncio
    async def test_unmount_dataset_success(self, dataset_service, mock_executor):
        """Test successful dataset unmounting."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await dataset_service.unmount_dataset("pool1/dataset1")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zfs.assert_called_once_with("unmount", "pool1/dataset1")
    
    @pytest.mark.asyncio
    async def test_unmount_dataset_force(self, dataset_service, mock_executor):
        """Test forced dataset unmounting."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await dataset_service.unmount_dataset("pool1/dataset1", force=True)
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zfs.assert_called_once_with("unmount", "-f", "pool1/dataset1")
    
    # Test clone_dataset
    
    @pytest.mark.asyncio
    async def test_clone_dataset_success(self, dataset_service, mock_executor, sample_dataset):
        """Test successful dataset cloning."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        # Mock get_dataset to return the cloned dataset
        with patch.object(dataset_service, 'get_dataset') as mock_get:
            mock_get.return_value = Result.success(sample_dataset)
            
            result = await dataset_service.clone_dataset("pool1/dataset1@snap1", "pool1/clone1")
            
            assert result.is_success
            assert result.value.name.value == "pool1/dataset1"
            mock_executor.execute_zfs.assert_called_once_with(
                "clone", "pool1/dataset1@snap1", "pool1/clone1"
            )
    
    # Test rename_dataset
    
    @pytest.mark.asyncio
    async def test_rename_dataset_success(self, dataset_service, mock_executor):
        """Test successful dataset renaming."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await dataset_service.rename_dataset("pool1/dataset1", "pool1/dataset_new")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zfs.assert_called_once_with(
            "rename", "pool1/dataset1", "pool1/dataset_new"
        )
    
    # Test error handling and edge cases
    
    @pytest.mark.asyncio
    async def test_unexpected_error_handling(self, dataset_service, mock_executor):
        """Test handling of unexpected errors."""
        # Mock executor to raise exception
        mock_executor.execute_zfs.side_effect = Exception("Unexpected error")
        
        result = await dataset_service.get_dataset("pool1/dataset1")
        
        assert result.is_failure
        assert isinstance(result.error, DatasetException)
        assert "Unexpected error" in str(result.error)
    
    @pytest.mark.asyncio
    async def test_malformed_zfs_output(self, dataset_service, mock_executor):
        """Test handling of malformed ZFS output."""
        # Mock ZFS command with malformed output
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="invalid\toutput",  # Missing required fields
            stderr=""
        )
        
        result = await dataset_service.list_datasets()
        
        assert result.is_failure
        assert isinstance(result.error, DatasetException)
    
    # Test validation integration
    
    @pytest.mark.asyncio
    async def test_dataset_name_validation_integration(self, dataset_service, mock_validator):
        """Test integration with dataset name validation."""
        # Mock validator to be called
        mock_validator.validate_dataset_name = Mock(return_value="pool1/dataset1")
        
        # Mock executor for successful creation
        mock_executor = Mock()
        mock_executor.execute_zfs = AsyncMock(return_value=CommandResult(
            success=True, returncode=0, stdout="", stderr=""
        ))
        dataset_service._executor = mock_executor
        
        # Mock get_dataset for post-creation verification
        with patch.object(dataset_service, 'get_dataset') as mock_get:
            mock_get.return_value = Result.success(Mock())
            
            await dataset_service.create_dataset("pool1/dataset1", {})
            
            # Verify validation was called
            mock_validator.validate_dataset_name.assert_called_with("pool1/dataset1")
    
    @pytest.mark.asyncio
    async def test_logger_integration(self, dataset_service, mock_logger, mock_executor):
        """Test integration with logger."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        await dataset_service.delete_dataset("pool1/dataset1")
        
        # Verify logger was called
        mock_logger.info.assert_called()
        assert any("Deleting dataset" in str(call) for call in mock_logger.info.call_args_list)
    
    # Test concurrent operations
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, dataset_service, mock_executor):
        """Test concurrent dataset operations."""
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        # Create multiple concurrent operations
        tasks = [
            dataset_service.delete_dataset(f"pool1/dataset{i}")
            for i in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All operations should succeed
        assert all(result.is_success for result in results)
        assert mock_executor.execute_zfs.call_count == 5 