# DB-130 — Outside-shop history search

Architecture & API Contracts decision: approved, 2026-10-15. Standard product
lane: additive read behavior with unchanged authorization, schema, and mutations.
Backend & Integrations owns the outcome; independent journey QA is required.

## Outcome and scope

Find prior outside-shop work for the exact vehicle by shop, work performed, or
reference without stepping through every page. Search applies to the complete
authorized record set, not the ten rows currently rendered. Existing native shop
history, export, receipt content, and change-event history are separate surfaces.

## Request and response

Add optional `search` to `GET /api/v1/vehicles/{vehicle_id}/external-services`.
Existing `skip` (default 0, minimum 0), `limit` (default 25, range 1–100), and
`include_voided` (default false) keep their behavior.

- `search` is a string of at most 200 characters on the wire; a longer value is
  rejected with HTTP 422, never silently truncated. Trim surrounding whitespace
  before matching. Omitted, empty, and whitespace-only values mean no filter.
- Match the whole normalized string as a case-insensitive **literal substring**
  of `provider_name`, `description`, or nullable `reference`, joined with OR.
  There is no token splitting, fuzzy matching, or accent normalization. `%`, `_`,
  backslash, quotes, and SQL-looking text are ordinary characters; parameterize
  the predicate and escape LIKE metacharacters if LIKE/ILIKE is used.
- Apply the predicate to the existing scoped conditions before both count and
  pagination. Preserve descending `service_date`, `created_at`, then `id` order.
- Return the existing `ExternalServicePage`: `items` retains its full unchanged
  `ExternalServiceItem` shape; `total` is the matching count; `has_more` remains
  `skip + len(items) < total`. No response fields are added or removed.

Example: `?search=air%20dryer&skip=0&limit=10&include_voided=false` returns matching
items in the established order, regardless of where they appeared in the
unfiltered list. A successful no-match response is exactly
`{"items": [], "total": 0, "has_more": false}`.

## Boundaries and failure behavior

Run the existing `load_vehicle` gate before record reads. Allow only garage
owner, garage admin, and receptionist; preserve tenant membership, non-deleted
exact vehicle, record tenant/vehicle, and non-deleted record predicates. Voided
records match only when `include_voided=true`. Do not join receipt bytes or audit
snapshots, broaden customer/driver/mechanic access, or search another vehicle.

Existing outcomes remain: unauthenticated 401, disallowed role 403, missing tenant
400, absent/foreign/deleted vehicle 404 with the existing generic message, invalid
query bounds 422. Successful responses remain `Cache-Control: no-store`. A query
failure is not an empty history. Search creates no events, versions, receipts,
financial changes, mileage updates, timers, or completion changes.

This GET is read-only and repeatable, with ordinary current-database pagination;
it is not a snapshot cursor. Existing mutation replay IDs, optimistic versions,
conflict handling, and retained void/restore history remain unchanged. No
migration, dependency, feature flag, or backfill is needed. Deploy the additive
backend before or with its consuming frontend; old clients continue unchanged.
Rollback can remove the search UI and additive parameter without data work.

## UI contract

- Place an explicitly named search field in outside-shop history with a visible
  clear action and a short scope hint such as “Shop, work, or reference.” Keep
  the native history search distinct. Use a 200-character input limit.
- A normalized query change, clear, or Show voided change resets to page one in
  the same state transition. Preserve the query across paging and editor Cancel
  or Escape; clear it on vehicle or tenant/actor/role/session change as the
  existing keyed component already does for its local state.
- Include normalized search in the existing tenant/actor/role/session/vehicle
  query key and request parameters; pass the cancellation signal. Rapid typing
  must not show an older response as the current result. If input is debounced,
  identify the pending state and do not mislabel previous rows as new matches.
- Distinguish loading, matching results/count, no matches with clear action,
  genuinely empty history, and failed load with explicit retry. Do not expose
  stale cached rows after a failed or denied refresh; keep the query for retry.
- Lock search/clear, Show voided, and paging while a service editor is open, as
  paging and the voided filter already are. Background refresh/search must not
  unmount a draft. Preserve failed-save and stale-version recovery. If another
  actor's edit makes a record disappear from the filtered list, retain the
  draft and the existing explicit recovery/Cancel message; absence from matches
  must not be presented as deletion or permission loss.
- After a successful mutation, invalidate all searches for that scoped vehicle.
  Show the existing success confirmation even if the saved record no longer
  matches. If mutation removes the final match on a later page, return to a
  valid page instead of suggesting that no matching history exists.
- Preserve customer/repair-order return state and parent search. Keep desktop
  density, theme tokens, one workspace scroll area, named controls, visible
  focus, mobile 44px targets and 16px text inputs; no horizontal overflow or
  wrapped button labels at narrow widths.

## Evidence and acceptance fixtures

Existing implementation anchors: `external_services.list_external_services`,
`external_service.page`, and `ExternalServiceHistory.ScopedHistory`. Existing
backend tests cover role denial before data queries, tenant/wrong/deleted vehicle
guards, voided scope, ordering/paging, HTTP query validation, no-store, and no
native side effects. Existing frontend tests cover failed refresh hiding cached
rows, identity/vehicle changes, malformed responses, draft/conflict recovery,
and void/restore. Extend those contracts rather than replacing the guards.

Use at least twelve records for vehicle A so a provider, work, and reference
match can each exist beyond the first unfiltered page. Include case variations,
surrounding whitespace, null reference, literal `%`, `_`, and backslash, tied
dates/timestamps, and a voided match. Add identical searchable text on another
vehicle in the same tenant and a vehicle in another tenant.

Required focused checks:

1. Provider/work/reference and mixed-case matching, trimming, blank equivalence,
   literal metacharacters, no match, 200/201-character boundary, unchanged shape.
2. Count and pagination are based on all matching records; stable tie ordering;
   matching foreign/deleted/voided records do not escape existing scopes.
3. Unauthorized roles and foreign/deleted vehicles with search retain existing
   denial behavior; search does not bypass gates or produce side effects.
4. UI can find a match beyond page one, resets paging, clears/retries, ignores a
   delayed prior response, and preserves query/draft through Cancel, Escape,
   failed save, and filtered-out stale-version recovery. Verify post-mutation
   invalidation and an emptied later page.
5. Signed-in local and deployed production desktop, narrow portrait, and compact
   landscape checks in Light and Night Shop: search/type/clear, no-match/retry,
   matching record/edit/Cancel, Show voided, exact vehicle and parent return.
   Record measured viewports and screenshot evidence; browser touch emulation
   is not physical-device certification. Production uses only explicitly marked
   synthetic QA records and restores any fixture/appearance changes.

Architecture approval establishes the contract only. Implementation, automated
checks, independent QA, protected CI, merge/deployment, and actual production
acceptance remain the delivery owner's responsibility.
