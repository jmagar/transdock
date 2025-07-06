"""
API routers for TransDock.
"""

from .dataset_router import router as dataset_router
from .snapshot_router import router as snapshot_router  
from .pool_router import router as pool_router
from .auth_router import router as auth_router

# Import the new routers we created
from . import migration_router
from . import system_router
from . import compose_router
from . import host_router

__all__ = [
    "dataset_router",
    "snapshot_router", 
    "pool_router",
    "auth_router",
    "migration_router",
    "system_router",
    "compose_router",
    "host_router"
] 