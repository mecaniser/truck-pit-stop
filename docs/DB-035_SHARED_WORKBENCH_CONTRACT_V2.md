# DB-035 Shared Daily Workbench Contract v2

Status: **Architecture GO — shared daily-workbench implementation authorized**

Board ID: DB-035A

Architecture decision owner: Architecture & API Contracts

Implementation owner: Frontend & UX Recovery Owner

This amendment supersedes only the **transition-only** Shop Work → Repair
Orders topology recorded in the earlier DB-035 presentation contract. It does
not invalidate the accepted shell, legacy rollback, existing routes, domain
ownership, previous evidence, or the historical Stage 3/4 records.

## 1. Product decision

DieselBridge will expose **one connected repair-order workbench with two entry
scopes**, rather than making Shop Work a short-lived handoff screen.

| Entry | Operator intent | Initial navigator scope | Selected workspace |
| --- | --- | --- | --- |
| Shop Work (`/dashboard`) | Run today's active work | Needs Attention, On the Floor, Closeout | The existing canonical Repair Orders workspace |
| Repair Orders (`/dashboard/repair-orders`) | Find, review, and work any repair order | All Repair Orders | The same existing canonical Repair Orders workspace |

The selected repair order remains open while the operator works. Selecting a
queue row must not force a route hop from Shop Work to Repair Orders, and it
must not create a Dashboard-owned repair workspace. The queue is a navigator;
the selected repair order is the canonical operating surface.

### 1.1 Daily workset language

- **Needs Attention**: the existing server-backed attention projection.
- **On the Floor**: the existing server-backed active-work projection.
- **Closeout**: daily finishing work, split only when source-backed:
  - **Ready to close**: open completed/invoiced work that still needs a final
    operational or financial action.
  - **Closed today**: work with a canonical paid event during the current
    tenant-local business day. It stays visible through that business day and
    leaves the daily workset at the next tenant-local midnight.
- **All Repair Orders**: the canonical paginated repair-order ledger, including
  historical work, direct lookup, and records outside the daily workset.
- **Activity**: the existing authentic activity view; it is not an invented
  workflow stage.

Open attention, on-floor, and ready-to-close records do not disappear at
midnight. Only the `Closed today` membership is date-bounded. Permanent record
history remains in All Repair Orders and in the existing contextual history,
invoice, and payment surfaces.

## 2. Hard boundaries

### 2.1 Ownership

| Concern | Owner | Contract rule |
| --- | --- | --- |
| Daily queue membership | Dashboard queue service | Server-provided, tenant-scoped projections only; no browser-created queue or status derivation. |
| Queue navigator rendering | Shared presentation component | May render compact queue fields and selection state; it owns no repair-order mutation or detail query. |
| Selected record, customer/vehicle, labor/parts, authorization/history, invoice/payment, dialogs, and mutations | Repair Orders feature | Reused as the one canonical selected-record workspace in both entry scopes. |
| Quick/full order, Refresh, Activity, and team-capacity affordances | Existing Dashboard behavior | Retain their existing permissions, routes, side effects, and WebSocket behavior. They are available only where currently authorized. |
| URLs and history | Existing router | Preserve current physical routes and query compatibility; no redirect is required to select a record. |

The workbench must not display a second handoff banner, connected-record strip,
return CTA, or summary header that repeats the order number, customer, vehicle,
status, work, labor, or payment state already presented by the selected
canonical workspace.

### 2.2 Existing routes and query compatibility

| URL | Required behavior after this amendment |
| --- | --- |
| `/dashboard` | Opens Shop Work in daily-workset scope. A selected daily record is represented by the existing `selected` ID plus its canonical `queue` lane. |
| `/dashboard/repair-orders` | Opens the same workbench in All Repair Orders scope. |
| `/dashboard/repair-orders?selected={real_id}&queue={needs_action\|on_floor\|ready_to_close}` | Remains valid without redirect. It opens that selected canonical record with its originating daily lane available in the navigator. |
| `/dashboard/repair-orders?selected={real_id}` | Remains a direct all-records selection. |
| `/dashboard/repair-orders?new=true` | Keeps its current create-order behavior. |

The daily route may use the existing `selected` and `queue` keys, but it must
not create an incompatible route, change IDs, or silently discard an existing
deep link. Clearing a selection preserves its scope and list position. Browser
Back returns to the prior URL state; it is not repurposed as a synthetic
"return to queue" control.

### 2.3 Legacy rollback and security

- This work is behind the existing new-presentation flag only. Flag-off
  rendering, labels, router behavior, Sidekick behavior, permissions, and
  business consequences remain unchanged.
- Existing principal resolution, tenant selection, feature-flag precedence,
  Appearance hydration/cache behavior, and notifications remain authoritative.
- Every queue and selected-record request continues to be resolved from the
  authenticated tenant principal. An absent, foreign, deleted, or unauthorized
  selected ID must retain the existing generic failure semantics and must not
  reveal cross-tenant existence.
- No mutation is added to the queue navigator. Existing Repair Orders
  permission/status/financial protections remain the sole mutation gates.

## 3. Data contract and daily boundary

### 3.1 Current source proof

`GET /dashboard/action-queue` currently returns only these bounded canonical
arrays:

```ts
{
  orders_needing_action: ActionQueueOrder[]
  orders_needing_action_has_more: boolean
  orders_on_floor: ActionQueueOrder[]
  orders_on_floor_has_more: boolean
  orders_ready_to_close: ActionQueueOrder[]
  orders_ready_to_close_has_more: boolean
}
```

Its current projections cover:

- Needs Action: draft, quoted, declined, pending review, plus the existing
  pending-Zelle exception.
- On the Floor: approved, assigned, acknowledged, and in progress.
- Ready to Close: completed and invoiced, excluding paid and cancelled invoices.

The projection includes `updated_at`, but it does **not** include a paid event
timestamp or `closed today` membership. `updated_at` is not an acceptable proxy
for payment or closeout timing.

### 3.2 Architecture decision — GO

Add **`GET /dashboard/daily-workset`** as a new tenant-scoped, read-only
projection. The existing `GET /dashboard/action-queue` remains byte-compatible
and keeps its three canonical lanes for legacy presentation and existing
clients. This avoids changing a bounded, established dashboard contract solely
to support the new presentation.

`daily-workset` provides:

```ts
type DailyWorkbenchResponse = {
  timezone: string                 // resolved tenant timezone
  business_date: string            // YYYY-MM-DD in that timezone
  next_reset_at: string            // UTC instant for the next local midnight
  needs_attention: QueueSlice
  on_floor: QueueSlice
  ready_to_close: QueueSlice
  closed_today: QueueSlice         // paid event inside [local midnight, next local midnight)
}

type QueueSlice = {
  items: DailyWorkbenchOrder[]
  has_more: boolean
}

type DailyWorkbenchOrder = ActionQueueOrder & {
  paid_at: string | null // populated only when a canonical paid event exists
}
```

`closed_today` membership must be calculated server-side from the canonical
invoice/payment paid timestamp, scoped by tenant, using the half-open local-day
window `[midnight, next_midnight)`. It is a query-time membership calculation,
not a midnight job that mutates repair orders or invoices. Paid records without
a trustworthy `paid_at` are excluded from `closed_today`; they remain in the
canonical all-record ledger and are never guessed into the day.

The endpoint resolves `Tenant.timezone` through IANA `ZoneInfo`. A missing or
invalid persisted value falls back to the existing product default
`America/New_York`; the response reports the resolved timezone. `business_date`
and `next_reset_at` are generated server-side from that resolved zone.

### 3.3 Authorization, errors, cache, and concurrency

- Read access uses the existing authenticated staff Dashboard authority and
  tenant principal. A user with no active tenant receives the existing empty
  queue behavior; unauthenticated behavior remains the existing auth failure.
- The endpoint is read-only and has no idempotency or mutation side effect.
- A response is always computed for the server's resolved tenant timezone. The
  browser may render `next_reset_at`, but it must not calculate its own local
  business date or move records between worksets.
- The shared cache identity includes the authenticated tenant and the daily
  projection key. Existing `dashboard-action-queue`, `repair-orders`,
  repair-order detail/workspace, invoice, payment, and activity invalidations
  remain active. The new daily query is invalidated by the same repair-order,
  quote, invoice, payment, and relevant mechanic events, and refetched after
  `next_reset_at`.
- Selection is latest-request-wins. Changing records cancels the outgoing
  selected record's lazy queries exactly as the current Repair Orders workspace
  does; stale responses cannot replace the most recently selected ID.

### 3.4 Fixtures required by Architecture

The shared test fixture must include one tenant with an explicit IANA timezone,
at least one record in every existing lane, one paid invoice just before and one
just after the tenant-local midnight boundary, a historical paid order, and an
unauthorized/foreign selected ID. It must exercise daylight-saving transitions
for the configured timezone. No production customer or payment data is used.

## 4. Interaction and responsive contract

### 4.1 Desktop (1280px and above)

- One operating canvas contains a compact scope row, independently scrollable
  navigator, and the selected canonical repair-order workspace.
- The navigator shows scan-level information only: order number, status, work
  summary, amount, and internal marker where already canonical. Customer and
  vehicle identity remain in the selected workspace during scanning to avoid
  duplicate context. An operator may disclose one inline, read-only order brief
  for comparison. That brief is derived only from the already-loaded ledger
  projection and can expose its existing customer, vehicle, work, technician,
  hold, estimate, update, and total fields; it neither requests more data nor
  changes the selected record, URL, or history.
- The brief excludes authorization, history, invoice, payment, and mutation
  controls. Selecting the record body opens the canonical selected repair
  order; **Details** itself never does. The brief provides a secondary explicit
  **Open repair order** control for that same selection action.
- The selected row uses a rounded inset selection cue. Keyboard focus is visible
  on the focused control or selected workspace heading, never as a rectangular
  frame around the entire workbench.
- The navigator has its own visible scroll region. Its parent cannot clip the
  selected-row cue, focus outline, or workspace elevation.

### 4.2 Compact desktop and iPad (960–1279px)

- Keep a stable selected record and a compact, independently scrollable
  navigator. Controls wrap or collapse by priority without hiding status,
  search, selection, or the canonical next action.
- Scope controls are operable with keyboard and touch; no fixed, clipped quick
  filter rail or browser-native menu may overlap the search field.

### 4.3 Mobile (390px and 320px)

- Present one task layer at a time: scoped list, then selected canonical
  workspace. Closing or browser-Back returns to the same scope, selection
  context, filter, and useful scroll position.
- No duplicate route, hidden off-canvas action, horizontal page overflow, or
  44px-underflow is allowed. Existing dialogs and keyboard behavior remain
  accessible.

### 4.4 Operator flows

```text
Daily scope → select canonical order → work, authorize, invoice, or record payment
          ↘ select next daily order without leaving the workbench

All Repair Orders → search/filter → select canonical order → same workspace

At tenant-local midnight → Closed today leaves daily scope; all permanent records remain searchable
```

## 5. Implementation slices

1. **Daily workset endpoint and fixtures**
   - Add the additive, tenant-scoped projection with a server-calculated local
     day boundary, paid-timestamp rule, timezone fallback, and focused
     deterministic fixtures. No client inference or schema/data mutation.
2. **Shared frontend extraction behind the existing flag**
   - Extract a route-neutral Repair Orders navigator/workspace composition from
     the current `RepairOrdersPage` without duplicating hooks, mutations, or
     selected-record state.
   - Make `/dashboard` host daily scope and `/dashboard/repair-orders` host all
     scope through that shared composition.
3. **Daily workset wiring**
   - Consume the Architecture-approved server projection. Preserve the existing
     dashboard activity, refresh, quick/full-order, capacity, URL, and WebSocket
     behavior.
4. **Responsive and accessibility completion**
   - Verify 1440, 1280, 960, 390, and 320; keyboard, focus, rapid selection,
     reduced motion, forced colors, 200% zoom, long values, empty/error/loading,
     role restriction, and cross-tenant selected-ID denial.
5. **Independent gates**
   - Product visual/interaction review, independent QA, independent Security for
     selected-ID and tenant boundaries, then release review. No self-approval.

## 6. Acceptance criteria for implementation

- Shop Work becomes a daily operating workbench, not a transition page.
- Repair Orders remains the all-record search/direct-access entry, using the
  same canonical selected workspace rather than a competing product.
- A selected queue record remains usable without navigating to a different page
  solely to access its workspace.
- No duplicate handoff context, return CTA, All Orders noise, or repeated
  customer/vehicle/order/work facts appears beside the selected record.
- Existing physical routes, selected IDs, `queue` compatibility, `?new=true`,
  permissions, APIs, status transitions, financial protections, mutations,
  dialogs, lazy loading, and WebSocket invalidation remain intact.
- `Closed today` is accurate to the resolved tenant-local date and uses a
  canonical paid timestamp; it never derives from `updated_at`.
- Legacy presentation remains an immediate rollback with its existing behavior.
- Focused unit/component tests, production build, changed-file lint/diff,
  deterministic browser fixtures, and independent runtime/security evidence
  meet the DB-035 gate before release.

## 7. Current constraints and non-goals

- No migration, data backfill, deployment, PR, or release is authorized by this
  document.
- The existing action queue remains unchanged and cannot itself truthfully
  implement `Closed today`; the additive daily-workset endpoint owns that data.
- The current local WorkOS/database issue blocks live authenticated evidence; it
  is not an excuse to weaken authentication or claim runtime acceptance.
- Customers, Messages, My Shop, Settings, and any standalone Invoice or Vehicle
  History route remain outside this amendment.

## 8. Contract handoff record

Board ID: DB-035A

From / To: Architecture & API Contracts / Frontend & UX Recovery Owner

User outcome: Let a shop operate continuously within one canonical
repair-order workbench: daily worksets in Shop Work and all-record discovery in
Repair Orders, without a redundant route hop or duplicate record context.

Scope completed: Product decision, source audit, ownership ledger, route
compatibility rules, daily-boundary requirement, implementation slices,
acceptance criteria, and Architecture GO are recorded in this contract.

Scope explicitly not completed: Daily-workset endpoint implementation, shared
frontend extraction, QA/Security review, authenticated browser evidence, PR,
merge, and deployment.

Contract or migration impact: Additive `GET /dashboard/daily-workset` API only;
no mutation, migration, or data backfill.

Acceptance evidence: Current `GET /dashboard/action-queue` source proves the
three existing projections and does not expose paid-today membership.
`Tenant.timezone` is an IANA source with an `America/New_York` default; both
Stripe and manual-payment finalization atomically persist `Invoice.paid_at` and
the paid repair-order state. Current Repair Orders source proves the canonical
selected workspace and existing `?selected`/`?queue` compatibility path.

Known failures / risks: Daily queue lanes are intentionally bounded and must
retain their `has_more` semantics. Live authenticated browser review remains
blocked by the local WorkOS/DB condition.

Branch / PR / environment: `codex/db035-ux-recovery`; no PR or deployment; no
application service was changed by this documentation amendment.

Next required action: Implement the additive endpoint and shared workbench
behind the existing presentation flag, then hand off exact evidence for
independent QA and Security.

Return condition: Product reviews the source-grounded shared daily workbench;
independent QA and Security must still gate any release.
