"""Infrastructure layer - External adapters and repositories"""

from .zfs.repositories.zfs_dataset_repository_impl import ZFSDatasetRepositoryImpl

__all__ = [
    'ZFSDatasetRepositoryImpl'
]