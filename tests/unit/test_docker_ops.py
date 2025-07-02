"""
Unit Tests for Docker Operations Module

This module contains tests for Docker operations with mocked system calls.
"""

import pytest
import yaml
from unittest.mock import AsyncMock, patch, Mock, mock_open
from backend.docker_ops import DockerOperations
from backend.models import VolumeMount
from tests.fixtures.test_data import (
    DOCKER_COMPOSE_AUTHELIA, 
    DOCKER_COMPOSE_SIMPLE,
    DOCKER_COMPOSE_COMPLEX,
    MOCK_COMMAND_OUTPUTS
)


class TestDockerOperations:
    """Test suite for Docker operations."""

    @pytest.fixture
    def docker_ops(self):
        """Create Docker operations instance."""
        return DockerOperations()

    @pytest.mark.asyncio
    async def test_is_available_true(self, docker_ops, mock_subprocess):
        """Test Docker availability detection when Docker is available."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = MOCK_COMMAND_OUTPUTS['docker_version']
        
        result = await docker_ops.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_available_false(self, docker_ops, mock_subprocess):
        """Test Docker availability detection when Docker is not available."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "command not found"
        
        result = await docker_ops.is_available()
        assert result is False

    def test_parse_compose_file_authelia(self, docker_ops, mock_file_operations):
        """Test parsing Authelia compose file."""
        compose_content = yaml.dump(DOCKER_COMPOSE_AUTHELIA)
        mock_file_operations['open'].return_value.__enter__.return_value.read.return_value = compose_content
        
        result = docker_ops.parse_compose_file("/path/to/authelia/docker-compose.yml")
        
        assert result is not None
        assert 'services' in result
        assert 'authelia' in result['services']
        assert 'redis' in result['services']
        assert 'mariadb' in result['services']

    def test_parse_compose_file_simple(self, docker_ops, mock_file_operations):
        """Test parsing simple compose file."""
        compose_content = yaml.dump(DOCKER_COMPOSE_SIMPLE)
        mock_file_operations['open'].return_value.__enter__.return_value.read.return_value = compose_content
        
        result = docker_ops.parse_compose_file("/path/to/nginx/docker-compose.yml")
        
        assert result is not None
        assert 'services' in result
        assert 'nginx' in result['services']

    def test_parse_compose_file_not_found(self, docker_ops, mock_file_operations):
        """Test parsing compose file that doesn't exist."""
        mock_file_operations['exists'].return_value = False
        
        result = docker_ops.parse_compose_file("/nonexistent/docker-compose.yml")
        assert result is None

    def test_parse_compose_file_invalid_yaml(self, docker_ops, mock_file_operations):
        """Test parsing compose file with invalid YAML."""
        mock_file_operations['open'].return_value.__enter__.return_value.read.return_value = "invalid: yaml: content:"
        
        result = docker_ops.parse_compose_file("/path/to/invalid/docker-compose.yml")
        assert result is None

    @pytest.mark.asyncio
    async def test_stop_stack_success(self, docker_ops, mock_subprocess):
        """Test successful stack stop."""
        mock_subprocess.return_value.returncode = 0
        
        result = await docker_ops.stop_stack("/path/to/compose/stack")
        assert result is True
        
        # Verify the correct command was called
        args, kwargs = mock_subprocess.call_args
        assert "docker-compose" in args[0] or "docker" in args[0]
        assert "down" in args[0]

    @pytest.mark.asyncio 
    async def test_stop_stack_failure(self, docker_ops, mock_subprocess):
        """Test stack stop failure."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "stack not found"
        
        result = await docker_ops.stop_stack("/path/to/nonexistent/stack")
        assert result is False

    @pytest.mark.asyncio
    async def test_start_stack_success(self, docker_ops, mock_subprocess):
        """Test successful stack start."""
        mock_subprocess.return_value.returncode = 0
        
        result = await docker_ops.start_stack("/path/to/compose/stack")
        assert result is True
        
        # Verify the correct command was called
        args, kwargs = mock_subprocess.call_args
        assert "docker-compose" in args[0] or "docker" in args[0]
        assert "up" in args[0]
        assert "-d" in args[0]  # Should run in detached mode

    @pytest.mark.asyncio
    async def test_start_stack_failure(self, docker_ops, mock_subprocess):
        """Test stack start failure."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "compose file not found"
        
        result = await docker_ops.start_stack("/path/to/broken/stack")
        assert result is False

    def test_get_stack_volumes_authelia(self, docker_ops, mock_file_operations):
        """Test extracting volumes from Authelia stack."""
        compose_content = yaml.dump(DOCKER_COMPOSE_AUTHELIA)
        mock_file_operations['open'].return_value.__enter__.return_value.read.return_value = compose_content
        
        volumes = docker_ops.get_stack_volumes("/path/to/authelia")
        
        assert isinstance(volumes, list)
        assert len(volumes) > 0
        
        # Check for expected volume mounts
        volume_sources = [vol.source for vol in volumes]
        assert any("config" in source for source in volume_sources)
        assert any("data" in source for source in volume_sources)
        assert any("redis" in source for source in volume_sources)
        assert any("mariadb" in source for source in volume_sources)

    def test_get_stack_volumes_simple(self, docker_ops, mock_file_operations):
        """Test extracting volumes from simple stack."""
        compose_content = yaml.dump(DOCKER_COMPOSE_SIMPLE)
        mock_file_operations['open'].return_value.__enter__.return_value.read.return_value = compose_content
        
        volumes = docker_ops.get_stack_volumes("/path/to/nginx")
        
        assert isinstance(volumes, list)
        assert len(volumes) >= 2  # html and nginx.conf
        
        # Check volume types
        for volume in volumes:
            assert isinstance(volume, VolumeMount)
            assert volume.source.startswith("./") or volume.source.startswith("/")
            assert volume.target.startswith("/")

    def test_get_stack_volumes_no_volumes(self, docker_ops, mock_file_operations):
        """Test extracting volumes from stack with no volumes."""
        compose_no_volumes = {
            'version': '3.8',
            'services': {
                'app': {
                    'image': 'alpine:latest',
                    'command': 'sleep 300'
                }
            }
        }
        compose_content = yaml.dump(compose_no_volumes)
        mock_file_operations['open'].return_value.__enter__.return_value.read.return_value = compose_content
        
        volumes = docker_ops.get_stack_volumes("/path/to/no-volumes")
        
        assert isinstance(volumes, list)
        assert len(volumes) == 0

    def test_update_compose_paths_success(self, docker_ops, mock_file_operations):
        """Test successful compose file path updates."""
        compose_content = yaml.dump(DOCKER_COMPOSE_AUTHELIA)
        mock_file_operations['open'].return_value.__enter__.return_value.read.return_value = compose_content
        
        volume_mapping = {
            "./config": "/new/path/config",
            "./data": "/new/path/data",
            "./redis": "/new/path/redis",
            "./mariadb": "/new/path/mariadb"
        }
        
        result = docker_ops.update_compose_paths(
            "/path/to/authelia/docker-compose.yml",
            volume_mapping
        )
        
        assert result is True
        
        # Verify write was called
        mock_file_operations['open'].assert_called()

    def test_update_compose_paths_no_file(self, docker_ops, mock_file_operations):
        """Test compose path updates when file doesn't exist."""
        mock_file_operations['exists'].return_value = False
        
        result = docker_ops.update_compose_paths(
            "/nonexistent/docker-compose.yml",
            {"./old": "/new"}
        )
        
        assert result is False

    def test_update_compose_paths_no_mapping(self, docker_ops, mock_file_operations):
        """Test compose path updates with empty mapping."""
        compose_content = yaml.dump(DOCKER_COMPOSE_SIMPLE)
        mock_file_operations['open'].return_value.__enter__.return_value.read.return_value = compose_content
        
        result = docker_ops.update_compose_paths(
            "/path/to/nginx/docker-compose.yml",
            {}
        )
        
        assert result is True  # Should succeed even with empty mapping

    def test_volume_mount_parsing_bind_mounts(self, docker_ops):
        """Test parsing of bind mount volumes."""
        volume_strings = [
            "./data:/app/data",
            "/host/path:/container/path",
            "/host/path:/container/path:ro",
            "./config:/etc/app/config:rw"
        ]
        
        for volume_str in volume_strings:
            volumes = docker_ops._parse_volume_string(volume_str, "/base/path")
            assert len(volumes) == 1
            
            volume = volumes[0]
            assert isinstance(volume, VolumeMount)
            assert ":" in volume_str  # Original format should have colons
            
            # Check that paths are properly split
            parts = volume_str.split(":")
            if volume.source.startswith("./"):
                # Relative path should be made absolute
                assert volume.source != parts[0]
            else:
                # Absolute path should remain unchanged
                assert volume.source == parts[0]
            
            assert volume.target == parts[1]

    def test_volume_mount_parsing_named_volumes(self, docker_ops):
        """Test parsing of named volumes."""
        volume_strings = [
            "redis_data:/data",
            "mysql_data:/var/lib/mysql",
            "app_logs:/var/log/app"
        ]
        
        for volume_str in volume_strings:
            volumes = docker_ops._parse_volume_string(volume_str, "/base/path")
            assert len(volumes) == 1
            
            volume = volumes[0]
            assert isinstance(volume, VolumeMount)
            
            # Named volumes should not be converted to absolute paths
            parts = volume_str.split(":")
            assert volume.source == parts[0]
            assert volume.target == parts[1]

    @pytest.mark.asyncio
    async def test_docker_compose_vs_docker_command(self, docker_ops, mock_subprocess):
        """Test that appropriate docker command is used."""
        # Test with docker-compose available
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = MOCK_COMMAND_OUTPUTS['docker_compose_version']
        
        # This should use docker-compose
        await docker_ops.start_stack("/path/to/stack")
        
        args, kwargs = mock_subprocess.call_args
        assert "docker-compose" in args[0] or "docker" in args[0]

    @pytest.mark.docker
    async def test_integration_stop_and_start_stack(self, docker_ops, mock_subprocess):
        """Integration test for stopping and starting a stack."""
        mock_subprocess.return_value.returncode = 0
        
        # Stop stack
        stop_result = await docker_ops.stop_stack("/path/to/test/stack")
        assert stop_result is True
        
        # Start stack
        start_result = await docker_ops.start_stack("/path/to/test/stack")
        assert start_result is True
        
        # Verify both commands were called
        assert mock_subprocess.call_count == 2

    @pytest.mark.docker
    def test_complex_compose_file_parsing(self, docker_ops, mock_file_operations):
        """Test parsing complex compose file with multiple services."""
        compose_content = yaml.dump(DOCKER_COMPOSE_COMPLEX)
        mock_file_operations['open'].return_value.__enter__.return_value.read.return_value = compose_content
        
        result = docker_ops.parse_compose_file("/path/to/complex/docker-compose.yml")
        
        assert result is not None
        assert 'services' in result
        assert len(result['services']) == 3  # web, db, phpmyadmin
        
        # Check service dependencies
        assert 'depends_on' in result['services']['web']
        assert 'db' in result['services']['web']['depends_on']

    def test_error_handling_corrupt_compose_file(self, docker_ops, mock_file_operations):
        """Test error handling for corrupt compose files."""
        # Simulate file read error
        mock_file_operations['open'].side_effect = IOError("Permission denied")
        
        result = docker_ops.parse_compose_file("/path/to/corrupt/docker-compose.yml")
        assert result is None

    @pytest.mark.asyncio
    async def test_concurrent_docker_operations(self, docker_ops, mock_subprocess):
        """Test concurrent Docker operations."""
        import asyncio
        
        mock_subprocess.return_value.returncode = 0
        
        # Run multiple operations concurrently
        tasks = [
            docker_ops.is_available(),
            docker_ops.stop_stack("/path/to/stack1"),
            docker_ops.start_stack("/path/to/stack2")
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(result is True for result in results)
        assert mock_subprocess.call_count == 3 