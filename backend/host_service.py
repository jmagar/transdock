import logging
import os
import yaml
import json
import asyncio
from typing import List, Dict, Optional, Tuple
from .models import HostInfo, HostCapabilities, RemoteStack, StackAnalysis, VolumeMount, StorageInfo, StorageValidationResult, MigrationStorageRequirement
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
            
            # Get storage information for discovered paths
            all_paths = list(set(capabilities.compose_paths + capabilities.appdata_paths))
            if not all_paths:
                # Add some common paths if none were discovered
                all_paths = ["/mnt/cache", "/mnt/user", "/opt", "/home"]
            
            capabilities.storage_info = await self.get_storage_info(host_info, all_paths)
            
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
            
            # Calculate storage requirement
            storage_requirement = await self.estimate_migration_storage_requirement(
                host_info, volumes, include_zfs_overhead=zfs_compatible
            )
            
            return StackAnalysis(
                name=os.path.basename(stack_path),
                path=stack_path,
                compose_file=compose_file,
                services=services,
                volumes=volumes,
                networks=networks,
                external_volumes=external_volumes,
                zfs_compatible=zfs_compatible,
                estimated_size=estimated_size,
                storage_requirement=storage_requirement
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
    
    async def get_storage_info(self, host_info: HostInfo, paths: List[str]) -> List[StorageInfo]:
        """Get storage information for specified paths on a remote host"""
        storage_info = []
        
        for path in paths:
            try:
                # Validate and sanitize path
                safe_path = SecurityUtils.sanitize_path(path, allow_absolute=True)
                
                # Get filesystem information using df
                df_cmd = f"df -B1 {SecurityUtils.escape_shell_argument(safe_path)} 2>/dev/null || echo 'error'"
                returncode, stdout, stderr = await self.run_remote_command(host_info, df_cmd)
                
                if returncode == 0 and 'error' not in stdout:
                    lines = stdout.strip().split('\n')
                    if len(lines) >= 2:
                        # Parse df output (filesystem, total, used, available, use%, mount)
                        fields = lines[1].split()
                        if len(fields) >= 6:
                            filesystem = fields[0]
                            total_bytes = int(fields[1])
                            used_bytes = int(fields[2])
                            available_bytes = int(fields[3])
                            mount_point = fields[5] if len(fields) > 5 else safe_path
                            
                            storage_info.append(StorageInfo(
                                path=safe_path,
                                total_bytes=total_bytes,
                                used_bytes=used_bytes,
                                available_bytes=available_bytes,
                                filesystem=filesystem,
                                mount_point=mount_point
                            ))
                            
                            from .utils import format_bytes
                            logger.info(f"Storage info for {safe_path}: {format_bytes(available_bytes)} available")
                
            except Exception as e:
                logger.error(f"Failed to get storage info for {path}: {e}")
                continue
        
        return storage_info
    
    async def check_storage_availability(self, host_info: HostInfo, target_path: str, required_bytes: int) -> StorageValidationResult:
        """Check if target path has enough storage space for migration"""
        try:
            # Validate inputs
            safe_path = SecurityUtils.sanitize_path(target_path, allow_absolute=True)
            
            if required_bytes < 0:
                return StorageValidationResult(
                    is_valid=False,
                    required_bytes=required_bytes,
                    available_bytes=0,
                    storage_path=safe_path,
                    error_message="Required bytes cannot be negative"
                )
            
            # Get storage info for target path
            storage_info_list = await self.get_storage_info(host_info, [safe_path])
            
            if not storage_info_list:
                return StorageValidationResult(
                    is_valid=False,
                    required_bytes=required_bytes,
                    available_bytes=0,
                    storage_path=safe_path,
                    error_message=f"Unable to get storage information for {safe_path}"
                )
            
            storage_info = storage_info_list[0]
            available_bytes = storage_info.available_bytes
            
            # Calculate safety margin (20% extra space)
            safety_margin_bytes = int(required_bytes * 0.2)
            total_required = required_bytes + safety_margin_bytes
            
            is_valid = available_bytes >= total_required
            
            result = StorageValidationResult(
                is_valid=is_valid,
                required_bytes=required_bytes,
                available_bytes=available_bytes,
                storage_path=safe_path,
                safety_margin_bytes=safety_margin_bytes
            )
            
            if not is_valid:
                from .utils import format_bytes
                shortage = total_required - available_bytes
                result.error_message = f"Insufficient storage space. Need {format_bytes(total_required)} ({format_bytes(required_bytes)} + {format_bytes(safety_margin_bytes)} safety margin), but only {format_bytes(available_bytes)} available. Shortage: {format_bytes(shortage)}"
            elif available_bytes < required_bytes * 1.5:
                # Warning if less than 50% extra space
                from .utils import format_bytes
                result.warning_message = f"Low storage space warning. Only {format_bytes(available_bytes)} available for {format_bytes(required_bytes)} required"
            
            from .utils import format_bytes
            logger.info(f"Storage validation for {safe_path}: {'✅ PASS' if is_valid else '❌ FAIL'} - {format_bytes(available_bytes)} available, {format_bytes(total_required)} required")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to check storage availability: {e}")
            return StorageValidationResult(
                is_valid=False,
                required_bytes=required_bytes,
                available_bytes=0,
                storage_path=target_path,
                error_message=f"Storage validation failed: {e}"
            )
    
    async def estimate_migration_storage_requirement(self, host_info: HostInfo, volumes: List[VolumeMount], 
                                                    include_zfs_overhead: bool = True) -> MigrationStorageRequirement:
        """Estimate storage requirements for a migration"""
        try:
            # Calculate total source size
            source_size_bytes = 0
            
            for volume in volumes:
                if os.path.isabs(volume.source):
                    # Get directory size using du
                    du_cmd = f"du -sb {SecurityUtils.escape_shell_argument(volume.source)} 2>/dev/null || echo '0 {volume.source}'"
                    returncode, stdout, stderr = await self.run_remote_command(host_info, du_cmd)
                    
                    if returncode == 0:
                        try:
                            size_str = stdout.split()[0]
                            size = int(size_str)
                            source_size_bytes += size
                            from .utils import format_bytes
                            logger.info(f"Volume {volume.source}: {format_bytes(size)}")
                        except (ValueError, IndexError):
                            logger.warning(f"Could not parse size for {volume.source}")
                            continue
            
            # Estimate transfer size (same as source for full copy)
            estimated_transfer_size_bytes = source_size_bytes
            
            # Calculate ZFS snapshot overhead if applicable
            zfs_snapshot_overhead_bytes = 0
            if include_zfs_overhead:
                # ZFS snapshots typically add 10-20% overhead for metadata
                zfs_snapshot_overhead_bytes = int(source_size_bytes * 0.15)
            
            # Use the first volume's target path as base (will be adjusted by caller)
            target_path = volumes[0].target if volumes else "/tmp"
            
            requirement = MigrationStorageRequirement(
                source_size_bytes=source_size_bytes,
                target_path=target_path,
                estimated_transfer_size_bytes=estimated_transfer_size_bytes,
                zfs_snapshot_overhead_bytes=zfs_snapshot_overhead_bytes
            )
            
            total_required = (estimated_transfer_size_bytes + 
                            zfs_snapshot_overhead_bytes)
            
            from .utils import format_bytes
            logger.info(f"Migration storage requirement: {format_bytes(total_required)} total "
                       f"({format_bytes(source_size_bytes)} source + {format_bytes(zfs_snapshot_overhead_bytes)} ZFS overhead)")
            
            return requirement
            
        except Exception as e:
            logger.error(f"Failed to estimate migration storage requirement: {e}")
            return MigrationStorageRequirement(
                source_size_bytes=0,
                target_path="/tmp",
                estimated_transfer_size_bytes=0,
                zfs_snapshot_overhead_bytes=0
            )
    
    async def validate_migration_storage(self, source_host_info: HostInfo, target_host_info: HostInfo,
                                        volumes: List[VolumeMount], target_base_path: str,
                                        use_zfs: bool = False) -> Dict[str, StorageValidationResult]:
        """Validate storage requirements for a complete migration"""
        results = {}
        
        try:
            # Get storage requirements
            storage_requirement = await self.estimate_migration_storage_requirement(
                source_host_info, volumes, include_zfs_overhead=use_zfs
            )
            
            # Check target storage
            total_required_bytes = (storage_requirement.estimated_transfer_size_bytes + 
                                  storage_requirement.zfs_snapshot_overhead_bytes)
            
            target_validation = await self.check_storage_availability(
                target_host_info, target_base_path, total_required_bytes
            )
            
            results["target"] = target_validation
            
            # Check source storage for ZFS snapshots if needed
            if use_zfs and storage_requirement.zfs_snapshot_overhead_bytes > 0:
                # Find source base path (use first volume's source path)
                source_path = "/"
                if volumes:
                    source_path = os.path.dirname(volumes[0].source)
                
                source_validation = await self.check_storage_availability(
                    source_host_info, source_path, storage_requirement.zfs_snapshot_overhead_bytes
                )
                
                results["source"] = source_validation
            
            # Log overall validation result
            overall_valid = all(result.is_valid for result in results.values())
            logger.info(f"Migration storage validation: {'✅ PASS' if overall_valid else '❌ FAIL'}")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to validate migration storage: {e}")
            return {
                "error": StorageValidationResult(
                    is_valid=False,
                    required_bytes=0,
                    available_bytes=0,
                    storage_path=target_base_path,
                    error_message=f"Storage validation failed: {e}"
                )
            }