import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Tuple
from .security_utils import SecurityUtils, SecurityValidationError

logger = logging.getLogger(__name__)

class ZFSOperations:
    """ZFS operations with security validation and helper method to reduce duplication"""
    
    def __init__(self):
        pass
    
    async def run_command(self, cmd: List[str]) -> tuple[int, str, str]:
        """Execute a command and return result"""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            # Ensure returncode is never None by defaulting to 1 if it somehow is
            returncode = process.returncode if process.returncode is not None else 1
            return returncode, stdout.decode(), stderr.decode()
        except Exception as e:
            return 1, "", str(e)

    async def safe_run_zfs_command(self, *args: str) -> tuple[int, str, str]:
        """
        Safely validate and execute a ZFS command with security validation.
        
        This helper method reduces code duplication by combining:
        1. SecurityUtils.validate_zfs_command_args() validation
        2. self.run_command() execution 
        3. SecurityValidationError handling
        
        Args:
            *args: ZFS command arguments to validate and execute
            
        Returns:
            tuple: (returncode, stdout, stderr) - same as run_command()
                   Returns (1, "", "Security validation failed") on validation error
        """
        try:
            cmd = SecurityUtils.validate_zfs_command_args(*args)
            return await self.run_command(cmd)
        except SecurityValidationError:
            return 1, "", "Security validation failed"

    async def dataset_exists(self, dataset_name: str) -> bool:
        """Check if a ZFS dataset exists"""
        returncode, _, _ = await self.safe_run_zfs_command("list", "-H", dataset_name)
        return returncode == 0

    async def list_datasets(self, pool_name: Optional[str] = None) -> List[str]:
        """List ZFS datasets"""
        if pool_name:
            pool_name = SecurityUtils.validate_dataset_name(pool_name)
            returncode, stdout, stderr = await self.safe_run_zfs_command("list", "-H", "-o", "name", pool_name)
        else:
            returncode, stdout, stderr = await self.safe_run_zfs_command("list", "-H", "-o", "name")
            
        if returncode == 0:
            return [line.strip() for line in stdout.split('\n') if line.strip()]
        return []

    async def is_dataset(self, path: str) -> bool:
        """Check if a path is a ZFS dataset"""
        dataset_name = await self.get_dataset_name(path)
        
        returncode, _, _ = await self.safe_run_zfs_command("list", "-H", dataset_name)
        return returncode == 0
    
    async def get_dataset_name(self, path: str) -> str:
        """Convert path to ZFS dataset name"""
        if path.startswith("/mnt/"):
            return path[5:]  # Remove /mnt/ prefix
        return path
    
    async def create_dataset(self, path: str) -> bool:
        """Create a ZFS dataset from a directory"""
        dataset_name = await self.get_dataset_name(path)
        
        # Check if already a dataset
        if await self.is_dataset(path):
            logger.info(f"Path {path} is already a dataset")
            return True
        
        # Move existing data to temporary location
        temp_path = f"{path}.tmp"
        returncode, _, stderr = await self.run_command(["mv", path, temp_path])
        if returncode != 0:
            logger.error(f"Failed to move {path} to {temp_path}: {stderr}")
            return False
        
        # Create the dataset
        returncode, _, stderr = await self.safe_run_zfs_command("create", dataset_name)
        if returncode != 0:
            logger.error(f"Failed to create dataset {dataset_name}: {stderr}")
            # Restore original directory
            await self.run_command(["mv", temp_path, path])
            return False
        
        # Move data back
        returncode, _, stderr = await self.run_command(["cp", "-a", f"{temp_path}/.", path])
        if returncode != 0:
            logger.error(f"Failed to copy data back to {path}: {stderr}")
            return False
        
        # Remove temp directory
        await self.run_command(["rm", "-rf", temp_path])
        
        logger.info(f"Successfully converted {path} to dataset {dataset_name}")
        return True
    
    async def create_snapshot(self, dataset_path: str, snapshot_name: Optional[str] = None) -> str:
        """Create a snapshot of a dataset"""
        dataset_name = await self.get_dataset_name(dataset_path)
        
        if not snapshot_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_name = f"transdock_{timestamp}"
        
        full_snapshot_name = f"{dataset_name}@{snapshot_name}"
        
        returncode, _, stderr = await self.safe_run_zfs_command("snapshot", full_snapshot_name)
        if returncode != 0:
            raise Exception(f"Failed to create snapshot {full_snapshot_name}: {stderr}")
        
        logger.info(f"Created snapshot: {full_snapshot_name}")
        return full_snapshot_name
    
    async def list_snapshots(self, dataset_path: str) -> List[str]:
        """List all snapshots for a dataset"""
        dataset_name = await self.get_dataset_name(dataset_path)
        
        returncode, stdout, stderr = await self.safe_run_zfs_command(
            "list", "-H", "-t", "snapshot", "-o", "name", "-s", "creation", dataset_name
        )
        
        if returncode != 0:
            logger.error(f"Failed to list snapshots for {dataset_name}: {stderr}")
            return []
        
        snapshots = [line.strip() for line in stdout.split('\n') if line.strip()]
        return snapshots
    
    async def send_snapshot(self, snapshot_name: str, target_host: str, target_dataset: str, 
                           ssh_user: str = "root", ssh_port: int = 22) -> bool:
        """Send a snapshot to a remote ZFS system"""
        logger.info(f"Sending snapshot {snapshot_name} to {target_host}:{target_dataset}")
        
        # Validate inputs to prevent command injection
        try:
            SecurityUtils.validate_hostname(target_host)
            SecurityUtils.validate_username(ssh_user)
            SecurityUtils.validate_port(ssh_port)
            SecurityUtils.validate_dataset_name(target_dataset)
            
            # Validate snapshot name format
            if '@' not in snapshot_name or len(snapshot_name) > 256:
                raise SecurityValidationError(f"Invalid snapshot name: {snapshot_name}")
        except SecurityValidationError as e:
            logger.error(f"Security validation failed: {e}")
            return False
        
        # Build secure command with proper escaping
        zfs_send_cmd = SecurityUtils.validate_zfs_command_args("send", snapshot_name)
        zfs_receive_cmd = SecurityUtils.validate_zfs_command_args("receive", target_dataset)
        
        # Create secure ssh command for the receive part
        receive_cmd_str = " ".join(zfs_receive_cmd)
        ssh_cmd = SecurityUtils.build_ssh_command(target_host, ssh_user, ssh_port, receive_cmd_str)
        
        # Build the pipeline command safely
        cmd = [
            "sh", "-c",
            f"{' '.join(zfs_send_cmd)} | {' '.join(ssh_cmd)}"
        ]
        
        returncode, stdout, stderr = await self.run_command(cmd)
        
        if returncode != 0:
            logger.error(f"Failed to send snapshot {snapshot_name}: {stderr}")
            return False
        
        logger.info(f"Successfully sent snapshot {snapshot_name} to {target_host}")
        return True
    
    async def mount_snapshot(self, snapshot_name: str, mount_point: str) -> bool:
        """Mount a snapshot to a temporary location"""
        returncode, _, stderr = await self.run_command(["mkdir", "-p", mount_point])
        if returncode != 0:
            logger.error(f"Failed to create mount point {mount_point}: {stderr}")
            return False
        
        # Clone the snapshot to make it writable
        clone_name = f"{snapshot_name.split('@')[0]}_clone_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        returncode, _, stderr = await self.safe_run_zfs_command("clone", snapshot_name, clone_name)
        if returncode != 0:
            logger.error(f"Failed to clone snapshot {snapshot_name}: {stderr}")
            return False
        
        # Set mountpoint
        returncode, _, stderr = await self.safe_run_zfs_command("set", f"mountpoint={mount_point}", clone_name)
        if returncode != 0:
            logger.error(f"Failed to set mountpoint for {clone_name}: {stderr}")
            await self.safe_run_zfs_command("destroy", clone_name)
            return False
        
        logger.info(f"Mounted snapshot {snapshot_name} at {mount_point} via clone {clone_name}")
        return True
    
    async def cleanup_snapshot(self, snapshot_name: str) -> bool:
        """Clean up a snapshot"""
        returncode, _, stderr = await self.safe_run_zfs_command("destroy", snapshot_name)
        if returncode != 0:
            logger.error(f"Failed to destroy snapshot {snapshot_name}: {stderr}")
            return False
        
        logger.info(f"Cleaned up snapshot: {snapshot_name}")
        return True
    
    async def check_remote_zfs(self, target_host: str, ssh_user: str = "root", ssh_port: int = 22) -> bool:
        """Check if the target host has ZFS available"""
        try:
            cmd = SecurityUtils.build_ssh_command(target_host, ssh_user, ssh_port, "which zfs")
            returncode, _, _ = await self.run_command(cmd)
            return returncode == 0
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for remote ZFS check: {e}")
            return False

    async def is_zfs_available(self) -> bool:
        """Check if ZFS is available on the system"""
        returncode, _, _ = await self.run_command(["which", "zfs"])
        return returncode == 0
