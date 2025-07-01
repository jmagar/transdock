# TransDock - Docker Stack Migration Tool

TransDock is a powerful tool for migrating Docker Compose stacks between machines using ZFS snapshots. It's designed specifically for Unraid environments but can work with any ZFS-enabled system.

## Features

- **Automated Migration**: Migrate entire Docker Compose stacks with a single API call
- **ZFS Integration**: Leverages ZFS snapshots for consistent data transfer
- **Intelligent Transfer**: Automatically chooses between ZFS send/receive or rsync based on target capabilities
- **Volume Management**: Automatically detects and converts directories to ZFS datasets
- **Path Updating**: Updates Docker Compose files with new paths on the target machine
- **RESTful API**: Fully featured FastAPI backend ready for frontend integration
- **Progress Tracking**: Real-time migration progress and status updates

## Architecture

TransDock consists of several key components:

1. **ZFS Operations** (`zfs_ops.py`) - Handles dataset creation, snapshots, and ZFS send/receive
2. **Docker Operations** (`docker_ops.py`) - Manages Docker Compose parsing and stack control
3. **Transfer Operations** (`transfer_ops.py`) - Handles data transfer via ZFS send or rsync
4. **Migration Service** (`migration_service.py`) - Orchestrates the entire migration process
5. **FastAPI App** (`main.py`) - Provides RESTful API endpoints

## Installation

### Prerequisites

- Python 3.8+
- ZFS utilities (`zfs`, `zpool`)
- Docker and docker-compose
- rsync (for fallback transfers)
- SSH access to target machines

### Setup

1. Clone or copy the TransDock files to your desired location:
   ```bash
   # Files should be in /mnt/cache/code/transdock/
   ```

2. Install Python dependencies:
   ```bash
   cd /mnt/cache/code/transdock
   pip3 install -r requirements.txt
   ```

3. Start the service:
   ```bash
   ./start.sh
   ```

The API will be available at `http://localhost:8000` with documentation at `http://localhost:8000/docs`.

## Usage

### API Endpoints

#### Start Migration
```http
POST /migrations
Content-Type: application/json

{
  "compose_dataset": "cache/compose/authelia",
  "target_host": "192.168.1.100",
  "target_base_path": "/home/jmagar",
  "ssh_user": "root",
  "ssh_port": 22,
  "force_rsync": false
}
```

#### Check Migration Status
```http
GET /migrations/{migration_id}
```

#### List All Migrations
```http
GET /migrations
```

#### System Information
```http
GET /system/info
GET /zfs/status
GET /datasets
GET /compose/stacks
```

### Example Migration Process

1. **Analyze a stack** to see what volumes will be migrated:
   ```http
   POST /compose/authelia/analyze
   ```

2. **Start migration** with your target details:
   ```json
   {
     "compose_dataset": "authelia",
     "target_host": "192.168.1.100", 
     "target_base_path": "/home/jmagar"
   }
   ```

3. **Monitor progress** using the returned migration ID:
   ```http
   GET /migrations/12345678-1234-1234-1234-123456789abc
   ```

## Migration Process

TransDock follows this workflow:

1. **Validation** - Checks ZFS availability and validates inputs
2. **Analysis** - Parses docker-compose file and identifies volume mounts
3. **Stopping** - Stops the Docker Compose stack
4. **Dataset Conversion** - Converts directories to ZFS datasets if needed
5. **Snapshotting** - Creates ZFS snapshots of all datasets
6. **Transfer Method Selection** - Chooses ZFS send or rsync based on target capabilities
7. **Data Transfer** - Transfers all data to target machine
8. **Path Updates** - Updates docker-compose file with new paths
9. **Stack Startup** - Starts the migrated stack on the target
10. **Cleanup** - Removes temporary snapshots

## Configuration

### Environment Variables

You can customize behavior through environment variables:

- `TRANSDOCK_PORT` - API port (default: 8000)
- `TRANSDOCK_HOST` - API host (default: 0.0.0.0)
- `COMPOSE_BASE_PATH` - Base path for compose files (default: /mnt/cache/compose)
- `APPDATA_BASE_PATH` - Base path for app data (default: /mnt/cache/appdata)

### Custom Paths

Edit the configuration in the respective modules:

```python
# docker_ops.py
self.compose_base_path = "/mnt/cache/compose"
self.appdata_base_path = "/mnt/cache/appdata"

# zfs_ops.py  
self.pool_name = "cache"  # Default Unraid cache pool
```

## Security Considerations

- Ensure SSH key authentication is set up between source and target machines
- Consider using SSH agent forwarding for automated deployments
- Restrict API access using firewalls or reverse proxies
- Validate target paths to prevent directory traversal attacks

## Troubleshooting

### Common Issues

1. **ZFS Not Available**
   - Ensure ZFS kernel modules are loaded
   - Check if `zfs` and `zpool` commands are available

2. **SSH Connection Failed**
   - Verify SSH key authentication is working
   - Check firewall settings on target machine
   - Ensure SSH daemon is running on target

3. **Permission Denied**
   - Run TransDock as root or with appropriate ZFS permissions
   - Ensure SSH user has sufficient privileges on target

4. **Dataset Creation Failed**
   - Check available space in ZFS pool
   - Verify parent dataset exists
   - Ensure proper ZFS permissions

### Logging

TransDock provides detailed logging. Check logs for specific error messages:

```bash
# Run with increased verbosity
PYTHONPATH=/mnt/cache/code/transdock python3 -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from main import app
import uvicorn
uvicorn.run(app, host='0.0.0.0', port=8000, log_level='debug')
"
```

## Development

### Project Structure

```
transdock/
├── main.py              # FastAPI application
├── models.py            # Pydantic data models
├── migration_service.py # Main orchestration service
├── zfs_ops.py          # ZFS operations
├── docker_ops.py       # Docker operations  
├── transfer_ops.py     # Transfer operations
├── requirements.txt    # Python dependencies
├── start.sh           # Startup script
└── README.md          # This file
```

### Adding Features

To extend TransDock:

1. Add new models to `models.py`
2. Implement operations in appropriate `*_ops.py` files
3. Update `migration_service.py` for orchestration changes
4. Add API endpoints to `main.py`

## Future Enhancements

- Web-based frontend interface
- Support for additional container orchestrators (Kubernetes, Swarm)
- Database persistence for migration history
- Webhook notifications for migration events
- Advanced scheduling and retry mechanisms
- Support for incremental transfers

## License

TransDock is released under the MIT License. See LICENSE file for details.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## Support

For issues and questions:

1. Check the troubleshooting section
2. Review API documentation at `/docs`
3. Create an issue with detailed error information
4. Include relevant log output and system information 