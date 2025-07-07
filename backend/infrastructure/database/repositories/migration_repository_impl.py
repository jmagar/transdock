"""Migration repository implementation"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import uuid

from ....core.interfaces.migration_repository import MigrationRepository
from ....core.entities.migration_entity import Migration, MigrationStep, MigrationStatus, MigrationStepType, MigrationStepStatus
from ....core.value_objects.host_connection import HostConnection
from ..models.migration_model import MigrationModel, MigrationStepModel, MigrationSnapshotModel, MigrationStatusEnum, MigrationStepTypeEnum, MigrationStepStatusEnum
import logging

logger = logging.getLogger(__name__)


class MigrationRepositoryImpl(MigrationRepository):
    """PostgreSQL implementation of migration repository"""
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def create(self, migration: Migration) -> Migration:
        """Create a new migration"""
        try:
            # Create migration model
            migration_model = MigrationModel(
                id=uuid.UUID(migration.id) if migration.id else uuid.uuid4(),
                name=migration.name,
                status=MigrationStatusEnum(migration.status.value),
                source_host=migration.source_host.hostname,
                source_port=str(migration.source_host.port) if migration.source_host.port else None,
                source_username=migration.source_host.username,
                target_host=migration.target_host.hostname,
                target_port=str(migration.target_host.port) if migration.target_host.port else None,
                target_username=migration.target_host.username,
                compose_stack_path=migration.compose_stack_path,
                target_base_path=migration.target_base_path,
                use_zfs=str(migration.use_zfs).lower(),
                transfer_method=migration.transfer_method,
                cleanup_on_success=str(migration.cleanup_on_success).lower(),
                verify_transfer=str(migration.verify_transfer).lower(),
                create_backup_snapshot=str(migration.create_backup_snapshot).lower(),
                created_at=migration.created_at,
                metadata=migration.metadata
            )
            
            # Add steps
            for step in migration.steps:
                step_model = MigrationStepModel(
                    id=uuid.UUID(step.id) if step.id else uuid.uuid4(),
                    migration_id=migration_model.id,
                    name=step.name,
                    step_type=MigrationStepTypeEnum(step.step_type.value),
                    status=MigrationStepStatusEnum(step.status.value),
                    progress_percentage=step.progress_percentage,
                    details=step.details
                )
                migration_model.steps.append(step_model)
            
            self._session.add(migration_model)
            await self._session.commit()
            await self._session.refresh(migration_model)
            
            # Convert back to entity
            return self._model_to_entity(migration_model)
            
        except Exception as e:
            logger.error(f"Failed to create migration: {e}")
            await self._session.rollback()
            raise
    
    async def find_by_id(self, migration_id: str) -> Optional[Migration]:
        """Find migration by ID"""
        try:
            result = await self._session.execute(
                select(MigrationModel)
                .options(selectinload(MigrationModel.steps))
                .options(selectinload(MigrationModel.snapshots))
                .where(MigrationModel.id == uuid.UUID(migration_id))
            )
            model = result.scalar_one_or_none()
            
            if not model:
                return None
            
            return self._model_to_entity(model)
            
        except Exception as e:
            logger.error(f"Failed to find migration by ID {migration_id}: {e}")
            return None
    
    async def find_by_name(self, name: str) -> Optional[Migration]:
        """Find migration by name"""
        try:
            result = await self._session.execute(
                select(MigrationModel)
                .options(selectinload(MigrationModel.steps))
                .options(selectinload(MigrationModel.snapshots))
                .where(MigrationModel.name == name)
                .order_by(MigrationModel.created_at.desc())
                .limit(1)
            )
            model = result.scalar_one_or_none()
            
            if not model:
                return None
            
            return self._model_to_entity(model)
            
        except Exception as e:
            logger.error(f"Failed to find migration by name {name}: {e}")
            return None
    
    async def list_all(self) -> List[Migration]:
        """List all migrations"""
        try:
            result = await self._session.execute(
                select(MigrationModel)
                .options(selectinload(MigrationModel.steps))
                .order_by(MigrationModel.created_at.desc())
            )
            models = result.scalars().all()
            
            return [self._model_to_entity(model) for model in models]
            
        except Exception as e:
            logger.error(f"Failed to list all migrations: {e}")
            return []
    
    async def list_active(self) -> List[Migration]:
        """List active (running) migrations"""
        try:
            active_statuses = [
                MigrationStatusEnum.PREPARING,
                MigrationStatusEnum.CREATING_SNAPSHOTS,
                MigrationStatusEnum.TRANSFERRING_DATA,
                MigrationStatusEnum.RECREATING_CONTAINERS,
                MigrationStatusEnum.STARTING_SERVICES,
                MigrationStatusEnum.VERIFYING,
                MigrationStatusEnum.ROLLING_BACK
            ]
            
            result = await self._session.execute(
                select(MigrationModel)
                .options(selectinload(MigrationModel.steps))
                .where(MigrationModel.status.in_(active_statuses))
                .order_by(MigrationModel.started_at.asc())
            )
            models = result.scalars().all()
            
            return [self._model_to_entity(model) for model in models]
            
        except Exception as e:
            logger.error(f"Failed to list active migrations: {e}")
            return []
    
    async def list_completed(self) -> List[Migration]:
        """List completed migrations"""
        try:
            result = await self._session.execute(
                select(MigrationModel)
                .options(selectinload(MigrationModel.steps))
                .where(MigrationModel.status == MigrationStatusEnum.COMPLETED)
                .order_by(MigrationModel.completed_at.desc())
            )
            models = result.scalars().all()
            
            return [self._model_to_entity(model) for model in models]
            
        except Exception as e:
            logger.error(f"Failed to list completed migrations: {e}")
            return []
    
    async def list_failed(self) -> List[Migration]:
        """List failed migrations"""
        try:
            result = await self._session.execute(
                select(MigrationModel)
                .options(selectinload(MigrationModel.steps))
                .where(MigrationModel.status == MigrationStatusEnum.FAILED)
                .order_by(MigrationModel.completed_at.desc())
            )
            models = result.scalars().all()
            
            return [self._model_to_entity(model) for model in models]
            
        except Exception as e:
            logger.error(f"Failed to list failed migrations: {e}")
            return []
    
    async def update(self, migration: Migration) -> Migration:
        """Update migration"""
        try:
            # Update main migration record
            stmt = (
                update(MigrationModel)
                .where(MigrationModel.id == uuid.UUID(migration.id))
                .values(
                    status=MigrationStatusEnum(migration.status.value),
                    started_at=migration.started_at,
                    completed_at=migration.completed_at,
                    error_message=migration.error_message,
                    metadata=migration.metadata
                )
            )
            await self._session.execute(stmt)
            
            # Update steps if needed
            for step in migration.steps:
                step_stmt = (
                    update(MigrationStepModel)
                    .where(MigrationStepModel.id == uuid.UUID(step.id))
                    .values(
                        status=MigrationStepStatusEnum(step.status.value),
                        started_at=step.started_at,
                        completed_at=step.completed_at,
                        progress_percentage=step.progress_percentage,
                        error_message=step.error_message,
                        details=step.details
                    )
                )
                await self._session.execute(step_stmt)
            
            await self._session.commit()
            
            # Fetch and return updated migration
            updated = await self.find_by_id(migration.id)
            if not updated:
                raise Exception(f"Failed to fetch updated migration {migration.id}")
            return updated
            
        except Exception as e:
            logger.error(f"Failed to update migration: {e}")
            await self._session.rollback()
            raise
    
    async def delete(self, migration_id: str) -> bool:
        """Delete migration"""
        try:
            # Delete migration (cascades to steps and snapshots)
            stmt = delete(MigrationModel).where(MigrationModel.id == uuid.UUID(migration_id))
            result = await self._session.execute(stmt)
            await self._session.commit()
            
            return result.rowcount > 0
            
        except Exception as e:
            logger.error(f"Failed to delete migration {migration_id}: {e}")
            await self._session.rollback()
            return False
    
    async def update_status(self, migration_id: str, status: str) -> bool:
        """Update migration status"""
        try:
            stmt = (
                update(MigrationModel)
                .where(MigrationModel.id == uuid.UUID(migration_id))
                .values(status=MigrationStatusEnum(status))
            )
            result = await self._session.execute(stmt)
            await self._session.commit()
            
            return result.rowcount > 0
            
        except Exception as e:
            logger.error(f"Failed to update migration status: {e}")
            await self._session.rollback()
            return False
    
    async def add_step(self, migration_id: str, step: MigrationStep) -> bool:
        """Add step to migration"""
        try:
            step_model = MigrationStepModel(
                id=uuid.UUID(step.id) if step.id else uuid.uuid4(),
                migration_id=uuid.UUID(migration_id),
                name=step.name,
                step_type=MigrationStepTypeEnum(step.step_type.value),
                status=MigrationStepStatusEnum(step.status.value),
                progress_percentage=step.progress_percentage,
                details=step.details
            )
            
            self._session.add(step_model)
            await self._session.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add step to migration: {e}")
            await self._session.rollback()
            return False
    
    async def update_step(self, migration_id: str, step: MigrationStep) -> bool:
        """Update migration step"""
        try:
            stmt = (
                update(MigrationStepModel)
                .where(
                    and_(
                        MigrationStepModel.id == uuid.UUID(step.id),
                        MigrationStepModel.migration_id == uuid.UUID(migration_id)
                    )
                )
                .values(
                    status=MigrationStepStatusEnum(step.status.value),
                    started_at=step.started_at,
                    completed_at=step.completed_at,
                    progress_percentage=step.progress_percentage,
                    error_message=step.error_message,
                    details=step.details
                )
            )
            result = await self._session.execute(stmt)
            await self._session.commit()
            
            return result.rowcount > 0
            
        except Exception as e:
            logger.error(f"Failed to update migration step: {e}")
            await self._session.rollback()
            return False
    
    async def get_migration_logs(self, migration_id: str) -> List[Dict[str, Any]]:
        """Get migration logs"""
        try:
            # For now, return step details as logs
            migration = await self.find_by_id(migration_id)
            if not migration:
                return []
            
            logs = []
            for step in migration.steps:
                log_entry = {
                    'timestamp': step.started_at or datetime.utcnow(),
                    'level': 'error' if step.is_failed() else 'info',
                    'step': step.name,
                    'status': step.status.value,
                    'progress': step.progress_percentage,
                    'message': step.error_message or step.details.get('progress_message', ''),
                    'details': step.details
                }
                logs.append(log_entry)
            
            return logs
            
        except Exception as e:
            logger.error(f"Failed to get migration logs: {e}")
            return []
    
    async def cleanup_old_migrations(self, keep_days: int = 30) -> int:
        """Clean up old completed migrations"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=keep_days)
            
            # Find old completed migrations
            result = await self._session.execute(
                select(MigrationModel.id)
                .where(
                    and_(
                        MigrationModel.status == MigrationStatusEnum.COMPLETED,
                        MigrationModel.completed_at < cutoff_date
                    )
                )
            )
            old_migration_ids = [row[0] for row in result.fetchall()]
            
            if not old_migration_ids:
                return 0
            
            # Delete old migrations (cascades to steps and snapshots)
            stmt = delete(MigrationModel).where(MigrationModel.id.in_(old_migration_ids))
            result = await self._session.execute(stmt)
            await self._session.commit()
            
            logger.info(f"Cleaned up {result.rowcount} old migrations")
            return result.rowcount
            
        except Exception as e:
            logger.error(f"Failed to cleanup old migrations: {e}")
            await self._session.rollback()
            return 0
    
    async def store_compose_content(self, migration_id: str, compose_content: str, env_content: Optional[str] = None, project_name: Optional[str] = None) -> bool:
        """Store Docker Compose file content for migration"""
        try:
            stmt = (
                update(MigrationModel)
                .where(MigrationModel.id == uuid.UUID(migration_id))
                .values(
                    compose_file_content=compose_content,
                    compose_env_content=env_content,
                    compose_project_name=project_name
                )
            )
            result = await self._session.execute(stmt)
            await self._session.commit()
            
            return result.rowcount > 0
            
        except Exception as e:
            logger.error(f"Failed to store compose content: {e}")
            await self._session.rollback()
            return False
    
    async def get_compose_content(self, migration_id: str) -> Optional[Dict[str, str]]:
        """Get Docker Compose file content for migration"""
        try:
            result = await self._session.execute(
                select(
                    MigrationModel.compose_file_content,
                    MigrationModel.compose_env_content,
                    MigrationModel.compose_project_name
                )
                .where(MigrationModel.id == uuid.UUID(migration_id))
            )
            row = result.one_or_none()
            
            if not row:
                return None
            
            return {
                'compose_file': row[0],
                'env_file': row[1],
                'project_name': row[2]
            }
            
        except Exception as e:
            logger.error(f"Failed to get compose content: {e}")
            return None
    
    def _model_to_entity(self, model: MigrationModel) -> Migration:
        """Convert database model to domain entity"""
        # Create host connections
        source_host = HostConnection(
            hostname=model.source_host,
            port=int(model.source_port) if model.source_port else 22,
            username=model.source_username or "root"
        )
        
        target_host = HostConnection(
            hostname=model.target_host,
            port=int(model.target_port) if model.target_port else 22,
            username=model.target_username or "root"
        )
        
        # Create migration entity
        migration = Migration(
            id=str(model.id),
            name=model.name,
            status=MigrationStatus(model.status.value),
            source_host=source_host,
            target_host=target_host,
            compose_stack_path=model.compose_stack_path,
            target_base_path=model.target_base_path,
            use_zfs=model.use_zfs == "true",
            transfer_method=model.transfer_method,
            cleanup_on_success=model.cleanup_on_success == "true",
            verify_transfer=model.verify_transfer == "true",
            create_backup_snapshot=model.create_backup_snapshot == "true",
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_message=model.error_message,
            metadata=model.metadata or {}
        )
        
        # Convert steps
        migration.steps = []
        for step_model in model.steps:
            step = MigrationStep(
                id=str(step_model.id),
                name=step_model.name,
                step_type=MigrationStepType(step_model.step_type.value),
                status=MigrationStepStatus(step_model.status.value),
                started_at=step_model.started_at,
                completed_at=step_model.completed_at,
                error_message=step_model.error_message,
                details=step_model.details or {},
                progress_percentage=step_model.progress_percentage
            )
            migration.steps.append(step)
        
        return migration