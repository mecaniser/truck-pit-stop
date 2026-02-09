# WebSocket Real-Time Updates - Educational Guide

## What Are WebSockets?

WebSockets provide **persistent, bidirectional communication** between a client (browser) and server. Unlike traditional HTTP requests where the client must ask for data, WebSockets allow the server to **push updates instantly** to connected clients.

### HTTP vs WebSocket

```
HTTP (Request-Response):
┌────────┐                    ┌────────┐
│ Client │ ──── Request ────> │ Server │
│        │ <─── Response ──── │        │
└────────┘                    └────────┘
(Connection closes after each request)

WebSocket (Persistent):
┌────────┐ <═══════════════> ┌────────┐
│ Client │   Open Connection  │ Server │
│        │ <──── Messages ──> │        │
└────────┘                    └────────┘
(Connection stays open for real-time communication)
```

## Why WebSockets for TruckPitStop?

### The Problem with Polling

Before WebSockets, we used **polling** - repeatedly asking the server "any updates?"

```typescript
// Old approach: Poll every 30 seconds
useQuery({
  queryKey: ['jobs'],
  queryFn: fetchJobs,
  refetchInterval: 30000, // Ask server every 30s
})
```

**Problems:**
- **Delayed updates**: Up to 30 seconds before seeing changes
- **Wasted requests**: Most polls return "no changes"
- **Server load**: Thousands of unnecessary requests
- **Battery drain**: Mobile devices constantly polling

### The WebSocket Solution

With WebSockets, the server **tells us** when something changes:

```
1. Mechanic completes work
2. Server broadcasts: "Order #123 status changed to PENDING_REVIEW"
3. All connected clients instantly update their UI
```

**Benefits:**
- **Instant updates**: Changes appear in < 100ms
- **Efficient**: Only sends data when something changes
- **Scalable**: Less server load than polling
- **Better UX**: Users see real-time progress

## How It Works in TruckPitStop

### Connection Flow

```
1. User logs in → Gets JWT token
2. Frontend opens WebSocket: ws://server/api/v1/ws?token=<jwt>
3. Server validates token, identifies user/tenant
4. Connection stays open for real-time messages
5. When status changes → Server broadcasts to relevant clients
6. Frontend receives message → Invalidates React Query cache → UI updates
```

### Who Receives What?

| Event | Recipients |
|-------|-----------|
| Repair order status change | All tenant staff + Customer who owns the order |
| Quote approved/declined | All tenant staff + Customer |
| Invoice created | All tenant staff + Customer |
| Payment received | All tenant staff + Customer |

### Message Format

```json
{
  "type": "repair_order_update",
  "order_id": "uuid-here",
  "order_number": "RO-ABC123-000001",
  "status": "in_progress",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

## Key Concepts

### 1. Connection Manager (Backend)

The `ConnectionManager` class tracks all active connections:

```python
class ConnectionManager:
    # Staff connections organized by tenant (supports multiple per user)
    tenant_connections: Dict[tenant_id, Dict[user_id, List[WebSocket]]]
    
    # Customer connections by customer ID (supports multiple per customer)
    customer_connections: Dict[customer_id, List[WebSocket]]
    
    # Rate limiting: tracks connection attempts
    _connection_attempts: Dict[user_id, List[datetime]]
```

This allows targeted broadcasts:
- `broadcast_to_tenant(tenant_id)` → All staff in that garage
- `send_to_customer(customer_id)` → Specific customer (all their tabs/devices)

### 2. Authentication

WebSockets can't use HTTP headers for auth, so we pass the JWT as a query parameter:

```
ws://server/api/v1/ws?token=eyJhbGciOiJIUzI1NiIs...
```

The server validates this token before accepting the connection.

### 3. Keepalive (Ping/Pong)

WebSocket connections can silently die. We use ping/pong to detect this:

```typescript
// Client sends "ping" every 30 seconds
setInterval(() => ws.send('ping'), 30000)

// Server responds with "pong"
// If no pong received, reconnect
```

### 4. Reconnection Strategy

Networks are unreliable. The frontend automatically reconnects:

```typescript
ws.onclose = () => {
  // Wait 3 seconds, then reconnect
  setTimeout(connect, 3000)
}

// Also reconnect when tab becomes visible
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && !isConnected) reconnect()
})
```

### 5. React Query Integration

Instead of managing state manually, WebSocket events **invalidate queries**:

```typescript
ws.onmessage = (event) => {
  const data = JSON.parse(event.data)
  
  if (data.type === 'repair_order_update') {
    // Tell React Query to refetch these queries
    queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
  }
}
```

This leverages React Query's existing caching and loading states.

## Event Types

| Event | Trigger | What It Means |
|-------|---------|---------------|
| `repair_order_update` | Any status change | Order moved to new stage |
| `quote_created` | Quote sent to customer | Customer has a quote to review |
| `quote_approved` | Customer approves | Work can begin |
| `quote_declined` | Customer declines | May need revised quote |
| `invoice_created` | Invoice generated | Customer can pay |
| `payment_received` | Payment confirmed | Order complete |

## Debugging WebSockets

### Browser DevTools

1. Open DevTools → Network tab
2. Filter by "WS" (WebSocket)
3. Click the connection to see messages

### Backend Logs

```
INFO: Staff WebSocket connected: tenant=abc123, user=def456
INFO: Customer WebSocket connected: customer=ghi789
INFO: Broadcast to tenant abc123: 3 recipients
```

### Common Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| Connection immediately closes | Invalid/expired token | Check JWT expiration |
| No messages received | Wrong tenant/customer ID | Verify user associations |
| Reconnecting constantly | Network issues | Check for firewall/proxy issues |
| Messages delayed | Server overload | Check server resources |

## Security Considerations

### Authentication & Authorization

| Control | Implementation |
|---------|---------------|
| JWT Validation | Token verified before accepting connection |
| Token Blacklist | Logged-out tokens are rejected |
| Token Versioning | Mass invalidation supported (password change, etc.) |
| Tenant Isolation | Users only receive events for their tenant |

### Rate Limiting & Resource Protection

| Control | Limit | Purpose |
|---------|-------|---------|
| Connection Rate Limit | 10 attempts/minute/user | Prevents connection spam attacks |
| Per-User Connection Limit | 3 connections/user | Prevents resource exhaustion |
| Stats Endpoint | Admin-only | Protects operational data |

When a user exceeds the connection limit, the **oldest connection is gracefully closed** with code `4008` to make room for the new one. This handles legitimate multi-tab usage while preventing abuse.

### Custom Close Codes

| Code | Meaning | User Action |
|------|---------|-------------|
| 4001 | Invalid/expired token | Re-authenticate |
| 4002 | No tenant/customer association | Contact support |
| 4008 | Connection replaced (limit) | Normal - old tab closed |
| 4029 | Rate limit exceeded | Wait and retry |

### Known Limitations

1. **Token in URL**: JWT appears in query string, may be logged. Mitigation: use short-lived access tokens, configure log sanitization.
2. **Single-server only**: Current implementation doesn't support horizontal scaling. Future: Redis pub/sub for multi-instance.
3. **No message-level auth**: Server only broadcasts, doesn't accept commands beyond ping/pong.

## Future Improvements

1. **Redis Pub/Sub**: For multi-instance deployments, use Redis to broadcast across servers.
2. **Message queuing**: Buffer messages if client temporarily disconnects.
3. **Selective subscriptions**: Let clients subscribe to specific order IDs.
4. **Compression**: Use WebSocket compression for large payloads.

## Summary

WebSockets transform TruckPitStop from a "refresh to see updates" app to a **real-time collaborative platform**. When a mechanic starts work, the customer sees it instantly. When a customer approves a quote, the garage knows immediately.

The implementation uses:
- **Backend**: FastAPI WebSocket endpoint + ConnectionManager
- **Frontend**: Custom React hook + React Query integration
- **Auth**: JWT token validation on connection
- **Reliability**: Auto-reconnect + ping/pong keepalive
