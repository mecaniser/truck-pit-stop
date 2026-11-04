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


## PR785 merge and display acceptance clarification

PR785 merged `d242868c8510a2e8b061ede9449777b2e612d9ce` at22:14:06UTC
after all seven checks in CI41921297155 passed. The merge tree is identical
to checked head `a5bcdb7ae902fc237b17d3d3612d8a22118de342`. The tracked backend
archive digest is `ffb018fe431a47e8183e5f4dda0e210e448f7a746ace35aeb99d65be2b5fc341`.
API deployment `1166be17-c153-4f07-820d-6a277355e941` and health image
`f4790844-5565-447b-ac33-792ba238ebbb` are pending runtime acceptance.

Independent QA directly inspected the retained production603/609/26 screenshots
and four unavailable-panel records. They cover the affected identity paths,
both populated fields, separate canonical service readings and unavailable
source states. Subsequent changes touch no frontend or public API. QA therefore
approved those display cases plus exhaustive new current API parity as the
changed-journey acceptance plan. This explicitly replaces the later self-added
full25-popup requirement; that additional visual sweep was not completed after
the Mac locked. This is a plan clarification, not live acceptance. All21 exact
source/receipt/saved/current projection matches, four null projections, unchanged
protected fingerprints and natural corrected-image execution remain required.


## PR785 manual canary returned — outer identity read

API `1166be17` became ready and public build SHA equals `d242868c`. Health image
`f4790844` became ready. Runtime attests collector `19d611fa`, login `6b713bcd`
and shared diagnostics `193b5447`; release artifact hashes remain exact.

Manual execution `dccff8a7-16f9-4162-9483-a7148850d97a`, requested22:19:53UTC,
authenticated through every new validation phase and app redirect. It exhausted
three transient `vehicle_identity` attempts before any health-vitals phase,
vehicle progress or import. Final category is browser timeout; imports were
prohibited. The unchanged shared outer reader has multiple timeout-capable
awaits, while its VIN-presence timeout is swallowed; current logs cannot locate
the failed await or establish missing VIN data. No candidate regression or
provider root cause is asserted. Shared reader, dependency locks and Dockerfile
are byte-identical to the successful PR775 image.

Retained failed source path:
`/data/motive-health/20261104T221955Z-5af0e1f2-11d4-404d-a22f-9b9a2dfdad60/source.json`.
The live observer lost its SSH payload at container exit; failure forensics will
be recovered during the existing scheduled run, without a separate provider job.
The earlier failed PR783 source was recovered privately: zero vehicle rows,
incomplete source, no receipt/attempt, static login-password failure marker.

The authenticated IAB Health directory still renders all21 expected provider
identities; a fresh first-vehicle document renders the exact Live link. This
proves current source UI availability, not readiness in the Railway context.
Architecture approved retaining the current fail-closed image for the already
scheduled22:30 execution. Rolling back PR775 would not change the implicated
outer helper. If repeated, use static substage diagnostics before changing any
timeout/retry/identity policy. Live and natural acceptance remain open.


## Scheduled failure and actual official-form finding

The22:30 schedule produced execution `20d60623-e81f-47a0-b0c5-4c3b932f6c84`
at22:35:35UTC, using scheduled redeployment
`cb118037-2b48-4897-ba63-72484dcd3c4a`. It failed at lookup revalidation with
`credential_count` before lookup submission or import. The redeployment carries
the prior CLI release message and the new validation phases, but its image digest
differs from `f4790844`; exact runtime hashes were not captured during this short
failed execution. No identical-image assertion is made.

Direct official-page inspection without a real account identifier found one
visible native lookup email and two additional hidden generic-email fields in
separate auxiliary forms. Each auxiliary form has the complete seven-control
profile recorded in the contract; all controls are hidden and no values were
read. Existing6b713bcd rejects the shape in an offline Chromium reproduction. A
separate native-semantics fixture posts only the selected form's own email.

One public native lookup with a synthetic reserved-domain identifier exposed
the password document without entering or submitting a password. Its selected
form owns password+hidden account; a separate optional SSO form owns its own
hidden generic email, and the same two auxiliary forms remain. These unrelated
controls must not be counted as participating native credentials. The exact
source structure is retained privately with no field values.

Architecture/Security approved the bounded ownership/profile contract before
implementation. It preserves visible-input/challenge checks, native destination
and account/value guards, and rejects all unclassified or rebound controls.
Auxiliary and SSO forms are never filled or submitted. Login helper/tests only
are assigned to Backend; new independent code gates and exact corrected live/
scheduled proof remain required. Runtime alignment is blocked by the owned dirty
documentation and missing isolated configuration; shared5173/8000 listeners were
preserved. No source UI or current automation success is claimed.


## Native ownership candidate and independent return

The initial ownership candidate `9ac9a825` passed178 tests but independent
Security reproduced a P1 native-submitter mismatch: a JavaScript-created nested
foreign form owned the selected button while the outer form passed review. The
intercepted fixture sent synthetic hidden metadata abroad; it did not transmit
the native password/account and made no live requests. The candidate was returned
before merge/deployment.

Corrected source `f1c46e4c` binds input, matching hidden account and submitter to
the exact reviewed native form handle. Owner182/182 Chromium tests passed,
including nested foreign/other-auth forms at both stages. Fresh independent
review is required; the earlier candidate is not approved.

The same recovery adds observational outer-reader substages, with no retry,
timeout, identity or navigation changes. WeakMap metadata preserves frozen and
non-Error throws and exposes only fixed stages/coarse route state. Owner57/57
shared collector/task/login-diagnostic tests passed. Health collector `9b729f97`,
shared reader `4bad4b34`, diagnostics module `a9653009` and task projection
`90f1a004` are frozen for the combined gate. This work still has no successful
corrected-source runtime or scheduled acceptance.


The corrected ownership candidate `f1c46e4c` was returned again by Security for
a P2 native account ambiguity: a hidden SELECT owned by the native form could
add a second account field because only INPUT elements were counted. This was
reproduced with intercepted synthetic requests, not a foreign transmission.
Neither rejected ownership candidate was released.

Final auth `5d22def7` / tests `ec8ab008` count all actual standard form-associated
credential controls, including off-form selects/textareas/buttons/fieldsets/
objects/outputs; expected credentials must still be the correct INPUT controls.
Owner205/205 tests passed. Fresh independent Security GO:205 auth and44 shared
tests passed, both reported defects closed in separate adversarial probes, no
remaining P0/P1/P2 finding. Shared observability hashes remain unchanged. Fresh
QA, protected CI and actual corrected runtime/scheduled acceptance remain open.


Fresh combined offline QA GO on final `5d22def7` / `ec8ab008`:402/402 Node
tests and21 independent intercepted Chromium probes passed. Negative native,
off-form, non-INPUT, nested and changed-ownership cases blocked password POST;
ignored auxiliary/SSO value getters were never read and only one modern context
was created. All source hashes match the final frozen combined scope. Security
GO independently passed205 auth +44 shared tests and reproduced closure of both
findings. No reviewer made a live provider request. These are offline source
gates; deployed capture/readback and successful natural scheduling remain open.
