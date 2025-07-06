"""ZFS infrastructure layer"""

from .repositories.zfs_dataset_repository_impl import ZFSDatasetRepositoryImpl

__all__ = [
    'ZFSDatasetRepositoryImpl'
]