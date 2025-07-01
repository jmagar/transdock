# TransDock Bug Report

## Critical Security Vulnerabilities

### 1. Command Injection Vulnerabilities (HIGH SEVERITY)

**Location**: Multiple files
**Risk**: Remote Code Execution

The codebase contains several instances where user-controlled input is directly interpolated into shell commands without proper sanitization:

#### SSH Command Injection
```python
# backend/migration_service.py:232
cmd = ["ssh", "-p", str(request.ssh_port), f"{request.ssh_user}@{request.target_host}", update_cmd]

# backend/zfs_ops.py:124  
f"zfs send {snapshot_name} | ssh -p {ssh_port} {ssh_user}@{target_host} 'zfs receive {target_dataset}'"
```

**Impact**: An attacker can inject arbitrary commands by manipulating `ssh_user`, `target_host`, or other parameters.

**Fix**: Use proper shell escaping or parameterized commands. Consider using `shlex.quote()` for shell escaping.

#### ZFS Command Injection
```python
# backend/transfer_ops.py:55
f"zfs create -p {parent_dataset} 2>/dev/null || true"

# backend/zfs_ops.py:152
returncode, _, stderr = await self.run_command(["zfs", "set", f"mountpoint={mount_point}", clone_name])
```

**Impact**: Malicious dataset names or mount points can execute arbitrary commands.

### 2. Path Traversal Vulnerabilities (MEDIUM SEVERITY)

**Location**: `backend/docker_ops.py`, `backend/migration_service.py`
**Risk**: Directory traversal attacks

```python
# backend/migration_service.py:158
compose_target_path = f"{request.target_base_path}/compose/{os.path.basename(compose_dir)}"
```

**Impact**: Attackers could potentially access files outside intended directories using `../` sequences.

**Fix**: Validate and sanitize all path inputs, use `os.path.normpath()` and check for directory traversal attempts.

## Logic and Runtime Bugs

### 3. Race Condition in Background Tasks (MEDIUM SEVERITY)

**Location**: `backend/migration_service.py:42`
```python
asyncio.create_task(self._execute_migration(migration_id, request))
```

**Issue**: Background tasks are created but not tracked. If they raise exceptions, they're silently ignored.

**Fix**: Store task references and add proper exception handling:
```python
task = asyncio.create_task(self._execute_migration(migration_id, request))
self.active_tasks[migration_id] = task
task.add_done_callback(lambda t: self._handle_task_completion(migration_id, t))
```

### 4. Bare Exception Handling (LOW-MEDIUM SEVERITY)

**Location**: `backend/migration_service.py:263`
```python
except:
    pass
```

**Issue**: Bare except clauses hide all exceptions, making debugging impossible.

**Fix**: Use specific exception types or at minimum log the exception.

### 5. Synchronous Operations in Async Context (MEDIUM SEVERITY)

**Location**: `backend/main.py:203, 210`
```python
result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
```

**Issue**: Blocking subprocess calls in async functions can cause performance issues.

**Fix**: Use `asyncio.create_subprocess_exec()` instead.

### 6. Missing Input Validation (MEDIUM SEVERITY)

**Location**: Throughout the API endpoints
**Issue**: No validation of SSH ports, hostnames, or paths before using them in commands.

**Examples**:
- SSH port could be negative or > 65535
- Hostnames could contain malicious characters
- Paths could contain null bytes or other dangerous characters

### 7. Resource Cleanup Issues (MEDIUM SEVERITY)

**Location**: `backend/transfer_ops.py:134`
```python
clone_name = f"{snapshot_name.split('@')[0]}_rsync_clone"
```

**Issue**: Clone cleanup only destroys clones with specific naming pattern. If creation fails partway, resources may leak.

**Fix**: Implement comprehensive cleanup tracking and error recovery.

### 8. Hardcoded Paths (LOW SEVERITY)

**Location**: `backend/docker_ops.py:16-17`
```python
self.compose_base_path = "/mnt/cache/compose"
self.appdata_base_path = "/mnt/cache/appdata"
```

**Issue**: Hardcoded Unraid-specific paths make the tool less portable.

**Fix**: Make these configurable via environment variables or config files.

### 9. Missing Error Propagation (LOW SEVERITY)

**Location**: `backend/migration_service.py:236, 246`
```python
logger.warning(f"Failed to update compose file paths: {stderr}")
# ... continues execution despite failure
```

**Issue**: Critical failures are logged as warnings but don't stop the migration process.

### 10. Import Path Issues (HIGH SEVERITY)

**Location**: `backend/main.py:6`
```python
from models import MigrationRequest, MigrationResponse, MigrationStatus
```

**Issue**: Relative imports without package structure can fail when the module is run from different contexts.

**Fix**: Use absolute imports or proper package structure.

## Dependency and Configuration Issues

### 11. Duplicate Requirements Files

**Found**: Both `pyproject.toml` and `backend/requirements.txt`
**Issue**: Can lead to dependency conflicts and confusion.
**Fix**: Use only one dependency management approach.

### 12. Missing Error Handling for External Dependencies

**Issue**: No checks for required external tools (docker, docker-compose, zfs, ssh, rsync).
**Impact**: Runtime failures with unclear error messages.

## Recommendations

1. **Immediate**: Fix command injection vulnerabilities using proper shell escaping
2. **High Priority**: Add comprehensive input validation for all user inputs
3. **Medium Priority**: Implement proper async patterns and exception handling
4. **Low Priority**: Make configuration more flexible and improve error messages

## Testing Recommendations

1. Add security tests for command injection scenarios
2. Test with malicious inputs (path traversal, command injection)
3. Add integration tests for SSH connectivity and ZFS operations
4. Test error handling and recovery scenarios