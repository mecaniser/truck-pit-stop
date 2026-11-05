# DB-036 location authentication — independent QA

**Source gate: GO.** The reviewer did not implement or direct this worker change
and made no product or owner-test corrections. Prior DB-157 implementation was
a separate outcome. This gate covers the frozen location authentication change;
it does not establish production recovery, import success or fresh speed.

## Frozen candidate

Checkout `truck-fleet-location-auth`, branch `codex/motive-location-auth`, base
`9ad6809e6700d2109e4654480de37215f7ba23d4`.

| File | SHA-256 |
| --- | --- |
| `motive_sync/collect.cjs` | `19d405dedd72d9918171a63febdb2fb4883c6fff81adf59276c4cb46fe389f82` |
| `motive_sync/sync_login.cjs` | `61cc98628800864fb354305a66c3fbe6b9a3c5865369643744e710fe9ad5c249` |
| `motive_sync/sync_login.test.cjs` | `bd245fd5dd42075e9ddf1cefb9391fa7dbabab5b42212d11a7c9bf16d9736c96` |
| unchanged `motive_health/login.cjs` | `5d22def79ead1c5c0c3ebdcb0967bf36773737f8c30e83ce2d109c8b4954028e` |

## Independently repeated checks

- **424/424 passed, zero skipped**, in 90.08 seconds: protected inline timestamp,
  legacy login, location login, health login, health collection and location
  collector suites. Real Chromium cases intercept synthetic requests locally.
  They cover one bounded native fallback after anonymous loops, exactly one
  lookup and one password submission, wrong source company, unsafe targets,
  auxiliary-form ambiguity, wrong hidden account, OTP, SSO and rejected password.
- **83/83 passed, zero skipped**, in 1.83 seconds: collector, fuel-day, fuel
  collection, tasks and safe-login-diagnostic regression suites.
- **11 additional independent probes passed** against actual collector/adapter
  source in isolated VMs. Only literal boolean true bypasses legacy credential
  submission; false, undefined, null, NaN, a Boolean object, Symbol, zero and a
  string do not. Every case reaches the next company boundary, grants clipboard
  access only on the existing app origin and closes its browser exactly once.
  The adapter preserves original browser, credentials, phase callback, timeouts
  and returned promise identity while mapping only its static diagnostic names.

The extra probes also compare the repository location Railway manifest, pinned
drivers Dockerfile, Docker ignore rules, worker supervisor, checkpoint/task
logic, legacy helpers, health helper, timestamp parser and identity module
byte-for-byte with the branch base. The source diff changes only the location
adapter and the caller's strict authenticated branch, plus tests/docs.
`git diff --check` passes.

## Artifact and scope review

The repository location manifest `railway.motive-location.json` uses the pinned
`backend/Dockerfile.motive-drivers`, overrides its command to
`python -m scripts.motive_sync.run_worker`, and specifies the five-minute cron.
This repository declaration is not proof of the active cloud build configuration.

Subsequent read-only cloud metadata inspection by the worker owner identifies
`backend/Dockerfile.motive-sync` as the actual location service's build path.
QA independently inspected both tracked Dockerfiles: both install Playwright
and copy the entire backend, including the same four-module authentication
dependency chain. The sync Dockerfile directly selects the location worker;
the repository manifest selects it through a command override. Docker ignore
rules do not exclude the reused authentication modules. The isolated artifact
test proves loading that module chain without circular imports; it does not
attest the active cloud configuration. Independent review of the owner's
read-only deployment plan/metadata remains required when that artifact is ready.
No Dockerfile, manifest or cloud setting was changed by this correction.
The temporary dependency symlink is test setup and must not be staged.

Reused health ownership, account, challenge, official-target, disposal and budget
guards are unchanged. Company/timezone checks still precede source collection.
VIN/provider bindings, membership resolution, source observation times,
inline-location-only speed exclusion, display freshness, import/replay rules,
scope and scheduling remain unchanged.

## Evidence and limits

Private local evidence:

- `/tmp/db036-location-auth-independent-protected-qa.log`
- `/tmp/db036-location-auth-independent-node-qa.log`
- `/tmp/db036-location-auth-independent-probe.cjs`
- `/tmp/db036-location-auth-independent-probe.json`

No live provider login/request, database write, worker trigger, configuration
change, commit or deployment was performed by QA. Local product startup is
exempt for this read-only source gate; existing services were not replaced.
Protected exact-head CI, merge/deployment identity and later authorized natural
scheduled source/receipt/current-fleet readback remain separate release gates.

## Independent runtime gate — November 5, 2026

**GO for the current location-worker recovery.** PR793 merged as `77a0d82a`
after its exact-head checks. Deployment `13535477` is SUCCESS with the expected
image, build-only upload flag, unchanged cloud manifest and mounts. Independent
review matches all27 archive pins, including Docker ignore rules, and all26
backend files actually attested in the running container. All four runtime
destination identities and all five preserved scope flags match.

The first natural execution `f9bfd00e` ran06:05:52.628–06:09:29.219UTC. Its
pinned source started06:06:09.431 and completed06:09:24.255UTC, with both source
company checks true and23 rows:20 located and3 unavailable. A later read from
the already-running second natural execution on the exact same deployment
verified the completed first source and receipt unchanged. Canonical hashes:

- Source: `d2fb483da02c303185d6a81254e6f42fd4af477474bb70f6e51a6aa5a656ed84`
- Receipt: `d3aa26c0d72e5496aa25597d201e3f91cad56a4daeb93996a8c08185f0bf6f3f`

Receipt mode is commit and committed is true:19 updates,1 unchanged,3 unavailable
and2 source-missing cases. All19 saved rows have saved-receipt verification and
post-commit projection verification. All19 independent saved identity comparisons
and all19 source/body/saved/current-Fleet comparisons pass, with stable evidence
and successful read-only transport. There are six available speed values in the
source; this does **not** mean all six are eligible as current UI speeds. Original
field observation times and the existing freshness rule still decide that.

### Historical artifact naming exceptions

The conservative observer's raw `acceptance_evidence_complete` and
`no_pending_commit_evidence` flags remain false because it checks only the exact
filename `receipt.json`. Independent read-only inspection positively identifies
both flagged October7 directories as historical workflows with alternate-named
committed and verified replay receipts, not pending current imports:

- The earlier directory retains `receipt-commit.json`, `receipt-replay.json`
  and a dry-run receipt. Commit and replay each verify all11 saved rows and
  their post-commit projections.
- The later directory retains alternate-named commit and replay receipts,
  each with one saved/receipt-verified/projection-verified row, plus a one-row
  scoped source containing `import_scope`. This is evidence of that scoped
  historical operation, not a claim that its full22-row source was imported.

Both directories and sources retain private0700/0600 modes and October7
timestamps. Neither contains a resumable source-task checkpoint; both sources
are complete. The unchanged scheduler skips complete sources and requires an
eligible recent incomplete task checkpoint before read recovery. These artifacts
therefore cannot enter automatic collection/import recovery. Their positive
committed/replay receipts close the exact-name-only observer false positives for
this bounded current-run gate; the observer's raw results were not rewritten.

This review performed two successful metadata-only SSH reads while a natural
execution was already running, with exact project/environment/service/deployment
assertions before reading files. Other attempts stopped before SSH when the
checked execution had ended. No worker/container was started, no provider login
was requested, and no legacy evidence, receipt, database row or replay was
changed. No cleanup or historical re-import is authorized by this classification.

Private evidence: `runtime-independent-qa-20261105-v2.json`,
`legacy-evidence-independent-qa-detail.json` and
`observation-20261105T061217267914Z.json` under
`/private/tmp/db036-location-auth-release/`. The independent assessment records
18 passing checks and preserves the raw observer limitation. Final fresh API and
protected identity/service-history fingerprint checks are recorded separately
by the release owner.

## Final post-worker and recorded production UI confirmation

**GO.** Independent artifact review adds17 passing checks after the runtime gate:

- The seven serving API hashes match the released source; migration203 remains
  applied. The exact25-asset fleet still contains23 tractors and2 trailers,
  with21 assets retaining both available Motive vitals and all four reciprocal
  Elis attachment projections unchanged.
- All six protected identity/membership/relationship fingerprint domains and
  all six service-history domains are byte-identical to their pre-deployment
  baselines.
- Worker image/deployment, manifest, mounts, root directory and five scope
  flags remain unchanged. The configured24-variable environment fingerprint
  remains `56a191f3f83b4f8bb90f66d5bcc31f8997f48e87f46acfb0032805adb02f091a`.
- The06:20:25UTC current projection shows later automatic location and speed
  captures through06:19:18UTC. Six speed readings have their own observations
  within five minutes:17 at66mph,26 at52mph, and four genuine zero values,
  including603. The21 mileage/engine-hours records retain the latest hourly
  captures from05:32–05:36UTC. Retained older speed/location readings are not
  mislabeled current.

The saved signed-in UI sequence records the same open603 location/speed popup
changing from Unavailable to0mph after its automatic query refresh. Independent
visual inspection of the resulting real phone screenshot confirms the correct
603 popup, an address, actual0mph and about-four-minute source ages. Recorded
geometry confirms the320px popup fits the375px viewport without document
overflow and the marker remains44px square. Review of that transition is based
on the recorded owner sequence; this reviewer independently inspected the
resulting image and artifacts without performing another live browser action.

Private confirmation: `/tmp/db036-location-final-independent-qa.json`,
the final source/config/fingerprint/telemetry readbacks listed there,
`/tmp/db157b-production-ui-evidence.json` and
`/tmp/db157b-production-restored-speed-phone.png`. No production Save, provider
request, SSH call, database write or additional test loop was performed for
this final review. Six eligible speeds are a point-in-time observation, not a
claim that every truck has available current speed or that freshness persists
without new source observations. The release owner's final checks are now
independently confirmed; the earlier pending wording records the prior gate.
