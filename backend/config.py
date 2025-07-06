"""
TransDock Configuration Module

Centralizes all environment variable loading and configuration management
for improved code organization and maintainability.
"""

import os
import secrets
import string
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServerConfig:
    """Server and application configuration settings"""
    # Application settings
    debug: bool = False
    testing: bool = False
    log_level: str = "INFO"
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    enable_docs: bool = True
    
    # CORS settings
    cors_origins: list[str] = field(default_factory=lambda: ["*"])


@dataclass
class MigrationConfig:
    """Migration paths and operational settings"""
    # Migration path settings
    local_compose_base_path: str = "/mnt/user/compose"
    local_appdata_base_path: str = "/mnt/cache/appdata"
    default_target_compose_path: str = "/opt/docker/compose"
    default_target_appdata_path: str = "/opt/docker/appdata"
    
    # Legacy settings
    transdock_compose_base: str = "/mnt/cache/compose"
    
    # ZFS settings
    zfs_pool: str = "cache"
    
    # RSYNC settings
    rsync_bandwidth_limit: str = ""


@dataclass
class SafetyConfig:
    """Safety and validation configuration settings"""
    # Basic migration safety
    require_explicit_target: bool = True
    allow_target_override: bool = True
    validate_target_exists: bool = True
    
    # Critical infrastructure safety
    mandatory_pre_migration_snapshots: bool = True
    require_rollback_capability: bool = True
    enable_atomic_operations: bool = True
    validate_checksum_integrity: bool = True
    require_dry_run_before_transfer: bool = True
    enable_progress_monitoring: bool = True
    require_disk_health_check: bool = True
    validate_network_stability: bool = True
    
    # Operational limits
    max_migration_timeout_hours: int = 12
    backup_retention_days: int = 30


@dataclass
class AuthConfig:
    """Authentication and security configuration settings"""
    # JWT settings
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # Default user credentials
    admin_password: str = ""
    user_password: str = ""


class TransDockConfig:
    """
    TransDock configuration settings loaded from environment variables.
    
    Provides centralized configuration management with type conversion,
    validation, and automatic generation of secure defaults using focused config objects.
    """
    
    def __init__(self):
        """Initialize configuration from environment variables"""
        # Initialize focused config objects
        self.server = ServerConfig()
        self.migration = MigrationConfig()
        self.safety = SafetyConfig()
        self.auth = AuthConfig()
        
        # Load environment variables into config objects
        self._load_environment_variables()
        
        # Validate all configurations
        self._validate_configuration()
    
    def _load_environment_variables(self):
        """Load and process all environment variables into focused config objects"""
        
        # ==== SERVER CONFIG ====
        self.server.debug = self._get_bool("DEBUG", self.server.debug)
        self.server.testing = self._get_bool("TESTING", self.server.testing)
        self.server.log_level = self._get_string("LOG_LEVEL", self.server.log_level).upper()
        self.server.host = self._get_string("HOST", self.server.host)
        self.server.port = self._get_int("PORT", self.server.port)
        self.server.enable_docs = self._get_bool("ENABLE_DOCS", self.server.enable_docs)
        self.server.cors_origins = self._get_string("CORS_ORIGINS", "*").split(",")
        
        # ==== MIGRATION CONFIG ====
        self.migration.local_compose_base_path = self._get_string(
            "LOCAL_COMPOSE_BASE_PATH", self.migration.local_compose_base_path
        )
        self.migration.local_appdata_base_path = self._get_string(
            "LOCAL_APPDATA_BASE_PATH", self.migration.local_appdata_base_path
        )
        self.migration.default_target_compose_path = self._get_string(
            "DEFAULT_TARGET_COMPOSE_PATH", self.migration.default_target_compose_path
        )
        self.migration.default_target_appdata_path = self._get_string(
            "DEFAULT_TARGET_APPDATA_PATH", self.migration.default_target_appdata_path
        )
        self.migration.transdock_compose_base = self._get_string(
            "TRANSDOCK_COMPOSE_BASE", self.migration.transdock_compose_base
        )
        self.migration.zfs_pool = self._get_string("ZFS_POOL", self.migration.zfs_pool)
        self.migration.rsync_bandwidth_limit = self._get_string(
            "RSYNC_BANDWIDTH_LIMIT", self.migration.rsync_bandwidth_limit
        )
        
        # ==== SAFETY CONFIG ====
        self.safety.require_explicit_target = self._get_bool(
            "REQUIRE_EXPLICIT_TARGET", self.safety.require_explicit_target
        )
        self.safety.allow_target_override = self._get_bool(
            "ALLOW_TARGET_OVERRIDE", self.safety.allow_target_override
        )
        self.safety.validate_target_exists = self._get_bool(
            "VALIDATE_TARGET_EXISTS", self.safety.validate_target_exists
        )
        self.safety.mandatory_pre_migration_snapshots = self._get_bool(
            "MANDATORY_PRE_MIGRATION_SNAPSHOTS", self.safety.mandatory_pre_migration_snapshots
        )
        self.safety.require_rollback_capability = self._get_bool(
            "REQUIRE_ROLLBACK_CAPABILITY", self.safety.require_rollback_capability
        )
        self.safety.enable_atomic_operations = self._get_bool(
            "ENABLE_ATOMIC_OPERATIONS", self.safety.enable_atomic_operations
        )
        self.safety.validate_checksum_integrity = self._get_bool(
            "VALIDATE_CHECKSUM_INTEGRITY", self.safety.validate_checksum_integrity
        )
        self.safety.require_dry_run_before_transfer = self._get_bool(
            "REQUIRE_DRY_RUN_BEFORE_TRANSFER", self.safety.require_dry_run_before_transfer
        )
        self.safety.max_migration_timeout_hours = self._get_int(
            "MAX_MIGRATION_TIMEOUT_HOURS", self.safety.max_migration_timeout_hours
        )
        self.safety.enable_progress_monitoring = self._get_bool(
            "ENABLE_PROGRESS_MONITORING", self.safety.enable_progress_monitoring
        )
        self.safety.require_disk_health_check = self._get_bool(
            "REQUIRE_DISK_HEALTH_CHECK", self.safety.require_disk_health_check
        )
        self.safety.validate_network_stability = self._get_bool(
            "VALIDATE_NETWORK_STABILITY", self.safety.validate_network_stability
        )
        self.safety.backup_retention_days = self._get_int(
            "BACKUP_RETENTION_DAYS", self.safety.backup_retention_days
        )
        
        # ==== AUTH CONFIG ====
        self.auth.jwt_secret_key = self._get_or_generate_jwt_secret()
        self.auth.jwt_algorithm = self._get_string("JWT_ALGORITHM", self.auth.jwt_algorithm)
        self.auth.access_token_expire_minutes = self._get_int(
            "ACCESS_TOKEN_EXPIRE_MINUTES", self.auth.access_token_expire_minutes
        )
        self.auth.refresh_token_expire_days = self._get_int(
            "REFRESH_TOKEN_EXPIRE_DAYS", self.auth.refresh_token_expire_days
        )
        self.auth.admin_password = self._get_or_generate_password("ADMIN_PASSWORD")
        self.auth.user_password = self._get_or_generate_password("USER_PASSWORD")
    
    def _get_string(self, key: str, default: str) -> str:
        """Get string value from environment with multiple key attempts"""
        for prefix in ["", "TRANSDOCK_"]:
            env_key = f"{prefix}{key}"
            value = os.getenv(env_key)
            if value is not None:
                return value
        return default
    
    def _get_int(self, key: str, default: int) -> int:
        """Get integer value from environment with validation"""
        value = self._get_string(key, str(default))
        try:
            return int(value)
        except ValueError:
            print(f"⚠️  Invalid integer value for {key}: {value}, using default: {default}")
            return default
    
    def _get_bool(self, key: str, default: bool) -> bool:
        """Get boolean value from environment with validation"""
        value = self._get_string(key, str(default)).lower()
        return value in ("true", "1", "yes", "on")
    
    def _get_or_generate_jwt_secret(self) -> str:
        """Get JWT secret or generate a secure one"""
        for prefix in ["", "TRANSDOCK_"]:
            for suffix in ["JWT_SECRET_KEY", "JWT_SECRET"]:
                env_key = f"{prefix}{suffix}"
                value = os.getenv(env_key)
                if value:
                    return value
        
        # Generate secure JWT secret
        secret = secrets.token_urlsafe(64)
        print("⚠️  JWT_SECRET_KEY not set, generated secure key. Please save this to your .env file:")
        print(f"JWT_SECRET_KEY={secret}")
        return secret
    
    def _get_or_generate_password(self, key: str) -> str:
        """Get password or generate a secure one"""
        for prefix in ["", "TRANSDOCK_"]:
            env_key = f"{prefix}{key}"
            value = os.getenv(env_key)
            if value:
                return value
        
        # Generate secure password
        password = self._generate_secure_password()
        print(f"⚠️  {key} not set, generated secure password. Please save this to your .env file:")
        print(f"{key}={password}")
        return password
    
    @staticmethod
    def _generate_secure_password(length: int = 16) -> str:
        """Generate a cryptographically secure password"""
        characters = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(characters) for _ in range(length))
    
    def _validate_configuration(self):
        """Validate configuration values across all config objects"""
        # Validate log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.server.log_level not in valid_levels:
            print(f"⚠️  Invalid log level: {self.server.log_level}, using INFO")
            self.server.log_level = "INFO"
        
        # Validate JWT algorithm
        secure_algorithms = ["HS256", "HS384", "HS512", "RS256", "RS384", "RS512"]
        if self.auth.jwt_algorithm not in secure_algorithms:
            print(f"⚠️  Invalid JWT algorithm: {self.auth.jwt_algorithm}, using HS256")
            self.auth.jwt_algorithm = "HS256"
        
        # Validate port range
        if not (1 <= self.server.port <= 65535):
            print(f"⚠️  Invalid port: {self.server.port}, using default: 8000")
            self.server.port = 8000
    
    def get_summary(self) -> dict:
        """Get a summary of configuration (without sensitive data)"""
        return {
            "application": {
                "debug": self.server.debug,
                "testing": self.server.testing,
                "log_level": self.server.log_level,
            },
            "server": {
                "host": self.server.host,
                "port": self.server.port,
                "enable_docs": self.server.enable_docs,
                "cors_origins": self.server.cors_origins,
            },
            "migration": {
                "local_compose_base_path": self.migration.local_compose_base_path,
                "local_appdata_base_path": self.migration.local_appdata_base_path,
                "default_target_compose_path": self.migration.default_target_compose_path,
                "default_target_appdata_path": self.migration.default_target_appdata_path,
                "zfs_pool": self.migration.zfs_pool,
                "rsync_bandwidth_limit": self.migration.rsync_bandwidth_limit,
            },
            "safety": {
                "require_explicit_target": self.safety.require_explicit_target,
                "mandatory_pre_migration_snapshots": self.safety.mandatory_pre_migration_snapshots,
                "require_rollback_capability": self.safety.require_rollback_capability,
                "enable_atomic_operations": self.safety.enable_atomic_operations,
                "validate_checksum_integrity": self.safety.validate_checksum_integrity,
                "max_migration_timeout_hours": self.safety.max_migration_timeout_hours,
                "backup_retention_days": self.safety.backup_retention_days,
            },
            "authentication": {
                "jwt_algorithm": self.auth.jwt_algorithm,
                "access_token_expire_minutes": self.auth.access_token_expire_minutes,
                "refresh_token_expire_days": self.auth.refresh_token_expire_days,
            }
        }
    
    # Backward compatibility properties
    @property
    def debug(self) -> bool:
        return self.server.debug
    
    @property
    def testing(self) -> bool:
        return self.server.testing
    
    @property
    def log_level(self) -> str:
        return self.server.log_level
    
    @property
    def host(self) -> str:
        return self.server.host
    
    @property
    def port(self) -> int:
        return self.server.port
    
    @property
    def enable_docs(self) -> bool:
        return self.server.enable_docs
    
    @property
    def cors_origins(self) -> list[str]:
        return self.server.cors_origins
    
    @property
    def local_compose_base_path(self) -> str:
        return self.migration.local_compose_base_path
    
    @property
    def local_appdata_base_path(self) -> str:
        return self.migration.local_appdata_base_path
    
    @property
    def default_target_compose_path(self) -> str:
        return self.migration.default_target_compose_path
    
    @property
    def default_target_appdata_path(self) -> str:
        return self.migration.default_target_appdata_path
    
    @property
    def transdock_compose_base(self) -> str:
        return self.migration.transdock_compose_base
    
    @property
    def zfs_pool(self) -> str:
        return self.migration.zfs_pool
    
    @property
    def rsync_bandwidth_limit(self) -> str:
        return self.migration.rsync_bandwidth_limit
    
    @property
    def require_explicit_target(self) -> bool:
        return self.safety.require_explicit_target
    
    @property
    def allow_target_override(self) -> bool:
        return self.safety.allow_target_override
    
    @property
    def validate_target_exists(self) -> bool:
        return self.safety.validate_target_exists
    
    @property
    def mandatory_pre_migration_snapshots(self) -> bool:
        return self.safety.mandatory_pre_migration_snapshots
    
    @property
    def require_rollback_capability(self) -> bool:
        return self.safety.require_rollback_capability
    
    @property
    def enable_atomic_operations(self) -> bool:
        return self.safety.enable_atomic_operations
    
    @property
    def validate_checksum_integrity(self) -> bool:
        return self.safety.validate_checksum_integrity
    
    @property
    def require_dry_run_before_transfer(self) -> bool:
        return self.safety.require_dry_run_before_transfer
    
    @property
    def max_migration_timeout_hours(self) -> int:
        return self.safety.max_migration_timeout_hours
    
    @property
    def enable_progress_monitoring(self) -> bool:
        return self.safety.enable_progress_monitoring
    
    @property
    def require_disk_health_check(self) -> bool:
        return self.safety.require_disk_health_check
    
    @property
    def validate_network_stability(self) -> bool:
        return self.safety.validate_network_stability
    
    @property
    def backup_retention_days(self) -> int:
        return self.safety.backup_retention_days
    
    @property
    def jwt_secret_key(self) -> str:
        return self.auth.jwt_secret_key
    
    @property
    def jwt_algorithm(self) -> str:
        return self.auth.jwt_algorithm
    
    @property
    def access_token_expire_minutes(self) -> int:
        return self.auth.access_token_expire_minutes
    
    @property
    def refresh_token_expire_days(self) -> int:
        return self.auth.refresh_token_expire_days
    
    @property
    def admin_password(self) -> str:
        return self.auth.admin_password
    
    @property
    def user_password(self) -> str:
        return self.auth.user_password


def load_dotenv_if_exists():
    """Load .env file if it exists, with proper error handling"""
    try:
        from dotenv import load_dotenv
        
        # Try to load from multiple possible locations
        env_files = [
            Path(".env"),  # Current directory
            Path(__file__).parent.parent / ".env",  # Project root
        ]
        
        for env_file in env_files:
            if env_file.exists():
                load_dotenv(env_file)
                print(f"✅ Environment variables loaded from: {env_file}")
                return True
        
        print("⚠️  No .env file found. Using environment variables and defaults.")
        return False
        
    except ImportError:
        print("⚠️  python-dotenv not installed. Install with: uv add python-dotenv")
        return False
    except Exception as e:
        print(f"⚠️  Could not load .env file: {e}")
        return False


# Load environment variables first
load_dotenv_if_exists()

# Create global configuration instance
config = TransDockConfig()


def get_config() -> TransDockConfig:
    """Get the global configuration instance"""
    return config


# Backward compatibility exports
# These can be gradually removed as code is updated
LOCAL_COMPOSE_BASE_PATH = config.local_compose_base_path
LOCAL_APPDATA_BASE_PATH = config.local_appdata_base_path
DEFAULT_TARGET_COMPOSE_PATH = config.default_target_compose_path
DEFAULT_TARGET_APPDATA_PATH = config.default_target_appdata_path
REQUIRE_EXPLICIT_TARGET = config.require_explicit_target
ALLOW_TARGET_OVERRIDE = config.allow_target_override
VALIDATE_TARGET_EXISTS = config.validate_target_exists 