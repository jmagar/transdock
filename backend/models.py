from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum


class TransferMethod(str, Enum):
    ZFS_SEND = "zfs_send"
    RSYNC = "rsync"


class HostInfo(BaseModel):
    hostname: str
    ssh_user: str = Field(default="root")
    ssh_port: int = Field(default=22)


class HostCapabilities(BaseModel):
    hostname: str
    docker_available: bool
    zfs_available: bool
    compose_paths: List[str] = []
    appdata_paths: List[str] = []
    zfs_pools: List[str] = []
    error: Optional[str] = None


class RemoteStack(BaseModel):
    name: str
    path: str
    compose_file: str
    services: List[str] = []
    status: str = "unknown"  # running, stopped, partial, unknown


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


class HostValidationRequest(BaseModel):
    hostname: str
    ssh_user: str = Field(default="root")
    ssh_port: int = Field(default=22)
    check_docker: bool = Field(default=True)
    check_zfs: bool = Field(default=True)
    discover_paths: bool = Field(default=True)
