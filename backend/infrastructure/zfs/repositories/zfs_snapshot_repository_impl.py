"""ZFS Snapshot Repository Implementation"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio
import json

from ....core.interfaces.zfs_repository import ZFSSnapshotRepository
from ....core.entities.zfs_entity import ZFSSnapshot
from ....core.value_objects.dataset_name import DatasetName
from ....core.value_objects.snapshot_name import SnapshotName
from ....core.value_objects.storage_size import StorageSize
from ....zfs_ops import ZFSOperations
import logging

logger = logging.getLogger(__name__)


class ZFSSnapshotRepositoryImpl(ZFSSnapshotRepository):
    """ZFS Snapshot repository implementation using existing ZFSOperations"""
    
    def __init__(self):
        self._zfs_ops = ZFSOperations()
    
    async def _run_zfs_command(self, *args: str) -> tuple[int, str, str]:
        """Internal helper that proxies to ZFSOperations.safe_run_zfs_command but returns a tuple."""
        return await self._zfs_ops.safe_run_zfs_command(*args)
    
    async def create(self, dataset_name: DatasetName, snapshot_name: str) -> ZFSSnapshot:
        """Create a snapshot"""
        try:
            full_snapshot_name = SnapshotName.create(dataset_name, snapshot_name)
            
            # Use existing ZFSOps method
            rc, stdout, stderr = await self._run_zfs_command("snapshot", str(full_snapshot_name))
            if rc != 0:
                raise Exception(f"Failed to create snapshot: {stderr}")
            
            # Get snapshot info
            snapshot = await self.find_by_name(full_snapshot_name)
            if not snapshot:
                # Create basic snapshot if not found
                snapshot = ZFSSnapshot(
                    name=full_snapshot_name,
                    created_at=datetime.now()
                )
            
            return snapshot
            
        except Exception as e:
            logger.error(f"Failed to create snapshot {dataset_name}@{snapshot_name}: {e}")
            raise
    
    async def find_by_name(self, name: SnapshotName) -> Optional[ZFSSnapshot]:
        """Find a snapshot by name"""
        try:
            # Use existing ZFSOps to get snapshot info
            rc, stdout, stderr = await self._run_zfs_command(
                "list", "-H", "-p", "-t", "snapshot", "-o", "name,creation,used,referenced", str(name)
            )
            if rc != 0:
                return None
            
            if not stdout.strip():
                return None
            
            # Parse output
            parts = stdout.strip().split('\t')
            if len(parts) >= 4:
                properties = {
                    'creation': parts[1],
                    'used': parts[2],
                    'referenced': parts[3]
                }
                
                # Convert creation timestamp
                created_at = datetime.fromtimestamp(int(parts[1]))
                
                return ZFSSnapshot(
                    name=name,
                    created_at=created_at,
                    properties=properties
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to find snapshot {name}: {e}")
            return None
    
    async def list_all(self) -> List[ZFSSnapshot]:
        """List all snapshots"""
        try:
            # Use existing ZFSOps method
            rc, stdout, stderr = await self._run_zfs_command(
                "list", "-H", "-p", "-t", "snapshot", "-o", "name,creation,used,referenced"
            )
            if rc != 0:
                return []
            
            snapshots = []
            for line in stdout.strip().split('\n'):
                if not line:
                    continue
                
                parts = line.split('\t')
                if len(parts) >= 4:
                    try:
                        name = SnapshotName(parts[0])
                        properties = {
                            'creation': parts[1],
                            'used': parts[2],
                            'referenced': parts[3]
                        }
                        
                        # Convert creation timestamp
                        created_at = datetime.fromtimestamp(int(parts[1]))
                        
                        snapshot = ZFSSnapshot(
                            name=name,
                            created_at=created_at,
                            properties=properties
                        )
                        snapshots.append(snapshot)
                    except Exception as e:
                        logger.warning(f"Failed to parse snapshot line: {line}, error: {e}")
                        continue
            
            return snapshots
            
        except Exception as e:
            logger.error(f"Failed to list snapshots: {e}")
            return []
    
    async def list_for_dataset(self, dataset_name: DatasetName) -> List[ZFSSnapshot]:
        """List snapshots for a specific dataset"""
        try:
            all_snapshots = await self.list_all()
            return [s for s in all_snapshots if s.dataset_name == dataset_name]
        except Exception as e:
            logger.error(f"Failed to list snapshots for dataset {dataset_name}: {e}")
            return []
    
    async def delete(self, name: SnapshotName) -> bool:
        """Delete a snapshot"""
        try:
            rc, stdout, stderr = await self._run_zfs_command("destroy", str(name))
            return rc == 0
            
        except Exception as e:
            logger.error(f"Failed to delete snapshot {name}: {e}")
            return False
    
    async def rollback(self, name: SnapshotName, force: bool = False) -> bool:
        """Rollback to a snapshot"""
        try:
            cmd = ["rollback"]
            if force:
                cmd.append("-r")  # Destroy newer snapshots
                cmd.append("-f")  # Force unmount/remount
            cmd.append(str(name))
            
            rc, stdout, stderr = await self._run_zfs_command(*cmd)
            return rc == 0
            
        except Exception as e:
            logger.error(f"Failed to rollback to snapshot {name}: {e}")
            return False
    
    async def clone(self, snapshot_name: SnapshotName, target_dataset: DatasetName) -> bool:
        """Clone a snapshot to create a new dataset"""
        try:
            rc, _, _ = await self._run_zfs_command("clone", str(snapshot_name), str(target_dataset))
            return rc == 0
            
        except Exception as e:
            logger.error(f"Failed to clone snapshot {snapshot_name}: {e}")
            return False
    
    async def send(self, snapshot_name: SnapshotName, target_host: str, target_dataset: DatasetName) -> bool:
        """Send snapshot to remote host"""
        try:
            # For localhost, use regular clone
            if target_host in ["localhost", "127.0.0.1"]:
                return await self.clone(snapshot_name, target_dataset)
            
            # For remote host, use SSH
            # This is a simplified version - in production you'd want more error handling
            send_cmd = f"zfs send {snapshot_name}"
            recv_cmd = f"ssh {target_host} 'zfs receive {target_dataset}'"
            full_cmd = f"{send_cmd} | {recv_cmd}"
            
            proc = await asyncio.create_subprocess_shell(
                full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                logger.error(f"Failed to send snapshot: {stderr.decode()}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send snapshot {snapshot_name} to {target_host}: {e}")
            return False
    
    async def exists(self, name: SnapshotName) -> bool:
        """Check if a snapshot exists"""
        try:
            snapshot = await self.find_by_name(name)
            return snapshot is not None
        except Exception as e:
            logger.error(f"Failed to check if snapshot {name} exists: {e}")
            return False
    
    async def get_properties(self, name: SnapshotName) -> Dict[str, str]:
        """Get all properties of a snapshot"""
        try:
            rc, stdout, stderr = await self._run_zfs_command("get", "-H", "-p", "all", str(name))
            if rc != 0:
                return {}
            
            properties = {}
            for line in stdout.strip().split('\n'):
                if not line:
                    continue
                
                parts = line.split('\t')
                if len(parts) >= 3:
                    prop_name = parts[1]
                    prop_value = parts[2]
                    properties[prop_name] = prop_value
            
            return properties
            
        except Exception as e:
            logger.error(f"Failed to get properties for snapshot {name}: {e}")
            return {}