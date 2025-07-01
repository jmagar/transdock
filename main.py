#!/usr/bin/env python3
"""
TransDock - Docker Stack Migration Tool
Main entry point for the FastAPI backend service.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(__file__))

def main():
    """Main entry point for TransDock API service."""
    import uvicorn
    from backend.main import app
    
    print("Starting TransDock API service...")
    print("Access the API at: http://localhost:8000")
    print("API documentation at: http://localhost:8000/docs")
    print("Press Ctrl+C to stop the service")
    
    # Start the FastAPI application
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )

if __name__ == "__main__":
    main()
