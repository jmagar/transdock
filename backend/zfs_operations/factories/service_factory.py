"""
Service factory for dependency injection and service creation.
"""
from typing import Dict, Any, Optional
from ..core.interfaces.command_executor import ICommandExecutor
from ..core.interfaces.security_validator import ISecurityValidator
from ..core.interfaces.logger_interface import ILogger
from ..infrastructure.command_executor import CommandExecutor
from ..infrastructure.security_validator import SecurityValidator
from ..infrastructure.logging.structured_logger import StructuredLogger


class ServiceFactory:
    """Factory for creating and managing service instances with dependency injection."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._instances: Dict[str, Any] = {}
        
        # Initialize core infrastructure
        self._command_executor = None
        self._security_validator = None
        self._logger = None
    
    def get_command_executor(self) -> ICommandExecutor:
        """Get or create command executor instance."""
        if self._command_executor is None:
            timeout = self._config.get('command_timeout', 30)
            self._command_executor = CommandExecutor(timeout=timeout)
        return self._command_executor
    
    def get_security_validator(self) -> ISecurityValidator:
        """Get or create security validator instance."""
        if self._security_validator is None:
            self._security_validator = SecurityValidator()
        return self._security_validator
    
    def get_logger(self, name: str = "zfs_operations") -> ILogger:
        """Get or create logger instance."""
        if self._logger is None:
            log_level = self._config.get('log_level', 'INFO')
            self._logger = StructuredLogger(name=name, level=log_level)
        return self._logger
    
    def create_dataset_service(self):
        """Create DatasetService with dependencies."""
        from ..services.dataset_service import DatasetService
        return DatasetService(
            executor=self.get_command_executor(),
            validator=self.get_security_validator(),
            logger=self.get_logger("dataset_service")
        )
    
    def create_snapshot_service(self):
        """Create SnapshotService with dependencies."""
        from ..services.snapshot_service import SnapshotService
        return SnapshotService(
            executor=self.get_command_executor(),
            validator=self.get_security_validator(),
            logger=self.get_logger("snapshot_service")
        )
    
    def create_pool_service(self):
        """Create PoolService with dependencies."""
        from ..services.pool_service import PoolService
        return PoolService(
            executor=self.get_command_executor(),
            validator=self.get_security_validator(),
            logger=self.get_logger("pool_service")
        )
    
    def create_backup_service(self):
        """Create BackupService with dependencies."""
        from ..services.backup_service import BackupService
        return BackupService(
            executor=self.get_command_executor(),
            validator=self.get_security_validator(),
            logger=self.get_logger("backup_service")
        )
    
    def create_encryption_service(self):
        """Create EncryptionService with dependencies."""
        from ..services.encryption_service import EncryptionService
        return EncryptionService(
            executor=self.get_command_executor(),
            validator=self.get_security_validator(),
            logger=self.get_logger("encryption_service")
        )
    
    def create_remote_service(self):
        """Create RemoteService with dependencies."""
        from ..services.remote_service import RemoteService
        max_connections = self._config.get('max_ssh_connections', 10)
        return RemoteService(
            executor=self.get_command_executor(),
            validator=self.get_security_validator(),
            logger=self.get_logger("remote_service"),
            max_connections=max_connections
        )
    
    def create_quota_service(self):
        """Create QuotaService with dependencies."""
        from ..services.quota_service import QuotaService
        return QuotaService(
            executor=self.get_command_executor(),
            validator=self.get_security_validator(),
            logger=self.get_logger("quota_service")
        )
    
    def configure(self, **kwargs) -> 'ServiceFactory':
        """Configure the factory with additional settings."""
        self._config.update(kwargs)
        return self
    
    def reset(self) -> None:
        """Reset all cached instances."""
        self._instances.clear()
        self._command_executor = None
        self._security_validator = None
        self._logger = None 