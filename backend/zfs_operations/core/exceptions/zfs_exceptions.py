from typing import Dict, Any, Optional


class ZFSException(Exception):
    """Base exception for all ZFS operations"""
    
    def __init__(self, message: str, error_code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for serialization"""
        return {
            'error_type': self.__class__.__name__,
            'message': str(self),
            'error_code': self.error_code,
            'details': self.details
        }


class DatasetException(ZFSException):
    """Dataset-related exceptions"""
    pass


class DatasetNotFoundError(DatasetException):
    """Dataset not found exception"""
    
    def __init__(self, dataset_name: str):
        super().__init__(
            f"Dataset '{dataset_name}' not found",
            error_code="DATASET_NOT_FOUND",
            details={"dataset_name": dataset_name}
        )


class DatasetAlreadyExistsError(DatasetException):
    """Dataset already exists exception"""
    
    def __init__(self, dataset_name: str):
        super().__init__(
            f"Dataset '{dataset_name}' already exists",
            error_code="DATASET_ALREADY_EXISTS",
            details={"dataset_name": dataset_name}
        )


class DatasetBusyError(DatasetException):
    """Dataset is busy exception"""
    
    def __init__(self, dataset_name: str, reason: str = ""):
        message = f"Dataset '{dataset_name}' is busy"
        if reason:
            message += f": {reason}"
        super().__init__(
            message,
            error_code="DATASET_BUSY",
            details={"dataset_name": dataset_name, "reason": reason}
        )


class SnapshotException(ZFSException):
    """Snapshot-related exceptions"""
    pass


class SnapshotNotFoundError(SnapshotException):
    """Snapshot not found exception"""
    
    def __init__(self, snapshot_name: str):
        super().__init__(
            f"Snapshot '{snapshot_name}' not found",
            error_code="SNAPSHOT_NOT_FOUND",
            details={"snapshot_name": snapshot_name}
        )


class SnapshotAlreadyExistsError(SnapshotException):
    """Snapshot already exists exception"""
    
    def __init__(self, snapshot_name: str):
        super().__init__(
            f"Snapshot '{snapshot_name}' already exists",
            error_code="SNAPSHOT_ALREADY_EXISTS",
            details={"snapshot_name": snapshot_name}
        )


class PoolException(ZFSException):
    """Pool-related exceptions"""
    pass


class PoolNotFoundError(PoolException):
    """Pool not found exception"""
    
    def __init__(self, pool_name: str):
        super().__init__(
            f"Pool '{pool_name}' not found",
            error_code="POOL_NOT_FOUND",
            details={"pool_name": pool_name}
        )


class PoolHealthError(PoolException):
    """Pool health issue exception"""
    
    def __init__(self, pool_name: str, health_status: str):
        super().__init__(
            f"Pool '{pool_name}' health issue: {health_status}",
            error_code="POOL_HEALTH_ERROR",
            details={"pool_name": pool_name, "health_status": health_status}
        )


class PoolUnavailableError(PoolException):
    """Pool unavailable exception"""
    
    def __init__(self, message: str):
        super().__init__(
            message,
            error_code="POOL_UNAVAILABLE",
            details={"message": message}
        )


class RemoteOperationException(ZFSException):
    """Remote operation exceptions"""
    pass


class RemoteConnectionError(RemoteOperationException):
    """Remote connection error"""
    
    def __init__(self, host: str, reason: str = ""):
        message = f"Failed to connect to remote host '{host}'"
        if reason:
            message += f": {reason}"
        super().__init__(
            message,
            error_code="REMOTE_CONNECTION_ERROR",
            details={"host": host, "reason": reason}
        )


class RemoteCommandError(RemoteOperationException):
    """Remote command execution error"""
    
    def __init__(self, host: str, command: str, exit_code: int, stderr: str = ""):
        message = f"Remote command failed on '{host}' (exit code {exit_code}): {command}"
        if stderr:
            message += f"\nError: {stderr}"
        super().__init__(
            message,
            error_code="REMOTE_COMMAND_ERROR",
            details={
                "host": host,
                "command": command,
                "exit_code": exit_code,
                "stderr": stderr
            }
        )


class BackupException(ZFSException):
    """Backup-related exceptions"""
    pass


class BackupNotFoundError(BackupException):
    """Backup not found exception"""
    
    def __init__(self, backup_name: str):
        super().__init__(
            f"Backup '{backup_name}' not found",
            error_code="BACKUP_NOT_FOUND",
            details={"backup_name": backup_name}
        )


class BackupCorruptedError(BackupException):
    """Backup corrupted exception"""
    
    def __init__(self, backup_name: str, reason: str = ""):
        message = f"Backup '{backup_name}' is corrupted"
        if reason:
            message += f": {reason}"
        super().__init__(
            message,
            error_code="BACKUP_CORRUPTED",
            details={"backup_name": backup_name, "reason": reason}
        )


class EncryptionException(ZFSException):
    """Encryption-related exceptions"""
    pass


class EncryptionKeyError(EncryptionException):
    """Encryption key error"""
    
    def __init__(self, dataset_name: str, reason: str = ""):
        message = f"Encryption key error for dataset '{dataset_name}'"
        if reason:
            message += f": {reason}"
        super().__init__(
            message,
            error_code="ENCRYPTION_KEY_ERROR",
            details={"dataset_name": dataset_name, "reason": reason}
        )


class EncryptionNotSupportedError(EncryptionException):
    """Encryption not supported exception"""
    
    def __init__(self, reason: str = ""):
        message = "Encryption is not supported"
        if reason:
            message += f": {reason}"
        super().__init__(
            message,
            error_code="ENCRYPTION_NOT_SUPPORTED",
            details={"reason": reason}
        )


class QuotaException(ZFSException):
    """Quota-related exceptions"""
    pass


class QuotaExceededError(QuotaException):
    """Quota exceeded exception"""
    
    def __init__(self, dataset_name: str, quota_type: str, current_usage: str, quota_limit: str):
        super().__init__(
            f"{quota_type} quota exceeded for dataset '{dataset_name}': {current_usage} > {quota_limit}",
            error_code="QUOTA_EXCEEDED",
            details={
                "dataset_name": dataset_name,
                "quota_type": quota_type,
                "current_usage": current_usage,
                "quota_limit": quota_limit
            }
        )


class InsufficientSpaceError(ZFSException):
    """Insufficient space exception"""
    
    def __init__(self, required_space: str, available_space: str, location: str = ""):
        message = f"Insufficient space: required {required_space}, available {available_space}"
        if location:
            message += f" at {location}"
        super().__init__(
            message,
            error_code="INSUFFICIENT_SPACE",
            details={
                "required_space": required_space,
                "available_space": available_space,
                "location": location
            }
        ) 