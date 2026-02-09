"""
WebSocket endpoint for real-time updates.

Provides WebSocket connections for staff and customers to receive
instant notifications about repair order status changes.

Security:
- JWT token validation before accepting connections
- Token blacklist and version checking
- Per-user connection limits (max 3)
- Connection rate limiting (max 10 attempts per minute)
- Stats endpoint requires authentication
"""
from typing import Optional, Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.core.security import decode_token
from app.core.redis import is_token_blacklisted, get_token_version
from app.core.websocket import manager
from app.core.dependencies import get_current_active_user
from app.db.session import AsyncSessionLocal
from app.db.models.user import User, UserRole

router = APIRouter()
logger = logging.getLogger(__name__)


async def validate_websocket_token(token: str) -> Optional[Dict]:
    """
    Validate a JWT token for WebSocket connection.
    
    Returns user info dict if valid, None otherwise.
    """
    payload = decode_token(token)
    if not payload:
        logger.warning("WebSocket auth failed: invalid/expired token")
        return None
    
    user_id = payload.get("sub")
    jti = payload.get("jti")
    token_version = payload.get("ver", 0)
    
    if not user_id:
        logger.warning("WebSocket auth failed: no user_id in token")
        return None
    
    # Check if token is blacklisted
    if jti and await is_token_blacklisted(jti):
        logger.warning(f"WebSocket auth failed: token blacklisted for user {user_id}")
        return None
    
    # Check token version
    current_version = await get_token_version(user_id)
    if token_version < current_version:
        logger.warning(f"WebSocket auth failed: token version {token_version} < {current_version} for user {user_id}")
        return None
    
    # Fetch user from database
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"WebSocket auth failed: user {user_id} not found")
            return None
        
        if not user.is_active:
            logger.warning(f"WebSocket auth failed: user {user_id} is inactive")
            return None
        
        return {
            "user_id": str(user.id),
            "tenant_id": str(user.tenant_id) if user.tenant_id else None,
            "customer_id": str(user.customer_id) if user.customer_id else None,
            "role": user.role,
        }


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
):
    """
    WebSocket endpoint for real-time updates.
    
    Connect with: ws://host/api/v1/ws?token=<jwt_token>
    
    The connection will receive JSON messages for events like:
    - repair_order_update: When a repair order status changes
    - quote_created: When a new quote is created
    - quote_approved: When a customer approves a quote
    - invoice_created: When an invoice is generated
    - payment_received: When a payment is confirmed
    
    Send "ping" to receive "pong" (keepalive).
    """
    # Validate token before accepting connection
    user_info = await validate_websocket_token(token)
    
    if not user_info:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return
    
    user_id = user_info["user_id"]
    tenant_id = user_info["tenant_id"]
    customer_id = user_info["customer_id"]
    role = user_info["role"]
    
    # Connect based on user type
    is_customer = role == "customer"
    connected = False
    
    try:
        if is_customer and customer_id:
            connected = await manager.connect_customer(websocket, customer_id)
            if connected:
                logger.info(f"Customer WebSocket connected: {customer_id}")
        elif tenant_id:
            connected = await manager.connect_staff(websocket, tenant_id, user_id)
            if connected:
                logger.info(f"Staff WebSocket connected: tenant={tenant_id}, user={user_id}")
        else:
            await websocket.close(code=4002, reason="User has no tenant or customer association")
            return
        
        if not connected:
            # Connection was rejected (rate limit or other)
            return
        
        # Keep connection alive
        while True:
            try:
                data = await websocket.receive_text()
                
                # Handle ping/pong keepalive
                if data == "ping":
                    await websocket.send_text("pong")
                    
            except WebSocketDisconnect:
                break
                
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        
    finally:
        # Clean up connection
        if connected:
            if is_customer and customer_id:
                await manager.disconnect_customer(customer_id, websocket)
                logger.info(f"Customer WebSocket disconnected: {customer_id}")
            elif tenant_id:
                await manager.disconnect_staff(tenant_id, user_id, websocket)
                logger.info(f"Staff WebSocket disconnected: tenant={tenant_id}, user={user_id}")


@router.get("/ws/stats")
async def websocket_stats(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get current WebSocket connection statistics (for monitoring).
    
    Requires authentication. Only garage owners, admins, and super admins can access.
    """
    # Only allow staff with admin privileges
    if current_user.role not in [UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view WebSocket stats",
        )
    
    return manager.get_connection_count()
