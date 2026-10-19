# Multi-shop SMS contract

DB-COMMS-005 · Architecture & API Contracts · 2026-10-16

Status: implementation contract; isolated tests only. Registration submissions, paid provisioning, live account changes, migration of existing numbers, and deployment are on HOLD.

## Outcome and compatibility

DieselBridge is the platform; each independent legal shop business has its own provider account and registration. A legal business can own several tenant locations, but common branding never grants cross-tenant inbox access. First-release onboarding creates a business for the authenticated tenant. Linking additional locations is platform-admin-only and requires explicit recorded ownership verification; no automatic matching by name, domain, or phone.

Current production code can send through its global Twilio client: `messaging_service.send_sms_with_tracking` uses tenant sender or the configured global sender; shared inbox and automated sender use the same global account. This establishes implementation capability, not a historical delivery rate. The failed recent campaign/test is not proof that all past production texts failed.

Use an explicit `SMS_TENANT_ROUTING_ENABLED` rollout flag, default false. Disabled retains existing production behavior until reviewed migration. Enabled means ALL customer/staff SMS paths use tenant bindings and fail closed when absent; there is no per-tenant fallback to the platform account. Isolated acceptance must enable this flag. UI must distinguish legacy configuration from a verified multi-shop connection. No old queued intent may silently acquire a new binding.

## Persisted data

Additive migration, with no real provider calls or production backfill:

- `MessagingBusiness`: UUID; legal name, trade name, website, support contact, consent evidence URL, privacy/terms URLs, authorized-representative name/email, service-message description/sample drafts; draft version; state (`draft`, `ready_for_review`, `submitted`, `in_review`, `approved`, `rejected`, `suspended`); rejection reason; actor/timestamps. No tax identifiers, credentials, or identity documents in this ordinary record.
- `TenantSMSBinding`: UUID; tenant_id; business_id; account SID; Customer Profile, Brand, Campaign, Messaging Service, and sender SIDs; normalized E.164 sender; opaque credential reference; registration status; enabled; last verified time; immutable revision; retired_at. One current binding per tenant; active sender unique across tenants, even when business/account shared. Same provider account may serve multiple explicitly linked locations only under the same business. Shared sender routing across locations is unsupported.
- Consent evidence: tenant_id, recipient kind/id, normalized phone, purpose (`service_notifications` initially), status (`granted`/`withdrawn`), source, disclosure version, collected_at, actor, created_at. No existing customer receives consent by migration. Staff/tenant-contact automated recipients also require purpose-appropriate evidence under managed mode; do not silently exempt them.
- Manual/automated operations and persisted SMS: binding_id plus immutable account SID and messaging-service SID context. Existing sender/body/recipient snapshots stay immutable. Nullable added fields represent legacy records, never an invitation to infer a managed account at dispatch. Provider SID lookups and idempotent inbound handling must include account context.

Binding configuration is versioned: create a replacement binding rather than rewriting credentials/account/sender under an in-flight operation. Disabling a binding is immediate. Credentials may rotate behind the same reference only for the same account. Audit configuration changes and readiness decisions; avoid logging bodies, secrets, or full phone numbers.

## API and permissions

Place under `/api/v1/communications/sms` (names may be aligned with existing router without changing semantics):

| Method/path | Actor | Behavior |
|---|---|---|
| GET `/onboarding` | Active tenant owner/admin | Own draft, readiness blockers, redacted connection summary, review state |
| PUT `/onboarding` | Active tenant owner/admin | Save only descriptive draft fields with `expected_version`; server derives tenant |
| POST `/onboarding/review` | Active tenant owner/admin | Validate draft, mark `ready_for_review`; NEVER calls Twilio or provisions anything |
| GET `/onboarding/review-package` | Active tenant owner/admin | Export review-only legal/shop identity, sample messages, consent evidence and unresolved fields |
| GET `/consents?customer_id=...` | Existing authorized messaging staff | Own tenant's consent status and evidence |
| POST `/consents` | Existing authorized messaging staff | Record explicit grant/withdrawal evidence; customer belongs to actor tenant; no implied grant |
| Operator binding mechanism (no public activation route) | Platform operator / isolated fixture | Store versioned local binding/verification metadata after validation; normal tenant cannot set account, credentials, approval or enabled status |

Tenant onboarding body example: `{ "expected_version": 1, "legal_name": "Example Repair LLC", "trade_name": "Example Repair", "website_url": "https://repair.example", "support_email": "help@repair.example", "consent_source_url": "https://repair.example/sms", "privacy_url": "https://repair.example/privacy", "terms_url": "https://repair.example/terms" }`.

Response example: `{ "version": 2, "status": "draft", "submission_enabled": false, "connection": { "status": "not_configured", "sender_last4": null }, "blockers": ["consent_evidence_required", "provider_registration_required"] }`.

Unknown/foreign resources:404; no role/active tenant access:403; stale expected_version or changed binding:409 with stable code; malformed fields:422. Input schemas reject extra fields, particularly approval, provider IDs, credential references and tenant IDs. URLs must be HTTPS public-style URLs; save does not fetch submitted URLs. Never return credential references or tokens to tenant APIs. Ordinary operators cannot self-assert provider approval.

## Provider and dispatch contract

Central resolver accepts `(db, tenant_id, binding_id?)`, returning a checked immutable context. Credential reference selects only an allowlisted server-side configured secret map, never arbitrary environment names, file paths, URLs or tenant-provided tokens. Secret payload's account SID must match binding account. SDK transport retries disabled; existing bounded timeout, one-attempt durable claim, ambiguous hold remain.

Readiness requires active tenant, SMS enabled, current enabled binding, approved registration, verified sender/service/account association metadata and resolvable credential reference. Fake provider fixtures may attest synthetic verification; production proof must come from an explicitly authorized provider verification procedure, not owner-entered data. Send with the binding's exact `from_` and `messaging_service_sid`; never let sender-pool selection cross shops.

At enqueue snapshot binding/account/service and include them in payload identity. At dispatch recheck binding active, immutable context unchanged, consent still valid for exact tenant/phone/purpose, opt-out absent, and existing identity/rate-limit rules. A binding rotation rejects pending old binding with `binding_changed`; uncertain/accepted operations remain held/terminal. Same idempotency key/event continues to return the original intent; it cannot create a replacement under a new account. Legacy sends must pass through the central resolver under managed mode, including all direct messaging and notification fallback paths.

## Webhooks and isolation

`AccountSid` is an untrusted routing hint, not authorization. Resolve a known account's reference, validate signature with that account's token, then enforce all ownership constraints. Unknown account/missing account or invalid signature fails without mutation. No global-token fallback under managed mode. Respect the existing public callback URL contract; do not add trust in arbitrary tenant callback URLs.

Inbound requires exact `(AccountSid, normalized To)` binding and current tenant ownership. Status requires `(AccountSid, MessageSid)` operation/message ownership and matching sender/service fields when supplied. Never find a row by SID alone and then mutate it under another validated account. Dedup key is account+message SID, and parallel replays must insert once. Preserve monotonic delivery transitions and current early-callback safeguards. A sender/service mismatch must not move a row to another tenant. Retired binding credentials remain available for authenticated receipts for its historical operations; retirement blocks new dispatch but does not discard delivery evidence.

STOP withdrawal affects only the matched tenant/program; shared customer phone in another business does not import grant or withdrawal. Existing opt-outs remain authoritative. START must not fabricate historical consent evidence; explicit verified re-enrollment is required before managed dispatch. No duplicate automatic STOP/HELP replies; leave provider response ownership unchanged in this increment.

## Required isolated acceptance

Two tenants, two businesses, two fake accounts/tokens/services/senders, same recipient phone, separate customers and consent; third unmapped tenant. Deny outbound network in test runtime.

1. Owner draft persistence/export/version conflict; staff/foreign-tenant and approval injection denied; review action makes zero provider calls.
2. Manual, automated customer, staff, and legacy path all select their own account/service/sender; missing/rejected/suspended binding and absent secrets block with zero calls.
3. Consent missing, withdrawn, foreign tenant, or changed phone blocks; no global legacy fallback when flag on. Existing opt-outs survive additive migration.
4. Concurrent replay makes one provider call; changed payload conflicts; timeout holds; restart/recovery never retries accepted/unknown intents.
5. Binding replacement before dispatch rejects; historical receipt on retired binding remains accepted only for its original account.
6. Valid A signature cannot mutate B by forged AccountSid, To, or MessageSid; wrong token rejected; duplicate inbound inserts once; status monotonicity preserved.
7. Same phone receives A and B messages only with separate grants; STOP A does not alter B. Tenant inbox queries never include other business data.
8. Real PostgreSQL migration upgrade and isolated workflow, focused backend tests, relevant frontend tests/build and signed-in browser onboarding/inbox proof; independent Security and QA reviewers cannot be implementers.

## Ownership handoff

Architecture owns this document only. Concrete proposed split:

- Backend schema/onboarding: `backend/app/db/models/messaging_business.py`, `backend/app/schemas/sms_onboarding.py`, `backend/app/services/sms_onboarding_service.py`, `backend/app/api/v1/endpoints/sms_onboarding.py`, new Alembic migration, model registry import, onboarding tests. Own additive binding snapshot columns in `communication.py`, `automated_sms.py`, `sms_message.py`; coordinate names before routing owner uses them.
- Routing: new `backend/app/services/tenant_sms_routing.py`, existing `communications_service.py`, `automated_sms_service.py`, `messaging_service.py`, `twilio_webhooks.py`, routing/dispatch/callback tests. Own shared credential-reference resolver. Do not edit onboarding-owned schema/model files without handoff.
- Frontend: onboarding view/client/types and focused UI tests after API schema confirmation. The UI may display connection blockers and prepare a review package; it must not show a working Submit to Twilio or Activate button.
- Parent: shared settings flag, router registration, isolated fixtures/runtime alignment, board and integration verification. Preserve previous live test CLI's consumed one-call ledger and recipient guard; it cannot become a general-purpose bypass.

Exact module names can be adapted together before implementation; the behavioral contract and tenant isolation remain mandatory.

Release remains blocked pending user review, legal identity and published consent evidence, explicit real registration/provisioning authority, verified registration, live handset/reply/signed-callback tests, independent gates and protected CI. No registration submission endpoint should be enabled in this increment.
