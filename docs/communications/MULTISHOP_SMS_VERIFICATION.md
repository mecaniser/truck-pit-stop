# DB-COMMS-005 isolated verification

2026-10-16 · Backend & Integrations accountable · branch codex/multishop-sms-onboarding.

Implemented persisted owner/admin onboarding drafts, version conflict checks, review-only preparation/export, explicit customer consent evidence, immutable operator-configured business bindings, credential-reference routing, manual/automated/legacy dispatch guards, and account-scoped inbound/status callbacks. Migration179 is additive with no consent backfill. No registration submission or tenant activation route exists.

## Verification

- Isolated PostgreSQL communications_local at loopback55460 upgraded178→179 successfully; single Alembic head179. Existing synthetic data preserved.
- Combined focused backend suite:186 passed, covering onboarding/routing/manual/automated/callback/legacy and live-test guard. Independent source/security gate127 backend and12 frontend checks passed. Two reviewer findings fixed: rollout rollback fallback and missing inbound MessageSid.
- Frontend:24 communications tests pass; changed-feature ESLint and production TypeScript/Vite build pass.
- HTTP acceptance script verify_multishop_sms_local.py passes after final backend restart: two tenant drafts/review/export, no provider calls from review, role/foreign-resource/field-injection/version negatives, two account/service/sender selections for the same recipient, three concurrent identical requests per shop produce one operation/provider call, changed payload409, signed callbacks/replies, wrong-token/account/sender denial, duplicate inbound and monotonic delivery.
- Runtime uses the real LiveSMSSender path with a fake per-context client, persistent account/service/sender/recipient ledger and global Twilio network denial. Credentials are synthetic only; recovery is disabled.
- Signed-in browser: owner sees SMS setup, saves synthetic support phone, prepares ready_for_review state, returns to inbox and sends through fake managed provider; draft clears and persisted row becomes queued. Synthetic replies and delivered statuses from HTTP workflow visible.390px onboarding layout has no horizontal overflow. Desktop screenshot: .impeccable/review/multishop-sms-onboarding-desktop.png.
- Local runtime alignment: frontend5186/PID56726 and backend8006/PID53925 share communications-foundation checkout, frontend proxy targets8006, readiness database+Redis OK. Branch/source and rendered onboarding verified. Local URL http://127.0.0.1:5186/ is aligned and browser-verified. Runtime receipt expires on server/branch changes.

## Production evidence boundary

The existing production source supports SMS submission through a global Twilio account. Read-only provider inspection of the latest30 outbound messages for the configured sender returned16 undelivered30034 and14 failed21211, with no delivered records in that sample. This is bounded evidence about that sender/sample, not a conclusion about all historical production delivery or other numbers.

## Holds and rollout

SMS_TENANT_ROUTING_ENABLED defaultsfalse. Never-migrated tenants preserve existing legacy behavior. Once a tenant has a managed binding, disabling rollout blocks new and pending sends instead of falling back to global credentials; historical receipts retain account authentication. No existing number, profile, campaign, production flag, webhook or production database was changed.

Registration submissions, provisioning, merge and deployment remain HOLD for user review. Customer legal identity/evidence and real registration approval, live handset/reply/public signed-callback acceptance, protected CI and a reviewed suppression-preserving migration remain release gates. Independent report: MULTISHOP_SMS_INDEPENDENT_REVIEW.md. No live registration or delivery acceptance is claimed.
