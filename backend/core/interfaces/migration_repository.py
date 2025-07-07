"""Migration repository interfaces"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from ..entities.migration_entity import Migration, MigrationStep
from ..value_objects.host_connection import HostConnection


class MigrationRepository(ABC):
    """Repository interface for migrations"""
    
    @abstractmethod
    async def create(self, migration: Migration) -> Migration:
        """Create a new migration"""
        pass
    
    @abstractmethod
    async def find_by_id(self, migration_id: str) -> Optional[Migration]:
        """Find migration by ID"""
        pass
    
    @abstractmethod
    async def find_by_name(self, name: str) -> Optional[Migration]:
        """Find migration by name"""
        pass
    
    @abstractmethod
    async def list_all(self) -> List[Migration]:
        """List all migrations"""
        pass
    
    @abstractmethod
    async def list_active(self) -> List[Migration]:
        """List active (running) migrations"""
        pass
    
    @abstractmethod
    async def list_completed(self) -> List[Migration]:
        """List completed migrations"""
        pass
    
    @abstractmethod
    async def list_failed(self) -> List[Migration]:
        """List failed migrations"""
        pass
    
    @abstractmethod
    async def update(self, migration: Migration) -> Migration:
        """Update migration"""
        pass
    
    @abstractmethod
    async def delete(self, migration_id: str) -> bool:
        """Delete migration"""
        pass
    
    @abstractmethod
    async def update_status(self, migration_id: str, status: str) -> bool:
        """Update migration status"""
        pass
    
    @abstractmethod
    async def add_step(self, migration_id: str, step: MigrationStep) -> bool:
        """Add step to migration"""
        pass
    
    @abstractmethod
    async def update_step(self, migration_id: str, step: MigrationStep) -> bool:
        """Update migration step"""
        pass
    
    @abstractmethod
    async def get_migration_logs(self, migration_id: str) -> List[Dict[str, Any]]:
        """Get migration logs"""
        pass
    
    @abstractmethod
    async def cleanup_old_migrations(self, keep_days: int = 30) -> int:
        """Clean up old completed migrations"""
        pass
    
    @abstractmethod
    async def store_compose_content(self, migration_id: str, compose_content: str, env_content: Optional[str] = None, project_name: Optional[str] = None) -> bool:
        """Store Docker Compose file content for migration"""
        pass
    
    @abstractmethod
    async def get_compose_content(self, migration_id: str) -> Optional[Dict[str, Any]]:
        """Get Docker Compose file content for migration"""
        pass