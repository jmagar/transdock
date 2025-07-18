import asyncio
import logging
from typing import Dict, List, Any
from ..models import (
    ContainerMigrationRequest, MigrationStatus, VolumeMount, 
    TransferMethod, HostInfo, IdentifierType
)
from ..docker_ops import DockerOperations, ContainerInfo, NetworkInfo
from ..zfs_operations.factories.service_factory import create_default_service_factory
from ..zfs_operations.services.dataset_service import DatasetService
from ..zfs_operations.services.snapshot_service import SnapshotService as NewSnapshotService

from ..transfer_ops import TransferOperations
from ..host_service import HostService
from .migration_orchestrator import MigrationOrchestrator
from .container_discovery_service import ContainerDiscoveryService

logger = logging.getLogger(__name__)


class ContainerMigrationService:
    """Handles container-specific migration operations"""
    
    def __init__(self, 
                 docker_ops: DockerOperations,
                 transfer_ops: TransferOperations,
                 host_service: HostService,
                 orchestrator: MigrationOrchestrator,
                 discovery_service: ContainerDiscoveryService):
        self.docker_ops = docker_ops
        self.transfer_ops = transfer_ops
        self.host_service = host_service
        self.orchestrator = orchestrator
        self.discovery_service = discovery_service
        self._service_factory = create_default_service_factory()
        self._dataset_service = None
        self._snapshot_service = None
    
    async def _get_dataset_service(self) -> DatasetService:
        """Get the dataset service instance"""
        if self._dataset_service is None:
            self._dataset_service = await self._service_factory.create_dataset_service()
        return self._dataset_service
    
    async def _get_snapshot_service(self) -> NewSnapshotService:
        """Get the snapshot service instance"""
        if self._snapshot_service is None:
            self._snapshot_service = await self._service_factory.create_snapshot_service()
        return self._snapshot_service
    
    def _handle_migration_completion(self, migration_id: str, task: asyncio.Task) -> None:
        """Handle completion of background migration task and log any exceptions"""
        try:
            if task.done() and task.exception():
                exception = task.exception()
                error_msg = f"Background migration task for {migration_id} failed: {exception}"
                logger.error(error_msg)
                logger.exception("Full traceback for migration task failure", exc_info=exception)
                
                # Update orchestrator with error status
                loop = asyncio.get_running_loop()
                asyncio.run_coroutine_threadsafe(
                    self.orchestrator.update_error(migration_id, error_msg),
                    loop
                )

        except Exception as e:
            # This shouldn't happen, but just in case there's an issue with the callback itself
            logger.error(f"Error in migration completion handler for {migration_id}: {e}")
    
    async def start_container_migration(self, request: ContainerMigrationRequest) -> str:
        """Start a container-based migration"""
        migration_id = self.orchestrator.create_migration_id()
        
        try:
            containers = []
            all_volumes = []
            networks = []

            if request.identifier_type == IdentifierType.PROJECT:
                compose_info = await self.docker_ops.discover_services_from_compose_file(
                    request.container_identifier
                )
                containers = compose_info.get("containers", [])
                all_volumes = compose_info.get("volumes", [])
                networks = [net.__dict__ for net in compose_info.get("networks", [])]

            elif request.identifier_type == IdentifierType.NAME:
                containers = await self.docker_ops.discover_containers_by_name(
                    request.container_identifier, request.source_host, request.source_ssh_user
                )
            else:
                containers = await self.docker_ops.discover_containers_by_labels(
                    request.label_filters or {}, request.source_host, request.source_ssh_user
                )

            if not containers:
                raise ValueError("No containers or services found matching criteria")

            # Extract volumes from running containers if not a project-based discovery
            if request.identifier_type != IdentifierType.PROJECT:
                for container in containers:
                    volumes = await self.docker_ops.get_container_volumes(container, request.source_host, request.source_ssh_user)
                    all_volumes.extend(volumes)

            # Remove duplicates
            unique_volumes = self.discovery_service._deduplicate_volumes(all_volumes)

            # Get networks for project-based migrations if not already discovered
            if request.identifier_type == IdentifierType.PROJECT and not networks:
                project_networks = await self.docker_ops.get_project_networks(
                    request.container_identifier, request.source_host, request.source_ssh_user
                )
                networks = [net.__dict__ for net in project_networks]

            # Create migration status
            status = MigrationStatus(
                id=migration_id,
                status="discovered",
                progress=5,
                message=f"Discovered {len(containers)} containers with {len(unique_volumes)} volumes",
                compose_dataset=request.container_identifier,
                source_host=request.source_host,
                target_host=request.target_host,
                target_base_path=request.target_base_path,
                volumes=unique_volumes,
                containers=[c.__dict__ for c in containers],
                networks=networks
            )
            
            await self.orchestrator.register_migration(migration_id, status)

            # Start migration process in background (task runs independently)
            migration_task = asyncio.create_task(self._execute_container_migration(migration_id, request, containers, unique_volumes, networks))
            # Note: We don't await this task as it should run in the background
            migration_task.add_done_callback(
                lambda t: self._handle_migration_completion(migration_id, t)
            )

            logger.info(f"Started container migration {migration_id} for {request.container_identifier}")
            return migration_id

        except Exception as e:
            error_msg = f"Failed to start container migration for {migration_id}: {e}"
            logger.error(error_msg)
            
            # Ensure orchestrator is updated with the error
            await self.orchestrator.update_error(migration_id, error_msg)
            
            raise
    
    async def _execute_container_migration(self, migration_id: str, request: ContainerMigrationRequest,
                                         containers: List[ContainerInfo], volumes: List[VolumeMount],
                                         networks: List[Dict[str, Any]]):
        """Execute the complete container migration process"""
        try:
            # Step 1: Validate target host and storage
            await self.orchestrator.update_status(migration_id, "validating", 10, "Validating target host and storage")
            
            # Validate Docker on target
            docker_available = await self.docker_ops.validate_docker_on_target(
                request.target_host, request.ssh_user, request.ssh_port
            )
            if not docker_available:
                raise Exception(f"Docker not available on target host {request.target_host}")

            # Storage validation
            target_host_info = HostInfo(
                hostname=request.target_host,
                ssh_user=request.ssh_user,
                ssh_port=request.ssh_port
            )
            
            # For container migration, create a dummy source host for local operations
            source_host_info = HostInfo(
                hostname=request.source_host or "localhost",
                ssh_user=request.source_ssh_user,
                ssh_port=request.source_ssh_port
            )
            
            storage_validation = await self.host_service.validate_migration_storage(
                source_host_info, target_host_info, volumes, request.target_base_path, use_zfs=False
            )

            failed_validations = {k: v for k, v in storage_validation.items() if not v.is_valid}
            if failed_validations:
                error_messages = [f"{location}: {result.error_message}" for location, result in failed_validations.items()]
                raise Exception(f"Storage validation failed: {'; '.join(error_messages)}")

            # Step 2: Stop containers - only if not a file-based discovery
            if request.identifier_type != IdentifierType.PROJECT:
                await self.orchestrator.update_status(migration_id, "stopping", 20, "Stopping containers")
                
                # Stop containers using unified Docker API
                success = await self.docker_ops.stop_containers(
                    containers, 10, request.source_host, request.source_ssh_user
                )
                
                if not success:
                    raise Exception("Failed to stop containers")

            # Step 3: Create snapshots and migrate data
            await self.orchestrator.update_status(migration_id, "migrating", 30, "Migrating container data")
            
            # Determine transfer method - simplified for now
            # TODO: Implement proper ZFS checking with new service layer
            target_has_zfs = False  # Disable ZFS for now until proper implementation
            source_has_zfs = False

            use_zfs = target_has_zfs and source_has_zfs and not request.force_rsync
            transfer_method = TransferMethod.ZFS_SEND if use_zfs else TransferMethod.RSYNC

            # Create volume mapping and transfer data
            volume_mapping = {}
            snapshots = []

            for volume in volumes:
                target_path = f"{request.target_base_path}/{volume.source.split('/')[-1]}"
                volume_mapping[volume.source] = target_path

                if use_zfs:
                    # ZFS migration - TODO: Implement with new service layer
                    raise Exception("ZFS migration not yet implemented with new service layer")
                else:
                    # Rsync migration
                    success = await self.transfer_ops.transfer_via_rsync(
                        volume.source, request.target_host, target_path,
                        request.ssh_user, request.ssh_port
                    )
                    if not success:
                        raise Exception(f"Failed to rsync data for {volume.source}")

            # Step 4: Pull images on target
            await self.orchestrator.update_status(migration_id, "preparing", 60, "Pulling container images on target")
            
            unique_images = list(set(container.image for container in containers))
            for image in unique_images:
                success = await self.docker_ops.pull_image_on_target(
                    image, request.target_host, request.ssh_user, request.ssh_port
                )
                if not success:
                    logger.warning(f"Failed to pull image {image}, container creation may fail")

            # Step 5: Create networks on target
            await self.orchestrator.update_status(migration_id, "networks", 70, "Creating networks on target")
            
            for network_dict in networks:
                # Convert dict back to NetworkInfo
                network_info = NetworkInfo(**network_dict)
                success = await self.docker_ops.create_network_on_target(
                    network_info, request.target_host, request.ssh_user, request.ssh_port
                )
                if not success:
                    logger.warning(f"Failed to create network {network_info.name}")

            # Step 6: Recreate containers on target
            await self.orchestrator.update_status(migration_id, "recreating", 80, "Recreating containers on target")
            
            success = await self.docker_ops.recreate_containers_on_target(
                containers, volume_mapping, request.target_host, 
                request.ssh_user, request.ssh_port
            )
            if not success:
                raise Exception("Failed to recreate containers on target")

            # Step 7: Connect containers to additional networks
            await self.orchestrator.update_status(migration_id, "connecting", 90, "Connecting containers to networks")
            
            for container in containers:
                if len(container.networks) > 1:
                    success = await self.docker_ops.connect_container_to_networks(
                        container.name, container.networks, request.target_host,
                        request.ssh_user, request.ssh_port
                    )
                    if not success:
                        logger.warning(f"Failed to connect {container.name} to additional networks")

            # Step 8: Complete migration
            await self.orchestrator.update_status(migration_id, "completed", 100, "Container migration completed successfully")

            # Update migration status with final information
            migration_status = await self.orchestrator.get_migration_status(migration_id)
            if migration_status:
                migration_status.transfer_method = transfer_method
                migration_status.volume_mapping = volume_mapping
                migration_status.snapshots = snapshots

            logger.info(f"Container migration {migration_id} completed successfully")

        except Exception as e:
            await self.orchestrator.update_error(migration_id, str(e))
            logger.exception(f"Container migration {migration_id} failed")