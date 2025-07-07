"""Docker management application service"""

from typing import List, Optional, Dict, Any
from ...core.entities.docker_entity import DockerContainer, DockerImage, DockerNetwork, DockerComposeStack
from ...core.interfaces.docker_repository import (
    DockerContainerRepository, DockerImageRepository, DockerNetworkRepository,
    DockerComposeRepository, DockerVolumeRepository, DockerHostRepository
)
from ...core.exceptions.docker_exceptions import DockerOperationError, DockerContainerNotFoundError
import logging

logger = logging.getLogger(__name__)


class DockerManagementService:
    """Application service for managing Docker resources"""
    
    def __init__(
        self,
        container_repository: DockerContainerRepository,
        image_repository: DockerImageRepository,
        network_repository: DockerNetworkRepository,
        compose_repository: DockerComposeRepository,
        volume_repository: DockerVolumeRepository,
        host_repository: DockerHostRepository
    ):
        self._container_repository = container_repository
        self._image_repository = image_repository
        self._network_repository = network_repository
        self._compose_repository = compose_repository
        self._volume_repository = volume_repository
        self._host_repository = host_repository
    
    # Container Management
    async def get_container(self, container_name: str) -> Optional[DockerContainer]:
        """Get a container by name"""
        try:
            return await self._container_repository.find_by_name(container_name)
        except Exception as e:
            logger.error(f"Failed to get container {container_name}: {e}")
            return None
    
    async def list_containers(self, running_only: bool = False) -> List[DockerContainer]:
        """List containers"""
        try:
            if running_only:
                return await self._container_repository.list_running()
            return await self._container_repository.list_all()
        except Exception as e:
            logger.error(f"Failed to list containers: {e}")
            return []
    
    async def start_container(self, container_name: str) -> bool:
        """Start a container"""
        try:
            container = await self._container_repository.find_by_name(container_name)
            if not container:
                raise DockerContainerNotFoundError(f"Container {container_name} not found")
            
            success = await self._container_repository.start(container.id)
            
            if success:
                logger.info(f"Started container: {container_name}")
            
            return success
            
        except (DockerOperationError, DockerContainerNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to start container {container_name}: {e}")
            raise DockerOperationError(f"Failed to start container {container_name}: {e}")
    
    async def stop_container(self, container_name: str, timeout: int = 10) -> bool:
        """Stop a container"""
        try:
            container = await self._container_repository.find_by_name(container_name)
            if not container:
                raise DockerContainerNotFoundError(f"Container {container_name} not found")
            
            success = await self._container_repository.stop(container.id, timeout)
            
            if success:
                logger.info(f"Stopped container: {container_name}")
            
            return success
            
        except (DockerOperationError, DockerContainerNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to stop container {container_name}: {e}")
            raise DockerOperationError(f"Failed to stop container {container_name}: {e}")
    
    async def get_container_logs(self, container_name: str, tail: int = 100) -> str:
        """Get container logs"""
        try:
            container = await self._container_repository.find_by_name(container_name)
            if not container:
                raise DockerContainerNotFoundError(f"Container {container_name} not found")
            
            return await self._container_repository.get_logs(container.id, tail)
            
        except (DockerOperationError, DockerContainerNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to get logs for container {container_name}: {e}")
            raise DockerOperationError(f"Failed to get logs for container {container_name}: {e}")
    
    async def get_container_stats(self, container_name: str) -> Dict[str, Any]:
        """Get container statistics"""
        try:
            container = await self._container_repository.find_by_name(container_name)
            if not container:
                raise DockerContainerNotFoundError(f"Container {container_name} not found")
            
            return await self._container_repository.get_stats(container.id)
            
        except (DockerOperationError, DockerContainerNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to get stats for container {container_name}: {e}")
            raise DockerOperationError(f"Failed to get stats for container {container_name}: {e}")
    
    # Compose Stack Management
    async def get_compose_stack(self, stack_name: str) -> Optional[DockerComposeStack]:
        """Get a compose stack by name"""
        try:
            return await self._compose_repository.find_stack_by_name(stack_name)
        except Exception as e:
            logger.error(f"Failed to get compose stack {stack_name}: {e}")
            return None
    
    async def get_compose_stack_by_path(self, compose_file_path: str) -> Optional[DockerComposeStack]:
        """Get a compose stack by file path"""
        try:
            return await self._compose_repository.find_stack_by_path(compose_file_path)
        except Exception as e:
            logger.error(f"Failed to get compose stack at {compose_file_path}: {e}")
            return None
    
    async def list_compose_stacks(self) -> List[DockerComposeStack]:
        """List all compose stacks"""
        try:
            return await self._compose_repository.list_all_stacks()
        except Exception as e:
            logger.error(f"Failed to list compose stacks: {e}")
            return []
    
    async def start_compose_stack(self, compose_file_path: str, project_name: Optional[str] = None) -> bool:
        """Start a compose stack"""
        try:
            # Validate compose file first
            validation_result = await self._compose_repository.validate_compose_file(compose_file_path)
            if not validation_result.get('valid', False):
                raise DockerOperationError(f"Invalid compose file: {validation_result.get('error', 'Unknown error')}")
            
            success = await self._compose_repository.start_stack(compose_file_path, project_name)
            
            if success:
                logger.info(f"Started compose stack: {compose_file_path}")
            
            return success
            
        except DockerOperationError:
            raise
        except Exception as e:
            logger.error(f"Failed to start compose stack {compose_file_path}: {e}")
            raise DockerOperationError(f"Failed to start compose stack {compose_file_path}: {e}")
    
    async def stop_compose_stack(self, compose_file_path: str, project_name: Optional[str] = None) -> bool:
        """Stop a compose stack"""
        try:
            success = await self._compose_repository.stop_stack(compose_file_path, project_name)
            
            if success:
                logger.info(f"Stopped compose stack: {compose_file_path}")
            
            return success
            
        except DockerOperationError:
            raise
        except Exception as e:
            logger.error(f"Failed to stop compose stack {compose_file_path}: {e}")
            raise DockerOperationError(f"Failed to stop compose stack {compose_file_path}: {e}")
    
    async def get_compose_stack_status(self, compose_file_path: str, project_name: Optional[str] = None) -> Dict[str, Any]:
        """Get compose stack status"""
        try:
            return await self._compose_repository.get_stack_status(compose_file_path, project_name)
        except Exception as e:
            logger.error(f"Failed to get compose stack status for {compose_file_path}: {e}")
            raise DockerOperationError(f"Failed to get compose stack status for {compose_file_path}: {e}")
    
    # Image Management
    async def list_images(self) -> List[DockerImage]:
        """List all images"""
        try:
            return await self._image_repository.list_all()
        except Exception as e:
            logger.error(f"Failed to list images: {e}")
            return []
    
    async def pull_image(self, image_tag: str) -> bool:
        """Pull an image"""
        try:
            success = await self._image_repository.pull(image_tag)
            
            if success:
                logger.info(f"Pulled image: {image_tag}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to pull image {image_tag}: {e}")
            raise DockerOperationError(f"Failed to pull image {image_tag}: {e}")
    
    # Network Management
    async def list_networks(self) -> List[DockerNetwork]:
        """List all networks"""
        try:
            return await self._network_repository.list_all()
        except Exception as e:
            logger.error(f"Failed to list networks: {e}")
            return []
    
    # Volume Management
    async def list_volumes(self) -> List[Dict[str, Any]]:
        """List all volumes"""
        try:
            return await self._volume_repository.list_all()
        except Exception as e:
            logger.error(f"Failed to list volumes: {e}")
            return []
    
    # Host Management
    async def get_docker_info(self) -> Dict[str, Any]:
        """Get Docker system information"""
        try:
            return await self._host_repository.get_system_info()
        except Exception as e:
            logger.error(f"Failed to get Docker info: {e}")
            raise DockerOperationError(f"Failed to get Docker info: {e}")
    
    async def get_docker_version(self) -> Dict[str, Any]:
        """Get Docker version information"""
        try:
            return await self._host_repository.get_version()
        except Exception as e:
            logger.error(f"Failed to get Docker version: {e}")
            raise DockerOperationError(f"Failed to get Docker version: {e}")
    
    async def ping_docker(self) -> bool:
        """Ping Docker daemon"""
        try:
            return await self._host_repository.ping()
        except Exception as e:
            logger.error(f"Failed to ping Docker daemon: {e}")
            return False
    
    # Analysis Methods
    async def analyze_compose_stack(self, compose_file_path: str) -> Dict[str, Any]:
        """Analyze a compose stack for migration readiness"""
        try:
            stack = await self._compose_repository.find_stack_by_path(compose_file_path)
            if not stack:
                raise DockerOperationError(f"Compose stack not found: {compose_file_path}")
            
            # Get ZFS mount points for compatibility check
            zfs_mount_points = []  # This would be populated from ZFS service
            
            analysis = {
                'stack_name': stack.name,
                'compose_file_path': compose_file_path,
                'project_directory': stack.project_directory,
                'container_count': len(stack.containers),
                'running_containers': len(stack.running_containers),
                'data_directories': stack.get_all_data_directories(),
                'external_volumes': stack.get_external_volumes(),
                'networks': [n.name for n in stack.networks],
                'complexity': stack.estimate_migration_complexity(),
                'zfs_compatible': stack.is_zfs_compatible(zfs_mount_points),
                'migration_summary': stack.get_migration_summary()
            }
            
            # Add recommendations
            recommendations = []
            
            if not stack.is_zfs_compatible(zfs_mount_points):
                recommendations.append({
                    'type': 'warning',
                    'message': 'Some data directories are not on ZFS-compatible paths'
                })
            
            if stack.get_external_volumes():
                recommendations.append({
                    'type': 'info',
                    'message': 'Stack uses external volumes that may need special handling'
                })
            
            if stack.estimate_migration_complexity() == 'complex':
                recommendations.append({
                    'type': 'warning',
                    'message': 'Complex migration - consider breaking down into smaller parts'
                })
            
            analysis['recommendations'] = recommendations
            
            return analysis
            
        except DockerOperationError:
            raise
        except Exception as e:
            logger.error(f"Failed to analyze compose stack {compose_file_path}: {e}")
            raise DockerOperationError(f"Failed to analyze compose stack {compose_file_path}: {e}")
    
    async def get_migration_candidates(self) -> List[Dict[str, Any]]:
        """Get containers/stacks that are candidates for migration"""
        try:
            stacks = await self._compose_repository.list_all_stacks()
            candidates = []
            
            for stack in stacks:
                if stack.is_running():
                    candidate = {
                        'type': 'compose_stack',
                        'name': stack.name,
                        'compose_file_path': stack.compose_file_path,
                        'containers': len(stack.containers),
                        'running_containers': len(stack.running_containers),
                        'data_directories': len(stack.get_all_data_directories()),
                        'complexity': stack.estimate_migration_complexity(),
                        'migration_summary': stack.get_migration_summary()
                    }
                    candidates.append(candidate)
            
            # Sort by complexity and container count
            candidates.sort(key=lambda x: (x['complexity'], x['containers']))
            
            return candidates
            
        except Exception as e:
            logger.error(f"Failed to get migration candidates: {e}")
            raise DockerOperationError(f"Failed to get migration candidates: {e}")
    
    async def validate_migration_prerequisites(self, compose_file_path: str) -> Dict[str, Any]:
        """Validate prerequisites for migration"""
        try:
            # Check if compose file exists and is valid
            validation_result = await self._compose_repository.validate_compose_file(compose_file_path)
            if not validation_result.get('valid', False):
                return {
                    'valid': False,
                    'error': f"Invalid compose file: {validation_result.get('error', 'Unknown error')}"
                }
            
            # Check if stack is running
            stack = await self._compose_repository.find_stack_by_path(compose_file_path)
            if not stack:
                return {
                    'valid': False,
                    'error': 'Compose stack not found'
                }
            
            # Check Docker daemon connectivity
            docker_ping = await self._host_repository.ping()
            if not docker_ping:
                return {
                    'valid': False,
                    'error': 'Cannot connect to Docker daemon'
                }
            
            # Check data directories
            data_dirs = stack.get_all_data_directories()
            missing_dirs = []
            for data_dir in data_dirs:
                # This would check if directories exist and are accessible
                # For now, we'll assume they exist
                pass
            
            if missing_dirs:
                return {
                    'valid': False,
                    'error': f"Missing data directories: {', '.join(missing_dirs)}"
                }
            
            return {
                'valid': True,
                'stack_name': stack.name,
                'container_count': len(stack.containers),
                'running_containers': len(stack.running_containers),
                'data_directories': data_dirs,
                'external_volumes': stack.get_external_volumes(),
                'complexity': stack.estimate_migration_complexity()
            }
            
        except Exception as e:
            logger.error(f"Failed to validate migration prerequisites for {compose_file_path}: {e}")
            return {
                'valid': False,
                'error': f"Validation failed: {str(e)}"
            }