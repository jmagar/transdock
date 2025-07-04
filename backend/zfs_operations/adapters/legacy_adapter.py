from typing import Dict, Any, List, Optional, Union
import logging
from datetime import datetime

from ..factories.service_factory import ServiceFactory, create_default_service_factory
from ..services.dataset_service import DatasetService
from ..services.snapshot_service import SnapshotService
from ..services.pool_service import PoolService
from ..core.result import Result
from ..core.exceptions.zfs_exceptions import ZFSException


class LegacyAdapter:
    """
    Adapter that provides backward compatibility with the existing API
    while using the new service layer underneath.
    """
    
    def __init__(self, service_factory: Optional[ServiceFactory] = None):
        """Initialize the legacy adapter with service factory."""
        self._service_factory = service_factory or create_default_service_factory()
        self._logger = logging.getLogger(__name__)
        
        # Initialize services
        self._dataset_service = self._service_factory.create_dataset_service()
        self._snapshot_service = self._service_factory.create_snapshot_service()
        self._pool_service = self._service_factory.create_pool_service()
    
    # Dataset operations (Legacy API compatibility)
    
    def create_dataset(self, name: str, properties: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Create a dataset - Legacy API compatible."""
        try:
            result = self._run_async(self._dataset_service.create_dataset(name, properties or {}))
            
            if result.is_success:
                return {
                    'success': True,
                    'dataset': result.value.to_dict(),
                    'message': f'Dataset {name} created successfully'
                }
            else:
                return {
                    'success': False,
                    'error': str(result.error),
                    'message': f'Failed to create dataset {name}'
                }
        except Exception as e:
            self._logger.error(f"Unexpected error creating dataset {name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Unexpected error creating dataset {name}'
            }
    
    def delete_dataset(self, name: str, recursive: bool = False) -> Dict[str, Any]:
        """Delete a dataset - Legacy API compatible."""
        try:
            result = self._run_async(self._dataset_service.delete_dataset(name, recursive))
            
            if result.is_success:
                return {
                    'success': True,
                    'message': f'Dataset {name} deleted successfully'
                }
            else:
                return {
                    'success': False,
                    'error': str(result.error),
                    'message': f'Failed to delete dataset {name}'
                }
        except Exception as e:
            self._logger.error(f"Unexpected error deleting dataset {name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Unexpected error deleting dataset {name}'
            }
    
    def list_datasets(self, pool_name: Optional[str] = None) -> Dict[str, Any]:
        """List datasets - Legacy API compatible."""
        try:
            result = self._run_async(self._dataset_service.list_datasets(pool_name))
            
            if result.is_success:
                datasets = [dataset.to_dict() for dataset in result.value]
                return {
                    'success': True,
                    'datasets': datasets,
                    'count': len(datasets)
                }
            else:
                return {
                    'success': False,
                    'error': str(result.error),
                    'message': 'Failed to list datasets'
                }
        except Exception as e:
            self._logger.error(f"Unexpected error listing datasets: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': 'Unexpected error listing datasets'
            }
    
    def get_dataset_properties(self, name: str) -> Dict[str, Any]:
        """Get dataset properties - Legacy API compatible."""
        try:
            result = self._run_async(self._dataset_service.get_dataset_properties(name))
            
            if result.is_success:
                return {
                    'success': True,
                    'properties': result.value
                }
            else:
                return {
                    'success': False,
                    'error': str(result.error),
                    'message': f'Failed to get properties for dataset {name}'
                }
        except Exception as e:
            self._logger.error(f"Unexpected error getting dataset properties {name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Unexpected error getting properties for dataset {name}'
            }
    
    def set_dataset_property(self, name: str, property_name: str, value: str) -> Dict[str, Any]:
        """Set dataset property - Legacy API compatible."""
        try:
            result = self._run_async(self._dataset_service.set_dataset_property(name, property_name, value))
            
            if result.is_success:
                return {
                    'success': True,
                    'message': f'Property {property_name} set to {value} for dataset {name}'
                }
            else:
                return {
                    'success': False,
                    'error': str(result.error),
                    'message': f'Failed to set property {property_name} for dataset {name}'
                }
        except Exception as e:
            self._logger.error(f"Unexpected error setting dataset property {name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Unexpected error setting property for dataset {name}'
            }
    
    # Snapshot operations (Legacy API compatibility)
    
    def create_snapshot(self, dataset_name: str, snapshot_name: str, recursive: bool = False) -> Dict[str, Any]:
        """Create a snapshot - Legacy API compatible."""
        try:
            full_name = f"{dataset_name}@{snapshot_name}"
            result = self._run_async(self._snapshot_service.create_snapshot(full_name, recursive))
            
            if result.is_success:
                return {
                    'success': True,
                    'snapshot': result.value.to_dict(),
                    'message': f'Snapshot {full_name} created successfully'
                }
            else:
                return {
                    'success': False,
                    'error': str(result.error),
                    'message': f'Failed to create snapshot {full_name}'
                }
        except Exception as e:
            self._logger.error(f"Unexpected error creating snapshot {dataset_name}@{snapshot_name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Unexpected error creating snapshot {dataset_name}@{snapshot_name}'
            }
    
    def delete_snapshot(self, dataset_name: str, snapshot_name: str) -> Dict[str, Any]:
        """Delete a snapshot - Legacy API compatible."""
        try:
            full_name = f"{dataset_name}@{snapshot_name}"
            result = self._run_async(self._snapshot_service.delete_snapshot(full_name))
            
            if result.is_success:
                return {
                    'success': True,
                    'message': f'Snapshot {full_name} deleted successfully'
                }
            else:
                return {
                    'success': False,
                    'error': str(result.error),
                    'message': f'Failed to delete snapshot {full_name}'
                }
        except Exception as e:
            self._logger.error(f"Unexpected error deleting snapshot {dataset_name}@{snapshot_name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Unexpected error deleting snapshot {dataset_name}@{snapshot_name}'
            }
    
    def list_snapshots(self, dataset_name: Optional[str] = None) -> Dict[str, Any]:
        """List snapshots - Legacy API compatible."""
        try:
            result = self._run_async(self._snapshot_service.list_snapshots(dataset_name))
            
            if result.is_success:
                snapshots = [snapshot.to_dict() for snapshot in result.value]
                return {
                    'success': True,
                    'snapshots': snapshots,
                    'count': len(snapshots)
                }
            else:
                return {
                    'success': False,
                    'error': str(result.error),
                    'message': 'Failed to list snapshots'
                }
        except Exception as e:
            self._logger.error(f"Unexpected error listing snapshots: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': 'Unexpected error listing snapshots'
            }
    
    def rollback_snapshot(self, dataset_name: str, snapshot_name: str) -> Dict[str, Any]:
        """Rollback to a snapshot - Legacy API compatible."""
        try:
            full_name = f"{dataset_name}@{snapshot_name}"
            result = self._run_async(self._snapshot_service.rollback_to_snapshot(full_name))
            
            if result.is_success:
                return {
                    'success': True,
                    'message': f'Rolled back to snapshot {full_name}'
                }
            else:
                return {
                    'success': False,
                    'error': str(result.error),
                    'message': f'Failed to rollback to snapshot {full_name}'
                }
        except Exception as e:
            self._logger.error(f"Unexpected error rolling back snapshot {dataset_name}@{snapshot_name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Unexpected error rolling back to snapshot {dataset_name}@{snapshot_name}'
            }
    
    # Pool operations (Legacy API compatibility)
    
    def list_pools(self) -> Dict[str, Any]:
        """List pools - Legacy API compatible."""
        try:
            result = self._run_async(self._pool_service.list_pools())
            
            if result.is_success:
                pools = [pool.to_dict() for pool in result.value]
                return {
                    'success': True,
                    'pools': pools,
                    'count': len(pools)
                }
            else:
                return {
                    'success': False,
                    'error': str(result.error),
                    'message': 'Failed to list pools'
                }
        except Exception as e:
            self._logger.error(f"Unexpected error listing pools: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': 'Unexpected error listing pools'
            }
    
    def get_pool_status(self, pool_name: str) -> Dict[str, Any]:
        """Get pool status - Legacy API compatible."""
        try:
            result = self._run_async(self._pool_service.get_pool(pool_name))
            
            if result.is_success:
                return {
                    'success': True,
                    'pool': result.value.to_dict(),
                    'status': result.value.state,
                    'health': result.value.health
                }
            else:
                return {
                    'success': False,
                    'error': str(result.error),
                    'message': f'Failed to get status for pool {pool_name}'
                }
        except Exception as e:
            self._logger.error(f"Unexpected error getting pool status {pool_name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Unexpected error getting status for pool {pool_name}'
            }
    
    def scrub_pool(self, pool_name: str, action: str = 'start') -> Dict[str, Any]:
        """Start or stop pool scrub - Legacy API compatible."""
        try:
            if action == 'start':
                result = self._run_async(self._pool_service.start_scrub(pool_name))
                message = f'Started scrub for pool {pool_name}'
            elif action == 'stop':
                result = self._run_async(self._pool_service.stop_scrub(pool_name))
                message = f'Stopped scrub for pool {pool_name}'
            else:
                return {
                    'success': False,
                    'error': f'Invalid action: {action}',
                    'message': 'Action must be "start" or "stop"'
                }
            
            if result.is_success:
                return {
                    'success': True,
                    'message': message
                }
            else:
                return {
                    'success': False,
                    'error': str(result.error),
                    'message': f'Failed to {action} scrub for pool {pool_name}'
                }
        except Exception as e:
            self._logger.error(f"Unexpected error during scrub operation {pool_name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Unexpected error during scrub operation for pool {pool_name}'
            }
    
    def get_pool_iostat(self, pool_name: Optional[str] = None) -> Dict[str, Any]:
        """Get pool I/O statistics - Legacy API compatible."""
        try:
            result = self._run_async(self._pool_service.get_iostat(pool_name))
            
            if result.is_success:
                return {
                    'success': True,
                    'iostat': result.value
                }
            else:
                return {
                    'success': False,
                    'error': str(result.error),
                    'message': f'Failed to get I/O statistics for pool {pool_name or "all"}'
                }
        except Exception as e:
            self._logger.error(f"Unexpected error getting iostat {pool_name or 'all'}: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Unexpected error getting I/O statistics for pool {pool_name or "all"}'
            }
    
    # Utility methods
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get system information - Legacy API compatible."""
        try:
            # Get combined system information
            pools_result = self._run_async(self._pool_service.list_pools())
            datasets_result = self._run_async(self._dataset_service.list_datasets())
            
            system_info = {
                'timestamp': datetime.now().isoformat(),
                'pools': {
                    'count': 0,
                    'total_size': 0,
                    'total_used': 0,
                    'total_free': 0
                },
                'datasets': {
                    'count': 0
                }
            }
            
            if pools_result.is_success:
                pools = pools_result.value
                system_info['pools']['count'] = len(pools)
                for pool in pools:
                    system_info['pools']['total_size'] += pool.size.bytes
                    system_info['pools']['total_used'] += pool.allocated.bytes
                    system_info['pools']['total_free'] += pool.free.bytes
            
            if datasets_result.is_success:
                system_info['datasets']['count'] = len(datasets_result.value)
            
            return {
                'success': True,
                'system_info': system_info
            }
        except Exception as e:
            self._logger.error(f"Unexpected error getting system info: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': 'Unexpected error getting system information'
            }
    
    def _run_async(self, coro):
        """Run async coroutine synchronously for legacy compatibility."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)
        except RuntimeError:
            # Create new event loop if none exists
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()


# Global instance for backward compatibility
_default_adapter = None


def get_legacy_adapter() -> LegacyAdapter:
    """Get the default legacy adapter instance."""
    global _default_adapter
    if _default_adapter is None:
        _default_adapter = LegacyAdapter()
    return _default_adapter


# Legacy function aliases for backward compatibility
def create_dataset(name: str, properties: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Legacy function - Create a dataset."""
    return get_legacy_adapter().create_dataset(name, properties)


def delete_dataset(name: str, recursive: bool = False) -> Dict[str, Any]:
    """Legacy function - Delete a dataset."""
    return get_legacy_adapter().delete_dataset(name, recursive)


def list_datasets(pool_name: Optional[str] = None) -> Dict[str, Any]:
    """Legacy function - List datasets."""
    return get_legacy_adapter().list_datasets(pool_name)


def create_snapshot(dataset_name: str, snapshot_name: str, recursive: bool = False) -> Dict[str, Any]:
    """Legacy function - Create a snapshot."""
    return get_legacy_adapter().create_snapshot(dataset_name, snapshot_name, recursive)


def delete_snapshot(dataset_name: str, snapshot_name: str) -> Dict[str, Any]:
    """Legacy function - Delete a snapshot."""
    return get_legacy_adapter().delete_snapshot(dataset_name, snapshot_name)


def list_snapshots(dataset_name: Optional[str] = None) -> Dict[str, Any]:
    """Legacy function - List snapshots."""
    return get_legacy_adapter().list_snapshots(dataset_name)


def list_pools() -> Dict[str, Any]:
    """Legacy function - List pools."""
    return get_legacy_adapter().list_pools()


def get_pool_status(pool_name: str) -> Dict[str, Any]:
    """Legacy function - Get pool status."""
    return get_legacy_adapter().get_pool_status(pool_name)


def scrub_pool(pool_name: str, action: str = 'start') -> Dict[str, Any]:
    """Legacy function - Start or stop pool scrub."""
    return get_legacy_adapter().scrub_pool(pool_name, action) 