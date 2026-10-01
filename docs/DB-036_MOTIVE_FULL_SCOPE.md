# DB-036: required complete Motive integration

Scope correction, 2026-09-30. Accountable owner: Backend & Integrations.
This supersedes the location-only deliverable as the product completion target.
The existing OAuth contract describes a foundation, not the full accepted scope.

## User outcome

Each customer fleet administrator can connect their company's Motive account to
DieselBridge, confirm truck/device associations, and receive ongoing location,
speed, odometer, engine-hour and fault-code data where supported by Motive.
Signed company webhooks and API reconciliation are required parts of the flow.
The partner application is general; it is not restricted to a named pilot fleet.

## Completion criteria

- Explicit customer-company administrator authority governs self-service OAuth,
  mappings, reconnection and disconnect; ordinary customer links confer no grant.
- Separate credentials, subscription secrets, data, and authorization per fleet.
  Negative tests cover another tenant, another fleet in the same tenant, removed
  membership, revoked roles, expired/replayed state and disconnected credentials.
- Discover actual vehicle inventory and device association; reviewed mappings
  support missing/ambiguous VINs, device reassignment and inactive vehicles.
- Retrieve and display location/speed, odometer, engine hours and fault status
  with verified units, source, observation time and freshness. Missing fields are
  unknown, and provider values do not silently overwrite canonical manual data.
- Provide a signed webhook HTTP receiver, verified raw-body authentication,
  durable receipt before acknowledgement, asynchronous processing, duplicate and
  ordering controls, supported activation probes and company-isolated routing.
- Cover supported vehicle/location and fault open/close events; reconcile API
  data after delivery gaps and outages with bounded pagination and backoff.
- Refresh/rotate tokens safely. Disconnect stops polling/event application,
  invalidates in-flight work and clears connection credentials/data as specified.
  Document separately any provider-side subscription removal/revocation limits.
- Define and verify retention/deletion for location, faults, event receipts,
  connection metadata and backups before production activation.
- Complete independent Security/QA, authenticated browser acceptance, migration
  checks, provider end-to-end validation, and approved release evidence.

## Evidence and gaps at intake

Candidate `d41f33d6`, draft PR443, implements owner/admin OAuth, encrypted tokens,
explicit fleet mappings, current-location polling, refresh/disconnect and UI.
Separate fixture ingestion verifies signatures and persistence. It does not yet
wire live webhooks into the OAuth connection or implement the full telemetry set
or customer-company administrator grants. Prior offline GO applies only to that
reviewed candidate; it does not approve this expanded completion target.

Local runtime preflight on 2026-09-30 found the intended checkout clean and ports
5173/8000 unbound. Controller switch dry-run is blocked by missing approved
`backend/.env`; no services, credentials, database or tenant settings were changed.
Provider credentials/approval and supported-field validation remain external gates.

## Partner review request

Request review of `companies.read`, `vehicles.read`, `eld_devices.read`,
`locations.vehicle_locations_list`, `locations.vehicle_locations_single` for
bounded reconciliation, and `fault_codes.read`. Request supported company events
for vehicle location updates/receipts, vehicle upserts and fault opening/closing.
Confirm the actual partner provisioning/permission mechanism and units rather
than inventing a webhook OAuth scope or promising unavailable data.

Proposed callback: `https://www.dieselbridge.com/fleet/motive/callback`.
It is not yet a registered, deployed Motive callback. Production webhook endpoint
registration follows implementation and verification of its connection routing.

Sources checked 2026-09-30:
- https://developer-docs.gomotive.com/docs/oauth-scopes
- https://developer.gomotive.com/reference/overview-company-webhooks

Application wording must distinguish the requested complete integration from
currently implemented controls and must not state that live access is active.

## Architecture assessment, 2026-09-30

Independent Architecture confirms that the narrow deliverable was an application
scope choice, not a documented Motive capability limitation. Vehicle/gateway
inventory, location history with calibrated/virtual odometer and engine-hour
fields, fault lifecycle REST access and signed webhook events have published
contracts. These implementation gaps must not be attributed to partner approval.

Provider confirmation is specifically needed for per-customer subscription
provisioning, V1 versus company-enabled V2 delivery, webhook numeric units,
revocation/uninstall behavior, entitlements and actual device payload validation.
Do not invent an OAuth webhook-management scope or endpoint. REST reconciliation
needs durable cursors and bounded overlap; disconnect must invalidate queued
events and webhook generations as well as polling. At architecture intake, expanded-scope gates were pending. The finished candidate
now has offline QA and application-security GO; see
`docs/verification/DB036_MOTIVE_FULL_INDEPENDENT_QA.md`. Live/runtime/release gates
remain open.
