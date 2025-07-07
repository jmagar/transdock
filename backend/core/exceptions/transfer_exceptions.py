"""Transfer domain exceptions"""

from typing import Optional


class TransferError(Exception):
    """Raised when a transfer operation fails"""
    
    def __init__(self, message: str, source: Optional[str] = None, target: Optional[str] = None):
        self.source = source
        self.target = target
        super().__init__(message)


class TransferTimeoutError(TransferError):
    """Raised when a transfer operation times out"""
    pass


class TransferValidationError(TransferError):
    """Raised when transfer validation fails"""
    pass


class TransferConnectionError(TransferError):
    """Raised when unable to establish transfer connection"""
    pass


class TransferPermissionError(TransferError):
    """Raised when transfer fails due to permission issues"""
    pass


class TransferInsufficientSpaceError(TransferError):
    """Raised when target doesn't have sufficient space"""
    pass