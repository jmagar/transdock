import asyncio
import logging
from datetime import datetime
from typing import List, Tuple, Optional
from ..models import VolumeMount, HostInfo
from ..zfs_ops import ZFSOperations
from ..host_service import HostService
from ..security_utils import SecurityUtils

logger = logging.getLogger(__name__)


class SnapshotService:
    """Handles ZFS snapshot creation and management operations"""
    
    def __init__(self, zfs_ops: ZFSOperations, host_service: HostService):
        self.zfs_ops = zfs_ops
        self.host_service = host_service
    
    def generate_timestamp(self) -> str:
        """Generate a timestamp for snapshot naming"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    async def create_local_snapshots(self, compose_dir: str, volumes: List[VolumeMount], 
                                   timestamp: Optional[str] = None) -> List[Tuple[str, str]]:
        """Create ZFS snapshots for all local volumes"""
        if timestamp is None:
            timestamp = self.generate_timestamp()
            
        snapshot_tasks = []
        for volume in volumes:
            snapshot_tasks.append(
                self._create_snapshot_for_volume(volume, timestamp)
            )
        
        results = await asyncio.gather(*snapshot_tasks)
        
        # Check for failures
        failed_snapshots = [result for result in results if not result[0]]
        if failed_snapshots:
            raise Exception(f"Failed to create {len(failed_snapshots)} snapshots")
        
        return results
    
    async def create_remote_snapshots(self, source_host_info: HostInfo, compose_dir: str, 
                                    volumes: List[VolumeMount], timestamp: Optional[str] = None) -> List[Tuple[str, str]]:
        """Create ZFS snapshots on remote host"""
        if timestamp is None:
            timestamp = self.generate_timestamp()
            
        snapshots = []
        
        # Check if compose directory is a dataset, convert if not
        zfs_list_cmd = f"zfs list -H {SecurityUtils.escape_shell_argument(compose_dir)} 2>/dev/null"
        returncode, stdout, stderr = await self.host_service.run_remote_command(source_host_info, zfs_list_cmd)
        
        if returncode != 0:
            # Try to create dataset
            dataset_name = compose_dir.replace('/mnt/', '')
            zfs_create_cmd = f"zfs create -p {SecurityUtils.escape_shell_argument(dataset_name)}"
            returncode, stdout, stderr = await self.host_service.run_remote_command(source_host_info, zfs_create_cmd)
            if returncode != 0:
                raise Exception(f"Failed to convert {compose_dir} to dataset: {stderr}")
        
        # Create snapshot for compose dataset
        dataset_name = compose_dir.replace('/mnt/', '')
        snapshot_name = f"{dataset_name}@migration_{timestamp}"
        zfs_snapshot_cmd = f"zfs snapshot {SecurityUtils.escape_shell_argument(snapshot_name)}"
        returncode, stdout, stderr = await self.host_service.run_remote_command(source_host_info, zfs_snapshot_cmd)
        
        if returncode != 0:
            raise Exception(f"Failed to create snapshot for {compose_dir}: {stderr}")
        
        snapshots.append((snapshot_name, compose_dir))
        
        # Process each volume mount
        for volume in volumes:
            # Check if volume source is a dataset
            zfs_list_cmd = f"zfs list -H {SecurityUtils.escape_shell_argument(volume.source)} 2>/dev/null"
            returncode, stdout, stderr = await self.host_service.run_remote_command(source_host_info, zfs_list_cmd)
            
            if returncode != 0:
                # Try to create dataset
                dataset_name = volume.source.replace('/mnt/', '')
                zfs_create_cmd = f"zfs create -p {SecurityUtils.escape_shell_argument(dataset_name)}"
                returncode, stdout, stderr = await self.host_service.run_remote_command(source_host_info, zfs_create_cmd)
                if returncode != 0:
                    logger.warning(f"Failed to convert {volume.source} to dataset, skipping...")
                    continue
            
            # Create snapshot for volume
            dataset_name = volume.source.replace('/mnt/', '')
            snapshot_name = f"{dataset_name}@migration_{timestamp}"
            zfs_snapshot_cmd = f"zfs snapshot {SecurityUtils.escape_shell_argument(snapshot_name)}"
            returncode, stdout, stderr = await self.host_service.run_remote_command(source_host_info, zfs_snapshot_cmd)
            
            if returncode != 0:
                logger.warning(f"Failed to create snapshot for {volume.source}: {stderr}")
                continue
                
            snapshots.append((snapshot_name, volume.source))
            volume.is_dataset = True
            volume.dataset_path = dataset_name
        
        return snapshots
    
    async def _create_snapshot_for_volume(self, volume: VolumeMount, timestamp: str) -> Tuple[str, str]:
        """Create a snapshot for a single volume"""
        dataset = volume.source
        snapshot_name = f"{dataset}@{timestamp}"
        success = await self.zfs_ops.create_snapshot(dataset, snapshot_name)
        if not success:
            logger.error(f"Failed to create snapshot for {dataset}")
            return ("", dataset)  # Return empty snapshot name to indicate failure
        return (snapshot_name, dataset)
    
    async def cleanup_snapshots(self, snapshot_names: List[str]):
        """Clean up multiple snapshots"""
        cleanup_tasks = []
        for snapshot_name in snapshot_names:
            cleanup_tasks.append(self.zfs_ops.cleanup_snapshot(snapshot_name))
        
        results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        # Log any cleanup failures but don't raise
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to cleanup snapshot {snapshot_names[i]}: {result}")
    
    async def list_snapshots(self, dataset: str = None) -> List[str]:
        """List available snapshots"""
        try:
            if dataset:
                # List snapshots for specific dataset
                validated_cmd = SecurityUtils.validate_zfs_command_args(
                    "list", "-t", "snapshot", "-H", "-o", "name", dataset
                )
            else:
                # List all snapshots
                validated_cmd = SecurityUtils.validate_zfs_command_args(
                    "list", "-t", "snapshot", "-H", "-o", "name"
                )
            
            returncode, stdout, stderr = await self.zfs_ops.run_command(validated_cmd)
            if returncode == 0:
                return [line.strip() for line in stdout.strip().split('\n') if line.strip()]
            else:
                logger.error(f"Failed to list snapshots: {stderr}")
                return []
                
        except Exception as e:
            logger.error(f"Error listing snapshots: {e}")
            return []
    
    async def snapshot_exists(self, snapshot_name: str) -> bool:
        """Check if a snapshot exists"""
        try:
            validated_cmd = SecurityUtils.validate_zfs_command_args(
                "list", "-t", "snapshot", "-H", snapshot_name
            )
            returncode, stdout, stderr = await self.zfs_ops.run_command(validated_cmd)
            return returncode == 0
        except Exception:
            return False