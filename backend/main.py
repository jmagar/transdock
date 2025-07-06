#!/usr/bin/env python3
"""
TransDock Backend API Service

This is the main FastAPI application that brings together all the routers
and services for the TransDock container migration platform.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import configuration
from .config import get_config

# Import services
from .migration_service import MigrationService
from .host_service import HostService
from .security_utils import SecurityValidationError

# Import routers
from .api.routers import (
    auth_router,
    dataset_router,
    snapshot_router,
    pool_router,
    migration_router,
    system_router,
    compose_router,
    host_router
)

# Initialize configuration
config = get_config()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle - startup and shutdown events
    """
    # Startup
    logger.info("Starting TransDock API service...")
    
    yield
    
    # Shutdown
    logger.info("Shutting down TransDock API service...")
    # Add any cleanup code here


# Create FastAPI app
app = FastAPI(
    title="TransDock API",
    description="Enterprise-grade container migration platform with ZFS integration",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)


# Custom exception handler for security validation errors
@app.exception_handler(SecurityValidationError)
async def security_validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={"detail": f"Security validation failed: {str(exc)}"}
    )

# Initialize services
migration_service = MigrationService()
host_service = HostService()

# Include all routers
app.include_router(auth_router)
app.include_router(dataset_router)
app.include_router(snapshot_router)
app.include_router(pool_router)
app.include_router(migration_router.router)
app.include_router(system_router.router)
app.include_router(compose_router.router)
app.include_router(host_router.router)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "TransDock",
        "version": "1.0.0",
        "description": "Docker Stack Migration Tool using ZFS snapshots",
        "docs": "/docs",
        "health": "/api/system/health"
    }


# Legacy datasets endpoint - redirect to new API
@app.get("/datasets")
async def list_datasets():
    """Legacy datasets endpoint - redirects to new API"""
    return JSONResponse(
        status_code=307,
        headers={"Location": "/api/v1/datasets/legacy"},
        content={"message": "This endpoint has moved to /api/v1/datasets/legacy"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.host, port=config.port)
