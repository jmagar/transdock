import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Union, Tuple, Any
from collections import defaultdict
from .security_utils import SecurityUtils, SecurityValidationError
from .utils import format_bytes

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
            # Ensure returncode is never None by defaulting to 1 if it somehow
            # is
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

            cmd = SecurityUtils.validate_zfs_command_args(
                command, *command_args)
            return await self.run_command(cmd)
        except SecurityValidationError:
            return 1, "", "Security validation failed"

    async def dataset_exists(self, dataset_name: str) -> bool:
        """Check if a ZFS dataset exists"""
        returncode, _, _ = await self.safe_run_zfs_command("list", "-H", dataset_name)
        return returncode == 0

    async def list_datasets(
            self,
            pool_name: Optional[str] = None) -> List[str]:
        """List ZFS datasets"""
        if pool_name:
            pool_name = SecurityUtils.validate_dataset_name(pool_name)
            returncode, stdout, stderr = await self.safe_run_zfs_command("list", "-H", "-o", "name", pool_name)
        else:
            returncode, stdout, stderr = await self.safe_run_zfs_command("list", "-H", "-o", "name")

        if returncode == 0:
            return [line.strip()
                    for line in stdout.split('\n') if line.strip()]
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

    async def create_snapshot(
            self,
            dataset_path: str,
            snapshot_name: Optional[str] = None) -> str:
        """Create a snapshot of a dataset"""
        dataset_name = await self.get_dataset_name(dataset_path)

        if not snapshot_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_name = f"transdock_{timestamp}"

        full_snapshot_name = f"{dataset_name}@{snapshot_name}"

        returncode, _, stderr = await self.safe_run_zfs_command("snapshot", full_snapshot_name)
        if returncode != 0:
            raise Exception(
                f"Failed to create snapshot {full_snapshot_name}: {stderr}")

        logger.info(f"Created snapshot: {full_snapshot_name}")
        return full_snapshot_name

    async def list_snapshots(self, dataset_path: str) -> List[str]:
        """List all snapshots for a dataset"""
        dataset_name = await self.get_dataset_name(dataset_path)

        returncode, stdout, stderr = await self.safe_run_zfs_command(
            "list", "-H", "-t", "snapshot", "-o", "name", "-s", "creation", dataset_name
        )

        if returncode != 0:
            logger.error(
                f"Failed to list snapshots for {dataset_name}: {stderr}")
            return []

        snapshots = [line.strip()
                     for line in stdout.split('\n') if line.strip()]
        return snapshots

    async def send_snapshot(
            self,
            snapshot_name: str,
            target_host: str,
            target_dataset: str,
            ssh_user: str = "root",
            ssh_port: int = 22) -> bool:
        """Send a snapshot to a remote ZFS system"""
        logger.info(
            f"Sending snapshot {snapshot_name} to {target_host}:{target_dataset}")

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

        # Handle target dataset - check if exists and prepare for overwrite
        dataset_exists = False
        dataset_mount_path = None

        try:
            logger.info(
                f"Checking if target dataset {target_dataset} exists on {target_host}")

            # Check if target dataset exists
            check_cmd = SecurityUtils.validate_zfs_command_args(
                "list", "-H", target_dataset)
            check_cmd_str = " ".join(check_cmd)
            check_ssh_cmd = SecurityUtils.build_ssh_command(
                target_host, ssh_user, ssh_port, check_cmd_str)

            returncode, stdout, stderr = await self.run_command(check_ssh_cmd)
            if returncode == 0:
                dataset_exists = True
                logger.info(f"Target dataset {target_dataset} exists")

                # Get the actual mount path using zfs get mountpoint
                get_mountpoint_cmd = SecurityUtils.validate_zfs_command_args(
                    "get", "-H", "-o", "value", "mountpoint", target_dataset)
                get_mountpoint_cmd_str = " ".join(get_mountpoint_cmd)
                mountpoint_ssh_cmd = SecurityUtils.build_ssh_command(
                    target_host, ssh_user, ssh_port, get_mountpoint_cmd_str)

                mp_returncode, mp_stdout, mp_stderr = await self.run_command(mountpoint_ssh_cmd)
                if mp_returncode == 0 and mp_stdout.strip():
                    dataset_mount_path = mp_stdout.strip()
                    if dataset_mount_path == "none" or dataset_mount_path == "-":
                        logger.info(
                            f"Target dataset {target_dataset} is not mounted")
                        dataset_mount_path = None
                    else:
                        logger.info(
                            f"Target dataset {target_dataset} is mounted at {dataset_mount_path}")

                        # Try to force unmount the dataset if it's busy
                        logger.info(
                            f"Attempting to force unmount {dataset_mount_path} to prevent busy errors")
                        unmount_success = await self.force_unmount_dataset(
                            target_host, dataset_mount_path, ssh_user, ssh_port
                        )
                        if unmount_success:
                            logger.info(
                                f"Successfully prepared {target_dataset} for overwrite")
                        else:
                            logger.warning(
                                f"Could not force unmount {dataset_mount_path}, will try -F flag anyway")
                else:
                    logger.warning(
                        f"Could not get mountpoint for {target_dataset}: {mp_stderr}")
                    dataset_mount_path = None

                # Clean up any existing snapshots on the target dataset
                logger.info(
                    f"Checking for existing snapshots on {target_dataset}")
                list_snapshots_cmd = SecurityUtils.validate_zfs_command_args(
                    "list", "-H", "-t", "snapshot", "-o", "name", "-s", "name", target_dataset)
                list_snapshots_cmd_str = " ".join(list_snapshots_cmd)
                snapshots_ssh_cmd = SecurityUtils.build_ssh_command(
                    target_host, ssh_user, ssh_port, list_snapshots_cmd_str)

                snap_returncode, snap_stdout, snap_stderr = await self.run_command(snapshots_ssh_cmd)
                if snap_returncode == 0 and snap_stdout.strip():
                    existing_snapshots = [
                        line.strip() for line in snap_stdout.strip().split('\n') if line.strip()]
                    logger.info(
                        f"Found {len(existing_snapshots)} existing snapshots on {target_dataset}")

                    # Destroy each existing snapshot
                    for snapshot in existing_snapshots:
                        logger.info(
                            f"Destroying existing snapshot: {snapshot}")
                        destroy_cmd = SecurityUtils.validate_zfs_command_args(
                            "destroy", snapshot)
                        destroy_cmd_str = " ".join(destroy_cmd)
                        destroy_ssh_cmd = SecurityUtils.build_ssh_command(
                            target_host, ssh_user, ssh_port, destroy_cmd_str)

                        destroy_returncode, destroy_stdout, destroy_stderr = await self.run_command(destroy_ssh_cmd)
                        if destroy_returncode == 0:
                            logger.info(
                                f"Successfully destroyed snapshot: {snapshot}")
                        else:
                            logger.warning(
                                f"Failed to destroy snapshot {snapshot}: {destroy_stderr}")
                else:
                    logger.info(
                        f"No existing snapshots found on {target_dataset}")
            else:
                logger.info(f"Target dataset {target_dataset} does not exist")

            # Ensure parent datasets exist
            parent_dataset = "/".join(target_dataset.split("/")[:-1])
            if parent_dataset:
                logger.info(
                    f"Ensuring parent dataset {parent_dataset} exists on {target_host}")
                parent_create_cmd = SecurityUtils.validate_zfs_command_args(
                    "create", "-p", parent_dataset)
                parent_create_cmd_str = " ".join(parent_create_cmd)
                parent_ssh_cmd = SecurityUtils.build_ssh_command(
                    target_host, ssh_user, ssh_port, parent_create_cmd_str)

                parent_returncode, parent_stdout, parent_stderr = await self.run_command(parent_ssh_cmd)
                if parent_returncode != 0:
                    logger.warning(
                        f"Failed to create parent dataset {parent_dataset}: {parent_stderr}")
                    # Continue anyway

        except SecurityValidationError as e:
            logger.warning(
                f"Failed to validate target dataset management commands: {e}")
            # Continue anyway

        # Build secure command with proper escaping
        zfs_send_cmd = SecurityUtils.validate_zfs_command_args(
            "send", snapshot_name)

        # Use -F flag to overwrite existing dataset if it exists
        if dataset_exists:
            zfs_receive_cmd = SecurityUtils.validate_zfs_command_args(
                "receive", "-F", target_dataset)
            logger.info(
                f"Using -F flag to overwrite existing dataset {target_dataset}")
        else:
            zfs_receive_cmd = SecurityUtils.validate_zfs_command_args(
                "receive", target_dataset)

        # Create secure ssh command for the receive part
        receive_cmd_str = " ".join(zfs_receive_cmd)
        ssh_cmd = SecurityUtils.build_ssh_command(
            target_host, ssh_user, ssh_port, receive_cmd_str)

        # Build the pipeline command safely
        cmd = [
            "sh", "-c",
            f"{' '.join(zfs_send_cmd)} | {' '.join(ssh_cmd)}"
        ]

        returncode, stdout, stderr = await self.run_command(cmd)

        if returncode != 0:
            logger.error(f"Failed to send snapshot {snapshot_name}: {stderr}")
            return False

        logger.info(
            f"Successfully sent snapshot {snapshot_name} to {target_host}")
        return True

    async def mount_snapshot(
            self,
            snapshot_name: str,
            mount_point: str) -> bool:
        """Mount a snapshot to a temporary location"""
        returncode, _, stderr = await self.run_command(["mkdir", "-p", mount_point])
        if returncode != 0:
            logger.error(
                f"Failed to create mount point {mount_point}: {stderr}")
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
            logger.error(
                f"Failed to set mountpoint for {clone_name}: {stderr}")
            await self.safe_run_zfs_command("destroy", clone_name)
            return False

        logger.info(
            f"Mounted snapshot {snapshot_name} at {mount_point} via clone {clone_name}")
        return True

    async def cleanup_snapshot(self, snapshot_name: str) -> bool:
        """Clean up a snapshot"""
        returncode, _, stderr = await self.safe_run_zfs_command("destroy", snapshot_name)
        if returncode != 0:
            logger.error(
                f"Failed to destroy snapshot {snapshot_name}: {stderr}")
            return False

        logger.info(f"Cleaned up snapshot: {snapshot_name}")
        return True

    async def check_remote_zfs(
            self,
            target_host: str,
            ssh_user: str = "root",
            ssh_port: int = 22) -> bool:
        """Check if the target host has ZFS available"""
        try:
            cmd = SecurityUtils.build_ssh_command(
                target_host, ssh_user, ssh_port, "which zfs")
            returncode, _, _ = await self.run_command(cmd)
            return returncode == 0
        except SecurityValidationError as e:
            logger.error(
                f"Security validation failed for remote ZFS check: {e}")
            return False

    async def is_zfs_available(self) -> bool:
        """Check if ZFS is available on the system"""
        returncode, _, _ = await self.run_command(["which", "zfs"])
        return returncode == 0
    
    # ===== ZFS Properties Management =====
    
    async def get_dataset_properties(self, dataset_name: str, properties: Optional[List[str]] = None) -> Dict[str, str]:
        """Get ZFS properties for a dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            if properties:
                # Get specific properties
                properties_str = ",".join(properties)
                returncode, stdout, stderr = await self.safe_run_zfs_command(
                    "get", "-H", "-o", "property,value", properties_str, dataset_name)
            else:
                # Get all properties
                returncode, stdout, stderr = await self.safe_run_zfs_command(
                    "get", "-H", "-o", "property,value", "all", dataset_name)
            
            if returncode != 0:
                logger.error(f"Failed to get properties for {dataset_name}: {stderr}")
                return {}
            
            # Parse the output
            props = {}
            for line in stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        props[parts[0]] = parts[1]
            
            return props
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for get_dataset_properties: {e}")
            return {}
    
    async def set_dataset_property(self, dataset_name: str, property_name: str, value: str) -> bool:
        """Set a ZFS property for a dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Validate property name (allow alphanumeric, underscore, colon, dash, and dot)
            if not all(c.isalnum() or c in '_:.-' for c in property_name):
                raise SecurityValidationError(f"Invalid property name: {property_name}")
            
            # Validate value (basic validation, ZFS will do more specific validation)
            if len(value) > 1024:  # Reasonable limit
                raise SecurityValidationError(f"Property value too long: {len(value)} characters")
            
            property_assignment = f"{property_name}={value}"
            returncode, _, stderr = await self.safe_run_zfs_command("set", property_assignment, dataset_name)
            
            if returncode != 0:
                logger.error(f"Failed to set property {property_name}={value} for {dataset_name}: {stderr}")
                return False
            
            logger.info(f"Successfully set property {property_name}={value} for {dataset_name}")
            return True
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for set_dataset_property: {e}")
            return False
    
    async def get_dataset_usage(self, dataset_name: str) -> Dict[str, Union[int, str]]:
        """Get detailed usage information for a dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Get space usage properties
            usage_properties = [
                "used", "available", "referenced", "compressratio", 
                "compression", "dedup", "logicalused", "logicalreferenced"
            ]
            
            props = await self.get_dataset_properties(dataset_name, usage_properties)
            
            if not props:
                return {}
            
            # Convert size values to bytes and add human-readable versions
            result = {}
            for prop, value in props.items():
                if prop in ["used", "available", "referenced", "logicalused", "logicalreferenced"]:
                    # Convert to bytes
                    try:
                        bytes_value = self._parse_zfs_size(value)
                        result[f"{prop}_bytes"] = bytes_value
                        result[f"{prop}_human"] = format_bytes(bytes_value)
                    except ValueError:
                        result[prop] = value
                else:
                    result[prop] = value
            
            return result
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for get_dataset_usage: {e}")
            return {}
    
    async def optimize_dataset_for_migration(self, dataset_name: str, migration_type: str = "docker") -> bool:
        """Optimize a dataset for migration by setting appropriate properties"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Get current properties to avoid unnecessary changes
            current_props = await self.get_dataset_properties(
                dataset_name, 
                ["compression", "dedup", "recordsize", "atime", "relatime"]
            )
            
            # Define optimization settings based on migration type
            if migration_type == "docker":
                optimizations = {
                    "compression": "lz4",  # Fast compression, good for mixed data
                    "atime": "off",        # Disable access time updates for performance
                    "relatime": "on",      # Enable relative atime for better balance
                    "recordsize": "128K",  # Good for larger files common in Docker
                }
            elif migration_type == "database":
                optimizations = {
                    "compression": "lz4",
                    "atime": "off",
                    "relatime": "on", 
                    "recordsize": "8K",    # Better for database workloads
                }
            elif migration_type == "media":
                optimizations = {
                    "compression": "off",  # Media files are usually already compressed
                    "atime": "off",
                    "relatime": "on",
                    "recordsize": "1M",    # Large record size for media files
                }
            else:
                # Default optimizations
                optimizations = {
                    "compression": "lz4",
                    "atime": "off",
                    "relatime": "on",
                }
            
            # Apply optimizations
            success = True
            for prop, value in optimizations.items():
                if current_props.get(prop) != value:
                    logger.info(f"Setting {prop}={value} for {dataset_name}")
                    if not await self.set_dataset_property(dataset_name, prop, value):
                        success = False
                        logger.error(f"Failed to set {prop}={value} for {dataset_name}")
                else:
                    logger.info(f"Property {prop} already set to {value} for {dataset_name}")
            
            if success:
                logger.info(f"Successfully optimized dataset {dataset_name} for {migration_type} migration")
            
            return success
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for optimize_dataset_for_migration: {e}")
            return False
    
    def _parse_zfs_size(self, size_str: str) -> int:
        """Parse ZFS size string to bytes"""
        size_str = size_str.strip().upper()
        
        # Handle special cases
        if size_str in ["-", "0"]:
            return 0
        
        # Extract numeric part and unit
        units = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
        
        # Find the unit
        unit = "B"
        for u in units:
            if size_str.endswith(u):
                unit = u
                size_str = size_str[:-len(u)]
                break
        
        try:
            # Handle decimal numbers
            if "." in size_str:
                numeric_value = float(size_str)
            else:
                numeric_value = int(size_str)
            
            return int(numeric_value * units[unit])
        except ValueError:
            raise ValueError(f"Cannot parse size: {size_str}")
    
    async def get_dataset_snapshots_detailed(self, dataset_name: str) -> List[Dict[str, Union[str, int]]]:
        """Get detailed information about snapshots for a dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Get detailed snapshot information
            returncode, stdout, stderr = await self.safe_run_zfs_command(
                "list", "-H", "-t", "snapshot", "-o", 
                "name,used,referenced,creation,clones", 
                "-s", "creation", dataset_name
            )
            
            if returncode != 0:
                logger.error(f"Failed to get detailed snapshots for {dataset_name}: {stderr}")
                return []
            
            snapshots = []
            for line in stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 4:
                        snapshot: Dict[str, Union[str, int]] = {
                            "name": parts[0],
                            "used": parts[1],
                            "referenced": parts[2],
                            "creation": parts[3],
                            "clones": parts[4] if len(parts) > 4 else "-"
                        }
                        
                        # Add parsed size information
                        try:
                            snapshot["used_bytes"] = self._parse_zfs_size(parts[1])
                            snapshot["used_human"] = format_bytes(snapshot["used_bytes"])
                            snapshot["referenced_bytes"] = self._parse_zfs_size(parts[2])
                            snapshot["referenced_human"] = format_bytes(snapshot["referenced_bytes"])
                        except ValueError:
                            pass
                        
                        snapshots.append(snapshot)
            
            return snapshots
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for get_dataset_snapshots_detailed: {e}")
            return []
    
    # ===== ZFS Pool Health Monitoring =====
    
    async def get_pool_status(self, pool_name: Optional[str] = None) -> Dict[str, Any]:
        """Get ZFS pool status and health information"""
        try:
            if pool_name:
                pool_name = SecurityUtils.validate_dataset_name(pool_name)
                returncode, stdout, stderr = await self.safe_run_zfs_command("status", "-v", pool_name)
            else:
                returncode, stdout, stderr = await self.safe_run_zfs_command("status", "-v")
            
            if returncode != 0:
                logger.error(f"Failed to get pool status: {stderr}")
                return {}
            
            # Parse the pool status output
            pools = self._parse_pool_status(stdout)
            
            if pool_name and pools:
                # Return single pool status
                return pools.get(pool_name, {})

            # Return all pools
            return {"pools": pools}
                
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for get_pool_status: {e}")
            return {}
    
    async def get_pool_health(self, pool_name: str) -> Dict[str, Union[str, bool, int]]:
        """Get comprehensive health information for a specific pool"""
        try:
            pool_name = SecurityUtils.validate_dataset_name(pool_name)
            
            # Get pool status
            pool_status = await self.get_pool_status(pool_name)
            
            if not pool_status:
                return {"healthy": False, "error": "Pool not found or inaccessible"}
            
            # Get pool properties for additional health metrics
            pool_props = await self.get_pool_properties(pool_name, [
                "health", "size", "allocated", "free", "capacity", 
                "dedupratio", "fragmentation", "readonly"
            ])
            
            # Determine overall health
            health_state = pool_status.get("state", "UNKNOWN")
            capacity = pool_props.get("capacity", "0%")
            fragmentation = pool_props.get("fragmentation", "0%")
            readonly = pool_props.get("readonly", "off")
            
            # Parse capacity percentage
            try:
                capacity_pct = int(capacity.rstrip('%'))
            except (ValueError, AttributeError):
                capacity_pct = 0
            
            # Parse fragmentation percentage
            try:
                fragmentation_pct = int(fragmentation.rstrip('%'))
            except (ValueError, AttributeError):
                fragmentation_pct = 0
            
            # Determine health status
            is_healthy = (
                health_state == "ONLINE" and
                capacity_pct < 90 and  # Not too full
                fragmentation_pct < 50 and  # Not too fragmented
                readonly == "off"  # Not in read-only mode
            )
            
            health_info = {
                "healthy": is_healthy,
                "state": health_state,
                "capacity_percent": capacity_pct,
                "fragmentation_percent": fragmentation_pct,
                "readonly": readonly == "on",
                "size": pool_props.get("size", "unknown"),
                "allocated": pool_props.get("allocated", "unknown"),
                "free": pool_props.get("free", "unknown"),
                "dedup_ratio": pool_props.get("dedupratio", "1.00x")
            }
            
            # Add human-readable sizes
            try:
                if pool_props.get("size") and pool_props["size"] != "-":
                    health_info["size_bytes"] = self._parse_zfs_size(pool_props["size"])
                    health_info["size_human"] = format_bytes(health_info["size_bytes"])
                if pool_props.get("allocated") and pool_props["allocated"] != "-":
                    health_info["allocated_bytes"] = self._parse_zfs_size(pool_props["allocated"])
                    health_info["allocated_human"] = format_bytes(health_info["allocated_bytes"])
                if pool_props.get("free") and pool_props["free"] != "-":
                    health_info["free_bytes"] = self._parse_zfs_size(pool_props["free"])
                    health_info["free_human"] = format_bytes(health_info["free_bytes"])
            except ValueError:
                pass  # Keep original string values if parsing fails
            
            # Add warnings for concerning conditions
            warnings = []
            if capacity_pct > 80:
                warnings.append(f"Pool is {capacity_pct}% full - consider adding space")
            if fragmentation_pct > 30:
                warnings.append(f"Pool is {fragmentation_pct}% fragmented - consider defragmentation")
            if readonly == "on":
                warnings.append("Pool is in read-only mode")
            if health_state != "ONLINE":
                warnings.append(f"Pool state is {health_state} - check for errors")
            
            if warnings:
                health_info["warnings"] = warnings
            
            return health_info
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for get_pool_health: {e}")
            return {"healthy": False, "error": "Security validation failed"}
    
    async def get_pool_properties(self, pool_name: str, properties: Optional[List[str]] = None) -> Dict[str, str]:
        """Get ZFS pool properties"""
        try:
            pool_name = SecurityUtils.validate_dataset_name(pool_name)
            
            if properties:
                # Get specific properties
                properties_str = ",".join(properties)
                returncode, stdout, stderr = await self.safe_run_zfs_command(
                    "get", "-H", "-o", "property,value", properties_str, pool_name)
            else:
                # Get all properties
                returncode, stdout, stderr = await self.safe_run_zfs_command(
                    "get", "-H", "-o", "property,value", "all", pool_name)
            
            if returncode != 0:
                logger.error(f"Failed to get pool properties for {pool_name}: {stderr}")
                return {}
            
            # Parse the output
            props = {}
            for line in stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        props[parts[0]] = parts[1]
            
            return props
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for get_pool_properties: {e}")
            return {}
    
    async def check_pool_before_migration(self, pool_name: str) -> Tuple[bool, List[str]]:
        """Check if a pool is ready for migration operations"""
        try:
            pool_name = SecurityUtils.validate_dataset_name(pool_name)
            
            health_info = await self.get_pool_health(pool_name)
            
            if not health_info:
                return False, ["Could not retrieve pool health information"]
            
            errors = []
            warnings = []
            
            # Check if pool is healthy
            if not health_info.get("healthy", False):
                errors.append(f"Pool {pool_name} is not healthy")
            
            # Check pool state
            if health_info.get("state") != "ONLINE":
                errors.append(f"Pool {pool_name} is not online (state: {health_info.get('state')})")
            
            # Check capacity
            capacity_pct = health_info.get("capacity_percent", 0)
            if isinstance(capacity_pct, int) and capacity_pct > 95:
                errors.append(f"Pool {pool_name} is {capacity_pct}% full - insufficient space for migration")
            elif isinstance(capacity_pct, int) and capacity_pct > 85:
                warnings.append(f"Pool {pool_name} is {capacity_pct}% full - monitor space during migration")
            
            # Check read-only mode
            readonly = health_info.get("readonly", False)
            if isinstance(readonly, bool) and readonly:
                errors.append(f"Pool {pool_name} is in read-only mode")
            
            # Check fragmentation
            fragmentation_pct = health_info.get("fragmentation_percent", 0)
            if isinstance(fragmentation_pct, int) and fragmentation_pct > 70:
                warnings.append(f"Pool {pool_name} is {fragmentation_pct}% fragmented - performance may be degraded")
            
            # Add any existing warnings from health check
            existing_warnings = health_info.get("warnings")
            if existing_warnings and isinstance(existing_warnings, list):
                warnings.extend(existing_warnings)
            
            # Log results
            if errors:
                for error in errors:
                    logger.error(error)
            if warnings:
                for warning in warnings:
                    logger.warning(warning)
            
            is_ready = len(errors) == 0
            all_messages = errors + warnings
            
            if is_ready:
                logger.info(f"Pool {pool_name} is ready for migration")
            else:
                logger.error(f"Pool {pool_name} is not ready for migration: {', '.join(errors)}")
            
            return is_ready, all_messages
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for check_pool_before_migration: {e}")
            return False, ["Security validation failed"]
    
    async def start_pool_scrub(self, pool_name: str) -> bool:
        """Start a scrub operation on a ZFS pool"""
        try:
            pool_name = SecurityUtils.validate_dataset_name(pool_name)
            
            returncode, _, stderr = await self.safe_run_zfs_command("scrub", pool_name)
            
            if returncode != 0:
                logger.error(f"Failed to start scrub on pool {pool_name}: {stderr}")
                return False
            
            logger.info(f"Started scrub operation on pool {pool_name}")
            return True
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for start_pool_scrub: {e}")
            return False
    
    async def get_pool_scrub_status(self, pool_name: str) -> Dict[str, Union[str, bool, int, Dict]]:
        """Get the scrub status for a ZFS pool, including progress and ETA."""
        try:
            pool_name = SecurityUtils.validate_dataset_name(pool_name)
            
            # Using safe_run_zfs_command to get the raw output
            returncode, stdout, stderr = await self.safe_run_zfs_command("status", "-v", pool_name)
            if returncode != 0:
                logger.error(f"Failed to get pool status for {pool_name}: {stderr}")
                return {"error": "Could not retrieve pool status"}

            status_text = stdout

            scrub_info: Dict[str, Any] = {
                "scrub_in_progress": "none",
                "state": "unknown",
                "last_scrub_time": "never",
                "errors": "none"
            }

            if "scrub in progress" in status_text:
                scrub_info["state"] = "scrubbing"
                
                progress_match = re.search(r"(\d+\.\d+)\% done", status_text)
                if progress_match:
                    scrub_info["progress_percent"] = float(progress_match.group(1))

                eta_match = re.search(r"(\d+h\d+m) to go", status_text)
                if eta_match:
                    scrub_info["eta"] = eta_match.group(1)

                repaired_match = re.search(r"repaired (\d+)B", status_text)
                if repaired_match:
                    scrub_info["repaired_bytes"] = int(repaired_match.group(1))

            elif "scrub repaired" in status_text or "scrub completed" in status_text:
                scrub_info["state"] = "completed"
                scan_line_match = re.search(r"scan:.+", status_text)
                if scan_line_match:
                    scrub_info["last_scrub_time"] = scan_line_match.group(0)

            errors_match = re.search(r"errors: (.+)", status_text)
            if errors_match:
                scrub_info["errors"] = errors_match.group(1)
            
            return scrub_info
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for get_pool_scrub_status: {e}")
            return {"error": "Security validation failed"}
    
    def _parse_pool_status(self, status_output: str) -> Dict[str, Dict[str, Union[str, List[Dict[str, str]]]]]:
        """Parse zpool status output into structured data"""
        pools = {}
        current_pool = None
        current_config = []
        
        lines = status_output.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            if line.startswith('pool:'):
                current_pool = line.split(':', 1)[1].strip()
                pools[current_pool] = {
                    "name": current_pool,
                    "state": "UNKNOWN",
                    "config": []
                }
                current_config = []
                
            elif line.startswith('state:') and current_pool:
                pools[current_pool]["state"] = line.split(':', 1)[1].strip()
                
            elif line.startswith('status:') and current_pool:
                pools[current_pool]["status"] = line.split(':', 1)[1].strip()
                
            elif line.startswith('action:') and current_pool:
                pools[current_pool]["action"] = line.split(':', 1)[1].strip()
                
            elif line.startswith('scan:') and current_pool:
                pools[current_pool]["scan"] = line.split(':', 1)[1].strip()
                
            elif line.startswith('errors:') and current_pool:
                pools[current_pool]["errors"] = line.split(':', 1)[1].strip()
                
            elif 'NAME' in line and 'STATE' in line and current_pool:
                # Start of config section
                i += 1
                while i < len(lines) and lines[i].strip() and not lines[i].startswith('\t\t'):
                    config_line = lines[i].strip()
                    if config_line and not config_line.startswith('pool:'):
                        parts = config_line.split()
                        if len(parts) >= 2:
                            current_config.append({
                                "name": parts[0],
                                "state": parts[1],
                                "read_errors": parts[2] if len(parts) > 2 else "0",
                                "write_errors": parts[3] if len(parts) > 3 else "0",
                                "checksum_errors": parts[4] if len(parts) > 4 else "0"
                            })
                    i += 1
                pools[current_pool]["config"] = current_config
                continue
                
            i += 1
        
        return pools
    
    # ===== Advanced Snapshot Management =====
    
    async def create_incremental_snapshot(
        self, dataset_name: str, base_snapshot: Optional[str] = None, 
        snapshot_name: Optional[str] = None
    ) -> Dict[str, Union[str, bool]]:
        """Create an incremental snapshot based on a previous snapshot"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            if not snapshot_name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                snapshot_name = f"transdock_incr_{timestamp}"
            
            full_snapshot_name = f"{dataset_name}@{snapshot_name}"
            
            # If no base snapshot provided, find the most recent one
            if not base_snapshot:
                existing_snapshots = await self.list_snapshots(dataset_name)
                if existing_snapshots:
                    base_snapshot = existing_snapshots[-1]  # Most recent
                else:
                    # No existing snapshots, create a full snapshot
                    logger.info(f"No existing snapshots found for {dataset_name}, creating full snapshot")
                    await self.create_snapshot(dataset_name, snapshot_name)
                    return {
                        "snapshot_name": full_snapshot_name,
                        "is_incremental": False,
                        "base_snapshot": "none",
                        "success": True
                    }
            
            # Create the incremental snapshot
            returncode, _, stderr = await self.safe_run_zfs_command("snapshot", full_snapshot_name)
            
            if returncode != 0:
                logger.error(f"Failed to create incremental snapshot {full_snapshot_name}: {stderr}")
                return {
                    "success": False,
                    "error": f"Failed to create snapshot: {stderr}"
                }
            
            logger.info(f"Created incremental snapshot {full_snapshot_name} based on {base_snapshot}")
            
            return {
                "snapshot_name": full_snapshot_name,
                "is_incremental": True,
                "base_snapshot": base_snapshot,
                "success": True
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for create_incremental_snapshot: {e}")
            return {"success": False, "error": "Security validation failed"}
    
    async def send_incremental_snapshot(
        self, dataset_name: str, base_snapshot: str, 
        incremental_snapshot: str, target_host: str, 
        target_dataset: str, ssh_user: str = "root", 
        ssh_port: int = 22
    ) -> bool:
        """Send an incremental snapshot to a remote system"""
        try:
            # Validate all inputs
            SecurityUtils.validate_hostname(target_host)
            SecurityUtils.validate_username(ssh_user)
            SecurityUtils.validate_port(ssh_port)
            SecurityUtils.validate_dataset_name(target_dataset)
            
            # Validate snapshot names
            if '@' not in base_snapshot or '@' not in incremental_snapshot:
                raise SecurityValidationError("Invalid snapshot name format")
            
            logger.info(f"Sending incremental snapshot {incremental_snapshot} (from {base_snapshot}) to {target_host}:{target_dataset}")
            
            # Build the incremental send command
            zfs_send_cmd = SecurityUtils.validate_zfs_command_args(
                "send", "-i", base_snapshot, incremental_snapshot)
            
            # Build receive command
            zfs_receive_cmd = SecurityUtils.validate_zfs_command_args(
                "receive", "-F", target_dataset)
            
            receive_cmd_str = " ".join(zfs_receive_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(
                target_host, ssh_user, ssh_port, receive_cmd_str)
            
            # Build the pipeline command
            cmd = [
                "sh", "-c",
                f"{' '.join(zfs_send_cmd)} | {' '.join(ssh_cmd)}"
            ]
            
            returncode, stdout, stderr = await self.run_command(cmd)
            
            if returncode != 0:
                logger.error(f"Failed to send incremental snapshot: {stderr}")
                return False
            
            logger.info(f"Successfully sent incremental snapshot {incremental_snapshot} to {target_host}")
            return True
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for send_incremental_snapshot: {e}")
            return False
    
    async def rollback_to_snapshot(self, snapshot_name: str, force: bool = False) -> bool:
        """Rollback a dataset to a specific snapshot"""
        try:
            # Validate snapshot name
            if '@' not in snapshot_name:
                raise SecurityValidationError("Invalid snapshot name format")
            
            dataset_name = snapshot_name.split('@')[0]
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Check if snapshot exists
            returncode, _, _ = await self.safe_run_zfs_command("list", "-H", "-t", "snapshot", snapshot_name)
            if returncode != 0:
                logger.error(f"Snapshot {snapshot_name} does not exist")
                return False
            
            # Perform rollback
            if force:
                returncode, _, stderr = await self.safe_run_zfs_command("rollback", "-r", snapshot_name)
            else:
                returncode, _, stderr = await self.safe_run_zfs_command("rollback", snapshot_name)
            
            if returncode != 0:
                logger.error(f"Failed to rollback to snapshot {snapshot_name}: {stderr}")
                return False
            
            logger.info(f"Successfully rolled back to snapshot {snapshot_name}")
            return True
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for rollback_to_snapshot: {e}")
            return False
    
    async def apply_snapshot_retention_policy(
        self, dataset_name: str, 
        keep_daily: int = 7, keep_weekly: int = 4, 
        keep_monthly: int = 6, keep_yearly: int = 2
    ) -> Dict[str, Union[int, List[str]]]:
        """Apply a retention policy to snapshots of a dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Get all snapshots for the dataset
            snapshots = await self.get_dataset_snapshots_detailed(dataset_name)
            
            if not snapshots:
                return {"deleted": 0, "kept": 0, "deleted_snapshots": []}
            
            # Sort snapshots by creation time (oldest first)
            snapshots.sort(key=lambda x: x.get("creation", ""))
            
            # Group snapshots by time periods
            keep_snapshots = set()
            
            # Keep daily snapshots
            daily_snapshots = self._group_snapshots_by_period(snapshots, "daily")
            keep_snapshots.update(daily_snapshots[-keep_daily:])
            
            # Keep weekly snapshots
            weekly_snapshots = self._group_snapshots_by_period(snapshots, "weekly")
            keep_snapshots.update(weekly_snapshots[-keep_weekly:])
            
            # Keep monthly snapshots
            monthly_snapshots = self._group_snapshots_by_period(snapshots, "monthly")
            keep_snapshots.update(monthly_snapshots[-keep_monthly:])
            
            # Keep yearly snapshots
            yearly_snapshots = self._group_snapshots_by_period(snapshots, "yearly")
            keep_snapshots.update(yearly_snapshots[-keep_yearly:])
            
            # Identify snapshots to delete
            all_snapshot_names = {snap["name"] for snap in snapshots}
            snapshots_to_delete = all_snapshot_names - keep_snapshots
            
            # Delete snapshots
            deleted_snapshots = []
            for snapshot_name in snapshots_to_delete:
                if isinstance(snapshot_name, str) and await self.cleanup_snapshot(snapshot_name):
                    deleted_snapshots.append(snapshot_name)
                    logger.info(f"Deleted snapshot {snapshot_name} per retention policy")
                else:
                    logger.warning(f"Failed to delete snapshot {snapshot_name}")
            
            logger.info(f"Applied retention policy to {dataset_name}: kept {len(keep_snapshots)}, deleted {len(deleted_snapshots)}")
            
            return {
                "deleted": len(deleted_snapshots),
                "kept": len(keep_snapshots),
                "deleted_snapshots": deleted_snapshots
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for apply_snapshot_retention_policy: {e}")
            return {"deleted": 0, "kept": 0, "deleted_snapshots": []}
    
    async def create_snapshot_bookmark(self, snapshot_name: str, bookmark_name: Optional[str] = None) -> bool:
        """Create a bookmark from a snapshot for space-efficient replication"""
        try:
            # Validate snapshot name
            if '@' not in snapshot_name:
                raise SecurityValidationError("Invalid snapshot name format")
            
            dataset_name = snapshot_name.split('@')[0]
            snapshot_suffix = snapshot_name.split('@')[1]
            
            if not bookmark_name:
                bookmark_name = f"{snapshot_suffix}_bookmark"
            
            # Validate bookmark name (bookmarks use # instead of @)
            if not all(c.isalnum() or c in '_-' for c in bookmark_name):
                raise SecurityValidationError("Invalid bookmark name")
            
            full_bookmark_name = f"{dataset_name}#{bookmark_name}"
            
            # Create the bookmark
            returncode, _, stderr = await self.safe_run_zfs_command("bookmark", snapshot_name, full_bookmark_name)
            
            if returncode != 0:
                logger.error(f"Failed to create bookmark {full_bookmark_name}: {stderr}")
                return False
            
            logger.info(f"Created bookmark {full_bookmark_name} from snapshot {snapshot_name}")
            return True
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for create_snapshot_bookmark: {e}")
            return False
    
    async def list_bookmarks(self, dataset_name: str) -> List[Dict[str, str]]:
        """List all bookmarks for a dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Get bookmarks
            returncode, stdout, stderr = await self.safe_run_zfs_command(
                "list", "-H", "-t", "bookmark", "-o", "name,creation", dataset_name
            )
            
            if returncode != 0:
                logger.error(f"Failed to list bookmarks for {dataset_name}: {stderr}")
                return []
            
            bookmarks = []
            for line in stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        bookmarks.append({
                            "name": parts[0],
                            "creation": parts[1]
                        })
            
            return bookmarks
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for list_bookmarks: {e}")
            return []
    
    def _group_snapshots_by_period(self, snapshots: List[Dict[str, Any]], period: str) -> List[str]:
        """Group snapshots by period and return the most recent one from each period."""
        if not snapshots:
            return []

        grouped_snapshots = defaultdict(list)
        
        for snapshot in snapshots:
            try:
                # The creation time from `zfs list` can have variable spacing.
                # A more robust solution would be to get raw timestamps (`zfs get -p creation`).
                creation_str = snapshot.get("creation", "")
                creation_time = datetime.strptime(creation_str, "%a %b %d %H:%M %Y")
            except (ValueError, KeyError):
                logger.warning(f"Could not parse creation date '{snapshot.get('creation')}' for snapshot {snapshot['name']}. Skipping.")
                continue

            if period == "daily":
                group_key = creation_time.date()
            elif period == "weekly":
                group_key = (creation_time.isocalendar().year, creation_time.isocalendar().week)
            elif period == "monthly":
                group_key = (creation_time.year, creation_time.month)
            elif period == "yearly":
                group_key = creation_time.year
            else:
                continue
            
            grouped_snapshots[group_key].append(snapshot)

        # The input snapshots are sorted newest first, so the first in each group is the one to keep.
        kept_snapshots = []
        for group_key, snaps_in_group in grouped_snapshots.items():
            # Sort again to be certain, as the primary source of sorting is outside this function.
            snaps_in_group.sort(key=lambda s: datetime.strptime(s.get("creation", ""), "%a %b %d %H:%M %Y"), reverse=True)
            if snaps_in_group:
                kept_snapshots.append(snaps_in_group[0]['name'])

        return kept_snapshots
    
    # ===== ZFS Performance Monitoring =====
    
    async def get_zfs_iostat(self, pools: Optional[List[str]] = None, interval: int = 1, count: int = 5) -> Dict[str, Any]:
        """Get ZFS I/O statistics"""
        try:
            # Build command
            cmd_args = ["iostat", "-v"]
            
            if pools:
                # Validate pool names
                validated_pools = []
                for pool in pools:
                    validated_pool = SecurityUtils.validate_dataset_name(pool)
                    validated_pools.append(validated_pool)
                cmd_args.extend(validated_pools)
            
            cmd_args.extend([str(interval), str(count)])
            
            returncode, stdout, stderr = await self.safe_run_zfs_command(*cmd_args)
            
            if returncode != 0:
                logger.error(f"Failed to get ZFS iostat: {stderr}")
                return {}
            
            # Parse iostat output
            iostat_data = self._parse_zfs_iostat(stdout)
            
            return {
                "iostat": iostat_data,
                "interval": interval,
                "count": count,
                "timestamp": datetime.now().isoformat()
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for get_zfs_iostat: {e}")
            return {}
    
    async def monitor_migration_performance(self, dataset_name: str, duration_seconds: int = 30) -> Dict[str, Any]:
        """Monitor ZFS performance during migration operations"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Get pool name from dataset
            pool_name = dataset_name.split('/')[0]
            
            logger.info(f"Starting performance monitoring for {dataset_name} for {duration_seconds} seconds")
            
            # Get baseline metrics
            baseline_props = await self.get_dataset_properties(dataset_name, [
                "used", "available", "referenced", "compressratio", "written"
            ])
            
            baseline_pool_iostat = await self.get_zfs_iostat([pool_name], interval=1, count=1)
            
            # Wait for the specified duration
            await asyncio.sleep(duration_seconds)
            
            # Get final metrics
            final_props = await self.get_dataset_properties(dataset_name, [
                "used", "available", "referenced", "compressratio", "written"
            ])
            
            final_pool_iostat = await self.get_zfs_iostat([pool_name], interval=1, count=1)
            
            # Calculate performance metrics
            performance_data = {
                "dataset": dataset_name,
                "monitoring_duration": duration_seconds,
                "baseline": {
                    "properties": baseline_props,
                    "iostat": baseline_pool_iostat
                },
                "final": {
                    "properties": final_props,
                    "iostat": final_pool_iostat
                }
            }
            
            # Calculate changes
            changes = {}
            for prop in ["used", "available", "referenced"]:
                if prop in baseline_props and prop in final_props:
                    try:
                        baseline_bytes = self._parse_zfs_size(baseline_props[prop])
                        final_bytes = self._parse_zfs_size(final_props[prop])
                        change_bytes = final_bytes - baseline_bytes
                        changes[f"{prop}_change_bytes"] = change_bytes
                        changes[f"{prop}_change_human"] = format_bytes(abs(change_bytes))
                        
                        if duration_seconds > 0:
                            rate_bytes_per_sec = change_bytes / duration_seconds
                            changes[f"{prop}_rate_bytes_per_sec"] = rate_bytes_per_sec
                            changes[f"{prop}_rate_human"] = f"{format_bytes(int(abs(rate_bytes_per_sec)))}/s"
                    except ValueError:
                        pass
            
            performance_data["changes"] = changes
            
            logger.info(f"Performance monitoring complete for {dataset_name}")
            
            return performance_data
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for monitor_migration_performance: {e}")
            return {}

    def _parse_arc_stats(self, arc_stats_output: str) -> Dict[str, Union[str, int, float]]:
        """Helper to parse ARC statistics from /proc/spl/kstat/zfs/arcstats."""
        arc_stats: Dict[str, Union[str, int, float]] = {}
        for line in arc_stats_output.strip().split('\n'):
            if not line.strip() or line.startswith('#'):
                continue
            
            parts = line.split()
            if len(parts) < 3:
                continue

            stat_name, _, stat_value = parts[0], parts[1], parts[2]

            if stat_name in ["size", "c", "c_max", "c_min", "mfu_size", "mru_size", "meta_size"]:
                try:
                    bytes_value = int(stat_value)
                    arc_stats[stat_name] = bytes_value
                    arc_stats[f"{stat_name}_human"] = format_bytes(bytes_value)
                except ValueError:
                    arc_stats[stat_name] = stat_value
            else:
                try:
                    arc_stats[stat_name] = int(stat_value)
                except ValueError:
                    arc_stats[stat_name] = stat_value

        hits = arc_stats.get("hits", 0)
        misses = arc_stats.get("misses", 0)

        if isinstance(hits, int) and isinstance(misses, int):
            total_requests = hits + misses
            if total_requests > 0:
                hit_ratio = (hits / total_requests) * 100
                arc_stats["hit_ratio_percent"] = round(hit_ratio, 2)
        
        return arc_stats

    async def get_arc_statistics(self) -> Dict[str, Union[str, int, float]]:
        """Get ZFS ARC (Adaptive Replacement Cache) statistics"""
        try:
            returncode, stdout, stderr = await self.run_command(["cat", "/proc/spl/kstat/zfs/arcstats"])
            if returncode != 0:
                logger.error(f"Failed to read ARC statistics: {stderr}")
                return {}
            
            return self._parse_arc_stats(stdout)
            
        except Exception as e:
            logger.error(f"Failed to get ARC statistics: {e}")
            return {}
    
    def _parse_zfs_iostat(self, iostat_output: str) -> Dict[str, Any]:
        """Parse zpool iostat output"""
        lines = iostat_output.strip().split('\n')
        
        # Find the data section (skip headers)
        data_lines = []
        in_data_section = False
        
        for line in lines:
            if line.strip() and not line.startswith('pool') and not line.startswith('---'):
                if any(char.isdigit() for char in line):
                    in_data_section = True
                    
                if in_data_section:
                    data_lines.append(line.strip())
        
        # Parse the data
        pools_data = []
        for line in data_lines:
            if line.strip():
                parts = line.split()
                if len(parts) >= 7:  # Basic iostat format
                    pool_data = {
                        "pool": parts[0],
                        "alloc": parts[1],
                        "free": parts[2],
                        "read_ops": parts[3],
                        "write_ops": parts[4],
                        "read_bandwidth": parts[5],
                        "write_bandwidth": parts[6]
                    }
                    
                    # Convert bandwidth to bytes per second if possible
                    try:
                        if pool_data["read_bandwidth"].endswith('K'):
                            pool_data["read_bandwidth_bytes_per_sec"] = int(float(pool_data["read_bandwidth"][:-1]) * 1024)
                        elif pool_data["read_bandwidth"].endswith('M'):
                            pool_data["read_bandwidth_bytes_per_sec"] = int(float(pool_data["read_bandwidth"][:-1]) * 1024 * 1024)
                        
                        if pool_data["write_bandwidth"].endswith('K'):
                            pool_data["write_bandwidth_bytes_per_sec"] = int(float(pool_data["write_bandwidth"][:-1]) * 1024)
                        elif pool_data["write_bandwidth"].endswith('M'):
                            pool_data["write_bandwidth_bytes_per_sec"] = int(float(pool_data["write_bandwidth"][:-1]) * 1024 * 1024)
                    except (ValueError, IndexError):
                        pass
                    
                    pools_data.append(pool_data)
        
        return {"pools": pools_data}
    
    # ===== Advanced Backup and Restore Capabilities =====
    
    async def create_backup_strategy(self, dataset_name: str, backup_type: str = "incremental", 
                                   retention_policy: Optional[Dict[str, int]] = None) -> Dict[str, Union[str, bool, Dict]]:
        """Create a comprehensive backup strategy for a dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            if backup_type not in ["full", "incremental", "differential"]:
                raise SecurityValidationError("Invalid backup type. Must be 'full', 'incremental', or 'differential'")
            
            if not retention_policy:
                retention_policy = {
                    "daily": 7,
                    "weekly": 4, 
                    "monthly": 6,
                    "yearly": 2
                }
            
            # Get existing snapshots to determine backup strategy
            existing_snapshots = await self.get_dataset_snapshots_detailed(dataset_name)
            
            strategy = {
                "dataset": dataset_name,
                "backup_type": backup_type,
                "retention_policy": retention_policy,
                "existing_snapshots_count": len(existing_snapshots),
                "recommendations": []
            }
            
            # Determine backup recommendations based on existing state
            if not existing_snapshots:
                strategy["recommendations"].append("Create initial full backup snapshot")
                strategy["next_action"] = "create_full_backup"
            else:
                # Find the most recent snapshot
                latest_snapshot = existing_snapshots[-1] if existing_snapshots else None
                strategy["latest_snapshot"] = latest_snapshot["name"] if latest_snapshot else None
                
                if backup_type == "incremental":
                    strategy["recommendations"].append(f"Create incremental backup based on {strategy['latest_snapshot']}")
                    strategy["next_action"] = "create_incremental_backup"
                elif backup_type == "full":
                    strategy["recommendations"].append("Create new full backup snapshot")
                    strategy["next_action"] = "create_full_backup"
                else:  # differential
                    # Find the last full backup
                    full_backups = [s for s in existing_snapshots if "full" in str(s.get("name", "")).lower()]
                    if full_backups:
                        base_full = full_backups[-1]["name"]
                        strategy["recommendations"].append(f"Create differential backup based on {base_full}")
                        strategy["base_full_snapshot"] = base_full
                        strategy["next_action"] = "create_differential_backup"
                    else:
                        strategy["recommendations"].append("No full backup found, creating full backup first")
                        strategy["next_action"] = "create_full_backup"
            
            # Check if retention policy should be applied
            if len(existing_snapshots) > sum(retention_policy.values()):
                strategy["recommendations"].append("Apply retention policy to clean up old snapshots")
                strategy["cleanup_needed"] = True
            
            logger.info(f"Created backup strategy for {dataset_name}: {strategy['next_action']}")
            
            return {
                "success": True,
                "strategy": strategy
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for create_backup_strategy: {e}")
            return {"success": False, "error": "Security validation failed"}

    async def _execute_full_backup(self, dataset_name: str, timestamp: str) -> Dict[str, Any]:
        """Helper to execute a full backup."""
        snapshot_name = f"backup_full_{timestamp}"
        success = await self.create_snapshot(dataset_name, snapshot_name)
        if not success:
            return {"success": False, "error": "Failed to create full backup snapshot"}

        full_snapshot_name = f"{dataset_name}@{snapshot_name}"
        actions = [f"Created full backup: {full_snapshot_name}"]

        bookmark_success = await self.create_snapshot_bookmark(full_snapshot_name, f"{snapshot_name}_bookmark")
        if bookmark_success:
            actions.append(f"Created bookmark: {dataset_name}#{snapshot_name}_bookmark")
        
        return {"success": True, "executed_actions": actions}

    async def _execute_incremental_backup(self, dataset_name: str, base_snapshot: str, timestamp: str) -> Dict[str, Any]:
        """Helper to execute an incremental backup."""
        if not base_snapshot:
            return {"success": False, "error": "No base snapshot available for incremental backup"}

        snapshot_name = f"backup_incr_{timestamp}"
        result = await self.create_incremental_snapshot(dataset_name, base_snapshot, snapshot_name)
        
        if not (isinstance(result, dict) and result.get("success")):
            error_msg = result.get("error", "Unknown error") if isinstance(result, dict) else "Failed to create incremental backup"
            return {"success": False, "error": f"Failed to create incremental backup: {error_msg}"}

        snapshot_full_name = result.get("snapshot_name", "")
        if not (isinstance(snapshot_full_name, str) and snapshot_full_name):
             return {"success": False, "error": "Incremental snapshot name not returned."}

        actions = [f"Created incremental backup: {snapshot_full_name}"]
        bookmark_success = await self.create_snapshot_bookmark(snapshot_full_name, f"{snapshot_name}_bookmark")
        if bookmark_success:
            actions.append(f"Created bookmark: {dataset_name}#{snapshot_name}_bookmark")

        return {"success": True, "executed_actions": actions}

    async def _execute_differential_backup(self, dataset_name: str, base_full: str, timestamp: str) -> Dict[str, Any]:
        """Helper to execute a differential backup."""
        snapshot_name = f"backup_diff_{timestamp}"
        success = await self.create_snapshot(dataset_name, snapshot_name)
        if not success:
            return {"success": False, "error": "Failed to create differential backup snapshot"}

        full_snapshot_name = f"{dataset_name}@{snapshot_name}"
        actions = [f"Created differential backup: {full_snapshot_name} (based on {base_full})"]

        bookmark_success = await self.create_snapshot_bookmark(full_snapshot_name, f"{snapshot_name}_bookmark")
        if bookmark_success:
            actions.append(f"Created bookmark: {dataset_name}#{snapshot_name}_bookmark")

        return {"success": True, "executed_actions": actions}

    async def _apply_retention_cleanup(self, dataset_name: str, retention_policy: Dict[str, int]) -> Dict[str, Any]:
        """Helper to apply retention policy and clean up old snapshots."""
        cleanup_result = await self.apply_snapshot_retention_policy(
            dataset_name,
            retention_policy.get("daily", 7),
            retention_policy.get("weekly", 4),
            retention_policy.get("monthly", 6),
            retention_policy.get("yearly", 2)
        )
        
        deleted_count = cleanup_result.get("deleted", 0)
        if not (isinstance(cleanup_result, dict) and isinstance(deleted_count, int) and deleted_count > 0):
            return {}

        return {
            "executed_actions": [f"Cleaned up {deleted_count} old snapshots"],
            "cleanup_result": cleanup_result
        }
    
    async def execute_backup_plan(self, dataset_name: str, backup_strategy: Dict[str, Union[str, Dict]], 
                                target_location: Optional[str] = None) -> Dict[str, Union[str, bool, List]]:
        """Execute a backup plan based on the provided strategy"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            strategy = backup_strategy.get("strategy", backup_strategy) if isinstance(backup_strategy, dict) else backup_strategy
            if not isinstance(strategy, dict):
                return {"success": False, "error": "Invalid backup strategy format"}
            
            results: Dict[str, Any] = { "dataset": dataset_name, "executed_actions": [], "success": True, "errors": [] }
            next_action = strategy.get("next_action", "")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_result = {}

            if next_action == "create_full_backup":
                backup_result = await self._execute_full_backup(dataset_name, timestamp)
            elif next_action == "create_incremental_backup":
                base_snapshot = strategy.get("latest_snapshot", "")
                backup_result = await self._execute_incremental_backup(dataset_name, base_snapshot, timestamp)
            elif next_action == "create_differential_backup":
                base_full = strategy.get("base_full_snapshot", "")
                backup_result = await self._execute_differential_backup(dataset_name, base_full, timestamp)

            if backup_result.get("success"):
                results["executed_actions"].extend(backup_result.get("executed_actions", []))
            else:
                results["success"] = False
                results["errors"].append(backup_result.get("error", "Unknown backup error"))

            if results["success"] and strategy.get("cleanup_needed", False):
                retention_policy = strategy.get("retention_policy", {})
                if isinstance(retention_policy, dict):
                    cleanup_actions = await self._apply_retention_cleanup(dataset_name, retention_policy)
                    if cleanup_actions:
                        results["executed_actions"].extend(cleanup_actions.get("executed_actions", []))
                        results["cleanup_result"] = cleanup_actions.get("cleanup_result")
            
            if target_location and results["success"]:
                results["executed_actions"].append(f"Backup plan ready for replication to {target_location}")
                results["replication_ready"] = True
            
            logger.info(f"Executed backup plan for {dataset_name}: {len(results['executed_actions'])} actions completed")
            
            return results
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for execute_backup_plan: {e}")
            return {"success": False, "error": "Security validation failed"}

    async def _restore_via_clone(self, backup_snapshot: str, target_dataset: str) -> Dict[str, Any]:
        """Helper to restore a backup via cloning."""
        returncode, _, stderr = await self.safe_run_zfs_command("clone", backup_snapshot, target_dataset)
        if returncode != 0:
            return {"success": False, "error": f"Failed to create clone: {stderr}"}
        
        logger.info(f"Successfully cloned {backup_snapshot} to {target_dataset}")
        return {"success": True, "action": f"Created clone {target_dataset} from backup {backup_snapshot}"}

    async def _restore_via_rollback(self, backup_snapshot: str, source_dataset: str) -> Dict[str, Any]:
        """Helper to restore a backup via rollback."""
        success = await self.rollback_to_snapshot(backup_snapshot, force=True)
        if not success:
            return {"success": False, "error": "Failed to rollback to backup snapshot"}

        logger.info(f"Successfully rolled back {source_dataset} to {backup_snapshot}")
        return {"success": True, "action": f"Rolled back {source_dataset} to backup {backup_snapshot}"}

    async def _restore_via_send_receive(self, backup_snapshot: str, target_dataset: str) -> Dict[str, Any]:
        """Helper to restore a backup via send/receive."""
        returncode, _, stderr = await self.safe_run_zfs_command("create", target_dataset)
        if returncode != 0 and "dataset already exists" not in stderr:
            return {"success": False, "error": f"Failed to create target dataset: {stderr}"}

        zfs_send_cmd = SecurityUtils.validate_zfs_command_args("send", backup_snapshot)
        zfs_receive_cmd = SecurityUtils.validate_zfs_command_args("receive", "-F", target_dataset)
        
        cmd = ["sh", "-c", f"{' '.join(zfs_send_cmd)} | {' '.join(zfs_receive_cmd)}"]
        
        returncode, _, stderr = await self.run_command(cmd)
        if returncode != 0:
            return {"success": False, "error": f"Failed to send/receive backup: {stderr}"}

        logger.info(f"Successfully restored {backup_snapshot} to {target_dataset}")
        return {"success": True, "action": f"Restored {backup_snapshot} to {target_dataset} via send/receive"}

    async def restore_from_backup(self, backup_snapshot: str, target_dataset: Optional[str] = None, 
                                restore_type: str = "clone") -> Dict[str, Union[str, bool]]:
        """Restore data from a backup snapshot using a strategy pattern."""
        try:
            if '@' not in backup_snapshot:
                raise SecurityValidationError("Invalid snapshot name format. Expected 'pool/dataset@snapshot'.")
            
            source_dataset = SecurityUtils.validate_dataset_name(backup_snapshot.split('@')[0])
            
            if not target_dataset:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                target_dataset = f"{source_dataset}_restore_{timestamp}"
            else:
                target_dataset = SecurityUtils.validate_dataset_name(target_dataset)

            returncode, _, _ = await self.safe_run_zfs_command("list", "-H", "-t", "snapshot", backup_snapshot)
            if returncode != 0:
                return {"success": False, "error": f"Backup snapshot '{backup_snapshot}' not found."}

            restore_handlers = {
                "clone": lambda: self._restore_via_clone(backup_snapshot, target_dataset),
                "rollback": lambda: self._restore_via_rollback(backup_snapshot, source_dataset),
                "send_receive": lambda: self._restore_via_send_receive(backup_snapshot, target_dataset)
            }

            if restore_type not in restore_handlers:
                return {"success": False, "error": f"Invalid restore type: {restore_type}"}
            
            result = await restore_handlers[restore_type]()
            
            return {
                "backup_snapshot": backup_snapshot,
                "target_dataset": target_dataset if restore_type != "rollback" else source_dataset,
                "restore_type": restore_type,
                "success": result.get("success", False),
                "action": result.get("action", ""),
                "error": result.get("error", "")
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for restore_from_backup: {e}")
            return {"success": False, "error": f"Security validation failed: {str(e)}"}
    
    async def verify_backup_integrity(self, backup_snapshot: str) -> Dict[str, Union[str, bool, int]]:
        """Verify the integrity of a backup snapshot"""
        try:
            # Validate snapshot name
            if '@' not in backup_snapshot:
                raise SecurityValidationError("Invalid snapshot name format")
            
            dataset_name = backup_snapshot.split('@')[0]
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            verification_result = {
                "backup_snapshot": backup_snapshot,
                "verification_time": datetime.now().isoformat(),
                "checks_performed": [],
                "issues_found": [],
                "overall_status": "unknown"
            }
            
            # Check 1: Verify snapshot exists
            returncode, _, _ = await self.safe_run_zfs_command("list", "-H", "-t", "snapshot", backup_snapshot)
            if returncode != 0:
                verification_result["issues_found"].append("Backup snapshot does not exist")
                verification_result["overall_status"] = "failed"
                return verification_result
            
            verification_result["checks_performed"].append("Snapshot existence check")
            
            # Check 2: Get snapshot properties and verify integrity
            snapshot_props = await self.get_dataset_properties(backup_snapshot, [
                "used", "referenced", "creation", "clones"
            ])
            
            if snapshot_props:
                verification_result["checks_performed"].append("Snapshot properties check")
                verification_result["properties"] = snapshot_props
                
                # Check if snapshot has reasonable size
                try:
                    used_bytes = self._parse_zfs_size(snapshot_props.get("used", "0"))
                    if used_bytes == 0:
                        verification_result["issues_found"].append("Snapshot reports zero used space")
                    else:
                        verification_result["size_bytes"] = used_bytes
                        verification_result["size_human"] = format_bytes(used_bytes)
                except ValueError:
                    verification_result["issues_found"].append("Could not parse snapshot size")
            else:
                verification_result["issues_found"].append("Could not retrieve snapshot properties")
            
            # Check 3: Verify parent dataset health
            parent_dataset = dataset_name
            pool_name = parent_dataset.split('/')[0]
            
            pool_health = await self.get_pool_health(pool_name)
            if pool_health and pool_health.get("healthy", False):
                verification_result["checks_performed"].append("Parent pool health check")
                verification_result["pool_healthy"] = True
            else:
                verification_result["issues_found"].append(f"Parent pool {pool_name} is not healthy")
                verification_result["pool_healthy"] = False
            
            # Check 4: Verify snapshot can be accessed (try to list its contents)
            try:
                # Get the mountpoint of the snapshot's .zfs/snapshot directory
                dataset_props = await self.get_dataset_properties(parent_dataset, ["mountpoint"])
                mountpoint = dataset_props.get("mountpoint")
                
                if mountpoint and mountpoint != "none" and mountpoint != "-":
                    snapshot_suffix = backup_snapshot.split('@')[1]
                    snapshot_path = f"{mountpoint}/.zfs/snapshot/{snapshot_suffix}"
                    
                    # Try to list the snapshot directory
                    returncode, stdout, stderr = await self.run_command(["ls", "-la", snapshot_path])
                    if returncode == 0:
                        verification_result["checks_performed"].append("Snapshot accessibility check")
                        verification_result["accessible"] = True
                    else:
                        verification_result["issues_found"].append(f"Cannot access snapshot contents: {stderr}")
                        verification_result["accessible"] = False
                else:
                    verification_result["checks_performed"].append("Snapshot accessibility check (skipped - no mountpoint)")
                    
            except Exception as e:
                verification_result["issues_found"].append(f"Error checking snapshot accessibility: {str(e)}")
            
            # Determine overall status
            if not verification_result["issues_found"]:
                verification_result["overall_status"] = "healthy"
            elif len(verification_result["issues_found"]) == 1 and "accessibility" in verification_result["issues_found"][0]:
                verification_result["overall_status"] = "warning"  # Snapshot exists but might not be mounted
            else:
                verification_result["overall_status"] = "failed"
            
            verification_result["issues_count"] = len(verification_result["issues_found"])
            verification_result["checks_count"] = len(verification_result["checks_performed"])
            
            logger.info(f"Verified backup integrity for {backup_snapshot}: {verification_result['overall_status']}")
            
            return verification_result
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for verify_backup_integrity: {e}")
            return {"success": False, "error": "Security validation failed"}
    
    # ===== ZFS Encryption Support =====
    
    async def create_encrypted_dataset(self, dataset_name: str, encryption_type: str = "aes-256-gcm", 
                                     key_format: str = "passphrase", key_location: Optional[str] = None) -> Dict[str, Union[str, bool]]:
        """Create an encrypted ZFS dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            if encryption_type not in ["aes-128-ccm", "aes-192-ccm", "aes-256-ccm", "aes-128-gcm", "aes-192-gcm", "aes-256-gcm"]:
                raise SecurityValidationError("Invalid encryption type")
            
            if key_format not in ["passphrase", "raw", "hex"]:
                raise SecurityValidationError("Invalid key format")
            
            # Check if dataset already exists
            returncode, _, _ = await self.safe_run_zfs_command("list", "-H", dataset_name)
            if returncode == 0:
                return {"success": False, "error": f"Dataset {dataset_name} already exists"}
            
            # Build create command with encryption
            create_args = [
                "create",
                "-o", f"encryption={encryption_type}",
                "-o", f"keyformat={key_format}"
            ]
            
            if key_location:
                # Validate key location path
                if not key_location.startswith("/") or ".." in key_location:
                    raise SecurityValidationError("Invalid key location path")
                create_args.extend(["-o", f"keylocation=file://{key_location}"])
            else:
                create_args.extend(["-o", "keylocation=prompt"])
            
            create_args.append(dataset_name)
            
            returncode, stdout, stderr = await self.safe_run_zfs_command(*create_args)
            
            if returncode != 0:
                return {"success": False, "error": f"Failed to create encrypted dataset: {stderr}"}
            
            logger.info(f"Created encrypted dataset: {dataset_name}")
            
            return {
                "success": True,
                "dataset": dataset_name,
                "encryption": encryption_type,
                "key_format": key_format,
                "key_location": key_location or "prompt"
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for create_encrypted_dataset: {e}")
            return {"success": False, "error": "Security validation failed"}
    
    async def get_encryption_status(self, dataset_name: str) -> Dict[str, Union[str, bool, Dict]]:
        """Get encryption status and properties for a dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Get encryption-related properties
            encryption_props = await self.get_dataset_properties(dataset_name, [
                "encryption", "encryptionroot", "keystatus", "keyformat", "keylocation"
            ])
            
            if not encryption_props:
                return {"success": False, "error": "Could not retrieve dataset properties"}
            
            encryption_status = {
                "dataset": dataset_name,
                "encrypted": encryption_props.get("encryption", "off") != "off",
                "encryption_algorithm": encryption_props.get("encryption", "none"),
                "encryption_root": encryption_props.get("encryptionroot", ""),
                "key_status": encryption_props.get("keystatus", "none"),
                "key_format": encryption_props.get("keyformat", "none"),
                "key_location": encryption_props.get("keylocation", "none")
            }
            
            # Determine if the dataset is ready for use
            encryption_status["ready_for_use"] = (
                encryption_status["key_status"] == "available" or 
                not encryption_status["encrypted"]
            )
            
            return {
                "success": True,
                "encryption_status": encryption_status
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for get_encryption_status: {e}")
            return {"success": False, "error": "Security validation failed"}
    
    async def load_encryption_key(self, dataset_name: str, key_file: Optional[str] = None) -> Dict[str, Union[str, bool]]:
        """Load encryption key for a dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Check if dataset is encrypted
            encryption_status = await self.get_encryption_status(dataset_name)
            if not isinstance(encryption_status, dict) or not encryption_status.get("success"):
                return {"success": False, "error": "Could not check encryption status"}
            
            enc_info = encryption_status.get("encryption_status", {})
            if not isinstance(enc_info, dict) or not enc_info.get("encrypted"):
                return {"success": False, "error": "Dataset is not encrypted"}
            
            if enc_info.get("key_status") == "available":
                return {"success": True, "message": "Key is already loaded"}
            
            # Load the key
            load_args = ["load-key"]
            
            if key_file:
                if not key_file.startswith("/") or ".." in key_file:
                    raise SecurityValidationError("Invalid key file path")
                load_args.extend(["-L", f"file://{key_file}"])
            
            load_args.append(dataset_name)
            
            returncode, stdout, stderr = await self.safe_run_zfs_command(*load_args)
            
            if returncode != 0:
                return {"success": False, "error": f"Failed to load encryption key: {stderr}"}
            
            logger.info(f"Loaded encryption key for dataset: {dataset_name}")
            
            return {
                "success": True,
                "dataset": dataset_name,
                "message": "Encryption key loaded successfully"
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for load_encryption_key: {e}")
            return {"success": False, "error": "Security validation failed"}
    
    async def unload_encryption_key(self, dataset_name: str) -> Dict[str, Union[str, bool]]:
        """Unload encryption key for a dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Check if dataset is encrypted
            encryption_status = await self.get_encryption_status(dataset_name)
            if not isinstance(encryption_status, dict) or not encryption_status.get("success"):
                return {"success": False, "error": "Could not check encryption status"}
            
            enc_info = encryption_status.get("encryption_status", {})
            if not isinstance(enc_info, dict) or not enc_info.get("encrypted"):
                return {"success": False, "error": "Dataset is not encrypted"}
            
            if enc_info.get("key_status") != "available":
                return {"success": True, "message": "Key is already unloaded"}
            
            returncode, stdout, stderr = await self.safe_run_zfs_command("unload-key", dataset_name)
            
            if returncode != 0:
                return {"success": False, "error": f"Failed to unload encryption key: {stderr}"}
            
            logger.info(f"Unloaded encryption key for dataset: {dataset_name}")
            
            return {
                "success": True,
                "dataset": dataset_name,
                "message": "Encryption key unloaded successfully"
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for unload_encryption_key: {e}")
            return {"success": False, "error": "Security validation failed"}
    
    async def change_encryption_key(self, dataset_name: str, new_key_file: Optional[str] = None) -> Dict[str, Union[str, bool]]:
        """Change encryption key for a dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Check if dataset is encrypted
            encryption_status = await self.get_encryption_status(dataset_name)
            if not isinstance(encryption_status, dict) or not encryption_status.get("success"):
                return {"success": False, "error": "Could not check encryption status"}
            
            enc_info = encryption_status.get("encryption_status", {})
            if not isinstance(enc_info, dict) or not enc_info.get("encrypted"):
                return {"success": False, "error": "Dataset is not encrypted"}
            
            change_args = ["change-key"]
            
            if new_key_file:
                if not new_key_file.startswith("/") or ".." in new_key_file:
                    raise SecurityValidationError("Invalid new key file path")
                change_args.extend(["-l", f"file://{new_key_file}"])
            
            change_args.append(dataset_name)
            
            returncode, stdout, stderr = await self.safe_run_zfs_command(*change_args)
            
            if returncode != 0:
                return {"success": False, "error": f"Failed to change encryption key: {stderr}"}
            
            logger.info(f"Changed encryption key for dataset: {dataset_name}")
            
            return {
                "success": True,
                "dataset": dataset_name,
                "message": "Encryption key changed successfully"
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for change_encryption_key: {e}")
            return {"success": False, "error": "Security validation failed"}
    
    # ===== ZFS Quota and Reservation Management =====
    
    async def set_quota(self, dataset_name: str, quota_size: str) -> Dict[str, Union[str, bool]]:
        """Set quota for a dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Validate quota size format (e.g., "10G", "1T", "500M")
            if not quota_size or quota_size == "none":
                quota_value = "none"
            else:
                # Simple validation for size format
                if not any(quota_size.endswith(unit) for unit in ["B", "K", "M", "G", "T", "P"]):
                    raise SecurityValidationError("Invalid quota size format")
                quota_value = quota_size
            
            returncode, stdout, stderr = await self.safe_run_zfs_command(
                "set", f"quota={quota_value}", dataset_name
            )
            
            if returncode != 0:
                return {"success": False, "error": f"Failed to set quota: {stderr}"}
            
            logger.info(f"Set quota for {dataset_name}: {quota_value}")
            
            return {
                "success": True,
                "dataset": dataset_name,
                "quota": quota_value
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for set_quota: {e}")
            return {"success": False, "error": "Security validation failed"}
    
    async def set_reservation(self, dataset_name: str, reservation_size: str) -> Dict[str, Union[str, bool]]:
        """Set reservation for a dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Validate reservation size format
            if not reservation_size or reservation_size == "none":
                reservation_value = "none"
            else:
                if not any(reservation_size.endswith(unit) for unit in ["B", "K", "M", "G", "T", "P"]):
                    raise SecurityValidationError("Invalid reservation size format")
                reservation_value = reservation_size
            
            returncode, stdout, stderr = await self.safe_run_zfs_command(
                "set", f"reservation={reservation_value}", dataset_name
            )
            
            if returncode != 0:
                return {"success": False, "error": f"Failed to set reservation: {stderr}"}
            
            logger.info(f"Set reservation for {dataset_name}: {reservation_value}")
            
            return {
                "success": True,
                "dataset": dataset_name,
                "reservation": reservation_value
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for set_reservation: {e}")
            return {"success": False, "error": "Security validation failed"}
    
    async def get_quota_usage(self, dataset_name: str) -> Dict[str, Union[str, bool, int, Dict]]:
        """Get quota and reservation usage for a ZFS dataset"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            # Get quota and reservation properties
            quota_props = await self.get_dataset_properties(dataset_name, [
                "quota", "used", "available", "reservation", "refreservation", "refquota"
            ])
            
            if not quota_props:
                return {"success": False, "error": "Could not retrieve dataset properties"}
            
            # Parse sizes to bytes for calculations
            used_bytes = self._parse_zfs_size(quota_props.get("used", "0"))
            available_bytes = self._parse_zfs_size(quota_props.get("available", "0"))
            
            quota_usage = {
                "dataset": dataset_name,
                "used": quota_props.get("used", "0"),
                "used_bytes": used_bytes,
                "used_human": format_bytes(used_bytes),
                "available": quota_props.get("available", "0"),
                "available_bytes": available_bytes,
                "available_human": format_bytes(available_bytes),
                "quota": quota_props.get("quota", "none"),
                "reservation": quota_props.get("reservation", "none"),
                "refreservation": quota_props.get("refreservation", "none"),
                "refquota": quota_props.get("refquota", "none")
            }
            
            # Calculate usage percentage if quota is set
            if quota_props.get("quota", "none") != "none":
                quota_bytes = self._parse_zfs_size(quota_props.get("quota", "0"))
                if quota_bytes > 0:
                    quota_usage["quota_bytes"] = quota_bytes
                    quota_usage["quota_human"] = format_bytes(quota_bytes)
                    quota_usage["quota_usage_percent"] = round((used_bytes / quota_bytes) * 100, 2)
            
            # Calculate reservation usage if reservation is set
            if quota_props.get("reservation", "none") != "none":
                reservation_bytes = self._parse_zfs_size(quota_props.get("reservation", "0"))
                if reservation_bytes > 0:
                    quota_usage["reservation_bytes"] = reservation_bytes
                    quota_usage["reservation_human"] = format_bytes(reservation_bytes)
                    quota_usage["reservation_usage_percent"] = round((used_bytes / reservation_bytes) * 100, 2)
            
            return {
                "success": True,
                "quota_usage": quota_usage
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for get_quota_usage: {e}")
            return {"success": False, "error": "Security validation failed"}
    
    async def manage_quota_alerts(self, dataset_name: str, warning_threshold: int = 80, 
                                critical_threshold: int = 95) -> Dict[str, Union[str, bool, List, Dict]]:
        """Manage quota alerts based on usage thresholds"""
        try:
            dataset_name = SecurityUtils.validate_dataset_name(dataset_name)
            
            quota_usage = await self.get_quota_usage(dataset_name)
            if not isinstance(quota_usage, dict) or not quota_usage.get("success"):
                return {"success": False, "error": "Could not retrieve quota usage"}
            
            usage_info = quota_usage.get("quota_usage", {})
            if not isinstance(usage_info, dict):
                return {"success": False, "error": "Invalid quota usage data"}
            
            quota_usage_percent = usage_info.get("quota_usage_percent", 0)
            
            alert_result = {
                "dataset": dataset_name,
                "quota_usage_percent": quota_usage_percent,
                "alerts": [],
                "alert_level": "ok"
            }
            
            if quota_usage_percent >= critical_threshold:
                alert_result["alerts"].append({
                    "level": "critical",
                    "message": f"Dataset {dataset_name} is at {quota_usage_percent}% of quota (critical threshold: {critical_threshold}%)",
                    "used": usage_info.get("used_human", ""),
                    "quota": usage_info.get("quota_human", "")
                })
                alert_result["alert_level"] = "critical"
            elif quota_usage_percent >= warning_threshold:
                alert_result["alerts"].append({
                    "level": "warning",
                    "message": f"Dataset {dataset_name} is at {quota_usage_percent}% of quota (warning threshold: {warning_threshold}%)",
                    "used": usage_info.get("used_human", ""),
                    "quota": usage_info.get("quota_human", "")
                })
                alert_result["alert_level"] = "warning"
            else:
                alert_result["alerts"].append({
                    "level": "ok",
                    "message": f"Dataset {dataset_name} quota usage is within acceptable limits: {quota_usage_percent}%",
                    "used": usage_info.get("used_human", ""),
                    "quota": usage_info.get("quota_human", "")
                })
            
            return {
                "success": True,
                "alert_result": alert_result
            }
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed for manage_quota_alerts: {e}")
            return {"success": False, "error": "Security validation failed"}

    async def safe_run_system_command(
            self, *args: str) -> tuple[int, str, str]:
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

            cmd = SecurityUtils.validate_system_command_args(
                command, *command_args)
            return await self.run_command(cmd)
        except SecurityValidationError:
            return 1, "", "Security validation failed"

    async def force_unmount_dataset(
            self,
            target_host: str,
            dataset_path: str,
            ssh_user: str = "root",
            ssh_port: int = 22) -> bool:
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
            dataset_path = SecurityUtils.sanitize_path(
                dataset_path, allow_absolute=True)

            logger.info(
                f"Attempting to force unmount {dataset_path} on {target_host}")

            # Step 1: Check if the path is actually mounted
            mountpoint_cmd = SecurityUtils.validate_system_command_args(
                "mountpoint", dataset_path)
            mountpoint_cmd_str = " ".join(mountpoint_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(
                target_host, ssh_user, ssh_port, mountpoint_cmd_str)

            returncode, stdout, stderr = await self.run_command(ssh_cmd)
            if returncode != 0:
                logger.info(
                    f"Path {dataset_path} is not mounted on {target_host}")
                return True  # Not mounted, so unmount "succeeded"

            # Step 2: Use lsof to find processes with open files in the dataset
            logger.info(f"Finding processes with open files in {dataset_path}")
            lsof_cmd = SecurityUtils.validate_system_command_args(
                "lsof", "+D", dataset_path)
            lsof_cmd_str = " ".join(lsof_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(
                target_host, ssh_user, ssh_port, lsof_cmd_str)

            returncode, lsof_stdout, lsof_stderr = await self.run_command(ssh_cmd)
            if returncode == 0 and lsof_stdout.strip():
                logger.warning(
                    f"Found processes with open files in {dataset_path}:")
                logger.warning(lsof_stdout.strip())

            # Step 3: Use fuser to find processes using the dataset
            logger.info(
                f"Finding processes using {dataset_path} on {target_host}")
            fuser_cmd = SecurityUtils.validate_system_command_args(
                "fuser", "-mv", dataset_path)
            fuser_cmd_str = " ".join(fuser_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(
                target_host, ssh_user, ssh_port, fuser_cmd_str)

            returncode, fuser_stdout, fuser_stderr = await self.run_command(ssh_cmd)
            if returncode == 0 and fuser_stdout.strip():
                logger.warning(
                    f"Found processes using {dataset_path}: {fuser_stdout.strip()}")

                # Step 4: Kill processes using the dataset (SIGTERM first)
                logger.info(
                    f"Attempting to kill processes using {dataset_path} with SIGTERM")
                fuser_kill_cmd = SecurityUtils.validate_system_command_args(
                    "fuser", "-km", dataset_path)
                fuser_kill_cmd_str = " ".join(fuser_kill_cmd)
                ssh_cmd = SecurityUtils.build_ssh_command(
                    target_host, ssh_user, ssh_port, fuser_kill_cmd_str)

                await self.run_command(ssh_cmd)

                # Wait a moment for processes to exit
                logger.info("Waiting for processes to exit gracefully...")
                await asyncio.sleep(3)

                # Step 5: Check if any processes are still there
                returncode, fuser_stdout, _ = await self.run_command(ssh_cmd)
                if returncode == 0 and fuser_stdout.strip():
                    logger.warning(
                        f"Some processes still using {dataset_path}, using SIGKILL")
                    fuser_kill9_cmd = SecurityUtils.validate_system_command_args(
                        "fuser", "-9km", dataset_path)
                    fuser_kill9_cmd_str = " ".join(fuser_kill9_cmd)
                    ssh_cmd = SecurityUtils.build_ssh_command(
                        target_host, ssh_user, ssh_port, fuser_kill9_cmd_str)

                    await self.run_command(ssh_cmd)

                    # Wait for cleanup
                    await asyncio.sleep(2)

            # Step 6: Try to unmount gracefully first
            logger.info(f"Attempting graceful unmount of {dataset_path}")
            umount_cmd = SecurityUtils.validate_system_command_args(
                "umount", dataset_path)
            umount_cmd_str = " ".join(umount_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(
                target_host, ssh_user, ssh_port, umount_cmd_str)

            returncode, stdout, stderr = await self.run_command(ssh_cmd)
            if returncode == 0:
                logger.info(
                    f"Successfully unmounted {dataset_path} on {target_host}")
                return True

            # Step 7: Try force unmount
            logger.info(
                f"Graceful unmount failed, attempting force unmount of {dataset_path}")
            umount_force_cmd = SecurityUtils.validate_system_command_args(
                "umount", "-f", dataset_path)
            umount_force_cmd_str = " ".join(umount_force_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(
                target_host, ssh_user, ssh_port, umount_force_cmd_str)

            returncode, stdout, stderr = await self.run_command(ssh_cmd)
            if returncode == 0:
                logger.info(
                    f"Successfully force unmounted {dataset_path} on {target_host}")
                return True

            # Step 8: Last resort - lazy unmount
            logger.warning(
                f"Force unmount failed, trying lazy unmount of {dataset_path}")
            umount_lazy_cmd = SecurityUtils.validate_system_command_args(
                "umount", "-l", dataset_path)
            umount_lazy_cmd_str = " ".join(umount_lazy_cmd)
            ssh_cmd = SecurityUtils.build_ssh_command(
                target_host, ssh_user, ssh_port, umount_lazy_cmd_str)

            returncode, stdout, stderr = await self.run_command(ssh_cmd)
            if returncode == 0:
                logger.info(
                    f"Successfully lazy unmounted {dataset_path} on {target_host}")
                return True
            else:
                logger.error(
                    f"All unmount attempts failed for {dataset_path}: {stderr}")
                return False

        except SecurityValidationError as e:
            logger.error(f"Security validation failed for force unmount: {e}")
            return False
        except Exception as e:
            logger.error(f"Error during force unmount of {dataset_path}: {e}")
            return False
