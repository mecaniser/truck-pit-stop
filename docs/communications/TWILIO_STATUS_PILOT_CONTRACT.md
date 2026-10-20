# Closed Twilio repair-status pilot — approved contract

Owner: Backend & Integrations; Architecture proposal approved by Product & Delivery Lead on2026-10-20. Scope is two explicitly simulated status messages to the user's approved number ending0486, using the existing legacy Twilio sender ending8774. No customer-wide enablement, real repair-order/status/billing edits, provider configuration changes or CallRail changes.

## Test boundary

The operator script uses only a dedicated isolated PostgreSQL database `twilio_status_pilot_20261020` on127.0.0.1:55460 as `comms_local`, through the existing approved local configuration. It creates its own synthetic tenant/customer/thread and two durable AutomatedSMSOperation records; production DBN and ETS identities are unchanged. Messages say TEST, simulated and no real repair status changed. The only event slots are `work_started_sms` and `ready_pickup_sms`. There are no order, invoice, quote, approval or payment mutations.

The live phase asserts `SMS_TENANT_ROUTING_ENABLED=false`, `SMS_AUTOMATION_OUTBOX_ENABLED=false`, `SMS_RECOVERY_ENABLED=false`, development environment and no live account/token in normal app settings. The existing outbox service may be invoked explicitly by this one operator process without enabling its producers or scheduler. Existing production legacy automated messaging remains unchanged: these three false flags preserve legacy immediate transport; they are not a global automation-off switch.

Managed tenant routing is tested separately using isolated synthetic approved bindings, explicit consent and a fake provider. Synthetic registration is never used with a real provider. Successful live legacy delivery does not certify managed registration, shared public callbacks or production automation readiness.

## Immutable authorization and budget

Recipient ending0486 and its authorization hash are read only from the fixed private `authorization.json` in the pilot state directory; fixed sender `+17755358774`; no CLI recipient/sender/body overrides. One fixed private state directory under the user's Codex state holds an immutable plan and permanent SQLite ledger across worktrees/restarts. Each approved event has exactly one provider-call budget. The claim commits before network access; a crash, timeout, missing receipt or unknown outcome permanently consumes that event budget. No reset/recreate/new-plan command exists. Only the two approved bodies, event identities, account fingerprint and phone pair may cross the provider boundary. SDK retries are disabled. Concurrent requests cannot claim the same slot twice.

An immutable24-hour plan contains only test identities, the two deterministic bodies, one reply token, creation time and a hash of the configured account SID. No credentials are stored in plan, ledger, checkout or output. Existing root `backend/.env` credentials are read in memory only inside explicit prepare/send/status operations. Normal local API/worker settings stay simulated. Provider preparation checks the fixed number exists exactly once and supports SMS without modifying it.

## Delivery and reply evidence

Exactly two operator send slots reuse durable outbox event identities; replay cannot resubmit. Provider receipt retrieval must match exact account, SID, sender, recipient and body before importing delivery status into the isolated database. API acceptance, terminal provider delivery and handset confirmation remain separate evidence. Reply polling queries only the approved pair since the plan time and imports only the exact reply token, once by provider SID, into the isolated inbox. Polling does not establish signed public-webhook acceptance. Production DBN/ETS duplicate-phone guards are not bypassed; CallRail selection, forwarding, webhooks and conversations remain unchanged.

The script prints masked/identifier-only receipts and never raw provider/DB exceptions. No provider calls are allowed during owner or independent automated tests. Independent Security/QA must approve source, closed budget, isolated dispatch/replay and managed fake routing before root performs authorized live calls.

## Verification and release limits

Required negatives: any other recipient/sender/account/body/event; changed plan/token/expiry; second plan in the fixed slot; concurrent/restarted claims; timeout consumes budget; provider rejection/no retry; mismatched receipts/replies; nonisolated database/real server credentials/any true live-phase flag; reused outbox event; revoked consent/foreign tenant/binding/sender/registration; all real order/customer/billing/CallRail rows unchanged. The root owns runtime/provider preflight and live execution. No public API or schema migration is required, and this pilot does not require a production deployment.


## Live gate: NO-GO — provider access source-locked

Root's read-only2026-10-20 provider inspection found sender1775 belongs to a verified campaign whose business/sample messages concern Right Solution Truck Parking reservations and START opt-in. That is not evidence of approval for Truck Pit Stop repair-status traffic. The user-authorized two clearly labeled technical tests do not enable or certify customer repair automation. Campaign/business/use-case alignment remains a blocker before broader repair updates, regardless of a successful handset test. No registration, Messaging Service, sender, forwarding or webhook configuration may change in this pilot.

## Identity and evidence limits

Receipt import validates the immutable planned tenant/customer and its unique normalized sender/recipient ownership, active messaging state, consent and existing customer thread before any local inbound write. It writes only that explicit thread; it never invokes a global customer/tenant inference or creates a customer. Duplicate receipt SID returns the existing planned message; a foreign receipt or rebound/deleted/opted-out identity fails closed. Tests release only their own synthetic sender claims and never modify a prepared live plan or consumed ledger.

This pilot exercises explicitly enqueued synthetic status bodies through durable outbox dispatch. It does not perform actual repair-order producer transitions or prove the full production repair workflow. Existing producer/transport tests and separate managed fake-routing tests provide their own evidence; no real order status is changed.


Independent review returned live NO-GO for the known campaign-purpose mismatch. `LIVE_CAMPAIGN_SCOPE_APPROVED = False` now blocks the real provider function before configuration, credential reads or SDK access. There is no environment or CLI override. Future matching registration review and a separately reviewed source change are required to lift this hold. Automated tests inject a fake provider only. No live prepare, provider submission or deployment occurred. Deliver this work as a draft while the registration correction remains review-only.


Public-source privacy: neither the approved personal number nor a recoverable unsalted authorization hash is stored in public source, tests or documentation. The script reads only the fixed private authorization file, owned by the current user, a regular non-symlink file with exact0600 permissions, with strict schema `{schema:1, recipient:<private E.164>, recipient_sha256:<private SHA-256>}`. Missing, malformed, duplicate or additional fields, inconsistent hash and unsafe permissions fail closed before plan state, credentials or provider access. The script never creates or changes authorization, and offers no CLI/environment override for path, phone or hash. Root may write only the user-approved number privately after review. Changing that file cannot reset an existing immutable plan or consumed event budget. Tests use temporary private authorization with a fictional number. Prose uses only the last four digits. The permanent live campaign hold remains unchanged.
