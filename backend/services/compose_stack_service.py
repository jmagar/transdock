import os
import logging
from typing import List, Dict, Any
from ..docker_ops import DockerOperations
from ..zfs_ops import ZFSOperations
from ..security_utils import SecurityUtils, SecurityValidationError

logger = logging.getLogger(__name__)


class ComposeStackService:
    """Handles legacy Docker Compose stack operations for backward compatibility"""
    
    def __init__(self, docker_ops: DockerOperations, zfs_ops: ZFSOperations):
        self.docker_ops = docker_ops
        self.zfs_ops = zfs_ops
        self.compose_base_path = os.getenv("TRANSDOCK_COMPOSE_BASE", "/mnt/cache/compose")
    
    def _is_valid_stack_name(self, name: str) -> bool:
        """Validate stack name for security."""
        if not name or len(name) > 64:
            return False
        return str(name).replace('-', '').replace('_', '').replace('.', '').isalnum()
    
    async def get_compose_stacks(self) -> List[Dict[str, str]]:
        """Get list of available Docker Compose stacks"""
        try:
            stacks = []
            
            # Validate base path for security
            validated_base = SecurityUtils.sanitize_path(
                self.compose_base_path, allow_absolute=True)

            if os.path.exists(validated_base):
                for item in os.listdir(validated_base):
                    # Validate each stack name
                    try:
                        if not self._is_valid_stack_name(item):
                            continue

                        stack_path = SecurityUtils.sanitize_path(os.path.join(
                            validated_base, item), validated_base, allow_absolute=True)

                        if os.path.isdir(stack_path):
                            # Look for common compose file names
                            compose_file = None
                            for filename in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
                                candidate = os.path.join(stack_path, filename)
                                if os.path.isfile(candidate):
                                    compose_file = candidate
                                    break
                            
                            if compose_file:
                                stacks.append({
                                    "name": item,
                                    "compose_file": compose_file
                                })
                    except SecurityValidationError:
                        # Skip invalid stack names silently
                        continue

            return stacks
        except Exception as e:
            logger.error(f"Failed to get compose stacks: {e}")
            return []
    
    async def get_stack_info(self, stack_name: str) -> Dict[str, Any]:
        """Get detailed information about a specific compose stack"""
        # Validate stack name for security
        if not stack_name or len(stack_name) > 64:
            raise ValueError("Invalid stack name length")
        if not str(stack_name).replace('-', '').replace('_', '').replace('.', '').isalnum():
            raise ValueError("Stack name contains invalid characters")

        compose_base = SecurityUtils.sanitize_path(
            self.compose_base_path, allow_absolute=True)
        stack_path = SecurityUtils.sanitize_path(
            os.path.join(compose_base, stack_name),
            compose_base,
            allow_absolute=True)

        if not os.path.exists(stack_path):
            raise FileNotFoundError("Compose stack not found")

        # Look for common compose file names
        compose_file = None
        for filename in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
            candidate = os.path.join(stack_path, filename)
            if os.path.isfile(candidate):
                compose_file = candidate
                break
        
        if not compose_file:
            raise FileNotFoundError("No compose file found in stack")

        # Note: Legacy compose parsing is deprecated
        # Use container discovery instead for modern operations
        return {
            "name": stack_name,
            "compose_file": compose_file,
            "volumes": [],  # Deprecated - use container discovery
            "services": [],  # Deprecated - use container discovery
            "note": "Legacy compose parsing deprecated. Use container discovery endpoints instead."
        }
    
    async def validate_stack_exists(self, stack_name: str) -> bool:
        """Check if a compose stack exists"""
        try:
            await self.get_stack_info(stack_name)
            return True
        except (FileNotFoundError, ValueError):
            return False
    
    async def get_stack_path(self, stack_name: str) -> str:
        """Get the full path to a compose stack directory"""
        if not self._is_valid_stack_name(stack_name):
            raise ValueError("Invalid stack name")
        
        compose_base = SecurityUtils.sanitize_path(
            self.compose_base_path, allow_absolute=True)
        stack_path = SecurityUtils.sanitize_path(
            os.path.join(compose_base, stack_name),
            compose_base,
            allow_absolute=True)
        
        return stack_path
    
    def get_compose_base_path(self) -> str:
        """Get the base path for compose stacks"""
        return self.compose_base_path
    
    async def list_stack_services(self, stack_name: str) -> List[str]:
        """Get list of services in a compose stack"""
        try:
            stack_info = await self.get_stack_info(stack_name)
            return stack_info["services"]
        except Exception as e:
            logger.error(f"Failed to list services for stack {stack_name}: {e}")
            return []
    
    async def get_stack_volumes(self, stack_name: str) -> List[Dict[str, Any]]:
        """Get volume information for a compose stack"""
        try:
            stack_info = await self.get_stack_info(stack_name)
            return stack_info["volumes"]
        except Exception as e:
            logger.error(f"Failed to get volumes for stack {stack_name}: {e}")
            return []