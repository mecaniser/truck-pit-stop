# DB-036 location/speed authentication recovery

Owner: Backend & Integrations. Branch `codex/motive-location-auth`, base
`9ad6809e6700d2109e4654480de37215f7ba23d4`. Contract:
[`DB036_LOCATION_AUTH_CONTRACT.md`](../DB036_LOCATION_AUTH_CONTRACT.md).

## Production diagnosis — read only

The location service `DBN-motive-sync` runs every five minutes with saving
enabled. Three inspected executions, scheduled November 5 at 04:25, 04:30 and
04:35 UTC, terminate with `login_legacy_redirect_loop` after the existing
anonymous context recovery. The latest starts 04:37:18 and fails 04:37:25 UTC
(November 4, 11:37 PM New York), before credential entry, source collection or
import. This is separate from the successfully restored health/vitals worker.

Actual current Fleet projection returns 21 historical speed readings, all
stale, and four null units. All 21 retained locations are stale too; newest
location capture is November 4, 09:03 UTC. Unit 609's retained speed is zero
observed November 4 at 05:01 UTC; 603's is zero observed November 3 at 22:30 UTC.
The UI intentionally requires a speed's own observation to be within five
minutes, so it correctly shows unavailable rather than presenting these old
values as current. This change does not alter that rule.

Read-only scope verification confirms the location service fixes the approved
Motive account and tenant, but has no fleet/customer pin. Its existing importer
resolves exact unique tenant VINs and one active enabled/internal fleet, rather
than equating the source account label with the local operating customer. Thus
609's enabled Elis membership and 603's enabled 77 Cargo operating membership
are already eligible. Both have one exact current tenant VIN record. Unit 26's
existing reviewed provider `5981300` allowlist and unrevoked, non-expiring binding
match its current membership and placeholder. No scope extension or membership
change is needed for this authentication repair. Fresh source availability and
per-field speed timestamp eligibility still require runtime acceptance.

## Implementation

- Location's adapter reuses the exact released native-form health login helper.
  Static diagnostic names identify the location service.
- Existing configured credentials enable the same bounded fallback only after
  the confirmed persistent legacy loop. The helper's strict official form,
  ownership, account, challenge, target, disposal and deadline checks are reused
  unchanged; no duplicated authentication implementation is introduced.
- The actual location collector skips its legacy credential submission only
  when the helper returns boolean `authenticated === true`. Unexpected truthy
  flags do not bypass the existing path.
- Company and timezone verification still occur before source collection.
  Scope, VIN/binding/membership rules, source times, inline-location-only speed
  exclusion, import/replay logic, cron and commit settings are unchanged.
- The repository `railway.motive-location.json` uses the pinned drivers Dockerfile;
  actual cloud deployment metadata instead uses `backend/Dockerfile.motive-sync`.
  Both copy the complete backend and include all four authentication modules;
  the isolated dependency test loads the exact chain without circular imports.
  The release plan preserves the actual cloud configuration, including the
  five-minute cron, NEVER restart policy, one replica and `/data`. The inspected
  scheduled execution metadata records `buildOnly=false`; upload/build lifecycle
  and a natural scheduled execution must be evidenced separately. Preserve the
  existing Dockerfile/base selectors without claiming identical resolved base
  image digests. No service configuration change is authorized here.

## Verification and corrections

Node syntax and diff checks pass. The five-file Node regression group passes
83/83, including speed/coordinate parsing, fuel, tasks and safe diagnostics.
The final six-file protected Chromium/authentication/collector/inline suite
passes 424/424 against the frozen source. It includes actual location-caller
execution through the native fallback,
two credential POSTs total, source-company rejection, unsafe targets, malformed
auxiliary forms, wrong account, OTP, active SSO and rejected-password negatives,
plus the unchanged released health/legacy guards. Synthetic requests are
intercepted locally with fail-closed DNS; no provider login occurs.

Frozen SHA-256:

| File | SHA-256 |
| --- | --- |
| `motive_sync/collect.cjs` | `19d405dedd72d9918171a63febdb2fb4883c6fff81adf59276c4cb46fe389f82` |
| `motive_sync/sync_login.cjs` | `61cc98628800864fb354305a66c3fbe6b9a3c5865369643744e710fe9ad5c249` |
| `motive_sync/sync_login.test.cjs` | `bd245fd5dd42075e9ddf1cefb9391fa7dbabab5b42212d11a7c9bf16d9736c96` |
| Reused, unchanged `motive_health/login.cjs` | `5d22def79ead1c5c0c3ebdcb0967bf36773737f8c30e83ce2d109c8b4954028e` |

Reproduce with the installed Playwright dependency available:

```sh
export NODE_PATH="$PWD/backend/scripts/motive_sync/node_modules"
node --test backend/scripts/motive_sync/inline_timestamp.test.cjs backend/scripts/motive_sync/login.test.cjs backend/scripts/motive_sync/sync_login.test.cjs backend/scripts/motive_health/login.test.cjs backend/scripts/motive_health/collect.test.cjs backend/scripts/motive_sync/collector.test.cjs
node --test backend/scripts/motive_sync/collector.test.cjs backend/scripts/motive_sync/fuel_day.test.cjs backend/scripts/motive_sync/collect_fuel.test.cjs backend/scripts/motive_sync/tasks.test.cjs backend/scripts/motive_sync/login_diagnostics.test.cjs
```

Earlier owner test failures were fixture/environment issues: two new assertions
expected a source save earlier than the existing caller performs and timeout
instead of the stronger SSO origin rejection; both assertions were corrected.
An added unchanged health suite initially lacked its literal relative Playwright
dependency; the library alias corrected the test setup and its rerun passed.
Security returned a real strict-boolean contract guard, corrected with four
actual-caller truthy-value regression cases before final gating.

## Local runtime receipt and handoff

On November 4 New York, mandatory local-runtime dry-run preflight reports this
checkout missing approved `backend/.env` and Vite dependencies. Port 8000 belongs
to the existing privacy-safety Docker checkout; no frontend listens on 5173.
Those services and configuration were preserved. The local product runtime is
**blocked/mismatched**, not browser-verified. Offline intercepted Chromium tests
exercise actual collector/authentication code without local application services.

Existing Playwright 1.61.1 libraries are supplied through `NODE_PATH` and a
temporary dependency-only `backend/scripts/motive_sync/node_modules` symlink for
the unchanged health tests' literal relative imports. This symlink is not part
of the source change and was removed after all owner and independent checks.

The November 5 development preflight was repeated before preparing the release
handoff: the controller refused the dirty target, approved backend environment
and frontend Vite dependencies are still absent, port 5173 has no listener and
8000 remains the unrelated privacy-safety Docker checkout. No services changed.

Fresh independent Security GO binds the frozen source and 293 independently
repeated Node/Chromium checks; the strict-boolean finding is closed with no
remaining findings. Independent QA GO repeats 424/424 and 83/83 checks plus 11
additional boundary probes; see
[`DB036_LOCATION_AUTH_QA_2026_11_04.md`](DB036_LOCATION_AUTH_QA_2026_11_04.md).

## Deployment-plan rehearsal — separately approved, not deployed

Independent Security also issued artifact **PLAN GO** after 15 checks, including
13 negative preflight probes and deterministic regeneration. The rehearsal
archive binds candidate `1c9fe967eb2eabcd91fabd6ff183d72b9708173d`, not a future
merged release. Its SHA-256 is
`9625e41593b5fd7c0356cefd4deb23bffc7a095e4ecd0665d9325e8413734d2e`.

The local plan under `/private/tmp/db036-location-auth-release/` pins 27 critical
source/config/dependency files, the credential-free cloud baseline hash and the
exact project/environment/location-service destination. Its final preflight
compares all 3,197 file/type/mode/content/symlink entries across that reviewed Git
tree plus the single cloud-config overlay, the immutable archive and the upload
directory. Runtime source identity must come from file attestation, not an
inherited deployment message. Original Dockerfile/base selectors are preserved;
resolved base-image digests are not claimed identical.

The root release owner must first obtain the UI merge and final protected checks,
regenerate the artifact from the final reviewed merge SHA, and repeat the exact
preflight immediately before upload without intervening staging edits. Plan GO
and rehearsal do not establish final artifact identity, deployment, provider
authentication, fresh speed or automatic location recovery.

The prepared one-shot monitor is read-only: metadata first, then optional SSH
only for an explicitly identified already-running natural image/execution. It
retains complete evidence separately from SSH transport status, can pin a
completed source during a later natural same-image run, and checks source/
receipt digests, stable persisted/Fleet readback and pending commit evidence.
It never starts a service or runs a collector, login, import or recovery.

Root's separate November 5 read-only health check confirms 21 trucks still have
both mileage/engine-hours readings with captures at 04:39–04:44 UTC. That is the
healthy vitals lane; it does not prove this location/speed repair is released.

Protected CI, PR/merge, final merged artifact/preflight, deployment and a later
authorized scheduled source/receipt/current Fleet readback remain required.
Root authorized the focused source
commit and branch push after independent gates. UI/API PR791 merged as
`beae00f8a76054ee0111acff46228181ec5ba8b9`; this branch then merged that exact
main cleanly at `5638c96d`, preserving all UI/payment/board changes. All 27
reviewed critical hashes still match, and the diff against main remains the
seven focused worker/test/document files. PR publication and exact-head protected
CI are next. The post-merge local runtime dry run still reports missing approved
backend configuration and Vite dependencies; unrelated privacy services remain
untouched. No production configuration, provider login, job
trigger, deployment, production data write, membership or financial change is
performed by this implementation handoff.


## Released November 5, 2026

[PR 793](https://github.com/mecaniser/truck-pit-stop/pull/793) merged as
`77a0d82aa633a5c08da64a6ab1922f9bdc360557` after all seven checks in
[run 41975718235](https://github.com/mecaniser/truck-pit-stop/actions/runs/41975718235)
passed on `8354bfc9`. Checked and merged trees are identical. The API deployment
`6af35ae0-4b6e-43b0-855d-28bd9a22eddd` succeeded with the exact public build stamp,
built 05:53:13.785 UTC; database/Redis readiness passed.

The dedicated location service received exactly one upload from that merged
Git archive. Archive SHA-256 is
`d00f14229095919a82f6776ad30f2b2bd89ce069f5a614738bb9fef7ad9499c3`.
The independently reviewed preparer/verifier matched 27 pinned files and all
3,205 Git/archive/staging entries, with only the existing cloud configuration
mapped into the release manifest. A first operational preflight found an older
build in progress and performed no upload. The successful 06:02:42 UTC recheck
confirmed terminal older executions and unchanged configuration, scope, mounts
and aggregate environment fingerprint. Upload started 06:02:43.985 UTC and
returned once at 06:03:08.431 UTC. No manual provider job was triggered.

Deployment `13535477-e698-4ae0-97de-b1745bf5a7fc` succeeded in build-only mode,
image `sha256:10da9531e8129367b95df3c58e305a5019d55c66b3264e5047bfb44a1863bdbb`.
The actual sync Dockerfile, command, five-minute cron, restart NEVER, one replica,
existing /data mount, company/tenant, saving=true and reviewed provider allowlist
are preserved. After-release metadata and the 24-variable aggregate environment
fingerprint match pre-upload; no credential values were printed or stored.

### Natural execution and committed readback

First natural execution `f9bfd00e-d600-4100-b733-7bb7bece863f` started
06:05:52.628 UTC and exited 06:09:29.219 UTC. Its complete source started
06:06:09.431 UTC and finished 06:09:24.255 UTC: 23 source rows, 20 located and
three unavailable. The provider company was verified before and after capture.
It supplied six verified speed observations, including real zero values.

The committed receipt reports 19 updates, one unchanged row, three unavailable
and two source-missing local assets. All 19 saved receipts and all 19 post-commit
projection checks pass. Independent comparison confirms source bodies, request
identities, tenant/vehicle/membership, saved values and the actual Fleet
projection; evidence was stable throughout the read. All 26 backend runtime
hashes match the reviewed archive; the 27th archive pin is the root Docker ignore
file, which is not copied to /app.

Canonical JSON SHA-256:

- source: `d2fb483da02c303185d6a81254e6f42fd4af477474bb70f6e51a6aa5a656ed84`;
- receipt: `d3aa26c0d72e5496aa25597d201e3f91cad56a4daeb93996a8c08185f0bf6f3f`.

A second normal execution started automatically at 06:10:01 UTC on the same
reviewed image. It hosted read-only attestation of the exact completed first
source, pinned to its original execution bounds; no exited container was started
for inspection. Later Fleet readback at 06:20:25 UTC shows location/speed captures
advancing through 06:19:18 and six speeds eligible under the existing five-minute
UI rule. This is a point-in-time count, not a promise that every speed remains
current. The open signed-in 603 popup refreshed from Unavailable to 0 mph without
a page reload as scheduled imports and query refresh continued. Its phone popup remained contained.
Unavailable, old and location-only-timestamp speeds remain unavailable; no
location or capture timestamp is borrowed to make speed look current.

### Independent acceptance and preserved records

Independent runtime QA is GO on 18 strict evidence checks, in addition to source
QA and Security. The conservative diagnostic scanner flagged two October7
sources because it only recognized receipt.json. Independent read-only inspection
found their alternate commit/replay receipts: 11 verified saved/replayed rows in
one and one verified scoped saved/replayed row in the other. Both are completed
legacy workflows and cannot enter automatic recovery. Raw scanner flags remain
unchanged; no legacy source, receipt, snapshot or journal was replayed or deleted.
This does not assert that every row in those original 22-row sources was imported.

Final production checks preserve 25 assets, 23 tractors/two trailers, all four
reciprocal Elis attachment projections and 21 assets with both Motive mileage
and engine hours. The seven UI/API source hashes remain correct. Six protected
identity/membership/relationship groups and six service-history groups are
byte-identical to before release. No canonical mileage, VIN, ownership, pair,
financial record or service history was changed by the worker release.

The location authentication recovery is Done. The existing hourly vitals and
five-minute location schedules continue automatically. Source artifacts, DOM,
images, private IDs and aggregate fingerprints remain outside Git.
