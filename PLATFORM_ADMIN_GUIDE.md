# Platform Admin Guide (SUPER_ADMIN)

## Overview

As the platform owner with SUPER_ADMIN access, you manage the TruckPitStop SaaS business. Your interface is **completely separate** from individual garage operations.

## Your Dashboard

### 1. Platform Analytics (`GET /api/v1/admin/platform/stats`)

View high-level metrics across your entire platform:

```json
{
  "tenants": {
    "total": 50,
    "active": 47,
    "inactive": 3
  },
  "users": {
    "by_role": {
      "garage_owner": 47,
      "garage_admin": 15,
      "mechanic": 120,
      "receptionist": 30,
      "customer": 5000
    },
    "total": 5212
  },
  "customers": {
    "total": 5000  // Total truck owners across all garages
  },
  "repair_orders": {
    "by_status": {
      "draft": 50,
      "quoted": 30,
      "approved": 20,
      "in_progress": 100,
      "completed": 500,
      "paid": 450
    },
    "total": 1150
  },
  "revenue": {
    "total": 2500000.00  // Platform-wide revenue
  }
}
```

## 2. Garage Management (Your Customers)

### List All Garages

```bash
GET /api/v1/admin/tenants
```

Response:
```json
[
  {
    "id": "uuid",
    "name": "Truck Pit Stop Wisconsin",
    "slug": "truck-pit-stop-wi",
    "address": "123 Highway 41, Milwaukee, WI",
    "phone": "(414) 555-0123",
    "email": "service@truckpitstopwi.com",
    "is_active": true,
    "owner_id": "uuid",
    "owner_email": "owner@truckpitstopwi.com",
    "owner_name": "John Smith",
    "owner_phone": "(414) 555-0100",
    "stripe_account_id": "acct_xxxxx",
    "stripe_onboarding_complete": true,
    "created_at": "2024-01-15T00:00:00Z"
  }
]
```

### Onboard New Garage

```bash
POST /api/v1/admin/tenants
Content-Type: application/json

{
  "name": "Texas Truck Repair",
  "slug": "texas-truck-repair",
  "address": "456 Interstate 35, Austin, TX 78701",
  "phone": "(512) 555-0200",
  "email": "service@texastruckrepair.com",
  "owner_email": "owner@texastruckrepair.com",
  "owner_first_name": "Maria",
  "owner_last_name": "Garcia",
  "owner_phone": "(512) 555-0201",
  "owner_password": "SecurePassword123!"
}
```

This creates:
1. New tenant (garage) record
2. GARAGE_OWNER user account (immediately active)
3. Links the owner to the tenant

### View Garage Details

```bash
GET /api/v1/admin/tenants/{tenant_id}
```

### Update Garage

```bash
PUT /api/v1/admin/tenants/{tenant_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "is_active": false,  // Suspend garage
  "stripe_onboarding_complete": true
}
```

### Deactivate Garage

```bash
DELETE /api/v1/admin/tenants/{tenant_id}
```

Soft deletes - sets `is_active` to `false`.

## 3. Garage-Specific Analytics

View detailed stats for a specific garage:

```bash
GET /api/v1/admin/tenants/{tenant_id}/stats
```

Response:
```json
{
  "tenant_id": "uuid",
  "tenant_name": "Truck Pit Stop Wisconsin",
  "is_active": true,
  "users": {
    "by_role": {
      "garage_owner": 1,
      "garage_admin": 2,
      "mechanic": 8,
      "receptionist": 2,
      "customer": 150
    },
    "total": 163
  },
  "customers": {
    "total": 150  // Their truck owner customers
  },
  "repair_orders": {
    "by_status": {
      "in_progress": 12,
      "completed": 50,
      "paid": 45
    },
    "total": 107
  },
  "revenue": {
    "total": 75000.00  // This garage's revenue
  }
}
```

## 4. Mechanic Workforce Timing (Platform Capability)

Garages now have workforce timing controls for mechanic attendance and utilization:

- Attendance: mechanic clock in/out sessions
- Break mode: break start/end sessions linked to attendance
- Work timers: repair-order + misc work timers
- Idle alerting: in-app + SMS when idle threshold is crossed during core hours

### Configuration Model

Garage owners/admins configure workforce defaults per tenant:
- `timezone`
- `default_core_hours_minutes` (default 480)
- `default_shift_start_local` / `default_shift_end_local` (default `08:00`–`18:00`)

Per-mechanic overrides are also supported for:
- core target minutes
- shift start/end

### Important Platform Note

As SUPER_ADMIN, you do not run day-to-day mechanic attendance actions for a garage.  
Garage owner/admin users operate these controls inside their garage dashboard.

## What You CANNOT Do

As SUPER_ADMIN, you **do not have access** to:

❌ Individual garage operations:
- View/edit specific repair orders
- Manage vehicles
- Manage customer details (truck owners)
- View inventory
- Manage mechanics
- Create quotes or invoices

❌ Garage-level dashboards:
- You don't see the garage operator's view
- You can't perform day-to-day garage operations

## Why This Separation?

1. **Scale**: You manage 50+ garages, not 5,000+ truck owners
2. **Privacy**: Garage owners control their customer data
3. **Autonomy**: Each garage operates independently
4. **Security**: Clear separation of concerns
5. **Focus**: You focus on platform health, they focus on repairs

## Login Credentials

**Your Account:**
- Email: `admin@truckpitstop.com`
- Password: `superadmin123`
- Role: `SUPER_ADMIN`
- Tenant: `null` (not tied to any garage)

## API Access

All your endpoints are under `/api/v1/admin/*`

### Authentication

```bash
# Login
POST /api/v1/auth/login
{
  "email": "admin@truckpitstop.com",
  "password": "superadmin123"
}

# Returns JWT token
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "admin@truckpitstop.com",
    "role": "super_admin",
    "tenant_id": null
  }
}

# Use token in subsequent requests
GET /api/v1/admin/tenants
Authorization: Bearer eyJ...
```

## Frontend Routes (Suggested)

Your platform admin interface should have routes like:

```
/platform
  /dashboard          # Platform-wide analytics
  /garages            # List of all garages (your customers)
  /garages/:id        # Detailed view of one garage
  /garages/new        # Onboard new garage
  /analytics          # Advanced platform analytics
  /stripe             # Stripe Connect management
  /settings           # Platform settings
```

You should **NOT** have routes like:
- `/vehicles`
- `/repair-orders`
- `/customers` (truck owners)
- `/inventory`
- `/my-garage`

## Testing Your Access

1. Login as SUPER_ADMIN
2. Try accessing: `GET /api/v1/admin/platform/stats` ✅ Should work
3. Try accessing: `GET /api/v1/repair-orders` ❌ Should return 403 Forbidden
4. Try accessing: `GET /api/v1/vehicles` ❌ Should return 403 Forbidden

## Next Steps

To build your platform admin interface, you'll need:

1. **Dashboard Component**: Shows platform stats
2. **Garages List**: Table of all garages with status, owner, revenue
3. **Garage Detail View**: Deep dive into one garage's performance
4. **Onboarding Form**: Create new garages
5. **Analytics Charts**: Growth, revenue trends, active garages over time

These are all separate from the garage operator interface!
