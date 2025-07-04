"""
Middleware for API error handling and common functionality.
"""
from typing import Dict, Any, Optional
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import time
from datetime import datetime, timezone

from ..zfs_operations.core.exceptions.zfs_exceptions import ZFSException
from ..zfs_operations.core.exceptions.validation_exceptions import ValidationException
from .models import APIError, ValidationError


logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for handling API errors consistently."""
    
    async def dispatch(self, request: Request, call_next):
        """Process the request and handle errors."""
        try:
            response = await call_next(request)
            return response
        except ZFSException as e:
            logger.error(f"ZFS error in {request.url.path}: {e}")
            return JSONResponse(
                status_code=400,
                content=APIError(
                    error=e.error_code or "ZFS_ERROR",
                    message=str(e),
                    details=e.details
                ).dict()
            )
        except ValidationException as e:
            logger.error(f"Validation error in {request.url.path}: {e}")
            return JSONResponse(
                status_code=422,
                content=ValidationError(
                    error="VALIDATION_ERROR",
                    message=str(e)
                ).dict()
            )
        except Exception as e:
            logger.error(f"Unexpected error in {request.url.path}: {e}")
            return JSONResponse(
                status_code=500,
                content=APIError(
                    error="INTERNAL_SERVER_ERROR",
                    message="An unexpected error occurred"
                ).dict()
            )


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging API requests."""
    
    async def dispatch(self, request: Request, call_next):
        """Log the request and response."""
        start_time = time.time()
        
        # Log the request
        logger.info(f"API Request: {request.method} {request.url.path}")
        
        response = await call_next(request)
        
        # Log the response
        process_time = time.time() - start_time
        logger.info(f"API Response: {response.status_code} - {process_time:.4f}s")
        
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware for adding security headers."""
    
    async def dispatch(self, request: Request, call_next):
        """Add security headers to response."""
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response


def create_error_response(error: Exception, status_code: int = 500) -> JSONResponse:
    """Create a standardized error response."""
    if isinstance(error, ZFSException):
        return JSONResponse(
            status_code=400,
            content=APIError(
                error=error.error_code or "ZFS_ERROR",
                message=str(error),
                details=error.details
            ).dict()
        )
    elif isinstance(error, ValidationException):
        return JSONResponse(
            status_code=422,
            content=ValidationError(
                error="VALIDATION_ERROR",
                message=str(error)
            ).dict()
        )
    else:
        return JSONResponse(
            status_code=status_code,
            content=APIError(
                error="INTERNAL_SERVER_ERROR",
                message=str(error)
            ).dict()
        )


def create_success_response(data: Dict[str, Any], message: Optional[str] = None) -> Dict[str, Any]:
    """Create a standardized success response."""
    response = {
        "success": True,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    if message:
        response["message"] = message
    return response


def create_list_response(items: list, count: Optional[int] = None) -> Dict[str, Any]:
    """Create a standardized list response."""
    return {
        "success": True,
        "items": items,
        "count": count if count is not None else len(items),
        "timestamp": datetime.now(timezone.utc).isoformat()
    } 