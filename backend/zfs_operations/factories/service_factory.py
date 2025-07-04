"""
Service factory for dependency injection and service creation.
"""
import asyncio
from typing import Dict, Any, Optional

from ..core.interfaces.command_executor import ICommandExecutor
from ..core.interfaces.security_validator import ISecurityValidator
from ..core.interfaces.logger_interface import ILogger
from ..infrastructure.command_executor import CommandExecutor
from ..infrastructure.security_validator import SecurityValidator
from ..infrastructure.logging.structured_logger import StructuredLogger
from ..services.dataset_service import DatasetService
from ..services.snapshot_service import SnapshotService
from ..services.pool_service import PoolService


class ServiceFactory:
    """Factory for creating service instances with proper dependency injection."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the service factory with configuration."""
        self._config = config or {}
        self._logger_instances: Dict[str, ILogger] = {}
        self._lock = asyncio.Lock()
        
        # Initialize shared dependencies
        self._executor: ICommandExecutor = CommandExecutor(
            timeout=self._config.get('command_timeout', 30)
        )
        self._validator: ISecurityValidator = SecurityValidator()
    
    async def create_dataset_service(self) -> DatasetService:
        """Create a DatasetService instance with injected dependencies."""
        logger = await self._get_logger("dataset_service")
        return DatasetService(
            executor=self._executor,
            validator=self._validator,
            logger=logger
        )
    
    async def create_snapshot_service(self) -> SnapshotService:
        """Create a SnapshotService instance with injected dependencies."""
        logger = await self._get_logger("snapshot_service")
        return SnapshotService(
            executor=self._executor,
            validator=self._validator,
            logger=logger
        )
    
    async def create_pool_service(self) -> PoolService:
        """Create a PoolService instance with injected dependencies."""
        logger = await self._get_logger("pool_service")
        return PoolService(
            executor=self._executor,
            validator=self._validator,
            logger=logger
        )
    
    async def create_all_services(self) -> Dict[str, Any]:
        """Create all services and return them as a dictionary."""
        return {
            'dataset_service': await self.create_dataset_service(),
            'snapshot_service': await self.create_snapshot_service(),
            'pool_service': await self.create_pool_service()
        }
    
    async def _get_logger(self, service_name: str) -> ILogger:
        """Get or create a logger instance for a service."""
        async with self._lock:
            if service_name not in self._logger_instances:
                self._logger_instances[service_name] = StructuredLogger(
                    name=service_name,
                    level=self._config.get('log_level', 'INFO')
                )
            return self._logger_instances[service_name]
    
    def get_config(self) -> Dict[str, Any]:
        """Get the current configuration."""
        return self._config.copy()
    
    async def update_config(self, new_config: Dict[str, Any]):
        """Update the configuration and reinitialize dependencies."""
        async with self._lock:
            self._config.update(new_config)
            # Reinitialize dependencies with new config
            self._executor = CommandExecutor(
                timeout=self._config.get('command_timeout', 30)
            )
            self._validator = SecurityValidator()
            # Clear logger instances to force recreation with new config
            self._logger_instances.clear()


class ServiceFactoryBuilder:
    """Builder for creating ServiceFactory instances with fluent configuration."""
    
    def __init__(self):
        self._config = {}
    
    def with_command_timeout(self, timeout: int) -> 'ServiceFactoryBuilder':
        """Set command timeout configuration."""
        self._config['command_timeout'] = timeout
        return self
    
    def with_log_level(self, level: str) -> 'ServiceFactoryBuilder':
        """Set logging level."""
        self._config['log_level'] = level
        return self
    
    def build(self) -> ServiceFactory:
        """Build the ServiceFactory instance."""
        return ServiceFactory(self._config)


# Convenience function for creating a default service factory
def create_default_service_factory() -> ServiceFactory:
    """Create a service factory with default configuration."""
    return ServiceFactoryBuilder() \
        .with_command_timeout(30) \
        .with_log_level('INFO') \
        .build()


# Convenience function for creating a development service factory
def create_development_service_factory() -> ServiceFactory:
    """Create a service factory configured for development."""
    return ServiceFactoryBuilder() \
        .with_command_timeout(10) \
        .with_log_level('DEBUG') \
        .build()


# Convenience function for creating a production service factory
def create_production_service_factory() -> ServiceFactory:
    """Create a service factory configured for production."""
    return ServiceFactoryBuilder() \
        .with_command_timeout(60) \
        .with_log_level('WARNING') \
        .build() 