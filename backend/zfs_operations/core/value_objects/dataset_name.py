from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class DatasetName:
    """Type-safe dataset name value object"""
    pool: str
    path: List[str]
    
    def __post_init__(self):
        if not self.pool:
            raise ValueError("Pool name cannot be empty")
        if not all(part.strip() for part in self.path):
            raise ValueError("Dataset path components cannot be empty")
        
        # Validate pool name format
        if not self.pool.replace('_', '').replace('-', '').isalnum():
            raise ValueError("Pool name must contain only alphanumeric characters, hyphens, and underscores")
        
        # Validate path components
        for part in self.path:
            # Allow alphanumeric characters, hyphens, underscores, dots, and spaces
            # Remove these allowed characters and check if anything suspicious remains
            sanitized = part.replace('_', '').replace('-', '').replace('.', '').replace(' ', '')
            if not sanitized.isalnum():
                raise ValueError("Dataset path components must contain only alphanumeric characters, hyphens, underscores, dots, and spaces")
    
    @classmethod
    def from_string(cls, dataset_str: str) -> 'DatasetName':
        """Create DatasetName from string representation"""
        if not dataset_str:
            raise ValueError("Dataset string cannot be empty")
        
        parts = dataset_str.split('/')
        if len(parts) < 1:
            raise ValueError("Invalid dataset string format")
        
        pool = parts[0]
        path = parts[1:] if len(parts) > 1 else []
        
        return cls(pool=pool, path=path)
    
    def __str__(self) -> str:
        """String representation of dataset name"""
        if self.path:
            return f"{self.pool}/{'/'.join(self.path)}"
        return self.pool
    
    @property
    def is_pool_root(self) -> bool:
        """Check if this is a pool root dataset"""
        return len(self.path) == 0
    
    @property
    def parent(self) -> 'DatasetName':
        """Get parent dataset name"""
        if self.is_pool_root:
            raise ValueError("Pool root has no parent")
        
        if len(self.path) == 1:
            return DatasetName(pool=self.pool, path=[])
        
        return DatasetName(pool=self.pool, path=self.path[:-1])
    
    def child(self, name: str) -> 'DatasetName':
        """Create child dataset name"""
        if not name.strip():
            raise ValueError("Child name cannot be empty")
        
        return DatasetName(pool=self.pool, path=self.path + [name])
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'pool': self.pool,
            'path': self.path,
            'full_name': str(self)
        } 