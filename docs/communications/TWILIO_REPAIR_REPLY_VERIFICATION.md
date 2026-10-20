# Repair reply route — isolated verification

DB-COMMS-014. Backend & Integrations accountable. 2026-10-20. Source readiness only; live registration/provider routing/callback acceptance and deployment remain held.

## Account and sender findings

Fresh read-only provider inventory confirms owned SMS-capable +17755358774 and +19129223939. The775 service routes inbound to TrucksParkingHub hiring; its VERIFIED SOLE_PROPRIETOR campaign describes parking reservations. The912 service defers to its number webhook, which already points at DieselBridge inbound/status URLs, but its repair campaign remains FAILED30907. Its ten most recent outbound records are undelivered30034. There is historical inbound activity; do not call it an unused spare. Provider URLs alone do not prove accepted application routing.

The user identifies Elis Tech LLC as the repair operator. Existing Elis Logistics registration is a distinct legal identity, even with common ownership. Updated correction plan explains account/profile/Brand/campaign/service/number roles and preserves existing parking, call forwarding and opt-out history. No submission, support outreach, number purchase, provider/account setting, production data or flag change occurred.

## Implementation and independent gate

Migration186 adds an empty disabled-by-default reply route table and nullable route receipt identity. No route-writing API or production seed exists. Explicit approved account/To/From maps only to a pinned tenant/customer/thread; receiver history prevents fallback after expiry/revocation. Strict signature authentication is independent of managed outbound rollout. Locking, current phone/tenant/thread checks, immutable approvals, strict receipt replay and post-wait/precommit expiry checks preserve ownership and duplicates. No outbound capability is added; prior two-event private send budgets were not opened, changed or replayed.

Initial independent gate was NO-GO: development signature bypass and expiry across lock waits required corrections; the gate database guard initially rejected its exact reviewed second database. All returned findings were fixed by the owner. Final owner suite76 passed; final independent Security/QA154 passed, including40 new signed-ASGI/PostgreSQL reply tests plus114 routing/callback/identity/messaging regressions. Missing token/signature in development, expiry while blocked, wrong account/receiver/sender, inactive/foreign/changed subjects, reserved receiver holds, concurrency, conflicting SID, STOP/START and unchanged ETS/TPH fixtures are covered. SQLite regression compatibility passes. Public added-diff privacy/whitespace review passes.

Populated185→186 migration retained SMS16, customers22, threads14 and tenants22 exactly. Canonical CHECK additions are constraint-only. A second fresh isolated database independently rehearsed185→final186; single head186 confirmed. No downgrade or history deletion was performed.

## Local runtime receipt

Branch codex/twilio-reply-route based on eb6a04fd, with the final reviewed source uncommitted at verification time. Standard runtime controller dry-run reported missing approved backend/.env and frontend dependencies; existing sessions were preserved. Approved synthetic communications configuration is referenced privately without copying provider credentials. Dedicated loopback PostgreSQL55460 database twilio_reply_route_test_20261020 and separate gate database twilio_reply_route_gate_20261020 use schema186; Redis6386/index13. The consumed actual Twilio pilot database/ledger remain untouched.

Backend http://127.0.0.1:8008 PID74951 serves this checkout; command/cwd and direct database/Redis readiness verified. All three new SMS flags false; normal server has no live Twilio account. Unsigned HTTP callback rejected400 before ingest. No frontend/UI changed or served for this backend-only outcome: authenticated page QA is not applicable, and no local UI visibility claim is made. Changed ingestion acceptance is signed ASGI integration against isolated real PostgreSQL, not an actual public Twilio webhook.

## Remaining live gates

Review correctly owned Elis Tech registration and dedicated912 assignment, verify voice/forwarding and suppression preservation, approve any provider/registration changes, then establish a fresh owner-only reply authorization before a real send-and-reply test. The old two-event outbound budgets remain consumed. No fresh handset message or actual public callback is claimed. Customer automation remains disabled pending a separate review; existing historical immediate legacy behavior is unchanged.
