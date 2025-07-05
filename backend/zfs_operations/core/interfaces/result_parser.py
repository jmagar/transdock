from abc import ABC, abstractmethod
from typing import Dict, Any


class IResultParser(ABC):
    """Interface for parsing command results"""
    
    @abstractmethod
    def can_parse(self, command_type: str) -> bool:
        """Check if this parser can handle the given command type"""
        pass
    
    @abstractmethod
    def parse(self, raw_output: str) -> Dict[str, Any]:
        """Parse raw command output into structured data"""
        pass


class ILogger(ABC):
    """Interface for logging operations"""
    
    @abstractmethod
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message"""
        pass
    
    @abstractmethod
    def info(self, message: str, **kwargs) -> None:
        """Log info message"""
        pass
    
    @abstractmethod
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message"""
        pass
    
    @abstractmethod
    def error(self, message: str, **kwargs) -> None:
        """Log error message"""
        pass
    
    @abstractmethod
    def critical(self, message: str, **kwargs) -> None:
        """Log critical message"""
        pass 