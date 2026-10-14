# DB-115 — Staff work hold contract

Architecture & API Contracts → Backend & Integrations / Frontend & UX. Contract ready 2026-10-13; branch `codex/staff-work-hold`. This contract defines behavior, not implementation or QA approval.

## Boundary and compatibility

Add `POST /api/v1/repair-orders/{order_id}/staff-hold` and `POST /api/v1/repair-orders/{order_id}/staff-release-hold`. Authorized roles are exactly `operation_execution.STAFF`: garage owner, garage admin, receptionist and fleet manager. Fleet managers retain the established `is_internal OR is_fleet_work` restriction. Mechanic, customer, driver and unrelated roles cannot call these routes. Keep existing mechanic `/hold` and `/resume` contracts: the assigned lead can still resume a held order and start their own timer. Staff release does not invoke mechanic resume.

No migration. Reuse `RepairOrder.hold_reason` (100 characters), `held_at`, `updated_at`, existing timer audit and `RepairOrderHistoryEvent`. This is an operational sub-state; status stays `in_progress`. Do not modify completion snapshots, operation assignments/status/versions, checklist answers, recommendation provenance, prices, discounts, inventory, quote/invoice state or custody release.

## Request and response

Hold JSON:

```json
{"reason":"Waiting for parts", "expected_updated_at":"2026-10-14T00:30:00.123456Z"}
```

Release JSON:

```json
{"expected_updated_at":"2026-10-14T00:31:00.234567Z"}
```

Both bodies reject unknown fields; timestamp is required, valid and timezone-aware. Normalize timestamps to UTC for comparison without truncating fractional precision. Hold requires a string trimmed to 1–100 characters; whitespace-only, null and overlong values return 422. No client-supplied actor, tenant, status, stop time or session IDs.

Both return 200 with this minimal authoritative shape:

```json
{
  "id":"00000000-0000-0000-0000-000000000115",
  "status":"in_progress",
  "hold_reason":"Waiting for parts",
  "held_at":"2026-10-14T00:31:00.234567Z",
  "updated_at":"2026-10-14T00:31:00.234567Z",
  "stopped_sessions_count":2
}
```

Release returns null `hold_reason`/`held_at` and zero stopped sessions. `updated_at` must change on every accepted transition, remain strictly later than the prior value, and be serialized after flush/refresh. The UI submits the exact raw server timestamp captured when the dialog opened, never a JavaScript Date round-trip. Apply these returned fields only to the same selected order and invalidate/refetch the queue, workspace/detail, operation execution and relevant timer views; do not replace the full workspace with this reduced payload.

## Transaction and errors

1. Reject disallowed roles before lookup. Missing authenticated tenant is 400; normal auth failures remain 401/403.
2. Use `operation_execution.load_order(..., write=True)` after enforcing staff-only: tenant advisory lock first, tenant-scoped non-deleted row lookup with `populate_existing=True`, then RO row lock. Wrong tenant, missing or deleted order is indistinguishable 404. Out-of-scope fleet work is 403.
3. Under this lock require `operation_execution.editable(order)` and `status == in_progress`; reject draft, assigned, pending review, completed, invoiced, paid, cancelled, or an effective pricing lock with 409. Legacy `quote_sent` lock remains editable, matching existing conventions.
4. Compare expected/current UTC `updated_at` before side effects. Stale input is 409, with refresh-and-retry text. Hold when already held and release when unheld are 409 even with a fresh timestamp; no duplicate event or altered timer. Replays are rejected, not silently reapplied.
5. Hold captures one UTC instant, stops all active, non-deleted timer sessions matching **both tenant and this repair order**, including general lead and operation-assigned technicians, using `operation_execution.stop_order_sessions(..., now=stamp, reason='hold')`. Record `hold_reason` and `held_at` at the same boundary. The helper already uses the same reentrant advisory lock and `stop_active_session`, preserving timer audit and actor identity. Its per-mechanic lookup is protected by the active-session unique index and tenant serialization; test that unrelated orders/misc work are untouched.
6. Release only clears hold fields and records history. Never call `start_session`, attendance/break helpers, or stop another order's timer. Technicians deliberately restart work through their existing controls.
7. Persist order, all timer stops/audits, and one history event in a single transaction/commit. Failure stopping any session or appending history rolls everything back. Advisory contention maps to existing 409 workflow-busy text; never wait while holding a different lifecycle lock.

`expected_updated_at` guards stale RO/hold intent, not every child edit: operation changes do not always update the RO timestamp. Tenant serialization plus a fresh lifecycle check is the concurrency guarantee for operation/timer/finalization races. Do not claim an aggregate version.

## History, privacy and notifications

Append event types `work_held` / `work_hold_released` with actor ID and actor display-name snapshot, previous/new hold state, original reason and held timestamp. Release history retains the former reason after live fields clear. The events belong to an internal event-type set included in the existing customer-history exclusion at `get_repair_order_detail`; history text renders as text, never HTML. Do not put this data in customer notes or the pricing `internal_notes` envelope.

Current source exposes `hold_reason`/`held_at` in customer list, workspace projection/fallback, basic and detail responses despite staff-only hold notifications. Because staff can now enter free-form operational reasons, redact these two fields for CUSTOMER responses in all those paths. Keep staff projections intact; do not change lifecycle status. Verify both projected and legacy/fallback paths so internal history/reason does not leak through alternate reads.

Only after commit, broadcast the order update with `send_to_customer=False`, `notify_status_change=False`. Send a timer update for each stopped session's actual mechanic ID, not merely the staff actor or order lead. Release sends only the order update. No email, SMS, customer websocket, attendance event, external provider call or worker job. Notification failure must not turn an already committed transition into a misleading failed write; the response remains authoritative and clients refetch.

## Required acceptance evidence

- Authorized owner/admin/receptionist and scoped internal/external-fleet manager succeed; unscoped fleet manager and every excluded role fail without writes. Wrong-tenant/missing/deleted IDs return 404 with unchanged orders, timers and audit counts.
- Hold a populated in-progress fixture with a lead general timer and a second technician's operation timer. Both end at the same instant with correct staff actor/stop reason and one history event; another order's active timer, misc timer, attendance/break records and another tenant remain unchanged. A no-active-timer order can still be held.
- Release preserves all prior timer rows/attendance counts and creates no active timer. Reload shows cleared hold and retained internal history. Mechanic self-resume remains compatible and still creates its own legitimate timer; staff never borrows that route.
- Reject blank/overlong reason, missing/naive/invalid timestamp, unknown body fields, stale version, repeat hold/release, final/wrong stage and effective pricing lock; allow quote-sent legacy lock. Assert zero partial effects.
- Inject a second-session stop/history failure and roll back: no hold, no stopped timer, no durable audit event.
- Real PostgreSQL two-session races, using isolated test data: hold wins timer-start → contender busy, then held-order rejection; timer-start wins → hold first busy, refreshed retry stops the committed timer; competing hold/release and mechanic resume → one mutation wins, stale/repeat loser leaves no effects; completion/finalization wins → staff hold rejects lifecycle/lock after refresh. Assert no active timer remains on a held order. SQLite tests alone do not prove lock behavior.
- Held work cannot complete an operation or finish the order through existing guards. After staff release normal explicit timer/operation/completion workflow works; all assignments, checklist answers, provenance and financial values retain their pre-hold snapshots.
- Customer list (projection and legacy), workspace (projection and fallback), basic and detail reads contain neither free-form hold fields nor internal hold events/actor history. Staff still sees them. Broadcast tests prove no customer delivery and one timer notification per affected technician, including post-commit notification failure recovery.
- Desktop and 390/320px mobile: compact Hold/Release action only when allowed; reason required and bounded; readable state/reason; named accessible dialog/close, Escape/cancel and focus return; pending prevents duplicate submit/dismiss; failed/stale request preserves input and provides refresh path; save/reload, release/reload, timer/completion checks work without clipping or extra workspace scroll areas. Existing dense desktop is retained.

## Handoff

Accountable owner: Backend & Integrations. Implementation participation: parent agent; this Architecture agent writes only this contract. Required next gates: focused API/schema/UI tests, real PostgreSQL race evidence, actual local desktop/mobile journey, independent QA and Security reviewers with no implementation/contract-direction participation, protected PR CI. Production writes, merge or deployment are not authorized by this contract. Return contract mismatches or newly discovered lifecycle/privacy ambiguity to Architecture before changing the behavior above.
