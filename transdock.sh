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
    echo "  sync        Sync virtual environment with UV"
    echo "  shell       Open UV shell with activated virtual environment"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 backend          # Start only the backend API"
    echo "  $0 dev              # Start full development environment"
    echo "  $0 sync             # Update dependencies"
    echo ""
}

install_deps() {
    echo "Installing TransDock dependencies with UV..."
    
    # Check if UV is available
    if ! command -v uv &> /dev/null; then
        echo "Error: UV is required but not installed."
        echo "Install UV with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
    
    cd "$SCRIPT_DIR"
    
    # Sync the virtual environment
    echo "Syncing virtual environment..."
    uv sync
    
    # Future: Install frontend dependencies
    # if [ -f "$SCRIPT_DIR/frontend/package.json" ]; then
    #     echo "Installing frontend dependencies..."
    #     cd "$SCRIPT_DIR/frontend"
    #     npm install
    # fi
    
    echo "Dependencies installed successfully!"
}

sync_deps() {
    echo "Syncing TransDock dependencies with UV..."
    
    if ! command -v uv &> /dev/null; then
        echo "Error: UV is required but not installed."
        exit 1
    fi
    
    cd "$SCRIPT_DIR"
    uv sync
    echo "Dependencies synced successfully!"
}

start_shell() {
    echo "Starting UV shell with activated virtual environment..."
    
    if ! command -v uv &> /dev/null; then
        echo "Error: UV is required but not installed."
        exit 1
    fi
    
    cd "$SCRIPT_DIR"
    exec uv run bash
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
    sync)
        sync_deps
        ;;
    shell)
        start_shell
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