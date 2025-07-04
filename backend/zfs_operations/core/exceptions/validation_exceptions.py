from typing import Dict, Any, Optional, List


class ValidationException(Exception):
    """Base validation exception"""
    
    def __init__(self, message: str, field: Optional[str] = None, value: Optional[Any] = None):
        super().__init__(message)
        self.field = field
        self.value = value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for serialization"""
        return {
            'error_type': self.__class__.__name__,
            'message': str(self),
            'field': self.field,
            'value': self.value
        }


class SecurityValidationError(ValidationException):
    """Security validation failed"""
    
    def __init__(self, message: str, field: Optional[str] = None, value: Optional[Any] = None, 
                 security_issue: Optional[str] = None):
        super().__init__(message, field, value)
        self.security_issue = security_issue
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for serialization"""
        result = super().to_dict()
        result['security_issue'] = self.security_issue
        return result


class ParameterValidationError(ValidationException):
    """Parameter validation failed"""
    
    def __init__(self, message: str, parameter: str, value: Any, expected_type: Optional[str] = None):
        super().__init__(message, parameter, value)
        self.parameter = parameter
        self.expected_type = expected_type
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for serialization"""
        result = super().to_dict()
        result['parameter'] = self.parameter
        result['expected_type'] = self.expected_type
        return result


class DatasetNameValidationError(ValidationException):
    """Dataset name validation failed"""
    
    def __init__(self, dataset_name: str, reason: str):
        super().__init__(f"Invalid dataset name '{dataset_name}': {reason}", 'dataset_name', dataset_name)
        self.dataset_name = dataset_name
        self.reason = reason


class SizeValidationError(ValidationException):
    """Size validation failed"""
    
    def __init__(self, size_string: str, reason: str):
        super().__init__(f"Invalid size '{size_string}': {reason}", 'size', size_string)
        self.size_string = size_string
        self.reason = reason


class HostValidationError(ValidationException):
    """Host validation failed"""
    
    def __init__(self, hostname: str, reason: str):
        super().__init__(f"Invalid hostname '{hostname}': {reason}", 'hostname', hostname)
        self.hostname = hostname
        self.reason = reason


class SSHConfigValidationError(ValidationException):
    """SSH configuration validation failed"""
    
    def __init__(self, config_field: str, value: Any, reason: str):
        super().__init__(f"Invalid SSH config {config_field} '{value}': {reason}", config_field, value)
        self.config_field = config_field
        self.reason = reason


class CommandValidationError(ValidationException):
    """Command validation failed"""
    
    def __init__(self, command: str, command_args: List[str], reason: str):
        super().__init__(f"Invalid command '{command}' with args {command_args}: {reason}", 'command', command)
        self.command = command
        self.command_args = command_args
        self.reason = reason


class PathValidationError(ValidationException):
    """Path validation failed"""
    
    def __init__(self, path: str, reason: str):
        super().__init__(f"Invalid path '{path}': {reason}", 'path', path)
        self.path = path
        self.reason = reason


class PortValidationError(ValidationException):
    """Port validation failed"""
    
    def __init__(self, port: int, reason: str):
        super().__init__(f"Invalid port {port}: {reason}", 'port', port)
        self.port = port
        self.reason = reason


class MultipleValidationError(ValidationException):
    """Multiple validation errors"""
    
    def __init__(self, errors: List[ValidationException]):
        messages = [str(error) for error in errors]
        super().__init__(f"Multiple validation errors: {'; '.join(messages)}")
        self.errors = errors
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for serialization"""
        return {
            'error_type': self.__class__.__name__,
            'message': str(self),
            'errors': [error.to_dict() for error in self.errors]
        } 