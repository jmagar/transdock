# TransDock - Multi-Host Docker Stack Migration Tool

TransDock is a powerful tool for migrating Docker Compose stacks between any machines using ZFS snapshots. With full multi-host support, it can migrate stacks between any combination of local and remote hosts without hardcoded configuration paths.

## ✨ Features

- **Multi-Host Support**: Source and destination can be any host accessible via SSH
- **Dynamic Host Management**: No hardcoded paths - everything specified via API calls
- **Remote Stack Management**: List, analyze, start/stop stacks on any remote host
- **Host Capability Discovery**: Automatically detect Docker, ZFS, and path availability
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

## 🌐 Multi-Host Architecture

TransDock supports all migration scenarios:
- **Local to Remote**: Migrate from local host to remote host
- **Remote to Local**: Migrate from remote host to local host  
- **Remote to Remote**: Migrate between two remote hosts
- **Local to Local**: Migrate within the same host (path changes)

Both ZFS and rsync transfer methods work across all host combinations.

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
│   ├── host_service.py  # Multi-host operations and SSH management
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
- **ZFS** installed and configured (optional - rsync fallback available)
- **Docker** and **docker-compose**
- **SSH access** to target/source machines
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

### Multi-Host Migration Examples

#### Local to Remote Migration
```python
import requests

# Migrate from local to remote host
response = requests.post("http://localhost:8000/migrations", json={
    "compose_dataset": "authelia",
    "target_host": "remote-server.local", 
    "target_base_path": "/opt/docker",
    "ssh_user": "root"
})

migration_id = response.json()["migration_id"]
```

#### Remote to Remote Migration
```python
# Migrate between two remote hosts
response = requests.post("http://localhost:8000/migrations", json={
    "compose_dataset": "nextcloud",
    "target_host": "dest-server.local",
    "target_base_path": "/home/docker",
    "ssh_user": "root",
    "source_host": "source-server.local",
    "source_ssh_user": "root",
    "source_compose_path": "/mnt/cache/compose",
    "source_appdata_path": "/mnt/cache/appdata"
})
```

#### Host Capability Discovery
```python
# Check what's available on a remote host
response = requests.post("http://localhost:8000/api/hosts/validate", json={
    "hostname": "remote-server.local",
    "ssh_user": "root",
    "ssh_port": 22
})

capabilities = response.json()
print(f"Docker: {capabilities['docker_available']}")
print(f"ZFS: {capabilities['zfs_available']}")
print(f"Compose paths: {capabilities['compose_paths']}")
```

#### Remote Stack Management
```python
# List stacks on remote host
response = requests.get(
    "http://localhost:8000/api/hosts/remote-server.local/compose/stacks",
    params={
        "compose_path": "/mnt/cache/compose",
        "ssh_user": "root"
    }
)

stacks = response.json()["stacks"]
for stack in stacks:
    print(f"Stack: {stack['name']} - Status: {stack['status']}")
```

### Migration Status Tracking

```python
# Check migration progress
status = requests.get(f"http://localhost:8000/migrations/{migration_id}")
print(f"Status: {status.json()['status']} - {status.json()['progress']}%")

# Cancel if needed
requests.post(f"http://localhost:8000/migrations/{migration_id}/cancel")
```

### Using the Example Client

```bash
cd backend
uv run python example.py
```

See the [API Documentation](docs/API.md) for complete endpoint details.

## 🔄 Migration Process

TransDock follows a 13-step migration workflow:

1. **Validation** - Check inputs, SSH connectivity, and host capabilities
2. **Parsing** - Parse docker-compose file from source location
3. **Analysis** - Extract volume mounts and dependencies
4. **Stopping** - Stop source Docker stack
5. **Dataset Conversion** - Convert directories to ZFS datasets
6. **Snapshotting** - Create atomic ZFS snapshots
7. **Capability Check** - Determine optimal transfer method
8. **Transfer Method** - Choose ZFS send or rsync based on host capabilities
9. **Data Transfer** - Move data between hosts (local/remote combinations)
10. **Path Updates** - Update compose file paths for target environment
11. **Stack Startup** - Start stack on target machine
12. **Cleanup** - Remove temporary snapshots and files
13. **Verification** - Verify container deployment and health

## 🎯 Multi-Host Use Cases

### Unraid to Unraid Migration
```bash
# Migrate between Unraid servers with ZFS cache pools
curl -X POST "http://localhost:8000/migrations" \
  -H "Content-Type: application/json" \
  -d '{
    "compose_dataset": "nextcloud",
    "target_host": "unraid2.local",
    "target_base_path": "/mnt/cache",
    "ssh_user": "root"
  }'
```

### Unraid to Linux Server Migration
```bash
# Migrate to non-ZFS system (uses rsync automatically)
curl -X POST "http://localhost:8000/migrations" \
  -H "Content-Type: application/json" \
  -d '{
    "compose_dataset": "homeassistant",
    "target_host": "ubuntu-server.local",
    "target_base_path": "/opt/docker",
    "ssh_user": "root"
  }'
```

### Remote to Remote Migration
```bash
# Migrate between two remote hosts
curl -X POST "http://localhost:8000/migrations" \
  -H "Content-Type: application/json" \
  -d '{
    "compose_dataset": "plex",
    "target_host": "new-server.local",
    "target_base_path": "/media/docker",
    "ssh_user": "root",
    "source_host": "old-server.local",
    "source_ssh_user": "root",
    "source_compose_path": "/opt/compose",
    "source_appdata_path": "/opt/appdata"
  }'
```

### Host Management Examples
```bash
# Check host capabilities
curl -X POST "http://localhost:8000/api/hosts/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "remote-server.local",
    "ssh_user": "root"
  }'

# List remote stacks
curl "http://localhost:8000/api/hosts/remote-server.local/compose/stacks?ssh_user=root&compose_path=/mnt/cache/compose"

# Start a remote stack
curl -X POST "http://localhost:8000/api/hosts/remote-server.local/compose/stacks/authelia/start?ssh_user=root&compose_path=/mnt/cache/compose"
```

## 🌐 Frontend Development

The web UI is planned for future development. See [frontend/README.md](frontend/README.md) for the roadmap and setup instructions.

**Planned features:**
- Multi-host management dashboard
- Migration wizard with host selection
- Real-time progress monitoring
- Remote stack browser and manager
- Host capability dashboard
- Migration history and logs
- SSH key management
- Visual migration planning

## 📖 Documentation

- [API Documentation](docs/API.md) - Complete API reference with multi-host examples
- [Frontend Roadmap](frontend/README.md) - Web UI development plan
- Backend code is extensively commented for developers

## 🤝 Contributing

Contributions are welcome! Areas needing development:

- **Frontend Implementation** - React/Vue.js web interface with multi-host support
- **Authentication** - API key or OAuth support
- **Monitoring** - Prometheus metrics and alerting
- **Testing** - Unit and integration tests
- **Docker Support** - Containerized deployment options
- **Advanced Features** - Scheduled migrations, batch operations, rollback functionality

## 📄 License

This project is open source. See the repository for license details.

## 🆘 Support

- **Issues**: Report bugs and feature requests on GitHub
- **API Docs**: http://localhost:8000/docs when running
- **Examples**: See `backend/example.py` for usage patterns

---

**TransDock v1.0** - Multi-host Docker stack migrations with ZFS snapshots 