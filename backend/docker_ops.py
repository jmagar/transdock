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
    
    async def discover_containers_by_project(self, project_name: str) -> List[ContainerInfo]:
        """Discover all containers belonging to a Docker Compose project"""
        try:
            containers = []
            all_containers = self.client.containers.list(all=True)
            
            for container in all_containers:
                labels = container.labels
                container_project = labels.get('com.docker.compose.project')
                
                if container_project == project_name:
                    container_info = self._extract_container_info(container)
                    container_info.project_name = project_name
                    container_info.service_name = labels.get('com.docker.compose.service')
                    containers.append(container_info)
            
            logger.info(f"Discovered {len(containers)} containers for project '{project_name}'")
            return containers
            
        except DockerException as e:
            logger.error(f"Failed to discover containers for project {project_name}: {e}")
            raise
    
    async def discover_containers_by_name(self, name_pattern: str) -> List[ContainerInfo]:
        """Discover containers by name pattern matching"""
        try:
            containers = []
            all_containers = self.client.containers.list(all=True)
            
            for container in all_containers:
                if name_pattern.lower() in container.name.lower():
                    containers.append(self._extract_container_info(container))
            
            logger.info(f"Discovered {len(containers)} containers matching pattern '{name_pattern}'")
            return containers
            
        except DockerException as e:
            logger.error(f"Failed to discover containers by name pattern {name_pattern}: {e}")
            raise
    
    async def discover_containers_by_labels(self, label_filters: Dict[str, str]) -> List[ContainerInfo]:
        """Discover containers by label filters"""
        try:
            containers = []
            filters = {f"label={key}={value}" for key, value in label_filters.items()}
            
            filtered_containers = self.client.containers.list(all=True, filters={"label": list(label_filters.keys())})
            
            for container in filtered_containers:
                # Verify all label filters match
                if all(container.labels.get(key) == value for key, value in label_filters.items()):
                    containers.append(self._extract_container_info(container))
            
            logger.info(f"Discovered {len(containers)} containers matching label filters")
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
    
    async def get_container_volumes(self, container_info: ContainerInfo) -> List[VolumeMount]:
        """Extract volume mounts from container information"""
        volume_mounts = []
        
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
                    volume = self.client.volumes.get(mount['Name'])
                    volume_mount = VolumeMount(
                        source=volume.attrs['Mountpoint'],
                        target=mount['Destination']
                    )
                    volume_mounts.append(volume_mount)
                except NotFound:
                    logger.warning(f"Named volume {mount['Name']} not found")
        
        return volume_mounts
    
    async def get_project_networks(self, project_name: str) -> List[NetworkInfo]:
        """Get all networks associated with a Docker Compose project"""
        try:
            networks = []
            all_networks = self.client.networks.list()
            
            for network in all_networks:
                labels = network.attrs.get('Labels') or {}
                if labels.get('com.docker.compose.project') == project_name:
                    network_info = NetworkInfo(
                        id=network.id,
                        name=network.name,
                        driver=network.attrs['Driver'],
                        scope=network.attrs['Scope'],
                        attachable=network.attrs['Attachable'],
                        ingress=network.attrs['Ingress'],
                        internal=network.attrs['Internal'],
                        labels=labels,
                        options=network.attrs.get('Options') or {}
                    )
                    networks.append(network_info)
            
            logger.info(f"Found {len(networks)} networks for project '{project_name}'")
            return networks
            
        except DockerException as e:
            logger.error(f"Failed to get networks for project {project_name}: {e}")
            raise
    
    async def stop_containers(self, container_infos: List[ContainerInfo], timeout: int = 10) -> bool:
        """Stop multiple containers gracefully"""
        try:
            stopped_count = 0
            
            for container_info in container_infos:
                try:
                    container = self.client.containers.get(container_info.id)
                    if container.status == 'running':
                        logger.info(f"Stopping container {container_info.name}")
                        container.stop(timeout=timeout)
                        stopped_count += 1
                    else:
                        logger.info(f"Container {container_info.name} is already stopped")
                except NotFound:
                    logger.warning(f"Container {container_info.name} not found (may have been removed)")
                except Exception as e:
                    logger.error(f"Failed to stop container {container_info.name}: {e}")
                    return False
            
            logger.info(f"Successfully stopped {stopped_count} containers")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop containers: {e}")
            return False
    
    async def remove_containers(self, container_infos: List[ContainerInfo], force: bool = False) -> bool:
        """Remove multiple containers"""
        try:
            removed_count = 0
            
            for container_info in container_infos:
                try:
                    container = self.client.containers.get(container_info.id)
                    logger.info(f"Removing container {container_info.name}")
                    container.remove(force=force)
                    removed_count += 1
                except NotFound:
                    logger.warning(f"Container {container_info.name} not found (already removed)")
                except Exception as e:
                    logger.error(f"Failed to remove container {container_info.name}: {e}")
                    return False
            
            logger.info(f"Successfully removed {removed_count} containers")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove containers: {e}")
            return False
    
    async def create_network_on_target(self, network_info: NetworkInfo, target_host: str, 
                                     ssh_user: str = "root", ssh_port: int = 22) -> bool:
        """Create a Docker network on the target host"""
        try:
            # Build docker network create command
            cmd_parts = ["docker", "network", "create"]
            
            # Add driver
            cmd_parts.extend(["--driver", network_info.driver])
            
            # Add labels
            for key, value in network_info.labels.items():
                cmd_parts.extend(["--label", f"{key}={value}"])
            
            # Add options
            for key, value in network_info.options.items():
                cmd_parts.extend(["--opt", f"{key}={value}"])
            
            # Add network name
            cmd_parts.append(network_info.name)
            
            # Execute on remote host
            ssh_cmd = [
                "ssh", "-p", str(ssh_port), f"{ssh_user}@{target_host}",
                " ".join(cmd_parts)
            ]
            
            returncode, stdout, stderr = await self._run_command(ssh_cmd)
            if returncode == 0:
                logger.info(f"Created network {network_info.name} on {target_host}")
                return True
            else:
                logger.error(f"Failed to create network {network_info.name}: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to create network on target: {e}")
            return False
    
    async def recreate_containers_on_target(self, container_infos: List[ContainerInfo], 
                                          volume_mapping: Dict[str, str], target_host: str,
                                          ssh_user: str = "root", ssh_port: int = 22) -> bool:
        """Recreate containers on target host with updated volume paths"""
        try:
            success_count = 0
            
            for container_info in container_infos:
                docker_run_cmd = self._generate_docker_run_command(container_info, volume_mapping)
                
                # Execute on remote host
                ssh_cmd = [
                    "ssh", "-p", str(ssh_port), f"{ssh_user}@{target_host}",
                    docker_run_cmd
                ]
                
                returncode, stdout, stderr = await self._run_command(ssh_cmd)
                if returncode == 0:
                    logger.info(f"Successfully recreated container {container_info.name} on {target_host}")
                    success_count += 1
                else:
                    logger.error(f"Failed to recreate container {container_info.name}: {stderr}")
                    return False
            
            logger.info(f"Successfully recreated {success_count} containers on target")
            return True
            
        except Exception as e:
            logger.error(f"Failed to recreate containers on target: {e}")
            return False
    
    def _generate_docker_run_command(self, container_info: ContainerInfo, 
                                   volume_mapping: Dict[str, str]) -> str:
        """Generate docker run command from container information"""
        cmd_parts = ["docker", "run", "-d"]
        
        # Add name
        cmd_parts.extend(["--name", container_info.name])
        
        # Add volumes with updated paths
        for mount in container_info.mounts:
            if mount['Type'] == 'bind':
                old_source = mount['Source']
                new_source = volume_mapping.get(old_source, old_source)
                destination = mount['Destination']
                
                # Add read-only flag if present
                if mount.get('RW', True) is False:
                    cmd_parts.extend(["-v", f"{new_source}:{destination}:ro"])
                else:
                    cmd_parts.extend(["-v", f"{new_source}:{destination}"])
        
        # Add ports
        for container_port, host_configs in container_info.ports.items():
            if host_configs:
                for host_config in host_configs:
                    host_port = host_config['HostPort']
                    host_ip = host_config.get('HostIp', '')
                    if host_ip:
                        cmd_parts.extend(["-p", f"{host_ip}:{host_port}:{container_port}"])
                    else:
                        cmd_parts.extend(["-p", f"{host_port}:{container_port}"])
        
        # Add environment variables
        for key, value in container_info.environment.items():
            # Escape shell special characters
            escaped_value = SecurityUtils.escape_shell_argument(value)
            cmd_parts.extend(["-e", f"{key}={escaped_value}"])
        
        # Add labels
        for key, value in container_info.labels.items():
            escaped_value = SecurityUtils.escape_shell_argument(value)
            cmd_parts.extend(["--label", f"{key}={escaped_value}"])
        
        # Add restart policy
        restart_policy = container_info.restart_policy
        if restart_policy.get('Name') and restart_policy['Name'] != 'no':
            policy_name = restart_policy['Name']
            if policy_name == 'on-failure' and restart_policy.get('MaximumRetryCount'):
                cmd_parts.extend(["--restart", f"{policy_name}:{restart_policy['MaximumRetryCount']}"])
            else:
                cmd_parts.extend(["--restart", policy_name])
        
        # Add working directory
        if container_info.working_dir:
            cmd_parts.extend(["-w", container_info.working_dir])
        
        # Add user
        if container_info.user:
            cmd_parts.extend(["-u", container_info.user])
        
        # Add networks (only first network, others added via docker network connect)
        if container_info.networks and container_info.networks[0] != 'bridge':
            cmd_parts.extend(["--network", container_info.networks[0]])
        
        # Add image
        cmd_parts.append(container_info.image)
        
        # Add command
        if container_info.command:
            cmd_parts.extend(container_info.command)
        
        return " ".join(cmd_parts)
    
    async def connect_container_to_networks(self, container_name: str, networks: List[str],
                                          target_host: str, ssh_user: str = "root", 
                                          ssh_port: int = 22) -> bool:
        """Connect container to additional networks on target host"""
        try:
            # Skip the first network (already connected during creation)
            additional_networks = networks[1:] if len(networks) > 1 else []
            
            for network in additional_networks:
                if network == 'bridge':
                    continue
                    
                connect_cmd = f"docker network connect {network} {container_name}"
                ssh_cmd = [
                    "ssh", "-p", str(ssh_port), f"{ssh_user}@{target_host}",
                    connect_cmd
                ]
                
                returncode, stdout, stderr = await self._run_command(ssh_cmd)
                if returncode != 0:
                    logger.error(f"Failed to connect {container_name} to network {network}: {stderr}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect container to networks: {e}")
            return False
    
    async def _run_command(self, cmd: List[str], cwd: Optional[str] = None) -> Tuple[int, str, str]:
        """Run a command asynchronously"""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            stdout, stderr = await process.communicate()
            returncode = process.returncode if process.returncode is not None else 1
            return returncode, stdout.decode(), stderr.decode()
        except Exception as e:
            logger.error(f"Command failed: {' '.join(cmd)} - {e}")
            return 1, "", str(e)
    
    async def get_container_by_name(self, name: str) -> Optional[ContainerInfo]:
        """Get container information by exact name"""
        try:
            container = self.client.containers.get(name)
            return self._extract_container_info(container)
        except NotFound:
            return None
        except DockerException as e:
            logger.error(f"Failed to get container {name}: {e}")
            raise
    
    async def list_all_containers(self, include_stopped: bool = True) -> List[ContainerInfo]:
        """List all containers on the system"""
        try:
            containers = []
            all_containers = self.client.containers.list(all=include_stopped)
            
            for container in all_containers:
                containers.append(self._extract_container_info(container))
            
            return containers
            
        except DockerException as e:
            logger.error(f"Failed to list containers: {e}")
            raise
    
    async def pull_image_on_target(self, image: str, target_host: str, 
                                 ssh_user: str = "root", ssh_port: int = 22) -> bool:
        """Pull Docker image on target host"""
        try:
            pull_cmd = f"docker pull {image}"
            ssh_cmd = [
                "ssh", "-p", str(ssh_port), f"{ssh_user}@{target_host}",
                pull_cmd
            ]
            
            returncode, stdout, stderr = await self._run_command(ssh_cmd)
            if returncode == 0:
                logger.info(f"Successfully pulled image {image} on {target_host}")
                return True
            else:
                logger.error(f"Failed to pull image {image}: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to pull image on target: {e}")
            return False
    
    async def validate_docker_on_target(self, target_host: str, ssh_user: str = "root", 
                                      ssh_port: int = 22) -> bool:
        """Validate Docker is available and accessible on target host"""
        try:
            version_cmd = "docker version --format '{{.Server.Version}}'"
            ssh_cmd = [
                "ssh", "-p", str(ssh_port), f"{ssh_user}@{target_host}",
                version_cmd
            ]
            
            returncode, stdout, stderr = await self._run_command(ssh_cmd)
            if returncode == 0:
                version = stdout.strip()
                logger.info(f"Docker {version} available on {target_host}")
                return True
            else:
                logger.error(f"Docker not available on {target_host}: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to validate Docker on target: {e}")
            return False
