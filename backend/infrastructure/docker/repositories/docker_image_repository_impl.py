"""Docker Image Repository Implementation using docker SDK"""

from typing import List, Optional
from datetime import datetime
import docker
from docker import errors as docker_errors

from ....core.interfaces.docker_repository import DockerImageRepository
from ....core.entities.docker_entity import DockerImage
import logging

logger = logging.getLogger(__name__)


class DockerImageRepositoryImpl(DockerImageRepository):
    """Concrete repository for Docker images using docker SDK"""

    def __init__(self, base_url: str = "unix://var/run/docker.sock"):
        self._client = docker.DockerClient(base_url=base_url)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _to_entity(self, image) -> DockerImage:
        tags = image.tags if image.tags else [image.short_id]
        created = datetime.fromtimestamp(image.attrs.get("Created", 0))
        size = image.attrs.get("Size", 0)
        arch = image.attrs.get("Architecture", "amd64")
        os_name = image.attrs.get("Os", "linux")
        return DockerImage(
            id=image.id,
            tags=tags,
            size=size,
            created_at=created,
            architecture=arch,
            os=os_name
        )

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------
    async def list_all(self) -> List[DockerImage]:
        images = self._client.images.list()
        return [self._to_entity(img) for img in images]

    async def find_by_id(self, image_id: str) -> Optional[DockerImage]:
        try:
            img = self._client.images.get(image_id)
            return self._to_entity(img)
        except docker_errors.ImageNotFound:
            return None

    async def find_by_tag(self, tag: str) -> Optional[DockerImage]:
        images = await self.list_all()
        for img in images:
            if tag in img.tags:
                return img
        return None

    async def pull(self, tag: str) -> bool:
        try:
            self._client.images.pull(tag)
            return True
        except docker_errors.APIError as e:
            logger.error(f"Failed to pull image {tag}: {e}")
            return False

    async def remove(self, image_id: str, force: bool = False) -> bool:
        try:
            self._client.images.remove(image_id, force=force)
            return True
        except docker_errors.APIError as e:
            logger.error(f"Failed to remove image {image_id}: {e}")
            return False

    async def tag(self, image_id: str, new_tag: str) -> bool:
        try:
            img = self._client.images.get(image_id)
            img.tag(new_tag)
            return True
        except docker_errors.APIError as e:
            logger.error(f"Failed to tag image {image_id} as {new_tag}: {e}")
            return False