# DB120 — Vehicle service-history CSV export

Status: approved by Product; Architecture owner external_history_contract.
No migration. Additive read-only staff API. Implementation agents cannot approve independent QA/Security.

## Outcome and scope

Export the exact active truck's complete matching service history from customer vehicle details or the repair-order vehicle context, independently of the visible page. One CSV row per qualifying repair order or outside-shop record. No costs, charges, balances or pricing amounts are exported; internal-fleet pricing and outside-shop cost comparisons stay out of this history file. Existing imported split records remain individually identified; export does not consolidate them or assert invoice reconciliation.

Include repair orders in completed/invoiced/paid status with matching tenant/vehicle and no deleted_at, including internal-fleet work. Include outside-shop records with matching tenant/vehicle and neither deleted_at nor voided_at. Do not filter service history by current customer/bill-to: history follows the truck after transfers/merges. This is a staff-only export, not a customer/fleet grant. Outside-shop original_vehicle_id remains visible as provenance after merges. No mutations, invoices, payments, current mileage/PM changes, attachments, or audit payload export.

## HTTP contract

`GET /api/v1/vehicles/{vehicle_id}/service-history.csv`

Optional `date_from=2026-01-01` and `date_to=2026-12-31`, inclusive ISO calendar dates, individually optional. Strict YYYY-MM-DD format, 1900–9999; date_from must not exceed date_to. Unknown query parameters are rejected (422). There is no skip/limit/format/customer/tenant override. Filter the **History date** defined below, never pretend a record-created date is a completion date.

Success 200, UTF-8 BOM CSV with CRLF, standard quoted CSV escaping:

- Content-Type: text/csv; charset=utf-8
- Content-Disposition: attachment; filename="vehicle-service-history-<vehicle UUID>.csv"
- Cache-Control: no-store
- X-Content-Type-Options: nosniff
- X-Export-Vehicle-Id: canonical exact vehicle UUID
- X-Export-Row-Count: integer (only returned on success)
- Access-Control-Expose-Headers: Content-Disposition, X-Export-Row-Count, X-Export-Vehicle-Id (existing permitted origins only; no CORS origin/credential changes)

Filename contains no user content. Frontend downloads the authenticated response blob only on success, never navigates directly to an API URL, never treats an error blob as a file; it parses JSON failure detail and retains date choices for explicit retry. Abort/scope completion to tenant, actor, role, session epoch and exact vehicle; a late response cannot download for a different vehicle/session. No blob/query caching. One export-in-progress at a time per open export UI. Cancel/Escape closes without changes, including during a pending export.

### Exact columns (in this order)

1. Vehicle ID
2. Unit
3. VIN
4. Year
5. Make
6. Model
7. Record ID
8. Source — `Shop work`, `Imported ETS history`, or `Outside-shop history`
9. Original vehicle ID — outside record original_vehicle_id, otherwise blank (never fabricate native pre-merge identity)
10. History date — ISO date, used for ordering/range filters
11. Date basis — `Work completed`, `Imported completion date`, `Record created`, or `Reported service date`
12. Service date — ISO date only when actually known; blank for missing RO completion
13. Provider — current tenant name for native shop work; `Easy Truck Shop import — provider not recorded` for imported ETS; recorded provider_name for outside shop
14. Reference — order_number or outside reference
15. Work description — RO.description or outside description; no notes fields
16. Operations — nondeleted same-tenant Labor.description, in created_at/id order, joined by newline; outside blank
17. Odometer (mi) — see rules below
18. Odometer basis — see rules below

All untrusted text cells are protected against spreadsheet formula execution: after control-character cleanup, if the first nonwhitespace character is =,+,-,@, prepend an apostrophe; preserve meaningful CSV commas, quotes and newlines. All text is CSV escaped. Remove NUL/unsupported C0/C1 controls; integer/date constants are canonical generated output. This protection includes unit/VIN/provider/reference/work/operation text, not only descriptions.

### Date and odometer rules

Native completed_at becomes tenant-local calendar date (tenant timezone; configured fallback America/New_York). Imported ETS completed_at is an imported calendar date stored as a timestamp: keep its UTC date rather than shifting it into the previous day. Unknown completion => Service date blank; History date is created_at in tenant timezone with Date basis `Record created`, including imports. UI explains this date fallback before export. Outside-shop uses reported service_date, not created_at. Newest History date first, then source/record ID deterministic ties. Valid dates use inclusive bounds, internally translating native timestamp boundaries in tenant time and imported completion bounds in UTC.

Native mileage_out when present => `Mileage out`; otherwise mileage_in => `Mileage in` or `Carried-forward mileage in` if flagged. Imported mileage_out/mileage_in => `Imported reading`. Outside odometer => `Reported outside reading`. Missing values leave both cells blank. Never fall back to the truck's current mileage. Zero is a known value.

### Errors and boundedness

Return JSON (not a CSV attachment). Domain errors use `{"detail":{"code":"...","message":"..."}}`; framework request validation remains standard422 detail arrays.

- 401: unauthenticated via existing active-user dependency.
- 403: role outside owner/admin/receptionist, before data reads; customer, driver, mechanic, fleet manager and superadmin are denied.
- 400: allowed staff actor has no tenant.
- 404 code`vehicle_not_found`, message`Vehicle not found`: foreign-tenant, missing or archived truck; indistinguishable.
- 404 code`history_empty`, message`No completed shop work or active outside-shop history matches this date range.`: active accessible vehicle, no matching records.
- 422: invalid/reversed date query, repeated or unsupported query parameters; domain code`invalid_export_filter`, otherwise framework detail arrays.
- 413 code`history_export_too_large`, message`This export is too large. Choose a narrower date range and try again.`: over 1,000 records, over 10,000 matching operations, raw source work text over 2 MiB characters, or CSV over 2 MiB. Metadata-only candidate queries use cap+1; SQL aggregate raw-text preflight precedes streamed, bounded text projections that also guard concurrent edits; no truncated CSV or empty-success export.

All route responses, including failure responses, carry no-store/nosniff. Cap is enforced before success bytes are emitted. Very large same-day work can still exceed the cap; user receives the limit error, never incomplete data. No asynchronous export/storage/attachment service first release.

## Implementation and consistency

Dedicated service + dedicated router under vehicles; explicit selected fields, no generic serializer or eager notes relationships. Every RO, operation and outside-record query independently scopes tenant and vehicle/selected order IDs. Both active and terminal-status predicates apply before caps. Ignore ended customer relationships for this staff-only physical-history read. No new customer authorization.

GET is naturally repeatable/idempotent with no audit or business writes. Concurrent edits may appear in the next export; this is a current read, not a signed immutable snapshot. Recheck exact active tenant vehicle before returning to prevent known archived/merged-target stale controls. No row locks or serializable transaction added. Cross-query read consistency does not confer a source-of-truth finance reconciliation claim.

## Fixtures and acceptance

Mixed fixture: native completed RO with two operations; imported ETS paid RO with unknown completion (Service date blank, Record created basis); outside records with historical odometer zero/unknown; in-progress, cancelled, deleted RO, deleted labor and voided outside record excluded. Duplicate values in two operations remain two descriptions; cost fields never appear.

Test all permitted/denied roles; unauthenticated; missing/archived/foreign vehicle; malicious inconsistent foreign-tenant RO/labor/outside links; foreign/deleted customer data not exported; deleted/voided and open-work exclusions; only eligible history beyond page25 exported; all source/date/odometer/zero/null semantics; imported midnight date; tenant DST edge; inclusive optional ranges/reversed/invalid/unknown query; cap+1 and byte-limit failure without attachment; private notes/operation-note envelopes/contact/payment/balance/cost fields absent; formula strings with leading whitespace/control/newline plus proper round-trip CSV escaping; no changed DB rows/timestamps or external events; merge/transferred physical-history behavior.

Frontend: authenticated download, exact content/count and identity, date range recovery, empty/error retained inputs/Retry, pending cancel and stale identity/session, keyboard focus/Escape, desktop1280, portrait390/320 and landscape740. Actual downloaded bytes and production desktop/mobile browser workflow are release evidence, not just mocked response tests.

## Rollout / rollback / ownership

Backend owner: service/router/registration and backend tests. Frontend owner: CustomerVehicleDetail shared export affordance and compact accessible inline form with date filters + tests. No new dependencies or schema/data migration. Independent Security for authorization/data export and QA for actual download workflow. Existing APIs unchanged. Rollback by reverting additive endpoint/frontend; no data repair. Release gates remain parent-owned; no self-approved security or QA.
