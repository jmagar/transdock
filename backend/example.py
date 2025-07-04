#!/usr/bin/env python3
"""
TransDock API Example Script

This script demonstrates how to use the TransDock API to migrate Docker Compose stacks.
"""

import requests
import time
from typing import Dict, Any


class TransDockClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[Any, Any]:
        """Make a request to the TransDock API"""
        url = f"{self.base_url}{endpoint}"
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def get_system_info(self) -> Dict[Any, Any]:
        """Get system information"""
        return self._request("GET", "/system/info")

    def get_zfs_status(self) -> Dict[Any, Any]:
        """Get ZFS status"""
        return self._request("GET", "/zfs/status")

    def list_compose_stacks(self) -> Dict[Any, Any]:
        """List available compose stacks"""
        return self._request("GET", "/compose/stacks")

    def analyze_stack(self, stack_name: str) -> Dict[Any, Any]:
        """Analyze a compose stack"""
        return self._request("POST", f"/compose/{stack_name}/analyze")

    def start_migration(self,
                        compose_dataset: str,
                        target_host: str,
                        target_base_path: str,
                        ssh_user: str = "root",
                        ssh_port: int = 22,
                        force_rsync: bool = False) -> Dict[Any,
                                                           Any]:
        """Start a migration"""
        data = {
            "compose_dataset": compose_dataset,
            "target_host": target_host,
            "target_base_path": target_base_path,
            "ssh_user": ssh_user,
            "ssh_port": ssh_port,
            "force_rsync": force_rsync
        }
        return self._request("POST", "/migrations", json=data)

    def get_migration_status(self, migration_id: str) -> Dict[Any, Any]:
        """Get migration status"""
        return self._request("GET", f"/migrations/{migration_id}")

    def list_migrations(self) -> Dict[Any, Any]:
        """List all migrations"""
        return self._request("GET", "/migrations")

    def wait_for_migration(self, migration_id: str,
                           timeout: int = 3600) -> Dict[Any, Any]:
        """Wait for a migration to complete"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            status = self.get_migration_status(migration_id)

            print(
                f"Migration {migration_id}: {status['status']} - {status['message']} ({status['progress']}%)")

            if status['status'] in ['completed', 'failed']:
                return status

            time.sleep(5)

        raise TimeoutError(
            f"Migration {migration_id} did not complete within {timeout} seconds")


def main():
    """Example usage of TransDock API"""
    client = TransDockClient()

    print("=== TransDock Migration Example ===\n")

    # Check system info
    print("1. Checking system information...")
    try:
        system_info = client.get_system_info()
        print(f"   Hostname: {system_info['hostname']}")
        print(f"   Docker: {system_info['docker_version']}")
        print(f"   ZFS Available: {system_info['zfs_available']}")
    except Exception as e:
        print(f"   Error: {e}")
        return

    # Check ZFS status
    print("\n2. Checking ZFS status...")
    try:
        zfs_status = client.get_zfs_status()
        print(f"   ZFS Available: {zfs_status['available']}")
    except Exception as e:
        print(f"   Error: {e}")

    # List compose stacks
    print("\n3. Listing available compose stacks...")
    try:
        stacks = client.list_compose_stacks()
        print(f"   Found {len(stacks['stacks'])} stacks:")
        for stack in stacks['stacks'][:5]:  # Show first 5
            print(f"     - {stack['name']} ({stack['compose_file']})")
    except Exception as e:
        print(f"   Error: {e}")
        return

    # Example migration (uncomment and modify as needed)
    """
    # Analyze a specific stack
    print("\n4. Analyzing 'authelia' stack...")
    try:
        analysis = client.analyze_stack("authelia")
        print(f"   Services: {', '.join(analysis['services'])}")
        print(f"   Volumes: {len(analysis['volumes'])}")
        for volume in analysis['volumes']:
            print(f"     - {volume['source']} -> {volume['target']} (Dataset: {volume['is_dataset']})")
    except Exception as e:
        print(f"   Error: {e}")

    # Start migration
    print("\n5. Starting migration...")
    try:
        migration = client.start_migration(
            compose_dataset="authelia",
            target_host="192.168.1.100",
            target_base_path="/home/jmagar",
            ssh_user="root"
        )

        migration_id = migration['migration_id']
        print(f"   Migration started: {migration_id}")

        # Wait for completion
        print("\n6. Waiting for migration to complete...")
        final_status = client.wait_for_migration(migration_id)

        if final_status['status'] == 'completed':
            print("   ✅ Migration completed successfully!")
        else:
            print(f"   ❌ Migration failed: {final_status.get('error', 'Unknown error')}")

    except Exception as e:
        print(f"   Error: {e}")
    """

    print("\n=== Example Complete ===")
    print("\nTo start a real migration, uncomment the migration section above")
    print("and modify the parameters for your environment.")


if __name__ == "__main__":
    main()
