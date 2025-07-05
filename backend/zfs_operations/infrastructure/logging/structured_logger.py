"""
Structured logger implementation for ZFS operations.
"""
import json
import logging
import sys
import threading
from typing import Dict, Any, Optional
from datetime import datetime
from ...core.interfaces.logger_interface import ILogger


class StructuredLogger(ILogger):
    """Structured logger implementation with JSON formatting and context support."""
    
    def __init__(self, name: str = "zfs_operations", level: str = "INFO"):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        
        # Create formatter
        formatter = StructuredFormatter()
        
        # Console handler
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        # Prevent duplicate logs
        self.logger.propagate = False
    
    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log debug message with optional extra context."""
        self._log(logging.DEBUG, message, extra)
    
    def info(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log info message with optional extra context."""
        self._log(logging.INFO, message, extra)
    
    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log warning message with optional extra context."""
        self._log(logging.WARNING, message, extra)
    
    def error(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log error message with optional extra context."""
        self._log(logging.ERROR, message, extra)
    
    def critical(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log critical message with optional extra context."""
        self._log(logging.CRITICAL, message, extra)
    
    def exception(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log exception with traceback."""
        self._log(logging.ERROR, message, extra, exc_info=True)
    
    def _log(self, level: int, message: str, extra: Optional[Dict[str, Any]] = None, exc_info: bool = False) -> None:
        """Internal logging method with structured context."""
        if extra is None:
            extra = {}
        
        # Create log record with structured data
        record = self.logger.makeRecord(
            name=self.name,
            level=level,
            fn="",
            lno=0,
            msg=message,
            args=(),
            exc_info=sys.exc_info() if exc_info else None
        )
        
        # Add extra context
        for key, value in extra.items():
            setattr(record, key, value)
        
        # Add timestamp
        record.timestamp = datetime.utcnow().isoformat()
        
        self.logger.handle(record)


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_entry = {
            "timestamp": getattr(record, 'timestamp', datetime.utcnow().isoformat()),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
                'module', 'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                'thread', 'threadName', 'processName', 'process', 'stack_info',
                'exc_info', 'exc_text', 'message', 'timestamp'
            }:
                # Ensure value is JSON serializable
                try:
                    json.dumps(value)
                    log_entry[key] = value
                except (TypeError, ValueError):
                    log_entry[key] = str(value)
        
        try:
            return json.dumps(log_entry, ensure_ascii=False, separators=(',', ':'))
        except (TypeError, ValueError):
            # Fallback to string representation if JSON serialization fails
            return str(log_entry)


class ContextLogger(StructuredLogger):
    """Logger with persistent context that gets added to all log messages."""
    
    def __init__(self, name: str = "zfs_operations", level: str = "INFO", context: Optional[Dict[str, Any]] = None):
        super().__init__(name, level)
        self.context = context or {}
        self._context_lock = threading.Lock()
    
    def add_context(self, key: str, value: Any) -> None:
        """Add persistent context to all future log messages."""
        with self._context_lock:
            self.context[key] = value
    
    def remove_context(self, key: str) -> None:
        """Remove context key."""
        with self._context_lock:
            self.context.pop(key, None)
    
    def clear_context(self) -> None:
        """Clear all context."""
        with self._context_lock:
            self.context.clear()
    
    def _log(self, level: int, message: str, extra: Optional[Dict[str, Any]] = None, exc_info: bool = False) -> None:
        """Internal logging method with merged context."""
        with self._context_lock:
            merged_extra = self.context.copy()
        if extra:
            merged_extra.update(extra)
        
        super()._log(level, message, merged_extra, exc_info)


class OperationLogger(ContextLogger):
    """Logger specifically for ZFS operations with operation tracking."""
    
    def __init__(self, name: str = "zfs_operations", level: str = "INFO"):
        super().__init__(name, level)
        self.operation_id = None
        self.operation_start_time = None
    
    def start_operation(self, operation_id: str, operation_type: str, **kwargs) -> None:
        """Start tracking an operation."""
        self.operation_id = operation_id
        self.operation_start_time = datetime.utcnow()
        
        self.add_context("operation_id", operation_id)
        self.add_context("operation_type", operation_type)
        
        # Add any additional context
        for key, value in kwargs.items():
            self.add_context(key, value)
        
        self.info(f"Starting operation: {operation_type}", {
            "operation_id": operation_id,
            "operation_type": operation_type,
            **kwargs
        })
    
    def complete_operation(self, success: bool = True, **kwargs) -> None:
        """Complete the current operation."""
        if self.operation_id and self.operation_start_time:
            duration = (datetime.utcnow() - self.operation_start_time).total_seconds()
            
            self.info(f"Operation completed: {self.context.get('operation_type', 'unknown')}", {
                "operation_id": self.operation_id,
                "success": success,
                "duration_seconds": duration,
                **kwargs
            })
            
            # Clean up operation context
            self.remove_context("operation_id")
            self.remove_context("operation_type")
            self.operation_id = None
            self.operation_start_time = None
    
    def fail_operation(self, error: str, **kwargs) -> None:
        """Mark operation as failed."""
        if self.operation_id and self.operation_start_time:
            duration = (datetime.utcnow() - self.operation_start_time).total_seconds()
            
            self.error(f"Operation failed: {self.context.get('operation_type', 'unknown')}", {
                "operation_id": self.operation_id,
                "success": False,
                "error": error,
                "duration_seconds": duration,
                **kwargs
            })
            
            # Clean up operation context
            self.remove_context("operation_id")
            self.remove_context("operation_type")
            self.operation_id = None
            self.operation_start_time = None 