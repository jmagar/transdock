#!/bin/bash

# TransDock Main Launcher
# Unified script to manage TransDock components

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"

show_help() {
    echo "TransDock - Docker Stack Migration Tool"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  backend     Start the FastAPI backend service"
    echo "  frontend    Start the frontend development server (coming soon)"
    echo "  dev         Start both backend and frontend in development mode"
    echo "  install     Install dependencies for all components"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 backend          # Start only the backend API"
    echo "  $0 dev              # Start full development environment"
    echo ""
}

install_deps() {
    echo "Installing TransDock dependencies..."
    
    # Install backend dependencies
    if [ -f "$SCRIPT_DIR/backend/requirements.txt" ]; then
        echo "Installing backend dependencies..."
        cd "$SCRIPT_DIR/backend"
        pip3 install -r requirements.txt
    fi
    
    # Future: Install frontend dependencies
    # if [ -f "$SCRIPT_DIR/frontend/package.json" ]; then
    #     echo "Installing frontend dependencies..."
    #     cd "$SCRIPT_DIR/frontend"
    #     npm install
    # fi
    
    echo "Dependencies installed successfully!"
}

start_backend() {
    echo "Starting TransDock backend..."
    exec "$SCRIPTS_DIR/start-backend.sh"
}

start_frontend() {
    echo "Frontend is not implemented yet."
    echo "Coming soon: React/Vue.js web interface"
    exit 1
}

start_dev() {
    echo "Starting TransDock in development mode..."
    echo "This will start the backend service."
    echo "Frontend development server will be added in future versions."
    echo ""
    start_backend
}

# Main command processing
case "${1:-help}" in
    backend|api)
        start_backend
        ;;
    frontend|ui)
        start_frontend
        ;;
    dev|development)
        start_dev
        ;;
    install|deps)
        install_deps
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac 