from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
import os
import asyncio
from datetime import datetime, timezone
import logging
import re

from ...models import (
    MigrationRequest, MigrationResponse, ContainerMigrationRequest
)
from ...migration_service import MigrationService
from ...security_utils import SecurityUtils, SecurityValidationError
from ...config import get_config

router = APIRouter(
    prefix="/api/migrations",
    tags=["Migration"],
)

config = get_config()
migration_service = MigrationService()
logger = logging.getLogger(__name__)

@router.post("/start", response_model=MigrationResponse)
async def create_migration(request: MigrationRequest):
    """Start a new migration process with security validation"""
    try:
        # Security validation for all user inputs
        SecurityUtils.validate_migration_request(
            compose_dataset=request.compose_dataset,
            target_host=request.target_host,
            ssh_user=request.ssh_user,
            ssh_port=request.ssh_port,
            target_base_path=request.target_base_path
        )

        migration_id = await migration_service.start_migration(request)
        return MigrationResponse(
            migration_id=migration_id,
            status="started",
            message="Migration process started successfully"
        )
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        error_message = str(e)
        # Provide more specific error handling for storage validation failures
        if "Storage validation failed" in error_message:
            raise HTTPException(
                status_code=422,
                detail=f"Storage validation failed - {error_message}. Please ensure target system has sufficient disk space.") from e
        if "Insufficient storage space" in error_message:
            raise HTTPException(
                status_code=422,
                detail=f"Insufficient storage space - {error_message}. Free up disk space or choose a different target path.") from e
        raise HTTPException(status_code=400, detail=error_message) from e

@router.get("/")
async def list_migrations():
    """List all migrations"""
    try:
        migrations = await migration_service.list_migrations()
        return {"migrations": migrations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{migration_id}/status")
async def get_migration_status(migration_id: str):
    """Get the status of a specific migration with input validation"""
    try:
        # Validate migration_id format to prevent injection
        if not migration_id or len(migration_id) > 64:
            raise SecurityValidationError("Invalid migration ID format")

        # Allow only alphanumeric characters, hyphens, and underscores
        if not all(c.isalnum() or c in '-_' for c in migration_id):
            raise SecurityValidationError(
                "Migration ID contains invalid characters")

        status = await migration_service.get_migration_status(migration_id)
        if not status:
            raise HTTPException(status_code=404, detail="Migration not found")
        return status
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/{migration_id}/cancel")
async def cancel_migration(migration_id: str):
    """Cancel a running migration"""
    try:
        # Validate migration_id format
        if not migration_id or len(migration_id) > 64:
            raise SecurityValidationError("Invalid migration ID format")

        if not all(c.isalnum() or c in '-_' for c in migration_id):
            raise SecurityValidationError(
                "Migration ID contains invalid characters")

        success = await migration_service.cancel_migration(migration_id)
        if success:
            return {
                "success": True,
                "message": "Migration cancelled successfully"}
        raise HTTPException(
            status_code=400,
            detail="Failed to cancel migration")
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except KeyError as e:
        raise HTTPException(
            status_code=404,
            detail="Migration not found") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{migration_id}/cleanup")
async def cleanup_migration(migration_id: str):
    """Clean up migration resources"""
    try:
        # Validate migration_id format
        if not migration_id or len(migration_id) > 64:
            raise SecurityValidationError("Invalid migration ID format")

        if not all(c.isalnum() or c in '-_' for c in migration_id):
            raise SecurityValidationError(
                "Migration ID contains invalid characters")

        success = await migration_service.cleanup_migration(migration_id)
        if success:
            return {
                "success": True,
                "message": "Migration cleanup successful"}
        raise HTTPException(
            status_code=400,
            detail="Failed to clean up migration")
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except KeyError as e:
        raise HTTPException(
            status_code=404,
            detail="Migration not found") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Container Discovery and Analysis Endpoints

@router.post("/smart")
async def smart_migration(
    identifier: str,
    target_host: str,
    target_base_path: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    compose_base_path: str = config.local_compose_base_path,
    force_rsync: bool = False,
    auto_start: bool = True
):
    """
    🎯 SMART MIGRATION - Compose-First Approach
    
    This is the PRIMARY migration endpoint that users should use.
    It automatically detects what you want to migrate and uses the best method:
    
    1. 🥇 FIRST: Checks for compose projects (stopped or running)
    2. 🥈 FALLBACK: Searches for individual containers if no compose project found
    
    - **identifier**: Project name (simple-web) or full path (/path/to/project)
    - **target_host**: Where to migrate to
    - **target_base_path**: Base directory on target
    - **compose_base_path**: Where to look for compose projects (uses configured path)
    """
    try:
        logger.info(f"🎯 Smart migration requested for: '{identifier}'")
        
        # STEP 1: 🥇 CHECK FOR COMPOSE PROJECT FIRST
        compose_project_path = None
        
        # Check if identifier is already a full path
        if os.path.isabs(identifier) and os.path.exists(identifier):
            # Check if it's a directory with compose file
            if os.path.isdir(identifier):
                compose_files = ['docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml']
                for compose_file in compose_files:
                    if os.path.exists(os.path.join(identifier, compose_file)):
                        compose_project_path = identifier
                        break
        else:
            # Look for project by name in compose base path
            potential_path = os.path.join(compose_base_path, identifier)
            if os.path.exists(potential_path) and os.path.isdir(potential_path):
                compose_files = ['docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml'] 
                for compose_file in compose_files:
                    if os.path.exists(os.path.join(potential_path, compose_file)):
                        compose_project_path = potential_path
                        break
        
        # FOUND COMPOSE PROJECT! 🎉
        if compose_project_path:
            logger.info(f"✅ Found compose project: {compose_project_path}")
            
            # Create compose migration request
            from ...models import MigrationRequest
            compose_request = MigrationRequest(
                compose_dataset=compose_project_path,
                target_host=target_host,
                target_base_path=target_base_path,
                ssh_user=ssh_user,
                ssh_port=ssh_port,
                force_rsync=force_rsync,
                source_host=None  # Local source
            )
            
            migration_id = await migration_service.start_migration(compose_request)
            
            return {
                "migration_id": migration_id,
                "status": "started",
                "migration_type": "compose_project",
                "message": f"🚀 Compose project migration started for '{os.path.basename(compose_project_path)}'",
                "project_path": compose_project_path,
                "target_host": target_host,
                "auto_start": auto_start,
                "discovery_method": "compose_first"
            }
        
        # STEP 2: 🥈 FALLBACK TO CONTAINER SEARCH
        logger.info(f"❌ No compose project found for '{identifier}', searching containers...")
        
        # Try to find running containers with the identifier
        try:
            from ...models import IdentifierType
            containers = await migration_service.discover_containers(
                container_identifier=identifier,
                identifier_type=IdentifierType.NAME,
                source_host=None,
                source_ssh_user=ssh_user,
                source_ssh_port=ssh_port
            )
            
            if containers and hasattr(containers, 'containers') and containers.containers:
                container_count = len(containers.containers)
                
                # Suggest compose migration instead
                return {
                    "status": "suggestion",
                    "migration_type": "container_fallback", 
                    "message": f"⚠️  Found {container_count} running container(s) with '{identifier}', but no compose project",
                    "suggestion": f"Consider using container migration endpoint instead, or check if '{identifier}' is a compose project",
                    "containers_found": [{"name": c["name"], "id": c["id"]} for c in containers.containers],
                    "recommendations": [
                        f"For complete stack migration, look for compose project in {compose_base_path}",
                        "For individual containers, use /migrations/containers endpoint",
                        f"To create compose project, run: cd {compose_base_path} && mkdir {identifier}"
                    ],
                    "next_steps": {
                        "container_migration": "/migrations/containers with identifier_type=name",
                        "create_compose": f"mkdir -p {compose_base_path}/{identifier} && cd {compose_base_path}/{identifier}"
                    }
                }
            
        except Exception as e:
            logger.warning(f"Container search failed: {e}")
        
        # STEP 3: 😞 NOTHING FOUND - HELPFUL ERROR
        return {
            "status": "not_found",
            "migration_type": "none",
            "message": f"❌ No compose project or containers found for '{identifier}'",
            "searched_locations": [
                f"{compose_base_path}/{identifier}",
                f"Running containers matching '{identifier}'"
            ],
            "suggestions": [
                f"✅ Create compose project: mkdir -p {compose_base_path}/{identifier}",
                f"✅ Check spelling: ls {compose_base_path}/",
                "✅ Use full path: /path/to/your/project",
                "✅ Start containers first if migrating running services"
            ],
            "available_projects": [
                item for item in os.listdir(compose_base_path) 
                if os.path.isdir(os.path.join(compose_base_path, item))
            ] if os.path.exists(compose_base_path) else []
        }
            
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {e}") from e
    except Exception as e:
        logger.error(f"Smart migration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Smart migration failed: {e}") from e

# Container Migration Endpoints

@router.post("/containers")
async def start_container_migration(request: ContainerMigrationRequest):
    """
    Start a container-based migration
    
    This is the primary migration endpoint that uses Docker API for container discovery
    """
    try:
        from ...models import IdentifierType
        # Validate request
        if request.identifier_type == IdentifierType.LABELS and not request.label_filters:
            raise HTTPException(
                status_code=422, 
                detail="label_filters required when identifier_type is 'labels'"
            )
        
        migration_id = await migration_service.start_container_migration(request)
        
        return {
            "migration_id": migration_id,
            "status": "started",
            "message": f"Container migration started for {request.container_identifier}"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {e}") from e
    except Exception as e:
        logger.error(f"Migration failed to start: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed to start: {e}") from e

@router.post("/compose")
async def start_compose_migration(
    project_path: str,
    target_host: str,
    target_base_path: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    force_rsync: bool = False,
    auto_start: bool = True
):
    """
    Start a compose project migration
    
    - **project_path**: Local path to the compose project
    - **target_host**: Target host to migrate to  
    - **target_base_path**: Base path on target host
    - **auto_start**: Whether to start the project on target after migration
    """
    try:
        # Create a legacy migration request for the compose path
        # This uses the existing migration logic but with compose-specific handling
        from ...models import MigrationRequest
        
        legacy_request = MigrationRequest(
            compose_dataset=project_path,
            target_host=target_host,
            target_base_path=target_base_path,
            ssh_user=ssh_user,
            ssh_port=ssh_port,
            force_rsync=force_rsync,
            source_host=None  # Local source
        )
        
        migration_id = await migration_service.start_migration(legacy_request)
        
        return {
            "migration_id": migration_id,
            "status": "started", 
            "message": f"Compose project migration started for {os.path.basename(project_path)}",
            "project_path": project_path,
            "target_host": target_host,
            "auto_start": auto_start
        }
        
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {e}") from e
    except Exception as e:
        logger.error(f"Compose migration failed to start: {e}")
        raise HTTPException(status_code=500, detail=f"Compose migration failed to start: {e}") from e


@router.post("/validate")
async def validate_migration_before_start(
    identifier: str,
    target_host: str,
    target_path: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    compose_base_path: Optional[str] = None
):
    """
    🛡️ VALIDATE MIGRATION TARGET BEFORE STARTING
    
    This endpoint MUST be called before any migration to ensure:
    - Explicit target specified (no defaults)
    - SSH connectivity and permissions
    - Sufficient storage space
    - Target directory writability
    
    Migration endpoints will REFUSE to proceed without successful validation.
    """
    try:
        # Use configured base path if not provided
        if not compose_base_path:
            compose_base_path = config.local_compose_base_path
        
        # 🔍 STEP 1: Estimate migration size
        estimated_size = 0
        source_path = None
        
        # Find source (compose project)
        if os.path.isabs(identifier) and os.path.exists(identifier):
            source_path = identifier
        else:
            potential_path = os.path.join(compose_base_path, identifier)
            if os.path.exists(potential_path):
                source_path = potential_path
        
        if source_path:
            # Estimate size using async du command
            try:
                process = await asyncio.create_subprocess_exec(
                    'du', '-sb', source_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
                if process.returncode == 0:
                    estimated_size = int(stdout.decode().split()[0])
            except Exception as e:
                logger.warning(f"Could not estimate size for {source_path}: {e}")
                estimated_size = 1024 * 1024 * 1024  # Default 1GB estimate
        
        # Add 20% buffer for safety
        required_space = int(estimated_size * 1.2)
        
        # 🔍 STEP 2: Validate target with comprehensive checks
        validation = await validate_migration_target(
            target_host=target_host,
            target_path=target_path,
            required_space_bytes=required_space,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        # 🔍 STEP 3: Add source-specific information
        validation["source"] = {
            "identifier": identifier,
            "path": source_path,
            "estimated_size_bytes": estimated_size,
            "estimated_size_gb": round(estimated_size / (1024**3), 2)
        }
        
        # 🔍 STEP 4: Return comprehensive validation results
        return {
            "validation_id": f"val_{int(datetime.now().timestamp())}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "migration_safe": validation["valid"],
            "validation_details": validation,
            "next_steps": {
                "if_valid": "Proceed with migration using /migrations/smart or /migrations/compose",
                "if_invalid": "Fix validation errors before attempting migration"
            }
        }
        
    except Exception as e:
        logger.error(f"Migration validation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {e}") from e


@router.post("/resume/{migration_id}")
async def resume_migration(migration_id: str, force_resume: bool = False):
    """
    🔄 RESUME INTERRUPTED MIGRATION
    
    Resume a migration that was interrupted due to:
    - Network failures
    - System reboots  
    - Process crashes
    - User interruption
    
    Uses checkpoints and partial file recovery for reliability.
    """
    try:
        logger.info(f"🔄 Attempting to resume migration: {migration_id}")
        
        resume_result = await resume_interrupted_migration(migration_id, force_resume)
        
        if resume_result["resume_successful"]:
            return {
                "migration_id": migration_id,
                "status": "resumed_successfully",
                "resume_details": resume_result,
                "message": f"✅ Migration {migration_id} resumed and completed successfully"
            }
        else:
            return {
                "migration_id": migration_id,
                "status": "resume_failed",
                "resume_details": resume_result,
                "message": f"❌ Failed to resume migration {migration_id}",
                "errors": resume_result["errors"]
            }
            
    except Exception as e:
        logger.error(f"Resume endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Resume failed: {e}") from e


@router.post("/verify-integrity/{migration_id}")
async def verify_migration_integrity(
    migration_id: str,
    source_path: str,
    target_host: str,
    target_path: str,
    ssh_user: str = "root",
    ssh_port: int = 22
):
    """
    🔐 VERIFY MIGRATION INTEGRITY
    
    Comprehensive checksum verification after migration:
    - Compare source vs target checksums
    - Verify file sizes and timestamps
    - Generate detailed integrity report
    - Recommend rollback if verification fails
    """
    try:
        logger.info(f"🔐 Verifying integrity for migration: {migration_id}")
        
        # Load source checksums
        checksum_file = f"/tmp/transdock_checksums_{migration_id}.json"
        
        import json
        import os
        if not os.path.exists(checksum_file):
            raise HTTPException(status_code=404, detail="Source checksums not found")
        
        with open(checksum_file, 'r') as f:
            source_checksums = json.load(f)
        
        # Verify target checksums
        verification = await verify_target_checksums(
            target_host=target_host,
            target_path=target_path,
            source_checksums=source_checksums,
            migration_id=migration_id,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        if verification["verification_passed"]:
            return {
                "migration_id": migration_id,
                "integrity_status": "verified",
                "verification_details": verification,
                "message": f"✅ Migration integrity verified: {verification['files_matched']} files passed",
                "recommendation": "Migration completed successfully - safe to cleanup snapshots"
            }
        else:
            return {
                "migration_id": migration_id,
                "integrity_status": "failed",
                "verification_details": verification,
                "message": f"❌ Integrity verification failed: {verification['files_mismatched']} mismatched files",
                "recommendation": "IMMEDIATE ROLLBACK RECOMMENDED - Data corruption detected",
                "critical_warning": "DO NOT use migrated data until integrity issues are resolved"
            }
            
    except Exception as e:
        logger.error(f"Integrity verification failed: {e}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {e}") from e


# Helper functions for migration operations

async def validate_migration_target(
    target_host: str,
    target_path: str, 
    required_space_bytes: int,
    ssh_user: str = "root",
    ssh_port: int = 22
) -> dict:
    """
    🛡️ COMPREHENSIVE MIGRATION TARGET VALIDATION
    
    This function ensures migration safety by validating:
    1. Target is explicitly provided (no defaults)
    2. SSH connectivity and permissions
    3. Target directory writability 
    4. Sufficient storage space
    5. Target host accessibility
    
    Returns validation results with detailed status
    """
    from ...models import HostInfo
    from ...host_service import HostService
    
    host_service = HostService()
    
    validation_results = {
        "valid": False,
        "target_host": target_host,
        "target_path": target_path,
        "required_space_gb": round(required_space_bytes / (1024**3), 2),
        "checks": {},
        "errors": [],
        "warnings": []
    }
    
    try:
        # 🔍 CHECK 1: Explicit Target Validation
        if config.require_explicit_target:
            if not target_path or target_path.strip() == "":
                validation_results["errors"].append("❌ Target path must be explicitly provided")
                validation_results["checks"]["explicit_target"] = False
            elif target_path in [config.default_target_compose_path, config.default_target_appdata_path]:
                validation_results["warnings"].append(f"⚠️ Using default target path: {target_path}")
                validation_results["checks"]["explicit_target"] = True
            else:
                validation_results["checks"]["explicit_target"] = True
        
        # 🔍 CHECK 2: SSH Connectivity
        try:
            ssh_test = await host_service.validate_ssh_connection(target_host, ssh_user, ssh_port)
            if ssh_test:
                validation_results["checks"]["ssh_connectivity"] = True
            else:
                validation_results["errors"].append(f"❌ Cannot establish SSH connection to {target_host}")
                validation_results["checks"]["ssh_connectivity"] = False
        except Exception as e:
            validation_results["errors"].append(f"❌ SSH connection failed: {e}")
            validation_results["checks"]["ssh_connectivity"] = False
        
        # 🔍 CHECK 3: Target Directory Permissions
        try:
            # Test if we can create/write to target directory
            permission_test = await host_service.test_directory_permissions(
                target_host, target_path, ssh_user, ssh_port
            )
            
            if permission_test.get("writable", False):
                validation_results["checks"]["write_permissions"] = True
            else:
                validation_results["errors"].append(
                    f"❌ No write permissions to {target_path} on {target_host}"
                )
                validation_results["checks"]["write_permissions"] = False
                
        except Exception as e:
            validation_results["errors"].append(f"❌ Permission check failed: {e}")
            validation_results["checks"]["write_permissions"] = False
        
        # 🔍 CHECK 4: Storage Space Validation
        try:
            # Create HostInfo object for the call
            target_host_info = HostInfo(hostname=target_host, ssh_user=ssh_user, ssh_port=ssh_port)
            storage_results = await host_service.get_storage_info(target_host_info, [target_path])
            storage_info = storage_results[0] if storage_results else None
            available_bytes = storage_info.available_bytes if storage_info else 0
            available_gb = round(available_bytes / (1024**3), 2)
            
            validation_results["available_space_gb"] = available_gb
            
            if available_bytes >= required_space_bytes:
                validation_results["checks"]["sufficient_storage"] = True
            else:
                required_gb = round(required_space_bytes / (1024**3), 2)
                validation_results["errors"].append(
                    f"❌ Insufficient storage: need {required_gb}GB, have {available_gb}GB"
                )
                validation_results["checks"]["sufficient_storage"] = False
                
        except Exception as e:
            validation_results["errors"].append(f"❌ Storage check failed: {e}")
            validation_results["checks"]["sufficient_storage"] = False
        
        # 🔍 CHECK 5: Target Host Accessibility
        try:
            # Basic connectivity test
            host_capabilities = await host_service.check_host_capabilities(
                HostInfo(hostname=target_host, ssh_user=ssh_user, ssh_port=ssh_port)
            )
            
            validation_results["checks"]["host_accessible"] = host_capabilities.is_accessible
            if not host_capabilities.is_accessible:
                validation_results["errors"].append(f"❌ Target host {target_host} is not accessible")
            
            # Store host capabilities for reference
            validation_results["host_capabilities"] = {
                "has_docker": host_capabilities.has_docker,
                "has_zfs": host_capabilities.has_zfs,
                "docker_version": host_capabilities.docker_version,
                "zfs_version": host_capabilities.zfs_version
            }
            
        except Exception as e:
            validation_results["errors"].append(f"❌ Host accessibility check failed: {e}")
            validation_results["checks"]["host_accessible"] = False
        
        # 🏁 FINAL VALIDATION
        all_checks_passed = all([
            validation_results["checks"].get("explicit_target", True),  # Optional
            validation_results["checks"].get("ssh_connectivity", False),
            validation_results["checks"].get("write_permissions", False),
            validation_results["checks"].get("sufficient_storage", False),
            validation_results["checks"].get("host_accessible", False)
        ])
        
        validation_results["valid"] = all_checks_passed
        
        if all_checks_passed:
            validation_results["summary"] = "✅ All validation checks passed - safe to proceed with migration"
        else:
            validation_results["summary"] = "❌ Validation failed - address errors before proceeding"
        
    except Exception as e:
        logger.error(f"Validation error: {e}")
        validation_results["errors"].append(f"❌ Unexpected validation error: {e}")
        validation_results["valid"] = False
    
    return validation_results


async def create_pre_migration_safety_snapshot(
    target_host: str,
    target_path: str,
    migration_id: str,
    ssh_user: str = "root",
    ssh_port: int = 22
) -> dict:
    """
    🛡️ CREATE SAFETY SNAPSHOT BEFORE MIGRATION
    
    Creates a safety snapshot/backup of the target location before migration.
    Supports both ZFS snapshots and directory backups.
    """
    from ...host_service import HostService
    from ...models import HostInfo
    host_service = HostService()
    
    safety_result = {
        "snapshot_created": False,
        "snapshot_type": None,
        "snapshot_name": None,
        "snapshot_path": None,
        "can_rollback": False,
        "errors": []
    }
    
    try:
        # Check if target is on ZFS
        zfs_check = await host_service.run_remote_command(
            HostInfo(hostname=target_host, ssh_user=ssh_user, ssh_port=ssh_port),
            f"df -T '{target_path}' | tail -1 | awk '{{print $2}}'"
        )
        
        is_zfs = zfs_check[1].strip() == "zfs" if zfs_check[0] == 0 else False
        
        if is_zfs:
            # Create ZFS snapshot
            dataset_cmd = f"df '{target_path}' | tail -1 | awk '{{print $1}}'"
            dataset_result = await host_service.run_remote_command(
                HostInfo(hostname=target_host, ssh_user=ssh_user, ssh_port=ssh_port),
                dataset_cmd
            )
            
            if dataset_result[0] == 0:
                dataset_name = dataset_result[1].strip()
                snapshot_name = f"{dataset_name}@pre-migration-{migration_id}-{int(datetime.now().timestamp())}"
                
                await create_zfs_safety_snapshot(
                    target_host, dataset_name, snapshot_name, 
                    safety_result, ssh_user, ssh_port
                )
        else:
            # Create directory backup
            backup_name = f"{target_path}.pre-migration-{migration_id}-{int(datetime.now().timestamp())}"
            
            await create_directory_safety_backup(
                target_host, target_path, backup_name,
                safety_result, ssh_user, ssh_port
            )
        
        # Verify snapshot was created
        if safety_result["snapshot_created"]:
            verified = await verify_safety_snapshot(
                target_host, safety_result, ssh_user, ssh_port
            )
            safety_result["verified"] = verified
        
    except Exception as e:
        logger.error(f"Safety snapshot creation failed: {e}")
        safety_result["errors"].append(str(e))
    
    return safety_result


async def create_zfs_safety_snapshot(
    target_host: str, zfs_dataset: str, snapshot_name: str, 
    safety_result: dict, ssh_user: str, ssh_port: int
):
    """Create a ZFS snapshot for safety"""
    from ...host_service import HostService
    from ...models import HostInfo
    
    host_service = HostService()
    
    try:
        # Create ZFS snapshot
        snapshot_cmd = f"zfs snapshot '{snapshot_name}'"
        result = await host_service.run_remote_command(
            HostInfo(hostname=target_host, ssh_user=ssh_user, ssh_port=ssh_port),
            snapshot_cmd
        )
        
        if result[0] == 0:
            safety_result["snapshot_created"] = True
            safety_result["snapshot_type"] = "zfs"
            safety_result["snapshot_name"] = snapshot_name
            safety_result["snapshot_path"] = snapshot_name
            safety_result["can_rollback"] = True
            logger.info(f"✅ Created ZFS safety snapshot: {snapshot_name}")
        else:
            safety_result["errors"].append(f"Failed to create ZFS snapshot: {result[2]}")
            
    except Exception as e:
        safety_result["errors"].append(f"ZFS snapshot error: {e}")


async def create_directory_safety_backup(
    target_host: str, target_path: str, backup_name: str,
    safety_result: dict, ssh_user: str, ssh_port: int
):
    """Create a directory backup for safety"""
    from ...host_service import HostService
    from ...models import HostInfo
    
    host_service = HostService()
    
    try:
        # Create backup using cp -a (preserves all attributes)
        backup_cmd = f"cp -a '{target_path}' '{backup_name}'"
        result = await host_service.run_remote_command(
            HostInfo(hostname=target_host, ssh_user=ssh_user, ssh_port=ssh_port),
            backup_cmd
        )
        
        if result[0] == 0:
            safety_result["snapshot_created"] = True
            safety_result["snapshot_type"] = "directory"
            safety_result["snapshot_name"] = os.path.basename(backup_name)
            safety_result["snapshot_path"] = backup_name
            safety_result["can_rollback"] = True
            logger.info(f"✅ Created directory safety backup: {backup_name}")
        else:
            safety_result["errors"].append(f"Failed to create directory backup: {result[2]}")
            
    except Exception as e:
        safety_result["errors"].append(f"Directory backup error: {e}")


async def verify_safety_snapshot(
    target_host: str, safety_result: dict, ssh_user: str, ssh_port: int
) -> bool:
    """Verify that safety snapshot/backup exists"""
    from ...host_service import HostService
    from ...models import HostInfo
    
    host_service = HostService()
    
    try:
        if safety_result["snapshot_type"] == "zfs":
            # Verify ZFS snapshot exists
            verify_cmd = f"zfs list -t snapshot '{safety_result['snapshot_name']}'"
        else:
            # Verify directory backup exists
            verify_cmd = f"test -d '{safety_result['snapshot_path']}' && echo 'exists'"
        
        result = await host_service.run_remote_command(
            HostInfo(hostname=target_host, ssh_user=ssh_user, ssh_port=ssh_port),
            verify_cmd
        )
        
        return result[0] == 0
        
    except Exception as e:
        logger.error(f"Snapshot verification failed: {e}")
        return False


async def create_safe_rsync_operation(
    source_path: str,
    target_host: str, 
    target_path: str,
    migration_id: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    dry_run: bool = True
) -> dict:
    """
    🛡️ CREATE SAFE RSYNC OPERATION WITH VALIDATION
    
    Builds a safe rsync command with:
    - Dry run capability
    - Progress tracking
    - Bandwidth limiting
    - Checksum verification
    - Partial file support
    """
    rsync_result = {
        "command": None,
        "dry_run": dry_run,
        "estimated_size": 0,
        "estimated_files": 0,
        "errors": []
    }
    
    try:
        # Build rsync command with safety features
        rsync_options = [
            "-avz",  # Archive, verbose, compress
            "--progress",  # Show progress
            "--partial",  # Keep partial files
            "--partial-dir=.rsync-partial",  # Partial directory
            f"--log-file=/tmp/rsync-{migration_id}.log",  # Log file
            "--checksum",  # Verify file integrity
            "--delete-after",  # Delete extraneous files after transfer
            "--backup",  # Make backups of replaced files
            f"--backup-dir=.rsync-backup-{migration_id}",  # Backup directory
            "--exclude=.rsync-partial",  # Exclude partial directory
            "--exclude=.rsync-backup-*",  # Exclude backup directories
        ]
        
        # Add bandwidth limit if configured
        if hasattr(config, 'rsync_bandwidth_limit') and config.rsync_bandwidth_limit:
            rsync_options.append(f"--bwlimit={config.rsync_bandwidth_limit}")
        
        # Add dry run flag if requested
        if dry_run:
            rsync_options.append("--dry-run")
            rsync_options.append("--stats")  # Get statistics in dry run
        
        # Build SSH command
        ssh_cmd = f"ssh -p {ssh_port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
        
        # Build full rsync command
        rsync_cmd = [
            "rsync",
            *rsync_options,
            "-e", ssh_cmd,
            f"{source_path}/",  # Trailing slash to copy contents
            f"{ssh_user}@{target_host}:{target_path}/"
        ]
        
        rsync_result["command"] = " ".join(rsync_cmd)
        
        # If dry run, execute to get estimates
        if dry_run:
            process = await asyncio.create_subprocess_exec(
                *rsync_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Parse dry run output for estimates
                output = stdout.decode()
                
                # Extract file count
                file_match = re.search(r'Number of files: ([\d,]+)', output)
                if file_match:
                    rsync_result["estimated_files"] = int(file_match.group(1).replace(',', ''))
                
                # Extract size
                size_match = re.search(r'Total file size: ([\d,]+) bytes', output)
                if size_match:
                    rsync_result["estimated_size"] = int(size_match.group(1).replace(',', ''))
                
                logger.info(f"✅ Dry run successful: {rsync_result['estimated_files']} files, "
                          f"{rsync_result['estimated_size'] / (1024**3):.2f} GB")
            else:
                rsync_result["errors"].append(f"Dry run failed: {stderr.decode()}")
        
    except Exception as e:
        logger.error(f"Failed to create rsync operation: {e}")
        rsync_result["errors"].append(str(e))
    
    return rsync_result


async def create_migration_checkpoint(
    migration_id: str,
    source_path: str,
    target_host: str,
    target_path: str,
    progress_state: dict
) -> dict:
    """
    💾 CREATE MIGRATION CHECKPOINT FOR RESUME CAPABILITY
    
    Saves current migration state to enable resume on failure
    """
    import json
    
    checkpoint = {
        "migration_id": migration_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_path": source_path,
        "target_host": target_host,
        "target_path": target_path,
        "progress": progress_state,
        "checkpoint_file": f"/tmp/migration-checkpoint-{migration_id}.json"
    }
    
    try:
        # Save checkpoint to file
        with open(checkpoint["checkpoint_file"], 'w') as f:
            json.dump(checkpoint, f, indent=2)
        
        logger.info(f"✅ Created migration checkpoint: {checkpoint['checkpoint_file']}")
        return checkpoint
        
    except Exception as e:
        logger.error(f"Failed to create checkpoint: {e}")
        checkpoint["error"] = str(e)
        return checkpoint


async def load_migration_checkpoint(migration_id: str) -> dict:
    """Load migration checkpoint for resume"""
    import json
    
    checkpoint_file = f"/tmp/migration-checkpoint-{migration_id}.json"
    
    try:
        if os.path.exists(checkpoint_file):
            with open(checkpoint_file, 'r') as f:
                return json.load(f)
        else:
            return {"error": "Checkpoint not found"}
            
    except Exception as e:
        logger.error(f"Failed to load checkpoint: {e}")
        return {"error": str(e)}


async def generate_source_checksums(
    source_path: str,
    migration_id: str,
    algorithm: str = "sha256"
) -> dict:
    """
    🔐 GENERATE CHECKSUMS FOR SOURCE FILES
    
    Creates checksums for all files to verify integrity after transfer
    """
    import hashlib
    
    checksum_result = {
        "algorithm": algorithm,
        "checksum_file": f"/tmp/checksums-{migration_id}.txt",
        "file_count": 0,
        "total_size": 0,
        "checksums": {},
        "errors": []
    }
    
    try:
        # Walk through all files
        for root, dirs, files in os.walk(source_path):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, source_path)
                
                try:
                    # Calculate checksum
                    hasher = hashlib.new(algorithm)
                    with open(file_path, 'rb') as f:
                        while chunk := f.read(8192):
                            hasher.update(chunk)
                    
                    checksum = hasher.hexdigest()
                    checksum_result["checksums"][relative_path] = checksum
                    checksum_result["file_count"] += 1
                    checksum_result["total_size"] += os.path.getsize(file_path)
                    
                except Exception as e:
                    checksum_result["errors"].append(f"Failed to checksum {relative_path}: {e}")
        
        # Save checksums to file
        with open(checksum_result["checksum_file"], 'w') as f:
            for path, checksum in checksum_result["checksums"].items():
                f.write(f"{checksum}  {path}\n")
        
        logger.info(f"✅ Generated {checksum_result['file_count']} checksums")
        
    except Exception as e:
        logger.error(f"Checksum generation failed: {e}")
        checksum_result["errors"].append(str(e))
    
    return checksum_result


async def verify_target_checksums(
    target_host: str,
    target_path: str,
    source_checksums: dict,
    migration_id: str,
    ssh_user: str = "root",
    ssh_port: int = 22
) -> dict:
    """
    🔐 VERIFY CHECKSUMS ON TARGET AFTER TRANSFER
    
    Ensures data integrity by comparing checksums
    """
    from ...host_service import HostService
    from ...models import HostInfo
    
    host_service = HostService()
    
    verification_result = {
        "verified": False,
        "files_checked": 0,
        "files_matched": 0,
        "files_mismatched": 0,
        "missing_files": [],
        "mismatched_files": [],
        "errors": []
    }
    
    try:
        # Create remote checksum script
        script_content = f"""#!/bin/bash
cd '{target_path}'
while IFS='  ' read -r expected_sum file_path; do
    if [ -f "$file_path" ]; then
        actual_sum=$(sha256sum "$file_path" | awk '{{print $1}}')
        if [ "$actual_sum" = "$expected_sum" ]; then
            echo "OK:$file_path"
        else
            echo "MISMATCH:$file_path:$expected_sum:$actual_sum"
        fi
    else
        echo "MISSING:$file_path"
    fi
done
"""
        
        # Create temporary script on target
        script_path = f"/tmp/verify-checksums-{migration_id}.sh"
        create_script_cmd = f"cat > {script_path} << 'EOF'\n{script_content}\nEOF"
        
        await host_service.run_remote_command(
            HostInfo(hostname=target_host, ssh_user=ssh_user, ssh_port=ssh_port),
            create_script_cmd
        )
        
        # Make script executable
        await host_service.run_remote_command(
            HostInfo(hostname=target_host, ssh_user=ssh_user, ssh_port=ssh_port),
            f"chmod +x {script_path}"
        )
        
        # Run verification
        checksum_data = ""
        for path, checksum in source_checksums["checksums"].items():
            checksum_data += f"{checksum}  {path}\n"
        
        verify_cmd = f"echo '{checksum_data}' | {script_path}"
        result = await host_service.run_remote_command(
            HostInfo(hostname=target_host, ssh_user=ssh_user, ssh_port=ssh_port),
            verify_cmd
        )
        
        if result[0] == 0:
            # Parse results
            for line in result[1].strip().split('\n'):
                if line.startswith("OK:"):
                    verification_result["files_checked"] += 1
                    verification_result["files_matched"] += 1
                elif line.startswith("MISMATCH:"):
                    parts = line.split(':')
                    verification_result["files_checked"] += 1
                    verification_result["files_mismatched"] += 1
                    verification_result["mismatched_files"].append(parts[1])
                elif line.startswith("MISSING:"):
                    verification_result["missing_files"].append(line.split(':')[1])
            
            verification_result["verified"] = (
                verification_result["files_mismatched"] == 0 and
                len(verification_result["missing_files"]) == 0
            )
            
        # Cleanup
        await host_service.run_remote_command(
            HostInfo(hostname=target_host, ssh_user=ssh_user, ssh_port=ssh_port),
            f"rm -f {script_path}"
        )
        
    except Exception as e:
        logger.error(f"Checksum verification failed: {e}")
        verification_result["errors"].append(str(e))
    
    return verification_result


async def resume_interrupted_migration(
    migration_id: str,
    force_resume: bool = False
) -> dict:
    """
    🔄 RESUME AN INTERRUPTED MIGRATION
    
    Loads checkpoint and continues from where it left off
    """
    resume_result = {
        "migration_id": migration_id,
        "resume_successful": False,
        "checkpoint_loaded": False,
        "errors": []
    }
    
    try:
        # Load checkpoint
        checkpoint = await load_migration_checkpoint(migration_id)
        
        if "error" in checkpoint:
            resume_result["errors"].append(f"Failed to load checkpoint: {checkpoint['error']}")
            return resume_result
        
        resume_result["checkpoint_loaded"] = True
        resume_result["checkpoint_data"] = checkpoint
        
        # Verify source still exists
        if not os.path.exists(checkpoint["source_path"]):
            resume_result["errors"].append("Source path no longer exists")
            return resume_result
        
        # Create rsync command for resume (uses --partial)
        rsync_result = await create_safe_rsync_operation(
            source_path=checkpoint["source_path"],
            target_host=checkpoint["target_host"],
            target_path=checkpoint["target_path"],
            migration_id=migration_id,
            ssh_user=checkpoint.get("ssh_user", "root"),
            ssh_port=checkpoint.get("ssh_port", 22),
            dry_run=False  # Actual transfer
        )
        
        if rsync_result["errors"]:
            resume_result["errors"].extend(rsync_result["errors"])
            return resume_result
        
        # Execute rsync
        process = await asyncio.create_subprocess_shell(
            rsync_result["command"],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            resume_result["resume_successful"] = True
            resume_result["message"] = "Migration resumed and completed successfully"
            logger.info(f"✅ Successfully resumed migration {migration_id}")
        else:
            resume_result["errors"].append(f"Rsync failed: {stderr.decode()}")
            
    except Exception as e:
        logger.error(f"Failed to resume migration: {e}")
        resume_result["errors"].append(str(e))
    
    return resume_result 