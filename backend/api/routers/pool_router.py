"""
Pool API router using the new service layer.
"""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse

from ..dependencies import get_pool_service
from ..models import (
    PoolScrubRequest, PoolResponse, 
    PoolListResponse, APIResponse
)
from ..middleware import create_success_response, create_error_response
from ...zfs_operations.services.pool_service import PoolService
from ...zfs_operations.core.exceptions.zfs_exceptions import ZFSException
from ...zfs_operations.core.exceptions.validation_exceptions import ValidationException


router = APIRouter(prefix="/api/v1/pools", tags=["pools"])


@router.get("/", response_model=PoolListResponse)
async def list_pools(
    pool_service: PoolService = Depends(get_pool_service)
):
    """List all ZFS pools."""
    try:
        result = await pool_service.list_pools()
        
        if result.is_success:
            pools = [pool.to_dict() for pool in result.value]
            return PoolListResponse(
                success=True,
                pools=pools,
                count=len(pools)
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list pools: {result.error}"
            )
    except Exception as e:
        return create_error_response(e)


@router.get("/{pool_name}", response_model=PoolResponse)
async def get_pool(
    pool_name: str,
    pool_service: PoolService = Depends(get_pool_service)
):
    """Get information about a specific pool."""
    try:
        result = await pool_service.get_pool(pool_name)
        
        if result.is_success:
            return PoolResponse(
                success=True,
                pool=result.value.to_dict()
            )
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Pool not found: {result.error}"
            )
    except Exception as e:
        return create_error_response(e)


@router.get("/{pool_name}/health", response_model=APIResponse)
async def get_pool_health(
    pool_name: str,
    pool_service: PoolService = Depends(get_pool_service)
):
    """Get detailed health information for a pool."""
    try:
        result = await pool_service.get_pool_health(pool_name)
        
        if result.is_success:
            return APIResponse(
                success=True,
                data={"health": result.value}
            )
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Failed to get pool health: {result.error}"
            )
    except Exception as e:
        return create_error_response(e)


@router.get("/{pool_name}/iostat", response_model=APIResponse)
async def get_pool_iostat(
    pool_name: str,
    interval: int = Query(1, description="Interval in seconds"),
    count: int = Query(1, description="Number of samples"),
    pool_service: PoolService = Depends(get_pool_service)
):
    """Get I/O statistics for a pool."""
    try:
        result = await pool_service.get_iostat(pool_name, interval, count)
        
        if result.is_success:
            return APIResponse(
                success=True,
                data={"iostat": result.value}
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to get pool iostat: {result.error}"
            )
    except Exception as e:
        return create_error_response(e)


@router.post("/{pool_name}/scrub", response_model=APIResponse)
async def manage_pool_scrub(
    pool_name: str,
    request: PoolScrubRequest,
    pool_service: PoolService = Depends(get_pool_service)
):
    """Start or stop a pool scrub operation."""
    try:
        if request.action == "start":
            result = await pool_service.start_scrub(pool_name)
        elif request.action == "stop":
            result = await pool_service.stop_scrub(pool_name)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scrub action: {request.action}. Valid actions are 'start' or 'stop'"
            )
        
        if result.is_success:
            return APIResponse(
                success=True,
                message=f"Pool scrub {request.action} initiated successfully"
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to {request.action} scrub: {result.error}"
            )
    except Exception as e:
        return create_error_response(e)


@router.get("/{pool_name}/history", response_model=APIResponse)
async def get_pool_history(
    pool_name: str,
    pool_service: PoolService = Depends(get_pool_service)
):
    """Get the history of a pool."""
    try:
        result = await pool_service.get_pool_history(pool_name)
        
        if result.is_success:
            return APIResponse(
                success=True,
                data={"history": result.value}
            )
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Failed to get pool history: {result.error}"
            )
    except Exception as e:
        return create_error_response(e)


@router.post("/{pool_name}/export", response_model=APIResponse)
async def export_pool(
    pool_name: str,
    force: bool = Query(False, description="Force export"),
    pool_service: PoolService = Depends(get_pool_service)
):
    """Export a pool."""
    try:
        result = await pool_service.export_pool(pool_name, force)
        
        if result.is_success:
            return APIResponse(
                success=True,
                message=f"Pool {pool_name} exported successfully"
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to export pool: {result.error}"
            )
    except Exception as e:
        return create_error_response(e)


@router.post("/{pool_name}/import", response_model=APIResponse)
async def import_pool(
    pool_name: str,
    new_name: Optional[str] = Query(None, description="New name for the pool"),
    force: bool = Query(False, description="Force import"),
    pool_service: PoolService = Depends(get_pool_service)
):
    """Import a pool."""
    try:
        result = await pool_service.import_pool(pool_name, new_name, force)
        
        if result.is_success:
            imported_name = new_name if new_name else pool_name
            return APIResponse(
                success=True,
                message=f"Pool imported as {imported_name}"
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to import pool: {result.error}"
            )
    except Exception as e:
        return create_error_response(e) 