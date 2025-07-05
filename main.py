#!/usr/bin/env python3
"""
TransDock - Docker Stack Migration Tool
Main entry point for the FastAPI backend service.
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(__file__))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Load .env file from project root
    env_path = Path(__file__).parent / '.env'
    load_dotenv(env_path)
    print(f"✅ Environment variables loaded from: {env_path}")
except ImportError:
    print("⚠️  python-dotenv not installed. Install with: uv add python-dotenv")
except Exception as e:
    print(f"⚠️  Could not load .env file: {e}")

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
