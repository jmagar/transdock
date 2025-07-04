# TransDock API Documentation

The TransDock backend provides a comprehensive RESTful API for managing Docker Compose stack migrations using ZFS snapshots, with full multi-host support and advanced ZFS management capabilities.

## Base URL

```
http://localhost:8000
```

## Interactive Documentation

When the backend is running, you can access interactive API documentation at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Overview

TransDock provides 40+ API endpoints covering:
- **Multi-Host Operations** (10+ endpoints) - Host management, stack operations, capabilities
- **Migration Management** (5+ endpoints) - Start, monitor, cancel migrations
- **ZFS Pool Management** (5+ endpoints) - Health monitoring, scrubbing, status
- **ZFS Dataset Management** (10+ endpoints) - Properties, usage, snapshots
- **Advanced Backup Operations** (5+ endpoints) - Strategy, execution, restore, verification
- **ZFS Encryption** (5+ endpoints) - Create, manage, key operations
- **Quota Management** (5+ endpoints) - Set quotas, monitor usage, alerts
- **Performance Monitoring** (3+ endpoints) - I/O stats, ARC statistics, migration monitoring
- **Storage Validation** (2+ endpoints) - Space validation, multi-path analysis

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

#### Storage Space Validation

#### GET /api/hosts/{hostname}/storage
Get storage information for host.

**Parameters:**
- `hostname` (path): Target hostname
- `paths` (query): Comma-separated list of paths to check (optional)
- `ssh_user` (query): SSH username
- `ssh_port` (query): SSH port (default: 22)

**Response:**
```json
{
  "hostname": "remote-server.local",
  "storage_info": [
    {
      "path": "/mnt/cache",
      "total_bytes": 1000000000000,
      "used_bytes": 500000000000,
      "available_bytes": 500000000000,
      "total_human": "931 GB",
      "used_human": "465 GB",
      "available_human": "465 GB",
      "usage_percent": 50.0,
      "filesystem": "zfs",
      "mount_point": "/mnt/cache"
    }
  ]
}
```

#### POST /api/hosts/{hostname}/storage/validate
Validate storage space for migration.

**Parameters:**
- `hostname` (path): Target hostname
- `ssh_user` (query): SSH username
- `ssh_port` (query): SSH port (default: 22)

**Request Body:**
```json
{
  "required_space": 100000000000,
  "target_path": "/mnt/cache",
  "safety_margin": 0.1
}
```

**Response:**
```json
{
  "hostname": "remote-server.local",
  "validation_result": {
    "validation_passed": true,
    "required_space": 100000000000,
    "required_space_human": "93.1 GB",
    "available_space": 500000000000,
    "available_space_human": "465 GB",
    "safety_margin": 0.1,
    "space_after_migration": 400000000000,
    "space_after_migration_human": "372 GB",
    "usage_after_migration": 60.0,
    "error_message": null,
    "warning_message": null
  }
}
```

**Error Response (422 - Insufficient Space):**
```json
{
  "detail": "Insufficient storage space: Required 93.1 GB, available 10.0 GB"
}
```

### Advanced ZFS Operations

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

#### Pool Health and Monitoring

#### GET /api/zfs/pools/{pool_name}/health

Get comprehensive health information for a ZFS pool.

**Parameters:**
- `pool_name` (path): The name of the ZFS pool (e.g., "cache", "backup").

**Response:**
```json
{
  "pool_name": "cache",
  "state": "ONLINE",
  "healthy": true,
  "errors": 0,
  "scan_status": "none requested",
  "disks": [
    {
      "name": "sda",
      "state": "ONLINE",
      "read_errors": 0,
      "write_errors": 0,
      "checksum_errors": 0
    }
  ],
  "capacity": {
    "total": 1000000000000,
    "used": 500000000000,
    "available": 500000000000,
    "usage_percent": 50.0
  }
}
```

#### GET /api/zfs/pools/{pool_name}/status
Get detailed pool status information.

**Parameters:**
- `pool_name` (path): ZFS pool name

**Response:**
```json
{
  "name": "cache",
  "state": "ONLINE",
  "status": "none requested",
  "action": "none",
  "see": "",
  "scan": "none requested",
  "config": [
    {
      "name": "cache",
      "state": "ONLINE",
      "read": 0,
      "write": 0,
      "cksum": 0
    }
  ],
  "errors": "No known data errors"
}
```

#### POST /api/zfs/pools/{pool_name}/scrub
Start pool scrubbing operation.

**Parameters:**
- `pool_name` (path): ZFS pool name

**Response:**
```json
{
  "success": true,
  "message": "Pool scrub started for cache",
  "pool_name": "cache"
}
```

#### GET /api/zfs/pools/{pool_name}/scrub/status
Get pool scrub status.

**Parameters:**
- `pool_name` (path): ZFS pool name

**Response:**
```json
{
  "pool_name": "cache",
  "scrub_in_progress": false,
  "scrub_completed": "2024-01-15 10:30:00",
  "errors_found": 0,
  "data_scrubbed": "500 GB",
  "throughput": "1.2 GB/s"
}
```

#### Dataset Management

#### GET /api/zfs/datasets/{dataset_name}/properties
Get dataset properties.

**Parameters:**
- `dataset_name` (path): ZFS dataset name
- `properties` (query): Comma-separated list of properties to retrieve

**Response:**
```json
{
  "dataset": "cache/appdata",
  "properties": {
    "used": "100G",
    "available": "400G",
    "compression": "lz4",
    "mountpoint": "/mnt/cache/appdata",
    "quota": "none",
    "reservation": "none"
  }
}
```

#### POST /api/zfs/datasets/{dataset_name}/properties
Set dataset properties.

**Parameters:**
- `dataset_name` (path): ZFS dataset name

**Request Body:**
```json
{
  "properties": {
    "compression": "gzip",
    "quota": "200G"
  }
}
```

**Response:**
```json
{
  "success": true,
  "dataset": "cache/appdata",
  "updated_properties": {
    "compression": "gzip",
    "quota": "200G"
  }
}
```

#### GET /api/zfs/datasets/{dataset_name}/usage
Get detailed dataset usage information.

**Parameters:**
- `dataset_name` (path): ZFS dataset name

**Response:**
```json
{
  "dataset": "cache/appdata",
  "used": "100G",
  "used_bytes": 107374182400,
  "available": "400G",
  "available_bytes": 429496729600,
  "referenced": "95G",
  "compression_ratio": "1.5x",
  "deduplication_ratio": "1.0x",
  "quota": "none",
  "reservation": "none"
}
```

#### Advanced Snapshot Management

#### GET /api/zfs/datasets/{dataset_name}/snapshots
List dataset snapshots with detailed information.

**Parameters:**
- `dataset_name` (path): ZFS dataset name

**Response:**
```json
{
  "dataset": "cache/appdata",
  "snapshots": [
    {
      "name": "backup_20240115_103000",
      "full_name": "cache/appdata@backup_20240115_103000",
      "creation": "2024-01-15 10:30:00",
      "used": "1.2G",
      "referenced": "100G",
      "clones": []
    }
  ]
}
```

#### POST /api/zfs/datasets/{dataset_name}/snapshots/incremental
Create incremental snapshot.

**Parameters:**
- `dataset_name` (path): ZFS dataset name

**Request Body:**
```json
{
  "base_snapshot": "backup_20240115_103000",
  "snapshot_name": "backup_20240115_143000"
}
```

**Response:**
```json
{
  "success": true,
  "snapshot_name": "cache/appdata@backup_20240115_143000",
  "base_snapshot": "cache/appdata@backup_20240115_103000",
  "size_saved": "45.2G"
}
```

#### POST /api/zfs/datasets/{dataset_name}/snapshots/retention
Apply snapshot retention policy.

**Parameters:**
- `dataset_name` (path): ZFS dataset name

**Request Body:**
```json
{
  "daily_retain": 7,
  "weekly_retain": 4,
  "monthly_retain": 6,
  "yearly_retain": 2
}
```

**Response:**
```json
{
  "success": true,
  "dataset": "cache/appdata",
  "deleted": 5,
  "deleted_snapshots": [
    "backup_20240101_103000",
    "backup_20240102_103000"
  ],
  "space_freed": "12.5G"
}
```

#### Advanced Backup Operations

#### POST /api/zfs/datasets/{dataset_name}/backup/strategy
Create backup strategy.

**Parameters:**
- `dataset_name` (path): ZFS dataset name

**Request Body:**
```json
{
  "backup_type": "incremental",
  "retention_policy": {
    "daily": 7,
    "weekly": 4,
    "monthly": 6,
    "yearly": 2
  }
}
```

**Response:**
```json
{
  "success": true,
  "strategy": {
    "dataset": "cache/appdata",
    "backup_type": "incremental",
    "next_action": "create_incremental_backup",
    "latest_snapshot": "backup_20240115_103000",
    "recommendations": [
      "Create incremental backup based on backup_20240115_103000"
    ]
  }
}
```

#### POST /api/zfs/datasets/{dataset_name}/backup/execute
Execute backup plan.

**Parameters:**
- `dataset_name` (path): ZFS dataset name

**Request Body:**
```json
{
  "strategy": {
    "backup_type": "incremental",
    "next_action": "create_incremental_backup"
  }
}
```

**Response:**
```json
{
  "success": true,
  "dataset": "cache/appdata",
  "executed_actions": [
    "Created incremental backup: cache/appdata@backup_20240115_143000",
    "Created bookmark: cache/appdata#backup_20240115_143000_bookmark"
  ]
}
```

#### POST /api/zfs/datasets/{dataset_name}/backup/restore
Restore from backup.

**Parameters:**
- `dataset_name` (path): ZFS dataset name

**Request Body:**
```json
{
  "backup_snapshot": "cache/appdata@backup_20240115_103000",
  "restore_type": "clone",
  "target_dataset": "cache/appdata_restored"
}
```

**Response:**
```json
{
  "success": true,
  "backup_snapshot": "cache/appdata@backup_20240115_103000",
  "target_dataset": "cache/appdata_restored",
  "restore_type": "clone",
  "action": "Created clone cache/appdata_restored from backup cache/appdata@backup_20240115_103000"
}
```

#### POST /api/zfs/datasets/{dataset_name}/backup/verify
Verify backup integrity.

**Parameters:**
- `dataset_name` (path): ZFS dataset name

**Request Body:**
```json
{
  "backup_snapshot": "cache/appdata@backup_20240115_103000"
}
```

**Response:**
```json
{
  "backup_snapshot": "cache/appdata@backup_20240115_103000",
  "overall_status": "healthy",
  "checks_performed": [
    "Snapshot existence check",
    "Snapshot properties check",
    "Parent pool health check"
  ],
  "issues_found": [],
  "size_bytes": 107374182400,
  "size_human": "100 GB",
  "pool_healthy": true
}
```

#### ZFS Encryption Support

#### POST /api/zfs/datasets/{dataset_name}/encryption/create
Create encrypted dataset.

**Parameters:**
- `dataset_name` (path): ZFS dataset name

**Request Body:**
```json
{
  "encryption_type": "aes-256-gcm",
  "key_format": "passphrase",
  "key_location": "/secure/keyfile"
}
```

**Response:**
```json
{
  "success": true,
  "dataset": "cache/secure_data",
  "encryption": "aes-256-gcm",
  "key_format": "passphrase",
  "key_location": "/secure/keyfile"
}
```

#### GET /api/zfs/datasets/{dataset_name}/encryption/status
Get encryption status.

**Parameters:**
- `dataset_name` (path): ZFS dataset name

**Response:**
```json
{
  "success": true,
  "encryption_status": {
    "dataset": "cache/secure_data",
    "encrypted": true,
    "encryption_algorithm": "aes-256-gcm",
    "key_status": "available",
    "key_format": "passphrase",
    "ready_for_use": true
  }
}
```

#### POST /api/zfs/datasets/{dataset_name}/encryption/load-key
Load encryption key.

**Parameters:**
- `dataset_name` (path): ZFS dataset name

**Request Body:**
```json
{
  "key_file": "/secure/keyfile"
}
```