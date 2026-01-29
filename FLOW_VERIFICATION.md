# Flow Verification Guide

Step-by-step guide to verify the Repair Order flow after recent UI/UX changes.

---

## Prerequisites

1. Backend running (`cd backend && uvicorn app.main:app --reload`)
2. Frontend running (`cd frontend && npm run dev`)
3. At least one mechanic user in the system
4. Some inventory items with stock > 0
5. Some services defined (e.g., "Brake Pad Replacement", "Oil Change")

---

## Complete Repair Order Flow

### Correct Order of Operations:

1. **Staff creates RO** (status: draft)
2. **Staff adds parts/services**
3. **Staff creates quote** (status: quoted)
4. **Staff sends quote to customer** → Email sent
5. **Customer approves quote via portal** (status: approved)
6. **Staff assigns mechanic** (status: in_progress)
7. **Mechanic completes work** (status: completed)
8. **Staff creates invoice** (status: invoiced)
9. **Customer pays** (status: paid)

---

## Test Flow: Create Repair Order with Services

### 1. Create New Repair Order

1. Go to **Repair Orders** page
2. Click **+ New Repair Order**
3. Select or create a customer
4. Select or create a vehicle
5. **Select services** (e.g., "Brake Pad Replacement" - $150)
6. Add optional description
7. Click **Create Repair Order**

**Expected**: RO created, appears in list

---

### 2. Open Repair Order Detail Panel

Click on the newly created RO to open the side panel.

**Verify these sections:**

#### Selected Services Section
- Shows each selected service with its price
- Shows **Labor** line at bottom with total (sum of service prices)
- Labor amount is amber colored

#### Parts Section
- Shows "Select part" dropdown, quantity input, and "Add" button
- All three elements should be **same height**
- No "No parts added" text when empty

#### Labor Section
- **Should NOT appear** when services are selected (services include labor)

#### Mechanic Section
- **DISABLED** until quote is approved by customer
- Shows amber note: "Quote must be approved before assigning a mechanic."
- Dropdown and quick-pick cards are grayed out and not clickable
- After customer approves quote → section becomes active

#### Customer & Vehicle Section
- **Collapsed by default** - shows only customer name
- Click to expand and see:
  - Customer details (name, email)
  - Vehicle details (year, make, model, VIN, plate)

#### Totals Section
- Single line: `Parts $X · Labor $Y · Total $Z`
- Parts = sum of added parts
- Labor = backend labor + services labor
- Total = Parts + Labor

#### Quote Section
- Shows two buttons: **Create** → **Send to customer**
- Arrow between buttons shows flow direction
- "Create" is active, "Send to customer" is grayed out initially
- After clicking "Create":
  - Quote details appear (number, amount, expiry)
  - "Create" becomes disabled
  - "Send to customer" becomes active
- After clicking "Send to customer":
  - Email sent to customer with quote details and portal link
  - Shows "Quote sent to customer. Waiting for approval..." message
  - Button becomes disabled
- **Customer approves via portal** → RO status changes to "approved"
- After customer approval:
  - Shows "Quote approved by customer — ready to assign mechanic."
  - **Mechanic section becomes active**

---

## Test Flow: Customer Approves Quote (Portal)

1. Log in as customer (or check email for portal link)
2. Go to **Customer Portal**
3. Find the repair order with pending quote
4. Click **Approve quote**
5. **Verify**: Quote status changes to approved

---

## Test Flow: Assign Mechanic (After Approval)

1. Open RO that has been approved by customer
2. **Verify**: Mechanic section is now **active**
3. Either:
   - Use dropdown to select mechanic, OR
   - Click a mechanic from quick-pick grid (3 columns, sorted by load)
4. **Verify**: 
   - Mechanic assigned, highlighted with amber border
   - RO status changes to "in_progress"

---

## Test Flow: Create Repair Order WITHOUT Services (Manual Labor)

### 1. Create RO without selecting services

1. Click **+ New Repair Order**
2. Select customer and vehicle
3. **Skip service selection** (leave empty)
4. Add description like "Custom diagnostic work"
5. Click **Create Repair Order**

### 2. Open Detail Panel

**Verify:**

#### Labor Section
- **Should appear** (since no services selected)
- Shows description input (optional)
- Shows hours input
- Shows rate display: `$100/hr` with pencil icon
  - Click pencil to edit rate inline
  - Press Enter or click away to confirm
- Click "Add" to add labor line

---

## Checklist Summary

| Feature | Expected Behavior |
|---------|-------------------|
| Services selected | Labor section hidden, services show labor total |
| No services | Labor section visible with manual entry |
| Labor rate | Shows $100/hr with edit icon, not text input |
| Parts inputs | Same height (dropdown, quantity, button) |
| Mechanic section | **Disabled until customer approves quote** |
| Mechanic note | "Quote must be approved before assigning a mechanic." |
| Mechanic quick pick | 3-column grid, sorted by load, color-coded |
| Customer & Vehicle | Collapsible, collapsed by default |
| Quote buttons | Create → Send to customer |
| Send quote | Emails customer, shows "waiting for approval" |
| Customer approval | Done via portal, unlocks mechanic assignment |
| Totals | Parts + Labor (from services) = Total |
