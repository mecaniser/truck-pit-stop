# Fleet vitals recovery — 2026-11-04

Backend & Integrations accountable. Branch `codex/fleet-health-vitals-coverage`.
Contract: [fleet coverage](../DB036_FLEET_HEALTH_COVERAGE_CONTRACT.md).

## Scope and source findings

Read-only production audit covered25 active memberships. Twenty had both stored
readings; their latest successful health captures were08:34–08:38UTC. Subsequent
hourly health jobs failed before credentials in Motive's legacy redirect loop.
An enabled schedule and historical readings therefore did not prove current
collection success.

The authenticated source account was checked before and after a complete Admin
Vehicles inventory:23active vehicles and one deactivated. Truck26 has both
readings and an existing reviewed VIN-less binding, which the previous health
worker skipped. Truck5 and Dontrans532 show blank odometer and engine hours in
Live; Elis24/42 are absent from both source directories. No substitute readings,
fabricated VIN, fleet transfer or source-account setting change is authorized.

Available-reading membership units:01,02,03,17,26,4,530,531,533,6,603,7,70,728,77,
8,860,88,9,W900 and609. Source unit labels may differ from local labels; exact
VIN/provider or the existing reviewed binding remains identity authority.

## Change and gates

The health collector reads explicitly allowlisted VIN-less vitals with identity
checks before/after Live. Import uses the existing bound-telemetry contract;
current membership, source time, company, reviewed binding and projection validity
remain mandatory. Bound fault diagnostics remain unavailable. Existing VIN capture
and immutable receipt identities are preserved.

Health-only login recovery follows official native lookup/password forms after
both anonymous legacy contexts fail in the exact redirect loop. It submits each
credential stage once, with a fixed recovery budget and strict origin/effective
native form destination, method, target, input/account and submitter checks.

Independent QA/Security returned the first candidate for empty submitter-override
and document-baseURI defects. These were corrected before deployment. Intercepted
Chromium regression probes reject both cases before credential entry/submission;
no real credentials or provider network requests were used in these probes.

Focused backend acceptance:102tests passed. Independent QA's expanded adjacent
backend suite:128passed; independent Security backend suite:99passed. Collector,
task and diagnostic Node suite:37passed. Ruff and backend partition verification
passed. Final login Chromium suite:103passed. Shared login/timestamp regression suite:
90passed. Independent Security cleared final helper40c00f3e after challenge and
completed-disposal probes; independent final QA remains a merge gate.

## Release acceptance (pending)

Protected PR checks, exact merge/deployment identity, live source/receipt/saved/
current-projection equality for all21available trucks, unchanged canonical vehicle
and membership/relationship fingerprints, production panel checks and a successful
natural hourly execution remain required. A manual canary alone is insufficient.
Local full-stack QA is blocked by missing isolated backend configuration; shared
5173/8000 services belong to other worktrees and were preserved.

Rollback signals: wrong account/identity, unexpected eligibility, binding authority
loss, receipt/readback mismatch, credential rejection or any import ambiguity.
Stop saving on these signals; preserve source/receipts for exact recovery and
restore the previous worker image/configuration if necessary. Never bypass the
binding, tenant, current membership or protected PR gates to obtain coverage.
