from dataclasses import dataclass
from typing import Optional, Dict, Any, Union
from datetime import datetime
from ..value_objects.dataset_name import DatasetName
from ..value_objects.size_value import SizeValue


@dataclass
class Dataset:
    """Dataset domain entity with business logic"""
    name: 'DatasetName'
    properties: Dict[str, str]
    used: Optional['SizeValue'] = None
    available: Optional['SizeValue'] = None
    referenced: Optional['SizeValue'] = None
    creation_time: Optional[datetime] = None
    parent_dataset: Optional['Dataset'] = None
    
    def is_encrypted(self) -> bool:
        """Check if dataset is encrypted"""
        encryption = self.properties.get('encryption', 'off')
        return encryption != 'off'
    
    def get_encryption_type(self) -> Optional[str]:
        """Get encryption type if dataset is encrypted"""
        if self.is_encrypted():
            return self.properties.get('encryption')
        return None
    
    def get_compression_ratio(self) -> float:
        """Get compression ratio as a float"""
        ratio_str = self.properties.get('compressratio', '1.00x')
        try:
            return float(ratio_str.rstrip('x'))
        except (ValueError, AttributeError):
            return 1.0
    
    def get_compression_type(self) -> str:
        """Get compression type"""
        return self.properties.get('compression', 'off')
    
    def is_compressed(self) -> bool:
        """Check if dataset uses compression"""
        compression = self.get_compression_type()
        return compression != 'off'
    
    def is_mounted(self) -> bool:
        """Check if dataset is mounted"""
        mountpoint = self.properties.get('mountpoint', 'none')
        return mountpoint not in ['none', '-', 'legacy']
    
    def get_mount_point(self) -> Optional[str]:
        """Get mount point if dataset is mounted"""
        mountpoint = self.properties.get('mountpoint')
        if mountpoint and mountpoint not in ['none', '-', 'legacy']:
            return mountpoint
        return None
    
    def get_quota(self) -> Optional['SizeValue']:
        """Get quota if set"""
        quota_str = self.properties.get('quota', 'none')
        if quota_str and quota_str != 'none':
            try:
                return SizeValue.from_zfs_string(quota_str)
            except ValueError:
                return None
        return None
    
    def get_reservation(self) -> Optional['SizeValue']:
        """Get reservation if set"""
        reservation_str = self.properties.get('reservation', 'none')
        if reservation_str and reservation_str != 'none':
            try:
                return SizeValue.from_zfs_string(reservation_str)
            except ValueError:
                return None
        return None
    
    def get_refquota(self) -> Optional['SizeValue']:
        """Get reference quota if set"""
        refquota_str = self.properties.get('refquota', 'none')
        if refquota_str and refquota_str != 'none':
            try:
                return SizeValue.from_zfs_string(refquota_str)
            except ValueError:
                return None
        return None
    
    def get_refreservation(self) -> Optional['SizeValue']:
        """Get reference reservation if set"""
        refreservation_str = self.properties.get('refreservation', 'none')
        if refreservation_str and refreservation_str != 'none':
            try:
                return SizeValue.from_zfs_string(refreservation_str)
            except ValueError:
                return None
        return None
    
    def is_quota_exceeded(self) -> bool:
        """Check if quota is exceeded"""
        quota = self.get_quota()
        if quota and self.used:
            return self.used > quota
        return False
    
    def get_quota_utilization(self) -> Optional[float]:
        """Get quota utilization as percentage (0-100)"""
        quota = self.get_quota()
        if quota and self.used and quota.bytes > 0:
            return (self.used.bytes / quota.bytes) * 100
        return None
    
    def is_readonly(self) -> bool:
        """Check if dataset is read-only"""
        readonly = self.properties.get('readonly', 'off')
        return readonly == 'on'
    
    def get_checksum_type(self) -> str:
        """Get checksum algorithm"""
        return self.properties.get('checksum', 'fletcher4')
    
    def get_recordsize(self) -> Optional['SizeValue']:
        """Get record size"""
        recordsize_str = self.properties.get('recordsize')
        if recordsize_str:
            try:
                return SizeValue.from_zfs_string(recordsize_str)
            except ValueError:
                return None
        return None
    
    def get_volsize(self) -> Optional['SizeValue']:
        """Get volume size for zvols"""
        volsize_str = self.properties.get('volsize')
        if volsize_str:
            try:
                return SizeValue.from_zfs_string(volsize_str)
            except ValueError:
                return None
        return None
    
    def is_zvol(self) -> bool:
        """Check if this is a zvol (volume)"""
        dataset_type = self.properties.get('type', 'filesystem')
        return dataset_type == 'volume'
    
    def is_snapshot(self) -> bool:
        """Check if this is a snapshot"""
        dataset_type = self.properties.get('type', 'filesystem')
        return dataset_type == 'snapshot'
    
    def is_filesystem(self) -> bool:
        """Check if this is a filesystem"""
        dataset_type = self.properties.get('type', 'filesystem')
        return dataset_type == 'filesystem'
    
    def get_origin(self) -> Optional[str]:
        """Get origin snapshot if dataset is a clone"""
        origin = self.properties.get('origin', '-')
        return origin if origin != '-' else None
    
    def is_clone(self) -> bool:
        """Check if dataset is a clone"""
        return self.get_origin() is not None
    
    def get_deduplication_ratio(self) -> float:
        """Get deduplication ratio"""
        dedup_str = self.properties.get('dedupratio', '1.00x')
        try:
            return float(dedup_str.rstrip('x'))
        except (ValueError, AttributeError):
            return 1.0
    
    def is_deduplication_enabled(self) -> bool:
        """Check if deduplication is enabled"""
        dedup = self.properties.get('dedup', 'off')
        return dedup != 'off'
    
    def get_atime_enabled(self) -> bool:
        """Check if access time updates are enabled"""
        atime = self.properties.get('atime', 'on')
        return atime == 'on'
    
    def get_sync_mode(self) -> str:
        """Get sync mode"""
        return self.properties.get('sync', 'standard')
    
    def get_copies(self) -> int:
        """Get number of copies"""
        copies_str = self.properties.get('copies', '1')
        try:
            return int(copies_str)
        except (ValueError, TypeError):
            return 1
    
    def get_space_efficiency(self) -> Dict[str, float]:
        """Get space efficiency metrics"""
        return {
            'compression_ratio': self.get_compression_ratio(),
            'deduplication_ratio': self.get_deduplication_ratio(),
            'total_efficiency': self.get_compression_ratio() * self.get_deduplication_ratio()
        }
    
    def get_health_status(self) -> Dict[str, Union[bool, float]]:
        """Get health status indicators"""
        status: Dict[str, Union[bool, float]] = {
            'quota_ok': not self.is_quota_exceeded(),
            'mounted': self.is_mounted(),
            'readonly': self.is_readonly(),
            'encrypted': self.is_encrypted(),
            'compressed': self.is_compressed(),
            'deduplication_enabled': self.is_deduplication_enabled()
        }
        
        # Add usage percentage as separate field
        if self.used and self.available:
            total_space = self.used + self.available
            if total_space.bytes > 0:
                status['usage_percentage'] = (self.used.bytes / total_space.bytes) * 100
        
        # Add quota utilization as separate field
        quota_util = self.get_quota_utilization()
        if quota_util is not None:
            status['quota_utilization'] = quota_util
        
        return status
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert dataset to dictionary for serialization"""
        result = {
            'name': str(self.name),
            'full_name': str(self.name),
            'pool': self.name.pool,
            'path': self.name.path,
            'properties': self.properties.copy(),
            'type': self.properties.get('type', 'filesystem'),
            'health_status': self.get_health_status(),
            'space_efficiency': self.get_space_efficiency()
        }
        
        # Add size information
        if self.used:
            result['used'] = self.used.to_dict()
        if self.available:
            result['available'] = self.available.to_dict()
        if self.referenced:
            result['referenced'] = self.referenced.to_dict()
        
        # Add creation time
        if self.creation_time:
            result['creation_time'] = self.creation_time.isoformat()
        
        # Add quota information
        quota = self.get_quota()
        if quota:
            result['quota'] = quota.to_dict()
        
        reservation = self.get_reservation()
        if reservation:
            result['reservation'] = reservation.to_dict()
        
        # Add mount point
        mount_point = self.get_mount_point()
        if mount_point:
            result['mount_point'] = mount_point
        
        # Add origin if clone
        origin = self.get_origin()
        if origin:
            result['origin'] = origin
        
        return result
    
    def __str__(self) -> str:
        """String representation"""
        return str(self.name)
    
    def __repr__(self) -> str:
        """Detailed string representation"""
        return f"Dataset(name={self.name}, type={self.properties.get('type', 'filesystem')}, used={self.used})" 