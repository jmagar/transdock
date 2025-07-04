# TransDock API Documentation

The TransDock backend provides a RESTful API for managing Docker Compose stack migrations using ZFS snapshots with full multi-host support.

## Base URL

```
http://localhost:8000
```

## Interactive Documentation

When the backend is running, you can access interactive API documentation at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Authentication

Currently, no authentication is required. Future versions may implement API key or OAuth authentication.

## Security Features

TransDock includes comprehensive security validation to protect against:
- **Path traversal attacks** - All paths are sanitized and validated
- **Command injection** - User inputs are escaped and validated
- **SSH injection** - Hostnames and usernames are validated with strict patterns
- **ZFS injection** - All ZFS commands are validated against allowed operations
- **Input validation** - All API inputs are validated for format and content

Security validation errors return `422 Unprocessable Entity` status codes with descriptive error messages.

## Multi-Host Architecture

TransDock supports full multi-host operations where both source and destination can be any host accessible via SSH. No more hardcoded paths in configuration files - everything is specified dynamically via API calls.

## Endpoints

### System Information

#### GET /
Get basic API information.

**Response:**
```json
{
  "name": "TransDock",
  "version": "1.0.0",
  "description": "Docker Stack Migration Tool using ZFS snapshots"
}
```

#### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "transdock"
}
```

#### GET /system/info
Get detailed system information.

**Response:**
```json
{
  "hostname": "unraid-server",
  "platform": "Linux-6.1.0-unraid-x86_64",
  "architecture": "64bit",
  "docker_version": "Docker version 20.10.21",
  "docker_compose_version": "docker-compose version 2.12.2",
  "zfs_available": true
}
```

### Multi-Host Operations

#### POST /api/hosts/validate
Validate host capabilities and discover available paths.

**Request Body:**
```json
{
  "hostname": "remote-server.local",
  "ssh_user": "root",
  "ssh_port": 22
}
```

**Response:**
```json
{
  "hostname": "remote-server.local",
  "docker_available": true,
  "zfs_available": true,
  "compose_paths": [
    "/mnt/cache/compose",
    "/mnt/user/compose"
  ],
  "appdata_paths": [
    "/mnt/cache/appdata",
    "/mnt/user/appdata"
  ],
  "zfs_pools": [
    "cache",
    "backup"
  ],
  "error": null
}
```

#### GET /api/hosts/{hostname}/capabilities
Get detailed host capabilities.

**Parameters:**
- `hostname` (path): Target hostname
- `ssh_user` (query): SSH username
- `ssh_port` (query): SSH port (default: 22)

**Response:**
```json
{
  "hostname": "remote-server.local",
  "docker_available": true,
  "zfs_available": true,
  "compose_paths": ["/mnt/cache/compose"],
  "appdata_paths": ["/mnt/cache/appdata"],
  "zfs_pools": ["cache"]
}
```

#### GET /api/hosts/{hostname}/compose/stacks
List Docker Compose stacks on remote host.

**Parameters:**
- `hostname` (path): Target hostname
- `compose_path` (query): Compose directory path
- `ssh_user` (query): SSH username
- `ssh_port` (query): SSH port (default: 22)

**Response:**
```json
{
  "stacks": [
    {
      "name": "authelia",
      "path": "/mnt/cache/compose/authelia",
      "compose_file": "/mnt/cache/compose/authelia/docker-compose.yml",
      "services": ["authelia", "redis", "postgres"],
      "status": "running"
    },
    {
      "name": "nextcloud",
      "path": "/mnt/cache/compose/nextcloud",
      "compose_file": "/mnt/cache/compose/nextcloud/docker-compose.yaml",
      "services": ["nextcloud", "mariadb"],
      "status": "stopped"
    }
  ]
}
```

#### GET /api/hosts/{hostname}/compose/stacks/{stack_name}
Analyze a specific stack on remote host.

**Parameters:**
- `hostname` (path): Target hostname
- `stack_name` (path): Stack name
- `compose_path` (query): Compose directory path
- `ssh_user` (query): SSH username
- `ssh_port` (query): SSH port (default: 22)

**Response:**
```json
{
  "stack_name": "authelia",
  "stack_path": "/mnt/cache/compose/authelia",
  "compose_file": "/mnt/cache/compose/authelia/docker-compose.yml",
  "volumes": [
    {
      "source": "/mnt/cache/appdata/authelia",
      "target": "/config",
      "dataset_path": "cache/appdata/authelia",
      "is_dataset": true
    }
  ],
  "services": ["authelia", "redis", "postgres"],
  "status": "running"
}
```

#### POST /api/hosts/{hostname}/compose/stacks/{stack_name}/start
Start a Docker Compose stack on remote host.

**Parameters:**
- `hostname` (path): Target hostname
- `stack_name` (path): Stack name
- `compose_path` (query): Compose directory path
- `ssh_user` (query): SSH username
- `ssh_port` (query): SSH port (default: 22)

**Response:**
```json
{
  "success": true,
  "message": "Stack 'authelia' started successfully",
  "stack_name": "authelia"
}
```

#### POST /api/hosts/{hostname}/compose/stacks/{stack_name}/stop
Stop a Docker Compose stack on remote host.

**Parameters:**
- `hostname` (path): Target hostname
- `stack_name` (path): Stack name
- `compose_path` (query): Compose directory path
- `ssh_user` (query): SSH username
- `ssh_port` (query): SSH port (default: 22)

**Response:**
```json
{
  "success": true,
  "message": "Stack 'authelia' stopped successfully",
  "stack_name": "authelia"
}
```

#### GET /api/hosts/{hostname}/datasets
List ZFS datasets on remote host.

**Parameters:**
- `hostname` (path): Target hostname
- `ssh_user` (query): SSH username
- `ssh_port` (query): SSH port (default: 22)

**Response:**
```json
{
  "datasets": [
    {
      "name": "cache/appdata",
      "mountpoint": "/mnt/cache/appdata"
    },
    {
      "name": "cache/compose",
      "mountpoint": "/mnt/cache/compose"
    }
  ]
}
```

### Local ZFS Operations

#### GET /zfs/status
Check ZFS availability and pool status.

**Response:**
```json
{
  "available": true,
  "pool_status": "pool: cache\n state: ONLINE\n..."
}
```

#### GET /datasets
List available ZFS datasets on local host.

**Response:**
```json
{
  "datasets": [
    {
      "name": "cache/appdata",
      "mountpoint": "/mnt/cache/appdata"
    },
    {
      "name": "cache/compose",
      "mountpoint": "/mnt/cache/compose"
    }
  ]
}
```

### Local Docker Compose Operations

#### GET /compose/stacks
List available Docker Compose stacks on local host.

**Response:**
```json
{
  "stacks": [
    {
      "name": "authelia",
      "path": "/mnt/cache/compose/authelia",
      "compose_file": "docker-compose.yml"
    },
    {
      "name": "nextcloud",
      "path": "/mnt/cache/compose/nextcloud",
      "compose_file": "docker-compose.yaml"
    }
  ]
}
```

#### POST /compose/{stack_name}/analyze
Analyze a compose stack on local host and return volume information.

**Parameters:**
- `stack_name` (path): Name of the compose stack

**Response:**
```json
{
  "stack_name": "authelia",
  "stack_path": "/mnt/cache/compose/authelia",
  "compose_file": "/mnt/cache/compose/authelia/docker-compose.yml",
  "volumes": [
    {
      "source": "/mnt/cache/appdata/authelia",
      "target": "/config",
      "dataset_path": "cache/appdata/authelia",
      "is_dataset": true
    }
  ],
  "services": ["authelia", "redis", "postgres"]
}
```

### Migration Operations

#### POST /migrations
Start a new migration process with multi-host support.

**Request Body:**
```json
{
  "compose_dataset": "authelia",
  "target_host": "192.168.1.100",
  "target_base_path": "/home/jmagar",
  "ssh_user": "root",
  "ssh_port": 22,
  "force_rsync": false,
  "source_host": "192.168.1.50",
  "source_ssh_user": "root",
  "source_ssh_port": 22,
  "source_compose_path": "/mnt/cache/compose",
  "source_appdata_path": "/mnt/cache/appdata",
  "transfer_method": "auto"
}
```

**Multi-Host Migration Examples:**

*Local to Remote:*
```json
{
  "compose_dataset": "authelia",
  "target_host": "remote-server.local",
  "target_base_path": "/opt/docker",
  "ssh_user": "root"
}
```

*Remote to Remote:*
```json
{
  "compose_dataset": "authelia",
  "target_host": "dest-server.local",
  "target_base_path": "/home/docker",
  "ssh_user": "root",
  "source_host": "source-server.local",
  "source_ssh_user": "root",
  "source_compose_path": "/mnt/cache/compose",
  "source_appdata_path": "/mnt/cache/appdata"
}
```

**Security Validation:**
- `compose_dataset`: Validated for path traversal and injection attacks
- `target_host`/`source_host`: Validated against hostname patterns, prevents command injection
- `target_base_path`: Sanitized for path traversal prevention
- `ssh_user`/`source_ssh_user`: Validated against username patterns
- `ssh_port`/`source_ssh_port`: Validated for valid port range (1-65535)

**Response:**
```json
{
  "migration_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "started",
  "message": "Migration process started successfully"
}
```

#### GET /migrations
List all migrations.

**Response:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "completed",
    "progress": 100,
    "message": "Migration completed successfully",
    "compose_dataset": "authelia",
    "target_host": "192.168.1.100",
    "target_base_path": "/home/jmagar",
    "source_host": "192.168.1.50",
    "volumes": [...],
    "transfer_method": "zfs_send",
    "error": null
  }
]
```

#### GET /migrations/{migration_id}
Get the status of a specific migration.

**Parameters:**
- `migration_id` (path): UUID of the migration (validated for format and security)

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "transferring",
  "progress": 75,
  "message": "Transferring authelia-db",
  "compose_dataset": "authelia",
  "target_host": "192.168.1.100",
  "target_base_path": "/home/jmagar",
  "source_host": "192.168.1.50",
  "volumes": [
    {
      "source": "/mnt/cache/appdata/authelia",
      "target": "/config",
      "dataset_path": "cache/appdata/authelia",
      "is_dataset": true
    }
  ],
  "transfer_method": "zfs_send",
  "error": null
}
```

#### POST /migrations/{migration_id}/cancel
Cancel a running migration.

**Parameters:**
- `migration_id` (path): UUID of the migration to cancel

**Response:**
```json
{
  "success": true,
  "message": "Migration cancelled successfully"
}
```

**Error Response:**
```json
{
  "detail": "Migration not found"
}
```

## Status Values

Migration status can be one of:
- `initializing` - Migration is being prepared
- `validating` - Validating inputs and checking ZFS
- `parsing` - Parsing docker-compose file
- `analyzing` - Analyzing volume mounts
- `stopping` - Stopping Docker compose stack
- `snapshotting` - Creating ZFS snapshots
- `checking` - Checking target system capabilities
- `preparing` - Preparing transfer method
- `transferring` - Transferring data to target
- `updating` - Updating compose file paths
- `starting` - Starting compose stack on target
- `cleaning` - Cleaning up snapshots
- `verifying` - Verifying container deployment and health with smart container name detection
- `completed` - Migration completed successfully
- `failed` - Migration failed with error

## Transfer Methods

- `zfs_send` - Uses ZFS send/receive for efficient block-level transfer
- `rsync` - Uses rsync for file-level transfer (fallback when target lacks ZFS)
- `auto` - Automatically chooses the best method based on host capabilities

## Multi-Host Transfer Support

TransDock supports all combinations of source and destination hosts:
- **Local to Remote**: Migrate from local host to remote host
- **Remote to Local**: Migrate from remote host to local host  
- **Remote to Remote**: Migrate between two remote hosts
- **Local to Local**: Migrate within the same host (path changes)

Both ZFS and rsync transfer methods work across all host combinations.

## Error Handling

All endpoints return appropriate HTTP status codes:
- `200` - Success
- `400` - Bad Request (invalid parameters)
- `404` - Not Found (migration/stack not found)
- `422` - Unprocessable Entity (security validation failed)
- `500` - Internal Server Error

### Security Validation Errors (422)

When security validation fails, the API returns a 422 status code with details:
```json
{
  "detail": "Security validation failed: Invalid hostname format: host; rm -rf /"
}
```

Common security validation errors:
- Invalid hostname format (contains special characters)
- Path traversal attempts in paths
- Command injection attempts in user inputs
- Invalid port numbers or ranges
- Malformed migration IDs

### Standard Error Responses

Other error responses include details:
```json
{
  "detail": "Migration not found"
}
```

## Migration Verification

The verification process includes:
- **Smart Container Detection**: Automatically detects container names using multiple Docker Compose naming patterns
- **Health Checks**: Verifies containers are running and healthy
- **Volume Validation**: Confirms volumes are properly mounted with updated paths
- **Service Validation**: Ensures all services from the compose file are operational

The verification system handles various Docker Compose naming conventions:
- Legacy format: `project_service_1`
- Modern format: `project-service-1`
- Simplified format: `project_service` or `project-service`
- Single service: `project` or `service` 