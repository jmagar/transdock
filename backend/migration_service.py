import asyncio
import os
import uuid
import logging
import tempfile
import yaml
from datetime import datetime
from typing import Dict, List, Optional
from .models import MigrationRequest, MigrationStatus, VolumeMount, TransferMethod
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
    
    async def get_migration_status(self, migration_id: str) -> Optional[MigrationStatus]:
        """Get the status of a migration"""
        return self.active_migrations.get(migration_id)
    
    async def list_migrations(self) -> List[MigrationStatus]:
        """List all migrations"""
        return list(self.active_migrations.values())
    
    async def _update_status(self, migration_id: str, status: str, progress: int, message: str):
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
    
    async def _execute_migration(self, migration_id: str, request: MigrationRequest):
        """Execute the complete migration process"""
        try:
            # Step 1: Validate inputs and check ZFS availability
            await self._update_status(migration_id, "validating", 5, "Validating inputs and checking ZFS")
            
            if not await self.zfs_ops.is_zfs_available():
                raise Exception("ZFS is not available on the source system")
            
            # Get compose directory path
            compose_dir = self.docker_ops.get_compose_path(request.compose_dataset)
            if not os.path.exists(compose_dir):
                raise Exception(f"Compose dataset not found: {compose_dir}")
            
            # Step 2: Find and parse compose file
            await self._update_status(migration_id, "parsing", 10, "Parsing docker-compose file")
            
            compose_file = await self.docker_ops.find_compose_file(compose_dir)
            if not compose_file:
                raise Exception(f"No docker-compose file found in {compose_dir}")
            
            compose_data = await self.docker_ops.parse_compose_file(compose_file)
            
            # Step 3: Extract volume mounts
            await self._update_status(migration_id, "analyzing", 15, "Analyzing volume mounts")
            
            volumes = await self.docker_ops.extract_volume_mounts(compose_data)
            self.active_migrations[migration_id].volumes = volumes
            
            logger.info(f"Found {len(volumes)} volume mounts for migration {migration_id}")
            
            # Step 4: Stop the compose stack
            await self._update_status(migration_id, "stopping", 20, "Stopping Docker compose stack")
            
            if not await self.docker_ops.stop_compose_stack(compose_dir):
                raise Exception("Failed to stop Docker compose stack")
            
            # Step 5: Create snapshots for compose and volume datasets
            await self._update_status(migration_id, "snapshotting", 25, "Creating ZFS snapshots")
            
            snapshots = []
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Snapshot the compose dataset
            if not await self.zfs_ops.is_dataset(compose_dir):
                if not await self.zfs_ops.create_dataset(compose_dir):
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
                if not await self.zfs_ops.is_dataset(volume.source):
                    if not await self.zfs_ops.create_dataset(volume.source):
                        logger.warning(f"Failed to convert {volume.source} to dataset, skipping...")
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
                os.path.join(request.target_base_path, "compose", compose_basename)
            )
            
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
                    target_path = volume_mapping.get(source_path, f"{request.target_base_path}/volumes/{os.path.basename(source_path)}")
                    description = f"volume {os.path.basename(source_path)}"
                
                await self._update_status(
                    migration_id, "transferring", int(progress),
                    f"Transferring {description}"
                )
                
                # Execute transfer based on method
                if transfer_method == TransferMethod.ZFS_SEND:
                    dataset_name = await self.zfs_ops.get_dataset_name(source_path)
                    target_dataset = target_path.replace(f"{request.target_base_path}/", "").replace("/", "_")
                    
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
            
            # Write compose file to temporary location first
            temp_compose_file = None
            try:
                # Create temporary compose file with original content
                with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
                    yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)
                    temp_compose_file = f.name
                
                # Update the compose file paths
                success = await self.docker_ops.update_compose_file_paths(temp_compose_file, volume_mapping)
                if not success:
                    raise Exception("Failed to update compose file paths")
                
                # Read the updated content
                with open(temp_compose_file, 'r') as f:
                    updated_compose = f.read()
                    
            finally:
                # Clean up temporary file
                if temp_compose_file and os.path.exists(temp_compose_file):
                    os.unlink(temp_compose_file)
            
            # Step 10: Save updated compose file on target
            await self._update_status(migration_id, "finalizing", 95, "Saving updated compose configuration")
            
            # Write updated compose file
            target_compose_file = os.path.join(compose_target_path, "docker-compose.yml")
            
            # Use secure file operations
            success = await self.transfer_ops.write_remote_file(
                request.target_host, target_compose_file, updated_compose,
                request.ssh_user, request.ssh_port
            )
            
            if not success:
                raise Exception("Failed to save updated compose file")
            
            # Step 11: Clean up snapshots
            await self._update_status(migration_id, "cleaning", 98, "Cleaning up snapshots")
            
            for snapshot_name, _ in snapshots:
                await self.zfs_ops.cleanup_snapshot(snapshot_name)
            
            # Step 12: Complete migration
            await self._update_status(migration_id, "completed", 100, "Migration completed successfully")
            
            # Store final configuration
            self.active_migrations[migration_id].target_compose_path = compose_target_path
            self.active_migrations[migration_id].volume_mapping = volume_mapping
            self.active_migrations[migration_id].snapshots = [snapshot_name for snapshot_name, _ in snapshots]
            
            logger.info(f"Migration {migration_id} completed successfully")
            
        except Exception as e:
            await self._update_error(migration_id, str(e))
            logger.exception(f"Migration {migration_id} failed")
    
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