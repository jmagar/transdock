"""
Unit Tests for Transfer Operations Module (v2)

This module contains updated tests for Transfer operations, aligned with the
refactored TransferOperations class.
"""

import pytest
from unittest.mock import AsyncMock
from backend.transfer_ops import TransferOperations
from backend.models import VolumeMount, TransferMethod

@pytest.fixture
def transfer_ops(mocker):
    """Create a TransferOperations instance with mocked dependencies."""
    ops = TransferOperations()
    # Mock the zfs_ops dependency which is created in the constructor
    ops.zfs_ops = mocker.AsyncMock()
    return ops

class TestTransferOperations:
    @pytest.mark.asyncio
    async def test_create_target_directories_success(self, transfer_ops, mocker):
        """Test successful creation of directories on a remote host."""
        mocker.patch.object(transfer_ops, 'run_command', return_value=(0, "", ""))
        mocker.patch('backend.transfer_ops.SecurityUtils.build_ssh_command', return_value=["ssh", "mkdir"])
        
        result = await transfer_ops.create_target_directories("host", ["/path/one", "/path/two"])
        assert result is True
        assert transfer_ops.run_command.call_count == 2

    @pytest.mark.asyncio
    async def test_transfer_via_zfs_send_success(self, transfer_ops, mocker):
        """Test successful transfer using ZFS send."""
        mocker.patch.object(transfer_ops, 'run_command', return_value=(0, "", ""))
        mocker.patch('backend.transfer_ops.SecurityUtils.build_ssh_command', return_value=["ssh", "zfs", "receive"])
        
        result = await transfer_ops.transfer_via_zfs_send("pool/data@snap", "host", "tank/data")
        assert result is True

    @pytest.mark.asyncio
    async def test_transfer_via_rsync_success(self, transfer_ops, mocker):
        """Test successful transfer using rsync."""
        mocker.patch.object(transfer_ops, 'create_target_directories', return_value=True)
        mocker.patch.object(transfer_ops, 'run_command', return_value=(0, "", ""))
        mocker.patch('backend.transfer_ops.SecurityUtils.build_rsync_command', return_value=["rsync"])
        
        result = await transfer_ops.transfer_via_rsync("/src/path", "host", "/dest/path")
        assert result is True

    @pytest.mark.asyncio
    async def test_mount_snapshot_for_rsync(self, transfer_ops, mocker):
        """Test mounting a snapshot for rsync transfer."""
        mocker.patch.object(transfer_ops, 'run_command', return_value=(0, "", ""))
        
        mount_point = await transfer_ops.mount_snapshot_for_rsync("pool/data@snap")
        assert mount_point is not None
        assert "pool_data_snap" in mount_point

    @pytest.mark.asyncio
    async def test_cleanup_rsync_mount(self, transfer_ops, mocker):
        """Test cleaning up a temporary rsync mount."""
        mocker.patch.object(transfer_ops, 'run_command', return_value=(0, "", ""))
        
        result = await transfer_ops.cleanup_rsync_mount("/tmp/mount", "pool/data@snap")
        assert result is True

    @pytest.mark.asyncio
    async def test_transfer_volume_data_zfs(self, transfer_ops, mocker):
        """Test transferring a volume using ZFS send."""
        mocker.patch.object(transfer_ops, 'transfer_via_zfs_send', return_value=True)
        volume = VolumeMount(source="/mnt/cache/appdata/test", target="/app/data")
        
        result = await transfer_ops.transfer_volume_data(
            volume, "pool/data@snap", "host", "/tank/data", TransferMethod.ZFS_SEND
        )
        assert result is True
        transfer_ops.transfer_via_zfs_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_transfer_volume_data_rsync(self, transfer_ops, mocker):
        """Test transferring a volume using rsync."""
        mocker.patch.object(transfer_ops, 'mount_snapshot_for_rsync', return_value="/tmp/mount")
        mocker.patch.object(transfer_ops, 'transfer_via_rsync', return_value=True)
        mocker.patch.object(transfer_ops, 'cleanup_rsync_mount', return_value=True)
        volume = VolumeMount(source="/mnt/cache/appdata/test", target="/app/data")

        result = await transfer_ops.transfer_volume_data(
            volume, "pool/data@snap", "host", "/dest/data", TransferMethod.RSYNC
        )
        assert result is True
        transfer_ops.mount_snapshot_for_rsync.assert_called_once()
        transfer_ops.transfer_via_rsync.assert_called_once()
        transfer_ops.cleanup_rsync_mount.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_volume_mapping(self, transfer_ops):
        """Test the creation of a volume mapping."""
        volumes = [
            VolumeMount(source="/mnt/cache/appdata/nginx", target="/app/nginx"),
            VolumeMount(source="/mnt/cache/compose/nginx", target="/etc/nginx")
        ]
        mapping = await transfer_ops.create_volume_mapping(volumes, "/new/base")
        assert mapping["/mnt/cache/appdata/nginx"] == "/new/base/appdata/nginx"
        assert mapping["/mnt/cache/compose/nginx"] == "/new/base/compose/nginx"

    @pytest.mark.asyncio
    async def test_verify_transfer_success(self, transfer_ops, mocker):
        """Test successful transfer verification."""
        # This mock is for the *local* file count
        mock_shell = mocker.patch('asyncio.create_subprocess_shell', new_callable=AsyncMock)
        mock_shell.return_value.communicate.return_value = (b'10\n', b'')
        mock_shell.return_value.returncode = 0

        # This mock is for the *remote* file count via run_command
        mocker.patch.object(transfer_ops, 'run_command', return_value=(0, "10\n", ""))
        
        result = await transfer_ops.verify_transfer("/src", "host", "/dest")
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_transfer_failure(self, transfer_ops, mocker):
        """Test failed transfer verification (mismatched counts)."""
        mocker.patch('asyncio.create_subprocess_shell', new_callable=AsyncMock)
        mocker.patch.object(transfer_ops, 'run_command', side_effect=[(0, "10\n", ""), (0, "9\n", "")])

        result = await transfer_ops.verify_transfer("/src", "host", "/dest")
        assert result is False

    @pytest.mark.asyncio
    async def test_write_remote_file_success(self, transfer_ops, mocker):
        """Test writing a file to a remote host successfully."""
        mocker.patch.object(transfer_ops, 'run_command', return_value=(0, "", ""))
        mocker.patch('backend.transfer_ops.SecurityUtils.build_ssh_command', return_value=["ssh", "echo"])
        
        result = await transfer_ops.write_remote_file("host", "/path/to/file", "content")
        assert result is True 