"""
Snapshot domain entity with business logic and relationships.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..value_objects.dataset_name import DatasetName
from ..value_objects.size_value import SizeValue


@dataclass
class Snapshot:
    """Domain entity representing a ZFS snapshot with business logic."""
    
    name: str
    dataset: DatasetName
    creation_time: datetime
    used: SizeValue
    referenced: SizeValue
    properties: Dict[str, str] = field(default_factory=dict)
    clones: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate snapshot after initialization."""
        if not self.name:
            raise ValueError("Snapshot name cannot be empty")
        
        if '@' in self.name:
            raise ValueError("Snapshot name should not contain '@' - use dataset@snapshot format")
        
        if not isinstance(self.dataset, DatasetName):
            raise ValueError("Dataset must be a DatasetName instance")
        
        if not isinstance(self.used, SizeValue):
            raise ValueError("Used size must be a SizeValue instance")
        
        if not isinstance(self.referenced, SizeValue):
            raise ValueError("Referenced size must be a SizeValue instance")
    
    @property
    def full_name(self) -> str:
        """Get the full snapshot name including dataset."""
        return f"{self.dataset}@{self.name}"
    
    @property
    def short_name(self) -> str:
        """Get just the snapshot name without dataset."""
        return self.name
    
    def has_clones(self) -> bool:
        """Check if this snapshot has any clones."""
        return len(self.clones) > 0
    
    @property
    def clone_count(self) -> int:
        """Get the number of clones for this snapshot."""
        return len(self.clones)
    
    def is_writable(self) -> bool:
        """Check if snapshot is writable (snapshots are read-only by default)."""
        return False  # Snapshots are always read-only
    
    def get_space_efficiency(self) -> float:
        """Calculate space efficiency ratio (used/referenced)."""
        if self.referenced.bytes == 0:
            return 0.0
        return self.used.bytes / self.referenced.bytes
    
    def is_space_efficient(self, threshold: float = 0.8) -> bool:
        """Check if snapshot is space efficient (low used/referenced ratio)."""
        return self.get_space_efficiency() < threshold
    
    def get_age_days(self) -> int:
        """Get the age of the snapshot in days."""
        now = datetime.utcnow()
        delta = now - self.creation_time
        return delta.days
    
    def is_old(self, days: int = 30) -> bool:
        """Check if snapshot is older than specified days."""
        return self.get_age_days() > days
    
    def is_recent(self, days: int = 7) -> bool:
        """Check if snapshot is newer than specified days."""
        return self.get_age_days() < days
    
    def can_be_destroyed(self) -> bool:
        """Check if snapshot can be safely destroyed (no clones)."""
        return not self.has_clones()
    
    def get_property(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Get a specific property value."""
        return self.properties.get(name, default)
    
    def is_encrypted(self) -> bool:
        """Check if the snapshot's dataset is encrypted."""
        return self.get_property('encryption', 'off') != 'off'
    
    def get_compression_ratio(self) -> float:
        """Get compression ratio for the snapshot."""
        ratio_str = self.get_property('compressratio', '1.00x')
        try:
            if ratio_str:
                return float(ratio_str.rstrip('x'))
            return 1.0
        except (ValueError, AttributeError):
            return 1.0
    
    def is_compressed(self) -> bool:
        """Check if the snapshot uses compression."""
        return self.get_compression_ratio() > 1.0
    
    def get_deduplication_ratio(self) -> float:
        """Get deduplication ratio for the snapshot."""
        ratio_str = self.get_property('dedupratio', '1.00x')
        try:
            if ratio_str:
                return float(ratio_str.rstrip('x'))
            return 1.0
        except (ValueError, AttributeError):
            return 1.0
    
    def is_deduplicated(self) -> bool:
        """Check if the snapshot benefits from deduplication."""
        return self.get_deduplication_ratio() > 1.0
    
    def get_origin(self) -> Optional[str]:
        """Get the origin snapshot if this is a clone."""
        return self.get_property('origin')
    
    def is_clone(self) -> bool:
        """Check if this snapshot is actually a clone."""
        return self.get_origin() is not None
    
    def get_written_since_creation(self) -> SizeValue:
        """Get the amount of data written since snapshot creation."""
        # This would be calculated based on the difference between
        # the parent dataset's used space and the snapshot's referenced space
        return SizeValue(max(0, self.referenced.bytes - self.used.bytes))
    
    def get_unique_data(self) -> SizeValue:
        """Get the amount of unique data in this snapshot."""
        return self.used
    
    def get_shared_data(self) -> SizeValue:
        """Get the amount of shared data referenced by this snapshot."""
        return SizeValue(max(0, self.referenced.bytes - self.used.bytes))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dictionary representation."""
        return {
            'name': self.name,
            'full_name': self.full_name,
            'dataset': str(self.dataset),
            'creation_time': self.creation_time.isoformat(),
            'used': self.used.bytes,
            'used_human': self.used.to_human_readable(),
            'referenced': self.referenced.bytes,
            'referenced_human': self.referenced.to_human_readable(),
            'properties': self.properties,
            'clones': self.clones,
            'clone_count': self.clone_count,
            'has_clones': self.has_clones(),
            'age_days': self.get_age_days(),
            'is_old': self.is_old(),
            'is_recent': self.is_recent(),
            'can_be_destroyed': self.can_be_destroyed(),
            'is_encrypted': self.is_encrypted(),
            'is_compressed': self.is_compressed(),
            'is_deduplicated': self.is_deduplicated(),
            'is_clone': self.is_clone(),
            'space_efficiency': self.get_space_efficiency(),
            'compression_ratio': self.get_compression_ratio(),
            'deduplication_ratio': self.get_deduplication_ratio(),
        }
    
    def __str__(self) -> str:
        """String representation of snapshot."""
        return f"Snapshot({self.full_name})"
    
    def __repr__(self) -> str:
        """Detailed representation of snapshot."""
        return (f"Snapshot(name='{self.name}', dataset={self.dataset}, "
                f"used={self.used.to_human_readable()}, "
                f"referenced={self.referenced.to_human_readable()}, "
                f"clones={self.clone_count})")


@dataclass
class SnapshotPolicy:
    """Snapshot retention policy configuration."""
    
    keep_hourly: int = 24
    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 12
    keep_yearly: int = 5
    
    def should_keep_snapshot(self, snapshot: Snapshot, all_snapshots: List[Snapshot]) -> bool:
        """Determine if a snapshot should be kept based on retention policy."""
        age_days = snapshot.get_age_days()
        
        # Always keep recent snapshots
        if age_days < 1:
            return True
        
        # Check if snapshot represents a time period we want to keep
        if age_days <= self.keep_daily:
            return True
        elif age_days <= self.keep_weekly * 7:
            return self._is_weekly_keeper(snapshot, all_snapshots)
        elif age_days <= self.keep_monthly * 30:
            return self._is_monthly_keeper(snapshot, all_snapshots)
        elif age_days <= self.keep_yearly * 365:
            return self._is_yearly_keeper(snapshot, all_snapshots)
        
        return False
    
    def _is_weekly_keeper(self, snapshot: Snapshot, all_snapshots: List[Snapshot]) -> bool:
        """Check if snapshot should be kept as weekly backup."""
        # Implementation would check if this is the oldest snapshot in its week
        return snapshot.creation_time.weekday() == 0  # Keep Monday snapshots
    
    def _is_monthly_keeper(self, snapshot: Snapshot, all_snapshots: List[Snapshot]) -> bool:
        """Check if snapshot should be kept as monthly backup."""
        # Implementation would check if this is the oldest snapshot in its month
        return snapshot.creation_time.day == 1  # Keep first day of month
    
    def _is_yearly_keeper(self, snapshot: Snapshot, all_snapshots: List[Snapshot]) -> bool:
        """Check if snapshot should be kept as yearly backup."""
        # Implementation would check if this is the oldest snapshot in its year
        return (snapshot.creation_time.month == 1 and 
                snapshot.creation_time.day == 1)  # Keep January 1st snapshots 