from abc import ABC, abstractmethod
from typing import List, Optional


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
    def escape_shell_argument(self, arg: str) -> str:
        """Escape shell argument to prevent injection"""
        pass 