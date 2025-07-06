"""Migration domain entities"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
from uuid import uuid4, UUID
from ..value_objects.host_connection import HostConnection
from ..value_objects.dataset_name import DatasetName


class MigrationStatus(Enum):
    """Migration status enumeration"""
    PENDING = "pending"
    PREPARING = "preparing"
    CREATING_SNAPSHOTS = "creating_snapshots"
    TRANSFERRING_DATA = "transferring_data"
    RECREATING_CONTAINERS = "recreating_containers"
    STARTING_SERVICES = "starting_services"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"


class MigrationStepType(Enum):
    """Migration step types"""
    VALIDATION = "validation"
    SNAPSHOT_CREATION = "snapshot_creation"
    DATA_TRANSFER = "data_transfer"
    CONTAINER_RECREATION = "container_recreation"
    SERVICE_START = "service_start"
    VERIFICATION = "verification"
    CLEANUP = "cleanup"


class MigrationStepStatus(Enum):
    """Migration step status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class MigrationStep:
    """Individual migration step"""
    
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    step_type: MigrationStepType = MigrationStepType.VALIDATION
    status: MigrationStepStatus = MigrationStepStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    progress_percentage: float = 0.0
    
    def start(self) -> None:
        """Mark step as started"""
        self.status = MigrationStepStatus.RUNNING
        self.started_at = datetime.now()
        self.progress_percentage = 0.0
    
    def complete(self, details: Optional[Dict[str, Any]] = None) -> None:
        """Mark step as completed"""
        self.status = MigrationStepStatus.COMPLETED
        self.completed_at = datetime.now()
        self.progress_percentage = 100.0
        if details:
            self.details.update(details)
    
    def fail(self, error_message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Mark step as failed"""
        self.status = MigrationStepStatus.FAILED
        self.completed_at = datetime.now()
        self.error_message = error_message
        if details:
            self.details.update(details)
    
    def skip(self, reason: str) -> None:
        """Mark step as skipped"""
        self.status = MigrationStepStatus.SKIPPED
        self.completed_at = datetime.now()
        self.details['skip_reason'] = reason
        self.progress_percentage = 100.0
    
    def update_progress(self, percentage: float, message: Optional[str] = None) -> None:
        """Update step progress"""
        self.progress_percentage = max(0.0, min(100.0, percentage))
        if message:
            self.details['progress_message'] = message
    
    @property
    def duration(self) -> Optional[float]:
        """Get step duration in seconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def is_running(self) -> bool:
        """Check if step is currently running"""
        return self.status == MigrationStepStatus.RUNNING
    
    def is_completed(self) -> bool:
        """Check if step completed successfully"""
        return self.status == MigrationStepStatus.COMPLETED
    
    def is_failed(self) -> bool:
        """Check if step failed"""
        return self.status == MigrationStepStatus.FAILED


@dataclass
class Migration:
    """Migration domain entity"""
    
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    status: MigrationStatus = MigrationStatus.PENDING
    source_host: HostConnection = field(default_factory=lambda: HostConnection.localhost())
    target_host: HostConnection = field(default_factory=lambda: HostConnection.localhost())
    compose_stack_path: str = ""
    target_base_path: str = ""
    use_zfs: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    steps: List[MigrationStep] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Migration configuration
    transfer_method: str = "zfs_send"  # zfs_send or rsync
    cleanup_on_success: bool = True
    verify_transfer: bool = True
    create_backup_snapshot: bool = True
    
    def start(self) -> None:
        """Start the migration"""
        self.status = MigrationStatus.PREPARING
        self.started_at = datetime.now()
    
    def complete(self) -> None:
        """Mark migration as completed"""
        self.status = MigrationStatus.COMPLETED
        self.completed_at = datetime.now()
    
    def fail(self, error_message: str) -> None:
        """Mark migration as failed"""
        self.status = MigrationStatus.FAILED
        self.completed_at = datetime.now()
        self.error_message = error_message
    
    def cancel(self) -> None:
        """Cancel the migration"""
        self.status = MigrationStatus.CANCELLED
        self.completed_at = datetime.now()
    
    def update_status(self, status: MigrationStatus) -> None:
        """Update migration status"""
        self.status = status
    
    def add_step(self, step: MigrationStep) -> None:
        """Add a migration step"""
        self.steps.append(step)
    
    def get_current_step(self) -> Optional[MigrationStep]:
        """Get the currently running step"""
        for step in self.steps:
            if step.is_running():
                return step
        return None
    
    def get_failed_step(self) -> Optional[MigrationStep]:
        """Get the first failed step"""
        for step in self.steps:
            if step.is_failed():
                return step
        return None
    
    def get_completed_steps(self) -> List[MigrationStep]:
        """Get all completed steps"""
        return [step for step in self.steps if step.is_completed()]
    
    def get_pending_steps(self) -> List[MigrationStep]:
        """Get all pending steps"""
        return [step for step in self.steps if step.status == MigrationStepStatus.PENDING]
    
    @property
    def duration(self) -> Optional[float]:
        """Get migration duration in seconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    @property
    def progress_percentage(self) -> float:
        """Calculate overall migration progress"""
        if not self.steps:
            return 0.0
        
        total_progress = sum(step.progress_percentage for step in self.steps)
        return total_progress / len(self.steps)
    
    def is_completed(self) -> bool:
        """Check if migration completed successfully"""
        return self.status == MigrationStatus.COMPLETED
    
    def is_failed(self) -> bool:
        """Check if migration failed"""
        return self.status == MigrationStatus.FAILED
    
    def is_running(self) -> bool:
        """Check if migration is currently running"""
        return self.status not in [
            MigrationStatus.PENDING,
            MigrationStatus.COMPLETED,
            MigrationStatus.FAILED,
            MigrationStatus.CANCELLED,
            MigrationStatus.ROLLED_BACK
        ]
    
    def can_be_cancelled(self) -> bool:
        """Check if migration can be cancelled"""
        return self.is_running()
    
    def can_be_retried(self) -> bool:
        """Check if migration can be retried"""
        return self.status in [MigrationStatus.FAILED, MigrationStatus.CANCELLED]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get migration summary"""
        completed_steps = len(self.get_completed_steps())
        total_steps = len(self.steps)
        
        summary = {
            'id': self.id,
            'name': self.name,
            'status': self.status.value,
            'progress_percentage': round(self.progress_percentage, 2),
            'source_host': str(self.source_host),
            'target_host': str(self.target_host),
            'compose_stack_path': self.compose_stack_path,
            'target_base_path': self.target_base_path,
            'use_zfs': self.use_zfs,
            'transfer_method': self.transfer_method,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration': self.duration,
            'steps_completed': completed_steps,
            'total_steps': total_steps,
            'error_message': self.error_message
        }
        
        # Add current step info
        current_step = self.get_current_step()
        if current_step:
            summary['current_step'] = {
                'name': current_step.name,
                'type': current_step.step_type.value,
                'progress': current_step.progress_percentage
            }
        
        # Add failed step info
        failed_step = self.get_failed_step()
        if failed_step:
            summary['failed_step'] = {
                'name': failed_step.name,
                'type': failed_step.step_type.value,
                'error': failed_step.error_message
            }
        
        return summary
    
    def estimate_remaining_time(self) -> Optional[float]:
        """Estimate remaining time in seconds based on completed steps"""
        completed_steps = self.get_completed_steps()
        if not completed_steps or not self.started_at:
            return None
        
        # Calculate average time per step
        total_duration = 0.0
        for step in completed_steps:
            if step.duration:
                total_duration += step.duration
        
        if total_duration == 0:
            return None
        
        avg_step_duration = total_duration / len(completed_steps)
        remaining_steps = len(self.get_pending_steps())
        
        # Add current step remaining time
        current_step = self.get_current_step()
        if current_step and current_step.progress_percentage > 0:
            current_step_remaining = (100 - current_step.progress_percentage) / 100 * avg_step_duration
            return (remaining_steps * avg_step_duration) + current_step_remaining
        
        return remaining_steps * avg_step_duration
    
    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to migration"""
        self.metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata value"""
        return self.metadata.get(key, default)