from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import Optional

from ...config import get_config
from ...migration_service import MigrationService

router = APIRouter(
    prefix="/api/system",
    tags=["System"],
)

config = get_config()
migration_service = MigrationService()


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "transdock",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/info")
async def system_info():
    """Get system information relevant to migrations"""
    try:
        return await migration_service.get_system_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/zfs/status")
async def zfs_status():
    """Check ZFS availability and pool status"""
    try:
        return await migration_service.get_zfs_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e 