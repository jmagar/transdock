"""API endpoints for Docker container management"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional

from ..dependencies import get_container_service
from ....application.docker.container_management_service import ContainerManagementService
from ....core.entities.docker_entity import DockerContainer

router = APIRouter(prefix="/docker/containers", tags=["docker-containers"])


@router.get("/", response_model=List[Dict[str, Any]])
async def list_containers(
    service: ContainerManagementService = Depends(get_container_service)
):
    containers = await service.list_containers()
    return [
        {
            "id": c.id,
            "name": c.name,
            "image": c.image,
            "state": c.state.value,
            "created_at": c.created_at,
            "project": c.project_name,
        }
        for c in containers
    ]


@router.get("/{container_id}", response_model=Dict[str, Any])
async def get_container(container_id: str, service: ContainerManagementService = Depends(get_container_service)):
    container = await service.get_container(container_id)
    if not container:
        raise HTTPException(status_code=404, detail="Container not found")
    return {
        "id": container.id,
        "name": container.name,
        "image": container.image,
        "state": container.state.value,
        "labels": container.labels,
        "environment": container.environment,
        "ports": [pm.__dict__ for pm in container.port_mappings],
        "mounts": [m.__dict__ for m in container.volume_mounts],
        "created_at": container.created_at,
    }


@router.post("/{container_id}/start")
async def start_container(container_id: str, service: ContainerManagementService = Depends(get_container_service)):
    success = await service.start_container(container_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to start container")
    return {"status": "started", "id": container_id}


@router.post("/{container_id}/stop")
async def stop_container(container_id: str, service: ContainerManagementService = Depends(get_container_service)):
    success = await service.stop_container(container_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to stop container")
    return {"status": "stopped", "id": container_id}


@router.delete("/{container_id}")
async def remove_container(container_id: str, service: ContainerManagementService = Depends(get_container_service)):
    success = await service.remove_container(container_id, force=True)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to remove container")
    return {"status": "removed", "id": container_id}