import asyncio
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional
from ..models import MigrationStatus, MigrationRequest, MigrationResponse

logger = logging.getLogger(__name__)


class MigrationOrchestrator:
    """Orchestrates migration workflows and manages migration status"""
    
    def __init__(self):
        self.active_migrations: Dict[str, MigrationStatus] = {}
    
    def create_migration_id(self) -> str:
        """Generate a unique migration ID"""
        return str(uuid.uuid4())
    
    async def get_migration_status(self, migration_id: str) -> Optional[MigrationStatus]:
        """Get the status of a migration"""
        return self.active_migrations.get(migration_id)
    
    async def list_migrations(self) -> List[MigrationStatus]:
        """List all migrations"""
        return list(self.active_migrations.values())
    
    async def update_status(self, migration_id: str, status: str, progress: int, message: str):
        """Update migration status"""
        if migration_id in self.active_migrations:
            self.active_migrations[migration_id].status = status
            self.active_migrations[migration_id].progress = progress
            self.active_migrations[migration_id].message = message
            logger.info(f"Migration {migration_id}: {message} ({progress}%)")
    
    async def update_error(self, migration_id: str, error: str):
        """Update migration with error"""
        if migration_id in self.active_migrations:
            self.active_migrations[migration_id].status = "failed"
            self.active_migrations[migration_id].error = error
            logger.error(f"Migration {migration_id} failed: {error}")
    
    def register_migration(self, migration_id: str, status: MigrationStatus):
        """Register a new migration"""
        self.active_migrations[migration_id] = status
        logger.info(f"Registered migration {migration_id}")
    
    async def cancel_migration(self, migration_id: str) -> bool:
        """Cancel a running migration"""
        if migration_id not in self.active_migrations:
            raise KeyError("Migration not found")
        
        status = self.active_migrations[migration_id]
        
        # Only allow cancellation of running migrations
        if status.status in ["completed", "failed", "cancelled"]:
            return False
        
        # Update status to cancelled
        await self.update_status(migration_id, "cancelled", status.progress, "Migration cancelled by user")
        
        logger.info(f"Cancelled migration {migration_id}")
        return True
    
    async def cleanup_migration(self, migration_id: str) -> bool:
        """Clean up migration resources"""
        if migration_id not in self.active_migrations:
            return False
        
        # Remove from active migrations
        del self.active_migrations[migration_id]
        
        logger.info(f"Cleaned up migration {migration_id}")
        return True
    
    def get_migration_metrics(self) -> Dict[str, int]:
        """Get migration metrics"""
        total = len(self.active_migrations)
        running = len([m for m in self.active_migrations.values() if m.status not in ["completed", "failed", "cancelled"]])
        completed = len([m for m in self.active_migrations.values() if m.status == "completed"])
        failed = len([m for m in self.active_migrations.values() if m.status == "failed"])
        
        return {
            "total": total,
            "running": running,
            "completed": completed,
            "failed": failed
        }