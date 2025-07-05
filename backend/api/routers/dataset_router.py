"""
Dataset API router using the new service layer.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse

from ..dependencies import get_dataset_service
from ..models import (
    DatasetCreateRequest, DatasetPropertyUpdateRequest, 
    DatasetResponse, DatasetListResponse, APIResponse
)
from ..middleware import create_success_response
from ...zfs_operations.services.dataset_service import DatasetService
from ...zfs_operations.core.value_objects.dataset_name import DatasetName
from ...zfs_operations.core.exceptions.zfs_exceptions import ZFSException
from ...zfs_operations.core.exceptions.validation_exceptions import ValidationException


router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])


@router.post("/", response_model=DatasetResponse, status_code=201)
async def create_dataset(
    request: DatasetCreateRequest,
    dataset_service: DatasetService = Depends(get_dataset_service)
):
    """Create a new ZFS dataset."""
    try:
        dataset_name = DatasetName.from_string(request.name)
        result = await dataset_service.create_dataset(dataset_name, request.properties)
        
        if result.is_success:
            return DatasetResponse(
                success=True,
                message=f"Dataset {request.name} created successfully",
                dataset=result.value.to_dict()
            )
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create dataset: {result.error}"
        )
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ZFSException as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/", response_model=DatasetListResponse)
async def list_datasets(
    pool_name: Optional[str] = Query(None, description="Filter by pool name"),
    dataset_service: DatasetService = Depends(get_dataset_service)
):
    """List all ZFS datasets."""
    try:
        result = await dataset_service.list_datasets(pool_name)
        
        if result.is_success:
            datasets = [dataset.to_dict() for dataset in result.value]
            return DatasetListResponse(
                success=True,
                datasets=datasets,
                count=len(datasets)
            )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list datasets: {result.error}"
        )
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ZFSException as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{dataset_name}", response_model=DatasetResponse)
async def get_dataset(
    dataset_name: str,
    dataset_service: DatasetService = Depends(get_dataset_service)
):
    """Get information about a specific dataset."""
    try:
        name = DatasetName.from_string(dataset_name)
        result = await dataset_service.get_dataset(name)
        
        if result.is_success:
            return DatasetResponse(
                success=True,
                dataset=result.value.to_dict()
            )
        raise HTTPException(
            status_code=404,
            detail=f"Dataset not found: {result.error}"
        )
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ZFSException as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/{dataset_name}", response_model=APIResponse)
async def delete_dataset(
    dataset_name: str,
    recursive: bool = Query(False, description="Recursively delete dataset and children"),
    force: bool = Query(False, description="Force deletion"),
    dataset_service: DatasetService = Depends(get_dataset_service)
):
    """Delete a ZFS dataset."""
    try:
        name = DatasetName.from_string(dataset_name)
        result = await dataset_service.destroy_dataset(name, force=force, recursive=recursive)
        
        if result.is_success:
            return APIResponse(
                success=True,
                message=f"Dataset {dataset_name} deleted successfully"
            )
        raise HTTPException(
            status_code=400,
            detail=f"Failed to delete dataset: {result.error}"
        )
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ZFSException as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put("/{dataset_name}/properties", response_model=APIResponse)
async def set_dataset_property(
    dataset_name: str,
    request: DatasetPropertyUpdateRequest,
    dataset_service: DatasetService = Depends(get_dataset_service)
):
    """Set a property on a dataset."""
    try:
        name = DatasetName.from_string(dataset_name)
        result = await dataset_service.set_property(
            name, request.property_name, request.value
        )
        
        if result.is_success:
            return APIResponse(
                success=True,
                message=f"Property {request.property_name} set to {request.value}"
            )
        raise HTTPException(
            status_code=400,
            detail=f"Failed to set property: {result.error}"
        )
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ZFSException as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{dataset_name}/usage", response_model=APIResponse)
async def get_dataset_usage(
    dataset_name: str,
    dataset_service: DatasetService = Depends(get_dataset_service)
):
    """Get usage information for a dataset."""
    try:
        name = DatasetName.from_string(dataset_name)
        result = await dataset_service.get_usage(name)
        
        if result.is_success:
            return APIResponse(
                success=True,
                data={"usage": result.value}
            )
        raise HTTPException(
            status_code=404,
            detail=f"Failed to get usage: {result.error}"
        )
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ZFSException as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/{dataset_name}/mount", response_model=APIResponse)
async def mount_dataset(
    dataset_name: str,
    dataset_service: DatasetService = Depends(get_dataset_service)
):
    """Mount a dataset."""
    try:
        name = DatasetName.from_string(dataset_name)
        result = await dataset_service.mount_dataset(name)
        
        if result.is_success:
            return APIResponse(
                success=True,
                message=f"Dataset {dataset_name} mounted successfully"
            )
        raise HTTPException(
            status_code=400,
            detail=f"Failed to mount dataset: {result.error}"
        )
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ZFSException as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/{dataset_name}/unmount", response_model=APIResponse)
async def unmount_dataset(
    dataset_name: str,
    force: bool = Query(False, description="Force unmount"),
    dataset_service: DatasetService = Depends(get_dataset_service)
):
    """Unmount a dataset."""
    try:
        name = DatasetName.from_string(dataset_name)
        result = await dataset_service.unmount_dataset(name, force=force)
        
        if result.is_success:
            return APIResponse(
                success=True,
                message=f"Dataset {dataset_name} unmounted successfully"
            )
        raise HTTPException(
            status_code=400,
            detail=f"Failed to unmount dataset: {result.error}"
        )
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ZFSException as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}") 