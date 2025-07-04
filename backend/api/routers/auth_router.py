"""
Authentication router for TransDock API

This module provides authentication endpoints including:
- User login and token generation
- Token refresh
- User management (CRUD operations)
- User profile management
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status

from pydantic import BaseModel

from ..auth import (
    User, UserInDB, UserLogin, UserCreate, Token, 
    UserManager, JWTManager, create_tokens_for_user,
    PasswordManager, invalidate_token, get_blacklist_stats
)
from ..dependencies import (
    get_current_active_user, get_token_from_request,
    require_admin
)
from ..rate_limiting import rate_limit

router = APIRouter(prefix="/auth", tags=["Authentication"])

def _user_from_db(user_db: UserInDB) -> User:
    """
    Convert UserInDB instance to User instance.
    
    This helper function reduces code duplication by centralizing the conversion
    of UserInDB objects (which include sensitive data like hashed passwords)
    to User objects (which are safe for API responses).
    
    Args:
        user_db: UserInDB instance from the database
        
    Returns:
        User: User instance suitable for API responses
    """
    return User(
        username=user_db.username,
        email=user_db.email,
        full_name=user_db.full_name,
        roles=user_db.roles,
        is_active=user_db.is_active,
        created_at=user_db.created_at,
        last_login=user_db.last_login
    )

class LoginResponse(BaseModel):
    """Login response model"""
    user: User
    token: Token
    message: str = "Login successful"

class RefreshTokenRequest(BaseModel):
    """Refresh token request model"""
    refresh_token: str

class ChangePasswordRequest(BaseModel):
    """Change password request model"""
    current_password: str
    new_password: str

class UserUpdateRequest(BaseModel):
    """User update request model"""
    email: Optional[str] = None
    full_name: Optional[str] = None
    roles: Optional[List[str]] = None
    is_active: Optional[bool] = None

@router.post("/login", response_model=LoginResponse)
@rate_limit(config_name='auth')
async def login(user_credentials: UserLogin):
    """
    Authenticate user and return JWT tokens.
    
    Args:
        user_credentials: Username and password
    
    Returns:
        LoginResponse: User information and JWT tokens
    
    Raises:
        HTTPException: If authentication fails
    """
    try:
        # Authenticate user
        user = UserManager.authenticate_user(
            user_credentials.username, 
            user_credentials.password
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create tokens
        tokens = create_tokens_for_user(user)
        
        # Convert to User model (without password)
        user_response = _user_from_db(user)
        
        return LoginResponse(
            user=user_response,
            token=tokens,
            message="Login successful"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        ) from e

@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_request: RefreshTokenRequest):
    """
    Refresh JWT access token using refresh token.
    
    Args:
        refresh_request: Refresh token request
    
    Returns:
        Token: New access and refresh tokens
    
    Raises:
        HTTPException: If refresh fails
    """
    try:
        # Verify refresh token
        payload = JWTManager.verify_token(refresh_request.refresh_token)
        
        # Check if it's a refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        username = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )
        
        # Get user
        user = UserManager.get_user(username)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # Blacklist the old refresh token to prevent reuse
        invalidate_token(refresh_request.refresh_token)
        
        # Create new tokens
        tokens = create_tokens_for_user(user)
        return tokens
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {str(e)}"
        ) from e

@router.get("/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """
    Get current user information.
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        User: Current user information
    """
    return current_user

@router.put("/me", response_model=User)
async def update_current_user(
    updates: UserUpdateRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Update current user information.
    
    Args:
        updates: User update data
        current_user: Current authenticated user
    
    Returns:
        User: Updated user information
    
    Raises:
        HTTPException: If update fails
    """
    try:
        # Prepare update data
        update_data = {}
        if updates.email is not None:
            update_data["email"] = updates.email
        if updates.full_name is not None:
            update_data["full_name"] = updates.full_name
        
        # Only admin can update roles and active status
        if "admin" in current_user.roles:
            if updates.roles is not None:
                update_data["roles"] = updates.roles
            if updates.is_active is not None:
                update_data["is_active"] = updates.is_active
        
        # Update user
        updated_user = UserManager.update_user(current_user.username, update_data)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return _user_from_db(updated_user)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User update failed: {str(e)}"
        ) from e

@router.post("/change-password")
async def change_password(
    password_change: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Change current user password.
    
    Args:
        password_change: Current and new password
        current_user: Current authenticated user
    
    Returns:
        Dict: Success message
    
    Raises:
        HTTPException: If password change fails
    """
    try:
        # Get user from database
        user = UserManager.get_user(current_user.username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Verify current password
        if not PasswordManager.verify_password(password_change.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )
        
        # Validate new password strength with detailed error messages
        password_errors = PasswordManager.get_password_validation_errors(password_change.new_password)
        if password_errors:
            error_message = "Password validation failed. Please ensure your password meets the following requirements: " + "; ".join(password_errors)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
        
        # Update password
        updated_user = UserManager.update_user(current_user.username, {"password": password_change.new_password})
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update password"
            )
        
        return {"message": "Password changed successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Password change failed: {str(e)}"
        ) from e

# Admin-only endpoints
@router.get("/users", response_model=List[User])
async def list_users(current_user: User = Depends(require_admin())):
    """
    List all users (admin only).
    
    Args:
        current_user: Current authenticated admin user
    
    Returns:
        List[User]: List of all users
    """
    try:
        users = UserManager.list_users()
        return users
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list users: {str(e)}"
        ) from e

@router.post("/users", response_model=User)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(require_admin())
):
    """
    Create new user (admin only).
    
    Args:
        user_data: User creation data
        current_user: Current authenticated admin user
    
    Returns:
        User: Created user information
    
    Raises:
        HTTPException: If user creation fails
    """
    try:
        new_user = UserManager.create_user(user_data)
        return _user_from_db(new_user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User creation failed: {str(e)}"
        ) from e

@router.get("/users/{username}", response_model=User)
async def get_user(
    username: str,
    current_user: User = Depends(require_admin())
):
    """
    Get user by username (admin only).
    
    Args:
        username: Username to get
        current_user: Current authenticated admin user
    
    Returns:
        User: User information
    
    Raises:
        HTTPException: If user not found
    """
    try:
        user = UserManager.get_user(username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return _user_from_db(user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user: {str(e)}"
        ) from e

@router.put("/users/{username}", response_model=User)
async def update_user(
    username: str,
    updates: UserUpdateRequest,
    current_user: User = Depends(require_admin())
):
    """
    Update user (admin only).
    
    Args:
        username: Username to update
        updates: User update data
        current_user: Current authenticated admin user
    
    Returns:
        User: Updated user information
    
    Raises:
        HTTPException: If update fails
    """
    try:
        # Prepare update data
        update_data = {}
        if updates.email is not None:
            update_data["email"] = updates.email
        if updates.full_name is not None:
            update_data["full_name"] = updates.full_name
        if updates.roles is not None:
            update_data["roles"] = updates.roles
        if updates.is_active is not None:
            update_data["is_active"] = updates.is_active
        
        # Update user
        updated_user = UserManager.update_user(username, update_data)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return _user_from_db(updated_user)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User update failed: {str(e)}"
        ) from e

@router.delete("/users/{username}")
async def delete_user(
    username: str,
    current_user: User = Depends(require_admin())
):
    """
    Delete user (admin only).
    
    Args:
        username: Username to delete
        current_user: Current authenticated admin user
    
    Returns:
        Dict: Success message
    
    Raises:
        HTTPException: If deletion fails
    """
    try:
        # Prevent self-deletion
        if username == current_user.username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account"
            )
        
        success = UserManager.delete_user(username)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return {"message": f"User {username} deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User deletion failed: {str(e)}"
        ) from e

@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_active_user),
    token: str = Depends(get_token_from_request)
):
    """
    Logout user and invalidate token.
    
    This endpoint properly invalidates the JWT token by adding it to a blacklist,
    ensuring that the token cannot be used for future authentication.
    
    Args:
        current_user: Current authenticated user
        token: JWT token to invalidate
    
    Returns:
        Dict: Success message with invalidation status
    
    Raises:
        HTTPException: If token invalidation fails
    """
    try:
        # Invalidate the token by adding it to the blacklist
        success = invalidate_token(token)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to invalidate token"
            )
        
        return {
            "message": "Logged out successfully",
            "user": current_user.username,
            "token_invalidated": True
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logout failed: {str(e)}"
        ) from e

@router.get("/validate")
async def validate_token(current_user: User = Depends(get_current_active_user)):
    """
    Validate current token.
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        Dict: Token validation result
    """
    return {
        "valid": True,
        "user": current_user.username,
        "roles": current_user.roles,
        "message": "Token is valid"
    }

@router.get("/blacklist-stats")
async def get_token_blacklist_stats(current_user: User = Depends(require_admin())):
    """
    Get token blacklist statistics (admin only).
    
    This endpoint provides information about the current state of the token blacklist,
    including the number of blacklisted tokens and cleanup status.
    
    Args:
        current_user: Current authenticated admin user
    
    Returns:
        Dict: Blacklist statistics
    """
    try:
        stats = get_blacklist_stats()
        return {
            "blacklist_stats": stats,
            "message": "Blacklist statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get blacklist stats: {str(e)}"
        ) from e 