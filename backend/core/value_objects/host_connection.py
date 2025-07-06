"""HostConnection value object"""

from dataclasses import dataclass
from typing import Optional
import re
from ..exceptions.validation_exceptions import InvalidHostnameError, InvalidPortError


@dataclass(frozen=True)
class HostConnection:
    """Immutable value object for SSH host connections"""
    
    hostname: str
    username: str = "root"
    port: int = 22
    
    def __post_init__(self):
        # Validate hostname
        if not self.hostname:
            raise InvalidHostnameError("Hostname cannot be empty")
        
        if len(self.hostname) > 253:
            raise InvalidHostnameError("Hostname cannot exceed 253 characters")
        
        # Basic hostname validation
        # Allow IP addresses and domain names
        if not self._is_valid_hostname(self.hostname):
            raise InvalidHostnameError(f"Invalid hostname format: {self.hostname}")
        
        # Validate username
        if not self.username:
            raise InvalidHostnameError("Username cannot be empty")
        
        if len(self.username) > 32:
            raise InvalidHostnameError("Username cannot exceed 32 characters")
        
        # Basic username validation (Unix usernames)
        if not re.match(r'^[a-z_][a-z0-9_-]*$', self.username):
            raise InvalidHostnameError(
                f"Invalid username: {self.username}. "
                "Must start with lowercase letter or underscore and contain only lowercase letters, numbers, hyphens, and underscores."
            )
        
        # Validate port
        if not isinstance(self.port, int):
            raise InvalidPortError("Port must be an integer")
        
        if not (1 <= self.port <= 65535):
            raise InvalidPortError(f"Port must be between 1 and 65535, got: {self.port}")
    
    def _is_valid_hostname(self, hostname: str) -> bool:
        """Validate hostname format (IPv4, IPv6, or domain name)"""
        # Check for IPv4 address
        if self._is_valid_ipv4(hostname):
            return True
        
        # Check for IPv6 address (basic check)
        if self._is_valid_ipv6(hostname):
            return True
        
        # Check for domain name
        if self._is_valid_domain(hostname):
            return True
        
        return False
    
    def _is_valid_ipv4(self, ip: str) -> bool:
        """Validate IPv4 address"""
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            for part in parts:
                if not (0 <= int(part) <= 255):
                    return False
                # No leading zeros except for 0 itself
                if len(part) > 1 and part[0] == '0':
                    return False
            return True
        except (ValueError, AttributeError):
            return False
    
    def _is_valid_ipv6(self, ip: str) -> bool:
        """Basic IPv6 validation"""
        # This is a simplified check - proper IPv6 validation is complex
        if ip.count(':') < 2:
            return False
        
        # Handle compressed notation
        if '::' in ip:
            if ip.count('::') > 1:
                return False
        
        # Basic pattern check
        return bool(re.match(r'^[0-9a-fA-F:]+$', ip))
    
    def _is_valid_domain(self, domain: str) -> bool:
        """Validate domain name"""
        if domain.endswith('.'):
            domain = domain[:-1]  # Remove trailing dot
        
        if len(domain) > 253:
            return False
        
        # Split into labels
        labels = domain.split('.')
        
        for label in labels:
            if not label:
                return False
            if len(label) > 63:
                return False
            if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$', label):
                return False
        
        return True
    
    @classmethod
    def localhost(cls, username: str = "root", port: int = 22) -> 'HostConnection':
        """Create localhost connection"""
        return cls("localhost", username, port)
    
    @classmethod
    def from_string(cls, connection_string: str) -> 'HostConnection':
        """Parse connection string in format [username@]hostname[:port]"""
        # Default values
        username = "root"
        port = 22
        
        # Parse username if present
        if '@' in connection_string:
            username, hostname_port = connection_string.split('@', 1)
        else:
            hostname_port = connection_string
        
        # Parse port if present
        if ':' in hostname_port:
            hostname, port_str = hostname_port.rsplit(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                raise InvalidPortError(f"Invalid port: {port_str}")
        else:
            hostname = hostname_port
        
        return cls(hostname, username, port)
    
    def to_string(self) -> str:
        """Convert to connection string format"""
        if self.port == 22:
            return f"{self.username}@{self.hostname}"
        return f"{self.username}@{self.hostname}:{self.port}"
    
    def to_ssh_url(self) -> str:
        """Convert to SSH URL format"""
        return f"ssh://{self.username}@{self.hostname}:{self.port}"
    
    def is_localhost(self) -> bool:
        """Check if this is a localhost connection"""
        localhost_names = {'localhost', '127.0.0.1', '::1'}
        return self.hostname.lower() in localhost_names
    
    def with_username(self, username: str) -> 'HostConnection':
        """Create new connection with different username"""
        return HostConnection(self.hostname, username, self.port)
    
    def with_port(self, port: int) -> 'HostConnection':
        """Create new connection with different port"""
        return HostConnection(self.hostname, self.username, port)
    
    def __str__(self) -> str:
        return self.to_string()
    
    def __repr__(self) -> str:
        return f"HostConnection('{self.hostname}', '{self.username}', {self.port})"