# Multi-Tenant SaaS Architecture

## Overview

The TruckPitStop application supports a proper multi-tenant SaaS architecture with **complete separation** between platform management and garage operations.

## Role Hierarchy

### Platform Level

- **SUPER_ADMIN** - Platform owner who manages the SaaS business
  - **Manages garages** (your customers)
  - **Platform-wide analytics** and monitoring
  - **Stripe Connect** management for all garages
  - Can create new garages with owner accounts
  - Not tied to any specific tenant
  - **CANNOT access garage-level operations** (vehicles, repair orders, etc.)

### Tenant Level (Per Garage)

- **GARAGE_OWNER** - Owner of a specific garage
  - Full control over their garage
  - Can manage staff, customers, and operations
  - Linked to tenant via `tenant.owner_id`
  - Same permissions as GARAGE_ADMIN but with ownership status

- **GARAGE_ADMIN** - Admin employee at a garage
  - Can manage garage operations
  - Cannot transfer ownership

- **MECHANIC** - Technician working on repairs
  - Can view and work on assigned repair orders
  - Has access to mechanic-specific features

- **RECEPTIONIST** - Front desk staff
  - Can manage customers, appointments, and basic operations

- **CUSTOMER** - Truck owners/operators
  - Can view their own vehicles and repair orders
  - Can request services

## Platform Separation

### SUPER_ADMIN Access (Platform Management)

**✅ Can Access:**
- `/api/v1/admin/*` - All platform management endpoints
- Platform analytics and reporting
- Tenant (garage) management
- Platform-wide Stripe Connect oversight

**❌ Cannot Access:**
- `/api/v1/repair-orders` - Individual repair operations
- `/api/v1/vehicles` - Vehicle management
- `/api/v1/customers` - Customer management (these are truck owners, not your garage customers)
- `/api/v1/inventory` - Inventory management
- `/api/v1/mechanics` - Mechanic management
- `/api/v1/dashboard` - Garage dashboard
- Any garage-level operations

### Garage Owners/Admins (Garage Operations)

**✅ Can Access:**
- All garage-level endpoints for their tenant
- Their garage dashboard
- Their customers, vehicles, repair orders
- Their inventory, services, mechanics

**❌ Cannot Access:**
- `/api/v1/admin/*` - Platform management
- Other garages' data

## Platform Admin Endpoints

All admin endpoints are prefixed with `/api/v1/admin` and require `SUPER_ADMIN` role.

### Tenant Management

```
GET    /api/v1/admin/tenants                    # List all garages
POST   /api/v1/admin/tenants                    # Create new garage with owner
GET    /api/v1/admin/tenants/{tenant_id}        # Get garage details
PUT    /api/v1/admin/tenants/{tenant_id}        # Update garage
DELETE /api/v1/admin/tenants/{tenant_id}        # Deactivate garage
```

### Platform Analytics

```
GET    /api/v1/admin/platform/stats             # Platform-wide statistics
GET    /api/v1/admin/tenants/{tenant_id}/stats  # Tenant-specific statistics
```

## Creating a New Garage

As a SUPER_ADMIN, you can onboard a new garage with:

```bash
POST /api/v1/admin/tenants
{
  "name": "Truck Stop Texas",
  "slug": "truck-stop-tx",
  "address": "123 Main St, Austin, TX",
  "phone": "(512) 555-0100",
  "email": "service@truckstoptx.com",
  "owner_email": "owner@truckstoptx.com",
  "owner_first_name": "John",
  "owner_last_name": "Smith",
  "owner_phone": "(512) 555-0101",
  "owner_password": "securepassword123"
}
```

This will:
1. Create a new tenant (garage)
2. Create a GARAGE_OWNER user account
3. Link the tenant to the owner
4. Both accounts are immediately active and verified

## Test Accounts

### Platform Level
- **Super Admin**: `admin@truckpitstop.com` / `superadmin123`
  - Access: Platform-wide management
  - Dashboard: All garages and analytics

### Garage Level (Truck Pit Stop Wisconsin)
- **Garage Owner**: `truxpitstop@gmail.com` / `BUse@1534`
  - Access: Full control of Wisconsin garage
  - Dashboard: Their garage operations

- **Mechanics, Receptionists, Customers**: See seed_data.py for full list

## Database Changes

### Migration 014
- Added `GARAGE_OWNER` enum value to `UserRole`
- Added `owner_id` column to `tenants` table
- Established ownership relationship between tenants and users

### Models Updated
- `User.tenant` relationship now explicitly uses `foreign_keys=[tenant_id]`
- `Tenant.owner` relationship points to owner user via `owner_id`

## Permission Updates

All endpoints that previously checked for `GARAGE_ADMIN` now also include `GARAGE_OWNER`:
- Customer management
- Vehicle management
- Repair order management
- Inventory management
- Service management
- Mechanic management
- Dashboard analytics
- And more...

## API Documentation

View the full API documentation at:
- **Development**: http://localhost:8000/docs
- Look for the "admin" tag to see all platform management endpoints

## Platform Analytics

### Platform-Wide Stats
```json
{
  "tenants": {
    "total": 5,
    "active": 4,
    "inactive": 1
  },
  "users": {
    "by_role": {
      "super_admin": 1,
      "garage_owner": 4,
      "garage_admin": 2,
      "mechanic": 15,
      "customer": 50
    },
    "total": 72
  },
  "revenue": {
    "total": 125000.00
  }
}
```

### Per-Tenant Stats
Each garage's performance, revenue, customer count, and more.

## Understanding "Customers"

**Important distinction:**

### Platform Level (SUPER_ADMIN)
- **Your "customers"** = The garages/repair shops running on your platform
- You manage **tenants** (garages), not individual truck owners
- You see garage analytics, not individual repair orders

### Garage Level (GARAGE_OWNER/ADMIN)
- **Their "customers"** = Truck owners who bring vehicles for repair
- They manage repair orders, vehicles, and day-to-day operations
- They see customer details, repair history, invoices

## Platform Dashboard Structure

### For SUPER_ADMIN (You)

Your dashboard should show:
```
📊 Platform Analytics
   - Total Garages: 50
   - Active Garages: 47
   - Monthly Revenue: $50,000
   - New Garages This Month: 3

🏢 Garages (Your Customers)
   - Truck Pit Stop Wisconsin
   - Texas Truck Repair
   - California Diesel Service
   - [etc...]

💳 Stripe Connect
   - Connected Accounts
   - Payout Status
   - Platform Fees

⚙️ Platform Settings
   - User Management (garage owners)
   - System Configuration
```

### For GARAGE_OWNER/ADMIN

Their dashboard should show:
```
📊 Garage Analytics
   - Repair Orders: In Progress, Pending
   - Revenue: This Month
   - Mechanics: Available, Busy

👥 Customers (Truck Owners)
   - List of their customers

🚛 Vehicles & Repair Orders
   - Active jobs
   - Pending quotes
```

## Security Considerations

1. **Super Admin Access**: Only platform owners should have SUPER_ADMIN accounts
2. **Strict Separation**: SUPER_ADMIN cannot and should not access garage operations
3. **Garage Owner**: Each garage should have exactly one GARAGE_OWNER
4. **Owner Transfer**: Currently not implemented - would require custom endpoint
5. **Tenant Isolation**: All garage-level data is isolated by `tenant_id`
6. **No Cross-Access**: SUPER_ADMIN manages garages, not their operations

## Future Enhancements

Potential features to consider:
- Garage owner transfer functionality
- Multi-garage ownership (one owner, multiple garages)
- Franchise management features
- White-label customization per tenant
- Tenant-specific pricing plans
- Usage-based billing
- SSO for garage owners
