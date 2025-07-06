#!/usr/bin/env python3
"""
Demonstration script showing the new clean architecture in action.

This script demonstrates how to use the new domain-driven design approach
while leveraging the existing ZFS operations.
"""

import asyncio
import logging
from typing import List

# New clean architecture imports
from backend.core.value_objects.dataset_name import DatasetName
from backend.core.value_objects.storage_size import StorageSize
from backend.core.entities.zfs_entity import ZFSDataset, ZFSDatasetType
from backend.application.zfs.dataset_management_service import DatasetManagementService
from backend.infrastructure.zfs.repositories.zfs_dataset_repository_impl import ZFSDatasetRepositoryImpl
from backend.core.exceptions.zfs_exceptions import ZFSOperationError

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def demonstrate_value_objects():
    """Demonstrate the new value objects"""
    print("\n=== Value Objects Demonstration ===")
    
    # DatasetName validation
    try:
        valid_name = DatasetName("tank/test-dataset")
        print(f"✅ Valid dataset name: {valid_name}")
        print(f"   Pool: {valid_name.pool_name()}")
        print(f"   Path: {valid_name.to_path()}")
        print(f"   Depth: {valid_name.depth()}")
        
        # Try invalid name
        try:
            invalid_name = DatasetName("invalid@name")
        except Exception as e:
            print(f"✅ Correctly rejected invalid name: {e}")
    except Exception as e:
        print(f"❌ Dataset name validation failed: {e}")
    
    # StorageSize parsing
    try:
        size1 = StorageSize.from_zfs_string("1.5G")
        size2 = StorageSize.from_gb(2.0)
        total = size1 + size2
        print(f"✅ Storage calculations: {size1} + {size2} = {total}")
    except Exception as e:
        print(f"❌ Storage size operations failed: {e}")


async def demonstrate_clean_architecture():
    """Demonstrate the clean architecture pattern"""
    print("\n=== Clean Architecture Demonstration ===")
    
    try:
        # Initialize the service with dependency injection
        repository = ZFSDatasetRepositoryImpl()
        service = DatasetManagementService(repository)
        
        print("✅ Service initialized with dependency injection")
        
        # List existing datasets using new architecture
        datasets = await service.list_datasets()
        print(f"✅ Found {len(datasets)} datasets using new architecture:")
        
        for dataset in datasets[:3]:  # Show first 3
            print(f"   - {dataset.name} ({dataset.dataset_type.value})")
            print(f"     Pool: {dataset.pool_name()}")
            print(f"     Mounted: {dataset.is_mounted()}")
            print(f"     Compressed: {dataset.is_compressed()}")
            if dataset.used_space:
                print(f"     Used: {dataset.used_space}")
    
    except Exception as e:
        print(f"❌ Clean architecture demo failed: {e}")
        logger.exception("Detailed error:")


async def demonstrate_business_logic():
    """Demonstrate domain business logic"""
    print("\n=== Business Logic Demonstration ===")
    
    try:
        repository = ZFSDatasetRepositoryImpl()
        service = DatasetManagementService(repository)
        
        # Get a dataset and check its health
        datasets = await service.list_datasets()
        if datasets:
            dataset_name = str(datasets[0].name)
            health = await service.check_dataset_health(dataset_name)
            
            print(f"✅ Health check for {dataset_name}:")
            print(f"   Exists: {health.get('exists')}")
            print(f"   Mounted: {health.get('mounted')}")
            print(f"   Pool: {health.get('pool')}")
            print(f"   Used Space: {health.get('used_space', 'Unknown')}")
            
            # Demonstrate optimization
            print(f"\n✅ Optimizing {dataset_name} for Docker migration...")
            success = await service.optimize_dataset_for_migration(dataset_name, "docker")
            if success:
                print("   Optimization completed successfully")
            else:
                print("   Optimization skipped (no changes needed)")
    
    except Exception as e:
        print(f"❌ Business logic demo failed: {e}")
        logger.exception("Detailed error:")


async def compare_old_vs_new():
    """Compare old monolithic approach vs new clean architecture"""
    print("\n=== Old vs New Architecture Comparison ===")
    
    try:
        # Old way - direct ZFS operations
        from backend.zfs_ops import ZFSOperations
        old_zfs = ZFSOperations()
        old_datasets = await old_zfs.list_datasets()
        print(f"🔹 Old approach found {len(old_datasets)} datasets")
        
        # New way - clean architecture
        repository = ZFSDatasetRepositoryImpl()
        service = DatasetManagementService(repository)
        new_datasets = await service.list_datasets()
        print(f"🔹 New approach found {len(new_datasets)} datasets")
        
        # Compare results
        old_names = set(old_datasets)
        new_names = set(str(dataset.name) for dataset in new_datasets)
        
        if old_names == new_names:
            print("✅ Both approaches return identical results!")
        else:
            print("⚠️  Different results between approaches:")
            print(f"   Old only: {old_names - new_names}")
            print(f"   New only: {new_names - old_names}")
        
        # Show advantages of new approach
        if new_datasets:
            dataset = new_datasets[0]
            print(f"\n🚀 New approach provides rich domain objects:")
            print(f"   - Type-safe dataset name: {type(dataset.name).__name__}")
            print(f"   - Business methods: is_mounted()={dataset.is_mounted()}")
            print(f"   - Parsed storage sizes: {dataset.used_space}")
            print(f"   - Domain validation built-in")
    
    except Exception as e:
        print(f"❌ Comparison failed: {e}")
        logger.exception("Detailed error:")


async def main():
    """Main demonstration function"""
    print("🚀 TransDock Backend Reorganization Demonstration")
    print("=" * 60)
    
    try:
        await demonstrate_value_objects()
        await demonstrate_clean_architecture()
        await demonstrate_business_logic()
        await compare_old_vs_new()
        
        print("\n" + "=" * 60)
        print("✅ Demonstration completed successfully!")
        print("\nKey Benefits Demonstrated:")
        print("  • Type-safe value objects with validation")
        print("  • Clean separation of concerns")
        print("  • Dependency injection for testability")
        print("  • Rich domain models with business logic")
        print("  • Backward compatibility with existing code")
        print("  • Better error handling and logging")
        
    except Exception as e:
        print(f"\n❌ Demonstration failed: {e}")
        logger.exception("Detailed error:")


if __name__ == "__main__":
    asyncio.run(main())