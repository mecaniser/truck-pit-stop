# DB-036 independent QA and security gate

2026-09-30. Reviewer: independent QA agent, no implementation participation.
Candidate: dirty `codex/db036-motive-sandbox` following
`d41f33d62c465a29235aa87758ac39af336cbbde`. Review is bounded to this local
candidate; subsequent material changes require review.
Reviewed dirty source/test/configuration digest (29 changed or new files under
`backend/`, `frontend/`, `.github/`; sorted pathname, NUL, contents, NUL):
`c03df16de277c412d6b2e91730b9c5a36bd34d7cc941a8bea9f4808a8a2bfd23`.

## Verdict

**Offline implementation QA: GO. Offline application security: GO.** No known
blocking finding remains in the reviewed scope after corrective retests.
This is not authenticated runtime, live provider, merge, deployment, or production
activation approval.

## Independently executed evidence

- `DB036_TEST_DATABASE_URL=<dedicated disposable PostgreSQL DSN> uv run --python
  3.11 --with-requirements requirements-dev.txt python -m pytest -q --tb=short
  tests/test_db036_motive*.py`: **140 passed, zero skipped**, 32.67 seconds.
  Randomized isolated schemas; no application database used.
- Frontend Vitest: `MotiveIntegration`, `MotiveFullIntegration`,
  `FleetApp.return-context`, `motiveCallback`, `apiRefreshRetry`: **37 passed**
  across five files. Includes partial-sync notices and secret lifecycle behavior.
- Independent real PostgreSQL, two-session customer-grant revocation reproduction:
  expire credentials; refresh through a synthetic provider; revoke the customer's
  company grant in a second session during inventory I/O; finish customer sync;
  roll back the caller session. Result: **403 denied; rotated refresh credentials
  remain durable**. This reproduces the actual cross-session grant change, in
  addition to the committed owner-inactivation and savepoint regression tests.
- Independent equivalent-instant history replay with UTC and UTC-minus-four
  representations: accepted as duplicate after timestamp normalization.

## Review coverage and corrected findings

Reviewed explicit customer grants, selected-tenant principal versus global user
home tenant, cross-company filtering, callback reauthorization, grant revocation,
no-store API responses, opaque signed webhook routes, raw-body size/time budgets,
constant-time signatures, receipt durability and replay, rotation/disconnect,
metadata-only webhook storage, post-mapping readings, deletion/retention, pagination,
rate-limit handling, and worker continuation. One-time webhook secret stays outside
query/mutation caches and storage; keyed connection ancestry prevents a late old
company response appearing in the next company's panel.

Findings returned to implementation owners and verified corrected:

1. Overlapped history catch-up exceeded the real client's one-day request bound.
2. Moving completion targets prevented fleets larger than five trucks completing;
   durable fixed cutoff and non-failure continuation now pass seven-truck coverage.
3. Equivalent timestamp offsets caused false event-content conflicts.
4. Customer access revocation after credential refresh lost the rotated credential
   bundle on rollback; the outer lock/savepoint flow now preserves credentials
   while denying the revoked request and rolling back telemetry changes.
5. Retention cleanup's ORM session synchronization mixed naive/aware datetimes;
   final full suite passes the corrected cleanup path.

The CI addition includes `tests/test_db036*.py` in critical backend regressions.
Real PostgreSQL cases remain opt-in via their disposable test DSN; this review ran
them locally without skips. The migrated-schema roundtrip and browser fixture
journeys are separate owner evidence in the main verification record, not claimed
as independently executed here.

## Remaining acceptance boundaries

Approved application runtime configuration is unavailable. No authenticated full
stack journey, actual provider payload, OAuth consent, live webhook subscription,
provider approval, production retention operation, merge or deployment is proven
by this offline gate. Synthetic browser fixtures cannot establish those outcomes.
