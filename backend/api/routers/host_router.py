from fastapi import APIRouter, HTTPException

from ...models import HostInfo, HostValidationRequest, HostCapabilities, StackAnalysis
from ...host_service import HostService
from ...security_utils import SecurityUtils, SecurityValidationError
from ...config import get_config

router = APIRouter(
    prefix="/api/hosts",
    tags=["Hosts"],
)

config = get_config()
host_service = HostService()


@router.post("/validate", response_model=HostCapabilities)
async def validate_host(request: HostValidationRequest):
    """Validate and check capabilities of a remote host"""
    try:
        host_info = HostInfo(
            hostname=request.hostname,
            ssh_user=request.ssh_user,
            ssh_port=request.ssh_port
        )
        
        capabilities = await host_service.check_host_capabilities(host_info)
        return capabilities
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{hostname}/capabilities")
async def get_host_capabilities(hostname: str, ssh_user: str = "root", ssh_port: int = 22):
    """Get capabilities of a specific host"""
    try:
        host_info = HostInfo(
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        capabilities = await host_service.check_host_capabilities(host_info)
        return capabilities
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{hostname}/compose/stacks")
async def list_remote_stacks(hostname: str, compose_path: str, ssh_user: str = "root", ssh_port: int = 22):
    """List compose stacks on a remote host"""
    try:
        host_info = HostInfo(
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        stacks = await host_service.list_remote_stacks(host_info, compose_path)
        return {"stacks": stacks}
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{hostname}/compose/stacks/{stack_name}", response_model=StackAnalysis)
async def analyze_remote_stack(hostname: str, stack_name: str, compose_path: str, ssh_user: str = "root", ssh_port: int = 22):
    """Analyze a specific stack on a remote host"""
    try:
        host_info = HostInfo(
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        # Construct stack path
        stack_path = f"{compose_path.rstrip('/')}/{stack_name}"
        
        analysis = await host_service.analyze_remote_stack(host_info, stack_path)
        return analysis
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{hostname}/compose/stacks/{stack_name}/start")
async def start_remote_stack(hostname: str, stack_name: str, compose_path: str, ssh_user: str = "root", ssh_port: int = 22):
    """Start a stack on a remote host"""
    try:
        host_info = HostInfo(
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        # Construct stack path
        stack_path = f"{compose_path.rstrip('/')}/{stack_name}"
        
        success = await host_service.start_remote_stack(host_info, stack_path)
        if success:
            return {"success": True, "message": f"Stack {stack_name} started successfully"}
        raise HTTPException(status_code=400, detail=f"Failed to start stack {stack_name}")
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{hostname}/compose/stacks/{stack_name}/stop")
async def stop_remote_stack(hostname: str, stack_name: str, compose_path: str, ssh_user: str = "root", ssh_port: int = 22):
    """Stop a stack on a remote host"""
    try:
        host_info = HostInfo(
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        # Construct stack path
        stack_path = f"{compose_path.rstrip('/')}/{stack_name}"
        
        success = await host_service.stop_remote_stack(host_info, stack_path)
        if success:
            return {"success": True, "message": f"Stack {stack_name} stopped successfully"}
        raise HTTPException(status_code=400, detail=f"Failed to stop stack {stack_name}")
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{hostname}/datasets")
async def list_remote_datasets(hostname: str, ssh_user: str = "root", ssh_port: int = 22):
    """List ZFS datasets on a remote host"""
    try:
        host_info = HostInfo(
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_port=ssh_port
        )
        
        # List datasets on remote host
        zfs_cmd_args = SecurityUtils.validate_zfs_command_args("list", "-H", "-o", "name,mountpoint", "-t", "filesystem")
        zfs_cmd = " ".join(zfs_cmd_args)
        returncode, stdout, stderr = await host_service.run_remote_command(host_info, zfs_cmd)
        
        if returncode != 0:
            if "command not found" in stderr or "No such file" in stderr:
                return {"datasets": [], "error": "ZFS not available on remote host"}
            raise HTTPException(status_code=500, detail=f"Failed to list datasets: {stderr}")
        
        datasets = []
        for line in stdout.strip().split('\n'):
            if line.strip():
                parts = line.split('\t')
                if len(parts) >= 2:
                    datasets.append({
                        "name": parts[0],
                        "mountpoint": parts[1]
                    })
        
        return {"datasets": datasets}
    except SecurityValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{hostname}/storage")
async def get_host_storage_info(hostname: str, ssh_user: str = "root", ssh_port: int = 22):
    """Get storage information for a remote host"""
    try:
        # Security validation
        SecurityUtils.validate_hostname(hostname)
        SecurityUtils.validate_username(ssh_user)
        SecurityUtils.validate_port(ssh_port)
        
        host_info = HostInfo(hostname=hostname, ssh_user=ssh_user, ssh_port=ssh_port)
        
        # Get storage info for common paths
        common_paths = ["/mnt/cache", "/mnt/user", "/opt", "/home", "/var/lib/docker"]
        storage_info = await host_service.get_storage_info(host_info, common_paths)
        
        return {"storage": storage_info}
        
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{hostname}/storage/validate")
async def validate_host_storage(hostname: str, target_path: str, required_bytes: int, ssh_user: str = "root", ssh_port: int = 22):
    """Validate storage capacity on a remote host"""
    try:
        # Security validation
        SecurityUtils.validate_hostname(hostname)
        SecurityUtils.validate_username(ssh_user)
        SecurityUtils.validate_port(ssh_port)
        
        if required_bytes < 0:
            raise HTTPException(status_code=400, detail="Required bytes must be non-negative")
        
        host_info = HostInfo(hostname=hostname, ssh_user=ssh_user, ssh_port=ssh_port)
        
        # Validate storage availability
        validation_result = await host_service.check_storage_availability(host_info, target_path, required_bytes)
        
        if not validation_result.is_valid:
            # Return detailed error information but still as successful HTTP response
            # The client can check the is_valid field
            return {
                "validation": validation_result,
                "recommendation": "Free up disk space or choose a different target path with more available space"
            }
        
        return {"validation": validation_result}
        
    except SecurityValidationError as e:
        raise HTTPException(status_code=422, detail=f"Security validation failed: {str(e)}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e 