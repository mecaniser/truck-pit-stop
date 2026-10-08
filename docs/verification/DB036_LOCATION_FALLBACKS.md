# DB-036 location collection fallbacks

Owner: Backend & Integrations. High-risk worker change; no migration or public API change.

The location collector previously required a US ZIP-formatted address in a fixed
text position and a particular timestamp-status element before attempting to copy
coordinates. Read-only live probes confirmed valid city-only and named-place
locations were rejected, and one location lacked that timestamp element.

Acceptance:
- Each vehicle attempt uses a fresh page and verifies the observed vehicle link
  and exact VIN before and after collection; a changed/ambiguous VIN fails closed.
- One bounded fresh-page retry may recover missing UI fields. No fields are mixed
  between attempts.
- The visible location control provides Copy coordinates independently of the
  optional address label. Two matching coordinate reads are required.
- Unique status-owned tooltip text is retained even when normalization cannot
  establish an observation timestamp. Observation time remains unknown; source
  read time is separate. Conflicting tooltip/coordinate observations are rejected.
- Unknown-time coordinates may fill a first-ever position but cannot supersede
  any prior position. Same unknown coordinates do not refresh capture time.
- Tenant, actor, VIN, membership, source recency, and unchanged replay checks remain.
- Missing device/location controls preserve prior positions and remain unavailable.

Runtime preflight October 8: branch codex/motive-location-fallbacks based on
6f2947a7. Local 5173/PID77357 belongs to truck-health-popover; no backend8000 or
approved backend/.env exists here. Other runtime preserved. Isolated tests and
source-only Railway canary do not establish local fullstack readiness.

Source probes run in isolated DBN-motive-location-canary with no database
configuration, no schedule, and no imports. Private evidence stays outside Git.
Required gates: independent QA/security, protected CI, immutable deployment,
fresh dry run followed by receipt/replay/readback and retained schedule checks.
Rollback: restore the previous known-good location worker image; retain receipts,
existing positions and the hourly schedule. Trip and health workers are unaffected.

## Acceptance and release, October 8

PR #486 merged as `110beb94b3421fbfb5b5b162a652da5ff17c6f4c` after all six
protected checks passed. Independent QA/security reviewed the source and full-fleet
dry run. Verification passed: 47 focused backend tests, 12 collector tests,
12 legacy assertions, and clipboard/timestamp checks.

The live canary exposed a persistent promotional tooltip and nested tooltip DOM.
The final collector compares visible leaf tooltip text before/after hover and
rejects ambiguous new content. A five-vehicle source-only probe and complete
22-vehicle capture then passed.

At 05:51 UTC, controlled capture saved 9 updates; 5 positions were unchanged,
6 source vehicles were unavailable, one VIN was unavailable, and one unknown-time
position was blocked. The source-missing board row overlaps the VIN-unavailable
unit, so these counts are not distinct fleet totals. Same-input replay returned
the identical 9 snapshot/request IDs and capture times with `created=false`;
all 9 saved-receipt and fleet-projection readbacks passed. Unit 77 was blocked as
`prior_time_unknown` on both passes. No credentials or private source data are
committed.

Authenticated production fleet verification showed 609 in Simpsonville with a
minute age, 531 in Talladega, 6 in OH, and retained 77 in Westwood. Unit 6's source
label only says OH; no city was invented. The map remains 15 located and 7 without
coordinates.

Production location deployment `c7dc3d55-d2a1-4a86-9ee1-594274c9f619` succeeded,
built from the immutable merged archive. Running collector/importer file hashes
match the merged source. Configuration preserves hourly `0 * * * *`, normal
`python -m scripts.motive_sync.run_worker`, restart NEVER, one replica, `/data`,
and automatic saving enabled. The production acceptance run completed successfully at 05:59:48 UTC.
The unscheduled temporary canary was stopped after saving private receipts.
Trip and health schedules were independently confirmed unchanged.

Production receipt `/data/motive-sync/20261008T055609Z-9ce6a325-e9bc-47e1-a4d8-a2e8c9527852/receipt.json`
confirms 7 newer snapshots, all with saved-receipt and post-commit board verification;
6 unchanged, 7 unavailable, 1 missing VIN and 1 retained unknown-time position.
The source-missing row again overlaps unit 26. Six unavailable rows lacked a
provider location; 531 returned `source_changed_during_capture`, safely retaining
the position saved during the controlled run. This is a successful consistency
rejection, not a fabricated fresh location. Unit 77 remained `prior_time_unknown`.
The one-shot container exited promptly; it was restarted once to retrieve its
persisted receipt through authenticated SSH. The additional normal capture was
left running under the same existing saving policy and hourly schedule.

Rollback target is previous location deployment
`111a56b0-1c59-4024-9e95-6043e9b53c7d`. No rollback trigger occurred.
