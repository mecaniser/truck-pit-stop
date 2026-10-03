# DB-036 browser history collector contract

Status: Architecture handoff, 2026-10-03. Accountable implementation owner:
Backend & Integrations. This document specifies the boundary; it is not evidence
that a collector is installed, scheduled, or that April history is imported.

## Outcome and scope

Import completed trips visibly available in the authorized Motive company from
2026-04-01 through the current day, with resumable daily refresh until OAuth is
available. Preserve the existing immutable trip importer and tenant checks.
Browser collection and database import are distinct stages with separate receipts.
Daily execution requires a reachable machine and a valid logged-in browser
session; an expired session is a visible authentication-required result.

Do not assert a universal one-year Motive retention limit without verifying it
in current official documentation or the account's visible controls. Distinguish:
requested history start, earliest source history accessible, earliest imported
trip, and verified collection coverage. None implies the others.

## Existing constraints verified in code

- `scripts/import_motive_trips.py` accepts 1–1,000 rows per atomic transaction,
  defaults to dry run, and requires an active owner/admin in the selected tenant.
- VIN must resolve to exactly one undeleted vehicle in that tenant. Exactly one
  current active fleet membership must cover departure, arrival (including the
  full arrival minute), and source-read time. Current read projection also
  requires `started_at >= membership.effective_from`.
- Consequently April trips can be rejected even for a correctly matched current
  truck if membership begins later. Inventory membership bounds before import.
  Never change membership dates merely to make backfill pass. Any genuine
  historical ownership/access correction requires separate evidence and review.
- Database identity is `(tenant_id, provider_vehicle_id, started_at)`. The source
  trip ID is not currently persisted as an application trip identifier. Different
  source trips departing in the same displayed minute must be quarantined rather
  than collapsed or assigned invented seconds.
- Digest excludes only `source_read_at` plus existing null/default compatibility
  cases; it includes addresses, unit, stops, measurements, and frozen fuel metrics.
  New source-read time alone is an unchanged retry. Changed measurements or a new
  MPG baseline are immutable conflicts, not permitted automatic updates.
- GET trips accepts at most 31 inclusive dates. A six-month backfill can be stored
  without allowing a six-month UI query; verify each month/window independently.
- Source is currently constrained to `motive_dashboard_manual`. Browser-assisted
  capture must keep that existing source until an explicitly reviewed migration
  changes it. Do not label it OAuth/live API.

## Current read-only discovery

Product/Delivery reports live SQL bounds: most current memberships begin
2026-07-22 20:13:45 UTC; truck 609 begins July 24 05:49:41 UTC; trucks
860/530/531 begin August 9 16:09 UTC. Apply each actual membership bound, rather
than treating those group descriptions as identity mapping data. Earlier source
rows are retained privately with `outside_membership` exclusion; no backdating.
The April source report visibly returned `No trips found` for the queried
filters. Record those exact filters in its receipt; that observation does not
prove an account-wide retention policy or absence in unqueried months.

Recommended implementation: reusable CUA-compatible collector module accepting
a supported page adapter, with bounded windows and private on-disk receipts.
A daily thread heartbeat can invoke that module using the existing authorized
browser. A standalone Playwright CLI is a separate browser/session setup and
cannot inherit IAB authentication automatically. Preserve `metrics: null` for
new historical rows; compare reobserved source core against saved rows and replay
the saved normalized row when core data matches, retaining frozen metrics.

## Collection artifact v1

Use a private run directory outside tracked source, with mode 0700 for directories
and 0600 for captured files/checkpoints. No credentials, cookies, authentication
headers, or browser storage exports in artifacts or logs.

Run manifest fields:

- `version: 1`, unique `run_id`, `tenant_id`, authorized source company identifier
  or verified visible label, `timezone: America/New_York` only when confirmed by
  the source, requested local `from`/`to`, and capture timestamps.
- Explicit per-vehicle mapping: provider vehicle ID, source unit, verified VIN,
  verification date/evidence reference. Unit number is descriptive, never the
  match key. A source company switch or VIN disagreement stops that mapping.
- Per bounded date window: requested range, actual source-filter range verified
  in UI, state, page/scroll checkpoint, unique observed row count, excluded row
  counts/reasons, raw-artifact hash, normalized-artifact hash, import receipts.
- States: `pending`, `collecting`, `collected`, `partial`, `authentication_required`,
  `source_unavailable`, `imported`, `import_failed`. A successful capture is not
  an imported checkpoint. Advance to imported only after committed receipt.

Raw rows preserve rendered column text and observed UI links, including a source
trip ID when visibly available. Normalized import remains the existing strict
`{"rows":[TripImport]}` shape; source-only fields remain in the manifest. The
collector must fail visibly when table headers or required fields change rather
than emit guessed or zero-valued rows.

## Traversal and time

Use the user-authorized browser session through supported UI automation. Read
rendered Trips/History data and interact with visible date/filter/pagination
controls. Do not depend on hidden application state, private HTTP endpoints,
or copied session secrets. A standalone script must have an explicitly supported
browser-control runtime; tool-session variables alone are not an installable
collector. Document the actual supported invocation and prerequisites.

Collect bounded daily/weekly windows (or the source's documented maximum), with
explicit end-of-list evidence for each. Repeated identical viewport content is
an error/partial outcome unless an end-of-list indicator or equivalent observed
boundary establishes completion. Capture total-count evidence where available.
Do not infer no trips from timeout, missing selector, or a temporarily empty list.

Use the source's displayed local dates and timezone, converting each timestamp
through the named zone; do not hard-code UTC-4 across all dates. Preserve
minute precision and measured duration separately. Keep ongoing rows out of the
completed-trip importer and revisit them in the next overlapping refresh.
Use actual read time for `source_read_at`, never import time or trip end.
Unknown stops, coordinates, fuel use and engine data remain null.

## Replay, checkpoint and import

1. Plan exact requested windows and capture raw pages before normalization.
2. Deduplicate identical observations by stable source identity and content.
   Detect conflicting versions and same-departure collisions explicitly.
3. Reconcile overlap with existing persisted identities/digests. Preserve frozen
   metrics for exact existing rows; do not attach today's MPG to old replay rows.
   Do not silently suppress changed source data merely because an ID was seen.
4. Write import batches of at most 1,000 accepted rows and separate exclusion
   reports for unknown VIN, duplicates, membership bounds, ongoing/invalid rows,
   source conflicts and unavailable history. The raw evidence remains preserved.
5. Dry run each batch, check tenant/VIN/membership matches, then use the existing
   transactional apply. Record created/unchanged IDs and batch hash. Replay must
   create zero additional rows. A failed batch does not advance the checkpoint.
6. Daily runs revisit a bounded overlap (recommended previous two days through
   today) and resume failed windows. This catches late completion but does not
   certify provider edits older than that overlap; periodic reconciliation can
   be added with its coverage recorded explicitly.
7. Use a local lock to prevent two collector/import runs sharing the same state.
   Atomically replace checkpoints. A crash between commit and checkpoint update
   is recovered by the immutable import replay, not by deleting stored trips.

Do not dynamically enrich backfilled April trips with a recent 30-day MPG as if
it were April efficiency. Omit estimate baselines for new historical rows unless
an appropriate documented estimation basis is intentionally supplied and clearly
labeled; measured fuel/MPG requires direct source evidence.

## History disclosure

The current `coverage: partial` contract remains truthful during backfill. A
compact UI may say `Imported history · Apr 1–Oct 3, 2026` only once that wording
accurately describes collected/imported coverage, with exclusions available in
details. Prefer `History from Apr 1, 2026` only after verifying the start boundary.
An earliest imported trip alone does not establish continuous coverage, and a
missing date must not be described as zero activity. Any provider retention text
must identify a verified source limit, not the user-requested start date.

If history coverage metadata is exposed in the app, return tenant- and
vehicle-scoped requested/verified intervals and gap statuses. Do not infer those
intervals with `MIN(started_at)`/`MAX(started_at)`. This is a new contract/migration
if persisted centrally and must be separately reviewed before frontend consumes it.

## Failure behavior and verification gates

- Expired login/MFA: stop source work, preserve checkpoint, request login; no
  credentials in environment variables and no repeated automated login attempts.
- Wrong company, unknown/duplicate VIN, inactive tenant/actor/membership: fail
  closed for that source/batch; no partial unreported attribution.
- Empty source window: record as confirmed empty only after successful filter
  and complete traversal; not as imported trips or globally complete history.
- UI drift, rate limiting, navigation timeout: bounded retry then partial/error;
  no checkpoints that skip unseen pages.
- Independent QA/security verify replay, crash recovery, authentication expiry,
  wrong company/tenant, pre-membership dates, same-minute collision, page overlap,
  empty-window handling, changed source content, DST and minute-boundary trips.
- Deployment/scheduling evidence must show the installed command, browser/runtime
  prerequisites, daily trigger, one real successful run, committed import receipt,
  production UI totals and exclusions. Scheduling a prompt alone is not proof
  of a working unattended scraper. Notify on completion/failure/login need rather
  than claiming fresh data when collection did not run.

No existing vehicle, service odometer, repair, PM or telemetry rows are modified
by the trip backfill. Fresh telemetry collection, if implemented alongside trips,
must use its existing separately reviewed snapshot importer and receipts.

## Additive imported-bounds read contract (approved implementation scope)

GET `/fleet/trips` adds nullable top-level `imported_start` and `imported_end`
(ISO local dates in the response timezone). They are the earliest/latest visible
imported **departure dates**, scoped to the same tenant, selected vehicle and
fleet-customer authorization/membership predicates, but independent of selected
dates and pagination. No visible imported rows returns both null. Existing items,
summary, date-window limit and ordering remain unchanged; no migration.

These endpoints describe only the bounds of recorded trips, not uninterrupted
coverage or provider retention. UI: `Imported Sep 28, 2026–Oct 3, 2026 · Partial`.
Null/older-server fallback: `Imported trips · Partial`. A concise tooltip explains
that dates bound imported departures and gaps may remain. Negative tests cover
other tenants, deleted vehicles and changed membership boundaries. Future or
incomplete source rows remain excluded by the existing visibility predicates.
