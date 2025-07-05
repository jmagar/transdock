from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SSHConfig:
    """SSH configuration value object"""
    host: str
    user: str = "root"
    port: int = 22
    key_file: Optional[str] = None
    timeout: int = 30
    
    def __post_init__(self):
        if not self.host:
            raise ValueError("Host cannot be empty")
        if not (1 <= self.port <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        if self.timeout <= 0:
            raise ValueError("Timeout must be positive")
        if not self.user:
            raise ValueError("User cannot be empty")
    
    @property
    def connection_string(self) -> str:
        """Get connection string for SSH"""
        return f"{self.user}@{self.host}:{self.port}"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'host': self.host,
            'user': self.user,
            'port': self.port,
            'key_file': self.key_file,
            'timeout': self.timeout
        } 