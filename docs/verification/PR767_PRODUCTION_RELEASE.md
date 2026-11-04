# PR767 production release — November3,2026

Accountable product owner: Frontend & UX. Release execution: Release & Reliability. User authorized merge/deploy and live desktop/mobile verification without real payments or financial-record edits. The user assigned manual prepayment bookkeeping to their accountant.

## Exact source and runtime evidence

- [PR767](https://github.com/mecaniser/truck-pit-stop/pull/767) reviewed product sourcea4f8d931; release-intake documentation-only head7840380e890e935cfb5a918fb8425f97b613fce1. [All7 final checks passed](https://github.com/mecaniser/truck-pit-stop/actions/runs/41768903566).
- Squash merge446b87d44ee8ede9b17472b0d2164ed343998e4b at2026-11-04T03:52:04Z (November3 local). Merge and checked head have identical tree3f178c903b961fc531111b4f80d7e05d22a14788.
- Web/API deploymentdca89db1-8ee4-4cdc-b6c5-ba517d4c5593 SUCCESS on that merge. Bothwww/api build-version return exact446b87d4; database/Redis readiness pass.
- Worker deployment43a3c7cd-1e72-4241-a4bc-aaabf2fd0a07 SUCCESS, runtime446b87d4/schema200. Registered expiry task and Beat60-second interval verified read-only; no task manually run.
- Migrations198/199/200 and required typed evidence columns present. All9 new request/booking/receipt/application/manual-review tables contain0 rows after release verification. No booking, request, charge, application, ACK or refund-verification submission.
- Previous ETS and separately pinned integration deployments were preserved. No deployment of an unrelated integration was initiated.

## Live acceptance and boundary

Actual signed-in Elis customer account,1440x1000 desktop and390x1100 mobile. Today-first fleet home, exact Unit603 scope, common-needs discovery, DOT search, service choice once, request optional date/details/final review and preserved vehicle context pass. No horizontal overflow at390px; reviewed action controls44px high. Stop before Send request. The existing invoice remained pending confirmation; no second payment was requested or submitted.

Reserve a time is correctly disabled under current production readiness, with customer-facing unavailability text. No card details entered, tokens created, payment attempts submitted, or holds created. The full prepaid checkout/success/expiry paths were previously accepted with isolated fictional fixtures; this live read-only pass is not provider payment certification.

Actual local screenshots: `/Users/sergio_m1_promax/.codex/visualizations/2026/10/31/01a1903f-abe6-7d20-bd1a-7bf7df5f4a4a/portal-implementation/release-767/`. Private read-only runtime/financial receipts: `/tmp/pr767-release/`.

## Prepaid activation remains blocked

BothWeb andWorker booking enable/approved-tenant flags remain absent/off. Active provider configurationv1 is an immutable not_ready snapshot. QBO realm/account mappings and scopes match; stored access token is expired and refresh token remains valid. No OAuth refresh, provider configuration write or feature activation was performed.

Fresh merged readiness is blocked by401 historical raw ETS mirror invoices without settlement rows (337paid/64sent). This is not evidence of401 unpaid customer debts. The earlier402 cohort included one legal bill-to collection mismatch; PR767 already fixes that predicate, and the current handoff settlement matches the approved billed customer. Do not reassign the customer or rewrite the settlement to satisfy an obsolete predicate.

The existing financial backfill command may create settlement/attempt/ledger rows and was NOT run under the no-financial-record-change constraint. Architecture identified a possible separate code-only correction: exclude only proven raw ETS mirror rows from tenant-wide missing-settlement readiness, keep direct imported checkout read-only, and retain all native-payment/Zelle/ancestry/source-handoff/tenant protections. This correction is a follow-up contract, not part of PR767 and not silently enabled. After its independent gate, activation still requires the normal authenticated credential-health and audited fresh provider-configuration workflow, exact TPS-only environment admission and worker readiness. Do not edit immutablev1 or force-ready values.

## Financial preservation evidence

Read-only repeatable-read snapshots before and after release match invoice, repair-order/labor/parts, quote, payment, settlement, ledger, accounting-link and source-handoff fingerprints. Normal production activity prevents claiming every database row was globally frozen: an existing pending card attempt retained its pending/receivedNULL/applied0/unapplied0 money state but its row hash/updated_at changed, and the provider outbox advanced. No new attempt count, payment or ledger entry was created by this verification. Additive appointment columns change its full-row shape. Exact changed fields of that pre-existing attempt cannot be reconstructed from hash-only baseline; this limitation is explicit.

## Small acceptance correction

Live unavailable-reservation copy repeated the request-visit fallback because the server message already contained it and the UI appended it again. The focused follow-up removes only the appended sentence, preserving the returned customer message, buttons, readiness, API and all payment behavior. Fast UI lane:28 focused booking tests pass; build/lint and exact-head CI are required. No financial code or records change.

Local preflight after switching to the owned copy-fix branch: frontend5173 PID86609 source `/private/tmp/portal-task-first-implementation/frontend`, effective API target8016, same owned backend bind; disposable database `portal_booking_fulfillment_final_qa`, environmenttest, schema200. Existing8000/8014/8015 preserved. HTTP frontend/API/proxy readiness pass. Local fallback rendering is not claimed from the available-provider fixture; existing focused tests cover the unavailable-provider branch. Final visual acceptance uses the authenticated production screen after this authorized copy correction deploys.

Rollback: keep booking admission off. The copy-only follow-up can roll Web back to verified446b87d4, which recognizes schema200. A full PR767 rollback must be a forward corrective/revert release retaining198–200 migrations and compatible schema preflight; an old197 image may not recognize the current revision. Do not downgrade198–200 or delete financial/audit evidence. No rollback trigger was observed during this release; prepaid activation stays blocked.

Current outcome: PR767 merged/deployed, request flow verified through final review on desktop/mobile, prepaid activation blocked on the explicit existing readiness issue. This item is not marked fully Done while that activation requirement remains unresolved.
