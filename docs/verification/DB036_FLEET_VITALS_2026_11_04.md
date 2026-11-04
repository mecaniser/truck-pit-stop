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

## PR780 live failure and readiness correction

PR780 merged1d57758d with all seven checks passing and identical checked tree.
API8c55b2d0 served that revision and readiness passed. Healthimage415ea940 canary
20ee26cd authenticated, then failed its first vehicle read21:11:43UTC before any
import. Static logs do not identify the exact exception. Offline exact-source
fixtures independently reproduce delayedLivehash and blank-loadingVIN failures.
The known-working PR775 collector was restored as imagece2d5033; configuration,
source scope, hourly schedule, prior snapshots and business records were preserved.

Current manualMotiveLive audit verified21uniqueproviders with both numerical
fields, matching genuineVINs or reviewed26absence, with account verified before/
after. Raw source/forensic/visual evidence stays private outside Git.

The readiness correction waits only through authorized loading states, validates
the actual field-bearing Summary snapshot, and preserves verified Summary/time
when both Live fields are unavailable. Identity/auth/route contradictions remain
terminal, including contradictory middle snapshots. Frozen19d611fa/test318a53a4
passed84collector cases;103login and24task/diagnostic regressions pass. Fresh final
independent gates and protectedCI are required before merge; exact deployed capture,
per-field readback, production display and naturalexecution remain required.


## Follow-up release gate — 21:47 UTC

PR783 merged `8c2406c259920f798390d135eba15525d39c080a` after all
seven protected checks. API deployment `c34eaba0-20cf-44ec-bc44-79565813957f`
and health image `20035ae0-92cb-4059-988d-7e9a0be8b733` became ready. Manual
execution `daa7d3f2-7497-4006-af83-9d2f271531d0` failed at
`login_password` / `login_form_ambiguous`, before the password-submission
phase and before collecting/importing readings. Existing logging cannot
distinguish empty loading DOM, duplicate/extra controls, or pre/post-fill
validation. No production root cause is asserted from that category alone.

Independent offline Chromium probes reproduce the identical category for both
an empty password document that becomes valid after 100–200ms and duplicate
password fields. Architecture approved a pre-credential empty-document wait
within the existing 15-second fallback budget, with every strict form/origin/
account/challenge check preserved and no extra credential submission or context.
Owner: Backend & Integrations; branch `codex/health-login-readiness`. Fresh
independent QA/Security and source/receipt/projection/runtime gates remain open.

Separately, the restored PR775 natural execution
`870720fa-db32-49ce-8477-d5216a08ce78`, starting 21:33:24UTC, succeeded with
21 both-field vitals and19 diagnostics (40 verified/replayed captures), exact
source/saved/current API projection parity across the21 available trucks,
and four unavailable projections. This is evidence for that older image only.
The full25-panel visual sweep remains blocked by the locked Mac; user unlock
was requested. Previously captured603/609/26 panels remain narrower evidence.


Auth candidate frozen for independent gates: login source `6b713bcd` and tests
`15b938e3`, shared diagnostic source `193b5447` and tests `42621d09`. Owner
Chromium suite 120/120 and diagnostic suite 12/12 pass. The 17 new login cases
cover empty readiness, contradiction/deadline failures and changed post-fill
forms/values with no refill or submission retry. Strict lookup checks remain
immediate. Independent QA/Security and protected CI remain pending at handoff.


Fresh independent Security GO on the frozen `6b713bcd` / `193b5447` sources: 120 login
and 12 diagnostic tests passed. Separate intercepted Chromium probes proved
blank-to-valid one-fill/one-submit success, foreign-origin/challenge transitions
stopping before password entry, and valid-looking post-fill form replacement
stopping without refill/submission. No foreign POST or credential-query leak.
No remaining P0/P1/P2 security finding; live and scheduled gates remain open.


Fresh independent offline QA GO on the same frozen hashes:216/216 Node tests
(120 login,84 collector,12 diagnostics) and eight independent intercepted
Chromium probes passed. Empty-to-valid performs one password fill/submission;
nonempty loading, challenge, duplicate controls, post-fill clear/replacement/
action changes and deadline exhaustion stop without retry. No live provider
requests were made by reviewers. The private extractor now requires explicit
expected login hash for the new version and preserves its strict21-both-fields
API acceptance gate. No live release acceptance is implied by these tests.
