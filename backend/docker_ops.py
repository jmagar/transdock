import os
import yaml
import logging
import re
from typing import List, Dict, Optional, Tuple
import asyncio
from pathlib import Path
from models import VolumeMount

logger = logging.getLogger(__name__)

class DockerOperations:
    def __init__(self):
        self.compose_base_path = "/mnt/cache/compose"
        self.appdata_base_path = "/mnt/cache/appdata"
    
    async def run_command(self, cmd: List[str], cwd: Optional[str] = None) -> Tuple[int, str, str]:
        """Run a command asynchronously"""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            stdout, stderr = await process.communicate()
            return process.returncode, stdout.decode(), stderr.decode()
        except Exception as e:
            logger.error(f"Command failed: {' '.join(cmd)} - {e}")
            return 1, "", str(e)
    
    def get_compose_path(self, dataset_name: str) -> str:
        """Get the full path to a compose dataset"""
        if dataset_name.startswith("/"):
            return dataset_name
        elif dataset_name.startswith("cache/"):
            return f"/mnt/{dataset_name}"
        else:
            return f"{self.compose_base_path}/{dataset_name}"
    
    async def find_compose_file(self, compose_dir: str) -> Optional[str]:
        """Find docker-compose.yml or docker-compose.yaml in directory"""
        possible_files = [
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml"
        ]
        
        for filename in possible_files:
            filepath = os.path.join(compose_dir, filename)
            if os.path.exists(filepath):
                return filepath
        
        return None
    
    async def parse_compose_file(self, compose_file_path: str) -> Dict:
        """Parse docker-compose file and return the configuration"""
        try:
            with open(compose_file_path, 'r') as file:
                compose_data = yaml.safe_load(file)
            return compose_data
        except Exception as e:
            logger.error(f"Failed to parse compose file {compose_file_path}: {e}")
            raise
    
    async def extract_volume_mounts(self, compose_data: Dict) -> List[VolumeMount]:
        """Extract volume mounts from compose data"""
        volume_mounts = []
        
        services = compose_data.get('services', {})
        
        for service_name, service_config in services.items():
            volumes = service_config.get('volumes', [])
            
            for volume in volumes:
                if isinstance(volume, str):
                    # Handle string format: "host_path:container_path"
                    if ':' in volume:
                        parts = volume.split(':')
                        if len(parts) >= 2:
                            host_path = parts[0]
                            container_path = parts[1]
                            
                            # Skip bind mounts that aren't in our data directories
                            if host_path.startswith('/') and (
                                host_path.startswith('/mnt/cache/appdata/') or
                                host_path.startswith('/mnt/cache/compose/')
                            ):
                                mount = VolumeMount(
                                    source=host_path,
                                    target=container_path
                                )
                                volume_mounts.append(mount)
                
                elif isinstance(volume, dict):
                    # Handle dictionary format
                    source = volume.get('source', '')
                    target = volume.get('target', '')
                    
                    if source.startswith('/') and (
                        source.startswith('/mnt/cache/appdata/') or
                        source.startswith('/mnt/cache/compose/')
                    ):
                        mount = VolumeMount(
                            source=source,
                            target=target
                        )
                        volume_mounts.append(mount)
        
        # Remove duplicates
        unique_mounts = []
        seen_sources = set()
        for mount in volume_mounts:
            if mount.source not in seen_sources:
                unique_mounts.append(mount)
                seen_sources.add(mount.source)
        
        return unique_mounts
    
    async def stop_compose_stack(self, compose_dir: str) -> bool:
        """Stop a docker compose stack"""
        compose_file = await self.find_compose_file(compose_dir)
        if not compose_file:
            logger.error(f"No compose file found in {compose_dir}")
            return False
        
        logger.info(f"Stopping compose stack in {compose_dir}")
        
        cmd = ["docker-compose", "-f", compose_file, "down"]
        returncode, stdout, stderr = await self.run_command(cmd, cwd=compose_dir)
        
        if returncode != 0:
            logger.error(f"Failed to stop compose stack: {stderr}")
            return False
        
        logger.info(f"Successfully stopped compose stack in {compose_dir}")
        return True
    
    async def start_compose_stack(self, compose_dir: str) -> bool:
        """Start a docker compose stack"""
        compose_file = await self.find_compose_file(compose_dir)
        if not compose_file:
            logger.error(f"No compose file found in {compose_dir}")
            return False
        
        logger.info(f"Starting compose stack in {compose_dir}")
        
        cmd = ["docker-compose", "-f", compose_file, "up", "-d"]
        returncode, stdout, stderr = await self.run_command(cmd, cwd=compose_dir)
        
        if returncode != 0:
            logger.error(f"Failed to start compose stack: {stderr}")
            return False
        
        logger.info(f"Successfully started compose stack in {compose_dir}")
        return True
    
    async def update_compose_file_paths(self, compose_file_path: str, volume_mapping: Dict[str, str]) -> bool:
        """Update volume paths in compose file"""
        try:
            # Read the original file
            with open(compose_file_path, 'r') as file:
                content = file.read()
            
            # Create a backup
            backup_path = f"{compose_file_path}.transdock.backup"
            with open(backup_path, 'w') as file:
                file.write(content)
            
            # Update the paths
            updated_content = content
            for old_path, new_path in volume_mapping.items():
                # Use regex to replace paths more accurately
                pattern = re.escape(old_path)
                updated_content = re.sub(pattern, new_path, updated_content)
            
            # Write the updated file
            with open(compose_file_path, 'w') as file:
                file.write(updated_content)
            
            logger.info(f"Updated compose file paths in {compose_file_path}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to update compose file {compose_file_path}: {e}")
            return False
    
    async def create_target_compose_dir(self, target_host: str, target_path: str, 
                                       ssh_user: str = "root", ssh_port: int = 22) -> bool:
        """Create the target compose directory on remote host"""
        cmd = [
            "ssh", "-p", str(ssh_port), f"{ssh_user}@{target_host}",
            f"mkdir -p {target_path}"
        ]
        
        returncode, _, stderr = await self.run_command(cmd)
        if returncode != 0:
            logger.error(f"Failed to create target directory {target_path}: {stderr}")
            return False
        
        return True
    
    async def copy_compose_files(self, source_dir: str, target_host: str, target_dir: str,
                                ssh_user: str = "root", ssh_port: int = 22) -> bool:
        """Copy compose files to target host"""
        cmd = [
            "rsync", "-avz", "-e", f"ssh -p {ssh_port}",
            f"{source_dir}/", f"{ssh_user}@{target_host}:{target_dir}/"
        ]
        
        returncode, stdout, stderr = await self.run_command(cmd)
        if returncode != 0:
            logger.error(f"Failed to copy compose files: {stderr}")
            return False
        
        logger.info(f"Successfully copied compose files from {source_dir} to {target_host}:{target_dir}")
        return True
    
    async def validate_compose_file(self, compose_file_path: str) -> bool:
        """Validate that a compose file is syntactically correct"""
        try:
            with open(compose_file_path, 'r') as file:
                yaml.safe_load(file)
            return True
        except Exception as e:
            logger.error(f"Compose file validation failed for {compose_file_path}: {e}")
            return False 