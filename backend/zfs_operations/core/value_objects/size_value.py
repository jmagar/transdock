from dataclasses import dataclass
import re
from typing import Union


@dataclass(frozen=True)
class SizeValue:
    """Size value object with unit handling"""
    bytes: int
    
    def __post_init__(self):
        if self.bytes < 0:
            raise ValueError("Size cannot be negative")
    
    @classmethod
    def from_zfs_string(cls, size_str: str) -> 'SizeValue':
        """Parse ZFS size string (e.g., '1.5G', '500M') to bytes"""
        size_str = size_str.strip().upper()
        
        # Handle special cases
        if size_str in ["-", "0", "0B"]:
            return cls(0)
        
        # Define units in bytes
        units = {
            "B": 1,
            "K": 1024,
            "M": 1024**2,
            "G": 1024**3,
            "T": 1024**4,
            "P": 1024**5,
            "E": 1024**6,
            "Z": 1024**7,
            "Y": 1024**8
        }
        
        # Extract numeric part and unit
        match = re.match(r'^(\d+(?:\.\d+)?)\s*([BKMGTPEZY]?)$', size_str)
        if not match:
            raise ValueError(f"Cannot parse size: {size_str}")
        
        numeric_value = float(match.group(1))
        unit = match.group(2) or "B"
        
        if unit not in units:
            raise ValueError(f"Unknown unit: {unit}")
        
        return cls(int(numeric_value * units[unit]))
    
    @classmethod
    def from_bytes(cls, byte_count: int) -> 'SizeValue':
        """Create SizeValue from byte count"""
        return cls(byte_count)
    
    @classmethod
    def from_human_readable(cls, size_str: str) -> 'SizeValue':
        """Create SizeValue from human readable string"""
        return cls.from_zfs_string(size_str)
    
    def to_human_readable(self, precision: int = 1) -> str:
        """Convert bytes to human readable format"""
        if self.bytes == 0:
            return "0B"
        
        units = ["B", "K", "M", "G", "T", "P", "E", "Z", "Y"]
        size = float(self.bytes)
        unit_index = 0
        
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        
        if size == int(size):
            return f"{int(size)}{units[unit_index]}"
        
        return f"{size:.{precision}f}{units[unit_index]}"
    
    def to_zfs_format(self) -> str:
        """Convert to ZFS format string"""
        return self.to_human_readable()
    
    def __str__(self) -> str:
        """String representation in human readable format"""
        return self.to_human_readable()
    
    def __add__(self, other: Union['SizeValue', int]) -> 'SizeValue':
        """Add two sizes"""
        if isinstance(other, int):
            return SizeValue(self.bytes + other)
        return SizeValue(self.bytes + other.bytes)
    
    def __sub__(self, other: Union['SizeValue', int]) -> 'SizeValue':
        """Subtract two sizes"""
        if isinstance(other, int):
            result = self.bytes - other
        else:
            result = self.bytes - other.bytes
        
        if result < 0:
            raise ValueError("Size cannot be negative")
        return SizeValue(result)
    
    def __mul__(self, multiplier: float) -> 'SizeValue':
        """Multiply size by a factor"""
        return SizeValue(int(self.bytes * multiplier))
    
    def __truediv__(self, divisor: float) -> 'SizeValue':
        """Divide size by a factor"""
        return SizeValue(int(self.bytes / divisor))
    
    def __lt__(self, other: Union['SizeValue', int]) -> bool:
        """Less than comparison"""
        if isinstance(other, int):
            return self.bytes < other
        return self.bytes < other.bytes
    
    def __le__(self, other: Union['SizeValue', int]) -> bool:
        """Less than or equal comparison"""
        if isinstance(other, int):
            return self.bytes <= other
        return self.bytes <= other.bytes
    
    def __gt__(self, other: Union['SizeValue', int]) -> bool:
        """Greater than comparison"""
        if isinstance(other, int):
            return self.bytes > other
        return self.bytes > other.bytes
    
    def __ge__(self, other: Union['SizeValue', int]) -> bool:
        """Greater than or equal comparison"""
        if isinstance(other, int):
            return self.bytes >= other
        return self.bytes >= other.bytes
    
    def __eq__(self, other: Union['SizeValue', int]) -> bool:
        """Equality comparison"""
        if isinstance(other, int):
            return self.bytes == other
        return self.bytes == other.bytes
    
    @property
    def kilobytes(self) -> float:
        """Size in kilobytes"""
        return self.bytes / 1024
    
    @property
    def megabytes(self) -> float:
        """Size in megabytes"""
        return self.bytes / (1024**2)
    
    @property
    def gigabytes(self) -> float:
        """Size in gigabytes"""
        return self.bytes / (1024**3)
    
    @property
    def terabytes(self) -> float:
        """Size in terabytes"""
        return self.bytes / (1024**4)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'bytes': self.bytes,
            'human_readable': self.to_human_readable(),
            'kilobytes': self.kilobytes,
            'megabytes': self.megabytes,
            'gigabytes': self.gigabytes,
            'terabytes': self.terabytes
        } 