# ETS cached hold recovery

Board DB-ETS-FRESHNESS; owner Backend & Integrations; high-risk source ordering.

## Contract and acceptance

The source adapter may recover a read-unavailable diagnostic when every current
invoice envelope is within 24 hours and has no failed-read/capacity watermark.
The existing envelope writer only clears such watermarks for a strictly newer
source read. The positive observation retains its actual source timestamp, even
when that precedes the later cached-data diagnostic. Direct persistence callers
keep strict timestamp ordering. Other hold reasons, invalid completion status,
manifest conflicts and canonical-root changes remain held. Source sequence and
canonical service idempotency are unchanged. No wire fields, migrations, financial
mutations, Google calls or import/collector execution are introduced.

Acceptance includes delayed fresh source success, later genuine source failure,
capacity, stale data, canceled service, other hold reasons, changed canonical root,
one failed invoice among several, repeated capture idempotency and unconfigured
tenant exclusion. No recovery changes existing financial evidence or timestamps.

## Local runtime receipt (2026-10-23)

Branch `codex/ets-cache-hold-recovery`, base `8346e1bd`. Isolated clean checkout at
intake; no frontend5173/backend8000 listeners. Approved backend configuration is
absent, so local serving is blocked; no credentials copied or services replaced.
This backend-only change uses synthetic unit fixtures and never invokes a
collector or Google provider. Browser acceptance is not claimed.

## Release gates

Owner verification: 137 focused ETS completion/evidence, signed delivery and native
completion tests pass; diff integrity passes. Independent QA/security reviewer returned GO after the final service-identity
equality guard, rerunning 102 focused tests with no findings. No merge,
deployment or production behavior proof yet. After protected CI and coordinated
Web/Worker release, verify normal capture produces a new signed evidence receipt
with original source time and stable service identity, while existing Google
submission identities remain unchanged. Roll back code on unexpected positive
recovery of a real later failure or identity conflict; do not replay submissions.

Release uses the existing GitHub protected six-check workflow and normal Railway
Git-backed Web/Worker deploy at the reviewed merge SHA. Run the repository's
read-only `scripts/release_receipt.py` against the PR; independently verify Worker
SHA because that script covers Web only. The application service module changes;
no ETS collector scripts or watched collector configuration change, and no manual
collector run is required. Keep ETS Sync deployment unchanged.
