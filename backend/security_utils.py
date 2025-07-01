"""Security utilities for input validation and sanitization."""

import os
import re
import shlex
from dataclasses import dataclass
from typing import List, Optional


class SecurityValidationError(Exception):
    """Exception raised when security validation fails."""
    pass


@dataclass
class RsyncConfig:
    """Configuration object for rsync command building."""
    source: str
    hostname: str
    username: str
    port: int
    target: str
    additional_args: Optional[List[str]] = None


class SecurityUtils:
    """Utilities for secure handling of user inputs and commands."""
    
    # Regex patterns for validation
    HOSTNAME_PATTERN = re.compile(r'^[a-zA-Z0-9.-]+$')
    USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9._-]+$')
    DATASET_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9/_.-]+$')
    
    @staticmethod
    def validate_hostname(hostname: str) -> str:
        """Validate and sanitize hostname."""
        if not hostname or len(hostname) > 253:
            raise SecurityValidationError(f"Invalid hostname length: {hostname}")
        
        if not SecurityUtils.HOSTNAME_PATTERN.match(hostname):
            raise SecurityValidationError(f"Invalid hostname format: {hostname}")
        
        # Check for obvious malicious patterns
        if any(char in hostname for char in ['&', '|', ';', '`', '$', '(', ')']):
            raise SecurityValidationError(f"Hostname contains invalid characters: {hostname}")
        
        return hostname
    
    @staticmethod
    def validate_username(username: str) -> str:
        """Validate and sanitize SSH username."""
        if not username or len(username) > 32:
            raise SecurityValidationError(f"Invalid username length: {username}")
        
        if not SecurityUtils.USERNAME_PATTERN.match(username):
            raise SecurityValidationError(f"Invalid username format: {username}")
        
        return username
    
    @staticmethod
    def validate_port(port: int) -> int:
        """Validate SSH port number."""
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise SecurityValidationError(f"Invalid port number: {port}")
        
        return port
    
    @staticmethod
    def validate_dataset_name(dataset_name: str) -> str:
        """Validate ZFS dataset name."""
        if not dataset_name or len(dataset_name) > 256:
            raise SecurityValidationError(f"Invalid dataset name length: {dataset_name}")
        
        if not SecurityUtils.DATASET_NAME_PATTERN.match(dataset_name):
            raise SecurityValidationError(f"Invalid dataset name format: {dataset_name}")
        
        # Check for path traversal attempts
        if '..' in dataset_name or dataset_name.startswith('/'):
            raise SecurityValidationError(f"Dataset name contains path traversal: {dataset_name}")
        
        return dataset_name
    
    @staticmethod
    def sanitize_path(path: str, base_path: Optional[str] = None) -> str:
        """Sanitize and validate file paths to prevent directory traversal."""
        if not path:
            raise SecurityValidationError("Path cannot be empty")
        
        # Check for path traversal attempts BEFORE normalization
        if '..' in path or path.startswith('../'):
            raise SecurityValidationError(f"Path contains directory traversal: {path}")
        
        # Check for null bytes and other dangerous characters
        if '\0' in path:
            raise SecurityValidationError(f"Path contains null bytes: {path}")
        
        # Normalize the path after validation
        normalized_path = os.path.normpath(path)
        
        # If base_path is provided, ensure the path is within it
        if base_path:
            # Make paths absolute for reliable comparison
            abs_base = os.path.abspath(base_path)
            abs_normalized = os.path.abspath(normalized_path)
            if not abs_normalized.startswith(abs_base + os.sep) and abs_normalized != abs_base:
                raise SecurityValidationError(f"Path is outside base directory: {path}")
        
        return normalized_path
    
    @staticmethod
    def escape_shell_argument(arg: str) -> str:
        """Safely escape shell arguments using shlex.quote."""
        return shlex.quote(str(arg))
    
    @staticmethod
    def build_ssh_command(hostname: str, username: str, port: int, remote_command: str) -> List[str]:
        """Build a secure SSH command with proper escaping."""
        # Validate inputs
        hostname = SecurityUtils.validate_hostname(hostname)
        username = SecurityUtils.validate_username(username)
        port = SecurityUtils.validate_port(port)
        
        # Build command - remote command should NOT be escaped as single argument
        # SSH handles the remote command directly
        return [
            "ssh",
            "-p", str(port),
            f"{username}@{hostname}",
            remote_command
        ]
    
    @staticmethod
    def build_rsync_command(config: RsyncConfig) -> List[str]:
        """Build a secure rsync command with proper escaping using RsyncConfig."""
        # Validate inputs
        hostname = SecurityUtils.validate_hostname(config.hostname)
        username = SecurityUtils.validate_username(config.username)
        port = SecurityUtils.validate_port(config.port)
        
        # Build base command - check for --delete in additional_args to avoid duplication
        cmd = ["rsync", "-avzP"]
        
        # Track existing flags to avoid duplicates
        existing_flags = set(cmd)
        
        # Add additional arguments if provided
        if config.additional_args:
            cmd.extend(arg for arg in config.additional_args if arg not in existing_flags)
            existing_flags.update(config.additional_args)
        
        # Add --delete if not already present in additional_args
        if "--delete" not in existing_flags:
            cmd.append("--delete")
        
        # Add SSH specification
        cmd.extend(["-e", f"ssh -p {port}"])
        
        # Add source and destination with proper escaping
        cmd.extend([
            SecurityUtils.escape_shell_argument(config.source),
            f"{username}@{hostname}:{SecurityUtils.escape_shell_argument(config.target)}"
        ])
        
        return cmd
    
    @staticmethod
    def validate_zfs_command_args(command: str, *args) -> List[str]:
        """Validate and build ZFS command arguments safely."""
        if command not in ['list', 'create', 'destroy', 'snapshot', 'send', 'receive', 'clone', 'set', 'get']:
            raise SecurityValidationError(f"Invalid ZFS command: {command}")
        
        validated_args = ["zfs", command]
        
        for arg in args:
            if isinstance(arg, str):
                # Basic validation for ZFS arguments
                if len(arg) > 512:  # Reasonable limit
                    raise SecurityValidationError(f"ZFS argument too long: {arg[:50]}...")
                
                # Check for command injection attempts
                if any(char in arg for char in ['&', '|', ';', '`', '$', '(', ')', '\n', '\r']):
                    raise SecurityValidationError(f"ZFS argument contains invalid characters: {arg}")
                    
                validated_args.append(SecurityUtils.escape_shell_argument(arg))
            else:
                validated_args.append(str(arg))
        
        return validated_args
    
    @staticmethod
    def validate_migration_request(compose_dataset: str, target_host: str, 
                                   ssh_user: str, ssh_port: int, target_base_path: str) -> None:
        """Validate all parameters for a complete migration request."""
        try:
            SecurityUtils.validate_dataset_name(compose_dataset)
            SecurityUtils.validate_hostname(target_host)
            SecurityUtils.validate_username(ssh_user)
            SecurityUtils.validate_port(ssh_port)
            SecurityUtils.sanitize_path(target_base_path)
        except SecurityValidationError as e:
            raise SecurityValidationError(f"Migration validation failed: {e}") from e