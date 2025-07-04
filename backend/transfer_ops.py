import logging
import os
from typing import List, Dict, Tuple, Optional
import asyncio
from .models import VolumeMount, TransferMethod
from .security_utils import SecurityUtils, SecurityValidationError, RsyncConfig

logger = logging.getLogger(__name__)


class TransferOperations:
    def __init__(self, zfs_ops=None):
        self.temp_mount_base = "/tmp/transdock_mounts"
        # Inject ZFSOperations to avoid duplication
        if zfs_ops is None:
            from .zfs_ops import ZFSOperations
            self.zfs_ops = ZFSOperations()
        else:
            self.zfs_ops = zfs_ops

    async def run_command(
            self, cmd: List[str], cwd: Optional[str] = None) -> Tuple[int, str, str]:
        """Run a command asynchronously"""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            stdout, stderr = await process.communicate()
            # Ensure returncode is never None by defaulting to 1 if it somehow
            # is
            returncode = process.returncode if process.returncode is not None else 1
            return returncode, stdout.decode(), stderr.decode()
        except Exception as e:
            logger.error(f"Command failed: {' '.join(cmd)} - {e}")
            return 1, "", str(e)

    async def create_target_directories(
            self,
            target_host: str,
            directories: List[str],
            ssh_user: str = "root",
            ssh_port: int = 22) -> bool:
        """Create target directories on remote host"""
        try:
            # Validate SSH parameters
            SecurityUtils.validate_hostname(target_host)
            SecurityUtils.validate_username(ssh_user)
            SecurityUtils.validate_port(ssh_port)
        except SecurityValidationError as e:
            logger.error(f"Security validation failed: {e}")
            return False

        for directory in directories:
            try:
                # Validate and sanitize directory path
                safe_directory = SecurityUtils.sanitize_path(
                    directory, allow_absolute=True)
                mkdir_cmd = f"mkdir -p {SecurityUtils.escape_shell_argument(safe_directory)}"
                cmd = SecurityUtils.build_ssh_command(
                    target_host, ssh_user, ssh_port, mkdir_cmd)

                returncode, _, stderr = await self.run_command(cmd)
                if returncode != 0:
                    logger.error(
                        f"Failed to create directory {directory} on {target_host}: {stderr}")
                    return False
            except SecurityValidationError as e:
                logger.error(
                    f"Security validation failed for directory {directory}: {e}")
                return False

        logger.info(f"Created {len(directories)} directories on {target_host}")
        return True

    async def transfer_via_zfs_send(
            self,
            snapshot_name: str,
            target_host: str,
            target_dataset: str,
            ssh_user: str = "root",
            ssh_port: int = 22) -> bool:
        """Transfer data using ZFS send/receive"""
        logger.info(
            f"Transferring {snapshot_name} via ZFS send to {target_host}:{target_dataset}")

        # Validate inputs to prevent command injection
        try:
            SecurityUtils.validate_hostname(target_host)
            SecurityUtils.validate_username(ssh_user)
            SecurityUtils.validate_port(ssh_port)
            SecurityUtils.validate_dataset_name(target_dataset)

            # Validate snapshot name format
            if '@' not in snapshot_name or len(snapshot_name) > 256:
                raise SecurityValidationError(
                    f"Invalid snapshot name: {snapshot_name}")
        except SecurityValidationError as e:
            logger.error(f"Security validation failed: {e}")
            return False

        # Create target dataset on remote system if it doesn't exist
        try:
            # First create parent datasets with -p flag
            zfs_create_cmd = SecurityUtils.validate_zfs_command_args(
                "create", "-p", target_dataset)
            create_cmd_str = " ".join(zfs_create_cmd)
            create_cmd = SecurityUtils.build_ssh_command(
                target_host, ssh_user, ssh_port, create_cmd_str)

            returncode, stdout, stderr = await self.run_command(create_cmd)
            if returncode != 0 and "dataset already exists" not in stderr:
                logger.warning(
                    f"Failed to create target dataset {target_dataset}: {stderr}")
                # Continue anyway - maybe the dataset will be created by the
                # receive command
        except SecurityValidationError as e:
            logger.warning(f"Failed to validate dataset creation command: {e}")

        # Send the snapshot using secure command construction
        try:
            zfs_send_cmd = SecurityUtils.validate_zfs_command_args(
                "send", snapshot_name)
            zfs_receive_cmd = SecurityUtils.validate_zfs_command_args(
                "receive", target_dataset)

            receive_cmd_str = " ".join(zfs_receive_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(
                target_host, ssh_user, ssh_port, receive_cmd_str)

            cmd = [
                "sh", "-c",
                f"{' '.join(zfs_send_cmd)} | {' '.join(ssh_cmd)}"
            ]
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for ZFS commands: {e}")
            return False

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
        logger.info(
            f"Transferring {source_path} via rsync to {target_host}:{target_path}")

        # Validate inputs and sanitize paths
        try:
            source_path = SecurityUtils.sanitize_path(
                source_path, allow_absolute=True)
            target_path = SecurityUtils.sanitize_path(
                target_path, allow_absolute=True)
        except SecurityValidationError as e:
            logger.error(f"Path validation failed: {e}")
            return False

        # Ensure target directory exists
        parent_dir = os.path.dirname(target_path)
        if parent_dir:
            await self.create_target_directories(target_host, [parent_dir], ssh_user, ssh_port)

        # Build secure rsync command using new RsyncConfig
        try:
            config = RsyncConfig(
                source=f"{source_path}/",
                hostname=target_host,
                username=ssh_user,
                port=ssh_port,
                target=f"{target_path}/",
                additional_args=["--delete"]
            )
            cmd = SecurityUtils.build_rsync_command(config)
        except SecurityValidationError as e:
            logger.error(f"Failed to build secure rsync command: {e}")
            return False

        returncode, stdout, stderr = await self.run_command(cmd)

        if returncode != 0:
            logger.error(f"rsync failed for {source_path}: {stderr}")
            return False

        logger.info(f"Successfully transferred {source_path} via rsync")
        return True

    async def mount_snapshot_for_rsync(
            self, snapshot_name: str) -> Optional[str]:
        """Mount a ZFS snapshot for rsync transfer - REFACTORED to use ZFSOperations"""
        mount_point = f"{self.temp_mount_base}/{snapshot_name.replace('/', '_').replace('@', '_')}"

        # Create mount point
        returncode, _, stderr = await self.run_command(["mkdir", "-p", mount_point])
        if returncode != 0:
            logger.error(
                f"Failed to create mount point {mount_point}: {stderr}")
            return None

        # Clone the snapshot to make it accessible
        clone_name = f"{snapshot_name.split('@')[0]}_rsync_clone"

        # Remove existing clone if it exists (best effort)
        try:
            destroy_cmd = SecurityUtils.validate_zfs_command_args(
                "destroy", clone_name)
            await self.run_command(destroy_cmd)
        except SecurityValidationError:
            # Best effort cleanup, continue if validation fails
            pass

        # Clone the snapshot using secure command construction
        try:
            clone_cmd = SecurityUtils.validate_zfs_command_args(
                "clone", snapshot_name, clone_name)
            returncode, _, stderr = await self.run_command(clone_cmd)
            if returncode != 0:
                logger.error(
                    f"Failed to clone snapshot {snapshot_name}: {stderr}")
                return None
        except SecurityValidationError as e:
            logger.error(
                f"Security validation failed for cloning snapshot: {e}")
            return None

        # Set mountpoint using secure command construction
        try:
            set_cmd = SecurityUtils.validate_zfs_command_args(
                "set", f"mountpoint={mount_point}", clone_name)
            returncode, _, stderr = await self.run_command(set_cmd)
            if returncode != 0:
                logger.error(
                    f"Failed to set mountpoint for {clone_name}: {stderr}")
                # Cleanup on failure
                try:
                    destroy_cmd = SecurityUtils.validate_zfs_command_args(
                        "destroy", clone_name)
                    await self.run_command(destroy_cmd)
                except SecurityValidationError:
                    pass  # Best effort cleanup
                return None
        except SecurityValidationError as e:
            logger.error(
                f"Security validation failed for setting mountpoint: {e}")
            # Cleanup on failure
            try:
                destroy_cmd = SecurityUtils.validate_zfs_command_args(
                    "destroy", clone_name)
                await self.run_command(destroy_cmd)
            except SecurityValidationError:
                pass  # Best effort cleanup
            return None

        logger.info(f"Mounted snapshot {snapshot_name} at {mount_point}")
        return mount_point

    async def cleanup_rsync_mount(
            self,
            mount_point: str,
            snapshot_name: str) -> bool:
        """Clean up temporary mount used for rsync - REFACTORED to use ZFSOperations"""
        clone_name = f"{snapshot_name.split('@')[0]}_rsync_clone"

        # Destroy the clone using secure command construction
        try:
            destroy_cmd = SecurityUtils.validate_zfs_command_args(
                "destroy", clone_name)
            returncode, _, stderr = await self.run_command(destroy_cmd)
            if returncode != 0:
                logger.error(f"Failed to destroy clone {clone_name}: {stderr}")
                return False
        except SecurityValidationError as e:
            logger.error(
                f"Security validation failed for destroying clone: {e}")
            return False

        # Remove mount point
        await self.run_command(["rm", "-rf", mount_point])

        logger.info(f"Cleaned up rsync mount {mount_point}")
        return True

    async def transfer_volume_data(
            self,
            volume: VolumeMount,
            snapshot_name: str,
            target_host: str,
            target_path: str,
            transfer_method: TransferMethod,
            ssh_user: str = "root",
            ssh_port: int = 22,
            source_host: Optional[str] = None,
            source_ssh_user: str = "root",
            source_ssh_port: int = 22) -> bool:
        """Transfer a volume's data based on the chosen method"""

        if transfer_method == TransferMethod.ZFS_SEND:
            # For ZFS send, we need to determine the target dataset name
            # Convert target path to dataset format
            if target_path.startswith("/mnt/"):
                target_dataset = target_path[5:]  # Remove /mnt/ prefix
            else:
                target_dataset = f"zpool{target_path}"  # Assume default zpool
        
            if source_host:
                # Remote source ZFS send
                return await self.transfer_via_remote_zfs_send(
                    snapshot_name, source_host, source_ssh_user, source_ssh_port,
                    target_host, target_dataset, ssh_user, ssh_port
                )
            # Local source ZFS send
            return await self.transfer_via_zfs_send(
                snapshot_name, target_host, target_dataset, ssh_user, ssh_port
            )
        
        # RSYNC
        if source_host:
            # Remote source rsync
            return await self.transfer_via_remote_rsync(
                volume.source, source_host, source_ssh_user, source_ssh_port,
                target_host, target_path, ssh_user, ssh_port
            )
        # Local source rsync - mount the snapshot and rsync
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
                # Remove "/mnt/cache/appdata/"
                relative_path = volume.source[19:]
                new_path = f"{target_base_path}/appdata/{relative_path}"
            elif volume.source.startswith("/mnt/cache/compose/"):
                # Remove "/mnt/cache/compose/"
                relative_path = volume.source[19:]
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
            # Validate inputs before using in shell commands
            SecurityUtils.validate_hostname(target_host)
            SecurityUtils.validate_username(ssh_user)
            SecurityUtils.validate_port(ssh_port)
            source_path = SecurityUtils.sanitize_path(
                source_path, allow_absolute=True)
            target_path = SecurityUtils.sanitize_path(
                target_path, allow_absolute=True)
            # Count files in source - use shell=True to handle pipe
            source_count_cmd = f"find {SecurityUtils.escape_shell_argument(source_path)} -type f | wc -l"
            process = await asyncio.create_subprocess_shell(
                source_count_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            returncode = process.returncode if process.returncode is not None else 1

            if returncode != 0:
                logger.error(
                    f"Failed to count source files: {stderr.decode()}")
                return False

            source_count = int(stdout.decode().strip())

            # Count files on target via SSH
            count_cmd = f"find {SecurityUtils.escape_shell_argument(target_path)} -type f | wc -l"
            ssh_cmd = SecurityUtils.build_ssh_command(
                target_host, ssh_user, ssh_port, count_cmd)

            returncode, stdout, stderr = await self.run_command(ssh_cmd)
            if returncode != 0:
                logger.error(f"Failed to count target files: {stderr}")
                return False

            target_count = int(stdout.strip())

            # Compare counts
            if source_count == target_count:
                logger.info(
                    f"Transfer verification successful: {source_count} files")
                return True
            else:
                logger.error(
                    f"Transfer verification failed: {source_count} source files != {target_count} target files")
                return False

        except Exception as e:
            logger.error(f"Transfer verification failed: {e}")
            return False

    async def rsync_transfer(
            self,
            source_path: str,
            target_host: str,
            target_path: str,
            ssh_user: str = "root",
            ssh_port: int = 22) -> bool:
        """Transfer data using rsync (wrapper around transfer_via_rsync)"""
        return await self.transfer_via_rsync(source_path, target_host, target_path, ssh_user, ssh_port)

    async def write_remote_file(
            self,
            target_host: str,
            target_file_path: str,
            content: str,
            ssh_user: str = "root",
            ssh_port: int = 22) -> bool:
        """Write content to a file on remote host"""
        try:
            # Validate inputs
            SecurityUtils.validate_hostname(target_host)
            SecurityUtils.validate_username(ssh_user)
            SecurityUtils.validate_port(ssh_port)
            target_file_path = SecurityUtils.sanitize_path(
                target_file_path, allow_absolute=True)

            # Create target directory if it doesn't exist
            target_dir = os.path.dirname(target_file_path)
            if target_dir:
                mkdir_cmd = f"mkdir -p {SecurityUtils.escape_shell_argument(target_dir)}"
                ssh_cmd = SecurityUtils.build_ssh_command(
                    target_host, ssh_user, ssh_port, mkdir_cmd)
                returncode, _, stderr = await self.run_command(ssh_cmd)
                if returncode != 0:
                    logger.error(
                        f"Failed to create target directory {target_dir}: {stderr}")
                    return False

            # Use echo to write content to file via SSH
            # Escape content for shell
            escaped_content = SecurityUtils.escape_shell_argument(content)
            escaped_path = SecurityUtils.escape_shell_argument(
                target_file_path)

            write_cmd = f"echo {escaped_content} > {escaped_path}"
            ssh_cmd = SecurityUtils.build_ssh_command(
                target_host, ssh_user, ssh_port, write_cmd)

            returncode, _, stderr = await self.run_command(ssh_cmd)
            if returncode != 0:
                logger.error(
                    f"Failed to write file {target_file_path}: {stderr}")
                return False

            logger.info(
                f"Successfully wrote file to {target_host}:{target_file_path}")
            return True

        except SecurityValidationError as e:
            logger.error(
                f"Security validation failed for remote file write: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to write remote file: {e}")
            return False

    async def transfer_via_remote_zfs_send(
            self,
            snapshot_name: str,
            source_host: str,
            source_ssh_user: str,
            source_ssh_port: int,
            target_host: str,
            target_dataset: str,
            target_ssh_user: str = "root",
            target_ssh_port: int = 22) -> bool:
        """Transfer ZFS snapshot from remote source to remote target"""
        try:
            # Validate inputs
            SecurityUtils.validate_hostname(source_host)
            SecurityUtils.validate_username(source_ssh_user)
            SecurityUtils.validate_port(source_ssh_port)
            SecurityUtils.validate_hostname(target_host)
            SecurityUtils.validate_username(target_ssh_user)
            SecurityUtils.validate_port(target_ssh_port)
            
            # Build the ZFS send command on source host
            zfs_send_cmd = f"zfs send {SecurityUtils.escape_shell_argument(snapshot_name)}"
            
            # Build the ZFS receive command on target host
            zfs_recv_cmd = f"zfs recv {SecurityUtils.escape_shell_argument(target_dataset)}"
            
            # Build the full command: ssh source "zfs send" | ssh target "zfs recv"
            source_ssh_cmd = SecurityUtils.build_ssh_command(
                source_host, source_ssh_user, source_ssh_port, zfs_send_cmd
            )
            target_ssh_cmd = SecurityUtils.build_ssh_command(
                target_host, target_ssh_user, target_ssh_port, zfs_recv_cmd
            )
            
            # Combine the commands with a pipe
            full_cmd = source_ssh_cmd + ["|"] + target_ssh_cmd
            
            # Execute the command
            process = await asyncio.create_subprocess_shell(
                " ".join(full_cmd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            returncode = process.returncode if process.returncode is not None else 1
            
            if returncode != 0:
                logger.error(f"Remote ZFS send failed: {stderr.decode()}")
                return False
            
            logger.info(f"Successfully transferred {snapshot_name} from {source_host} to {target_host}")
            return True
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for remote ZFS send: {e}")
            return False
        except Exception as e:
            logger.error(f"Remote ZFS send failed: {e}")
            return False
    
    async def transfer_via_remote_rsync(
            self,
            source_path: str,
            source_host: str,
            source_ssh_user: str,
            source_ssh_port: int,
            target_host: str,
            target_path: str,
            target_ssh_user: str = "root",
            target_ssh_port: int = 22) -> bool:
        """Transfer data using rsync between two remote hosts."""
        logger.info(
            f"Transferring {source_path} from {source_host} to {target_host}:{target_path} via rsync")

        try:
            # Validate all inputs
            SecurityUtils.validate_hostname(source_host)
            SecurityUtils.validate_username(source_ssh_user)
            SecurityUtils.validate_port(source_ssh_port)
            SecurityUtils.validate_hostname(target_host)
            SecurityUtils.validate_username(target_ssh_user)
            SecurityUtils.validate_port(target_ssh_port)
            
            # Sanitize paths
            safe_source_path = SecurityUtils.sanitize_path(source_path, allow_absolute=True)
            safe_target_path = SecurityUtils.sanitize_path(target_path, allow_absolute=True)

            # Ensure remote target directory exists
            await self.create_target_directories(
                target_host, [os.path.dirname(safe_target_path)], target_ssh_user, target_ssh_port
            )

            # Build the rsync command to be executed on the source host
            rsync_cmd_str = (
                f"rsync -avzP --delete "
                f"-e '{SecurityUtils.escape_shell_argument(f'ssh -p {target_ssh_port}')}' "
                f"{SecurityUtils.escape_shell_argument(f'{safe_source_path}/')} "
                f"{SecurityUtils.escape_shell_argument(f'{target_ssh_user}@{target_host}:{safe_target_path}/')}"
            )
            
            # Build the outer SSH command to run rsync on the source host
            cmd = SecurityUtils.build_ssh_command(
                source_host,
                source_ssh_user,
                source_ssh_port,
                rsync_cmd_str
            )
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed: {e}")
            return False

        returncode, stdout, stderr = await self.run_command(cmd)

        if returncode != 0:
            logger.error(
                f"Remote rsync failed for {safe_source_path}: {stderr}")
            return False

        logger.info(
            f"Successfully transferred {safe_source_path} from {source_host} to {target_host} via rsync")
        return True
