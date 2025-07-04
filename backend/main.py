from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
from .models import MigrationRequest, MigrationResponse
from .migration_service import MigrationService
from .security_utils import SecurityUtils, SecurityValidationError
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="TransDock - Docker Stack Migration Tool",
    description="Migrate Docker Compose stacks between machines using ZFS snapshots",
    version="1.0.0")

# Enable CORS for web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize migration service
migration_service = MigrationService()


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "TransDock",
        "version": "1.0.0",
        "description": "Docker Stack Migration Tool using ZFS snapshots"
    }


@app.post("/api/migrations/start", response_model=MigrationResponse)
async def create_migration(request: MigrationRequest):
    """Start a new migration process with security validation"""
    try:
        # Security validation for all user inputs
        SecurityUtils.validate_migration_request(
            compose_dataset=request.compose_dataset,
            target_host=request.target_host,
            ssh_user=request.ssh_user,
            ssh_port=request.ssh_port,
            target_base_path=request.target_base_path
        )

        migration_id = await migration_service.start_migration(request)
        return MigrationResponse(
            migration_id=migration_id,
            status="started",
            message="Migration process started successfully"
        )
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/migrations")
async def list_migrations():
    """List all migrations"""
    try:
        migrations = await migration_service.list_migrations()
        return {"migrations": migrations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/migrations/{migration_id}/status")
async def get_migration_status(migration_id: str):
    """Get the status of a specific migration with input validation"""
    try:
        # Validate migration_id format to prevent injection
        if not migration_id or len(migration_id) > 64:
            raise SecurityValidationError("Invalid migration ID format")

        # Allow only alphanumeric characters, hyphens, and underscores
        if not all(c.isalnum() or c in '-_' for c in migration_id):
            raise SecurityValidationError(
                "Migration ID contains invalid characters")

        status = await migration_service.get_migration_status(migration_id)
        if not status:
            raise HTTPException(status_code=404, detail="Migration not found")
        return status
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "transdock",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/zfs/status")
async def zfs_status():
    """Check ZFS availability and pool status"""
    try:
        return await migration_service.get_zfs_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/datasets")
async def list_datasets():
    """List available ZFS datasets with security validation"""
    try:
        zfs_ops = migration_service.zfs_ops

        # Use secure ZFS command validation
        validated_cmd = SecurityUtils.validate_zfs_command_args(
            "list", "-H", "-o", "name,mountpoint", "-t", "filesystem")
        returncode, stdout, stderr = await zfs_ops.run_command(validated_cmd)

        if returncode != 0:
            raise HTTPException(status_code=500,
                                detail=f"Failed to list datasets: {stderr}")

        datasets = []
        for line in stdout.strip().split('\n'):
            if line.strip():
                parts = line.split('\t')
                if len(parts) >= 2:
                    datasets.append({
                        "name": parts[0],
                        "mountpoint": parts[1]
                    })

        return {"datasets": datasets}
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/compose/stacks")
async def list_compose_stacks():
    """List available Docker Compose stacks with path validation"""
    try:
        stacks = await migration_service.get_compose_stacks()
        return {"stacks": stacks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/compose/stacks/{stack_name}")
async def analyze_compose_stack(stack_name: str):
    """Analyze a compose stack with security validation"""
    try:
        stack_info = await migration_service.get_stack_info(stack_name)
        return stack_info
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/system/info")
async def system_info():
    """Get system information relevant to migrations"""
    try:
        return await migration_service.get_system_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/migrations/{migration_id}/cancel")
async def cancel_migration(migration_id: str):
    """Cancel a running migration"""
    try:
        # Validate migration_id format
        if not migration_id or len(migration_id) > 64:
            raise SecurityValidationError("Invalid migration ID format")

        if not all(c.isalnum() or c in '-_' for c in migration_id):
            raise SecurityValidationError(
                "Migration ID contains invalid characters")

        success = await migration_service.cancel_migration(migration_id)
        if success:
            return {
                "success": True,
                "message": "Migration cancelled successfully"}
        raise HTTPException(
            status_code=400,
            detail="Failed to cancel migration")
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except KeyError as e:
        raise HTTPException(
            status_code=404,
            detail="Migration not found") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/migrations/{migration_id}/cleanup")
async def cleanup_migration(migration_id: str):
    """Clean up migration resources"""
    try:
        # Validate migration_id format
        if not migration_id or len(migration_id) > 64:
            raise SecurityValidationError("Invalid migration ID format")

        if not all(c.isalnum() or c in '-_' for c in migration_id):
            raise SecurityValidationError(
                "Migration ID contains invalid characters")

        success = await migration_service.cleanup_migration(migration_id)
        if success:
            return {
                "success": True,
                "message": "Migration cleaned up successfully"}
        raise HTTPException(
            status_code=400,
            detail="Failed to cleanup migration")
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except KeyError as e:
        raise HTTPException(
            status_code=404,
            detail="Migration not found") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
