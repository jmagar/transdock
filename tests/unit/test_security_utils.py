"""
Unit Tests for SecurityUtils Module

This module contains comprehensive tests for the SecurityUtils security validation framework.
Tests focus on input validation, command injection prevention, and path traversal protection.
"""

import pytest
from backend.security_utils import SecurityUtils, SecurityValidationError
from tests.fixtures.test_data import SECURITY_TEST_PAYLOADS


class TestSecurityUtils:
    """Test suite for SecurityUtils validation methods."""

    def test_validate_hostname_valid(self):
        """Test hostname validation with valid hostnames."""
        valid_hostnames = [
            "example.com",
            "sub.example.com", 
            "192.168.1.100",
            "localhost",
            "server-01",
            "test.local"
        ]
        
        for hostname in valid_hostnames:
            result = SecurityUtils.validate_hostname(hostname)
            assert result == hostname

    def test_validate_hostname_injection_attempts(self):
        """Test hostname validation against injection attempts."""
        for hostname in SECURITY_TEST_PAYLOADS['hostname_injection']:
            with pytest.raises(SecurityValidationError):
                SecurityUtils.validate_hostname(hostname)

    def test_validate_username_valid(self):
        """Test username validation with valid usernames."""
        valid_usernames = ["root", "admin", "user123", "test-user", "user_name"]
        
        for username in valid_usernames:
            result = SecurityUtils.validate_username(username)
            assert result == username

    def test_validate_username_injection_attempts(self):
        """Test username validation against injection attempts."""
        for username in SECURITY_TEST_PAYLOADS['ssh_injection']:
            with pytest.raises(SecurityValidationError):
                SecurityUtils.validate_username(username)

    def test_validate_port_valid(self):
        """Test port validation with valid ports."""
        valid_ports = [1, 22, 80, 443, 8080, 65535]
        
        for port in valid_ports:
            result = SecurityUtils.validate_port(port)
            assert result == port

    def test_validate_port_invalid(self):
        """Test port validation with invalid ports."""
        invalid_ports = [0, -1, 65536, 99999]
        
        for port in invalid_ports:
            with pytest.raises(SecurityValidationError):
                SecurityUtils.validate_port(port)

    def test_sanitize_path_valid(self):
        """Test path sanitization with valid paths."""
        # Test relative paths (should work without allow_absolute)
        relative_paths = ["relative/path", "data/files", "config"]
        
        for path in relative_paths:
            result = SecurityUtils.sanitize_path(path)
            assert result is not None
            assert ".." not in result
        
        # Test absolute paths (require allow_absolute=True)
        absolute_paths = ["/home/user/docker", "/mnt/cache/compose", "/opt/docker/stacks"]
        
        for path in absolute_paths:
            result = SecurityUtils.sanitize_path(path, allow_absolute=True)
            assert result is not None
            assert ".." not in result

    def test_sanitize_path_traversal_attempts(self):
        """Test path sanitization against traversal attempts."""
        for path in SECURITY_TEST_PAYLOADS['path_traversal']:
            with pytest.raises(SecurityValidationError):
                SecurityUtils.sanitize_path(path)

    def test_sanitize_path_empty(self):
        """Test path sanitization with empty paths."""
        with pytest.raises(SecurityValidationError):
            SecurityUtils.sanitize_path("")

    def test_validate_dataset_name_valid(self):
        """Test dataset name validation with valid names."""
        valid_datasets = [
            "cache/compose",
            "cache/compose/authelia",
            "pool/dataset",
            "tank/backups/daily"
        ]
        
        for dataset in valid_datasets:
            result = SecurityUtils.validate_dataset_name(dataset)
            assert result == dataset

    def test_validate_dataset_name_injection_attempts(self):
        """Test dataset name validation against injection attempts."""
        for dataset in SECURITY_TEST_PAYLOADS['zfs_injection']:
            with pytest.raises(SecurityValidationError):
                SecurityUtils.validate_dataset_name(dataset)

    def test_escape_shell_argument(self):
        """Test shell argument escaping."""
        dangerous_args = [
            "with spaces",
            "with;semicolon",
            "with&ampersand",
            "with|pipe",
            "with$(injection)"
        ]
        
        for arg in dangerous_args:
            result = SecurityUtils.escape_shell_argument(arg)
            assert result is not None
            # Should be properly quoted
            assert result.startswith("'") or "'" in result

    def test_build_ssh_command_valid(self):
        """Test SSH command building with valid parameters."""
        result = SecurityUtils.build_ssh_command(
            hostname="test.example.com",
            username="root", 
            port=22,
            remote_command="ls -la"
        )
        
        assert isinstance(result, list)
        assert "ssh" in result[0]
        assert "test.example.com" in " ".join(result)

    def test_build_ssh_command_injection_prevention(self):
        """Test SSH command building prevents injection attacks."""
        with pytest.raises(SecurityValidationError):
            SecurityUtils.build_ssh_command(
                hostname="host; rm -rf /",
                username="root",
                port=22,
                remote_command="ls"
            )

    def test_validate_zfs_command_args_valid(self):
        """Test ZFS command argument validation with valid commands."""
        result = SecurityUtils.validate_zfs_command_args("list", "cache/compose")
        
        assert isinstance(result, list)
        assert result[0] == "zfs" 
        assert "list" in result

    def test_validate_zfs_command_args_injection_prevention(self):
        """Test ZFS command argument validation prevents injection attacks.""" 
        with pytest.raises(SecurityValidationError):
            SecurityUtils.validate_zfs_command_args("list", "cache; rm -rf /")

    @pytest.mark.security
    def test_comprehensive_injection_prevention(self):
        """Comprehensive test for all injection prevention mechanisms."""
        # Test hostname injection
        for payload in SECURITY_TEST_PAYLOADS['hostname_injection']:
            with pytest.raises(SecurityValidationError):
                SecurityUtils.validate_hostname(payload)
        
        # Test username injection  
        for payload in SECURITY_TEST_PAYLOADS['ssh_injection']:
            with pytest.raises(SecurityValidationError):
                SecurityUtils.validate_username(payload)
                
        # Test path traversal
        for payload in SECURITY_TEST_PAYLOADS['path_traversal']:
            with pytest.raises(SecurityValidationError):
                SecurityUtils.sanitize_path(payload)
                
        # Test dataset injection
        for payload in SECURITY_TEST_PAYLOADS['zfs_injection']:
            with pytest.raises(SecurityValidationError):
                SecurityUtils.validate_dataset_name(payload)

    @pytest.mark.security
    def test_security_validation_error_messages(self):
        """Test that SecurityValidationError contains descriptive messages."""
        test_cases = [
            (SecurityUtils.validate_hostname, "host; inject", "Invalid hostname"),
            (SecurityUtils.validate_username, "user; inject", "Invalid username"),
            (SecurityUtils.validate_port, 65536, "Invalid port number"),
            (SecurityUtils.sanitize_path, "../../../etc/passwd", "Path contains directory traversal"),
        ]
        
        for method, invalid_input, expected_message in test_cases:
            with pytest.raises(SecurityValidationError, match=expected_message):
                method(invalid_input) 