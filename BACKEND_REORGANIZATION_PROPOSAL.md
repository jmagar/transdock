# TransDock Backend Reorganization Proposal

## Current State Analysis

### Critical Issues Identified

1. **Massive Single Files** - Several files have grown beyond maintainable sizes:
   - `zfs_ops.py`: 114KB, 2513 lines - Monolithic ZFS operations class
   - `main.py`: 32KB, 844 lines - All API endpoints in one file
   - `host_service.py`: 29KB, 638 lines - All host operations
   - `docker_ops.py`: 26KB, 643 lines - All Docker operations
   - `transfer_ops.py`: 25KB, 613 lines - All transfer operations

2. **Single Responsibility Principle Violations**:
   - `ZFSOperations` class handles: basic operations, snapshots, pools, backups, encryption, quotas, performance monitoring, replication, etc.
   - API routes mixed with business logic in `main.py`
   - Services are too broad in scope

3. **Inconsistent Organization**:
   - Some newer services in `backend/services/` are better organized
   - Some newer API routes in `backend/api/routers/` are properly structured
   - But the main massive files haven't been refactored
   - Duplicate functionality exists in different places

## Proposed New Structure

### 1. Domain-Driven Design Approach

```
backend/
├── core/                           # Core domain logic
│   ├── __init__.py
│   ├── exceptions/                 # Domain exceptions
│   │   ├── __init__.py
│   │   ├── zfs_exceptions.py
│   │   ├── docker_exceptions.py
│   │   ├── transfer_exceptions.py
│   │   └── validation_exceptions.py
│   ├── entities/                   # Domain entities
│   │   ├── __init__.py
│   │   ├── zfs_entity.py
│   │   ├── docker_entity.py
│   │   ├── migration_entity.py
│   │   └── host_entity.py
│   ├── value_objects/              # Immutable value objects
│   │   ├── __init__.py
│   │   ├── dataset_name.py
│   │   ├── snapshot_name.py
│   │   ├── host_connection.py
│   │   └── storage_size.py
│   └── interfaces/                 # Repository/service interfaces
│       ├── __init__.py
│       ├── zfs_repository.py
│       ├── docker_repository.py
│       └── transfer_repository.py
│
├── application/                    # Application services (use cases)
│   ├── __init__.py
│   ├── migration/
│   │   ├── __init__.py
│   │   ├── start_migration_use_case.py
│   │   ├── monitor_migration_use_case.py
│   │   ├── cancel_migration_use_case.py
│   │   └── migration_orchestrator.py
│   ├── zfs/
│   │   ├── __init__.py
│   │   ├── dataset_management_service.py
│   │   ├── snapshot_management_service.py
│   │   ├── pool_management_service.py
│   │   ├── backup_service.py
│   │   └── replication_service.py
│   ├── docker/
│   │   ├── __init__.py
│   │   ├── container_discovery_service.py
│   │   ├── container_management_service.py
│   │   ├── compose_stack_service.py
│   │   └── image_management_service.py
│   └── transfer/
│       ├── __init__.py
│       ├── zfs_transfer_service.py
│       ├── rsync_transfer_service.py
│       └── transfer_orchestrator.py
│
├── infrastructure/                 # Infrastructure layer
│   ├── __init__.py
│   ├── zfs/
│   │   ├── __init__.py
│   │   ├── commands/
│   │   │   ├── __init__.py
│   │   │   ├── dataset_commands.py
│   │   │   ├── snapshot_commands.py
│   │   │   ├── pool_commands.py
│   │   │   ├── backup_commands.py
│   │   │   └── replication_commands.py
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── zfs_dataset_repository.py
│   │   │   ├── zfs_snapshot_repository.py
│   │   │   └── zfs_pool_repository.py
│   │   └── adapters/
│   │       ├── __init__.py
│   │       ├── zfs_command_adapter.py
│   │       └── zfs_api_adapter.py
│   ├── docker/
│   │   ├── __init__.py
│   │   ├── api_client.py
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── container_repository.py
│   │   │   ├── image_repository.py
│   │   │   └── network_repository.py
│   │   └── adapters/
│   │       ├── __init__.py
│   │       ├── docker_api_adapter.py
│   │       └── compose_file_adapter.py
│   ├── ssh/
│   │   ├── __init__.py
│   │   ├── ssh_client.py
│   │   ├── command_executor.py
│   │   └── file_transfer.py
│   └── storage/
│       ├── __init__.py
│       ├── migration_state_store.py
│       └── cache_manager.py
│
├── api/                            # API layer (keep existing structure)
│   ├── __init__.py
│   ├── v1/                         # Version the API
│   │   ├── __init__.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── datasets.py
│   │   │   ├── snapshots.py
│   │   │   ├── pools.py
│   │   │   ├── migrations.py
│   │   │   ├── docker.py
│   │   │   ├── hosts.py
│   │   │   └── system.py
│   │   ├── dependencies.py
│   │   ├── auth.py
│   │   └── websocket.py
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── error_handling.py
│   │   ├── logging.py
│   │   ├── security.py
│   │   └── rate_limiting.py
│   └── models/                     # API models separate from domain
│       ├── __init__.py
│       ├── request_models.py
│       ├── response_models.py
│       └── dto_models.py
│
├── shared/                         # Shared utilities and common code
│   ├── __init__.py
│   ├── security/
│   │   ├── __init__.py
│   │   ├── validation.py
│   │   ├── sanitization.py
│   │   └── encryption.py
│   ├── monitoring/
│   │   ├── __init__.py
│   │   ├── metrics.py
│   │   ├── health_checks.py
│   │   └── logging.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── formatting.py
│   │   ├── file_utils.py
│   │   └── async_utils.py
│   └── constants/
│       ├── __init__.py
│       ├── zfs_constants.py
│       ├── docker_constants.py
│       └── system_constants.py
│
├── config/                         # Configuration management
│   ├── __init__.py
│   ├── settings.py
│   ├── database.py
│   └── logging.py
│
├── tests/                          # Test structure mirrors main structure
│   ├── unit/
│   │   ├── core/
│   │   ├── application/
│   │   ├── infrastructure/
│   │   └── api/
│   ├── integration/
│   │   ├── zfs/
│   │   ├── docker/
│   │   └── migration/
│   └── e2e/
│       ├── migration_flows/
│       └── api_workflows/
│
├── main.py                         # Minimal FastAPI app initialization
├── __init__.py
└── requirements.txt
```

## Detailed Refactoring Plan

### Phase 1: Core Domain Extraction (Week 1-2)

1. **Create Domain Entities**:
   - Extract core business concepts from existing models
   - Create immutable value objects for things like dataset names, snapshot names
   - Define clear entity boundaries

2. **Define Repository Interfaces**:
   - Abstract away infrastructure concerns
   - Create interfaces for ZFS, Docker, and Transfer operations
   - Enable dependency injection and testing

3. **Extract Core Exceptions**:
   - Create domain-specific exceptions
   - Remove infrastructure details from domain exceptions

### Phase 2: Break Down Monolithic Files (Week 3-4)

1. **Decompose `zfs_ops.py`**:
   ```python
   # Current: 2513 lines in one class
   # New: Split into focused classes
   
   # infrastructure/zfs/commands/dataset_commands.py
   class DatasetCommands:
       async def create_dataset(self, name: str) -> Result
       async def delete_dataset(self, name: str) -> Result
       async def list_datasets(self) -> List[Dataset]
       async def get_dataset_properties(self, name: str) -> Dict
   
   # infrastructure/zfs/commands/snapshot_commands.py
   class SnapshotCommands:
       async def create_snapshot(self, dataset: str, name: str) -> Result
       async def delete_snapshot(self, name: str) -> Result
       async def list_snapshots(self, dataset: str) -> List[Snapshot]
       async def rollback_snapshot(self, name: str) -> Result
   
   # infrastructure/zfs/commands/pool_commands.py
   class PoolCommands:
       async def get_pool_status(self, name: str) -> PoolStatus
       async def get_pool_health(self, name: str) -> PoolHealth
       async def scrub_pool(self, name: str) -> Result
   
   # infrastructure/zfs/commands/backup_commands.py
   class BackupCommands:
       async def create_backup_strategy(self, dataset: str) -> BackupStrategy
       async def execute_backup(self, strategy: BackupStrategy) -> Result
       async def verify_backup(self, snapshot: str) -> Result
   
   # infrastructure/zfs/commands/replication_commands.py
   class ReplicationCommands:
       async def send_snapshot(self, snapshot: str, target: str) -> Result
       async def receive_snapshot(self, source: str) -> Result
       async def send_incremental(self, base: str, incremental: str) -> Result
   ```

2. **Refactor `main.py`**:
   ```python
   # New minimal main.py
   from fastapi import FastAPI
   from backend.api.v1.routers import (
       datasets, snapshots, pools, migrations, 
       docker, hosts, system
   )
   from backend.config.settings import get_settings
   from backend.api.middleware.error_handling import ErrorHandlingMiddleware
   
   def create_app() -> FastAPI:
       settings = get_settings()
       
       app = FastAPI(
           title="TransDock API",
           version="2.0.0",
           description="ZFS-based Docker migration platform"
       )
       
       # Add middleware
       app.add_middleware(ErrorHandlingMiddleware)
       
       # Include routers
       app.include_router(datasets.router, prefix="/api/v1")
       app.include_router(snapshots.router, prefix="/api/v1")
       app.include_router(pools.router, prefix="/api/v1")
       app.include_router(migrations.router, prefix="/api/v1")
       app.include_router(docker.router, prefix="/api/v1")
       app.include_router(hosts.router, prefix="/api/v1")
       app.include_router(system.router, prefix="/api/v1")
       
       return app
   
   app = create_app()
   ```

3. **Break Down Other Large Files**:
   - `host_service.py` → Split into host management, remote operations, and storage validation
   - `docker_ops.py` → Split into container operations, image management, and network operations
   - `transfer_ops.py` → Split into ZFS transfers, rsync transfers, and transfer orchestration

### Phase 3: Application Service Layer (Week 5-6)

1. **Create Use Cases**:
   ```python
   # application/migration/start_migration_use_case.py
   class StartMigrationUseCase:
       def __init__(
           self,
           zfs_repo: ZFSRepository,
           docker_repo: DockerRepository,
           transfer_repo: TransferRepository
       ):
           self._zfs_repo = zfs_repo
           self._docker_repo = docker_repo
           self._transfer_repo = transfer_repo
       
       async def execute(self, request: StartMigrationRequest) -> MigrationResult:
           # Orchestrate the migration process
           # Clear separation of concerns
           # Testable business logic
   ```

2. **Service Coordination**:
   ```python
   # application/migration/migration_orchestrator.py
   class MigrationOrchestrator:
       async def orchestrate_migration(self, request: MigrationRequest) -> MigrationResult:
           # 1. Validate prerequisites
           # 2. Create snapshots
           # 3. Transfer data
           # 4. Recreate containers
           # 5. Verify migration
           # 6. Cleanup
   ```

### Phase 4: Infrastructure Layer (Week 7-8)

1. **Command Pattern for ZFS Operations**:
   ```python
   # infrastructure/zfs/commands/base_command.py
   class ZFSCommand(ABC):
       @abstractmethod
       async def execute(self) -> Result
       
       @abstractmethod
       def validate(self) -> bool
   
   # infrastructure/zfs/commands/create_dataset_command.py
   class CreateDatasetCommand(ZFSCommand):
       def __init__(self, name: str, properties: Dict[str, str]):
           self.name = SecurityUtils.validate_dataset_name(name)
           self.properties = properties
       
       async def execute(self) -> Result:
           # Secure command execution
           # Proper error handling
           # Logging and monitoring
   ```

2. **Repository Pattern Implementation**:
   ```python
   # infrastructure/zfs/repositories/zfs_dataset_repository.py
   class ZFSDatasetRepository(DatasetRepository):
       def __init__(self, command_executor: CommandExecutor):
           self._executor = command_executor
       
       async def create(self, dataset: Dataset) -> Result:
           command = CreateDatasetCommand(dataset.name, dataset.properties)
           return await self._executor.execute(command)
       
       async def find_by_name(self, name: str) -> Optional[Dataset]:
           command = GetDatasetCommand(name)
           result = await self._executor.execute(command)
           return Dataset.from_zfs_output(result.output) if result.success else None
   ```

### Phase 5: API Layer Refinement (Week 9-10)

1. **Versioned API Structure**:
   ```python
   # api/v1/routers/datasets.py
   from backend.application.zfs.dataset_management_service import DatasetManagementService
   
   @router.post("/datasets", response_model=DatasetResponse)
   async def create_dataset(
       request: CreateDatasetRequest,
       service: DatasetManagementService = Depends(get_dataset_service)
   ):
       result = await service.create_dataset(request.name, request.properties)
       if result.success:
           return DatasetResponse.from_domain(result.data)
       raise HTTPException(status_code=400, detail=result.error)
   ```

2. **Dependency Injection**:
   ```python
   # api/dependencies.py
   def get_dataset_service() -> DatasetManagementService:
       return DatasetManagementService(
           dataset_repo=get_dataset_repository(),
           command_executor=get_command_executor()
       )
   ```

## Benefits of This Reorganization

### 1. **Maintainability**
- **Single Responsibility**: Each class/module has one clear purpose
- **Testability**: Small, focused units that can be easily tested
- **Readability**: Clear structure makes it easy to find and understand code

### 2. **Scalability**
- **Modular Design**: Easy to add new features without affecting existing code
- **Domain-Driven**: Business logic is separated from infrastructure concerns
- **Loose Coupling**: Components can be modified independently

### 3. **Testing**
- **Unit Tests**: Each component can be tested in isolation
- **Integration Tests**: Clear boundaries make integration testing easier
- **Mocking**: Repository pattern enables easy mocking of dependencies

### 4. **Performance**
- **Lazy Loading**: Services can be loaded on-demand
- **Caching**: Repository pattern enables sophisticated caching strategies
- **Resource Management**: Better control over resource lifecycle

### 5. **Security**
- **Input Validation**: Centralized validation in value objects
- **Command Sanitization**: Security validation in command pattern
- **Access Control**: Clear boundaries enable better access control

## Migration Strategy

### 1. **Parallel Development**
- Keep existing code working while building new structure
- Gradually migrate endpoints to new structure
- Feature flags to control rollout

### 2. **Testing Strategy**
- Comprehensive test coverage for new code
- Integration tests to ensure compatibility
- Performance benchmarks to ensure no regression

### 3. **Documentation**
- API documentation updates
- Architecture decision records
- Migration guides for team members

### 4. **Monitoring**
- Metrics for new components
- Error tracking and alerting
- Performance monitoring

## Implementation Timeline

| Phase | Duration | Focus | Deliverables |
|-------|----------|--------|-------------|
| 1 | 2 weeks | Core Domain | Entities, Value Objects, Interfaces |
| 2 | 2 weeks | Monolith Breakdown | Split large files, Command pattern |
| 3 | 2 weeks | Application Layer | Use cases, Service coordination |
| 4 | 2 weeks | Infrastructure | Repositories, Adapters |
| 5 | 2 weeks | API Refinement | Versioned APIs, Dependency injection |
| 6 | 1 week | Testing & Documentation | Comprehensive tests, Documentation |
| 7 | 1 week | Performance & Security | Optimization, Security review |

**Total: 12 weeks for complete reorganization**

## Risk Mitigation

1. **Backward Compatibility**: Maintain existing API contracts during transition
2. **Incremental Migration**: Move one feature at a time
3. **Comprehensive Testing**: Ensure no functionality is lost
4. **Performance Monitoring**: Watch for any performance degradation
5. **Team Training**: Ensure team understands new architecture

This reorganization will transform your backend from a monolithic structure into a clean, maintainable, and scalable architecture that follows modern software engineering principles.