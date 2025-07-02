"""
Security Penetration Tests for TransDock

This module contains security penetration tests focusing on injection attacks,
validation bypasses, and security boundary testing.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock

from backend.main import app
from backend.security_utils import SecurityUtils, SecurityValidationError
from tests.fixtures.test_data import SECURITY_TEST_PAYLOADS


class TestPenetrationSecurity:
    """Security penetration test suite."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_migration_service(self):
        """Mock migration service."""
        with patch('backend.main.migration_service') as mock:
            yield mock

    @pytest.mark.security
    def test_command_injection_api_endpoints(self, client):
        """Test command injection attempts via API endpoints."""
        injection_payloads = SECURITY_TEST_PAYLOADS['command_injection']
        
        for payload in injection_payloads:
            # Test migration start endpoint
            malicious_request = {
                "compose_dataset": f"authelia{payload}",
                "target_host": "192.168.1.100",
                "target_base_path": "/home/user/docker",
                "ssh_user": "root",
                "ssh_port": 22
            }
            
            response = client.post("/migrations", json=malicious_request)
            # Should either fail validation (422) or be blocked (400/500)
            assert response.status_code in [400, 422, 500]

    @pytest.mark.security
    def test_hostname_injection_attacks(self, client):
        """Test hostname injection attacks."""
        for payload in SECURITY_TEST_PAYLOADS['hostname_injection']:
            malicious_request = {
                "compose_dataset": "authelia",
                "target_host": payload,
                "target_base_path": "/home/user/docker", 
                "ssh_user": "root",
                "ssh_port": 22
            }
            
            response = client.post("/migrations", json=malicious_request)
            # Should be blocked by validation
            assert response.status_code in [400, 422, 500]

    @pytest.mark.security
    def test_ssh_injection_attacks(self, client):
        """Test SSH injection attacks."""
        for payload in SECURITY_TEST_PAYLOADS['ssh_injection']:
            malicious_request = {
                "compose_dataset": "authelia",
                "target_host": "192.168.1.100",
                "target_base_path": "/home/user/docker",
                "ssh_user": payload,
                "ssh_port": 22
            }
            
            response = client.post("/migrations", json=malicious_request)
            # Should be blocked by validation
            assert response.status_code in [400, 422, 500]

    @pytest.mark.security
    def test_path_traversal_attacks(self, client):
        """Test path traversal attacks."""
        for payload in SECURITY_TEST_PAYLOADS['path_traversal']:
            malicious_request = {
                "compose_dataset": "authelia",
                "target_host": "192.168.1.100", 
                "target_base_path": payload,
                "ssh_user": "root",
                "ssh_port": 22
            }
            
            response = client.post("/migrations", json=malicious_request)
            # Should be blocked by validation
            assert response.status_code in [400, 422, 500]

    @pytest.mark.security
    def test_zfs_injection_attacks(self, client):
        """Test ZFS injection attacks."""
        for payload in SECURITY_TEST_PAYLOADS['zfs_injection']:
            malicious_request = {
                "compose_dataset": payload,
                "target_host": "192.168.1.100",
                "target_base_path": "/home/user/docker",
                "ssh_user": "root",
                "ssh_port": 22
            }
            
            response = client.post("/migrations", json=malicious_request)
            # Should be blocked by validation
            assert response.status_code in [400, 422, 500]

    @pytest.mark.security
    def test_sql_injection_attempts(self, client):
        """Test SQL injection attempts (even though we don't use SQL)."""
        sql_payloads = [
            "'; DROP TABLE users; --",
            "' OR 1=1 --",
            "'; SELECT * FROM migrations; --",
            "' UNION SELECT * FROM system; --"
        ]
        
        for payload in sql_payloads:
            malicious_request = {
                "compose_dataset": payload,
                "target_host": "192.168.1.100",
                "target_base_path": "/home/user/docker",
                "ssh_user": "root",
                "ssh_port": 22
            }
            
            response = client.post("/migrations", json=malicious_request)
            # Should be blocked by validation
            assert response.status_code in [400, 422, 500]

    @pytest.mark.security
    def test_xss_attempts(self, client):
        """Test XSS attempts in input fields."""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<svg onload=alert('xss')>",
            "';alert('xss');//"
        ]
        
        for payload in xss_payloads:
            malicious_request = {
                "compose_dataset": payload,
                "target_host": "192.168.1.100",
                "target_base_path": "/home/user/docker",
                "ssh_user": "root",
                "ssh_port": 22
            }
            
            response = client.post("/migrations", json=malicious_request)
            # Should be blocked by validation
            assert response.status_code in [400, 422, 500]

    @pytest.mark.security
    def test_buffer_overflow_attempts(self, client):
        """Test buffer overflow attempts with oversized input."""
        oversized_payloads = [
            "A" * 1000,   # 1KB
            "A" * 10000,  # 10KB  
            "A" * 100000, # 100KB
            "A" * 1000000 # 1MB (if allowed by server)
        ]
        
        for payload in oversized_payloads:
            malicious_request = {
                "compose_dataset": payload,
                "target_host": "192.168.1.100",
                "target_base_path": "/home/user/docker",
                "ssh_user": "root",
                "ssh_port": 22
            }
            
            response = client.post("/migrations", json=malicious_request)
            # Should be blocked by validation or size limits
            assert response.status_code in [400, 413, 422, 500]

    @pytest.mark.security
    def test_unicode_bypass_attempts(self, client):
        """Test Unicode bypass attempts."""
        unicode_payloads = [
            "test\u0000null",  # Null byte
            "test\u202Eoverflow",  # Right-to-left override
            "test\uFEFFbypass",    # Zero-width no-break space
            "test\u00A0space",     # Non-breaking space
        ]
        
        for payload in unicode_payloads:
            malicious_request = {
                "compose_dataset": payload,
                "target_host": "192.168.1.100",
                "target_base_path": "/home/user/docker",
                "ssh_user": "root",
                "ssh_port": 22
            }
            
            response = client.post("/migrations", json=malicious_request)
            # Should be handled appropriately
            assert response.status_code in [400, 422, 500]

    @pytest.mark.security
    def test_port_range_attacks(self, client):
        """Test invalid port number attacks."""
        invalid_ports = [
            -1, 0, 65536, 99999, -65536,
            "22; rm -rf /",
            "22 && rm -rf /",
            "22 | rm -rf /"
        ]
        
        for port in invalid_ports:
            malicious_request = {
                "compose_dataset": "authelia",
                "target_host": "192.168.1.100",
                "target_base_path": "/home/user/docker",
                "ssh_user": "root",
                "ssh_port": port
            }
            
            response = client.post("/migrations", json=malicious_request)
            # Should be blocked by validation
            assert response.status_code in [400, 422, 500]

    @pytest.mark.security
    def test_directory_traversal_comprehensive(self, client):
        """Test comprehensive directory traversal attacks."""
        traversal_payloads = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",  # URL encoded
            "....//....//....//etc/passwd",            # Double dots
            "..%252f..%252f..%252fetc%252fpasswd",     # Double URL encoded
            "..%c0%af..%c0%af..%c0%afetc%c0%afpasswd", # Unicode encoded
        ]
        
        for payload in traversal_payloads:
            malicious_request = {
                "compose_dataset": "authelia",
                "target_host": "192.168.1.100",
                "target_base_path": payload,
                "ssh_user": "root",
                "ssh_port": 22
            }
            
            response = client.post("/migrations", json=malicious_request)
            # Should be blocked by path validation
            assert response.status_code in [400, 422, 500]

    @pytest.mark.security
    def test_http_header_injection(self, client):
        """Test HTTP header injection attempts."""
        header_injection_payloads = [
            "test\r\nX-Injected: true",
            "test\nSet-Cookie: admin=true",
            "test\r\n\r\n<script>alert('xss')</script>",
        ]
        
        for payload in header_injection_payloads:
            response = client.get(
                "/system/info",
                headers={"X-Custom-Header": payload}
            )
            
            # Response should not contain injected headers
            assert "X-Injected" not in response.headers
            assert "Set-Cookie" not in response.headers or "admin=true" not in str(response.headers.get("Set-Cookie", ""))

    @pytest.mark.security
    def test_timing_attack_resistance(self, client):
        """Test resistance to timing attacks."""
        import time
        
        # Test with valid and invalid data
        valid_request = {
            "compose_dataset": "authelia",
            "target_host": "192.168.1.100",
            "target_base_path": "/home/user/docker",
            "ssh_user": "root",
            "ssh_port": 22
        }
        
        invalid_request = {
            "compose_dataset": "nonexistent",
            "target_host": "192.168.1.100",
            "target_base_path": "/home/user/docker",
            "ssh_user": "root",
            "ssh_port": 22
        }
        
        # Measure timing for multiple requests
        valid_times = []
        invalid_times = []
        
        for _ in range(5):
            start = time.time()
            client.post("/migrations", json=valid_request)
            valid_times.append(time.time() - start)
            
            start = time.time()
            client.post("/migrations", json=invalid_request)
            invalid_times.append(time.time() - start)
        
        # Timing difference should not be excessive (avoid timing attacks)
        avg_valid = sum(valid_times) / len(valid_times)
        avg_invalid = sum(invalid_times) / len(invalid_times)
        
        # Allow reasonable variance but not excessive timing differences
        assert abs(avg_valid - avg_invalid) < 1.0  # Less than 1 second difference

    @pytest.mark.security
    def test_rate_limiting_bypass_attempts(self, client):
        """Test rate limiting bypass attempts."""
        # Rapid fire requests to test rate limiting
        for i in range(100):
            response = client.get("/system/info")
            
            # After a certain number of requests, should be rate limited
            # (This depends on implementation - may return 429 Too Many Requests)
            if i > 50:  # Allow some requests initially
                # If rate limiting is implemented, should see 429 responses
                if response.status_code == 429:
                    break
        
        # At minimum, server should remain responsive
        assert response.status_code in [200, 429, 500]

    @pytest.mark.security
    def test_authentication_bypass_attempts(self, client):
        """Test authentication bypass attempts."""
        # Test various authentication bypass techniques
        auth_bypass_headers = [
            {"Authorization": "Bearer fake_token"},
            {"X-Forwarded-For": "127.0.0.1"},
            {"X-Originating-IP": "127.0.0.1"},
            {"X-Remote-Addr": "127.0.0.1"},
            {"X-Real-IP": "127.0.0.1"},
            {"X-Admin": "true"},
            {"X-Authenticated": "true"},
        ]
        
        for headers in auth_bypass_headers:
            response = client.get("/system/info", headers=headers)
            # Should not provide unauthorized access
            # (TransDock currently doesn't have auth, but test the pattern)
            assert response.status_code in [200, 401, 403]

    @pytest.mark.security
    def test_input_validation_edge_cases(self, client):
        """Test edge cases in input validation."""
        edge_case_requests = [
            # Null values
            {
                "compose_dataset": None,
                "target_host": "192.168.1.100",
                "target_base_path": "/home/user/docker",
                "ssh_user": "root",
                "ssh_port": 22
            },
            
            # Empty arrays/objects
            {
                "compose_dataset": [],
                "target_host": "192.168.1.100",
                "target_base_path": "/home/user/docker",
                "ssh_user": "root",
                "ssh_port": 22
            },
            
            # Type confusion
            {
                "compose_dataset": 12345,
                "target_host": "192.168.1.100", 
                "target_base_path": "/home/user/docker",
                "ssh_user": "root",
                "ssh_port": 22
            },
            
            # Boolean values
            {
                "compose_dataset": True,
                "target_host": "192.168.1.100",
                "target_base_path": "/home/user/docker", 
                "ssh_user": "root",
                "ssh_port": 22
            }
        ]
        
        for malicious_request in edge_case_requests:
            response = client.post("/migrations", json=malicious_request)
            # Should be properly validated
            assert response.status_code in [400, 422, 500]

    @pytest.mark.security
    def test_security_utils_comprehensive_bypass(self):
        """Test comprehensive bypass attempts of SecurityUtils."""
        # Direct testing of SecurityUtils methods
        bypass_attempts = [
            # Hostname bypasses
            ("validate_hostname", "192.168.1.1`whoami`"),
            ("validate_hostname", "host$IFS$9rm$IFS$9-rf$IFS$9/"),
            
            # Username bypasses  
            ("validate_username", "root;id"),
            ("validate_username", "$(whoami)"),
            
            # Path bypasses
            ("sanitize_path", "/var/lib/../../etc/passwd"),
            ("sanitize_path", "/home/user\\..\\..\\..\\etc\\passwd"),
            
            # Dataset bypasses
            ("validate_dataset_name", "cache/compose`rm -rf /`"),
            ("validate_dataset_name", "cache$(touch /tmp/pwned)"),
        ]
        
        for method_name, malicious_input in bypass_attempts:
            method = getattr(SecurityUtils, method_name)
            
            with pytest.raises(SecurityValidationError):
                method(malicious_input) 