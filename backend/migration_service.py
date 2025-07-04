"""
Refactored MigrationService - Facade Pattern

This refactored version coordinates smaller, focused services while maintaining
backward compatibility with the existing API.

The monolithic MigrationService has been broken down into:
- MigrationOrchestrator: Status tracking and workflow coordination  
- ContainerDiscoveryService: Container discovery and analysis
- ContainerMigrationService: Container-specific migration operations
- SnapshotService: ZFS snapshot management
- SystemInfoService: System information and capabilities
- ComposeStackService: Legacy compose stack operations
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from .models import (
    MigrationRequest, ContainerMigrationRequest, MigrationStatus,
    ContainerDiscoveryResult, ContainerAnalysis, IdentifierType
)
from .docker_ops import DockerOperations
from .zfs_ops import ZFSOperations
from .transfer_ops import TransferOperations
from .host_service import HostService
from .services import (
    MigrationOrchestrator,
    ContainerDiscoveryService,
    ContainerMigrationService,
    SnapshotService,
    SystemInfoService,
    ComposeStackService
)

logger = logging.getLogger(__name__)


class MigrationService:
    """
    Refactored MigrationService using the Facade pattern.
    
    Coordinates multiple focused services while maintaining backward compatibility
    with the existing API. This approach provides better separation of concerns,
    easier testing, and improved maintainability.
    """
    
    def __init__(self):
        # Initialize core operations
        self.zfs_ops = ZFSOperations()
        self.docker_ops = DockerOperations()
        self.transfer_ops = TransferOperations(zfs_ops=self.zfs_ops)
        self.host_service = HostService()
        
        # Initialize specialized services
        self.orchestrator = MigrationOrchestrator()
        self.discovery_service = ContainerDiscoveryService(self.docker_ops)
        self.snapshot_service = SnapshotService(self.zfs_ops, self.host_service)
        self.system_info_service = SystemInfoService(self.zfs_ops, self.docker_ops)
        self.compose_stack_service = ComposeStackService(self.docker_ops, self.zfs_ops)
        
        # Initialize container migration service (needs other services)
        self.container_migration_service = ContainerMigrationService(
            self.docker_ops,
            self.zfs_ops,
            self.transfer_ops,
            self.host_service,
            self.orchestrator,
            self.discovery_service
        )
        
        logger.info("MigrationService initialized with refactored architecture")
    
    # === Core Migration Management (delegated to MigrationOrchestrator) ===
    
    def create_migration_id(self) -> str:
        """Generate a unique migration ID"""
        return self.orchestrator.create_migration_id()
    
    async def get_migration_status(self, migration_id: str) -> Optional[MigrationStatus]:
        """Get the status of a migration"""
        return await self.orchestrator.get_migration_status(migration_id)
    
    async def list_migrations(self) -> List[MigrationStatus]:
        """List all migrations"""
        return await self.orchestrator.list_migrations()
    
    async def cancel_migration(self, migration_id: str) -> bool:
        """Cancel a running migration"""
        return await self.orchestrator.cancel_migration(migration_id)
    
    async def cleanup_migration(self, migration_id: str) -> bool:
        """Clean up migration resources"""
        return await self.orchestrator.cleanup_migration(migration_id)
    
    async def get_migration_metrics(self) -> Dict[str, int]:
        """Get migration metrics"""
        return await self.orchestrator.get_migration_metrics()
    
    # === Container Discovery and Analysis (delegated to ContainerDiscoveryService) ===
    
    async def discover_containers(self, 
                                container_identifier: str,
                                identifier_type: IdentifierType,
                                label_filters: Optional[Dict[str, str]] = None,
                                source_host: Optional[str] = None,
                                source_ssh_user: str = "root",
                                source_ssh_port: int = 22) -> ContainerDiscoveryResult:
        """Discover containers for migration"""
        return await self.discovery_service.discover_containers(
            container_identifier, identifier_type, label_filters,
            source_host, source_ssh_user
        )
    
    async def analyze_containers_for_migration(self,
                                             container_identifier: str,
                                             identifier_type: IdentifierType,
                                             label_filters: Optional[Dict[str, str]] = None,
                                             source_host: Optional[str] = None) -> ContainerAnalysis:
        """Analyze containers to provide migration insights"""
        return await self.discovery_service.analyze_containers_for_migration(
            container_identifier, identifier_type, label_filters, source_host
        )
    
    # === Container Migration (delegated to ContainerMigrationService) ===
    
    async def start_container_migration(self, request: ContainerMigrationRequest) -> str:
        """Start a container-based migration"""
        return await self.container_migration_service.start_container_migration(request)
    
    # === System Information (delegated to SystemInfoService) ===
    
    async def get_system_info(self) -> Dict[str, Any]:
        """Get system information relevant to migrations"""
        return await self.system_info_service.get_system_info()
    
    async def get_zfs_status(self) -> Dict[str, Any]:
        """Get detailed ZFS status information"""
        return await self.system_info_service.get_zfs_status()
    
    async def get_capabilities_summary(self) -> Dict[str, bool]:
        """Get a summary of system capabilities"""
        return await self.system_info_service.get_capabilities_summary()
    
    # === Legacy Compose Operations (delegated to ComposeStackService) ===
    
    async def get_compose_stacks(self) -> List[Dict[str, str]]:
        """Get list of available Docker Compose stacks (DEPRECATED)"""
        logger.warning("get_compose_stacks is deprecated. Use container discovery instead.")
        return await self.compose_stack_service.get_compose_stacks()
    
    async def get_stack_info(self, stack_name: str) -> Dict[str, Any]:
        """Get detailed information about a specific compose stack (DEPRECATED)"""
        logger.warning("get_stack_info is deprecated. Use container discovery instead.")
        return await self.compose_stack_service.get_stack_info(stack_name)
    
    # === Legacy Migration Support ===
    
    async def start_migration(self, request: MigrationRequest) -> str:
        """
        Start a legacy compose-based migration (DEPRECATED)
        
        This method is maintained for backward compatibility but is deprecated.
        New applications should use start_container_migration() instead.
        """
        logger.warning("start_migration is deprecated. Use start_container_migration instead.")
        
        # Convert legacy request to container migration request
        try:
            # Try to discover containers by project name (compose dataset name)
            container_request = ContainerMigrationRequest(
                container_identifier=request.compose_dataset,
                identifier_type=IdentifierType.PROJECT,
                target_host=request.target_host,
                target_base_path=request.target_base_path,
                ssh_user=request.ssh_user,
                ssh_port=request.ssh_port,
                source_host=request.source_host,
                source_ssh_user=request.source_ssh_user or "root",
                source_ssh_port=request.source_ssh_port or 22,
                force_rsync=request.force_rsync or False
            )
            
            return await self.start_container_migration(container_request)
            
        except Exception as e:
            logger.error(f"Failed to convert legacy migration to container migration: {e}")
            raise ValueError(f"Legacy migration failed: {e}. Please use container migration instead.")
    
    # === Service Health and Diagnostics ===
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check of all services"""
        health = {
            "status": "healthy",
            "services": {},
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # Check Docker operations
        try:
            docker_status = await self.system_info_service.check_docker_status()
            health["services"]["docker"] = {
                "status": "healthy" if docker_status["available"] else "unhealthy",
                "details": docker_status
            }
        except Exception as e:
            health["services"]["docker"] = {"status": "error", "error": str(e)}
        
        # Check ZFS operations
        try:
            zfs_status = await self.system_info_service.get_zfs_status()
            health["services"]["zfs"] = {
                "status": "healthy" if zfs_status["available"] else "unavailable",
                "details": zfs_status
            }
        except Exception as e:
            health["services"]["zfs"] = {"status": "error", "error": str(e)}
        
        # Check migration orchestrator
        try:
            metrics = await self.orchestrator.get_migration_metrics()
            health["services"]["migration_orchestrator"] = {
                "status": "healthy",
                "metrics": metrics
            }
        except Exception as e:
            health["services"]["migration_orchestrator"] = {"status": "error", "error": str(e)}
        
        # Overall health status
        unhealthy_services = [
            name for name, service in health["services"].items() 
            if service["status"] not in ["healthy", "unavailable"]
        ]
        
        if unhealthy_services:
            health["status"] = "degraded"
            health["unhealthy_services"] = unhealthy_services
        
        return health
    
    # === Service Information ===
    
    def get_service_architecture(self) -> Dict[str, Any]:
        """Get information about the service architecture"""
        return {
            "architecture": "refactored_facade",
            "description": "Refactored MigrationService using focused, single-responsibility services",
            "services": {
                "migration_orchestrator": "Migration workflow and status management",
                "container_discovery_service": "Container discovery and analysis",
                "container_migration_service": "Container-specific migration operations",
                "snapshot_service": "ZFS snapshot creation and management",
                "system_info_service": "System information and capabilities",
                "compose_stack_service": "Legacy compose stack operations (deprecated)"
            },
            "benefits": [
                "Single Responsibility Principle",
                "Better testability",
                "Improved maintainability", 
                "Easier to extend",
                "Clear separation of concerns"
            ],
            "migration_status": "complete",
            "backward_compatibility": "maintained"
        }
