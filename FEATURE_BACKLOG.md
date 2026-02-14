# TruckPitStop Feature Backlog

Features identified from competitor analysis (Fullbay, Easy Truck Shop), with implementation status tracked below.

---

## High Priority (Revenue/Efficiency Impact)

### Reporting & Analytics

| Feature | Description | Competitor | Complexity | Value | Dependencies |
|---------|-------------|------------|------------|-------|--------------|
| Service Profitability Reports | Margin analysis per service type showing revenue vs cost | Fullbay, ETS | Medium | High | Services, Labor data |
| Labor Efficiency Reports | Compare estimated hours vs actual hours per job | Fullbay, ETS | Low | High | `work_started_at`, `work_completed_at` (implemented) |
| Parts Revenue/Cost Analysis | Track parts markup, cost trends, and revenue by category | Fullbay, ETS | Medium | High | Inventory module |
| Technician Productivity Metrics | Jobs completed, hours worked, efficiency rating per mechanic | ETS | Medium | High | Mechanic assignments |
| Revenue Trend Charts | Time-series charts with projections and comparisons | Fullbay, ETS | Medium | High | Invoice/Payment data |

### Inventory Enhancements

| Feature | Description | Competitor | Complexity | Value | Dependencies |
|---------|-------------|------------|------------|-------|--------------|
| Multi-Location Inventory | Track parts across multiple warehouse/shop locations | Fullbay | High | High | Schema changes |
| Automated Reorder Alerts | Email/SMS notifications when stock hits reorder threshold | Fullbay, ETS | Low | High | Twilio, Resend (implemented) |
| Vendor Ordering Integration | Generate and send POs directly to suppliers | Fullbay | High | Medium | Supplier module |
| Parts Markup Calculator | Tool to determine ideal gross profit and markup % | Fullbay | Low | Medium | None |
| QR Code Scanning | Scan QR/barcodes for quick part lookup and inventory updates | ETS | Medium | Medium | Mobile camera API |

### QuickBooks Integration

| Feature | Description | Competitor | Complexity | Value | Dependencies |
|---------|-------------|------------|------------|-------|--------------|
| Invoice Sync | Automatically sync invoices to QuickBooks Online | Fullbay, ETS | High | High | QuickBooks API |
| Automated Bookkeeping | Sync payments, expenses, and journal entries | Fullbay | High | High | QuickBooks API |
| Purchase Order Sync | Sync PO history for expense tracking | Fullbay | Medium | Medium | Vendor ordering feature |

---

## Medium Priority (Customer Experience)

### Zelle Payment Enhancement

| Feature | Description | Complexity | Value | Status |
|---------|-------------|------------|-------|--------|
| QR Code Upload & Display | Garage uploads their Zelle QR image, displayed when staff selects Zelle payment | Low | High | **Implemented** |
| Walk-in Customer Capture | When recording Zelle payment from unknown customer, staff can capture sender email/phone (seen in bank notification) and enrich the customer profile | Low | High | **Implemented** |
| Customer Source Tracking | Mark customers created from walk-in/Zelle flows with `source` metadata for later enrichment/reporting | Low | Medium | **Implemented** |

**Walk-in Zelle Customer Flow:**
1. Walk-in customer gets repair done (no existing customer record, or placeholder)
2. Customer pays via Zelle → shop receives bank notification showing sender's email/phone
3. Staff records Zelle payment → prompted to enter sender's Zelle info
4. Walk-in customer record is enriched with sender contact info and tagged with `source = "zelle"`
5. Customer returns later → staff can add truck/trailer details to complete profile

**Implementation Steps:**
1. ~~Add `zelle_qr_image_url` field to Tenant model (migration)~~ ✓
2. ~~Update Garage Settings page to allow QR image upload~~ ✓
3. ~~Display QR image in Zelle payment modal on repair orders~~ ✓
4. ~~Add `source` field to Customer model (migration) — for "zelle", "walk-in", "portal", etc.~~ ✓
5. ~~Add quick customer capture fields when recording Zelle payment for unknown customer~~ ✓
6. ~~Show customer source badge on profile, prompt to complete partial records~~ ✓

---

### 2-Way Texting

| Feature | Description | Competitor | Complexity | Value | Status |
|---------|-------------|------------|------------|-------|--------|
| Receive Customer Texts | Inbound SMS handling with Twilio signature validation and idempotency | Fullbay | Medium | High | **Implemented (v1)** |
| Text Thread View | Staff thread UI with cursor pagination and real-time updates | Fullbay | Medium | High | **Implemented (v1)** |
| Conversation Dashboard | Shared staff inbox with reply + new outbound compose flow | Fullbay | Medium | Medium | **Implemented (v1)** |
| Opt-out Compliance | STOP/START handling, persisted customer opt-out flags, pre-send enforcement | Fullbay | Medium | High | **Implemented (v1)** |
| Delivery Tracking | Twilio status callback mapped to explicit delivery states | Fullbay | Medium | Medium | **Implemented (v1)** |

**Implemented in v1 (Feb 2026):**
- New persistence layer for `message_threads` and `sms_messages` with Twilio SID uniqueness for webhook idempotency.
- Per-tenant SMS number support (`tenant.sms_phone_number`, `tenant.sms_phone_sid`, `tenant.sms_enabled`) with Super Admin provisioning endpoint.
- Super Admin manual attach flow for existing Twilio numbers by SID (with optional webhook auto-configuration and replace safeguards).
- Public Twilio webhook endpoints:
  `POST /api/v1/webhooks/twilio/sms/inbound`
  `POST /api/v1/webhooks/twilio/sms/status`
- Staff messaging endpoints:
  `GET /api/v1/messages/threads`
  `GET /api/v1/messages/threads/{thread_id}/messages`
  `POST /api/v1/messages/send`
  `POST /api/v1/messages/threads/new`
- `POST /messages/send` rate limit at tenant scope (`30/min`) to reduce accidental spam.
- Customer consent fields added:
  `sms_opt_out`, `sms_opted_out_at`, `sms_opt_out_source`.
- Automated customer-facing SMS now flows into thread history (`source=automated`) for unified timeline visibility.

**Still in backlog (future enhancements):**
- MMS/media attachments and image/video rendering in threads.
- Assignment/ownership and SLA workflow per conversation.
- AI triage/intent routing and canned automation playbooks.
- Customer portal two-way chat surface (currently staff inbox only).

### Customer Portal Enhancements

| Feature | Description | Competitor | Complexity | Value | Dependencies |
|---------|-------------|------------|------------|-------|--------------|
| Repair Status with Photos | Real-time status updates with technician photos/notes | Fullbay | Medium | High | File upload, storage |
| Invoice History | View and download past invoices in portal | ETS | Low | Medium | Invoice module |
| PM Schedule Visibility | Show upcoming preventive maintenance for customer vehicles | Fullbay | Medium | Medium | PM scheduling feature |

### Fleet Management

| Feature | Description | Competitor | Complexity | Value | Dependencies |
|---------|-------------|------------|------------|-------|--------------|
| Fleet Customer Accounts | Group multiple vehicles under one fleet/company | Fullbay, ETS | Medium | High | Customer schema changes |
| PM Schedule Tracking | Per-vehicle preventive maintenance schedules and alerts | Fullbay | Medium | High | Vehicle module |
| Fleet-Wide Reporting | Aggregate reports across all fleet vehicles | Fullbay | Medium | Medium | Fleet accounts |

---

## Lower Priority (Nice to Have)

### AI Features

| Feature | Description | Competitor | Complexity | Value | Dependencies |
|---------|-------------|------------|------------|-------|--------------|
| AI Service Notes Cleanup | Clean up and professionalize technician notes | Fullbay | Medium | Medium | LLM API (OpenAI) |
| Voice-to-Text Notes | Transcribe voice memos to text for service orders | Fullbay | Medium | Medium | Speech API |
| Smart Parts Suggestions | AI-powered parts cross-reference recommendations | Fullbay | High | Low | Parts database |

### External Integrations

| Feature | Description | Competitor | Complexity | Value | Dependencies |
|---------|-------------|------------|------------|-------|--------------|
| MOTOR Labor Guides | Access labor times, wiring diagrams, parts cross-ref | Fullbay | High | Medium | MOTOR API subscription |
| VIN Decoder Tool | Decode VIN for vehicle details auto-fill | Fullbay | Low | Medium | NHTSA API (free) (implemented) |
| FleetNet Integration | Receive emergency repair requests from FleetNet | Fullbay | High | Low | FleetNet partnership |
| Whip Around DVIR | Auto-create service requests from inspection defects | Fullbay | High | Low | Whip Around API |

### Marketing Tools

| Feature | Description | Competitor | Complexity | Value | Dependencies |
|---------|-------------|------------|------------|-------|--------------|
| Review Collection | Automated post-repair review requests | Fullbay | Low | Medium | Email/SMS templates |
| Follow-Up Messages | Automated check-in messages after repairs | Fullbay | Low | Low | Notification system |

---

## Already Implemented (Sprint Completed)

These features were identified from competitor analysis and have been built:

### Core Workflow
- Per-job time tracking (`work_started_at`, `work_completed_at`)
- Live timer in mechanic portal
- Mechanic Timer V1.1: attendance clock in/out, break mode, flex tracking, idle alerts, manager controls
- Mechanic Timer V1.2: focus-mode mechanic UX, attendance-based core countdown, manager next-action recommendations
- Auto-approval thresholds for customers
- SMS quote notifications with approval links
- Quote decline workflow with shop notifications
- Declined quote status and dashboard alerts
- Customer portal with quote approval/decline
- Walk-in customer flow with account linking
- Two-way SMS shared inbox (Twilio-backed) with compliance controls and delivery tracking
- Super Admin can provision new SMS numbers or manually attach existing Twilio numbers to a garage

### Payment Options (Feb 2026)
- **Cash payments** - Staff can mark invoices as paid with cash
- **Zelle payments** - Manual payment recording, email/phone config in garage settings
- **Zelle QR upload/display** - Garage uploads QR in settings; staff can show QR in repair order payment modal
- **Zelle walk-in capture** - Staff can capture sender email/phone during Zelle payment and enrich walk-in customer profiles
- **Check/ACH payments** - Manual payment recording for all methods
- **Invoice due dates** - Set due date when creating invoice, track overdue

### Vehicle Management (Feb 2026)
- **Unit number field** - Fleet/company unit identifier for trucks
- **Vehicle repair history** - Click on vehicle to see all repair orders and mechanics who worked on it
- **Nested vehicle endpoints** - Vehicles managed under customers (`/customers/{id}/vehicles`)
- **VIN decoder integration** - Decode VIN in customer and vehicle forms using NHTSA vPIC API
- **Initial truck on customer creation** - Create customer with first vehicle in one flow, with explicit no-truck option

---

## Platform Growth Features

### Garage Enrollment (Feb 2026 - Implemented)
- **Self-service enrollment** - Public `/enroll` page for garage owners to apply
- **Multi-step form** - Garage info, business details, owner account
- **Admin approval workflow** - Super admins review and approve/reject applications
- **Email notifications** - Confirmation to applicant, notification to admins
- **Pending enrollments dashboard** - Super admin view with approve/reject actions

### Pricing & Subscriptions (Planned)

| Feature | Description | Complexity | Value | Dependencies |
|---------|-------------|------------|-------|--------------|
| Pricing Tiers | Multiple subscription levels (Free, Pro, Enterprise) | Medium | High | Stripe Billing |
| Tier Selection at Enrollment | Choose plan during garage signup | Low | High | Pricing tiers |
| Usage-Based Billing | Charge based on repair orders, users, or features | High | Medium | Stripe Metered Billing |
| Trial Period | 14-30 day free trial for new garages | Low | High | Pricing tiers |
| Plan Upgrade/Downgrade | Self-service plan changes in garage settings | Medium | Medium | Stripe Customer Portal |
| Feature Gating | Restrict features based on subscription tier | Medium | High | Pricing tiers |
| Billing Dashboard | View invoices, payment history, update payment method | Low | Medium | Stripe Customer Portal |

---

## Implementation Notes

### Quick Wins (Low complexity, High value)
1. **Parts Markup Calculator** - Simple utility tool
2. **Invoice History in Portal** - Invoice data exists

### Strategic Investments (High complexity, High value)
1. **QuickBooks Integration** - Major accounting workflow improvement
2. **2-Way Texting** - Significant customer communication upgrade
3. **Fleet Management** - Opens B2B market segment
4. **Multi-Location Inventory** - Scales for larger operations

---

*Last updated: February 13, 2026*
*Based on analysis of Fullbay and Easy Truck Shop platforms*
