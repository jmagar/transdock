"""StorageSize value object"""

from dataclasses import dataclass
from typing import Union
import re
from ..exceptions.validation_exceptions import ValidationError


@dataclass(frozen=True)
class StorageSize:
    """Immutable value object for storage sizes in bytes"""
    
    bytes: int
    
    def __post_init__(self):
        if self.bytes < 0:
            raise ValidationError("Storage size cannot be negative")
    
    @classmethod
    def from_bytes(cls, bytes_value: int) -> 'StorageSize':
        """Create from bytes value"""
        return cls(bytes_value)
    
    @classmethod
    def from_kb(cls, kb: Union[int, float]) -> 'StorageSize':
        """Create from kilobytes"""
        return cls(int(kb * 1024))
    
    @classmethod
    def from_mb(cls, mb: Union[int, float]) -> 'StorageSize':
        """Create from megabytes"""
        return cls(int(mb * 1024 * 1024))
    
    @classmethod
    def from_gb(cls, gb: Union[int, float]) -> 'StorageSize':
        """Create from gigabytes"""
        return cls(int(gb * 1024 * 1024 * 1024))
    
    @classmethod
    def from_tb(cls, tb: Union[int, float]) -> 'StorageSize':
        """Create from terabytes"""
        return cls(int(tb * 1024 * 1024 * 1024 * 1024))
    
    @classmethod
    def from_zfs_string(cls, zfs_str: str) -> 'StorageSize':
        """Parse ZFS size string (e.g., '1.5G', '500M', '2.3T')"""
        if not zfs_str or zfs_str in ['-', 'none']:
            return cls(0)
        
        # Remove whitespace and convert to uppercase
        zfs_str = zfs_str.strip().upper()
        
        # Match number with optional unit
        match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMGT]?B?)$', zfs_str)
        if not match:
            raise ValidationError(f"Invalid ZFS size format: {zfs_str}")
        
        value_str, unit = match.groups()
        value = float(value_str)
        
        # Convert based on unit
        multipliers = {
            '': 1,
            'B': 1,
            'K': 1024,
            'KB': 1024,
            'M': 1024 ** 2,
            'MB': 1024 ** 2,
            'G': 1024 ** 3,
            'GB': 1024 ** 3,
            'T': 1024 ** 4,
            'TB': 1024 ** 4,
        }
        
        multiplier = multipliers.get(unit, 1)
        return cls(int(value * multiplier))
    
    @classmethod
    def from_human_string(cls, human_str: str) -> 'StorageSize':
        """Parse human-readable string (e.g., '1.5 GB', '500 MB')"""
        if not human_str:
            return cls(0)
        
        # Remove extra whitespace and convert to uppercase
        human_str = ' '.join(human_str.strip().split()).upper()
        
        # Match number with unit
        match = re.match(r'^(\d+(?:\.\d+)?)\s*(BYTES?|B|KB|MB|GB|TB)$', human_str)
        if not match:
            raise ValidationError(f"Invalid size format: {human_str}")
        
        value_str, unit = match.groups()
        value = float(value_str)
        
        multipliers = {
            'BYTE': 1,
            'BYTES': 1,
            'B': 1,
            'KB': 1024,
            'MB': 1024 ** 2,
            'GB': 1024 ** 3,
            'TB': 1024 ** 4,
        }
        
        multiplier = multipliers.get(unit, 1)
        return cls(int(value * multiplier))
    
    def to_kb(self) -> float:
        """Convert to kilobytes"""
        return self.bytes / 1024
    
    def to_mb(self) -> float:
        """Convert to megabytes"""
        return self.bytes / (1024 ** 2)
    
    def to_gb(self) -> float:
        """Convert to gigabytes"""
        return self.bytes / (1024 ** 3)
    
    def to_tb(self) -> float:
        """Convert to terabytes"""
        return self.bytes / (1024 ** 4)
    
    def to_human_string(self, precision: int = 2) -> str:
        """Convert to human-readable string"""
        if self.bytes == 0:
            return "0 B"
        
        units = [
            (1024 ** 4, "TB"),
            (1024 ** 3, "GB"),
            (1024 ** 2, "MB"),
            (1024, "KB"),
            (1, "B")
        ]
        
        for size, unit in units:
            if self.bytes >= size:
                value = self.bytes / size
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.{precision}f} {unit}"
        
        return f"{self.bytes} B"
    
    def __add__(self, other: 'StorageSize') -> 'StorageSize':
        """Add two storage sizes"""
        return StorageSize(self.bytes + other.bytes)
    
    def __sub__(self, other: 'StorageSize') -> 'StorageSize':
        """Subtract two storage sizes"""
        result = self.bytes - other.bytes
        if result < 0:
            raise ValidationError("Storage size subtraction cannot result in negative value")
        return StorageSize(result)
    
    def __mul__(self, factor: Union[int, float]) -> 'StorageSize':
        """Multiply storage size by a factor"""
        return StorageSize(int(self.bytes * factor))
    
    def __truediv__(self, divisor: Union[int, float, 'StorageSize']) -> Union['StorageSize', float]:
        """Divide storage size"""
        if isinstance(divisor, StorageSize):
            # Return ratio when dividing by another StorageSize
            return self.bytes / divisor.bytes if divisor.bytes > 0 else 0
        return StorageSize(int(self.bytes / divisor))
    
    def __lt__(self, other: 'StorageSize') -> bool:
        return self.bytes < other.bytes
    
    def __le__(self, other: 'StorageSize') -> bool:
        return self.bytes <= other.bytes
    
    def __gt__(self, other: 'StorageSize') -> bool:
        return self.bytes > other.bytes
    
    def __ge__(self, other: 'StorageSize') -> bool:
        return self.bytes >= other.bytes
    
    def __str__(self) -> str:
        return self.to_human_string()
    
    def __repr__(self) -> str:
        return f"StorageSize({self.bytes} bytes)"