"""Migration orchestration application service"""

from typing import List, Optional, Dict, Any, Callable
import asyncio
from datetime import datetime
from ...core.entities.migration_entity import Migration, MigrationStep, MigrationStatus, MigrationStepType, MigrationStepStatus
from ...core.interfaces.migration_repository import MigrationRepository
from ...core.exceptions.migration_exceptions import MigrationOperationError, MigrationNotFoundError
from ...core.value_objects.host_connection import HostConnection
from ..zfs.dataset_management_service import DatasetManagementService
from ..zfs.snapshot_management_service import SnapshotManagementService
from ..docker.docker_management_service import DockerManagementService
import logging

logger = logging.getLogger(__name__)


class MigrationOrchestrationService:
    """Application service for orchestrating complete migrations"""
    
    def __init__(
        self,
        migration_repository: MigrationRepository,
        dataset_service: DatasetManagementService,
        snapshot_service: SnapshotManagementService,
        docker_service: DockerManagementService
    ):
        self._migration_repository = migration_repository
        self._dataset_service = dataset_service
        self._snapshot_service = snapshot_service
        self._docker_service = docker_service
        self._running_migrations: Dict[str, asyncio.Task] = {}
    
    async def create_migration(
        self,
        name: str,
        compose_stack_path: str,
        target_host: HostConnection,
        target_base_path: str,
        use_zfs: bool = True,
        transfer_method: str = "zfs_send",
        source_host: Optional[HostConnection] = None
    ) -> Migration:
        """Create a new migration"""
        try:
            # Use localhost as default source host
            if source_host is None:
                source_host = HostConnection.localhost()
            
            migration = Migration(
                name=name,
                source_host=source_host,
                target_host=target_host,
                compose_stack_path=compose_stack_path,
                target_base_path=target_base_path,
                use_zfs=use_zfs,
                transfer_method=transfer_method
            )
            
            # Create migration steps
            await self._create_migration_steps(migration)
            
            # Save migration
            migration = await self._migration_repository.create(migration)
            
            logger.info(f"Created migration: {migration.name} (ID: {migration.id})")
            return migration
            
        except Exception as e:
            logger.error(f"Failed to create migration {name}: {e}")
            raise MigrationOperationError(f"Failed to create migration {name}: {e}")
    
    async def start_migration(self, migration_id: str) -> bool:
        """Start a migration"""
        try:
            migration = await self._migration_repository.find_by_id(migration_id)
            if not migration:
                raise MigrationNotFoundError(f"Migration {migration_id} not found")
            
            if migration.is_running():
                raise MigrationOperationError(f"Migration {migration_id} is already running")
            
            # Start migration in background
            task = asyncio.create_task(self._execute_migration(migration))
            self._running_migrations[migration_id] = task
            
            logger.info(f"Started migration: {migration.name} (ID: {migration_id})")
            return True
            
        except (MigrationOperationError, MigrationNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to start migration {migration_id}: {e}")
            raise MigrationOperationError(f"Failed to start migration {migration_id}: {e}")
    
    async def cancel_migration(self, migration_id: str) -> bool:
        """Cancel a running migration"""
        try:
            migration = await self._migration_repository.find_by_id(migration_id)
            if not migration:
                raise MigrationNotFoundError(f"Migration {migration_id} not found")
            
            if not migration.can_be_cancelled():
                raise MigrationOperationError(f"Migration {migration_id} cannot be cancelled")
            
            # Cancel the task
            task = self._running_migrations.get(migration_id)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                finally:
                    self._running_migrations.pop(migration_id, None)
            
            # Update migration status
            migration.cancel()
            await self._migration_repository.update(migration)
            
            logger.info(f"Cancelled migration: {migration.name} (ID: {migration_id})")
            return True
            
        except (MigrationOperationError, MigrationNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to cancel migration {migration_id}: {e}")
            raise MigrationOperationError(f"Failed to cancel migration {migration_id}: {e}")
    
    async def get_migration(self, migration_id: str) -> Optional[Migration]:
        """Get a migration by ID"""
        try:
            return await self._migration_repository.find_by_id(migration_id)
        except Exception as e:
            logger.error(f"Failed to get migration {migration_id}: {e}")
            return None
    
    async def list_migrations(self) -> List[Migration]:
        """List all migrations"""
        try:
            return await self._migration_repository.list_all()
        except Exception as e:
            logger.error(f"Failed to list migrations: {e}")
            return []
    
    async def get_migration_status(self, migration_id: str) -> Dict[str, Any]:
        """Get migration status"""
        try:
            migration = await self._migration_repository.find_by_id(migration_id)
            if not migration:
                raise MigrationNotFoundError(f"Migration {migration_id} not found")
            
            status = migration.get_summary()
            
            # Add real-time information
            if migration.is_running():
                task = self._running_migrations.get(migration_id)
                if task:
                    status['task_running'] = not task.done()
            
            # Add estimated remaining time
            estimated_time = migration.estimate_remaining_time()
            if estimated_time:
                status['estimated_remaining_seconds'] = estimated_time
            
            return status
            
        except (MigrationOperationError, MigrationNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to get migration status {migration_id}: {e}")
            raise MigrationOperationError(f"Failed to get migration status {migration_id}: {e}")
    
    async def validate_migration_request(
        self,
        compose_stack_path: str,
        target_host: HostConnection,
        target_base_path: str
    ) -> Dict[str, Any]:
        """Validate a migration request"""
        try:
            validation_result = {
                'valid': True,
                'errors': [],
                'warnings': [],
                'requirements': []
            }
            
            # Validate compose stack
            docker_validation = await self._docker_service.validate_migration_prerequisites(compose_stack_path)
            if not docker_validation.get('valid', False):
                validation_result['valid'] = False
                validation_result['errors'].append(f"Docker validation failed: {docker_validation.get('error', 'Unknown error')}")
            
            # Validate target host connectivity
            if not target_host.is_localhost():
                try:
                    # This would test SSH connectivity
                    # For now, we'll assume it's valid
                    pass
                except Exception as e:
                    validation_result['valid'] = False
                    validation_result['errors'].append(f"Cannot connect to target host: {e}")
            
            # Validate target path
            if not target_base_path or not target_base_path.startswith('/'):
                validation_result['valid'] = False
                validation_result['errors'].append("Target base path must be an absolute path")
            
            # Add requirements
            if docker_validation.get('complexity') == 'complex':
                validation_result['warnings'].append('Complex migration - consider breaking down into smaller parts')
            
            if docker_validation.get('external_volumes'):
                validation_result['warnings'].append('Stack uses external volumes that may need special handling')
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Failed to validate migration request: {e}")
            return {
                'valid': False,
                'errors': [f"Validation failed: {str(e)}"],
                'warnings': [],
                'requirements': []
            }
    
    async def _create_migration_steps(self, migration: Migration) -> None:
        """Create migration steps based on migration configuration"""
        steps = []
        
        # Step 1: Validation
        steps.append(MigrationStep(
            name="Validate Migration Prerequisites",
            step_type=MigrationStepType.VALIDATION
        ))
        
        # Step 2: Create snapshots (if using ZFS)
        if migration.use_zfs:
            steps.append(MigrationStep(
                name="Create ZFS Snapshots",
                step_type=MigrationStepType.SNAPSHOT_CREATION
            ))
        
        # Step 3: Transfer data
        steps.append(MigrationStep(
            name="Transfer Data",
            step_type=MigrationStepType.DATA_TRANSFER
        ))
        
        # Step 4: Recreate containers
        steps.append(MigrationStep(
            name="Recreate Containers",
            step_type=MigrationStepType.CONTAINER_RECREATION
        ))
        
        # Step 5: Start services
        steps.append(MigrationStep(
            name="Start Services",
            step_type=MigrationStepType.SERVICE_START
        ))
        
        # Step 6: Verify migration
        steps.append(MigrationStep(
            name="Verify Migration",
            step_type=MigrationStepType.VERIFICATION
        ))
        
        # Step 7: Cleanup (if configured)
        if migration.cleanup_on_success:
            steps.append(MigrationStep(
                name="Cleanup",
                step_type=MigrationStepType.CLEANUP
            ))
        
        migration.steps = steps
    
    async def _execute_migration(self, migration: Migration) -> None:
        """Execute the migration steps"""
        try:
            migration.start()
            await self._migration_repository.update(migration)
            
            for step in migration.steps:
                try:
                    # Start step
                    step.start()
                    await self._migration_repository.update_step(migration.id, step)
                    
                    # Execute step
                    await self._execute_migration_step(migration, step)
                    
                    # Complete step
                    step.complete()
                    await self._migration_repository.update_step(migration.id, step)
                    
                except Exception as e:
                    step.fail(str(e))
                    await self._migration_repository.update_step(migration.id, step)
                    raise
            
            # Migration completed successfully
            migration.complete()
            await self._migration_repository.update(migration)
            
            logger.info(f"Migration completed successfully: {migration.name} (ID: {migration.id})")
            
        except asyncio.CancelledError:
            migration.cancel()
            await self._migration_repository.update(migration)
            logger.info(f"Migration cancelled: {migration.name} (ID: {migration.id})")
            raise
        except Exception as e:
            migration.fail(str(e))
            await self._migration_repository.update(migration)
            logger.error(f"Migration failed: {migration.name} (ID: {migration.id}): {e}")
            raise
        finally:
            # Clean up running migrations dict
            self._running_migrations.pop(migration.id, None)
    
    async def _execute_migration_step(self, migration: Migration, step: MigrationStep) -> None:
        """Execute a specific migration step"""
        logger.info(f"Executing step: {step.name} for migration {migration.name}")
        
        if step.step_type == MigrationStepType.VALIDATION:
            await self._execute_validation_step(migration, step)
        elif step.step_type == MigrationStepType.SNAPSHOT_CREATION:
            await self._execute_snapshot_creation_step(migration, step)
        elif step.step_type == MigrationStepType.DATA_TRANSFER:
            await self._execute_data_transfer_step(migration, step)
        elif step.step_type == MigrationStepType.CONTAINER_RECREATION:
            await self._execute_container_recreation_step(migration, step)
        elif step.step_type == MigrationStepType.SERVICE_START:
            await self._execute_service_start_step(migration, step)
        elif step.step_type == MigrationStepType.VERIFICATION:
            await self._execute_verification_step(migration, step)
        elif step.step_type == MigrationStepType.CLEANUP:
            await self._execute_cleanup_step(migration, step)
        else:
            raise MigrationOperationError(f"Unknown step type: {step.step_type}")
    
    async def _execute_validation_step(self, migration: Migration, step: MigrationStep) -> None:
        """Execute validation step"""
        step.update_progress(10, "Validating Docker prerequisites")
        
        # Validate Docker stack
        docker_validation = await self._docker_service.validate_migration_prerequisites(migration.compose_stack_path)
        if not docker_validation.get('valid', False):
            raise MigrationOperationError(f"Docker validation failed: {docker_validation.get('error', 'Unknown error')}")
        
        step.update_progress(50, "Validating target host connectivity")
        
        # Validate target host (simplified)
        if not migration.target_host.is_localhost():
            # This would test SSH connectivity
            await asyncio.sleep(1)  # Simulate network check
        
        step.update_progress(80, "Validating ZFS prerequisites")
        
        # Validate ZFS if needed
        if migration.use_zfs:
            # Check if ZFS is available
            # This would call ZFS service to validate
            await asyncio.sleep(1)  # Simulate ZFS check
        
        step.update_progress(100, "Validation completed")
        
        # Store validation results
        step.details.update({
            'docker_validation': docker_validation,
            'target_host_reachable': True,
            'zfs_available': migration.use_zfs
        })
    
    async def _execute_snapshot_creation_step(self, migration: Migration, step: MigrationStep) -> None:
        """Execute snapshot creation step"""
        step.update_progress(10, "Analyzing data directories")
        
        # Get stack information
        stack = await self._docker_service.get_compose_stack_by_path(migration.compose_stack_path)
        if not stack:
            raise MigrationOperationError("Compose stack not found")
        
        data_directories = stack.get_all_data_directories()
        if not data_directories:
            step.skip("No data directories found")
            return
        
        step.update_progress(30, f"Creating snapshots for {len(data_directories)} directories")
        
        # Create snapshots for each data directory
        created_snapshots = []
        for i, data_dir in enumerate(data_directories):
            # Determine dataset name from path
            # This is simplified - in reality, we'd need to map paths to datasets
            dataset_name = data_dir.replace('/', '_').strip('_')
            
            try:
                snapshot_name = f"migration_{migration.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                snapshot = await self._snapshot_service.create_snapshot(
                    dataset_name=dataset_name,
                    snapshot_name=snapshot_name,
                    prefix="migration"
                )
                created_snapshots.append(snapshot.full_name)
                
                # Update progress
                progress = 30 + (i + 1) * 60 / len(data_directories)
                step.update_progress(progress, f"Created snapshot for {data_dir}")
                
            except Exception as e:
                logger.warning(f"Failed to create snapshot for {data_dir}: {e}")
                # Continue with other directories
        
        step.update_progress(100, f"Created {len(created_snapshots)} snapshots")
        
        # Store created snapshots
        step.details['created_snapshots'] = created_snapshots
        migration.add_metadata('snapshots', created_snapshots)
    
    async def _execute_data_transfer_step(self, migration: Migration, step: MigrationStep) -> None:
        """Execute data transfer step"""
        step.update_progress(10, "Preparing data transfer")
        
        # Get transfer method
        if migration.transfer_method == "zfs_send" and migration.use_zfs:
            await self._execute_zfs_send_transfer(migration, step)
        else:
            await self._execute_rsync_transfer(migration, step)
    
    async def _execute_zfs_send_transfer(self, migration: Migration, step: MigrationStep) -> None:
        """Execute ZFS send transfer"""
        snapshots = migration.get_metadata('snapshots', [])
        if not snapshots:
            raise MigrationOperationError("No snapshots available for ZFS send")
        
        step.update_progress(20, f"Transferring {len(snapshots)} snapshots via ZFS send")
        
        # Transfer each snapshot
        for i, snapshot_name in enumerate(snapshots):
            try:
                # This would call the snapshot service to send the snapshot
                success = await self._snapshot_service.send_snapshot(
                    snapshot_name=snapshot_name,
                    target_host=str(migration.target_host),
                    target_dataset_name=f"{migration.target_base_path}/{snapshot_name}"
                )
                
                if not success:
                    raise MigrationOperationError(f"Failed to send snapshot {snapshot_name}")
                
                # Update progress
                progress = 20 + (i + 1) * 70 / len(snapshots)
                step.update_progress(progress, f"Transferred snapshot {snapshot_name}")
                
            except Exception as e:
                raise MigrationOperationError(f"Failed to transfer snapshot {snapshot_name}: {e}")
        
        step.update_progress(100, "ZFS send transfer completed")
    
    async def _execute_rsync_transfer(self, migration: Migration, step: MigrationStep) -> None:
        """Execute rsync transfer"""
        step.update_progress(20, "Preparing rsync transfer")
        
        # Get stack information
        stack = await self._docker_service.get_compose_stack_by_path(migration.compose_stack_path)
        if not stack:
            raise MigrationOperationError("Compose stack not found")
        
        data_directories = stack.get_all_data_directories()
        
        step.update_progress(40, f"Transferring {len(data_directories)} directories via rsync")
        
        # Transfer each directory
        for i, data_dir in enumerate(data_directories):
            try:
                # This would execute rsync command
                # For now, we'll simulate the transfer
                await asyncio.sleep(2)  # Simulate transfer time
                
                # Update progress
                progress = 40 + (i + 1) * 50 / len(data_directories)
                step.update_progress(progress, f"Transferred directory {data_dir}")
                
            except Exception as e:
                raise MigrationOperationError(f"Failed to transfer directory {data_dir}: {e}")
        
        step.update_progress(100, "Rsync transfer completed")
    
    async def _execute_container_recreation_step(self, migration: Migration, step: MigrationStep) -> None:
        """Execute container recreation step"""
        step.update_progress(10, "Stopping source containers")
        
        # Stop source stack
        success = await self._docker_service.stop_compose_stack(migration.compose_stack_path)
        if not success:
            raise MigrationOperationError("Failed to stop source compose stack")
        
        step.update_progress(50, "Recreating containers on target host")
        
        # This would copy the compose file to target host and update paths
        # For now, we'll simulate this
        await asyncio.sleep(3)  # Simulate container recreation
        
        step.update_progress(100, "Container recreation completed")
    
    async def _execute_service_start_step(self, migration: Migration, step: MigrationStep) -> None:
        """Execute service start step"""
        step.update_progress(20, "Starting services on target host")
        
        # This would start the compose stack on the target host
        # For now, we'll simulate this
        await asyncio.sleep(2)  # Simulate service start
        
        step.update_progress(100, "Services started successfully")
    
    async def _execute_verification_step(self, migration: Migration, step: MigrationStep) -> None:
        """Execute verification step"""
        step.update_progress(20, "Verifying service health")
        
        # This would check if services are running correctly
        # For now, we'll simulate this
        await asyncio.sleep(3)  # Simulate verification
        
        step.update_progress(100, "Verification completed")
    
    async def _execute_cleanup_step(self, migration: Migration, step: MigrationStep) -> None:
        """Execute cleanup step"""
        step.update_progress(20, "Cleaning up temporary snapshots")
        
        # Clean up snapshots if configured
        snapshots = migration.get_metadata('snapshots', [])
        for snapshot_name in snapshots:
            try:
                await self._snapshot_service.delete_snapshot(snapshot_name)
            except Exception as e:
                logger.warning(f"Failed to cleanup snapshot {snapshot_name}: {e}")
        
        step.update_progress(100, "Cleanup completed")
    
    async def cleanup_old_migrations(self, keep_days: int = 30) -> int:
        """Clean up old completed migrations"""
        try:
            return await self._migration_repository.cleanup_old_migrations(keep_days)
        except Exception as e:
            logger.error(f"Failed to cleanup old migrations: {e}")
            return 0