"""SnapshotName value object"""

from dataclasses import dataclass
from typing import Tuple
import re
from datetime import datetime
from ..exceptions.validation_exceptions import InvalidSnapshotNameError
from .dataset_name import DatasetName


@dataclass(frozen=True)
class SnapshotName:
    """Immutable value object for ZFS snapshot names"""
    
    full_name: str  # Format: dataset@snapshot
    
    def __post_init__(self):
        if not self.full_name:
            raise InvalidSnapshotNameError("Snapshot name cannot be empty")
        
        if '@' not in self.full_name:
            raise InvalidSnapshotNameError("Snapshot name must contain '@' separator")
        
        parts = self.full_name.split('@')
        if len(parts) != 2:
            raise InvalidSnapshotNameError("Snapshot name must have exactly one '@' separator")
        
        dataset_part, snapshot_part = parts
        
        if not dataset_part:
            raise InvalidSnapshotNameError("Dataset part cannot be empty")
        
        if not snapshot_part:
            raise InvalidSnapshotNameError("Snapshot part cannot be empty")
        
        # Validate dataset name part
        try:
            DatasetName(dataset_part)
        except Exception as e:
            raise InvalidSnapshotNameError(f"Invalid dataset part: {e}")
        
        # Validate snapshot name part
        if len(snapshot_part) > 255:
            raise InvalidSnapshotNameError("Snapshot name part cannot exceed 255 characters")
        
        # Snapshot name validation (more restrictive than dataset names)
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_\-.]*$', snapshot_part):
            raise InvalidSnapshotNameError(
                f"Invalid snapshot name: {snapshot_part}. "
                "Must start with alphanumeric and contain only letters, numbers, hyphens, underscores, and dots."
            )
    
    @classmethod
    def create(cls, dataset: DatasetName, snapshot_name: str) -> 'SnapshotName':
        """Create snapshot name from dataset and snapshot parts"""
        return cls(f"{dataset.value}@{snapshot_name}")
    
    @classmethod
    def create_timestamped(cls, dataset: DatasetName, prefix: str = "transdock") -> 'SnapshotName':
        """Create a timestamped snapshot name"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_name = f"{prefix}_{timestamp}"
        return cls.create(dataset, snapshot_name)
    
    def dataset_name(self) -> DatasetName:
        """Get the dataset name part"""
        dataset_part = self.full_name.split('@')[0]
        return DatasetName(dataset_part)
    
    def snapshot_part(self) -> str:
        """Get just the snapshot name part (after @)"""
        return self.full_name.split('@')[1]
    
    def split(self) -> Tuple[DatasetName, str]:
        """Split into dataset and snapshot parts"""
        return self.dataset_name(), self.snapshot_part()
    
    def is_transdock_snapshot(self) -> bool:
        """Check if this is a TransDock-created snapshot"""
        return self.snapshot_part().startswith('transdock_')
    
    def is_timestamped(self) -> bool:
        """Check if snapshot name contains a timestamp pattern"""
        snapshot_part = self.snapshot_part()
        # Look for YYYYMMDD_HHMMSS pattern
        return bool(re.search(r'\d{8}_\d{6}', snapshot_part))
    
    def get_timestamp(self) -> datetime:
        """Extract timestamp from snapshot name if present"""
        snapshot_part = self.snapshot_part()
        match = re.search(r'(\d{8}_\d{6})', snapshot_part)
        if match:
            timestamp_str = match.group(1)
            try:
                return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            except ValueError:
                pass
        raise InvalidSnapshotNameError(f"No valid timestamp found in snapshot name: {snapshot_part}")
    
    def with_dataset(self, new_dataset: DatasetName) -> 'SnapshotName':
        """Create new snapshot name with different dataset"""
        return SnapshotName.create(new_dataset, self.snapshot_part())
    
    def __str__(self) -> str:
        return self.full_name
    
    def __repr__(self) -> str:
        return f"SnapshotName('{self.full_name}')"