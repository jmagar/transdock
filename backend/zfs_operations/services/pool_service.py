from typing import List, Optional, Dict, Any
from datetime import datetime

from ..core.interfaces.command_executor import ICommandExecutor
from ..core.interfaces.security_validator import ISecurityValidator  
from ..core.interfaces.logger_interface import ILogger
from ..core.entities.pool import Pool, PoolState, VDev
from ..core.value_objects.size_value import SizeValue
from ..core.exceptions.zfs_exceptions import (
    PoolException, 
    PoolNotFoundError, 
    PoolUnavailableError
)
from ..core.exceptions.validation_exceptions import ValidationException
from ..core.result import Result


class PoolService:
    """Service for managing ZFS pools with comprehensive operations."""
    
    def __init__(self, 
                 executor: ICommandExecutor,
                 validator: ISecurityValidator,
                 logger: ILogger):
        self._executor = executor
        self._validator = validator
        self._logger = logger
    
    async def get_pool(self, pool_name: str) -> Result[Pool, PoolException]:
        """Get detailed information about a specific pool."""
        try:
            self._logger.info(f"Fetching pool: {pool_name}")
            
            # Validate pool name
            validation_result = await self._validate_pool_name(pool_name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Get pool status information
            status_result = await self._get_pool_status(pool_name)
            if status_result.is_failure:
                return Result.failure(status_result.error)
            
            # Get pool properties
            properties_result = await self._get_pool_properties(pool_name)
            if properties_result.is_failure:
                return Result.failure(properties_result.error)
            
            # Get pool capacity information
            capacity_result = await self._get_pool_capacity(pool_name)
            if capacity_result.is_failure:
                return Result.failure(capacity_result.error)
            
            # Combine all information into Pool entity
            pool_data = {
                **status_result.value,
                **properties_result.value,
                **capacity_result.value
            }
            
            # Convert state string to PoolState enum
            state_str = pool_data.get('state', PoolState.ONLINE.value)
            try:
                pool_state = PoolState(state_str)
            except ValueError:
                pool_state = PoolState.ONLINE  # Default to ONLINE if unknown state
            
            pool = Pool(
                name=pool_name,
                state=pool_state,
                size=pool_data.get('size', SizeValue(0)),
                allocated=pool_data.get('allocated', SizeValue(0)),
                free=pool_data.get('free', SizeValue(0)),
                properties=pool_data.get('properties', {}),
                vdevs=pool_data.get('vdevs', []),
                scan_stats=pool_data.get('scan_stats'),
                errors=pool_data.get('errors', {})
            )
            
            self._logger.info(f"Successfully fetched pool: {pool_name}")
            return Result.success(pool)
            
        except Exception as e:
            self._logger.error(f"Unexpected error fetching pool {pool_name}: {e}")
            return Result.failure(PoolException(
                f"Unexpected error: {str(e)}",
                error_code="POOL_UNEXPECTED_ERROR"
            ))
    
    async def list_pools(self) -> Result[List[Pool], PoolException]:
        """List all ZFS pools in the system."""
        try:
            self._logger.info("Listing all pools")
            
            # Execute zpool list command
            result = await self._executor.execute_system("zpool", "list", "-H", "-o", "name,size,alloc,free,ckpoint,expandsz,frag,cap,dedup,health,altroot")
            
            if not result.success:
                return Result.failure(PoolException(
                    f"Failed to list pools: {result.stderr}",
                    error_code="POOL_LIST_FAILED"
                ))
            
            # Parse pool list
            pools_result = await self._parse_pool_list(result.stdout)
            if pools_result.is_failure:
                return Result.failure(pools_result.error)
            
            self._logger.info(f"Successfully listed {len(pools_result.value)} pools")
            return Result.success(pools_result.value)
            
        except Exception as e:
            self._logger.error(f"Unexpected error listing pools: {e}")
            return Result.failure(PoolException(
                f"Unexpected error: {str(e)}",
                error_code="POOL_LIST_UNEXPECTED_ERROR"
            ))
    
    async def get_pool_health(self, pool_name: str) -> Result[Dict[str, Any], PoolException]:
        """Get comprehensive health information for a pool."""
        try:
            self._logger.info(f"Getting health information for pool: {pool_name}")
            
            # Validate pool name
            validation_result = await self._validate_pool_name(pool_name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Get detailed pool status
            status_result = await self._get_detailed_pool_status(pool_name)
            if status_result.is_failure:
                return Result.failure(status_result.error)
            
            # Get pool errors
            errors_result = await self._get_pool_errors(pool_name)
            if errors_result.is_failure:
                return Result.failure(errors_result.error)
            
            # Get scrub status
            scrub_result = await self._get_scrub_status(pool_name)
            if scrub_result.is_failure:
                return Result.failure(scrub_result.error)
            
            # Combine health information
            health_info = {
                'pool_name': pool_name,
                'status': status_result.value,
                'errors': errors_result.value,
                'scrub': scrub_result.value,
                'health_score': self._calculate_health_score(status_result.value, errors_result.value),
                'recommendations': self._generate_health_recommendations(status_result.value, errors_result.value)
            }
            
            self._logger.info(f"Successfully retrieved health information for pool: {pool_name}")
            return Result.success(health_info)
            
        except Exception as e:
            self._logger.error(f"Unexpected error getting pool health {pool_name}: {e}")
            return Result.failure(PoolException(
                f"Unexpected error: {str(e)}",
                error_code="POOL_HEALTH_UNEXPECTED_ERROR"
            ))
    
    async def start_scrub(self, pool_name: str) -> Result[bool, PoolException]:
        """Start a scrub operation on a pool."""
        try:
            self._logger.info(f"Starting scrub for pool: {pool_name}")
            
            # Validate pool name
            validation_result = await self._validate_pool_name(pool_name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Check if pool exists and is online
            pool_result = await self.get_pool(pool_name)
            if pool_result.is_failure:
                return Result.failure(pool_result.error)
            
            pool = pool_result.value
            if pool.state != PoolState.ONLINE:
                return Result.failure(PoolUnavailableError(
                    f"Pool {pool_name} is not online (state: {pool.state})"
                ))
            
            # Check if scrub is already running
            scrub_status_result = await self._get_scrub_status(pool_name)
            if scrub_status_result.is_success and scrub_status_result.value.get('in_progress'):
                return Result.failure(PoolException(
                    f"Scrub already in progress for pool: {pool_name}",
                    error_code="SCRUB_ALREADY_RUNNING"
                ))
            
            # Start scrub
            result = await self._executor.execute_system("zpool", "scrub", pool_name)
            
            if not result.success:
                return Result.failure(PoolException(
                    f"Failed to start scrub: {result.stderr}",
                    error_code="SCRUB_START_FAILED"
                ))
            
            self._logger.info(f"Successfully started scrub for pool: {pool_name}")
            return Result.success(True)
            
        except Exception as e:
            self._logger.error(f"Unexpected error starting scrub for pool {pool_name}: {e}")
            return Result.failure(PoolException(
                f"Unexpected error: {str(e)}",
                error_code="SCRUB_START_UNEXPECTED_ERROR"
            ))
    
    async def stop_scrub(self, pool_name: str) -> Result[bool, PoolException]:
        """Stop a running scrub operation on a pool."""
        try:
            self._logger.info(f"Stopping scrub for pool: {pool_name}")
            
            # Validate pool name
            validation_result = await self._validate_pool_name(pool_name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Check if scrub is running
            scrub_status_result = await self._get_scrub_status(pool_name)
            if scrub_status_result.is_failure:
                return Result.failure(scrub_status_result.error)
            
            if not scrub_status_result.value.get('in_progress'):
                return Result.failure(PoolException(
                    f"No scrub in progress for pool: {pool_name}",
                    error_code="NO_SCRUB_RUNNING"
                ))
            
            # Stop scrub
            result = await self._executor.execute_system("zpool", "scrub", "-s", pool_name)
            
            if not result.success:
                return Result.failure(PoolException(
                    f"Failed to stop scrub: {result.stderr}",
                    error_code="SCRUB_STOP_FAILED"
                ))
            
            self._logger.info(f"Successfully stopped scrub for pool: {pool_name}")
            return Result.success(True)
            
        except Exception as e:
            self._logger.error(f"Unexpected error stopping scrub for pool {pool_name}: {e}")
            return Result.failure(PoolException(
                f"Unexpected error: {str(e)}",
                error_code="SCRUB_STOP_UNEXPECTED_ERROR"
            ))
    
    async def get_iostat(self, 
                        pool_name: Optional[str] = None,
                        interval: int = 1,
                        count: int = 1) -> Result[Dict[str, Any], PoolException]:
        """Get I/O statistics for pools."""
        try:
            self._logger.info(f"Getting I/O statistics for pool: {pool_name or 'all'}")
            
            # Build command arguments
            command_args = ["iostat", "-v"]
            
            if pool_name:
                validation_result = await self._validate_pool_name(pool_name)
                if validation_result.is_failure:
                    return Result.failure(validation_result.error)
                command_args.append(pool_name)
            
            command_args.extend([str(interval), str(count)])
            
            # Execute iostat command
            result = await self._executor.execute_system("zpool", *command_args)
            
            if not result.success:
                return Result.failure(PoolException(
                    f"Failed to get I/O statistics: {result.stderr}",
                    error_code="IOSTAT_FAILED"
                ))
            
            # Parse iostat output
            iostat_data = await self._parse_iostat_output(result.stdout)
            if iostat_data.is_failure:
                return Result.failure(iostat_data.error)
            
            self._logger.info("Successfully retrieved I/O statistics")
            return Result.success(iostat_data.value)
            
        except Exception as e:
            self._logger.error(f"Unexpected error getting I/O statistics: {e}")
            return Result.failure(PoolException(
                f"Unexpected error: {str(e)}",
                error_code="IOSTAT_UNEXPECTED_ERROR"
            ))
    
    async def export_pool(self, pool_name: str, force: bool = False) -> Result[bool, PoolException]:
        """Export a ZFS pool."""
        try:
            self._logger.info(f"Exporting pool: {pool_name} (force={force})")
            
            # Validate pool name
            validation_result = await self._validate_pool_name(pool_name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Check if pool exists
            pool_result = await self.get_pool(pool_name)
            if pool_result.is_failure:
                return Result.failure(pool_result.error)
            
            # Build export command
            command_args = ["export"]
            if force:
                command_args.append("-f")
            command_args.append(pool_name)
            
            # Execute export command
            result = await self._executor.execute_system("zpool", *command_args)
            
            if not result.success:
                return Result.failure(PoolException(
                    f"Failed to export pool: {result.stderr}",
                    error_code="POOL_EXPORT_FAILED"
                ))
            
            self._logger.info(f"Successfully exported pool: {pool_name}")
            return Result.success(True)
            
        except Exception as e:
            self._logger.error(f"Unexpected error exporting pool {pool_name}: {e}")
            return Result.failure(PoolException(
                f"Unexpected error: {str(e)}",
                error_code="POOL_EXPORT_UNEXPECTED_ERROR"
            ))
    
    async def import_pool(self, 
                        pool_name: str,
                        new_name: Optional[str] = None,
                        force: bool = False) -> Result[bool, PoolException]:
        """Import a ZFS pool."""
        try:
            import_name = new_name or pool_name
            self._logger.info(f"Importing pool: {pool_name} as {import_name} (force={force})")
            
            # Validate pool names
            validation_result = await self._validate_pool_name(pool_name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            if new_name:
                validation_result = await self._validate_pool_name(new_name)
                if validation_result.is_failure:
                    return Result.failure(validation_result.error)
            
            # Build import command
            command_args = ["import"]
            if force:
                command_args.append("-f")
            command_args.append(pool_name)
            if new_name:
                command_args.append(new_name)
            
            # Execute import command
            result = await self._executor.execute_system("zpool", *command_args)
            
            if not result.success:
                return Result.failure(PoolException(
                    f"Failed to import pool: {result.stderr}",
                    error_code="POOL_IMPORT_FAILED"
                ))
            
            self._logger.info(f"Successfully imported pool: {pool_name} as {import_name}")
            return Result.success(True)
            
        except Exception as e:
            self._logger.error(f"Unexpected error importing pool {pool_name}: {e}")
            return Result.failure(PoolException(
                f"Unexpected error: {str(e)}",
                error_code="POOL_IMPORT_UNEXPECTED_ERROR"
            ))
    
    async def get_pool_history(self, pool_name: str) -> Result[List[Dict[str, Any]], PoolException]:
        """Get history of operations for a pool."""
        try:
            self._logger.info(f"Getting history for pool: {pool_name}")
            
            # Validate pool name
            validation_result = await self._validate_pool_name(pool_name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Execute history command
            result = await self._executor.execute_system("zpool", "history", "-l", pool_name)
            
            if not result.success:
                return Result.failure(PoolException(
                    f"Failed to get pool history: {result.stderr}",
                    error_code="POOL_HISTORY_FAILED"
                ))
            
            # Parse history output
            history_data = await self._parse_pool_history(result.stdout)
            if history_data.is_failure:
                return Result.failure(history_data.error)
            
            self._logger.info(f"Successfully retrieved history for pool: {pool_name}")
            return Result.success(history_data.value)
            
        except Exception as e:
            self._logger.error(f"Unexpected error getting pool history {pool_name}: {e}")
            return Result.failure(PoolException(
                f"Unexpected error: {str(e)}",
                error_code="POOL_HISTORY_UNEXPECTED_ERROR"
            ))
    
    # Private helper methods
    
    async def _validate_pool_name(self, pool_name: str) -> Result[bool, ValidationException]:
        """Validate pool name using security validator."""
        try:
            validated = self._validator.validate_pool_name(pool_name)
            if not validated:
                return Result.failure(ValidationException(
                    f"Invalid pool name: {pool_name}"
                ))
            return Result.success(True)
        except Exception as e:
            return Result.failure(ValidationException(
                f"Pool name validation failed: {str(e)}"
            ))
    
    async def _get_pool_status(self, pool_name: str) -> Result[Dict[str, Any], PoolException]:
        """Get basic pool status information."""
        try:
            result = await self._executor.execute_system("zpool", "status", pool_name)
            
            if not result.success:
                if "no such pool" in result.stderr.lower():
                    return Result.failure(PoolNotFoundError(pool_name))
                return Result.failure(PoolException(
                    f"Failed to get pool status: {result.stderr}",
                    error_code="POOL_STATUS_FAILED"
                ))
            
            return await self._parse_pool_status(result.stdout)
            
        except Exception as e:
            return Result.failure(PoolException(
                f"Failed to get pool status: {str(e)}",
                error_code="POOL_STATUS_UNEXPECTED_ERROR"
            ))
    
    async def _get_pool_properties(self, pool_name: str) -> Result[Dict[str, Any], PoolException]:
        """Get pool properties."""
        try:
            result = await self._executor.execute_system("zpool", "get", "-H", "all", pool_name)
            
            if not result.success:
                return Result.failure(PoolException(
                    f"Failed to get pool properties: {result.stderr}",
                    error_code="POOL_PROPERTIES_FAILED"
                ))
            
            properties = {}
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        properties[parts[1]] = parts[2]
            
            return Result.success(properties)
            
        except Exception as e:
            return Result.failure(PoolException(
                f"Failed to parse pool properties: {str(e)}",
                error_code="POOL_PROPERTIES_PARSE_FAILED"
            ))
    
    async def _get_pool_capacity(self, pool_name: str) -> Result[Dict[str, Any], PoolException]:
        """Get pool capacity information."""
        try:
            result = await self._executor.execute_system("zpool", "list", "-H", "-o", "size,alloc,free,cap,frag", pool_name)
            
            if not result.success:
                return Result.failure(PoolException(
                    f"Failed to get pool capacity: {result.stderr}",
                    error_code="POOL_CAPACITY_FAILED"
                ))
            
            lines = result.stdout.strip().split('\n')
            if not lines or not lines[0].strip():
                return Result.failure(PoolException(
                    "Empty pool capacity output",
                    error_code="POOL_CAPACITY_EMPTY"
                ))
            
            parts = lines[0].split('\t')
            if len(parts) < 5:
                return Result.failure(PoolException(
                    f"Invalid pool capacity format: {lines[0]}",
                    error_code="POOL_CAPACITY_FORMAT_INVALID"
                ))
            
            capacity_info = {
                'size': SizeValue.from_zfs_string(parts[0]),
                'allocated': SizeValue.from_zfs_string(parts[1]),
                'free': SizeValue.from_zfs_string(parts[2]),
                'capacity_percent': int(parts[3].rstrip('%')) if parts[3] != '-' else 0,
                'fragmentation_percent': int(parts[4].rstrip('%')) if parts[4] != '-' else 0
            }
            
            return Result.success(capacity_info)
            
        except Exception as e:
            return Result.failure(PoolException(
                f"Failed to parse pool capacity: {str(e)}",
                error_code="POOL_CAPACITY_PARSE_FAILED"
            ))
    
    async def _get_detailed_pool_status(self, pool_name: str) -> Result[Dict[str, Any], PoolException]:
        """Get detailed pool status with vdev information."""
        try:
            result = await self._executor.execute_system("zpool", "status", "-v", pool_name)
            
            if not result.success:
                return Result.failure(PoolException(
                    f"Failed to get detailed pool status: {result.stderr}",
                    error_code="POOL_DETAILED_STATUS_FAILED"
                ))
            
            return await self._parse_detailed_pool_status(result.stdout)
            
        except Exception as e:
            return Result.failure(PoolException(
                f"Failed to get detailed pool status: {str(e)}",
                error_code="POOL_DETAILED_STATUS_UNEXPECTED_ERROR"
            ))
    
    async def _get_pool_errors(self, pool_name: str) -> Result[Dict[str, Any], PoolException]:
        """Get pool error information."""
        try:
            result = await self._executor.execute_system("zpool", "status", "-x", pool_name)
            
            if not result.success:
                return Result.failure(PoolException(
                    f"Failed to get pool errors: {result.stderr}",
                    error_code="POOL_ERRORS_FAILED"
                ))
            
            # Parse error output
            errors = {
                'read_errors': 0,
                'write_errors': 0,
                'checksum_errors': 0,
                'error_details': []
            }
            
            # If output contains "all pools are healthy", no errors
            if "all pools are healthy" in result.stdout.lower():
                errors['healthy'] = True
            else:
                errors['healthy'] = False
                errors['error_details'] = result.stdout.strip().split('\n')
            
            return Result.success(errors)
            
        except Exception as e:
            return Result.failure(PoolException(
                f"Failed to get pool errors: {str(e)}",
                error_code="POOL_ERRORS_UNEXPECTED_ERROR"
            ))
    
    async def _get_scrub_status(self, pool_name: str) -> Result[Dict[str, Any], PoolException]:
        """Get scrub status for a pool."""
        try:
            result = await self._executor.execute_system("zpool", "status", "-v", pool_name)
            
            if not result.success:
                return Result.failure(PoolException(
                    f"Failed to get scrub status: {result.stderr}",
                    error_code="SCRUB_STATUS_FAILED"
                ))
            
            return await self._parse_scrub_status(result.stdout)
            
        except Exception as e:
            return Result.failure(PoolException(
                f"Failed to get scrub status: {str(e)}",
                error_code="SCRUB_STATUS_UNEXPECTED_ERROR"
            ))
    
    def _calculate_health_score(self, status_info: Dict[str, Any], error_info: Dict[str, Any]) -> int:
        """Calculate a health score for the pool (0-100)."""
        score = 100
        
        # Deduct points for state issues
        state = status_info.get('state', 'UNKNOWN')
        if state != 'ONLINE':
            score -= 30
        
        # Deduct points for errors
        if not error_info.get('healthy', True):
            score -= 20
        
        # Deduct points for capacity
        capacity = status_info.get('capacity_percent', 0)
        if capacity > 90:
            score -= 20
        elif capacity > 80:
            score -= 10
        
        # Deduct points for fragmentation
        fragmentation = status_info.get('fragmentation_percent', 0)
        if fragmentation > 50:
            score -= 15
        elif fragmentation > 30:
            score -= 10
        
        return max(0, score)
    
    def _generate_health_recommendations(self, status_info: Dict[str, Any], error_info: Dict[str, Any]) -> List[str]:
        """Generate health recommendations based on pool status."""
        recommendations = []
        
        # State recommendations
        state = status_info.get('state', 'UNKNOWN')
        if state != 'ONLINE':
            recommendations.append(f"Pool state is {state}. Check pool status and resolve any issues.")
        
        # Error recommendations
        if not error_info.get('healthy', True):
            recommendations.append("Pool has errors. Run 'zpool scrub' to identify and potentially repair issues.")
        
        # Capacity recommendations
        capacity = status_info.get('capacity_percent', 0)
        if capacity > 90:
            recommendations.append("Pool is over 90% full. Add more storage or remove data to prevent performance issues.")
        elif capacity > 80:
            recommendations.append("Pool is over 80% full. Consider adding more storage.")
        
        # Fragmentation recommendations
        fragmentation = status_info.get('fragmentation_percent', 0)
        if fragmentation > 50:
            recommendations.append("Pool has high fragmentation (>50%). Consider defragmentation strategies.")
        elif fragmentation > 30:
            recommendations.append("Pool has moderate fragmentation (>30%). Monitor and consider optimization.")
        
        # Scrub recommendations
        scrub_info = status_info.get('scrub', {})
        if not scrub_info.get('recent_scrub', False):
            recommendations.append("No recent scrub detected. Run regular scrubs to maintain data integrity.")
        
        if not recommendations:
            recommendations.append("Pool appears healthy. Continue regular monitoring and maintenance.")
        
        return recommendations
    
    async def _parse_pool_status(self, output: str) -> Result[Dict[str, Any], PoolException]:
        """Parse basic pool status output."""
        try:
            status_info = {
                'state': 'UNKNOWN',
                'health': 'UNKNOWN',
                'scan': 'none'
            }
            
            lines = output.strip().split('\n')
            for line in lines:
                line = line.strip()
                if 'state:' in line.lower():
                    status_info['state'] = line.split(':', 1)[1].strip()
                elif 'status:' in line.lower():
                    status_info['health'] = line.split(':', 1)[1].strip()
                elif 'scan:' in line.lower():
                    status_info['scan'] = line.split(':', 1)[1].strip()
            
            return Result.success(status_info)
            
        except Exception as e:
            return Result.failure(PoolException(
                f"Failed to parse pool status: {str(e)}",
                error_code="POOL_STATUS_PARSE_FAILED"
            ))
    
    async def _parse_detailed_pool_status(self, output: str) -> Result[Dict[str, Any], PoolException]:
        """Parse detailed pool status with vdev information."""
        try:
            # This would include parsing vdev information
            # For now, return basic status info
            return await self._parse_pool_status(output)
            
        except Exception as e:
            return Result.failure(PoolException(
                f"Failed to parse detailed pool status: {str(e)}",
                error_code="POOL_DETAILED_STATUS_PARSE_FAILED"
            ))
    
    async def _parse_scrub_status(self, output: str) -> Result[Dict[str, Any], PoolException]:
        """Parse scrub status from pool status output."""
        try:
            scrub_info = {
                'in_progress': False,
                'recent_scrub': False,
                'completion_time': None,
                'errors_found': 0
            }
            
            lines = output.strip().split('\n')
            for line in lines:
                line = line.strip().lower()
                if 'scrub in progress' in line:
                    scrub_info['in_progress'] = True
                elif 'scrub repaired' in line or 'scrub completed' in line:
                    scrub_info['recent_scrub'] = True
                elif 'no known data errors' in line:
                    scrub_info['errors_found'] = 0
            
            return Result.success(scrub_info)
            
        except Exception as e:
            return Result.failure(PoolException(
                f"Failed to parse scrub status: {str(e)}",
                error_code="SCRUB_STATUS_PARSE_FAILED"
            ))
    
    async def _parse_pool_list(self, output: str) -> Result[List[Pool], PoolException]:
        """Parse list of pools from zpool list output."""
        try:
            pools = []
            lines = output.strip().split('\n')
            
            for line in lines:
                if not line.strip():
                    continue
                
                parts = line.split('\t')
                if len(parts) < 11:
                    continue
                
                try:
                    pool = Pool(
                        name=parts[0],
                        state=PoolState.ONLINE,  # Default, will be updated by status check
                        size=SizeValue.from_zfs_string(parts[1]),
                        allocated=SizeValue.from_zfs_string(parts[2]),
                        free=SizeValue.from_zfs_string(parts[3])
                    )
                    
                    pools.append(pool)
                    
                except Exception as e:
                    self._logger.warning(f"Failed to parse pool line: {line}, error: {e}")
                    continue
            
            return Result.success(pools)
            
        except Exception as e:
            return Result.failure(PoolException(
                f"Failed to parse pool list: {str(e)}",
                error_code="POOL_LIST_PARSE_FAILED"
            ))
    
    async def _parse_iostat_output(self, output: str) -> Result[Dict[str, Any], PoolException]:
        """Parse zpool iostat output."""
        try:
            iostat_data = {
                'timestamp': datetime.now(),
                'pools': []
            }
            
            lines = output.strip().split('\n')
            
            # Skip header lines and parse pool data
            for line in lines:
                if line.strip() and not line.startswith('pool') and not line.startswith('-'):
                    parts = line.split()
                    if len(parts) >= 7:
                        pool_data = {
                            'name': parts[0],
                            'alloc': parts[1],
                            'free': parts[2],
                            'read_ops': parts[3],
                            'write_ops': parts[4],
                            'read_bandwidth': parts[5],
                            'write_bandwidth': parts[6]
                        }
                        iostat_data['pools'].append(pool_data)
            
            return Result.success(iostat_data)
            
        except Exception as e:
            return Result.failure(PoolException(
                f"Failed to parse iostat output: {str(e)}",
                error_code="IOSTAT_PARSE_FAILED"
            ))
    
    async def _parse_pool_history(self, output: str) -> Result[List[Dict[str, Any]], PoolException]:
        """Parse pool history output."""
        try:
            history = []
            lines = output.strip().split('\n')
            
            for line in lines:
                if line.strip() and not line.startswith('History'):
                    # Basic parsing - would need more sophisticated parsing for full history
                    history.append({
                        'timestamp': datetime.now(),
                        'event': line.strip()
                    })
            
            return Result.success(history)
            
        except Exception as e:
            return Result.failure(PoolException(
                f"Failed to parse pool history: {str(e)}",
                error_code="POOL_HISTORY_PARSE_FAILED"
            )) 