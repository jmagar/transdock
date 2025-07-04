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

### 🔧 Advanced ZFS Features

- **ZFS Pool Health Monitoring**: Check pool status, health, and disk conditions
- **Pool Scrubbing**: Automated pool maintenance with scrub status tracking
- **Dataset Property Management**: Configure compression, deduplication, and custom properties
- **Advanced Snapshot Management**: Incremental snapshots, rollback capabilities, and retention policies
- **Performance Monitoring**: Real-time I/O statistics and ARC cache performance metrics
- **Backup Strategies**: Full/incremental/differential backups with bookmark support
- **ZFS Encryption**: Native encryption support with key management
- **Quota and Reservation Management**: Automated quota monitoring with alerts
- **Migration Optimization**: ZFS-specific optimizations for faster migrations

### 💾 Storage Space Validation

- **Pre-Migration Validation**: Check available storage space before starting migrations
- **Multi-Path Storage Analysis**: Analyze storage across multiple mount points
- **Human-Readable Storage Reports**: Clear storage information with safety margins
- **Automated Safety Checks**: Prevent migrations when insufficient space is available
- **Real-Time Storage Monitoring**: Monitor storage usage during migration processes

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

### Storage Space Validation
```python
# Check storage space before migration
response = requests.get(
    "http://localhost:8000/api/hosts/remote-server.local/storage",
    params={
        "paths": "/mnt/cache,/mnt/user",
        "ssh_user": "root"
    }
)

storage_info = response.json()["storage_info"]
for storage in storage_info:
    print(f"Path: {storage['path']}")
    print(f"Available: {storage['available_human']} ({storage['usage_percent']:.1f}% used)")

# Validate storage space for migration
validation_response = requests.post(
    "http://localhost:8000/api/hosts/remote-server.local/storage/validate",
    json={
        "required_space": 100000000000,  # 100GB
        "target_path": "/mnt/cache",
        "safety_margin": 0.1
    },
    params={"ssh_user": "root"}
)

if validation_response.json()["validation_result"]["validation_passed"]:
    print("✅ Storage validation passed - migration can proceed")
else:
    print("❌ Insufficient storage space")
```

### Advanced ZFS Management
```python
# Check pool health
response = requests.get("http://localhost:8000/api/zfs/pools/cache/health")
health = response.json()
print(f"Pool health: {health['state']} - {health['capacity']['usage_percent']:.1f}% used")

# Get dataset properties
response = requests.get(
    "http://localhost:8000/api/zfs/datasets/cache/appdata/properties",
    params={"properties": "compression,quota,used"}
)
properties = response.json()["properties"]
print(f"Compression: {properties['compression']}, Used: {properties['used']}")

# Create incremental backup
response = requests.post(
    "http://localhost:8000/api/zfs/datasets/cache/appdata/snapshots/incremental",
    json={
        "base_snapshot": "backup_20240115_103000",
        "snapshot_name": "backup_20240115_143000"
    }
)
if response.json()["success"]:
    print(f"Created incremental backup - saved {response.json()['size_saved']}")

# Monitor ZFS performance
response = requests.get("http://localhost:8000/api/zfs/pools/cache/iostat")
stats = response.json()["statistics"]
print(f"Read: {stats['read_bandwidth']}, Write: {stats['write_bandwidth']}")

# Check quota usage
response = requests.get("http://localhost:8000/api/zfs/datasets/cache/appdata/quota/usage")
quota_info = response.json()["quota_usage"]
print(f"Quota usage: {quota_info['used_human']} / {quota_info['quota_human']} ({quota_info['quota_usage_percent']:.1f}%)")
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

TransDock follows a comprehensive 13-step migration workflow with integrated storage validation:

1. **Validation** - Check inputs, SSH connectivity, and host capabilities
2. **Storage Validation** - Verify sufficient storage space with safety margins
3. **Parsing** - Parse docker-compose file from source location
4. **Analysis** - Extract volume mounts and dependencies
5. **Stopping** - Stop source Docker stack
6. **Snapshot Creation** - Create ZFS snapshots of all volumes for consistent data transfer
7. **Capability Check** - Verify target host capabilities (Docker, ZFS availability)
8. **Transfer Method Selection** - Choose optimal method (ZFS send or rsync) based on capabilities
9. **Data Transfer** - Transfer all volume data to the target host
10. **Path Translation** - Update docker-compose file with new paths
11. **Final Validation** - Verify storage and paths on target host
12. **Stack Startup** - Start stack on target machine
13. **Cleanup** - Remove temporary snapshots and files
14. **Verification** - Verify container deployment and health

### Storage Validation Features
- **Multi-checkpoint validation** at steps 2, 8, and during transfer
- **Safety margins** prevent system disk space exhaustion
- **Human-readable reporting** with clear storage requirements
- **Automatic validation failure handling** with detailed error messages

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

### ZFS Management Examples
```bash
# Check ZFS pool health
curl "http://localhost:8000/api/zfs/pools/cache/health"

# Start pool scrub
curl -X POST "http://localhost:8000/api/zfs/pools/cache/scrub"

# Create encrypted dataset
curl -X POST "http://localhost:8000/api/zfs/datasets/cache/secure_data/encryption/create" \
  -H "Content-Type: application/json" \
  -d '{
    "encryption_type": "aes-256-gcm",
    "key_format": "passphrase",
    "key_location": "/secure/keyfile"
  }'

# Set dataset quota
curl -X POST "http://localhost:8000/api/zfs/datasets/cache/appdata/quota" \
  -H "Content-Type: application/json" \
  -d '{
    "quota_size": "500G"
  }'

# Create incremental backup
curl -X POST "http://localhost:8000/api/zfs/datasets/cache/appdata/snapshots/incremental" \
  -H "Content-Type: application/json" \
  -d '{
    "base_snapshot": "backup_20240115_103000",
    "snapshot_name": "backup_20240115_143000"
  }'

# Monitor performance
curl "http://localhost:8000/api/zfs/pools/cache/iostat"

# Check quota alerts
curl "http://localhost:8000/api/zfs/datasets/cache/appdata/quota/alerts?warning_threshold=80"
```

### Storage Validation Examples
```bash
# Check storage space
curl "http://localhost:8000/api/hosts/remote-server.local/storage?paths=/mnt/cache,/mnt/user&ssh_user=root"

# Validate storage for migration
curl -X POST "http://localhost:8000/api/hosts/remote-server.local/storage/validate?ssh_user=root" \
  -H "Content-Type: application/json" \
  -d '{
    "required_space": 100000000000,
    "target_path": "/mnt/cache",
    "safety_margin": 0.1
  }'
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

**New ZFS Management Features:**
- ZFS pool health monitoring dashboard
- Interactive dataset property editor
- Visual backup strategy planner
- Real-time performance monitoring charts
- Storage space validation interface
- Quota management and alerting dashboard
- Snapshot timeline visualization
- Encryption key management interface

## 📖 Documentation

- [API Documentation](docs/API.md) - Complete API reference with multi-host examples
- [Frontend Roadmap](frontend/README.md) - Web UI development plan
- Backend code is extensively commented for developers

## 🤝 Contributing

Contributions are welcome! Areas needing development:

- **Frontend Implementation** - React/Vue.js web interface with multi-host support
  - ZFS management dashboard
  - Storage monitoring interface
  - Migration performance visualizations
- **Authentication** - API key or OAuth support
- **Monitoring** - Prometheus metrics and alerting
- **Testing** - Unit and integration tests
- **Docker Support** - Containerized deployment options
- **Advanced Features** - Scheduled migrations, batch operations, rollback functionality
- **Enhanced ZFS Features** - Custom retention policies, automated maintenance
- **Cloud Integration** - AWS, Azure, GCP storage backends
- **Database Support** - PostgreSQL, MySQL migration optimizations

## 📄 License

This project is open source. See the repository for license details.

## 🆘 Support

- **Issues**: Report bugs and feature requests on GitHub
- **API Docs**: http://localhost:8000/docs when running
- **Examples**: See `backend/example.py` for usage patterns

---

**TransDock v1.0** - Multi-host Docker stack migrations with advanced ZFS management and storage validation 