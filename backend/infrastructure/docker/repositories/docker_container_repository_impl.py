"""Docker Container Repository Implementation using docker SDK"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import docker

from ....core.interfaces.docker_repository import DockerContainerRepository
from ....core.entities.docker_entity import (
    DockerContainer, DockerContainerState, DockerVolumeMount,
    DockerPortMapping
)
from ....core.value_objects.host_connection import HostConnection
import logging

logger = logging.getLogger(__name__)


class DockerContainerRepositoryImpl(DockerContainerRepository):
    """Concrete repository that talks to local Docker engine via docker-py SDK."""

    def __init__(self, base_url: str = "unix://var/run/docker.sock"):
        self._client = docker.DockerClient(base_url=base_url)

    # ---------------------------------------------------------------------
    # Helper conversion functions
    # ---------------------------------------------------------------------
    def _to_entity(self, container) -> DockerContainer:
        """Convert docker SDK Container to domain entity"""
        attrs = container.attrs
        state_str = attrs.get("State", {}).get("Status", "running")
        try:
            state = DockerContainerState(state_str)
        except ValueError:
            state = DockerContainerState.RUNNING

        # Labels
        labels = attrs.get("Config", {}).get("Labels", {}) or {}

        # Environment
        env_list = attrs.get("Config", {}).get("Env", []) or []
        environment = {}
        for item in env_list:
            if "=" in item:
                k, v = item.split("=", 1)
                environment[k] = v

        # Volume mounts
        mounts = []
        for m in attrs.get("Mounts", []):
            mounts.append(
                DockerVolumeMount(
                    source=m.get("Source", ""),
                    target=m.get("Destination", ""),
                    type=m.get("Type", "bind"),
                    read_only=bool(m.get("RW") is False)
                )
            )

        # Ports
        port_mappings = []
        ports_dict = attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
        for container_port_proto, host_bindings in ports_dict.items():
            if host_bindings:
                container_port, proto = container_port_proto.split("/")
                for binding in host_bindings:
                    port_mappings.append(
                        DockerPortMapping(
                            container_port=int(container_port),
                            host_port=int(binding.get("HostPort")),
                            host_ip=binding.get("HostIp", "0.0.0.0"),
                            protocol=proto
                        )
                    )

        return DockerContainer(
            id=container.id,
            name=container.name,
            image=container.image.tags[0] if container.image.tags else container.image.short_id,
            state=state,
            labels=labels,
            environment=environment,
            volume_mounts=mounts,
            port_mappings=port_mappings,
            networks=list(container.attrs.get("NetworkSettings", {}).get("Networks", {}).keys()),
            created_at=datetime.fromtimestamp(attrs.get("Created", "0").split(".")[0]) if attrs.get("Created") else None
        )

    # ---------------------------------------------------------------------
    # Interface methods
    # ---------------------------------------------------------------------
    async def list_all(self, host: Optional[HostConnection] = None) -> List[DockerContainer]:
        containers = self._client.containers.list(all=True)
        return [self._to_entity(c) for c in containers]

    async def find_by_id(self, container_id: str, host: Optional[HostConnection] = None) -> Optional[DockerContainer]:
        try:
            container = self._client.containers.get(container_id)
            return self._to_entity(container)
        except docker.errors.NotFound:
            return None

    async def find_by_name(self, name: str, host: Optional[HostConnection] = None) -> Optional[DockerContainer]:
        containers = await self.list_all(host)
        for c in containers:
            if c.name == name:
                return c
        return None

    async def start(self, container_id: str, host: Optional[HostConnection] = None) -> bool:
        try:
            self._client.containers.get(container_id).start()
            return True
        except docker.errors.APIError as e:
            logger.error(f"Failed to start container {container_id}: {e}")
            return False

    async def stop(self, container_id: str, timeout: int = 10, host: Optional[HostConnection] = None) -> bool:
        try:
            self._client.containers.get(container_id).stop(timeout=timeout)
            return True
        except docker.errors.APIError as e:
            logger.error(f"Failed to stop container {container_id}: {e}")
            return False

    async def remove(self, container_id: str, force: bool = False, host: Optional[HostConnection] = None) -> bool:
        try:
            self._client.containers.get(container_id).remove(force=force)
            return True
        except docker.errors.APIError as e:
            logger.error(f"Failed to remove container {container_id}: {e}")
            return False

    async def get_logs(self, container_id: str, tail: Optional[int] = None, host: Optional[HostConnection] = None) -> str:
        try:
            logs = self._client.containers.get(container_id).logs(tail=tail)
            return logs.decode()
        except docker.errors.APIError as e:
            logger.error(f"Failed to get logs for {container_id}: {e}")
            return ""

    async def get_stats(self, container_id: str, host: Optional[HostConnection] = None) -> Dict[str, Any]:
        try:
            stats = self._client.containers.get(container_id).stats(stream=False)
            return stats
        except docker.errors.APIError as e:
            logger.error(f"Failed to get stats for {container_id}: {e}")
            return {}

    async def exec_command(self, container_id: str, command: List[str], host: Optional[HostConnection] = None) -> str:
        try:
            cont = self._client.containers.get(container_id)
            exec_id = self._client.api.exec_create(cont.id, command)
            output = self._client.api.exec_start(exec_id).decode()
            return output
        except docker.errors.APIError as e:
            logger.error(f"Failed to exec in {container_id}: {e}")
            return ""