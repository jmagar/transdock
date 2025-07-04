# TransDock Testing Guide

This comprehensive guide covers how to use the entire TransDock testing infrastructure, including unit tests, integration tests, security tests, and all testing utilities.

## Table of Contents

1. [Test Structure Overview](#test-structure-overview)
2. [Prerequisites](#prerequisites)
3. [Running Tests](#running-tests)
4. [Test Categories](#test-categories)
5. [Test Fixtures and Mocks](#test-fixtures-and-mocks)
6. [Coverage Reports](#coverage-reports)
7. [Adding New Tests](#adding-new-tests)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

## Test Structure Overview

```text
tests/
├── __init__.py
├── conftest.py                 # Common fixtures and test configuration
├── fixtures/
│   ├── __init__.py
│   └── test_data.py           # Sample data, mock responses, security payloads
├── unit/                      # Unit tests for individual modules
│   ├── __init__.py
│   ├── test_security_utils.py # SecurityUtils validation tests
│   ├── test_zfs_ops.py        # ZFS operations tests (mocked)
│   ├── test_docker_ops.py     # Docker operations tests (mocked)
│   └── test_transfer_ops.py   # Transfer operations tests (mocked)
├── integration/               # API and workflow integration tests
│   ├── __init__.py
│   ├── test_api_endpoints.py  # FastAPI endpoint tests
│   └── test_migration_workflow.py # End-to-end workflow tests
└── security/                  # Security and penetration tests
    ├── __init__.py
    └── test_penetration.py    # Comprehensive security validation
```

## Prerequisites

### Install Dependencies
```bash
# Install testing dependencies (should already be in pyproject.toml)
uv add --dev pytest pytest-asyncio httpx pytest-mock pytest-cov
```

### Dependencies Included:
- **pytest**: Core testing framework
- **pytest-asyncio**: Async test support
- **httpx**: HTTP client for API testing
- **pytest-mock**: Advanced mocking capabilities
- **pytest-cov**: Coverage reporting

## Running Tests

### Quick Start Commands

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test categories
uv run pytest tests/unit/          # Unit tests only
uv run pytest tests/integration/   # Integration tests only
uv run pytest tests/security/      # Security tests only

# Run specific test files
uv run pytest tests/unit/test_security_utils.py
uv run pytest tests/security/test_penetration.py

# Run specific test methods
uv run pytest tests/unit/test_security_utils.py::TestSecurityUtils::test_hostname_validation
```

### Test Markers

Use markers to run specific types of tests:

```bash
# Run by test markers (when pytest.ini is working)
pytest -m unit          # Unit tests
pytest -m integration   # Integration tests  
pytest -m security      # Security tests
pytest -m slow          # Tests that take longer
pytest -m network       # Tests requiring network
pytest -m zfs           # Tests requiring ZFS
pytest -m docker        # Tests requiring Docker
```

### Coverage Reports

```bash
# Run tests with coverage
uv run pytest --cov=backend --cov-report=term-missing

# Generate HTML coverage report
uv run pytest --cov=backend --cov-report=html:htmlcov
# View report: open htmlcov/index.html

# Coverage with specific threshold
uv run pytest --cov=backend --cov-fail-under=80
```

## Test Categories

### 1. Unit Tests (`tests/unit/`)

**Purpose**: Test individual modules in isolation with mocked dependencies.

#### SecurityUtils Tests (`test_security_utils.py`)
```bash
# Run all security utils tests
uv run pytest tests/unit/test_security_utils.py -v

# Test specific validation functions
uv run pytest tests/unit/test_security_utils.py::TestSecurityUtils::test_hostname_validation
uv run pytest tests/unit/test_security_utils.py::TestSecurityUtils::test_path_sanitization
```

**What it tests**:
- Hostname validation with malicious input detection
- Username and port validation
- Path sanitization and traversal prevention
- ZFS dataset name validation
- Command argument escaping
- Migration request validation

#### ZFS Operations Tests (`test_zfs_ops.py`)
```bash
# Run ZFS operation tests
uv run pytest tests/unit/test_zfs_ops.py -v
```

**What it tests**:
- ZFS availability detection
- Dataset operations (create, destroy, snapshot)
- ZFS send/receive operations
- Error handling for ZFS commands
- Concurrent ZFS operations

#### Docker Operations Tests (`test_docker_ops.py`)
```bash
# Run Docker operation tests
uv run pytest tests/unit/test_docker_ops.py -v
```

**What it tests**:
- Compose file parsing
- Volume mount extraction
- Docker stack operations
- Service management
- Path remapping logic

#### Transfer Operations Tests (`test_transfer_ops.py`)
```bash
# Run transfer operation tests
uv run pytest tests/unit/test_transfer_ops.py -v
```

**What it tests**:
- ZFS send/receive transfers
- Rsync fallback operations
- SSH connection handling
- Progress tracking
- Transfer method selection

### 2. Integration Tests (`tests/integration/`)

**Purpose**: Test API endpoints and complete workflows with realistic scenarios.

#### API Endpoints Tests (`test_api_endpoints.py`)
```bash
# Run API endpoint tests
uv run pytest tests/integration/test_api_endpoints.py -v

# Test specific endpoints
uv run pytest tests/integration/test_api_endpoints.py::TestAPIEndpoints::test_create_migration
uv run pytest tests/integration/test_api_endpoints.py::TestAPIEndpoints::test_system_info
```

**What it tests**:
- `/migrations` POST endpoint (migration creation)
- `/migrations` GET endpoint (list migrations)
- `/migrations/{id}` GET endpoint (migration status)
- `/health` endpoint
- `/system/info` endpoint
- `/zfs/status` endpoint
- `/datasets` endpoint
- `/compose/stacks` endpoint
- Error handling and status codes

#### Migration Workflow Tests (`test_migration_workflow.py`)
```bash
# Run workflow tests
uv run pytest tests/integration/test_migration_workflow.py -v
```

**What it tests**:
- Complete migration workflows
- Error scenarios and recovery
- Migration cancellation
- Concurrent migration handling
- Progress tracking through full workflow

### 3. Security Tests (`tests/security/`)

**Purpose**: Validate security measures against various attack vectors.

#### Penetration Tests (`test_penetration.py`)
```bash
# Run all security tests
uv run pytest tests/security/test_penetration.py -v

# Run specific security test categories
uv run pytest tests/security/test_penetration.py::TestPenetrationSecurity::test_command_injection_api_endpoints
uv run pytest tests/security/test_penetration.py::TestPenetrationSecurity::test_path_traversal_attacks
```

**Security Test Coverage** (All 17 tests):
1. **Command injection** - API endpoints with malicious commands
2. **Hostname injection** - Malicious hostnames in requests
3. **SSH injection** - SSH parameter injection attempts
4. **Path traversal** - Directory traversal attacks
5. **ZFS injection** - ZFS command injection
6. **SQL injection** - SQL injection attempts
7. **XSS attempts** - Cross-site scripting prevention
8. **Buffer overflow** - Large input handling
9. **Unicode bypass** - Unicode-based bypass attempts
10. **Port range attacks** - Invalid port numbers
11. **Directory traversal comprehensive** - Advanced path traversal
12. **HTTP header injection** - Header manipulation
13. **Timing attack resistance** - Timing-based attacks
14. **Rate limiting bypass** - Rate limit circumvention
15. **Authentication bypass** - Authentication circumvention
16. **Input validation edge cases** - Edge case validation
17. **SecurityUtils comprehensive** - Complete SecurityUtils testing

## Test Fixtures and Mocks

### Available Fixtures (`tests/conftest.py`)

```python
# Common fixtures available in all tests
def test_client():          # FastAPI test client
def mock_zfs_ops():         # Mocked ZFS operations
def mock_docker_ops():      # Mocked Docker operations  
def mock_transfer_ops():    # Mocked transfer operations
def mock_migration_service(): # Mocked migration service
def sample_migration_request(): # Sample migration data
```

### Test Data (`tests/fixtures/test_data.py`)

**Available Test Data**:
```python
# Docker Compose configurations
DOCKER_COMPOSE_AUTHELIA     # Sample Authelia stack
DOCKER_COMPOSE_WORDPRESS    # Sample WordPress stack
DOCKER_COMPOSE_COMPLEX      # Complex multi-service stack

# Migration requests and responses
MIGRATION_REQUEST_VALID     # Valid migration request
MIGRATION_STATUS_RUNNING    # Running migration status
MIGRATION_STATUS_COMPLETED  # Completed migration status

# Security test payloads
SECURITY_TEST_PAYLOADS = {
    'command_injection': [...],
    'path_traversal': [...],
    'zfs_injection': [...],
    'ssh_injection': [...],
    'hostname_injection': [...]
}

# Mock command outputs
MOCK_COMMAND_OUTPUTS = {
    'zfs_list': "...",
    'docker_version': "...",
    'ssh_test': "..."
}
```

### Using Fixtures in Tests

```python
import pytest
from tests.fixtures.test_data import DOCKER_COMPOSE_AUTHELIA

def test_compose_parsing(mock_docker_ops):
    """Example of using fixtures in tests."""
    # Use mocked operations
    result = mock_docker_ops.parse_compose_file('/path/to/compose.yml')
    
    # Use test data
    assert result == DOCKER_COMPOSE_AUTHELIA

def test_api_endpoint(test_client, sample_migration_request):
    """Example of testing API endpoints."""
    response = test_client.post("/migrations", json=sample_migration_request)
    assert response.status_code == 200
```

## Coverage Reports

### Generating Coverage Reports

```bash
# Terminal coverage report
uv run pytest --cov=backend --cov-report=term-missing

# HTML coverage report
uv run pytest --cov=backend --cov-report=html:htmlcov

# XML coverage report (for CI/CD)
uv run pytest --cov=backend --cov-report=xml

# Combined coverage report
uv run pytest --cov=backend --cov-report=term-missing --cov-report=html:htmlcov
```

### Coverage Thresholds

The project is configured with an 80% coverage threshold:
```bash
# Fail if coverage is below 80%
uv run pytest --cov=backend --cov-fail-under=80
```

### Viewing HTML Coverage

```bash
# Generate and view HTML coverage
uv run pytest --cov=backend --cov-report=html:htmlcov
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Adding New Tests

### Creating Unit Tests

```python
# tests/unit/test_new_module.py
import pytest
from unittest.mock import Mock, patch
from backend.new_module import NewModule

class TestNewModule:
    """Test the NewModule class."""
    
    def test_basic_functionality(self):
        """Test basic functionality."""
        module = NewModule()
        result = module.some_method()
        assert result is not None
    
    @patch('backend.new_module.external_dependency')
    def test_with_mocked_dependency(self, mock_dependency):
        """Test with mocked external dependency."""
        mock_dependency.return_value = "mocked_result"
        
        module = NewModule()
        result = module.method_using_dependency()
        
        assert result == "expected_result"
        mock_dependency.assert_called_once()
```

### Creating Integration Tests

```python
# tests/integration/test_new_endpoint.py
import pytest
from fastapi.testclient import TestClient
from backend.main import app

class TestNewEndpoint:
    """Test the new API endpoint."""
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_new_endpoint_success(self, client):
        """Test successful API call."""
        response = client.post("/new-endpoint", json={"key": "value"})
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    
    def test_new_endpoint_validation_error(self, client):
        """Test validation error handling."""
        response = client.post("/new-endpoint", json={"invalid": "data"})
        assert response.status_code == 422
```

### Creating Security Tests

```python
# Add to tests/security/test_penetration.py
@pytest.mark.security
def test_new_security_validation(self, client):
    """Test new security validation."""
    malicious_payloads = [
        "malicious_input_1",
        "malicious_input_2"
    ]
    
    for payload in malicious_payloads:
        response = client.post("/endpoint", json={"field": payload})
        # Should be rejected by security validation
        assert response.status_code in [400, 422, 500]
```

## Best Practices

### 1. Test Organization

- **Group related tests** in classes
- **Use descriptive test names** that explain what is being tested
- **Follow the AAA pattern** (Arrange, Act, Assert)

```python
def test_hostname_validation_rejects_malicious_input():
    """Test that hostname validation rejects malicious command injection."""
    # Arrange
    malicious_hostname = "host.com; rm -rf /"
    
    # Act & Assert
    with pytest.raises(SecurityValidationError):
        SecurityUtils.validate_hostname(malicious_hostname)
```

### 2. Mocking Best Practices

- **Mock external dependencies** (file system, network, databases)
- **Don't mock the code under test**
- **Use specific assertions** on mock calls

```python
@patch('backend.zfs_ops.subprocess.run')
def test_zfs_operation(self, mock_subprocess):
    """Test ZFS operation with mocked subprocess."""
    # Setup mock
    mock_subprocess.return_value.returncode = 0
    mock_subprocess.return_value.stdout = "success"
    
    # Test the operation
    result = zfs_ops.create_snapshot("pool/dataset")
    
    # Verify mock was called correctly
    mock_subprocess.assert_called_once_with(
        ["zfs", "snapshot", "pool/dataset@snapshot"],
        capture_output=True,
        text=True
    )
```

### 3. Async Testing

- **Use pytest-asyncio** for async tests
- **Mark async tests** with `@pytest.mark.asyncio`

```python
@pytest.mark.asyncio
async def test_async_migration_workflow():
    """Test async migration workflow."""
    migration_service = MigrationService()
    result = await migration_service.start_migration(request)
    assert result is not None
```

### 4. Security Testing Guidelines

- **Test all input validation** with malicious inputs
- **Include edge cases** and boundary conditions
- **Test encoding bypasses** (URL encoding, Unicode)
- **Verify error messages** don't leak sensitive information

### 5. Performance Testing

```python
import time

def test_operation_performance():
    """Test that operation completes within acceptable time."""
    start_time = time.time()
    
    # Perform operation
    result = some_operation()
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    assert execution_time < 1.0  # Should complete within 1 second
    assert result is not None
```

## Troubleshooting

### Common Issues

#### 1. Import Errors
```bash
# If you get import errors, make sure you're in the project root
cd /path/to/transdock

# Run tests from project root
uv run pytest tests/
```

#### 2. Async Test Issues
```bash
# If async tests fail, ensure pytest-asyncio is installed
uv add --dev pytest-asyncio

# Make sure async tests are marked properly
@pytest.mark.asyncio
async def test_async_function():
    ...
```

#### 3. Mock Issues
```bash
# If mocks aren't working, check the import path
# Wrong:
@patch('tests.unit.test_module.some_function')

# Correct:
@patch('backend.module.some_function')
```

#### 4. Coverage Issues
```bash
# If coverage is low, check what's not covered
uv run pytest --cov=backend --cov-report=term-missing

# Focus on specific modules
uv run pytest --cov=backend.security_utils --cov-report=term-missing
```

### Running Tests in CI/CD

```bash
# Recommended CI/CD test command
uv run pytest \
    --cov=backend \
    --cov-report=xml \
    --cov-report=term \
    --cov-fail-under=80 \
    -v
```

### Debug Mode

```bash
# Run tests with debug output
uv run pytest -v -s --tb=long

# Run single test with maximum output
uv run pytest tests/unit/test_security_utils.py::TestSecurityUtils::test_hostname_validation -v -s --tb=long
```

## Test Results Interpretation

### Successful Test Output
```bash
================================ test session starts =================================
collected 17 items

tests/security/test_penetration.py::TestPenetrationSecurity::test_command_injection_api_endpoints PASSED [  5%]
...
========================== 17 passed, 0 failed, 17 warnings in 4.68s ===============

# ✅ All tests passed - security measures working correctly
```

### Failed Test Output
```bash
FAILED tests/security/test_penetration.py::TestPenetrationSecurity::test_path_traversal_attacks - assert 200 in [400, 422, 500]

# ❌ Security test failed - path traversal attack was not blocked
# This indicates a security vulnerability that needs to be fixed
```

### Coverage Report Example
```bash
Name                     Stmts   Miss  Cover   Missing
------------------------------------------------------
backend/main.py            150     10    93%   45-48, 67-70
backend/security_utils.py  200      5    97%   123, 156-159
backend/zfs_ops.py         180     25    86%   67-70, 89-95, 120-135
------------------------------------------------------
TOTAL                      530     40    92%
```

This comprehensive testing guide ensures you can effectively use all aspects of the TransDock testing infrastructure for maintaining high code quality and security standards. 