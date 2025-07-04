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
            if not args:
                raise SecurityValidationError("No ZFS command provided")
            
            # First argument is the command, rest are arguments
            command = args[0]
            command_args = args[1:] if len(args) > 1 else []
            
            cmd = SecurityUtils.validate_zfs_command_args(command, *command_args)
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
        
        # Handle target dataset - check if exists and prepare for overwrite
        dataset_exists = False
        dataset_mount_path = None
        
        try:
            logger.info(f"Checking if target dataset {target_dataset} exists on {target_host}")
            
            # Check if target dataset exists
            check_cmd = SecurityUtils.validate_zfs_command_args("list", "-H", target_dataset)
            check_cmd_str = " ".join(check_cmd)
            check_ssh_cmd = SecurityUtils.build_ssh_command(target_host, ssh_user, ssh_port, check_cmd_str)
            
            returncode, stdout, stderr = await self.run_command(check_ssh_cmd)
            if returncode == 0:
                dataset_exists = True
                logger.info(f"Target dataset {target_dataset} exists")
                
                # Get the actual mount path using zfs get mountpoint
                get_mountpoint_cmd = SecurityUtils.validate_zfs_command_args("get", "-H", "-o", "value", "mountpoint", target_dataset)
                get_mountpoint_cmd_str = " ".join(get_mountpoint_cmd)
                mountpoint_ssh_cmd = SecurityUtils.build_ssh_command(target_host, ssh_user, ssh_port, get_mountpoint_cmd_str)
                
                mp_returncode, mp_stdout, mp_stderr = await self.run_command(mountpoint_ssh_cmd)
                if mp_returncode == 0 and mp_stdout.strip():
                    dataset_mount_path = mp_stdout.strip()
                    if dataset_mount_path == "none" or dataset_mount_path == "-":
                        logger.info(f"Target dataset {target_dataset} is not mounted")
                        dataset_mount_path = None
                    else:
                        logger.info(f"Target dataset {target_dataset} is mounted at {dataset_mount_path}")
                        
                        # Try to force unmount the dataset if it's busy
                        logger.info(f"Attempting to force unmount {dataset_mount_path} to prevent busy errors")
                        unmount_success = await self.force_unmount_dataset(
                            target_host, dataset_mount_path, ssh_user, ssh_port
                        )
                        if unmount_success:
                            logger.info(f"Successfully prepared {target_dataset} for overwrite")
                        else:
                            logger.warning(f"Could not force unmount {dataset_mount_path}, will try -F flag anyway")
                else:
                    logger.warning(f"Could not get mountpoint for {target_dataset}: {mp_stderr}")
                    dataset_mount_path = None
            else:
                logger.info(f"Target dataset {target_dataset} does not exist")
                
            # Ensure parent datasets exist
            parent_dataset = "/".join(target_dataset.split("/")[:-1])
            if parent_dataset:
                logger.info(f"Ensuring parent dataset {parent_dataset} exists on {target_host}")
                parent_create_cmd = SecurityUtils.validate_zfs_command_args("create", "-p", parent_dataset)
                parent_create_cmd_str = " ".join(parent_create_cmd)
                parent_ssh_cmd = SecurityUtils.build_ssh_command(target_host, ssh_user, ssh_port, parent_create_cmd_str)
                
                parent_returncode, parent_stdout, parent_stderr = await self.run_command(parent_ssh_cmd)
                if parent_returncode != 0:
                    logger.warning(f"Failed to create parent dataset {parent_dataset}: {parent_stderr}")
                    # Continue anyway
                    
        except SecurityValidationError as e:
            logger.warning(f"Failed to validate target dataset management commands: {e}")
            # Continue anyway
        
        # Build secure command with proper escaping
        zfs_send_cmd = SecurityUtils.validate_zfs_command_args("send", snapshot_name)
        
        # Use -F flag to overwrite existing dataset if it exists
        if dataset_exists:
            zfs_receive_cmd = SecurityUtils.validate_zfs_command_args("receive", "-F", target_dataset)
            logger.info(f"Using -F flag to overwrite existing dataset {target_dataset}")
        else:
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
    
    async def safe_run_system_command(self, *args: str) -> tuple[int, str, str]:
        """
        Safely validate and execute a system command with security validation.
        
        Args:
            *args: System command arguments to validate and execute
            
        Returns:
            tuple: (returncode, stdout, stderr) - same as run_command()
                   Returns (1, "", "Security validation failed") on validation error
        """
        try:
            if not args:
                raise SecurityValidationError("No system command provided")
            
            # First argument is the command, rest are arguments
            command = args[0]
            command_args = args[1:] if len(args) > 1 else []
            
            cmd = SecurityUtils.validate_system_command_args(command, *command_args)
            return await self.run_command(cmd)
        except SecurityValidationError:
            return 1, "", "Security validation failed"
    
    async def force_unmount_dataset(self, target_host: str, dataset_path: str, 
                                   ssh_user: str = "root", ssh_port: int = 22) -> bool:
        """
        Forcefully unmount a busy dataset on remote host by killing processes using it.
        
        Args:
            target_host: Remote host hostname
            dataset_path: Path to the dataset mount point (e.g., /mnt/backup/compose/simple-web)
            ssh_user: SSH username
            ssh_port: SSH port
            
        Returns:
            bool: True if successfully unmounted, False otherwise
        """
        try:
            # Validate inputs
            SecurityUtils.validate_hostname(target_host)
            SecurityUtils.validate_username(ssh_user)
            SecurityUtils.validate_port(ssh_port)
            dataset_path = SecurityUtils.sanitize_path(dataset_path, allow_absolute=True)
            
            logger.info(f"Attempting to force unmount {dataset_path} on {target_host}")
            
            # Step 1: Check if the path is actually mounted
            mountpoint_cmd = SecurityUtils.validate_system_command_args("mountpoint", dataset_path)
            mountpoint_cmd_str = " ".join(mountpoint_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(target_host, ssh_user, ssh_port, mountpoint_cmd_str)
            
            returncode, stdout, stderr = await self.run_command(ssh_cmd)
            if returncode != 0:
                logger.info(f"Path {dataset_path} is not mounted on {target_host}")
                return True  # Not mounted, so unmount "succeeded"
            
            # Step 2: Use lsof to find processes with open files in the dataset
            logger.info(f"Finding processes with open files in {dataset_path}")
            lsof_cmd = SecurityUtils.validate_system_command_args("lsof", "+D", dataset_path)
            lsof_cmd_str = " ".join(lsof_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(target_host, ssh_user, ssh_port, lsof_cmd_str)
            
            returncode, lsof_stdout, lsof_stderr = await self.run_command(ssh_cmd)
            if returncode == 0 and lsof_stdout.strip():
                logger.warning(f"Found processes with open files in {dataset_path}:")
                logger.warning(lsof_stdout.strip())
            
            # Step 3: Use fuser to find processes using the dataset
            logger.info(f"Finding processes using {dataset_path} on {target_host}")
            fuser_cmd = SecurityUtils.validate_system_command_args("fuser", "-mv", dataset_path)
            fuser_cmd_str = " ".join(fuser_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(target_host, ssh_user, ssh_port, fuser_cmd_str)
            
            returncode, fuser_stdout, fuser_stderr = await self.run_command(ssh_cmd)
            if returncode == 0 and fuser_stdout.strip():
                logger.warning(f"Found processes using {dataset_path}: {fuser_stdout.strip()}")
                
                # Step 4: Kill processes using the dataset (SIGTERM first)
                logger.info(f"Attempting to kill processes using {dataset_path} with SIGTERM")
                fuser_kill_cmd = SecurityUtils.validate_system_command_args("fuser", "-km", dataset_path)
                fuser_kill_cmd_str = " ".join(fuser_kill_cmd)
                ssh_cmd = SecurityUtils.build_ssh_command(target_host, ssh_user, ssh_port, fuser_kill_cmd_str)
                
                await self.run_command(ssh_cmd)
                
                # Wait a moment for processes to exit
                logger.info("Waiting for processes to exit gracefully...")
                await asyncio.sleep(3)
                
                # Step 5: Check if any processes are still there
                returncode, fuser_stdout, _ = await self.run_command(ssh_cmd)
                if returncode == 0 and fuser_stdout.strip():
                    logger.warning(f"Some processes still using {dataset_path}, using SIGKILL")
                    fuser_kill9_cmd = SecurityUtils.validate_system_command_args("fuser", "-9km", dataset_path)
                    fuser_kill9_cmd_str = " ".join(fuser_kill9_cmd)
                    ssh_cmd = SecurityUtils.build_ssh_command(target_host, ssh_user, ssh_port, fuser_kill9_cmd_str)
                    
                    await self.run_command(ssh_cmd)
                    
                    # Wait for cleanup
                    await asyncio.sleep(2)
            
            # Step 6: Try to unmount gracefully first
            logger.info(f"Attempting graceful unmount of {dataset_path}")
            umount_cmd = SecurityUtils.validate_system_command_args("umount", dataset_path)
            umount_cmd_str = " ".join(umount_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(target_host, ssh_user, ssh_port, umount_cmd_str)
            
            returncode, stdout, stderr = await self.run_command(ssh_cmd)
            if returncode == 0:
                logger.info(f"Successfully unmounted {dataset_path} on {target_host}")
                return True
            
            # Step 7: Try force unmount
            logger.info(f"Graceful unmount failed, attempting force unmount of {dataset_path}")
            umount_force_cmd = SecurityUtils.validate_system_command_args("umount", "-f", dataset_path)
            umount_force_cmd_str = " ".join(umount_force_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(target_host, ssh_user, ssh_port, umount_force_cmd_str)
            
            returncode, stdout, stderr = await self.run_command(ssh_cmd)
            if returncode == 0:
                logger.info(f"Successfully force unmounted {dataset_path} on {target_host}")
                return True
            
            # Step 8: Last resort - lazy unmount
            logger.warning(f"Force unmount failed, trying lazy unmount of {dataset_path}")
            umount_lazy_cmd = SecurityUtils.validate_system_command_args("umount", "-l", dataset_path)
            umount_lazy_cmd_str = " ".join(umount_lazy_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(target_host, ssh_user, ssh_port, umount_lazy_cmd_str)
            
            returncode, stdout, stderr = await self.run_command(ssh_cmd)
            if returncode == 0:
                logger.info(f"Successfully lazy unmounted {dataset_path} on {target_host}")
                return True
            else:
                logger.error(f"All unmount attempts failed for {dataset_path}: {stderr}")
                return False
                
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for force unmount: {e}")
            return False
        except Exception as e:
            logger.error(f"Error during force unmount of {dataset_path}: {e}")
            return False
