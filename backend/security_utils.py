"""Security utilities for input validation and sanitization."""

import os
import re
import shlex
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import unquote


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
    DATASET_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9/_. -]+$')

    @staticmethod
    def validate_hostname(hostname: str) -> str:
        """Validate and sanitize hostname."""
        if not hostname or len(hostname) > 253:
            raise SecurityValidationError(
                f"Invalid hostname length: {hostname}")

        if not SecurityUtils.HOSTNAME_PATTERN.match(hostname):
            raise SecurityValidationError(
                f"Invalid hostname format: {hostname}")

        # Check for obvious malicious patterns
        if any(
            char in hostname for char in [
                '&', '|', ';', '`', '$', '(', ')']):
            raise SecurityValidationError(
                f"Hostname contains invalid characters: {hostname}")

        return hostname

    @staticmethod
    def validate_username(username: str) -> str:
        """Validate and sanitize SSH username."""
        if not username or len(username) > 32:
            raise SecurityValidationError(
                f"Invalid username length: {username}")

        if not SecurityUtils.USERNAME_PATTERN.match(username):
            raise SecurityValidationError(
                f"Invalid username format: {username}")

        return username

    @staticmethod
    def validate_port(port: int) -> int:
        """Validate SSH port number."""
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise SecurityValidationError(f"Invalid port number: {port}")

        return port

    @staticmethod
    def validate_dataset_name(name: str) -> str:
        """Validate ZFS dataset name."""
        if not name or len(name) > 256:
            raise SecurityValidationError(
                f"Invalid dataset name length: {name}")

        if not SecurityUtils.DATASET_NAME_PATTERN.match(name):
            raise SecurityValidationError(
                f"Invalid dataset name format: {name}")

        # Check for path traversal attempts
        if '..' in name or name.startswith('/'):
            raise SecurityValidationError(
                f"Dataset name contains path traversal: {name}")

        return name

    @staticmethod
    def sanitize_path(
            path: str,
            base_path: Optional[str] = None,
            allow_absolute: bool = False) -> str:
        """Sanitize and validate file paths to prevent directory traversal."""
        if not path:
            raise SecurityValidationError("Path cannot be empty")

        original_path = path

        # 1. URL Decode (single and double)
        try:
            decoded_path = unquote(path)
            while path != decoded_path:
                path = decoded_path
                decoded_path = unquote(path)
        except Exception as e:
            # If decoding fails, it's a suspicious path
            raise SecurityValidationError(
                f"Path contains invalid URL encoding: {original_path}") from e

        # 2. Check for null bytes
        if '\\0' in path or '\x00' in path:
            raise SecurityValidationError(
                f"Path contains null bytes: {original_path}")

        # 3. Check for various path traversal patterns BEFORE normalization
        traversal_patterns = [
            '..\\.',
            '../',
            '..\\',
            '%2e%2e',
            '%2e%2e%2f',
            '%2e%2e%5c',
            '....//']
        for pattern in traversal_patterns:
            if pattern in path.lower():
                raise SecurityValidationError(
                    f"Path contains directory traversal attempt: {original_path}")

        # Additional check for Unicode-encoded path traversal
        if '\xc0\xaf' in path or '��' in path:
            raise SecurityValidationError(
                f"Path contains directory traversal attempt: {original_path}")

        # 4. Check for absolute paths (both Unix and Windows style) - block by
        # default for security
        if path.startswith('/') or (len(path) >
                                    1 and path[1] == ':') or path.startswith('\\'):
            if not allow_absolute:
                raise SecurityValidationError(
                    f"Path contains directory traversal attempt: {original_path}")

        # 5. Normalize the path to resolve '..' and '.' components
        normalized_path = os.path.normpath(path)

        # 6. Check for directory traversal patterns AFTER normalization
        if '..' in normalized_path.split(os.sep):
            raise SecurityValidationError(
                f"Path contains directory traversal attempt: {original_path}")

        # 7. If base_path is provided, ensure the path is within it
        if base_path:
            real_base_path = os.path.realpath(base_path)
            # IMPORTANT: Join with the *un-normalized* path to avoid issues with absolute paths
            # The realpath will resolve it safely
            real_user_path = os.path.realpath(
                os.path.join(real_base_path, normalized_path))

            if not real_user_path.startswith(real_base_path):
                raise SecurityValidationError(
                    f"Path is outside of the allowed base directory: {original_path}")

        return normalized_path

    @staticmethod
    def split_wildcard_path(path: str) -> Tuple[str, str]:
        """
        Safely splits a path containing a wildcard into a base path and the pattern.
        Example: /home/*/appdata -> ("/home", "*/appdata")
        """
        if '*' not in path:
            raise ValueError("Path does not contain a wildcard.")

        # Sanitize first to prevent tricks like /home/../*/etc/passwd
        sanitized_path = SecurityUtils.sanitize_path(path, allow_absolute=True)

        parts = sanitized_path.split(os.sep)
        
        # Find the first part with a wildcard
        wildcard_index = -1
        for i, part in enumerate(parts):
            if '*' in part:
                wildcard_index = i
                break
        
        if wildcard_index <= 1 and sanitized_path.startswith('/'):
            # Avoid overly broad wildcards like /* or /tmp/*
            raise ValueError(f"Wildcard is too high in the directory structure: {path}")
        
        # Reconstruct base path and pattern
        base_path = os.sep.join(parts[:wildcard_index])
        pattern = os.sep.join(parts[wildcard_index:])
        
        # Final validation on base_path
        if not base_path or '..' in base_path:
            raise ValueError(f"Invalid base path derived from wildcard: {path}")

        return base_path, pattern

    @staticmethod
    def escape_shell_argument(arg: str) -> str:
        """Safely escape shell arguments using shlex.quote."""
        return shlex.quote(str(arg))

    @staticmethod
    def build_ssh_command(
            hostname: str,
            username: str,
            port: int,
            remote_command: str) -> List[str]:
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

        # Build base command
        cmd = ["rsync", "-avzP"]

        # Check if --delete is already in additional_args to avoid duplication
        has_delete_flag = False
        if config.additional_args:
            has_delete_flag = "--delete" in config.additional_args
            cmd.extend(config.additional_args)

        # Add --delete if not already present in additional_args
        if not has_delete_flag:
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
        if command not in [
            'list',
            'create',
            'destroy',
            'snapshot',
            'send',
            'receive',
            'clone',
            'set',
                'get']:
            raise SecurityValidationError(f"Invalid ZFS command: {command}")

        validated_args = ["zfs", command]

        for arg in args:
            if isinstance(arg, str):
                # Basic validation for ZFS arguments
                if len(arg) > 512:  # Reasonable limit
                    raise SecurityValidationError(
                        f"ZFS argument too long: {arg[:50]}...")

                # Check for command injection attempts
                if any(
                    char in arg for char in [
                        '&', '|', ';', '`', '$', '(', ')', '\n', '\r']):
                    raise SecurityValidationError(
                        f"ZFS argument contains invalid characters: {arg}")

                validated_args.append(SecurityUtils.escape_shell_argument(arg))
            else:
                validated_args.append(str(arg))

        return validated_args

    @staticmethod
    def validate_system_command_args(command: str, *args) -> List[str]:
        """Validate and build system command arguments safely for dataset management."""
        # Only allow specific system commands needed for dataset management
        allowed_commands = ['umount', 'fuser', 'lsof', 'kill', 'mountpoint']

        if command not in allowed_commands:
            raise SecurityValidationError(f"Invalid system command: {command}")

        validated_args = [command]

        for arg in args:
            if isinstance(arg, str):
                # Basic validation for system command arguments
                if len(arg) > 512:  # Reasonable limit
                    raise SecurityValidationError(
                        f"System command argument too long: {arg[:50]}...")

                # Check for command injection attempts
                if any(
                    char in arg for char in [
                        '&', '|', ';', '`', '$', '(', ')', '\n', '\r']):
                    raise SecurityValidationError(
                        f"System command argument contains invalid characters: {arg}")

                validated_args.append(SecurityUtils.escape_shell_argument(arg))
            else:
                validated_args.append(str(arg))

        return validated_args

    @staticmethod
    def create_secure_mount_point(base_path: str, identifier: str) -> str:
        """Create a secure mount point path."""
        # Sanitize identifier
        safe_identifier = re.sub(r'[^a-zA-Z0-9_-]', '_', identifier)

        # Create path within base directory
        mount_point = os.path.join(base_path, safe_identifier)

        # Validate the resulting path
        return SecurityUtils.sanitize_path(mount_point, base_path)

    @staticmethod
    def validate_migration_request(
            compose_dataset: str,
            target_host: str,
            ssh_user: str,
            ssh_port: int,
            target_base_path: str) -> None:
        """Validate all parameters of a migration request."""
        # Validate compose dataset with proper dataset validation
        SecurityUtils.validate_dataset_name(compose_dataset)

        # Validate target host
        SecurityUtils.validate_hostname(target_host)

        # Validate SSH credentials
        SecurityUtils.validate_username(ssh_user)
        SecurityUtils.validate_port(ssh_port)

        # Validate target base path
        SecurityUtils.sanitize_path(target_base_path, allow_absolute=True)

        # Additional validation for obviously malicious target paths
        dangerous_paths = [
            '/etc/', '/var/log/', '/usr/bin/', '/bin/', '/sbin/', '/boot/',
            '/sys/', '/proc/', '/dev/', '/root/', '/tmp/', '/var/tmp/',
            '\\windows\\', '\\system32\\', '\\program files\\', '\\users\\',
            '\\boot\\', '\\recovery\\'
        ]

        target_lower = target_base_path.lower()
        for dangerous_path in dangerous_paths:
            if target_lower.startswith(
                    dangerous_path) or dangerous_path in target_lower:
                raise SecurityValidationError(
                    f"Target path contains dangerous system directory: {target_base_path}")
