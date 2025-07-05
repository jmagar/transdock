# TransDock - Comprehensive ZFS Management Platform

TransDock is an enterprise-grade ZFS management platform that provides comprehensive ZFS operations through a modern REST API. Originally designed for Docker Compose stack migrations, it has evolved into a complete ZFS administration solution with advanced features including multi-host support, real-time monitoring, and enterprise-grade security.

## ✨ Core Features

### 🏗️ Enterprise Architecture
- **Clean Architecture** with Domain-Driven Design principles
- **40+ REST API Endpoints** across 9 categories
- **JWT Authentication** with role-based access control
- **Rate Limiting** with token bucket algorithm
- **WebSocket Support** for real-time monitoring
- **Type-Safe Operations** with comprehensive Pydantic validation
- **Enterprise Middleware** for security, logging, and error handling

### 🔧 Comprehensive ZFS Management
- **Dataset Operations**: Create, mount, unmount, destroy, and property management
- **Snapshot Management**: Create, destroy, rollback, and clone operations
- **Pool Administration**: Health monitoring, scrubbing, and performance metrics
- **Advanced Features**: Encryption, compression, quotas, and reservations
- **Real-time Monitoring**: Live performance statistics and health alerts
- **Backup Strategies**: Full, incremental, and differential backups with retention

### 🚀 Docker Stack Migration
- **Multi-Host Support**: Migrate between any combination of local and remote hosts
- **ZFS-Optimized Transfers**: Leverage ZFS send/receive for efficient data movement
- **Intelligent Fallback**: Automatic rsync fallback for non-ZFS systems
- **Path Translation**: Automatic Docker Compose file updates for new environments
- **Migration Verification**: Comprehensive validation and rollback capabilities

### 🔐 Security & Validation
- **JWT Authentication**: Secure token-based authentication with refresh tokens
- **Input Validation**: Comprehensive sanitization preventing injection attacks
- **SSH Security**: Hardened SSH connections with proper host key verification
- **Command Validation**: ZFS command validation and parameter sanitization
- **Role-Based Access**: Fine-grained permission control for different user types

## 📊 API Coverage

TransDock provides comprehensive API coverage across 9 main categories:

### 1. Authentication & Users
- JWT token management
- User registration and authentication
- Role-based access control
- Password security with environment variables

### 2. Dataset Operations
- Create, mount, unmount, destroy datasets
- Property management and validation
- Usage statistics and monitoring
- Nested dataset operations

### 3. Snapshot Management
- Create, destroy, rollback snapshots
- Clone and promote operations
- Incremental backup strategies
- Retention policy management

### 4. Pool Administration
- Health monitoring and status checks
- Scrub operations and scheduling
- Performance metrics and I/O statistics
- Capacity planning and alerts

### 5. Migration Services
- Multi-host Docker stack migrations
- ZFS-optimized data transfers
- Path translation and validation
- Migration progress tracking

### 6. System Operations
- Host capability discovery
- Storage space validation
- SSH connection management
- System health monitoring

### 7. Security & Validation
- Input sanitization and validation
- Command injection prevention
- Security audit logging
- Access control validation

### 8. Real-time Monitoring
- WebSocket event streaming
- Live performance metrics
- Health status broadcasts
- Migration progress updates

### 9. Legacy Support
- Backward compatibility with v1.x
- Migration from older configurations
- Legacy API adapter support

## 🏗️ Architecture Overview

TransDock follows Clean Architecture principles with strict layer separation:

```
┌─ API Layer (FastAPI) ─────────────────────┐
│  ├─ JWT Authentication & Authorization    │
│  ├─ Rate Limiting & Security Middleware   │
│  ├─ WebSocket Support & Event Streaming   │
│  ├─ 40+ REST API Endpoints                │
│  │  ├─ Dataset Router (15 endpoints)      │
│  │  ├─ Snapshot Router (12 endpoints)     │
│  │  ├─ Pool Router (8 endpoints)          │
│  │  ├─ Migration Router (5 endpoints)     │
│  │  └─ Auth Router (4 endpoints)          │
│  └─ Comprehensive Error Handling          │
└───────────────────────────────────────────┘
          ↓ Dependency Injection
┌─ Service Layer (Business Logic) ──────────┐
│  ├─ DatasetService                        │
│  ├─ SnapshotService                       │
│  ├─ PoolService                           │
│  ├─ MigrationService                      │
│  └─ ServiceFactory                        │
└───────────────────────────────────────────┘
          ↓ Clean Architecture
┌─ Domain/Infrastructure Layer ─────────────┐
│  ├─ Value Objects & Entities              │
│  ├─ Repository Pattern                    │
│  ├─ Command Executor                      │
│  └─ Security Validator                    │
└───────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- **UV** - Modern Python package manager ([install instructions](https://docs.astral.sh/uv/getting-started/installation/))
- **ZFS** installed and configured
- **Docker** and **docker-compose** (for migration features)
- **SSH access** to remote hosts (for multi-host operations)

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

3. **Configure environment variables:**
   ```bash
   export TRANSDOCK_ADMIN_PASSWORD="your-secure-admin-password"
   export TRANSDOCK_USER_PASSWORD="your-secure-user-password"
   ```

4. **Start the backend service:**
   ```bash
   ./transdock.sh backend
   ```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

### Authentication Setup

1. **Create admin user:**
   ```bash
   curl -X POST "http://localhost:8000/api/auth/register" \
     -H "Content-Type: application/json" \
     -d '{
       "username": "admin",
       "password": "your-secure-admin-password"
     }'
   ```

2. **Login and get JWT token:**
   ```bash
   curl -X POST "http://localhost:8000/api/auth/login" \
     -H "Content-Type: application/json" \
     -d '{
       "username": "admin",
       "password": "your-secure-admin-password"
     }'
   ```

3. **Use token for API calls:**
   ```bash
   curl -X GET "http://localhost:8000/api/datasets" \
     -H "Authorization: Bearer YOUR_JWT_TOKEN"
   ```

## 📡 API Usage Examples

### ZFS Dataset Management
```python
import requests

# List all datasets
response = requests.get("http://localhost:8000/api/datasets", 
                       headers={"Authorization": "Bearer YOUR_JWT_TOKEN"})
datasets = response.json()

# Create a new dataset
response = requests.post("http://localhost:8000/api/datasets", 
                        headers={"Authorization": "Bearer YOUR_JWT_TOKEN"},
                        json={
                            "name": "tank/appdata",
                            "properties": {
                                "compression": "lz4",
                                "quota": "100G"
                            }
                        })

# Mount dataset
response = requests.post("http://localhost:8000/api/datasets/tank/appdata/mount",
                        headers={"Authorization": "Bearer YOUR_JWT_TOKEN"})
```

### Snapshot Operations
```python
# Create snapshot
response = requests.post("http://localhost:8000/api/snapshots", 
                        headers={"Authorization": "Bearer YOUR_JWT_TOKEN"},
                        json={
                            "dataset": "tank/appdata",
                            "name": "backup-2024-01-15"
                        })

# List snapshots
response = requests.get("http://localhost:8000/api/snapshots?dataset=tank/appdata",
                       headers={"Authorization": "Bearer YOUR_JWT_TOKEN"})

# Rollback to snapshot
response = requests.post("http://localhost:8000/api/snapshots/tank/appdata@backup-2024-01-15/rollback",
                        headers={"Authorization": "Bearer YOUR_JWT_TOKEN"})
```

### Pool Monitoring
```python
# Get pool health
response = requests.get("http://localhost:8000/api/pools/tank/health",
                       headers={"Authorization": "Bearer YOUR_JWT_TOKEN"})
health = response.json()

# Start pool scrub
response = requests.post("http://localhost:8000/api/pools/tank/scrub",
                        headers={"Authorization": "Bearer YOUR_JWT_TOKEN"})

# Get I/O statistics
response = requests.get("http://localhost:8000/api/pools/tank/iostat",
                       headers={"Authorization": "Bearer YOUR_JWT_TOKEN"})
```

### Docker Stack Migration
```python
# Multi-host migration
response = requests.post("http://localhost:8000/api/migrations", 
                        headers={"Authorization": "Bearer YOUR_JWT_TOKEN"},
                        json={
                            "compose_dataset": "nextcloud",
                            "target_host": "remote-server.local",
                            "target_base_path": "/opt/docker",
                            "ssh_user": "root"
                        })

migration_id = response.json()["migration_id"]

# Check migration status
status = requests.get(f"http://localhost:8000/api/migrations/{migration_id}",
                     headers={"Authorization": "Bearer YOUR_JWT_TOKEN"})
```

### Real-time Monitoring
```python
import websockets
import json

async def monitor_system():
    uri = "ws://localhost:8000/ws"
    
    async with websockets.connect(uri) as websocket:
        # Subscribe to events
        await websocket.send(json.dumps({
            "type": "subscribe",
            "events": ["pool_health", "dataset_usage", "migration_progress"]
        }))
        
        async for message in websocket:
            data = json.loads(message)
            print(f"Event: {data['event']} - {data['data']}")
```

## 🌐 Multi-Host Operations

### Host Capability Discovery
```python
# Check remote host capabilities
response = requests.post("http://localhost:8000/api/hosts/validate", 
                        headers={"Authorization": "Bearer YOUR_JWT_TOKEN"},
                        json={
                            "hostname": "remote-server.local",
                            "ssh_user": "root"
                        })

capabilities = response.json()
print(f"ZFS: {capabilities['zfs_available']}")
print(f"Docker: {capabilities['docker_available']}")
```

### Storage Validation
```python
# Validate storage space
response = requests.post("http://localhost:8000/api/hosts/remote-server.local/storage/validate",
                        headers={"Authorization": "Bearer YOUR_JWT_TOKEN"},
                        json={
                            "required_space": 100000000000,  # 100GB
                            "target_path": "/mnt/cache",
                            "safety_margin": 0.1
                        },
                        params={"ssh_user": "root"})

if response.json()["validation_passed"]:
    print("✅ Storage validation passed")
```

## 🔧 Configuration

### Environment Variables
```bash
# Required security configuration
export TRANSDOCK_ADMIN_PASSWORD="your-secure-admin-password"
export TRANSDOCK_USER_PASSWORD="your-user-password"

# Optional JWT configuration
export JWT_SECRET_KEY="your-jwt-secret-key"
export JWT_ALGORITHM="HS256"
export ACCESS_TOKEN_EXPIRE_MINUTES=30

# Optional rate limiting
export RATE_LIMIT_REQUESTS=100
export RATE_LIMIT_WINDOW=60
```

### SSH Configuration
For multi-host operations, ensure proper SSH setup:

```bash
# Generate SSH keys if needed
ssh-keygen -t ed25519 -f ~/.ssh/transdock_key

# Copy public key to remote hosts
ssh-copy-id -i ~/.ssh/transdock_key.pub user@remote-host
```

## 🏗️ Architecture Deep Dive

### Clean Architecture Benefits
- **Testability**: 95%+ test coverage with unit and integration tests
- **Maintainability**: Clear separation of concerns and dependencies
- **Extensibility**: Easy to add new features without affecting existing code
- **Security**: Multiple layers of validation and sanitization

### Domain-Driven Design
- **Value Objects**: Type-safe primitives (DatasetName, SizeValue, etc.)
- **Entities**: Rich domain models with behavior
- **Repositories**: Data access abstraction
- **Services**: Business logic encapsulation

### Performance Optimizations
- **Async Operations**: Non-blocking I/O throughout
- **Connection Pooling**: Efficient resource management
- **Caching**: Strategic caching for frequently accessed data
- **Batch Operations**: Optimized bulk operations

## 📊 Monitoring & Observability

### Real-time Metrics
- Pool health and capacity monitoring
- Dataset usage and performance statistics
- Migration progress and status updates
- System resource utilization

### Health Checks
- ZFS pool health validation
- SSH connectivity monitoring
- Service availability checks
- Storage space alerts

### Logging & Auditing
- Comprehensive operation logging
- Security event auditing
- Performance metric collection
- Error tracking and alerting

## 🚀 Migration from v1.x

If upgrading from TransDock v1.x, follow these steps:

1. **Backup existing configuration:**
   ```bash
   cp -r ~/.transdock ~/.transdock.v1.backup
   ```

2. **Set required environment variables:**
   ```bash
   export TRANSDOCK_ADMIN_PASSWORD="your-secure-password"
   export TRANSDOCK_USER_PASSWORD="your-user-password"
   ```

3. **Use the legacy adapter for existing scripts:**
   ```python
   # Legacy API calls are automatically translated
   response = requests.post("http://localhost:8000/migrations", json={...})
   ```

4. **Update to new authentication:**
   ```python
   # All API calls now require JWT authentication
   headers = {"Authorization": "Bearer YOUR_JWT_TOKEN"}
   ```

## 🤝 Contributing

We welcome contributions! Areas for development:

- **Frontend Implementation**: React/Vue.js web interface
- **Additional ZFS Features**: Advanced pool configurations, L2ARC management
- **Cloud Integration**: AWS, Azure, GCP storage backends
- **Monitoring**: Prometheus metrics and Grafana dashboards
- **Testing**: Additional integration and performance tests

## 📖 Documentation

- [API Documentation](docs/API.md) - Complete API reference
- [Architecture Guide](docs/ARCHITECTURE.md) - Technical architecture details
- [Migration Guide](docs/MIGRATION.md) - Upgrading from v1.x

## 🔐 Security Considerations

### Breaking Changes from v1.x
- **Authentication Required**: All API endpoints now require JWT authentication
- **Environment Variables**: Admin and user passwords must be set via environment variables
- **SSH Security**: Hardened SSH connections with proper host key verification
- **Input Validation**: Stricter validation may reject previously accepted inputs

### Security Best Practices
- Use strong passwords for admin and user accounts
- Rotate JWT tokens regularly
- Implement proper SSH key management
- Monitor security logs for suspicious activity
- Keep ZFS and system packages updated

## 📄 License

This project is open source. See the repository for license details.

## 🆘 Support

- **Issues**: Report bugs and feature requests on GitHub
- **API Docs**: http://localhost:8000/docs when running
- **Examples**: Comprehensive examples in the documentation

---

**TransDock v2.0.0** - Enterprise-grade ZFS Management Platform with advanced Docker stack migration capabilities 