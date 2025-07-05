"""
Logger interface for structured logging abstraction.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class ILogger(ABC):
    """Interface for structured logging operations."""
    
    @abstractmethod
    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log debug message with optional extra context."""
        pass
    
    @abstractmethod
    def info(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log info message with optional extra context."""
        pass
    
    @abstractmethod
    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log warning message with optional extra context."""
        pass
    
    @abstractmethod
    def error(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log error message with optional extra context."""
        pass
    
    @abstractmethod
    def critical(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log critical message with optional extra context."""
        pass
    
    @abstractmethod
    def exception(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log exception with traceback."""
        pass 