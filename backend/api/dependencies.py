"""
Dependencies for API endpoints.
"""
from typing import Dict, Any, Optional, List
from functools import lru_cache
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..zfs_operations.factories.service_factory import ServiceFactory, create_default_service_factory
from ..zfs_operations.services.dataset_service import DatasetService
from ..zfs_operations.services.snapshot_service import SnapshotService
from ..zfs_operations.services.pool_service import PoolService
from .auth import JWTManager, UserManager, User, AuthorizationManager, invalidate_token


# Global service factory instance
_service_factory: Optional[ServiceFactory] = None


@lru_cache()
def get_service_factory() -> ServiceFactory:
    """Get the global service factory instance."""
    global _service_factory
    if _service_factory is None:
        _service_factory = create_default_service_factory()
    return _service_factory


async def get_dataset_service() -> DatasetService:
    """Get a DatasetService instance."""
    return await get_service_factory().create_dataset_service()


async def get_snapshot_service() -> SnapshotService:
    """Get a SnapshotService instance."""
    return await get_service_factory().create_snapshot_service()


async def get_pool_service() -> PoolService:
    """Get a PoolService instance."""
    return await get_service_factory().create_pool_service()


async def get_all_services() -> Dict[str, Any]:
    """Get all services as a dictionary."""
    return {
        'dataset_service': await get_dataset_service(),
        'snapshot_service': await get_snapshot_service(),
        'pool_service': await get_pool_service()
    }


def configure_services(config: Dict[str, Any]):
    """Configure services with custom settings."""
    global _service_factory
    _service_factory = ServiceFactory(config)
    # Clear the cache to force recreation
    get_service_factory.cache_clear()


# Authentication dependencies
security = HTTPBearer()
logger = logging.getLogger(__name__)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """
    Dependency to get current authenticated user from JWT token.
    
    Args:
        credentials: HTTP authorization credentials
    
    Returns:
        User: Current authenticated user
    
    Raises:
        HTTPException: If authentication fails
    """
    try:
        token = credentials.credentials
        payload = JWTManager.verify_token(token)
        username = payload.get("sub")
        
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user = UserManager.get_user(username)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Convert to User model (without password)
        return User(
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            roles=user.roles,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=user.last_login
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to get current active user.
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        User: Current active user
    
    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
    return current_user


async def get_token_from_request(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Dependency to extract the raw JWT token from the request.
    
    Args:
        credentials: HTTP authorization credentials
    
    Returns:
        str: Raw JWT token
    
    Raises:
        HTTPException: If no token is provided
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def require_roles(required_roles: List[str]):
    """
    Dependency factory to require specific roles.
    
    Args:
        required_roles: List of required roles
    
    Returns:
        Function that checks user roles
    """
    async def check_roles(current_user: User = Depends(get_current_active_user)) -> User:
        if not AuthorizationManager.check_permission(current_user.roles, required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {required_roles}"
            )
        return current_user
    
    return check_roles


def require_admin():
    """
    Dependency to require admin role.
    
    Returns:
        Function that checks for admin role
    """
    return require_roles(["admin"])


def require_user():
    """
    Dependency to require user role (or admin).
    
    Returns:
        Function that checks for user role
    """
    return require_roles(["user", "admin"]) 