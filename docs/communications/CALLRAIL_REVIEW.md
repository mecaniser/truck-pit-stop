# DB-COMMS-009 independent Security and QA gate

2026-10-19. Reviewer: independent Security & QA; no implementation ownership or implementation edits. Accountable implementation owner remains Backend & Integrations.

**GO for the reviewed source and isolated integration scope. Production activation, protected CI, deployed browser acceptance and real handset send/reply remain separate gates.** No provider or production changes were performed by this reviewer.

## Independent evidence

Read the manual-inbox contract, changed backend/frontend sources, additive migration182, existing authorization/manual operations and unchanged Twilio callback lookup. Ran the isolated PostgreSQL suite through the approved harness:

```
/tmp/db134-test-venv/bin/python scripts/communications_local.py exec python -m pytest /tmp/test_callrail_independent.py tests/test_callrail_service.py tests/test_callrail_dispatch.py tests/test_communications_service.py -q -p no:cacheprovider
```

Final result: **36 passed**, two existing deprecation warnings, 6.19 seconds. This comprises29 repository cases plus7 independently constructed challenge cases in a temporary review file. Synthetic data only; no SMS was sent. The independent cases exercise two tenants with the same customer phone, three concurrent duplicate callbacks yielding one message/one unread event, actor revocation, recipient rebound, disabled binding, sender/tracker changes before dispatch, and a failed provider receipt arriving before a successful HTTP return.

Repository cases additionally cover raw-body HMAC/tamper, signature rejection before JSON trust, bounded webhook bodies, malformed signed fields, unknown/wrong company/sender/stale receipt quarantine, STOP suppression, daily CallRail conversation IDs and numeric/resource alias import deduplication, canonical DBN/ETS duplicate preservation, manual140-character enforcement, automated-source denial, idempotent replay, uncertain outcomes held without retry, and successful receipt reconciliation after an HTTP timeout. Existing shared-inbox cases remain passing.

## Finding closed during gate

**P2: a successful HTTP response could overwrite a concurrently ingested FAILED CallRail receipt with SENT.** Independently reproduced against PostgreSQL. Initial terminal-state guard alone did not fix the issue because the dispatch session retained its stale SMS identity-map object. Owner corrected the final locked SMS SELECT with `populate_existing=True` and preserved terminal delivery state. Both the repository regression and independent reproduction now pass. This reviewer did not implement the fix.

## Security and compatibility assessment

- Existing authenticated messaging/tenant guards remain in place. Explicit mapping validates tenant, thread, canonical customer, recipient and enabled provider binding; disabled/invalid CallRail mappings fail closed instead of falling back to Twilio.
- Queued intents retain provider/account/binding and sender/recipient identity snapshots. Binding company/tracker/sender edits invalidate their account identity. Actor/recipient/binding changes are rechecked before the durable dispatch claim.
- One attempt is durably committed before provider I/O. Unknown outcomes are not retried. Callback acceptance can reconcile an HTTP timeout without duplicating the local message.
- Raw callback signatures use the trusted mapped company signing-key reference before JSON interpretation; company and local-number checks precede conversation lookup. Unmapped/ambiguous events are quarantined rather than creating or reassigning customer records.
- Binding row locks serialize callback replay; account-scoped alias uniqueness deduplicates numeric and resource receipts. Callback thread→operation locking does not form a cycle with pending dispatch operation→thread locking because callback receipt matching excludes pending operations; post-I/O completion acquires operation→SMS only.
- Credential values remain environment-only and are not returned through the API/UI. The allowed credential-reference namespace prevents resolving arbitrary process secrets. Provider response bodies are not copied into raised errors.
- New provider IDs never occupy Twilio SID fields. Existing Twilio SID-based callbacks cannot match CallRail-only receipts. Source adds no CallRail forwarding/settings mutation or automated producer path.
- UI exposes CallRail sender/provider and a140-character manual limit; backend independently enforces it. Existing non-CallRail limits and draft content are preserved.

Reviewed source SHA256:

| File | SHA256 |
|---|---|
| backend/app/services/callrail_service.py | bdca7c418b8eb2d2116527a48ca0617521184d8034f686aff67225f4f593cb76 |
| backend/app/services/communications_service.py | 8db966d473afccad5d6d19877fbc176235ec42148509f0748dae4b8039f010ed |
| backend/app/api/v1/endpoints/callrail.py | 76949c9bc62ec8f71cadcadba31a517d3bdad18dc47f1e019a5d342df5c4179a |
| backend/alembic/versions/182_callrail_manual_inbox.py | 29431fd70bb7d73f6aeef13774b1442f0cb3abb32384beb644b3600b2b0d3816 |

## Remaining release gates

Owner must record integrated desktop/mobile runtime evidence, all required protected CI, additive production migration/deployment health, explicit pilot mapping to the canonical DBN conversation with ETS/history retained, existing CallRail forwarding/webhook preservation, and one manual send/reply test to the authorized recipient ending0486. Keep new Twilio routing, automation outbox and recovery disabled. No general campaign/automation enablement is approved by this source gate.

## Scoped final delta re-review after c95292ce

2026-10-19: **GO** for the two-file tracker-null compatibility correction. Independently checked the official [Send a Text Message response documentation](https://apidocs.callrail.com/#send-a-text-message), which defines a null `current_tracker_id` as using `initial_tracker_id`. The helper adopts that documented fallback; a present different or malformed current tracker never falls back. Company, current sender number and recipient matching remain strict; a null sender number cannot borrow the initial sender. No credential, callback, automation or tenant-binding changes are included.

Independent re-run of `tests/test_callrail_service.py` through the isolated harness: **19 passed**, two existing deprecation warnings,1.29 seconds. Tests include accepted documented null tracker, wrong initial tracker, present conflicting/empty current tracker, import fallback, and missing current sender rejection.

Superseding reviewed hashes for this delta:

- `backend/app/services/callrail_service.py`: `c7288e31e5973a494501960b4d6d534c0075c711624a6ba0d9f06d9dbd1e2850`
- `backend/tests/test_callrail_service.py`: `bec6eaec6e1c8b18d039d9ee0a2b4144b13c1ad2a21740ac6c514ca3cbb43109`

Previous source-gate boundaries and remaining release gates are unchanged. No provider or deployment mutation was performed by this reviewer.

## Actual API receipt-shape and historical attribution delta

2026-10-19: **GO** for the final service/test delta adapting the read-only provider response shape. Historical API SCI message IDs become resource aliases; live signed events still require a valid SCI resource ID (numeric aliases are optional). API imports no longer infer historical local senders from the conversation's current tracker: unknown historical messages are quarantined unless an operator explicitly verified their IDs. The allowlist is server/operator-only, with no HTTP/client acceptance path. Previously known aliases still undergo tenant/thread/body/direction/from/to identity checks. Actual `message_type` is respected so MMS is quarantined rather than misrepresented as SMS. Company/current sender/recipient guards remain strict.

Independent isolated provider+dispatch suites plus the seven independent challenge cases: **32 passed**, two existing deprecation warnings,4.25 seconds. Command:

```
/tmp/db134-test-venv/bin/python scripts/communications_local.py exec python -m pytest tests/test_callrail_service.py tests/test_callrail_dispatch.py /tmp/test_callrail_independent.py -q -p no:cacheprovider
```

Superseding final delta SHA256:

- `backend/app/services/callrail_service.py`: `d89efda00ec8920812462e2f544a752836c7980fa0dfba488ce01d1a65f445de`
- `backend/tests/test_callrail_service.py`: `de5764ff553790931c2f01088976db3ca9cd88f451c413005441af0610f863ff`

No new actionable source finding. Real pilot provenance must be recorded for each operator-allowlisted historical ID; only the two approved test-message IDs are in the planned import scope. All prior production/CI/live-acceptance gate boundaries remain unchanged. Reviewer made no implementation, provider or deployment mutation.
