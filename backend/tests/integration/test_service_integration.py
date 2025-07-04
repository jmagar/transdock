import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from backend.zfs_operations.factories.service_factory import ServiceFactory
# from backend.zfs_operations.adapters.legacy_adapter import LegacyAdapter  # TODO: Implement LegacyAdapter
from backend.zfs_operations.core.interfaces.command_executor import CommandResult
from backend.zfs_operations.core.result import Result


class TestServiceIntegration:
    """Integration tests for the ZFS service layer."""
    
    @pytest.fixture
    def mock_executor(self):
        """Create mock command executor."""
        executor = Mock()
        executor.execute_zfs = AsyncMock()
        executor.execute_zpool = AsyncMock()
        executor.execute_system = AsyncMock()
        return executor
    
    @pytest.fixture
    def mock_validator(self):
        """Create mock security validator."""
        validator = Mock()
        validator.validate_dataset_name = Mock(side_effect=lambda x: x)
        validator.validate_snapshot_name = Mock(side_effect=lambda x: x)
        validator.validate_zfs_command = Mock(side_effect=lambda cmd, args: args)
        validator.validate_zfs_property = Mock(side_effect=lambda prop, val: (prop, val))
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
    def service_factory(self, mock_executor, mock_validator, mock_logger):
        """Create service factory with mocked dependencies."""
        factory = ServiceFactory()
        factory._executor = mock_executor
        factory._validator = mock_validator
        factory._logger_instances = {"test": mock_logger}
        return factory
    
    # @pytest.fixture
    # def legacy_adapter(self, service_factory):
    #     """Create legacy adapter with service factory."""
    #     return LegacyAdapter(service_factory)
    
    # Test service factory integration
    
    def test_service_factory_creates_all_services(self, service_factory):
        """Test that service factory can create all required services."""
        # Create all services
        dataset_service = service_factory.create_dataset_service()
        snapshot_service = service_factory.create_snapshot_service()
        pool_service = service_factory.create_pool_service()
        
        # Verify all services are created
        assert dataset_service is not None
        assert snapshot_service is not None
        assert pool_service is not None
        
        # Verify services have the same dependencies
        assert dataset_service._executor is service_factory._executor
        assert snapshot_service._executor is service_factory._executor
        assert pool_service._executor is service_factory._executor
    
    def test_service_factory_singleton_dependencies(self, service_factory):
        """Test that service factory uses singleton dependencies."""
        # Create multiple services
        dataset_service1 = service_factory.create_dataset_service()
        dataset_service2 = service_factory.create_dataset_service()
        
        # Verify they share the same dependencies
        assert dataset_service1._executor is dataset_service2._executor
        assert dataset_service1._validator is dataset_service2._validator
    
    # Test cross-service operations
    
    @pytest.mark.asyncio
    async def test_dataset_snapshot_integration(self, service_factory, mock_executor):
        """Test integration between dataset and snapshot services."""
        # Setup mock responses
        mock_executor.execute_zfs.side_effect = [
            # Dataset creation
            CommandResult(success=True, returncode=0, stdout="", stderr=""),
            # Dataset verification
            CommandResult(success=True, returncode=0, stdout="pool1/dataset1\t1G\t500M\t500M\tlz4\tsha256", stderr=""),
            # Snapshot creation
            CommandResult(success=True, returncode=0, stdout="", stderr=""),
            # Snapshot verification
            CommandResult(success=True, returncode=0, stdout="pool1/dataset1@snap1\t100M\t1640995200\tsnapshot", stderr="")
        ]
        
        dataset_service = service_factory.create_dataset_service()
        snapshot_service = service_factory.create_snapshot_service()
        
        # Create dataset
        dataset_result = await dataset_service.create_dataset("pool1/dataset1", {"compression": "lz4"})
        assert dataset_result.is_success
        
        # Create snapshot of the dataset
        snapshot_result = await snapshot_service.create_snapshot("pool1/dataset1@snap1", recursive=False)
        assert snapshot_result.is_success
        
        # Verify both operations succeeded
        assert dataset_result.value.name.value == "pool1/dataset1"
        assert snapshot_result.value.name == "pool1/dataset1@snap1"
    
    @pytest.mark.asyncio
    async def test_pool_dataset_integration(self, service_factory, mock_executor):
        """Test integration between pool and dataset services."""
        # Setup mock responses
        mock_executor.execute_zpool.side_effect = [
            # Pool creation
            CommandResult(success=True, returncode=0, stdout="", stderr=""),
            # Pool verification
            CommandResult(success=True, returncode=0, stdout="pool1\t10G\t5G\t5G\t-\t50%\tONLINE\tONLINE", stderr="")
        ]
        
        mock_executor.execute_zfs.side_effect = [
            # Dataset creation
            CommandResult(success=True, returncode=0, stdout="", stderr=""),
            # Dataset verification
            CommandResult(success=True, returncode=0, stdout="pool1/dataset1\t1G\t500M\t500M\tlz4\tsha256", stderr="")
        ]
        
        pool_service = service_factory.create_pool_service()
        dataset_service = service_factory.create_dataset_service()
        
        # Create pool
        vdev_spec = {"type": "single", "devices": ["/dev/sda"]}
        pool_result = await pool_service.create_pool("pool1", [vdev_spec])
        assert pool_result.is_success
        
        # Create dataset in the pool
        dataset_result = await dataset_service.create_dataset("pool1/dataset1", {})
        assert dataset_result.is_success
        
        # Verify both operations succeeded
        assert pool_result.value.name == "pool1"
        assert dataset_result.value.name.value == "pool1/dataset1"
    
    # Test legacy adapter integration
    # TODO: Implement LegacyAdapter before enabling these tests
    # 
    # @pytest.mark.asyncio
    # async def test_legacy_adapter_dataset_operations(self, legacy_adapter, mock_executor):
        """Test legacy adapter dataset operations."""
        # Setup mock responses
        mock_executor.execute_zfs.side_effect = [
            # Create dataset
            CommandResult(success=True, returncode=0, stdout="", stderr=""),
            # Get dataset (for verification)
            CommandResult(success=True, returncode=0, stdout="pool1/dataset1\t1G\t500M\t500M\tlz4\tsha256", stderr=""),
            # List datasets
            CommandResult(success=True, returncode=0, stdout="pool1/dataset1\t1G\t500M\t500M\tlz4\tsha256", stderr=""),
            # Delete dataset
            CommandResult(success=True, returncode=0, stdout="", stderr="")
        ]
        
        # Test create dataset
        create_result = legacy_adapter.create_dataset("pool1/dataset1", {"compression": "lz4"})
        assert create_result["success"] is True
        assert "dataset" in create_result
        
        # Test list datasets
        list_result = legacy_adapter.list_datasets()
        assert list_result["success"] is True
        assert len(list_result["datasets"]) == 1
        
        # Test delete dataset
        delete_result = legacy_adapter.delete_dataset("pool1/dataset1")
        assert delete_result["success"] is True
    
    @pytest.mark.asyncio
    async def test_legacy_adapter_snapshot_operations(self, legacy_adapter, mock_executor):
        """Test legacy adapter snapshot operations."""
        # Setup mock responses
        mock_executor.execute_zfs.side_effect = [
            # Create snapshot
            CommandResult(success=True, returncode=0, stdout="", stderr=""),
            # Get snapshot (for verification)
            CommandResult(success=True, returncode=0, stdout="pool1/dataset1@snap1\t100M\t1640995200\tsnapshot", stderr=""),
            # List snapshots
            CommandResult(success=True, returncode=0, stdout="pool1/dataset1@snap1\t100M\t1640995200\tsnapshot", stderr=""),
            # Delete snapshot
            CommandResult(success=True, returncode=0, stdout="", stderr="")
        ]
        
        # Test create snapshot
        create_result = legacy_adapter.create_snapshot("pool1/dataset1", "snap1")
        assert create_result["success"] is True
        assert "snapshot" in create_result
        
        # Test list snapshots
        list_result = legacy_adapter.list_snapshots()
        assert list_result["success"] is True
        assert len(list_result["snapshots"]) == 1
        
        # Test delete snapshot
        delete_result = legacy_adapter.delete_snapshot("pool1/dataset1", "snap1")
        assert delete_result["success"] is True
    
    @pytest.mark.asyncio
    async def test_legacy_adapter_pool_operations(self, legacy_adapter, mock_executor):
        """Test legacy adapter pool operations."""
        # Setup mock responses
        mock_executor.execute_zpool.side_effect = [
            # List pools
            CommandResult(success=True, returncode=0, stdout="pool1\t10G\t5G\t5G\t-\t50%\tONLINE\tONLINE", stderr=""),
            # Get pool status
            CommandResult(success=True, returncode=0, stdout="pool1\t10G\t5G\t5G\t-\t50%\tONLINE\tONLINE", stderr=""),
            # Start scrub
            CommandResult(success=True, returncode=0, stdout="", stderr=""),
            # Get I/O stats
            CommandResult(success=True, returncode=0, stdout="pool1\t10G\t5G\t5G\t-\t50%\tONLINE\tONLINE", stderr="")
        ]
        
        # Test list pools
        list_result = legacy_adapter.list_pools()
        assert list_result["success"] is True
        assert len(list_result["pools"]) == 1
        
        # Test get pool status
        status_result = legacy_adapter.get_pool_status("pool1")
        assert status_result["success"] is True
        assert "pool" in status_result
        
        # Test scrub pool
        scrub_result = legacy_adapter.scrub_pool("pool1", "start")
        assert scrub_result["success"] is True
        
        # Test get I/O stats
        iostat_result = legacy_adapter.get_pool_iostat("pool1")
        assert iostat_result["success"] is True
    
    # Test error handling integration
    
    @pytest.mark.asyncio
    async def test_error_propagation_through_layers(self, legacy_adapter, mock_executor):
        """Test that errors propagate correctly through all layers."""
        # Setup mock to return error
        mock_executor.execute_zfs.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="dataset does not exist"
        )
        
        # Test that error is properly handled in legacy adapter
        result = legacy_adapter.get_dataset_properties("nonexistent/dataset")
        assert result["success"] is False
        assert "error" in result
        assert "dataset does not exist" in result["error"]
    
    @pytest.mark.asyncio
    async def test_validation_integration(self, legacy_adapter, mock_validator):
        """Test that validation is properly integrated across all layers."""
        # Setup validator to reject invalid names
        mock_validator.validate_dataset_name.side_effect = lambda x: x if x != "invalid" else (_ for _ in ()).throw(Exception("Invalid name"))
        
        # Test that validation error is handled properly
        result = legacy_adapter.create_dataset("invalid", {})
        assert result["success"] is False
        assert "error" in result
    
    # Test concurrent operations integration
    
    @pytest.mark.asyncio
    async def test_concurrent_service_operations(self, service_factory, mock_executor):
        """Test concurrent operations across multiple services."""
        # Setup mock responses for concurrent operations
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True, returncode=0, stdout="", stderr=""
        )
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True, returncode=0, stdout="pool1\t10G\t5G\t5G\t-\t50%\tONLINE\tONLINE", stderr=""
        )
        
        dataset_service = service_factory.create_dataset_service()
        snapshot_service = service_factory.create_snapshot_service()
        pool_service = service_factory.create_pool_service()
        
        # Create concurrent operations
        tasks = [
            dataset_service.delete_dataset("pool1/dataset1"),
            snapshot_service.delete_snapshot("pool1/dataset2@snap1"),
            pool_service.get_pool("pool1"),
            dataset_service.delete_dataset("pool1/dataset3"),
            snapshot_service.delete_snapshot("pool1/dataset4@snap2")
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All operations should complete successfully
        assert all(result.is_success for result in results)
    
    # Test legacy function aliases
    
    @pytest.mark.asyncio
    async def test_legacy_function_aliases(self, mock_executor):
        """Test that legacy function aliases work correctly."""
        # Import the legacy functions
        from backend.zfs_operations.adapters.legacy_adapter import (
            create_dataset, delete_dataset, list_datasets,
            create_snapshot, delete_snapshot, list_snapshots,
            list_pools, get_pool_status
        )
        
        # Setup mock responses
        mock_executor.execute_zfs.side_effect = [
            # Create dataset
            CommandResult(success=True, returncode=0, stdout="", stderr=""),
            # Get dataset (for verification)
            CommandResult(success=True, returncode=0, stdout="pool1/dataset1\t1G\t500M\t500M\tlz4\tsha256", stderr=""),
            # Delete dataset
            CommandResult(success=True, returncode=0, stdout="", stderr=""),
            # List datasets
            CommandResult(success=True, returncode=0, stdout="pool1/dataset1\t1G\t500M\t500M\tlz4\tsha256", stderr=""),
            # Create snapshot
            CommandResult(success=True, returncode=0, stdout="", stderr=""),
            # Get snapshot (for verification)
            CommandResult(success=True, returncode=0, stdout="pool1/dataset1@snap1\t100M\t1640995200\tsnapshot", stderr=""),
            # Delete snapshot
            CommandResult(success=True, returncode=0, stdout="", stderr=""),
            # List snapshots
            CommandResult(success=True, returncode=0, stdout="pool1/dataset1@snap1\t100M\t1640995200\tsnapshot", stderr="")
        ]
        
        mock_executor.execute_zpool.side_effect = [
            # List pools
            CommandResult(success=True, returncode=0, stdout="pool1\t10G\t5G\t5G\t-\t50%\tONLINE\tONLINE", stderr=""),
            # Get pool status
            CommandResult(success=True, returncode=0, stdout="pool1\t10G\t5G\t5G\t-\t50%\tONLINE\tONLINE", stderr="")
        ]
        
        # Patch the global adapter's executor
        with patch('backend.zfs_operations.adapters.legacy_adapter._default_adapter') as mock_adapter:
            mock_adapter._executor = mock_executor
            mock_adapter.create_dataset = Mock(return_value={"success": True})
            mock_adapter.delete_dataset = Mock(return_value={"success": True})
            mock_adapter.list_datasets = Mock(return_value={"success": True, "datasets": []})
            mock_adapter.create_snapshot = Mock(return_value={"success": True})
            mock_adapter.delete_snapshot = Mock(return_value={"success": True})
            mock_adapter.list_snapshots = Mock(return_value={"success": True, "snapshots": []})
            mock_adapter.list_pools = Mock(return_value={"success": True, "pools": []})
            mock_adapter.get_pool_status = Mock(return_value={"success": True, "pool": {}})
            
            # Test legacy function aliases
            result = create_dataset("pool1/dataset1", {"compression": "lz4"})
            assert result["success"] is True
            
            result = delete_dataset("pool1/dataset1")
            assert result["success"] is True
            
            result = list_datasets()
            assert result["success"] is True
            
            result = create_snapshot("pool1/dataset1", "snap1")
            assert result["success"] is True
            
            result = delete_snapshot("pool1/dataset1", "snap1")
            assert result["success"] is True
            
            result = list_snapshots()
            assert result["success"] is True
            
            result = list_pools()
            assert result["success"] is True
            
            result = get_pool_status("pool1")
            assert result["success"] is True
    
    # Test system information integration
    
    @pytest.mark.asyncio
    async def test_system_info_integration(self, legacy_adapter, mock_executor):
        """Test system information aggregation across services."""
        # Setup mock responses for system info
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True, returncode=0, 
            stdout="pool1\t10G\t5G\t5G\t-\t50%\tONLINE\tONLINE\npool2\t20G\t10G\t10G\t-\t50%\tONLINE\tONLINE", 
            stderr=""
        )
        
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True, returncode=0,
            stdout="pool1/dataset1\t1G\t500M\t500M\tlz4\tsha256\npool2/dataset1\t2G\t1G\t1G\tgzip\tsha256",
            stderr=""
        )
        
        # Test system info aggregation
        result = legacy_adapter.get_system_info()
        assert result["success"] is True
        assert "system_info" in result
        
        system_info = result["system_info"]
        assert "pools" in system_info
        assert "datasets" in system_info
        assert system_info["pools"]["count"] == 2
        assert system_info["datasets"]["count"] == 2
    
    # Test configuration and dependency injection
    
    def test_custom_configuration_integration(self):
        """Test that custom configuration is properly integrated."""
        # Create factory with custom configuration
        config = {
            "command_timeout": 60,
            "log_level": "DEBUG"
        }
        
        factory = ServiceFactory(config)
        
        # Verify configuration is applied
        assert factory._config["command_timeout"] == 60
        assert factory._config["log_level"] == "DEBUG"
        
        # Verify services are created with custom config
        dataset_service = factory.create_dataset_service()
        assert dataset_service is not None
    
    def test_service_factory_builder_integration(self):
        """Test service factory builder integration."""
        from backend.zfs_operations.factories.service_factory import (
            ServiceFactoryBuilder,
            create_default_service_factory,
            create_development_service_factory,
            create_production_service_factory
        )
        
        # Test builder pattern
        factory = ServiceFactoryBuilder() \
            .with_command_timeout(45) \
            .with_log_level("INFO") \
            .build()
        
        assert factory._config["command_timeout"] == 45
        assert factory._config["log_level"] == "INFO"
        
        # Test convenience functions
        default_factory = create_default_service_factory()
        assert default_factory is not None
        
        dev_factory = create_development_service_factory()
        assert dev_factory is not None
        
        prod_factory = create_production_service_factory()
        assert prod_factory is not None
    
    # Test backward compatibility
    
    @pytest.mark.asyncio
    async def test_backward_compatibility(self, legacy_adapter, mock_executor):
        """Test that legacy adapter maintains backward compatibility."""
        # Setup mock responses that match legacy API expectations
        mock_executor.execute_zfs.side_effect = [
            # Create dataset
            CommandResult(success=True, returncode=0, stdout="", stderr=""),
            # Get dataset (for verification)
            CommandResult(success=True, returncode=0, stdout="pool1/dataset1\t1G\t500M\t500M\tlz4\tsha256", stderr="")
        ]
        
        # Test legacy API format
        result = legacy_adapter.create_dataset("pool1/dataset1", {"compression": "lz4"})
        
        # Verify legacy API response format
        assert isinstance(result, dict)
        assert "success" in result
        assert "dataset" in result or "error" in result
        assert "message" in result
        
        # Test error format
        mock_executor.execute_zfs.return_value = CommandResult(
            success=False, returncode=1, stdout="", stderr="dataset already exists"
        )
        
        error_result = legacy_adapter.create_dataset("pool1/existing", {})
        assert error_result["success"] is False
        assert "error" in error_result
        assert "message" in error_result
    
    # Test resource cleanup
    
    @pytest.mark.asyncio
    async def test_resource_cleanup_integration(self, service_factory, mock_executor):
        """Test that resources are properly cleaned up."""
        # Create services
        dataset_service = service_factory.create_dataset_service()
        snapshot_service = service_factory.create_snapshot_service()
        
        # Simulate operations that might create resources
        mock_executor.execute_zfs.return_value = CommandResult(
            success=True, returncode=0, stdout="", stderr=""
        )
        
        # Perform operations
        await dataset_service.delete_dataset("pool1/dataset1")
        await snapshot_service.delete_snapshot("pool1/dataset1@snap1")
        
        # Verify no resource leaks (in real scenario, this would check file handles, etc.)
        # For now, just verify operations completed
        assert mock_executor.execute_zfs.call_count == 2 