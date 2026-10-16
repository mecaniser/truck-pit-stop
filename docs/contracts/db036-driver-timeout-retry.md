# DB-036: driver identity page timeout recovery

Owner: Backend & Integrations. Worker change; high-risk lane.

## Evidence and acceptance before implementation

The Oct16 daily run completed fleet1 then failed in fleet2 before_summary with ui_timeout. One same-image recovery completed fleet1 then failed in fleet2 after_summary with ui_timeout on a different vehicle. Fleet2 did not create a journal and fleet3 was skipped. Existing valid records remain intact.

The existing readDriverVehicleVin retries missing rendered VIN values but lets a Playwright TimeoutError from the fresh-page reader abort immediately. Narrowly amend the exception rule:

- Null VINs and TimeoutErrors share one total budget of three fresh-page reads of the same provider route.
- A returned VIN must match expectedVin exactly when present. Changed VIN, wrong source/route, ambiguity, and every other reader exception abort immediately, including after a timeout.
- A successful exact VIN recovers. If the budget ends without a verified VIN after any timeout (including mixed timeout/null sequences), preserve the timeout and sanitized ui_timeout reason; never manufacture a missing-VIN row from that failure.
- Three genuine null reads retain initial unavailable/post-summary failure behavior.
- Retry diagnostics contain only bounded attempt counts and the safe ui_timeout reason, never exception text, credentials or VINs.
- No API/schema, tenant scope, journal, storage, schedule, freshness or assignment changes. Independent QA/Security and protected final-head CI are required.

## Runtime preflight — Oct16 15:23UTC

Intended worktree driver-identity-timeout-retry, branch codex/driver-identity-timeout-retry, clean base7299722d. Frontend5173 PID27324 belongs to the separate motive-driver-records checkout; preserved. Backend8000 has no listener. New worktree has no approved backend/database configuration; frontend proxy defaults to localhost8000. Local full-stack runtime is blocked/mismatched, with no local browser visibility claim. This change is a headless collector helper; use isolated node tests and an approved deployed collector canary instead. No servers, database or secrets changed.

## Release and rollback

Build only from merged protected source. Preserve existing driver service command, approved three fleets, database journal, environment, daily schedule, one replica and NEVER restart. Verify deployed source hash and one complete three-fleet run with verified committed journals/read models. Revert to the previous image on new identity, scope or import regression. Existing timeout failures must remain visible if recovery exhausts; do not relax safeguards or fabricate data.

## Candidate verification

Five new focused regressions failed on the prior helper (31 pass,5 fail) and pass with the bounded retry (36 pass,0 fail). They cover initial/post-summary recovery, the shared budget, every mixed timeout/null placement, exact mismatch/source/ambiguity immediate failures, and sanitized retry metadata. Node syntax and diff checks pass. Independent candidate QA/Security GO at adc02f07:36 tests plus686 independent combinations pass; see [gate evidence](../evidence/db036-driver-timeout-independent-gate.md). Final-head CI and deployed three-fleet canary remain pending.
