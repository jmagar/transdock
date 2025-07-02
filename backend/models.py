from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum

class TransferMethod(str, Enum):
    ZFS_SEND = "zfs_send"
    RSYNC = "rsync"

class MigrationRequest(BaseModel):
    compose_dataset: str = Field(..., description="Source compose dataset path (e.g., cache/compose/authelia)")
    target_host: str = Field(..., description="Target machine hostname or IP")
    target_base_path: str = Field(..., description="Target base folder (e.g., /home/jmagar)")
    ssh_user: str = Field(default="root", description="SSH username for target machine")
    ssh_port: int = Field(default=22, description="SSH port for target machine")
    force_rsync: bool = Field(default=False, description="Force rsync even if target has ZFS")

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
    compose_dataset: str
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