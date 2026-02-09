# WebSocket Implementation Reference

Technical documentation for the WebSocket real-time update system.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Customer   │  │   Mechanic   │  │   Dashboard  │          │
│  │    Portal    │  │    Portal    │  │     Home     │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│         └────────────┬────┴─────────────────┘                   │
│                      │                                          │
│              ┌───────▼───────┐                                  │
│              │ useWebSocket  │  React Hook                      │
│              │     Hook      │  (auto-reconnect, cache invalidate)
│              └───────┬───────┘                                  │
└──────────────────────┼──────────────────────────────────────────┘
                       │ WebSocket Connection
                       │ ws://host/api/v1/ws?token=<jwt>
┌──────────────────────┼──────────────────────────────────────────┐
│                      │           Backend                        │
│              ┌───────▼───────┐                                  │
│              │   WebSocket   │  /api/v1/ws endpoint             │
│              │   Endpoint    │  (JWT validation)                │
│              └───────┬───────┘                                  │
│                      │                                          │
│              ┌───────▼───────┐                                  │
│              │  Connection   │  Manages active connections      │
│              │   Manager     │  by tenant_id / customer_id      │
│              └───────┬───────┘                                  │
│                      │                                          │
│    ┌─────────────────┼─────────────────┐                       │
│    │                 │                 │                        │
│ ┌──▼──┐  ┌──────────▼──────────┐  ┌──▼──┐                     │
│ │ RO  │  │       Quotes        │  │ Inv │  API Endpoints       │
│ │ API │  │        API          │  │ API │  (broadcast on change)│
│ └─────┘  └─────────────────────┘  └─────┘                      │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
backend/
├── app/
│   ├── core/
│   │   └── websocket.py          # ConnectionManager + broadcast helpers
│   └── api/v1/endpoints/
│       ├── websocket.py          # WebSocket endpoint
│       ├── repair_orders.py      # Modified: broadcasts on status change
│       ├── quotes.py             # Modified: broadcasts on approve/decline
│       ├── invoices.py           # Modified: broadcasts on create
│       └── payments.py           # Modified: broadcasts on payment

frontend/
└── src/
    ├── hooks/
    │   └── useWebSocket.ts       # WebSocket React hook
    └── features/
        ├── customer-portal/
        │   └── CustomerPortalPage.tsx  # Uses useWebSocket
        ├── mechanic-portal/
        │   └── MechanicPortalPage.tsx  # Uses useWebSocket
        └── dashboard/
            └── DashboardHome.tsx       # Uses useWebSocket
```

## Backend Implementation

### Connection Manager

**File:** `backend/app/core/websocket.py`

```python
class ConnectionManager:
    def __init__(self):
        # Staff: tenant_id -> {user_id -> WebSocket}
        self.tenant_connections: Dict[str, Dict[str, WebSocket]] = {}
        # Customers: customer_id -> WebSocket
        self.customer_connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()  # Thread-safe operations
    
    async def connect_staff(self, ws: WebSocket, tenant_id: str, user_id: str)
    async def connect_customer(self, ws: WebSocket, customer_id: str)
    async def disconnect_staff(self, tenant_id: str, user_id: str)
    async def disconnect_customer(self, customer_id: str)
    async def broadcast_to_tenant(self, tenant_id: str, message: dict) -> int
    async def send_to_customer(self, customer_id: str, message: dict) -> bool

# Global instance
manager = ConnectionManager()
```

### Broadcast Helpers

```python
async def broadcast_repair_order_update(
    tenant_id: str,
    customer_id: str,
    order_id: str,
    order_number: str,
    status: str,
    updated_at: Optional[str] = None,
)

async def broadcast_quote_event(
    tenant_id: str,
    customer_id: str,
    quote_id: str,
    quote_number: str,
    event_type: str,  # QUOTE_APPROVED or QUOTE_DECLINED
    order_id: str,
)

async def broadcast_invoice_created(
    tenant_id: str,
    customer_id: str,
    invoice_id: str,
    invoice_number: str,
    order_id: str,
    total_amount: str,
)

async def broadcast_payment_received(
    tenant_id: str,
    customer_id: str,
    invoice_id: str,
    order_id: str,
)
```

### WebSocket Endpoint

**File:** `backend/app/api/v1/endpoints/websocket.py`

```python
@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),  # JWT passed as query param
):
    # 1. Validate JWT token
    user_info = await validate_websocket_token(token)
    if not user_info:
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    # 2. Connect based on user type
    if user_info["role"] == "customer":
        await manager.connect_customer(websocket, user_info["customer_id"])
    else:
        await manager.connect_staff(websocket, user_info["tenant_id"], user_info["user_id"])
    
    # 3. Keep connection alive
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        # 4. Clean up on disconnect
        await manager.disconnect_...
```

### Adding Broadcasts to Endpoints

Example from `repair_orders.py`:

```python
from app.core.websocket import broadcast_repair_order_update

@router.post("/{order_id}/start-work")
async def start_work(order_id: UUID, ...):
    # ... existing logic ...
    
    order.status = RepairOrderStatus.IN_PROGRESS
    await db.commit()
    await db.refresh(order)
    
    # ADD: Broadcast WebSocket update
    await broadcast_repair_order_update(
        tenant_id=str(order.tenant_id),
        customer_id=str(order.customer_id),
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )
    
    # ... rest of endpoint (email notifications, etc.) ...
```

## Frontend Implementation

### useWebSocket Hook

**File:** `frontend/src/hooks/useWebSocket.ts`

```typescript
interface UseWebSocketOptions {
  showToasts?: boolean  // Show toast notifications
  debug?: boolean       // Console logging
}

interface UseWebSocketReturn {
  isConnected: boolean
  reconnect: () => void
}

export function useWebSocket(options?: UseWebSocketOptions): UseWebSocketReturn
```

**Key Features:**

1. **Auto-connect on auth**: Connects when `isAuthenticated && token`
2. **Auto-reconnect**: Reconnects after 3s on disconnect
3. **Visibility-aware**: Reconnects when tab becomes visible
4. **Ping/pong keepalive**: Sends ping every 30s
5. **Query invalidation**: Invalidates React Query caches on events

### Query Invalidation Map

```typescript
switch (data.type) {
  case 'repair_order_update':
    queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
    queryClient.invalidateQueries({ queryKey: ['mechanic-jobs'] })
    queryClient.invalidateQueries({ queryKey: ['mechanic-history'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
    break
    
  case 'quote_approved':
  case 'quote_declined':
    queryClient.invalidateQueries({ queryKey: ['quotes'] })
    queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
    break
    
  case 'invoice_created':
    queryClient.invalidateQueries({ queryKey: ['invoices'] })
    queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
    break
    
  case 'payment_received':
    queryClient.invalidateQueries({ queryKey: ['invoices'] })
    queryClient.invalidateQueries({ queryKey: ['payments'] })
    queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
    break
}
```

### Usage in Components

```typescript
// CustomerPortalPage.tsx
export default function CustomerPortalPage() {
  useWebSocket({ showToasts: true })
  // ... rest of component
}

// MechanicPortalPage.tsx
export default function MechanicPortalPage() {
  useWebSocket({ showToasts: true })
  // ... rest of component
}

// DashboardHome.tsx
export default function DashboardHome() {
  useWebSocket({ showToasts: true })
  // ... rest of component
}
```

## Event Types Reference

### repair_order_update

Sent when any repair order status changes.

```json
{
  "type": "repair_order_update",
  "order_id": "550e8400-e29b-41d4-a716-446655440000",
  "order_number": "RO-F90D5493-000042",
  "status": "in_progress",
  "updated_at": "2024-01-15T10:30:00.000Z"
}
```

**Triggers:**
- `assign_mechanic` → status: assigned
- `acknowledge` → status: acknowledged
- `start_work` → status: in_progress
- `complete_work` → status: pending_review
- `approve_completion` → status: completed
- Quote approval → status: approved
- Invoice created → status: invoiced
- Payment received → status: paid

### quote_approved / quote_declined

```json
{
  "type": "quote_approved",
  "quote_id": "550e8400-e29b-41d4-a716-446655440001",
  "quote_number": "QT-F90D5493-000015",
  "order_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### invoice_created

```json
{
  "type": "invoice_created",
  "invoice_id": "550e8400-e29b-41d4-a716-446655440002",
  "invoice_number": "INV-F90D5493-000008",
  "order_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_amount": "1250.00"
}
```

### payment_received

```json
{
  "type": "payment_received",
  "invoice_id": "550e8400-e29b-41d4-a716-446655440002",
  "order_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## WebSocket Close Codes

| Code | Reason | Action |
|------|--------|--------|
| 1000 | Normal closure | None |
| 1006 | Abnormal closure | Auto-reconnect (5s delay) |
| 4001 | Invalid/expired token | Redirect to login |
| 4002 | No tenant/customer association | Check user setup |

## Monitoring

### Stats Endpoint

```
GET /api/v1/ws/stats

Response:
{
  "staff_connections": 12,
  "customer_connections": 5,
  "tenant_count": 3
}
```

### Server Logs

```
INFO: Staff WebSocket connected: tenant=f90d5493, user=60af11da
INFO: Customer WebSocket connected: customer=2ccbb000
DEBUG: Broadcast to tenant f90d5493: 4 recipients
INFO: Staff WebSocket disconnected: tenant=f90d5493, user=60af11da
```

## Testing

### Manual Testing

1. Open two browser tabs (garage dashboard + customer portal)
2. Perform an action (e.g., start work on an order)
3. Verify both tabs update instantly

### Automated Testing

```python
# Backend: Test broadcast
async def test_broadcast_to_tenant():
    manager = ConnectionManager()
    mock_ws = AsyncMock()
    await manager.connect_staff(mock_ws, "tenant1", "user1")
    
    count = await manager.broadcast_to_tenant("tenant1", {"type": "test"})
    
    assert count == 1
    mock_ws.send_json.assert_called_once()
```

```typescript
// Frontend: Test hook
test('invalidates queries on repair_order_update', () => {
  const queryClient = new QueryClient()
  // ... mock WebSocket, trigger message
  expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
    queryKey: ['repair-orders']
  })
})
```

## Scaling (Future)

For multi-instance deployments, add Redis Pub/Sub:

```python
# In websocket.py
class ConnectionManager:
    async def init_redis(self):
        self.redis = await aioredis.from_url(settings.REDIS_URL)
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe("ws_events")
        asyncio.create_task(self._listen_redis())
    
    async def _listen_redis(self):
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                await self._handle_redis_message(data)
    
    async def publish_event(self, event: dict):
        await self.redis.publish("ws_events", json.dumps(event))
```

This allows broadcasts to reach clients connected to any server instance.
