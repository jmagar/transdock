"""
TransDock Configuration Module

Centralizes all environment variable loading and configuration management
for improved code organization and maintainability.
"""

import os
import secrets
import string
from pathlib import Path
from typing import Optional


class TransDockConfig:
    """
    TransDock configuration settings loaded from environment variables.
    
    Provides centralized configuration management with type conversion,
    validation, and automatic generation of secure defaults.
    """
    
    def __init__(self):
        """Initialize configuration from environment variables"""
        self._load_environment_variables()
    
    def _load_environment_variables(self):
        """Load and process all environment variables"""
        
        # ==== APPLICATION SETTINGS ====
        self.debug = self._get_bool("DEBUG", False)
        self.testing = self._get_bool("TESTING", False)
        self.log_level = self._get_string("LOG_LEVEL", "INFO").upper()
        
        # ==== SERVER SETTINGS ====
        self.host = self._get_string("HOST", "0.0.0.0")
        self.port = self._get_int("PORT", 8000)
        self.enable_docs = self._get_bool("ENABLE_DOCS", True)
        
        # ==== MIGRATION PATH SETTINGS ====
        self.local_compose_base_path = self._get_string(
            "LOCAL_COMPOSE_BASE_PATH", "/mnt/user/compose"
        )
        self.local_appdata_base_path = self._get_string(
            "LOCAL_APPDATA_BASE_PATH", "/mnt/cache/appdata"
        )
        self.default_target_compose_path = self._get_string(
            "DEFAULT_TARGET_COMPOSE_PATH", "/opt/docker/compose"
        )
        self.default_target_appdata_path = self._get_string(
            "DEFAULT_TARGET_APPDATA_PATH", "/opt/docker/appdata"
        )
        
        # ==== MIGRATION SAFETY SETTINGS ====
        self.require_explicit_target = self._get_bool("REQUIRE_EXPLICIT_TARGET", True)
        self.allow_target_override = self._get_bool("ALLOW_TARGET_OVERRIDE", True)
        self.validate_target_exists = self._get_bool("VALIDATE_TARGET_EXISTS", True)
        
        # ==== CRITICAL INFRASTRUCTURE SAFETY SETTINGS ====
        self.mandatory_pre_migration_snapshots = self._get_bool(
            "MANDATORY_PRE_MIGRATION_SNAPSHOTS", True
        )
        self.require_rollback_capability = self._get_bool(
            "REQUIRE_ROLLBACK_CAPABILITY", True
        )
        self.enable_atomic_operations = self._get_bool("ENABLE_ATOMIC_OPERATIONS", True)
        self.validate_checksum_integrity = self._get_bool(
            "VALIDATE_CHECKSUM_INTEGRITY", True
        )
        self.require_dry_run_before_transfer = self._get_bool(
            "REQUIRE_DRY_RUN_BEFORE_TRANSFER", True
        )
        self.max_migration_timeout_hours = self._get_int(
            "MAX_MIGRATION_TIMEOUT_HOURS", 12
        )
        self.enable_progress_monitoring = self._get_bool(
            "ENABLE_PROGRESS_MONITORING", True
        )
        self.require_disk_health_check = self._get_bool(
            "REQUIRE_DISK_HEALTH_CHECK", True
        )
        self.validate_network_stability = self._get_bool(
            "VALIDATE_NETWORK_STABILITY", True
        )
        self.backup_retention_days = self._get_int("BACKUP_RETENTION_DAYS", 30)
        
        # ==== AUTHENTICATION SETTINGS ====
        self.jwt_secret_key = self._get_or_generate_jwt_secret()
        self.jwt_algorithm = self._get_string("JWT_ALGORITHM", "HS256")
        self.access_token_expire_minutes = self._get_int(
            "ACCESS_TOKEN_EXPIRE_MINUTES", 30
        )
        self.refresh_token_expire_days = self._get_int("REFRESH_TOKEN_EXPIRE_DAYS", 7)
        
        # ==== DEFAULT USER CREDENTIALS ====
        self.admin_password = self._get_or_generate_password("ADMIN_PASSWORD")
        self.user_password = self._get_or_generate_password("USER_PASSWORD")
        
        # ==== LEGACY SETTINGS ====
        self.transdock_compose_base = self._get_string(
            "TRANSDOCK_COMPOSE_BASE", "/mnt/cache/compose"
        )
        
        # ==== ZFS SETTINGS ====
        self.zfs_pool = self._get_string("ZFS_POOL", "cache")
        
        # ==== RSYNC SETTINGS ====
        self.rsync_bandwidth_limit = self._get_string("RSYNC_BANDWIDTH_LIMIT", "")
        
        # ==== CORS SETTINGS ====
        self.cors_origins = self._get_string("CORS_ORIGINS", "*").split(",")
        
        # Validate settings
        self._validate_configuration()
    
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
        """Validate configuration values"""
        # Validate log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level not in valid_levels:
            print(f"⚠️  Invalid log level: {self.log_level}, using INFO")
            self.log_level = "INFO"
        
        # Validate JWT algorithm
        secure_algorithms = ["HS256", "HS384", "HS512", "RS256", "RS384", "RS512"]
        if self.jwt_algorithm not in secure_algorithms:
            print(f"⚠️  Invalid JWT algorithm: {self.jwt_algorithm}, using HS256")
            self.jwt_algorithm = "HS256"
        
        # Validate port range
        if not (1 <= self.port <= 65535):
            print(f"⚠️  Invalid port: {self.port}, using default: 8000")
            self.port = 8000
    
    def get_summary(self) -> dict:
        """Get a summary of configuration (without sensitive data)"""
        return {
            "application": {
                "debug": self.debug,
                "testing": self.testing,
                "log_level": self.log_level,
            },
            "server": {
                "host": self.host,
                "port": self.port,
                "enable_docs": self.enable_docs,
            },
            "paths": {
                "local_compose_base_path": self.local_compose_base_path,
                "local_appdata_base_path": self.local_appdata_base_path,
                "default_target_compose_path": self.default_target_compose_path,
                "default_target_appdata_path": self.default_target_appdata_path,
            },
            "safety": {
                "require_explicit_target": self.require_explicit_target,
                "mandatory_pre_migration_snapshots": self.mandatory_pre_migration_snapshots,
                "require_rollback_capability": self.require_rollback_capability,
                "enable_atomic_operations": self.enable_atomic_operations,
                "validate_checksum_integrity": self.validate_checksum_integrity,
                "max_migration_timeout_hours": self.max_migration_timeout_hours,
            },
            "authentication": {
                "jwt_algorithm": self.jwt_algorithm,
                "access_token_expire_minutes": self.access_token_expire_minutes,
                "refresh_token_expire_days": self.refresh_token_expire_days,
            }
        }


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