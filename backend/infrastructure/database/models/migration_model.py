"""Migration database models"""

from sqlalchemy import Column, String, DateTime, JSON, Enum, ForeignKey, Float, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from ..config import Base


class MigrationStatusEnum(str, enum.Enum):
    """Migration status enumeration for database"""
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


class MigrationStepTypeEnum(str, enum.Enum):
    """Migration step type enumeration for database"""
    VALIDATION = "validation"
    SNAPSHOT_CREATION = "snapshot_creation"
    DATA_TRANSFER = "data_transfer"
    CONTAINER_RECREATION = "container_recreation"
    SERVICE_START = "service_start"
    VERIFICATION = "verification"
    CLEANUP = "cleanup"


class MigrationStepStatusEnum(str, enum.Enum):
    """Migration step status enumeration for database"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class MigrationModel(Base):
    """Migration database model"""
    __tablename__ = "migrations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    status = Column(Enum(MigrationStatusEnum), nullable=False, default=MigrationStatusEnum.PENDING)
    
    # Host information
    source_host = Column(String(255), nullable=False, default="localhost")
    source_port = Column(String(10), nullable=True)
    source_username = Column(String(255), nullable=True)
    target_host = Column(String(255), nullable=False)
    target_port = Column(String(10), nullable=True)
    target_username = Column(String(255), nullable=True)
    
    # Migration configuration
    compose_stack_path = Column(Text, nullable=False)
    target_base_path = Column(Text, nullable=False)
    use_zfs = Column(String(10), nullable=False, default="true")
    transfer_method = Column(String(50), nullable=False, default="zfs_send")
    cleanup_on_success = Column(String(10), nullable=False, default="true")
    verify_transfer = Column(String(10), nullable=False, default="true")
    create_backup_snapshot = Column(String(10), nullable=False, default="true")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Error information
    error_message = Column(Text, nullable=True)
    
    # Metadata storage
    metadata = Column(JSON, nullable=False, default=dict)
    
    # Docker Compose specific fields
    compose_project_name = Column(String(255), nullable=True)
    compose_file_content = Column(Text, nullable=True)
    compose_env_content = Column(Text, nullable=True)
    
    # Relationships
    steps = relationship("MigrationStepModel", back_populates="migration", cascade="all, delete-orphan")
    snapshots = relationship("MigrationSnapshotModel", back_populates="migration", cascade="all, delete-orphan")


class MigrationStepModel(Base):
    """Migration step database model"""
    __tablename__ = "migration_steps"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    migration_id = Column(UUID(as_uuid=True), ForeignKey("migrations.id"), nullable=False)
    
    name = Column(String(255), nullable=False)
    step_type = Column(Enum(MigrationStepTypeEnum), nullable=False)
    status = Column(Enum(MigrationStepStatusEnum), nullable=False, default=MigrationStepStatusEnum.PENDING)
    
    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Progress and error tracking
    progress_percentage = Column(Float, nullable=False, default=0.0)
    error_message = Column(Text, nullable=True)
    
    # Step details
    details = Column(JSON, nullable=False, default=dict)
    
    # Relationship
    migration = relationship("MigrationModel", back_populates="steps")


class MigrationSnapshotModel(Base):
    """Migration snapshot tracking model"""
    __tablename__ = "migration_snapshots"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    migration_id = Column(UUID(as_uuid=True), ForeignKey("migrations.id"), nullable=False)
    
    full_name = Column(String(500), nullable=False, unique=True)
    dataset_name = Column(String(500), nullable=False)
    snapshot_part = Column(String(255), nullable=False)
    
    # Snapshot metadata
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    is_deleted = Column(String(10), nullable=False, default="false")
    
    # Transfer status
    transfer_started_at = Column(DateTime(timezone=True), nullable=True)
    transfer_completed_at = Column(DateTime(timezone=True), nullable=True)
    transfer_status = Column(String(50), nullable=True)
    
    # Relationship
    migration = relationship("MigrationModel", back_populates="snapshots")