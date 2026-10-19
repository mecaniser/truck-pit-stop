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

## Staff sender selection independent gate

2026-10-19: **GO for the final source and isolated test scope**, after correction of one additional gate finding. Reviewed the new authenticated PATCH sender endpoint, backend selection/context helpers, changed conversation serialization and frontend selection/draft flow against5e928028. No implementation edits were made by this reviewer.

**Finding closed:** initial selection held uncertain manual sends only by thread. An independent PostgreSQL reproduction showed a duplicate ETS-like customer/thread sharing the DBN phone could choose an alternate sender around an existing unknown manual outcome. Owner corrected sender-switch holds to tenant plus thread-or-phone for pending/dispatching/unknown; manual send policy now also holds dispatching/unknown outcomes by phone. The independent reproduction now receives409 and a previously mapped duplicate conversation also cannot send around that hold.

The endpoint retains existing active-user messaging authorization and optimistic version guards. Actual isolated HTTP challenges confirmed403 for an unauthorized customer-role user,404 for foreign-tenant thread/binding targets, and409 for a disabled binding. Binding locks are ordered before the thread to match callback lock order; competing same-phone selection serializes and retains the unique phone ownership guard. Idempotent same-selection requests do not increment version. No forwarding, customer identity, message history or automated transport is updated by selection.

Frontend sends only after server confirmation using the returned account/version, blocks both click/keyboard sends during change, preserves over-limit drafts, and represents a disabled current option as unavailable. The reviewer independently re-ran:

```
/tmp/db134-test-venv/bin/python scripts/communications_local.py exec python -m pytest /tmp/test_callrail_sender_gate.py tests/test_callrail_service.py tests/test_callrail_dispatch.py /tmp/test_callrail_independent.py -q -p no:cacheprovider
npm exec vitest run src/features/communications/ConnectedInbox.test.tsx src/features/communications/api.test.ts src/features/communications/communications.test.tsx
```

Results: **42 isolated backend cases passed**, two existing deprecation warnings,6.50 seconds; **29 frontend cases passed** across3files,3.07 seconds. New independent challenges include actual endpoint authorization/foreign targets/disabled binding, duplicate-phone unknown routing bypass, an already-mapped duplicate's send hold, and automated pending/dispatching/unknown phone holds.

Final reviewed source SHA256 for this delta:

| File | SHA256 |
|---|---|
| backend/app/services/callrail_service.py | 9a8257ac0bf8eb9c5817880df829ab5cbf9adb7851f4c342e6825fe1aaea578e |
| backend/app/services/communications_service.py | 6f5fa8710dd78121d27638560b255c9ceacbae559570a2bebf563d4c2bdad64f |
| backend/app/api/v1/endpoints/communications.py | 96b0a663d6e63482520c820cd993ba2813f1546b3e4b8da7aeb16c2593eab44d |
| frontend/src/features/communications/ConnectedInbox.tsx | a228fc347b5b4fb76d21245a3dd1ccd22ee49ed0d706b4ba0e988653caef6fe9 |
| frontend/src/features/communications/CommunicationsPreview.tsx | 5bfc633aa04dc986b2f9d6d110548102be886cbdc14dbf60c088767ea63f7cd5 |
| frontend/src/features/communications/api.ts | 4a55787718415fa66fd690a305e183cc284ea0c6421d37de31b67b113bd25105 |
| frontend/src/features/communications/model.ts | d095e64723e62b223f9a86808e91365792868c7b697d2f511f0300a5e8b52320 |

Behavior boundary communicated to Product/Delivery: selecting a different binding or restoring Twilio replaces/soft-deletes the sole active CallRail conversation mapping. Existing messages remain intact, but later replies to the former CallRail binding are held as unmapped contact rather than automatically attributed to the new sender. This gate does not claim simultaneous inbound routing across historical bindings. Protected CI, actual browser acceptance and deployed/live pilot gates remain separate; automation remains disabled.

## Final preservation and stale-poll correction gate

2026-10-19: **GO for the final preservation delta. The former-number reply limitation in the previous section is closed.** Selection now changes only `selected_for_sending`; previous CallRail routes remain active for inbound replies on their original binding, independently of the selected outbound sender. Canonical customer/phone and tenant checks apply to each route. Restoring Twilio leaves both CallRail inbound routes intact. ETS-like duplicate threads cannot claim reserved bindings; switching back reuses the original route, and concurrent outbound choices retain exactly one selected route.

Independent isolated evidence:

- **45 backend cases passed**, two existing deprecation warnings,7.90 seconds. Includes prior provider/dispatch/security challenges plus actual raw-signed HTTP replies to both historical CallRail numbers after restoring Twilio. Each reply reached the original thread, replay deduplicated, and STOP on an old number still suppressed the canonical customer's SMS.
- Independently rehearsed migration183 against182-shaped active and soft-deleted rows in a throwaway PostgreSQL schema. Existing IDs/thread/binding/phone/deleted timestamps remained identical; the added selection column defaults true. Adding a second preserved route succeeds; lossy downgrade refuses with all rows retained. The entire scratch-schema transaction was rolled back.
- **30 frontend cases passed** across3files,3.61 seconds. The in-flight older-poll regression retains confirmed sender/account/version8 and the draft/140-character policy, then sends with the confirmed account/version. No implementation changes by this reviewer.
- `git diff --check` passed.

Commands:

```
/tmp/db134-test-venv/bin/python scripts/communications_local.py exec python -m pytest /tmp/test_callrail_preservation_gate.py /tmp/test_callrail_sender_gate.py tests/test_callrail_service.py tests/test_callrail_dispatch.py /tmp/test_callrail_independent.py -q -p no:cacheprovider
npm exec vitest run src/features/communications/ConnectedInbox.test.tsx src/features/communications/api.test.ts src/features/communications/communications.test.tsx
```

Superseding final reviewed source SHA256:

| File | SHA256 |
|---|---|
| backend/app/services/callrail_service.py | a9b1705bcf692cc68b3f40edeafa4618b83aea82605149a64e557afcffddb274 |
| backend/app/db/models/callrail.py | 7ce1df8a8138e2cde7543c619ad85be380abc278cd353df702e99cd07c0bbc4b |
| backend/alembic/versions/183_callrail_preserve_reply_routes.py | 8ebd91145919c7a3eae18b539dc4632097c723ce15c50d1922442fab6a0325fa |
| backend/app/services/communications_service.py | 6f5fa8710dd78121d27638560b255c9ceacbae559570a2bebf563d4c2bdad64f |
| backend/app/api/v1/endpoints/communications.py | 96b0a663d6e63482520c820cd993ba2813f1546b3e4b8da7aeb16c2593eab44d |
| frontend/src/features/communications/ConnectedInbox.tsx | 8cb1b32502533c093cea2062b54ef82a3cfd5765a14b2c8a8558d5132fbcb551 |
| frontend/src/features/communications/CommunicationsPreview.tsx | 5bfc633aa04dc986b2f9d6d110548102be886cbdc14dbf60c088767ea63f7cd5 |
| frontend/src/features/communications/api.ts | 4a55787718415fa66fd690a305e183cc284ea0c6421d37de31b67b113bd25105 |
| frontend/src/features/communications/model.ts | d095e64723e62b223f9a86808e91365792868c7b697d2f511f0300a5e8b52320 |

No unresolved actionable source finding in this delta. Protected CI, deployed migration/health, actual browser acceptance, preservation of external provider settings and real send/reply evidence remain release gates. No production/provider mutation or automation activation was performed by the independent reviewer.

## Production activation script review and rollback plan

2026-10-19: **GO for the reviewed activation-script scope only**, conditional on protected CI, deployed schema/application acceptance and the authorized live pilot. Reviewed `/tmp/callrail-production-binding.py` SHA256 `c61d062b51d2e73f1a8d44455bab32cbbfbf325b5f2407e947c8d1777026dec3` without executing it or touching production. Source parses and compiles; no `assert` guards remain.

Gate findings corrected by the owner before this GO: the initial guard used the migration filename stem rather than the actual revision `183_callrail_reply_routes`; flags/schema/identity/config checks initially used optimization-removable assertions; identity checks initially lacked active/nondeleted tenant/customer/thread and pinned thread-phone/opt-out checks. Current explicit `require` exceptions cover those cases.

The script's only possible mutation is insertion of the exact approved number binding when `CALLRAIL_ACTIVATE=yes`. Otherwise it performs reads. It checks all three SMS flags remain false, both dedicated credential references exist in the deployed environment, and the exact single Alembic revision183 is applied. Canonical tenant/customer/thread IDs and normalized approved recipient phone are pinned, with deleted/inactive/messaging-disabled/opted-out states rejected. Existing number ownership and every expected binding field must match exactly; unexpected existing config stops instead of overwriting. It creates no customer, conversation route, message or send operation, makes no provider request, and does not select a sender; staff must explicitly select it through the guarded UI. Commit is limited to the new binding. Credential values are not printed.

**Activation and rollback signals:**

1. Hold activation if final protected CI fails, deployed source identity/readiness/schema is wrong, any SMS flag is enabled, canonical customer/thread has changed, callback signature fails, or current CallRail integration/forwarding differs unexpectedly from its saved pre-change state. Do not substitute another customer or sender.
2. Stop further manual sends immediately if a wrong tenant/recipient/sender appears, a signed reply is misattributed/duplicated, forwarding changes, or an operation becomes dispatching/unknown without a reconciled receipt. Preserve the operation and provider receipts; do not resend uncertain work.
3. The safe application stop is to disable only the new CallRail number binding, retaining its row and all selected/inbound routes, messages, aliases and quarantine evidence. Selected mapped threads then fail closed and do not silently fall back to Twilio. While disabled, incoming callbacks are durably quarantined; CallRail retains its own conversation history. Keep all three global SMS flags false.
4. If provider webhook rollback is required, remove only the newly appended DieselBridge sent/received URLs from integration2593909, using a fresh current config and comparing the full remaining receiver set to the saved pre-change config. Preserve existing ELIS call receivers, all unrelated integrations and forwarding. Do not broadly replace provider settings from a stale snapshot.
5. Do not delete message/operation rows or downgrade schema183 to squeeze multiple preserved inbound routes into the old unique-thread schema. The migration correctly refuses lossy downgrade. Default rollback is configuration disablement with schema retained.
6. Do not blindly redeploy pre182/183 code after migration183: `railway.json` runs `alembic upgrade head` in pre-deploy, and old source may not resolve the newly applied revision. Any code rollback must retain compatible migration definitions or receive a separately verified recovery plan. Configuration disablement avoids this graph mismatch.
7. Resume only after exact failure reconciliation and renewed source/runtime/provider acceptance. Restore Twilio through staff UI only when pending/unknown holds have been resolved; do not bypass those holds with direct mapping edits. The authorized pilot remains limited to the user's recipient ending0486.

The provider plan to append only text sent/received URLs is source-reviewed, not a claim that external settings have been changed or verified after mutation. No production SQL, provider request, deployment or activation was performed by the independent reviewer.
