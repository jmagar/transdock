import asyncio
import os
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional
from models import MigrationRequest, MigrationStatus, VolumeMount, TransferMethod
from zfs_ops import ZFSOperations
from docker_ops import DockerOperations
from transfer_ops import TransferOperations

logger = logging.getLogger(__name__)

class MigrationService:
    def __init__(self):
        self.zfs_ops = ZFSOperations()
        self.docker_ops = DockerOperations()
        self.transfer_ops = TransferOperations()
        self.active_migrations: Dict[str, MigrationStatus] = {}
    
    def create_migration_id(self) -> str:
        """Generate a unique migration ID"""
        return str(uuid.uuid4())
    
    async def start_migration(self, request: MigrationRequest) -> str:
        """Start a new migration process"""
        migration_id = self.create_migration_id()
        
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
            compose_target_path = f"{request.target_base_path}/compose/{os.path.basename(compose_dir)}"
            
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
                    target_path = volume_mapping.get(source_path, f"{request.target_base_path}/data/{os.path.basename(source_path)}")
                    description = os.path.basename(source_path)
                
                await self._update_status(
                    migration_id, "transferring", int(progress),
                    f"Transferring {description}"
                )
                
                # Find corresponding volume for non-compose transfers
                volume = None
                for v in volumes:
                    if v.source == source_path:
                        volume = v
                        break
                
                success = await self.transfer_ops.transfer_volume_data(
                    volume or VolumeMount(source=source_path, target=""),
                    snapshot_name,
                    request.target_host,
                    target_path,
                    transfer_method,
                    request.ssh_user,
                    request.ssh_port
                )
                
                if not success:
                    raise Exception(f"Failed to transfer {source_path}")
            
            # Step 9: Update compose file paths
            await self._update_status(migration_id, "updating", 90, "Updating compose file paths")
            
            target_compose_file = await self.docker_ops.find_compose_file(compose_target_path)
            if target_compose_file:
                # Copy compose files to target first if using rsync
                if transfer_method == TransferMethod.RSYNC:
                    await self.docker_ops.copy_compose_files(
                        compose_dir, request.target_host, compose_target_path,
                        request.ssh_user, request.ssh_port
                    )
                
                # Update paths remotely
                update_cmd = f"""
                    cd {compose_target_path} && 
                    cp docker-compose.yml docker-compose.yml.backup &&
                    python3 -c "
import re
with open('docker-compose.yml', 'r') as f:
    content = f.read()
"""
                for old_path, new_path in volume_mapping.items():
                    if old_path != compose_dir:  # Don't replace compose dir path
                        update_cmd += f"content = content.replace('{old_path}', '{new_path}')\n"
                
                update_cmd += """
with open('docker-compose.yml', 'w') as f:
    f.write(content)
"
                """
                
                cmd = ["ssh", "-p", str(request.ssh_port), f"{request.ssh_user}@{request.target_host}", update_cmd]
                returncode, _, stderr = await self.transfer_ops.run_command(cmd)
                
                if returncode != 0:
                    logger.warning(f"Failed to update compose file paths: {stderr}")
            
            # Step 10: Start the compose stack on target
            await self._update_status(migration_id, "starting", 95, "Starting compose stack on target")
            
            start_cmd = f"cd {compose_target_path} && docker-compose up -d"
            cmd = ["ssh", "-p", str(request.ssh_port), f"{request.ssh_user}@{request.target_host}", start_cmd]
            returncode, stdout, stderr = await self.transfer_ops.run_command(cmd)
            
            if returncode != 0:
                logger.warning(f"Failed to start compose stack on target: {stderr}")
            
            # Step 11: Cleanup snapshots
            await self._update_status(migration_id, "cleaning", 98, "Cleaning up snapshots")
            
            for snapshot_name, _ in snapshots:
                await self.zfs_ops.cleanup_snapshot(snapshot_name)
            
            # Step 12: Complete
            await self._update_status(migration_id, "completed", 100, "Migration completed successfully")
            
        except Exception as e:
            await self._update_error(migration_id, str(e))
            # Try to restart the original stack if it was stopped
            try:
                compose_dir = self.docker_ops.get_compose_path(request.compose_dataset)
                await self.docker_ops.start_compose_stack(compose_dir)
            except:
                pass 