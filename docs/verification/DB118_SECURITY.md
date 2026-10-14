# DB118 independent security and privacy gate

Reviewer: Security & Identity, independent of implementation and contract design.
Review date: 2026-10-14. Scope: operation-specific shop notes only.

## Final decision: GO for the reviewed security scope

The three initial client privacy findings below are resolved in the reviewed
working tree on `codex/operation-shop-notes`. No remaining blocking security
finding was identified. This gate does not replace independent workflow QA,
protected CI, deployment evidence or production desktop/mobile acceptance.

## Initial findings returned to the owner — resolved

The backend boundary is structurally sound: a positive garage-owner/admin,
receptionist and mechanic allowlist; tenant/order/labor identity checks; current
mechanic assignment; tenant advisory lock before order/labor row locks; lifecycle
checks; exact authorized UUID replay; savepoint handling for global key collisions;
and no note-body broadcast. Notes render as literal text. The schema rejects
client-supplied identity, audience, author and timestamps. Existing order-note and
authorization routes retain explicit event-type allowlists.

The reviewer returned these new-feature privacy findings to the owner:

1. Full-detail history now contains shop-only note bodies, but the existing
   `RepairOrdersPage` detail cache is keyed only by order ID. It can survive SPA
   account/tenant changes, and history has no positive shop-note presentation
   guard. Scope this history-bearing cache to authenticated identity and retain
   order-prefix invalidation; filter the new event for unsupported roles.
2. The same issue is reachable in fleet history: owner/admin may open `/fleet`
   and populate `fleet-ro-detail` with authorized shop notes, then SPA logout and
   fleet-manager login can reuse that cache while the replacement request is slow
   or fails. `FleetPriceBuilderPanel` renders every cached history event. Scope
   the detail cache and filter the new event for denied roles.
3. `OperationNotes` retains and renders the last successful collection after a
   refetch returns 403/404. Current access denial must hide the cached collection
   and prevent submission. A transient network error may retain previously
   authorized data with an error, but an explicit authorization/not-found denial
   must not be presented as an ordinary refresh failure.

These findings concern the newly added private operation note. They do not call
for a broad cleanup of unrelated legacy fields or caches.

## Projection review

The application has one full-detail history serializer. Its new positive
`operation_notes.visible_history` filter runs before response serialization.
Customer, fleet-manager, driver and super-admin events are omitted entirely;
mechanics are restricted to active, same-order, non-sublet operations within their
current scope. Staff may retain history for physically removed labor. Dedicated
GET/POST reject deleted orders and removed labor.

Order-level notes and authorization history explicitly exclude the new event.
Customer/vehicle history, repair-order read models, invoice/quote/PDF/email paths
do not read this event table outside those reviewed serializers. The append route
does not copy the body to an order/invoice field or broadcast. Customer-only
detail consumers use separate query prefixes and do not render history; the two
staff-capable history caches above are the affected client boundaries.

## Remediation reassessment and evidence

- `scopedOrderDetailKey` now partitions both dashboard and fleet full-detail
  caches by tenant, user, role and authentication-session epoch. The existing
  order-ID prefix remains intact for invalidation. Both dashboard cache writes
  use the scoped key; deletion/restoration clear all matching variants.
- Dashboard history additionally applies a positive role filter to the new
  event and hides it on a failed detail refresh. Fleet history excludes the
  new event altogether, including when an owner visits the fleet presentation.
- `OperationNotes` hides cached bodies, authors and counts after a failed
  refresh. Submission stays disabled while the read is failed/fetching. Drafts
  remain scoped to the authenticated operation identity.
- Independently ran
  `backend/venv/bin/python -m pytest tests/test_operation_notes.py -q` using the
  established root-checkout Python environment with the implementation backend
  as working directory: **39 passed in 11.97 seconds**. This includes HTTP
  schema/replay behavior, all denied roles, tenant/operation identity, current
  mechanic scope, frozen/deleted/removed states, unrelated-field stability,
  customer/authorization/invoice/quote exclusions and staff history retention.
- Reviewed owner-run `/tmp/db118-backend-focused.log`: **140 passed** across
  notes, operation execution and staff-hold coverage. Reviewed
  `/tmp/db118-postgres-tests.log`: **8 passed**, including same-key contention,
  competing lifecycle/assignment/removal changes, finalization after a saved
  note, and a real cross-tenant primary-key race that preserves the outer
  transaction. `/tmp/db118-history-scope.log` passes the strengthened removed,
  sublet and helper-history projection check.
- Reviewed `/tmp/db118-frontend-privacy.log`: **22 passed** across operation
  notes, session-partition privacy and deleted-order workspace tests. The
  populated-cache-to-403 case hides note body and author; both history queries
  drop the former session's private body while another account response is
  pending, including a new session for the same user and role.
- `git diff --check` passed. Test output includes existing deprecation warnings
  and React test `act` warnings; no failed assertion. No application/test code,
  browser state, local runtime configuration or production data was changed by
  this reviewer. Only this gate document was written.

## Release conditions

This document is not a runtime or production-acceptance claim. Independent QA
and Release must complete the remaining browser and protected release gates.
Material changes to the reviewed authorization, serializer or cache boundaries
require reassessment.

Rollback must retain the `operation_note_shop` privacy filter and the protected
client history boundaries. An older serializer does not recognize this event
type and must not be redeployed unchanged after note rows exist. No migration,
provider, external notification or data-backfill change is present.

## PR519 final memoization re-review

Security GO remains valid after reviewing the application diff against
`eab4b247`. The only application change is in `RepairOrdersPage`: its selected
detail key is now memoized from scalar order ID, tenant ID, user ID, role and
session epoch. The tuple values and their order exactly match the previously
reviewed scoped key. The workspace-to-detail write remains guarded by matching
workspace/selected order IDs and targets the same memoized tuple as the query.
Removing the whole user-object reference from the effect dependency list does
not remove an authorization dimension; every identity scalar remains a
dependency. Role filtering, fleet exclusions, mutation replay and backend
authorization are unchanged.

Independently reran `OperationNotes.privacy.test.tsx` against this working tree:
**4 passed**, covering dashboard and fleet caches through different-account and
same-account new-session transitions while the new response remains pending.
Existing React test `act`, Router future-flag and Browserslist notices remain;
there were no failed assertions. This re-review does not sign off the pending
full CI, merge, deployment or production workflow gates.
