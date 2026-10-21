# Automatic reply sender verification

DB-COMMS-015; Backend & Integrations accountable. Contract: [automatic sender](AUTOMATIC_REPLY_SENDER_CONTRACT.md). Source branch `codex/automatic-reply-sender`, integration base `b772fb56399ce45f16096cb7c94d36c6215170f2`.

## Behavior

The operator sees a read-only receiving number instead of tenant-wide sender inventory. Customer replies derive their route from the latest persisted inbound evidence; inquiry replies remain pinned to their original number. Invalid or ambiguous newest evidence holds instead of falling back. With no inbound, validated provider-backed outbound history or the existing explicit shop default can establish a route. Existing conversations and historical mappings are retained.

An old client cannot override the sender: the authenticated, tenant-scoped sender PATCH returns409 without workflow or mapping mutations. Pending sends revalidate the snapshotted route before provider access; changed or disabled routes reject without sending. Duplicate and uncertain operations keep their original identity. Drafts survive automatic route changes and reloads; confirmation of an original uncertain send clears only its matching copied draft, preserving later edits and other recipients.

## Local runtime receipt — 2026-10-20

Dedicated source-aligned worktree on the branch above, uncommitted implementation under review. Frontend `http://127.0.0.1:5190` PID82894; API `http://127.0.0.1:8010` PID87138, same checkout/backend. Listener working directories, Vite proxy target and rendered branch indicator verified. PostgreSQL loopback55460, separate synthetic database `auto_reply_routes_20261020`, sole existing migration head185; Redis loopback6386/index14. Synthetic staff authenticated through the real local login API. Direct and proxied readiness confirm database/Redis healthy. Standard controller dry-run identified missing configuration; the existing approved synthetic configuration was referenced in a private launcher, with no live provider credentials copied.

Only local simulated transports were used, with Twilio SDK network access explicitly denied. All three new routing/outbox/recovery feature flags stayed false. Existing local servers and databases were preserved. This receipt expires on a process, source, configuration or date change.

## Runtime acceptance

Playwright with the real isolated API and PostgreSQL, fictional contacts only:

- Historical CallRail mapping marked unselected still supplies the receiving number, without a sender chooser.
- Manual reply accepted through the simulated CallRail adapter; one durable synthetic provider call.
- Newer Twilio inbound changes the read-only sender automatically. Unsent text survives the poll and reload, then sends through the simulated Twilio adapter; one durable synthetic provider call.
- Disabling the latest receiving CallRail binding shows “Reply number unavailable” and disables sending; an unsent draft remains intact. No fallback to the older Twilio route and no extra provider call.
- Desktop1440 and mobile390 layouts verified; mobile conversation has no horizontal overflow and shows the read-only sender.

Local screenshots are under `output/playwright/automatic-reply-*.png` and are not committed. Browser acceptance is isolated, not production acceptance.

## Automated and independent gates

- Owner backend focused suites:95 passed before independent review. After the review correction, independent backend gate:97 passed on separate PostgreSQL `auto_reply_routes_gate_20261020` at the existing migration head185.
- Owner frontend focused suites:39 passed; additional narrow recovery/lineage checks passed. Changed-source ESLint clean.
- Production TypeScript/Vite build passed.
- Independent Security/QA GO:97 backend and39 frontend cases passed. Reviewed tenant/provider/address boundaries, immutable sender PATCH, uncertain-send preservation, UI drafts and added-source privacy; no unresolved gate finding. Final resolver SHA256 begins `3f73f4e1`; regression source `37b8d7f6`.

Review caught sent/delivered outbound rows without a receipt being skipped in no-inbound routing. Corrected to hold such contradictory evidence; both older-route and default fallback regression cases passed in the independent gate. Querying only the newest timestamp plus ties is an optional future performance refinement; the current contract uses persisted timestamps and does not promise perfect chronology across provider clocks.

## Release boundary

Implementation `4f8fe2e9` is submitted as draft [PR596](https://github.com/mecaniser/truck-pit-stop/pull/596). The pre-push scanner flagged24 phone patterns; each is a fictional +1500555 test value, confirmed against the added source. No schema migration, provider registration, forwarding change, real SMS, customer automation enablement, merge or deployment occurs in this task. Twilio registration is handled in a separate user-owned chat. Protected CI and deployment acceptance remain required before release. Rollback is the code revert, with any resulting sender-selection exposure reviewed before release; held/unknown send operations must never be blindly retried. Preserve TrucksParkingHub inbound routing, DBN/ETS identities, CallRail forwarding and all prior conversations.

## Authorized release attempt — 2026-10-20

User authorized sequential merge/deployment of589,591,594,596. PR589 passed all six checks in39462290395 and merged as064db78cccf57be3f26d559972bdecfe3df4e233; checked and merged trees match. PR591 integrates that exact main asb9995fa8 with only an additive board conflict resolved, pilot source unchanged; fresh CI39467210649 pending. Later PR runs were stopped because each needs the preceding actual main revision before its required checks. No gate was bypassed.

Railway rejected an exact064db78c deployment request: `Deploys have been paused temporarily`. The official [Railway build incident](https://status.railway.com/incident/JUA1PC5H) confirms a provider-wide pause. Current production remains healthy onb772fb56399ce45f16096cb7c94d36c6215170f2 / Webeb92d1da-5ae8-4c0f-bec5-dbe00b157287, so the new reply UI is not live. Web and Worker effective settings independently confirm tenant routing, automated outbox and recovery allfalse. Baseline PostgreSQL has199messages,14threads,772customers,3CallRail conversations,16CallRail bindings at185, with no repair reply-route table. No SMS/provider/registration action or customer automation activation. Finish protected CI, deployment identity and authenticated UI acceptance after provider recovery before marking released.

Independent integration preparation1cce518b combines reviewed PR594 and PR596 production source without changes to either implementation. Only additive board history conflicted and both sides were retained. Independent gate97 automatic/CallRail/tenant plus40 signed reply-route cases passed on separate databases at sole head186; privacy/whitespace passed. This preparation remains local until actual preceding main commits are integrated; remote PR596 still requires its fresh protected checks. No production migration or route activation occurred.


## Production acceptance — October 20, 2026 EDT

- Final protected PR head: `dc147ab482a1b77ec59c11a5a4a9788e441b1927`, including actual PR600 main. All six checks in run39508728270 passed; full backend3444passed/386skipped. Test-only identity-gate correction independently reviewed with23focused cases; production SMS implementation unchanged.
- Normal guarded squash merge: `392057cdc46fc13c6cb44c85ccfc2d5c181727b1`. Exact Web deployment `2aeea14e-c0ee-41ba-8f39-9a680cc598eb` and Worker `4b74a8a7-5215-4d4c-982d-1631c756cde1` both SUCCESS. API and website build-version serve that SHA; database and Redis readiness pass.
- Effective `SMS_TENANT_ROUTING_ENABLED`, `SMS_AUTOMATION_OUTBOX_ENABLED`, `SMS_RECOVERY_ENABLED` false on both running services. No route approvals seeded; production migration186_twilio_reply_routes remains empty. Read-only retention199SMS,14threads,772customers,3CallRail conversations,16bindings unchanged.
- Authenticated production Messages browser acceptance: giant sender chooser absent; existing DBN conversation shows readonly Replying from+1***1896; owner test inquiry shows Replying from+1***6600, matching its receiving number. Existing DBN and inquiry histories retained; legacy Twilio conversation also derives its historical sender.
- Existing identity-held contact shows Verify and link this contact before replying with disabled Send SMS; disconnected WhatsApp shows Not connected/This channel is not connected yet with sending disabled. These are observed live contact/channel holds. Invalid authoritative SMS-route evidence/disabled-binding holds were verified separately in isolated integration, rather than manufacturing unavailable routes in production.
- Desktop screenshot inspected, layout usable. Prior isolated mobile acceptance remains the compact-layout evidence. Original DBN conversation and SMS channel restored; no draft entered, no Send/consent/service-update/assignment/resolve action. No real SMS or provider/forwarding/registration changes. Screenshot kept private outside the public repository.
- Duplicate post-merge main39518881331 shares the checked tree and actual six-suite coverage; cancellation is authoritatively confirmed, not treated as a passing check. Local release documentation commits preserve receipts without another source deployment or CI restart.
