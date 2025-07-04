"""
Concrete implementation of command executor interface.
"""
import asyncio
import logging
from typing import List
from ..core.interfaces.command_executor import ICommandExecutor, CommandResult
from ..core.value_objects.ssh_config import SSHConfig


class CommandExecutor(ICommandExecutor):
    """Concrete implementation of command executor with security validation."""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        
        # Allowed ZFS commands for security
        self._allowed_zfs_commands = {
            'list', 'get', 'set', 'create', 'destroy', 'snapshot', 'clone',
            'send', 'receive', 'rollback', 'promote', 'rename', 'mount',
            'unmount', 'share', 'unshare', 'diff', 'bookmark', 'holds',
            'release', 'userspace', 'groupspace', 'projectspace'
        }
        
        # Allowed system commands
        self._allowed_system_commands = {
            'zpool', 'zfs', 'ssh', 'rsync', 'pv', 'mbuffer'
        }
    
    async def execute_zfs(self, command: str, *args: str) -> CommandResult:
        """Execute ZFS command with validation."""
        if command not in self._allowed_zfs_commands:
            return CommandResult(
                success=False,
                returncode=1,
                stdout="",
                stderr=f"ZFS command '{command}' not allowed"
            )
        
        full_command = ["zfs", command] + list(args)
        return await self._execute_command(full_command)
    
    async def execute_system(self, command: str, *args: str) -> CommandResult:
        """Execute system command with validation."""
        if command not in self._allowed_system_commands:
            return CommandResult(
                success=False,
                returncode=1,
                stdout="",
                stderr=f"System command '{command}' not allowed"
            )
        
        full_command = [command] + list(args)
        return await self._execute_command(full_command)
    
    async def execute_remote(self, host: str, command: List[str], 
                           ssh_config: SSHConfig) -> CommandResult:
        """Execute command on remote host via SSH."""
        try:
            # Build SSH command
            ssh_cmd = [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", f"ConnectTimeout={ssh_config.timeout}",
                "-p", str(ssh_config.port),
                "-l", ssh_config.user
            ]
            
            if ssh_config.key_file:
                ssh_cmd.extend(["-i", ssh_config.key_file])
            
            ssh_cmd.append(host)
            ssh_cmd.extend(command)
            
            return await self._execute_command(ssh_cmd)
            
        except Exception as e:
            return CommandResult(
                success=False,
                returncode=1,
                stdout="",
                stderr=f"Remote execution failed: {str(e)}"
            )
    
    async def _execute_command(self, command: List[str]) -> CommandResult:
        """Execute command with proper error handling."""
        try:
            self.logger.debug(f"Executing command: {' '.join(command)}")
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024*1024  # 1MB limit
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return CommandResult(
                    success=False,
                    returncode=124,  # Timeout exit code
                    stdout="",
                    stderr=f"Command timed out after {self.timeout} seconds"
                )
            
            stdout_str = stdout.decode('utf-8', errors='replace').strip()
            stderr_str = stderr.decode('utf-8', errors='replace').strip()
            
            success = process.returncode == 0
            
            if not success:
                self.logger.warning(
                    f"Command failed with exit code {process.returncode}: {stderr_str}"
                )
            
            return CommandResult(
                success=success,
                returncode=process.returncode or 1,  # Default to 1 if None
                stdout=stdout_str,
                stderr=stderr_str
            )
            
        except Exception as e:
            self.logger.error(f"Command execution failed: {str(e)}")
            return CommandResult(
                success=False,
                returncode=1,
                stdout="",
                stderr=f"Command execution failed: {str(e)}"
            ) 