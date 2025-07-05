"""
Concrete implementation of command executor interface.
"""
import asyncio
import logging
import os
import hashlib
import subprocess
from pathlib import Path
from typing import List, Optional
from ..core.interfaces.command_executor import ICommandExecutor, CommandResult
from ..core.value_objects.ssh_config import SSHConfig


class CommandExecutor(ICommandExecutor):
    """Concrete implementation of command executor with security validation."""
    
    def __init__(self, timeout: int = 30, known_hosts_file: Optional[str] = None):
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        
        # Set up known_hosts file path
        self.known_hosts_file = known_hosts_file or os.path.expanduser("~/.ssh/known_hosts")
        self._ensure_ssh_directory()
        
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
    
    def _ensure_ssh_directory(self) -> None:
        """Ensure SSH directory and known_hosts file exist with proper permissions."""
        try:
            ssh_dir = Path(self.known_hosts_file).parent
            ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            
            # Create known_hosts file if it doesn't exist
            if not Path(self.known_hosts_file).exists():
                Path(self.known_hosts_file).touch(mode=0o600)
                self.logger.info(f"Created known_hosts file: {self.known_hosts_file}")
            else:
                # Ensure proper permissions on existing file
                os.chmod(self.known_hosts_file, 0o600)
                
        except Exception as e:
            self.logger.error(f"Failed to set up SSH directory: {e}")
            raise
    
    def _get_host_key(self, host: str, port: int = 22) -> Optional[str]:
        """
        Get the host key for verification before connecting.
        
        Args:
            host: Hostname to get key for
            port: SSH port (default 22)
            
        Returns:
            Host key string if available, None otherwise
        """
        try:
            # Use ssh-keyscan to get the host key
            cmd = ["ssh-keyscan", "-p", str(port), host]
            process = asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Note: This is a synchronous operation for key scanning
            # In production, you might want to make this async
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            else:
                self.logger.warning(f"Failed to get host key for {host}:{port}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting host key for {host}:{port}: {e}")
            return None
    
    def _is_host_known(self, host: str, port: int = 22) -> bool:
        """
        Check if host is in known_hosts file.
        
        Args:
            host: Hostname to check
            port: SSH port (default 22)
            
        Returns:
            True if host is known, False otherwise
        """
        try:
            if not Path(self.known_hosts_file).exists():
                return False
                
            with open(self.known_hosts_file, 'r') as f:
                content = f.read()
                
            # Check for various host formats in known_hosts
            host_patterns = [
                host,  # hostname
                f"[{host}]:{port}" if port != 22 else host,  # [hostname]:port
                f"{host}:{port}" if port != 22 else host,   # hostname:port
            ]
            
            for pattern in host_patterns:
                if pattern in content:
                    return True
                    
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking known hosts: {e}")
            return False
    
    def add_host_key(self, host: str, port: int = 22, auto_accept: bool = False) -> bool:
        """
        Add host key to known_hosts file.
        
        Args:
            host: Hostname to add
            port: SSH port (default 22)
            auto_accept: If True, automatically accept the key without prompting
            
        Returns:
            True if key was added successfully, False otherwise
        """
        try:
            if self._is_host_known(host, port):
                self.logger.info(f"Host {host}:{port} is already known")
                return True
                
            host_key = self._get_host_key(host, port)
            if not host_key:
                self.logger.error(f"Could not retrieve host key for {host}:{port}")
                return False
            
            if not auto_accept:
                # In a real implementation, you would prompt the user here
                # For now, we'll log the key and require explicit approval
                self.logger.warning(
                    f"New host key for {host}:{port}:\n{host_key}\n"
                    f"To accept this key, set auto_accept=True or manually add to {self.known_hosts_file}"
                )
                return False
            
            # Add the key to known_hosts
            with open(self.known_hosts_file, 'a') as f:
                f.write(f"{host_key}\n")
                
            self.logger.info(f"Added host key for {host}:{port} to known_hosts")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add host key for {host}:{port}: {e}")
            return False
    
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
                           ssh_config: SSHConfig, auto_accept_hostkey: bool = False) -> CommandResult:
        """
        Execute command on remote host via SSH with proper host key verification.
        
        Args:
            host: Remote hostname
            command: Command to execute
            ssh_config: SSH configuration
            auto_accept_hostkey: If True, automatically accept unknown host keys
            
        Returns:
            CommandResult with execution results
        """
        try:
            # Check if host key is known
            if not self._is_host_known(host, ssh_config.port):
                self.logger.warning(f"Host {host}:{ssh_config.port} is not in known_hosts")
                
                if auto_accept_hostkey:
                    if not self.add_host_key(host, ssh_config.port, auto_accept=True):
                        return CommandResult(
                            success=False,
                            returncode=1,
                            stdout="",
                            stderr=f"Failed to add host key for {host}:{ssh_config.port}"
                        )
                else:
                    return CommandResult(
                        success=False,
                        returncode=1,
                        stdout="",
                        stderr=(
                            f"Host {host}:{ssh_config.port} is not in known_hosts. "
                            f"To proceed:\n"
                            f"1. Manually add the host key to {self.known_hosts_file}, or\n"
                            f"2. Use add_host_key() method to verify and add the key, or\n"
                            f"3. Set auto_accept_hostkey=True (not recommended for production)"
                        )
                    )
            
            # Build secure SSH command
            ssh_cmd = [
                "ssh",
                "-o", "StrictHostKeyChecking=yes",  # Enable host key checking
                "-o", f"UserKnownHostsFile={self.known_hosts_file}",  # Use our known_hosts file
                "-o", f"ConnectTimeout={ssh_config.timeout}",
                "-o", "BatchMode=yes",  # Don't prompt for passwords/passphrases
                "-o", "PasswordAuthentication=no",  # Force key-based auth
                "-p", str(ssh_config.port),
                "-l", ssh_config.user
            ]
            
            if ssh_config.key_file:
                ssh_cmd.extend(["-i", ssh_config.key_file])
            
            ssh_cmd.append(host)
            ssh_cmd.extend(command)
            
            self.logger.debug(f"Executing secure SSH command to {host}:{ssh_config.port}")
            return await self._execute_command(ssh_cmd)
            
        except Exception as e:
            self.logger.error(f"Remote execution failed: {e}")
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