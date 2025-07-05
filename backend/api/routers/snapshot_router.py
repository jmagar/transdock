"""
Snapshot API router using the new service layer.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query

from ..dependencies import get_snapshot_service
from ..models import (
    SnapshotCreateRequest, SnapshotResponse, 
    SnapshotListResponse, APIResponse
)
from ..middleware import create_error_response
from ...zfs_operations.services.snapshot_service import SnapshotService
from ...zfs_operations.core.value_objects.dataset_name import DatasetName



router = APIRouter(prefix="/api/v1/snapshots", tags=["snapshots"])


@router.post("/", response_model=SnapshotResponse, status_code=201)
async def create_snapshot(
    request: SnapshotCreateRequest,
    snapshot_service: SnapshotService = Depends(get_snapshot_service)
):
    """Create a new ZFS snapshot."""
    try:
        dataset_name = DatasetName.from_string(request.dataset_name)
        result = await snapshot_service.create_snapshot(dataset_name, request.snapshot_name, request.recursive)
        
        if result.is_success:
            return SnapshotResponse(
                success=True,
                message=f"Snapshot {request.dataset_name}@{request.snapshot_name} created successfully",
                snapshot=result.value.to_dict()
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to create snapshot: {result.error}"
            )
    except Exception as e:
        return create_error_response(e)


@router.get("/", response_model=SnapshotListResponse)
async def list_snapshots(
    dataset_name: Optional[str] = Query(None, description="Filter by dataset name"),
    recursive: bool = Query(False, description="Recursive listing"),
    snapshot_service: SnapshotService = Depends(get_snapshot_service)
):
    """List all ZFS snapshots."""
    try:
        dataset = None
        if dataset_name:
            dataset = DatasetName.from_string(dataset_name)
            
        result = await snapshot_service.list_snapshots(dataset, recursive)
        
        if result.is_success:
            snapshots = [snapshot.to_dict() for snapshot in result.value]
            return SnapshotListResponse(
                success=True,
                snapshots=snapshots,
                count=len(snapshots)
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list snapshots: {result.error}"
            )
    except Exception as e:
        return create_error_response(e)


@router.get("/{dataset_name}@{snapshot_name}", response_model=SnapshotResponse)
async def get_snapshot(
    dataset_name: str,
    snapshot_name: str,
    snapshot_service: SnapshotService = Depends(get_snapshot_service)
):
    """Get information about a specific snapshot."""
    try:
        dataset = DatasetName.from_string(dataset_name)
        result = await snapshot_service.get_snapshot(dataset, snapshot_name)
        
        if result.is_success:
            return SnapshotResponse(
                success=True,
                snapshot=result.value.to_dict()
            )
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Snapshot not found: {result.error}"
            )
    except Exception as e:
        return create_error_response(e)


@router.delete("/{dataset_name}@{snapshot_name}", response_model=APIResponse)
async def delete_snapshot(
    dataset_name: str,
    snapshot_name: str,
    force: bool = Query(False, description="Force deletion"),
    recursive: bool = Query(False, description="Recursive deletion"),
    snapshot_service: SnapshotService = Depends(get_snapshot_service)
):
    """Delete a ZFS snapshot."""
    try:
        dataset = DatasetName.from_string(dataset_name)
        result = await snapshot_service.destroy_snapshot(dataset, snapshot_name, force, recursive)
        
        if result.is_success:
            return APIResponse(
                success=True,
                message=f"Snapshot {dataset_name}@{snapshot_name} deleted successfully"
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to delete snapshot: {result.error}"
            )
    except Exception as e:
        return create_error_response(e)


@router.post("/{dataset_name}@{snapshot_name}/rollback", response_model=APIResponse)
async def rollback_snapshot(
    dataset_name: str,
    snapshot_name: str,
    force: bool = Query(False, description="Force rollback"),
    snapshot_service: SnapshotService = Depends(get_snapshot_service)
):
    """Rollback to a snapshot."""
    try:
        dataset = DatasetName.from_string(dataset_name)
        result = await snapshot_service.rollback_to_snapshot(dataset, snapshot_name, force)
        
        if result.is_success:
            return APIResponse(
                success=True,
                message=f"Rolled back to snapshot {dataset_name}@{snapshot_name}"
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to rollback snapshot: {result.error}"
            )
    except Exception as e:
        return create_error_response(e)


@router.post("/{dataset_name}/incremental", response_model=SnapshotResponse)
async def create_incremental_snapshot(
    dataset_name: str,
    base_snapshot_name: str = Query(..., description="Base snapshot name"),
    new_snapshot_name: str = Query(..., description="New snapshot name"),
    snapshot_service: SnapshotService = Depends(get_snapshot_service)
):
    """Create an incremental snapshot."""
    try:
        dataset = DatasetName.from_string(dataset_name)
        result = await snapshot_service.create_incremental_snapshot(
            dataset, base_snapshot_name, new_snapshot_name
        )
        
        if result.is_success:
            return SnapshotResponse(
                success=True,
                message=f"Incremental snapshot {dataset_name}@{new_snapshot_name} created successfully",
                snapshot=result.value.to_dict()
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to create incremental snapshot: {result.error}"
            )
    except Exception as e:
        return create_error_response(e)


@router.post("/{dataset_name}/retention", response_model=APIResponse)
async def apply_retention_policy(
    dataset_name: str,
    retention_days: int = Query(..., description="Number of days to retain snapshots"),
    dry_run: bool = Query(False, description="Perform dry run without actually deleting"),
    snapshot_service: SnapshotService = Depends(get_snapshot_service)
):
    """Apply retention policy to snapshots."""
    try:
        dataset = DatasetName.from_string(dataset_name)
        result = await snapshot_service.apply_retention_policy(dataset, retention_days, dry_run)
        
        if result.is_success:
            return APIResponse(
                success=True,
                message=f"Retention policy applied to {dataset_name}",
                data=result.value
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to apply retention policy: {result.error}"
            )
    except Exception as e:
        return create_error_response(e) 