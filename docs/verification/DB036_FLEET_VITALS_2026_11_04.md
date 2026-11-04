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
completed-disposal probes; independent final QA127Node/128Python passed on final helper40c00f3e/tests
e51f06fa. [PR775](https://github.com/mecaniser/truck-pit-stop/pull/775) awaits
protected checks. Signed-in production26baseline shows both readings unavailable
with canonical service odometer536528; private screenshot retained outside Git.

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

## PR775 release and live gate return

PR775 merged as e64c2e2f035e536b7c028e62d450f7683a2fe6a5 after all protected
checks passed. Production app6144e8df served that exact build SHA and ready
(database/Redis ok). Health image630af561 retained the approved source hashes and
hourly schedule; only the existing reviewed26source pair was added, preserving
all previous variables. Independent Security confirmed live official auth recovery
in5.273seconds and exact deployed source.

Manual executiona3cf3665 ran20:06:44–20:13:09UTC, verified/replayed40captures
(21vitals,19diagnostics), and left no pending commit. Truck26now showed548550.86mi/
21109h in the production panel, with service odometer536528 unchanged. Fingerprints
of all1520vehicles,48memberships and1482customer relationships, plus the25-truck
fleet subsets, matched the before-release baseline exactly.

The full live gate correctly failed:70had a new Summary-only567615mi capture,
engine_hours=null, and its older98hours remained projected. Authenticated Live
inspection then showed567618.88mi/104h under the matching VIN. Source account was
verified before and after. A partialcapture must not be described as21freshpairs.

Architecture approved scoped bounded Live-read recovery on follow-up branch
`codex/fleet-vitals-read-recovery`. Authentication, bound26, importer and receipt
contracts stay unchanged. Independent gates, protected CI and complete live source/
receipt/saved/current-projection checks remain required; no finalDone claim yet.

## Read-recovery offline gates

Frozen collectord76d1323 / testsb549b734 passed48routed collector tests and103
unchanged login regressions. Independent QA repeated48cases plus four cleanup,
phase, identity and late-page probes; Security repeated48cases plus wrong-provider,
foreign-origin and same-origin auth-overlay probes. Both cleared offline source.
Each vehicle gets one fixed90-second budget and at most two fresh pages in its
existing authenticated context. Initial pre-Live failures are terminal; only an
actual classified transient Live failure allows the one extra page. Page disposal
must finish successfully before proceeding. Unknown/missing/malformed readings do
not manufacture retries or values. Auth/challenge presence checks inspect only
attributes, not values/tokens. Existing bound/auth/import/receipt contracts retain
their approved hashes. Protected checks and live release gates remain pending.
