import platform
import logging
from typing import Dict, Any, Union, List
from ..zfs_operations.factories.service_factory import create_default_service_factory
from ..zfs_operations.services.pool_service import PoolService
from ..docker_ops import DockerOperations
from ..security_utils import SecurityUtils

logger = logging.getLogger(__name__)


class SystemInfoService:
    """Handles system information and capabilities checking"""
    
    def __init__(self, docker_ops: DockerOperations):
        self.docker_ops = docker_ops
        self._service_factory = create_default_service_factory()
        self._pool_service = None
    
    async def _get_pool_service(self) -> PoolService:
        """Get the pool service instance"""
        if self._pool_service is None:
            self._pool_service = await self._service_factory.create_pool_service()
        return self._pool_service
    
    async def get_system_info(self) -> Dict[str, Union[str, bool, None]]:
        """Get system information relevant to migrations"""
        # Basic system info
        info: Dict[str, Union[str, bool, None]] = {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "architecture": platform.architecture()[0]
        }

        # Check Docker status safely using Docker API
        try:
            version_info = self.docker_ops.client.version()
            info["docker_version"] = version_info.get('Version', 'unavailable')
        except Exception:
            info["docker_version"] = "unavailable"

        # Check ZFS status safely
        try:
            pool_service = await self._get_pool_service()
            pools_result = await pool_service.list_pools()
            zfs_available = pools_result.is_success
            info["zfs_available"] = zfs_available
            if zfs_available:
                info["zfs_version"] = await self._get_zfs_version()
            else:
                info["zfs_version"] = None
        except Exception:
            info["zfs_available"] = False
            info["zfs_version"] = None

        # Add feature flags
        info["docker_api_available"] = True  # We're using Docker API
        info["container_migration_supported"] = True
        info["legacy_compose_migration_supported"] = True

        return info
    
    async def get_zfs_status(self) -> Dict[str, Any]:
        """Get detailed ZFS status information"""
        try:
            pool_service = await self._get_pool_service()
            pools_result = await pool_service.list_pools()
            is_available = pools_result.is_success

            if not is_available:
                return {
                    "available": False,
                    "version": None,
                    "pools": []
                }

            # Get ZFS version
            version = await self._get_zfs_version()

            # Get pool list
            pools = [pool.name for pool in pools_result.value] if pools_result.is_success else []

            return {
                "available": True,
                "version": version,
                "pools": pools
            }
        except Exception as e:
            logger.error(f"Failed to get ZFS status: {e}")
            return {
                "available": False,
                "version": None,
                "pools": []
            }
    
    async def _get_zfs_version(self) -> str:
        """Get ZFS version"""
        try:
            # Use subprocess for version check since new services might not have this method
            import subprocess
            validated_cmd = SecurityUtils.validate_zfs_command_args("version")
            result = subprocess.run(validated_cmd, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout:
                # Extract version from first line
                first_line = result.stdout.strip().split('\n')[0]
                if 'zfs-' in first_line:
                    return first_line.split('zfs-')[1].split()[0]
                return "unknown"
            else:
                return "unknown"
        except Exception:
            return "unknown"
    
    async def _get_zfs_pools(self) -> List[str]:
        """Get list of ZFS pools"""
        try:
            pool_service = await self._get_pool_service()
            pools_result = await pool_service.list_pools()
            if pools_result.is_success:
                return [pool.name for pool in pools_result.value]
        except Exception:
            pass
        return []
    
    async def check_docker_status(self) -> Dict[str, Any]:
        """Check Docker daemon status and version"""
        try:
            # Test local Docker connection
            self.docker_ops.client.ping()
            version_info = self.docker_ops.client.version()
            
            return {
                "available": True,
                "version": version_info.get('Version', 'unknown'),
                "api_version": version_info.get('ApiVersion', 'unknown'),
                "platform": version_info.get('Platform', {}).get('Name', 'unknown')
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e),
                "version": None,
                "api_version": None,
                "platform": None
            }
    
    async def get_capabilities_summary(self) -> Dict[str, bool]:
        """Get a summary of system capabilities"""
        docker_status = await self.check_docker_status()
        zfs_status = await self.get_zfs_status()
        
        return {
            "docker_available": bool(docker_status["available"]),
            "zfs_available": bool(zfs_status["available"]),
            "container_migration": bool(docker_status["available"]),
            "snapshot_migration": bool(docker_status["available"]) and bool(zfs_status["available"]),
            "legacy_compose_migration": bool(docker_status["available"])
        }