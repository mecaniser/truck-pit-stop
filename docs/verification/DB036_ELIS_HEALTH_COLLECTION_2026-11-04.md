# DB-036 Elis health collection correction

Backend & Integrations accountable. Branch `codex/elis-health-vitals`, base
`d25c7743`. User authorized verifying603/609 VIN mappings and fixing collection
on the existing correct Elis records.

## Verified diagnosis

Read-only production transactions establish both physical vehicles are owned by
Elis Logistics LLC (DBN) in the same Truck Pit Stop tenant. Each has exactly one
nondeleted matching VIN in that tenant; saved Motive diagnostics contain that exact
VIN. Provider identities are distinct.603 has a dated77Cargo operating membership
and fresh mileage/engine hours on the same Elis-owned vehicle.609's current fleet
membership is Elis; it has matching fault capture but zero telemetry rows with
mileage or engine hours. Current health worker environment pins77Cargo. Earlier
fault captures for609 therefore do not prove current vitals import eligibility.
A separate603 in another tenant has a different VIN and is unrelated. No ownership,
operator, payer, membership or canonical mileage correction is needed for this fix.

## Contract and verification

Independent Architecture approved [reviewed target exceptions](../DB036_REVIEWED_HEALTH_TARGETS_CONTRACT.md).
Keep the default fleet pin and add only the verified609 provider/vehicle/customer
target. No schema, public API, frontend or provider-account change.

-80 focused/adjacent backend tests pass: health targets, diagnostics, worker and
telemetry.17 new target cases cover successful scoped exception, default-fleet
regression, unavailable faults, zero hours, unreviewed exclusion, source-missing
scope, wrong vehicle/customer/VIN/tenant, deleted target, duplicate membership,
source before membership, mapping drift/removal and legacy receipt recovery.
-37 collector/login tests pass after installing the existing locked Playwright
dependencies and supplying its module path. Initial local invocation lacked that
module path; no source correction was necessary.
-Changed-source Ruff and diff integrity pass.
-Fresh independent QA GO:80 tests plus3 independent probes for diagnostic-only
target, unavailable-fault VIN drift and membership-replacement recovery.
-Fresh independent Security GO:59 tests, noP0/P1/P2 findings.

Both independent reviewers attested identical SHA256 source:

```text
targets.py       39883ff2c2c14a8fa3685ad7c61f6e2eccf7e9e2a4c510958525c37a69b7b2ca
import_health.py bc92d801831b9d341ce79d540c199e4a7d18f5169b2df6bc478e2b7a3b501de0
runner.py        350af10d19359dbd556bd64948bce7f7d0a3824c6450b06e7f324a531d9cb58f
```

## Runtime and rollout gates

Local runtime preflight ran on2026-11-04: shared5173 belongs to the portal-task-first
checkout and8000 mounts privacy-safety backend. This checkout lacks approved
`backend/.env`; controller dry-run refuses startup. Shared services were preserved.
No claim of aligned local full-stack browser acceptance. A dedicated signed-in
production tab reproduces609's unavailable fields on the correct Elis header.

Before enabling target configuration, inspect/reconcile pending old-scope receipts.
The stopped cron container cannot be SSH-inspected between runs; retain old scope
for an existing-code preflight run, inspect while running and require verified
completion before enabling609 and taking one fresh new-code canary. Preserve cron, volume, default pin
and all other worker services. Do not recover an old attempt under expanded scope.

PR/CI, deploy source attestation, fresh source/VIN/readback, exact service-odometer
preservation and signed-in production health-panel acceptance remain release gates.
Rollback: stop new captures or remove only the reviewed target config after all
pending attempts are reconciled with their exact mapping; preserve imported
append-only captures and all source/receipt evidence. Never rewrite existing
attempts to force recovery under a different scope.


## Protected merge and deployment

PR770 passed all seven protected checks on `e9d2d2b3` and squash-merged as
`d717486eed116a03f6da0830704a4a5207918258` at2026-11-04 06:19:06UTC.
The first broad frontend run had one unchanged return-context test hit its5s
limit (2306others passed). The exact file passed6/6 locally; the frontend path
was rerun with freshly prepared dependencies and passed without changing tests,
assertions or timeouts. Backend critical and full suites passed in the initial run.

Existing-code preflight execution`c20e58f4-d26b-4f27-a2e6-0ed7253d3809`
ran06:05:29–06:10:43UTC. SSH inspection found zero pending commit receipts across
568retained receipts before its new import. Application logs then confirmed
`mode=commit, stage=verified, committed=true`,36created,2excluded,2source-missing
and2unavailable at06:10:38UTC, followed by worker-complete. Fresh source rows
for both exact VINs were inspected:603693231.19mi/23546h and609672634.54mi/8293h.
The source609 readings remained excluded under the old default fleet pin.
A monitor printed full final payload, but the container exit returned transport1;
that wrapper did not retain the final payload. Verified application logs and the
preexisting no-pending inspection establish the old-scope rollout prerequisite.
Do not treat the locally named `baseline-verified` partial19-row source capture
as complete source evidence. Its protected-record baseline is independently valid.

The reviewed609 provider/vehicle/customer configuration was set with skip-deploys
only after this verified old-scope completion. The tenant, source account,
default77Cargo pin and commit setting were preserved. No fleet relationships,
owner/payer pointer, canonical mileage, financial/provider records or other workers
were changed.

Worker deployment`13527d1a-d731-40d7-b8f3-21d4a7d4a38e` succeeded from a git archive
of the exact merged backend plus the worker-specific manifest; no environment,
private output or untracked files were uploaded. API deployment
`434306bc-dc56-4935-aba8-cb0bb182eaa7` also succeeded and public`/build-version`
reports the exact merge, built06:21:28UTC. SSH on the new running worker attested
all three reviewed file hashes above, the expected tenant/default fleet, saving
true and exactly one609 exception. Its manifest retains hourly`30 * * * *`,
restartNEVER, one replica and persistent`/data`.

Exactly one new-code canary`671786f5-8843-4c29-b4a4-af3074c51db1` started
06:23:35.498UTC. Its new source started06:24:00.050UTC and finalized all21rows with company checks.
Application receipt verified39created captures at06:29:15.516UTC; worker-complete
followed at06:29:16.032UTC and the execution exited06:29:17.753UTC (342seconds).
The monitor was pinned to the new execution start and saved the complete verified
payload before container shutdown. Its SSH transport exited1 on normal container
exit; acceptance uses the complete matching payload plus independent API readback,
not platform/transport exit status.

Source/receipt SHA256:
`93107f53d9b1fa883e1882a3f9c5d2475c5c55c1eef7708758f16feeaf3956eb`.
Persistent source directory:
`/data/motive-health/20261104T062336Z-c9a1aeb9-2695-4a47-b3e7-9441af33da02/`.
Receipt is committed/verified with39unchanged replays and39exact readbacks, no
pending commits, expected609-only reviewed target and default77Cargo pin.

| Tractor | Mileage | Engine hours | Source read (UTC) |
| --- | ---: | ---: | --- |
|603|693,231.19mi|23,546h|2026-11-04 06:25:51.412|
|609|672,634.54mi|8,293h|2026-11-04 06:26:11.158|

Fresh independent **live backend QA GO**: exact VIN/provider/vehicle/membership,
source/receipt hash, saved capture IDs, both projected snapshot IDs, source values
and source-read capture time all match. Provider observation time remains unknown.
An independent query through the deployed API service successfully read back both
vitals and both current diagnostic captures. API SSH completed with exit0.
Protected baseline owner/customer, membership IDs/intervals, relationship hashes
and canonical service odometers remain unchanged:603682225mi,609652767mi.
Worker image attestation reports
`sha256:48a07c7a2d4d578331c8e7d3b053874b0939321ca6b2869d4a84f34dcfabd568`.
No provider-account, financial, ownership or fleet-transfer mutation occurred.

The Mac remained locked at the production browser gate. A signed-in tab was opened
on the correct609 detail before rollout, but clicks cannot complete while locked.
The user has been asked to unlock; no live popup acceptance is claimed yet.


## Production visual acceptance completed — 2026-11-04

After the user unlocked the Mac, the agent opened a dedicated signed-in production
Fleet tab. The browser connector's click path timed out; native Chrome controls
completed the actual journeys without changing any business records.

-609: selected the existing Elis Logistics LLC (DBN)609 detail, clicked View health,
then observed Mileage672634.54mi and Engine hours8293h in the Truck health panel.
Fault codes remained visible alongside the readings. Service odometer652767mi is
separate and unchanged. A clear browser screenshot was saved locally at
`/tmp/db036-health-ui-proof/609.png` and directly inspected by independent QA.
-603: closed609's panel, returned to Fleet board, clicked the exact
`Open Elis Logistics LLC (DBN) 603 truck details` button, then View health.
The correct Elis603 header and rendered health fields show693231.19mi/23546h,
with fault codes alongside and separate service odometer682225mi.
Selected actual native accessibility output is retained locally at
`/tmp/db036-health-ui-proof/visible-readings.txt` and reviewed by independent QA.
A603 screenshot retrieval timed out; no603 screenshot is claimed.

Both panels display a November4 dashboard capture. These observations verify the
visible fields and record identity; they do not establish provider observation-time
precision, present device health, or continuously fresh collection.

Fresh independent **UI evidence QA GO** follows direct inspection of609's screenshot
and review of603's retained native click/AX evidence. Together with the earlier
independent production backend readback, the requested collection/display outcome
passes acceptance. No new collection trigger, import, status change, inspection,
repair, payment, fleet membership or other business-record mutation was performed
for this visual check. The previously blocked visual gate is now closed.
