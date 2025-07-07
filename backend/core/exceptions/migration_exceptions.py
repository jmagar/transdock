"""Migration domain exceptions"""

from typing import Optional, List


class MigrationOperationError(Exception):
    """Exception raised when a migration operation fails"""
    
    def __init__(self, message: str, migration_id: Optional[str] = None, step_id: Optional[str] = None):
        super().__init__(message)
        self.migration_id = migration_id
        self.step_id = step_id


class MigrationNotFoundError(MigrationOperationError):
    """Exception raised when a migration is not found"""
    
    def __init__(self, message: str, migration_id: Optional[str] = None):
        super().__init__(message, migration_id=migration_id)


class MigrationValidationError(MigrationOperationError):
    """Exception raised when migration validation fails"""
    
    def __init__(self, message: str, validation_errors: Optional[List[str]] = None):
        super().__init__(message)
        self.validation_errors = validation_errors or []


class MigrationStepError(MigrationOperationError):
    """Exception raised when a migration step fails"""
    
    def __init__(self, message: str, step_type: Optional[str] = None, step_id: Optional[str] = None):
        super().__init__(message, step_id=step_id)
        self.step_type = step_type


class MigrationCancelledError(MigrationOperationError):
    """Exception raised when a migration is cancelled"""
    
    def __init__(self, message: str, migration_id: Optional[str] = None):
        super().__init__(message, migration_id=migration_id)


class MigrationTimeoutError(MigrationOperationError):
    """Exception raised when a migration times out"""
    
    def __init__(self, message: str, migration_id: Optional[str] = None, timeout_seconds: Optional[int] = None):
        super().__init__(message, migration_id=migration_id)
        self.timeout_seconds = timeout_seconds