from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
from typing import Optional
from .models import (
    MigrationRequest, MigrationResponse, HostValidationRequest, 
    HostInfo, HostCapabilities, StackAnalysis
)
from .migration_service import MigrationService
from .host_service import HostService
from .security_utils import SecurityUtils, SecurityValidationError
from .zfs_ops import ZFSOperations
from datetime import datetime, timezone

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
