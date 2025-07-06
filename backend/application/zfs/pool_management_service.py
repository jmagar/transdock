"""Pool management application service"""

from typing import List, Optional, Dict, Any
from ...core.entities.zfs_entity import ZFSPool
from ...core.interfaces.zfs_repository import ZFSPoolRepository
from ...core.exceptions.zfs_exceptions import ZFSOperationError, ZFSPoolNotFoundError
from ...core.value_objects.storage_size import StorageSize
import logging

logger = logging.getLogger(__name__)


class PoolManagementService:
    """Application service for managing ZFS pools"""
    
    def __init__(self, pool_repository: ZFSPoolRepository):
        self._pool_repository = pool_repository
    
    async def get_pool(self, pool_name: str) -> Optional[ZFSPool]:
        """Get a ZFS pool by name"""
        try:
            return await self._pool_repository.find_by_name(pool_name)
        except Exception as e:
            logger.error(f"Failed to get pool {pool_name}: {e}")
            return None
    
    async def list_pools(self) -> List[ZFSPool]:
        """List all ZFS pools"""
        try:
            return await self._pool_repository.list_all()
        except Exception as e:
            logger.error(f"Failed to list pools: {e}")
            return []
    
    async def get_pool_status(self, pool_name: str) -> Dict[str, Any]:
        """Get detailed pool status"""
        try:
            pool = await self._pool_repository.find_by_name(pool_name)
            if not pool:
                raise ZFSPoolNotFoundError(f"Pool {pool_name} not found")
            
            status = await self._pool_repository.get_status(pool_name)
            
            # Add computed information
            status.update({
                'pool_name': pool.name,
                'total_size': str(pool.total_size) if pool.total_size else None,
                'used_size': str(pool.used_size) if pool.used_size else None,
                'free_size': str(pool.free_size) if pool.free_size else None,
                'usage_percentage': pool.usage_percentage(),
                'health_status': pool.health.value,
                'is_healthy': pool.is_healthy(),
                'has_errors': pool.has_errors(),
                'needs_attention': pool.needs_attention(),
                'dataset_count': len(pool.datasets)
            })
            
            return status
            
        except (ZFSOperationError, ZFSPoolNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to get pool status for {pool_name}: {e}")
            raise ZFSOperationError(f"Failed to get pool status for {pool_name}: {e}")
    
    async def get_pool_properties(self, pool_name: str) -> Dict[str, Any]:
        """Get pool properties"""
        try:
            pool = await self._pool_repository.find_by_name(pool_name)
            if not pool:
                raise ZFSPoolNotFoundError(f"Pool {pool_name} not found")
            
            properties = await self._pool_repository.get_properties(pool_name)
            
            # Add computed properties
            additional_properties = {
                'pool_name': pool.name,
                'total_size_bytes': str(pool.total_size.bytes) if pool.total_size else '0',
                'used_size_bytes': str(pool.used_size.bytes) if pool.used_size else '0',
                'free_size_bytes': str(pool.free_size.bytes) if pool.free_size else '0',
                'usage_percentage': str(pool.usage_percentage()),
                'health_status': pool.health.value,
                'version': pool.version or '',
                'guid': pool.guid or '',
                'altroot': pool.altroot or '',
                'readonly': str(pool.readonly),
                'dedup_ratio': str(pool.dedup_ratio()),
                'compression_ratio': str(pool.compression_ratio()),
                'dataset_count': str(len(pool.datasets))
            }
            properties.update(additional_properties)
            
            return properties
            
        except (ZFSOperationError, ZFSPoolNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to get pool properties for {pool_name}: {e}")
            raise ZFSOperationError(f"Failed to get pool properties for {pool_name}: {e}")
    
    async def scrub_pool(self, pool_name: str) -> bool:
        """Start a scrub operation on the pool"""
        try:
            pool = await self._pool_repository.find_by_name(pool_name)
            if not pool:
                raise ZFSPoolNotFoundError(f"Pool {pool_name} not found")
            
            if not pool.is_healthy():
                raise ZFSOperationError(f"Pool {pool_name} is not healthy, scrub may not be safe")
            
            success = await self._pool_repository.scrub(pool_name)
            
            if success:
                logger.info(f"Started scrub for pool: {pool_name}")
            
            return success
            
        except (ZFSOperationError, ZFSPoolNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to start scrub for pool {pool_name}: {e}")
            raise ZFSOperationError(f"Failed to start scrub for pool {pool_name}: {e}")
    
    async def stop_scrub(self, pool_name: str) -> bool:
        """Stop a scrub operation on the pool"""
        try:
            pool = await self._pool_repository.find_by_name(pool_name)
            if not pool:
                raise ZFSPoolNotFoundError(f"Pool {pool_name} not found")
            
            success = await self._pool_repository.stop_scrub(pool_name)
            
            if success:
                logger.info(f"Stopped scrub for pool: {pool_name}")
            
            return success
            
        except (ZFSOperationError, ZFSPoolNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to stop scrub for pool {pool_name}: {e}")
            raise ZFSOperationError(f"Failed to stop scrub for pool {pool_name}: {e}")
    
    async def get_scrub_status(self, pool_name: str) -> Dict[str, Any]:
        """Get scrub status for the pool"""
        try:
            pool = await self._pool_repository.find_by_name(pool_name)
            if not pool:
                raise ZFSPoolNotFoundError(f"Pool {pool_name} not found")
            
            return await self._pool_repository.get_scrub_status(pool_name)
            
        except (ZFSOperationError, ZFSPoolNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to get scrub status for pool {pool_name}: {e}")
            raise ZFSOperationError(f"Failed to get scrub status for pool {pool_name}: {e}")
    
    async def export_pool(self, pool_name: str, force: bool = False) -> bool:
        """Export a ZFS pool"""
        try:
            pool = await self._pool_repository.find_by_name(pool_name)
            if not pool:
                raise ZFSPoolNotFoundError(f"Pool {pool_name} not found")
            
            # Business logic validation
            if not pool.can_be_exported() and not force:
                raise ZFSOperationError(
                    f"Pool {pool_name} cannot be exported safely. "
                    "It may have active datasets or be in use. Use force=True to override."
                )
            
            success = await self._pool_repository.export(pool_name, force)
            
            if success:
                logger.info(f"Exported pool: {pool_name}")
            
            return success
            
        except (ZFSOperationError, ZFSPoolNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to export pool {pool_name}: {e}")
            raise ZFSOperationError(f"Failed to export pool {pool_name}: {e}")
    
    async def import_pool(self, pool_name: str, force: bool = False, altroot: Optional[str] = None) -> bool:
        """Import a ZFS pool"""
        try:
            # Check if pool already exists
            existing_pool = await self._pool_repository.find_by_name(pool_name)
            if existing_pool and not force:
                raise ZFSOperationError(f"Pool {pool_name} already exists. Use force=True to override.")
            
            success = await self._pool_repository.import_pool(pool_name, force, altroot)
            
            if success:
                logger.info(f"Imported pool: {pool_name}")
            
            return success
            
        except ZFSOperationError:
            raise
        except Exception as e:
            logger.error(f"Failed to import pool {pool_name}: {e}")
            raise ZFSOperationError(f"Failed to import pool {pool_name}: {e}")
    
    async def get_pool_history(self, pool_name: str) -> List[Dict[str, Any]]:
        """Get pool history"""
        try:
            pool = await self._pool_repository.find_by_name(pool_name)
            if not pool:
                raise ZFSPoolNotFoundError(f"Pool {pool_name} not found")
            
            return await self._pool_repository.get_history(pool_name)
            
        except (ZFSOperationError, ZFSPoolNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to get pool history for {pool_name}: {e}")
            raise ZFSOperationError(f"Failed to get pool history for {pool_name}: {e}")
    
    async def get_pool_events(self, pool_name: str) -> List[Dict[str, Any]]:
        """Get pool events"""
        try:
            pool = await self._pool_repository.find_by_name(pool_name)
            if not pool:
                raise ZFSPoolNotFoundError(f"Pool {pool_name} not found")
            
            return await self._pool_repository.get_events(pool_name)
            
        except (ZFSOperationError, ZFSPoolNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to get pool events for {pool_name}: {e}")
            raise ZFSOperationError(f"Failed to get pool events for {pool_name}: {e}")
    
    async def get_pool_iostat(self, pool_name: str) -> Dict[str, Any]:
        """Get pool I/O statistics"""
        try:
            pool = await self._pool_repository.find_by_name(pool_name)
            if not pool:
                raise ZFSPoolNotFoundError(f"Pool {pool_name} not found")
            
            return await self._pool_repository.get_iostat(pool_name)
            
        except (ZFSOperationError, ZFSPoolNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to get pool iostat for {pool_name}: {e}")
            raise ZFSOperationError(f"Failed to get pool iostat for {pool_name}: {e}")
    
    async def set_pool_property(self, pool_name: str, property_name: str, value: str) -> bool:
        """Set a pool property"""
        try:
            pool = await self._pool_repository.find_by_name(pool_name)
            if not pool:
                raise ZFSPoolNotFoundError(f"Pool {pool_name} not found")
            
            # Business logic validation for critical properties
            if property_name in ['readonly', 'version'] and not pool.is_healthy():
                raise ZFSOperationError(
                    f"Cannot modify {property_name} on unhealthy pool {pool_name}"
                )
            
            success = await self._pool_repository.set_property(pool_name, property_name, value)
            
            if success:
                logger.info(f"Set property {property_name}={value} for pool: {pool_name}")
            
            return success
            
        except (ZFSOperationError, ZFSPoolNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to set property {property_name} for pool {pool_name}: {e}")
            raise ZFSOperationError(f"Failed to set property {property_name} for pool {pool_name}: {e}")
    
    async def clear_pool_errors(self, pool_name: str) -> bool:
        """Clear pool errors"""
        try:
            pool = await self._pool_repository.find_by_name(pool_name)
            if not pool:
                raise ZFSPoolNotFoundError(f"Pool {pool_name} not found")
            
            success = await self._pool_repository.clear_errors(pool_name)
            
            if success:
                logger.info(f"Cleared errors for pool: {pool_name}")
            
            return success
            
        except (ZFSOperationError, ZFSPoolNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to clear errors for pool {pool_name}: {e}")
            raise ZFSOperationError(f"Failed to clear errors for pool {pool_name}: {e}")
    
    async def get_pool_health_summary(self) -> Dict[str, Any]:
        """Get health summary for all pools"""
        try:
            pools = await self._pool_repository.list_all()
            
            healthy_pools = []
            unhealthy_pools = []
            pools_with_errors = []
            pools_needing_attention = []
            
            total_capacity = StorageSize.from_bytes(0)
            total_used = StorageSize.from_bytes(0)
            
            for pool in pools:
                if pool.is_healthy():
                    healthy_pools.append(pool.name)
                else:
                    unhealthy_pools.append(pool.name)
                
                if pool.has_errors():
                    pools_with_errors.append(pool.name)
                
                if pool.needs_attention():
                    pools_needing_attention.append(pool.name)
                
                if pool.total_size:
                    total_capacity = StorageSize.from_bytes(
                        total_capacity.bytes + pool.total_size.bytes
                    )
                
                if pool.used_size:
                    total_used = StorageSize.from_bytes(
                        total_used.bytes + pool.used_size.bytes
                    )
            
            overall_usage = 0.0
            if total_capacity.bytes > 0:
                overall_usage = (total_used.bytes / total_capacity.bytes) * 100
            
            return {
                'total_pools': len(pools),
                'healthy_pools': len(healthy_pools),
                'unhealthy_pools': len(unhealthy_pools),
                'pools_with_errors': len(pools_with_errors),
                'pools_needing_attention': len(pools_needing_attention),
                'total_capacity': str(total_capacity),
                'total_used': str(total_used),
                'overall_usage_percentage': round(overall_usage, 2),
                'healthy_pool_names': healthy_pools,
                'unhealthy_pool_names': unhealthy_pools,
                'pools_with_errors_names': pools_with_errors,
                'pools_needing_attention_names': pools_needing_attention
            }
            
        except Exception as e:
            logger.error(f"Failed to get pool health summary: {e}")
            raise ZFSOperationError(f"Failed to get pool health summary: {e}")
    
    async def recommend_pool_actions(self, pool_name: str) -> List[Dict[str, Any]]:
        """Get recommended actions for a pool"""
        try:
            pool = await self._pool_repository.find_by_name(pool_name)
            if not pool:
                raise ZFSPoolNotFoundError(f"Pool {pool_name} not found")
            
            recommendations = []
            
            # Health-based recommendations
            if not pool.is_healthy():
                recommendations.append({
                    'priority': 'high',
                    'action': 'investigate_health',
                    'title': 'Pool Health Issue',
                    'description': f'Pool {pool_name} is not healthy. Check pool status and resolve issues.',
                    'command': f'zpool status {pool_name}'
                })
            
            # Error-based recommendations
            if pool.has_errors():
                recommendations.append({
                    'priority': 'high',
                    'action': 'clear_errors',
                    'title': 'Pool Has Errors',
                    'description': f'Pool {pool_name} has errors. Consider clearing them after resolving the root cause.',
                    'command': f'zpool clear {pool_name}'
                })
            
            # Usage-based recommendations
            usage = pool.usage_percentage()
            if usage > 90:
                recommendations.append({
                    'priority': 'high',
                    'action': 'free_space',
                    'title': 'Low Free Space',
                    'description': f'Pool {pool_name} is {usage:.1f}% full. Consider freeing up space.',
                    'command': f'zfs list -o space {pool_name}'
                })
            elif usage > 80:
                recommendations.append({
                    'priority': 'medium',
                    'action': 'monitor_space',
                    'title': 'Monitor Space Usage',
                    'description': f'Pool {pool_name} is {usage:.1f}% full. Monitor space usage closely.',
                    'command': f'zfs list -o space {pool_name}'
                })
            
            # Scrub recommendations
            scrub_status = await self._pool_repository.get_scrub_status(pool_name)
            if scrub_status.get('last_scrub_age_days', 0) > 30:
                recommendations.append({
                    'priority': 'medium',
                    'action': 'scrub_pool',
                    'title': 'Scrub Pool',
                    'description': f'Pool {pool_name} has not been scrubbed in over 30 days. Consider running a scrub.',
                    'command': f'zpool scrub {pool_name}'
                })
            
            # Performance recommendations
            iostat = await self._pool_repository.get_iostat(pool_name)
            if iostat.get('high_latency', False):
                recommendations.append({
                    'priority': 'low',
                    'action': 'check_performance',
                    'title': 'Check Performance',
                    'description': f'Pool {pool_name} may have performance issues. Check I/O statistics.',
                    'command': f'zpool iostat {pool_name}'
                })
            
            return recommendations
            
        except (ZFSOperationError, ZFSPoolNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to get pool recommendations for {pool_name}: {e}")
            raise ZFSOperationError(f"Failed to get pool recommendations for {pool_name}: {e}")