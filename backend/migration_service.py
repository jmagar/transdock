"""
DEPRECATED: Monolithic MigrationService

This file has been refactored into focused services for better maintainability.

The monolithic MigrationService (1,454 lines) has been broken down into:

📁 NEW ARCHITECTURE (use migration_service_refactored.py):
├── services/migration_orchestrator.py        # Status & workflow management
├── services/container_discovery_service.py   # Container discovery & analysis  
├── services/container_migration_service.py   # Container migration operations
├── services/snapshot_service.py             # ZFS snapshot management
├── services/system_info_service.py          # System information & capabilities
├── services/compose_stack_service.py        # Legacy compose operations
└── migration_service_refactored.py          # Clean facade (250 lines)

🚨 DO NOT USE THIS FILE - Use migration_service_refactored.py instead!

Benefits of the new architecture:
✅ Single Responsibility Principle - Each service has one clear purpose
✅ Better Testability - Test individual services independently  
✅ Improved Maintainability - Changes isolated to specific services
✅ Enhanced Extensibility - Easy to add new functionality
✅ Dependency Injection - Clear dependencies, easy to mock

To migrate your code:
OLD: from .migration_service import MigrationService
NEW: from .migration_service_refactored import MigrationService

All APIs remain the same - this is a drop-in replacement!
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

class MigrationService:
    """
    DEPRECATED: This class has been refactored.
    
    Use migration_service_refactored.MigrationService instead.
    """
    
    def __init__(self):
        logger.error(
            "DEPRECATED: migration_service.MigrationService is deprecated. "
            "Use migration_service_refactored.MigrationService instead. "
            "Update your imports!"
        )
        raise ImportError(
            "This MigrationService has been refactored. "
            "Please use: from .migration_service_refactored import MigrationService"
        )
    
    def __getattr__(self, name: str) -> Any:
        raise AttributeError(
            f"MigrationService.{name} is not available. "
            "This class has been refactored. Use migration_service_refactored.MigrationService instead."
        )
