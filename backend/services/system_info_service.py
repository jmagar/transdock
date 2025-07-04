import platform
import subprocess
import logging
from typing import Dict, Any, Union
from ..zfs_ops import ZFSOperations
from ..docker_ops import DockerOperations
from ..security_utils import SecurityUtils

logger = logging.getLogger(__name__)


class SystemInfoService:
    """Handles system information and capabilities checking"""
    
    def __init__(self, zfs_ops: ZFSOperations, docker_ops: DockerOperations):
        self.zfs_ops = zfs_ops
        self.docker_ops = docker_ops
    
    async def get_system_info(self) -> Dict[str, Union[str, bool, None]]:
        """Get system information relevant to migrations"""
        # Basic system info
        info: Dict[str, Union[str, bool, None]] = {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "architecture": platform.architecture()[0]
        }

        # Check Docker status safely
        try:
            result = subprocess.run(["docker",
                                     "version",
                                     "--format",
                                     "{{.Server.Version}}"],
                                    capture_output=True,
                                    text=True,
                                    timeout=10)
            if result.returncode == 0:
                info["docker_version"] = result.stdout.strip()
            else:
                info["docker_version"] = "unavailable"
        except Exception:
            info["docker_version"] = "unavailable"

        # Check ZFS status safely
        try:
            zfs_available = await self.zfs_ops.is_zfs_available()
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
            is_available = await self.zfs_ops.is_zfs_available()

            if not is_available:
                return {
                    "available": False,
                    "version": None,
                    "pools": []
                }

            # Get ZFS version
            version = await self._get_zfs_version()

            # Get pool list
            pools = await self._get_zfs_pools()

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
            validated_cmd = SecurityUtils.validate_zfs_command_args("version")
            returncode, stdout, stderr = await self.zfs_ops.run_command(validated_cmd)
            if returncode == 0 and stdout:
                # Extract version from first line
                first_line = stdout.strip().split('\n')[0]
                if 'zfs-' in first_line:
                    return first_line.split('zfs-')[1].split()[0]
                else:
                    return "unknown"
            else:
                return "unknown"
        except Exception:
            return "unknown"
    
    async def _get_zfs_pools(self) -> list[str]:
        """Get list of ZFS pools"""
        try:
            validated_cmd = SecurityUtils.validate_zfs_command_args(
                "list", "-H", "-o", "name", "-t", "filesystem")
            returncode, stdout, stderr = await self.zfs_ops.run_command(validated_cmd)
            if returncode == 0:
                pools = []
                for line in stdout.strip().split('\n'):
                    if line.strip() and '/' not in line:  # Only root pools
                        pools.append(line.strip())
                return pools
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