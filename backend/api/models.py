"""
Pydantic models for API request/response validation.
"""
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum


class APIResponse(BaseModel):
    """Base API response model."""
    success: bool
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class DatasetResponse(APIResponse):
    """Dataset operation response."""
    dataset: Optional[Dict[str, Any]] = None


class SnapshotResponse(APIResponse):
    """Snapshot operation response."""
    snapshot: Optional[Dict[str, Any]] = None


class PoolResponse(APIResponse):
    """Pool operation response."""
    pool: Optional[Dict[str, Any]] = None


# Dataset API Models
class DatasetCreateRequest(BaseModel):
    """Request model for creating a dataset."""
    name: str = Field(..., description="Dataset name")
    properties: Optional[Dict[str, str]] = Field(default_factory=dict, description="Dataset properties")
    
    @validator('name')
    def validate_name(cls, v):
        if not v or len(v) > 255:
            raise ValueError('Dataset name must be between 1 and 255 characters')
        return v


class DatasetPropertyUpdateRequest(BaseModel):
    """Request model for updating dataset properties."""
    property_name: str = Field(..., description="Property name")
    value: str = Field(..., description="Property value")


class DatasetListResponse(BaseModel):
    """Response model for listing datasets."""
    success: bool
    datasets: List[Dict[str, Any]]
    count: int


# Snapshot API Models
class SnapshotCreateRequest(BaseModel):
    """Request model for creating a snapshot."""
    dataset_name: str = Field(..., description="Dataset name")
    snapshot_name: str = Field(..., description="Snapshot name")
    recursive: bool = Field(default=False, description="Recursive snapshot")
    
    @validator('dataset_name', 'snapshot_name')
    def validate_names(cls, v):
        if not v or len(v) > 255:
            raise ValueError('Name must be between 1 and 255 characters')
        return v


class SnapshotSendRequest(BaseModel):
    """Request model for sending a snapshot."""
    snapshot_name: str = Field(..., description="Snapshot name")
    target_host: str = Field(..., description="Target host")
    target_dataset: str = Field(..., description="Target dataset")
    incremental: bool = Field(default=False, description="Incremental send")
    base_snapshot: Optional[str] = Field(None, description="Base snapshot for incremental")


class SnapshotListResponse(BaseModel):
    """Response model for listing snapshots."""
    success: bool
    snapshots: List[Dict[str, Any]]
    count: int


# Pool API Models
class PoolCreateRequest(BaseModel):
    """Request model for creating a pool."""
    name: str = Field(..., description="Pool name")
    devices: List[str] = Field(..., description="Device list")
    properties: Optional[Dict[str, str]] = Field(default_factory=dict, description="Pool properties")


class PoolScrubRequest(BaseModel):
    """Request model for pool scrub operations."""
    action: str = Field(..., description="Scrub action (start/stop/pause)")
    
    @validator('action')
    def validate_action(cls, v):
        if v not in ['start', 'stop', 'pause']:
            raise ValueError('Action must be one of: start, stop, pause')
        return v


class PoolListResponse(BaseModel):
    """Response model for listing pools."""
    success: bool
    pools: List[Dict[str, Any]]
    count: int


# Performance Monitoring Models
class PerformanceStatsResponse(BaseModel):
    """Response model for performance statistics."""
    success: bool
    stats: Dict[str, Any]
    timestamp: datetime


class IOStatsRequest(BaseModel):
    """Request model for I/O statistics."""
    pools: Optional[List[str]] = Field(None, description="Pool names")
    interval: int = Field(default=1, description="Interval in seconds")
    count: int = Field(default=5, description="Number of samples")
    
    @validator('interval', 'count')
    def validate_positive(cls, v):
        if v <= 0:
            raise ValueError('Value must be positive')
        return v


# Error Models
class APIError(BaseModel):
    """API error response model."""
    success: bool = False
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ValidationError(APIError):
    """Validation error response model."""
    field_errors: Optional[Dict[str, List[str]]] = None


# Health Check Models
class HealthCheckResponse(BaseModel):
    """Health check response model."""
    status: str
    service: str
    timestamp: datetime
    details: Optional[Dict[str, Any]] = None


# System Info Models
class SystemInfoResponse(BaseModel):
    """System information response model."""
    success: bool
    system_info: Dict[str, Any]
    zfs_version: Optional[str] = None
    pools: Optional[List[Dict[str, Any]]] = None 