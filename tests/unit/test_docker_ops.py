"""
Unit Tests for Docker Operations Module (v2)

This module contains updated tests for Docker operations with mocked system calls,
aligned with the refactored DockerOperations class.
"""

import pytest
import yaml
from unittest.mock import patch, mock_open
from backend.docker_ops import DockerOperations
from tests.fixtures.test_data import (
    DOCKER_COMPOSE_AUTHELIA, 
)

# New test data with absolute paths for volume tests
DOCKER_COMPOSE_ABSOLUTE_PATHS = {
    'version': '3.8',
    'services': {
        'web': {
            'image': 'nginx:latest',
            'volumes': ['/mnt/cache/appdata/nginx_app:/usr/share/nginx/html']
        },
        'db': {
            'image': 'postgres:latest',
            'volumes': ['/mnt/cache/appdata/postgres_data:/var/lib/postgresql/data']
        }
    }
}

@pytest.fixture
def docker_ops():
    """Create a DockerOperations instance for testing."""
    return DockerOperations()

@pytest.mark.asyncio
async def test_run_command_success(docker_ops, mocker):
    """Test successful command execution."""
    mock_process = mocker.AsyncMock()
    mock_process.communicate.return_value = (b'stdout', b'stderr')
    mock_process.returncode = 0
    
    mocker.patch('asyncio.create_subprocess_exec', return_value=mock_process)

    returncode, stdout, stderr = await docker_ops.run_command(["echo", "hello"])

    assert returncode == 0
    assert stdout == "stdout"
    assert stderr == "stderr"

def test_get_compose_path(docker_ops):
    """Test compose path resolution."""
    assert docker_ops.get_compose_path("authelia") == "/mnt/cache/compose/authelia"
    assert docker_ops.get_compose_path("/custom/path") == "/custom/path"
    assert docker_ops.get_compose_path("cache/custom") == "/mnt/cache/custom"

@pytest.mark.asyncio
async def test_find_compose_file(docker_ops, mocker):
    """Test finding various compose file names."""
    mocker.patch('os.path.exists', side_effect=lambda p: p == '/fake/dir/docker-compose.yml')
    result = await docker_ops.find_compose_file("/fake/dir")
    assert result == "/fake/dir/docker-compose.yml"

@pytest.mark.asyncio
async def test_find_compose_file_yaml(docker_ops, mocker):
    """Test finding compose.yaml."""
    mocker.patch('os.path.exists', side_effect=lambda p: p == '/fake/dir/compose.yaml')
    result = await docker_ops.find_compose_file("/fake/dir")
    assert result == "/fake/dir/compose.yaml"

@pytest.mark.asyncio
async def test_find_compose_file_not_found(docker_ops, mocker):
    """Test not finding a compose file."""
    mocker.patch('os.path.exists', return_value=False)
    result = await docker_ops.find_compose_file("/fake/dir")
    assert result is None

@pytest.mark.asyncio
async def test_parse_compose_file(docker_ops):
    """Test parsing a valid compose file."""
    compose_content = yaml.dump(DOCKER_COMPOSE_AUTHELIA)
    with patch("builtins.open", mock_open(read_data=compose_content)):
        result = await docker_ops.parse_compose_file("fake_path.yml")
        assert result['services']['authelia']['image'] == DOCKER_COMPOSE_AUTHELIA['services']['authelia']['image']

@pytest.mark.asyncio
async def test_extract_volume_mounts(docker_ops):
    """Test extracting volume mounts from compose data."""
    # Using test data with absolute paths
    mounts = await docker_ops.extract_volume_mounts(DOCKER_COMPOSE_ABSOLUTE_PATHS)
    assert len(mounts) == 2
    
    sources = {m.source for m in mounts}
    assert "/mnt/cache/appdata/nginx_app" in sources
    assert "/mnt/cache/appdata/postgres_data" in sources

@pytest.mark.asyncio
async def test_stop_compose_stack_success(docker_ops):
    """Test successful stopping of a compose stack."""
    with patch.object(docker_ops, 'find_compose_file', return_value="/fake/docker-compose.yml"), \
         patch.object(docker_ops, 'run_command', return_value=(0, "stopped", "")):
        result = await docker_ops.stop_compose_stack("/fake/dir")
        assert result is True

@pytest.mark.asyncio
async def test_start_compose_stack_success(docker_ops):
    """Test successful starting of a compose stack."""
    with patch.object(docker_ops, 'find_compose_file', return_value="/fake/docker-compose.yml"), \
         patch.object(docker_ops, 'run_command', return_value=(0, "started", "")):
        result = await docker_ops.start_compose_stack("/fake/dir")
        assert result is True

@pytest.mark.asyncio
async def test_update_compose_file_paths(docker_ops):
    """Test updating paths directly in the compose file."""
    compose_content = "    - /mnt/cache/appdata/old_path:/data"
    volume_mapping = {"/mnt/cache/appdata/old_path": "/mnt/cache/appdata/new_path"}

    with patch("builtins.open", mock_open(read_data=compose_content)) as m_open, \
         patch("os.path.exists", return_value=True):
        
        result = await docker_ops.update_compose_file_paths("fake_path.yml", volume_mapping)
        assert result is True
        
        # Check that the file was written with the new path
        handle = m_open()
        written_content = handle.write.call_args[0][0]
        assert "/mnt/cache/appdata/new_path" in written_content

@pytest.mark.asyncio
async def test_create_target_compose_dir(docker_ops):
    """Test creating a directory on the target host."""
    with patch.object(docker_ops, 'run_command', return_value=(0, "", "")):
        result = await docker_ops.create_target_compose_dir("host", "/path")
        assert result is True

@pytest.mark.asyncio
async def test_copy_compose_files(docker_ops):
    """Test copying compose files to the target host."""
    with patch.object(docker_ops, 'run_command', return_value=(0, "copied", "")):
        result = await docker_ops.copy_compose_files("/source", "host", "/target")
        assert result is True

@pytest.mark.asyncio
async def test_validate_compose_file(docker_ops):
    """Test compose file validation."""
    with patch.object(docker_ops, 'parse_compose_file', return_value={}):
        result = await docker_ops.validate_compose_file("path.yml")
        assert result is True
    
    with patch.object(docker_ops, 'parse_compose_file', side_effect=Exception("bad yaml")):
        result = await docker_ops.validate_compose_file("path.yml")
        assert result is False

@pytest.mark.asyncio
async def test_update_compose_paths_in_memory(docker_ops):
    """Test in-memory update of compose data."""
    volume_mapping = {
        "/mnt/cache/appdata/nginx_app": "/tank/nginx",
        "/mnt/cache/appdata/postgres_data": "/tank/postgres"
    }
    
    updated_yaml_str = await docker_ops.update_compose_paths(DOCKER_COMPOSE_ABSOLUTE_PATHS, volume_mapping)
    
    updated_data = yaml.safe_load(updated_yaml_str)
    
    web_volumes = updated_data['services']['web']['volumes']
    assert web_volumes[0] == '/tank/nginx:/usr/share/nginx/html'
    
    db_volumes = updated_data['services']['db']['volumes']
    assert db_volumes[0] == '/tank/postgres:/var/lib/postgresql/data' 