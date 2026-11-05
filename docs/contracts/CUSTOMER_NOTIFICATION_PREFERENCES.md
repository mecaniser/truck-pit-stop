# Customer notification preferences — v1

Owner: Architecture & API Contracts. Implementation accountable: Backend & Integrations.
High-risk lane: tenant-scoped persistence, migration and delivery-worker enforcement; independent QA/Security required.

## Contract

GET /auth/me/notification-preferences and PUT at the same path require an active customer session with a current tenant/customer mapping. No customer/tenant ID is accepted from the client. Wrong role403; missing/wrong/deleted customer404; no cross-shop fallback.

Response: context_key (SHA256 of feature namespace, tenant ID and customer ID), revision (0 before first save), invoice_email, invoice_sms, repair_email, repair_sms, has_email, has_phone, sms_opted_out. All four choices default true to retain existing delivery policy; legacy browser-only switches are not imported.

PUT requires expected_context, base_revision and all four strict Boolean choices; extra/null/invalid fields422. Context or revision mismatch409 with no write. Lock the customer while updating; a separate per-tenant/customer preferences row avoids changing contact-details timestamps. Atomic full update increments revision. GET never creates a row.

## Delivery

Preferences apply to the current shop's customer account, shared across browsers/devices. Explicit template classification:
- invoice email: invoice_created, invoice_reminder_email.
- invoice text: invoice_reminder_sms.
- repair email: work_started.
- repair text: work_started_sms, work_complete_sms, ready_pickup_sms.
Real billing customers retain their preferences when an invoice snapshots their delivery address, including authorized collection handoffs. Only a legacy internal-fleet placeholder with a separate external fleet billing contact has no customer preference scope. Resolve the payer from existing financial relationships, never from an email-address lookup.

Security/account notices, receipts, approval requests, staff notifications, explicit invoice resends and direct shop conversations remain outside these optional automatic-update switches.

The actual email send service, durable email worker and legacy/durable automated SMS delivery paths must consult the same persisted policy. Durable queued messages recheck at dispatch. SMS STOP/consent, sender, tenant, identity, idempotency, domain eligibility and ambiguous-provider-outcome safeguards remain authoritative; turning a preference on never opts a customer back into SMS. Rejected/suppressed attempts must have no provider ID or sent timestamp and must never be marked sent/delivered. Use existing failed/rejected/dead audit states with an explicit preference-suppression reason; do not introduce enum values that break rollback.

Preference changes affect future dispatch; already-dispatching messages may arrive. Enabling does not resend previously rejected or held events. No scheduler, replay, catch-up or real customer message is authorized by implementation/testing. PM reminders have no customer delivery path and remain clearly unavailable.

## UI and errors

Use separate Email/Text choices for supported invoice and repair updates, explicit Save changes/Cancel, saved confirmation only after server acknowledgement and scope-bound query/mutation state. Save writes once; unknown write outcome requires readback/reload, not automatic resend. Revision conflicts preserve the draft and offer explicit reload with the existing in-app discard modal. Generic account departure confirmation protects dirty notification drafts. Missing contact/SMS opt-out state is explained; no fake delivery promises.

## Acceptance

Tenant/customer/role/soft-delete rejection; wrong context; conflict/concurrent saves; default compatibility; each channel/category's enabled/disabled dispatch; SMS global opt-out preserved; mandatory/staff/manual messages unaffected; queued email/SMS recheck; no provider call for suppressed delivery; no automatic replay on enabling; browser reload persistence, dirty/cancel/failure/conflict states, session/shop change, keyboard/mobile. Migrate a new isolated local database; no production/customer preference or provider mutation during testing.

## Release and rollback

Apply additive migration204 before the API and all email/SMS worker processes; do not start a new worker against schema203. No backfill is needed: absent preferences retain existing policy. Deploy the UI only when its GET/PUT endpoint is ready. Restart existing delivery workers to load enforcement before exposing the controls; old workers cannot honor the new policy. Smoke-test with an authorized synthetic customer, inspect suppressed audit reasons, and observe provider/worker errors without sending test messages to real customers. Do not replay dead/rejected events.

Rollback the UI independently while retaining migration204 and backend/worker enforcement. A blanket rollback to pre-preferences senders would ignore saved opt-outs and is unsafe. For a backend regression, retain enforcement and forward-fix; if it cannot run safely, pause affected optional producers/dispatchers during remediation. Do not downgrade/drop the preference table in production or reset SMS consent/STOP. Escalate any emergency pause that also interrupts essential notices.
