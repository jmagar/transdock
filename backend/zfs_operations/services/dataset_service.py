from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from ..core.interfaces.command_executor import ICommandExecutor
from ..core.interfaces.security_validator import ISecurityValidator  
from ..core.interfaces.logger_interface import ILogger
from ..core.entities.dataset import Dataset
from ..core.value_objects.dataset_name import DatasetName
from ..core.value_objects.size_value import SizeValue
from ..core.exceptions.zfs_exceptions import (
    DatasetException, 
    DatasetNotFoundError, 
    DatasetAlreadyExistsError
)
from ..core.exceptions.validation_exceptions import ValidationException
from ..core.result import Result


class DatasetService:
    """Service for managing ZFS datasets with comprehensive operations."""
    
    def __init__(self, 
                 executor: ICommandExecutor,
                 validator: ISecurityValidator,
                 logger: ILogger):
        self._executor = executor
        self._validator = validator
        self._logger = logger
    
    async def get_dataset(self, name: DatasetName) -> Result[Dataset, DatasetException]:
        """Get dataset information with comprehensive details."""
        try:
            self._logger.info(f"Fetching dataset: {name}")
            
            # Validate dataset name
            validation_result = await self._validate_dataset_name(name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Execute ZFS list command for detailed information
            result = await self._executor.execute_zfs(
                "list", "-H", "-o", "name,used,available,creation,mounted,mountpoint,compression,compressratio,encryption,quota,reservation", 
                str(name)
            )
            
            if not result.success:
                if "dataset does not exist" in result.stderr.lower():
                    return Result.failure(DatasetNotFoundError(str(name)))
                return Result.failure(DatasetException(
                    f"Failed to get dataset info: {result.stderr}",
                    error_code="DATASET_INFO_FAILED"
                ))
            
            # Parse dataset information
            dataset_info = await self._parse_dataset_info(result.stdout, name)
            if dataset_info.is_failure:
                return Result.failure(dataset_info.error)
            
            # Get additional properties
            properties_result = await self._get_dataset_properties(name)
            if properties_result.is_failure:
                return Result.failure(properties_result.error)
            
            # Merge properties into dataset
            dataset = dataset_info.value
            dataset.properties.update(properties_result.value)
            
            self._logger.info(f"Successfully fetched dataset: {name}")
            return Result.success(dataset)
            
        except Exception as e:
            self._logger.error(f"Unexpected error fetching dataset {name}: {e}")
            return Result.failure(DatasetException(
                f"Unexpected error: {str(e)}", 
                error_code="DATASET_UNEXPECTED_ERROR"
            ))
    
    async def list_datasets(self, pool_name: Optional[str] = None) -> Result[List[Dataset], DatasetException]:
        """List all datasets in a pool or entire system."""
        try:
            self._logger.info(f"Listing datasets for pool: {pool_name or 'all'}")
            
            command_args = ["list", "-H", "-o", "name,used,available,creation,mounted,mountpoint"]
            
            if pool_name:
                # Validate pool name
                validated_pool = self._validator.validate_dataset_name(pool_name)
                if not validated_pool:
                    return Result.failure(DatasetException(
                        f"Invalid pool name: {pool_name}",
                        error_code="INVALID_POOL_NAME"
                    ))
                command_args.append(validated_pool)
            
            result = await self._executor.execute_zfs(*command_args)
            
            if not result.success:
                return Result.failure(DatasetException(
                    f"Failed to list datasets: {result.stderr}",
                    error_code="DATASET_LIST_FAILED"
                ))
            
            # Parse dataset list
            datasets_result = await self._parse_dataset_list(result.stdout)
            if datasets_result.is_failure:
                return Result.failure(datasets_result.error)
            
            self._logger.info(f"Successfully listed {len(datasets_result.value)} datasets")
            return Result.success(datasets_result.value)
            
        except Exception as e:
            self._logger.error(f"Unexpected error listing datasets: {e}")
            return Result.failure(DatasetException(
                f"Unexpected error: {str(e)}",
                error_code="DATASET_LIST_UNEXPECTED_ERROR"
            ))
    
    async def create_dataset(self, 
                           name: DatasetName, 
                           properties: Optional[Dict[str, str]] = None) -> Result[Dataset, DatasetException]:
        """Create a new dataset with optional properties."""
        try:
            self._logger.info(f"Creating dataset: {name}")
            
            # Validate dataset name
            validation_result = await self._validate_dataset_name(name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Check if dataset already exists
            exists_result = await self._dataset_exists(name)
            if exists_result.is_failure:
                return Result.failure(exists_result.error)
            if exists_result.value:
                return Result.failure(DatasetAlreadyExistsError(str(name)))
            
            # Build create command
            command_args = ["create"]
            
            # Add properties if provided
            if properties:
                validated_props = self._validator.validate_zfs_properties(properties)
                if not validated_props:
                    return Result.failure(DatasetException(
                        f"Invalid properties specified",
                        error_code="INVALID_PROPERTIES"
                    ))
                
                for key, value in validated_props.items():
                    command_args.extend(["-o", f"{key}={value}"])
            
            command_args.append(str(name))
            
            # Execute create command
            result = await self._executor.execute_zfs(*command_args)
            
            if not result.success:
                return Result.failure(DatasetException(
                    f"Failed to create dataset: {result.stderr}",
                    error_code="DATASET_CREATE_FAILED"
                ))
            
            # Fetch the created dataset
            created_dataset = await self.get_dataset(name)
            if created_dataset.is_failure:
                return Result.failure(DatasetException(
                    f"Dataset created but failed to fetch: {created_dataset.error}",
                    error_code="DATASET_CREATE_FETCH_FAILED"
                ))
            
            self._logger.info(f"Successfully created dataset: {name}")
            return Result.success(created_dataset.value)
            
        except Exception as e:
            self._logger.error(f"Unexpected error creating dataset {name}: {e}")
            return Result.failure(DatasetException(
                f"Unexpected error: {str(e)}",
                error_code="DATASET_CREATE_UNEXPECTED_ERROR"
            ))
    
    async def destroy_dataset(self, 
                            name: DatasetName, 
                            force: bool = False,
                            recursive: bool = False) -> Result[bool, DatasetException]:
        """Destroy a dataset with optional force and recursive options."""
        try:
            self._logger.info(f"Destroying dataset: {name} (force={force}, recursive={recursive})")
            
            # Validate dataset name
            validation_result = await self._validate_dataset_name(name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Check if dataset exists
            exists_result = await self._dataset_exists(name)
            if exists_result.is_failure:
                return Result.failure(exists_result.error)
            if not exists_result.value:
                return Result.failure(DatasetNotFoundError(str(name)))
            
            # Build destroy command
            command_args = ["destroy"]
            
            if force:
                command_args.append("-f")
            if recursive:
                command_args.append("-r")
            
            command_args.append(str(name))
            
            # Execute destroy command
            result = await self._executor.execute_zfs(*command_args)
            
            if not result.is_success:
                return Result.failure(DatasetException(
                    f"Failed to destroy dataset: {result.stderr}",
                    error_code="DATASET_DESTROY_FAILED"
                ))
            
            self._logger.info(f"Successfully destroyed dataset: {name}")
            return Result.success(True)
            
        except Exception as e:
            self._logger.error(f"Unexpected error destroying dataset {name}: {e}")
            return Result.failure(DatasetException(
                f"Unexpected error: {str(e)}",
                error_code="DATASET_DESTROY_UNEXPECTED_ERROR"
            ))
    
    async def set_property(self, 
                         name: DatasetName, 
                         property_name: str, 
                         value: str) -> Result[bool, DatasetException]:
        """Set a property on a dataset."""
        try:
            self._logger.info(f"Setting property {property_name}={value} on dataset: {name}")
            
            # Validate dataset name
            validation_result = await self._validate_dataset_name(name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Validate property
            validated_props = self._validator.validate_zfs_properties({property_name: value})
            if not validated_props:
                return Result.failure(DatasetException(
                    f"Invalid property: {property_name}={value}",
                    error_code="INVALID_PROPERTY"
                ))
            
            # Execute set command
            result = await self._executor.execute_zfs(
                "set", f"{property_name}={value}", str(name)
            )
            
            if not result.is_success:
                return Result.failure(DatasetException(
                    f"Failed to set property: {result.stderr}",
                    error_code="DATASET_PROPERTY_SET_FAILED"
                ))
            
            self._logger.info(f"Successfully set property {property_name}={value} on dataset: {name}")
            return Result.success(True)
            
        except Exception as e:
            self._logger.error(f"Unexpected error setting property on dataset {name}: {e}")
            return Result.failure(DatasetException(
                f"Unexpected error: {str(e)}",
                error_code="DATASET_PROPERTY_SET_UNEXPECTED_ERROR"
            ))
    
    async def get_usage(self, name: DatasetName) -> Result[Dict[str, Any], DatasetException]:
        """Get detailed usage information for a dataset."""
        try:
            self._logger.info(f"Getting usage for dataset: {name}")
            
            # Validate dataset name
            validation_result = await self._validate_dataset_name(name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Get usage information
            result = await self._executor.execute_zfs(
                "list", "-H", "-o", 
                "name,used,available,referenced,logicalused,logicalreferenced,quota,reservation,compressratio,dedup",
                str(name)
            )
            
            if not result.is_success:
                if "dataset does not exist" in result.stderr.lower():
                    return Result.failure(DatasetNotFoundError(str(name)))
                return Result.failure(DatasetException(
                    f"Failed to get usage: {result.stderr}",
                    error_code="DATASET_USAGE_FAILED"
                ))
            
            # Parse usage information
            usage_info = await self._parse_usage_info(result.stdout)
            if usage_info.is_failure:
                return Result.failure(usage_info.error)
            
            self._logger.info(f"Successfully retrieved usage for dataset: {name}")
            return Result.success(usage_info.value)
            
        except Exception as e:
            self._logger.error(f"Unexpected error getting usage for dataset {name}: {e}")
            return Result.failure(DatasetException(
                f"Unexpected error: {str(e)}",
                error_code="DATASET_USAGE_UNEXPECTED_ERROR"
            ))
    
    async def mount_dataset(self, name: DatasetName) -> Result[bool, DatasetException]:
        """Mount a dataset."""
        try:
            self._logger.info(f"Mounting dataset: {name}")
            
            # Validate dataset name
            validation_result = await self._validate_dataset_name(name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Execute mount command
            result = await self._executor.execute_zfs("mount", str(name))
            
            if not result.is_success:
                return Result.failure(DatasetException(
                    f"Failed to mount dataset: {result.stderr}",
                    error_code="DATASET_MOUNT_FAILED"
                ))
            
            self._logger.info(f"Successfully mounted dataset: {name}")
            return Result.success(True)
            
        except Exception as e:
            self._logger.error(f"Unexpected error mounting dataset {name}: {e}")
            return Result.failure(DatasetException(
                f"Unexpected error: {str(e)}",
                error_code="DATASET_MOUNT_UNEXPECTED_ERROR"
            ))
    
    async def unmount_dataset(self, name: DatasetName, force: bool = False) -> Result[bool, DatasetException]:
        """Unmount a dataset."""
        try:
            self._logger.info(f"Unmounting dataset: {name} (force={force})")
            
            # Validate dataset name
            validation_result = await self._validate_dataset_name(name)
            if validation_result.is_failure:
                return Result.failure(validation_result.error)
            
            # Build unmount command
            command_args = ["unmount"]
            if force:
                command_args.append("-f")
            command_args.append(str(name))
            
            # Execute unmount command
            result = await self._executor.execute_zfs(*command_args)
            
            if not result.is_success:
                return Result.failure(DatasetException(
                    f"Failed to unmount dataset: {result.stderr}",
                    error_code="DATASET_UNMOUNT_FAILED"
                ))
            
            self._logger.info(f"Successfully unmounted dataset: {name}")
            return Result.success(True)
            
        except Exception as e:
            self._logger.error(f"Unexpected error unmounting dataset {name}: {e}")
            return Result.failure(DatasetException(
                f"Unexpected error: {str(e)}",
                error_code="DATASET_UNMOUNT_UNEXPECTED_ERROR"
            ))
    
    # Private helper methods
    
    async def _validate_dataset_name(self, name: DatasetName) -> Result[bool, ValidationException]:
        """Validate dataset name using security validator."""
        try:
            validated = self._validator.validate_dataset_name(str(name))
            if not validated:
                return Result.failure(ValidationException(
                    f"Invalid dataset name: {name}"
                ))
            return Result.success(True)
        except Exception as e:
            return Result.failure(ValidationException(
                f"Dataset name validation failed: {str(e)}"
            ))
    
    async def _dataset_exists(self, name: DatasetName) -> Result[bool, DatasetException]:
        """Check if a dataset exists."""
        try:
            result = await self._executor.execute_zfs("list", "-H", "-o", "name", str(name))
            return Result.success(result.is_success)
        except Exception as e:
            return Result.failure(DatasetException(
                f"Failed to check dataset existence: {str(e)}",
                error_code="DATASET_EXISTS_CHECK_FAILED"
            ))
    
    async def _get_dataset_properties(self, name: DatasetName) -> Result[Dict[str, str], DatasetException]:
        """Get all properties for a dataset."""
        try:
            result = await self._executor.execute_zfs("get", "-H", "-o", "property,value", "all", str(name))
            
            if not result.is_success:
                return Result.failure(DatasetException(
                    f"Failed to get properties: {result.stderr}",
                    error_code="DATASET_PROPERTIES_FAILED"
                ))
            
            properties = {}
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        properties[parts[0]] = parts[1]
            
            return Result.success(properties)
            
        except Exception as e:
            return Result.failure(DatasetException(
                f"Failed to parse properties: {str(e)}",
                error_code="DATASET_PROPERTIES_PARSE_FAILED"
            ))
    
    async def _parse_dataset_info(self, output: str, name: DatasetName) -> Result[Dataset, DatasetException]:
        """Parse dataset information from ZFS output."""
        try:
            lines = output.strip().split('\n')
            if not lines or not lines[0].strip():
                return Result.failure(DatasetException(
                    "Empty dataset info output",
                    error_code="DATASET_INFO_EMPTY"
                ))
            
            parts = lines[0].split('\t')
            if len(parts) < 11:
                return Result.failure(DatasetException(
                    f"Invalid dataset info format: {lines[0]}",
                    error_code="DATASET_INFO_FORMAT_INVALID"
                ))
            
            # Parse values
            used = SizeValue.from_zfs_string(parts[1]) if parts[1] != '-' else None
            available = SizeValue.from_zfs_string(parts[2]) if parts[2] != '-' else None
            
            # Parse creation time
            creation_time = None
            if parts[3] != '-':
                try:
                    creation_time = datetime.fromtimestamp(int(parts[3]))
                except (ValueError, TypeError):
                    pass
            
            # Build properties dictionary
            properties = {
                'mounted': parts[4],
                'mountpoint': parts[5],
                'compression': parts[6],
                'compressratio': parts[7],
                'encryption': parts[8],
                'quota': parts[9],
                'reservation': parts[10]
            }
            
            dataset = Dataset(
                name=name,
                properties=properties,
                used=used,
                available=available,
                creation_time=creation_time
            )
            
            return Result.success(dataset)
            
        except Exception as e:
            return Result.failure(DatasetException(
                f"Failed to parse dataset info: {str(e)}",
                error_code="DATASET_INFO_PARSE_FAILED"
            ))
    
    async def _parse_dataset_list(self, output: str) -> Result[List[Dataset], DatasetException]:
        """Parse list of datasets from ZFS output."""
        try:
            datasets = []
            lines = output.strip().split('\n')
            
            for line in lines:
                if not line.strip():
                    continue
                
                parts = line.split('\t')
                if len(parts) < 6:
                    continue
                
                try:
                    name = DatasetName.from_string(parts[0])
                    used = SizeValue.from_zfs_string(parts[1]) if parts[1] != '-' else None
                    available = SizeValue.from_zfs_string(parts[2]) if parts[2] != '-' else None
                    
                    # Parse creation time
                    creation_time = None
                    if parts[3] != '-':
                        try:
                            creation_time = datetime.fromtimestamp(int(parts[3]))
                        except (ValueError, TypeError):
                            pass
                    
                    properties = {
                        'mounted': parts[4],
                        'mountpoint': parts[5]
                    }
                    
                    dataset = Dataset(
                        name=name,
                        properties=properties,
                        used=used,
                        available=available,
                        creation_time=creation_time
                    )
                    
                    datasets.append(dataset)
                    
                except Exception as e:
                    self._logger.warning(f"Failed to parse dataset line: {line}, error: {e}")
                    continue
            
            return Result.success(datasets)
            
        except Exception as e:
            return Result.failure(DatasetException(
                f"Failed to parse dataset list: {str(e)}",
                error_code="DATASET_LIST_PARSE_FAILED"
            ))
    
    async def _parse_usage_info(self, output: str) -> Result[Dict[str, Any], DatasetException]:
        """Parse usage information from ZFS output."""
        try:
            lines = output.strip().split('\n')
            if not lines or not lines[0].strip():
                return Result.failure(DatasetException(
                    "Empty usage info output",
                    error_code="DATASET_USAGE_EMPTY"
                ))
            
            parts = lines[0].split('\t')
            if len(parts) < 10:
                return Result.failure(DatasetException(
                    f"Invalid usage info format: {lines[0]}",
                    error_code="DATASET_USAGE_FORMAT_INVALID"
                ))
            
            usage_info = {
                'name': parts[0],
                'used': SizeValue.from_zfs_string(parts[1]) if parts[1] != '-' else None,
                'available': SizeValue.from_zfs_string(parts[2]) if parts[2] != '-' else None,
                'referenced': SizeValue.from_zfs_string(parts[3]) if parts[3] != '-' else None,
                'logicalused': SizeValue.from_zfs_string(parts[4]) if parts[4] != '-' else None,
                'logicalreferenced': SizeValue.from_zfs_string(parts[5]) if parts[5] != '-' else None,
                'quota': SizeValue.from_zfs_string(parts[6]) if parts[6] not in ['-', 'none'] else None,
                'reservation': SizeValue.from_zfs_string(parts[7]) if parts[7] not in ['-', 'none'] else None,
                'compressratio': parts[8] if parts[8] != '-' else None,
                'dedup': parts[9] if parts[9] != '-' else None
            }
            
            return Result.success(usage_info)
            
        except Exception as e:
            return Result.failure(DatasetException(
                f"Failed to parse usage info: {str(e)}",
                error_code="DATASET_USAGE_PARSE_FAILED"
            )) 