"""Datasets API router using clean architecture"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from ....application.zfs.dataset_management_service import DatasetManagementService
from ....infrastructure.zfs.repositories.zfs_dataset_repository_impl import ZFSDatasetRepositoryImpl
from ....core.exceptions.zfs_exceptions import ZFSOperationError, ZFSDatasetExistsError
from ....core.entities.zfs_entity import ZFSDatasetType
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])


# Request/Response Models
class CreateDatasetRequest(BaseModel):
    """Request model for creating a dataset"""
    name: str
    properties: Optional[Dict[str, str]] = None
    dataset_type: str = "filesystem"


class UpdateDatasetRequest(BaseModel):
    """Request model for updating dataset properties"""
    properties: Dict[str, str]


class DatasetResponse(BaseModel):
    """Response model for dataset information"""
    name: str
    dataset_type: str
    properties: Dict[str, str]
    used_space: Optional[str] = None
    available_space: Optional[str] = None
    mount_point: Optional[str] = None
    is_mounted: bool
    is_encrypted: bool
    is_compressed: bool
    pool_name: str
    
    @classmethod
    def from_entity(cls, dataset) -> 'DatasetResponse':
        """Create response from domain entity"""
        return cls(
            name=str(dataset.name),
            dataset_type=dataset.dataset_type.value,
            properties=dataset.properties,
            used_space=str(dataset.used_space) if dataset.used_space else None,
            available_space=str(dataset.available_space) if dataset.available_space else None,
            mount_point=dataset.mount_point,
            is_mounted=dataset.is_mounted(),
            is_encrypted=dataset.is_encrypted(),
            is_compressed=dataset.is_compressed(),
            pool_name=dataset.pool_name()
        )


# Dependency injection
def get_dataset_service() -> DatasetManagementService:
    """Get dataset management service with injected dependencies"""
    repository = ZFSDatasetRepositoryImpl()
    return DatasetManagementService(repository)


# API Endpoints
@router.post("/", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    request: CreateDatasetRequest,
    service: DatasetManagementService = Depends(get_dataset_service)
):
    """Create a new ZFS dataset using clean architecture"""
    try:
        # Convert string to enum
        dataset_type = ZFSDatasetType.FILESYSTEM
        if request.dataset_type.lower() == "volume":
            dataset_type = ZFSDatasetType.VOLUME
        
        dataset = await service.create_dataset(
            request.name, 
            request.properties,
            dataset_type
        )
        return DatasetResponse.from_entity(dataset)
    except ZFSDatasetExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Dataset already exists: {e}"
        )
    except ZFSOperationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ZFS operation failed: {e}"
        )
    except Exception as e:
        logger.error(f"Unexpected error creating dataset: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/{name}", response_model=DatasetResponse)
async def get_dataset(
    name: str,
    service: DatasetManagementService = Depends(get_dataset_service)
):
    """Get a ZFS dataset by name using clean architecture"""
    try:
        dataset = await service.get_dataset(name)
        if not dataset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dataset {name} not found"
            )
        return DatasetResponse.from_entity(dataset)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting dataset {name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/", response_model=List[DatasetResponse])
async def list_datasets(
    pool_name: Optional[str] = None,
    service: DatasetManagementService = Depends(get_dataset_service)
):
    """List ZFS datasets using clean architecture"""
    try:
        datasets = await service.list_datasets(pool_name)
        return [DatasetResponse.from_entity(dataset) for dataset in datasets]
    except Exception as e:
        logger.error(f"Unexpected error listing datasets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.put("/{name}/properties", response_model=Dict[str, str])
async def update_dataset_properties(
    name: str,
    request: UpdateDatasetRequest,
    service: DatasetManagementService = Depends(get_dataset_service)
):
    """Update ZFS dataset properties using clean architecture"""
    try:
        success = await service.update_dataset_properties(name, request.properties)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to update properties for dataset {name}"
            )
        return {"message": "Properties updated successfully"}
    except ZFSOperationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ZFS operation failed: {e}"
        )
    except Exception as e:
        logger.error(f"Unexpected error updating dataset {name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    name: str,
    force: bool = False,
    service: DatasetManagementService = Depends(get_dataset_service)
):
    """Delete a ZFS dataset using clean architecture"""
    try:
        success = await service.delete_dataset(name, force)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to delete dataset {name}"
            )
    except ZFSOperationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ZFS operation failed: {e}"
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting dataset {name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/{name}/usage", response_model=Dict[str, Any])
async def get_dataset_usage(
    name: str,
    service: DatasetManagementService = Depends(get_dataset_service)
):
    """Get dataset usage information using clean architecture"""
    try:
        usage = await service.get_dataset_usage(name)
        return usage
    except ZFSOperationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ZFS operation failed: {e}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting usage for dataset {name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/{name}/optimize", response_model=Dict[str, str])
async def optimize_dataset(
    name: str,
    migration_type: str = "docker",
    service: DatasetManagementService = Depends(get_dataset_service)
):
    """Optimize dataset for migration using clean architecture"""
    try:
        success = await service.optimize_dataset_for_migration(name, migration_type)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to optimize dataset {name}"
            )
        return {"message": f"Dataset {name} optimized for {migration_type} migration"}
    except ZFSOperationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ZFS operation failed: {e}"
        )
    except Exception as e:
        logger.error(f"Unexpected error optimizing dataset {name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/{name}/health", response_model=Dict[str, Any])
async def check_dataset_health(
    name: str,
    service: DatasetManagementService = Depends(get_dataset_service)
):
    """Check dataset health using clean architecture"""
    try:
        health = await service.check_dataset_health(name)
        return health
    except ZFSOperationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ZFS operation failed: {e}"
        )
    except Exception as e:
        logger.error(f"Unexpected error checking health for dataset {name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )