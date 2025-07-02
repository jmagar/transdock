from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import asyncio
import os
from typing import List, Optional
from .models import MigrationRequest, MigrationResponse, MigrationStatus
from .migration_service import MigrationService
from .security_utils import SecurityUtils, SecurityValidationError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="TransDock - Docker Stack Migration Tool",
    description="Migrate Docker Compose stacks between machines using ZFS snapshots",
    version="1.0.0"
)

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

@app.post("/migrations", response_model=MigrationResponse)
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
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/migrations", response_model=List[MigrationStatus])
async def list_migrations():
    """List all migrations"""
    try:
        migrations = await migration_service.list_migrations()
        return migrations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/migrations/{migration_id}", response_model=MigrationStatus)
async def get_migration_status(migration_id: str):
    """Get the status of a specific migration with input validation"""
    try:
        # Validate migration_id format to prevent injection
        if not migration_id or len(migration_id) > 64:
            raise SecurityValidationError("Invalid migration ID format")
        
        # Allow only alphanumeric characters, hyphens, and underscores
        if not all(c.isalnum() or c in '-_' for c in migration_id):
            raise SecurityValidationError("Migration ID contains invalid characters")
        
        status = await migration_service.get_migration_status(migration_id)
        if not status:
            raise HTTPException(status_code=404, detail="Migration not found")
        return status
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "transdock"}

@app.get("/zfs/status")
async def zfs_status():
    """Check ZFS availability and pool status"""
    try:
        zfs_ops = migration_service.zfs_ops
        is_available = await zfs_ops.is_zfs_available()
        
        if not is_available:
            return {"available": False, "message": "ZFS not available"}
        
        # Use secure ZFS command validation
        validated_cmd = SecurityUtils.validate_zfs_command_args("list", "-H", "-o", "name")
        returncode, stdout, stderr = await zfs_ops.run_command(validated_cmd)
        
        return {
            "available": True,
            "pool_status": stdout if returncode == 0 else "Unable to get pool status"
        }
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/datasets")
async def list_datasets():
    """List available ZFS datasets with security validation"""
    try:
        zfs_ops = migration_service.zfs_ops
        
        # Use secure ZFS command validation  
        validated_cmd = SecurityUtils.validate_zfs_command_args("list", "-H", "-o", "name,mountpoint", "-t", "filesystem")
        returncode, stdout, stderr = await zfs_ops.run_command(validated_cmd)
        
        if returncode != 0:
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
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/compose/stacks")
async def list_compose_stacks():
    """List available Docker Compose stacks with path validation"""
    try:
        docker_ops = migration_service.docker_ops
        compose_base = docker_ops.compose_base_path
        
        # Validate base path for security
        validated_base = SecurityUtils.sanitize_path(compose_base)
        
        stacks = []
        
        if os.path.exists(validated_base):
            for item in os.listdir(validated_base):
                # Validate each stack name
                try:
                    # Basic validation for stack names  
                    if not item or len(item) > 64:
                        continue
                    if not all(c.isalnum() or c in '-_.' for c in item):
                        continue
                        
                    stack_path = SecurityUtils.sanitize_path(os.path.join(validated_base, item), validated_base)
                    
                    if os.path.isdir(stack_path):
                        compose_file = await docker_ops.find_compose_file(stack_path)
                        if compose_file:
                            stacks.append({
                                "name": item,
                                "path": stack_path,
                                "compose_file": os.path.basename(compose_file)
                            })
                except SecurityValidationError:
                    # Skip invalid stack names silently
                    continue
        
        return {"stacks": stacks}
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/compose/{stack_name}/analyze")
async def analyze_compose_stack(stack_name: str):
    """Analyze a compose stack with security validation"""
    try:
        # Validate stack name for security
        if not stack_name or len(stack_name) > 64:
            raise SecurityValidationError("Invalid stack name length")
        if not all(c.isalnum() or c in '-_.' for c in stack_name):
            raise SecurityValidationError("Stack name contains invalid characters")
        
        docker_ops = migration_service.docker_ops
        compose_base = SecurityUtils.sanitize_path(docker_ops.compose_base_path)
        stack_path = SecurityUtils.sanitize_path(os.path.join(compose_base, stack_name), compose_base)
        
        if not os.path.exists(stack_path):
            raise HTTPException(status_code=404, detail="Compose stack not found")
        
        compose_file = await docker_ops.find_compose_file(stack_path)
        if not compose_file:
            raise HTTPException(status_code=404, detail="No compose file found in stack")
        
        compose_data = await docker_ops.parse_compose_file(compose_file)
        volumes = await docker_ops.extract_volume_mounts(compose_data)
        
        # Check if volumes are datasets
        zfs_ops = migration_service.zfs_ops
        for volume in volumes:
            volume.is_dataset = await zfs_ops.is_dataset(volume.source)
            if volume.is_dataset:
                volume.dataset_path = await zfs_ops.get_dataset_name(volume.source)
        
        return {
            "stack_name": stack_name,
            "stack_path": stack_path,
            "compose_file": compose_file,
            "volumes": volumes,
            "services": list(compose_data.get('services', {}).keys())
        }
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/system/info")
async def system_info():
    """Get system information relevant to migrations"""
    try:
        import platform
        import subprocess
        
        # Basic system info
        info = {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "architecture": platform.architecture()[0]
        }
        
        # Check Docker status safely
        try:
            result = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], 
                                    capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                info["docker_version"] = result.stdout.strip()
            else:
                info["docker_version"] = "unavailable"
        except Exception:
            info["docker_version"] = "unavailable"
        
        # Check ZFS status safely
        try:
            zfs_ops = migration_service.zfs_ops
            info["zfs_available"] = str(await zfs_ops.is_zfs_available())
        except Exception:
            info["zfs_available"] = "False"
        
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)