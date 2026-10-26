# DB-036 populated trip completeness proof

Status: independent source/security GO; Backend accountable. The diagnostic_gate independently passed 44 focused Python tests and 51 Node tests. Runtime read-only canary remains pending and is required before imports. Branch `codex/motive-trip-populated-proof`, base `292586b32949ba71ef68a943481650e69202d6e1`. No production authority in this worktree.

## Evidence and user outcome

The existing collector can accept a quiet 50-row loaded page before a later page appears. Actual passive observation on September 1 found two naturally issued provider JSON responses with exact date parameters: root `total=87`, `per_page=50`, and `driving_periods` arrays of50 and37 wrapped in `driving_period`. Company gates passed; response start/end timestamp fields were present. The response gap exceeded nine seconds. A footer describing loaded rows is not authoritative total evidence.

Goal: certify populated source completeness only when an authoritative total and unique response identities exactly reconcile with captured rendered source identities. Never manufacture empty, overwrite retained trips, or advance coverage from incomplete observations.

## Contract before implementation

- Listen passively on the report page before navigation; never fetch, replay, intercept, mutate request headers or invent endpoints. Exact approved response origin `https://api.keeptruckin.com`; app-origin observations alone do not satisfy the grounded provider proof.
- Each invocation/window owns a fresh epoch and listener. Accept only browser-issued requests initiated for that epoch's page and exact single-day requested date pair. Reject duplicate/conflicting date parameters, wrong origins/windows, stale/inflight prior-window requests, unknown identity shapes and malformed responses. Only successful JSON responses with the grounded driving_periods structure qualify.
- Existing authenticated company/timezone gates remain before/after collection; source proof is embedded in the current tenant/actor/company-bound immutable source document. No reuse across companies, days or executions.
- Stable nonnegative integer root total and per_page, bounded by existing row limit. Distinct page/response identities must cover exactly total, and their canonical provider+departure identities must equal captured DOM identities. Reject duplicate pages/identities, conflicting versions or totals, truncated responses, invalid IDs/timestamps and missing tail. Mere summed page lengths or duplicate footer counts never prove completion.
- The adapter conditionally requires documented `driving_period.id`, nested `vehicle.id` and ISO-offset `start_time`. These remain unverified dashboard-schema hypotheses: missing or invalid fields fail before import. Response timestamps map to the existing New York rendered minute; distinct IDs collapsing to one provider/minute fail bijection rather than merge. The runtime read-only canary must prove this exact crosswalk before writes. No count-only fallback exists.
- Versioned populated_proof carries window, epoch/request observations, authoritative total, page/identity counts and a deterministic identity digest tied to source rows. Persist no raw response bodies, secrets, URLs or network headers. Hold raw response material only in bounded container memory and dispose after reduction.
- Decoded body limits and sequential reads retain the explicit Playwright allocation caveat. Hard invocation timeout and source row limits remain. Loading signals can delay capture; no quiet timer can replace proof.
- Python preimport validation and receipt-derived coverage indexing both require valid populated proof. Reopen legacy unproven populated days; preserve source/receipt artifacts and existing database rows. Preserve latest mapping and observation signals before filtering invalid proofs to avoid resurrecting obsolete scope.
- Missing proof is systemic capture failure, not the narrow preimport prior-coverage rejection permitted to continue by PR655. No receipt/cursor advancement on failure; ambiguous import recovery remains unchanged.
- No database migration or changes to tenant, membership, reviewed binding, immutable identity or readback guards. Re-import through existing idempotent path after recapture.

## Acceptance and negative fixtures

Actual collector integration:50-row pause beyond9s remains incomplete, delayed37 completes only with total87 and matching distinct identities. Negative cases: duplicate page, overlapping/duplicate identities, changed total/per_page, missing page, wrong request epoch/day/origin/company, malformed provider IDs/timestamps, body limit/timeout, stale callbacks afterclose, response/DOM identity mismatch despite equal counts. Python validates same proof and rejects legacy populated receipts without deleting data; mapping-change and latest-observation regression tests remain. Existing retained-row checks and committed-receipt recovery still pass. Independent source/security review then exact runtime canary are required before historical collection resumes.

## Local runtime receipt

New worktree clean at intake; no5173/8000 listeners. Mandatory controller switch dry-run blocked by missing `backend/.env` and frontend Vite. No secrets copied, servers started or local-browser visibility claimed. Focused isolated tests remain available.

## Verification and release canary

Owner checks:135 focused Python trip tests passed, including retained rows, immutable replay/recovery, placeholder authorization and receipt/index behavior;51 Node tests passed, including delayed50→87 actual collector integration, malformed/duplicate/conflicting response negatives, request epoch/inflight sealing, populated-versus-empty contradiction and exact canary launcher. Two existing Python warnings remain. Protected CI now includes the new populated suite, and Docker layout test includes its helper.

Read-only canary command in the reviewed image:

```sh
node /app/scripts/motive_sync/probe_trip_populated.cjs --read-only 2026-09-01
```

This entrypoint calls actual collectWindow with a no-op checkpoint, verifies the produced proof through the stdlib-only Python validator over container-local stdin, and rechecks company/timezone before emitting only aggregate counts. It does not call collect/importDay or any importer/database API and creates no source/normalized/attempt/receipt artifacts. A300second hard deadline bounds the job. Browser temporary state is ephemeral; no session export occurs. Local fixture verifies positive preflight and browser-stage static error redaction without auth/network. Actual candidate fields/parity remain unproven until release owner runs the independently approved canary.

Release owner must prevent overlap, reconcile exactly one diagnostic start, and restore effective normal deployment command before normal cron. Missing candidate fields, identity disagreement or incomplete pagination keeps populated imports on HOLD. Do not weaken proof to obtain a passing canary.
