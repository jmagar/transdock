from pydantic import BaseModel, Field, computed_field
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from .utils import format_bytes


class TransferMethod(str, Enum):
    ZFS_SEND = "zfs_send"
    RSYNC = "rsync"


class IdentifierType(str, Enum):
    PROJECT = "project"
    NAME = "name" 
    LABELS = "labels"


class HostInfo(BaseModel):
    hostname: str
    ssh_user: str = Field(default="root")
    ssh_port: int = Field(default=22)


class StorageInfo(BaseModel):
    path: str
    total_bytes: int
    used_bytes: int
    available_bytes: int
    filesystem: str
    mount_point: str
    
    @computed_field
    def total_human(self) -> str:
        return format_bytes(self.total_bytes)
    
    @computed_field
    def used_human(self) -> str:
        return format_bytes(self.used_bytes)
    
    @computed_field
    def available_human(self) -> str:
        return format_bytes(self.available_bytes)
    
    @computed_field
    def usage_percent(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return (self.used_bytes / self.total_bytes) * 100


class StorageValidationResult(BaseModel):
    is_valid: bool
    required_bytes: int
    available_bytes: int
    storage_path: str
    error_message: Optional[str] = None
    warning_message: Optional[str] = None
    safety_margin_bytes: int = 0
    
    @computed_field
    def required_human(self) -> str:
        return format_bytes(self.required_bytes)
    
    @computed_field
    def available_human(self) -> str:
        return format_bytes(self.available_bytes)
    
    @computed_field
    def safety_margin_human(self) -> str:
        return format_bytes(self.safety_margin_bytes)
    
    @computed_field
    def total_required_human(self) -> str:
        return format_bytes(self.required_bytes + self.safety_margin_bytes)


class MigrationStorageRequirement(BaseModel):
    source_size_bytes: int
    target_path: str
    estimated_transfer_size_bytes: int
    zfs_snapshot_overhead_bytes: int = 0
    safety_margin_factor: float = 1.2  # 20% safety margin
    
    @computed_field
    def source_size_human(self) -> str:
        return format_bytes(self.source_size_bytes)
    
    @computed_field
    def estimated_transfer_size_human(self) -> str:
        return format_bytes(self.estimated_transfer_size_bytes)
    
    @computed_field
    def zfs_snapshot_overhead_human(self) -> str:
        return format_bytes(self.zfs_snapshot_overhead_bytes)
    
    @computed_field
    def total_requirement_human(self) -> str:
        total = self.estimated_transfer_size_bytes + self.zfs_snapshot_overhead_bytes
        return format_bytes(total)


class HostCapabilities(BaseModel):
    hostname: str
    docker_available: bool
    zfs_available: bool
    compose_paths: List[str] = []
    appdata_paths: List[str] = []
    zfs_pools: List[str] = []
    storage_info: List[StorageInfo] = []
    error: Optional[str] = None


class RemoteStack(BaseModel):
    name: str
    path: str
    compose_file: str
    services: List[str] = []
    status: str = "unknown"  # running, stopped, partial, unknown


class ContainerMigrationRequest(BaseModel):
    """Request model for container-based migration"""
    # Container identification
    container_identifier: str = Field(..., description="Container name, project name, or label selector")
    identifier_type: IdentifierType = Field(..., description="Type of identifier: project, name, or labels")
    label_filters: Optional[Dict[str, str]] = Field(None, description="Label filters when using labels identifier type")
    
    # Source host information (None for local)
    source_host: Optional[str] = Field(None, description="Source machine hostname or IP (None for local)")
    source_ssh_user: str = Field(default="root", description="SSH username for source machine")
    source_ssh_port: int = Field(default=22, description="SSH port for source machine")
    
    # Target host information  
    target_host: str = Field(..., description="Target machine hostname or IP")
    target_base_path: str = Field(..., description="Target base folder for data")
    ssh_user: str = Field(default="root", description="SSH username for target machine")
    ssh_port: int = Field(default=22, description="SSH port for target machine")
    force_rsync: bool = Field(default=False, description="Force rsync even if target has ZFS")


class MigrationRequest(BaseModel):
    # Source host information
    source_host: Optional[str] = Field(None, description="Source machine hostname or IP (None for local)")
    source_ssh_user: str = Field(default="root", description="SSH username for source machine")
    source_ssh_port: int = Field(default=22, description="SSH port for source machine")
    
    # Source stack information
    compose_dataset: str = Field(
        ..., description="Source compose dataset path (e.g., cache/compose/authelia)")
    
    # Target host information
    target_host: str = Field(..., description="Target machine hostname or IP")
    target_base_path: str = Field(...,
                                  description="Target base folder (e.g., /home/jmagar)")
    ssh_user: str = Field(
        default="root",
        description="SSH username for target machine")
    ssh_port: int = Field(
        default=22,
        description="SSH port for target machine")
    force_rsync: bool = Field(default=False,
                              description="Force rsync even if target has ZFS")


class VolumeMount(BaseModel):
    source: str
    target: str
    dataset_path: Optional[str] = None
    is_dataset: bool = False


class ContainerDiscoveryResult(BaseModel):
    """Result of container discovery operation"""
    containers: List[Dict[str, Any]]
    total_containers: int
    discovery_method: str
    query: str


class ContainerSummary(BaseModel):
    """Summary information about discovered containers"""
    id: str
    name: str
    image: str
    state: str
    status: str
    project_name: Optional[str] = None
    service_name: Optional[str] = None
    volume_count: int = 0
    network_count: int = 0
    port_count: int = 0


class NetworkSummary(BaseModel):
    """Summary of Docker network information"""
    id: str
    name: str
    driver: str
    scope: str
    project_name: Optional[str] = None


class MigrationStatus(BaseModel):
    id: str
    status: str
    progress: int
    message: str
    # Source information
    source_host: Optional[str] = None
    compose_dataset: str
    # Target information
    target_host: str
    target_base_path: str
    volumes: List[VolumeMount] = []
    transfer_method: Optional[TransferMethod] = None
    error: Optional[str] = None
    snapshots: List[str] = []
    target_compose_path: Optional[str] = None
    volume_mapping: Optional[Dict[str, str]] = None
    # Storage validation information
    storage_validation_results: Optional[Dict[str, StorageValidationResult]] = None
    estimated_storage_requirement: Optional[MigrationStorageRequirement] = None
    # Container-specific information
    containers: Optional[List[Dict[str, Any]]] = None
    networks: Optional[List[Dict[str, Any]]] = None


class MigrationResponse(BaseModel):
    migration_id: str
    status: str
    message: str


class StackAnalysis(BaseModel):
    name: str
    path: str
    compose_file: str
    services: Dict[str, Dict] = {}
    volumes: List[VolumeMount] = []
    networks: List[str] = []
    external_volumes: List[str] = []
    estimated_size: Optional[int] = None
    zfs_compatible: bool = False
    storage_requirement: Optional[MigrationStorageRequirement] = None


class ContainerAnalysis(BaseModel):
    """Analysis of containers for migration"""
    containers: List[ContainerSummary]
    networks: List[NetworkSummary]
    total_volumes: int
    total_bind_mounts: int
    estimated_data_size: Optional[int] = None
    migration_complexity: str = "simple"  # simple, medium, complex
    warnings: List[str] = []
    recommendations: List[str] = []


class HostValidationRequest(BaseModel):
    hostname: str
    ssh_user: str = Field(default="root")
    ssh_port: int = Field(default=22)
    check_docker: bool = Field(default=True)
    check_zfs: bool = Field(default=True)
    discover_paths: bool = Field(default=True)
