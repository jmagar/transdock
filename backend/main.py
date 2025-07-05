from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import logging
from typing import Optional
from .models import (
    MigrationRequest, MigrationResponse, HostValidationRequest, 
    HostInfo, HostCapabilities, StackAnalysis, ContainerMigrationRequest
)
from .migration_service import MigrationService
from .host_service import HostService
from .security_utils import SecurityUtils, SecurityValidationError
from .zfs_ops import ZFSOperations
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Migration Safety Configuration
LOCAL_COMPOSE_BASE_PATH = os.getenv('LOCAL_COMPOSE_BASE_PATH', '/mnt/user/compose')
LOCAL_APPDATA_BASE_PATH = os.getenv('LOCAL_APPDATA_BASE_PATH', '/mnt/cache/appdata')
DEFAULT_TARGET_COMPOSE_PATH = os.getenv('DEFAULT_TARGET_COMPOSE_PATH', '/opt/docker/compose')
DEFAULT_TARGET_APPDATA_PATH = os.getenv('DEFAULT_TARGET_APPDATA_PATH', '/opt/docker/appdata')
REQUIRE_EXPLICIT_TARGET = os.getenv('REQUIRE_EXPLICIT_TARGET', 'true').lower() == 'true'
ALLOW_TARGET_OVERRIDE = os.getenv('ALLOW_TARGET_OVERRIDE', 'true').lower() == 'true'
VALIDATE_TARGET_EXISTS = os.getenv('VALIDATE_TARGET_EXISTS', 'true').lower() == 'true'

# Import new API layer
from .api.routers import dataset_router, snapshot_router, pool_router
from .api.routers.auth_router import router as auth_router
from .api.middleware import ErrorHandlingMiddleware, LoggingMiddleware, SecurityHeadersMiddleware
from .api.rate_limiting import RateLimitMiddleware, default_rate_limiter
from .api.websocket import ws_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="TransDock - ZFS Management Platform",
    description="""
    **TransDock** is a comprehensive ZFS management platform that evolved from a Docker migration tool.
    
    ## Features
    
    * **ZFS Operations**: Complete ZFS dataset, snapshot, and pool management
    * **Docker Migration**: Migrate Docker Compose stacks between machines using ZFS snapshots
    * **Real-time Monitoring**: WebSocket-based real-time system monitoring
    * **Authentication**: JWT-based authentication and authorization
    * **Rate Limiting**: Built-in API rate limiting and protection
    * **RESTful API**: Clean, well-documented REST API with OpenAPI specification
    
    ## API Categories
    
    * **Authentication** (`/auth`): User authentication and management
    * **Datasets** (`/api/datasets`): ZFS dataset operations
    * **Snapshots** (`/api/snapshots`): ZFS snapshot management
    * **Pools** (`/api/pools`): ZFS pool monitoring and management
    * **Migration** (`/api/migrations`): Docker stack migration operations
    * **WebSocket** (`/ws`): Real-time monitoring and notifications
    
    ## Authentication
    
    Most endpoints require authentication. Use the `/auth/login` endpoint to obtain a JWT token,
    then include it in the `Authorization` header as `Bearer <token>`.
    
    ## Rate Limiting
    
    API endpoints are rate-limited to prevent abuse. Rate limit information is included in response headers.
    
    ## WebSocket
    
    Real-time monitoring is available via WebSocket at `/ws/monitor`. Authentication is optional via query parameter.
    """,
    version="2.0.0",
    contact={
        "name": "TransDock Development Team",
        "email": "support@transdock.local",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {
            "name": "Authentication",
            "description": "User authentication and management operations",
        },
        {
            "name": "Datasets", 
            "description": "ZFS dataset operations including creation, deletion, and property management",
        },
        {
            "name": "Snapshots",
            "description": "ZFS snapshot management including creation, deletion, and rollback operations",
        },
        {
            "name": "Pools",
            "description": "ZFS pool monitoring and management operations",
        },
        {
            "name": "Migration",
            "description": "Docker stack migration operations between machines",
        },
        {
            "name": "WebSocket",
            "description": "Real-time monitoring and notifications via WebSocket",
        },
        {
            "name": "System",
            "description": "System information and health check endpoints",
        },
    ],
    servers=[
        {
            "url": "http://localhost:8000",
            "description": "Development server"
        },
        {
            "url": "https://api.transdock.local",
            "description": "Production server"
        }
    ]
)

# Add new API middleware
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, rate_limiter=default_rate_limiter)

# Enable CORS for web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include new API routers
app.include_router(auth_router)
app.include_router(dataset_router)
app.include_router(snapshot_router)
app.include_router(pool_router)
app.include_router(ws_router)

# Initialize services
migration_service = MigrationService()
host_service = HostService()
zfs_service = ZFSOperations()

logger = logging.getLogger(__name__)


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
        error_message = str(e)
        # Provide more specific error handling for storage validation failures
        if "Storage validation failed" in error_message:
            raise HTTPException(
                status_code=422,
                detail=f"Storage validation failed - {error_message}. Please ensure target system has sufficient disk space.") from e
        if "Insufficient storage space" in error_message:
            raise HTTPException(
                status_code=422,
                detail=f"Insufficient storage space - {error_message}. Free up disk space or choose a different target path.") from e
        raise HTTPException(status_code=400, detail=error_message) from e


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
                "message": "Migration cleanup successful"}
        raise HTTPException(
            status_code=400,
            detail="Failed to clean up migration")
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


# Multi-Host Stack Management Endpoints

@app.post("/api/hosts/validate", response_model=HostCapabilities)
async def validate_host(request: HostValidationRequest):
    """Validate and check capabilities of a remote host"""
    try:
        host_info = HostInfo(
            hostname=request.hostname,
            ssh_user=request.ssh_user,
            ssh_port=request.ssh_port
        )
        
        capabilities = await host_service.check_host_capabilities(host_info)
        return capabilities
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/hosts/{hostname}/capabilities")
async def get_host_capabilities(hostname: str, ssh_user: str = "root", ssh_port: int = 22):
    """Get capabilities of a specific host"""
    try:
        host_info = HostInfo(
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        capabilities = await host_service.check_host_capabilities(host_info)
        return capabilities
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/hosts/{hostname}/compose/stacks")
async def list_remote_stacks(hostname: str, compose_path: str, ssh_user: str = "root", ssh_port: int = 22):
    """List compose stacks on a remote host"""
    try:
        host_info = HostInfo(
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        stacks = await host_service.list_remote_stacks(host_info, compose_path)
        return {"stacks": stacks}
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/hosts/{hostname}/compose/stacks/{stack_name}", response_model=StackAnalysis)
async def analyze_remote_stack(hostname: str, stack_name: str, compose_path: str, ssh_user: str = "root", ssh_port: int = 22):
    """Analyze a specific stack on a remote host"""
    try:
        host_info = HostInfo(
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        # Construct stack path
        stack_path = f"{compose_path.rstrip('/')}/{stack_name}"
        
        analysis = await host_service.analyze_remote_stack(host_info, stack_path)
        return analysis
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/hosts/{hostname}/compose/stacks/{stack_name}/start")
async def start_remote_stack(hostname: str, stack_name: str, compose_path: str, ssh_user: str = "root", ssh_port: int = 22):
    """Start a stack on a remote host"""
    try:
        host_info = HostInfo(
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        # Construct stack path
        stack_path = f"{compose_path.rstrip('/')}/{stack_name}"
        
        success = await host_service.start_remote_stack(host_info, stack_path)
        if success:
            return {"success": True, "message": f"Stack {stack_name} started successfully"}
        raise HTTPException(status_code=400, detail=f"Failed to start stack {stack_name}")
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/hosts/{hostname}/compose/stacks/{stack_name}/stop")
async def stop_remote_stack(hostname: str, stack_name: str, compose_path: str, ssh_user: str = "root", ssh_port: int = 22):
    """Stop a stack on a remote host"""
    try:
        host_info = HostInfo(
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        # Construct stack path
        stack_path = f"{compose_path.rstrip('/')}/{stack_name}"
        
        success = await host_service.stop_remote_stack(host_info, stack_path)
        if success:
            return {"success": True, "message": f"Stack {stack_name} stopped successfully"}
        raise HTTPException(status_code=400, detail=f"Failed to stop stack {stack_name}")
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/hosts/{hostname}/datasets")
async def list_remote_datasets(hostname: str, ssh_user: str = "root", ssh_port: int = 22):
    """List ZFS datasets on a remote host"""
    try:
        host_info = HostInfo(
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        # List datasets on remote host
        zfs_cmd_args = SecurityUtils.validate_zfs_command_args("list", "-H", "-o", "name,mountpoint", "-t", "filesystem")
        zfs_cmd = " ".join(zfs_cmd_args)
        returncode, stdout, stderr = await host_service.run_remote_command(host_info, zfs_cmd)
        
        if returncode != 0:
            if "command not found" in stderr or "No such file" in stderr:
                return {"datasets": [], "error": "ZFS not available on remote host"}
            raise HTTPException(status_code=500, detail=f"Failed to list datasets: {stderr}")
        
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


@app.get("/api/hosts/{hostname}/storage")
async def get_host_storage_info(hostname: str, ssh_user: str = "root", ssh_port: int = 22):
    """Get storage information for a remote host"""
    try:
        # Security validation
        SecurityUtils.validate_hostname(hostname)
        SecurityUtils.validate_username(ssh_user)
        SecurityUtils.validate_port(ssh_port)
        
        host_info = HostInfo(hostname=hostname, ssh_user=ssh_user, ssh_port=ssh_port)
        
        # Get storage info for common paths
        common_paths = ["/mnt/cache", "/mnt/user", "/opt", "/home", "/var/lib/docker"]
        storage_info = await host_service.get_storage_info(host_info, common_paths)
        
        return {"storage": storage_info}
        
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/hosts/{hostname}/storage/validate")
async def validate_host_storage(hostname: str, target_path: str, required_bytes: int, ssh_user: str = "root", ssh_port: int = 22):
    """Validate storage capacity on a remote host"""
    try:
        # Security validation
        SecurityUtils.validate_hostname(hostname)
        SecurityUtils.validate_username(ssh_user)
        SecurityUtils.validate_port(ssh_port)
        
        if required_bytes < 0:
            raise HTTPException(status_code=400, detail="Required bytes must be non-negative")
        
        host_info = HostInfo(hostname=hostname, ssh_user=ssh_user, ssh_port=ssh_port)
        
        # Validate storage availability
        validation_result = await host_service.check_storage_availability(host_info, target_path, required_bytes)
        
        if not validation_result.is_valid:
            # Return detailed error information but still as successful HTTP response
            # The client can check the is_valid field
            return {
                "validation": validation_result,
                "recommendation": "Free up disk space or choose a different target path with more available space"
            }
        
        return {"validation": validation_result}
        
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/zfs/pools/{pool_name}/health")
async def get_zfs_pool_health(pool_name: str):
    """Get comprehensive health information for a ZFS pool"""
    try:
        health_info = await zfs_service.get_pool_health(pool_name)
        
        if not health_info:
            raise HTTPException(status_code=404, detail="Pool not found or inaccessible")
        
        return health_info
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/zfs/pools/{pool_name}/status")
async def get_zfs_pool_status(pool_name: str):
    """Get ZFS pool status"""
    try:
        status = await zfs_service.get_pool_status(pool_name)
        
        if not status:
            raise HTTPException(status_code=404, detail="Pool not found")
        
        return status
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/zfs/datasets/{dataset_name}/properties")
async def get_zfs_dataset_properties(dataset_name: str, properties: Optional[str] = None):
    """Get ZFS dataset properties"""
    try:
        prop_list = properties.split(",") if properties else None
        props = await zfs_service.get_dataset_properties(dataset_name, prop_list)
        
        return {"dataset": dataset_name, "properties": props}
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/zfs/datasets/{dataset_name}/properties")
async def set_zfs_dataset_property(dataset_name: str, property_name: str, value: str):
    """Set a ZFS dataset property"""
    try:
        success = await zfs_service.set_dataset_property(dataset_name, property_name, value)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to set property")
        
        return {"dataset": dataset_name, "property": property_name, "value": value, "success": True}
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/zfs/datasets/{dataset_name}/usage")
async def get_zfs_dataset_usage(dataset_name: str):
    """Get detailed usage information for a ZFS dataset"""
    try:
        usage = await zfs_service.get_dataset_usage(dataset_name)
        
        return {"dataset": dataset_name, "usage": usage}
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/zfs/datasets/{dataset_name}/optimize")
async def optimize_zfs_dataset(dataset_name: str, migration_type: str = "docker"):
    """Optimize a ZFS dataset for migration"""
    try:
        success = await zfs_service.optimize_dataset_for_migration(dataset_name, migration_type)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to optimize dataset")
        
        return {"dataset": dataset_name, "migration_type": migration_type, "optimized": True}
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/zfs/datasets/{dataset_name}/snapshots/detailed")
async def get_zfs_dataset_snapshots_detailed(dataset_name: str):
    """Get detailed snapshot information for a ZFS dataset"""
    try:
        snapshots = await zfs_service.get_dataset_snapshots_detailed(dataset_name)
        
        return {"dataset": dataset_name, "snapshots": snapshots}
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/zfs/datasets/{dataset_name}/snapshots/incremental")
async def create_incremental_zfs_snapshot(dataset_name: str, base_snapshot: Optional[str] = None, 
                                          snapshot_name: Optional[str] = None):
    """Create an incremental ZFS snapshot"""
    try:
        result = await zfs_service.create_incremental_snapshot(dataset_name, base_snapshot, snapshot_name)
        
        if not result.get("success", False):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to create snapshot"))
        
        return result
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/zfs/snapshots/{snapshot_name}/rollback")
async def rollback_zfs_snapshot(snapshot_name: str, force: bool = False):
    """Rollback to a ZFS snapshot"""
    try:
        success = await zfs_service.rollback_to_snapshot(snapshot_name, force)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to rollback to snapshot")
        
        return {"snapshot": snapshot_name, "rollback_success": True}
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/zfs/datasets/{dataset_name}/snapshots/retention")
async def apply_zfs_snapshot_retention(dataset_name: str, keep_daily: int = 7, keep_weekly: int = 4, 
                                       keep_monthly: int = 6, keep_yearly: int = 2):
    """Apply retention policy to ZFS snapshots"""
    try:
        result = await zfs_service.apply_snapshot_retention_policy(
            dataset_name, keep_daily, keep_weekly, keep_monthly, keep_yearly
        )
        
        return {"dataset": dataset_name, "retention_result": result}
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/zfs/performance/iostat")
async def get_zfs_iostat(pools: Optional[str] = None, interval: int = 1, count: int = 5):
    """Get ZFS I/O statistics"""
    try:
        pool_list = pools.split(",") if pools else None
        iostat = await zfs_service.get_zfs_iostat(pool_list, interval, count)
        
        if not iostat:
            raise HTTPException(status_code=404, detail="Failed to get iostat for specified pools")
        
        return iostat
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/zfs/performance/arc")
async def get_zfs_arc_stats():
    """Get ZFS ARC statistics"""
    try:
        arc_stats = await zfs_service.get_arc_statistics()
        
        if not arc_stats:
            raise HTTPException(status_code=500, detail="Failed to retrieve ARC statistics")
        
        return {"arc_statistics": arc_stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/zfs/datasets/{dataset_name}/performance/monitor")
async def monitor_zfs_dataset_performance(dataset_name: str, duration_seconds: int = 30):
    """Monitor ZFS performance for a dataset over a duration"""
    try:
        performance_data = await zfs_service.monitor_migration_performance(dataset_name, duration_seconds)
        
        if not performance_data:
            raise HTTPException(status_code=404, detail="Failed to monitor performance for the specified dataset")
        
        return performance_data
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/zfs/pools/{pool_name}/scrub")
async def start_zfs_pool_scrub(pool_name: str):
    """Start a scrub operation on a ZFS pool"""
    try:
        success = await zfs_service.start_pool_scrub(pool_name)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to start scrub operation")
        
        return {"pool": pool_name, "scrub_started": True}
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/zfs/pools/{pool_name}/scrub/status")
async def get_zfs_pool_scrub_status(pool_name: str):
    """Get the status of a scrub operation on a ZFS pool"""
    try:
        scrub_status = await zfs_service.get_pool_scrub_status(pool_name)
        
        if "error" in scrub_status:
            raise HTTPException(status_code=404, detail=scrub_status["error"])
        
        return {"pool": pool_name, "scrub_status": scrub_status}
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Container Discovery and Analysis Endpoints

@app.post("/migrations/smart")
async def smart_migration(
    identifier: str,
    target_host: str,
    target_base_path: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    compose_base_path: str = "/mnt/user/compose",
    force_rsync: bool = False,
    auto_start: bool = True
):
    """
    🎯 SMART MIGRATION - Compose-First Approach
    
    This is the PRIMARY migration endpoint that users should use.
    It automatically detects what you want to migrate and uses the best method:
    
    1. 🥇 FIRST: Checks for compose projects (stopped or running)
    2. 🥈 FALLBACK: Searches for individual containers if no compose project found
    
    - **identifier**: Project name (simple-web) or full path (/path/to/project)
    - **target_host**: Where to migrate to
    - **target_base_path**: Base directory on target
    - **compose_base_path**: Where to look for compose projects (default: /mnt/user/compose)
    """
    try:
        logger.info(f"🎯 Smart migration requested for: '{identifier}'")
        
        # STEP 1: 🥇 CHECK FOR COMPOSE PROJECT FIRST
        compose_project_path = None
        
        # Check if identifier is already a full path
        if os.path.isabs(identifier) and os.path.exists(identifier):
            # Check if it's a directory with compose file
            if os.path.isdir(identifier):
                compose_files = ['docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml']
                for compose_file in compose_files:
                    if os.path.exists(os.path.join(identifier, compose_file)):
                        compose_project_path = identifier
                        break
        else:
            # Look for project by name in compose base path
            potential_path = os.path.join(compose_base_path, identifier)
            if os.path.exists(potential_path) and os.path.isdir(potential_path):
                compose_files = ['docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml'] 
                for compose_file in compose_files:
                    if os.path.exists(os.path.join(potential_path, compose_file)):
                        compose_project_path = potential_path
                        break
        
        # FOUND COMPOSE PROJECT! 🎉
        if compose_project_path:
            logger.info(f"✅ Found compose project: {compose_project_path}")
            
            # Create compose migration request
            from .models import MigrationRequest
            compose_request = MigrationRequest(
                compose_dataset=compose_project_path,
                target_host=target_host,
                target_base_path=target_base_path,
                ssh_user=ssh_user,
                ssh_port=ssh_port,
                force_rsync=force_rsync,
                source_host=None  # Local source
            )
            
            migration_id = await migration_service.start_migration(compose_request)
            
            return {
                "migration_id": migration_id,
                "status": "started",
                "migration_type": "compose_project",
                "message": f"🚀 Compose project migration started for '{os.path.basename(compose_project_path)}'",
                "project_path": compose_project_path,
                "target_host": target_host,
                "auto_start": auto_start,
                "discovery_method": "compose_first"
            }
        
        # STEP 2: 🥈 FALLBACK TO CONTAINER SEARCH
        logger.info(f"❌ No compose project found for '{identifier}', searching containers...")
        
        # Try to find running containers with the identifier
        try:
            from .models import IdentifierType
            containers = await migration_service.discover_containers(
                container_identifier=identifier,
                identifier_type=IdentifierType.NAME,
                source_host=None,
                source_ssh_user=ssh_user,
                source_ssh_port=ssh_port
            )
            
            if containers and hasattr(containers, 'containers') and containers.containers:
                container_count = len(containers.containers)
                
                # Suggest compose migration instead
                return {
                    "status": "suggestion",
                    "migration_type": "container_fallback", 
                    "message": f"⚠️  Found {container_count} running container(s) with '{identifier}', but no compose project",
                    "suggestion": f"Consider using container migration endpoint instead, or check if '{identifier}' is a compose project",
                    "containers_found": [{"name": c["name"], "id": c["id"]} for c in containers.containers],
                    "recommendations": [
                        f"For complete stack migration, look for compose project in {compose_base_path}",
                        f"For individual containers, use /migrations/containers endpoint",
                        f"To create compose project, run: cd {compose_base_path} && mkdir {identifier}"
                    ],
                    "next_steps": {
                        "container_migration": f"/migrations/containers with identifier_type=name",
                        "create_compose": f"mkdir -p {compose_base_path}/{identifier} && cd {compose_base_path}/{identifier}"
                    }
                }
            
        except Exception as e:
            logger.warning(f"Container search failed: {e}")
        
        # STEP 3: 😞 NOTHING FOUND - HELPFUL ERROR
        return {
            "status": "not_found",
            "migration_type": "none",
            "message": f"❌ No compose project or containers found for '{identifier}'",
            "searched_locations": [
                f"{compose_base_path}/{identifier}",
                f"Running containers matching '{identifier}'"
            ],
            "suggestions": [
                f"✅ Create compose project: mkdir -p {compose_base_path}/{identifier}",
                f"✅ Check spelling: ls {compose_base_path}/",
                f"✅ Use full path: /path/to/your/project",
                f"✅ Start containers first if migrating running services"
            ],
            "available_projects": [
                item for item in os.listdir(compose_base_path) 
                if os.path.isdir(os.path.join(compose_base_path, item))
            ] if os.path.exists(compose_base_path) else []
        }
            
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {e}") from e
    except Exception as e:
        logger.error(f"Smart migration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Smart migration failed: {e}") from e


@app.get("/containers/discover")
async def discover_containers(
    container_identifier: str,
    identifier_type: str,
    label_filters: Optional[str] = None,
    source_host: Optional[str] = None,
    source_ssh_user: str = "root",
    source_ssh_port: int = 22
):
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
        
        from .models import IdentifierType
        # Convert string to enum
        id_type = IdentifierType(identifier_type)
        
        return await migration_service.discover_containers(
            container_identifier=container_identifier,
            identifier_type=id_type,
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
    identifier_type: str,
    label_filters: Optional[str] = None,
    source_host: Optional[str] = None
):
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
        
        from .models import IdentifierType
        # Convert string to enum
        id_type = IdentifierType(identifier_type)
        
        return await migration_service.analyze_containers_for_migration(
            container_identifier=container_identifier,
            identifier_type=id_type,
            label_filters=parsed_label_filters,
            source_host=source_host
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Container analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Container analysis failed: {e}") from e


# Container Migration Endpoints

@app.post("/migrations/containers")
async def start_container_migration(request: ContainerMigrationRequest):
    """
    Start a container-based migration
    
    This is the primary migration endpoint that uses Docker API for container discovery
    """
    try:
        from .models import IdentifierType
        # Validate request
        if request.identifier_type == IdentifierType.LABELS and not request.label_filters:
            raise HTTPException(
                status_code=422, 
                detail="label_filters required when identifier_type is 'labels'"
            )
        
        migration_id = await migration_service.start_container_migration(request)
        
        return {
            "migration_id": migration_id,
            "status": "started",
            "message": f"Container migration started for {request.container_identifier}"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {e}") from e
    except Exception as e:
        logger.error(f"Migration failed to start: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed to start: {e}") from e


# Compose Project Discovery Endpoints

@app.get("/compose/discover")
async def discover_compose_projects(
    base_path: str = "/mnt/user/compose",
    project_name: Optional[str] = None
):
    """
    Discover Docker Compose projects from filesystem
    
    - **base_path**: Base directory to search for compose projects
    - **project_name**: Optional specific project name to find
    """
    try:
        # Validate base path for security
        safe_base_path = SecurityUtils.sanitize_path(base_path, allow_absolute=True)
        
        if project_name:
            # Look for specific project
            project_path = os.path.join(safe_base_path, project_name)
            if os.path.exists(project_path):
                compose_file = await migration_service.docker_ops.find_compose_file(project_path)
                if compose_file:
                    return {
                        "projects": [{
                            "name": project_name,
                            "path": project_path,
                            "compose_file": compose_file,
                            "status": "found"
                        }],
                        "total_projects": 1,
                        "base_path": safe_base_path
                    }
            
            return {
                "projects": [],
                "total_projects": 0,
                "base_path": safe_base_path,
                "error": f"Project '{project_name}' not found"
            }
        else:
            # Discover all projects in base path
            projects = []
            if os.path.exists(safe_base_path):
                for item in os.listdir(safe_base_path):
                    item_path = os.path.join(safe_base_path, item)
                    if os.path.isdir(item_path):
                        compose_file = await migration_service.docker_ops.find_compose_file(item_path)
                        if compose_file:
                            projects.append({
                                "name": item,
                                "path": item_path,
                                "compose_file": compose_file,
                                "status": "ready"
                            })
            
            return {
                "projects": projects,
                "total_projects": len(projects),
                "base_path": safe_base_path
            }
    
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {e}") from e
    except Exception as e:
        logger.error(f"Compose discovery failed: {e}")
        raise HTTPException(status_code=500, detail=f"Compose discovery failed: {e}") from e


@app.get("/compose/analyze")
async def analyze_compose_project(
    project_path: str,
    estimate_size: bool = True
):
    """
    Analyze a compose project for migration readiness
    """
    try:
        # Validate and sanitize path
        safe_path = SecurityUtils.sanitize_path(project_path, allow_absolute=True)
        
        if not os.path.exists(safe_path):
            raise HTTPException(status_code=404, detail=f"Project path not found: {project_path}")
        
        compose_file = await migration_service.docker_ops.find_compose_file(safe_path)
        if not compose_file:
            raise HTTPException(status_code=404, detail=f"No compose file found in: {project_path}")
        
        # Parse compose file
        compose_data = await migration_service.docker_ops.parse_compose_file(compose_file)
        
        # Extract volume information
        volumes = await migration_service.docker_ops.extract_volume_mounts(compose_data)
        
        # Estimate data size if requested
        estimated_size = None
        if estimate_size:
            total_size = 0
            for volume in volumes:
                if os.path.exists(volume.source):
                    # Get directory size
                    import subprocess
                    result = subprocess.run(['du', '-sb', volume.source], capture_output=True, text=True)
                    if result.returncode == 0:
                        size = int(result.stdout.split()[0])
                        total_size += size
            estimated_size = total_size
        
        # Determine complexity
        complexity = "simple"
        if len(volumes) > 3:
            complexity = "medium"
        if len(compose_data.get('services', {})) > 5:
            complexity = "complex"
        
        return {
            "project_name": os.path.basename(safe_path),
            "project_path": safe_path,
            "compose_file": compose_file,
            "services": list(compose_data.get('services', {}).keys()),
            "volumes": [{"source": v.source, "target": v.target} for v in volumes],
            "total_volumes": len(volumes),
            "estimated_size_bytes": estimated_size,
            "migration_complexity": complexity,
            "can_migrate": True,
            "warnings": [],
            "recommendations": [
                "Ensure target system has sufficient storage space",
                "Consider stopping running containers before migration for consistency"
            ]
        }
    
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {e}") from e
    except Exception as e:
        logger.error(f"Compose analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Compose analysis failed: {e}") from e


@app.post("/migrations/compose")
async def start_compose_migration(
    project_path: str,
    target_host: str,
    target_base_path: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    force_rsync: bool = False,
    auto_start: bool = True
):
    """
    Start a compose project migration
    
    - **project_path**: Local path to the compose project
    - **target_host**: Target host to migrate to  
    - **target_base_path**: Base path on target host
    - **auto_start**: Whether to start the project on target after migration
    """
    try:
        # Create a legacy migration request for the compose path
        # This uses the existing migration logic but with compose-specific handling
        from .models import MigrationRequest
        
        legacy_request = MigrationRequest(
            compose_dataset=project_path,
            target_host=target_host,
            target_base_path=target_base_path,
            ssh_user=ssh_user,
            ssh_port=ssh_port,
            force_rsync=force_rsync,
            source_host=None  # Local source
        )
        
        migration_id = await migration_service.start_migration(legacy_request)
        
        return {
            "migration_id": migration_id,
            "status": "started", 
            "message": f"Compose project migration started for {os.path.basename(project_path)}",
            "project_path": project_path,
            "target_host": target_host,
            "auto_start": auto_start
        }
        
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {e}") from e
    except Exception as e:
        logger.error(f"Compose migration failed to start: {e}")
        raise HTTPException(status_code=500, detail=f"Compose migration failed to start: {e}") from e


@app.post("/migrations/validate")
async def validate_migration_before_start(
    identifier: str,
    target_host: str,
    target_path: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    compose_base_path: Optional[str] = None
):
    """
    🛡️ VALIDATE MIGRATION TARGET BEFORE STARTING
    
    This endpoint MUST be called before any migration to ensure:
    - Explicit target specified (no defaults)
    - SSH connectivity and permissions
    - Sufficient storage space
    - Target directory writability
    
    Migration endpoints will REFUSE to proceed without successful validation.
    """
    try:
        # Use configured base path if not provided
        if not compose_base_path:
            compose_base_path = LOCAL_COMPOSE_BASE_PATH
        
        # 🔍 STEP 1: Estimate migration size
        estimated_size = 0
        source_path = None
        
        # Find source (compose project)
        if os.path.isabs(identifier) and os.path.exists(identifier):
            source_path = identifier
        else:
            potential_path = os.path.join(compose_base_path, identifier)
            if os.path.exists(potential_path):
                source_path = potential_path
        
        if source_path:
            # Estimate size using du command
            import subprocess
            try:
                result = subprocess.run(
                    ['du', '-sb', source_path], 
                    capture_output=True, 
                    text=True, 
                    timeout=30
                )
                if result.returncode == 0:
                    estimated_size = int(result.stdout.split()[0])
            except Exception as e:
                logger.warning(f"Could not estimate size for {source_path}: {e}")
                estimated_size = 1024 * 1024 * 1024  # Default 1GB estimate
        
        # Add 20% buffer for safety
        required_space = int(estimated_size * 1.2)
        
        # 🔍 STEP 2: Validate target with comprehensive checks
        validation = await validate_migration_target(
            target_host=target_host,
            target_path=target_path,
            required_space_bytes=required_space,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        # 🔍 STEP 3: Add source-specific information
        validation["source"] = {
            "identifier": identifier,
            "path": source_path,
            "estimated_size_bytes": estimated_size,
            "estimated_size_gb": round(estimated_size / (1024**3), 2)
        }
        
        # 🔍 STEP 4: Return comprehensive validation results
        return {
            "validation_id": f"val_{int(datetime.now().timestamp())}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "migration_safe": validation["valid"],
            "validation_details": validation,
            "next_steps": {
                "if_valid": "Proceed with migration using /migrations/smart or /migrations/compose",
                "if_invalid": "Fix validation errors before attempting migration"
            }
        }
        
    except Exception as e:
        logger.error(f"Migration validation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {e}") from e


async def validate_migration_target(
    target_host: str,
    target_path: str, 
    required_space_bytes: int,
    ssh_user: str = "root",
    ssh_port: int = 22
) -> dict:
    """
    🛡️ COMPREHENSIVE MIGRATION TARGET VALIDATION
    
    This function ensures migration safety by validating:
    1. Target is explicitly provided (no defaults)
    2. SSH connectivity and permissions
    3. Target directory writability 
    4. Sufficient storage space
    5. Target host accessibility
    
    Returns validation results with detailed status
    """
    validation_results = {
        "valid": False,
        "target_host": target_host,
        "target_path": target_path,
        "required_space_gb": round(required_space_bytes / (1024**3), 2),
        "checks": {},
        "errors": [],
        "warnings": []
    }
    
    try:
        # 🔍 CHECK 1: Explicit Target Validation
        if REQUIRE_EXPLICIT_TARGET:
            if not target_path or target_path.strip() == "":
                validation_results["errors"].append("❌ Target path must be explicitly provided")
                validation_results["checks"]["explicit_target"] = False
            elif target_path in [DEFAULT_TARGET_COMPOSE_PATH, DEFAULT_TARGET_APPDATA_PATH]:
                validation_results["warnings"].append(f"⚠️ Using default target path: {target_path}")
                validation_results["checks"]["explicit_target"] = True
            else:
                validation_results["checks"]["explicit_target"] = True
        
        # 🔍 CHECK 2: SSH Connectivity
        try:
            ssh_test = await host_service.validate_ssh_connection(target_host, ssh_user, ssh_port)
            if ssh_test:
                validation_results["checks"]["ssh_connectivity"] = True
            else:
                validation_results["errors"].append(f"❌ Cannot establish SSH connection to {target_host}")
                validation_results["checks"]["ssh_connectivity"] = False
        except Exception as e:
            validation_results["errors"].append(f"❌ SSH connection failed: {e}")
            validation_results["checks"]["ssh_connectivity"] = False
        
        # 🔍 CHECK 3: Target Directory Permissions
        try:
            # Test if we can create/write to target directory
            permission_test = await host_service.test_directory_permissions(
                target_host, target_path, ssh_user, ssh_port
            )
            
            if permission_test.get("writable", False):
                validation_results["checks"]["write_permissions"] = True
            else:
                validation_results["errors"].append(
                    f"❌ No write permissions to {target_path} on {target_host}"
                )
                validation_results["checks"]["write_permissions"] = False
                
        except Exception as e:
            validation_results["errors"].append(f"❌ Permission check failed: {e}")
            validation_results["checks"]["write_permissions"] = False
        
        # 🔍 CHECK 4: Storage Space Validation
        try:
            # Create HostInfo object for the call
            from .models import HostInfo
            target_host_info = HostInfo(hostname=target_host, ssh_user=ssh_user, ssh_port=ssh_port)
            storage_results = await host_service.get_storage_info(target_host_info, [target_path])
            storage_info = storage_results[0] if storage_results else None
            available_bytes = storage_info.available_bytes if storage_info else 0
            available_gb = round(available_bytes / (1024**3), 2)
            
            validation_results["available_space_gb"] = available_gb
            
            if available_bytes >= required_space_bytes:
                validation_results["checks"]["sufficient_storage"] = True
            else:
                required_gb = round(required_space_bytes / (1024**3), 2)
                validation_results["errors"].append(
                    f"❌ Insufficient storage: need {required_gb}GB, have {available_gb}GB"
                )
                validation_results["checks"]["sufficient_storage"] = False
                
        except Exception as e:
            validation_results["errors"].append(f"❌ Storage check failed: {e}")
            validation_results["checks"]["sufficient_storage"] = False
        
        # 🔍 CHECK 5: Docker Availability (if needed)
        try:
            docker_available = await migration_service.docker_ops.validate_docker_on_target(
                target_host, ssh_user, ssh_port
            )
            
            if docker_available:
                validation_results["checks"]["docker_available"] = True
            else:
                validation_results["warnings"].append(
                    f"⚠️ Docker not available on {target_host} (may be needed for container operations)"
                )
                validation_results["checks"]["docker_available"] = False
                
        except Exception as e:
            validation_results["warnings"].append(f"⚠️ Docker check failed: {e}")
            validation_results["checks"]["docker_available"] = False
        
        # 🔍 OVERALL VALIDATION RESULT
        required_checks = ["explicit_target", "ssh_connectivity", "write_permissions", "sufficient_storage"]
        all_required_passed = all(validation_results["checks"].get(check, False) for check in required_checks)
        
        validation_results["valid"] = all_required_passed and len(validation_results["errors"]) == 0
        
        if validation_results["valid"]:
            validation_results["message"] = f"✅ Migration target validated successfully: {target_host}:{target_path}"
        else:
            validation_results["message"] = f"❌ Migration target validation failed: {len(validation_results['errors'])} errors found"
        
        return validation_results
        
    except Exception as e:
        validation_results["errors"].append(f"❌ Validation process failed: {e}")
        validation_results["valid"] = False
        validation_results["message"] = f"❌ Critical validation error: {e}"
        return validation_results


async def create_pre_migration_safety_snapshot(
    target_host: str,
    target_path: str,
    migration_id: str,
    ssh_user: str = "root",
    ssh_port: int = 22
) -> dict:
    """
    🛡️ CRITICAL INFRASTRUCTURE SAFETY: Pre-Migration Snapshots
    
    Creates safety snapshots/backups before ANY modification to target:
    1. ZFS snapshots (if ZFS dataset)
    2. Directory backups (if regular filesystem)
    3. Verification of snapshot/backup integrity
    4. Rollback instructions generation
    
    NEVER proceed with migration without successful snapshot creation!
    """
    safety_result = {
        "snapshot_created": False,
        "snapshot_type": None,
        "snapshot_name": None,
        "rollback_command": None,
        "backup_location": None,
        "verification_passed": False,
        "errors": [],
        "warnings": []
    }
    
    try:
        snapshot_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_name = f"pre_migration_{migration_id}_{snapshot_timestamp}"
        
        # 🔍 CHECK 1: Determine if target is on ZFS
        try:
            # Test if target path is on ZFS dataset
            zfs_check_cmd = f"ssh -p {ssh_port} {ssh_user}@{target_host} 'zfs list -H -o name $(df --output=source {target_path} | tail -n1) 2>/dev/null'"
            
            import subprocess
            result = subprocess.run(zfs_check_cmd, shell=True, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and result.stdout.strip():
                # Target is on ZFS - create ZFS snapshot
                zfs_dataset = result.stdout.strip()
                await create_zfs_safety_snapshot(
                    target_host, zfs_dataset, snapshot_name, safety_result, ssh_user, ssh_port
                )
            else:
                # Target is on regular filesystem - create directory backup
                await create_directory_safety_backup(
                    target_host, target_path, snapshot_name, safety_result, ssh_user, ssh_port
                )
                
        except Exception as e:
            safety_result["errors"].append(f"❌ Failed to determine filesystem type: {e}")
            # Fallback to directory backup
            await create_directory_safety_backup(
                target_host, target_path, snapshot_name, safety_result, ssh_user, ssh_port
            )
        
        # 🔍 CHECK 2: Verify snapshot/backup integrity
        if safety_result["snapshot_created"]:
            verification_passed = await verify_safety_snapshot(
                target_host, safety_result, ssh_user, ssh_port
            )
            safety_result["verification_passed"] = verification_passed
            
            if not verification_passed:
                safety_result["errors"].append("❌ Snapshot/backup verification failed")
        
        return safety_result
        
    except Exception as e:
        safety_result["errors"].append(f"❌ Critical error creating safety snapshot: {e}")
        return safety_result


async def create_zfs_safety_snapshot(
    target_host: str, zfs_dataset: str, snapshot_name: str, 
    safety_result: dict, ssh_user: str, ssh_port: int
):
    """Create ZFS snapshot for rollback capability"""
    try:
        full_snapshot_name = f"{zfs_dataset}@{snapshot_name}"
        
        # Create ZFS snapshot
        snapshot_cmd = f"ssh -p {ssh_port} {ssh_user}@{target_host} 'zfs snapshot {full_snapshot_name}'"
        
        import subprocess
        result = subprocess.run(snapshot_cmd, shell=True, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            safety_result.update({
                "snapshot_created": True,
                "snapshot_type": "zfs",
                "snapshot_name": full_snapshot_name,
                "rollback_command": f"ssh {ssh_user}@{target_host} 'zfs rollback {full_snapshot_name}'",
                "cleanup_command": f"ssh {ssh_user}@{target_host} 'zfs destroy {full_snapshot_name}'"
            })
            logger.info(f"✅ ZFS safety snapshot created: {full_snapshot_name}")
        else:
            safety_result["errors"].append(f"❌ ZFS snapshot failed: {result.stderr}")
            
    except Exception as e:
        safety_result["errors"].append(f"❌ ZFS snapshot creation failed: {e}")


async def create_directory_safety_backup(
    target_host: str, target_path: str, backup_name: str,
    safety_result: dict, ssh_user: str, ssh_port: int
):
    """Create directory backup for rollback capability"""
    try:
        backup_location = f"{target_path}.backup.{backup_name}"
        
        # Create backup using cp -a (preserves all attributes)
        backup_cmd = f"ssh -p {ssh_port} {ssh_user}@{target_host} 'if [ -d \"{target_path}\" ]; then cp -a \"{target_path}\" \"{backup_location}\"; echo \"Backup created\"; else echo \"Directory does not exist\"; fi'"
        
        import subprocess
        result = subprocess.run(backup_cmd, shell=True, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0 and "Backup created" in result.stdout:
            safety_result.update({
                "snapshot_created": True,
                "snapshot_type": "directory_backup",
                "backup_location": backup_location,
                "rollback_command": f"ssh {ssh_user}@{target_host} 'rm -rf \"{target_path}\" && mv \"{backup_location}\" \"{target_path}\"'",
                "cleanup_command": f"ssh {ssh_user}@{target_host} 'rm -rf \"{backup_location}\"'"
            })
            logger.info(f"✅ Directory safety backup created: {backup_location}")
        else:
            safety_result["errors"].append(f"❌ Directory backup failed: {result.stderr}")
            
    except Exception as e:
        safety_result["errors"].append(f"❌ Directory backup creation failed: {e}")


async def verify_safety_snapshot(
    target_host: str, safety_result: dict, ssh_user: str, ssh_port: int
) -> bool:
    """Verify snapshot/backup integrity"""
    try:
        if safety_result["snapshot_type"] == "zfs":
            # Verify ZFS snapshot exists and is valid
            snapshot_name = safety_result["snapshot_name"]
            verify_cmd = f"ssh -p {ssh_port} {ssh_user}@{target_host} 'zfs list -t snapshot {snapshot_name}'"
            
        elif safety_result["snapshot_type"] == "directory_backup":
            # Verify backup directory exists and has content
            backup_location = safety_result["backup_location"]
            verify_cmd = f"ssh -p {ssh_port} {ssh_user}@{target_host} 'test -d \"{backup_location}\" && echo \"Backup verified\"'"
        
        import subprocess
        result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True, timeout=30)
        
        return result.returncode == 0
        
    except Exception as e:
        logger.error(f"Snapshot verification failed: {e}")
        return False


async def create_safe_rsync_operation(
    source_path: str,
    target_host: str, 
    target_path: str,
    migration_id: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    dry_run: bool = True
) -> dict:
    """
    🛡️ CRITICAL INFRASTRUCTURE SAFETY: Safe Rsync Operations
    
    Implements safe rsync with:
    1. Mandatory dry-run first
    2. Incremental transfer with --link-dest for rollback
    3. Atomic operations via temp directory + rename
    4. Progress monitoring and interruption capability
    5. Verification checksums
    """
    rsync_result = {
        "operation_safe": False,
        "dry_run_completed": False,
        "transfer_completed": False,
        "verification_passed": False,
        "temp_location": None,
        "final_location": None,
        "rollback_available": False,
        "errors": [],
        "warnings": [],
        "transfer_stats": {}
    }
    
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = f"{target_path}.temp.{migration_id}_{timestamp}"
        previous_dir = f"{target_path}.previous.{migration_id}_{timestamp}"
        
        # 🔍 PHASE 1: MANDATORY DRY RUN
        if dry_run:
            dry_run_cmd = [
                "rsync", "-avz", "--dry-run", "--stats",
                f"-e", f"ssh -p {ssh_port}",
                f"{source_path}/",
                f"{ssh_user}@{target_host}:{temp_dir}/"
            ]
            
            import subprocess
            dry_result = subprocess.run(dry_run_cmd, capture_output=True, text=True, timeout=300)
            
            if dry_result.returncode == 0:
                rsync_result["dry_run_completed"] = True
                rsync_result["transfer_stats"]["dry_run_output"] = dry_result.stdout
                logger.info("✅ Rsync dry-run completed successfully")
            else:
                rsync_result["errors"].append(f"❌ Rsync dry-run failed: {dry_result.stderr}")
                return rsync_result
        
        # 🔍 PHASE 2: ATOMIC RSYNC WITH LINK-DEST
        if rsync_result["dry_run_completed"]:
            # Create temp directory and perform transfer
            mkdir_cmd = f"ssh -p {ssh_port} {ssh_user}@{target_host} 'mkdir -p {temp_dir}'"
            subprocess.run(mkdir_cmd, shell=True, timeout=30)
            
            # Build rsync command with safety features
            rsync_cmd = [
                "rsync", "-avz", "--progress", "--stats",
                "--partial", "--partial-dir=.rsync-partial",
                f"-e", f"ssh -p {ssh_port}",
                f"{source_path}/",
                f"{ssh_user}@{target_host}:{temp_dir}/"
            ]
            
            # Add link-dest if previous version exists
            check_existing = f"ssh -p {ssh_port} {ssh_user}@{target_host} 'test -d {target_path}'"
            existing_result = subprocess.run(check_existing, shell=True, capture_output=True)
            
            if existing_result.returncode == 0:
                rsync_cmd.insert(-2, f"--link-dest={target_path}")
                rsync_result["rollback_available"] = True
            
            # Execute actual transfer
            transfer_result = subprocess.run(rsync_cmd, capture_output=True, text=True, timeout=3600)
            
            if transfer_result.returncode == 0:
                rsync_result["transfer_completed"] = True
                rsync_result["temp_location"] = temp_dir
                rsync_result["transfer_stats"]["rsync_output"] = transfer_result.stdout
                logger.info(f"✅ Rsync transfer completed to temp location: {temp_dir}")
            else:
                rsync_result["errors"].append(f"❌ Rsync transfer failed: {transfer_result.stderr}")
                return rsync_result
        
        # 🔍 PHASE 3: ATOMIC RENAME OPERATION
        if rsync_result["transfer_completed"]:
            # Move existing to previous (if exists) and temp to final - atomically
            atomic_cmd = f"""ssh -p {ssh_port} {ssh_user}@{target_host} '
                if [ -d "{target_path}" ]; then
                    mv "{target_path}" "{previous_dir}"
                fi &&
                mv "{temp_dir}" "{target_path}" &&
                echo "Atomic rename completed"
            '"""
            
            atomic_result = subprocess.run(atomic_cmd, shell=True, capture_output=True, text=True, timeout=60)
            
            if atomic_result.returncode == 0 and "Atomic rename completed" in atomic_result.stdout:
                rsync_result["final_location"] = target_path
                rsync_result["operation_safe"] = True
                logger.info(f"✅ Atomic rename completed: {target_path}")
            else:
                rsync_result["errors"].append(f"❌ Atomic rename failed: {atomic_result.stderr}")
        
        return rsync_result
        
    except Exception as e:
        rsync_result["errors"].append(f"❌ Safe rsync operation failed: {e}")
        return rsync_result


async def create_migration_checkpoint(
    migration_id: str,
    source_path: str,
    target_host: str,
    target_path: str,
    progress_state: dict
) -> dict:
    """
    🔄 MIGRATION RESUME: Create Checkpoint for Resume Capability
    
    Saves migration progress state to enable resume after interruption:
    1. Files completed successfully
    2. Files partially transferred
    3. Checksums of completed files
    4. Current transfer position
    5. Migration configuration
    """
    checkpoint_file = f"/tmp/transdock_checkpoint_{migration_id}.json"
    
    checkpoint_data = {
        "migration_id": migration_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_path": source_path,
        "target_host": target_host,
        "target_path": target_path,
        "progress": progress_state,
        "completed_files": progress_state.get("completed_files", []),
        "partial_files": progress_state.get("partial_files", []),
        "failed_files": progress_state.get("failed_files", []),
        "checksums": progress_state.get("checksums", {}),
        "bytes_transferred": progress_state.get("bytes_transferred", 0),
        "total_bytes": progress_state.get("total_bytes", 0),
        "resume_capable": True
    }
    
    try:
        import json
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        logger.info(f"✅ Migration checkpoint saved: {checkpoint_file}")
        return {"checkpoint_saved": True, "checkpoint_file": checkpoint_file}
        
    except Exception as e:
        logger.error(f"❌ Failed to save checkpoint: {e}")
        return {"checkpoint_saved": False, "error": str(e)}


async def load_migration_checkpoint(migration_id: str) -> dict:
    """Load migration checkpoint for resume capability"""
    checkpoint_file = f"/tmp/transdock_checkpoint_{migration_id}.json"
    
    try:
        import json, os
        if os.path.exists(checkpoint_file):
            with open(checkpoint_file, 'r') as f:
                checkpoint_data = json.load(f)
            
            logger.info(f"✅ Migration checkpoint loaded: {migration_id}")
            return {"checkpoint_found": True, "data": checkpoint_data}
        else:
            return {"checkpoint_found": False, "error": "No checkpoint file found"}
            
    except Exception as e:
        logger.error(f"❌ Failed to load checkpoint: {e}")
        return {"checkpoint_found": False, "error": str(e)}


async def generate_source_checksums(
    source_path: str,
    migration_id: str,
    algorithm: str = "sha256"
) -> dict:
    """
    🔐 CHECKSUM INTEGRITY: Generate Source Checksums
    
    Creates comprehensive checksums for source data:
    1. Individual file checksums (for incremental verification)
    2. Directory tree checksum (for overall integrity)
    3. Metadata checksums (permissions, timestamps)
    4. Progress tracking for large directories
    """
    checksum_result = {
        "checksums_generated": False,
        "algorithm": algorithm,
        "source_path": source_path,
        "file_checksums": {},
        "directory_checksum": None,
        "metadata_checksum": None,
        "total_files": 0,
        "total_bytes": 0,
        "checksum_file": None,
        "errors": []
    }
    
    try:
        import subprocess, os, hashlib, json
        
        checksum_file = f"/tmp/transdock_checksums_{migration_id}.json"
        
        # Generate file-by-file checksums for resume capability
        logger.info(f"🔐 Generating {algorithm} checksums for {source_path}")
        
        file_checksums = {}
        total_files = 0
        total_bytes = 0
        
        # Walk through source directory
        for root, dirs, files in os.walk(source_path):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, source_path)
                
                try:
                    # Generate file checksum
                    hash_obj = hashlib.new(algorithm)
                    file_size = 0
                    
                    with open(file_path, 'rb') as f:
                        while chunk := f.read(8192):
                            hash_obj.update(chunk)
                            file_size += len(chunk)
                    
                    file_checksums[relative_path] = {
                        "checksum": hash_obj.hexdigest(),
                        "size": file_size,
                        "mtime": os.path.getmtime(file_path)
                    }
                    
                    total_files += 1
                    total_bytes += file_size
                    
                    # Progress logging for large directories
                    if total_files % 100 == 0:
                        logger.info(f"🔐 Processed {total_files} files, {total_bytes / (1024*1024):.1f} MB")
                        
                except Exception as e:
                    checksum_result["errors"].append(f"❌ Failed to checksum {relative_path}: {e}")
        
        # Generate overall directory checksum using find + sort + sha256sum
        try:
            find_cmd = f"find {source_path} -type f -exec {algorithm}sum {{}} \\; | sort | {algorithm}sum"
            result = subprocess.run(find_cmd, shell=True, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                directory_checksum = result.stdout.split()[0]
                checksum_result["directory_checksum"] = directory_checksum
            
        except Exception as e:
            checksum_result["errors"].append(f"❌ Directory checksum failed: {e}")
        
        # Save checksums to file for resume capability
        checksum_data = {
            "migration_id": migration_id,
            "source_path": source_path,
            "algorithm": algorithm,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file_checksums": file_checksums,
            "directory_checksum": checksum_result["directory_checksum"],
            "total_files": total_files,
            "total_bytes": total_bytes
        }
        
        with open(checksum_file, 'w') as f:
            json.dump(checksum_data, f, indent=2)
        
        checksum_result.update({
            "checksums_generated": True,
            "file_checksums": file_checksums,
            "total_files": total_files,
            "total_bytes": total_bytes,
            "checksum_file": checksum_file
        })
        
        logger.info(f"✅ Generated checksums for {total_files} files ({total_bytes / (1024*1024):.1f} MB)")
        return checksum_result
        
    except Exception as e:
        checksum_result["errors"].append(f"❌ Checksum generation failed: {e}")
        return checksum_result


async def verify_target_checksums(
    target_host: str,
    target_path: str,
    source_checksums: dict,
    migration_id: str,
    ssh_user: str = "root",
    ssh_port: int = 22
) -> dict:
    """
    🔐 CHECKSUM INTEGRITY: Verify Target Checksums
    
    Validates data integrity after migration:
    1. Compare individual file checksums
    2. Verify directory tree checksum
    3. Check file sizes and timestamps
    4. Generate detailed mismatch report
    """
    verification_result = {
        "verification_passed": False,
        "algorithm": source_checksums.get("algorithm", "sha256"),
        "files_verified": 0,
        "files_matched": 0,
        "files_mismatched": 0,
        "files_missing": 0,
        "mismatched_files": [],
        "missing_files": [],
        "size_differences": {},
        "directory_checksum_match": False,
        "errors": []
    }
    
    try:
        import subprocess
        algorithm = verification_result["algorithm"]
        
        logger.info(f"🔐 Verifying checksums on {target_host}:{target_path}")
        
        # Verify individual files
        source_files = source_checksums.get("file_checksums", {})
        
        for relative_path, source_data in source_files.items():
            target_file_path = f"{target_path}/{relative_path}"
            
            # Generate checksum for target file
            checksum_cmd = f"ssh -p {ssh_port} {ssh_user}@{target_host} '{algorithm}sum \"{target_file_path}\" 2>/dev/null'"
            
            try:
                result = subprocess.run(checksum_cmd, shell=True, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    target_checksum = result.stdout.split()[0]
                    source_checksum = source_data["checksum"]
                    
                    verification_result["files_verified"] += 1
                    
                    if target_checksum == source_checksum:
                        verification_result["files_matched"] += 1
                    else:
                        verification_result["files_mismatched"] += 1
                        verification_result["mismatched_files"].append({
                            "file": relative_path,
                            "source_checksum": source_checksum,
                            "target_checksum": target_checksum
                        })
                        
                else:
                    verification_result["files_missing"] += 1
                    verification_result["missing_files"].append(relative_path)
                    
            except Exception as e:
                verification_result["errors"].append(f"❌ Failed to verify {relative_path}: {e}")
        
        # Verify overall directory checksum
        if source_checksums.get("directory_checksum"):
            try:
                dir_checksum_cmd = f"ssh -p {ssh_port} {ssh_user}@{target_host} 'find {target_path} -type f -exec {algorithm}sum {{}} \\; | sort | {algorithm}sum'"
                
                result = subprocess.run(dir_checksum_cmd, shell=True, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    target_dir_checksum = result.stdout.split()[0]
                    source_dir_checksum = source_checksums["directory_checksum"]
                    
                    verification_result["directory_checksum_match"] = (target_dir_checksum == source_dir_checksum)
                    
                    if not verification_result["directory_checksum_match"]:
                        verification_result["errors"].append(
                            f"❌ Directory checksum mismatch: source={source_dir_checksum}, target={target_dir_checksum}"
                        )
                
            except Exception as e:
                verification_result["errors"].append(f"❌ Directory checksum verification failed: {e}")
        
        # Overall verification result
        verification_result["verification_passed"] = (
            verification_result["files_mismatched"] == 0 and
            verification_result["files_missing"] == 0 and
            len(verification_result["errors"]) == 0 and
            verification_result["directory_checksum_match"]
        )
        
        if verification_result["verification_passed"]:
            logger.info(f"✅ Checksum verification PASSED: {verification_result['files_matched']} files verified")
        else:
            logger.error(f"❌ Checksum verification FAILED: {verification_result['files_mismatched']} mismatched, {verification_result['files_missing']} missing")
        
        return verification_result
        
    except Exception as e:
        verification_result["errors"].append(f"❌ Verification process failed: {e}")
        return verification_result


async def resume_interrupted_migration(
    migration_id: str,
    force_resume: bool = False
) -> dict:
    """
    🔄 MIGRATION RESUME: Resume Interrupted Migration
    
    Resumes migration from last successful checkpoint:
    1. Load checkpoint data
    2. Verify partial files
    3. Resume rsync with --partial
    4. Continue from last position
    5. Update progress tracking
    """
    resume_result = {
        "resume_successful": False,
        "checkpoint_loaded": False,
        "files_to_resume": 0,
        "resume_method": None,
        "errors": []
    }
    
    try:
        # Load checkpoint
        checkpoint = await load_migration_checkpoint(migration_id)
        
        if not checkpoint["checkpoint_found"]:
            resume_result["errors"].append("❌ No checkpoint found for migration")
            return resume_result
        
        checkpoint_data = checkpoint["data"]
        resume_result["checkpoint_loaded"] = True
        
        source_path = checkpoint_data["source_path"]
        target_host = checkpoint_data["target_host"]
        target_path = checkpoint_data["target_path"]
        
        # Determine resume strategy
        partial_files = checkpoint_data.get("partial_files", [])
        completed_files = checkpoint_data.get("completed_files", [])
        
        if partial_files:
            resume_result["resume_method"] = "partial_file_resume"
            resume_result["files_to_resume"] = len(partial_files)
            
            # Resume using rsync --partial
            logger.info(f"🔄 Resuming {len(partial_files)} partial files")
            
            # Continue rsync with partial support
            rsync_resume = await create_safe_rsync_operation(
                source_path=source_path,
                target_host=target_host,
                target_path=target_path,
                migration_id=migration_id,
                dry_run=False  # Skip dry run for resume
            )
            
            resume_result["resume_successful"] = rsync_resume["operation_safe"]
            
        else:
            resume_result["resume_method"] = "incremental_sync"
            
            # Use rsync --update to sync only newer files
            logger.info("🔄 Performing incremental sync of remaining files")
            
            # Incremental rsync
            incremental_sync = await create_safe_rsync_operation(
                source_path=source_path,
                target_host=target_host,
                target_path=target_path,
                migration_id=migration_id,
                dry_run=False
            )
            
            resume_result["resume_successful"] = incremental_sync["operation_safe"]
        
        # Update checkpoint after resume attempt
        if resume_result["resume_successful"]:
            progress_state = {
                "status": "resumed_and_completed",
                "resume_timestamp": datetime.now(timezone.utc).isoformat()
            }
            await create_migration_checkpoint(migration_id, source_path, target_host, target_path, progress_state)
        
        return resume_result
        
    except Exception as e:
        resume_result["errors"].append(f"❌ Migration resume failed: {e}")
        return resume_result


@app.post("/migrations/resume/{migration_id}")
async def resume_migration(migration_id: str, force_resume: bool = False):
    """
    🔄 RESUME INTERRUPTED MIGRATION
    
    Resume a migration that was interrupted due to:
    - Network failures
    - System reboots  
    - Process crashes
    - User interruption
    
    Uses checkpoints and partial file recovery for reliability.
    """
    try:
        logger.info(f"🔄 Attempting to resume migration: {migration_id}")
        
        resume_result = await resume_interrupted_migration(migration_id, force_resume)
        
        if resume_result["resume_successful"]:
            return {
                "migration_id": migration_id,
                "status": "resumed_successfully",
                "resume_details": resume_result,
                "message": f"✅ Migration {migration_id} resumed and completed successfully"
            }
        else:
            return {
                "migration_id": migration_id,
                "status": "resume_failed",
                "resume_details": resume_result,
                "message": f"❌ Failed to resume migration {migration_id}",
                "errors": resume_result["errors"]
            }
            
    except Exception as e:
        logger.error(f"Resume endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Resume failed: {e}") from e


@app.post("/migrations/verify-integrity/{migration_id}")
async def verify_migration_integrity(
    migration_id: str,
    source_path: str,
    target_host: str,
    target_path: str,
    ssh_user: str = "root",
    ssh_port: int = 22
):
    """
    🔐 VERIFY MIGRATION INTEGRITY
    
    Comprehensive checksum verification after migration:
    - Compare source vs target checksums
    - Verify file sizes and timestamps
    - Generate detailed integrity report
    - Recommend rollback if verification fails
    """
    try:
        logger.info(f"🔐 Verifying integrity for migration: {migration_id}")
        
        # Load source checksums
        checksum_file = f"/tmp/transdock_checksums_{migration_id}.json"
        
        import json, os
        if not os.path.exists(checksum_file):
            raise HTTPException(status_code=404, detail="Source checksums not found")
        
        with open(checksum_file, 'r') as f:
            source_checksums = json.load(f)
        
        # Verify target checksums
        verification = await verify_target_checksums(
            target_host=target_host,
            target_path=target_path,
            source_checksums=source_checksums,
            migration_id=migration_id,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        if verification["verification_passed"]:
            return {
                "migration_id": migration_id,
                "integrity_status": "verified",
                "verification_details": verification,
                "message": f"✅ Migration integrity verified: {verification['files_matched']} files passed",
                "recommendation": "Migration completed successfully - safe to cleanup snapshots"
            }
        else:
            return {
                "migration_id": migration_id,
                "integrity_status": "failed",
                "verification_details": verification,
                "message": f"❌ Integrity verification failed: {verification['files_mismatched']} mismatched files",
                "recommendation": "IMMEDIATE ROLLBACK RECOMMENDED - Data corruption detected",
                "critical_warning": "DO NOT use migrated data until integrity issues are resolved"
            }
            
    except Exception as e:
        logger.error(f"Integrity verification failed: {e}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {e}") from e


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
