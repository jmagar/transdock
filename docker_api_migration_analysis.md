# Docker API Migration Analysis

## Executive Summary

Switching from CLI-based Docker operations to Docker API would represent a paradigm shift for TransDock, eliminating the need for hardcoded paths and compose file parsing while providing more robust container discovery and management capabilities.

## Current vs. Proposed Architecture

### Current CLI-Based Approach
```
User Input (compose_dataset: "authelia") 
    ↓
Find compose file in /mnt/cache/compose/authelia/
    ↓
Parse docker-compose.yml to extract volumes
    ↓
Filter volumes by hardcoded paths (/mnt/cache/appdata/, /mnt/cache/compose/)
    ↓
Migrate data using ZFS/rsync
    ↓
Update compose file with new paths
    ↓
Deploy updated compose file on target
```

### Proposed Docker API Approach
```
User Input (container_name or label_selector)
    ↓
Query Docker API for container(s) and their configuration
    ↓
Extract volumes, networks, env vars directly from running containers
    ↓
Determine data locations from container inspection
    ↓
Migrate data using ZFS/rsync
    ↓
Recreate containers on target with updated volume paths
```

## Key Benefits

### 1. **Eliminates Path Dependencies**
- No need for `TRANSDOCK_COMPOSE_BASE` or `TRANSDOCK_APPDATA_BASE`
- Works with containers regardless of where compose files are stored
- Supports containers created outside of compose workflows

### 2. **Real-Time Container State**
- Gets actual running configuration vs. static compose files
- Handles cases where containers were modified after creation
- Discovers volumes that may not be in original compose files

### 3. **Container Discovery Flexibility**
```python
# Current: Must know exact compose dataset path
compose_dataset = "authelia"  # Assumes /mnt/cache/compose/authelia/

# Proposed: Multiple discovery methods
container_name = "authelia"
label_selector = "com.docker.compose.project=authelia"
service_name = "authelia"
```

### 4. **Robust Volume Discovery**
```python
# Current: Limited to hardcoded paths
if host_path.startswith('/mnt/cache/appdata/') or host_path.startswith('/mnt/cache/compose/'):
    # Include in migration

# Proposed: Discover all bind mounts and volumes
for mount in container.attrs['Mounts']:
    if mount['Type'] == 'bind':
        # Migrate any bind mount
        volume_mounts.append(mount)
```

## Implementation Strategy

### Phase 1: Docker API Integration

```python
import docker
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class ContainerInfo:
    id: str
    name: str
    image: str
    state: str
    labels: Dict[str, str]
    mounts: List[Dict[str, Any]]
    networks: List[str]
    environment: Dict[str, str]
    ports: Dict[str, Any]
    command: List[str]
    working_dir: str
    user: str
    restart_policy: Dict[str, Any]
    
class DockerAPIOperations:
    def __init__(self):
        self.client = docker.from_env()
    
    async def discover_containers_by_project(self, project_name: str) -> List[ContainerInfo]:
        """Discover containers by Docker Compose project name"""
        containers = []
        
        # Find containers with compose project label
        for container in self.client.containers.list(all=True):
            labels = container.labels
            if labels.get('com.docker.compose.project') == project_name:
                containers.append(self._extract_container_info(container))
        
        return containers
    
    async def discover_containers_by_name(self, name_pattern: str) -> List[ContainerInfo]:
        """Discover containers by name pattern"""
        containers = []
        
        for container in self.client.containers.list(all=True):
            if name_pattern in container.name:
                containers.append(self._extract_container_info(container))
        
        return containers
    
    def _extract_container_info(self, container) -> ContainerInfo:
        """Extract comprehensive container information"""
        return ContainerInfo(
            id=container.id,
            name=container.name,
            image=container.image.tags[0] if container.image.tags else str(container.image.id),
            state=container.status,
            labels=container.labels,
            mounts=container.attrs['Mounts'],
            networks=list(container.attrs['NetworkSettings']['Networks'].keys()),
            environment=self._parse_environment(container.attrs['Config']['Env']),
            ports=container.attrs['NetworkSettings']['Ports'],
            command=container.attrs['Config']['Cmd'] or [],
            working_dir=container.attrs['Config']['WorkingDir'],
            user=container.attrs['Config']['User'],
            restart_policy=container.attrs['HostConfig']['RestartPolicy']
        )
    
    def _parse_environment(self, env_list: List[str]) -> Dict[str, str]:
        """Parse environment variables from container config"""
        env_dict = {}
        for env_var in env_list:
            if '=' in env_var:
                key, value = env_var.split('=', 1)
                env_dict[key] = value
        return env_dict
    
    async def get_container_volumes(self, container_info: ContainerInfo) -> List[VolumeMount]:
        """Extract volume mounts from container information"""
        volume_mounts = []
        
        for mount in container_info.mounts:
            if mount['Type'] == 'bind':
                volume_mounts.append(VolumeMount(
                    source=mount['Source'],
                    target=mount['Destination'],
                    is_dataset=False  # Will be determined later
                ))
        
        return volume_mounts
    
    async def stop_containers(self, container_infos: List[ContainerInfo]) -> bool:
        """Stop multiple containers"""
        try:
            for container_info in container_infos:
                container = self.client.containers.get(container_info.id)
                if container.status == 'running':
                    container.stop()
            return True
        except Exception as e:
            logger.error(f"Failed to stop containers: {e}")
            return False
    
    async def recreate_containers(self, 
                                 container_infos: List[ContainerInfo], 
                                 volume_mapping: Dict[str, str]) -> bool:
        """Recreate containers with updated volume paths"""
        try:
            for container_info in container_infos:
                await self._recreate_single_container(container_info, volume_mapping)
            return True
        except Exception as e:
            logger.error(f"Failed to recreate containers: {e}")
            return False
    
    async def _recreate_single_container(self, 
                                        container_info: ContainerInfo, 
                                        volume_mapping: Dict[str, str]):
        """Recreate a single container with updated configuration"""
        # Update volume mounts
        updated_mounts = []
        for mount in container_info.mounts:
            if mount['Type'] == 'bind':
                source = mount['Source']
                new_source = volume_mapping.get(source, source)
                updated_mounts.append(f"{new_source}:{mount['Destination']}")
        
        # Create container configuration
        container_config = {
            'image': container_info.image,
            'name': container_info.name,
            'environment': container_info.environment,
            'volumes': updated_mounts,
            'ports': self._convert_ports(container_info.ports),
            'working_dir': container_info.working_dir,
            'user': container_info.user,
            'restart_policy': container_info.restart_policy,
            'labels': container_info.labels,
            'command': container_info.command,
            'detach': True
        }
        
        # Remove old container
        try:
            old_container = self.client.containers.get(container_info.id)
            old_container.remove(force=True)
        except docker.errors.NotFound:
            pass
        
        # Create new container
        new_container = self.client.containers.run(**container_config)
        logger.info(f"Recreated container {container_info.name} with ID {new_container.id}")
    
    def _convert_ports(self, ports_config: Dict[str, Any]) -> Dict[str, int]:
        """Convert port configuration from inspect format to create format"""
        port_bindings = {}
        for container_port, host_config in ports_config.items():
            if host_config:
                host_port = host_config[0]['HostPort']
                port_bindings[container_port] = int(host_port)
        return port_bindings
```

### Phase 2: Enhanced Migration Service

```python
class EnhancedMigrationService:
    def __init__(self):
        self.zfs_ops = ZFSOperations()
        self.docker_api_ops = DockerAPIOperations()
        self.transfer_ops = TransferOperations(zfs_ops=self.zfs_ops)
        self.host_service = HostService()
        self.active_migrations = {}
    
    async def start_migration_by_container(self, 
                                         container_identifier: str,
                                         identifier_type: str,  # 'name', 'project', 'label'
                                         target_host: str,
                                         target_base_path: str,
                                         **kwargs) -> str:
        """Start migration using container-based discovery"""
        migration_id = str(uuid.uuid4())
        
        # Discover containers
        if identifier_type == 'project':
            containers = await self.docker_api_ops.discover_containers_by_project(container_identifier)
        elif identifier_type == 'name':
            containers = await self.docker_api_ops.discover_containers_by_name(container_identifier)
        else:
            raise ValueError(f"Unsupported identifier type: {identifier_type}")
        
        if not containers:
            raise ValueError(f"No containers found for {identifier_type}: {container_identifier}")
        
        # Extract volumes from all containers
        all_volumes = []
        for container in containers:
            volumes = await self.docker_api_ops.get_container_volumes(container)
            all_volumes.extend(volumes)
        
        # Remove duplicates
        unique_volumes = self._deduplicate_volumes(all_volumes)
        
        # Create migration request
        migration_request = MigrationRequest(
            compose_dataset=container_identifier,  # For compatibility
            target_host=target_host,
            target_base_path=target_base_path,
            **kwargs
        )
        
        # Store container info for recreation
        self.active_migrations[migration_id] = MigrationStatus(
            id=migration_id,
            status="discovered",
            progress=0,
            message=f"Discovered {len(containers)} containers with {len(unique_volumes)} volumes",
            compose_dataset=container_identifier,
            target_host=target_host,
            target_base_path=target_base_path,
            volumes=unique_volumes
        )
        
        # Add container metadata
        self.active_migrations[migration_id].containers = containers
        
        # Start migration process
        asyncio.create_task(self._execute_api_migration(migration_id, migration_request))
        
        return migration_id
    
    async def _execute_api_migration(self, migration_id: str, request: MigrationRequest):
        """Execute migration using Docker API approach"""
        try:
            containers = self.active_migrations[migration_id].containers
            
            # Step 1: Stop containers
            await self._update_status(migration_id, "stopping", 10, "Stopping containers")
            success = await self.docker_api_ops.stop_containers(containers)
            if not success:
                raise Exception("Failed to stop containers")
            
            # Step 2: Migrate data (same as current approach)
            await self._update_status(migration_id, "migrating", 30, "Migrating data")
            volumes = self.active_migrations[migration_id].volumes
            
            # ... existing migration logic for data transfer ...
            
            # Step 3: Recreate containers on target
            await self._update_status(migration_id, "recreating", 80, "Recreating containers on target")
            
            # Create volume mapping for target paths
            volume_mapping = {}
            for volume in volumes:
                old_path = volume.source
                new_path = f"{request.target_base_path}/{os.path.basename(old_path)}"
                volume_mapping[old_path] = new_path
            
            # Recreate containers on target host
            success = await self._recreate_containers_on_target(
                containers, volume_mapping, request.target_host, request.ssh_user, request.ssh_port
            )
            
            if not success:
                raise Exception("Failed to recreate containers on target")
            
            # Step 4: Complete migration
            await self._update_status(migration_id, "completed", 100, "Migration completed successfully")
            
        except Exception as e:
            await self._update_error(migration_id, str(e))
    
    async def _recreate_containers_on_target(self, 
                                           containers: List[ContainerInfo],
                                           volume_mapping: Dict[str, str],
                                           target_host: str,
                                           ssh_user: str,
                                           ssh_port: int) -> bool:
        """Recreate containers on target host using Docker API"""
        try:
            # Generate Docker commands for remote execution
            for container in containers:
                docker_run_cmd = self._generate_docker_run_command(container, volume_mapping)
                
                # Execute on remote host
                ssh_cmd = [
                    "ssh", "-p", str(ssh_port), f"{ssh_user}@{target_host}",
                    docker_run_cmd
                ]
                
                returncode, stdout, stderr = await self.docker_api_ops.run_command(ssh_cmd)
                if returncode != 0:
                    logger.error(f"Failed to recreate container {container.name}: {stderr}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to recreate containers on target: {e}")
            return False
    
    def _generate_docker_run_command(self, 
                                   container: ContainerInfo, 
                                   volume_mapping: Dict[str, str]) -> str:
        """Generate docker run command from container info"""
        cmd_parts = ["docker", "run", "-d"]
        
        # Add name
        cmd_parts.extend(["--name", container.name])
        
        # Add volumes
        for mount in container.mounts:
            if mount['Type'] == 'bind':
                old_source = mount['Source']
                new_source = volume_mapping.get(old_source, old_source)
                cmd_parts.extend(["-v", f"{new_source}:{mount['Destination']}"])
        
        # Add ports
        for container_port, host_config in container.ports.items():
            if host_config:
                host_port = host_config[0]['HostPort']
                cmd_parts.extend(["-p", f"{host_port}:{container_port}"])
        
        # Add environment variables
        for key, value in container.environment.items():
            cmd_parts.extend(["-e", f"{key}={value}"])
        
        # Add labels
        for key, value in container.labels.items():
            cmd_parts.extend(["--label", f"{key}={value}"])
        
        # Add restart policy
        if container.restart_policy.get('Name'):
            cmd_parts.extend(["--restart", container.restart_policy['Name']])
        
        # Add image
        cmd_parts.append(container.image)
        
        # Add command
        if container.command:
            cmd_parts.extend(container.command)
        
        return " ".join(cmd_parts)
```

### Phase 3: API Updates

```python
# New API endpoints for container-based migration
@app.post("/migrations/by-container")
async def start_migration_by_container(request: ContainerMigrationRequest):
    """Start migration using container discovery"""
    try:
        migration_id = await migration_service.start_migration_by_container(
            container_identifier=request.container_identifier,
            identifier_type=request.identifier_type,
            target_host=request.target_host,
            target_base_path=request.target_base_path,
            ssh_user=request.ssh_user,
            ssh_port=request.ssh_port
        )
        
        return MigrationResponse(
            migration_id=migration_id,
            status="started",
            message="Container-based migration started successfully"
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/containers/discover")
async def discover_containers(
    project_name: Optional[str] = None,
    container_name: Optional[str] = None,
    label_selector: Optional[str] = None
):
    """Discover containers for migration"""
    try:
        docker_ops = DockerAPIOperations()
        
        if project_name:
            containers = await docker_ops.discover_containers_by_project(project_name)
        elif container_name:
            containers = await docker_ops.discover_containers_by_name(container_name)
        else:
            raise ValueError("Must specify project_name or container_name")
        
        return {
            "containers": [
                {
                    "id": c.id,
                    "name": c.name,
                    "image": c.image,
                    "state": c.state,
                    "volumes": len([m for m in c.mounts if m['Type'] == 'bind'])
                }
                for c in containers
            ],
            "total_containers": len(containers)
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

## Migration Benefits

### 1. **Simplified User Experience**
```bash
# Current approach
curl -X POST "http://localhost:8000/migrations" \
  -H "Content-Type: application/json" \
  -d '{
    "compose_dataset": "authelia",  # Must know exact path structure
    "target_host": "remote-server",
    "target_base_path": "/opt/docker"
  }'

# New approach
curl -X POST "http://localhost:8000/migrations/by-container" \
  -H "Content-Type: application/json" \
  -d '{
    "container_identifier": "authelia",  # Just the name/project
    "identifier_type": "project",
    "target_host": "remote-server",
    "target_base_path": "/opt/docker"
  }'
```

### 2. **Universal Container Support**
- Works with containers created by docker-compose
- Works with containers created by docker run
- Works with containers created by orchestration tools
- Works with containers with modified configurations

### 3. **Elimination of Path Dependencies**
- No need to configure base paths
- No hardcoded directory structures
- Works with any volume mount structure
- Dynamic discovery of actual data locations

### 4. **Better Error Handling**
- Structured API responses vs. parsing command output
- Real container state vs. assumed state from files
- Detailed error information from Docker daemon

## Implementation Challenges

### 1. **Compose-Specific Features**
- Networks created by compose
- Service dependencies
- Compose labels and metadata
- Environment variable substitution

**Solution**: Preserve compose metadata in labels and recreate networks

### 2. **Container Dependencies**
- Service startup order
- Health checks
- Inter-container communication

**Solution**: Implement dependency resolution from container links/networks

### 3. **Remote Docker API Access**
- API access over SSH tunnels
- Authentication and security
- Docker daemon accessibility

**Solution**: Use SSH port forwarding or remote docker CLI commands

## Compatibility Strategy

### Phase 1: Parallel Implementation
- Keep existing compose-based approach
- Add new Docker API approach
- Allow users to choose migration method

### Phase 2: Migration Path
- Provide migration tools for existing workflows
- Update documentation and examples
- Deprecate old approach with warnings

### Phase 3: Full Transition
- Remove compose-based approach
- Simplify codebase
- Full Docker API integration

## Conclusion

Switching to Docker API would be a **major architectural improvement** that:

1. **Eliminates Path Dependencies**: No more hardcoded compose/appdata paths
2. **Improves Reliability**: Real container state vs. static compose files
3. **Enhances Flexibility**: Works with any container creation method
4. **Simplifies User Experience**: Just specify container names/projects
5. **Provides Better Error Handling**: Structured API responses

The migration would require significant development effort but would result in a more robust, flexible, and user-friendly system that truly works with "any Docker container" regardless of how it was created or where its files are stored.

This approach aligns perfectly with the modern containerization philosophy of treating containers as the primary abstraction rather than the underlying file system structure.