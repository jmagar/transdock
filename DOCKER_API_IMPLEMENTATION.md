# Docker API Implementation - Production Ready

## Overview

TransDock has been completely rewritten to use the Docker API instead of CLI commands, eliminating the need for hardcoded paths and providing robust container discovery and management capabilities.

## Key Changes

### 1. **Eliminated Path Dependencies**
- ❌ **Old**: `TRANSDOCK_COMPOSE_BASE`, `TRANSDOCK_APPDATA_BASE` 
- ✅ **New**: Dynamic container discovery via Docker API

### 2. **Container-Centric Approach**
- ❌ **Old**: Compose file parsing and path-based operations
- ✅ **New**: Container inspection and Docker API operations

### 3. **Flexible Discovery Methods**
- **Project-based**: Discover all containers in a Docker Compose project
- **Name-based**: Find containers by name pattern matching
- **Label-based**: Discover containers using custom label selectors

## New API Endpoints

### Container Discovery
```bash
# Discover containers by project name
GET /containers/discover?container_identifier=authelia&identifier_type=project

# Discover containers by name pattern
GET /containers/discover?container_identifier=nginx&identifier_type=name

# Discover containers by labels
GET /containers/discover?container_identifier=app&identifier_type=labels&label_filters={"app":"authelia"}
```

### Container Analysis
```bash
# Analyze containers for migration readiness
GET /containers/analyze?container_identifier=authelia&identifier_type=project
```

### Container Migration
```bash
# Start container-based migration
POST /migrations/containers
{
  "container_identifier": "authelia",
  "identifier_type": "project", 
  "target_host": "new-server.local",
  "target_base_path": "/opt/docker"
}
```

## Implementation Details

### Docker Operations Class (`docker_ops.py`)

Complete rewrite with production-ready features:

- **Docker API Client**: Direct Docker daemon communication
- **Container Discovery**: Multiple discovery methods (project, name, labels)
- **Volume Extraction**: Automatic detection of bind mounts and volumes
- **Network Management**: Recreation of Docker networks on target
- **Image Management**: Automatic image pulling on target host
- **Remote Operations**: SSH-based Docker operations for remote hosts

### Migration Service (`migration_service.py`)

Enhanced with container-focused migration:

- **Container-Based Migration**: Primary migration method using Docker API
- **Backward Compatibility**: Legacy compose-dataset support
- **Network Recreation**: Automatic Docker network setup
- **Volume Discovery**: No hardcoded path filtering
- **Multi-Container Support**: Handle complex multi-service deployments

### Models (`models.py`)

New data structures for container operations:

- `ContainerMigrationRequest`: Container-based migration parameters
- `ContainerDiscoveryResult`: Container discovery results
- `ContainerAnalysis`: Migration readiness analysis
- `IdentifierType`: Discovery method enumeration

## Usage Examples

### 1. Simple Container Migration

```bash
# Discover containers in the "authelia" project
curl "http://localhost:8000/containers/discover?container_identifier=authelia&identifier_type=project"

# Start migration
curl -X POST "http://localhost:8000/migrations/containers" \
  -H "Content-Type: application/json" \
  -d '{
    "container_identifier": "authelia",
    "identifier_type": "project",
    "target_host": "new-server.local",
    "target_base_path": "/opt/docker"
  }'
```

### 2. Advanced Label-Based Discovery

```bash
# Discover containers with specific labels
curl "http://localhost:8000/containers/discover?container_identifier=production&identifier_type=labels&label_filters={\"environment\":\"production\",\"team\":\"backend\"}"

# Migrate all production backend containers
curl -X POST "http://localhost:8000/migrations/containers" \
  -H "Content-Type: application/json" \
  -d '{
    "container_identifier": "production",
    "identifier_type": "labels",
    "label_filters": {"environment": "production", "team": "backend"},
    "target_host": "prod-server.local",
    "target_base_path": "/srv/containers"
  }'
```

### 3. Cross-Host Migration

```bash
# Migrate from remote source to remote target
curl -X POST "http://localhost:8000/migrations/containers" \
  -H "Content-Type: application/json" \
  -d '{
    "container_identifier": "nextcloud",
    "identifier_type": "project",
    "source_host": "old-server.local",
    "source_ssh_user": "root",
    "target_host": "new-server.local",
    "target_base_path": "/mnt/storage/containers"
  }'
```

## Benefits

### 1. **Universal Container Support**
- Works with containers created by `docker-compose`
- Works with containers created by `docker run`
- Works with containers from orchestration tools
- Works with manually modified containers

### 2. **No Path Configuration**
- No environment variables needed
- No hardcoded directory structures
- Works with any volume mount configuration
- Automatic discovery of data locations

### 3. **Enhanced Reliability**
- Real container state vs. static compose files
- Structured API responses vs. CLI output parsing
- Better error handling and reporting
- Automatic image pulling and network recreation

### 4. **Simplified Workflow**

**Before (CLI-based):**
```bash
# Required setup
export TRANSDOCK_COMPOSE_BASE="/mnt/cache/compose" 
export TRANSDOCK_APPDATA_BASE="/mnt/cache/appdata"

# Migration (path-dependent)
curl -X POST "/migrations" -d '{
  "compose_dataset": "authelia",  # Must exist in /mnt/cache/compose/authelia/
  "target_host": "server",
  "target_base_path": "/opt/docker"
}'
```

**After (Docker API):**
```bash
# No setup required

# Migration (path-independent) 
curl -X POST "/migrations/containers" -d '{
  "container_identifier": "authelia",  # Any project name
  "identifier_type": "project",
  "target_host": "server",
  "target_base_path": "/opt/docker"
}'
```

## Migration Process

### 1. **Discovery Phase**
- Query Docker API for containers
- Extract volume mounts, networks, environment variables
- Analyze migration complexity

### 2. **Validation Phase**
- Validate Docker availability on target
- Check storage space requirements
- Verify SSH connectivity

### 3. **Migration Phase**
- Stop source containers
- Create ZFS snapshots or use rsync
- Transfer data to target host
- Pull required images on target

### 4. **Recreation Phase**
- Create Docker networks on target
- Recreate containers with updated volume paths
- Connect containers to networks
- Start containers

### 5. **Verification Phase**
- Verify containers are running
- Check service accessibility
- Validate data integrity

## Advanced Features

### Container Analysis
```json
{
  "containers": [
    {
      "id": "abc123",
      "name": "authelia",
      "image": "authelia/authelia:latest",
      "state": "running",
      "volume_count": 2,
      "network_count": 2,
      "port_count": 1
    }
  ],
  "networks": [
    {
      "id": "net123",
      "name": "authelia_default",
      "driver": "bridge"
    }
  ],
  "migration_complexity": "simple",
  "warnings": [],
  "recommendations": [
    "Consider using ZFS snapshots for consistent data migration"
  ]
}
```

### Remote Operations
- SSH-based container discovery on remote hosts
- Remote container inspection and analysis
- Cross-host migration support
- Secure command execution with validation

## Security Features

- **Input Validation**: All container identifiers and parameters validated
- **SSH Security**: Secure command construction and execution
- **Path Sanitization**: Automatic path validation and sanitization
- **Command Injection Prevention**: Parameterized command construction
- **Docker API Security**: Direct API communication (no shell commands)

## Backward Compatibility

Legacy endpoints still work but are converted to container-based operations:

```bash
# Legacy endpoint (still works)
POST /migrations
{
  "compose_dataset": "authelia",
  "target_host": "server", 
  "target_base_path": "/opt/docker"
}

# Automatically converted to:
POST /migrations/containers  
{
  "container_identifier": "authelia",
  "identifier_type": "project",
  "target_host": "server",
  "target_base_path": "/opt/docker" 
}
```

## Error Handling

Comprehensive error handling with detailed messages:

- **Container Not Found**: Clear indication when containers don't exist
- **Docker API Errors**: Structured error responses from Docker daemon  
- **Network Issues**: SSH and connectivity problem reporting
- **Storage Issues**: Detailed storage validation failures
- **Permission Issues**: Clear Docker and file system permission errors

## Performance Improvements

- **Faster Discovery**: Direct API calls vs. file system scanning
- **Parallel Operations**: Concurrent container operations
- **Efficient Data Transfer**: Optimal ZFS/rsync usage
- **Connection Reuse**: Docker API client connection pooling
- **Reduced I/O**: No compose file parsing overhead

## Dependencies

Updated `requirements.txt`:
```
docker==6.1.3
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
PyYAML==6.0.1
```

## Conclusion

The Docker API implementation transforms TransDock from a "compose file migration tool" into a true "container migration platform" that works with any Docker container regardless of how it was created or where its files are stored. This aligns with modern containerization philosophy where containers are the primary abstraction, not the underlying file system structure.

**Key Result**: TransDock now works with ANY Docker container, anywhere, without configuration.