# DB-036 Motive Fleet Telematics Sandbox Contract

## 2026-09-28 two-truck pilot and persistence contract

Product confirmed that both pilot trucks have Motive devices and all trucks are
under one Motive company. The intended live pilot uses one server-side company
API credential. This implementation remains fixture-only until account access
and provider validation are available.

Architecture approved the following persistence slice in this session:

- One fixture account per tenant/provider, disabled by default, with no secret.
- Explicit reviewed powered-vehicle bindings with immutable half-open time
  intervals. Closing then creating a binding represents reassignment.
- Composite foreign keys enforce tenant/account/vehicle consistency. Account
  row locks serialize binding changes and ingestion; historical intervals must
  not overlap for a provider vehicle, gateway, or canonical truck.
- Store normalized location samples and metadata-only delivery receipts. A
  location ID is scoped to its account. Compare a canonical content fingerprint
  (excluding action and delivery formatting) to distinguish duplicates from
  conflicts. Keep the first accepted value and record conflicts without overwrite.
- Resolve late events against the binding at provider `located_at`. Latest
  selection uses provider time; equal timestamps retain the first accepted point
  via a durable sequence allocated under the account lock, including equal
  receipt timestamps.
- Reject observations over five minutes in the future or over 30 days old.
  Filter expired samples from reads and provide explicit purge. Replay identity
  expires 30 days after first acceptance, without renewal by duplicate delivery.
- Only active owners/admins manage accounts and bindings. Internal ingestion
  receives trusted tenant/account identity. Foreign, deleted and missing records
  share a generic not-found result. Disabled accounts ingest nothing and expose
  no location overlay. Existing truck mileage/driver/manual location is untouched.

Acceptance: focused tests cover tenant and role denial, database foreign keys,
duplicate/conflicting delivery, older/equal/newer observations, interval overlaps,
exact reassignment cutover, retention/replay and manual-field preservation;
isolated PostgreSQL covers migration roundtrip and concurrent delivery. Independent
Security/QA review remains required. No HTTP route, worker schedule or Fleet UI
is claimed by this slice; purge scheduling belongs to the ingestion worker slice.

Implementation resumed 2026-09-28 on `codex/db036-motive-sandbox` from
`origin/main` `88995fc2`. The predecessor hold below is retained as historical
context. The initial slice implemented offline signature verification and
location normalization. The persistence slice above now has independent local
Security and QA GO; the ingestion route, worker, Fleet output and release gates
remain pending. Current Motive docs confirm that Webhooks v2 use HMAC-SHA1 over
the raw JSON body and require partner activation. No partner activation is
assumed or requested by this branch.
Motive's location documentation distinguishes virtual `odometer` from
`true_odometer`; this fixture boundary names webhook `odometer` as virtual and
does not write it into the canonical vehicle mileage field.

Status: Product accepted for bounded sandbox implementation on 2026-08-18.

Architecture decision: conditional GO for a deterministic, sandbox-first proof
of concept. Production onboarding and activation remain NO-GO until Motive access,
commercial, rate-limit, webhook, retention and hardware questions are answered
and independent Security and QA return GO.

## Authority boundary

Authorized now:

- deterministic Motive-compatible fixtures and a fixture-backed provider adapter;
- tenant-scoped provider-account metadata, asset bindings and normalized samples;
- schema/migration work required by those sandbox records;
- webhook-shaped ingestion, deduplication, ordering and reconciliation behavior;
- additive Fleet API freshness/source fields and the existing Fleet Board consumer;
- a tenant-off-by-default rollback flag and manual-location fallback;
- focused tests, local runtime evidence and independent Security/QA gates.

Not authorized:

- Motive credentials, OAuth/app registration, vendor contact, purchase or quote;
- calls to Motive, production access or data, real vehicle/device binding;
- merge, deployment, tenant activation or live/shadow production ingestion.

The implementation must not make a future credential swap the release gate.
Real Motive payloads, scopes, pagination, refresh behavior, webhook activation,
latency and rate limits still require a separate provider-validation gate.

## Canonical ownership

- `Vehicle.id` remains the permanent powered-vehicle identity.
- `FleetTrailer` (or a separately accepted canonical equipment entity) owns
  trailers and equipment. Provider assets do not become `Vehicle` records.
- Motive driver association is observational and never overwrites DieselBridge
  driver identity, employer relationship or custody.
- A Motive identifier is unique only within one tenant provider account.
- VIN can suggest a match only when exact and unique. Unit number or plate alone,
  duplicate/reused/missing VIN and device reassignment require explicit review.
- Foreign, missing and deleted provider/account/binding/vehicle identifiers use
  the same generic not-found behavior; known external IDs reveal no tenant.

## Sandbox data model

Backend is accountable for final model naming while preserving this contract:

1. Tenant provider account: `tenant_id`, provider=`motive`, mode=`fixture`,
   external company ID, granted scopes, connection state, token expiry metadata,
   last successful sync and credential key version. Sandbox rows contain no real
   secret. Future secrets are server-only and encrypted with versioned keys.
2. Asset binding: provider account, canonical entity type/ID, provider entity
   type/ID, mutable gateway/device ID, active interval, match basis, verification
   state and actor. One active binding cannot cross tenants or canonical assets.
3. Location sample: tenant, binding, provider event/location ID, `located_at`,
   `received_at`, coordinates, speed, bearing, odometer, engine hours, source
   type and payload hash. Deduplicate by provider account plus provider event ID.
4. Ingestion receipt/replay state sufficient to prove signature outcome,
   idempotency, retry/dead-letter disposition and out-of-order handling without
   persisting raw sensitive payloads.

Raw sandbox location history defaults to 30 days. Longer retention, diagnostic
events and device-health tables require later Product/privacy acceptance.

## Ingestion contract

Use webhook-first ingestion with reconciliation polling. The fixture adapter must
exercise the same normalized boundary intended for the real provider.

- Verify a fixture signature over the raw body before parsing.
- Acknowledge quickly, enqueue/process outside the request, and deduplicate.
- Out-of-order samples may be retained, but `latest` changes only when
  `located_at` is newer.
- Reconciliation recovers missed entity changes and recent locations.
- `429` and transient `5xx` use bounded exponential backoff with jitter.
- Revoked/denied credentials, provider outage and invalid payload are explicit
  states; the last known point is retained and becomes delayed/stale.
- Browser requests never call the provider directly and never carry a provider
  credential or raw webhook payload.

## Additive Fleet API contract

`GET /api/v1/fleet/board` remains canonical. Each `BoardTruck` gains an optional
`telematics` object; existing consumers remain compatible when it is absent:

```json
{
  "vehicle_id": "dieselbridge-uuid",
  "state": "fresh",
  "connectivity": "online",
  "location": {
    "lat": 35.1168,
    "lng": -80.7237,
    "located_at": "2026-08-17T14:02:00Z",
    "received_at": "2026-08-17T14:02:04Z",
    "accuracy_meters": null
  },
  "motion": {
    "speed_mph": 54,
    "bearing_degrees": 92,
    "ignition": "unknown"
  },
  "odometer": {
    "miles": 541190,
    "kind": "true_odometer"
  },
  "source": {
    "provider": "motive",
    "expected_update_seconds": 60
  }
}
```

Allowed `state` values are `fresh`, `delayed`, `stale`, `unlinked`, `unknown`
and `provider_error`. Allowed `connectivity` values are `online`, `offline`,
`scheduled` and `unknown`.

- Unknown location returns null coordinates, never `0,0` or yard placement.
- The API/UI never fabricates accuracy, ignition, driver or connectivity.
- UI copy uses a timestamp such as “Updated 2 minutes ago,” never an unsupported
  “Live” claim.
- Battery trackers use scheduled-tracking semantics, not powered-device online
  semantics.
- History is excluded from the first UI slice and later requires a separate
  permission plus bounded date/cursor pagination.
- Customer portal exposure is excluded.

Tenant provider-account/binding management endpoints are staff-only and derive
`tenant_id` from the authenticated principal. Fixture mode may create deterministic
local records but may not accept or return a provider secret. Architecture must
review any deviation from these response, authorization or error semantics.

## Shared deterministic fixtures

Backend owns a versioned fixture pack; Frontend imports only its normalized Fleet
API outputs. The minimum cases are:

- fresh powered truck, delayed truck, stale/offline truck and unlinked truck;
- scheduled battery asset and unknown location with null coordinates;
- duplicate and out-of-order webhook, replayed event and reconciliation recovery;
- duplicate VIN, cross-tenant provider-ID collision and device reassignment;
- revoked credential, provider outage, `429`, malformed/signature-invalid event;
- rollback flag off, preserving manual location and existing Fleet Board behavior.

Fixture IDs are synthetic, tenant-scoped and stable. They contain no production
identifier, unmasked real VIN, driver movement or copied Motive credential.

## Work split and gates

- **Accountable owner — Backend & Integrations:** isolated implementation branch;
  migration, fixture adapter, provider accounts/bindings/samples, ingestion,
  reconciliation, additive Fleet API contract, rollback flag and backend tests.
- **Contributing owner — Frontend & UX:** consume the shared normalized fixtures;
  remove fake missing-location placement; render explicit freshness, unknown,
  scheduled and provider-error states in existing Fleet Board/detail surfaces.
  Real map tiles are a separate dependency and are not authorized here.
- **Independent Security & Identity gate:** credential boundary, webhook
  verification, tenant isolation, external-ID enumeration, location privacy,
  retention/offboarding, logging and rollback.
- **Independent QA gate:** migration, deterministic ingestion/replay/outage
  matrix, existing Fleet behavior with flag off, responsive/accessible Fleet UI,
  strict console/network checks and rollback.

Implementation returns to Architecture if provider behavior changes the accepted
contract. Product must separately authorize credentials/provider validation,
pilot activation, merge and deployment.

## Official-source assumptions frozen for sandbox design

Architecture verified these on 2026-08-17; implementation must not infer beyond
them: [authentication](https://developer-docs.gomotive.com/docs/authentication.md),
[OAuth](https://developer-docs.gomotive.com/docs/oauth-20.md),
[OAuth scopes](https://developer-docs.gomotive.com/docs/oauth-scopes.md),
[pagination](https://developer-docs.gomotive.com/docs/pagination.md),
[vehicle locations v3](https://developer-docs.gomotive.com/reference/fetch-a-vehicles-location-using-its-id-v3.md),
[fault codes](https://developer-docs.gomotive.com/reference/fetch-a-list-of-all-the-vehicles-fault-codes.md),
[webhooks v2](https://developer-docs.gomotive.com/reference/webhooks-v2.md),
[Asset Gateway Mini](https://helpcenter.gomotive.com/hc/en-us/articles/12486052017821-Asset-Gateway-Mini),
and [Vehicle Gateway](https://helpcenter.gomotive.com/hc/en-us/articles/31078407997981-Vehicle-Gateway-ELD-Overview).
