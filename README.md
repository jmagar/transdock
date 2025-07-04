# TransDock - Docker Stack Migration Tool

TransDock is a powerful tool for migrating Docker Compose stacks between machines using ZFS snapshots. It's designed for Unraid environments but works with any ZFS-enabled system.

## ✨ Features

- **Automated Migration**: Migrate entire Docker Compose stacks with a single API call
- **ZFS Integration**: Leverages ZFS snapshots for consistent data transfer
- **Intelligent Transfer**: Automatically chooses between ZFS send/receive or rsync
- **Volume Management**: Automatically detects and converts directories to ZFS datasets
- **Path Translation**: Updates Docker Compose files with new paths on target machine
- **Migration Verification**: Verifies successful container deployment with smart container name detection
- **Security Validation**: Comprehensive input validation and sanitization to prevent attacks
- **RESTful API**: Fully featured FastAPI backend ready for frontend integration
- **Progress Tracking**: Real-time migration progress and status updates
- **Error Recovery**: Comprehensive error handling with rollback capabilities
- **Migration Control**: Cancel running migrations with cleanup operations

## 🔐 Security Features

TransDock includes enterprise-grade security validation to protect against common attack vectors:

- **Path Traversal Prevention**: All file paths are sanitized and validated against directory traversal attacks
- **Command Injection Protection**: User inputs are escaped and validated to prevent command injection
- **SSH Security**: Hostnames and usernames validated with strict patterns to prevent SSH injection
- **ZFS Command Validation**: All ZFS operations validated against allowed commands and parameters
- **Input Sanitization**: Comprehensive validation of all API inputs for format, length, and content
- **Smart Container Detection**: Secure container name resolution prevents injection through compose service names

Security validation failures return detailed error messages with `422 Unprocessable Entity` status codes.

## 🏗️ Project Structure

```
transdock/
├── backend/              # FastAPI backend service
│   ├── main.py          # API application entry point
│   ├── models.py        # Pydantic data models
│   ├── migration_service.py  # Core migration orchestration
│   ├── zfs_ops.py       # ZFS operations (snapshots, send/receive)
│   ├── docker_ops.py    # Docker Compose parsing and control
│   ├── transfer_ops.py  # Data transfer operations
│   ├── example.py       # API client example
│   └── requirements.txt # Python dependencies
├── frontend/            # Web UI (planned)
│   └── README.md        # Frontend development guide
├── scripts/             # Utility scripts
│   └── start-backend.sh # Backend startup script
├── docs/                # Documentation
│   └── API.md          # Complete API documentation
├── main.py              # UV entry point
├── pyproject.toml       # UV project configuration
├── transdock.sh         # Main launcher script
└── README.md           # This file
```

## 🚀 Quick Start

### Prerequisites

- **UV** - Modern Python package manager ([install here](https://docs.astral.sh/uv/getting-started/installation/))
- **ZFS** installed and configured
- **Docker** and **docker-compose**
- **SSH access** to target machines
- **rsync** for fallback transfers

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/jmagar/transdock.git
   cd transdock
   ```

2. **Install dependencies with UV:**
   ```bash
   ./transdock.sh install
   # or directly: uv sync
   ```

3. **Start the backend service:**
   ```bash
   ./transdock.sh backend
   ```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

### Alternative Startup Methods

```bash
# Direct backend startup
./scripts/start-backend.sh

# Development mode (same as backend for now)
./transdock.sh dev

# Update dependencies
./transdock.sh sync

# Open UV shell with virtual environment
./transdock.sh shell

# Help and available commands
./transdock.sh help
```

### UV Commands

TransDock uses **UV** for modern Python dependency management:

```bash
# Install/update all dependencies
uv sync

# Run the application
uv run python main.py

# Run any command in the virtual environment
uv run <command>

# Add new dependencies
uv add <package>

# Open shell with activated environment
uv shell
```

## 📡 API Usage

### Basic Migration Example

```python
import requests

# Start a migration
response = requests.post("http://localhost:8000/migrations", json={
    "compose_dataset": "authelia",
    "target_host": "192.168.1.100", 
    "target_base_path": "/home/jmagar",
    "ssh_user": "root"
})

migration_id = response.json()["migration_id"]

# Check status
status = requests.get(f"http://localhost:8000/migrations/{migration_id}")
print(f"Status: {status.json()['status']} - {status.json()['progress']}%")
```

### Using the Example Client

```bash
cd backend
uv run python example.py
```

See the [API Documentation](docs/API.md) for complete endpoint details.

## 🔧 Configuration

### Default Paths

- **Compose Base**: `/mnt/cache/compose` (Unraid default)
- **AppData Base**: `/mnt/cache/appdata` (Unraid default)
- **ZFS Pool**: `cache` (Unraid cache pool)

### Environment Variables

Set these in your shell or startup script:

```bash
export TRANSDOCK_COMPOSE_BASE="/custom/compose/path"
export TRANSDOCK_APPDATA_BASE="/custom/appdata/path"
export TRANSDOCK_ZFS_POOL="custom-pool"
```

## 🔄 Migration Process

TransDock follows a 13-step migration workflow:

1. **Validation** - Check inputs and ZFS availability
2. **Parsing** - Parse docker-compose file
3. **Analysis** - Extract volume mounts and dependencies
4. **Stopping** - Stop source Docker stack
5. **Dataset Conversion** - Convert directories to ZFS datasets
6. **Snapshotting** - Create atomic ZFS snapshots
7. **Capability Check** - Determine target transfer method
8. **Transfer Method** - Choose ZFS send or rsync
9. **Data Transfer** - Move data to target machine
10. **Path Updates** - Update compose file paths
11. **Stack Startup** - Start stack on target machine
12. **Cleanup** - Remove temporary snapshots
13. **Verification** - Verify container deployment and health

## 🎯 Use Cases

### Unraid to Unraid Migration
```bash
# Migrate between Unraid servers with ZFS cache pools
curl -X POST "http://localhost:8000/migrations" \
  -H "Content-Type: application/json" \
  -d '{
    "compose_dataset": "nextcloud",
    "target_host": "unraid2.local",
    "target_base_path": "/mnt/cache"
  }'
```

### Unraid to Linux Server
```bash
# Migrate to non-ZFS system (uses rsync)
curl -X POST "http://localhost:8000/migrations" \
  -H "Content-Type: application/json" \
  -d '{
    "compose_dataset": "homeassistant",
    "target_host": "ubuntu-server.local",
    "target_base_path": "/opt/docker",
    "force_rsync": true
  }'
```

## 🌐 Frontend Development

The web UI is planned for future development. See [frontend/README.md](frontend/README.md) for the roadmap and setup instructions.

**Planned features:**
- Migration wizard with guided setup
- Real-time progress dashboard
- Stack browser and analyzer
- Migration history and logs
- SSH key management

## 📖 Documentation

- [API Documentation](docs/API.md) - Complete API reference
- [Frontend Roadmap](frontend/README.md) - Web UI development plan
- Backend code is extensively commented for developers

## 🤝 Contributing

Contributions are welcome! Areas needing development:

- **Frontend Implementation** - React/Vue.js web interface
- **Authentication** - API key or OAuth support
- **Monitoring** - Prometheus metrics and alerting
- **Testing** - Unit and integration tests
- **Docker Support** - Containerized deployment options

## 📄 License

This project is open source. See the repository for license details.

## 🆘 Support

- **Issues**: Report bugs and feature requests on GitHub
- **API Docs**: http://localhost:8000/docs when running
- **Examples**: See `backend/example.py` for usage patterns

---

**TransDock v1.0** - Built for reliable Docker stack migrations with ZFS snapshots 