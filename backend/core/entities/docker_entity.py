"""Docker domain entities"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
from ..value_objects.host_connection import HostConnection


class DockerContainerState(Enum):
    """Docker container states"""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    RESTARTING = "restarting"
    REMOVING = "removing"
    EXITED = "exited"
    DEAD = "dead"


class DockerRestartPolicy(Enum):
    """Docker restart policies"""
    NO = "no"
    ALWAYS = "always"
    UNLESS_STOPPED = "unless-stopped"
    ON_FAILURE = "on-failure"


@dataclass
class DockerVolumeMount:
    """Docker volume mount information"""
    source: str
    target: str
    type: str = "bind"  # bind, volume, tmpfs
    read_only: bool = False
    
    def is_bind_mount(self) -> bool:
        """Check if this is a bind mount"""
        return self.type == "bind"
    
    def is_named_volume(self) -> bool:
        """Check if this is a named volume"""
        return self.type == "volume"
    
    def is_absolute_path(self) -> bool:
        """Check if source is an absolute path"""
        return self.source.startswith('/')


@dataclass
class DockerPortMapping:
    """Docker port mapping information"""
    container_port: int
    host_port: Optional[int] = None
    host_ip: str = "0.0.0.0"
    protocol: str = "tcp"
    
    def to_docker_format(self) -> str:
        """Convert to Docker port format (host:container)"""
        if self.host_port:
            return f"{self.host_ip}:{self.host_port}:{self.container_port}/{self.protocol}"
        return f"{self.container_port}/{self.protocol}"


@dataclass
class DockerContainer:
    """Docker Container domain entity"""
    
    id: str
    name: str
    image: str
    state: DockerContainerState
    labels: Dict[str, str] = field(default_factory=dict)
    environment: Dict[str, str] = field(default_factory=dict)
    volume_mounts: List[DockerVolumeMount] = field(default_factory=list)
    port_mappings: List[DockerPortMapping] = field(default_factory=list)
    networks: List[str] = field(default_factory=list)
    restart_policy: DockerRestartPolicy = DockerRestartPolicy.NO
    working_dir: Optional[str] = None
    user: Optional[str] = None
    command: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    @property
    def project_name(self) -> Optional[str]:
        """Get Docker Compose project name from labels"""
        return self.labels.get('com.docker.compose.project')
    
    @property
    def service_name(self) -> Optional[str]:
        """Get Docker Compose service name from labels"""
        return self.labels.get('com.docker.compose.service')
    
    @property
    def compose_file(self) -> Optional[str]:
        """Get Docker Compose file path from labels"""
        return self.labels.get('com.docker.compose.project.config_files')
    
    def is_running(self) -> bool:
        """Check if container is running"""
        return self.state == DockerContainerState.RUNNING
    
    def is_compose_container(self) -> bool:
        """Check if this is a Docker Compose container"""
        return self.project_name is not None
    
    def get_bind_mounts(self) -> List[DockerVolumeMount]:
        """Get all bind mounts"""
        return [mount for mount in self.volume_mounts if mount.is_bind_mount()]
    
    def get_named_volumes(self) -> List[DockerVolumeMount]:
        """Get all named volumes"""
        return [mount for mount in self.volume_mounts if mount.is_named_volume()]
    
    def get_data_directories(self) -> List[str]:
        """Get all directories that contain persistent data"""
        data_dirs = []
        for mount in self.get_bind_mounts():
            if mount.is_absolute_path() and not mount.read_only:
                data_dirs.append(mount.source)
        return data_dirs
    
    def has_exposed_ports(self) -> bool:
        """Check if container has exposed ports"""
        return len(self.port_mappings) > 0
    
    def is_zfs_compatible(self, zfs_mount_points: List[str]) -> bool:
        """Check if all data directories are on ZFS"""
        data_dirs = self.get_data_directories()
        for data_dir in data_dirs:
            is_on_zfs = any(data_dir.startswith(mount) for mount in zfs_mount_points)
            if not is_on_zfs:
                return False
        return True
    
    def get_environment_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get environment variable value"""
        return self.environment.get(key, default)


@dataclass
class DockerImage:
    """Docker Image domain entity"""
    
    id: str
    tags: List[str] = field(default_factory=list)
    size: int = 0  # Size in bytes
    created_at: Optional[datetime] = None
    architecture: str = "amd64"
    os: str = "linux"
    
    @property
    def primary_tag(self) -> Optional[str]:
        """Get the primary tag (first one)"""
        return self.tags[0] if self.tags else None
    
    @property
    def repository(self) -> Optional[str]:
        """Get repository name from primary tag"""
        if self.primary_tag and ':' in self.primary_tag:
            return self.primary_tag.split(':')[0]
        return self.primary_tag
    
    @property
    def tag_version(self) -> Optional[str]:
        """Get tag version from primary tag"""
        if self.primary_tag and ':' in self.primary_tag:
            return self.primary_tag.split(':', 1)[1]
        return "latest"
    
    def is_official_image(self) -> bool:
        """Check if this is an official Docker Hub image"""
        if not self.repository:
            return False
        return '/' not in self.repository or self.repository.startswith('library/')
    
    def is_local_image(self) -> bool:
        """Check if this is a locally built image"""
        if not self.repository:
            return True
        return not ('.' in self.repository or '/' in self.repository)
    
    def size_mb(self) -> float:
        """Get size in megabytes"""
        return self.size / (1024 * 1024)


@dataclass
class DockerNetwork:
    """Docker Network domain entity"""
    
    id: str
    name: str
    driver: str = "bridge"
    scope: str = "local"
    attachable: bool = True
    internal: bool = False
    labels: Dict[str, str] = field(default_factory=dict)
    options: Dict[str, str] = field(default_factory=dict)
    connected_containers: List[str] = field(default_factory=list)
    
    @property
    def project_name(self) -> Optional[str]:
        """Get Docker Compose project name from labels"""
        return self.labels.get('com.docker.compose.project')
    
    def is_compose_network(self) -> bool:
        """Check if this is a Docker Compose network"""
        return self.project_name is not None
    
    def is_bridge_network(self) -> bool:
        """Check if this is a bridge network"""
        return self.driver == "bridge"
    
    def is_overlay_network(self) -> bool:
        """Check if this is an overlay network (for swarm)"""
        return self.driver == "overlay"
    
    def is_host_network(self) -> bool:
        """Check if this is the host network"""
        return self.driver == "host"
    
    def is_isolated(self) -> bool:
        """Check if this network is isolated (internal)"""
        return self.internal
    
    def container_count(self) -> int:
        """Get number of connected containers"""
        return len(self.connected_containers)


@dataclass
class DockerComposeStack:
    """Docker Compose Stack domain entity"""
    
    name: str
    compose_file_path: str
    project_directory: str
    containers: List[DockerContainer] = field(default_factory=list)
    networks: List[DockerNetwork] = field(default_factory=list)
    volumes: Dict[str, Any] = field(default_factory=dict)
    services: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def running_containers(self) -> List[DockerContainer]:
        """Get all running containers"""
        return [c for c in self.containers if c.is_running()]
    
    @property
    def stopped_containers(self) -> List[DockerContainer]:
        """Get all stopped containers"""
        return [c for c in self.containers if not c.is_running()]
    
    def is_running(self) -> bool:
        """Check if stack has any running containers"""
        return len(self.running_containers) > 0
    
    def is_fully_running(self) -> bool:
        """Check if all containers in stack are running"""
        return len(self.containers) > 0 and len(self.running_containers) == len(self.containers)
    
    def get_all_data_directories(self) -> List[str]:
        """Get all data directories from all containers"""
        data_dirs = []
        for container in self.containers:
            data_dirs.extend(container.get_data_directories())
        return list(set(data_dirs))  # Remove duplicates
    
    def is_zfs_compatible(self, zfs_mount_points: List[str]) -> bool:
        """Check if entire stack is ZFS compatible"""
        for container in self.containers:
            if not container.is_zfs_compatible(zfs_mount_points):
                return False
        return True
    
    def get_external_volumes(self) -> List[str]:
        """Get all external volume names"""
        external_volumes = []
        for volume_name, volume_config in self.volumes.items():
            if isinstance(volume_config, dict) and volume_config.get('external', False):
                external_volumes.append(volume_name)
        return external_volumes
    
    def estimate_migration_complexity(self) -> str:
        """Estimate migration complexity based on stack characteristics"""
        score = 0
        
        # Container count
        score += len(self.containers)
        
        # External dependencies
        if self.get_external_volumes():
            score += 5
        
        # Custom networks
        compose_networks = [n for n in self.networks if n.is_compose_network()]
        score += len(compose_networks) * 2
        
        # Port mappings
        total_ports = sum(len(c.port_mappings) for c in self.containers)
        score += total_ports
        
        # Data directories
        data_dirs = self.get_all_data_directories()
        score += len(data_dirs) * 2
        
        if score <= 5:
            return "simple"
        elif score <= 15:
            return "moderate"
        else:
            return "complex"
    
    def get_migration_summary(self) -> Dict[str, Any]:
        """Get comprehensive migration summary"""
        return {
            'name': self.name,
            'containers': len(self.containers),
            'running_containers': len(self.running_containers),
            'networks': len(self.networks),
            'external_volumes': len(self.get_external_volumes()),
            'data_directories': len(self.get_all_data_directories()),
            'complexity': self.estimate_migration_complexity(),
            'compose_file': self.compose_file_path,
            'project_directory': self.project_directory
        }