import os
import logging
import asyncio
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
import docker
from docker.errors import DockerException, NotFound, APIError
from .models import VolumeMount
from .security_utils import SecurityUtils, SecurityValidationError

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
    environment: Dict[str, str]
    ports: Dict[str, Any]
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
            try:
                self.client.close()
            except:
                pass
    
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
        client = self.get_docker_client(host, ssh_user)
        volume_mounts = []
        
        try:
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
            if host:
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
                    return False
            
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
                    return False
            
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
                existing_network = client.networks.get(network_info.name)
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
            
            created_network = client.networks.create(**network_config)
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
        try:
            client = self.get_docker_client(target_host, ssh_user)
            success_count = 0
            
            for container_info in container_infos:
                try:
                    # Build container configuration
                    container_config = self._build_container_config(container_info, volume_mapping)
                    
                    # Create and start container
                    container = client.containers.run(**container_config)
                    logger.info(f"Successfully recreated container {container_info.name} on {target_host}")
                    success_count += 1
                    
                except DockerException as e:
                    logger.error(f"Failed to recreate container {container_info.name}: {e}")
                    client.close()
                    return False
            
            logger.info(f"Successfully recreated {success_count} containers on {target_host}")
            client.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to recreate containers on target: {e}")
            return False
    
    def _build_container_config(self, container_info: ContainerInfo, 
                               volume_mapping: Dict[str, str]) -> Dict[str, Any]:
        """Build container configuration for Docker API"""
        config = {
            'image': container_info.image,
            'name': container_info.name,
            'detach': True,
            'environment': container_info.environment,
            'labels': container_info.labels,
            'command': container_info.command if container_info.command else None,
            'working_dir': container_info.working_dir if container_info.working_dir else None,
            'user': container_info.user if container_info.user else None,
        }
        
        # Add volumes with updated paths
        volumes = {}
        for mount in container_info.mounts:
            if mount['Type'] == 'bind':
                old_source = mount['Source']
                new_source = volume_mapping.get(old_source, old_source)
                destination = mount['Destination']
                
                # Add read-only flag if present
                mode = 'ro' if mount.get('RW', True) is False else 'rw'
                volumes[new_source] = {'bind': destination, 'mode': mode}
        
        if volumes:
            config['volumes'] = volumes
        
        # Add ports
        ports = {}
        port_bindings = {}
        for container_port, host_configs in container_info.ports.items():
            if host_configs:
                for host_config in host_configs:
                    host_port = host_config['HostPort']
                    host_ip = host_config.get('HostIp', '')
                    
                    if host_ip:
                        port_bindings[container_port] = [(host_ip, host_port)]
                    else:
                        port_bindings[container_port] = host_port
                    
                    ports[container_port] = None
        
        if ports:
            config['ports'] = ports
        if port_bindings:
            config['port_bindings'] = port_bindings
        
        # Add restart policy
        restart_policy = container_info.restart_policy
        if restart_policy.get('Name') and restart_policy['Name'] != 'no':
            policy_name = restart_policy['Name']
            if policy_name == 'on-failure' and restart_policy.get('MaximumRetryCount'):
                config['restart_policy'] = {
                    'Name': policy_name,
                    'MaximumRetryCount': restart_policy['MaximumRetryCount']
                }
            else:
                config['restart_policy'] = {'Name': policy_name}
        
        # Add networks (only first network, others added separately)
        if container_info.networks and container_info.networks[0] != 'bridge':
            config['network'] = container_info.networks[0]
        
        return config
    
    async def connect_container_to_networks(self, container_name: str, networks: List[str],
                                          target_host: str, ssh_user: str = "root", 
                                          ssh_port: int = 22) -> bool:
        """Connect container to additional networks on target host using Docker API"""
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
                    client.close()
                    return False
                except DockerException as e:
                    logger.error(f"Failed to connect {container_name} to network {network_name}: {e}")
                    client.close()
                    return False
            
            client.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect container to networks: {e}")
            return False
    
    async def get_container_by_name(self, name: str,
                                  host: Optional[str] = None,
                                  ssh_user: str = "root") -> Optional[ContainerInfo]:
        """Get container information by exact name"""
        try:
            client = self.get_docker_client(host, ssh_user)
            container = client.containers.get(name)
            container_info = self._extract_container_info(container)
            
            # Clean up remote client
            if host:
                client.close()
            
            return container_info
        except NotFound:
            if host:
                client.close()
            return None
        except DockerException as e:
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
            pulled_image = client.images.pull(image)
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
