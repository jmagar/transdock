from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from typing import List, Optional
from models import MigrationRequest, MigrationResponse, MigrationStatus
from migration_service import MigrationService

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
    """Start a new migration process"""
    try:
        migration_id = await migration_service.start_migration(request)
        return MigrationResponse(
            migration_id=migration_id,
            status="started",
            message="Migration process started successfully"
        )
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
    """Get the status of a specific migration"""
    try:
        status = await migration_service.get_migration_status(migration_id)
        if not status:
            raise HTTPException(status_code=404, detail="Migration not found")
        return status
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
        
        # Get pool status
        returncode, stdout, stderr = await zfs_ops.run_command(["zpool", "status"])
        
        return {
            "available": True,
            "pool_status": stdout if returncode == 0 else "Unable to get pool status"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/datasets")
async def list_datasets():
    """List available ZFS datasets"""
    try:
        zfs_ops = migration_service.zfs_ops
        returncode, stdout, stderr = await zfs_ops.run_command([
            "zfs", "list", "-H", "-o", "name,mountpoint", "-t", "filesystem"
        ])
        
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/compose/stacks")
async def list_compose_stacks():
    """List available Docker Compose stacks"""
    try:
        docker_ops = migration_service.docker_ops
        compose_base = docker_ops.compose_base_path
        
        import os
        stacks = []
        
        if os.path.exists(compose_base):
            for item in os.listdir(compose_base):
                stack_path = os.path.join(compose_base, item)
                if os.path.isdir(stack_path):
                    compose_file = await docker_ops.find_compose_file(stack_path)
                    if compose_file:
                        stacks.append({
                            "name": item,
                            "path": stack_path,
                            "compose_file": os.path.basename(compose_file)
                        })
        
        return {"stacks": stacks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/compose/{stack_name}/analyze")
async def analyze_compose_stack(stack_name: str):
    """Analyze a compose stack and return volume information"""
    try:
        docker_ops = migration_service.docker_ops
        stack_path = os.path.join(docker_ops.compose_base_path, stack_name)
        
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
        
        # Check Docker
        try:
            result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
            info["docker_version"] = result.stdout.strip() if result.returncode == 0 else "Not available"
        except:
            info["docker_version"] = "Not available"
        
        # Check docker-compose
        try:
            result = subprocess.run(["docker-compose", "--version"], capture_output=True, text=True)
            info["docker_compose_version"] = result.stdout.strip() if result.returncode == 0 else "Not available"
        except:
            info["docker_compose_version"] = "Not available"
        
        # Check ZFS
        zfs_ops = migration_service.zfs_ops
        info["zfs_available"] = await zfs_ops.is_zfs_available()
        
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 