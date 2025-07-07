"""Domain validation exceptions"""

from typing import Optional


class ValidationError(ValueError):
    """Raised when domain validation fails"""
    
    def __init__(self, message: str, field: Optional[str] = None):
        self.field = field
        super().__init__(message)


class InvalidDatasetNameError(ValidationError):
    """Raised when dataset name validation fails"""
    pass


class InvalidSnapshotNameError(ValidationError):
    """Raised when snapshot name validation fails"""
    pass


class InvalidHostnameError(ValidationError):
    """Raised when hostname validation fails"""
    pass


class InvalidPortError(ValidationError):
    """Raised when port validation fails"""
    pass