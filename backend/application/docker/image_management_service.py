"""Service for Docker image operations"""

from typing import List, Optional
from ...core.entities.docker_entity import DockerImage
from ...core.interfaces.docker_repository import DockerImageRepository


class ImageManagementService:
    """Business logic for Docker images"""

    def __init__(self, repo: DockerImageRepository):
        self._repo = repo

    async def list_images(self) -> List[DockerImage]:
        return await self._repo.list_all()

    async def pull(self, tag: str) -> bool:
        return await self._repo.pull(tag)

    async def remove(self, image_id: str, force: bool = False) -> bool:
        return await self._repo.remove(image_id, force)

    async def tag(self, image_id: str, new_tag: str) -> bool:
        return await self._repo.tag(image_id, new_tag)