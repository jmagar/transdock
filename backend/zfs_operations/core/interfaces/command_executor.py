from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class CommandResult:
    """Result of a command execution"""
    returncode: int
    stdout: str
    stderr: str
    success: Optional[bool] = None
    
    def __post_init__(self):
        if self.success is None:
            self.success = self.returncode == 0


class ICommandExecutor(ABC):
    """Interface for command execution with validation"""
    
    @abstractmethod
    async def execute_zfs(self, command: str, *args: str) -> CommandResult:
        """Execute ZFS command with validation"""
        pass

    @abstractmethod
    async def execute_system(self, command: str, *args: str) -> CommandResult:
        """Execute system command with validation"""
        pass

    @abstractmethod
    async def execute_remote(self, host: str, command: List[str], 
                           ssh_config: Optional['SSHConfig'] = None) -> CommandResult:
        """Execute command on remote host"""
        pass 