"""ZFS domain entities"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
from ..value_objects.dataset_name import DatasetName
from ..value_objects.storage_size import StorageSize
from ..value_objects.snapshot_name import SnapshotName


class ZFSDatasetType(Enum):
    """ZFS dataset types"""
    FILESYSTEM = "filesystem"
    VOLUME = "volume"


class ZFSPoolStatus(Enum):
    """ZFS pool status"""
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    FAULTED = "FAULTED"
    OFFLINE = "OFFLINE"
    UNAVAIL = "UNAVAIL"
    REMOVED = "REMOVED"


@dataclass
class ZFSDataset:
    """ZFS Dataset domain entity"""
    
    name: DatasetName
    dataset_type: ZFSDatasetType = ZFSDatasetType.FILESYSTEM
    properties: Dict[str, str] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    @property
    def used_space(self) -> Optional[StorageSize]:
        """Get used space from properties"""
        used_str = self.properties.get('used')
        if used_str:
            return StorageSize.from_zfs_string(used_str)
        return None
    
    @property
    def available_space(self) -> Optional[StorageSize]:
        """Get available space from properties"""
        available_str = self.properties.get('available')
        if available_str:
            return StorageSize.from_zfs_string(available_str)
        return None
    
    @property
    def referenced_space(self) -> Optional[StorageSize]:
        """Get referenced space from properties"""
        referenced_str = self.properties.get('referenced')
        if referenced_str:
            return StorageSize.from_zfs_string(referenced_str)
        return None
    
    @property
    def mount_point(self) -> Optional[str]:
        """Get mount point from properties"""
        return self.properties.get('mountpoint')
    
    @property
    def compression(self) -> str:
        """Get compression setting"""
        return self.properties.get('compression', 'off')
    
    @property
    def quota(self) -> Optional[StorageSize]:
        """Get quota from properties"""
        quota_str = self.properties.get('quota')
        if quota_str and quota_str != 'none':
            return StorageSize.from_zfs_string(quota_str)
        return None
    
    @property
    def reservation(self) -> Optional[StorageSize]:
        """Get reservation from properties"""
        reservation_str = self.properties.get('reservation')
        if reservation_str and reservation_str != 'none':
            return StorageSize.from_zfs_string(reservation_str)
        return None
    
    def is_mounted(self) -> bool:
        """Check if dataset is mounted"""
        mountpoint = self.mount_point
        return bool(mountpoint and mountpoint not in ['none', '-'])
    
    def can_create_snapshot(self) -> bool:
        """Check if dataset can create snapshots"""
        return self.properties.get('readonly') != 'on'
    
    def is_encrypted(self) -> bool:
        """Check if dataset is encrypted"""
        encryption = self.properties.get('encryption', 'off')
        return encryption != 'off'
    
    def is_compressed(self) -> bool:
        """Check if dataset has compression enabled"""
        compression = self.properties.get('compression', 'off')
        return compression != 'off'
    
    def pool_name(self) -> str:
        """Get the pool name this dataset belongs to"""
        return self.name.pool_name()
    
    def parent_dataset(self) -> Optional[DatasetName]:
        """Get parent dataset name"""
        return self.name.parent()
    
    def is_child_of(self, parent: DatasetName) -> bool:
        """Check if this dataset is a child of the given parent"""
        parent_name = self.parent_dataset()
        return parent_name is not None and str(parent_name) == str(parent)


@dataclass
class ZFSSnapshot:
    """ZFS Snapshot domain entity"""
    
    name: SnapshotName
    created_at: datetime
    properties: Dict[str, str] = field(default_factory=dict)
    
    @property
    def dataset_name(self) -> DatasetName:
        """Get the dataset this snapshot belongs to"""
        return self.name.dataset_name()
    
    @property
    def snapshot_part(self) -> str:
        """Get just the snapshot name part"""
        return self.name.snapshot_part()
    
    @property
    def full_name(self) -> str:
        """Get full snapshot name (dataset@snapshot)"""
        return str(self.name)
    
    @property
    def size(self) -> Optional[StorageSize]:
        """Get snapshot size"""
        used_str = self.properties.get('used')
        if used_str:
            return StorageSize.from_zfs_string(used_str)
        return None
    
    @property
    def referenced_size(self) -> Optional[StorageSize]:
        """Get referenced size"""
        referenced_str = self.properties.get('referenced')
        if referenced_str:
            return StorageSize.from_zfs_string(referenced_str)
        return None
    
    def can_rollback(self) -> bool:
        """Check if snapshot can be rolled back to"""
        # Basic check - can be enhanced with more business rules
        return True
    
    def can_clone(self) -> bool:
        """Check if snapshot can be cloned"""
        # Basic check - can be enhanced with more business rules
        return True
    
    def is_transdock_snapshot(self) -> bool:
        """Check if this is a TransDock-created snapshot"""
        return self.name.is_transdock_snapshot()
    
    def is_timestamped(self) -> bool:
        """Check if snapshot has a timestamp"""
        return self.name.is_timestamped()
    
    def get_timestamp(self) -> datetime:
        """Get timestamp from snapshot name"""
        return self.name.get_timestamp()
    
    def pool_name(self) -> str:
        """Get the pool name this snapshot belongs to"""
        return self.dataset_name.pool_name()


@dataclass
class ZFSPool:
    """ZFS Pool domain entity"""
    
    name: str
    status: ZFSPoolStatus
    properties: Dict[str, str] = field(default_factory=dict)
    datasets: List[DatasetName] = field(default_factory=list)
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    @property
    def total_size(self) -> Optional[StorageSize]:
        """Get total pool size"""
        size_str = self.properties.get('size')
        if size_str:
            return StorageSize.from_zfs_string(size_str)
        return None
    
    @property
    def allocated_size(self) -> Optional[StorageSize]:
        """Get allocated space"""
        allocated_str = self.properties.get('allocated')
        if allocated_str:
            return StorageSize.from_zfs_string(allocated_str)
        return None
    
    @property
    def used_size(self) -> Optional[StorageSize]:
        """Get used space - alias for allocated_size"""
        return self.allocated_size
    
    @property
    def free_size(self) -> Optional[StorageSize]:
        """Get free space"""
        free_str = self.properties.get('free')
        if free_str:
            return StorageSize.from_zfs_string(free_str)
        return None
    
    @property
    def health(self) -> ZFSPoolStatus:
        """Get pool health status"""
        health_str = self.properties.get('health', 'UNKNOWN')
        try:
            return ZFSPoolStatus(health_str)
        except ValueError:
            return ZFSPoolStatus.OFFLINE
    
    @property
    def capacity_percentage(self) -> float:
        """Get capacity usage as percentage"""
        capacity_str = self.properties.get('capacity', '0%')
        try:
            return float(capacity_str.rstrip('%'))
        except (ValueError, AttributeError):
            return 0.0
    
    @property
    def version(self) -> Optional[str]:
        """Get pool version"""
        return self.properties.get('version')
    
    @property
    def guid(self) -> Optional[str]:
        """Get pool GUID"""
        return self.properties.get('guid')
    
    @property
    def altroot(self) -> Optional[str]:
        """Get pool altroot"""
        return self.properties.get('altroot')
    
    @property
    def readonly(self) -> bool:
        """Check if pool is readonly"""
        return self.properties.get('readonly', 'off') == 'on'
    
    def usage_percentage(self) -> float:
        """Get usage percentage"""
        return self.capacity_percentage
    
    def is_healthy(self) -> bool:
        """Check if pool is healthy"""
        return self.status == ZFSPoolStatus.ONLINE and self.health == ZFSPoolStatus.ONLINE
    
    def is_degraded(self) -> bool:
        """Check if pool is degraded"""
        return self.status == ZFSPoolStatus.DEGRADED
    
    def is_faulted(self) -> bool:
        """Check if pool is faulted"""
        return self.status == ZFSPoolStatus.FAULTED
    
    def has_errors(self) -> bool:
        """Check if pool has errors"""
        return self.status in [ZFSPoolStatus.DEGRADED, ZFSPoolStatus.FAULTED]
    
    def needs_attention(self) -> bool:
        """Check if pool needs attention"""
        return not self.is_healthy()
    
    def can_be_exported(self) -> bool:
        """Check if pool can be exported"""
        return self.is_healthy() and not self.readonly
    
    def dedup_ratio(self) -> float:
        """Get deduplication ratio"""
        dedup_str = self.properties.get('dedupratio', '1.00x')
        try:
            return float(dedup_str.replace('x', ''))
        except (ValueError, AttributeError):
            return 1.0
    
    def compression_ratio(self) -> float:
        """Get compression ratio"""
        compression_str = self.properties.get('compressratio', '1.00x')
        try:
            return float(compression_str.replace('x', ''))
        except (ValueError, AttributeError):
            return 1.0
    
    def has_sufficient_space(self, required: StorageSize) -> bool:
        """Check if pool has sufficient free space"""
        free = self.free_size
        return free is not None and free >= required
    
    def get_usage_info(self) -> Dict[str, Any]:
        """Get comprehensive usage information"""
        return {
            'total': self.total_size,
            'allocated': self.allocated_size,
            'used': self.used_size,
            'free': self.free_size,
            'capacity_percentage': self.capacity_percentage,
            'health': self.health.value,
            'status': self.status.value,
            'dataset_count': len(self.datasets),
            'version': self.version,
            'guid': self.guid,
            'readonly': self.readonly,
            'dedup_ratio': self.dedup_ratio(),
            'compression_ratio': self.compression_ratio()
        }