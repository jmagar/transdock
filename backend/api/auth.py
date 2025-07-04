"""
JWT Authentication System for TransDock API

This module provides comprehensive JWT-based authentication including:
- JWT token generation and validation
- Password hashing and verification
- User authentication utilities
- Security configurations
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from fastapi import HTTPException, status
from ..security_utils import SecurityUtils
import hashlib
import logging

logger = logging.getLogger(__name__)

# Security configuration
SECRET_KEY = secrets.token_urlsafe(32)  # Generate a secure secret key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Password context for hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Mock user database (in production, this would be a real database)
USERS_DB = {
    "admin": {
        "username": "admin",
        "hashed_password": pwd_context.hash("admin123"),  # Default password
        "email": "admin@transdock.local",
        "full_name": "System Administrator",
        "roles": ["admin", "user"],
        "is_active": True,
        "created_at": datetime.utcnow(),
        "last_login": None
    },
    "user": {
        "username": "user",
        "hashed_password": pwd_context.hash("user123"),  # Default password
        "email": "user@transdock.local",
        "full_name": "Standard User",
        "roles": ["user"],
        "is_active": True,
        "created_at": datetime.utcnow(),
        "last_login": None
    }
}

class UserInDB(BaseModel):
    """User model for database storage"""
    username: str
    email: str
    full_name: str
    roles: List[str]
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    hashed_password: str

class User(BaseModel):
    """User model for API responses (without password)"""
    username: str
    email: str
    full_name: str
    roles: List[str]
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

class UserLogin(BaseModel):
    """User login request model"""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)

class UserCreate(BaseModel):
    """User creation request model"""
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')
    full_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=100)
    roles: List[str] = Field(default=["user"])

class Token(BaseModel):
    """Token response model"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds

class TokenData(BaseModel):
    """Token data model for JWT payload"""
    username: Optional[str] = None
    roles: List[str] = []
    exp: Optional[datetime] = None

class AuthenticationError(Exception):
    """Custom authentication error"""
    pass

class AuthorizationError(Exception):
    """Custom authorization error"""
    pass

class JWTManager:
    """JWT token management utilities"""
    
    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire, "type": "access"})
        
        try:
            encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
            logger.info(f"Created access token for user: {data.get('sub')}")
            return encoded_jwt
        except Exception as e:
            logger.error(f"Failed to create access token: {e}")
            raise HTTPException(status_code=500, detail="Failed to create access token")
    
    @staticmethod
    def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT refresh token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        to_encode.update({"exp": expire, "type": "refresh"})
        
        try:
            encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
            logger.info(f"Created refresh token for user: {data.get('sub')}")
            return encoded_jwt
        except Exception as e:
            logger.error(f"Failed to create refresh token: {e}")
            raise AuthenticationError("Failed to create refresh token")
    
    @staticmethod
    def verify_token(token: str) -> Dict[str, Any]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            
            # Check expiration
            exp = payload.get("exp")
            if exp is None:
                raise HTTPException(status_code=401, detail="Token missing expiration")
            
            if datetime.utcnow() > datetime.fromtimestamp(exp):
                raise HTTPException(status_code=401, detail="Token has expired")
            
            return payload
        except JWTError as e:
            logger.error(f"JWT verification failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")

class PasswordManager:
    """Password hashing and verification utilities"""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash password"""
        try:
            return pwd_context.hash(password)
        except Exception as e:
            logger.error(f"Password hashing failed: {e}")
            raise AuthenticationError("Failed to hash password")
    
    @staticmethod
    def validate_password_strength(password: str) -> bool:
        """Validate password strength requirements"""
        if len(password) < 8:
            return False
        if not any(c.isupper() for c in password):
            return False
        if not any(c.islower() for c in password):
            return False
        if not any(c.isdigit() for c in password):
            return False
        return True

class UserManager:
    """User management utilities"""
    
    @staticmethod
    def get_user(username: str) -> Optional[UserInDB]:
        """Get user from database"""
        try:
            user_data = USERS_DB.get(username)
            if user_data:
                return UserInDB(**user_data)
            return None
        except Exception as e:
            logger.error(f"Failed to get user {username}: {e}")
            return None
    
    @staticmethod
    def authenticate_user(username: str, password: str) -> Optional[UserInDB]:
        """Authenticate user with username and password"""
        try:
            # Validate input
            username = SecurityUtils.validate_username(username)
            
            user = UserManager.get_user(username)
            if not user:
                logger.warning(f"Authentication failed: User {username} not found")
                return None
            
            if not user.is_active:
                logger.warning(f"Authentication failed: User {username} is inactive")
                return None
            
            if not PasswordManager.verify_password(password, user.hashed_password):
                logger.warning(f"Authentication failed: Invalid password for user {username}")
                return None
            
            # Update last login
            USERS_DB[username]["last_login"] = datetime.utcnow()
            
            logger.info(f"User {username} authenticated successfully")
            return user
        except Exception as e:
            logger.error(f"Authentication error for user {username}: {e}")
            return None
    
    @staticmethod
    def create_user(user_data: UserCreate) -> UserInDB:
        """Create new user"""
        try:
            # Validate username
            username = SecurityUtils.validate_username(user_data.username)
            
            # Check if user already exists
            if username in USERS_DB:
                raise AuthenticationError(f"User {username} already exists")
            
            # Validate password strength
            if not PasswordManager.validate_password_strength(user_data.password):
                raise AuthenticationError("Password does not meet strength requirements")
            
            # Hash password
            hashed_password = PasswordManager.get_password_hash(user_data.password)
            
            # Create user
            user = UserInDB(
                username=username,
                email=user_data.email,
                full_name=user_data.full_name,
                roles=user_data.roles,
                is_active=True,
                created_at=datetime.utcnow(),
                hashed_password=hashed_password
            )
            
            # Store in database
            USERS_DB[username] = user.dict()
            
            logger.info(f"Created new user: {username}")
            return user
        except Exception as e:
            logger.error(f"Failed to create user {user_data.username}: {e}")
            raise AuthenticationError(f"Failed to create user: {e}")
    
    @staticmethod
    def update_user(username: str, updates: Dict[str, Any]) -> Optional[UserInDB]:
        """Update user information"""
        try:
            username = SecurityUtils.validate_username(username)
            
            if username not in USERS_DB:
                return None
            
            # Update user data
            for key, value in updates.items():
                if key in ["password"]:
                    # Hash password if updating
                    USERS_DB[username]["hashed_password"] = PasswordManager.get_password_hash(value)
                elif key in ["username", "created_at", "hashed_password"]:
                    # Skip immutable fields
                    continue
                else:
                    USERS_DB[username][key] = value
            
            logger.info(f"Updated user: {username}")
            return UserInDB(**USERS_DB[username])
        except Exception as e:
            logger.error(f"Failed to update user {username}: {e}")
            return None
    
    @staticmethod
    def delete_user(username: str) -> bool:
        """Delete user"""
        try:
            username = SecurityUtils.validate_username(username)
            
            if username not in USERS_DB:
                return False
            
            del USERS_DB[username]
            logger.info(f"Deleted user: {username}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete user {username}: {e}")
            return False
    
    @staticmethod
    def list_users() -> List[User]:
        """List all users (without passwords)"""
        try:
            users = []
            for user_data in USERS_DB.values():
                user = User(**{k: v for k, v in user_data.items() if k != "hashed_password"})
                users.append(user)
            return users
        except Exception as e:
            logger.error(f"Failed to list users: {e}")
            return []

class AuthorizationManager:
    """Authorization and role management utilities"""
    
    @staticmethod
    def check_permission(user_roles: List[str], required_roles: List[str]) -> bool:
        """Check if user has required roles"""
        if not required_roles:
            return True
        
        # Admin role has all permissions
        if "admin" in user_roles:
            return True
        
        # Check if user has any of the required roles
        return any(role in user_roles for role in required_roles)
    
    @staticmethod
    def check_resource_access(user: UserInDB, resource: str, action: str) -> bool:
        """Check if user can access specific resource with specific action"""
        try:
            # Admin can access everything
            if "admin" in user.roles:
                return True
            
            # Define resource-based permissions
            permissions = {
                "datasets": {
                    "read": ["user", "admin"],
                    "write": ["admin"],
                    "delete": ["admin"]
                },
                "snapshots": {
                    "read": ["user", "admin"],
                    "write": ["admin"],
                    "delete": ["admin"]
                },
                "pools": {
                    "read": ["user", "admin"],
                    "write": ["admin"],
                    "delete": ["admin"]
                },
                "system": {
                    "read": ["admin"],
                    "write": ["admin"],
                    "delete": ["admin"]
                }
            }
            
            resource_permissions = permissions.get(resource, {})
            required_roles = resource_permissions.get(action, ["admin"])
            
            return AuthorizationManager.check_permission(user.roles, required_roles)
        except Exception as e:
            logger.error(f"Authorization check failed: {e}")
            return False

def create_tokens_for_user(user: UserInDB) -> Token:
    """Create access and refresh tokens for user"""
    try:
        # Create token data
        token_data = {
            "sub": user.username,
            "roles": user.roles,
            "email": user.email,
            "full_name": user.full_name
        }
        
        # Create tokens
        access_token = JWTManager.create_access_token(token_data)
        refresh_token = JWTManager.create_refresh_token(token_data)
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    except Exception as e:
        logger.error(f"Failed to create tokens for user {user.username}: {e}")
        raise AuthenticationError(f"Failed to create tokens: {e}")

def validate_token_and_get_user(token: str) -> UserInDB:
    """Validate token and return user"""
    try:
        payload = JWTManager.verify_token(token)
        username = payload.get("sub")
        
        if username is None:
            raise AuthenticationError("Invalid token payload")
        
        user = UserManager.get_user(username)
        if user is None:
            raise AuthenticationError("User not found")
        
        if not user.is_active:
            raise AuthenticationError("User account is inactive")
        
        return user
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        raise AuthenticationError(f"Token validation failed: {e}")

# Initialize default admin user if not exists
def initialize_default_users():
    """Initialize default users if they don't exist"""
    try:
        logger.info("Initializing default users...")
        # Users are already initialized in USERS_DB
        logger.info("Default users initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize default users: {e}")

# Initialize on module load
initialize_default_users() 