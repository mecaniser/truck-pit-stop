# DB-036 current speed and driver coverage release

Accountable owner: Backend & Integrations. High-risk worker/data lane.
Status on 2026-10-16: **Done — deployed, data verified and authenticated production UI accepted**.

## Shipped behavior

[PR548](https://github.com/mecaniser/truck-pit-stop/pull/548) captures numeric speed
from Motive's visible Live location panel with the same verified source observation
as location. It preserves explicit zero, rejects unstable identity/observations,
and does not infer zero from a stationary label or invent an observation time.
Immutable speed-only supplements preserve existing location history and replay.
The overlap guard no longer counts disjoint lifetime history toward its limit.

Cards and truck details share a five-minute current-speed and motion rule and
age readings while open. The main fleet map keeps its separate location-age
rule; its operational truck status is not measured motion. Undated or stale
speed is unavailable; integration diagnostics label retained readings as recorded
speed. The hourly location schedule is unchanged: this is not continuous live telemetry.

The driver collector retries transient missing VIN reads, while actual VIN
mismatches and ambiguous identity still fail closed. No migration, authentication
change, contact rewrite or fleet-membership change was introduced.

## Source, checks and deployment

- Reviewed head: `5b1070c5948d95d03bf0fb314114083f5ca43cd6`.
- All six CI checks passed in run `38844297984`.
- Squash merge: `e3ff99e0c1ef866fe3fd711c2f248841fe7c1152`,
  2026-10-16 04:06:18 UTC. Backend, frontend and workflow trees match the reviewed head.
- Independent QA/Security and release-plan review approved the implementation.
  Focused verification: 80 SQLite backend, 4 PostgreSQL, 48 collector tests plus
  12 legacy assertions, and 76 frontend tests; lint, TypeScript and build passed.
- Actual local components at desktop and 390×844 rejected stale/undated speed,
  preserved fresh 0/45 mph, and expired open readings. This is not a local
  full-stack claim: backend port 8000 was unbound.

| Runtime | Successful deployment | Source proof |
| --- | --- | --- |
| Web | `c7eaef64-de93-4d94-9575-0180bea24bb1` | Merged SHA; four runtime file hashes verified |
| App worker | `6f0be5e5-4810-4da4-b8a7-e92a591b8eaf` | Merged SHA |
| Driver collector | `8bfb34f4-6451-42a6-98f0-9d37a5e1161a` | Immutable merged backend archive; six runtime hashes verified |
| Location collector | `0d3efd78-6fe8-4c15-93ba-05d8fd32be17` | Immutable merged backend archive; four runtime hashes verified |

Both dedicated collectors use the existing pinned Motive worker Docker runtime.
The driver command remains `python -m scripts.motive_drivers.run_fleets`, daily
at 13:45 UTC, with existing PostgreSQL journal storage and no volume. Location
remains `python -m scripts.motive_sync.run_worker`, hourly, commit enabled, with
its existing `/data` volume. One replica and no automatic restart are retained.
No new storage volume, billing plan or schedule was introduced.

Web readiness passed after rollout and again after both canaries: database and
Redis healthy, uptime over 24 minutes on the final check.

## Committed production canaries

The supported Railway cron-run command triggered each existing service once
outside its schedule. No temporary keepalive command was used.

| Worker | Execution | Terminal result |
| --- | --- | --- |
| Driver | `12659a0e-7e0a-4188-b903-8f327bae422a` | EXITED 04:27:25 UTC; `fleets_complete`, all three fleets |
| Location | `e90c6427-e505-4c1b-a624-4622770c0ee1` | EXITED 04:19:12 UTC; `worker_complete` |

Driver durable journals reached all five stages through verified/committed:

| Fleet | Journal | Saved records / verified readbacks |
| --- | --- | --- |
| 77 Cargo | `87909fcc-adb2-4f14-be0d-db4679b0bbf3` | 18 |
| Elis Logistics | `f6fc77c1-f3a1-417d-b192-f4bd0b0736bb` | 1 |
| DONTRANS | `9733fd63-4961-4598-a8ca-3eb2d532b2ca` | 1 |

Each source collection covered the complete 22-row directory. Final deployed
service readback at 04:33:53 UTC showed 20 available, non-stale records checked
on October 16, including trucks 609 and 532, and 15 numeric safety scores.

Location covered 22 vehicles with 18 source locations and committed nine updates.
The database contains nine distinct saved request/snapshot identities and eight
new numeric speeds. Independent review measured those speeds at 70–250 seconds
old at commit. There was no projection failure.

A separate controlled import through the deployed Web importer proved ten
committed observations and ten identical replays, with unchanged request,
snapshot, capture time and content fingerprint and no replay writes. It used
fresh source-only collection from the exact merged archive and ran while the
hourly location worker was idle. This controlled proof is distinct from the
dedicated worker execution above.

Final preservation readback at 04:33:50 UTC, after the last driver commit, matched
all four pre-canary fingerprints: 1,474 vehicle identity/contact rows, 48 fleet
memberships, and outside-scope driver captures/directories. Truck 609 remains in
Elis Logistics. Private source and customer data are not included in this document.

## Coverage and remaining provider gaps

- Twenty records are matched; five have no reliable numeric provider score:
  trucks 17, 4, 5, 532 and 603. Missing scores are not zero.
- Truck 70 has no assigned Motive driver. Truck 26 lacks a source VIN.
- At the user's direction, truck 26 has DBN-only temporary reference
  `PENDING-26` and an explanatory note. It is not a real VIN and is not used for
  automatic matching. Driver assignment revision and provider identity were preserved.
- Motive provides no current location for trucks 5, 532 and 70; truck 26 remains
  blocked by missing VIN. Trucks 4 and 77 have old/unknown-time source positions.
- W900's historical 10 mph reading has no observation timestamp. It remains
  historical data and fails the deployed current-speed rule. Its latest provider
  view gave no numeric speed, so no zero was fabricated.
- The daily audit found verified runs for all three fleets on October 10, 11,
  13 and 14, with gaps on October 12 and 15. October 15's execution crashed at
  VIN recheck. The new retry recovered a demonstrated transient missing VIN
  for 532; old logs do not prove every historical failure had that same cause.
  Successful canaries establish recovery, not a guarantee of future daily runs.

## Authenticated production acceptance — October 16, 9:17–9:33 AM EDT

The user restored the existing sign-in session. Production checks used the normal
in-app browser at 1280×900 and 390×844. The active Web deployment was
`582d69ad-3fec-4103-8297-46c9ae245763` at `d5cb662839f82789184be846bc0db876c860594e`,
one commit after this release. Independent ancestry review confirms PR549 changed
no frontend, fleet telemetry or Motive collector files. The observed app asset was
`index-B1jbD32a.js`.

| Journey | Desktop | Phone viewport |
| --- | --- | --- |
| Fleet card: W900 score 88, old 10 mph unavailable, separate location age | Passed | Passed |
| Truck details: same score, unavailable speed, motion unknown | Passed | Passed |
| Fleet map: W900 selected, score 88, last-known location, usable driver popover | Passed | Passed |
| Fresh truck 860 card and details: 51 mph with source timestamp | Passed | Passed |
| Fresh map position and truck 860 score 85 | Passed | Passed |

All six score-popover entry points opened the correct record. Phone content
remained inside the viewport, scrolled through safety events, and closed with
Escape or the close control. No horizontal document overflow occurred at 390 px.
No browser warning/error was captured. The old `Local contact` wording was absent.
These are browser viewport checks, not physical-device certification.

The full board showed 22 truck cards, 15 numeric scores and six unavailable-score
buttons; the latter includes truck 26's local alias without a Motive capture.
Truck 70 remains unassigned. Truck 609 retained Elis Logistics and score 81.
Truck 532's record showed an October 16 check and an explicit unavailable safety
summary; no zero score was substituted.

One additional off-schedule location refresh ran after the existing hourly job
had exited. Execution `e223df0d-8fe0-4b50-96d2-371b584ff95e` completed at 9:25:56 AM
EDT: all 22 vehicles attempted, 17 locations currently available from the source,
12 committed updates and no projection error. The map retains 18 saved positions,
including an older position that the current source did not return. This does not
turn that older position into a current observation.

The refreshed board preserved five explicit 0 mph readings. Truck 860 showed
51 mph, observed around 9:25 AM and captured at 9:25:50 AM, on both viewport sizes.
At 9:28:52 AM its open phone details showed 51 mph and `moving`. Without a reload
or intervening UI interaction, the same view showed `Unavailable` and
`motion unknown` at 9:30:39 AM. Its location and safety score stayed visible;
the fleet card also suppressed the expired speed. No clock or response mocking
was used. The fleet map's location freshness remains independent of speed expiry.

Independent UI acceptance is GO. Together with the earlier backend/worker GO,
the required DB-036 release gates are closed. No app code changed in this final
verification. The default viewport was restored and the fleet board left open.

Private screenshots, complete DOM snapshots, console output, execution receipt
and before/after timestamps are retained in
`output/speed-coverage-2026-10-15/production-ui-2026-10-16/`.

## Rollback and evidence

Rollback signals: provider identity mismatch, replay/readback divergence,
overlapping incompatible speed, changed protected identity/membership, worker
failure, or incorrect current-motion display. No such backend signal occurred
during the completed canaries.

Previous worker images remain recorded in the private release receipt:

- Driver: `sha256:4eda1a6233747fb5d8ded8e27f56f4dde6e036e573d42d088195a677a5acad80`.
- Location: `sha256:e6c2ec3e9f6786c1fa5c2c17e9df29bc6b8f9da0315ad953a29117141c8e4522`.
- Previous Web deployment: `6c2e0321-5ca4-4f96-a7dc-d0413aaf602c`.

See [contract](../contracts/db036-current-speed.md) and
[independent gate](../evidence/db036-current-speed-independent-gate.md).
Private evidence is retained under `output/speed-coverage-2026-10-15/`, including
CI, deployment/hash proofs, execution logs, durable journals, replay receipts,
coverage audits and preservation fingerprints. It is excluded from the commit.
