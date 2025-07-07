"""ZFS Pool Repository Implementation"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import re
import json

from ....core.interfaces.zfs_repository import ZFSPoolRepository
from ....core.entities.zfs_entity import ZFSPool, ZFSPoolStatus
from ....core.value_objects.dataset_name import DatasetName
from ....zfs_ops import ZFSOperations
import logging

logger = logging.getLogger(__name__)


class ZFSPoolRepositoryImpl(ZFSPoolRepository):
    """ZFS Pool repository implementation using existing ZFSOperations"""
    
    def __init__(self):
        self._zfs_ops = ZFSOperations()
    
    async def _get_pool_names(self) -> List[str]:
        """Derive pool names from dataset list since zpool_list helper is not available."""
        try:
            datasets = await self._zfs_ops.list_datasets()
            pool_names = sorted({ds.split('/')[0] for ds in datasets})
            return pool_names
        except Exception:
            return []
    
    async def list_all(self) -> List[ZFSPool]:
        """List all ZFS pools"""
        try:
            # Use existing zpool_list method
            pool_names = await self._get_pool_names()
            
            pools = []
            for pool_name in pool_names:
                pool = await self.find_by_name(pool_name)
                if pool:
                    pools.append(pool)
            
            return pools
            
        except Exception as e:
            logger.error(f"Failed to list pools: {e}")
            return []
    
    async def find_by_name(self, name: str) -> Optional[ZFSPool]:
        """Find a pool by name"""
        try:
            # Check if pool exists
            pool_names = await self._get_pool_names()
            if name not in pool_names:
                return None
            
            # Get pool properties
            properties = await self.get_properties(name)
            
            # Get pool status
            status_info = await self.get_status(name)
            
            # Determine pool status from state
            status = ZFSPoolStatus.ONLINE
            if 'state' in status_info:
                state_str = status_info['state'].upper()
                try:
                    status = ZFSPoolStatus(state_str)
                except ValueError:
                    status = ZFSPoolStatus.OFFLINE
            
            # Get datasets in pool
            all_datasets = await self._zfs_ops.list_datasets(name)
            dataset_names = []
            for ds_name in all_datasets:
                try:
                    dataset_names.append(DatasetName(ds_name))
                except Exception:
                    continue
            
            return ZFSPool(
                name=name,
                status=status,
                properties=properties,
                datasets=dataset_names
            )
            
        except Exception as e:
            logger.error(f"Failed to find pool {name}: {e}")
            return None
    
    async def get_properties(self, name: str) -> Dict[str, str]:
        """Get pool properties"""
        try:
            # Fallback: use get_pool_status details (zpool properties unavailable)
            status_info = await self.get_status(name)
            if not status_info:
                return {}
            properties = {}
            
            # Extract basic properties from status
            if 'state' in status_info:
                properties['health'] = status_info['state']
            
            if 'config' in status_info:
                # Parse pool size information from config
                config_lines = status_info['config'].split('\n')
                for line in config_lines:
                    if name in line and 'ONLINE' in line:
                        # Try to extract size info
                        parts = line.split()
                        if len(parts) >= 3:
                            properties['size'] = parts[2] if parts[2] != '-' else '0'
            
            # Get additional properties using zpool get
            # Since we don't have direct zpool command access, use the info we have
            properties.update({
                'allocated': status_info.get('allocated', '0'),
                'free': status_info.get('free', '0'),
                'capacity': status_info.get('capacity', '0%'),
                'dedupratio': status_info.get('dedupratio', '1.00x'),
                'compressratio': status_info.get('compressratio', '1.00x'),
                'version': status_info.get('version', '-'),
                'guid': status_info.get('guid', '-'),
                'altroot': status_info.get('altroot', '-'),
                'readonly': status_info.get('readonly', 'off')
            })
            
            return properties
            
        except Exception as e:
            logger.error(f"Failed to get properties for pool {name}: {e}")
            return {}
    
    async def get_status(self, name: str) -> Dict[str, Any]:
        """Get pool status"""
        try:
            return await self._zfs_ops.get_pool_status(name)
        except Exception as e:
            logger.error(f"Failed to get status for pool {name}: {e}")
            return {}
    
    async def scrub(self, name: str) -> bool:
        """Start scrub on pool"""
        try:
            return await self._zfs_ops.start_pool_scrub(name)
        except Exception as e:
            logger.error(f"Failed to scrub pool {name}: {e}")
            return False
    
    async def stop_scrub(self, name: str) -> bool:
        """Stop scrub on pool"""
        try:
            # ZFSOperations doesn't have stop scrub, so use safe_run_zfs_command
            # Actually need zpool command, not zfs command
            # This is a limitation - we can't stop scrub without zpool command access
            logger.warning("Stop scrub not implemented in current ZFSOperations")
            return False
        except Exception as e:
            logger.error(f"Failed to stop scrub on pool {name}: {e}")
            return False
    
    async def get_scrub_status(self, name: str) -> Dict[str, Any]:
        """Get scrub status for pool"""
        try:
            status = await self._zfs_ops.get_scrub_status(name)
            
            # Add additional calculated fields
            if 'last_scrub_time' in status:
                try:
                    last_scrub_time = datetime.fromisoformat(status['last_scrub_time'])
                    age_days = (datetime.now() - last_scrub_time).days
                    status['last_scrub_age_days'] = age_days
                except Exception:
                    pass
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get scrub status for pool {name}: {e}")
            return {}
    
    async def export(self, name: str, force: bool = False) -> bool:
        """Export pool"""
        try:
            # ZFSOperations doesn't have export, this would need implementation
            logger.warning("Export not implemented in current ZFSOperations")
            return False
        except Exception as e:
            logger.error(f"Failed to export pool {name}: {e}")
            return False
    
    async def import_pool(self, name: str, force: bool = False, altroot: Optional[str] = None) -> bool:
        """Import pool"""
        try:
            # ZFSOperations doesn't have import, this would need implementation
            logger.warning("Import not implemented in current ZFSOperations")
            return False
        except Exception as e:
            logger.error(f"Failed to import pool {name}: {e}")
            return False
    
    async def get_history(self, name: str) -> List[Dict[str, Any]]:
        """Get pool history"""
        try:
            # ZFSOperations doesn't have history command
            # Would need to implement zpool history
            logger.warning("History not implemented in current ZFSOperations")
            return []
        except Exception as e:
            logger.error(f"Failed to get history for pool {name}: {e}")
            return []
    
    async def get_events(self, name: str) -> List[Dict[str, Any]]:
        """Get pool events"""
        try:
            # ZFSOperations doesn't have events command
            logger.warning("Events not implemented in current ZFSOperations")
            return []
        except Exception as e:
            logger.error(f"Failed to get events for pool {name}: {e}")
            return []
    
    async def get_iostat(self, name: str) -> Dict[str, Any]:
        """Get pool I/O statistics"""
        try:
            # Use existing zpool_iostat method
            iostat_data = await self._zfs_ops.get_zfs_iostat([name], interval=1, count=1)
            
            # Add high latency detection
            if 'operations' in iostat_data:
                read_ops = iostat_data['operations'].get('read', 0)
                write_ops = iostat_data['operations'].get('write', 0)
                if 'bandwidth' in iostat_data:
                    read_bw = iostat_data['bandwidth'].get('read', 0)
                    write_bw = iostat_data['bandwidth'].get('write', 0)
                    
                    # Simple heuristic for high latency
                    if (read_ops > 0 and read_bw < 1048576) or (write_ops > 0 and write_bw < 1048576):
                        iostat_data['high_latency'] = True
                    else:
                        iostat_data['high_latency'] = False
            
            return iostat_data
            
        except Exception as e:
            logger.error(f"Failed to get iostat for pool {name}: {e}")
            return {}
    
    async def set_property(self, name: str, property_name: str, value: str) -> bool:
        """Set pool property"""
        try:
            # ZFSOperations doesn't have zpool set command
            logger.warning("Set property not implemented in current ZFSOperations")
            return False
        except Exception as e:
            logger.error(f"Failed to set property {property_name} for pool {name}: {e}")
            return False
    
    async def clear_errors(self, name: str) -> bool:
        """Clear pool errors"""
        try:
            # ZFSOperations doesn't have zpool clear command
            logger.warning("Clear errors not implemented in current ZFSOperations")
            return False
        except Exception as e:
            logger.error(f"Failed to clear errors for pool {name}: {e}")
            return False