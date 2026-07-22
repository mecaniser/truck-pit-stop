# Work-First Repair Order Verification

Use this guide to verify the canonical repair-order workflow. Estimates are optional authorization documents; they are not gates for shop work.

## Prerequisites

1. Run the database migrations, including revision `092`.
2. Start the backend and frontend.
3. Have a staff user, a mechanic, a customer with a vehicle, and inventory with available stock.
4. For retryable email verification, run the Celery worker and set `PROVIDER_OUTBOX_ENABLED=true`. With it disabled, invoice email uses the synchronous compatibility path.

## Canonical flow

1. Staff creates a repair order. It appears as **Checked in**.
2. Staff may immediately add services, operations, labor, parts, discounts, notes, and photos.
3. Staff may assign a technician and start work without creating or approving an estimate.
4. The customer sees operational progress, but no live line-item prices or running total.
5. An estimate may be created, sent, approved, declined, or revised without changing the repair order's operational status or locking its live pricing.
6. Technician completion moves the order to **Quality review**.
7. Staff selects **Finalize & Send Invoice**. Finalization locks pricing, captures immutable invoice lines, and sends/publishes the final invoice.
8. The customer can see the final itemized amount and pay it.

## Scenario A: direct work without an estimate

1. Create an order with a customer, vehicle, complaint, and optional services.
2. Confirm that no estimate is created automatically.
3. Open the workspace and confirm the initial label is **Checked in**.
4. Add and edit an operation, labor line, part, and discount.
5. Assign a mechanic immediately.
6. Start work, make another pricing change, and confirm it saves.
7. Complete technician work and confirm the order reaches **Quality review**.
8. Finalize the order and confirm it becomes **Invoiced**.

Expected results:

- Assignment and work are never blocked by missing estimate approval.
- Pricing stays editable through quality review.
- Finalization creates the invoice and changes the pricing lock reason to `invoice_finalized`.
- Editing financial work lines after invoicing is rejected.

## Scenario B: optional estimate

1. From an active order, select **Create estimate**.
2. Send it to the customer and authorize or decline it in the customer portal.
3. Confirm that the repair order keeps its operational state throughout.
4. Continue assigning, starting, and editing the order before and after the estimate response.

Expected results:

- Sending an estimate does not stamp a pricing lock.
- Authorizing or declining an estimate does not move the repair order to `approved` or `declined`.
- The estimate remains an authorization snapshot while the live work record can evolve.

## Scenario C: customer visibility

Inspect the order as the customer while it is checked in, assigned, in progress, and in quality review.

Expected results:

- Operational status and permitted customer-facing updates are visible.
- Internal notes are hidden.
- Live labor/part lines, discounts, and totals are hidden.
- A sent estimate exposes only that estimate and its requested action.
- Final line items and totals appear only after the order is invoiced or paid.

## Scenario D: immutable invoice snapshot

1. Finalize an order containing labor and parts.
2. Download the invoice PDF and record its lines and totals.
3. Resend the invoice and open its public PDF link.
4. Trigger a paid-invoice confirmation email.

Expected results:

- All invoice render paths use the `line_items_snapshot` stored at finalization.
- PDFs, resends, and payment confirmations show identical lines and totals.
- Existing invoices without a snapshot continue to render using legacy live rows as a compatibility fallback.
- Order status, pricing lock, invoice snapshot, and invoice-email outbox record commit together.
- If invoice creation fails, the order remains in quality review, stays unlocked, and has no partial invoice.
- Repeating the manager action cannot create a second invoice.

## Regression checklist

| Area | Expected behavior |
|---|---|
| Intake | Creates a checked-in order, not an automatic estimate |
| Workspace | Operational workflow is primary; estimate is secondary |
| Assignment | Available on active customer orders without approval |
| Work editing | Allowed from checked in through quality review |
| Customer portal | No unpublished financials on active work |
| Estimate | Optional and independent of operational status |
| Finalization | Atomically locks pricing, snapshots invoice lines, and moves to invoiced |
| Invoice delivery | Retryable outbox when enabled; all render paths use the snapshot |
| Payment | Paid state and confirmation retain the finalized invoice content |
