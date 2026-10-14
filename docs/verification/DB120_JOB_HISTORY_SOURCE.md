# DB-120 source capture handoff

Backend & Integrations → independent QA/Security → Release.

## Implemented

- Invoice identity owns the job; exact imported service/customer siblings supply
  operation context. Conflicting equipment, source provenance or deleted context
  marks grouping uncertain. No operation-total summing or financial mutations.
- Per-tenant cursor scans 50 invoice records per five-minute run (configurable
  1–200), rotates at end, and revisits customer/vehicle/operation corrections.
- Per-invoice observation sequence increments only when source snapshot changes;
  A→B→A gets observations 1, 2, 3. Cursor, observation and immutable outbox commit
  atomically under tenant lock. Retry sends the same source event identity.
- Imported paid dates retain day precision; no midnight payment instant invented.
- Existing HMAC/URL/secret, leases, retries and absolute PII expiry are reused.
  History failures do not pause native settlement delivery; native gets priority.
  Expiry redacts the nested snapshot, and no expired snapshot is rebuilt.
- Capture and history delivery require both `SHOP_HISTORY_CAPTURE_ENABLED` and
  membership in `SHOP_HISTORY_CAPTURE_TENANT_IDS`. Empty/default is off.

## Verification

2026-10-14: 50 focused tests passed across history source, existing paid webhook,
and native ELIS outcome contract. Coverage includes replay, A→B→A, bounded cursor,
rollback, tenant rejection, split operations, dates, redaction, disabled scope,
and history terminal failure isolation. Invalid allowlist disables only history;
oversized descriptions are explicitly marked and held. Invalid source records
produce a non-deliverable audit event and do not strand other invoices. A
previous valid retained snapshot is re-emitted as uncertain with a new sequence
so its prior automatic match can be quarantined. If retention already erased that
snapshot, no old private payload is reconstructed; failed-capture audit remains
an explicit operator exception requiring source repair. Migration170 PostgreSQL offline SQL
compiles. Independent gates and actual PostgreSQL migration/concurrency runtime
acceptance remain required; synthetic SQLite tests do not prove lock semantics.

Runtime preflight: intended branch `codex/shop-history-intake` at base `6b7dfcb0`;
5173 belongs to another worktree, 8000 has no listener, and this worktree has no
approved local environment. No servers were stopped or secrets copied. Tests
use synthetic test configuration and this checkout's source with the existing
Python dependency environment. Backend-only worker change has no browser journey.
No live capture, provider settings, Google submission, payment or campaign changes
were made during implementation.

## Rollout / rollback

1. Deploy receiver that accepts history v1 and sequences observations.
2. Deploy source and migration170 with capture disabled. Verify worker/beat task
   registration and migration independently.
3. Enable only the explicitly approved shop UUID in the private allowlist, then
   enable capture. Observe bounded scheduled capture and signed receipt; verify
   unknown matches stay held and existing submissions are unchanged.
4. Disable `SHOP_HISTORY_CAPTURE_ENABLED` to stop both new history capture and
   history delivery; native paid delivery continues. Preserve cursor, observation,
   source receipts and held history. Never replay Google conversions as rollback.

Do not call the item released before independent gates, merged/deployed SHAs,
actual scheduled source receipt and receiver held-state evidence are recorded.
