# DB-036 Motive OAuth and fleet connection contract

Architecture contract v1, 2026-09-29. Accountable implementation owner: Backend
& Integrations; Frontend consumes the routes below. Architecture GO for app-side
implementation and offline verification. Independent Security and QA approval
remain required. This document supersedes the sandbox credential prohibition
only for implementing OAuth code and encrypted storage: the user authorized the
full application connection workflow while Motive approval is pending. No real
credential entry, provider operation, activation, merge or deployment is implied.

## Identity and authorization

One connection belongs to `(tenant_id, fleet_customer_id)`, where tenant is the
shop and customer is the operating fleet company. The user's two trucks are the
initial pilot in one company. A shop can have multiple customer fleet companies;
one shop-wide token would cross their business boundaries.

All routes below require an active GARAGE_OWNER or GARAGE_ADMIN with a tenant.
Resolve the tenant from the authenticated principal, never JSON or a query string.
Resolve fleet_customer_id to a nondeleted same-tenant Customer with fleet_enabled or is_internal_fleet.
FLEET_MANAGER, CUSTOMER, DRIVER, MECHANIC, RECEPTIONIST and tenantless SUPER_ADMIN
cannot manage this first connection surface. Current FLEET_ROLES is too broad.

Customer self-service is an intended later extension. RequestUserPrincipal and
UserCustomerLink currently prove selected shop/customer association, not company
administrator authority. Neither table provides a verified fleet administrator
grant. Do not infer one from an email match, customer association, vehicle
ownership, or the fleet-manager role. Add an explicit scoped grant before exposing
connection management in the customer portal.

Mapping requires a nondeleted same-tenant Vehicle and an active FleetMembership
for that exact fleet_customer_id (effective_from <= now < effective_to, or no end).
Vehicle.customer_id and is_internal_fleet determine other business concerns and
are not substitutes for membership. Recheck membership when syncing and reading
telemetry. A membership ended or moved to another company suppresses that
connection's overlay even if its binding still exists. The first UI is the
authenticated staff Fleet surface with an explicit company selector.

Foreign, missing, deleted and inaccessible company/connection/vehicle IDs return
the same 404. Authenticated disallowed roles return 403; missing/invalid sessions
return 401. All mutation routes use the existing authenticated JSON client and
enforce same-origin/allowlisted Origin for cookie authentication. No wildcard
credentialed CORS, query-string access token, or GET mutation.

## HTTP contract

Prefix: `/api/v1/fleet/motive`. IDs are strings, times are UTC ISO-8601. Responses
contain normalized allowlisted fields only, never provider response blobs, tokens,
client secrets, authorization codes, or stored state. Use Cache-Control: no-store.

| Method / path | Input | Output |
| --- | --- | --- |
| GET /connection | query fleet_customer_id | ConnectionStatus |
| POST /connect | `{ "fleet_customer_id": "uuid" }` | `{ "authorization_url": "https://gomotive.com/oauth/authorize?...", "expires_at": "UTC timestamp" }` |
| POST /callback | `{ "state": "opaque", "code": "opaque" }`, or state + error | ConnectionStatus |
| GET /vehicles | query fleet_customer_id | `{ "items": [RemoteVehicle], "synced_at": null }` |
| PUT /bindings/{provider_vehicle_id} | `{ "fleet_customer_id": "uuid", "vehicle_id": "uuid" }` | `{ "provider_vehicle_id": "123", "vehicle_id": "uuid", "mapped_at": "UTC timestamp" }` |
| DELETE /bindings/{provider_vehicle_id} | query fleet_customer_id | 204 |
| POST /sync | `{ "fleet_customer_id": "uuid" }` | `{ "status": "connected", "counts": { "discovered": 2, "mapped": 2, "updated": 2, "rejected": 0 }, "completed_at": "UTC timestamp" }` |
| DELETE /connection | query fleet_customer_id | 204, including already disconnected |

```json
{
  "fleet_customer_id": "uuid",
  "configured": false,
  "status": "not_configured",
  "company": null,
  "last_sync_at": null,
  "next_sync_at": null,
  "last_sync_error_code": null,
  "last_sync_counts": null,
  "can_connect": false
}
```

Connection status: not_configured, disconnected, connected, reconnect_required,
provider_error. `company`, when known, is `{ "id": "provider-company-id", "name":
"Company name" }`. `configured` means server configuration and explicit global
feature enablement are valid; it does not attest vendor approval or a live test.
`connected` means token exchange/company validation completed; it does not mean
trucks are mapped or data is fresh. Starting consent does not replace a healthy
connection's status. Callback success permits an explicit Sync action. `next_sync_at` is the earliest next collection attempt; UI disables manual sync until it is due and displays the time. Background collection also respects this bound.

RemoteVehicle contains provider_vehicle_id, number, vin, gateway_id, vehicle_id
(nullable), mapping_state (unmapped, mapped, membership_ended), and
match_candidates (`[{vehicle_id,unit_number}]`). Gateway is null unless actually
returned by a validated provider endpoint. Exact unique VIN may suggest a match;
the operator still confirms. No unit-number or plate-only automatic binding.
The list is a local cached inventory read, not a provider call. Do not silently
truncate a larger inventory: add bounded pagination before exceeding the pilot
response cap, or return an explicit inventory_limit error.

Each RemoteVehicle additionally has `telemetry`, null or
`{ "location": { "lat": 35.1, "lng": -80.7, "located_at": "UTC timestamp",
"received_at": "UTC timestamp" }, "speed_mph": null, "bearing_degrees": null,
"state": "fresh", "source": "motive" }`. No additional latest-location route is
required for the integration panel. Telemetry is visible only through a currently
mapped vehicle and active membership, and is null after disconnect/unmapping.
During a provider error the last accepted point remains available with its own
age. UI thresholds are fresh <=5 minutes, delayed <=15 minutes, otherwise stale;
these are application display policy, not claimed Motive delivery guarantees.
No point means null/unknown, never zero coordinates or an inferred yard location.

Error shape: HTTP detail object `{ "code": "stable_code", "message": "safe copy" }`.
Use 409 for already mapped/conflicting company, sync in progress, disabled or
reconnect-required state; 400 for denied, expired, mismatched or reused OAuth
state (generic oauth_session_invalid), 422 for invalid request fields, 503 for
unconfigured/provider unavailable, 429 for rate limiting. Store error codes;
never expose token endpoint bodies or arbitrary provider error descriptions.

## OAuth state and callback

Register exactly the configured frontend URL `/fleet/motive/callback`; do not
derive redirect_uri from request Host, return_to, or body. Frontend reads code,
state or error once, immediately replaces the URL to remove them, then submits
the authenticated POST callback. Do not place third-party tracking/assets on the
callback view; use Referrer-Policy: no-referrer. React rerender must not exchange
the code twice. Browser storage may hold no provider credentials or raw code.

Generate at least 256 bits of random state; store only its hash, tenant, fleet,
actor user, hashed initiating access JWT jti, creation/expiry (10 minutes), and
connection generation. Read jti only from the validated request token. Callback
requires the same active actor/tenant and same jti, plus current owner/admin role
and active company. Refresh/relogin changing jti invalidates this consent attempt;
show a restart message. This deliberate first-version constraint avoids inventing
a stable session identifier. A dedicated stable browser-session nonce can replace
it only with equivalent logout/revocation coverage and Architecture review.

Atomically consume matching unexpired state and commit consumption BEFORE token
exchange. A network failure requires a new consent attempt, not replay of a code.
Consume a valid denied flow without token HTTP. Never consume another user's state
on an identity mismatch. Disconnect invalidates outstanding states and increments
connection generation. Recheck generation and current principal before saving
exchange results: an in-flight callback cannot resurrect a disconnected account.

Exchange code server-side with a fixed HTTPS token endpoint, form encoding and
the identical configured redirect_uri. Validate nonempty access/refresh tokens,
Bearer token_type and bounded positive expires_in; do not fabricate an expiry.
Identify the granted company through GET /v1/companies before persisting a usable
connection. Exactly one unambiguous returned company is required for this pilot.
Reconnect to a different company returns company_mismatch; it must not silently
reassign old mappings. Changing company requires disconnect and explicit mapping
again. Prevent the same provider company being linked to two customer fleets
within a shop. Do not create a global cross-tenant company uniqueness constraint.

## Tokens, refresh and disconnect

Settings: MOTIVE_ENABLED (false by default), MOTIVE_CLIENT_ID,
MOTIVE_CLIENT_SECRET, MOTIVE_REDIRECT_URI, MOTIVE_TOKEN_ENCRYPTION_KEYS (versioned
keyring), MOTIVE_TOKEN_ACTIVE_KEY_VERSION, and MOTIVE_APPROVED_TENANT_IDS. Provider requests have a fixed ten-second timeout; the full sync provider phase is bounded to twenty seconds. Configuration
validation must fail closed when enabled with missing/invalid values. No secrets
in VITE variables, examples, database fixtures, logs or API responses.

Encrypt tokens at rest using authenticated encryption with a dedicated versioned
key. Bind encrypted plaintext to connection/tenant/fleet identity (AAD or an
authenticated envelope checked after decrypt) so moving ciphertext between rows
cannot exchange fleets. Store key version separately. Access and refresh tokens
are server-only; permit only fixed allowlisted HTTPS provider destinations and
disable redirects when credentials are attached.

Refresh within 120 seconds of expiry. Serialize refresh per connection and
recheck expiry after acquiring the lock. Persist rotated refresh tokens atomically
with access token and expiry; retain an old refresh token only when a successful
refresh omits a new one. Never carry a previous company's refresh token into a
new connection. A refresh invalid_grant or repeated resource 401 transitions to
reconnect_required and disables subsequent sync until reauthorization. A resource
401 permits at most one refresh and retry; 403 becomes insufficient_scope, not an
endless refresh loop. Timeouts/429/5xx retain the last successful snapshot and
produce provider_error plus a bounded retry time. Honor bounded Retry-After.

Disconnect atomically clears encrypted credentials, disables sync, invalidates
OAuth states, increments generation and ends mappings; it never changes truck
ownership, drivers, mileage or manual location. Every in-flight refresh/sync
must verify generation before storing results. Local disconnect is complete even
when provider is unavailable. Motive token-revocation support is not established
by the reviewed docs: do not invent a revocation endpoint or claim provider-side
revocation. UI may explain that provider access can also be removed in Motive.

## Discovery, mapping and location collection

Backend fetches only company/current-location read data. Minimum scopes:
companies.read and locations.vehicle_locations_list. No driver, camera, HOS,
payment, history or write scopes. First discovery and current locations both use
GET /v3/vehicle_locations for supported Vehicle Gateways. The panel labels this
supported vehicle inventory; it does not claim to list every Motive device. A
later complete vehicle inventory can add GET /v1/vehicles and vehicles.read.
Do not assume every installed Motive device supports v3; unsupported/missing
location remains unknown pending real provider validation.

Use page_no/per_page with an explicit total-request and response-size bound.
Follow documented pagination; detect repeated/nonadvancing pages, unexpected
shape and inconsistent totals. A page failure produces a failed/partial sync,
never a successful full inventory or deletion of absent vehicles. On-demand sync is synchronous and bounded, with 409 for a locked connection. A registered five-minute worker handles at most twenty due connections, filtering approved tenants and active fleet companies before the limit. It uses skip-locked selection, respects per-connection retry times and isolates each company failure. This is implemented and tested offline; continuous live collection still requires deployed Worker/Beat identity and provider validation.

The documented v3 shape is vehicles -> vehicle -> current_location. It supplies
lat, lon, located_at, nullable bearing and kph. Convert kph explicitly to mph
(/1.609344). Missing fields stay null. Do not invent gateway, odometer or engine
hours absent from this endpoint. A polling point lacks a documented event ID;
derive a deterministic namespaced identity from provider vehicle + UTC observation
time, scoped by connection. Compare canonical content excluding transport/action
for deduplication. Same identity/different content is a conflict, not an overwrite.
Do not generate a fake webhook HMAC to reuse the fixture ingestion path.

The first OAuth slice stores only the latest accepted point per RemoteVehicle,
with mapping vehicle_id, mapped_at and mapped_by_user_id. It exposes no history.
Same mapping PUT is idempotent. A changed mapping/unmap clears all point fields
and fingerprint before setting the new server mapping time. Accept only points
with located_at >= mapped_at and with applicable fleet membership at that time;
recheck current membership on reads/sync. A stale observation from before a new
mapping must not be attached to it. The first update can remain unknown until a
post-mapping sample arrives. Resolve a cross-connection canonical truck mapping
conflict under a Vehicle lock and partial unique tenant+vehicle index.

Strictly newer observations replace the latest point. Equal timestamp plus equal
canonical fingerprint is a no-op; equal timestamp with changed content increments
rejected/conflict and retains the first point. Older points do not replace newer
ones. The sandbox historical binding/sample implementation remains separate and
unchanged; adding live history later requires its stronger historical contract.

Store normalized point fields on the provider row; never write Vehicle.mileage, driver fields or
manual last_* columns. Retain provider observation/receipt timestamps and source.
Freshness derives from observation time, not time of sync. Reject >5-minute future
observations and observations older than 30 days. Purge point fields older than
30 days and filter expiry on reads even if the purge is late. The latest-only
slice does not claim historical replay detection beyond the current point.
First Fleet display uses additive optional
telematics fields; disabled/disconnected/membership-ended connections contribute
no overlay and existing manual location remains available.

## Migration and backward compatibility

Add separate OAuth connection/state/remote-vehicle tables rather than
relaxing MotiveAccount's existing fixture-only check or repurposing fixture rows.
Existing sandbox tests and constraints continue unchanged; share only pure
normalization helpers where semantics agree.

Connection: UUID; tenant_id, fleet_customer_id; provider company ID/name; status;
encrypted token envelope/key version/expiry; generation; last sync/error/counts;
connected/disconnected timestamps and actor IDs. Unique tenant+fleet, and unique
tenant+provider-company when company identity is present. Composite customer FK
(tenant_id,fleet_customer_id) and unique (tenant_id,fleet_customer_id,id).

OAuthState: unique state hash; initiating user/jti hash; tenant/fleet/connection
generation; expires_at and consumed_at. Expired state metadata may be purged after
one day; never store raw code, state, credential or provider payload.

RemoteVehicle: unique connection+provider vehicle ID; allowlisted identifier/VIN/
unit/gateway fields and last_seen_at; optional mapped vehicle/actor/time; latest
normalized point, observed/received time and canonical fingerprint. No driver
data or historical location array. Composite tenant+connection FK reaches the immutable fleet scope through the connection, and tenant+Vehicle FK enforces truck tenancy; provider rows cannot specify a different fleet. State uses the same tenant+connection reference. Partial unique tenant+vehicle where vehicle_id
is present prevents simultaneous mappings across connections. New models must
not merely trust separate UUID FKs to enforce tenant identity. Thirty-day point
retention requires tested purge; the five-minute worker runs the purge before its provider feature flag check, so disabling collection does not suspend retention.

Migration applies additively to the actual Alembic head, no fixture conversion or
production backfill. Prove PostgreSQL upgrade and downgrade on a disposable DB.
Rollback disables MOTIVE_ENABLED and stops collection while preserving manual
Fleet behavior. Downgrade removing new tables is destructive and is not the first
production rollback mechanism.

## Required offline evidence and release gates

- HTTP mocked exact authorization/token/refresh/company/vehicle/location shapes;
  no real provider credentials, contact, or network from automated tests.
- Every route: allowed owner/admin, rejected other roles, foreign shop, different
  company in same shop, deleted/disabled customer, ended membership, wrong vehicle.
- OAuth: denied, missing/expired/replayed state, same user different jti, different
  user, role revoked, logout/revoked JWT, token failure after consumption, malformed
  token, missing refresh/expiry, missing scope, ambiguous or changed company.
- Refresh concurrency and rotated token durability; disconnect racing callback,
  refresh and sync cannot restore credentials or imported data.
- Encryption round trip, unknown key version, tampered envelope, ciphertext swap;
  logs/errors/status responses never contain secrets, codes or raw payloads.
- Multi-page/empty/malformed discovery; 401 once then failure, 403, 429, timeout,
  5xx; no absent-record deletion on failed pagination; stable bounded counts.
- Exact VIN suggestion, duplicate VIN, explicit mapping, cross-company collision,
  device reassignment, idempotent mapping, clearing on map/unmap and membership-ended suppression.
- Location conversion/null fields, deterministic duplicate/conflict, late/equal
  timestamps, future/expired points and retention; canonical truck fields unchanged.
- Staff UI: company selection, unavailable configuration, consent denial, success,
  map/unmap, sync error/retry/status, disconnect; callback URL cleanup and no secret
  browser persistence. Existing Fleet works with feature disabled.

Independent Security and QA must review the completed exact candidate. Actual
Motive app approval, registered callback, approved scopes, provider payload/unit/
device validation, and two-truck read-only pilot remain external evidence gates.
Offline green tests prove app behavior against the contract, not live collection.

## Official evidence checked 2026-09-29

- [OAuth flow](https://developer-docs.gomotive.com/docs/oauth-20): authorization at
  gomotive.com/oauth/authorize, form-encoded token/refresh at
  api.gomotive.com/oauth/token; ten-minute code lifetime; Bearer access token.
  The example expiry is not a guaranteed lifetime. PKCE support, refresh-token
  lifetime/rotation guarantees and revocation endpoint are not established here.
- [Scope list](https://developer-docs.gomotive.com/docs/oauth-scopes): the two
  initial read scopes map to company and current-location endpoints; vehicles.read
  is reserved for a later explicit complete inventory endpoint.
- [Company identity](https://developer-docs.gomotive.com/reference/identify-a-company-using-its-access-token):
  /v1/companies identifies the company associated with the access token.
- [Vehicle inventory](https://developer-docs.gomotive.com/reference/list-all-the-company-vehicles):
  /v1/vehicles supports page_no/per_page.
- [Current locations v3](https://developer-docs.gomotive.com/reference/fetch-a-list-of-all-the-vehicles-and-their-locations-v3):
  Vehicle Gateway requirement, nested current_location, kph and pagination.
  Its examples do not provide a location event ID or gateway ID.
- [Location history v3](https://developer-docs.gomotive.com/reference/fetch-a-vehicles-location-using-its-id-v3):
  virtual odometer and true_odometer differ. History polling is not part of the
  minimum scopes or first collection path.

Repository evidence: core/dependencies.py RequestUserPrincipal and JWT validation;
db/models/user_customer_link.py association without administrator grant;
db/models/vehicle_relationship.py temporal FleetMembership; endpoints/fleet.py
require_fleet_access and companies; db/models/motive.py fixture-only constraints.

## Reviewed implementation choices

- Scoped management stays owner/admin-only until customer-company admin grants
  exist. Internal fleet eligibility also accepts `is_internal_fleet`.
- `mapped_by_user_id` records the actor. Mapping writes and provider collection
  serialize on connection rows; tenant+vehicle uniqueness rejects cross-connection
  mapping collisions. Reads and ingestion recheck dated fleet membership.
- Local disconnect clears tokens/mappings and invalidates pending consent. The
  app does not claim that a token has been revoked at Motive.
- This first provider client collects identity and current coordinates/speed for
  supported Vehicle Gateways. Engine hours, odometer, fault codes and HOS are
  future endpoint work, not values inferred from the location response.
