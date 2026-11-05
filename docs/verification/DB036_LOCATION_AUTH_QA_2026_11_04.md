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
