# DB-036 history collector independent review

Reviewer: independent history_review agent; implementation by root and
history_contract. Read-only review; no application edits or production writes.
Scope: browser collection, offline normalization, safe immutable import handoff.
Date: 2026-10-03. Initial gate: **NO-GO pending corrections and final collector**.

## Evidence

- Read contract, delivery instructions, normalizer, its documentation and tests,
  initial collector module. Services not started: this is offline/read-only QA.
- `python3 -m unittest backend/tests/test_motive_history_preparation.py`: 14 pass.
- Independent synthetic reproductions: all of the following currently produce
  one accepted row despite malformed or ambiguous source structure:
  - `links=["https://unrelated.example/123"]` with known provider ID 123;
  - `links=["/vehicles/123", "/vehicles/999"]`;
  - distance text `4,0.25`, silently normalized to 40.25 miles.

## Findings returned to owner

1. **P1 source identity validation:** first-link basename is treated as a verified
   provider identity regardless of origin/path, and additional disagreeing links
   are ignored. Accept only observed Motive vehicle-summary links and reject
   multiple distinct identities. Add negative tests for foreign paths/origins and
   multiple vehicle IDs.
2. **P2 malformed numeric format:** loose comma handling invents a numerical
   interpretation. Validate plain digits or correctly grouped thousands before
   conversion; malformed measurement text must be quarantined.
3. Collector is still under implementation. Final gate requires actual filter
   range/account checks, full expected column order, definitive traversal-end
   evidence, private checkpoint persistence, and bounded failure behavior.

## Positive boundaries checked

Tenant/company exact agreement is required between capture and mapping; duplicate
VIN/provider mappings reject. Pre-membership departures, future source captures,
ambiguous DST, partial windows, unknown vehicles, invalid durations and incomplete
arrival minutes are excluded or rejected. Conflicting source core removes every
accepted version for that identity. Prior matching core retains complete frozen
payload; downstream strict importer remains responsible for revalidating prior
payload schema and live tenant/actor/VIN/membership bounds. Files are 0600 inside
0700 new output directories; existing output directories are not overwritten.

This review does not certify browser collection, complete historical coverage,
committed imports, daily scheduling, deployment, or runtime acceptance.

## Normalizer correction re-review

Root corrected the findings; reviewer made no corrective edits. Independent
rerun: **16 tests pass**. Repeated all three original reproductions: unrelated
URL, conflicting links and malformed grouped mileage now accept zero rows with
explicit exclusion reasons. Additional positive controls accept the absolute
Motive URL and correctly grouped `1,040.25` mileage. The link expression anchors
the entire observed relative/absolute summary URL and requires one link.

**Normalizer component: GO**, subject to existing downstream strict importer
validation of frozen prior payloads and live tenant/membership authority.
Collector, end-to-end import, history UI and daily execution remain unapproved
until their separate evidence is reviewed. Initial findings 1 and 2 resolved.

## Imported date bounds API/UI review

Independent focused reruns: **55 backend tests pass** (trip and coverage suites),
including zero-result selected dates, pagination independence, selected vehicle,
foreign tenant, deleted vehicle, pre-membership trip exclusion and timezone date
conversion. Code inspection confirms history aggregate uses the same
`visible_query` with only request date predicates removed: tenant, vehicle,
fleet-customer, deletion, active membership, historical membership, capture and
completion bounds remain intact. Response nullable date fields are additive.
UI explicitly labels these as `Imported ... · Partial`; tooltip identifies
minimum/maximum imported departure dates and remaining gaps. This does not claim
continuous source coverage. **Bounds component: GO** (runtime/release pending).

## Collector completion finding

**P1 / NO-GO for automatic window completion:** deduplication by full raw JSON
counts changed versions of one physical trip as multiple rows. Reproduction via
mock page: source footer says 2 results; capture one provider/departure at 40 miles,
then revisit the same provider/departure at 41 miles. `receipt.rows.length` becomes
2 and `finalizeWindow(receipt, 2, "visible counter 1/2")` returns `captured` even
though the second physical source trip was never observed. Normalizer conflict
quarantine cannot restore that missing traversal coverage. Return to owner:
completion must use distinct stable source identities or reject changed versions
for completion while retaining raw evidence. Add overlap, changed-version,
missing-tail, loading and explicit-empty tests.

Independent frontend rerun: `FleetTrips.test.tsx` **20 tests pass**. Browser runtime
not independently rerun; root's acceptance remains required before release.
