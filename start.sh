#!/bin/bash

# TransDock Startup Script
# This script starts the TransDock migration service

# Set script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

# Check if pip is available
if ! command -v pip3 &> /dev/null; then
    echo "Error: pip3 is required but not installed."
    exit 1
fi

# Install dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "Installing Python dependencies..."
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install dependencies."
        exit 1
    fi
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

echo "Starting TransDock migration service..."
echo "Access the API at: http://localhost:8000"
echo "API documentation at: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop the service"

# Start the FastAPI application
python3 main.py 