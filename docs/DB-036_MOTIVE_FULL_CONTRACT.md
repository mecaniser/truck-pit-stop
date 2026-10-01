# DB-036 complete Motive integration contract

Architecture v2, 2026-09-30. Board item DB-036; accountable implementation owner
Backend & Integrations. This supersedes the scope limitations in
`DB-036_MOTIVE_OAUTH_CONTRACT.md`; that document's existing OAuth security,
tenant isolation, encryption and error requirements remain in force. The full
customer onboarding, device discovery, telemetry, faults, webhooks and
reconciliation flow is the accepted outcome. This contract does not represent
provider approval or a deployed/live integration.

## Ownership and acceptance

- Backend owns provider client, authorization/grants, persistence, ingestion,
  worker and **the single additive migration after 152**. Recheck Alembic head
  before naming it. Root owns HTTP wrappers and coordinates frontend work.
- Frontend consumes the additive response contract below and supplies staff grant
  controls plus the customer connection journey. Do not reuse broad shop inventory
  APIs for customer mapping options.
- Architecture owns this document. Independent fresh QA and Security reviewers
  must review the finished candidate, including customer and webhook boundaries.
- Done requires working authorized-customer consent, complete inventory/device
  mapping, timestamped location/speed/odometer/engine-hour/fault data, durable
  signed webhook reception, reconciliation, token refresh, disconnect, and the
  test/runtime/release evidence. Missing provider setup is recorded explicitly.

## Authorization and customer onboarding

Connection identity remains `(tenant_id, fleet_customer_id)`. Tenant comes from
the validated principal, not client JSON. Staff GARAGE_OWNER/GARAGE_ADMIN can
manage a same-tenant nondeleted enabled/internal fleet company.

Customer self-service requires all of:

1. Current active User with role CUSTOMER; validated selected-tenant principal.
2. Nondeleted `UserCustomerLink` with exact user, selected tenant and customer.
3. Principal customer_id equals the requested fleet customer.
4. Active `MotiveFleetAdminGrant` for that exact user/tenant/customer.
5. Active tenant and eligible nondeleted fleet company.

Reload current User status/role but **do not replace the validated principal's
selected tenant with User.tenant_id**: global customer identities may have a
different home tenant. Never infer administrator authority from association,
email, ownership, or FLEET_MANAGER alone. Other roles remain rejected.

Staff explicitly issues/revokes grants; customers cannot grant themselves or
other users. Grant candidates are only active CUSTOMER users with a current
exact-company link. Candidate names/emails are staff-only. Issuing an existing
active grant is idempotent. Revocation is immediate on all reads/mutations and
after provider I/O; in-flight OAuth initiated by a revoked grantee cannot save
credentials. Revocation removes that user's access, not the company's existing
connection or another authorized user's access. Recheck grants on callback,
mapping and any user-initiated operation after asynchronous provider work.

## HTTP contract

Authenticated prefix `/api/v1/fleet/motive`. Existing routes, safe error shape,
no-store, Origin enforcement for cookie mutations and one-use callback semantics
remain. All IDs below are strings; times are UTC ISO-8601 or null.

| Method/path | Input | Result |
| --- | --- | --- |
| GET /companies | none | `{items: CompanyChoice[]}` scoped to current actor |
| GET /trucks | fleet_customer_id query | `{items: TruckChoice[]}` current exact-company memberships |
| GET /grant-candidates | fleet_customer_id query; staff only | `{items: GrantCandidate[]}` |
| GET /grants | fleet_customer_id query; staff only | `{items: FleetAdminGrant[]}` |
| PUT /grants/{user_id} | `{fleet_customer_id}`; staff only | FleetAdminGrant |
| DELETE /grants/{user_id} | fleet_customer_id query; staff only | 204, idempotent |
| GET /webhook | fleet_customer_id query | WebhookStatus; never returns secret |
| POST /webhook/rotate | `{fleet_customer_id}` | WebhookSetup with one-time secret |
| DELETE /webhook | fleet_customer_id query | 204; disables receipt and invalidates old route/secret |

```typescript
type CompanyChoice = {
  id: string; company_name: string; fleet_enabled: boolean;
  is_internal_fleet: boolean; can_manage_grants: boolean;
}
type TruckChoice = { id: string; unit_number: string | null; vin: string | null }
type GrantCandidate = { user_id: string; name: string | null; email: string }
type FleetAdminGrant = {
  user_id: string; name: string | null; email: string;
  granted_at: string; granted_by_user_id: string;
}
type WebhookStatus = {
  status: 'not_configured' | 'awaiting_provider' | 'receiving' | 'disabled';
  url: string | null; last_received_at: string | null;
  pending_count: number; failed_count: number;
}
type WebhookSetup = WebhookStatus & { shared_secret: string }
```

Webhook setup can be performed by the same explicitly authorized company
administrator. Generate an opaque route ID and random shared secret server-side;
return secret only once on rotation, with no-store and no generic idempotency
response cache. Never reveal it in GET/status/logs. Display it only in an explicit
setup panel; never persist it in browser storage or analytics. Rotation must be
clearly labeled because prior Motive webhook settings stop verifying until
updated. Provider registration remains explicit; the response must not say the
subscription is enabled merely because a local secret exists.

Existing `/connection` adds these fields:

```typescript
type FullConnectionFields = {
  can_manage_grants: boolean;
  webhook_status: 'not_configured' | 'awaiting_provider' | 'receiving' | 'disabled';
  last_webhook_at: string | null;
  last_reconciled_at: string | null;
}
```

Existing `/vehicles` remains `{items, synced_at}`. Each item retains existing
identity/mapping/telemetry fields and adds:

```typescript
type FullRemoteFields = {
  gateway_id: string | null;
  gateway_identifier: string | null;
  gateway_model: string | null;
  metrics: null | {
    odometer_miles: number | null;       // true_odometer only
    virtual_odometer_miles: number | null;
    engine_hours: number | null;         // true_engine_hours only
    virtual_engine_hours: number | null;
    observed_at: string;
    received_at: string;
    source: 'motive';
  };
  faults: Array<{
    id: string; code: string | null; code_label: string | null;
    description: string | null; status: 'open' | 'closed';
    first_observed_at: string | null; last_observed_at: string | null;
    fmi: string | null; source: 'motive';
  }>;
  faults_synced_at: string | null;
}
```

Unavailable values remain null; actual zero is valid. UI labels calibrated and
virtual readings distinctly. A null metrics object means no accepted reading.
Faults are empty when none are known; `faults_synced_at: null` means not yet
checked, never proof of no faults. Preserve independent location/metric/fault
timestamps. No telemetry/faults exposed after unmapping, disconnect or ended
membership. GET responses must apply expiry even if scheduled purge is late.

Existing sync response retains status/counts/completed_at. A complete successful
sync covers discovery, devices, mapped-vehicle history and faults. Normal bounded continuation retains connected status with
`last_sync_error_code: reconciliation_incomplete`, `completed_at: null`, a saved
fixed sweep watermark and a due continuation time; it does not increment failure
count. Show Sync in progress. A completed sweep records its covered watermark in
last_reconciled_at; do not substitute finish wall time. Any stage failure produces
provider_error and retains its last successful snapshot/cursor;
never describe partial work as a complete reconciliation. Retain bounded request
and overall execution limits; large fleets need continuation rather than silent
truncation or skipping devices. Stable errors include existing codes plus
`grant_required`, `invalid_grant_target`, `webhook_not_configured`,
`unsupported_webhook_event`, `reconciliation_incomplete` when applicable.

## Provider contract

Request exactly these documented read scopes:
`companies.read vehicles.read eld_devices.read locations.vehicle_locations_list
locations.vehicle_locations_single fault_codes.read`. Persist granted scopes;
an older limited grant requires renewed consent for full collection. No invented
webhook-management scope or endpoint.

| Purpose | Provider request |
| --- | --- |
| Company identity | GET /v1/companies |
| Complete vehicle inventory | GET /v1/vehicles, page_no/per_page |
| Assigned gateway inventory | GET /v1/eld_devices, page_no/per_page |
| Current locations | GET /v3/vehicle_locations, page_no/per_page |
| Per-vehicle history/readings | GET /v3/vehicle_locations/{id}, start_date/end_date/updated_after |
| Fault snapshots/changes | GET /v1/fault_codes, vehicle_ids[], start_date/end_date/updated_after/page_no/per_page |

Use explicit unit headers and endpoint-specific conversion. The existing current
location `kph` value remains kph regardless of a field named speed on another
endpoint. For history/odometer prefer explicit `X-Metric-Units: false` and store
miles; test the actual documented response shape. Never convert engine hours as
distance. Preserve true and virtual fields separately; missing true values are
not silently filled from virtual readings. No writes to canonical manual vehicle
mileage, ownership, driver or location columns.

Use an initial bounded history window within local retention and no earlier than
mapping/membership effective time. History windows never exceed the documented
three-month maximum; cap simultaneous requests below the documented ten-request
limit. Reconcile with a small overlap (five minutes) and event deduplication.
Cursor advance is durable only after the entire bounded stage is accepted.
Keep source event/object IDs and observation time; do not use receipt time as
measurement freshness. An overlapping record cannot regress the newest point.
Fault identity is provider fault ID within connection; open/closed are versions
of one fault, not permanently deduplicated separate records. An old webhook only
schedules a fresh REST lookup and cannot reopen a closed fault.

## Public webhook and durable worker

`POST /api/v1/webhooks/motive/{opaque_route_id}/{generation}` is a separate public router with
no user cookie/CSRF requirement. Opaque route identifies one connection; payload
tenant/company IDs do not choose routing. Require enabled feature, active
connection/tenant/fleet and current configured secret. Limit raw body to 256 KiB.
Verify raw bytes with constant-time HMAC-SHA1 comparison against the signature
header. Reject unverifiable requests with 403. Unknown route returns generic 404.

Accepted actions: `vehicle_location_received`, `vehicle_location_updated`,
`vehicle_upserted`, `fault_code_opened`, `fault_code_closed`. Signed documented
activation test arrays are accepted as probes without fabricating vehicle data.
Unknown actions return a safe 400 and are not processed as supported events.

Persist a compact inbox record and commit before returning 200/201, within the
provider's three-second response limit. Do not perform provider calls inline.
No durable receipt => return 503 so the provider retries. Do not return 202 or
204: provider documents 200/201 as successful acknowledgement.

Inbox stores connection/tenant/generation, action, optional provider event/object
and vehicle ID, raw SHA256, received_at, state, attempt count, next_attempt_at,
safe last_error_code and processed_at. Do not persist raw payloads, coordinates,
names or webhook secret in inbox. Unique `(connection_id,generation,raw_sha256)`
suppresses byte-identical replay; bounded duplicates with different formatting
are safe because reconciliation is idempotent. Do not deduplicate faults solely
by fault ID, since open and closed must both trigger reconciliation.

Events trigger authoritative REST reconciliation, **not direct numeric webhook
ingestion**. This supports every required event while avoiding undocumented
webhook units. Webhook vehicle IDs must resolve through this connection's
inventory; unknown IDs trigger discovery and remain unbound until validated.

Worker claims due inbox entries with skip-locked/lease semantics. Coalesce
entries per connection, retain generation, apply provider retry-after/backoff,
and mark processed only following successful relevant reconciliation. Retry
bounded failures and surface exhausted/dead entries. Scheduled reconciliation
continues independently of webhooks to repair missing events. Wakeups may prompt
reconciliation but never bypass provider rate limits. Healthy connection work
must not starve behind blocked connections.

Disconnect/rotation invalidates old route/secret and pending event generation.
Disconnect also clears tokens/mappings, increments generation and prevents any
in-flight worker from writing data. Old queued work becomes discarded. Do not
claim provider-side unsubscribe/revocation without a documented supported call.

## Data model and retention

Backend migration owns all changes together; do not relax fixture-only account
constraints or repurpose fixture data as production telemetry.

- `MotiveFleetAdminGrant`: tenant_id, fleet_customer_id, user_id, granted_by,
  granted_at, revoked_at; unique tenant/company/user. Composite tenant/company
  FK. Explicit link/current-user validation remains necessary for global users.
- Connection: opaque unique webhook route ID, encrypted context-bound webhook
  secret/key version, webhook setup/last receipt timestamps, generation, last
  completed reconciliation timestamp. Never return encrypted material.
- Remote vehicle: gateway ID/identifier/model; true/virtual metric values and
  source timestamps; history progress/cursor; discovery/device reconciliation
  timestamps. Preserve existing tenant+connection and tenant+vehicle constraints.
- `MotiveFault`: tenant/connection/provider fault ID, provider vehicle ID,
  allowlisted fields above, source update/receipt timestamps; unique
  connection/provider fault ID and composite tenant/connection FK.
- `MotiveWebhookInbox`: fields above with composite tenant/connection FK,
  generation/retry indexes and replay uniqueness. No raw-body persistence.

Live measurements and inbox receipts use a 30-day retention bound; expired
measurements are suppressed on reads. Closed faults expire 30 days after last
observed/confirmed close; active faults remain only while recently confirmed by
REST within 30 days. Purge runs even when collection is disabled. Tokens/secrets
clear immediately on disconnect; inactive mapping metadata/grants follow the
application's existing deletion policy and are not advertised as telemetry.
Any new backup retention claim needs actual configured infrastructure evidence.

## Required evidence and deployment conditions

Tests cover correct and foreign tenants/companies, customer linked but ungranted,
revoked grants and roles during OAuth I/O, global customer selected tenant,
staff-only candidate privacy, explicit mapping and reassignment, metric null/zero
and unit conversion, fault close/reopen ordering, page failure/cursor rollback,
signed probes, wrong signature/body alteration, duplicate webhook, receipt DB
failure, worker retry/lease/disconnect races and disabled-feature behavior.

Provide real PostgreSQL upgrade/downgrade evidence, component/browser customer
and staff journeys, independent security/QA, and deployed web/worker/beat identity
before claiming live readiness. Feature remains off by default, with explicit
tenant allowlist until rollout authorization. Local implementation can proceed
without provider secrets; external gates are Motive approval/credentials, exact
redirect registration, webhook subscription provisioning and real payload/unit
validation. Provider setup must cover general customer onboarding, without
hardcoding a specific company or test-fleet identity.

## Official sources checked 2026-09-30

- [OAuth scopes](https://developer-docs.gomotive.com/docs/oauth-scopes)
- [Vehicle inventory](https://developer-docs.gomotive.com/reference/list-all-the-company-vehicles)
- [Gateway inventory](https://developer-docs.gomotive.com/reference/fetch-the-eld-devices-of-an-organization)
- [Location history and true readings](https://developer-docs.gomotive.com/reference/fetch-a-vehicles-location-using-its-id-v3)
- [Fault codes](https://developer-docs.gomotive.com/reference/fetch-a-list-of-all-the-vehicles-fault-codes)
- [Webhooks V1 signing and acknowledgements](https://developer-docs.gomotive.com/reference/overview-company-webhooks)
- [Webhooks V2 company enablement](https://developer-docs.gomotive.com/reference/webhooks-v2)

Webhook-management API/scopes and provider token revocation are not established
by these reviewed sources. Ask Motive for their supported partner provisioning
flow; do not implement guessed provider writes.
