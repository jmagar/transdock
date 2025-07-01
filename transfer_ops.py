import logging
import os
from typing import List, Dict, Tuple, Optional
import asyncio
from models import VolumeMount, TransferMethod

logger = logging.getLogger(__name__)

class TransferOperations:
    def __init__(self):
        self.temp_mount_base = "/tmp/transdock_mounts"
    
    async def run_command(self, cmd: List[str], cwd: Optional[str] = None) -> Tuple[int, str, str]:
        """Run a command asynchronously"""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            stdout, stderr = await process.communicate()
            return process.returncode, stdout.decode(), stderr.decode()
        except Exception as e:
            logger.error(f"Command failed: {' '.join(cmd)} - {e}")
            return 1, "", str(e)
    
    async def create_target_directories(self, target_host: str, directories: List[str],
                                       ssh_user: str = "root", ssh_port: int = 22) -> bool:
        """Create target directories on remote host"""
        for directory in directories:
            cmd = [
                "ssh", "-p", str(ssh_port), f"{ssh_user}@{target_host}",
                f"mkdir -p {directory}"
            ]
            
            returncode, _, stderr = await self.run_command(cmd)
            if returncode != 0:
                logger.error(f"Failed to create directory {directory} on {target_host}: {stderr}")
                return False
        
        logger.info(f"Created {len(directories)} directories on {target_host}")
        return True
    
    async def transfer_via_zfs_send(self, snapshot_name: str, target_host: str, 
                                   target_dataset: str, ssh_user: str = "root", 
                                   ssh_port: int = 22) -> bool:
        """Transfer data using ZFS send/receive"""
        logger.info(f"Transferring {snapshot_name} via ZFS send to {target_host}:{target_dataset}")
        
        # Create parent dataset on target if it doesn't exist
        parent_dataset = "/".join(target_dataset.split("/")[:-1])
        if parent_dataset:
            create_cmd = [
                "ssh", "-p", str(ssh_port), f"{ssh_user}@{target_host}",
                f"zfs create -p {parent_dataset} 2>/dev/null || true"
            ]
            await self.run_command(create_cmd)
        
        # Send the snapshot
        cmd = [
            "sh", "-c",
            f"zfs send {snapshot_name} | ssh -p {ssh_port} {ssh_user}@{target_host} 'zfs receive {target_dataset}'"
        ]
        
        returncode, stdout, stderr = await self.run_command(cmd)
        
        if returncode != 0:
            logger.error(f"ZFS send failed for {snapshot_name}: {stderr}")
            return False
        
        logger.info(f"Successfully transferred {snapshot_name} via ZFS send")
        return True
    
    async def transfer_via_rsync(self, source_path: str, target_host: str, 
                                target_path: str, ssh_user: str = "root", 
                                ssh_port: int = 22) -> bool:
        """Transfer data using rsync"""
        logger.info(f"Transferring {source_path} via rsync to {target_host}:{target_path}")
        
        # Ensure target directory exists
        parent_dir = os.path.dirname(target_path)
        if parent_dir:
            await self.create_target_directories(target_host, [parent_dir], ssh_user, ssh_port)
        
        cmd = [
            "rsync", "-avzP", "--delete",
            "-e", f"ssh -p {ssh_port}",
            f"{source_path}/",
            f"{ssh_user}@{target_host}:{target_path}/"
        ]
        
        returncode, stdout, stderr = await self.run_command(cmd)
        
        if returncode != 0:
            logger.error(f"rsync failed for {source_path}: {stderr}")
            return False
        
        logger.info(f"Successfully transferred {source_path} via rsync")
        return True
    
    async def mount_snapshot_for_rsync(self, snapshot_name: str) -> Optional[str]:
        """Mount a ZFS snapshot for rsync transfer"""
        mount_point = f"{self.temp_mount_base}/{snapshot_name.replace('/', '_').replace('@', '_')}"
        
        # Create mount point
        returncode, _, stderr = await self.run_command(["mkdir", "-p", mount_point])
        if returncode != 0:
            logger.error(f"Failed to create mount point {mount_point}: {stderr}")
            return None
        
        # Clone the snapshot to make it accessible
        clone_name = f"{snapshot_name.split('@')[0]}_rsync_clone"
        
        # Remove existing clone if it exists
        await self.run_command(["zfs", "destroy", clone_name])
        
        returncode, _, stderr = await self.run_command(["zfs", "clone", snapshot_name, clone_name])
        if returncode != 0:
            logger.error(f"Failed to clone snapshot {snapshot_name}: {stderr}")
            return None
        
        # Set mountpoint
        returncode, _, stderr = await self.run_command(["zfs", "set", f"mountpoint={mount_point}", clone_name])
        if returncode != 0:
            logger.error(f"Failed to set mountpoint for {clone_name}: {stderr}")
            await self.run_command(["zfs", "destroy", clone_name])
            return None
        
        logger.info(f"Mounted snapshot {snapshot_name} at {mount_point}")
        return mount_point
    
    async def cleanup_rsync_mount(self, mount_point: str, snapshot_name: str) -> bool:
        """Clean up temporary mount used for rsync"""
        clone_name = f"{snapshot_name.split('@')[0]}_rsync_clone"
        
        # Destroy the clone
        returncode, _, stderr = await self.run_command(["zfs", "destroy", clone_name])
        if returncode != 0:
            logger.error(f"Failed to destroy clone {clone_name}: {stderr}")
            return False
        
        # Remove mount point
        await self.run_command(["rm", "-rf", mount_point])
        
        logger.info(f"Cleaned up rsync mount {mount_point}")
        return True
    
    async def transfer_volume_data(self, volume: VolumeMount, snapshot_name: str,
                                  target_host: str, target_path: str, 
                                  transfer_method: TransferMethod,
                                  ssh_user: str = "root", ssh_port: int = 22) -> bool:
        """Transfer data for a single volume mount"""
        if transfer_method == TransferMethod.ZFS_SEND:
            # For ZFS send, we need to determine the target dataset name
            # Convert target path to dataset format
            if target_path.startswith("/mnt/"):
                target_dataset = target_path[5:]  # Remove /mnt/ prefix
            else:
                target_dataset = f"zpool{target_path}"  # Assume default zpool
            
            return await self.transfer_via_zfs_send(
                snapshot_name, target_host, target_dataset, ssh_user, ssh_port
            )
        
        else:  # RSYNC
            # Mount the snapshot and rsync
            mount_point = await self.mount_snapshot_for_rsync(snapshot_name)
            if not mount_point:
                return False
            
            try:
                success = await self.transfer_via_rsync(
                    mount_point, target_host, target_path, ssh_user, ssh_port
                )
                return success
            finally:
                await self.cleanup_rsync_mount(mount_point, snapshot_name)
    
    async def create_volume_mapping(self, volumes: List[VolumeMount], 
                                   target_base_path: str) -> Dict[str, str]:
        """Create mapping from old paths to new paths"""
        volume_mapping = {}
        
        for volume in volumes:
            # Extract the relative path from the source
            if volume.source.startswith("/mnt/cache/appdata/"):
                relative_path = volume.source[19:]  # Remove "/mnt/cache/appdata/"
                new_path = f"{target_base_path}/appdata/{relative_path}"
            elif volume.source.startswith("/mnt/cache/compose/"):
                relative_path = volume.source[19:]  # Remove "/mnt/cache/compose/"
                new_path = f"{target_base_path}/compose/{relative_path}"
            else:
                # Handle other paths
                relative_path = os.path.basename(volume.source)
                new_path = f"{target_base_path}/data/{relative_path}"
            
            volume_mapping[volume.source] = new_path
        
        return volume_mapping
    
    async def verify_transfer(self, source_path: str, target_host: str, 
                             target_path: str, ssh_user: str = "root", 
                             ssh_port: int = 22) -> bool:
        """Verify that the transfer was successful by comparing file counts"""
        try:
            # Count files in source
            returncode, stdout, _ = await self.run_command([
                "find", source_path, "-type", "f", "|", "wc", "-l"
            ])
            if returncode != 0:
                return False
            source_count = int(stdout.strip())
            
            # Count files in target
            returncode, stdout, _ = await self.run_command([
                "ssh", "-p", str(ssh_port), f"{ssh_user}@{target_host}",
                f"find {target_path} -type f | wc -l"
            ])
            if returncode != 0:
                return False
            target_count = int(stdout.strip())
            
            logger.info(f"Transfer verification: source={source_count}, target={target_count}")
            return source_count == target_count
        
        except Exception as e:
            logger.error(f"Transfer verification failed: {e}")
            return False 