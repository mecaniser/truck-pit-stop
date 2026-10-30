# DB-146 / C3 — Standalone truck issues and staff follow-up

Status: Implemented and released in PR698 / `18255c03` on 2026-10-30 after Architecture, independent QA/Security, protected CI and production acceptance. Backend & Integrations is accountable. Contract semantics remain frozen; [final verification receipt](../verification/DB146_TRUCK_ISSUES.md) records exact release evidence and production read-only coverage limits.

## Outcome and fixed limits

Shop staff can record a truck issue without opening an RO, give a staff member responsibility, choose a follow-up date, and find that same issue when the truck returns. An explicit reference can connect it to an existing visit without creating work, changing prices, or declaring repair complete.

Follow-up owner means responsibility for reviewing the issue. It is not technician dispatch, work assignment, a customer reminder or an automatic notification. Only new standalone issues receive this metadata in C3. Existing RO recommendations retain their source, APIs, mutation rules and conversion behavior unchanged. No source backfill, copied recommendations, fabricated ROs, importer changes, financial writes, invoice creation, stock/time/status writes, messages, provider calls, collector changes or worker schedules.

## Verified existing seams and compatibility

- `RecommendedService.repair_order_id` is required; it has no standalone vehicle, responsible user or follow-up date.
- `GET /repair-orders/recommended-work` and its frontend Zod parser require non-null `source_order`. Keep this contract byte/behavior compatible; do not add standalone rows to it.
- `RecommendedWorkPanel.tsx` already gates itself to owner/admin/receptionist, scopes query/cache by tenant/truck/customer/current RO, and defaults conversion off. Its existing conversion-enabled placement in `RepairOrdersPage.tsx` around line4855 and read-only placement around line5064 must remain unchanged in effect.
- `CustomerVehicleDetail.tsx` contains truck facts/notes, `MaintenanceSection`, repair history and `ExternalServiceHistory`. It does not currently mount RecommendedWorkPanel. `CustomersPage.tsx` mounts that detail around line1143. This is the safe primary C3 insertion surface, before repair history, without redesigning Shop Work.
- Compose a new `VehicleIssuesPanel` and existing `RecommendedWorkPanel` as separate sections. Customer truck detail passes exact vehicle/customer IDs and `canConvert=false` to the existing recommendation component. Its heading/empty copy should say recommendations from repair orders in this no-current-RO context rather than implying another order is open. This optional presentation prop must not change data shapes or conversion defaults.
- Add VehicleIssuesPanel adjacent to existing recommendation placements in the staff RO workspace, passing exact vehicle/context RO. Standalone issues are not excluded merely because already linked to this RO. Display the link instead of an Add action. Do not replace or nest issue actions in RecommendationConversionAction.
- Fleet TruckDetail has its own incident/create-repair workflow and fleet permission domain. Do not reuse, alter or expose that workflow for C3; no fleet/customer/driver-portal expansion.
- DB107 conversion creates priced Labor, audits it and recomputes RO totals. C3 must never call that endpoint or simulate conversion with a zero-cost labor line.

## Additive records

`vehicle_issues` (standard UUID and UTC created/updated timestamps):
- tenant_id, vehicle_id: required exact identities; vehicle immutable after creation.
- description: required trimmed plain text, 1..2000 characters; render as text.
- priority: urgent | soon | monitor, default soon (reuse vocabulary, not existing table).
- responsible_user_id: nullable active same-tenant garage_owner/garage_admin/receptionist. Null is Unassigned.
- follow_up_on: nullable ISO calendar date; no timestamp conversion. Null is Not scheduled. Past dates allowed for an existing backlog.
- state: open | resolved | dismissed; default open.
- state_reason: nullable plain text, at most1000 characters; required on resolve/dismiss/reopen transitions.
- state_changed_at, state_changed_by_user_id; created_by_user_id; version integer beginning1.

Separate issue-specific audit events preserve create/edit/ownership/date/state/link changes and actor. Do not append RO history or mutate source records. No hard-delete API in v1; dismissal retains history. Technical history is staff-only and contains no pricing/contact snapshots.

`vehicle_issue_links`: durable issue-to-RO references with tenant, issue, exact vehicle, target RO UUID and order-number snapshot, creator, created_at, ended_at, ended_by, end_reason. At most one current (ended_at null) link per tenant/issue, enforced by partial unique index. No cascade deleting evidence with an RO. Current link availability derives from tenant/vehicle-scoped target read; cancellation/deletion yields unavailable, never creates a replacement or marks the issue resolved. Completed/invoiced/paid does not mean the issue was fixed.

`vehicle_issue_requests`: tenant/request UUID unique, actor identity, operation, canonical normalized request hash, result issue/link IDs and accepted version, timestamps. This is metadata-only idempotency evidence. Store only necessary inputs; never credentials. All request/event/issue/link rows participate in the same transaction.

## Additive API (all under /api/v1)

All requests reject unknown fields. Tenant, actor, timestamps, target snapshots and capability flags are server-controlled. Every list response returns `as_of` UTC and validated shop timezone so follow-up due state is consistent.

1. `GET /vehicles/{vehicle_id}/issues`
   Query: optional customer_id/context_order_id, state=open|resolved|dismissed|all (default open), skip>=0, limit1..100 (default25).
   Response `{items: Issue[], total, skip, limit, has_more, as_of, timezone}`. Exact same authorized filters before count/order/page; unique issue IDs. Order priority urgent/soon/monitor, follow_up_on ascending nulls last, created_at ascending, id ascending. No speculative count merging with recommendation pages.
2. `GET /vehicles/{vehicle_id}/issues/{issue_id}` — one issue, including current safe link; optional customer/context IDs receive the same validation.
3. `GET /vehicles/{vehicle_id}/issue-owners` — eligible same-tenant active staff only, reduced `{items:[{id,display_name}]}` sorted name/id. No emails, pay rates or broad user-directory access.
4. `POST /vehicles/{vehicle_id}/issues`
   `{request_id:UUID, description:string, priority:'soon', responsible_user_id:UUID|null, follow_up_on:'YYYY-MM-DD'|null}`. All except request_id/description optional as defaults above. Return201 `{issue, replayed:false}`; exact replay200.
5. `PATCH /vehicles/{vehicle_id}/issues/{issue_id}`
   `{request_id:UUID, expected_version:positiveInt, description?, priority?, responsible_user_id?, follow_up_on?}`. At least one editable field. Omitted keeps value; explicit null clears only nullable fields. Only open issues editable; closed issues must deliberately reopen first. Return200 `{issue,replayed}`.
6. `POST /vehicles/{vehicle_id}/issues/{issue_id}/state`
   `{request_id,expected_version,state:'resolved'|'dismissed'|'open',reason:string}`. Nonempty reason required. Open->resolved/dismissed or closed->open only; same-state new request409. Resolution records a staff assertion about the issue, not performed labor, paid status, or RO completion. Never infer from a linked visit. Preserve link history. Return200 `{issue,replayed}`.
7. `POST /vehicles/{vehicle_id}/issues/{issue_id}/links`
   `{request_id,expected_version,target_order_id:UUID}`. Issue must be open. Target exact same tenant/truck, undeleted, noncancelled native order under existing ownership-veto rules (including linked ETS/historical-hold provenance). It may already be completed/invoiced/paid: link is a reference only. New link201; identical replay200. New request to same current target returns existing link without extra audit/version increment; different current link409. UI default is Link this visit when context RO eligible, not a universal RO picker. No RO creation.
8. `POST /vehicles/{vehicle_id}/issues/{issue_id}/links/{link_id}/end`
   `{request_id,expected_version,reason:string}`. End exact current link; preserve it and leave issue state unchanged, including already resolved or dismissed issues; never reopen as a side effect. User can then deliberately link a different visit. Stale/already ended link with a new request409. No implicit unlink or repair after target removal. Return200 `{issue,replayed}`.

Mutation responses have no customer/context_order parameter. Return `can_link_context=false` there; the UI refetches its validated context-scoped list after a mutation to obtain current contextual capabilities.

Issue response shape:
```ts
type Issue = {
  id: string; vehicle_id: string;
  description: string; priority: 'urgent'|'soon'|'monitor';
  state: 'open'|'resolved'|'dismissed'; version: number;
  responsible_user: {id:string; display_name:string; active:boolean}|null;
  follow_up_on: string|null;
  follow_up_state: 'unscheduled'|'upcoming'|'today'|'overdue'|'closed'|'unknown';
  created_at:string; updated_at:string;
  state_changed_at:string|null; state_reason:string|null;
  current_link: {id:string; target_order_id:string|null; order_number:string|null;
    availability:'available'|'unavailable'; created_at:string}|null;
  capabilities:{can_edit:boolean;can_change_state:boolean;can_link_context:boolean;can_end_link:boolean};
};
```
`follow_up_state` uses shop-local calendar date, only for open issues; absent/invalid shop timezone yields unknown for dated open issues, never fabricated overdue. Inactive former responsible user remains legible as unavailable/inactive; cannot be selected for a new assignment. For inaccessible/corrupt cross-tenant link targets, redact ID/number and expose only unavailable; retain server-side audit. Do not include prices, source payer, contacts, quote/invoice identifiers, notes from other records or operation capabilities. No issue money/value total.

## Auth, identity and scope

Only active garage_owner, garage_admin and receptionist. Reject mechanics, fleet managers, customers, drivers and superadmin absent this exact role with403 before entity disclosure. Missing tenant400. Use authenticated tenant, never client tenant. Missing/foreign/deleted truck/issue/customer/RO/owner contexts share generic404 `issue_context_not_found`; do not disclose other tenant values.

If customer context supplied, validate same DB099 current vehicle linkage: legacy vehicle.customer_id OR active current owner/operator relationship; not ended/future/default-payer-only. Context RO must be tenant-scoped, exact truck, undeleted/noncancelled; read context does not authorize financial/work actions. Same VIN/unit text never substitutes for UUID. Source import does not block recording a new native issue against a valid truck, but ETS-owned orders cannot become handling links. Do not read providers to establish ownership.

Repeat role/tenant checks inside mutation services and validate vehicle/assignee/target under the mutation transaction. Current link target changing tenant/vehicle must not expose data. Apply the approved [vehicle-merge compatibility contract](db146-vehicle-merge-compatibility.md): reject preview and POST when either vehicle has any issue history, regardless of state. Recheck POST under existing sorted vehicle locks before any source writes. No rehoming, copying, deduplication or override. Existing no-issue merge behavior and permissions remain unchanged.

## Transactions, retries, errors

Authorize and validate scope first, then lock the exact same-tenant undeleted vehicle FOR UPDATE OF vehicles with populate_existing and recheck availability. Acquire issue locks next, followed by link/request locks. This vehicle-first order serializes first issue creation with vehicle merge; request uniqueness also handles concurrent create. No tenant financial lock. Read an existing tenant/request receipt and require same actor, operation and normalized payload including expected_version. Exact replay returns accepted result references plus CURRENT issue representation (`accepted_version` may be included), never re-applies a mutation or restores an old link. Different payload/actor/operation with reused request ID409 `idempotency_key_reused`. Recheck replay after locks. Version mismatch409 `issue_changed`, no partial effects. Each effective change increments version exactly once and records one audit event; all failures roll back. No-op edits may return unchanged version with a receipt and no duplicate event. DB uniqueness handles concurrent link/create/retry; translate constraint collisions into replay or409, not500.

Errors use existing FastAPI structured detail style `{detail:{code,message}}`: 403 access_denied;400 tenant_required;404 issue_context_not_found;409 issue_changed, issue_closed, invalid_state_transition, issue_already_linked, link_changed, target_not_linkable, idempotency_key_reused;422 validation_error for fields/UUID/date/length/empty patch. Target ownership/status conflicts reveal only already-authorized local context. No mutation retries with a fresh request ID automatically after an uncertain network response; reuse original logical-submit ID.

## UI and refresh

Primary section label Truck issues with Add issue; each compact row shows description, urgency, staff owner, follow-up date and current visit link. No duplicate global search or new dashboard, no notification/estimate/invoice buttons. Owner/date blank states must be honest. Creation works with zero ROs. Form cancel performs no POST; dirty navigation asks keep/discard. Resolution/dismiss/reopen requires explicit action/reason. Link confirmation says it references this visit and creates no work. Existing RO recommendation display/actions stay separate and unchanged.

New query keys include user/role auth scope, tenant, vehicle, optional customer/context RO, state/page. Reset and cancel requests on scope change; never render prior truck/tenant results. Mutation refreshes issue list/detail/current context only, not prices or financial totals. Linked RO availability refreshes on normal order events or panel re-entry; do not invent optimistic availability. Each section has its own loading/error/retry; issue failure does not erase recommendations and vice versa. Restore caller origin/focus when opening a linked RO through existing workspace navigation. New issue component never mounts for forbidden roles, even if an authorized cache remains.

## Acceptance and release gates

- Create for exact truck with no RO; update owner/date; carry same ID to next visit; dates unscheduled/today/overdue/unknown/DST boundaries; explicit resolve/reopen/dismiss; untouched and dirty cancel.
- Link creates no RO/labor/parts/pricing/history/status changes; linked completed/paid order leaves issue open. End/relink retains history. Cancelled/deleted/ETS/historical-owned targets never become a valid new handling link. Same vehicle with changed payer does not reveal payer history.
- Same request repeated/concurrent creates one issue/event/link; competing target requests yield one current link; stale version409; request reuse mismatches409; retries after state/link changes do not resurrect. Failed changes rollback all metadata.
- Full role matrix, tenantless actor, foreign IDs in every parameter, inactive/wrong-role owner, malformed cross-tenant relationship/target, sameVIN differentUUID, source deletion and context/cache switching. Legacy DB099 response/source_order and DB107 tests unchanged.
- Count/page/filter/order stable with >25 issues; existing recommendations paginated separately. No dedupe by description. HTML safely rendered as text. Long names/descriptions, keyboard/focus and desktop/390px Day/Night acceptance.
- Actual PostgreSQL first-create versus vehicle-merge races in both winning orders, clean preview followed by issue creation, all issue states, unchanged no-issue merge behavior and tenant-consistent foreign keys. Merge rejection precedes any aliases, archival or source movement; preserve all history.
- Additive migration rehearsal, independent QA and tenant/security GO. Fixed local source cohort retention for finance/RO/labor/stock/time/provider tables; production acceptance uses existing reads/unsaved drafts unless separately authorized metadata fixtures. No invented real issues or production resolution for QA.
- Exact protected CI, merge/deploy readiness and changed-journey acceptance before C3 Done. A2 acceptance is recorded; Shop Work redesign and held ETS importer remain separate.

## Handoff

Architecture & API Contracts approved the linked merge-compatibility amendment; Product & Delivery Lead freezes this combined contract. Backend & Integrations owns additive schema/service/API implementation and focused PostgreSQL/tenant/idempotency evidence; Frontend & UX then consumes the exact contract. Independent QA and Security review the changed boundaries before release. No production issues, links, merges, financial writes or provider actions are authorized for QA. C3 is not Done until the full release gates above pass.
