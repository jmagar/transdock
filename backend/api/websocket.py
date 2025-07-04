"""
WebSocket system for TransDock real-time monitoring

This module provides WebSocket functionality including:
- Real-time system monitoring
- Migration progress updates
- ZFS operation notifications
- User session management
- Event broadcasting
"""

import json
import asyncio
import uuid
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from enum import Enum
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field
from collections import defaultdict
import logging

from .auth import User, JWTManager, UserManager

logger = logging.getLogger(__name__)

class EventType(str, Enum):
    """WebSocket event types"""
    # System events
    SYSTEM_STATUS = "system_status"
    SYSTEM_ALERT = "system_alert"
    
    # Migration events
    MIGRATION_STARTED = "migration_started"
    MIGRATION_PROGRESS = "migration_progress"
    MIGRATION_COMPLETED = "migration_completed"
    MIGRATION_FAILED = "migration_failed"
    
    # ZFS events
    ZFS_DATASET_CREATED = "zfs_dataset_created"
    ZFS_DATASET_DELETED = "zfs_dataset_deleted"
    ZFS_SNAPSHOT_CREATED = "zfs_snapshot_created"
    ZFS_SNAPSHOT_DELETED = "zfs_snapshot_deleted"
    ZFS_POOL_STATUS = "zfs_pool_status"
    
    # User events
    USER_CONNECTED = "user_connected"
    USER_DISCONNECTED = "user_disconnected"
    
    # Error events
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class WebSocketMessage(BaseModel):
    """WebSocket message model"""
    event_type: EventType
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex}")
    user_id: Optional[str] = None

class ConnectionManager:
    """WebSocket connection manager"""
    
    def __init__(self):
        """Initialize connection manager"""
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_connections: Dict[str, Set[str]] = defaultdict(set)
        self.connection_users: Dict[str, str] = {}
        self.subscriptions: Dict[str, Set[EventType]] = defaultdict(set)
        self.connection_counter = 0
        self._counter_lock = asyncio.Lock()
    
    async def _generate_connection_id(self) -> str:
        """Generate unique connection ID with thread safety"""
        async with self._counter_lock:
            self.connection_counter += 1
            return f"conn_{self.connection_counter}"
    
    async def connect(self, websocket: WebSocket, user: Optional[User] = None) -> str:
        """
        Accept new WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            user: Authenticated user (optional)
        
        Returns:
            str: Connection ID
        """
        await websocket.accept()
        
        connection_id = await self._generate_connection_id()
        self.active_connections[connection_id] = websocket
        
        if user:
            self.user_connections[user.username].add(connection_id)
            self.connection_users[connection_id] = user.username
            
            # Send welcome message
            await self.send_personal_message(
                connection_id,
                WebSocketMessage(
                    event_type=EventType.USER_CONNECTED,
                    data={
                        "user": user.username,
                        "connection_id": connection_id,
                        "timestamp": datetime.utcnow().isoformat()
                    },
                    user_id=user.username
                )
            )
            
            logger.info(f"User {user.username} connected via WebSocket (ID: {connection_id})")
        else:
            logger.info(f"Anonymous user connected via WebSocket (ID: {connection_id})")
        
        return connection_id
    
    async def disconnect(self, connection_id: str):
        """
        Disconnect WebSocket connection.
        
        Args:
            connection_id: Connection ID to disconnect
        """
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        
        # Clean up user associations
        if connection_id in self.connection_users:
            username = self.connection_users[connection_id]
            self.user_connections[username].discard(connection_id)
            
            if not self.user_connections[username]:
                del self.user_connections[username]
            
            del self.connection_users[connection_id]
            
            logger.info(f"User {username} disconnected from WebSocket (ID: {connection_id})")
        
        # Clean up subscriptions
        if connection_id in self.subscriptions:
            del self.subscriptions[connection_id]
    
    async def send_personal_message(self, connection_id: str, message: WebSocketMessage):
        """
        Send message to specific connection.
        
        Args:
            connection_id: Target connection ID
            message: Message to send
        """
        if connection_id in self.active_connections:
            try:
                websocket = self.active_connections[connection_id]
                await websocket.send_text(message.json())
            except Exception as e:
                logger.error(f"Failed to send message to connection {connection_id}: {e}")
                await self.disconnect(connection_id)
    
    async def send_user_message(self, username: str, message: WebSocketMessage):
        """
        Send message to all connections for a user.
        
        Args:
            username: Target username
            message: Message to send
        """
        if username in self.user_connections:
            message.user_id = username
            for connection_id in self.user_connections[username].copy():
                await self.send_personal_message(connection_id, message)
    
    async def broadcast(self, message: WebSocketMessage):
        """
        Broadcast message to all connections.
        """
        disconnected_connections = []
        
        for connection_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(message.json())
            except Exception as e:
                logger.error(f"Failed to broadcast to connection {connection_id}: {e}")
                disconnected_connections.append(connection_id)
        
        for connection_id in disconnected_connections:
            await self.disconnect(connection_id)
    
    async def subscribe(self, connection_id: str, event_types: List[EventType]):
        """
        Subscribe connection to specific event types.
        
        Args:
            connection_id: Connection ID
            event_types: List of event types to subscribe to
        """
        if connection_id in self.active_connections:
            self.subscriptions[connection_id].update(event_types)
            logger.info(f"Connection {connection_id} subscribed to events: {event_types}")
    
    async def unsubscribe(self, connection_id: str, event_types: List[EventType]):
        """
        Unsubscribe connection from specific event types.
        
        Args:
            connection_id: Connection ID
            event_types: List of event types to unsubscribe from
        """
        if connection_id in self.subscriptions:
            for event_type in event_types:
                self.subscriptions[connection_id].discard(event_type)
            logger.info(f"Connection {connection_id} unsubscribed from events: {event_types}")
    
    def get_connection_count(self) -> int:
        """Get total number of active connections"""
        return len(self.active_connections)
    
    def get_user_count(self) -> int:
        """Get number of connected users"""
        return len(self.user_connections)
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection statistics"""
        return {
            "total_connections": self.get_connection_count(),
            "authenticated_users": self.get_user_count(),
            "anonymous_connections": self.get_connection_count() - sum(len(conns) for conns in self.user_connections.values()),
            "active_users": list(self.user_connections.keys())
        }

class EventBroadcaster:
    """Event broadcasting system"""
    
    def __init__(self, connection_manager: ConnectionManager):
        """Initialize event broadcaster"""
        self.connection_manager = connection_manager
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.running = False
        self.worker_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start event broadcaster"""
        if not self.running:
            self.running = True
            self.worker_task = asyncio.create_task(self._worker())
            logger.info("Event broadcaster started")
    
    async def stop(self):
        """Stop event broadcaster"""
        if self.running:
            self.running = False
            if self.worker_task:
                self.worker_task.cancel()
                try:
                    await self.worker_task
                except asyncio.CancelledError:
                    pass
            logger.info("Event broadcaster stopped")
    
    async def _worker(self):
        """Event processing worker"""
        while self.running:
            try:
                message = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                await self.connection_manager.broadcast(message)
                self.event_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Event broadcaster error: {e}")
    
    async def emit(self, event_type: EventType, data: Dict[str, Any], user_id: Optional[str] = None):
        """
        Emit event to be broadcasted.
        
        Args:
            event_type: Type of event
            data: Event data
            user_id: Optional user ID for user-specific events
        """
        message = WebSocketMessage(
            event_type=event_type,
            data=data,
            user_id=user_id
        )
        
        if user_id:
            await self.connection_manager.send_user_message(user_id, message)
        else:
            await self.event_queue.put(message)

# Global instances
connection_manager = ConnectionManager()
event_broadcaster = EventBroadcaster(connection_manager)

# WebSocket router
ws_router = APIRouter(prefix="/ws", tags=["WebSocket"])

async def authenticate_websocket(websocket: WebSocket) -> Optional[User]:
    """
    Authenticate WebSocket connection using query parameter token.
    
    Args:
        websocket: WebSocket connection
    
    Returns:
        Optional[User]: Authenticated user or None
    """
    try:
        # Get token from query parameters
        token = websocket.query_params.get("token")
        if not token:
            return None
        
        # Verify token
        payload = JWTManager.verify_token(token)
        username = payload.get("sub")
        
        if not username:
            return None
        
        # Get user
        user = UserManager.get_user(username)
        if not user or not user.is_active:
            return None
        
        # Convert to User model
        return User(
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            roles=user.roles,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=user.last_login
        )
    
    except Exception as e:
        logger.warning(f"WebSocket authentication failed: {e}")
        return None

@ws_router.websocket("/monitor")
async def websocket_monitor(websocket: WebSocket):
    """
    WebSocket endpoint for real-time monitoring.
    
    Supports optional authentication via token query parameter.
    Example: ws://localhost:8000/ws/monitor?token=your_jwt_token
    """
    user = await authenticate_websocket(websocket)
    connection_id = await connection_manager.connect(websocket, user)
    
    try:
        while True:
            # Wait for client messages
            data = await websocket.receive_text()
            
            try:
                client_message = json.loads(data)
                await handle_client_message(connection_id, client_message, user)
            except json.JSONDecodeError:
                await connection_manager.send_personal_message(
                    connection_id,
                    WebSocketMessage(
                        event_type=EventType.ERROR,
                        data={"error": "Invalid JSON format"}
                    )
                )
            except Exception as e:
                logger.error(f"Error handling client message: {e}")
                await connection_manager.send_personal_message(
                    connection_id,
                    WebSocketMessage(
                        event_type=EventType.ERROR,
                        data={"error": "Message processing failed"}
                    )
                )
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for connection {connection_id}: {e}")
    finally:
        await connection_manager.disconnect(connection_id)

async def handle_client_message(connection_id: str, message: Dict[str, Any], user: Optional[User]):
    """
    Handle messages from WebSocket clients.
    
    Args:
        connection_id: Connection ID
        message: Client message
        user: Authenticated user (if any)
    """
    try:
        action = message.get("action")
        
        if action == "subscribe":
            # Subscribe to event types
            event_types = [EventType(et) for et in message.get("event_types", [])]
            await connection_manager.subscribe(connection_id, event_types)
            
            await connection_manager.send_personal_message(
                connection_id,
                WebSocketMessage(
                    event_type=EventType.INFO,
                    data={
                        "message": f"Subscribed to events: {event_types}",
                        "subscribed_events": [et.value for et in event_types]
                    }
                )
            )
        
        elif action == "unsubscribe":
            # Unsubscribe from event types
            event_types = [EventType(et) for et in message.get("event_types", [])]
            await connection_manager.unsubscribe(connection_id, event_types)
            
            await connection_manager.send_personal_message(
                connection_id,
                WebSocketMessage(
                    event_type=EventType.INFO,
                    data={
                        "message": f"Unsubscribed from events: {event_types}",
                        "unsubscribed_events": [et.value for et in event_types]
                    }
                )
            )
        
        elif action == "get_status":
            # Get system status
            await send_system_status(connection_id)
        
        elif action == "ping":
            # Ping/pong for connection testing
            await connection_manager.send_personal_message(
                connection_id,
                WebSocketMessage(
                    event_type=EventType.INFO,
                    data={"message": "pong", "timestamp": datetime.utcnow().isoformat()}
                )
            )
        
        else:
            await connection_manager.send_personal_message(
                connection_id,
                WebSocketMessage(
                    event_type=EventType.ERROR,
                    data={"error": f"Unknown action: {action}"}
                )
            )
    
    except Exception as e:
        logger.error(f"Error handling client message: {e}")
        await connection_manager.send_personal_message(
            connection_id,
            WebSocketMessage(
                event_type=EventType.ERROR,
                data={"error": "Failed to process message"}
            )
        )

async def send_system_status(connection_id: str):
    """Send current system status to connection"""
    try:
        # Get connection info
        connection_info = connection_manager.get_connection_info()
        
        # Basic system status (can be extended)
        status_data = {
            "system": {
                "status": "operational",
                "timestamp": datetime.utcnow().isoformat(),
                "uptime": "system_uptime_placeholder"  # TODO: Implement actual uptime
            },
            "websocket": connection_info,
            "services": {
                "zfs": "available",  # TODO: Check actual ZFS status
                "migration": "ready",
                "api": "operational"
            }
        }
        
        await connection_manager.send_personal_message(
            connection_id,
            WebSocketMessage(
                event_type=EventType.SYSTEM_STATUS,
                data=status_data
            )
        )
    
    except Exception as e:
        logger.error(f"Failed to send system status: {e}")

# Event emission functions for use by other services
async def emit_migration_progress(migration_id: str, progress: int, status: str, details: str = ""):
    """Emit migration progress event"""
    await event_broadcaster.emit(
        EventType.MIGRATION_PROGRESS,
        {
            "migration_id": migration_id,
            "progress": progress,
            "status": status,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

async def emit_zfs_event(event_type: EventType, dataset_name: str, details: Optional[Dict[str, Any]] = None):
    """Emit ZFS-related event"""
    data = {
        "dataset_name": dataset_name,
        "timestamp": datetime.utcnow().isoformat()
    }
    if details is not None:
        data.update(details)
    
    await event_broadcaster.emit(event_type, data)

async def emit_system_alert(level: str, message: str, details: Optional[Dict[str, Any]] = None):
    """Emit system alert"""
    data = {
        "level": level,
        "message": message,
        "timestamp": datetime.utcnow().isoformat()
    }
    if details is not None:
        data.update(details)
    
    event_type = EventType.SYSTEM_ALERT if level == "error" else EventType.WARNING if level == "warning" else EventType.INFO
    await event_broadcaster.emit(event_type, data)

# WebSocket lifecycle management
async def start_websocket_system():
    """Start WebSocket system"""
    await event_broadcaster.start()
    logger.info("WebSocket system started")

async def stop_websocket_system():
    """Stop WebSocket system"""
    await event_broadcaster.stop()
    logger.info("WebSocket system stopped") 