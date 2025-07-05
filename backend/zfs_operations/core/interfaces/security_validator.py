from abc import ABC, abstractmethod
from typing import List, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from ..value_objects.ssh_config import SSHConfig


class ISecurityValidator(ABC):
    """Interface for security validation operations"""
    
    @abstractmethod
    def validate_dataset_name(self, name: str) -> str:
        """Validate and sanitize dataset name"""
        pass
    
    @abstractmethod
    def validate_zfs_command(self, command: str, args: List[str]) -> List[str]:
        """Validate ZFS command and arguments"""
        pass
    
    @abstractmethod
    def validate_ssh_config(self, config: 'SSHConfig') -> 'SSHConfig':
        """Validate SSH configuration"""
        pass
    
    @abstractmethod
    def validate_hostname(self, hostname: str) -> str:
        """Validate and sanitize hostname"""
        pass
    
    @abstractmethod
    def validate_username(self, username: str) -> str:
        """Validate and sanitize username"""
        pass
    
    @abstractmethod
    def validate_port(self, port: int) -> int:
        """Validate port number"""
        pass
    
    @abstractmethod
    def validate_path(self, path: str) -> str:
        """Validate and sanitize file path"""
        pass
    
    @abstractmethod
    def validate_snapshot_name(self, snapshot_name: str) -> str:
        """Validate and sanitize snapshot name"""
        pass
    
    @abstractmethod
    def escape_shell_argument(self, arg: str) -> str:
        """Escape shell argument to prevent injection"""
        pass
    
    @abstractmethod
    def validate_zfs_properties(self, properties: Dict[str, str]) -> Dict[str, str]:
        """Validate multiple ZFS properties"""
        pass
    
    @abstractmethod
    def validate_pool_name(self, pool_name: str) -> str:
        """Validate and sanitize pool name"""
        pass 