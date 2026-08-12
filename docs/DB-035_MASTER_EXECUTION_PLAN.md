# DB-035 Controlled Product Redesign Plan

Status: **Product review — Stage 3 Shop Cockpit candidate**

Accountable owner: Product & Delivery Lead

Implementation baseline: `a7b7fc0879af2b811ccf5c04b224133e6f7e9d0c`

Rejected audit evidence: `5c8c698` (rail and queue rearrangement; not an
accepted product direction)

## 1. Outcome

A tenant who sees DieselBridge's public product preview must enter an
authenticated staff application that is recognizably the same connected
operating system, expanded with real tenant data, permissions, actions and
financial consequences.

The redesign is not a visual skin. It changes information hierarchy,
navigation, responsive composition and task flow while preserving canonical
routes, API contracts, records, permissions, mutations, statuses and audit
consequences.

## 2. Product truth

- **Shop Work** is the real Dashboard Shop Cockpit backed by
  `GET /dashboard/action-queue` and its three canonical projections: Needs
  Action, On the Floor and Ready to Close.
- **Repair Orders** owns selected repair work and its canonical workspace.
  Dashboard may select read-only queue context and deep-link by repair-order ID;
  it does not own repair mutations or a parallel workstation.
- **Customers** owns customer, vehicle, relationship, balance and service
  history context.
- **Invoices** and **Vehicle History** remain authentic embedded surfaces; DB-035
  does not fabricate standalone routes.
- The connected record path is repair order ↔ customer ↔ vehicle ↔ work/labor/
  parts ↔ authorization/history ↔ invoice/payment.

## 3. Explicit anti-goals

- No CSS-only reskin, renamed legacy columns, or large empty composition passed
  off as a redesigned cockpit.
- No presentation-only OperationalWorkstation, invented queue, fake action,
  alternate route, graph API or duplicated domain state.
- No implementation milestone is accepted because tests are green when the
  product outcome is visibly wrong.
- No agent starts an alternate local port when the canonical port is occupied.

## 4. Canonical local development environment

One active DB-035 checkout and one service pair are allowed:

| Service | Canonical address | Rule |
| --- | --- | --- |
| Frontend | `http://127.0.0.1:5173` | Vite `strictPort: true`; collision fails |
| Backend | `http://127.0.0.1:8000` | Uvicorn fails on collision |

The canonical checkout is the DB-035 recovery worktree on
`codex/db035-ux-recovery`. Before starting local development, Product verifies
listeners and stops only confirmed DieselBridge Vite/Uvicorn processes on the
canonical and historical DB-035 ports. Frontend and backend must run from the
same candidate commit. Ports `5174–5178` and `8001` are not DB-035 fallbacks.

## 5. Product selection and visual continuity contract

Product selects **Action Ledger** as the Shop Cockpit topology, with one compact
connected-record strip borrowed from Record Atlas. Record Atlas remains rejected
as the default high-frequency cockpit.

This selection approves interaction structure only. The current all-dark Action
Ledger prototype is not the approved authenticated visual language. Before
production implementation, it must be revised into a direct authenticated
extension of the real public `ProductWorkspace`:

- deep navy remains the product/shell field;
- the active operational workspace is road white, not another dark admin panel;
- the product rail uses the same DieselBridge identity, icon grammar, compact
  labels and selected-state treatment as the public preview, expanded only for
  canonical authenticated destinations;
- copper remains scarce and meaningful: current product context, primary action,
  focus and connected handoff—not generic decoration;
- success/paid uses service green and semantic warning/destructive/financial
  colors remain outside user accent personalization;
- queue rows reuse the compact identity, status, customer, vehicle and amount
  anatomy visible in the public repair-order and Shop Work samples;
- the compact connected-record strip uses the landing evidence vocabulary for
  customer/vehicle, work, authorization/history and invoice/payment while
  remaining read-only on Dashboard;
- Repair Orders expands the same road-white record anatomy into real workspace,
  history, invoice and payment controls instead of switching to an unrelated UI;
- authenticated depth adds real tenant data, permissions, loading/error states,
  stable URLs and mutations; it does not copy the public miniature's floating
  marketing sheets or decorative connector geometry;
- desktop, iPad, 390 and 320 must remain recognizably one product even though the
  authenticated shell uses persistent/compact/mobile navigation appropriate to
  operation.

The isolated prototype packet originally supplied two source-grounded choices:

1. **Action Ledger (recommended):** a fast queue ledger preserving canonical
   queue labels, with read-only connected context and one explicit handoff to
   Repair Orders.
2. **Record Atlas:** a relationship-first view that teaches the connected record
   model but is slower for high-volume shop supervision.

No production implementation begins until Product sees and accepts the revised
landing-derived Action Ledger at desktop and mobile. It must retain visibly
distinct canonical queue identity and never become a Dashboard repair workspace.

## 6. Execution sequence and gates

### Stage 0 — Control and preservation

- Preserve backend/Appearance foundation and accepted Harden commit.
- Preserve rejected commits and screenshots as audit evidence only.
- Freeze the former Frontend task and allow one accountable recovery owner.
- Normalize local ports and candidate checkout.

Exit: one clean baseline, one service pair, one Product plan. **Complete.**

### Stage 1 — Selected prototype correction

- Action Ledger topology and the compact Record Atlas context strip are selected.
- Revise their visual/material system against the actual public ProductWorkspace
  at desktop and mobile.
- Confirm selected-context boundary and transition into Repair Orders.
- Product compares the revised prototype directly with the public product tour.

Exit: explicit Product visual acceptance. No production code. **Complete:
Product approved the corrected landing-derived Action Ledger prototype on
2026-08-12.**

### Stage 2 — Shared authenticated shell

- Implement DieselBridge-primary product identity and subordinate tenant context
  behind the existing tenant/user presentation flag.
- Reuse one router and all existing route/permission ownership.
- Preserve legacy mode as immediate rollback.
- Verify desktop rail, iPad compact navigation and existing mobile navigation.

Exit: focused component tests and one bounded browser pass. Do not run the full
suite repeatedly at this intermediate stage. **Complete: Product accepted the
corrected shared shell at `1bc1cb28d035e8b17a26eccd95a78add69a3b077` on
2026-08-12.**

### Stage 3 — Shop Cockpit

- Implement the approved cockpit using only the three server-backed queue
  projections and existing quick/full order, refresh, Activity and team-capacity
  behavior.
- Add read-only connected context from fields already present in the projection.
- Deep-link to Repair Orders by canonical ID; no Dashboard mutations or detail
  query ownership.
- Cover loading, empty, failure, long values, rapid selection and role states.

Exit: Product visual acceptance plus focused/runtime evidence at 1440, 960, 390
and 320. **Implementation and bounded evidence are complete locally; Product
visual/interaction acceptance remains pending.**

### Stage 4 — Repair Orders workspace

- Recompose the canonical list/workspace so the selected repair order carries
  customer, vehicle, work, authorization/history and invoice/payment context.
- Preserve URL selection, lazy detail/history loading, edit gates, financial
  protection and existing mutations.
- Make the Dashboard → Repair Orders → Dashboard transition preserve real queue
  and selection context.

Exit: focused tests, browser flow and Product acceptance of the complete
Shop Work → Repair Orders experience.

### Stage 5 — Remaining authenticated surfaces

Implement in bounded slices, in this order:

1. Customers and vehicle/history continuity.
2. Messages within the shared shell.
3. My Shop management hierarchy.
4. Settings and Appearance live preview/reset/persistence.

Each slice maps visible regions to existing routes, fields, permissions and
actions before implementation.

### Stage 6 — Adapt, optimize and polish

- Keyboard, screen reader, visible focus, 200% zoom, reduced motion,
  transparency, high contrast, forced colors and coarse pointer.
- Compact/default/comfortable/large density and every curated appearance
  combination.
- Performance, stale-data behavior, interruption, loading/error/empty states,
  long localization-safe content and 44px touch targets.
- One Impeccable/Emil finish pass with one bounded remediation round.

### Stage 7 — Independent gates and release

- Run the full frontend suite and production build once on the complete
  candidate, not after every cosmetic edit.
- Fresh independent QA verifies all changed user journeys and responsive widths.
- Fresh independent Security verifies presentation preference authorization,
  tenant boundaries, cache identity and flag precedence.
- Open one focused PR, require protected CI, then merge/deploy only with explicit
  Product release authority and a rollback/canary plan.

## 7. Delivery controls

- Product & Delivery Lead is the sole normal router and records every state
  transition on `docs/PROJECT_BOARD.md`.
- One accountable implementation owner works from the canonical branch.
- Implementers do not approve their own design, QA or Security gates.
- Product inspects the changed visual outcome at the end of Stages 2–5; automated
  checks cannot substitute for that decision.
- Repeated full-suite runs are prohibited unless a complete candidate, a gate
  failure or a material cross-cutting change warrants them.
- A failed visual direction returns to prototype/Shape, not to another round of
  CSS edits in production files.

## 8. Current decision

**Selected:** Action Ledger + compact connected-record strip.

**Visual direction accepted:** the corrected landing-derived prototype using a
navy product field, road-white operating workspace, compact record anatomy,
sparse copper actions and semantic service green.

**Next gate:** Product reviews the Stage 3 Shop Cockpit at 1440, 960, 390 and
320, including keyboard selection and the projection-only connected-record
handoff. Stage 4 Repair Orders implementation is not authorized until Product
accepts this visual and interaction outcome.
