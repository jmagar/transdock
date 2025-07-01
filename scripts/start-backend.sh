#!/bin/bash

# TransDock Backend Startup Script
# This script starts the TransDock FastAPI backend service using UV

# Set script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Check if UV is available
if ! command -v uv &> /dev/null; then
    echo "Error: UV is required but not installed."
    echo "Install UV with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Check if ZFS is available
if ! command -v zfs &> /dev/null; then
    echo "Warning: ZFS is not available. Some features may not work."
fi

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "Warning: Docker is not available. Some features may not work."
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "Warning: docker-compose is not available. Some features may not work."
fi

# Check if rsync is available
if ! command -v rsync &> /dev/null; then
    echo "Warning: rsync is not available. Fallback transfer method may not work."
fi

echo "Starting TransDock backend service with UV..."
echo "Project directory: $PROJECT_ROOT"
echo "Access the API at: http://localhost:8000"
echo "API documentation at: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop the service"

# Start the FastAPI application using UV
uv run python main.py 