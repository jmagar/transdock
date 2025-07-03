"""
Unit Tests for ZFS Operations Module (v2)

This module contains updated tests for ZFS operations, aligned with the
refactored ZFSOperations class which uses a secure command runner.
"""

import pytest
from unittest.mock import patch
from backend.zfs_ops import ZFSOperations

@pytest.fixture
def zfs_ops():
    """Create a ZFSOperations instance for testing."""
    return ZFSOperations()

@pytest.mark.asyncio
async def test_safe_run_zfs_command_success(zfs_ops, mocker):
    """Test the safe ZFS command runner with a valid command."""
    mocker.patch.object(ZFSOperations, 'run_command', return_value=(0, "success", ""))
    
    returncode, stdout, stderr = await zfs_ops.safe_run_zfs_command("list", "-H")
    
    assert returncode == 0
    assert stdout == "success"
    assert stderr == ""

@pytest.mark.asyncio
async def test_safe_run_zfs_command_security_error(zfs_ops):
    """Test that the safe runner catches invalid ZFS commands."""
    returncode, stdout, stderr = await zfs_ops.safe_run_zfs_command("list; rm -rf /")
    
    assert returncode == 1
    assert "Security validation failed" in stderr

@pytest.mark.asyncio
async def test_dataset_exists(zfs_ops, mocker):
    """Test dataset existence check."""
    mocker.patch.object(zfs_ops, 'safe_run_zfs_command', return_value=(0, "", ""))
    result = await zfs_ops.dataset_exists("cache/compose")
    assert result is True

@pytest.mark.asyncio
async def test_dataset_not_exists(zfs_ops, mocker):
    """Test dataset non-existence check."""
    mocker.patch.object(zfs_ops, 'safe_run_zfs_command', return_value=(1, "", "does not exist"))
    result = await zfs_ops.dataset_exists("nonexistent/dataset")
    assert result is False

@pytest.mark.asyncio
async def test_list_datasets(zfs_ops, mocker):
    """Test listing ZFS datasets."""
    mock_stdout = "cache/appdata\ncache/compose\ncache/system"
    mocker.patch.object(zfs_ops, 'safe_run_zfs_command', return_value=(0, mock_stdout, ""))
    
    datasets = await zfs_ops.list_datasets()
    assert len(datasets) == 3
    assert "cache/compose" in datasets

@pytest.mark.asyncio
async def test_create_snapshot_success(zfs_ops, mocker):
    """Test successful snapshot creation."""
    mocker.patch.object(zfs_ops, 'safe_run_zfs_command', return_value=(0, "", ""))
    
    snapshot_name = await zfs_ops.create_snapshot("cache/compose", "test_snap")
    assert "cache/compose@test_snap" in snapshot_name

@pytest.mark.asyncio
async def test_create_snapshot_failure(zfs_ops, mocker):
    """Test snapshot creation failure."""
    mocker.patch.object(zfs_ops, 'safe_run_zfs_command', return_value=(1, "", "cannot create"))
    
    with pytest.raises(Exception, match="Failed to create snapshot"):
        await zfs_ops.create_snapshot("nonexistent/dataset", "bad_snap")

@pytest.mark.asyncio
async def test_send_snapshot_success(zfs_ops, mocker):
    """Test successful snapshot send."""
    mocker.patch('backend.zfs_ops.SecurityUtils.validate_zfs_command_args', return_value=["zfs", "send", "snapshot"])
    mocker.patch('backend.zfs_ops.SecurityUtils.build_ssh_command', return_value=["ssh", "zfs", "receive"])
    mocker.patch.object(zfs_ops, 'run_command', return_value=(0, "", ""))

    result = await zfs_ops.send_snapshot("cache/compose@snap", "host", "tank/compose")
    assert result is True

@pytest.mark.asyncio
async def test_cleanup_snapshot_success(zfs_ops, mocker):
    """Test successful snapshot cleanup."""
    mocker.patch.object(zfs_ops, 'safe_run_zfs_command', return_value=(0, "", ""))
    result = await zfs_ops.cleanup_snapshot("cache/compose@snap")
    assert result is True

@pytest.mark.asyncio
async def test_check_remote_zfs_success(zfs_ops, mocker):
    """Test checking for ZFS on a remote host successfully."""
    mocker.patch('backend.zfs_ops.SecurityUtils.build_ssh_command', return_value=["ssh", "which", "zfs"])
    mocker.patch.object(zfs_ops, 'run_command', return_value=(0, "/usr/sbin/zfs", ""))
    result = await zfs_ops.check_remote_zfs("host")
    assert result is True

@pytest.mark.asyncio
async def test_is_zfs_available_true(zfs_ops, mocker):
    """Test local ZFS availability."""
    mocker.patch.object(zfs_ops, 'run_command', return_value=(0, "/usr/sbin/zfs", ""))
    result = await zfs_ops.is_zfs_available()
    assert result is True

@pytest.mark.asyncio
async def test_is_zfs_available_false(zfs_ops, mocker):
    """Test local ZFS unavailability."""
    mocker.patch.object(zfs_ops, 'run_command', return_value=(1, "", "not found"))
    result = await zfs_ops.is_zfs_available()
    assert result is False 