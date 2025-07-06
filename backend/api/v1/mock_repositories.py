"""Mock repository implementations for development and testing"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from ...core.interfaces.docker_repository import (
    DockerContainerRepository, DockerImageRepository, DockerNetworkRepository,
    DockerComposeRepository, DockerVolumeRepository, DockerHostRepository
)
from ...core.entities.docker_entity import (
    DockerContainer, DockerImage, DockerNetwork, DockerComposeStack,
    DockerContainerState, DockerVolumeMount, DockerPortMapping
)
from ...core.value_objects.host_connection import HostConnection
import logging

logger = logging.getLogger(__name__)


class MockDockerContainerRepository(DockerContainerRepository):
    """Mock implementation of Docker container repository"""
    
    def __init__(self):
        self._containers = {}
    
    async def list_all(self, host: Optional[HostConnection] = None) -> List[DockerContainer]:
        """List all containers"""
        # Return mock containers
        return [
            DockerContainer(
                id="mock-container-1",
                name="app_web_1",
                image="nginx:latest",
                state=DockerContainerState.RUNNING,
                created_at=datetime.now(),
                labels={"com.docker.compose.project": "app"},
                volume_mounts=[
                    DockerVolumeMount(
                        source="/data/app/html",
                        target="/usr/share/nginx/html",
                        read_only=False
                    )
                ],
                port_mappings=[
                    DockerPortMapping(
                        host_port=8080,
                        container_port=80,
                        protocol="tcp"
                    )
                ]
            )
        ]
    
    async def find_by_id(self, container_id: str, host: Optional[HostConnection] = None) -> Optional[DockerContainer]:
        """Find container by ID"""
        if container_id == "mock-container-1":
            containers = await self.list_all(host)
            return containers[0] if containers else None
        return None
    
    async def find_by_name(self, name: str, host: Optional[HostConnection] = None) -> Optional[DockerContainer]:
        """Find container by name"""
        if name == "app_web_1":
            containers = await self.list_all(host)
            return containers[0] if containers else None
        return None
    
    async def start(self, container_id: str, host: Optional[HostConnection] = None) -> bool:
        """Start container"""
        logger.info(f"Mock: Starting container {container_id}")
        return True
    
    async def stop(self, container_id: str, timeout: int = 10, host: Optional[HostConnection] = None) -> bool:
        """Stop container"""
        logger.info(f"Mock: Stopping container {container_id}")
        return True
    
    async def remove(self, container_id: str, force: bool = False, host: Optional[HostConnection] = None) -> bool:
        """Remove container"""
        logger.info(f"Mock: Removing container {container_id}")
        return True
    
    async def get_logs(self, container_id: str, tail: Optional[int] = None, host: Optional[HostConnection] = None) -> str:
        """Get container logs"""
        return f"Mock logs for container {container_id}\nApplication started successfully"
    
    async def get_stats(self, container_id: str, host: Optional[HostConnection] = None) -> Dict[str, Any]:
        """Get container stats"""
        return {
            "cpu_usage": 15.5,
            "memory_usage": 256 * 1024 * 1024,  # 256MB
            "memory_limit": 1024 * 1024 * 1024,  # 1GB
            "network_rx": 1024 * 1024,  # 1MB
            "network_tx": 512 * 1024  # 512KB
        }
    
    async def exec_command(self, container_id: str, command: List[str], host: Optional[HostConnection] = None) -> str:
        """Execute command in container"""
        return f"Mock execution of {' '.join(command)} in container {container_id}"


class MockDockerImageRepository(DockerImageRepository):
    """Mock implementation of Docker image repository"""
    
    async def list_all(self, host: Optional[HostConnection] = None) -> List[DockerImage]:
        """List all images"""
        return [
            DockerImage(
                id="mock-image-1",
                tags=["nginx:latest", "nginx:1.21"],
                size=150 * 1024 * 1024,  # 150MB
                created_at=datetime.now()
            )
        ]
    
    async def find_by_id(self, image_id: str, host: Optional[HostConnection] = None) -> Optional[DockerImage]:
        """Find image by ID"""
        if image_id == "mock-image-1":
            images = await self.list_all(host)
            return images[0] if images else None
        return None
    
    async def find_by_tag(self, tag: str, host: Optional[HostConnection] = None) -> Optional[DockerImage]:
        """Find image by tag"""
        if tag in ["nginx:latest", "nginx:1.21"]:
            images = await self.list_all(host)
            return images[0] if images else None
        return None
    
    async def pull(self, tag: str, host: Optional[HostConnection] = None) -> bool:
        """Pull image"""
        logger.info(f"Mock: Pulling image {tag}")
        return True
    
    async def remove(self, image_id: str, force: bool = False, host: Optional[HostConnection] = None) -> bool:
        """Remove image"""
        logger.info(f"Mock: Removing image {image_id}")
        return True
    
    async def tag(self, image_id: str, new_tag: str, host: Optional[HostConnection] = None) -> bool:
        """Tag image"""
        logger.info(f"Mock: Tagging image {image_id} as {new_tag}")
        return True


class MockDockerNetworkRepository(DockerNetworkRepository):
    """Mock implementation of Docker network repository"""
    
    async def list_all(self, host: Optional[HostConnection] = None) -> List[DockerNetwork]:
        """List all networks"""
        return [
            DockerNetwork(
                id="mock-network-1",
                name="app_default",
                driver="bridge",
                internal=False,
                labels={"com.docker.compose.project": "app"}
            )
        ]
    
    async def find_by_id(self, network_id: str, host: Optional[HostConnection] = None) -> Optional[DockerNetwork]:
        """Find network by ID"""
        if network_id == "mock-network-1":
            networks = await self.list_all(host)
            return networks[0] if networks else None
        return None
    
    async def find_by_name(self, name: str, host: Optional[HostConnection] = None) -> Optional[DockerNetwork]:
        """Find network by name"""
        if name == "app_default":
            networks = await self.list_all(host)
            return networks[0] if networks else None
        return None
    
    async def create(self, name: str, driver: str = "bridge", options: Optional[Dict[str, Any]] = None, host: Optional[HostConnection] = None) -> bool:
        """Create network"""
        logger.info(f"Mock: Creating network {name} with driver {driver}")
        return True
    
    async def remove(self, network_id: str, host: Optional[HostConnection] = None) -> bool:
        """Remove network"""
        logger.info(f"Mock: Removing network {network_id}")
        return True


class MockDockerComposeRepository(DockerComposeRepository):
    """Mock implementation of Docker Compose repository"""
    
    async def list_stacks(self, host: Optional[HostConnection] = None) -> List[DockerComposeStack]:
        """List all compose stacks"""
        return [
            DockerComposeStack(
                name="app",
                compose_file_path="/apps/app/docker-compose.yml",
                project_directory="/apps/app",
                containers=[],
                services={"web": {}, "db": {}, "redis": {}},
                networks=[],
                volumes={"app_data": {}, "app_logs": {}}
            )
        ]
    
    async def find_by_path(self, compose_file_path: str, host: Optional[HostConnection] = None) -> Optional[DockerComposeStack]:
        """Find stack by compose file path"""
        if compose_file_path == "/apps/app/docker-compose.yml":
            stacks = await self.list_stacks(host)
            return stacks[0] if stacks else None
        return None
    
    async def find_by_name(self, name: str, host: Optional[HostConnection] = None) -> Optional[DockerComposeStack]:
        """Find stack by project name"""
        if name == "app":
            stacks = await self.list_stacks(host)
            return stacks[0] if stacks else None
        return None
    
    async def start(self, compose_file_path: str, project_name: Optional[str] = None, host: Optional[HostConnection] = None) -> bool:
        """Start compose stack"""
        logger.info(f"Mock: Starting stack from {compose_file_path}")
        return True
    
    async def stop(self, compose_file_path: str, project_name: Optional[str] = None, host: Optional[HostConnection] = None) -> bool:
        """Stop compose stack"""
        logger.info(f"Mock: Stopping stack from {compose_file_path}")
        return True
    
    async def down(self, compose_file_path: str, remove_volumes: bool = False, project_name: Optional[str] = None, host: Optional[HostConnection] = None) -> bool:
        """Down compose stack"""
        logger.info(f"Mock: Bringing down stack from {compose_file_path}")
        return True
    
    async def get_status(self, compose_file_path: str, project_name: Optional[str] = None, host: Optional[HostConnection] = None) -> Dict[str, Any]:
        """Get stack status"""
        return {
            "running": True,
            "services": {
                "web": "running",
                "db": "running",
                "redis": "running"
            }
        }


class MockDockerVolumeRepository(DockerVolumeRepository):
    """Mock implementation of Docker volume repository"""
    
    async def list_all(self, host: Optional[HostConnection] = None) -> List[Dict[str, Any]]:
        """List all volumes"""
        return [
            {
                "name": "app_data",
                "driver": "local",
                "labels": {"com.docker.compose.project": "app"},
                "mountpoint": "/var/lib/docker/volumes/app_data/_data"
            }
        ]
    
    async def find_by_name(self, name: str, host: Optional[HostConnection] = None) -> Optional[Dict[str, Any]]:
        """Find volume by name"""
        if name == "app_data":
            volumes = await self.list_all(host)
            return volumes[0] if volumes else None
        return None
    
    async def create(self, name: str, driver: str = "local", options: Optional[Dict[str, Any]] = None, host: Optional[HostConnection] = None) -> bool:
        """Create volume"""
        logger.info(f"Mock: Creating volume {name}")
        return True
    
    async def remove(self, name: str, force: bool = False, host: Optional[HostConnection] = None) -> bool:
        """Remove volume"""
        logger.info(f"Mock: Removing volume {name}")
        return True
    
    async def get_size(self, name: str, host: Optional[HostConnection] = None) -> int:
        """Get volume size in bytes"""
        return 1024 * 1024 * 1024  # 1GB


class MockDockerHostRepository(DockerHostRepository):
    """Mock implementation of Docker host repository"""
    
    async def get_info(self, host: Optional[HostConnection] = None) -> Dict[str, Any]:
        """Get Docker host info"""
        return {
            "server_version": "20.10.17",
            "storage_driver": "overlay2",
            "containers": 5,
            "containers_running": 3,
            "images": 10,
            "cpu_count": 4,
            "memory_total": 8 * 1024 * 1024 * 1024  # 8GB
        }
    
    async def get_version(self, host: Optional[HostConnection] = None) -> str:
        """Get Docker version"""
        return "20.10.17"
    
    async def test_connection(self, host: Optional[HostConnection] = None) -> bool:
        """Test Docker connection"""
        return True
    
    async def get_disk_usage(self, host: Optional[HostConnection] = None) -> Dict[str, Any]:
        """Get Docker disk usage"""
        return {
            "images": {
                "count": 10,
                "size": 2 * 1024 * 1024 * 1024  # 2GB
            },
            "containers": {
                "count": 5,
                "size": 500 * 1024 * 1024  # 500MB
            },
            "volumes": {
                "count": 3,
                "size": 1 * 1024 * 1024 * 1024  # 1GB
            },
            "build_cache": {
                "count": 20,
                "size": 300 * 1024 * 1024  # 300MB
            }
        }