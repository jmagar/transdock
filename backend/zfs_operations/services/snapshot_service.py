from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from ..core.interfaces.command_executor import ICommandExecutor
from ..core.interfaces.security_validator import ISecurityValidator  
from ..core.interfaces.logger_interface import ILogger
from ..core.entities.snapshot import Snapshot
from ..core.entities.dataset import Dataset
from ..core.value_objects.dataset_name import DatasetName
from ..core.value_objects.size_value import SizeValue
from ..core.exceptions.zfs_exceptions import (
    SnapshotException, 
    SnapshotNotFoundError, 
    SnapshotExistsError,
    DatasetException
)
from ..core.exceptions.validation_exceptions import ValidationException
from ..core.result import Result


class SnapshotService:
    """Service for managing ZFS snapshots with comprehensive operations."""
    
    def __init__(self, 
                 executor: ICommandExecutor,
                 validator: ISecurityValidator,
                 logger: ILogger):
        self._executor = executor
        self._validator = validator
        self._logger = logger
    
    async def create_snapshot(self, 
                            dataset_name: DatasetName, 
                            snapshot_name: str,
                            recursive: bool = False) -> Result[Snapshot, SnapshotException]:
        """Create a new snapshot of a dataset."""
        try:
            self._logger.info(f"Creating snapshot {snapshot_name} for dataset: {dataset_name}")
            
            # Validate inputs
            validation_result = await self._validate_snapshot_inputs(dataset_name, snapshot_name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Build full snapshot name
            full_snapshot_name = f"{dataset_name}@{snapshot_name}"
            
            # Check if snapshot already exists
            exists_result = await self._snapshot_exists(full_snapshot_name)
            if exists_result.is_failure:
                return Result.failure(exists_result.error)
            if exists_result.value:
                return Result.failure(SnapshotExistsError(full_snapshot_name))
            
            # Build create command
            command_args = ["snapshot"]
            if recursive:
                command_args.append("-r")
            command_args.append(full_snapshot_name)
            
            # Execute create command
            result = await self._executor.execute_zfs(*command_args)
            
            if not result.is_success:
                return Result.failure(SnapshotException(
                    f"Failed to create snapshot: {result.stderr}",
                    error_code="SNAPSHOT_CREATE_FAILED"
                ))
            
            # Fetch the created snapshot
            created_snapshot = await self.get_snapshot(dataset_name, snapshot_name)
            if created_snapshot.is_failure:
                return Result.failure(SnapshotException(
                    f"Snapshot created but failed to fetch: {created_snapshot.error}",
                    error_code="SNAPSHOT_CREATE_FETCH_FAILED"
                ))
            
            self._logger.info(f"Successfully created snapshot: {full_snapshot_name}")
            return Result.success(created_snapshot.value)
            
        except Exception as e:
            self._logger.error(f"Unexpected error creating snapshot {snapshot_name}: {e}")
            return Result.failure(SnapshotException(
                f"Unexpected error: {str(e)}",
                error_code="SNAPSHOT_CREATE_UNEXPECTED_ERROR"
            ))
    
    async def get_snapshot(self, 
                         dataset_name: DatasetName, 
                         snapshot_name: str) -> Result[Snapshot, SnapshotException]:
        """Get detailed information about a specific snapshot."""
        try:
            full_snapshot_name = f"{dataset_name}@{snapshot_name}"
            self._logger.info(f"Fetching snapshot: {full_snapshot_name}")
            
            # Validate inputs
            validation_result = await self._validate_snapshot_inputs(dataset_name, snapshot_name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Execute ZFS list command for snapshot information
            result = await self._executor.execute_zfs(
                "list", "-H", "-t", "snapshot", "-o", 
                "name,used,referenced,creation,clones",
                full_snapshot_name
            )
            
            if not result.is_success:
                if "dataset does not exist" in result.stderr.lower():
                    return Result.failure(SnapshotNotFoundError(full_snapshot_name))
                return Result.failure(SnapshotException(
                    f"Failed to get snapshot info: {result.stderr}",
                    error_code="SNAPSHOT_INFO_FAILED"
                ))
            
            # Parse snapshot information
            snapshot_info = await self._parse_snapshot_info(result.stdout, dataset_name, snapshot_name)
            if snapshot_info.is_failure:
                return Result.failure(snapshot_info.error)
            
            self._logger.info(f"Successfully fetched snapshot: {full_snapshot_name}")
            return Result.success(snapshot_info.value)
            
        except Exception as e:
            self._logger.error(f"Unexpected error fetching snapshot {snapshot_name}: {e}")
            return Result.failure(SnapshotException(
                f"Unexpected error: {str(e)}",
                error_code="SNAPSHOT_UNEXPECTED_ERROR"
            ))
    
    async def list_snapshots(self, 
                           dataset_name: Optional[DatasetName] = None,
                           recursive: bool = False) -> Result[List[Snapshot], SnapshotException]:
        """List snapshots for a dataset or all datasets."""
        try:
            self._logger.info(f"Listing snapshots for dataset: {dataset_name or 'all'}")
            
            # Build command
            command_args = ["list", "-H", "-t", "snapshot", "-o", 
                          "name,used,referenced,creation,clones"]
            
            if recursive:
                command_args.append("-r")
            
            if dataset_name:
                # Validate dataset name
                validated_dataset = self._validator.validate_dataset_name(str(dataset_name))
                if not validated_dataset:
                    return Result.failure(SnapshotException(
                        f"Invalid dataset name: {dataset_name}",
                        error_code="INVALID_DATASET_NAME"
                    ))
                command_args.append(str(dataset_name))
            
            # Execute command
            result = await self._executor.execute_zfs(*command_args)
            
            if not result.is_success:
                return Result.failure(SnapshotException(
                    f"Failed to list snapshots: {result.stderr}",
                    error_code="SNAPSHOT_LIST_FAILED"
                ))
            
            # Parse snapshot list
            snapshots_result = await self._parse_snapshot_list(result.stdout)
            if snapshots_result.is_failure:
                return Result.failure(snapshots_result.error)
            
            self._logger.info(f"Successfully listed {len(snapshots_result.value)} snapshots")
            return Result.success(snapshots_result.value)
            
        except Exception as e:
            self._logger.error(f"Unexpected error listing snapshots: {e}")
            return Result.failure(SnapshotException(
                f"Unexpected error: {str(e)}",
                error_code="SNAPSHOT_LIST_UNEXPECTED_ERROR"
            ))
    
    async def destroy_snapshot(self, 
                             dataset_name: DatasetName, 
                             snapshot_name: str,
                             force: bool = False,
                             recursive: bool = False) -> Result[bool, SnapshotException]:
        """Destroy a snapshot."""
        try:
            full_snapshot_name = f"{dataset_name}@{snapshot_name}"
            self._logger.info(f"Destroying snapshot: {full_snapshot_name} (force={force}, recursive={recursive})")
            
            # Validate inputs
            validation_result = await self._validate_snapshot_inputs(dataset_name, snapshot_name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Check if snapshot exists
            exists_result = await self._snapshot_exists(full_snapshot_name)
            if exists_result.is_failure:
                return Result.failure(exists_result.error)
            if not exists_result.value:
                return Result.failure(SnapshotNotFoundError(full_snapshot_name))
            
            # Build destroy command
            command_args = ["destroy"]
            if force:
                command_args.append("-f")
            if recursive:
                command_args.append("-r")
            command_args.append(full_snapshot_name)
            
            # Execute destroy command
            result = await self._executor.execute_zfs(*command_args)
            
            if not result.is_success:
                return Result.failure(SnapshotException(
                    f"Failed to destroy snapshot: {result.stderr}",
                    error_code="SNAPSHOT_DESTROY_FAILED"
                ))
            
            self._logger.info(f"Successfully destroyed snapshot: {full_snapshot_name}")
            return Result.success(True)
            
        except Exception as e:
            self._logger.error(f"Unexpected error destroying snapshot {snapshot_name}: {e}")
            return Result.failure(SnapshotException(
                f"Unexpected error: {str(e)}",
                error_code="SNAPSHOT_DESTROY_UNEXPECTED_ERROR"
            ))
    
    async def rollback_to_snapshot(self, 
                                 dataset_name: DatasetName, 
                                 snapshot_name: str,
                                 force: bool = False) -> Result[bool, SnapshotException]:
        """Rollback a dataset to a specific snapshot."""
        try:
            full_snapshot_name = f"{dataset_name}@{snapshot_name}"
            self._logger.info(f"Rolling back to snapshot: {full_snapshot_name} (force={force})")
            
            # Validate inputs
            validation_result = await self._validate_snapshot_inputs(dataset_name, snapshot_name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Check if snapshot exists
            exists_result = await self._snapshot_exists(full_snapshot_name)
            if exists_result.is_failure:
                return Result.failure(exists_result.error)
            if not exists_result.value:
                return Result.failure(SnapshotNotFoundError(full_snapshot_name))
            
            # Build rollback command
            command_args = ["rollback"]
            if force:
                command_args.append("-f")
            command_args.append(full_snapshot_name)
            
            # Execute rollback command
            result = await self._executor.execute_zfs(*command_args)
            
            if not result.is_success:
                return Result.failure(SnapshotException(
                    f"Failed to rollback to snapshot: {result.stderr}",
                    error_code="SNAPSHOT_ROLLBACK_FAILED"
                ))
            
            self._logger.info(f"Successfully rolled back to snapshot: {full_snapshot_name}")
            return Result.success(True)
            
        except Exception as e:
            self._logger.error(f"Unexpected error rolling back to snapshot {snapshot_name}: {e}")
            return Result.failure(SnapshotException(
                f"Unexpected error: {str(e)}",
                error_code="SNAPSHOT_ROLLBACK_UNEXPECTED_ERROR"
            ))
    
    async def create_incremental_snapshot(self, 
                                        dataset_name: DatasetName,
                                        base_snapshot_name: str,
                                        new_snapshot_name: str) -> Result[Snapshot, SnapshotException]:
        """Create an incremental snapshot based on a previous snapshot."""
        try:
            self._logger.info(f"Creating incremental snapshot {new_snapshot_name} from {base_snapshot_name}")
            
            # Validate inputs
            validation_result = await self._validate_snapshot_inputs(dataset_name, base_snapshot_name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            validation_result = await self._validate_snapshot_inputs(dataset_name, new_snapshot_name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Check if base snapshot exists
            base_full_name = f"{dataset_name}@{base_snapshot_name}"
            exists_result = await self._snapshot_exists(base_full_name)
            if exists_result.is_failure:
                return Result.failure(exists_result.error)
            if not exists_result.value:
                return Result.failure(SnapshotNotFoundError(base_full_name))
            
            # Create new snapshot
            create_result = await self.create_snapshot(dataset_name, new_snapshot_name)
            if create_result.is_failure:
                return Result.failure(create_result.error)
            
            # Create bookmark for incremental operations
            bookmark_result = await self._create_bookmark(dataset_name, base_snapshot_name)
            if bookmark_result.is_failure:
                self._logger.warning(f"Failed to create bookmark for incremental: {bookmark_result.error}")
            
            self._logger.info(f"Successfully created incremental snapshot: {new_snapshot_name}")
            return Result.success(create_result.value)
            
        except Exception as e:
            self._logger.error(f"Unexpected error creating incremental snapshot: {e}")
            return Result.failure(SnapshotException(
                f"Unexpected error: {str(e)}",
                error_code="SNAPSHOT_INCREMENTAL_UNEXPECTED_ERROR"
            ))
    
    async def apply_retention_policy(self, 
                                   dataset_name: DatasetName,
                                   retention_days: int,
                                   dry_run: bool = False) -> Result[Dict[str, Any], SnapshotException]:
        """Apply retention policy to snapshots of a dataset."""
        try:
            self._logger.info(f"Applying retention policy to {dataset_name} (days={retention_days}, dry_run={dry_run})")
            
            # Get all snapshots for the dataset
            snapshots_result = await self.list_snapshots(dataset_name)
            if snapshots_result.is_failure:
                return Result.failure(snapshots_result.error)
            
            snapshots = snapshots_result.value
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            # Identify snapshots to delete
            to_delete = []
            to_keep = []
            
            for snapshot in snapshots:
                if snapshot.creation_time and snapshot.creation_time < cutoff_date:
                    # Check if snapshot has clones
                    if snapshot.has_clones():
                        self._logger.warning(f"Snapshot {snapshot.full_name} has clones, skipping deletion")
                        to_keep.append(snapshot)
                    else:
                        to_delete.append(snapshot)
                else:
                    to_keep.append(snapshot)
            
            # Delete snapshots if not dry run
            deleted_count = 0
            failed_deletions = []
            
            if not dry_run:
                for snapshot in to_delete:
                    destroy_result = await self.destroy_snapshot(
                        snapshot.dataset, 
                        snapshot.name, 
                        force=True
                    )
                    if destroy_result.is_success:
                        deleted_count += 1
                    else:
                        failed_deletions.append({
                            'snapshot': snapshot.full_name,
                            'error': str(destroy_result.error)
                        })
            
            result = {
                'dataset': str(dataset_name),
                'retention_days': retention_days,
                'total_snapshots': len(snapshots),
                'to_delete': len(to_delete),
                'to_keep': len(to_keep),
                'deleted_count': deleted_count,
                'failed_deletions': failed_deletions,
                'dry_run': dry_run
            }
            
            self._logger.info(f"Retention policy applied: {result}")
            return Result.success(result)
            
        except Exception as e:
            self._logger.error(f"Unexpected error applying retention policy: {e}")
            return Result.failure(SnapshotException(
                f"Unexpected error: {str(e)}",
                error_code="SNAPSHOT_RETENTION_UNEXPECTED_ERROR"
            ))
    
    async def get_snapshot_space_efficiency(self, 
                                          dataset_name: DatasetName, 
                                          snapshot_name: str) -> Result[Dict[str, Any], SnapshotException]:
        """Calculate space efficiency metrics for a snapshot."""
        try:
            full_snapshot_name = f"{dataset_name}@{snapshot_name}"
            self._logger.info(f"Calculating space efficiency for snapshot: {full_snapshot_name}")
            
            # Get snapshot details
            snapshot_result = await self.get_snapshot(dataset_name, snapshot_name)
            if snapshot_result.is_failure:
                return Result.failure(snapshot_result.error)
            
            snapshot = snapshot_result.value
            
            # Calculate efficiency metrics
            efficiency = {
                'snapshot_name': full_snapshot_name,
                'used_space': snapshot.used,
                'referenced_space': snapshot.referenced,
                'space_efficiency': 0.0,
                'compression_ratio': 1.0,
                'deduplication_ratio': 1.0
            }
            
            # Calculate space efficiency
            if snapshot.referenced and snapshot.referenced.bytes > 0:
                efficiency['space_efficiency'] = (
                    1.0 - (snapshot.used.bytes / snapshot.referenced.bytes)
                ) * 100
            
            # Get compression and deduplication ratios
            compression_result = await self._get_compression_ratio(dataset_name)
            if compression_result.is_success:
                efficiency['compression_ratio'] = compression_result.value
            
            dedup_result = await self._get_deduplication_ratio(dataset_name)
            if dedup_result.is_success:
                efficiency['deduplication_ratio'] = dedup_result.value
            
            self._logger.info(f"Space efficiency calculated: {efficiency}")
            return Result.success(efficiency)
            
        except Exception as e:
            self._logger.error(f"Unexpected error calculating space efficiency: {e}")
            return Result.failure(SnapshotException(
                f"Unexpected error: {str(e)}",
                error_code="SNAPSHOT_EFFICIENCY_UNEXPECTED_ERROR"
            ))
    
    # Private helper methods
    
    async def _validate_snapshot_inputs(self, 
                                      dataset_name: DatasetName, 
                                      snapshot_name: str) -> Result[bool, ValidationException]:
        """Validate snapshot inputs using security validator."""
        try:
            # Validate dataset name
            validated_dataset = self._validator.validate_dataset_name(str(dataset_name))
            if not validated_dataset:
                return Result.failure(ValidationException(
                    f"Invalid dataset name: {dataset_name}"
                ))
            
            # Validate snapshot name
            validated_snapshot = self._validator.validate_snapshot_name(snapshot_name)
            if not validated_snapshot:
                return Result.failure(ValidationException(
                    f"Invalid snapshot name: {snapshot_name}"
                ))
            
            return Result.success(True)
            
        except Exception as e:
            return Result.failure(ValidationException(
                f"Input validation failed: {str(e)}"
            ))
    
    async def _snapshot_exists(self, full_snapshot_name: str) -> Result[bool, SnapshotException]:
        """Check if a snapshot exists."""
        try:
            result = await self._executor.execute_zfs(
                "list", "-H", "-t", "snapshot", "-o", "name", full_snapshot_name
            )
            return Result.success(result.is_success)
        except Exception as e:
            return Result.failure(SnapshotException(
                f"Failed to check snapshot existence: {str(e)}",
                error_code="SNAPSHOT_EXISTS_CHECK_FAILED"
            ))
    
    async def _create_bookmark(self, 
                             dataset_name: DatasetName, 
                             snapshot_name: str) -> Result[bool, SnapshotException]:
        """Create a bookmark for a snapshot."""
        try:
            bookmark_name = f"{dataset_name}#{snapshot_name}_bookmark"
            
            result = await self._executor.execute_zfs(
                "bookmark", f"{dataset_name}@{snapshot_name}", bookmark_name
            )
            
            if not result.is_success:
                return Result.failure(SnapshotException(
                    f"Failed to create bookmark: {result.stderr}",
                    error_code="BOOKMARK_CREATE_FAILED"
                ))
            
            return Result.success(True)
            
        except Exception as e:
            return Result.failure(SnapshotException(
                f"Failed to create bookmark: {str(e)}",
                error_code="BOOKMARK_CREATE_UNEXPECTED_ERROR"
            ))
    
    async def _get_compression_ratio(self, dataset_name: DatasetName) -> Result[float, SnapshotException]:
        """Get compression ratio for a dataset."""
        try:
            result = await self._executor.execute_zfs(
                "get", "-H", "-o", "value", "compressratio", str(dataset_name)
            )
            
            if not result.is_success:
                return Result.failure(SnapshotException(
                    f"Failed to get compression ratio: {result.stderr}",
                    error_code="COMPRESSION_RATIO_FAILED"
                ))
            
            # Parse compression ratio (e.g., "1.50x" -> 1.5)
            ratio_str = result.stdout.strip()
            if ratio_str.endswith('x'):
                ratio = float(ratio_str[:-1])
            else:
                ratio = float(ratio_str)
            
            return Result.success(ratio)
            
        except Exception as e:
            return Result.failure(SnapshotException(
                f"Failed to parse compression ratio: {str(e)}",
                error_code="COMPRESSION_RATIO_PARSE_FAILED"
            ))
    
    async def _get_deduplication_ratio(self, dataset_name: DatasetName) -> Result[float, SnapshotException]:
        """Get deduplication ratio for a dataset."""
        try:
            result = await self._executor.execute_zfs(
                "get", "-H", "-o", "value", "dedup", str(dataset_name)
            )
            
            if not result.is_success:
                return Result.failure(SnapshotException(
                    f"Failed to get deduplication ratio: {result.stderr}",
                    error_code="DEDUPLICATION_RATIO_FAILED"
                ))
            
            # Parse deduplication ratio (e.g., "1.50x" -> 1.5)
            ratio_str = result.stdout.strip()
            if ratio_str.endswith('x'):
                ratio = float(ratio_str[:-1])
            else:
                ratio = 1.0  # Default if dedup is off
            
            return Result.success(ratio)
            
        except Exception as e:
            return Result.failure(SnapshotException(
                f"Failed to parse deduplication ratio: {str(e)}",
                error_code="DEDUPLICATION_RATIO_PARSE_FAILED"
            ))
    
    async def _parse_snapshot_info(self, 
                                 output: str, 
                                 dataset_name: DatasetName, 
                                 snapshot_name: str) -> Result[Snapshot, SnapshotException]:
        """Parse snapshot information from ZFS output."""
        try:
            lines = output.strip().split('\n')
            if not lines or not lines[0].strip():
                return Result.failure(SnapshotException(
                    "Empty snapshot info output",
                    error_code="SNAPSHOT_INFO_EMPTY"
                ))
            
            parts = lines[0].split('\t')
            if len(parts) < 5:
                return Result.failure(SnapshotException(
                    f"Invalid snapshot info format: {lines[0]}",
                    error_code="SNAPSHOT_INFO_FORMAT_INVALID"
                ))
            
            # Parse values
            used = SizeValue.from_zfs_string(parts[1]) if parts[1] != '-' else SizeValue(0)
            referenced = SizeValue.from_zfs_string(parts[2]) if parts[2] != '-' else SizeValue(0)
            
            # Parse creation time
            creation_time = None
            if parts[3] != '-':
                try:
                    creation_time = datetime.fromtimestamp(int(parts[3]))
                except (ValueError, TypeError):
                    pass
            
            # Parse clones
            clones = []
            if parts[4] != '-':
                clones = [clone.strip() for clone in parts[4].split(',') if clone.strip()]
            
            snapshot = Snapshot(
                name=snapshot_name,
                dataset=dataset_name,
                creation_time=creation_time or datetime.now(),
                used=used,
                referenced=referenced,
                clones=clones
            )
            
            return Result.success(snapshot)
            
        except Exception as e:
            return Result.failure(SnapshotException(
                f"Failed to parse snapshot info: {str(e)}",
                error_code="SNAPSHOT_INFO_PARSE_FAILED"
            ))
    
    async def _parse_snapshot_list(self, output: str) -> Result[List[Snapshot], SnapshotException]:
        """Parse list of snapshots from ZFS output."""
        try:
            snapshots = []
            lines = output.strip().split('\n')
            
            for line in lines:
                if not line.strip():
                    continue
                
                parts = line.split('\t')
                if len(parts) < 5:
                    continue
                
                try:
                    # Parse snapshot name (format: dataset@snapshot)
                    full_name = parts[0]
                    if '@' not in full_name:
                        continue
                    
                    dataset_str, snapshot_name = full_name.split('@', 1)
                    dataset_name = DatasetName.from_string(dataset_str)
                    
                    # Parse other fields
                    used = SizeValue.from_zfs_string(parts[1]) if parts[1] != '-' else SizeValue(0)
                    referenced = SizeValue.from_zfs_string(parts[2]) if parts[2] != '-' else SizeValue(0)
                    
                    # Parse creation time
                    creation_time = None
                    if parts[3] != '-':
                        try:
                            creation_time = datetime.fromtimestamp(int(parts[3]))
                        except (ValueError, TypeError):
                            pass
                    
                    # Parse clones
                    clones = []
                    if parts[4] != '-':
                        clones = [clone.strip() for clone in parts[4].split(',') if clone.strip()]
                    
                    snapshot = Snapshot(
                        name=snapshot_name,
                        dataset=dataset_name,
                        creation_time=creation_time or datetime.now(),
                        used=used,
                        referenced=referenced,
                        clones=clones
                    )
                    
                    snapshots.append(snapshot)
                    
                except Exception as e:
                    self._logger.warning(f"Failed to parse snapshot line: {line}, error: {e}")
                    continue
            
            return Result.success(snapshots)
            
        except Exception as e:
            return Result.failure(SnapshotException(
                f"Failed to parse snapshot list: {str(e)}",
                error_code="SNAPSHOT_LIST_PARSE_FAILED"
            )) 