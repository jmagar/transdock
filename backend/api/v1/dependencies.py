"""API Dependencies for dependency injection"""

from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database.config import get_db_session
from ...infrastructure.database.repositories.migration_repository_impl import MigrationRepositoryImpl
from ...infrastructure.zfs.repositories.zfs_dataset_repository_impl import ZFSDatasetRepositoryImpl
from ...infrastructure.zfs.repositories.zfs_snapshot_repository_impl import ZFSSnapshotRepositoryImpl
from ...infrastructure.zfs.repositories.zfs_pool_repository_impl import ZFSPoolRepositoryImpl

from ...application.zfs.dataset_management_service import DatasetManagementService
from ...application.zfs.snapshot_management_service import SnapshotManagementService
from ...application.zfs.pool_management_service import PoolManagementService
from ...application.docker.docker_management_service import DockerManagementService
from ...application.migration.migration_orchestration_service import MigrationOrchestrationService

# For now, we'll create mock implementations for Docker repositories
# In production, these would be real implementations
from ...core.interfaces.docker_repository import (
    DockerContainerRepository, DockerImageRepository, DockerNetworkRepository,
    DockerComposeRepository, DockerVolumeRepository, DockerHostRepository
)


# Database session dependency
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session"""
    async for session in get_db_session():
        yield session


# Repository dependencies
async def get_migration_repository(
    session: AsyncSession = Depends(get_session)
) -> MigrationRepositoryImpl:
    """Get migration repository"""
    return MigrationRepositoryImpl(session)


async def get_zfs_dataset_repository() -> ZFSDatasetRepositoryImpl:
    """Get ZFS dataset repository"""
    return ZFSDatasetRepositoryImpl()


async def get_zfs_snapshot_repository() -> ZFSSnapshotRepositoryImpl:
    """Get ZFS snapshot repository"""
    return ZFSSnapshotRepositoryImpl()


async def get_zfs_pool_repository() -> ZFSPoolRepositoryImpl:
    """Get ZFS pool repository"""
    return ZFSPoolRepositoryImpl()


# Service dependencies
async def get_dataset_service(
    dataset_repo: ZFSDatasetRepositoryImpl = Depends(get_zfs_dataset_repository)
) -> DatasetManagementService:
    """Get dataset management service"""
    return DatasetManagementService(dataset_repo)


async def get_snapshot_service(
    snapshot_repo: ZFSSnapshotRepositoryImpl = Depends(get_zfs_snapshot_repository),
    dataset_repo: ZFSDatasetRepositoryImpl = Depends(get_zfs_dataset_repository)
) -> SnapshotManagementService:
    """Get snapshot management service"""
    return SnapshotManagementService(snapshot_repo, dataset_repo)


async def get_pool_service(
    pool_repo: ZFSPoolRepositoryImpl = Depends(get_zfs_pool_repository)
) -> PoolManagementService:
    """Get pool management service"""
    return PoolManagementService(pool_repo)


async def get_docker_service() -> DockerManagementService:
    """Get Docker management service"""
    # For now, create mock repositories
    # In production, these would be real implementations
    from .mock_repositories import (
        MockDockerContainerRepository, MockDockerImageRepository,
        MockDockerNetworkRepository, MockDockerComposeRepository,
        MockDockerVolumeRepository, MockDockerHostRepository
    )
    
    return DockerManagementService(
        container_repository=MockDockerContainerRepository(),
        image_repository=MockDockerImageRepository(),
        network_repository=MockDockerNetworkRepository(),
        compose_repository=MockDockerComposeRepository(),
        volume_repository=MockDockerVolumeRepository(),
        host_repository=MockDockerHostRepository()
    )


async def get_migration_service(
    migration_repo: MigrationRepositoryImpl = Depends(get_migration_repository),
    dataset_service: DatasetManagementService = Depends(get_dataset_service),
    snapshot_service: SnapshotManagementService = Depends(get_snapshot_service),
    docker_service: DockerManagementService = Depends(get_docker_service)
) -> MigrationOrchestrationService:
    """Get migration orchestration service"""
    return MigrationOrchestrationService(
        migration_repository=migration_repo,
        dataset_service=dataset_service,
        snapshot_service=snapshot_service,
        docker_service=docker_service
    )