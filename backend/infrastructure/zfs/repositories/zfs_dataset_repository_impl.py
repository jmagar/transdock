"""ZFS Dataset repository implementation"""

from typing import List, Optional, Dict, Any
from ....core.entities.zfs_entity import ZFSDataset, ZFSDatasetType
from ....core.value_objects.dataset_name import DatasetName
from ....core.interfaces.zfs_repository import ZFSDatasetRepository
from ....zfs_ops import ZFSOperations  # Import the existing monolithic class
import logging

logger = logging.getLogger(__name__)


class ZFSDatasetRepositoryImpl(ZFSDatasetRepository):
    """Implementation of ZFS dataset repository using existing ZFSOperations"""
    
    def __init__(self):
        # Use the existing ZFSOperations class as the underlying implementation
        self._zfs_ops = ZFSOperations()
    
    async def create(self, dataset: ZFSDataset) -> bool:
        """Create a new dataset using existing ZFS operations"""
        try:
            # Convert to the format expected by the old implementation
            dataset_path = dataset.name.to_path()
            
            # Use the existing create_dataset method
            success = await self._zfs_ops.create_dataset(dataset_path)
            
            # If we have properties to set, apply them after creation
            if success and dataset.properties:
                for prop_name, prop_value in dataset.properties.items():
                    try:
                        await self._zfs_ops.set_dataset_property(
                            str(dataset.name), prop_name, prop_value
                        )
                    except Exception as e:
                        logger.warning(f"Failed to set property {prop_name}={prop_value}: {e}")
            
            return success
        except Exception as e:
            logger.error(f"Failed to create dataset {dataset.name}: {e}")
            return False
    
    async def find_by_name(self, name: DatasetName) -> Optional[ZFSDataset]:
        """Find dataset by name using existing ZFS operations"""
        try:
            # Check if dataset exists
            if not await self._zfs_ops.dataset_exists(str(name)):
                return None
            
            # Get dataset properties
            properties = await self._zfs_ops.get_dataset_properties(str(name))
            
            # Determine dataset type from properties
            dataset_type = ZFSDatasetType.FILESYSTEM
            if properties.get('type') == 'volume':
                dataset_type = ZFSDatasetType.VOLUME
            
            return ZFSDataset(
                name=name,
                dataset_type=dataset_type,
                properties=properties
            )
        except Exception as e:
            logger.error(f"Failed to find dataset {name}: {e}")
            return None
    
    async def list_all(self) -> List[ZFSDataset]:
        """List all datasets using existing ZFS operations"""
        try:
            # Get dataset names from existing operation
            dataset_names = await self._zfs_ops.list_datasets()
            
            datasets = []
            for dataset_name in dataset_names:
                try:
                    name = DatasetName(dataset_name)
                    dataset = await self.find_by_name(name)
                    if dataset:
                        datasets.append(dataset)
                except Exception as e:
                    logger.warning(f"Failed to process dataset {dataset_name}: {e}")
                    continue
            
            return datasets
        except Exception as e:
            logger.error(f"Failed to list datasets: {e}")
            return []
    
    async def list_by_pool(self, pool_name: str) -> List[ZFSDataset]:
        """List datasets in a specific pool"""
        try:
            # Get all datasets and filter by pool
            all_datasets = await self.list_all()
            return [
                dataset for dataset in all_datasets 
                if dataset.pool_name() == pool_name
            ]
        except Exception as e:
            logger.error(f"Failed to list datasets for pool {pool_name}: {e}")
            return []
    
    async def update_properties(self, name: DatasetName, properties: Dict[str, str]) -> bool:
        """Update dataset properties using existing ZFS operations"""
        try:
            success = True
            for prop_name, prop_value in properties.items():
                try:
                    result = await self._zfs_ops.set_dataset_property(
                        str(name), prop_name, prop_value
                    )
                    if not result:
                        success = False
                        logger.error(f"Failed to set property {prop_name}={prop_value} for {name}")
                except Exception as e:
                    success = False
                    logger.error(f"Failed to set property {prop_name}={prop_value} for {name}: {e}")
            
            return success
        except Exception as e:
            logger.error(f"Failed to update properties for dataset {name}: {e}")
            return False
    
    async def delete(self, name: DatasetName, force: bool = False) -> bool:
        """Delete a dataset using existing ZFS operations"""
        try:
            # The existing ZFS operations may not have a direct delete method
            # So we'll use the ZFS command directly through the safe run method
            if force:
                returncode, stdout, stderr = await self._zfs_ops.safe_run_zfs_command(
                    "destroy", "-f", str(name)
                )
            else:
                returncode, stdout, stderr = await self._zfs_ops.safe_run_zfs_command(
                    "destroy", str(name)
                )
            
            success = returncode == 0
            if not success:
                logger.error(f"Failed to delete dataset {name}: {stderr}")
            
            return success
        except Exception as e:
            logger.error(f"Failed to delete dataset {name}: {e}")
            return False
    
    async def exists(self, name: DatasetName) -> bool:
        """Check if dataset exists using existing ZFS operations"""
        try:
            return await self._zfs_ops.dataset_exists(str(name))
        except Exception as e:
            logger.error(f"Failed to check if dataset {name} exists: {e}")
            return False
    
    async def get_properties(self, name: DatasetName, properties: Optional[List[str]] = None) -> Dict[str, str]:
        """Get dataset properties using existing ZFS operations"""
        try:
            return await self._zfs_ops.get_dataset_properties(str(name), properties)
        except Exception as e:
            logger.error(f"Failed to get properties for dataset {name}: {e}")
            return {}
    
    async def set_property(self, name: DatasetName, property_name: str, value: str) -> bool:
        """Set a single dataset property using existing ZFS operations"""
        try:
            return await self._zfs_ops.set_dataset_property(str(name), property_name, value)
        except Exception as e:
            logger.error(f"Failed to set property {property_name}={value} for dataset {name}: {e}")
            return False
    
    async def get_usage(self, name: DatasetName) -> Dict[str, Any]:
        """Get dataset usage information using existing ZFS operations"""
        try:
            return await self._zfs_ops.get_dataset_usage(str(name))
        except Exception as e:
            logger.error(f"Failed to get usage for dataset {name}: {e}")
            return {}