"""ZFS repository interfaces"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from ..entities.zfs_entity import ZFSDataset, ZFSSnapshot, ZFSPool
from ..value_objects.dataset_name import DatasetName
from ..value_objects.snapshot_name import SnapshotName


class ZFSDatasetRepository(ABC):
    """Repository interface for ZFS datasets"""
    
    @abstractmethod
    async def create(self, dataset: ZFSDataset) -> bool:
        """Create a new dataset"""
        pass
    
    @abstractmethod
    async def find_by_name(self, name: DatasetName) -> Optional[ZFSDataset]:
        """Find dataset by name"""
        pass
    
    @abstractmethod
    async def list_all(self) -> List[ZFSDataset]:
        """List all datasets"""
        pass
    
    @abstractmethod
    async def list_by_pool(self, pool_name: str) -> List[ZFSDataset]:
        """List datasets in a specific pool"""
        pass
    
    @abstractmethod
    async def update_properties(self, name: DatasetName, properties: Dict[str, str]) -> bool:
        """Update dataset properties"""
        pass
    
    @abstractmethod
    async def delete(self, name: DatasetName, force: bool = False) -> bool:
        """Delete a dataset"""
        pass
    
    @abstractmethod
    async def exists(self, name: DatasetName) -> bool:
        """Check if dataset exists"""
        pass
    
    @abstractmethod
    async def get_properties(self, name: DatasetName, properties: Optional[List[str]] = None) -> Dict[str, str]:
        """Get dataset properties"""
        pass
    
    @abstractmethod
    async def set_property(self, name: DatasetName, property_name: str, value: str) -> bool:
        """Set a single dataset property"""
        pass
    
    @abstractmethod
    async def get_usage(self, name: DatasetName) -> Dict[str, Any]:
        """Get dataset usage information"""
        pass


class ZFSSnapshotRepository(ABC):
    """Repository interface for ZFS snapshots"""
    
    @abstractmethod
    async def create(self, dataset: DatasetName, snapshot_name: str) -> ZFSSnapshot:
        """Create a new snapshot"""
        pass
    
    @abstractmethod
    async def find_by_name(self, name: SnapshotName) -> Optional[ZFSSnapshot]:
        """Find snapshot by full name"""
        pass
    
    @abstractmethod
    async def list_for_dataset(self, dataset: DatasetName) -> List[ZFSSnapshot]:
        """List all snapshots for a dataset"""
        pass
    
    @abstractmethod
    async def list_all(self) -> List[ZFSSnapshot]:
        """List all snapshots"""
        pass
    
    @abstractmethod
    async def delete(self, name: SnapshotName) -> bool:
        """Delete a snapshot"""
        pass
    
    @abstractmethod
    async def rollback(self, name: SnapshotName, force: bool = False) -> bool:
        """Rollback to a snapshot"""
        pass
    
    @abstractmethod
    async def clone(self, name: SnapshotName, target_dataset: DatasetName) -> bool:
        """Clone a snapshot to create a new dataset"""
        pass
    
    @abstractmethod
    async def send(self, name: SnapshotName, target_host: str, target_dataset: DatasetName) -> bool:
        """Send snapshot to remote host"""
        pass
    
    @abstractmethod
    async def send_incremental(self, base_snapshot: SnapshotName, incremental_snapshot: SnapshotName, 
                             target_host: str, target_dataset: DatasetName) -> bool:
        """Send incremental snapshot to remote host"""
        pass
    
    @abstractmethod
    async def get_properties(self, name: SnapshotName) -> Dict[str, str]:
        """Get snapshot properties"""
        pass


class ZFSPoolRepository(ABC):
    """Repository interface for ZFS pools"""
    
    @abstractmethod
    async def find_by_name(self, name: str) -> Optional[ZFSPool]:
        """Find pool by name"""
        pass
    
    @abstractmethod
    async def list_all(self) -> List[ZFSPool]:
        """List all pools"""
        pass
    
    @abstractmethod
    async def get_status(self, name: str) -> Dict[str, Any]:
        """Get pool status information"""
        pass
    
    @abstractmethod
    async def get_health(self, name: str) -> Dict[str, Any]:
        """Get pool health information"""
        pass
    
    @abstractmethod
    async def scrub(self, name: str) -> bool:
        """Start pool scrub"""
        pass
    
    @abstractmethod
    async def get_scrub_status(self, name: str) -> Dict[str, Any]:
        """Get pool scrub status"""
        pass
    
    @abstractmethod
    async def get_properties(self, name: str) -> Dict[str, str]:
        """Get pool properties"""
        pass
    
    @abstractmethod
    async def get_iostat(self, name: str, interval: int = 1, count: int = 5) -> Dict[str, Any]:
        """Get pool I/O statistics"""
        pass