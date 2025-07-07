# Implementation Guide: Backend Reorganization

## Step-by-Step Implementation

### Step 1: Create the New Structure (Phase 1)

Start by creating the new directory structure while keeping the existing code intact:

```bash
# Create the new directory structure
mkdir -p backend/core/{entities,value_objects,interfaces,exceptions}
mkdir -p backend/application/{migration,zfs,docker,transfer}
mkdir -p backend/infrastructure/{zfs,docker,ssh,storage}
mkdir -p backend/api/v1/{routers,middleware,models}
mkdir -p backend/shared/{security,monitoring,utils,constants}
mkdir -p backend/config
mkdir -p backend/tests/{unit,integration,e2e}
```

### Step 2: Start with Core Domain (Example Implementation)

#### 2.1 Create Value Objects

Create `backend/core/value_objects/dataset_name.py`:

```python
from dataclasses import dataclass
from typing import Optional
import re
from ..exceptions.validation_exceptions import ValidationError


@dataclass(frozen=True)
class DatasetName:
    """Immutable value object for ZFS dataset names"""
    
    value: str
    
    def __post_init__(self):
        if not self.value:
            raise ValidationError("Dataset name cannot be empty")
        
        if len(self.value) > 255:
            raise ValidationError("Dataset name cannot exceed 255 characters")
        
        # ZFS dataset name validation
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_\-./]*$', self.value):
            raise ValidationError(
                f"Invalid dataset name: {self.value}. "
                "Must start with alphanumeric and contain only letters, numbers, hyphens, underscores, dots, and slashes."
            )
    
    @classmethod
    def from_path(cls, path: str) -> 'DatasetName':
        """Create dataset name from mount path"""
        if path.startswith("/mnt/"):
            return cls(path[5:])  # Remove /mnt/ prefix
        return cls(path)
    
    def to_path(self) -> str:
        """Convert to mount path"""
        return f"/mnt/{self.value}"
    
    def parent(self) -> Optional['DatasetName']:
        """Get parent dataset name"""
        if '/' not in self.value:
            return None
        parent_path = '/'.join(self.value.split('/')[:-1])
        return DatasetName(parent_path)
    
    def child(self, name: str) -> 'DatasetName':
        """Create child dataset name"""
        return DatasetName(f"{self.value}/{name}")
    
    def __str__(self) -> str:
        return self.value
```

#### 2.2 Create Domain Entities

Create `backend/core/entities/zfs_entity.py`:

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from ..value_objects.dataset_name import DatasetName
from ..value_objects.storage_size import StorageSize


@dataclass
class ZFSDataset:
    """ZFS Dataset domain entity"""
    
    name: DatasetName
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
    def mount_point(self) -> Optional[str]:
        """Get mount point from properties"""
        return self.properties.get('mountpoint')
    
    def is_mounted(self) -> bool:
        """Check if dataset is mounted"""
        mountpoint = self.mount_point
        return mountpoint and mountpoint not in ['none', '-']
    
    def can_create_snapshot(self) -> bool:
        """Check if dataset can create snapshots"""
        return self.properties.get('readonly') != 'on'


@dataclass
class ZFSSnapshot:
    """ZFS Snapshot domain entity"""
    
    name: str
    dataset: DatasetName
    created_at: datetime
    properties: Dict[str, str] = field(default_factory=dict)
    
    @property
    def snapshot_name(self) -> str:
        """Get just the snapshot name part"""
        return self.name.split('@')[1] if '@' in self.name else self.name
    
    @property
    def full_name(self) -> str:
        """Get full snapshot name (dataset@snapshot)"""
        return f"{self.dataset}@{self.snapshot_name}"
    
    @property
    def size(self) -> Optional[StorageSize]:
        """Get snapshot size"""
        used_str = self.properties.get('used')
        if used_str:
            return StorageSize.from_zfs_string(used_str)
        return None
    
    def can_rollback(self) -> bool:
        """Check if snapshot can be rolled back to"""
        return True  # Basic check, can be enhanced
    
    def can_clone(self) -> bool:
        """Check if snapshot can be cloned"""
        return True  # Basic check, can be enhanced
```

#### 2.3 Create Repository Interfaces

Create `backend/core/interfaces/zfs_repository.py`:

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from ..entities.zfs_entity import ZFSDataset, ZFSSnapshot
from ..value_objects.dataset_name import DatasetName


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
    async def delete(self, name: DatasetName) -> bool:
        """Delete a dataset"""
        pass
    
    @abstractmethod
    async def exists(self, name: DatasetName) -> bool:
        """Check if dataset exists"""
        pass


class ZFSSnapshotRepository(ABC):
    """Repository interface for ZFS snapshots"""
    
    @abstractmethod
    async def create(self, dataset: DatasetName, snapshot_name: str) -> ZFSSnapshot:
        """Create a new snapshot"""
        pass
    
    @abstractmethod
    async def find_by_name(self, full_name: str) -> Optional[ZFSSnapshot]:
        """Find snapshot by full name"""
        pass
    
    @abstractmethod
    async def list_for_dataset(self, dataset: DatasetName) -> List[ZFSSnapshot]:
        """List all snapshots for a dataset"""
        pass
    
    @abstractmethod
    async def delete(self, full_name: str) -> bool:
        """Delete a snapshot"""
        pass
    
    @abstractmethod
    async def rollback(self, full_name: str) -> bool:
        """Rollback to a snapshot"""
        pass
    
    @abstractmethod
    async def clone(self, full_name: str, target_dataset: DatasetName) -> bool:
        """Clone a snapshot to create a new dataset"""
        pass
```

### Step 3: Create Application Services

Create `backend/application/zfs/dataset_management_service.py`:

```python
from typing import List, Optional, Dict
from ...core.entities.zfs_entity import ZFSDataset
from ...core.value_objects.dataset_name import DatasetName
from ...core.interfaces.zfs_repository import ZFSDatasetRepository
from ...core.exceptions.zfs_exceptions import ZFSOperationError
import logging

logger = logging.getLogger(__name__)


class DatasetManagementService:
    """Application service for managing ZFS datasets"""
    
    def __init__(self, dataset_repository: ZFSDatasetRepository):
        self._dataset_repository = dataset_repository
    
    async def create_dataset(
        self, 
        name: str, 
        properties: Optional[Dict[str, str]] = None
    ) -> ZFSDataset:
        """Create a new ZFS dataset"""
        try:
            dataset_name = DatasetName(name)
            
            # Check if dataset already exists
            if await self._dataset_repository.exists(dataset_name):
                raise ZFSOperationError(f"Dataset {name} already exists")
            
            # Create dataset entity
            dataset = ZFSDataset(
                name=dataset_name,
                properties=properties or {}
            )
            
            # Create through repository
            success = await self._dataset_repository.create(dataset)
            if not success:
                raise ZFSOperationError(f"Failed to create dataset {name}")
            
            logger.info(f"Created dataset: {name}")
            return dataset
            
        except Exception as e:
            logger.error(f"Failed to create dataset {name}: {e}")
            raise ZFSOperationError(f"Failed to create dataset {name}: {e}")
    
    async def get_dataset(self, name: str) -> Optional[ZFSDataset]:
        """Get a dataset by name"""
        try:
            dataset_name = DatasetName(name)
            return await self._dataset_repository.find_by_name(dataset_name)
        except Exception as e:
            logger.error(f"Failed to get dataset {name}: {e}")
            return None
    
    async def list_datasets(self, pool_name: Optional[str] = None) -> List[ZFSDataset]:
        """List all datasets or datasets in a specific pool"""
        try:
            if pool_name:
                return await self._dataset_repository.list_by_pool(pool_name)
            return await self._dataset_repository.list_all()
        except Exception as e:
            logger.error(f"Failed to list datasets: {e}")
            return []
    
    async def update_dataset_properties(
        self, 
        name: str, 
        properties: Dict[str, str]
    ) -> bool:
        """Update dataset properties"""
        try:
            dataset_name = DatasetName(name)
            
            # Validate dataset exists
            if not await self._dataset_repository.exists(dataset_name):
                raise ZFSOperationError(f"Dataset {name} does not exist")
            
            success = await self._dataset_repository.update_properties(
                dataset_name, properties
            )
            
            if success:
                logger.info(f"Updated properties for dataset {name}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to update dataset {name}: {e}")
            raise ZFSOperationError(f"Failed to update dataset {name}: {e}")
    
    async def delete_dataset(self, name: str, force: bool = False) -> bool:
        """Delete a dataset"""
        try:
            dataset_name = DatasetName(name)
            
            # Validate dataset exists
            if not await self._dataset_repository.exists(dataset_name):
                raise ZFSOperationError(f"Dataset {name} does not exist")
            
            # Additional validation logic can go here
            # - Check for snapshots
            # - Check for clones
            # - Check if mounted
            
            success = await self._dataset_repository.delete(dataset_name)
            
            if success:
                logger.info(f"Deleted dataset: {name}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete dataset {name}: {e}")
            raise ZFSOperationError(f"Failed to delete dataset {name}: {e}")
```

### Step 4: Create Infrastructure Implementation

Create `backend/infrastructure/zfs/repositories/zfs_dataset_repository.py`:

```python
from typing import List, Optional, Dict, Any
from ....core.entities.zfs_entity import ZFSDataset
from ....core.value_objects.dataset_name import DatasetName
from ....core.interfaces.zfs_repository import ZFSDatasetRepository
from ..commands.dataset_commands import DatasetCommands
from ....shared.security.validation import SecurityUtils
import logging

logger = logging.getLogger(__name__)


class ZFSDatasetRepositoryImpl(ZFSDatasetRepository):
    """Implementation of ZFS dataset repository"""
    
    def __init__(self):
        self._commands = DatasetCommands()
    
    async def create(self, dataset: ZFSDataset) -> bool:
        """Create a new dataset"""
        try:
            # Use the command to create dataset
            success = await self._commands.create_dataset(
                str(dataset.name), 
                dataset.properties
            )
            return success
        except Exception as e:
            logger.error(f"Failed to create dataset {dataset.name}: {e}")
            return False
    
    async def find_by_name(self, name: DatasetName) -> Optional[ZFSDataset]:
        """Find dataset by name"""
        try:
            properties = await self._commands.get_dataset_properties(str(name))
            if properties:
                return ZFSDataset(name=name, properties=properties)
            return None
        except Exception as e:
            logger.error(f"Failed to find dataset {name}: {e}")
            return None
    
    async def list_all(self) -> List[ZFSDataset]:
        """List all datasets"""
        try:
            datasets_data = await self._commands.list_datasets()
            datasets = []
            
            for data in datasets_data:
                name = DatasetName(data['name'])
                properties = data.get('properties', {})
                datasets.append(ZFSDataset(name=name, properties=properties))
            
            return datasets
        except Exception as e:
            logger.error(f"Failed to list datasets: {e}")
            return []
    
    async def list_by_pool(self, pool_name: str) -> List[ZFSDataset]:
        """List datasets in a specific pool"""
        try:
            all_datasets = await self.list_all()
            return [
                dataset for dataset in all_datasets 
                if str(dataset.name).startswith(f"{pool_name}/")
            ]
        except Exception as e:
            logger.error(f"Failed to list datasets for pool {pool_name}: {e}")
            return []
    
    async def update_properties(self, name: DatasetName, properties: Dict[str, str]) -> bool:
        """Update dataset properties"""
        try:
            return await self._commands.set_dataset_properties(str(name), properties)
        except Exception as e:
            logger.error(f"Failed to update properties for {name}: {e}")
            return False
    
    async def delete(self, name: DatasetName) -> bool:
        """Delete a dataset"""
        try:
            return await self._commands.destroy_dataset(str(name))
        except Exception as e:
            logger.error(f"Failed to delete dataset {name}: {e}")
            return False
    
    async def exists(self, name: DatasetName) -> bool:
        """Check if dataset exists"""
        try:
            return await self._commands.dataset_exists(str(name))
        except Exception as e:
            logger.error(f"Failed to check if dataset {name} exists: {e}")
            return False
```

### Step 5: Create New API Endpoints

Create `backend/api/v1/routers/datasets.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict
from ....application.zfs.dataset_management_service import DatasetManagementService
from ....core.exceptions.zfs_exceptions import ZFSOperationError
from ..models.request_models import CreateDatasetRequest, UpdateDatasetRequest
from ..models.response_models import DatasetResponse
from ..dependencies import get_dataset_service

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("/", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    request: CreateDatasetRequest,
    service: DatasetManagementService = Depends(get_dataset_service)
):
    """Create a new ZFS dataset"""
    try:
        dataset = await service.create_dataset(request.name, request.properties)
        return DatasetResponse.from_entity(dataset)
    except ZFSOperationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{name}", response_model=DatasetResponse)
async def get_dataset(
    name: str,
    service: DatasetManagementService = Depends(get_dataset_service)
):
    """Get a ZFS dataset by name"""
    dataset = await service.get_dataset(name)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset {name} not found"
        )
    return DatasetResponse.from_entity(dataset)


@router.get("/", response_model=List[DatasetResponse])
async def list_datasets(
    pool_name: Optional[str] = None,
    service: DatasetManagementService = Depends(get_dataset_service)
):
    """List ZFS datasets"""
    datasets = await service.list_datasets(pool_name)
    return [DatasetResponse.from_entity(dataset) for dataset in datasets]


@router.put("/{name}/properties", response_model=Dict[str, str])
async def update_dataset_properties(
    name: str,
    request: UpdateDatasetRequest,
    service: DatasetManagementService = Depends(get_dataset_service)
):
    """Update ZFS dataset properties"""
    try:
        success = await service.update_dataset_properties(name, request.properties)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to update properties for dataset {name}"
            )
        return {"message": "Properties updated successfully"}
    except ZFSOperationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    name: str,
    force: bool = False,
    service: DatasetManagementService = Depends(get_dataset_service)
):
    """Delete a ZFS dataset"""
    try:
        success = await service.delete_dataset(name, force)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to delete dataset {name}"
            )
    except ZFSOperationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
```

### Step 6: Migration Strategy

#### 6.1 Gradual Migration Approach

1. **Create New Structure**: Set up new directories and interfaces
2. **Migrate One Feature**: Start with a single feature (e.g., dataset management)
3. **Parallel Implementation**: Keep old code working while building new
4. **Feature Flags**: Use feature flags to switch between old and new implementations
5. **Test Thoroughly**: Ensure new implementation works correctly
6. **Switch Over**: Replace old endpoints with new ones
7. **Remove Old Code**: Delete old code once migration is complete

#### 6.2 Example Migration Script

Create `scripts/migrate_zfs_operations.py`:

```python
import asyncio
import logging
from backend.zfs_ops import ZFSOperations  # Old implementation
from backend.application.zfs.dataset_management_service import DatasetManagementService
from backend.infrastructure.zfs.repositories.zfs_dataset_repository import ZFSDatasetRepositoryImpl

logger = logging.getLogger(__name__)


async def migrate_zfs_operations():
    """Migrate ZFS operations to new architecture"""
    
    # Initialize old and new implementations
    old_zfs = ZFSOperations()
    new_repo = ZFSDatasetRepositoryImpl()
    new_service = DatasetManagementService(new_repo)
    
    # Test compatibility
    print("Testing compatibility between old and new implementations...")
    
    # Get datasets using old method
    old_datasets = await old_zfs.list_datasets()
    print(f"Old implementation found {len(old_datasets)} datasets")
    
    # Get datasets using new method
    new_datasets = await new_service.list_datasets()
    print(f"New implementation found {len(new_datasets)} datasets")
    
    # Compare results
    old_names = set(old_datasets)
    new_names = set(str(dataset.name) for dataset in new_datasets)
    
    if old_names == new_names:
        print("✅ Dataset lists match between old and new implementations")
    else:
        print("❌ Dataset lists don't match")
        print(f"Old only: {old_names - new_names}")
        print(f"New only: {new_names - old_names}")
    
    print("Migration test completed")


if __name__ == "__main__":
    asyncio.run(migrate_zfs_operations())
```

## Next Steps

1. **Start Small**: Begin with one domain (e.g., datasets)
2. **Create Tests**: Write comprehensive tests for new code
3. **Parallel Development**: Keep old code working while building new
4. **Gradual Migration**: Move one feature at a time
5. **Monitor Performance**: Ensure no performance regressions
6. **Documentation**: Update API documentation as you go

This approach allows you to gradually transform your monolithic backend into a clean, maintainable architecture without breaking existing functionality.