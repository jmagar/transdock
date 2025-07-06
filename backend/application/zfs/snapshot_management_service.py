"""Snapshot management application service"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from ...core.entities.zfs_entity import ZFSSnapshot
from ...core.value_objects.dataset_name import DatasetName
from ...core.value_objects.snapshot_name import SnapshotName
from ...core.interfaces.zfs_repository import ZFSSnapshotRepository, ZFSDatasetRepository
from ...core.exceptions.zfs_exceptions import ZFSOperationError, ZFSSnapshotNotFoundError
import logging

logger = logging.getLogger(__name__)


class SnapshotManagementService:
    """Application service for managing ZFS snapshots"""
    
    def __init__(self, snapshot_repository: ZFSSnapshotRepository, dataset_repository: ZFSDatasetRepository):
        self._snapshot_repository = snapshot_repository
        self._dataset_repository = dataset_repository
    
    async def create_snapshot(
        self, 
        dataset_name: str, 
        snapshot_name: Optional[str] = None,
        prefix: str = "transdock"
    ) -> ZFSSnapshot:
        """Create a new ZFS snapshot"""
        try:
            dataset = DatasetName(dataset_name)
            
            # Validate dataset exists
            if not await self._dataset_repository.exists(dataset):
                raise ZFSOperationError(f"Dataset {dataset_name} does not exist", dataset=dataset_name)
            
            # Generate snapshot name if not provided
            if not snapshot_name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                snapshot_name = f"{prefix}_{timestamp}"
            
            # Create and validate snapshot name
            full_snapshot_name = SnapshotName.create(dataset, snapshot_name)
            
            # Create through repository
            snapshot = await self._snapshot_repository.create(dataset, snapshot_name)
            
            logger.info(f"Created snapshot: {full_snapshot_name}")
            return snapshot
            
        except ZFSOperationError:
            raise
        except Exception as e:
            logger.error(f"Failed to create snapshot for dataset {dataset_name}: {e}")
            raise ZFSOperationError(f"Failed to create snapshot for dataset {dataset_name}: {e}")
    
    async def get_snapshot(self, snapshot_name: str) -> Optional[ZFSSnapshot]:
        """Get a snapshot by name"""
        try:
            name = SnapshotName(snapshot_name)
            return await self._snapshot_repository.find_by_name(name)
        except Exception as e:
            logger.error(f"Failed to get snapshot {snapshot_name}: {e}")
            return None
    
    async def list_snapshots(self, dataset_name: Optional[str] = None) -> List[ZFSSnapshot]:
        """List snapshots for a dataset or all snapshots"""
        try:
            if dataset_name:
                dataset = DatasetName(dataset_name)
                return await self._snapshot_repository.list_for_dataset(dataset)
            return await self._snapshot_repository.list_all()
        except Exception as e:
            logger.error(f"Failed to list snapshots: {e}")
            return []
    
    async def delete_snapshot(self, snapshot_name: str) -> bool:
        """Delete a snapshot"""
        try:
            name = SnapshotName(snapshot_name)
            
            # Validate snapshot exists
            snapshot = await self._snapshot_repository.find_by_name(name)
            if not snapshot:
                raise ZFSSnapshotNotFoundError(f"Snapshot {snapshot_name} does not exist")
            
            success = await self._snapshot_repository.delete(name)
            
            if success:
                logger.info(f"Deleted snapshot: {snapshot_name}")
            
            return success
            
        except (ZFSOperationError, ZFSSnapshotNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to delete snapshot {snapshot_name}: {e}")
            raise ZFSOperationError(f"Failed to delete snapshot {snapshot_name}: {e}")
    
    async def rollback_to_snapshot(self, snapshot_name: str, force: bool = False) -> bool:
        """Rollback dataset to a specific snapshot"""
        try:
            name = SnapshotName(snapshot_name)
            
            # Validate snapshot exists
            snapshot = await self._snapshot_repository.find_by_name(name)
            if not snapshot:
                raise ZFSSnapshotNotFoundError(f"Snapshot {snapshot_name} does not exist")
            
            # Business logic validation
            if not snapshot.can_rollback() and not force:
                raise ZFSOperationError(
                    f"Snapshot {snapshot_name} cannot be rolled back. Use force=True to override."
                )
            
            success = await self._snapshot_repository.rollback(name, force)
            
            if success:
                logger.info(f"Rolled back to snapshot: {snapshot_name}")
            
            return success
            
        except (ZFSOperationError, ZFSSnapshotNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to rollback to snapshot {snapshot_name}: {e}")
            raise ZFSOperationError(f"Failed to rollback to snapshot {snapshot_name}: {e}")
    
    async def clone_snapshot(self, snapshot_name: str, target_dataset_name: str) -> bool:
        """Clone a snapshot to create a new dataset"""
        try:
            snapshot_name_obj = SnapshotName(snapshot_name)
            target_dataset = DatasetName(target_dataset_name)
            
            # Validate snapshot exists
            snapshot = await self._snapshot_repository.find_by_name(snapshot_name_obj)
            if not snapshot:
                raise ZFSSnapshotNotFoundError(f"Snapshot {snapshot_name} does not exist")
            
            # Validate target dataset doesn't exist
            if await self._dataset_repository.exists(target_dataset):
                raise ZFSOperationError(f"Target dataset {target_dataset_name} already exists")
            
            # Business logic validation
            if not snapshot.can_clone():
                raise ZFSOperationError(f"Snapshot {snapshot_name} cannot be cloned")
            
            success = await self._snapshot_repository.clone(snapshot_name_obj, target_dataset)
            
            if success:
                logger.info(f"Cloned snapshot {snapshot_name} to dataset {target_dataset_name}")
            
            return success
            
        except (ZFSOperationError, ZFSSnapshotNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to clone snapshot {snapshot_name}: {e}")
            raise ZFSOperationError(f"Failed to clone snapshot {snapshot_name}: {e}")
    
    async def send_snapshot(
        self, 
        snapshot_name: str, 
        target_host: str, 
        target_dataset_name: str
    ) -> bool:
        """Send snapshot to remote host"""
        try:
            snapshot_name_obj = SnapshotName(snapshot_name)
            target_dataset = DatasetName(target_dataset_name)
            
            # Validate snapshot exists
            snapshot = await self._snapshot_repository.find_by_name(snapshot_name_obj)
            if not snapshot:
                raise ZFSSnapshotNotFoundError(f"Snapshot {snapshot_name} does not exist")
            
            success = await self._snapshot_repository.send(
                snapshot_name_obj, target_host, target_dataset
            )
            
            if success:
                logger.info(f"Sent snapshot {snapshot_name} to {target_host}:{target_dataset_name}")
            
            return success
            
        except (ZFSOperationError, ZFSSnapshotNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to send snapshot {snapshot_name}: {e}")
            raise ZFSOperationError(f"Failed to send snapshot {snapshot_name}: {e}")
    
    async def apply_retention_policy(
        self, 
        dataset_name: str,
        keep_daily: int = 7,
        keep_weekly: int = 4,
        keep_monthly: int = 6,
        keep_yearly: int = 2
    ) -> Dict[str, Any]:
        """Apply snapshot retention policy"""
        try:
            dataset = DatasetName(dataset_name)
            
            # Get all snapshots for the dataset
            snapshots = await self._snapshot_repository.list_for_dataset(dataset)
            
            # Filter to only TransDock snapshots with timestamps
            transdock_snapshots = [
                s for s in snapshots 
                if s.is_transdock_snapshot() and s.is_timestamped()
            ]
            
            if not transdock_snapshots:
                return {
                    "total_snapshots": len(snapshots),
                    "transdock_snapshots": 0,
                    "snapshots_deleted": 0,
                    "snapshots_kept": 0,
                    "deleted_snapshots": []
                }
            
            # Sort by creation time (newest first)
            transdock_snapshots.sort(key=lambda s: s.created_at, reverse=True)
            
            # Apply retention logic
            snapshots_to_keep = set()
            snapshots_to_delete = []
            
            # Group snapshots by time periods
            now = datetime.now()
            daily_cutoff = now - timedelta(days=keep_daily)
            weekly_cutoff = now - timedelta(weeks=keep_weekly)
            monthly_cutoff = now - timedelta(days=keep_monthly * 30)
            yearly_cutoff = now - timedelta(days=keep_yearly * 365)
            
            # Keep daily snapshots
            daily_count = 0
            for snapshot in transdock_snapshots:
                if snapshot.created_at >= daily_cutoff and daily_count < keep_daily:
                    snapshots_to_keep.add(snapshot.full_name)
                    daily_count += 1
            
            # Keep weekly snapshots (one per week)
            weekly_snapshots = {}
            for snapshot in transdock_snapshots:
                if daily_cutoff <= snapshot.created_at >= weekly_cutoff:
                    week_key = snapshot.created_at.strftime("%Y-W%U")
                    if week_key not in weekly_snapshots:
                        weekly_snapshots[week_key] = snapshot
                        snapshots_to_keep.add(snapshot.full_name)
            
            # Keep monthly snapshots (one per month)
            monthly_snapshots = {}
            for snapshot in transdock_snapshots:
                if weekly_cutoff <= snapshot.created_at >= monthly_cutoff:
                    month_key = snapshot.created_at.strftime("%Y-%m")
                    if month_key not in monthly_snapshots:
                        monthly_snapshots[month_key] = snapshot
                        snapshots_to_keep.add(snapshot.full_name)
            
            # Keep yearly snapshots (one per year)
            yearly_snapshots = {}
            for snapshot in transdock_snapshots:
                if monthly_cutoff <= snapshot.created_at >= yearly_cutoff:
                    year_key = snapshot.created_at.strftime("%Y")
                    if year_key not in yearly_snapshots:
                        yearly_snapshots[year_key] = snapshot
                        snapshots_to_keep.add(snapshot.full_name)
            
            # Identify snapshots to delete
            for snapshot in transdock_snapshots:
                if snapshot.full_name not in snapshots_to_keep:
                    snapshots_to_delete.append(snapshot)
            
            # Delete excess snapshots
            deleted_snapshots = []
            for snapshot in snapshots_to_delete:
                try:
                    success = await self._snapshot_repository.delete(snapshot.name)
                    if success:
                        deleted_snapshots.append(snapshot.full_name)
                        logger.info(f"Deleted snapshot {snapshot.full_name} (retention policy)")
                except Exception as e:
                    logger.error(f"Failed to delete snapshot {snapshot.full_name}: {e}")
            
            result = {
                "total_snapshots": len(snapshots),
                "transdock_snapshots": len(transdock_snapshots),
                "snapshots_deleted": len(deleted_snapshots),
                "snapshots_kept": len(snapshots_to_keep),
                "deleted_snapshots": deleted_snapshots,
                "retention_policy": {
                    "daily": keep_daily,
                    "weekly": keep_weekly,
                    "monthly": keep_monthly,
                    "yearly": keep_yearly
                }
            }
            
            logger.info(f"Applied retention policy to {dataset_name}: kept {len(snapshots_to_keep)}, deleted {len(deleted_snapshots)}")
            return result
            
        except ZFSOperationError:
            raise
        except Exception as e:
            logger.error(f"Failed to apply retention policy to {dataset_name}: {e}")
            raise ZFSOperationError(f"Failed to apply retention policy to {dataset_name}: {e}")
    
    async def get_snapshot_details(self, snapshot_name: str) -> Dict[str, Any]:
        """Get detailed snapshot information"""
        try:
            name = SnapshotName(snapshot_name)
            
            snapshot = await self._snapshot_repository.find_by_name(name)
            if not snapshot:
                raise ZFSSnapshotNotFoundError(f"Snapshot {snapshot_name} not found")
            
            properties = await self._snapshot_repository.get_properties(name)
            
            details = {
                'name': snapshot.full_name,
                'dataset': str(snapshot.dataset_name),
                'snapshot_part': snapshot.snapshot_part,
                'created_at': snapshot.created_at.isoformat(),
                'size': str(snapshot.size) if snapshot.size else None,
                'referenced_size': str(snapshot.referenced_size) if snapshot.referenced_size else None,
                'pool': snapshot.pool_name(),
                'is_transdock_snapshot': snapshot.is_transdock_snapshot(),
                'is_timestamped': snapshot.is_timestamped(),
                'can_rollback': snapshot.can_rollback(),
                'can_clone': snapshot.can_clone(),
                'properties': properties
            }
            
            # Add timestamp if available
            if snapshot.is_timestamped():
                try:
                    timestamp = snapshot.get_timestamp()
                    details['timestamp'] = timestamp.isoformat()
                except Exception:
                    pass
            
            return details
            
        except (ZFSOperationError, ZFSSnapshotNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to get details for snapshot {snapshot_name}: {e}")
            raise ZFSOperationError(f"Failed to get details for snapshot {snapshot_name}: {e}")