"""Migration API endpoints"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

from ....core.entities.migration_entity import Migration
from ....core.value_objects.host_connection import HostConnection
from ....application.migration.migration_orchestration_service import MigrationOrchestrationService
from ....core.exceptions.migration_exceptions import MigrationOperationError, MigrationNotFoundError
from ....infrastructure.database.config import get_db_session
from ....infrastructure.database.repositories.migration_repository_impl import MigrationRepositoryImpl
from ..dependencies import get_migration_service

router = APIRouter(prefix="/migrations", tags=["migrations"])


# Request/Response Models
class CreateMigrationRequest(BaseModel):
    """Request model for creating a migration"""
    name: str = Field(..., description="Migration name")
    compose_stack_path: str = Field(..., description="Path to docker-compose.yml file")
    target_host: str = Field(..., description="Target host (hostname or IP)")
    target_port: Optional[int] = Field(22, description="Target SSH port")
    target_username: Optional[str] = Field("root", description="Target SSH username")
    target_base_path: str = Field(..., description="Target base path for migration")
    use_zfs: bool = Field(True, description="Use ZFS for efficient transfer")
    transfer_method: str = Field("zfs_send", description="Transfer method: zfs_send or rsync")
    source_host: Optional[str] = Field("localhost", description="Source host")
    source_port: Optional[int] = Field(22, description="Source SSH port")
    source_username: Optional[str] = Field("root", description="Source SSH username")


class MigrationResponse(BaseModel):
    """Response model for migration"""
    id: str
    name: str
    status: str
    source_host: str
    target_host: str
    compose_stack_path: str
    target_base_path: str
    use_zfs: bool
    transfer_method: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    progress_percentage: float
    current_step: Optional[Dict[str, Any]]


class MigrationStatusResponse(BaseModel):
    """Response model for migration status"""
    id: str
    name: str
    status: str
    progress_percentage: float
    source_host: str
    target_host: str
    compose_stack_path: str
    target_base_path: str
    use_zfs: bool
    transfer_method: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    duration: Optional[float]
    steps_completed: int
    total_steps: int
    error_message: Optional[str]
    current_step: Optional[Dict[str, Any]]
    failed_step: Optional[Dict[str, Any]]
    estimated_remaining_seconds: Optional[float]
    task_running: Optional[bool]


class ValidationResponse(BaseModel):
    """Response model for migration validation"""
    valid: bool
    errors: List[str]
    warnings: List[str]
    requirements: List[str]


# Endpoints
@router.post("/", response_model=MigrationResponse)
async def create_migration(
    request: CreateMigrationRequest,
    background_tasks: BackgroundTasks,
    service: MigrationOrchestrationService = Depends(get_migration_service)
) -> MigrationResponse:
    """Create a new migration"""
    try:
        # Create host connections
        source_host = HostConnection(
            hostname=request.source_host or "localhost",
            port=request.source_port or 22,
            username=request.source_username or "root"
        )
        
        target_host = HostConnection(
            hostname=request.target_host,
            port=request.target_port or 22,
            username=request.target_username or "root"
        )
        
        # Create migration
        migration = await service.create_migration(
            name=request.name,
            compose_stack_path=request.compose_stack_path,
            target_host=target_host,
            target_base_path=request.target_base_path,
            use_zfs=request.use_zfs,
            transfer_method=request.transfer_method,
            source_host=source_host
        )
        
        # Convert to response
        return MigrationResponse(
            id=migration.id,
            name=migration.name,
            status=migration.status.value,
            source_host=str(migration.source_host),
            target_host=str(migration.target_host),
            compose_stack_path=migration.compose_stack_path,
            target_base_path=migration.target_base_path,
            use_zfs=migration.use_zfs,
            transfer_method=migration.transfer_method,
            created_at=migration.created_at,
            started_at=migration.started_at,
            completed_at=migration.completed_at,
            error_message=migration.error_message,
            progress_percentage=migration.progress_percentage,
            current_step=_get_current_step_info(migration)
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{migration_id}/start")
async def start_migration(
    migration_id: str,
    service: MigrationOrchestrationService = Depends(get_migration_service)
) -> Dict[str, str]:
    """Start a migration"""
    try:
        success = await service.start_migration(migration_id)
        if success:
            return {"status": "started", "migration_id": migration_id}
        else:
            raise HTTPException(status_code=400, detail="Failed to start migration")
            
    except MigrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MigrationOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{migration_id}/cancel")
async def cancel_migration(
    migration_id: str,
    service: MigrationOrchestrationService = Depends(get_migration_service)
) -> Dict[str, str]:
    """Cancel a running migration"""
    try:
        success = await service.cancel_migration(migration_id)
        if success:
            return {"status": "cancelled", "migration_id": migration_id}
        else:
            raise HTTPException(status_code=400, detail="Failed to cancel migration")
            
    except MigrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MigrationOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{migration_id}", response_model=MigrationResponse)
async def get_migration(
    migration_id: str,
    service: MigrationOrchestrationService = Depends(get_migration_service)
) -> MigrationResponse:
    """Get migration details"""
    try:
        migration = await service.get_migration(migration_id)
        if not migration:
            raise HTTPException(status_code=404, detail="Migration not found")
        
        return MigrationResponse(
            id=migration.id,
            name=migration.name,
            status=migration.status.value,
            source_host=str(migration.source_host),
            target_host=str(migration.target_host),
            compose_stack_path=migration.compose_stack_path,
            target_base_path=migration.target_base_path,
            use_zfs=migration.use_zfs,
            transfer_method=migration.transfer_method,
            created_at=migration.created_at,
            started_at=migration.started_at,
            completed_at=migration.completed_at,
            error_message=migration.error_message,
            progress_percentage=migration.progress_percentage,
            current_step=_get_current_step_info(migration)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{migration_id}/status", response_model=MigrationStatusResponse)
async def get_migration_status(
    migration_id: str,
    service: MigrationOrchestrationService = Depends(get_migration_service)
) -> MigrationStatusResponse:
    """Get detailed migration status"""
    try:
        status = await service.get_migration_status(migration_id)
        return MigrationStatusResponse(**status)
        
    except MigrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[MigrationResponse])
async def list_migrations(
    service: MigrationOrchestrationService = Depends(get_migration_service)
) -> List[MigrationResponse]:
    """List all migrations"""
    try:
        migrations = await service.list_migrations()
        
        return [
            MigrationResponse(
                id=m.id,
                name=m.name,
                status=m.status.value,
                source_host=str(m.source_host),
                target_host=str(m.target_host),
                compose_stack_path=m.compose_stack_path,
                target_base_path=m.target_base_path,
                use_zfs=m.use_zfs,
                transfer_method=m.transfer_method,
                created_at=m.created_at,
                started_at=m.started_at,
                completed_at=m.completed_at,
                error_message=m.error_message,
                progress_percentage=m.progress_percentage,
                current_step=_get_current_step_info(m)
            )
            for m in migrations
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate", response_model=ValidationResponse)
async def validate_migration(
    request: CreateMigrationRequest,
    service: MigrationOrchestrationService = Depends(get_migration_service)
) -> ValidationResponse:
    """Validate a migration request without creating it"""
    try:
        target_host = HostConnection(
            hostname=request.target_host,
            port=request.target_port or 22,
            username=request.target_username or "root"
        )
        
        result = await service.validate_migration_request(
            compose_stack_path=request.compose_stack_path,
            target_host=target_host,
            target_base_path=request.target_base_path
        )
        
        return ValidationResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{migration_id}")
async def delete_migration(
    migration_id: str,
    service: MigrationOrchestrationService = Depends(get_migration_service)
) -> Dict[str, str]:
    """Delete a migration (only if completed or failed)"""
    try:
        # Get migration to check status
        migration = await service.get_migration(migration_id)
        if not migration:
            raise HTTPException(status_code=404, detail="Migration not found")
        
        if migration.is_running():
            raise HTTPException(
                status_code=400, 
                detail="Cannot delete running migration. Cancel it first."
            )
        
        # Use repository directly for deletion
        from ....infrastructure.database.config import get_db_session
        async for session in get_db_session():
            repo = MigrationRepositoryImpl(session)
            success = await repo.delete(migration_id)
            
        if success:
            return {"status": "deleted", "migration_id": migration_id}
        else:
            raise HTTPException(status_code=400, detail="Failed to delete migration")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Helper functions
def _get_current_step_info(migration: Migration) -> Optional[Dict[str, Any]]:
    """Get current step information"""
    current_step = migration.get_current_step()
    if current_step:
        return {
            "name": current_step.name,
            "type": current_step.step_type.value,
            "status": current_step.status.value,
            "progress": current_step.progress_percentage
        }
    return None