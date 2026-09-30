# Motive OAuth deployment and pilot checklist

This is app-side configuration guidance. Motive approval, live consent, production
activation, merge and deployment have not been completed by this change.

## Provider application

Register DieselBridge Network as a Motive developer application. Confirm partner
approval and the pilot company's API entitlement with Motive API Support. Register
one exact HTTPS frontend return URL ending `/fleet/motive/callback`. Request only
`companies.read locations.vehicle_locations_list` for this first location slice.
Confirm that the pilot devices are Vehicle Gateways supported by v3 locations.

## Server configuration

Set these only through the approved server secret/configuration mechanism:

| Setting | Meaning |
| --- | --- |
| `MOTIVE_ENABLED` | Defaults false; final activation requires approval. |
| `MOTIVE_CLIENT_ID` / `MOTIVE_CLIENT_SECRET` | OAuth application identity; never frontend variables. |
| `MOTIVE_REDIRECT_URI` | Exact registered HTTPS frontend callback. |
| `MOTIVE_TOKEN_ENCRYPTION_KEYS` | JSON object mapping key versions to dedicated Fernet keys; no example secrets are committed. |
| `MOTIVE_TOKEN_ACTIVE_KEY_VERSION` | Key version used for new writes, default label `v1`. |
| `MOTIVE_APPROVED_TENANT_IDS` | Explicit comma-separated DieselBridge shop tenant UUID allowlist. Empty blocks all live connections, including in development. |

Keep old encryption versions available while existing rows still use them. The
ciphertext envelope binds tokens to connection, tenant and operating fleet.
Web and Worker must share the configuration/keyring. Do not log provider bodies,
authorization URLs/codes, token responses, or decrypted values.

Apply additive migration152 after151 through the release workflow. Verify both
Web and Worker use the intended commit/schema. Celery Beat registers Motive
reconciliation every five minutes; each job processes at most twenty eligible due
connections and purges expired point/state metadata. There are no provider calls
when the feature is disabled or a tenant is absent from the allowlist.

## Two-truck pilot

1. An active DieselBridge shop owner/admin opens Fleet → profile menu → Integrations.
2. Select the exact operating fleet company; connect with that company's Motive
   administrator and review provider consent.
3. Verify the returned Motive company name, then sync the supported device inventory.
4. Review exact VIN candidates and explicitly map each of the two existing trucks.
5. Allow the next scheduled or eligible manual sync. A point predating a new
   mapping cannot be attached to it; it remains unknown until a new reading arrives.
6. Verify observed timestamps, coordinates, speed conversion, loss-of-access
   handling, freshness and disconnect using the agreed live pilot procedure.
   Canonical truck mileage, driver identity and manual location remain unchanged.

This first surface supports current position and speed. It does not yet collect
engine hours, odometer, fault codes, cameras, HOS or history. Customer portal
self-service requires a separate, explicit company administrator grant before
its connection controls can be enabled; a customer association alone is insufficient.

## Rollback

Disable `MOTIVE_ENABLED` and stop/roll back the new collection code if required.
Retain schema and encrypted records while investigating; schema downgrade deletes
integration data and is not the routine production rollback. Local Disconnect
clears credentials, ends mappings and invalidates pending authorization attempts.
Provider-side revocation is not claimed; remove app access in Motive as needed.

## Offline UI preview

`frontend/tests/motive-preview.html` is a development-only acceptance fixture.
It uses synthetic company/truck records and an in-memory Axios adapter that blocks
unknown requests. Its synthetic auth state does not persist to app storage.
It is not a production build entry or a substitute for live pilot evidence.
