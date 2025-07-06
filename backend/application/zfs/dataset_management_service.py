"""Dataset management application service"""

from typing import List, Optional, Dict, Any
from ...core.entities.zfs_entity import ZFSDataset, ZFSDatasetType
from ...core.value_objects.dataset_name import DatasetName
from ...core.value_objects.storage_size import StorageSize
from ...core.interfaces.zfs_repository import ZFSDatasetRepository
from ...core.exceptions.zfs_exceptions import ZFSOperationError, ZFSDatasetExistsError
import logging

logger = logging.getLogger(__name__)


class DatasetManagementService:
    """Application service for managing ZFS datasets"""
    
    def __init__(self, dataset_repository: ZFSDatasetRepository):
        self._dataset_repository = dataset_repository
    
    async def create_dataset(
        self, 
        name: str, 
        properties: Optional[Dict[str, str]] = None,
        dataset_type: ZFSDatasetType = ZFSDatasetType.FILESYSTEM
    ) -> ZFSDataset:
        """Create a new ZFS dataset"""
        try:
            dataset_name = DatasetName(name)
            
            # Check if dataset already exists
            if await self._dataset_repository.exists(dataset_name):
                raise ZFSDatasetExistsError(f"Dataset {name} already exists", dataset=name)
            
            # Create dataset entity
            dataset = ZFSDataset(
                name=dataset_name,
                dataset_type=dataset_type,
                properties=properties or {}
            )
            
            # Create through repository
            success = await self._dataset_repository.create(dataset)
            if not success:
                raise ZFSOperationError(f"Failed to create dataset {name}", dataset=name)
            
            # Refresh dataset with current properties
            created_dataset = await self._dataset_repository.find_by_name(dataset_name)
            if not created_dataset:
                raise ZFSOperationError(f"Dataset {name} was created but cannot be found", dataset=name)
            
            logger.info(f"Created dataset: {name}")
            return created_dataset
            
        except (ZFSOperationError, ZFSDatasetExistsError):
            raise
        except Exception as e:
            logger.error(f"Failed to create dataset {name}: {e}")
            raise ZFSOperationError(f"Failed to create dataset {name}: {e}", dataset=name)
    
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
                raise ZFSOperationError(f"Dataset {name} does not exist", dataset=name)
            
            success = await self._dataset_repository.update_properties(
                dataset_name, properties
            )
            
            if success:
                logger.info(f"Updated properties for dataset {name}")
            
            return success
            
        except ZFSOperationError:
            raise
        except Exception as e:
            logger.error(f"Failed to update dataset {name}: {e}")
            raise ZFSOperationError(f"Failed to update dataset {name}: {e}", dataset=name)
    
    async def set_dataset_property(
        self, 
        name: str, 
        property_name: str, 
        value: str
    ) -> bool:
        """Set a single dataset property"""
        try:
            dataset_name = DatasetName(name)
            
            # Validate dataset exists
            if not await self._dataset_repository.exists(dataset_name):
                raise ZFSOperationError(f"Dataset {name} does not exist", dataset=name)
            
            success = await self._dataset_repository.set_property(
                dataset_name, property_name, value
            )
            
            if success:
                logger.info(f"Set property {property_name}={value} for dataset {name}")
            
            return success
            
        except ZFSOperationError:
            raise
        except Exception as e:
            logger.error(f"Failed to set property for dataset {name}: {e}")
            raise ZFSOperationError(f"Failed to set property for dataset {name}: {e}", dataset=name)
    
    async def delete_dataset(self, name: str, force: bool = False) -> bool:
        """Delete a dataset"""
        try:
            dataset_name = DatasetName(name)
            
            # Validate dataset exists
            if not await self._dataset_repository.exists(dataset_name):
                raise ZFSOperationError(f"Dataset {name} does not exist", dataset=name)
            
            # Get dataset for validation
            dataset = await self._dataset_repository.find_by_name(dataset_name)
            if dataset:
                # Business logic validation
                if dataset.is_mounted() and not force:
                    raise ZFSOperationError(
                        f"Dataset {name} is mounted. Use force=True to delete anyway.", 
                        dataset=name
                    )
            
            success = await self._dataset_repository.delete(dataset_name, force)
            
            if success:
                logger.info(f"Deleted dataset: {name}")
            
            return success
            
        except ZFSOperationError:
            raise
        except Exception as e:
            logger.error(f"Failed to delete dataset {name}: {e}")
            raise ZFSOperationError(f"Failed to delete dataset {name}: {e}", dataset=name)
    
    async def get_dataset_usage(self, name: str) -> Dict[str, Any]:
        """Get dataset usage information"""
        try:
            dataset_name = DatasetName(name)
            
            # Validate dataset exists
            if not await self._dataset_repository.exists(dataset_name):
                raise ZFSOperationError(f"Dataset {name} does not exist", dataset=name)
            
            usage_info = await self._dataset_repository.get_usage(dataset_name)
            return usage_info
            
        except ZFSOperationError:
            raise
        except Exception as e:
            logger.error(f"Failed to get usage for dataset {name}: {e}")
            raise ZFSOperationError(f"Failed to get usage for dataset {name}: {e}", dataset=name)
    
    async def optimize_dataset_for_migration(
        self, 
        name: str, 
        migration_type: str = "docker"
    ) -> bool:
        """Optimize dataset properties for migration"""
        try:
            dataset_name = DatasetName(name)
            
            # Validate dataset exists
            if not await self._dataset_repository.exists(dataset_name):
                raise ZFSOperationError(f"Dataset {name} does not exist", dataset=name)
            
            # Define optimization properties based on migration type
            optimization_properties = {}
            
            if migration_type == "docker":
                optimization_properties.update({
                    "compression": "lz4",
                    "sync": "standard",
                    "atime": "off",
                    "relatime": "off"
                })
            elif migration_type == "database":
                optimization_properties.update({
                    "compression": "lz4",
                    "sync": "always",
                    "atime": "off",
                    "recordsize": "8K"
                })
            
            if optimization_properties:
                success = await self._dataset_repository.update_properties(
                    dataset_name, optimization_properties
                )
                
                if success:
                    logger.info(f"Optimized dataset {name} for {migration_type} migration")
                
                return success
            
            return True  # No optimization needed
            
        except ZFSOperationError:
            raise
        except Exception as e:
            logger.error(f"Failed to optimize dataset {name}: {e}")
            raise ZFSOperationError(f"Failed to optimize dataset {name}: {e}", dataset=name)
    
    async def set_quota(self, name: str, quota_size: str) -> bool:
        """Set quota for a dataset"""
        try:
            # Validate quota size format
            if quota_size != "none":
                StorageSize.from_zfs_string(quota_size)  # Validate format
            
            return await self.set_dataset_property(name, "quota", quota_size)
            
        except Exception as e:
            logger.error(f"Failed to set quota for dataset {name}: {e}")
            raise ZFSOperationError(f"Failed to set quota for dataset {name}: {e}", dataset=name)
    
    async def set_reservation(self, name: str, reservation_size: str) -> bool:
        """Set reservation for a dataset"""
        try:
            # Validate reservation size format
            if reservation_size != "none":
                StorageSize.from_zfs_string(reservation_size)  # Validate format
            
            return await self.set_dataset_property(name, "reservation", reservation_size)
            
        except Exception as e:
            logger.error(f"Failed to set reservation for dataset {name}: {e}")
            raise ZFSOperationError(f"Failed to set reservation for dataset {name}: {e}", dataset=name)
    
    async def check_dataset_health(self, name: str) -> Dict[str, Any]:
        """Check dataset health and return comprehensive status"""
        try:
            dataset_name = DatasetName(name)
            
            dataset = await self._dataset_repository.find_by_name(dataset_name)
            if not dataset:
                raise ZFSOperationError(f"Dataset {name} not found", dataset=name)
            
            usage = await self._dataset_repository.get_usage(dataset_name)
            
            health_info = {
                'name': str(dataset.name),
                'exists': True,
                'mounted': dataset.is_mounted(),
                'encrypted': dataset.is_encrypted(),
                'compressed': dataset.is_compressed(),
                'pool': dataset.pool_name(),
                'mount_point': dataset.mount_point,
                'used_space': str(dataset.used_space) if dataset.used_space else None,
                'available_space': str(dataset.available_space) if dataset.available_space else None,
                'quota': str(dataset.quota) if dataset.quota else None,
                'reservation': str(dataset.reservation) if dataset.reservation else None,
                'usage_details': usage
            }
            
            return health_info
            
        except ZFSOperationError:
            raise
        except Exception as e:
            logger.error(f"Failed to check health for dataset {name}: {e}")
            raise ZFSOperationError(f"Failed to check health for dataset {name}: {e}", dataset=name)