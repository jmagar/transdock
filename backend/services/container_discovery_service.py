import logging
from typing import Dict, List, Optional
from ..models import (
    ContainerDiscoveryResult, ContainerAnalysis, ContainerSummary, 
    NetworkSummary, IdentifierType, VolumeMount
)
from ..docker_ops import DockerOperations, ContainerInfo

logger = logging.getLogger(__name__)


class ContainerDiscoveryService:
    """Handles container discovery and analysis operations"""
    
    def __init__(self, docker_ops: DockerOperations):
        self.docker_ops = docker_ops
    
    async def discover_containers(self, 
                                container_identifier: str,
                                identifier_type: IdentifierType,
                                label_filters: Optional[Dict[str, str]] = None,
                                source_host: Optional[str] = None,
                                source_ssh_user: str = "root") -> ContainerDiscoveryResult:
        """Discover containers for migration"""
        try:
            # Discover containers using unified Docker API
            if identifier_type == IdentifierType.PROJECT:
                containers = await self.docker_ops.discover_containers_by_project(
                    container_identifier, source_host, source_ssh_user
                )
            elif identifier_type == IdentifierType.NAME:
                containers = await self.docker_ops.discover_containers_by_name(
                    container_identifier, source_host, source_ssh_user
                )
            elif identifier_type == IdentifierType.LABELS:
                if not label_filters:
                    raise ValueError("Label filters required when using labels identifier type")
                containers = await self.docker_ops.discover_containers_by_labels(
                    label_filters, source_host, source_ssh_user
                )
            else:
                raise ValueError(f"Unsupported identifier type: {identifier_type}")

            # Convert to summary format
            container_summaries = []
            for container in containers:
                volumes = await self.docker_ops.get_container_volumes(container, source_host, source_ssh_user)
                summary = {
                    "id": container.id,
                    "name": container.name,
                    "image": container.image,
                    "state": container.state,
                    "status": container.status,
                    "project_name": container.project_name,
                    "service_name": container.service_name,
                    "volume_count": len([v for v in volumes if v.source.startswith('/')]),
                    "network_count": len(container.networks),
                    "port_count": len([p for p in container.ports.values() if p])
                }
                container_summaries.append(summary)

            return ContainerDiscoveryResult(
                containers=container_summaries,
                total_containers=len(containers),
                discovery_method=identifier_type.value,
                query=container_identifier
            )

        except Exception as e:
            logger.error(f"Container discovery failed: {e}")
            raise
    
    async def analyze_containers_for_migration(self,
                                             container_identifier: str,
                                             identifier_type: IdentifierType,
                                             label_filters: Optional[Dict[str, str]] = None,
                                             source_host: Optional[str] = None) -> ContainerAnalysis:
        """Analyze containers to provide migration insights"""
        try:
            # Get detailed container information using unified Docker API
            if identifier_type == IdentifierType.PROJECT:
                containers = await self.docker_ops.discover_containers_by_project(
                    container_identifier, source_host
                )
            elif identifier_type == IdentifierType.NAME:
                containers = await self.docker_ops.discover_containers_by_name(
                    container_identifier, source_host
                )
            else:
                if not label_filters:
                    raise ValueError("Label filters required when using labels identifier type")
                containers = await self.docker_ops.discover_containers_by_labels(
                    label_filters, source_host
                )

            # Analyze containers
            container_summaries = []
            networks = []
            total_volumes = 0
            total_bind_mounts = 0
            warnings = []
            recommendations = []

            for container in containers:
                volumes = await self.docker_ops.get_container_volumes(container, source_host)
                bind_mounts = [v for v in volumes if v.source.startswith('/')]
                
                container_summary = ContainerSummary(
                    id=container.id,
                    name=container.name,
                    image=container.image,
                    state=container.state,
                    status=container.status,
                    project_name=container.project_name,
                    service_name=container.service_name,
                    volume_count=len(volumes),
                    network_count=len(container.networks),
                    port_count=len([p for p in container.ports.values() if p])
                )
                container_summaries.append(container_summary)
                
                total_volumes += len(volumes)
                total_bind_mounts += len(bind_mounts)

                # Generate warnings
                if container.state != 'running':
                    warnings.append(f"Container {container.name} is not running")
                
                if not bind_mounts:
                    warnings.append(f"Container {container.name} has no persistent data volumes")

            # Get project networks if this is a project-based discovery
            if identifier_type == IdentifierType.PROJECT and containers:
                project_networks = await self.docker_ops.get_project_networks(container_identifier, source_host)
                for net in project_networks:
                    network_summary = NetworkSummary(
                        id=net.id,
                        name=net.name,
                        driver=net.driver,
                        scope=net.scope,
                        project_name=container_identifier
                    )
                    networks.append(network_summary)

            # Determine complexity
            complexity = "simple"
            if len(containers) > 3 or len(networks) > 2:
                complexity = "medium"
            if len(containers) > 5 or total_bind_mounts > 10 or len(networks) > 3:
                complexity = "complex"

            # Generate recommendations
            if total_bind_mounts > 0:
                recommendations.append("Consider using ZFS snapshots for consistent data migration")
            
            if len(networks) > 1:
                recommendations.append("Custom networks will be recreated on the target system")
            
            if complexity == "complex":
                recommendations.append("Consider migrating containers in smaller batches")

            return ContainerAnalysis(
                containers=container_summaries,
                networks=networks,
                total_volumes=total_volumes,
                total_bind_mounts=total_bind_mounts,
                migration_complexity=complexity,
                warnings=warnings,
                recommendations=recommendations
            )

        except Exception as e:
            logger.error(f"Container analysis failed: {e}")
            raise
    
    def _deduplicate_volumes(self, volumes: List[VolumeMount]) -> List[VolumeMount]:
        """Remove duplicate volume mounts"""
        unique_volumes = []
        seen_sources = set()
        
        for volume in volumes:
            if volume.source not in seen_sources:
                unique_volumes.append(volume)
                seen_sources.add(volume.source)
        
        return unique_volumes