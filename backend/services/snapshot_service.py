import asyncio
import logging
from datetime import datetime
from typing import List, Tuple, Optional
from ..models import VolumeMount, HostInfo
from ..zfs_operations.factories.service_factory import create_default_service_factory
from ..zfs_operations.services.snapshot_service import SnapshotService as NewSnapshotService
from ..zfs_operations.core.value_objects.dataset_name import DatasetName
from ..host_service import HostService
from ..security_utils import SecurityUtils

logger = logging.getLogger(__name__)


class SnapshotService:
    """Handles ZFS snapshot creation and management operations - Legacy wrapper for new service"""
    
    def __init__(self, host_service: HostService):
        self.host_service = host_service
        self._service_factory = create_default_service_factory()
        self._new_snapshot_service = None
    
    async def _get_new_service(self) -> NewSnapshotService:
        """Get the new snapshot service instance"""
        if self._new_snapshot_service is None:
            self._new_snapshot_service = await self._service_factory.create_snapshot_service()
        return self._new_snapshot_service
    
    def generate_timestamp(self) -> str:
        """Generate a timestamp for snapshot naming"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    async def _get_dataset_name_by_mountpoint(self, mountpoint: str, host_info: Optional[HostInfo] = None) -> Optional[str]:
        """Get ZFS dataset name by mountpoint using ZFS list command"""
        try:
            if host_info:
                # Remote command
                cmd = "zfs list -H -o name,mountpoint"
                returncode, stdout, stderr = await self.host_service.run_remote_command(host_info, cmd)
            else:
                # Local command - use SecurityUtils for command execution
                validated_cmd = SecurityUtils.validate_zfs_command_args("list", "-H", "-o", "name,mountpoint")
                # Use subprocess or similar for local execution
                import subprocess
                result = subprocess.run(validated_cmd, capture_output=True, text=True)
                returncode, stdout, stderr = result.returncode, result.stdout, result.stderr
            
            if returncode != 0:
                logger.warning(f"Failed to list ZFS datasets: {stderr}")
                return None
            
            # Parse output to find matching mountpoint
            for line in stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        dataset_name, mount_path = parts[0], parts[1]
                        if mount_path == mountpoint:
                            return dataset_name
            
            # If no exact match found, try fallback to string replacement
            if mountpoint.startswith('/mnt/'):
                return mountpoint[5:]  # Remove /mnt/ prefix
            
            return None
            
        except Exception as e:
            logger.warning(f"Error getting dataset name for {mountpoint}: {e}")
            # Fallback to string replacement
            if mountpoint.startswith('/mnt/'):
                return mountpoint[5:]
            return None
    
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
            dataset_name = await self._get_dataset_name_by_mountpoint(compose_dir, source_host_info)
            if not dataset_name:
                raise Exception(f"Could not determine dataset name for {compose_dir}")
            zfs_create_cmd = f"zfs create -p {SecurityUtils.escape_shell_argument(dataset_name)}"
            returncode, stdout, stderr = await self.host_service.run_remote_command(source_host_info, zfs_create_cmd)
            if returncode != 0:
                raise Exception(f"Failed to convert {compose_dir} to dataset: {stderr}")
        
        # Create snapshot for compose dataset
        dataset_name = await self._get_dataset_name_by_mountpoint(compose_dir, source_host_info)
        if not dataset_name:
            raise Exception(f"Could not determine dataset name for {compose_dir}")
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
                dataset_name = await self._get_dataset_name_by_mountpoint(volume.source, source_host_info)
                if not dataset_name:
                    logger.warning(f"Could not determine dataset name for {volume.source}, skipping...")
                    continue
                zfs_create_cmd = f"zfs create -p {SecurityUtils.escape_shell_argument(dataset_name)}"
                returncode, stdout, stderr = await self.host_service.run_remote_command(source_host_info, zfs_create_cmd)
                if returncode != 0:
                    logger.warning(f"Failed to convert {volume.source} to dataset, skipping...")
                    continue
            
            # Create snapshot for volume
            dataset_name = await self._get_dataset_name_by_mountpoint(volume.source, source_host_info)
            if not dataset_name:
                logger.warning(f"Could not determine dataset name for {volume.source}, skipping...")
                continue
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
        try:
            # Use new snapshot service
            new_service = await self._get_new_service()
            dataset_name = DatasetName.from_string(dataset)
            snapshot_name = f"migration_{timestamp}"
            
            result = await new_service.create_snapshot(dataset_name, snapshot_name)
            if result.is_success:
                return (result.value.full_name, dataset)
            else:
                logger.error(f"Failed to create snapshot for {dataset}: {result.error}")
                return ("", dataset)
        except Exception as e:
            logger.error(f"Failed to create snapshot for {dataset}: {e}")
            return ("", dataset)
    
    async def cleanup_snapshots(self, snapshot_names: List[str]):
        """Clean up multiple snapshots"""
        new_service = await self._get_new_service()
        
        for snapshot_name in snapshot_names:
            try:
                # Parse snapshot name to get dataset and snapshot parts
                if '@' in snapshot_name:
                    dataset_str, snap_name = snapshot_name.split('@', 1)
                    dataset_name = DatasetName.from_string(dataset_str)
                    result = await new_service.destroy_snapshot(dataset_name, snap_name, force=True)
                    if not result.is_success:
                        logger.warning(f"Failed to cleanup snapshot {snapshot_name}: {result.error}")
                else:
                    logger.warning(f"Invalid snapshot name format: {snapshot_name}")
            except Exception as e:
                logger.warning(f"Failed to cleanup snapshot {snapshot_name}: {e}")
    
    async def list_snapshots(self, dataset: Optional[str] = None) -> List[str]:
        """List available snapshots"""
        try:
            new_service = await self._get_new_service()
            
            if dataset:
                dataset_name = DatasetName.from_string(dataset)
                result = await new_service.list_snapshots(dataset_name)
            else:
                result = await new_service.list_snapshots(None)
            
            if result.is_success:
                return [snapshot.full_name for snapshot in result.value]
            else:
                logger.error(f"Failed to list snapshots: {result.error}")
                return []
                
        except Exception as e:
            logger.error(f"Error listing snapshots: {e}")
            return []
    
    async def snapshot_exists(self, snapshot_name: str) -> bool:
        """Check if a snapshot exists"""
        try:
            if '@' not in snapshot_name:
                return False
            
            dataset_str, snap_name = snapshot_name.split('@', 1)
            dataset_name = DatasetName.from_string(dataset_str)
            new_service = await self._get_new_service()
            
            result = await new_service.get_snapshot(dataset_name, snap_name)
            return result.is_success
        except Exception:
            return False