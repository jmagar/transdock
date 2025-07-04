from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
from typing import Optional
from docker.errors import DockerException
from .models import (
    MigrationRequest, MigrationResponse, HostValidationRequest, 
    HostCapabilities, ContainerMigrationRequest,
    ContainerDiscoveryResult, ContainerAnalysis, IdentifierType
)
from .migration_service import MigrationService
from .host_service import HostService
from .security_utils import SecurityUtils, SecurityValidationError
from .zfs_ops import ZFSOperations
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="TransDock - Container Migration Tool",
    description="Migrate Docker containers between machines using ZFS snapshots and Docker API",
    version="2.0.0")

# Enable CORS for web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
migration_service = MigrationService()
host_service = HostService()
zfs_service = ZFSOperations()

logger = logging.getLogger(__name__)


@app.get("/")
async def root():
    """Get basic API information"""
    return {
        "name": "TransDock",
        "version": "2.0.0",
        "description": "Container Migration Tool using Docker API and ZFS snapshots",
        "features": [
            "Docker API-based container discovery",
            "Container migration by name, project, or labels",
            "Multi-host support",
            "ZFS snapshots and rsync fallback",
            "Network recreation",
            "Real-time migration tracking"
        ]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "transdock"}


# Container Discovery and Analysis Endpoints

@app.get("/containers/discover")
async def discover_containers(
    container_identifier: str,
    identifier_type: IdentifierType,
    label_filters: Optional[str] = None,
    source_host: Optional[str] = None,
    source_ssh_user: str = "root",
    source_ssh_port: int = 22
) -> ContainerDiscoveryResult:
    """
    Discover containers for migration
    
    - **container_identifier**: Container name, project name, or identifier
    - **identifier_type**: project, name, or labels
    - **label_filters**: JSON string of label filters (for labels type)
    - **source_host**: Source host (None for local)
    """
    try:
        # Parse label filters if provided
        parsed_label_filters = None
        if label_filters:
            import json
            parsed_label_filters = json.loads(label_filters)
        
        return await migration_service.discover_containers(
            container_identifier=container_identifier,
            identifier_type=identifier_type,
            label_filters=parsed_label_filters,
            source_host=source_host,
            source_ssh_user=source_ssh_user,
            source_ssh_port=source_ssh_port
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Container discovery failed: {e}")
        raise HTTPException(status_code=500, detail=f"Container discovery failed: {e}") from e


@app.get("/containers/analyze")
async def analyze_containers(
    container_identifier: str,
    identifier_type: IdentifierType,
    label_filters: Optional[str] = None,
    source_host: Optional[str] = None
) -> ContainerAnalysis:
    """
    Analyze containers for migration readiness
    
    Provides insights about migration complexity, warnings, and recommendations
    """
    try:
        # Parse label filters if provided
        parsed_label_filters = None
        if label_filters:
            import json
            parsed_label_filters = json.loads(label_filters)
        
        return await migration_service.analyze_containers_for_migration(
            container_identifier=container_identifier,
            identifier_type=identifier_type,
            label_filters=parsed_label_filters,
            source_host=source_host
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Container analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Container analysis failed: {e}") from e


# Migration Endpoints

@app.post("/migrations/containers")
async def start_container_migration(request: ContainerMigrationRequest) -> MigrationResponse:
    """
    Start a container-based migration
    
    This is the primary migration endpoint that uses Docker API for container discovery
    """
    try:
        # Validate request
        if request.identifier_type == IdentifierType.LABELS and not request.label_filters:
            raise HTTPException(
                status_code=422, 
                detail="label_filters required when identifier_type is 'labels'"
            )
        
        migration_id = await migration_service.start_container_migration(request)
        
        return MigrationResponse(
            migration_id=migration_id,
            status="started",
            message=f"Container migration started for {request.container_identifier}"
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {e}") from e
    except Exception as e:
        logger.error(f"Migration failed to start: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed to start: {e}") from e


@app.post("/migrations")
async def start_legacy_migration(request: MigrationRequest) -> MigrationResponse:
    """
    Legacy migration endpoint (backward compatibility)
    
    Attempts to convert legacy requests to container-based migration
    """
    try:
        migration_id = await migration_service.start_migration(request)
        
        return MigrationResponse(
            migration_id=migration_id,
            status="started",
            message=f"Legacy migration started (converted to container migration)"
        )
        
    except Exception as e:
        logger.error(f"Legacy migration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Legacy migration failed: {e}") from e


@app.get("/migrations/{migration_id}")
async def get_migration_status(migration_id: str):
    """Get migration status by ID"""
    try:
        status = await migration_service.get_migration_status(migration_id)
        if not status:
            raise HTTPException(status_code=404, detail="Migration not found")
        return status
    except Exception as e:
        logger.error(f"Failed to get migration status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/migrations")
async def list_migrations():
    """List all active migrations"""
    try:
        return await migration_service.list_migrations()
    except Exception as e:
        logger.error(f"Failed to list migrations: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.delete("/migrations/{migration_id}")
async def cancel_migration(migration_id: str):
    """Cancel a running migration"""
    try:
        success = await migration_service.cancel_migration(migration_id)
        if not success:
            raise HTTPException(status_code=404, detail="Migration not found")
        return {"message": "Migration cancelled successfully"}
    except Exception as e:
        logger.error(f"Failed to cancel migration: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# System Information Endpoints

@app.get("/system/info")
async def get_system_info():
    """Get detailed system information"""
    try:
        # Get basic system information
        import platform
        
        return {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "architecture": platform.architecture()[0],
            "python_version": platform.python_version(),
            "docker_available": True  # We know Docker API is available if we got this far
        }
    except Exception as e:
        logger.error(f"Failed to get system info: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/system/docker")
async def get_docker_info():
    """Get Docker system information"""
    try:
        docker_ops = migration_service.docker_ops
        
        # Test Docker connection
        containers = await docker_ops.list_all_containers(include_stopped=False)
        all_containers = await docker_ops.list_all_containers(include_stopped=True)
        
        return {
            "available": True,
            "running_containers": len(containers),
            "total_containers": len(all_containers),
            "api_version": "Docker API connection successful"
        }
    except Exception as e:
        logger.error(f"Failed to get Docker info: {e}")
        return {
            "available": False,
            "error": str(e)
        }


# Host Management Endpoints

@app.post("/hosts/validate")
async def validate_host(request: HostValidationRequest) -> HostCapabilities:
    """Validate host capabilities and discover available paths"""
    try:
        # Validate Docker availability on target host
        docker_ops = migration_service.docker_ops
        docker_available = await docker_ops.validate_docker_on_target(
            target_host=request.hostname,
            ssh_user=request.ssh_user,
            ssh_port=request.ssh_port
        )
        
        # Check ZFS availability (basic check for now)
        zfs_available = await zfs_service.is_zfs_available()
        
        return HostCapabilities(
            hostname=request.hostname,
            docker_available=docker_available,
            zfs_available=zfs_available,
            compose_paths=[],
            appdata_paths=[],
            zfs_pools=[],
            storage_info=[]
        )
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {e}") from e
    except Exception as e:
        logger.error(f"Host validation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Host validation failed: {e}") from e


@app.get("/hosts/{hostname}/containers")
async def list_remote_containers(
    hostname: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    include_stopped: bool = True
):
    """List containers on remote host"""
    try:
        # Use Docker API via SSH to list containers on remote host
        docker_ops = migration_service.docker_ops
        containers = await docker_ops.list_all_containers(
            include_stopped=include_stopped,
            host=hostname,
            ssh_user=ssh_user
        )
        
        # Convert ContainerInfo objects to dictionaries for API response
        container_data = []
        for container in containers:
            container_data.append({
                "id": container.id,
                "name": container.name,
                "image": container.image,
                "state": container.state,
                "status": container.status,
                "labels": container.labels,
                "networks": container.networks,
                "created": container.created,
                "project_name": container.project_name,
                "service_name": container.service_name
            })
        
        return {
            "hostname": hostname,
            "containers": container_data,
            "total_containers": len(containers),
            "running_containers": len([c for c in containers if c.state == "running"])
        }
    except DockerException as e:
        logger.error(f"Failed to connect to Docker on {hostname}: {e}")
        raise HTTPException(status_code=503, detail=f"Docker not available on {hostname}: {e}") from e
    except Exception as e:
        logger.error(f"Failed to list remote containers: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# ZFS Endpoints (existing functionality)

@app.get("/zfs/status")
async def get_zfs_status():
    """Get ZFS status"""
    try:
        available = await zfs_service.is_zfs_available()
        if not available:
            return {"available": False, "error": "ZFS not available"}
        
        # Get pools using zfs list command
        try:
            validated_cmd = SecurityUtils.validate_zfs_command_args("list", "-H", "-o", "name", "-t", "pool")
            returncode, stdout, stderr = await zfs_service.run_command(validated_cmd)
            
            pools = []
            if returncode == 0:
                pools = [line.strip() for line in stdout.strip().split('\n') if line.strip()]
        except (ValueError, SecurityValidationError) as e:
            logger.warning(f"Failed to list ZFS pools: {e}")
            pools = []
        
        return {
            "available": True,
            "pools": pools
        }
    except Exception as e:
        logger.error(f"Failed to get ZFS status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/datasets")
async def list_datasets():
    """List available ZFS datasets with security validation"""
    try:
        # Use secure ZFS command validation
        validated_cmd = SecurityUtils.validate_zfs_command_args(
            "list", "-H", "-o", "name,mountpoint", "-t", "filesystem")
        returncode, stdout, stderr = await zfs_service.run_command(validated_cmd)
        
        if returncode != 0:
            raise HTTPException(status_code=500, detail=f"ZFS command failed: {stderr}")
        
        datasets = []
        for line in stdout.strip().split('\n'):
            if line:
                parts = line.split('\t')
                if len(parts) >= 2:
                    datasets.append({
                        "name": parts[0],
                        "mountpoint": parts[1]
                    })
        
        return {"datasets": datasets}
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {e}") from e
    except Exception as e:
        logger.error(f"Failed to list datasets: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# Utility Endpoints

@app.get("/version")
async def get_version():
    """Get API version information"""
    return {
        "version": "2.0.0",
        "api_type": "Docker API",
        "build_date": datetime.now(timezone.utc).isoformat(),
        "features": {
            "docker_api": True,
            "container_discovery": True,
            "multi_host": True,
            "zfs_snapshots": True,
            "network_recreation": True
        }
    }


@app.get("/features")
async def get_features():
    """Get available features and capabilities"""
    try:
        docker_available = True
        try:
            docker_ops = migration_service.docker_ops
            await docker_ops.list_all_containers(include_stopped=False)
        except Exception as e:
            logger.debug(f"Docker not available: {e}")
            docker_available = False
        
        zfs_available = await zfs_service.is_zfs_available()
        
        return {
            "docker_api": docker_available,
            "zfs_support": zfs_available,
            "container_discovery": docker_available,
            "project_based_migration": docker_available,
            "name_based_migration": docker_available,
            "label_based_migration": docker_available,
            "network_recreation": docker_available,
            "multi_host_support": True,
            "storage_validation": True,
            "security_validation": True
        }
    except Exception as e:
        logger.error(f"Failed to get features: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
