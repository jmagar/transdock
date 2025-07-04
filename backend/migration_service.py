import asyncio
import json
import os
import uuid
import logging
import yaml
from datetime import datetime
from typing import Dict, List, Any
from .models import MigrationRequest, MigrationStatus, TransferMethod
from .zfs_ops import ZFSOperations
from .docker_ops import DockerOperations
from .transfer_ops import TransferOperations
from .security_utils import SecurityUtils, SecurityValidationError

logger = logging.getLogger(__name__)


class MigrationService:
    def __init__(self):
        self.zfs_ops = ZFSOperations()
        self.docker_ops = DockerOperations()
        # Pass ZFS operations to transfer operations to avoid duplication
        self.transfer_ops = TransferOperations(zfs_ops=self.zfs_ops)
        self.active_migrations: Dict[str, MigrationStatus] = {}

    def create_migration_id(self) -> str:
        """Generate a unique migration ID"""
        return str(uuid.uuid4())

    async def start_migration(self, request: MigrationRequest) -> str:
        """Start a new migration process"""
        migration_id = self.create_migration_id()

        # Validate all input parameters for security
        try:
            SecurityUtils.validate_migration_request(
                request.compose_dataset,
                request.target_host,
                request.ssh_user,
                request.ssh_port,
                request.target_base_path
            )
        except SecurityValidationError as e:
            raise ValueError(f"Security validation failed: {e}") from e

        # Initialize migration status
        status = MigrationStatus(
            id=migration_id,
            status="initializing",
            progress=0,
            message="Starting migration process",
            compose_dataset=request.compose_dataset,
            target_host=request.target_host,
            target_base_path=request.target_base_path
        )

        self.active_migrations[migration_id] = status

        # Start the migration process in the background
        asyncio.create_task(self._execute_migration(migration_id, request))

        return migration_id

    async def get_migration_status(
            self, migration_id: str) -> MigrationStatus | None:
        """Get the status of a migration"""
        return self.active_migrations.get(migration_id)

    async def list_migrations(self) -> List[MigrationStatus]:
        """List all migrations"""
        return list(self.active_migrations.values())

    async def _update_status(
            self,
            migration_id: str,
            status: str,
            progress: int,
            message: str):
        """Update migration status"""
        if migration_id in self.active_migrations:
            self.active_migrations[migration_id].status = status
            self.active_migrations[migration_id].progress = progress
            self.active_migrations[migration_id].message = message
            logger.info(f"Migration {migration_id}: {message} ({progress}%)")

    async def _update_error(self, migration_id: str, error: str):
        """Update migration with error"""
        if migration_id in self.active_migrations:
            self.active_migrations[migration_id].status = "failed"
            self.active_migrations[migration_id].error = error
            logger.error(f"Migration {migration_id} failed: {error}")

    async def _execute_migration(
            self,
            migration_id: str,
            request: MigrationRequest):
        """Execute the complete migration process"""
        try:
            # Step 1: Validate inputs and check ZFS availability
            await self._update_status(migration_id, "validating", 5, "Validating inputs and checking ZFS")

            if not await self.zfs_ops.is_zfs_available():
                raise Exception("ZFS is not available on the source system")

            # Get compose directory path
            compose_dir = self.docker_ops.get_compose_path(
                request.compose_dataset)
            if not os.path.exists(compose_dir):
                raise Exception(f"Compose dataset not found: {compose_dir}")

            # Step 2: Find and parse compose file
            await self._update_status(migration_id, "parsing", 10, "Parsing docker-compose file")

            compose_file = await self.docker_ops.find_compose_file(compose_dir)
            if not compose_file:
                raise Exception(
                    f"No docker-compose file found in {compose_dir}")

            compose_data = await self.docker_ops.parse_compose_file(compose_file)

            # Step 3: Extract volume mounts
            await self._update_status(migration_id, "analyzing", 15, "Analyzing volume mounts")

            volumes = await self.docker_ops.extract_volume_mounts(compose_data)
            self.active_migrations[migration_id].volumes = volumes

            logger.info(
                f"Found {len(volumes)} volume mounts for migration {migration_id}")

            # Step 4: Stop the compose stack
            await self._update_status(migration_id, "stopping", 20, "Stopping Docker compose stack")

            if not await self.docker_ops.stop_compose_stack(compose_dir):
                raise Exception("Failed to stop Docker compose stack")

            # Step 5: Create snapshots for compose and volume datasets
            await self._update_status(migration_id, "snapshotting", 25, "Creating ZFS snapshots")

            snapshots = []
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Snapshot the compose dataset
            if not await self.zfs_ops.is_dataset(compose_dir) and not await self.zfs_ops.create_dataset(compose_dir):
                raise Exception(f"Failed to convert {compose_dir} to dataset")

            compose_snapshot = await self.zfs_ops.create_snapshot(compose_dir, f"migration_{timestamp}")
            snapshots.append((compose_snapshot, compose_dir))

            # Process each volume mount
            for i, volume in enumerate(volumes):
                progress = 25 + (i + 1) * (35 / len(volumes))
                await self._update_status(
                    migration_id, "snapshotting", int(progress),
                    f"Creating snapshot for {volume.source}"
                )

                # Check if volume source is a dataset, convert if not
                if not await self.zfs_ops.is_dataset(volume.source) and not await self.zfs_ops.create_dataset(volume.source):
                    logger.warning(
                        f"Failed to convert {volume.source} to dataset, skipping...")
                    continue

                # Create snapshot
                volume_snapshot = await self.zfs_ops.create_snapshot(volume.source, f"migration_{timestamp}")
                snapshots.append((volume_snapshot, volume.source))
                volume.is_dataset = True
                volume.dataset_path = await self.zfs_ops.get_dataset_name(volume.source)

            # Step 6: Determine transfer method
            await self._update_status(migration_id, "checking", 60, "Checking target system capabilities")

            has_remote_zfs = await self.zfs_ops.check_remote_zfs(
                request.target_host, request.ssh_user, request.ssh_port
            )

            if request.force_rsync or not has_remote_zfs:
                transfer_method = TransferMethod.RSYNC
                await self._update_status(migration_id, "preparing", 65, "Preparing rsync transfer")
            else:
                transfer_method = TransferMethod.ZFS_SEND
                await self._update_status(migration_id, "preparing", 65, "Preparing ZFS send transfer")

            self.active_migrations[migration_id].transfer_method = transfer_method

            # Step 7: Create volume path mapping
            volume_mapping = await self.transfer_ops.create_volume_mapping(volumes, request.target_base_path)

            # Safely create compose target path to prevent path traversal
            compose_basename = os.path.basename(compose_dir)
            compose_target_path = SecurityUtils.sanitize_path(
                os.path.join(
                    request.target_base_path,
                    "compose",
                    compose_basename),
                allow_absolute=True)

            # Add compose directory to mapping
            volume_mapping[compose_dir] = compose_target_path

            # Step 8: Transfer data
            await self._update_status(migration_id, "transferring", 70, "Transferring data to target")

            for i, (snapshot_name, source_path) in enumerate(snapshots):
                progress = 70 + (i + 1) * (20 / len(snapshots))

                if source_path == compose_dir:
                    target_path = compose_target_path
                    description = "compose files"
                else:
                    target_path = volume_mapping.get(
                        source_path,
                        f"{request.target_base_path}/volumes/{os.path.basename(source_path)}")
                    description = f"volume {os.path.basename(source_path)}"

                await self._update_status(
                    migration_id, "transferring", int(progress),
                    f"Transferring {description}"
                )

                # Execute transfer based on method
                if transfer_method == TransferMethod.ZFS_SEND:
                    # Convert target path to proper ZFS dataset name (keep
                    # slashes)
                    if target_path.startswith("/mnt/"):
                        target_dataset = target_path[5:]  # Remove /mnt/ prefix
                    else:
                        target_dataset = target_path.replace(
                            f"{request.target_base_path}/", "")

                    success = await self.zfs_ops.send_snapshot(
                        snapshot_name, request.target_host, target_dataset,
                        request.ssh_user, request.ssh_port
                    )
                else:  # RSYNC
                    success = await self.transfer_ops.transfer_via_rsync(
                        source_path, request.target_host, target_path,
                        request.ssh_user, request.ssh_port
                    )

                if not success:
                    raise Exception(f"Failed to transfer {source_path}")

            # Step 9: Generate updated docker-compose file
            await self._update_status(migration_id, "generating", 90, "Generating updated compose file")

            updated_compose = await self.docker_ops.update_compose_paths(compose_data, volume_mapping)

            # Step 10: Save updated compose file on target
            await self._update_status(migration_id, "finalizing", 95, "Saving updated compose configuration")

            # Write updated compose file
            target_compose_file = os.path.join(
                compose_target_path, "docker-compose.yml")

            # Use secure file operations
            success = await self.transfer_ops.write_remote_file(
                request.target_host, target_compose_file, updated_compose,
                request.ssh_user, request.ssh_port
            )

            if not success:
                raise Exception("Failed to save updated compose file")

            # Step 11: Clean up snapshots
            await self._update_status(migration_id, "cleaning", 97, "Cleaning up snapshots")

            for snapshot_name, _ in snapshots:
                await self.zfs_ops.cleanup_snapshot(snapshot_name)

            # Step 12: Start the stack on target system
            await self._update_status(migration_id, "starting", 98, "Starting stack on target system")

            stack_started = await self.docker_ops.start_compose_stack_remote(
                request.target_host, compose_target_path, request.ssh_user, request.ssh_port
            )

            if not stack_started:
                logger.warning(
                    f"Failed to start stack on target system for migration {migration_id}")
                # Don't fail the migration, just log warning

            # Step 13: Verify migration success
            await self._update_status(migration_id, "verifying", 99, "Verifying migration success")

            verification_success = await self._verify_migration_success(
                migration_id, request, compose_target_path, volume_mapping
            )

            if not verification_success:
                logger.warning(
                    f"Migration verification failed for {migration_id}")
                # Log warning but don't fail the migration

            # Step 14: Complete migration
            await self._update_status(migration_id, "completed", 100, "Migration completed successfully")

            # Store final configuration
            self.active_migrations[migration_id].target_compose_path = compose_target_path
            self.active_migrations[migration_id].volume_mapping = volume_mapping
            self.active_migrations[migration_id].snapshots = [
                snapshot_name for snapshot_name, _ in snapshots]

            logger.info(f"Migration {migration_id} completed successfully")

        except Exception as e:
            await self._update_error(migration_id, str(e))
            logger.exception(f"Migration {migration_id} failed")

    async def _verify_migration_success(self,
                                        migration_id: str,
                                        request: MigrationRequest,
                                        compose_target_path: str,
                                        volume_mapping: Dict[str,
                                                             str]) -> bool:
        """
        Verify that the migration was successful by checking the target system.

        Args:
            migration_id: ID of the migration
            request: Original migration request
            compose_target_path: Path to the compose file on target
            volume_mapping: Mapping of old paths to new paths

        Returns:
            bool: True if verification successful, False otherwise
        """
        try:
            logger.info(
                f"Verifying migration {migration_id} on target system {request.target_host}")

            # Step 1: Get running containers and parse their names
            logger.info(f"Checking container status on {request.target_host}")
            # Get container names in parseable format
            docker_ps_cmd_str = "docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'"

            ssh_cmd = SecurityUtils.build_ssh_command(
                request.target_host, request.ssh_user, request.ssh_port, docker_ps_cmd_str)

            returncode, stdout, stderr = await self.docker_ops.run_command(ssh_cmd)
            if returncode != 0:
                logger.error(f"Failed to check container status: {stderr}")
                return False

            # Parse actual container names from docker ps output
            running_containers = {}
            for line in stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        container_name = parts[0]
                        container_status = parts[1]
                        container_ports = parts[2]
                        running_containers[container_name] = {
                            'status': container_status,
                            'ports': container_ports
                        }

            logger.info(f"Found {len(running_containers)} running containers:")
            for name, info in running_containers.items():
                logger.info(f"  {name}: {info['status']} - {info['ports']}")

            # Step 2: Get container names from compose file
            try:
                # Parse compose file to get service names
                compose_file_path = os.path.join(
                    compose_target_path, "docker-compose.yml")

                # Read the compose file from target
                cat_cmd = ["cat", compose_file_path]
                cat_cmd_str = " ".join(cat_cmd)
                ssh_cmd = SecurityUtils.build_ssh_command(
                    request.target_host, request.ssh_user, request.ssh_port, cat_cmd_str)

                returncode, compose_content, stderr = await self.docker_ops.run_command(ssh_cmd)
                if returncode != 0:
                    logger.error(
                        f"Failed to read compose file from target: {stderr}")
                    return False

                # Parse compose file to get service names
                compose_data = yaml.safe_load(compose_content)
                services = compose_data.get('services', {})

                # Step 3: Match running containers to services and inspect them
                verification_success = True
                project_name = os.path.basename(compose_target_path)

                for service_name in services.keys():
                    logger.info(
                        f"Looking for container for service '{service_name}'")

                    # Try different naming patterns Docker Compose might use
                    possible_names = [
                        f"{project_name}_{service_name}_1",  # Old format
                        # New format with dashes
                        f"{project_name}-{service_name}-1",
                        f"{project_name}_{service_name}",    # Without number
                        # New format without number
                        f"{project_name}-{service_name}",
                        service_name,                        # Just service name
                        # Just project name (single service)
                        project_name
                    ]

                    # Find the actual container name
                    actual_container_name = None
                    for possible_name in possible_names:
                        if possible_name in running_containers:
                            actual_container_name = possible_name
                            break

                    if not actual_container_name:
                        logger.warning(
                            f"⚠️  No running container found for service '{service_name}'")
                        logger.warning(
                            f"   Tried: {', '.join(possible_names)}")
                        logger.warning(
                            f"   Available: {', '.join(running_containers.keys())}")
                        verification_success = False
                        continue

                    logger.info(
                        f"Found container '{actual_container_name}' for service '{service_name}'")

                    # Use docker inspect to get detailed container info
                    inspect_cmd = ["docker", "inspect", actual_container_name]
                    inspect_cmd_str = " ".join(inspect_cmd)
                    ssh_cmd = SecurityUtils.build_ssh_command(
                        request.target_host, request.ssh_user, request.ssh_port, inspect_cmd_str)

                    returncode, inspect_output, stderr = await self.docker_ops.run_command(ssh_cmd)
                    if returncode == 0:
                        try:
                            container_info = json.loads(inspect_output)

                            if container_info and len(container_info) > 0:
                                container = container_info[0]

                                # Check if container is running
                                state = container.get('State', {})
                                if state.get('Running', False):
                                    logger.info(
                                        f"✅ Container {actual_container_name} is running")
                                else:
                                    logger.error(
                                        f"❌ Container {actual_container_name} is not running")
                                    verification_success = False

                                # Check volume mounts
                                mounts = container.get('Mounts', [])
                                logger.info(
                                    f"Volume mounts for {actual_container_name}:")
                                for mount in mounts:
                                    source = mount.get('Source', '')
                                    destination = mount.get('Destination', '')
                                    mount_type = mount.get('Type', '')
                                    logger.info(
                                        f"  {mount_type}: {source} -> {destination}")

                                    # Verify that the source path is using the
                                    # new migrated path
                                    if mount_type == 'bind':
                                        # Check if this mount uses one of our
                                        # migrated paths
                                        for old_path, new_path in volume_mapping.items():
                                            if new_path in source:
                                                logger.info(
                                                    f"✅ Volume mount using migrated path: {source}")
                                                break

                                # Check network configuration
                                networks = container.get(
                                    'NetworkSettings', {}).get(
                                    'Networks', {})
                                for network_name, network_info in networks.items():
                                    ip_address = network_info.get(
                                        'IPAddress', 'N/A')
                                    logger.info(
                                        f"Network {network_name}: {ip_address}")

                            else:
                                logger.error(
                                    f"❌ No container info found for {actual_container_name}")
                                verification_success = False

                        except json.JSONDecodeError as e:
                            logger.error(
                                f"Failed to parse docker inspect output: {e}")
                            verification_success = False
                    else:
                        logger.error(
                            f"❌ Failed to inspect container {actual_container_name}: {stderr}")
                        verification_success = False

                return verification_success

            except Exception as e:
                logger.error(f"Error during container verification: {e}")
                return False

        except Exception as e:
            logger.error(f"Error during migration verification: {e}")
            return False

    async def cancel_migration(self, migration_id: str) -> bool:
        """Cancel a running migration"""
        if migration_id not in self.active_migrations:
            raise KeyError("Migration not found")

        status = self.active_migrations[migration_id]

        # Only allow cancellation of running migrations
        if status.status in ["completed", "failed", "cancelled"]:
            return False

        # Update status to cancelled
        await self._update_status(migration_id, "cancelled", status.progress, "Migration cancelled by user")

        logger.info(f"Cancelled migration {migration_id}")
        return True

    async def cleanup_migration(self, migration_id: str) -> bool:
        """Clean up migration resources"""
        if migration_id not in self.active_migrations:
            return False

        status = self.active_migrations[migration_id]

        # Clean up any remaining snapshots
        if hasattr(status, 'snapshots'):
            for snapshot_name in status.snapshots:
                await self.zfs_ops.cleanup_snapshot(snapshot_name)

        # Remove from active migrations
        del self.active_migrations[migration_id]

        logger.info(f"Cleaned up migration {migration_id}")
        return True

    async def get_system_info(self) -> Dict[str, Any]:
        """Get system information relevant to migrations"""
        import platform
        import subprocess

        # Basic system info - using Union type for mixed value types
        info: Dict[str, str | bool | None] = {
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
                # Get ZFS version if available
                try:
                    validated_cmd = SecurityUtils.validate_zfs_command_args(
                        "version")
                    returncode, stdout, stderr = await self.zfs_ops.run_command(validated_cmd)
                    if returncode == 0 and stdout:
                        # Extract version from first line
                        first_line = stdout.strip().split('\n')[0]
                        if 'zfs-' in first_line:
                            info["zfs_version"] = first_line.split(
                                'zfs-')[1].split()[0]
                        else:
                            info["zfs_version"] = "unknown"
                    else:
                        info["zfs_version"] = "unknown"
                except Exception:
                    info["zfs_version"] = "unknown"
            else:
                info["zfs_version"] = None
        except Exception:
            info["zfs_available"] = False
            info["zfs_version"] = None

        # Add configuration paths
        info["compose_base"] = self.docker_ops.compose_base_path
        info["appdata_base"] = self.docker_ops.appdata_base_path
        info["zfs_pool"] = os.getenv(
            "TRANSDOCK_ZFS_POOL",
            "cache")  # Default ZFS pool name for Unraid

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
            version = None
            try:
                validated_cmd = SecurityUtils.validate_zfs_command_args(
                    "version")
                returncode, stdout, stderr = await self.zfs_ops.run_command(validated_cmd)
                if returncode == 0 and stdout:
                    first_line = stdout.strip().split('\n')[0]
                    if 'zfs-' in first_line:
                        version = first_line.split('zfs-')[1].split()[0]
            except Exception:
                version = "unknown"

            # Get pool list
            pools = []
            try:
                validated_cmd = SecurityUtils.validate_zfs_command_args(
                    "list", "-H", "-o", "name", "-t", "filesystem")
                returncode, stdout, stderr = await self.zfs_ops.run_command(validated_cmd)
                if returncode == 0:
                    for line in stdout.strip().split('\n'):
                        if line.strip() and '/' not in line:  # Only root pools
                            pools.append(line.strip())
            except Exception:
                pools = []

            return {
                "available": True,
                "version": version,
                "pools": pools
            }
        except Exception:
            return {
                "available": False,
                "version": None,
                "pools": []
            }

    def _is_valid_stack_name(self, name: str) -> bool:
        """Validate stack name for security."""
        if not name or len(name) > 64:
            return False
        return str(name).replace(
            '-',
            '').replace(
            '_',
            '').replace(
            '.',
            '').isalnum()

    async def get_compose_stacks(self) -> List[Dict[str, str]]:
        """Get list of available Docker Compose stacks"""
        try:
            stacks = []
            compose_base = self.docker_ops.compose_base_path

            # Validate base path for security
            validated_base = SecurityUtils.sanitize_path(
                compose_base, allow_absolute=True)

            if os.path.exists(validated_base):
                for item in os.listdir(validated_base):
                    # Validate each stack name
                    try:
                        if not self._is_valid_stack_name(item):
                            continue

                        stack_path = SecurityUtils.sanitize_path(os.path.join(
                            validated_base, item), validated_base, allow_absolute=True)

                        if os.path.isdir(stack_path):
                            compose_file = await self.docker_ops.find_compose_file(stack_path)
                            if compose_file:
                                stacks.append({
                                    "name": item,
                                    "compose_file": compose_file
                                })
                    except SecurityValidationError:
                        # Skip invalid stack names silently
                        continue

            return stacks
        except Exception:
            return []

    async def get_stack_info(self, stack_name: str) -> Dict[str, Any]:
        """Get detailed information about a specific compose stack"""
        # Validate stack name for security
        if not stack_name or len(stack_name) > 64:
            raise ValueError("Invalid stack name length")
        if not str(stack_name).replace(
            '-',
            '').replace(
            '_',
            '').replace(
            '.',
                '').isalnum():
            raise ValueError("Stack name contains invalid characters")

        compose_base = SecurityUtils.sanitize_path(
            self.docker_ops.compose_base_path, allow_absolute=True)
        stack_path = SecurityUtils.sanitize_path(
            os.path.join(
                compose_base,
                stack_name),
            compose_base,
            allow_absolute=True)

        if not os.path.exists(stack_path):
            raise FileNotFoundError("Compose stack not found")

        compose_file = await self.docker_ops.find_compose_file(stack_path)
        if not compose_file:
            raise FileNotFoundError("No compose file found in stack")

        compose_data = await self.docker_ops.parse_compose_file(compose_file)
        volumes = await self.docker_ops.extract_volume_mounts(compose_data)

        # Check if volumes are datasets
        for volume in volumes:
            volume.is_dataset = await self.zfs_ops.is_dataset(volume.source)
            if volume.is_dataset:
                volume.dataset_path = await self.zfs_ops.get_dataset_name(volume.source)

        return {"name": stack_name,
                "compose_file": compose_file,
                "volumes": [{"source": v.source,
                             "target": v.target,
                             "is_dataset": v.is_dataset} for v in volumes],
                "services": list(compose_data.get('services',
                                                  {}).keys())}
