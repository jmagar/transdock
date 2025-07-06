import logging
from typing import List, Dict, Optional, Any, Union
from dataclasses import dataclass
import contextlib
import docker
from docker.errors import DockerException, NotFound
from .models import VolumeMount
import os
import yaml

logger = logging.getLogger(__name__)


@dataclass
class ContainerInfo:
    """Comprehensive container information extracted from Docker API"""
    id: str
    name: str
    image: str
    image_id: str
    state: str
    status: str
    labels: Dict[str, str]
    mounts: List[Dict[str, Any]]
    networks: List[str]
    environment: Union[Dict[str, str], List[str]]
    ports: Union[Dict[str, Any], List[str]]
    command: List[str]
    working_dir: str
    user: str
    restart_policy: Dict[str, Any]
    created: str
    project_name: Optional[str] = None
    service_name: Optional[str] = None


@dataclass
class NetworkInfo:
    """Docker network information"""
    id: str
    name: str
    driver: str
    scope: str
    attachable: bool
    ingress: bool
    internal: bool
    labels: Dict[str, str]
    options: Dict[str, str]


class DockerOperations:
    """Production Docker API operations for container discovery and management"""
    
    def __init__(self):
        try:
            self.client = docker.from_env()
            # Test connection
            self.client.ping()
            logger.info("Docker API connection established")
        except DockerException as e:
            logger.error(f"Failed to connect to Docker API: {e}")
            raise
    
    def __del__(self):
        """Clean up Docker client connection"""
        if hasattr(self, 'client'):
            with contextlib.suppress(OSError, ConnectionError, RuntimeError, AttributeError, DockerException):
                self.client.close()
    
    def get_docker_client(self, host: Optional[str] = None, ssh_user: str = "root", ssh_port: int = 22) -> docker.DockerClient:
        """Get Docker client for local or remote host
        
        Args:
            host (Optional[str]): Remote host address. If None, use local client.
            ssh_user (str): SSH username for remote connection. Default is "root".
            ssh_port (int): SSH port for remote connection. Default is 22.
        
        Returns:
            docker.DockerClient: Docker client instance.
        """
        if host:
            # Create remote Docker client via SSH
            base_url = f"ssh://{ssh_user}@{host}:{ssh_port}"
            try:
                remote_client = docker.DockerClient(base_url=base_url)
                # Test connection
                remote_client.ping()
                logger.info(f"Remote Docker API connection established to {host}:{ssh_port}")
                return remote_client
            except DockerException as e:
                logger.error(f"Failed to connect to remote Docker API at {host}:{ssh_port}: {e}")
                raise
        else:
            return self.client  # Local client
    
    async def discover_containers_by_project(self, project_name: str, 
                                           host: Optional[str] = None, 
                                           ssh_user: str = "root") -> List[ContainerInfo]:
        """Discover all containers belonging to a Docker Compose project"""
        try:
            client = self.get_docker_client(host, ssh_user)
            containers = []
            all_containers = client.containers.list(all=True)
            
            for container in all_containers:
                labels = container.labels
                container_project = labels.get('com.docker.compose.project')
                
                if container_project == project_name:
                    container_info = self._extract_container_info(container)
                    container_info.project_name = project_name
                    container_info.service_name = labels.get('com.docker.compose.service')
                    containers.append(container_info)
            
            logger.info(f"Discovered {len(containers)} containers for project '{project_name}' on {host or 'localhost'}")
            
            # Clean up remote client
            if host:
                client.close()
            
            return containers
            
        except DockerException as e:
            logger.error(f"Failed to discover containers for project {project_name}: {e}")
            raise
    
    async def discover_containers_by_name(self, name_pattern: str,
                                        host: Optional[str] = None,
                                        ssh_user: str = "root") -> List[ContainerInfo]:
        """Discover containers by name pattern matching"""
        try:
            client = self.get_docker_client(host, ssh_user)
            containers = []
            all_containers = client.containers.list(all=True)
            
            for container in all_containers:
                if name_pattern.lower() in container.name.lower():
                    containers.append(self._extract_container_info(container))
            
            logger.info(f"Discovered {len(containers)} containers matching pattern '{name_pattern}' on {host or 'localhost'}")
            
            # Clean up remote client
            if host:
                client.close()
            
            return containers
            
        except DockerException as e:
            logger.error(f"Failed to discover containers by name pattern {name_pattern}: {e}")
            raise
    
    async def discover_containers_by_labels(self, label_filters: Dict[str, str],
                                          host: Optional[str] = None,
                                          ssh_user: str = "root") -> List[ContainerInfo]:
        """Discover containers by label filters"""
        try:
            client = self.get_docker_client(host, ssh_user)
            containers = []
            filtered_containers = client.containers.list(all=True, filters={"label": [f"{key}={value}" for key, value in label_filters.items()]})
            
            for container in filtered_containers:
                # Verify all label filters match
                if all(container.labels.get(key) == value for key, value in label_filters.items()):
                    containers.append(self._extract_container_info(container))
            
            logger.info(f"Discovered {len(containers)} containers matching label filters on {host or 'localhost'}")
            
            # Clean up remote client
            if host:
                client.close()
            
            return containers
            
        except DockerException as e:
            logger.error(f"Failed to discover containers by labels {label_filters}: {e}")
            raise
    
    async def discover_services_from_compose_file(self, project_path: str) -> Dict[str, Any]:
        """Discover services, volumes, and networks from a Docker Compose file."""
        try:
            compose_file = await self.find_compose_file(project_path)
            if not compose_file:
                raise FileNotFoundError(f"No Docker Compose file found in {project_path}")

            compose_data = await self.parse_compose_file(compose_file)
            
            services = compose_data.get('services', {})
            containers = []
            for service_name, service_def in services.items():
                # Convert ports from compose format to Docker API format
                ports_config = service_def.get('ports', [])
                ports_dict = {}
                
                # Handle ports properly - compose files use list format, but Docker API expects dict
                if isinstance(ports_config, list):
                    for port_mapping in ports_config:
                        if isinstance(port_mapping, str):
                            # Handle string format like "3000:3000" or "8080:8080/tcp"
                            parts = port_mapping.split(':')
                            if len(parts) == 2:
                                host_port, container_port = parts
                                # Add protocol if missing
                                if '/' not in container_port:
                                    container_port += '/tcp'
                                ports_dict[container_port] = [{"HostIp": "0.0.0.0", "HostPort": host_port}]
                            elif len(parts) == 1:
                                # Just expose the port
                                container_port = parts[0]
                                if '/' not in container_port:
                                    container_port += '/tcp'
                                ports_dict[container_port] = [{"HostIp": "0.0.0.0", "HostPort": ""}]
                        elif isinstance(port_mapping, dict):
                            # Handle dict format from compose file
                            target = port_mapping.get('target', '')
                            published = port_mapping.get('published', '')
                            protocol = port_mapping.get('protocol', 'tcp')
                            container_port = f"{target}/{protocol}"
                            if published:
                                ports_dict[container_port] = [{"HostIp": "0.0.0.0", "HostPort": str(published)}]
                            else:
                                ports_dict[container_port] = [{"HostIp": "0.0.0.0", "HostPort": ""}]
                elif isinstance(ports_config, dict):
                    # Already in dict format
                    ports_dict = ports_config
                
                container_info = ContainerInfo(
                    id='',  # Not available from compose file
                    name=f"{os.path.basename(project_path)}_{service_name}_1",
                    image=service_def.get('image', ''),
                    image_id='', # Not available
                    state='exited', # Assume stopped
                    status='exited',
                    labels=service_def.get('labels', {}),
                    mounts=[], # Will be populated by volume extraction
                    networks=list(service_def.get('networks', {}).keys()),
                    environment=service_def.get('environment', {}),
                    ports=ports_dict,
                    command=service_def.get('command', []),
                    working_dir=service_def.get('working_dir', ''),
                    user=service_def.get('user', ''),
                    restart_policy=service_def.get('restart', {}),
                    created='',
                    project_name=os.path.basename(project_path),
                    service_name=service_name
                )
                containers.append(container_info)

            volumes = await self.extract_volume_mounts(compose_data)
            
            networks = []
            compose_networks = compose_data.get('networks', {})
            if compose_networks:
                for network_name, net_def in compose_networks.items():
                    networks.append(NetworkInfo(
                        id='', # Not available
                        name=f"{os.path.basename(project_path)}_{network_name}",
                        driver=net_def.get('driver', 'bridge') if net_def else 'bridge',
                        scope='local',
                        attachable=net_def.get('attachable', False) if net_def else False,
                        ingress=False,
                        internal=net_def.get('internal', False) if net_def else False,
                        labels=net_def.get('labels', {}) if net_def else {},
                        options=net_def.get('driver_opts', {}) if net_def else {}
                    ))

            return {
                "containers": containers,
                "volumes": volumes,
                "networks": networks
            }

        except Exception as e:
            logger.error(f"Failed to discover services from compose file {project_path}: {e}")
            raise
    
    def _extract_container_info(self, container) -> ContainerInfo:
        """Extract comprehensive container information from Docker container object"""
        try:
            # Get detailed container information
            container.reload()
            attrs = container.attrs
            
            # Parse environment variables
            env_dict = {}
            env_list = attrs['Config'].get('Env', [])
            for env_var in env_list:
                if '=' in env_var:
                    key, value = env_var.split('=', 1)
                    env_dict[key] = value
            
            # Extract network information
            networks = list(attrs['NetworkSettings']['Networks'].keys())
            
            # Parse command
            cmd = attrs['Config'].get('Cmd') or []
            entrypoint = attrs['Config'].get('Entrypoint') or []
            command = entrypoint + cmd if entrypoint else cmd
            
            # Get image information
            image_tags = container.image.tags if hasattr(container.image, 'tags') else []
            image_name = image_tags[0] if image_tags else str(container.image.id)
            
            return ContainerInfo(
                id=container.id or '',
                name=container.name or '',
                image=image_name,
                image_id=container.image.id or '',
                state=attrs['State']['Status'],
                status=container.status,
                labels=attrs['Config'].get('Labels') or {},
                mounts=attrs.get('Mounts', []),
                networks=networks,
                environment=env_dict,
                ports=attrs['NetworkSettings'].get('Ports', {}),
                command=command,
                working_dir=attrs['Config'].get('WorkingDir', ''),
                user=attrs['Config'].get('User', ''),
                restart_policy=attrs['HostConfig'].get('RestartPolicy', {}),
                created=attrs['Created']
            )
            
        except Exception as e:
            logger.error(f"Failed to extract container info for {container.name}: {e}")
            raise

    async def get_container_volumes(self, container_info: ContainerInfo,
                                    host: Optional[str] = None,
                                    ssh_user: str = "root") -> List[VolumeMount]:
        """Extract volume mounts from container information"""
        client = None
        volume_mounts = []

        try:
            client = self.get_docker_client(host, ssh_user)
            for mount in container_info.mounts:
                if mount['Type'] == 'bind':
                    volume_mount = VolumeMount(
                        source=mount['Source'],
                        target=mount['Destination']
                    )
                    volume_mounts.append(volume_mount)
                elif mount['Type'] == 'volume':
                    # Handle named volumes by getting their mount point
                    try:
                        volume = client.volumes.get(mount['Name'])
                        volume_mount = VolumeMount(
                            source=volume.attrs['Mountpoint'],
                            target=mount['Destination']
                        )
                        volume_mounts.append(volume_mount)
                    except NotFound:
                        logger.warning(f"Named volume {mount['Name']} not found")
            
            return volume_mounts
            
        finally:
            # Clean up remote client
            if host and client:
                client.close()
    
    async def get_project_networks(self, project_name: str,
                                 host: Optional[str] = None,
                                 ssh_user: str = "root") -> List[NetworkInfo]:
        """Get all networks associated with a Docker Compose project"""
        try:
            client = self.get_docker_client(host, ssh_user)
            networks = []
            all_networks = client.networks.list()
            
            for network in all_networks:
                labels = network.attrs.get('Labels') or {}
                if labels.get('com.docker.compose.project') == project_name:
                    # Handle potential None values
                    network_id = network.id or ''
                    network_name = network.name or ''
                    
                    network_info = NetworkInfo(
                        id=network_id,
                        name=network_name,
                        driver=network.attrs['Driver'],
                        scope=network.attrs['Scope'],
                        attachable=network.attrs['Attachable'],
                        ingress=network.attrs['Ingress'],
                        internal=network.attrs['Internal'],
                        labels=labels,
                        options=network.attrs.get('Options') or {}
                    )
                    networks.append(network_info)
            
            logger.info(f"Found {len(networks)} networks for project '{project_name}' on {host or 'localhost'}")
            
            # Clean up remote client
            if host:
                client.close()
            
            return networks
            
        except DockerException as e:
            logger.error(f"Failed to get networks for project {project_name}: {e}")
            raise
    
    async def stop_containers(self, container_infos: List[ContainerInfo], 
                            timeout: int = 10,
                            host: Optional[str] = None,
                            ssh_user: str = "root") -> bool:
        """Stop multiple containers gracefully"""
        try:
            client = self.get_docker_client(host, ssh_user)
            stopped_count = 0
            
            for container_info in container_infos:
                try:
                    container = client.containers.get(container_info.id)
                    if container.status == 'running':
                        logger.info(f"Stopping container {container_info.name} on {host or 'localhost'}")
                        container.stop(timeout=timeout)
                        stopped_count += 1
                    else:
                        logger.info(f"Container {container_info.name} is already stopped")
                except NotFound:
                    logger.warning(f"Container {container_info.name} not found (may have been removed)")
                except Exception as e:
                    logger.error(f"Failed to stop container {container_info.name}: {e}")
                    continue

            logger.info(f"Successfully stopped {stopped_count} containers on {host or 'localhost'}")
            
            # Clean up remote client
            if host:
                client.close()
            
            return True

        except Exception as e:
            logger.error(f"Failed to stop containers: {e}")
            return False

    async def remove_containers(self, container_infos: List[ContainerInfo], 
                              force: bool = False,
                              host: Optional[str] = None,
                              ssh_user: str = "root") -> bool:
        """Remove multiple containers"""
        try:
            client = self.get_docker_client(host, ssh_user)
            removed_count = 0
            
            for container_info in container_infos:
                try:
                    container = client.containers.get(container_info.id)
                    logger.info(f"Removing container {container_info.name} on {host or 'localhost'}")
                    container.remove(force=force)
                    removed_count += 1
                except NotFound:
                    logger.warning(f"Container {container_info.name} not found (already removed)")
                except Exception as e:
                    logger.error(f"Failed to remove container {container_info.name}: {e}")
                    continue

            logger.info(f"Successfully removed {removed_count} containers on {host or 'localhost'}")
            
            # Clean up remote client
            if host:
                client.close()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove containers: {e}")
            return False

    async def create_network_on_target(self, network_info: NetworkInfo, target_host: str, 
                                     ssh_user: str = "root", ssh_port: int = 22) -> bool:
        """Create a Docker network on the target host using Docker API"""
        try:
            client = self.get_docker_client(target_host, ssh_user)
            
            # Check if network already exists
            try:
                client.networks.get(network_info.name)
                logger.info(f"Network {network_info.name} already exists on {target_host}")
                client.close()
                return True
            except NotFound:
                pass  # Network doesn't exist, create it
            
            # Create network using Docker API
            network_config = {
                'name': network_info.name,
                'driver': network_info.driver,
                'labels': network_info.labels,
                'options': network_info.options,
                'attachable': network_info.attachable,
                'ingress': network_info.ingress,
                'internal': network_info.internal
            }
            
            client.networks.create(**network_config)
            logger.info(f"Created network {network_info.name} on {target_host}")
            
            client.close()
            return True
                
        except DockerException as e:
            logger.error(f"Failed to create network {network_info.name} on {target_host}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to create network on target: {e}")
            return False

    async def recreate_containers_on_target(self, container_infos: List[ContainerInfo], 
                                          volume_mapping: Dict[str, str], target_host: str,
                                          ssh_user: str = "root", ssh_port: int = 22) -> bool:
        """Recreate containers on target host with updated volume paths using Docker API"""
        client = None
        try:
            client = self.get_docker_client(target_host, ssh_user)
            success_count = 0
            
            for container_info in container_infos:
                try:
                    # Build container configuration
                    container_config = self._build_container_config(container_info, volume_mapping)
                    
                    # Create and start container
                    client.containers.run(**container_config)
                    logger.info(f"Successfully recreated container {container_info.name} on {target_host}")
                    success_count += 1
                    
                except DockerException as e:
                    logger.error(f"Failed to recreate container {container_info.name}: {e}")
                    if client:
                        client.close()
                    return False
            
            logger.info(f"Successfully recreated {success_count} containers on {target_host}")
            if client:
                client.close()
            return True

        except Exception as e:
            logger.error(f"Failed to recreate containers on target: {e}")
            if client:
                client.close()
            return False

    def _build_container_config(self, container_info: ContainerInfo, 
                               volume_mapping: Dict[str, str]) -> Dict[str, Any]:
        """Build the container create configuration from ContainerInfo"""
        
        # Build volume bindings
        binds = {}
        for source, target in volume_mapping.items():
            binds[source] = {
                "bind": target,
                "mode": "rw" # Assuming read-write, can be made more flexible
            }
        
        # Build environment variables, handling both list and dict formats
        environment = {}
        if isinstance(container_info.environment, dict):
            environment = container_info.environment
        elif isinstance(container_info.environment, list):
            for env_var in container_info.environment:
                if '=' in env_var:
                    key, value = env_var.split('=', 1)
                    environment[key] = value

        # Build port bindings, handling both list and dict formats
        port_bindings = {}
        if isinstance(container_info.ports, list):
            for port_mapping in container_info.ports:
                parts = str(port_mapping).split(':')
                if len(parts) == 2:
                    host_port, container_port = parts
                    # Add protocol if missing
                    if '/' not in container_port:
                        container_port += '/tcp'
                    port_bindings[container_port] = host_port
                elif len(parts) == 1:
                    container_port = parts[0]
                    if '/' not in container_port:
                        container_port += '/tcp'
                    port_bindings[container_port] = None # Expose port
        elif isinstance(container_info.ports, dict):
            # Convert Docker API format to Docker client create format
            for container_port, host_bindings in container_info.ports.items():
                if host_bindings and isinstance(host_bindings, list) and len(host_bindings) > 0:
                    host_port = host_bindings[0].get('HostPort', '')
                    port_bindings[container_port] = host_port if host_port else None
                else:
                    port_bindings[container_port] = None

        config = {
            "name": container_info.name,
            "image": container_info.image,
            "labels": container_info.labels,
            "environment": environment,
            "host_config": self.client.api.create_host_config(
                binds=binds,
                port_bindings=port_bindings,
                restart_policy=container_info.restart_policy
            ),
            "command": container_info.command,
            "working_dir": container_info.working_dir,
            "user": container_info.user,
            "tty": True,
            "stdin_open": True
        }
        
        return config
    
    async def connect_container_to_networks(self, container_name: str, networks: List[str],
                                          target_host: str, ssh_user: str = "root", 
                                          ssh_port: int = 22) -> bool:
        """Connect container to additional networks on target host using Docker API"""
        client = None
        try:
            client = self.get_docker_client(target_host, ssh_user)
            
            # Skip the first network (already connected during creation)
            additional_networks = networks[1:] if len(networks) > 1 else []
            
            for network_name in additional_networks:
                if network_name == 'bridge':
                    continue
                    
                try:
                    network = client.networks.get(network_name)
                    container = client.containers.get(container_name)
                    network.connect(container)
                    logger.info(f"Connected {container_name} to network {network_name}")
                except NotFound as e:
                    logger.error(f"Network {network_name} or container {container_name} not found: {e}")
                    if client:
                        client.close()
                    return False
                except DockerException as e:
                    logger.error(f"Failed to connect {container_name} to network {network_name}: {e}")
                    if client:
                        client.close()
                    return False
            
            if client:
                client.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect container to networks: {e}")
            if client:
                client.close()
            return False

    async def get_container_by_name(self, name: str,
                                  host: Optional[str] = None,
                                  ssh_user: str = "root") -> Optional[ContainerInfo]:
        """Get container information by exact name"""
        client = None
        try:
            client = self.get_docker_client(host, ssh_user)
            container = client.containers.get(name)
            container_info = self._extract_container_info(container)
            
            # Clean up remote client
            if host and client:
                client.close()
            
            return container_info
        except NotFound:
            if host and client:
                client.close()
            return None
        except DockerException as e:
            if host and client:
                client.close()
            logger.error(f"Failed to get container {name}: {e}")
            raise
    
    async def list_all_containers(self, include_stopped: bool = True,
                                host: Optional[str] = None,
                                ssh_user: str = "root") -> List[ContainerInfo]:
        """List all containers on the system"""
        try:
            client = self.get_docker_client(host, ssh_user)
            containers = []
            all_containers = client.containers.list(all=include_stopped)
            
            for container in all_containers:
                containers.append(self._extract_container_info(container))
            
            # Clean up remote client
            if host:
                client.close()
            
            return containers
            
        except DockerException as e:
            logger.error(f"Failed to list containers: {e}")
            raise
    
    async def pull_image_on_target(self, image: str, target_host: str, 
                                 ssh_user: str = "root", ssh_port: int = 22) -> bool:
        """Pull Docker image on target host using Docker API"""
        try:
            client = self.get_docker_client(target_host, ssh_user)
            
            # Pull image using Docker API
            client.images.pull(image)
            logger.info(f"Successfully pulled image {image} on {target_host}")
            
            client.close()
            return True
                
        except DockerException as e:
            logger.error(f"Failed to pull image {image} on {target_host}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to pull image on target: {e}")
            return False
    
    async def validate_docker_on_target(self, target_host: str, ssh_user: str = "root", 
                                      ssh_port: int = 22) -> bool:
        """Validate Docker is available and accessible on target host using Docker API"""
        try:
            client = self.get_docker_client(target_host, ssh_user)
            
            # Test connection and get version
            client.ping()
            version_info = client.version()
            version = version_info.get('Version', 'unknown')
            
            logger.info(f"Docker {version} available on {target_host}")
            client.close()
            return True
                
        except DockerException as e:
            logger.error(f"Docker not available on {target_host}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to validate Docker on target: {e}")
            return False

    async def find_compose_file(self, project_path: str) -> Optional[str]:
        """Find a Docker Compose file in the given directory"""
        compose_files = ['docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml']
        
        for compose_file in compose_files:
            full_path = os.path.join(project_path, compose_file)
            if os.path.exists(full_path):
                return full_path
        
        return None

    async def parse_compose_file(self, compose_file_path: str) -> Dict[str, Any]:
        """Parse a Docker Compose file and return its contents"""
        try:
            with open(compose_file_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to parse compose file {compose_file_path}: {e}")
            return {}

    async def extract_volume_mounts(self, compose_data: Dict[str, Any]) -> List[VolumeMount]:
        """Extract volume mounts from parsed compose data"""
        volumes = []
        
        services = compose_data.get('services', {})
        
        # Early return if no services defined
        if not services:
            return volumes
            
        compose_dir = os.path.dirname(os.path.abspath(compose_data.get('_compose_file_path', '')))
        
        for service_config in services.values():
            service_volumes = service_config.get('volumes', [])
            
            # Skip services without volumes
            if not service_volumes:
                continue
                
            for volume in service_volumes:
                volume_mount = self._parse_volume_definition(volume, compose_dir)
                # Use guard clause to handle invalid volume mounts
                if not volume_mount:
                    continue
                    
                volumes.append(volume_mount)
        
        return volumes
    
    def _parse_volume_definition(self, volume: Any, compose_dir: str) -> Optional[VolumeMount]:
        """Parse a single volume definition from compose data"""
        import os
        
        # Handle string format volumes
        if isinstance(volume, str):
            return self._parse_string_volume(volume, compose_dir)
            
        # Handle dictionary format volumes
        if isinstance(volume, dict):
            return self._parse_dict_volume(volume, compose_dir)
        
        # Log unsupported formats and return None
        logger.warning(f"Unsupported volume format: {type(volume)}")
        return None
    
    def _parse_string_volume(self, volume: str, compose_dir: str) -> Optional[VolumeMount]:
        """Parse string format volume: 'host_path:container_path'"""
        import os
        
        # Guard clause: volume must contain colon separator
        if ':' not in volume:
            return None
            
        parts = volume.split(':')
        
        # Guard clause: must have at least host and container paths
        if len(parts) < 2:
            return None
            
        host_path = parts[0]
        container_path = parts[1]
        
        # Expand relative paths to absolute
        if not os.path.isabs(host_path):
            host_path = os.path.join(compose_dir, host_path)
        
        return VolumeMount(source=host_path, target=container_path)
    
    def _parse_dict_volume(self, volume: Dict[str, Any], compose_dir: str) -> Optional[VolumeMount]:
        """Parse dictionary format volume: {'source': 'host_path', 'target': 'container_path'}"""
        import os
        
        source = volume.get('source', '')
        target = volume.get('target', '')
        
        # Guard clause: both source and target must be specified
        if not source or not target:
            return None
            
        # Expand relative paths to absolute
        if not os.path.isabs(source):
            source = os.path.join(compose_dir, source)
        
        return VolumeMount(source=source, target=target)
