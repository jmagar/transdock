"""
Authentication router for TransDock API

This module provides authentication endpoints including:
- User login and token generation
- Token refresh
- User management (CRUD operations)
- User profile management
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from ..auth import (
    User, UserLogin, UserCreate, Token, 
    UserManager, JWTManager, create_tokens_for_user,
    PasswordManager, AuthorizationManager
)
from ..dependencies import (
    get_current_user, get_current_active_user, 
    require_admin, require_user, security
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

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
        user_response = User(
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            roles=user.roles,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=user.last_login
        )
        
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
        )

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
        
        # Create new tokens
        tokens = create_tokens_for_user(user)
        return tokens
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {str(e)}"
        )

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
        
        return User(
            username=updated_user.username,
            email=updated_user.email,
            full_name=updated_user.full_name,
            roles=updated_user.roles,
            is_active=updated_user.is_active,
            created_at=updated_user.created_at,
            last_login=updated_user.last_login
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User update failed: {str(e)}"
        )

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
        
        # Validate new password strength
        if not PasswordManager.validate_password_strength(password_change.new_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password does not meet strength requirements"
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
        )

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
        )

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
        return User(
            username=new_user.username,
            email=new_user.email,
            full_name=new_user.full_name,
            roles=new_user.roles,
            is_active=new_user.is_active,
            created_at=new_user.created_at,
            last_login=new_user.last_login
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User creation failed: {str(e)}"
        )

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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user: {str(e)}"
        )

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
        
        return User(
            username=updated_user.username,
            email=updated_user.email,
            full_name=updated_user.full_name,
            roles=updated_user.roles,
            is_active=updated_user.is_active,
            created_at=updated_user.created_at,
            last_login=updated_user.last_login
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"User update failed: {str(e)}"
        )

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
        )

@router.post("/logout")
async def logout(current_user: User = Depends(get_current_active_user)):
    """
    Logout user (invalidate token).
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        Dict: Success message
    
    Note:
        In a production environment, you would typically maintain a blacklist
        of invalidated tokens or use shorter token expiration times.
    """
    return {"message": "Logged out successfully"}

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