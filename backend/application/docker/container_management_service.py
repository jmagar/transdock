"""Application service for Docker container operations"""

from typing import List, Optional, Dict, Any
from ...core.interfaces.docker_repository import DockerContainerRepository
from ...core.entities.docker_entity import DockerContainer
from ...core.value_objects.host_connection import HostConnection


class ContainerManagementService:
    """Business logic layer for Docker containers"""

    def __init__(self, repository: DockerContainerRepository):
        self._repo = repository

    async def list_containers(self, all: bool = True, host: Optional[HostConnection] = None) -> List[DockerContainer]:
        """Return list of containers"""
        # Repo currently lists all containers regardless of `all` flag – future enhancement
        return await self._repo.list_all(host)

    async def get_container(self, container_id: str, host: Optional[HostConnection] = None) -> Optional[DockerContainer]:
        return await self._repo.find_by_id(container_id, host)

    async def start_container(self, container_id: str, host: Optional[HostConnection] = None) -> bool:
        return await self._repo.start(container_id, host)

    async def stop_container(self, container_id: str, timeout: int = 10, host: Optional[HostConnection] = None) -> bool:
        return await self._repo.stop(container_id, timeout, host)

    async def remove_container(self, container_id: str, force: bool = False, host: Optional[HostConnection] = None) -> bool:
        return await self._repo.remove(container_id, force, host)

    async def get_logs(self, container_id: str, tail: Optional[int] = None, host: Optional[HostConnection] = None) -> str:
        return await self._repo.get_logs(container_id, tail, host)

    async def exec(self, container_id: str, command: List[str], host: Optional[HostConnection] = None) -> str:
        return await self._repo.exec_command(container_id, command, host)