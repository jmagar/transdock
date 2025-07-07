"""DatasetName value object"""

from dataclasses import dataclass
from typing import Optional
import re
from ..exceptions.validation_exceptions import InvalidDatasetNameError


@dataclass(frozen=True)
class DatasetName:
    """Immutable value object for ZFS dataset names"""
    
    value: str
    
    def __post_init__(self):
        if not self.value:
            raise InvalidDatasetNameError("Dataset name cannot be empty")
        
        if len(self.value) > 255:
            raise InvalidDatasetNameError("Dataset name cannot exceed 255 characters")
        
        # ZFS dataset name validation
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_\-./]*$', self.value):
            raise InvalidDatasetNameError(
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
    
    def depth(self) -> int:
        """Get the depth of the dataset (number of path components)"""
        return len(self.value.split('/'))
    
    def is_pool_root(self) -> bool:
        """Check if this is a pool root dataset"""
        return '/' not in self.value
    
    def pool_name(self) -> str:
        """Get the pool name this dataset belongs to"""
        return self.value.split('/')[0]
    
    def __str__(self) -> str:
        return self.value
    
    def __repr__(self) -> str:
        return f"DatasetName('{self.value}')"