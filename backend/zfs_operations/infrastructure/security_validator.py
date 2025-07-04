"""
Concrete implementation of security validator interface.
"""
import re
from typing import List, Dict, Tuple
from ..core.interfaces.security_validator import ISecurityValidator
from ..core.value_objects.ssh_config import SSHConfig
from ..core.exceptions.validation_exceptions import (
    SecurityValidationError,
    ParameterValidationError
)


class SecurityValidator(ISecurityValidator):
    """Concrete implementation of security validator with comprehensive validation rules."""
    
    def __init__(self):
        # Dataset name validation patterns
        self._dataset_name_pattern = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_\-\.]*(?:/[a-zA-Z0-9][a-zA-Z0-9_\-\.]*)*$')
        self._pool_name_pattern = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_\-\.]*$')
        
        # Hostname validation
        self._hostname_pattern = re.compile(
            r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$'
        )
        
        # Username validation
        self._username_pattern = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_\-\.]*$')
        
        # Command injection patterns to block
        self._dangerous_patterns = [
            r'[;&|`$(){}[\]\\]',  # Command separators and shell metacharacters
            r'\.\./',             # Path traversal attempts
            r'<|>',               # Redirection operators
            r'\n|\r',             # Newline characters
        ]
        
        # ZFS property validation
        self._valid_zfs_properties = {
            'compression', 'dedup', 'encryption', 'keyformat', 'keylocation',
            'mountpoint', 'quota', 'reservation', 'recordsize', 'atime',
            'relatime', 'checksum', 'copies', 'readonly', 'canmount',
            'devices', 'exec', 'setuid', 'nbmand', 'overlay', 'acltype',
            'aclinherit', 'dnodesize', 'logbias', 'primarycache',
            'secondarycache', 'sync', 'redundant_metadata', 'special_small_blocks'
        }
    
    def validate_dataset_name(self, name: str) -> str:
        """Validate dataset name for security and format compliance."""
        if not name or not isinstance(name, str):
            raise SecurityValidationError("Dataset name cannot be empty or non-string")
        
        # Length check
        if len(name) > 256:
            raise SecurityValidationError("Dataset name too long (max 256 characters)")
        
        # Check for dangerous patterns
        for pattern in self._dangerous_patterns:
            if re.search(pattern, name):
                raise SecurityValidationError(f"Dataset name contains dangerous characters: {name}")
        
        # Format validation
        if not self._dataset_name_pattern.match(name):
            raise SecurityValidationError(f"Invalid dataset name format: {name}")
        
        # Additional security checks
        if name.startswith('/') or name.endswith('/'):
            raise SecurityValidationError("Dataset name cannot start or end with '/'")
        
        if '//' in name:
            raise SecurityValidationError("Dataset name cannot contain consecutive slashes")
        
        return name
    
    def validate_zfs_command(self, command: str, args: List[str]) -> List[str]:
        """Validate ZFS command and its arguments."""
        if not command or not isinstance(command, str):
            raise SecurityValidationError("Command cannot be empty or non-string")
        
        # Check command for dangerous patterns
        for pattern in self._dangerous_patterns:
            if re.search(pattern, command):
                raise SecurityValidationError(f"Command contains dangerous characters: {command}")
        
        # Validate arguments
        validated_args = []
        for arg in args:
            if not isinstance(arg, str):
                raise SecurityValidationError("All arguments must be strings")
            
            # Check for dangerous patterns
            for pattern in self._dangerous_patterns:
                if re.search(pattern, arg):
                    raise SecurityValidationError(f"Argument contains dangerous characters: {arg}")
            
            # Length check
            if len(arg) > 1024:
                raise SecurityValidationError("Argument too long (max 1024 characters)")
            
            validated_args.append(arg)
        
        return validated_args
    
    def validate_ssh_config(self, config: SSHConfig) -> SSHConfig:
        """Validate SSH configuration."""
        if not config:
            raise SecurityValidationError("SSH config cannot be None")
        
        # Validate hostname
        if not self._hostname_pattern.match(config.host):
            raise SecurityValidationError(f"Invalid hostname format: {config.host}")
        
        # Validate username
        if not self._username_pattern.match(config.user):
            raise SecurityValidationError(f"Invalid username format: {config.user}")
        
        # Validate port range
        if not (1 <= config.port <= 65535):
            raise SecurityValidationError(f"Invalid port number: {config.port}")
        
        # Validate timeout
        if config.timeout <= 0 or config.timeout > 300:
            raise SecurityValidationError(f"Invalid timeout value: {config.timeout}")
        
        # Validate key file path if provided
        if config.key_file:
            if not isinstance(config.key_file, str):
                raise SecurityValidationError("Key file path must be a string")
            
            # Check for path traversal attempts
            if '..' in config.key_file:
                raise SecurityValidationError("Key file path contains path traversal attempts")
        
        return config
    
    def validate_hostname(self, hostname: str) -> str:
        """Validate hostname format."""
        if not hostname or not isinstance(hostname, str):
            raise SecurityValidationError("Hostname cannot be empty or non-string")
        
        if len(hostname) > 253:
            raise SecurityValidationError("Hostname too long (max 253 characters)")
        
        if not self._hostname_pattern.match(hostname):
            raise SecurityValidationError(f"Invalid hostname format: {hostname}")
        
        return hostname
    
    def validate_username(self, username: str) -> str:
        """Validate username format."""
        if not username or not isinstance(username, str):
            raise SecurityValidationError("Username cannot be empty or non-string")
        
        if len(username) > 32:
            raise SecurityValidationError("Username too long (max 32 characters)")
        
        if not self._username_pattern.match(username):
            raise SecurityValidationError(f"Invalid username format: {username}")
        
        return username
    
    def validate_port(self, port: int) -> int:
        """Validate port number."""
        if not isinstance(port, int):
            raise SecurityValidationError("Port must be an integer")
        
        if not (1 <= port <= 65535):
            raise SecurityValidationError(f"Invalid port number: {port}")
        
        return port
    
    def validate_zfs_property(self, property_name: str, value: str) -> Tuple[str, str]:
        """Validate ZFS property name and value."""
        if not property_name or not isinstance(property_name, str):
            raise SecurityValidationError("Property name cannot be empty or non-string")
        
        if property_name not in self._valid_zfs_properties:
            raise SecurityValidationError(f"Invalid ZFS property: {property_name}")
        
        if not isinstance(value, str):
            raise SecurityValidationError("Property value must be a string")
        
        # Check for dangerous patterns in value
        for pattern in self._dangerous_patterns:
            if re.search(pattern, value):
                raise SecurityValidationError(f"Property value contains dangerous characters: {value}")
        
        # Property-specific validation
        if property_name == 'compression':
            valid_compression = {'on', 'off', 'lzjb', 'gzip', 'gzip-1', 'gzip-2', 'gzip-3', 
                               'gzip-4', 'gzip-5', 'gzip-6', 'gzip-7', 'gzip-8', 'gzip-9', 
                               'lz4', 'zle', 'zstd'}
            if value not in valid_compression:
                raise SecurityValidationError(f"Invalid compression value: {value}")
        
        elif property_name == 'encryption':
            valid_encryption = {'on', 'off', 'aes-128-ccm', 'aes-192-ccm', 'aes-256-ccm',
                              'aes-128-gcm', 'aes-192-gcm', 'aes-256-gcm'}
            if value not in valid_encryption:
                raise SecurityValidationError(f"Invalid encryption value: {value}")
        
        elif property_name in ['quota', 'reservation']:
            # Basic size validation
            if not re.match(r'^\d+[BKMGTPEZ]?$', value.upper()) and value not in ['none', '0']:
                raise SecurityValidationError(f"Invalid size value: {value}")
        
        return property_name, value
    
    def validate_snapshot_name(self, name: str) -> str:
        """Validate snapshot name format."""
        if not name or not isinstance(name, str):
            raise SecurityValidationError("Snapshot name cannot be empty or non-string")
        
        if '@' not in name:
            raise SecurityValidationError("Snapshot name must contain '@' separator")
        
        dataset_part, snapshot_part = name.rsplit('@', 1)
        
        # Validate dataset part
        self.validate_dataset_name(dataset_part)
        
        # Validate snapshot part
        if not snapshot_part:
            raise SecurityValidationError("Snapshot suffix cannot be empty")
        
        if len(snapshot_part) > 256:
            raise SecurityValidationError("Snapshot suffix too long (max 256 characters)")
        
        # Check for dangerous patterns in snapshot part
        for pattern in self._dangerous_patterns:
            if re.search(pattern, snapshot_part):
                raise SecurityValidationError(f"Snapshot name contains dangerous characters: {name}")
        
        return name
    
    def validate_path(self, path: str) -> str:
        """Validate and sanitize file path."""
        if not path or not isinstance(path, str):
            raise SecurityValidationError("Path cannot be empty or non-string")
        
        if len(path) > 1024:
            raise SecurityValidationError("Path too long (max 1024 characters)")
        
        # Check for dangerous patterns
        for pattern in self._dangerous_patterns:
            if re.search(pattern, path):
                raise SecurityValidationError(f"Path contains dangerous characters: {path}")
        
        # Check for path traversal attempts
        if '..' in path:
            raise SecurityValidationError("Path contains path traversal attempts")
        
        # Path should start with / for absolute paths
        if not path.startswith('/'):
            raise SecurityValidationError("Path must be absolute (start with /)")
        
        return path
    
    def escape_shell_argument(self, arg: str) -> str:
        """Escape shell argument to prevent injection."""
        if not arg or not isinstance(arg, str):
            return ""
        
        # Simple escaping - wrap in single quotes and escape any single quotes
        escaped = arg.replace("'", "'\"'\"'")
        return f"'{escaped}'"
    
    def validate_zfs_properties(self, properties: Dict[str, str]) -> Dict[str, str]:
        """Validate multiple ZFS properties."""
        if not properties:
            return {}
        
        validated_properties = {}
        for property_name, value in properties.items():
            try:
                validated_name, validated_value = self.validate_zfs_property(property_name, value)
                validated_properties[validated_name] = validated_value
            except Exception as e:
                raise SecurityValidationError(f"Property validation failed for {property_name}: {str(e)}")
        
        return validated_properties
    
    def validate_pool_name(self, pool_name: str) -> str:
        """Validate and sanitize pool name."""
        if not pool_name or not isinstance(pool_name, str):
            raise SecurityValidationError("Pool name cannot be empty or non-string")
        
        # Use same validation as dataset name for consistency
        return self.validate_dataset_name(pool_name)