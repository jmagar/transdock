"""Docker repository interfaces"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from ..entities.docker_entity import DockerContainer, DockerImage, DockerNetwork, DockerComposeStack
from ..value_objects.host_connection import HostConnection


class DockerContainerRepository(ABC):
    """Repository interface for Docker containers"""
    
    @abstractmethod
    async def list_all(self) -> List[DockerContainer]:
        """List all containers"""
        pass
    
    @abstractmethod
    async def list_running(self) -> List[DockerContainer]:
        """List running containers"""
        pass
    
    @abstractmethod
    async def find_by_name(self, name: str) -> Optional[DockerContainer]:
        """Find container by name"""
        pass
    
    @abstractmethod
    async def find_by_id(self, container_id: str) -> Optional[DockerContainer]:
        """Find container by ID"""
        pass
    
    @abstractmethod
    async def find_by_compose_project(self, project_name: str) -> List[DockerContainer]:
        """Find containers belonging to a compose project"""
        pass
    
    @abstractmethod
    async def start(self, container_id: str) -> bool:
        """Start a container"""
        pass
    
    @abstractmethod
    async def stop(self, container_id: str, timeout: int = 10) -> bool:
        """Stop a container"""
        pass
    
    @abstractmethod
    async def remove(self, container_id: str, force: bool = False) -> bool:
        """Remove a container"""
        pass
    
    @abstractmethod
    async def get_logs(self, container_id: str, tail: int = 100) -> str:
        """Get container logs"""
        pass
    
    @abstractmethod
    async def get_stats(self, container_id: str) -> Dict[str, Any]:
        """Get container statistics"""
        pass
    
    @abstractmethod
    async def exec_command(self, container_id: str, command: List[str]) -> Dict[str, Any]:
        """Execute command in container"""
        pass


class DockerImageRepository(ABC):
    """Repository interface for Docker images"""
    
    @abstractmethod
    async def list_all(self) -> List[DockerImage]:
        """List all images"""
        pass
    
    @abstractmethod
    async def find_by_tag(self, tag: str) -> Optional[DockerImage]:
        """Find image by tag"""
        pass
    
    @abstractmethod
    async def find_by_id(self, image_id: str) -> Optional[DockerImage]:
        """Find image by ID"""
        pass
    
    @abstractmethod
    async def pull(self, image_tag: str) -> bool:
        """Pull an image"""
        pass
    
    @abstractmethod
    async def remove(self, image_id: str, force: bool = False) -> bool:
        """Remove an image"""
        pass
    
    @abstractmethod
    async def build(self, context_path: str, dockerfile_path: str, tag: str) -> bool:
        """Build an image"""
        pass
    
    @abstractmethod
    async def get_history(self, image_id: str) -> List[Dict[str, Any]]:
        """Get image history"""
        pass
    
    @abstractmethod
    async def export(self, image_id: str, output_path: str) -> bool:
        """Export image to tar file"""
        pass
    
    @abstractmethod
    async def import_from_tar(self, tar_path: str, tag: str) -> bool:
        """Import image from tar file"""
        pass


class DockerNetworkRepository(ABC):
    """Repository interface for Docker networks"""
    
    @abstractmethod
    async def list_all(self) -> List[DockerNetwork]:
        """List all networks"""
        pass
    
    @abstractmethod
    async def find_by_name(self, name: str) -> Optional[DockerNetwork]:
        """Find network by name"""
        pass
    
    @abstractmethod
    async def find_by_id(self, network_id: str) -> Optional[DockerNetwork]:
        """Find network by ID"""
        pass
    
    @abstractmethod
    async def create(self, name: str, driver: str = "bridge", options: Optional[Dict[str, str]] = None) -> DockerNetwork:
        """Create a network"""
        pass
    
    @abstractmethod
    async def remove(self, network_id: str) -> bool:
        """Remove a network"""
        pass
    
    @abstractmethod
    async def connect_container(self, network_id: str, container_id: str) -> bool:
        """Connect container to network"""
        pass
    
    @abstractmethod
    async def disconnect_container(self, network_id: str, container_id: str) -> bool:
        """Disconnect container from network"""
        pass


class DockerComposeRepository(ABC):
    """Repository interface for Docker Compose operations"""
    
    @abstractmethod
    async def find_stack_by_name(self, project_name: str) -> Optional[DockerComposeStack]:
        """Find compose stack by project name"""
        pass
    
    @abstractmethod
    async def find_stack_by_path(self, compose_file_path: str) -> Optional[DockerComposeStack]:
        """Find compose stack by compose file path"""
        pass
    
    @abstractmethod
    async def list_all_stacks(self) -> List[DockerComposeStack]:
        """List all compose stacks"""
        pass
    
    @abstractmethod
    async def start_stack(self, compose_file_path: str, project_name: Optional[str] = None) -> bool:
        """Start a compose stack"""
        pass
    
    @abstractmethod
    async def stop_stack(self, compose_file_path: str, project_name: Optional[str] = None) -> bool:
        """Stop a compose stack"""
        pass
    
    @abstractmethod
    async def down_stack(self, compose_file_path: str, project_name: Optional[str] = None, remove_volumes: bool = False) -> bool:
        """Bring down a compose stack"""
        pass
    
    @abstractmethod
    async def build_stack(self, compose_file_path: str, project_name: Optional[str] = None) -> bool:
        """Build services in compose stack"""
        pass
    
    @abstractmethod
    async def get_stack_logs(self, compose_file_path: str, project_name: Optional[str] = None, tail: int = 100) -> str:
        """Get logs for compose stack"""
        pass
    
    @abstractmethod
    async def validate_compose_file(self, compose_file_path: str) -> Dict[str, Any]:
        """Validate compose file"""
        pass
    
    @abstractmethod
    async def get_stack_status(self, compose_file_path: str, project_name: Optional[str] = None) -> Dict[str, Any]:
        """Get status of compose stack"""
        pass
    
    @abstractmethod
    async def recreate_stack(self, compose_file_path: str, project_name: Optional[str] = None) -> bool:
        """Recreate compose stack"""
        pass
    
    @abstractmethod
    async def scale_service(self, compose_file_path: str, service_name: str, scale: int, project_name: Optional[str] = None) -> bool:
        """Scale a service in compose stack"""
        pass


class DockerVolumeRepository(ABC):
    """Repository interface for Docker volumes"""
    
    @abstractmethod
    async def list_all(self) -> List[Dict[str, Any]]:
        """List all volumes"""
        pass
    
    @abstractmethod
    async def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find volume by name"""
        pass
    
    @abstractmethod
    async def create(self, name: str, driver: str = "local", options: Optional[Dict[str, str]] = None) -> bool:
        """Create a volume"""
        pass
    
    @abstractmethod
    async def remove(self, name: str, force: bool = False) -> bool:
        """Remove a volume"""
        pass
    
    @abstractmethod
    async def prune(self) -> Dict[str, Any]:
        """Prune unused volumes"""
        pass
    
    @abstractmethod
    async def inspect(self, name: str) -> Dict[str, Any]:
        """Inspect volume details"""
        pass


class DockerHostRepository(ABC):
    """Repository interface for Docker host operations"""
    
    @abstractmethod
    async def get_system_info(self) -> Dict[str, Any]:
        """Get Docker system information"""
        pass
    
    @abstractmethod
    async def get_version(self) -> Dict[str, Any]:
        """Get Docker version information"""
        pass
    
    @abstractmethod
    async def get_disk_usage(self) -> Dict[str, Any]:
        """Get Docker disk usage"""
        pass
    
    @abstractmethod
    async def prune_system(self, all_unused: bool = False) -> Dict[str, Any]:
        """Prune Docker system"""
        pass
    
    @abstractmethod
    async def get_events(self, since: Optional[str] = None, until: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get Docker events"""
        pass
    
    @abstractmethod
    async def ping(self) -> bool:
        """Ping Docker daemon"""
        pass
    
    @abstractmethod
    async def login(self, username: str, password: str, registry: Optional[str] = None) -> bool:
        """Login to Docker registry"""
        pass
    
    @abstractmethod
    async def logout(self, registry: Optional[str] = None) -> bool:
        """Logout from Docker registry"""
        pass