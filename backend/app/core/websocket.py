"""
WebSocket Connection Manager for real-time updates.

Manages WebSocket connections organized by tenant and user,
enabling targeted broadcasts for repair order status updates.

Security features:
- Per-user connection limits (max 3 connections per user)
- Connection tracking for rate limiting
- Automatic cleanup of stale connections
"""
from fastapi import WebSocket
from typing import Dict, Optional, List
from collections import defaultdict
from datetime import datetime, timedelta
import logging
import asyncio

from app.core.config import settings

logger = logging.getLogger(__name__)

# Security constants
MAX_CONNECTIONS_PER_USER = 3
CONNECTION_RATE_LIMIT_WINDOW = 60  # seconds
MAX_CONNECTIONS_PER_WINDOW = 10  # max connection attempts per window

# Disable rate limiting in development
RATE_LIMIT_ENABLED = settings.ENVIRONMENT != "development"


class ConnectionManager:
    """
    Manages WebSocket connections for real-time updates.
    
    Connections are organized by:
    - tenant_id -> user_id -> WebSocket (for staff)
    - customer_id -> WebSocket (for customers)
    
    Security:
    - Limits connections per user to prevent resource exhaustion
    - Tracks connection attempts for rate limiting
    """
    
    def __init__(self):
        # Staff connections: tenant_id -> {user_id -> [websockets]}
        self.tenant_connections: Dict[str, Dict[str, List[WebSocket]]] = {}
        # Customer connections: customer_id -> [websockets]
        self.customer_connections: Dict[str, List[WebSocket]] = defaultdict(list)
        # Connection attempt tracking: user_id -> [timestamps]
        self._connection_attempts: Dict[str, List[datetime]] = defaultdict(list)
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
    
    def _check_rate_limit(self, user_id: str) -> bool:
        """
        Check if user has exceeded connection rate limit.
        Returns True if allowed, False if rate limited.
        Disabled in development environment.
        """
        if not RATE_LIMIT_ENABLED:
            return True
        
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=CONNECTION_RATE_LIMIT_WINDOW)
        
        # Clean old attempts
        self._connection_attempts[user_id] = [
            ts for ts in self._connection_attempts[user_id] if ts > cutoff
        ]
        
        # Check limit
        if len(self._connection_attempts[user_id]) >= MAX_CONNECTIONS_PER_WINDOW:
            logger.warning(f"Rate limit exceeded for user {user_id}")
            return False
        
        # Record this attempt
        self._connection_attempts[user_id].append(now)
        return True
    
    async def connect_staff(
        self, 
        websocket: WebSocket, 
        tenant_id: str, 
        user_id: str
    ) -> bool:
        """
        Connect a staff member (garage owner, admin, mechanic, receptionist).
        
        Returns True if connected, False if rejected (rate limit or connection limit).
        """
        async with self._lock:
            # Check rate limit
            if not self._check_rate_limit(user_id):
                await websocket.close(code=4029, reason="Too many connection attempts")
                return False
            
            # Initialize tenant dict if needed
            if tenant_id not in self.tenant_connections:
                self.tenant_connections[tenant_id] = {}
            if user_id not in self.tenant_connections[tenant_id]:
                self.tenant_connections[tenant_id][user_id] = []
            
            # Check connection limit
            current_connections = self.tenant_connections[tenant_id][user_id]
            if len(current_connections) >= MAX_CONNECTIONS_PER_USER:
                # Close oldest connection to make room
                oldest = current_connections.pop(0)
                try:
                    await oldest.close(code=4008, reason="Connection replaced by new session")
                except Exception:
                    pass
                logger.info(f"Closed oldest connection for user {user_id} (limit reached)")
            
            await websocket.accept()
            self.tenant_connections[tenant_id][user_id].append(websocket)
        
        logger.info(f"Staff connected: tenant={tenant_id}, user={user_id}")
        return True
    
    async def connect_customer(
        self, 
        websocket: WebSocket, 
        customer_id: str
    ) -> bool:
        """
        Connect a customer.
        
        Returns True if connected, False if rejected (rate limit or connection limit).
        """
        async with self._lock:
            # Check rate limit
            if not self._check_rate_limit(f"customer:{customer_id}"):
                await websocket.close(code=4029, reason="Too many connection attempts")
                return False
            
            # Check connection limit
            current_connections = self.customer_connections[customer_id]
            if len(current_connections) >= MAX_CONNECTIONS_PER_USER:
                # Close oldest connection to make room
                oldest = current_connections.pop(0)
                try:
                    await oldest.close(code=4008, reason="Connection replaced by new session")
                except Exception:
                    pass
                logger.info(f"Closed oldest connection for customer {customer_id} (limit reached)")
            
            await websocket.accept()
            self.customer_connections[customer_id].append(websocket)
        
        logger.info(f"Customer connected: customer={customer_id}")
        return True
    
    async def disconnect_staff(
        self, 
        tenant_id: str, 
        user_id: str, 
        websocket: Optional[WebSocket] = None
    ) -> None:
        """
        Disconnect a staff member.
        
        If websocket is provided, only that specific connection is removed.
        If websocket is None, all connections for the user are removed.
        """
        async with self._lock:
            if tenant_id in self.tenant_connections and user_id in self.tenant_connections[tenant_id]:
                if websocket:
                    # Remove specific connection
                    try:
                        self.tenant_connections[tenant_id][user_id].remove(websocket)
                    except ValueError:
                        pass
                else:
                    # Remove all connections
                    self.tenant_connections[tenant_id][user_id] = []
                
                # Clean up empty entries
                if not self.tenant_connections[tenant_id][user_id]:
                    del self.tenant_connections[tenant_id][user_id]
                if not self.tenant_connections[tenant_id]:
                    del self.tenant_connections[tenant_id]
        
        logger.info(f"Staff disconnected: tenant={tenant_id}, user={user_id}")
    
    async def disconnect_customer(
        self, 
        customer_id: str, 
        websocket: Optional[WebSocket] = None
    ) -> None:
        """
        Disconnect a customer.
        
        If websocket is provided, only that specific connection is removed.
        If websocket is None, all connections for the customer are removed.
        """
        async with self._lock:
            if customer_id in self.customer_connections:
                if websocket:
                    # Remove specific connection
                    try:
                        self.customer_connections[customer_id].remove(websocket)
                    except ValueError:
                        pass
                else:
                    # Remove all connections
                    self.customer_connections[customer_id] = []
                
                # Clean up empty entries
                if not self.customer_connections[customer_id]:
                    del self.customer_connections[customer_id]
        
        logger.info(f"Customer disconnected: customer={customer_id}")
    
    async def _safe_send(self, websocket: WebSocket, message: dict) -> bool:
        """Safely send a message, returning False if connection is closed."""
        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.warning(f"Failed to send WebSocket message: {e}")
            return False
    
    async def broadcast_to_tenant(self, tenant_id: str, message: dict) -> int:
        """
        Broadcast a message to all connected staff in a tenant.
        Returns the number of successful sends.
        """
        sent_count = 0
        async with self._lock:
            user_connections = self.tenant_connections.get(tenant_id, {}).copy()
        
        disconnected_websockets = []
        for user_id, websockets in user_connections.items():
            for ws in websockets.copy():
                if await self._safe_send(ws, message):
                    sent_count += 1
                else:
                    disconnected_websockets.append((tenant_id, user_id, ws))
        
        # Clean up disconnected clients
        for tenant_id, user_id, ws in disconnected_websockets:
            await self.disconnect_staff(tenant_id, user_id, ws)
        
        logger.debug(f"Broadcast to tenant {tenant_id}: {sent_count} recipients")
        return sent_count
    
    async def send_to_customer(self, customer_id: str, message: dict) -> bool:
        """Send a message to all connections for a specific customer."""
        async with self._lock:
            websockets = self.customer_connections.get(customer_id, []).copy()
        
        if not websockets:
            return False
        
        success = False
        disconnected = []
        for ws in websockets:
            if await self._safe_send(ws, message):
                success = True
            else:
                disconnected.append(ws)
        
        # Clean up disconnected
        for ws in disconnected:
            await self.disconnect_customer(customer_id, ws)
        
        return success
    
    async def send_to_user(
        self, 
        tenant_id: str, 
        user_id: str, 
        message: dict
    ) -> bool:
        """Send a message to all connections for a specific staff member."""
        async with self._lock:
            websockets = self.tenant_connections.get(tenant_id, {}).get(user_id, []).copy()
        
        if not websockets:
            return False
        
        success = False
        disconnected = []
        for ws in websockets:
            if await self._safe_send(ws, message):
                success = True
            else:
                disconnected.append(ws)
        
        # Clean up disconnected
        for ws in disconnected:
            await self.disconnect_staff(tenant_id, user_id, ws)
        
        return success
    
    def get_connection_count(self) -> dict:
        """Get current connection statistics."""
        staff_count = sum(
            sum(len(websockets) for websockets in users.values())
            for users in self.tenant_connections.values()
        )
        customer_count = sum(
            len(websockets) for websockets in self.customer_connections.values()
        )
        return {
            "staff_connections": staff_count,
            "customer_connections": customer_count,
            "tenant_count": len(self.tenant_connections),
        }


# Global connection manager instance
manager = ConnectionManager()


# Event type constants
class WSEventType:
    """WebSocket event types for real-time updates."""
    REPAIR_ORDER_UPDATE = "repair_order_update"
    QUOTE_CREATED = "quote_created"
    QUOTE_APPROVED = "quote_approved"
    QUOTE_DECLINED = "quote_declined"
    INVOICE_CREATED = "invoice_created"
    PAYMENT_RECEIVED = "payment_received"
    SMS_MESSAGE_CREATED = "sms_message_created"
    SMS_THREAD_UPDATED = "sms_thread_updated"
    MECHANIC_TIMER_UPDATE = "mechanic_timer_update"
    MECHANIC_IDLE_ALERT = "mechanic_idle_alert"
    MECHANIC_ATTENDANCE_UPDATE = "mechanic_attendance_update"
    MECHANIC_BREAK_UPDATE = "mechanic_break_update"


async def broadcast_repair_order_update(
    tenant_id: str,
    customer_id: str,
    order_id: str,
    order_number: str,
    status: str,
    updated_at: Optional[str] = None,
    hold_reason: Optional[str] = None,
    held_at: Optional[str] = None,
) -> None:
    """
    Broadcast a repair order status update to relevant parties.
    
    Sends to:
    - All staff in the tenant
    - The customer who owns the order
    """
    message = {
        "type": WSEventType.REPAIR_ORDER_UPDATE,
        "order_id": order_id,
        "order_number": order_number,
        "status": status,
        "updated_at": updated_at,
        "hold_reason": hold_reason,
        "held_at": held_at,
    }
    
    # Broadcast to tenant staff
    await manager.broadcast_to_tenant(tenant_id, message)
    
    # Send to customer
    await manager.send_to_customer(customer_id, message)


async def broadcast_quote_event(
    tenant_id: str,
    customer_id: str,
    quote_id: str,
    quote_number: str,
    event_type: str,
    order_id: str,
) -> None:
    """Broadcast quote-related events."""
    message = {
        "type": event_type,
        "quote_id": quote_id,
        "quote_number": quote_number,
        "order_id": order_id,
    }
    
    await manager.broadcast_to_tenant(tenant_id, message)
    await manager.send_to_customer(customer_id, message)


async def broadcast_invoice_created(
    tenant_id: str,
    customer_id: str,
    invoice_id: str,
    invoice_number: str,
    order_id: str,
    total_amount: str,
) -> None:
    """Broadcast invoice creation event."""
    message = {
        "type": WSEventType.INVOICE_CREATED,
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "order_id": order_id,
        "total_amount": total_amount,
    }
    
    await manager.broadcast_to_tenant(tenant_id, message)
    await manager.send_to_customer(customer_id, message)


async def broadcast_payment_received(
    tenant_id: str,
    customer_id: str,
    invoice_id: str,
    order_id: str,
) -> None:
    """Broadcast payment received event."""
    message = {
        "type": WSEventType.PAYMENT_RECEIVED,
        "invoice_id": invoice_id,
        "order_id": order_id,
    }
    
    await manager.broadcast_to_tenant(tenant_id, message)
    await manager.send_to_customer(customer_id, message)


async def broadcast_sms_message_event(
    tenant_id: str,
    thread_id: str,
    message_id: str,
    customer_id: str,
    direction: str,
    source: str,
    body: str,
    delivery_status: str,
    created_at: Optional[str] = None,
) -> None:
    """Broadcast an SMS message creation/update event to tenant staff."""
    message = {
        "type": WSEventType.SMS_MESSAGE_CREATED,
        "thread_id": thread_id,
        "message_id": message_id,
        "customer_id": customer_id,
        "direction": direction,
        "source": source,
        "body": body,
        "delivery_status": delivery_status,
        "created_at": created_at,
    }
    await manager.broadcast_to_tenant(tenant_id, message)


async def broadcast_sms_thread_event(
    tenant_id: str,
    thread_id: str,
    customer_id: str,
    unread_count_staff: int,
    last_message_at: Optional[str],
    last_message_preview: Optional[str],
    action: Optional[str] = None,
) -> None:
    """Broadcast a thread summary update to tenant staff."""
    message = {
        "type": WSEventType.SMS_THREAD_UPDATED,
        "thread_id": thread_id,
        "customer_id": customer_id,
        "unread_count_staff": unread_count_staff,
        "last_message_at": last_message_at,
        "last_message_preview": last_message_preview,
        "action": action,
    }
    await manager.broadcast_to_tenant(tenant_id, message)


async def broadcast_mechanic_timer_update(
    tenant_id: str,
    mechanic_id: str,
    session_id: str,
    action: str,
) -> None:
    message = {
        "type": WSEventType.MECHANIC_TIMER_UPDATE,
        "mechanic_id": mechanic_id,
        "session_id": session_id,
        "action": action,
    }
    await manager.broadcast_to_tenant(tenant_id, message)


async def broadcast_mechanic_idle_alert(
    tenant_id: str,
    mechanic_id: str,
    idle_minutes: int,
    local_date: str,
    mechanic_name: Optional[str] = None,
) -> None:
    message = {
        "type": WSEventType.MECHANIC_IDLE_ALERT,
        "mechanic_id": mechanic_id,
        "idle_minutes": idle_minutes,
        "local_date": local_date,
        "mechanic_name": mechanic_name,
    }
    await manager.broadcast_to_tenant(tenant_id, message)


async def broadcast_mechanic_attendance_update(
    tenant_id: str,
    mechanic_id: str,
    attendance_session_id: str,
    action: str,
) -> None:
    message = {
        "type": WSEventType.MECHANIC_ATTENDANCE_UPDATE,
        "mechanic_id": mechanic_id,
        "attendance_session_id": attendance_session_id,
        "action": action,
    }
    await manager.broadcast_to_tenant(tenant_id, message)


async def broadcast_mechanic_break_update(
    tenant_id: str,
    mechanic_id: str,
    break_session_id: str,
    action: str,
) -> None:
    message = {
        "type": WSEventType.MECHANIC_BREAK_UPDATE,
        "mechanic_id": mechanic_id,
        "break_session_id": break_session_id,
        "action": action,
    }
    await manager.broadcast_to_tenant(tenant_id, message)
