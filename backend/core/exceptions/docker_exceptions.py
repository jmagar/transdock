"""Docker domain exceptions"""

from typing import Optional


class DockerOperationError(Exception):
    """Raised when a Docker operation fails"""
    
    def __init__(self, message: str, container_id: Optional[str] = None, image: Optional[str] = None):
        self.container_id = container_id
        self.image = image
        super().__init__(message)


class DockerNotFoundError(DockerOperationError):
    """Raised when a Docker resource is not found"""
    pass


class DockerContainerNotFoundError(DockerNotFoundError):
    """Raised when a Docker container is not found"""
    pass


class DockerImageNotFoundError(DockerNotFoundError):
    """Raised when a Docker image is not found"""
    pass


class DockerNetworkNotFoundError(DockerNotFoundError):
    """Raised when a Docker network is not found"""
    pass


class DockerConnectionError(DockerOperationError):
    """Raised when unable to connect to Docker daemon"""
    pass