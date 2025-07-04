import logging
import os
import yaml
import json
import asyncio
from typing import List, Dict, Optional, Tuple
from .models import HostInfo, HostCapabilities, RemoteStack, StackAnalysis, VolumeMount
from .security_utils import SecurityUtils, SecurityValidationError
from .docker_ops import DockerOperations

logger = logging.getLogger(__name__)


class HostService:
    """Service for managing remote hosts and stack operations"""
    
    def __init__(self):
        self.docker_ops = DockerOperations()
        # Common paths to check for compose stacks
        self.common_compose_paths = [
            "/mnt/cache/compose",
            "/mnt/user/compose", 
            "/opt/compose",
            "/home/*/compose",
            "/docker/compose"
        ]
        # Common paths to check for appdata
        self.common_appdata_paths = [
            "/mnt/cache/appdata",
            "/mnt/user/appdata",
            "/opt/appdata", 
            "/home/*/appdata",
            "/docker/appdata"
        ]
    
    async def run_remote_command(self, host_info: HostInfo, command: str) -> Tuple[int, str, str]:
        """Run a command on a remote host"""
        try:
            # Validate inputs
            SecurityUtils.validate_hostname(host_info.hostname)
            SecurityUtils.validate_username(host_info.ssh_user)
            SecurityUtils.validate_port(host_info.ssh_port)
            
            # Build SSH command
            ssh_cmd = SecurityUtils.build_ssh_command(
                host_info.hostname, 
                host_info.ssh_user, 
                host_info.ssh_port, 
                command
            )
            
            # Execute command
            process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            returncode = process.returncode if process.returncode is not None else 1
            
            return returncode, stdout.decode(), stderr.decode()
            
        except SecurityValidationError as e:
            logger.error(f"Security validation failed: {e}")
            return 1, "", f"Security validation failed: {e}"
        except Exception as e:
            logger.error(f"Failed to run remote command: {e}")
            return 1, "", str(e)
    
    async def check_host_capabilities(self, host_info: HostInfo) -> HostCapabilities:
        """Check what capabilities are available on a remote host"""
        capabilities = HostCapabilities(
            hostname=host_info.hostname,
            docker_available=False,
            zfs_available=False
        )
        
        try:
            # Check Docker availability
            returncode, stdout, stderr = await self.run_remote_command(
                host_info, "docker --version"
            )
            capabilities.docker_available = returncode == 0
            
            # Check ZFS availability
            returncode, stdout, stderr = await self.run_remote_command(
                host_info, "zfs version"
            )
            capabilities.zfs_available = returncode == 0
            
            # If ZFS is available, get pools
            if capabilities.zfs_available:
                returncode, stdout, stderr = await self.run_remote_command(
                    host_info, "zpool list -H -o name"
                )
                if returncode == 0:
                    capabilities.zfs_pools = [line.strip() for line in stdout.split('\n') if line.strip()]
            
            # Discover compose paths
            capabilities.compose_paths = await self._discover_paths(host_info, self.common_compose_paths)
            
            # Discover appdata paths
            capabilities.appdata_paths = await self._discover_paths(host_info, self.common_appdata_paths)
            
        except Exception as e:
            logger.error(f"Failed to check host capabilities: {e}")
            capabilities.error = str(e)
        
        return capabilities
    
    async def _discover_paths(self, host_info: HostInfo, paths: List[str]) -> List[str]:
        """Discover which paths exist on the remote host"""
        existing_paths = []
        
        for path in paths:
            # Handle wildcard paths
            if '*' in path:
                # Use find to expand wildcards
                find_cmd = f"find {path.replace('*', '')} -maxdepth 1 -type d 2>/dev/null || true"
                returncode, stdout, stderr = await self.run_remote_command(host_info, find_cmd)
                if returncode == 0 and stdout.strip():
                    existing_paths.extend([line.strip() for line in stdout.split('\n') if line.strip()])
            else:
                # Check if directory exists
                test_cmd = f"test -d {path} && echo 'exists' || echo 'not_found'"
                returncode, stdout, stderr = await self.run_remote_command(host_info, test_cmd)
                if returncode == 0 and 'exists' in stdout:
                    existing_paths.append(path)
        
        return existing_paths
    
    async def list_remote_stacks(self, host_info: HostInfo, compose_path: str) -> List[RemoteStack]:
        """List compose stacks on a remote host"""
        stacks = []
        
        try:
            # Validate path
            safe_path = SecurityUtils.sanitize_path(compose_path, allow_absolute=True)
            
            # Find compose files
            find_cmd = f"find {SecurityUtils.escape_shell_argument(safe_path)} -name 'docker-compose.yml' -o -name 'docker-compose.yaml' -o -name 'compose.yml' -o -name 'compose.yaml' 2>/dev/null || true"
            returncode, stdout, stderr = await self.run_remote_command(host_info, find_cmd)
            
            if returncode == 0 and stdout.strip():
                compose_files = [line.strip() for line in stdout.split('\n') if line.strip()]
                
                for compose_file in compose_files:
                    stack_dir = os.path.dirname(compose_file)
                    stack_name = os.path.basename(stack_dir)
                    
                    # Get stack status
                    status = await self._get_remote_stack_status(host_info, stack_dir)
                    
                    # Get services from compose file
                    services = await self._get_remote_stack_services(host_info, compose_file)
                    
                    stack = RemoteStack(
                        name=stack_name,
                        path=stack_dir,
                        compose_file=compose_file,
                        services=services,
                        status=status
                    )
                    stacks.append(stack)
        
        except Exception as e:
            logger.error(f"Failed to list remote stacks: {e}")
        
        return stacks
    
    async def _get_remote_stack_status(self, host_info: HostInfo, stack_dir: str) -> str:
        """Get the status of a remote stack"""
        try:
            # Check if stack is running using docker-compose ps
            compose_cmd = f"cd {SecurityUtils.escape_shell_argument(stack_dir)} && docker-compose ps -q"
            returncode, stdout, stderr = await self.run_remote_command(host_info, compose_cmd)
            
            if returncode == 0:
                if stdout.strip():
                    # Check if containers are actually running
                    container_ids = stdout.strip().split('\n')
                    running_count = 0
                    
                    for container_id in container_ids:
                        if container_id.strip():
                            status_cmd = f"docker inspect {container_id.strip()} --format='{{{{.State.Running}}}}'"
                            ret, out, err = await self.run_remote_command(host_info, status_cmd)
                            if ret == 0 and 'true' in out:
                                running_count += 1
                    
                    if running_count == len(container_ids):
                        return "running"
                    elif running_count > 0:
                        return "partial"
                    else:
                        return "stopped"
                else:
                    return "stopped"
            else:
                return "unknown"
        
        except Exception as e:
            logger.error(f"Failed to get stack status: {e}")
            return "unknown"
    
    async def _get_remote_stack_services(self, host_info: HostInfo, compose_file: str) -> List[str]:
        """Get services from a remote compose file"""
        try:
            # Read compose file
            cat_cmd = f"cat {SecurityUtils.escape_shell_argument(compose_file)}"
            returncode, stdout, stderr = await self.run_remote_command(host_info, cat_cmd)
            
            if returncode == 0:
                try:
                    compose_data = yaml.safe_load(stdout)
                    services = compose_data.get('services', {})
                    return list(services.keys())
                except yaml.YAMLError as e:
                    logger.error(f"Failed to parse compose file: {e}")
                    return []
            else:
                logger.error(f"Failed to read compose file: {stderr}")
                return []
        
        except Exception as e:
            logger.error(f"Failed to get stack services: {e}")
            return []
    
    async def analyze_remote_stack(self, host_info: HostInfo, stack_path: str) -> StackAnalysis:
        """Analyze a remote stack and return detailed information"""
        try:
            # Find compose file
            compose_file = None
            for filename in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
                test_path = os.path.join(stack_path, filename)
                test_cmd = f"test -f {SecurityUtils.escape_shell_argument(test_path)} && echo 'exists' || echo 'not_found'"
                returncode, stdout, stderr = await self.run_remote_command(host_info, test_cmd)
                if returncode == 0 and 'exists' in stdout:
                    compose_file = test_path
                    break
            
            if not compose_file:
                raise ValueError(f"No compose file found in {stack_path}")
            
            # Read and parse compose file
            cat_cmd = f"cat {SecurityUtils.escape_shell_argument(compose_file)}"
            returncode, stdout, stderr = await self.run_remote_command(host_info, cat_cmd)
            
            if returncode != 0:
                raise ValueError(f"Failed to read compose file: {stderr}")
            
            compose_data = yaml.safe_load(stdout)
            services = compose_data.get('services', {})
            
            # Extract volume mounts
            volumes = []
            for service_name, service_config in services.items():
                service_volumes = service_config.get('volumes', [])
                for volume in service_volumes:
                    if isinstance(volume, str):
                        # Handle string format: "source:target"
                        if ':' in volume:
                            source, target = volume.split(':', 1)
                            volumes.append(VolumeMount(source=source, target=target))
                    elif isinstance(volume, dict):
                        # Handle dict format: {"source": "...", "target": "..."}
                        source = volume.get('source', '')
                        target = volume.get('target', '')
                        if source and target:
                            volumes.append(VolumeMount(source=source, target=target))
            
            # Extract networks
            networks = list(compose_data.get('networks', {}).keys())
            
            # Extract external volumes
            external_volumes = []
            volume_definitions = compose_data.get('volumes', {})
            for vol_name, vol_config in volume_definitions.items():
                if isinstance(vol_config, dict) and vol_config.get('external', False):
                    external_volumes.append(vol_name)
            
            # Check if stack is ZFS compatible (all volumes are on ZFS)
            zfs_compatible = await self._check_zfs_compatibility(host_info, volumes)
            
            # Estimate size (if possible)
            estimated_size = await self._estimate_stack_size(host_info, volumes)
            
            return StackAnalysis(
                name=os.path.basename(stack_path),
                path=stack_path,
                compose_file=compose_file,
                services=services,
                volumes=volumes,
                networks=networks,
                external_volumes=external_volumes,
                zfs_compatible=zfs_compatible,
                estimated_size=estimated_size
            )
        
        except Exception as e:
            logger.error(f"Failed to analyze stack: {e}")
            raise ValueError(f"Failed to analyze stack: {e}")
    
    async def _check_zfs_compatibility(self, host_info: HostInfo, volumes: List[VolumeMount]) -> bool:
        """Check if all volumes are on ZFS"""
        try:
            for volume in volumes:
                # Check if volume source is a ZFS dataset
                zfs_cmd = f"zfs list -H {SecurityUtils.escape_shell_argument(volume.source)} 2>/dev/null"
                returncode, stdout, stderr = await self.run_remote_command(host_info, zfs_cmd)
                if returncode != 0:
                    return False
            return True
        except Exception:
            return False
    
    async def _estimate_stack_size(self, host_info: HostInfo, volumes: List[VolumeMount]) -> Optional[int]:
        """Estimate the total size of a stack in bytes"""
        try:
            total_size = 0
            for volume in volumes:
                if os.path.isabs(volume.source):
                    # Get directory size
                    du_cmd = f"du -sb {SecurityUtils.escape_shell_argument(volume.source)} 2>/dev/null || echo '0'"
                    returncode, stdout, stderr = await self.run_remote_command(host_info, du_cmd)
                    if returncode == 0:
                        try:
                            size = int(stdout.split()[0])
                            total_size += size
                        except (ValueError, IndexError):
                            continue
            return total_size if total_size > 0 else None
        except Exception:
            return None
    
    async def start_remote_stack(self, host_info: HostInfo, stack_path: str) -> bool:
        """Start a remote stack"""
        try:
            # Find compose file
            compose_file = None
            for filename in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
                test_path = os.path.join(stack_path, filename)
                test_cmd = f"test -f {SecurityUtils.escape_shell_argument(test_path)} && echo 'exists' || echo 'not_found'"
                returncode, stdout, stderr = await self.run_remote_command(host_info, test_cmd)
                if returncode == 0 and 'exists' in stdout:
                    compose_file = filename
                    break
            
            if not compose_file:
                raise ValueError(f"No compose file found in {stack_path}")
            
            # Start the stack
            start_cmd = f"cd {SecurityUtils.escape_shell_argument(stack_path)} && docker-compose -f {compose_file} up -d"
            returncode, stdout, stderr = await self.run_remote_command(host_info, start_cmd)
            
            if returncode != 0:
                logger.error(f"Failed to start stack: {stderr}")
                return False
            
            logger.info(f"Successfully started stack in {stack_path}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to start remote stack: {e}")
            return False
    
    async def stop_remote_stack(self, host_info: HostInfo, stack_path: str) -> bool:
        """Stop a remote stack"""
        try:
            # Find compose file
            compose_file = None
            for filename in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
                test_path = os.path.join(stack_path, filename)
                test_cmd = f"test -f {SecurityUtils.escape_shell_argument(test_path)} && echo 'exists' || echo 'not_found'"
                returncode, stdout, stderr = await self.run_remote_command(host_info, test_cmd)
                if returncode == 0 and 'exists' in stdout:
                    compose_file = filename
                    break
            
            if not compose_file:
                raise ValueError(f"No compose file found in {stack_path}")
            
            # Stop the stack
            stop_cmd = f"cd {SecurityUtils.escape_shell_argument(stack_path)} && docker-compose -f {compose_file} down"
            returncode, stdout, stderr = await self.run_remote_command(host_info, stop_cmd)
            
            if returncode != 0:
                logger.error(f"Failed to stop stack: {stderr}")
                return False
            
            logger.info(f"Successfully stopped stack in {stack_path}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to stop remote stack: {e}")
            return False 