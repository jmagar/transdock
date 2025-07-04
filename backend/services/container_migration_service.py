import asyncio
import logging
from typing import Dict, List, Any
from ..models import (
    ContainerMigrationRequest, MigrationStatus, VolumeMount, 
    TransferMethod, HostInfo, IdentifierType
)
from ..docker_ops import DockerOperations, ContainerInfo, NetworkInfo
from ..zfs_ops import ZFSOperations
from ..transfer_ops import TransferOperations
from ..host_service import HostService
from .migration_orchestrator import MigrationOrchestrator
from .container_discovery_service import ContainerDiscoveryService

logger = logging.getLogger(__name__)


class ContainerMigrationService:
    """Handles container-specific migration operations"""
    
    def __init__(self, 
                 docker_ops: DockerOperations,
                 zfs_ops: ZFSOperations,
                 transfer_ops: TransferOperations,
                 host_service: HostService,
                 orchestrator: MigrationOrchestrator,
                 discovery_service: ContainerDiscoveryService):
        self.docker_ops = docker_ops
        self.zfs_ops = zfs_ops
        self.transfer_ops = transfer_ops
        self.host_service = host_service
        self.orchestrator = orchestrator
        self.discovery_service = discovery_service
    
    async def start_container_migration(self, request: ContainerMigrationRequest) -> str:
        """Start a container-based migration"""
        migration_id = self.orchestrator.create_migration_id()
        
        try:
            # Discover containers using unified Docker API
            if request.identifier_type == IdentifierType.PROJECT:
                containers = await self.docker_ops.discover_containers_by_project(
                    request.container_identifier, request.source_host, request.source_ssh_user
                )
            elif request.identifier_type == IdentifierType.NAME:
                containers = await self.docker_ops.discover_containers_by_name(
                    request.container_identifier, request.source_host, request.source_ssh_user
                )
            else:
                containers = await self.docker_ops.discover_containers_by_labels(
                    request.label_filters or {}, request.source_host, request.source_ssh_user
                )

            if not containers:
                raise ValueError(f"No containers found matching criteria")

            # Extract volumes from all containers
            all_volumes = []
            for container in containers:
                volumes = await self.docker_ops.get_container_volumes(container, request.source_host, request.source_ssh_user)
                all_volumes.extend(volumes)

            # Remove duplicates
            unique_volumes = self.discovery_service._deduplicate_volumes(all_volumes)

            # Get networks for project-based migrations
            networks = []
            if request.identifier_type == IdentifierType.PROJECT:
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
                containers=[container.__dict__ for container in containers],
                networks=networks
            )
            
            self.orchestrator.register_migration(migration_id, status)

            # Start migration process
            asyncio.create_task(self._execute_container_migration(migration_id, request, containers, unique_volumes, networks))

            logger.info(f"Started container migration {migration_id} for {request.container_identifier}")
            return migration_id

        except Exception as e:
            error_msg = f"Failed to start container migration: {e}"
            logger.error(error_msg)
            
            if migration_id:
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

            # Step 2: Stop containers
            await self.orchestrator.update_status(migration_id, "stopping", 20, "Stopping containers")
            
            # Stop containers using unified Docker API
            success = await self.docker_ops.stop_containers(
                containers, 10, request.source_host, request.source_ssh_user
            )
            
            if not success:
                raise Exception("Failed to stop containers")

            # Step 3: Create snapshots and migrate data
            await self.orchestrator.update_status(migration_id, "migrating", 30, "Migrating container data")
            
            # Determine transfer method
            target_has_zfs = await self.zfs_ops.check_remote_zfs(
                request.target_host, request.ssh_user, request.ssh_port
            )
            source_has_zfs = request.source_host is None or await self.zfs_ops.check_remote_zfs(
                request.source_host or "localhost"
            )

            use_zfs = target_has_zfs and source_has_zfs and not request.force_rsync
            transfer_method = TransferMethod.ZFS_SEND if use_zfs else TransferMethod.RSYNC

            # Create volume mapping and transfer data
            volume_mapping = {}
            snapshots = []

            for volume in volumes:
                target_path = f"{request.target_base_path}/{volume.source.split('/')[-1]}"
                volume_mapping[volume.source] = target_path

                if use_zfs:
                    # ZFS migration
                    dataset_name = await self.zfs_ops.get_dataset_name(volume.source)
                    snapshot_name = await self.zfs_ops.create_snapshot(volume.source)
                    snapshots.append(snapshot_name)
                    
                    # Send snapshot to target
                    success = await self.zfs_ops.send_snapshot(
                        snapshot_name, request.target_host, target_path,
                        request.ssh_user, request.ssh_port
                    )
                    if not success:
                        raise Exception(f"Failed to send ZFS snapshot for {volume.source}")
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