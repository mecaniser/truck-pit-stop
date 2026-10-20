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
