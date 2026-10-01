# Motive full integration setup

Updated 2026-09-30. The user reports the general partner application submitted
for **Elis Tech LLC / DieselBridge Network**. Motive approval and credentials are
pending. The implementation candidate follows the full contract in
`DB-036_MOTIVE_FULL_CONTRACT.md`; submission, offline tests and fixtures do not
prove that the integration is deployed or collecting real truck data.

## Partner application and approved access

Obtain OAuth client credentials and register the exact HTTPS frontend callback
ending `/fleet/motive/callback`. The proposed public application callback is
`https://www.dieselbridge.com/fleet/motive/callback`; confirm the deployed hostname
and Motive registration agree before activation. Do not derive this URL from a
request header or customer input.

Request the six documented read scopes:

```text
companies.read
vehicles.read
eld_devices.read
locations.vehicle_locations_list
locations.vehicle_locations_single
fault_codes.read
```

The integration covers customer-company OAuth onboarding, complete vehicle and
assigned-gateway inventory, location/speed, calibrated and virtual odometer and
engine hours, fault-code lifecycle, signed events and REST reconciliation.
Previously issued limited-scope consent must be renewed for full access.
Confirm customer entitlements, supported devices, payload units and request
limits with Motive. No specific company is hardcoded into partner onboarding.

## Server configuration and rollout

Use the approved server secret/configuration mechanism only:

| Setting | Required value |
| --- | --- |
| `MOTIVE_ENABLED` | False by default; enable only for an authorized rollout. |
| `MOTIVE_CLIENT_ID` / `MOTIVE_CLIENT_SECRET` | Approved application credentials; server-only. |
| `MOTIVE_REDIRECT_URI` | Exact HTTPS URI registered with Motive. |
| `MOTIVE_TOKEN_ENCRYPTION_KEYS` | Dedicated versioned Fernet keyring as JSON. |
| `MOTIVE_TOKEN_ACTIVE_KEY_VERSION` | Active encryption key version. |
| `MOTIVE_APPROVED_TENANT_IDS` | Explicit comma-separated shop tenant UUID allowlist; empty permits none. |
| `PUBLIC_API_BASE_URL` | Public HTTPS API origin for generated webhook URLs, without path, query or credentials. |

Web and Worker must share the intended commit, schema, feature configuration and
keyring. Keep old key versions until stored credentials have been rotated.
Never expose provider secrets in VITE variables, application logs or analytics.
Apply additive migrations 151/152/153 through the release process after checking
the candidate migration graph. Do not migrate a shared database during local QA.

Deploy webhook ingress and workers/Beat as well as the frontend and API. Verify
durable receipt processing, periodic reconciliation and retention jobs execute
against the intended database. The deployed task frequency and limits are
operational settings, not a provider delivery guarantee. Disabled features and
non-allowlisted tenants must make no provider requests; cleanup remains active.

## Customer onboarding

1. Staff owner/admin opens Fleet → Integrations and selects a fleet company.
2. Under Company administrators, grant access to an active customer identity
   explicitly linked to that same shop/company. A customer link alone grants no
   integration-management authority.
3. The granted customer uses Integrations in the customer portal. Staff can also
   manage the selected company. OAuth authorizes that customer's Motive company;
   verify its returned identity.
4. Discover vehicles and installed gateways. Review exact VIN suggestions and
   explicitly map the company's DieselBridge trucks.
5. Collect and verify post-mapping readings. Missing values stay unknown;
   calibrated and virtual readings remain distinct. Existing manual truck
   mileage, ownership, drivers and manual locations are preserved.
6. Configure and verify live-event subscriptions below. Periodic REST
   reconciliation repairs missed events independently.

Customer grant revocation immediately removes that user's management rights.
It does not disconnect the company's integration for its other administrators.
Test selected-tenant global customer identities, foreign-company denial and
revocation during an OAuth exchange before release.

## Manual Motive V1 webhook subscription

No supported partner webhook-management API has been established by the reviewed
documentation. Until Motive provides an approved automated provisioning flow,
subscription configuration in Motive is an explicit onboarding step.

1. In the connected company's Live updates panel choose Prepare live updates.
   The server generates a company-specific opaque URL and signing secret. Save
   the one-time secret directly into Motive; the status API cannot recover it.
2. Configure HTTPS V1 subscriptions in Motive using the exact generated URL,
   currently `/api/v1/webhooks/motive/{opaque_route_id}/{generation}`, and shared
   secret. Subscribe to `vehicle_location_received`, `vehicle_location_updated`,
   `vehicle_upserted`, `fault_code_opened` and `fault_code_closed`. Confirm available
   subscription slots; do not replace another application's subscriptions.
3. Verify the signed activation probe receives 200/201, followed by a real event
   and successful REST reconciliation. A prepared URL or successful probe alone
   does not prove ongoing vehicle data collection.
4. The receiver verifies raw-body HMAC-SHA1 and durably records a receipt before
   acknowledging within three seconds. Events prompt authoritative REST
   reconciliation; webhook numeric readings are not assigned guessed units.
5. Rotation changes URL/generation/secret. Update Motive's subscriptions with the
   new values and verify delivery; old subscriptions no longer authenticate.

V2 delivery requires explicit Motive company enablement. Do not switch versions
or claim automatic partner-wide subscription activation without confirmation.
The UI distinguishes Awaiting Motive setup from Receiving events.

## Validation before activation

Required evidence includes customer/staff browser journeys, actual company and
device identity, units/nulls/true-versus-virtual readings, fault open/close,
signed events, replay/out-of-order delivery, missed-event recovery, refresh and
reconnect, generation races, disconnect, independent Security/QA, migrations and
deployed web/worker/Beat identity. Validate against consenting customers after
approval; synthetic data is not live evidence.

Full authenticated local testing currently needs approved `backend/.env`
configuration. The isolated fixture can exercise UI interactions without it.
This limitation does not authorize production credentials, provider changes or
bypassing tenant checks.

## Retention, disconnect and rollback

Measurements and inbox receipts have a 30-day retention bound. The contract
defines active/closed-fault confirmation and expiry independently. Connection
metadata and backups follow separately configured application/infrastructure
policies; do not claim an unverified backup deletion duration.

Local Disconnect clears credentials/mappings, invalidates OAuth attempts and
webhook generations, and stops collection and queued writes. Remove the app and
subscriptions in Motive where needed; provider-side revocation is not claimed.
For rollback disable `MOTIVE_ENABLED` and stop/roll back collection code while
preserving manual Fleet behavior. Retain schema/encrypted records for diagnosis;
schema downgrade destroys integration data and is not routine rollback.

## Offline UI preview

`frontend/tests/motive-preview.html` is a development-only browser fixture using
synthetic company/truck data and an in-memory Axios adapter that rejects unknown
requests. Synthetic auth does not persist to normal application storage. It is
not a production build entry, authenticated app test or live provider validation.
