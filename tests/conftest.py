"""
TransDock Test Configuration and Fixtures

This module provides common fixtures and configuration for TransDock tests.
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
import httpx

# Import TransDock modules
from backend.models import MigrationRequest, MigrationStatus, VolumeMount
from backend.migration_service import MigrationService
from backend.zfs_ops import ZFSOperations
from backend.docker_ops import DockerOperations
from backend.transfer_ops import TransferOperations


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_zfs_operations():
    """Mock ZFS operations for testing."""
    mock = Mock(spec=ZFSOperations)
    mock.is_available = AsyncMock(return_value=True)
    mock.is_dataset = AsyncMock(return_value=False)
    mock.create_dataset = AsyncMock(return_value=True)
    mock.create_snapshot = AsyncMock(return_value=True)
    mock.send_snapshot = AsyncMock(return_value=True)
    mock.cleanup_snapshot = AsyncMock(return_value=True)
    mock.get_datasets = AsyncMock(return_value=[])
    mock.run_command = AsyncMock(return_value=(0, "success", ""))
    mock.safe_run_zfs_command = AsyncMock(return_value=(0, "success", ""))
    return mock


@pytest.fixture
def mock_docker_operations():
    """Mock Docker operations for testing."""
    mock = Mock(spec=DockerOperations)
    mock.is_available = AsyncMock(return_value=True)
    mock.parse_compose_file = AsyncMock(return_value={
        'services': {
            'test-service': {
                'image': 'test:latest',
                'volumes': ['./data:/app/data']
            }
        }
    })
    mock.stop_stack = AsyncMock(return_value=True)
    mock.start_stack = AsyncMock(return_value=True)
    mock.update_compose_paths = AsyncMock(return_value=True)
    mock.get_stack_volumes = AsyncMock(return_value=[
        VolumeMount(source="/test/data", target="/app/data", is_dataset=False)
    ])
    return mock


@pytest.fixture
def mock_transfer_operations():
    """Mock Transfer operations for testing."""
    mock = Mock(spec=TransferOperations)
    mock.transfer_via_zfs = AsyncMock(return_value=True)
    mock.transfer_via_rsync = AsyncMock(return_value=True)
    mock.rsync_transfer = AsyncMock(return_value=True)
    mock.write_remote_file = AsyncMock(return_value=True)
    mock.verify_transfer = AsyncMock(return_value=True)
    mock.create_volume_mapping = AsyncMock(return_value={"old": "new"})
    return mock


@pytest.fixture
def mock_migration_service(mock_zfs_operations, mock_docker_operations, mock_transfer_operations):
    """Mock Migration service with all dependencies."""
    mock = Mock(spec=MigrationService)
    mock.zfs_ops = mock_zfs_operations
    mock.docker_ops = mock_docker_operations
    mock.transfer_ops = mock_transfer_operations
    mock.migrations = {}
    mock.start_migration = AsyncMock()
    mock.get_migration_status = Mock()
    mock.list_migrations = Mock(return_value=[])
    return mock


@pytest.fixture
def sample_migration_request():
    """Sample migration request for testing."""
    return MigrationRequest(
        compose_dataset="test-stack",
        target_host="192.168.1.100",
        target_base_path="/home/user/docker",
        ssh_user="root",
        ssh_port=22,
        force_rsync=False
    )


@pytest.fixture
def sample_migration_status():
    """Sample migration status for testing."""
    return MigrationStatus(
        id="test-migration-123",
        status="running",
        progress=50,
        message="Transfer in progress",
        compose_dataset="test-stack",
        target_host="192.168.1.100",
        target_base_path="/home/user/docker",
        snapshots=["test-stack@migration-123"],
        target_compose_path="/home/user/docker/test-stack/docker-compose.yml",
        volume_mapping={"old_path": "new_path"}
    )


@pytest.fixture
def sample_docker_compose():
    """Sample Docker Compose content for testing."""
    return {
        'version': '3.8',
        'services': {
            'web': {
                'image': 'nginx:latest',
                'ports': ['80:80'],
                'volumes': [
                    './data:/usr/share/nginx/html',
                    './config:/etc/nginx/conf.d'
                ]
            },
            'db': {
                'image': 'mysql:8.0',
                'environment': {
                    'MYSQL_ROOT_PASSWORD': 'secret'
                },
                'volumes': [
                    './mysql:/var/lib/mysql'
                ]
            }
        }
    }


@pytest.fixture
def malicious_inputs():
    """Collection of malicious inputs for security testing."""
    return {
        'path_traversal': [
            '../../../etc/passwd',
            '..\\..\\..\\windows\\system32',
            '/etc/passwd',
            '\\..\\..\\..\\etc\\passwd',
            '../etc/passwd',
            '..%2f..%2f..%2fetc%2fpasswd',
            '..%252f..%252f..%252fetc%252fpasswd',
            '..%c0%af..%c0%af..%c0%afetc%c0%afpasswd'
        ],
        'command_injection': [
            '; rm -rf /',
            '`rm -rf /`',
            '$(rm -rf /)',
            '| rm -rf /',
            '&& rm -rf /',
            '|| rm -rf /',
            '; cat /etc/passwd',
            '`cat /etc/passwd`',
            '$(cat /etc/passwd)',
            '| cat /etc/passwd'
        ],
        'zfs_injection': [
            'pool/dataset; rm -rf /',
            'pool/dataset`rm -rf /`',
            'pool/dataset$(rm -rf /)',
            'pool/dataset | rm -rf /',
            'pool/dataset && rm -rf /',
            'pool/dataset; zfs destroy -r pool',
            'pool/dataset`zfs destroy -r pool`'
        ],
        'ssh_injection': [
            'user; rm -rf /',
            'user`rm -rf /`',
            'user$(rm -rf /)',
            'user | rm -rf /',
            'user && rm -rf /',
            'user; cat /etc/passwd',
            'user`cat /etc/passwd`'
        ],
        'hostname_injection': [
            'host; rm -rf /',
            'host`rm -rf /`',
            'host$(rm -rf /)',
            'host | rm -rf /',
            'host && rm -rf /',
            'host.example.com; cat /etc/passwd',
            'host.example.com`cat /etc/passwd`'
        ]
    }


@pytest.fixture
def test_client():
    """Create test client for FastAPI application."""
    # Import here to avoid circular imports
    from backend.main import app
    return TestClient(app)


@pytest.fixture
async def async_client():
    """Create async test client for FastAPI application."""
    from backend.main import app
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_subprocess():
    """Mock subprocess operations for testing."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=0,
            stdout="success",
            stderr="",
            decode=Mock(return_value="success")
        )
        yield mock_run


@pytest.fixture
def mock_ssh_client():
    """Mock SSH client for testing."""
    with patch('paramiko.SSHClient') as mock_client:
        mock_instance = Mock()
        mock_client.return_value = mock_instance
        mock_instance.connect = Mock()
        mock_instance.exec_command = Mock(return_value=(Mock(), Mock(), Mock()))
        mock_instance.close = Mock()
        yield mock_instance


@pytest.fixture
def mock_file_operations():
    """Mock file operations for testing."""
    with patch('builtins.open', create=True) as mock_open, \
         patch('os.path.exists') as mock_exists, \
         patch('os.makedirs') as mock_makedirs, \
         patch('shutil.copy2') as mock_copy:
        
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = "test content"
        mock_open.return_value.__enter__.return_value.write.return_value = None
        
        yield {
            'open': mock_open,
            'exists': mock_exists,
            'makedirs': mock_makedirs,
            'copy': mock_copy
        }


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Automatically set up test environment for all tests."""
    # Set test environment variables
    os.environ['TRANSDOCK_TEST_MODE'] = 'true'
    os.environ['TRANSDOCK_COMPOSE_BASE'] = '/tmp/test/compose'
    os.environ['TRANSDOCK_APPDATA_BASE'] = '/tmp/test/appdata'
    os.environ['TRANSDOCK_ZFS_POOL'] = 'test-pool'
    
    yield
    
    # Clean up test environment
    test_vars = [
        'TRANSDOCK_TEST_MODE',
        'TRANSDOCK_COMPOSE_BASE', 
        'TRANSDOCK_APPDATA_BASE',
        'TRANSDOCK_ZFS_POOL'
    ]
    for var in test_vars:
        if var in os.environ:
            del os.environ[var]


@pytest.fixture
def security_test_context():
    """Security testing context with validation tracking."""
    return {
        'validation_attempts': [],
        'security_exceptions': [],
        'command_executions': [],
        'file_operations': []
    } 