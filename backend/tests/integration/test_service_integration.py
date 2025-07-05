import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from backend.zfs_operations.factories.service_factory import ServiceFactory
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
    
    # TODO: Implement LegacyAdapter for backward compatibility
    # 
    # The LegacyAdapter should provide a dictionary-based API that wraps the modern
    # service layer, returning responses in the format: {"success": bool, "data": any, "error": str}
    # This will enable backward compatibility with existing code while leveraging the new architecture.
    # 
    # Planned LegacyAdapter features:
    # - Dataset operations (create, delete, list, get properties, set properties)
    # - Snapshot operations (create, delete, list, clone, rollback)
    # - Pool operations (list, status, scrub, iostat)
    # - System information aggregation
    # - Error handling with legacy response format
    # - Function aliases for direct method calls
    # 
    # Issue: Create separate GitHub issue to track LegacyAdapter implementation
    
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