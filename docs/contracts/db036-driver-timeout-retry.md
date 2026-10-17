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

## Protected merge and driver-only upload

PR555 exact head `7fc067c0823d35368cf899246c958546ab17b159` passed all six required contexts in run `38937720902`, with full backend completing at17:52:46UTC. Main remained `c42009e0`; normal squash merge at17:53:20 produced `c9beafe497fe7b4909acc2d03dd8d6bb9195faf2`, whose entire tracked tree equals the tested head. Only the existing driver service received the877-file immutable archive; deployment `958360c0-c1b4-44c1-ae50-f01c63f9656b` is building. No driver execution was active at upload; all configuration/environment/location invariants matched baseline. Runtime and canary acceptance remain pending.

Railway currently reports rollback/redeploy unavailable for the previous failed deployment `f8912205`. A separate exact pre-fix-main `c42009e0` driver archive is prepared with the identical manifest and approved environment hashes, but has not been uploaded. Its archiveSHA256 is `235bf84205000061d1b071ab0d2209147954b30a3433fb0ce60e3da19df382e5`; collector/test files match the reviewed pre-fix implementation. This is a known-source fallback, not proof of the failed image's source. On any new identity/scope/import regression, stop rollout and return evidence to Product & Delivery before selecting recovery.

## Production backend release acceptance

Release & Reliability GO at2026-10-16 18:16:41UTC. This closes the worker/backend release gate; authenticated production UI is owned separately by Product & Delivery.

- Exact merged source: `c9beafe497fe7b4909acc2d03dd8d6bb9195faf2`. The six required checks passed on `7fc067c0823d35368cf899246c958546ab17b159` in run `38937720902`; merged/tested tree is `bc3a54a1f2f913fe0a887d2054606d1e881f626b`. The coordinator later canceled the redundant identical-tree postmerge run `38943130322` to free runners. That canceled run is not a pass and is not used as the release gate.
- Existing driver service only: deployment `958360c0-c1b4-44c1-ae50-f01c63f9656b`, image `sha256:c335535ba89e5b09e76d7f5b753d66b267ed7705c677966234a626cb66051510`, SUCCESS. All seven deployed source hashes match the immutable merged archive, including `collect.cjs` and the shared `collect_trips.cjs` VIN reader.
- After proving no active driver run and no automatic new-image execution, one explicit cron canary was requested. Execution `04b537f2-f6dc-4c46-b8c1-87a859cf1330` ran18:00:05.730–18:14:53.899UTC and EXITED. One runtime instance was observed, no overlapping driver execution exists, and `fleets_complete` confirms three scopes. The source intervals below are sequential.

| Approved scope | Source collection UTC | New verified committed journal | Current captures / numeric scores |
| --- | --- | --- | --- |
| 77 CARGO LLC | 18:00:07.719–18:05:24.304 | `1ed07bb3-e57f-4d25-9453-4878dc5e14b3` | 18 / 14 |
| Elis Logistics LLC (DBN) | 18:05:27.834–18:10:02.897 | `38392a24-e7c6-4149-a4f1-da8ff6ff86e6` | 1 / 1 |
| DONTRANS LLC | 18:10:05.486–18:14:51.785 | `08fa9bd4-4089-4007-9f61-254ac4dba9eb` | 1 / 0 |

Final read-only DB snapshot at18:16:14UTC verifies all20 saved captures against their new source rows and the actual current read model: provider identities, payload digests, source/capture times, safety score and scoring period all match. All three new journals have five verified receipts, committed=true, recovery=false and matching replay/readback/projection counts. No available record is stale or retained from the prior run. Other-tenant capture fingerprints remain unchanged.

Coverage is22/22 board trucks across three approved scopes, with no uncovered, ambiguous or future membership. Four listing labels (77 Cargo, Dontrans, Elis and Lynx) do not imply four collector scopes; Lynx is covered through the approved77Cargo scope. There are15 numeric scores,5 captured records for which Motive supplies no safety summary, and2 source-unavailable rows (one unassigned driver, one unavailable VIN). The provider scoring period remains Sep28–Oct11 for the numeric examples; the new checked time proves a fresh read of that provider period, not a newer provider calculation. No score is invented for missing provider data.

The canary logged seven bounded identity retries without the `ui_timeout` reason. All resolved into the existing valid-identity or genuine missing-VIN paths and the run completed. This is proof of a complete new-image run, not evidence that an actual TimeoutError occurred and recovered during this canary; timeout behavior is covered by the focused and exhaustive negative tests.

Configuration hashes, all three approved scope identities, daily13:45UTC command/schedule, one replica, NEVER restart and database journal/storage match the baseline. The location service remains on its existing five-minute schedule, deployment `0d3efd78` and image `1c5739e6`; no location action was taken. The known-source fallback archive remains unuploaded. A successful canary does not establish future daily reliability; the two earlier failed runs remain in the audit history.

Private evidence: `output/driver-timeout/release-2026-10-16/` contains `release-plan.json`, `runtime-source-proof.json`, `canary-trigger-intent.json`, `current-state.json`, accumulated exact-deployment `current-logs.json`, `db-verification-20261016T181617Z.json` and `canary-acceptance-20261016T181641Z.json` (63/63 accepted checks). The17:01UTC baseline remains preserved as `pre-canary-baseline-20261016T170129Z.json`; all12 synthetic parity cases and all14 saved-evidence acceptance cases passed. Raw provider rows and environment values are not included in tracked documentation.

## Authenticated production acceptance

**Scoped worker release Done.** Product & Delivery completed authenticated, read-only score/period/timestamp and responsive-layout acceptance on desktop1280×900 and mobile390×844. The saved UI receipt and all seven referenced screenshots exist in `output/driver-timeout/ui/production-ui-acceptance.json` and its directory. Release & Reliability independently compared every focused UI score, provider period, checked time and assignment time in that receipt with the final verified DB readback; all match.

- W900: score88 and provider period Sep28–Oct11 on desktop card/map and mobile map/detail; checked18:03:54.639UTC, assignment18:05:24.304UTC.
- Elis609: score81 and the same provider period in desktop detail; checked18:08:19.762UTC, assignment18:10:02.897UTC. Elis ownership remains displayed.
- Lynx17: explicit safety unavailable on the mobile card; checked18:01:49.241UTC, assignment18:05:24.304UTC.
- DONTRANS532: explicit safety unavailable on the mobile card; checked18:11:03.871UTC, assignment18:14:51.785UTC.

The board shows22 trucks and21 driver controls:15 numeric scores,6 unavailable-score controls and1 unassigned truck. This is consistent with20 captured records (15 scores and5 provider-no-score), one assigned row without a verified capture, and one unassigned row. Mobile document width equals the390px viewport; the dialog spans x12–378 with no horizontal overflow. Console errors/warnings are empty. Stale W900 speed remains unavailable with motion unknown and last-known map location. The original viewport and Fleet Board tab were restored.

Public Web advanced from `c42009e0` to exact merged `c9beafe4`; DB and Redis readiness passed. After reload, root reconfirmed22 trucks,21 driver controls, W90088 with the same exact fresh timestamps and an empty console. Worker/source and public-Web identities are separately evidenced.

**Separate frontend investigation:** pointer dismissal of a fleet-card driver popover opened the underlying truck in IAB, both before and after the worker rollout. Escape dismissed correctly. Source cause is unconfirmed, and full pointer-interaction acceptance is not claimed. This collector-only change does not explain that pre-existing behavior; no worker rollback is required. The completed worker release does not close this separate investigation or establish future daily reliability.
