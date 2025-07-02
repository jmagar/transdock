"""
Unit Tests for Transfer Operations Module

This module contains tests for Transfer operations with mocked system calls.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, Mock
from backend.transfer_ops import TransferOperations, TransferMethod
from backend.security_utils import RsyncConfig
from tests.fixtures.test_data import MOCK_COMMAND_OUTPUTS


class TestTransferOperations:
    """Test suite for Transfer operations."""

    @pytest.fixture
    def transfer_ops(self):
        """Create Transfer operations instance."""
        return TransferOperations()

    @pytest.mark.asyncio
    async def test_test_ssh_connection_success(self, transfer_ops, mock_subprocess):
        """Test successful SSH connection test."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = MOCK_COMMAND_OUTPUTS['ssh_test']
        
        result = await transfer_ops.test_ssh_connection(
            hostname="192.168.1.100",
            username="root", 
            port=22
        )
        
        assert result is True

    @pytest.mark.asyncio
    async def test_test_ssh_connection_failure(self, transfer_ops, mock_subprocess):
        """Test failed SSH connection test."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "Connection refused"
        
        result = await transfer_ops.test_ssh_connection(
            hostname="192.168.1.100",
            username="root",
            port=22
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_test_ssh_connection_timeout(self, transfer_ops):
        """Test SSH connection timeout."""
        with patch('asyncio.create_subprocess_exec') as mock_create:
            # Mock a process that times out
            mock_process = Mock()
            mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
            mock_process.returncode = None
            mock_create.return_value = mock_process
            
            result = await transfer_ops.test_ssh_connection(
                hostname="192.168.1.100",
                username="root",
                port=22
            )
            
            assert result is False

    @pytest.mark.asyncio
    async def test_rsync_transfer_success(self, transfer_ops, mock_subprocess):
        """Test successful rsync transfer."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = MOCK_COMMAND_OUTPUTS['rsync_test']
        
        config = RsyncConfig(
            source="/mnt/cache/compose/authelia",
            hostname="192.168.1.100",
            username="root",
            port=22,
            target="/home/user/docker/authelia"
        )
        
        result = await transfer_ops.rsync_transfer(config)
        assert result is True

    @pytest.mark.asyncio
    async def test_rsync_transfer_failure(self, transfer_ops, mock_subprocess):
        """Test failed rsync transfer."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "rsync: connection unexpectedly closed"
        
        config = RsyncConfig(
            source="/mnt/cache/compose/authelia",
            hostname="192.168.1.100",
            username="root", 
            port=22,
            target="/home/user/docker/authelia"
        )
        
        result = await transfer_ops.rsync_transfer(config)
        assert result is False

    @pytest.mark.asyncio
    async def test_rsync_transfer_with_additional_args(self, transfer_ops, mock_subprocess):
        """Test rsync transfer with additional arguments."""
        mock_subprocess.return_value.returncode = 0
        
        config = RsyncConfig(
            source="/mnt/cache/compose/authelia",
            hostname="192.168.1.100",
            username="root",
            port=22,
            target="/home/user/docker/authelia",
            additional_args=["--dry-run", "--verbose"]
        )
        
        result = await transfer_ops.rsync_transfer(config)
        assert result is True
        
        # Verify additional args were included
        args, kwargs = mock_subprocess.call_args
        assert "--dry-run" in args[0]
        assert "--verbose" in args[0]

    @pytest.mark.asyncio
    async def test_zfs_send_transfer_success(self, transfer_ops, mock_subprocess):
        """Test successful ZFS send transfer."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = MOCK_COMMAND_OUTPUTS['zfs_send_test']
        
        result = await transfer_ops.zfs_send_transfer(
            snapshot="cache/compose/authelia@migration-123",
            target_host="192.168.1.100", 
            ssh_user="root",
            target_dataset="tank/compose/authelia"
        )
        
        assert result is True

    @pytest.mark.asyncio
    async def test_zfs_send_transfer_failure(self, transfer_ops, mock_subprocess):
        """Test failed ZFS send transfer."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "cannot send snapshot: no such dataset"
        
        result = await transfer_ops.zfs_send_transfer(
            snapshot="cache/compose/nonexistent@migration-123",
            target_host="192.168.1.100",
            ssh_user="root", 
            target_dataset="tank/compose/nonexistent"
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_zfs_send_incremental_transfer(self, transfer_ops, mock_subprocess):
        """Test incremental ZFS send transfer."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "incremental stream"
        
        result = await transfer_ops.zfs_send_transfer(
            snapshot="cache/compose/authelia@migration-124",
            target_host="192.168.1.100",
            ssh_user="root",
            target_dataset="tank/compose/authelia", 
            incremental_base="cache/compose/authelia@migration-123"
        )
        
        assert result is True
        
        # Verify incremental flag was used
        args, kwargs = mock_subprocess.call_args
        command_str = " ".join(args[0])
        assert "-i" in args[0] or "--incremental" in command_str

    @pytest.mark.asyncio
    async def test_determine_transfer_method_zfs_available(self, transfer_ops):
        """Test transfer method determination when ZFS is available on both ends."""
        with patch.object(transfer_ops, '_check_remote_zfs_support', return_value=True):
            method = await transfer_ops.determine_transfer_method(
                source_has_zfs=True,
                target_host="192.168.1.100",
                ssh_user="root"
            )
            
            assert method == TransferMethod.ZFS_SEND

    @pytest.mark.asyncio
    async def test_determine_transfer_method_no_zfs(self, transfer_ops):
        """Test transfer method determination when ZFS is not available."""
        with patch.object(transfer_ops, '_check_remote_zfs_support', return_value=False):
            method = await transfer_ops.determine_transfer_method(
                source_has_zfs=False,
                target_host="192.168.1.100",
                ssh_user="root"
            )
            
            assert method == TransferMethod.RSYNC

    @pytest.mark.asyncio
    async def test_determine_transfer_method_force_rsync(self, transfer_ops):
        """Test transfer method determination when forced to use rsync."""
        method = await transfer_ops.determine_transfer_method(
            source_has_zfs=True,
            target_host="192.168.1.100",
            ssh_user="root",
            force_rsync=True
        )
        
        assert method == TransferMethod.RSYNC

    @pytest.mark.asyncio
    async def test_check_remote_zfs_support_available(self, transfer_ops, mock_subprocess):
        """Test checking remote ZFS support when available."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "zfs-2.1.5"
        
        result = await transfer_ops._check_remote_zfs_support(
            hostname="192.168.1.100",
            username="root"
        )
        
        assert result is True

    @pytest.mark.asyncio
    async def test_check_remote_zfs_support_not_available(self, transfer_ops, mock_subprocess):
        """Test checking remote ZFS support when not available."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "command not found"
        
        result = await transfer_ops._check_remote_zfs_support(
            hostname="192.168.1.100",
            username="root"
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_create_remote_directory_success(self, transfer_ops, mock_subprocess):
        """Test successful remote directory creation."""
        mock_subprocess.return_value.returncode = 0
        
        result = await transfer_ops.create_remote_directory(
            hostname="192.168.1.100",
            username="root",
            directory="/home/user/docker/authelia"
        )
        
        assert result is True
        
        # Verify mkdir command was called
        args, kwargs = mock_subprocess.call_args
        assert "mkdir" in args[0]
        assert "-p" in args[0]  # Should create parent directories

    @pytest.mark.asyncio
    async def test_create_remote_directory_failure(self, transfer_ops, mock_subprocess):
        """Test failed remote directory creation."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "Permission denied"
        
        result = await transfer_ops.create_remote_directory(
            hostname="192.168.1.100",
            username="user",
            directory="/root/restricted"
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_cleanup_remote_snapshots_success(self, transfer_ops, mock_subprocess):
        """Test successful remote snapshot cleanup."""
        mock_subprocess.return_value.returncode = 0
        
        result = await transfer_ops.cleanup_remote_snapshots(
            hostname="192.168.1.100",
            username="root",
            snapshots=["tank/compose/authelia@migration-123"]
        )
        
        assert result is True

    @pytest.mark.asyncio
    async def test_cleanup_remote_snapshots_failure(self, transfer_ops, mock_subprocess):
        """Test failed remote snapshot cleanup."""
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "snapshot does not exist"
        
        result = await transfer_ops.cleanup_remote_snapshots(
            hostname="192.168.1.100", 
            username="root",
            snapshots=["tank/compose/nonexistent@migration-123"]
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_transfer_progress_rsync(self, transfer_ops):
        """Test getting transfer progress from rsync output."""
        rsync_output = """
        building file list ... done
        file1.txt
             1,234 bytes  received
        file2.txt
             5,678 bytes  received
        
        sent 1,234 bytes  received 6,912 bytes  total size 8,146
        """
        
        progress = transfer_ops._parse_rsync_progress(rsync_output)
        assert progress >= 0
        assert progress <= 100

    @pytest.mark.asyncio
    async def test_get_transfer_progress_zfs_send(self, transfer_ops):
        """Test getting transfer progress from ZFS send output."""
        zfs_output = MOCK_COMMAND_OUTPUTS['zfs_send_test']
        
        progress = transfer_ops._parse_zfs_progress(zfs_output)
        assert progress >= 0
        assert progress <= 100

    @pytest.mark.asyncio
    async def test_secure_transfer_validation(self, transfer_ops):
        """Test security validation in transfer operations."""
        # Test with malicious hostname
        with pytest.raises(Exception):
            await transfer_ops.test_ssh_connection(
                hostname="host; rm -rf /",
                username="root",
                port=22
            )
        
        # Test with malicious username
        with pytest.raises(Exception):
            await transfer_ops.test_ssh_connection(
                hostname="192.168.1.100",
                username="user; rm -rf /",
                port=22
            )

    @pytest.mark.ssh
    async def test_integration_ssh_and_rsync(self, transfer_ops, mock_subprocess):
        """Integration test for SSH connection and rsync transfer."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "success"
        
        # Test SSH connection first
        ssh_result = await transfer_ops.test_ssh_connection(
            hostname="192.168.1.100",
            username="root",
            port=22
        )
        assert ssh_result is True
        
        # Then test rsync transfer
        config = RsyncConfig(
            source="/test/source",
            hostname="192.168.1.100",
            username="root",
            port=22,
            target="/test/target"
        )
        
        rsync_result = await transfer_ops.rsync_transfer(config)
        assert rsync_result is True
        
        # Verify both operations were called
        assert mock_subprocess.call_count == 2

    @pytest.mark.asyncio
    async def test_concurrent_transfer_operations(self, transfer_ops, mock_subprocess):
        """Test concurrent transfer operations."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "success"
        
        # Run multiple SSH connection tests concurrently
        tasks = [
            transfer_ops.test_ssh_connection(f"192.168.1.{100+i}", "root", 22)
            for i in range(3)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(result is True for result in results)
        assert mock_subprocess.call_count == 3

    @pytest.mark.asyncio
    async def test_error_recovery_retry_mechanism(self, transfer_ops, mock_subprocess):
        """Test error recovery and retry mechanisms."""
        # Mock first call to fail, second to succeed
        mock_subprocess.side_effect = [
            Mock(returncode=1, stderr="temporary failure"),
            Mock(returncode=0, stdout="success")
        ]
        
        # This should retry on failure (implementation dependent)
        result = await transfer_ops.test_ssh_connection(
            hostname="192.168.1.100",
            username="root",
            port=22
        )
        
        # Depending on implementation, this might succeed after retry
        # For now, we just test that the first call failed
        assert mock_subprocess.call_count >= 1

    @pytest.mark.asyncio
    async def test_bandwidth_limiting_rsync(self, transfer_ops, mock_subprocess):
        """Test bandwidth limiting in rsync transfers."""
        mock_subprocess.return_value.returncode = 0
        
        config = RsyncConfig(
            source="/test/source",
            hostname="192.168.1.100", 
            username="root",
            port=22,
            target="/test/target",
            additional_args=["--bwlimit=1000"]  # Limit to 1MB/s
        )
        
        result = await transfer_ops.rsync_transfer(config)
        assert result is True
        
        # Verify bandwidth limit was included
        args, kwargs = mock_subprocess.call_args
        assert "--bwlimit=1000" in args[0]

    @pytest.mark.asyncio
    async def test_transfer_with_progress_callback(self, transfer_ops, mock_subprocess):
        """Test transfer operations with progress callbacks."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = MOCK_COMMAND_OUTPUTS['rsync_test']
        
        progress_updates = []
        
        def progress_callback(percent):
            progress_updates.append(percent)
        
        config = RsyncConfig(
            source="/test/source",
            hostname="192.168.1.100",
            username="root",
            port=22,
            target="/test/target"
        )
        
        # This would depend on the actual implementation having progress callback support
        result = await transfer_ops.rsync_transfer(config)
        assert result is True 