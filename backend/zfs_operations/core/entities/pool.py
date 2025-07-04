"""
Pool domain entity with health monitoring and management capabilities.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum
from ..value_objects.size_value import SizeValue


class PoolState(Enum):
    """Pool state enumeration."""
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"
    FAULTED = "FAULTED"
    REMOVED = "REMOVED"
    UNAVAIL = "UNAVAIL"
    SUSPENDED = "SUSPENDED"


class PoolHealth(Enum):
    """Pool health status enumeration."""
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    FAILED = "FAILED"


@dataclass
class VDev:
    """Virtual device within a pool."""
    name: str
    type: str
    state: str
    read_errors: int = 0
    write_errors: int = 0
    checksum_errors: int = 0
    children: List['VDev'] = field(default_factory=list)
    
    def has_errors(self) -> bool:
        """Check if vdev has any errors."""
        return (self.read_errors > 0 or 
                self.write_errors > 0 or 
                self.checksum_errors > 0)
    
    def total_errors(self) -> int:
        """Get total error count."""
        return self.read_errors + self.write_errors + self.checksum_errors
    
    def is_healthy(self) -> bool:
        """Check if vdev is healthy."""
        return self.state == "ONLINE" and not self.has_errors()


@dataclass
class Pool:
    """Domain entity representing a ZFS pool with health monitoring."""
    
    name: str
    state: PoolState
    size: SizeValue
    allocated: SizeValue
    free: SizeValue
    properties: Dict[str, str] = field(default_factory=dict)
    vdevs: List[VDev] = field(default_factory=list)
    scan_stats: Optional[Dict[str, Any]] = None
    errors: Dict[str, int] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate pool after initialization."""
        if not self.name:
            raise ValueError("Pool name cannot be empty")
        
        if not isinstance(self.size, SizeValue):
            raise ValueError("Size must be a SizeValue instance")
        
        if not isinstance(self.allocated, SizeValue):
            raise ValueError("Allocated must be a SizeValue instance")
        
        if not isinstance(self.free, SizeValue):
            raise ValueError("Free must be a SizeValue instance")
        
        # Validate that allocated + free <= size (allowing for metadata overhead)
        if self.allocated.bytes + self.free.bytes > self.size.bytes * 1.1:
            raise ValueError("Allocated + Free exceeds pool size beyond reasonable metadata overhead")
    
    @property
    def capacity_percent(self) -> int:
        """Get capacity utilization as percentage."""
        if self.size.bytes == 0:
            return 0
        return int((self.allocated.bytes / self.size.bytes) * 100)
    
    @property
    def free_percent(self) -> int:
        """Get free space as percentage."""
        return 100 - self.capacity_percent
    
    def get_health_status(self) -> PoolHealth:
        """Determine overall pool health status."""
        if self.state == PoolState.FAULTED:
            return PoolHealth.FAILED
        elif self.state in [PoolState.OFFLINE, PoolState.UNAVAIL, PoolState.SUSPENDED]:
            return PoolHealth.CRITICAL
        elif self.state == PoolState.DEGRADED:
            return PoolHealth.WARNING
        elif self.capacity_percent >= 95:
            return PoolHealth.CRITICAL
        elif self.capacity_percent >= 85:
            return PoolHealth.WARNING
        elif self.has_errors():
            return PoolHealth.WARNING
        else:
            return PoolHealth.HEALTHY
    
    def is_healthy(self) -> bool:
        """Check if pool is in healthy state."""
        return (self.state == PoolState.ONLINE and 
                self.capacity_percent < 85 and 
                not self.has_errors())
    
    def needs_attention(self) -> bool:
        """Check if pool needs immediate attention."""
        return (self.capacity_percent > 80 or 
                self.state != PoolState.ONLINE or 
                self.has_errors() or
                self.has_failed_vdevs())
    
    def is_critical(self) -> bool:
        """Check if pool is in critical state."""
        return (self.capacity_percent > 95 or 
                self.state in [PoolState.FAULTED, PoolState.OFFLINE, PoolState.UNAVAIL] or
                self.has_failed_vdevs())
    
    def has_errors(self) -> bool:
        """Check if pool has any errors."""
        return any(count > 0 for count in self.errors.values())
    
    def total_errors(self) -> int:
        """Get total error count across all categories."""
        return sum(self.errors.values())
    
    def has_failed_vdevs(self) -> bool:
        """Check if pool has any failed vdevs."""
        return any(not vdev.is_healthy() for vdev in self.vdevs)
    
    def get_failed_vdevs(self) -> List[VDev]:
        """Get list of failed vdevs."""
        return [vdev for vdev in self.vdevs if not vdev.is_healthy()]
    
    def get_vdev_count(self) -> int:
        """Get total number of vdevs."""
        return len(self.vdevs)
    
    def get_property(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Get a specific property value."""
        return self.properties.get(name, default)
    
    def is_auto_replace_enabled(self) -> bool:
        """Check if auto-replace is enabled."""
        return self.get_property('autoreplace', 'off') == 'on'
    
    def get_version(self) -> Optional[str]:
        """Get pool version."""
        return self.get_property('version')
    
    def is_bootable(self) -> bool:
        """Check if pool is bootable."""
        return self.get_property('bootfs') is not None
    
    def get_fragmentation_percent(self) -> int:
        """Get fragmentation percentage."""
        frag_str = self.get_property('fragmentation', '0%')
        try:
            if frag_str and frag_str.endswith('%'):
                return int(frag_str[:-1])
            return 0
        except (ValueError, AttributeError):
            return 0
    
    def is_highly_fragmented(self, threshold: int = 50) -> bool:
        """Check if pool is highly fragmented."""
        return self.get_fragmentation_percent() > threshold
    
    def get_deduplication_ratio(self) -> float:
        """Get deduplication ratio."""
        ratio_str = self.get_property('dedupratio', '1.00x')
        try:
            if ratio_str and ratio_str.endswith('x'):
                return float(ratio_str[:-1])
            return 1.0
        except (ValueError, AttributeError):
            return 1.0
    
    def is_deduplicated(self) -> bool:
        """Check if pool benefits from deduplication."""
        return self.get_deduplication_ratio() > 1.0
    
    def get_compression_ratio(self) -> float:
        """Get compression ratio."""
        ratio_str = self.get_property('compressratio', '1.00x')
        try:
            if ratio_str and ratio_str.endswith('x'):
                return float(ratio_str[:-1])
            return 1.0
        except (ValueError, AttributeError):
            return 1.0
    
    def is_compressed(self) -> bool:
        """Check if pool uses compression."""
        return self.get_compression_ratio() > 1.0
    
    def get_space_efficiency(self) -> float:
        """Calculate space efficiency from compression and deduplication."""
        return self.get_compression_ratio() * self.get_deduplication_ratio()
    
    def is_space_efficient(self, threshold: float = 1.2) -> bool:
        """Check if pool is space efficient."""
        return self.get_space_efficiency() > threshold
    
    def get_scrub_status(self) -> Optional[Dict[str, Any]]:
        """Get scrub status information."""
        if self.scan_stats:
            return self.scan_stats.get('scrub')
        return None
    
    def is_scrub_in_progress(self) -> bool:
        """Check if scrub is currently in progress."""
        scrub_status = self.get_scrub_status()
        return scrub_status is not None and scrub_status.get('state') == 'scanning'
    
    def get_last_scrub_time(self) -> Optional[datetime]:
        """Get the timestamp of the last scrub."""
        scrub_status = self.get_scrub_status()
        if scrub_status and 'end_time' in scrub_status:
            return scrub_status['end_time']
        return None
    
    def needs_scrub(self, days: int = 30) -> bool:
        """Check if pool needs scrubbing."""
        last_scrub = self.get_last_scrub_time()
        if not last_scrub:
            return True
        
        days_since_scrub = (datetime.now(timezone.utc) - last_scrub).days
        return days_since_scrub > days
    
    def get_resilver_status(self) -> Optional[Dict[str, Any]]:
        """Get resilver status information."""
        if self.scan_stats:
            return self.scan_stats.get('resilver')
        return None
    
    def is_resilver_in_progress(self) -> bool:
        """Check if resilver is currently in progress."""
        resilver_status = self.get_resilver_status()
        return resilver_status is not None and resilver_status.get('state') == 'scanning'
    
    def get_io_stats(self) -> Dict[str, int]:
        """Get I/O statistics."""
        return {
            'read_ops': int(self.get_property('read_ops', '0') or '0'),
            'write_ops': int(self.get_property('write_ops', '0') or '0'),
            'read_bytes': int(self.get_property('read_bytes', '0') or '0'),
            'write_bytes': int(self.get_property('write_bytes', '0') or '0'),
        }
    
    def get_recommendations(self) -> List[str]:
        """Get health recommendations for the pool."""
        recommendations = []
        
        if self.capacity_percent > 95:
            recommendations.append("URGENT: Pool is critically full (>95%). Add storage immediately.")
        elif self.capacity_percent > 85:
            recommendations.append("WARNING: Pool is getting full (>85%). Consider adding storage.")
        elif self.capacity_percent > 80:
            recommendations.append("Pool is approaching capacity (>80%). Monitor closely.")
        
        if self.is_highly_fragmented():
            recommendations.append(f"Pool is highly fragmented ({self.get_fragmentation_percent()}%). Consider defragmentation.")
        
        if self.has_errors():
            recommendations.append("Pool has errors. Check logs and consider replacing faulty hardware.")
        
        if self.has_failed_vdevs():
            recommendations.append("Pool has failed vdevs. Replace faulty devices immediately.")
        
        if self.needs_scrub():
            recommendations.append("Pool needs scrubbing. Run 'zpool scrub' to verify data integrity.")
        
        if self.state == PoolState.DEGRADED:
            recommendations.append("Pool is in degraded state. Check vdev status and replace failed devices.")
        
        if not self.is_auto_replace_enabled():
            recommendations.append("Consider enabling auto-replace for better resilience.")
        
        return recommendations
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert pool to dictionary representation."""
        return {
            'name': self.name,
            'state': self.state.value,
            'health': self.get_health_status().value,
            'size': self.size.bytes,
            'size_human': self.size.to_human_readable(),
            'allocated': self.allocated.bytes,
            'allocated_human': self.allocated.to_human_readable(),
            'free': self.free.bytes,
            'free_human': self.free.to_human_readable(),
            'capacity_percent': self.capacity_percent,
            'free_percent': self.free_percent,
            'fragmentation_percent': self.get_fragmentation_percent(),
            'compression_ratio': self.get_compression_ratio(),
            'deduplication_ratio': self.get_deduplication_ratio(),
            'space_efficiency': self.get_space_efficiency(),
            'properties': self.properties,
            'vdev_count': self.get_vdev_count(),
            'errors': self.errors,
            'total_errors': self.total_errors(),
            'has_errors': self.has_errors(),
            'has_failed_vdevs': self.has_failed_vdevs(),
            'is_healthy': self.is_healthy(),
            'needs_attention': self.needs_attention(),
            'is_critical': self.is_critical(),
            'is_scrub_in_progress': self.is_scrub_in_progress(),
            'is_resilver_in_progress': self.is_resilver_in_progress(),
            'needs_scrub': self.needs_scrub(),
            'recommendations': self.get_recommendations(),
        }
    
    def __str__(self) -> str:
        """String representation of pool."""
        return f"Pool({self.name})"
    
    def __repr__(self) -> str:
        """Detailed representation of pool."""
        return (f"Pool(name='{self.name}', state={self.state.value}, "
                f"size={self.size.to_human_readable()}, "
                f"capacity={self.capacity_percent}%, "
                f"health={self.get_health_status().value})")


@dataclass
class PoolConfiguration:
    """Pool configuration and topology information."""
    
    name: str
    pool_type: str  # mirror, raidz, raidz2, raidz3, etc.
    vdev_configs: List[Dict[str, Any]] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)
    
    def get_redundancy_level(self) -> int:
        """Get redundancy level (number of drives that can fail)."""
        if self.pool_type == 'mirror':
            return 1
        elif self.pool_type == 'raidz':
            return 1
        elif self.pool_type == 'raidz2':
            return 2
        elif self.pool_type == 'raidz3':
            return 3
        else:
            return 0  # No redundancy (single disk or stripe)
    
    def is_redundant(self) -> bool:
        """Check if pool has redundancy."""
        return self.get_redundancy_level() > 0
    
    def get_optimal_vdev_size(self) -> int:
        """Get optimal vdev size based on type."""
        if self.pool_type == 'mirror':
            return 2
        elif self.pool_type == 'raidz':
            return 3  # Minimum for raidz
        elif self.pool_type == 'raidz2':
            return 4  # Minimum for raidz2
        elif self.pool_type == 'raidz3':
            return 5  # Minimum for raidz3
        else:
            return 1 