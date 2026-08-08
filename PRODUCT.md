# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two primary users, weighted equally — and often the same person at a small shop that also runs trucks:

- **Garage owner / admin** — runs the shop cockpit: the work queue, pricing, invoicing, getting paid.
- **Fleet manager** — runs the fleet board: keeping their own trucks rolling through PM, inspections, incidents, and downtime.

Secondary, each with a dedicated app shell: **mechanics** (`/mechanic` — what to work next, time on job, parts used) and **customers** (`/portal` — their trucks and repair history). Seven roles exist in the data model: `super_admin`, `garage_owner`, `garage_admin`, `mechanic`, `receptionist`, `fleet_manager`, `customer`.

## Product Purpose

A multi-tenant system for semi-truck repair garages, covering the whole path from a breakdown request to a paid invoice. Success is a truck that spends less time waiting between people — dispatch, driver, shop, and mechanic all working the same record instead of trading phone calls.

## Positioning

Two mechanisms, and future work must serve both without favoring one:

- **The wedge — one shared breakdown-to-repair thread.** Dispatch, driver, and shop work the same request from first call to closeout. No separate call chains, no disconnected updates while a truck sits.
- **The retention — the shop runs its own fleet inside the same system.** A garage's own trucks are managed at internal cost alongside customer work, with one service history per truck either way.

## Operating Context

- Work happens on the shop floor and in the yard, not only at a desk. The fleet manager is confirmed to use an **iPad, standing, one-handed, next to the truck** — large targets, minimal typing, and portrait layout are functional requirements there, not polish.
- Four app shells serve different situations: `/dashboard` (owner/admin), `/fleet` (fleet manager), `/mechanic` (technician), `/portal` (customer), plus a public marketing site and token-gated quote/invoice pages customers open without an account.
- Money leaves the product through real integrations: Stripe (including Connect) for payment, QuickBooks Online for accounting sync, Twilio for SMS, Resend for email.

## Capabilities and Constraints

- Repair orders, quotes, invoices, payments, inventory and parts, appointments, DOT/periodic inspections, PM scheduling, incidents, messaging, reports, and a fleet board.
- **Tenant isolation is absolute.** Every record is scoped by `tenant_id`; a garage must never see another garage's data.
- **One truck, one service history.** A truck's record is continuous whether the work is customer-billed or internal-fleet; only pricing and the payer change per visit.
- **Fleet work and shop work are the same record, separated by two independent flags.** `is_fleet_work` records provenance (the truck is a fleet vehicle); `is_internal` records pricing (garage labor cost, parts at cost), derived from whether the payer is the shop's own house account. They are orthogonal: a fleet truck's visit can be customer-billed (`is_fleet_work` true, `is_internal` false). There is one `repair_orders` table and one order-number sequence — creating a fleet work order also changes the owner's cockpit queue.
- **Open work outranks manual state.** While a repair order is open, the truck reads as in the shop regardless of any manual status the operator set; the manual status takes over when the order closes. Confirmed 2026-08-08.
- Financial records are protected: once invoiced or paid, an order can no longer be cancelled or deleted.
- Background work (Celery + Redis) and deployment target Railway.

### Settled decisions

- **A fleet manager's orders are defined by `is_internal`, not `is_fleet_work`.** Decided 2026-08-08. The list previously used `is_internal` on the projection path and `is_fleet_work` on the fallback path, so results changed with the code path; `is_internal` is now the single definition. Consequence, accepted deliberately: a fleet truck's **customer-billed** order (`is_fleet_work` true, `is_internal` false) does not appear in a fleet manager's repair order list, while the fleet board still shows that truck as in the shop. Board and list diverge for that case by design. Access checks still use `is_fleet_work OR is_internal` and were not narrowed.
- **The record is a "repair order."** Decided 2026-08-08, resolving the drift where the fleet side said "work order" and the garage side said "repair order". "Repair order" wins everywhere, matching the database, API, and schemas, which already say `repair_order`. Fleet surfaces still carrying "work order" in labels, copy, and component names are legacy to be converged; do not add new "work order" wording.

## Brand Commitments

- The product is **DieselBridge** / **Diesel Bridge Network**. "Truck Pit Stop" is the repository name and the name of a tenant, not the product.
- Logo concept and animation spec live in `docs/brand/`.
- Design handoffs exist and carry incumbent visual truth for their surfaces: `docs/design_handoff_fleet_board/`, `design_handoff_price_builder/`, `design_handoff_customer_portal/`, `design_handoff_analytics/`, `design_handoff_customer_payment/`, `design_handoff_weekly_inspection/`.

## Evidence on Hand

- Real working software with a populated local dataset, including imported EasyTruck service history (`backend/scripts/easytruck_sync/`).
- Shop names appearing in the marketing page and local data: Truck Pit Stop Wisconsin, Del Garage, Spartan Truck Repair.
- **Absences future work must not fabricate:** there are no customer testimonials, case studies, press mentions, published benchmarks, or pricing claims on hand. Do not invent them, and do not present the partner shop names as endorsements.

## Product Principles

1. **Serve the network and the internal fleet equally.** The shared thread wins the shop; the fleet board keeps it. Neither gets to become the second-class surface.
2. **The truck is the record.** Continuity of one truck's history outranks the convenience of any single screen or billing arrangement.
3. **Design for the yard, not the desk.** Where the real usage scene is a tablet in one hand beside a truck, touch size and low typing beat density.
4. **Never claim a state the system won't honor.** If a rule outranks what the operator just did, the interface says so plainly instead of reporting success and showing something else.
5. **Money is a record, not a draft.** Anything that has been invoiced or paid stops being editable, and the interface should make that boundary visible before it is hit.
