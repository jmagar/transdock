import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from backend.zfs_operations.services.pool_service import PoolService
from backend.zfs_operations.core.entities.pool import Pool, PoolState, VDev
from backend.zfs_operations.core.value_objects.size_value import SizeValue
from backend.zfs_operations.core.exceptions.zfs_exceptions import (
    PoolException,
    PoolNotFoundError,
    PoolUnavailableError
)
from backend.zfs_operations.core.exceptions.validation_exceptions import ValidationException
from backend.zfs_operations.core.result import Result
from backend.zfs_operations.core.interfaces.command_executor import CommandResult


class TestPoolService:
    """Test suite for PoolService."""
    
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
        validator.validate_zfs_command = Mock(side_effect=lambda cmd, args: args)
        validator.validate_pool_name = Mock(return_value=True)
        validator.validate_vdev_spec = Mock(return_value=True)
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
    def pool_service(self, mock_executor, mock_validator, mock_logger):
        """Create PoolService instance with mocks."""
        return PoolService(
            executor=mock_executor,
            validator=mock_validator,
            logger=mock_logger
        )
    
    @pytest.fixture
    def sample_pool(self):
        """Create sample pool for testing."""
        # Create a sample vdev
        vdev = VDev(
            name="raidz1-0",
            type="raidz1",
            state="ONLINE"
        )
        
        return Pool(
            name="pool1",
            state=PoolState.ONLINE,
            size=SizeValue(10000000000),
            allocated=SizeValue(5000000000),
            free=SizeValue(5000000000),
            vdevs=[vdev],
            properties={
                "version": "28",
                "bootfs": "none",
                "delegation": "on"
            }
        )
    
    # Test list_pools
    
    @pytest.mark.asyncio
    async def test_list_pools_success(self, pool_service, mock_executor):
        """Test successful pool listing."""
        # Mock zpool list command output
        zpool_output = """pool1\t10G\t5G\t5G\t-\t50%\tONLINE\tONLINE
pool2\t20G\t10G\t10G\t-\t50%\tONLINE\tONLINE"""
        
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=zpool_output,
            stderr=""
        )
        
        result = await pool_service.list_pools()
        
        assert result.is_success
        assert len(result.value) == 2
        assert result.value[0].name == "pool1"
        assert result.value[1].name == "pool2"
        mock_executor.execute_zpool.assert_called_once_with(
            "list", "-H", "-o", "name,size,alloc,free,expandsz,frag,health,dedup"
        )
    
    @pytest.mark.asyncio
    async def test_list_pools_empty_result(self, pool_service, mock_executor):
        """Test pool listing with empty result."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.list_pools()
        
        assert result.is_success
        assert len(result.value) == 0
    
    @pytest.mark.asyncio
    async def test_list_pools_command_failure(self, pool_service, mock_executor):
        """Test pool listing with command failure."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="permission denied"
        )
        
        result = await pool_service.list_pools()
        
        assert result.is_failure
        assert isinstance(result.error, PoolException)
        assert "permission denied" in str(result.error)
    
    # Test get_pool
    
    @pytest.mark.asyncio
    async def test_get_pool_success(self, pool_service, mock_executor):
        """Test successful pool retrieval."""
        # Mock zpool list command output for specific pool
        zpool_output = "pool1\t10G\t5G\t5G\t-\t50%\tONLINE\tONLINE"
        
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=zpool_output,
            stderr=""
        )
        
        result = await pool_service.get_pool("pool1")
        
        assert result.is_success
        assert result.value.name == "pool1"
        assert result.value.state == "ONLINE"
        assert result.value.health == "ONLINE"
        mock_executor.execute_zpool.assert_called_once_with(
            "list", "-H", "-o", "name,size,alloc,free,expandsz,frag,health,dedup", "pool1"
        )
    
    @pytest.mark.asyncio
    async def test_get_pool_not_found(self, pool_service, mock_executor):
        """Test retrieval of non-existent pool."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="pool does not exist"
        )
        
        result = await pool_service.get_pool("nonexistent")
        
        assert result.is_failure
        assert isinstance(result.error, PoolNotFoundError)
    
    # Test get_pool_status
    
    @pytest.mark.asyncio
    async def test_get_pool_status_success(self, pool_service, mock_executor):
        """Test successful pool status retrieval."""
        # Mock zpool status command output
        status_output = """  pool: pool1
 state: ONLINE
  scan: none requested
config:

\tNAME        STATE     READ WRITE CKSUM
\tpool1       ONLINE       0     0     0
\t  raidz1-0  ONLINE       0     0     0
\t    sda     ONLINE       0     0     0
\t    sdb     ONLINE       0     0     0
\t    sdc     ONLINE       0     0     0

errors: No known data errors"""
        
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=status_output,
            stderr=""
        )
        
        result = await pool_service.get_pool_status("pool1")
        
        assert result.is_success
        assert "pool1" in result.value
        assert "ONLINE" in result.value
        mock_executor.execute_zpool.assert_called_once_with("status", "pool1")
    
    @pytest.mark.asyncio
    async def test_get_pool_status_not_found(self, pool_service, mock_executor):
        """Test pool status for non-existent pool."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="pool does not exist"
        )
        
        result = await pool_service.get_pool_status("nonexistent")
        
        assert result.is_failure
        assert isinstance(result.error, PoolNotFoundError)
    
    # Test create_pool
    
    @pytest.mark.asyncio
    async def test_create_pool_success(self, pool_service, mock_executor, sample_pool):
        """Test successful pool creation."""
        # Mock successful zpool create command
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        # Mock get_pool to return the created pool
        with patch.object(pool_service, 'get_pool') as mock_get:
            mock_get.return_value = Result.success(sample_pool)
            
            vdev_spec = {
                "type": "raidz1",
                "devices": ["/dev/sda", "/dev/sdb", "/dev/sdc"]
            }
            
            result = await pool_service.create_pool("pool1", [vdev_spec])
            
            assert result.is_success
            assert result.value.name == "pool1"
            mock_executor.execute_zpool.assert_called_once_with(
                "create", "pool1", "raidz1", "/dev/sda", "/dev/sdb", "/dev/sdc"
            )
    
    @pytest.mark.asyncio
    async def test_create_pool_with_properties(self, pool_service, mock_executor, sample_pool):
        """Test pool creation with properties."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        with patch.object(pool_service, 'get_pool') as mock_get:
            mock_get.return_value = Result.success(sample_pool)
            
            vdev_spec = {
                "type": "mirror",
                "devices": ["/dev/sda", "/dev/sdb"]
            }
            
            properties = {
                "ashift": "12",
                "autoreplace": "on"
            }
            
            result = await pool_service.create_pool("pool1", [vdev_spec], properties)
            
            assert result.is_success
            mock_executor.execute_zpool.assert_called_once_with(
                "create", "-o", "ashift=12", "-o", "autoreplace=on", 
                "pool1", "mirror", "/dev/sda", "/dev/sdb"
            )
    
    @pytest.mark.asyncio
    async def test_create_pool_validation_error(self, pool_service, mock_validator):
        """Test pool creation with validation error."""
        # Mock validation to fail
        mock_validator.validate_dataset_name.side_effect = ValidationException("Invalid pool name")
        
        vdev_spec = {
            "type": "single",
            "devices": ["/dev/sda"]
        }
        
        result = await pool_service.create_pool("invalid-pool", [vdev_spec])
        
        assert result.is_failure
        assert isinstance(result.error, ValidationException)
    
    # Test destroy_pool
    
    @pytest.mark.asyncio
    async def test_destroy_pool_success(self, pool_service, mock_executor):
        """Test successful pool destruction."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.destroy_pool("pool1")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zpool.assert_called_once_with("destroy", "pool1")
    
    @pytest.mark.asyncio
    async def test_destroy_pool_force(self, pool_service, mock_executor):
        """Test forced pool destruction."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.destroy_pool("pool1", force=True)
        
        assert result.is_success
        mock_executor.execute_zpool.assert_called_once_with("destroy", "-f", "pool1")
    
    @pytest.mark.asyncio
    async def test_destroy_pool_not_found(self, pool_service, mock_executor):
        """Test destruction of non-existent pool."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="pool does not exist"
        )
        
        result = await pool_service.destroy_pool("nonexistent")
        
        assert result.is_failure
        assert isinstance(result.error, PoolNotFoundError)
    
    # Test export_pool
    
    @pytest.mark.asyncio
    async def test_export_pool_success(self, pool_service, mock_executor):
        """Test successful pool export."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.export_pool("pool1")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zpool.assert_called_once_with("export", "pool1")
    
    @pytest.mark.asyncio
    async def test_export_pool_force(self, pool_service, mock_executor):
        """Test forced pool export."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.export_pool("pool1", force=True)
        
        assert result.is_success
        mock_executor.execute_zpool.assert_called_once_with("export", "-f", "pool1")
    
    # Test import_pool
    
    @pytest.mark.asyncio
    async def test_import_pool_success(self, pool_service, mock_executor):
        """Test successful pool import."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.import_pool("pool1")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zpool.assert_called_once_with("import", "pool1")
    
    @pytest.mark.asyncio
    async def test_import_pool_with_new_name(self, pool_service, mock_executor):
        """Test pool import with new name."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.import_pool("pool1", new_name="pool1_imported")
        
        assert result.is_success
        mock_executor.execute_zpool.assert_called_once_with("import", "pool1", "pool1_imported")
    
    @pytest.mark.asyncio
    async def test_import_pool_force(self, pool_service, mock_executor):
        """Test forced pool import."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.import_pool("pool1", force=True)
        
        assert result.is_success
        mock_executor.execute_zpool.assert_called_once_with("import", "-f", "pool1")
    
    # Test scrub operations
    
    @pytest.mark.asyncio
    async def test_start_scrub_success(self, pool_service, mock_executor):
        """Test successful scrub start."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.start_scrub("pool1")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zpool.assert_called_once_with("scrub", "pool1")
    
    @pytest.mark.asyncio
    async def test_stop_scrub_success(self, pool_service, mock_executor):
        """Test successful scrub stop."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.stop_scrub("pool1")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zpool.assert_called_once_with("scrub", "-s", "pool1")
    
    @pytest.mark.asyncio
    async def test_get_scrub_status_success(self, pool_service, mock_executor):
        """Test successful scrub status retrieval."""
        status_output = """  pool: pool1
 state: ONLINE
  scan: scrub repaired 0B in 0 days 00:15:23 with 0 errors on Sun Dec 31 23:59:59 2023
config:

\tNAME        STATE     READ WRITE CKSUM
\tpool1       ONLINE       0     0     0

errors: No known data errors"""
        
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=status_output,
            stderr=""
        )
        
        result = await pool_service.get_scrub_status("pool1")
        
        assert result.is_success
        assert "scrub repaired" in result.value
        mock_executor.execute_zpool.assert_called_once_with("status", "pool1")
    
    # Test I/O statistics
    
    @pytest.mark.asyncio
    async def test_get_iostat_success(self, pool_service, mock_executor):
        """Test successful I/O statistics retrieval."""
        iostat_output = """               capacity     operations    bandwidth
pool         alloc   free   read  write   read  write
-----------  -----  -----  -----  -----  -----  -----
pool1         5.0G   5.0G     10     20   100K   200K
  raidz1-0    5.0G   5.0G     10     20   100K   200K
    sda          -      -      3      7   33.3K   66.7K
    sdb          -      -      3      7   33.3K   66.7K
    sdc          -      -      4      6   33.3K   66.7K
-----------  -----  -----  -----  -----  -----  -----"""
        
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=iostat_output,
            stderr=""
        )
        
        result = await pool_service.get_iostat("pool1")
        
        assert result.is_success
        assert "pool1" in result.value
        assert "capacity" in result.value
        mock_executor.execute_zpool.assert_called_once_with("iostat", "pool1")
    
    @pytest.mark.asyncio
    async def test_get_iostat_all_pools(self, pool_service, mock_executor):
        """Test I/O statistics for all pools."""
        iostat_output = """               capacity     operations    bandwidth
pool         alloc   free   read  write   read  write
-----------  -----  -----  -----  -----  -----  -----
pool1         5.0G   5.0G     10     20   100K   200K
pool2        10.0G  10.0G     20     40   200K   400K
-----------  -----  -----  -----  -----  -----  -----"""
        
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=iostat_output,
            stderr=""
        )
        
        result = await pool_service.get_iostat()
        
        assert result.is_success
        assert "pool1" in result.value
        assert "pool2" in result.value
        mock_executor.execute_zpool.assert_called_once_with("iostat")
    
    # Test pool health monitoring
    
    @pytest.mark.asyncio
    async def test_check_pool_health_success(self, pool_service, mock_executor):
        """Test successful pool health check."""
        # Mock healthy pool status
        status_output = """  pool: pool1
 state: ONLINE
  scan: none requested
config:

\tNAME        STATE     READ WRITE CKSUM
\tpool1       ONLINE       0     0     0
\t  raidz1-0  ONLINE       0     0     0
\t    sda     ONLINE       0     0     0
\t    sdb     ONLINE       0     0     0
\t    sdc     ONLINE       0     0     0

errors: No known data errors"""
        
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=status_output,
            stderr=""
        )
        
        result = await pool_service.check_pool_health("pool1")
        
        assert result.is_success
        health_info = result.value
        assert health_info["pool"] == "pool1"
        assert health_info["state"] == "ONLINE"
        assert health_info["health"] == "HEALTHY"
        assert health_info["errors"] == 0
    
    @pytest.mark.asyncio
    async def test_check_pool_health_degraded(self, pool_service, mock_executor):
        """Test pool health check with degraded state."""
        # Mock degraded pool status
        status_output = """  pool: pool1
 state: DEGRADED
status: One or more devices has experienced an unrecoverable error.
\tSufficient replicas exist for the pool to continue functioning.
action: Determine if the device needs to be replaced, and clear the errors
\tusing 'zpool clear' or replace the device with 'zpool replace'.
config:

\tNAME        STATE     READ WRITE CKSUM
\tpool1       DEGRADED     0     0     0
\t  raidz1-0  DEGRADED     0     0     0
\t    sda     ONLINE       0     0     0
\t    sdb     UNAVAIL      0     0     0  corrupted data
\t    sdc     ONLINE       0     0     0

errors: No known data errors"""
        
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=status_output,
            stderr=""
        )
        
        result = await pool_service.check_pool_health("pool1")
        
        assert result.is_success
        health_info = result.value
        assert health_info["pool"] == "pool1"
        assert health_info["state"] == "DEGRADED"
        assert health_info["health"] == "DEGRADED"
        assert "corrupted data" in health_info["issues"]
    
    # Test pool properties
    
    @pytest.mark.asyncio
    async def test_get_pool_properties_success(self, pool_service, mock_executor):
        """Test successful pool properties retrieval."""
        # Mock zpool get command output
        props_output = """pool1\tversion\t28\tdefault
pool1\tbootfs\tnone\tdefault
pool1\tdelegation\ton\tdefault
pool1\tautoreplace\toff\tdefault"""
        
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=props_output,
            stderr=""
        )
        
        result = await pool_service.get_pool_properties("pool1")
        
        assert result.is_success
        props = result.value
        assert props["version"] == "28"
        assert props["bootfs"] == "none"
        assert props["delegation"] == "on"
        mock_executor.execute_zpool.assert_called_once_with("get", "all", "pool1")
    
    @pytest.mark.asyncio
    async def test_set_pool_property_success(self, pool_service, mock_executor):
        """Test successful pool property setting."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.set_pool_property("pool1", "autoreplace", "on")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zpool.assert_called_once_with("set", "autoreplace=on", "pool1")
    
    # Test device management
    
    @pytest.mark.asyncio
    async def test_add_device_success(self, pool_service, mock_executor):
        """Test successful device addition."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.add_device("pool1", ["/dev/sdd"])
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zpool.assert_called_once_with("add", "pool1", "/dev/sdd")
    
    @pytest.mark.asyncio
    async def test_remove_device_success(self, pool_service, mock_executor):
        """Test successful device removal."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.remove_device("pool1", "/dev/sdd")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zpool.assert_called_once_with("remove", "pool1", "/dev/sdd")
    
    @pytest.mark.asyncio
    async def test_replace_device_success(self, pool_service, mock_executor):
        """Test successful device replacement."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = await pool_service.replace_device("pool1", "/dev/sdb", "/dev/sdd")
        
        assert result.is_success
        assert result.value is True
        mock_executor.execute_zpool.assert_called_once_with("replace", "pool1", "/dev/sdb", "/dev/sdd")
    
    # Test error handling and edge cases
    
    @pytest.mark.asyncio
    async def test_unexpected_error_handling(self, pool_service, mock_executor):
        """Test handling of unexpected errors."""
        # Mock executor to raise exception
        mock_executor.execute_zpool.side_effect = Exception("Unexpected error")
        
        result = await pool_service.get_pool("pool1")
        
        assert result.is_failure
        assert isinstance(result.error, PoolException)
        assert "Unexpected error" in str(result.error)
    
    @pytest.mark.asyncio
    async def test_malformed_zpool_output(self, pool_service, mock_executor):
        """Test handling of malformed zpool output."""
        # Mock zpool command with malformed output
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="invalid\toutput",  # Missing required fields
            stderr=""
        )
        
        result = await pool_service.list_pools()
        
        assert result.is_failure
        assert isinstance(result.error, PoolException)
    
    @pytest.mark.asyncio
    async def test_pool_unavailable_error(self, pool_service, mock_executor):
        """Test handling of pool unavailable error."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=False,
            returncode=1,
            stdout="",
            stderr="pool is unavailable"
        )
        
        result = await pool_service.get_pool("pool1")
        
        assert result.is_failure
        assert isinstance(result.error, PoolUnavailableError)
    
    # Test validation integration
    
    @pytest.mark.asyncio
    async def test_pool_name_validation_integration(self, pool_service, mock_validator):
        """Test integration with pool name validation."""
        # Mock validator to be called
        mock_validator.validate_dataset_name = Mock(return_value="pool1")
        
        # Mock executor for successful creation
        mock_executor = Mock()
        mock_executor.execute_zpool = AsyncMock(return_value=CommandResult(
            success=True, returncode=0, stdout="", stderr=""
        ))
        pool_service._executor = mock_executor
        
        # Mock get_pool for post-creation verification
        with patch.object(pool_service, 'get_pool') as mock_get:
            mock_get.return_value = Result.success(Mock())
            
            vdev_spec = {"type": "single", "devices": ["/dev/sda"]}
            await pool_service.create_pool("pool1", [vdev_spec])
            
            # Verify validation was called
            mock_validator.validate_dataset_name.assert_called_with("pool1")
    
    @pytest.mark.asyncio
    async def test_logger_integration(self, pool_service, mock_logger, mock_executor):
        """Test integration with logger."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="",
            stderr=""
        )
        
        await pool_service.destroy_pool("pool1")
        
        # Verify logger was called
        mock_logger.info.assert_called()
        assert any("Destroying pool" in str(call) for call in mock_logger.info.call_args_list)
    
    # Test concurrent operations
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, pool_service, mock_executor):
        """Test concurrent pool operations."""
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout="pool1\t10G\t5G\t5G\t-\t50%\tONLINE\tONLINE",
            stderr=""
        )
        
        # Create multiple concurrent operations
        tasks = [
            pool_service.get_pool(f"pool{i}")
            for i in range(1, 6)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All operations should succeed
        assert all(result.is_success for result in results)
        assert mock_executor.execute_zpool.call_count == 5
    
    # Test pool monitoring and alerts
    
    @pytest.mark.asyncio
    async def test_monitor_pool_health_success(self, pool_service, mock_executor):
        """Test pool health monitoring."""
        # Mock multiple health checks
        health_checks = [
            "pool1\tONLINE\tONLINE",
            "pool2\tONLINE\tONLINE",
            "pool3\tDEGRADED\tDEGRADED"
        ]
        
        mock_executor.execute_zpool.side_effect = [
            CommandResult(success=True, returncode=0, stdout="\n".join(health_checks), stderr="")
        ]
        
        result = await pool_service.monitor_all_pools()
        
        assert result.is_success
        health_report = result.value
        assert len(health_report) == 3
        assert health_report[0]["pool"] == "pool1"
        assert health_report[0]["status"] == "HEALTHY"
        assert health_report[2]["pool"] == "pool3"
        assert health_report[2]["status"] == "DEGRADED"
    
    # Test data parsing accuracy
    
    @pytest.mark.asyncio
    async def test_size_parsing_accuracy(self, pool_service, mock_executor):
        """Test accurate size parsing from zpool output."""
        # Test various size formats
        zpool_output = "pool1\t1.5T\t750G\t750G\t-\t50%\tONLINE\tONLINE"
        
        mock_executor.execute_zpool.return_value = CommandResult(
            success=True,
            returncode=0,
            stdout=zpool_output,
            stderr=""
        )
        
        result = await pool_service.get_pool("pool1")
        
        assert result.is_success
        pool = result.value
        # Verify size conversion (1.5T = 1.5 * 1024^4 bytes)
        expected_size = int(1.5 * 1024**4)
        assert abs(pool.size.bytes - expected_size) < 1024**3  # Allow for rounding
    
    @pytest.mark.asyncio
    async def test_health_state_parsing(self, pool_service, mock_executor):
        """Test accurate health state parsing."""
        # Test various health states
        test_cases = [
            ("ONLINE", "ONLINE", "HEALTHY"),
            ("DEGRADED", "DEGRADED", "DEGRADED"),
            ("FAULTED", "FAULTED", "FAULTED"),
            ("UNAVAIL", "UNAVAIL", "UNAVAILABLE")
        ]
        
        for state, health, expected in test_cases:
            zpool_output = f"pool1\t10G\t5G\t5G\t-\t50%\t{state}\t{health}"
            
            mock_executor.execute_zpool.return_value = CommandResult(
                success=True,
                returncode=0,
                stdout=zpool_output,
                stderr=""
            )
            
            result = await pool_service.get_pool("pool1")
            
            assert result.is_success
            pool = result.value
            assert pool.state == state
            assert pool.health == health 