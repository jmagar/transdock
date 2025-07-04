"""
Rate limiting system for TransDock API

This module provides rate limiting functionality including:
- Rate limiting middleware
- Token bucket algorithm implementation
- Per-user and per-IP rate limiting
- Configurable rate limits
- Rate limit headers
"""

import time
import asyncio
from typing import Dict, Callable, Any, Tuple
from functools import wraps
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

class TokenBucket:
    """Token bucket algorithm implementation for rate limiting"""
    
    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.
        
        Args:
            capacity: Maximum number of tokens
            refill_rate: Tokens per second refill rate
        """
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()
        self.lock = asyncio.Lock()
    
    async def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from bucket.
        
        Args:
            tokens: Number of tokens to consume
        
        Returns:
            bool: True if tokens were consumed, False otherwise
        """
        async with self.lock:
            now = time.time()
            # Calculate tokens to add based on time elapsed
            time_elapsed = now - self.last_refill
            tokens_to_add = time_elapsed * self.refill_rate
            
            # Add tokens but don't exceed capacity
            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_refill = now
            
            # Check if we have enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    def remaining_tokens(self) -> int:
        """Get remaining tokens in bucket"""
        return int(self.tokens)
    
    def time_to_refill(self) -> float:
        """Get time until next token is available"""
        if self.tokens >= 1:
            return 0.0
        return (1 - self.tokens) / self.refill_rate

class RateLimitConfig:
    """Rate limit configuration"""
    
    def __init__(self, requests_per_minute: int = 60, burst_size: int = 10):
        """
        Initialize rate limit configuration.
        
        Args:
            requests_per_minute: Requests per minute limit
            burst_size: Burst size for token bucket
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
    
    def get_bucket_config(self) -> Tuple[int, float]:
        """
        Get token bucket configuration.
        
        Returns:
            Tuple[int, float]: (capacity, refill_rate)
        """
        return (self.burst_size, self.requests_per_minute / 60.0)

class RateLimiter:
    """Rate limiter implementation"""
    
    def __init__(self, config: RateLimitConfig, cleanup_interval: float = 300.0, bucket_timeout: float = 600.0):
        """
        Initialize rate limiter.
        
        Args:
            config: Rate limit configuration
            cleanup_interval: Seconds between cleanup runs (default: 300 = 5 minutes)
            bucket_timeout: Seconds of inactivity before bucket removal (default: 600 = 10 minutes)
        """
        self.config = config
        self.buckets: Dict[str, TokenBucket] = {}
        self.cleanup_interval = cleanup_interval
        self.bucket_timeout = bucket_timeout
        self.last_cleanup = time.time()
        self._buckets_lock = asyncio.Lock()
    
    async def is_allowed(self, identifier: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request is allowed.
        
        Args:
            identifier: Unique identifier (IP, user ID, etc.)
        
        Returns:
            Tuple[bool, Dict[str, Any]]: (allowed, rate_limit_info)
        """
        # Check if cleanup is needed
        current_time = time.time()
        if current_time - self.last_cleanup >= self.cleanup_interval:
            await self._cleanup_inactive_buckets()
        
        # Thread-safe access to buckets dictionary
        async with self._buckets_lock:
            if identifier not in self.buckets:
                capacity, refill_rate = self.config.get_bucket_config()
                self.buckets[identifier] = TokenBucket(capacity, refill_rate)
            
            bucket = self.buckets[identifier]
        
        # Keep bucket.consume outside the lock since TokenBucket manages its own locking
        allowed = await bucket.consume()
        
        rate_info = {
            'allowed': allowed,
            'remaining_tokens': bucket.remaining_tokens()
        }
        
        return allowed, rate_info
    
    async def _cleanup_inactive_buckets(self) -> None:
        """
        Remove inactive buckets to prevent memory leaks.
        
        This method removes buckets that haven't been used for bucket_timeout duration
        based on their last_refill timestamp.
        """
        current_time = time.time()
        inactive_identifiers = []
        
        # Thread-safe access to buckets dictionary
        async with self._buckets_lock:
            # Find inactive buckets
            for identifier, bucket in self.buckets.items():
                time_since_last_use = current_time - bucket.last_refill
                if time_since_last_use >= self.bucket_timeout:
                    inactive_identifiers.append(identifier)
            
            # Remove inactive buckets
            for identifier in inactive_identifiers:
                del self.buckets[identifier]
                logger.debug(f"Removed inactive rate limit bucket for identifier: {identifier}")
        
        # Update last cleanup time
        self.last_cleanup = current_time
        
        if inactive_identifiers:
            logger.info(f"Cleaned up {len(inactive_identifiers)} inactive rate limit buckets")

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware"""
    
    def __init__(self, app, rate_limiter: RateLimiter):
        """
        Initialize rate limit middleware.
        
        Args:
            app: FastAPI app
            rate_limiter: Rate limiter instance
        """
        super().__init__(app)
        self.rate_limiter = rate_limiter
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with rate limiting.
        
        Args:
            request: HTTP request
            call_next: Next middleware in chain
        
        Returns:
            Response: HTTP response
        """
        # Skip rate limiting for health checks
        if request.url.path in ['/health', '/docs', '/openapi.json']:
            return await call_next(request)
        
        # Get client identifier
        client_ip = request.client.host if request.client else "unknown"
        
        # Check rate limit
        allowed, rate_info = await self.rate_limiter.is_allowed(client_ip)
        
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": "Too many requests. Please try again later."
                }
            )
        
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(rate_info['remaining_tokens'])
        
        return response

# Predefined rate limit configurations
RATE_LIMIT_CONFIGS = {
    'default': RateLimitConfig(
        requests_per_minute=60,
        burst_size=10
    ),
    'auth': RateLimitConfig(
        requests_per_minute=10,
        burst_size=3
    ),
    'strict': RateLimitConfig(
        requests_per_minute=30,
        burst_size=5
    ),
    'generous': RateLimitConfig(
        requests_per_minute=120,
        burst_size=20
    )
}

# Pre-initialized rate limiters (one per config to maintain state across requests)
RATE_LIMITERS: Dict[str, RateLimiter] = {}

def _initialize_rate_limiters():
    """Initialize rate limiters for all configurations."""
    for config_name, config in RATE_LIMIT_CONFIGS.items():
        RATE_LIMITERS[config_name] = RateLimiter(config)

# Initialize rate limiters at module load time
_initialize_rate_limiters()

# Default rate limiter (for backward compatibility)
default_rate_limiter = RATE_LIMITERS['default']

def rate_limit(config_name: str = 'default'):
    """
    Decorator for applying rate limiting to specific endpoints.
    
    Args:
        config_name: Name of rate limit configuration
    
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get request from args (FastAPI injects it)
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                # No request found, skip rate limiting
                return await func(*args, **kwargs)
            
            # Get pre-created rate limiter (maintains state across requests)
            rate_limiter = RATE_LIMITERS.get(config_name, RATE_LIMITERS['default'])
            
            # Check rate limit
            identifier = f"ip:{request.client.host if request.client else 'unknown'}"
            
            allowed, rate_info = await rate_limiter.is_allowed(identifier)
            
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Please try again later."
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

def create_rate_limit_middleware(config_name: str = 'default'):
    """
    Create rate limit middleware with specific configuration.
    
    Args:
        config_name: Name of rate limit configuration
    
    Returns:
        Configured middleware class
    """
    # Get pre-created rate limiter (maintains state across requests)
    rate_limiter = RATE_LIMITERS.get(config_name, RATE_LIMITERS['default'])
    
    class ConfiguredRateLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Callable) -> Response:
            middleware = RateLimitMiddleware(None, rate_limiter)
            return await middleware.dispatch(request, call_next)
    
    return ConfiguredRateLimitMiddleware 