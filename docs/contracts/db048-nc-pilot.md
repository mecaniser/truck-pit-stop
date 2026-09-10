# DB-048 NC-only production activation

Owner: Release & Reliability; backend gate correction owned by Backend & Integrations.
User approved shop-only activation, required accounting configuration and historical
reconciliation. No new charge, refund, cross-tenant enablement or destructive cleanup.

Target: Truck Pit Stop NC, tenant828acd84-38bf-4a66-8fa1-cdf076f4e241,
slug truck-pit-stop, live QBO realm9341456094535202. Browser active shop verified.
Wisconsin tenant2b45a36a-8630-48ec-aed3-3a9c5a752706 remains unchanged.

## Acceptance before activation

- Central QBP global-plus-tenant allowlist gate protects new canonical and legacy
  charges and new legacy refunds, guest preparation and provider selection; empty/malformed production
  list fails closed. Explicit nonproduction sandbox retains test compatibility.
- Negative tests cover a second connected tenant, missing identity, invalid list
  and global-off. Existing durable reconciliation is not disabled by rollout gates.
- Independent Security/QA approval, protected CI and deployed exact SHA required.
- Canonical attempt-linked payments must be excluded from legacy scheduled and
  manual reconciliation before provider calls or status changes; the legacy
  accounting writer must refuse them. Existing unlinked legacy payments retain
  their prior reconciliation path.
- NC configuration uses verified live realm/account/item/tax-code identities,
  one accounting writer, immutable versioned configuration and verified factual
  historical baseline. Do not infer rates or manufacture payment details.
- Enable API/worker gates only with target-only allowlist; Stripe stays disabled,
  other tenant flags remain false. Verify target readiness and nonpilot denial.
- On failure, stop new attempts, preserve audit/history and durable reconciliation;
  no automatic refund, database downgrade or provider record deletion.

Discovery: both NC and WI are connected with accounting/payment scopes; all
tenant rollout flags false, production provider configuration/backfill tables empty.
The old global flag alone would unlock WI legacy checkout, so it remains false
until the correction is deployed. Existing release96f0c865 remains healthy.

## Accounting preparation verified 2026-09-10

NC-only immutable configuration version 1 binds the verified live realm above.
Account mappings: clearing/check deposit 9, Zelle/checking 155, processor expense
119, sales-tax liability 152. Added fee-income account 166 and service item 11;
existing item 6 was not modified. Existing tax code 10/rate 14 matches the shop's
unchanged 8.25% setting; the customer card-fee setting remains unchanged.

Historical baseline cutoff 2026-09-10T05:50:51Z is verified with 1,380 settlements,
two supported payment attempts and 1,435 ledger events. Imported unsupported
tenders retain historical treatment rather than invented processor details.
Readback verified_at: 2026-09-10T05:53:31.917661Z; error_summary null.
Before/after fingerprints match for all other tenants' records, NC legacy payment
amount/status/method and invoice total/status. Accounting links remain 0 and
provider outbox remains 584: no historical provider posting or new payment.

Preparation script SHA256:
`a7208b1b87aa1583f2c33c29e013978289af6316a2cf44dd85eccb8de5ace283`.
Private pre-activation custom-format database backup was created and archive-read
verified; no restore or destructive cleanup performed.

Rollback: remove NC from the production approval allowlist and disable its tenant
rollout flag to stop new admission. Preserve durable charge/refund reconciliation,
configuration versions, provider objects, baseline and audit history.

Final NC-only activation runner independently reviewed at SHA256
`36af4f01b8f95ba53cb065a9b1ed9e0d47067bdb463277d7663f6fcb9ddd1097`.
It requires actual production flags and an exact single-tenant allowlist, checks
prospective readiness, commits only the NC flag when explicitly applied, then
reads NC readiness and nonpilot denial in a new session. No provider operations.
ETS imports remain untouched; future newly imported legacy sources can correctly
close readiness until their factual baseline is refreshed. This is not evidence
of a second external accounting writer.

## Historical-readiness correction

PR363 passed all six checks and deployed as cd277efb. Prospective activation
correctly stopped before the tenant flag commit: one verified historical Zelle
record belongs to an archived repair order. The factual backfill preserves it,
but readiness previously required an active repair order even for backfill.
Production admission switches were returned off; no new charge/refund occurred.

Independent contract: allow an archived order only for a backfill-source attempt
in the readiness evidence predicate, retaining verified baseline, active invoice,
tenant/customer identities, reciprocal links, payment state and exact money
checks. Native/canonical attempts on archived orders remain blocked. Live charge
and confirmation eligibility are unchanged. Do not restore orders or rewrite
historical amounts. Prove the candidate against production in a read-only
transaction before another deployment and activation attempt.

Live-data candidate simulation PASS: service SHA256
`474f9b90d68ff366bd039c6921ed1cc5854acd929abb789cce0050dc725d65f4`
under read-only transaction/no-autoflush returned NC `ready` with no reasons and
both other tenants `not_ready`. All persisted tenant flags were asserted false.
This verifies candidate behavior against actual records, not deployed activation.
Diagnostic SHA256:
`56931c8c0ec5e09c8ff5d25e764b100dd7f2e425e67dfac04abe41a239bef9f6`.
