"""ZFS domain exceptions"""

from typing import Optional
from .validation_exceptions import ValidationError


class ZFSOperationError(Exception):
    """Raised when a ZFS operation fails"""
    
    def __init__(self, message: str, dataset: Optional[str] = None, command: Optional[str] = None):
        self.dataset = dataset
        self.command = command
        super().__init__(message)


class ZFSNotFoundError(ZFSOperationError):
    """Raised when a ZFS dataset or snapshot is not found"""
    pass


class ZFSValidationError(ValidationError):
    """Raised when ZFS-specific validation fails"""
    pass


class ZFSDatasetExistsError(ZFSOperationError):
    """Raised when trying to create a dataset that already exists"""
    pass


class ZFSInsufficientSpaceError(ZFSOperationError):
    """Raised when there's insufficient space for ZFS operations"""
    pass


class ZFSSnapshotNotFoundError(ZFSNotFoundError):
    """Raised when a ZFS snapshot is not found"""
    pass


class ZFSPoolNotFoundError(ZFSNotFoundError):
    """Raised when a ZFS pool is not found"""
    pass