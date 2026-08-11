"""
WebSocket endpoint for real-time updates.

Provides WebSocket connections for staff and customers to receive
instant notifications about repair order status changes.

Security:
- HttpOnly access-token cookie validation before accepting connections
- Exact Origin allowlisting for browser cookie authentication
- Token blacklist and version checking
- Active tenant, customer-link, and WorkOS membership revalidation
- Per-user connection limits (max 3)
- Connection rate limiting (max 10 attempts per minute)
- Stats endpoint requires authentication
"""
import asyncio
from dataclasses import dataclass
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import get_current_active_user, get_current_user
from app.core.security import decode_token
from app.core.websocket import manager
from app.core.workos_auth import get_current_principal
from app.db.session import AsyncSessionLocal
from app.db.models.user import User, UserRole

router = APIRouter()
logger = logging.getLogger(__name__)

# Application close codes intentionally distinguish only the client action.
# Reasons stay generic so authentication or tenant state is never disclosed.
WS_CLOSE_AUTHENTICATION = 4001
WS_CLOSE_AUTHORIZATION = 4002
WS_CLOSE_ORIGIN = 4003
WS_CLOSE_CONNECTION_POLICY = 4008
WS_CLOSE_RATE_LIMIT = 4029
WS_CLOSE_UNSUPPORTED_MESSAGE = 1008
WS_CLOSE_MESSAGE_TOO_LARGE = 1009
WS_CLOSE_INTERNAL_ERROR = 1011

WS_AUTH_REVALIDATE_SECONDS = 30.0
WS_MAX_CLIENT_MESSAGE_BYTES = 64

_CLOSE_REASONS = {
    WS_CLOSE_AUTHENTICATION: "Authentication required",
    WS_CLOSE_AUTHORIZATION: "Not authorized",
    WS_CLOSE_ORIGIN: "Origin not allowed",
    WS_CLOSE_CONNECTION_POLICY: "Connection policy",
    WS_CLOSE_RATE_LIMIT: "Try again later",
    WS_CLOSE_UNSUPPORTED_MESSAGE: "Unsupported message",
    WS_CLOSE_MESSAGE_TOO_LARGE: "Message too large",
    WS_CLOSE_INTERNAL_ERROR: "Connection error",
}


@dataclass(frozen=True)
class WebSocketPrincipal:
    user_id: str
    tenant_id: Optional[str]
    customer_id: Optional[str]
    role: str


@dataclass(frozen=True)
class WebSocketAuthResult:
    principal: Optional[WebSocketPrincipal]
    close_code: int = WS_CLOSE_AUTHENTICATION


def websocket_origin_is_allowed(websocket: WebSocket) -> bool:
    """Require exact membership in the same configured browser-origin allowlist."""
    origin = websocket.headers.get("origin")
    return bool(origin) and origin in frozenset(settings.CORS_ORIGINS)


def _principal_from_user(user: User, *, tenant_id: Optional[str] = None) -> WebSocketPrincipal:
    role = user.role.value if isinstance(user.role, UserRole) else str(user.role)
    return WebSocketPrincipal(
        user_id=str(user.id),
        tenant_id=tenant_id or (str(user.tenant_id) if user.tenant_id else None),
        customer_id=str(user.customer_id) if user.customer_id else None,
        role=role,
    )


async def resolve_websocket_principal(
    token: str,
    db: AsyncSession,
) -> WebSocketAuthResult:
    """Resolve a WebSocket through the same HTTPS identity authorities.

    Legacy/customer sessions reuse ``get_current_user`` so blacklist, token
    version, active-tenant, and selected customer-link rules cannot drift.
    WorkOS sessions reuse ``get_current_principal`` so the exact organization,
    external identity, principal, and active membership are revalidated.
    """
    claims = decode_token(token)
    if not claims or claims.get("type") is not None:
        return WebSocketAuthResult(None, WS_CLOSE_AUTHENTICATION)

    try:
        if claims.get("auth_provider") == "workos":
            principal = await get_current_principal(token=token, db=db)
            user = (
                await db.execute(select(User).where(User.id == principal.local_user_id))
            ).scalar_one_or_none()
            if not user or not user.is_active:
                return WebSocketAuthResult(None, WS_CLOSE_AUTHORIZATION)
            return WebSocketAuthResult(
                _principal_from_user(user, tenant_id=str(principal.tenant_id))
            )

        user = await get_current_user(token=token, db=db)
        return WebSocketAuthResult(_principal_from_user(user))
    except HTTPException as exc:
        close_code = (
            WS_CLOSE_AUTHENTICATION
            if exc.status_code == status.HTTP_401_UNAUTHORIZED
            else WS_CLOSE_AUTHORIZATION
        )
        return WebSocketAuthResult(None, close_code)


async def validate_websocket_token(token: str) -> WebSocketAuthResult:
    """Validate a cookie token in a fresh session for initial and live checks."""
    try:
        async with AsyncSessionLocal() as db:
            return await resolve_websocket_principal(token, db)
    except Exception:
        logger.exception("websocket_authentication_error")
        return WebSocketAuthResult(None, WS_CLOSE_INTERNAL_ERROR)


async def _close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code, reason=_CLOSE_REASONS[code])
    except Exception:
        # Closing an already-disconnected socket is intentionally best effort.
        pass


async def _accept_then_close(websocket: WebSocket, code: int) -> None:
    """Return a useful close code without registering or exposing any data.

    Once the Origin is trusted, accepting only long enough to send a generic
    close frame lets the browser perform bounded refresh/terminal handling.
    The socket is never added to the connection manager.
    """
    try:
        await websocket.accept()
    except Exception:
        pass
    await _close(websocket, code)


async def _connection_is_still_authorized(
    websocket: WebSocket,
    token: str,
    expected: WebSocketPrincipal,
) -> bool:
    result = await validate_websocket_token(token)
    if not result.principal:
        await _close(websocket, result.close_code)
        return False
    if result.principal != expected:
        # A role, tenant, customer-link, or WorkOS membership context changed.
        await _close(websocket, WS_CLOSE_AUTHORIZATION)
        return False
    return True


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
):
    """
    WebSocket endpoint for real-time updates.
    
    Authentication comes only from the existing HttpOnly ``access_token``
    cookie. Query-string credentials are never read or accepted.
    
    The connection will receive JSON messages for events like:
    - repair_order_update: When a repair order status changes
    - quote_created: When a new quote is created
    - quote_approved: When a customer approves a quote
    - invoice_created: When an invoice is generated
    - payment_received: When a payment is confirmed
    
    Send "ping" to receive "pong" (keepalive).
    """
    if not websocket_origin_is_allowed(websocket):
        await _close(websocket, WS_CLOSE_ORIGIN)
        return

    token = websocket.cookies.get("access_token")
    if not token:
        await _accept_then_close(websocket, WS_CLOSE_AUTHENTICATION)
        return

    auth_result = await validate_websocket_token(token)
    principal = auth_result.principal
    if not principal:
        await _accept_then_close(websocket, auth_result.close_code)
        return

    user_id = principal.user_id
    tenant_id = principal.tenant_id
    customer_id = principal.customer_id
    role = principal.role
    
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
            await _accept_then_close(websocket, WS_CLOSE_AUTHORIZATION)
            return
        
        if not connected:
            # Connection was rejected (rate limit or other)
            return
        
        # Keep the notification-only connection alive. A timeout performs
        # continuous expiry/revocation/membership checks even on an idle tab.
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive(),
                    timeout=WS_AUTH_REVALIDATE_SECONDS,
                )
            except asyncio.TimeoutError:
                if not await _connection_is_still_authorized(
                    websocket, token, principal
                ):
                    break
                continue

            if message.get("type") == "websocket.disconnect":
                break

            text_data = message.get("text")
            bytes_data = message.get("bytes")
            raw_size = (
                len(text_data.encode("utf-8"))
                if isinstance(text_data, str)
                else len(bytes_data or b"")
            )
            if raw_size > WS_MAX_CLIENT_MESSAGE_BYTES:
                await _close(websocket, WS_CLOSE_MESSAGE_TOO_LARGE)
                break
            if text_data != "ping":
                await _close(websocket, WS_CLOSE_UNSUPPORTED_MESSAGE)
                break
            if not await _connection_is_still_authorized(
                websocket, token, principal
            ):
                break
            await websocket.send_text("pong")

    except Exception:
        logger.exception("websocket_connection_error")
        await _close(websocket, WS_CLOSE_INTERNAL_ERROR)
        
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
