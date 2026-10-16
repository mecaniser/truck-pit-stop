# DB-036: driver identity page timeout recovery

Owner: Backend & Integrations. Worker change; high-risk lane.

## Evidence and acceptance before implementation

The Oct16 daily run completed fleet1 then failed in fleet2 before_summary with ui_timeout. One manual recovery of the existing service completed fleet1 then failed in fleet2 after_summary with ui_timeout on a different vehicle. The daily and recovery executions used different image digests; source equivalence was not established. Fleet2 did not create a journal and fleet3 was skipped. Existing valid records remain intact.

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

## Coordinated release hold

PR555 head `847e28f21525a67c4572d908fa569aecce63d326` contains the same reviewed
collector files plus corrected recovery provenance. The release coordinator
reserved the next slot for PR551/550. PR555's queued run `38926105312` was
canceled before execution; it is not a passing check. No merge or driver
deployment occurred. Wait for release clearance, refresh against the resulting
main and rerun all six required checks before proceeding. Driver settings,
approved fleet scope and journal hashes were captured privately; the location
worker's five-minute schedule and image remain unchanged.

## Resumed release preflight

2026-10-16T17:01:52.099943+00:00 UTC: intended branch codex/driver-identity-timeout-retry at847e28f2, only owned board/contract edits plus private output. Frontend5173/PID27324 still serves motive-driver-records/frontend; backend8000 has no listener and this checkout has no approved backend/database environment. Proxy defaults to127.0.0.1:8000. Local full-stack remains blocked/mismatched; unrelated runtime preserved. No source change or local visibility claim. User reauthorized completing deployment and current-score verification; coordinated PR550 release hold still applies. Prior detail-refresh production closure is carried with this branch as documentation only.

PR550 merged as c42009e0 and is integrated locally. Only board append history conflicted; both histories retained. Collector source/test files are byte-identical to independently reviewed adc02f07. Branch-only CI proceeds against the fixed main while the coordinated hold still blocks merge/deploy until immediate PR550 deployment/schema/retention clearance. Fresh private read-only parity checks confirm all20 existing captures, safety scores and scoring periods match the saved source and current read model; these old journals are explicitly not accepted as the new-image canary.
