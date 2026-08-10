# Diesel Bridge Network WorkOS organization authentication

## Authority boundary

WorkOS is authoritative for authentication, organization membership, role, and
coarse permission claims. Diesel Bridge Network keeps provider-neutral local
identity and tenant-membership projections for durable foreign keys, local
resource scope, audit history, and webhook reconciliation. Email is descriptive
and is never used to auto-link an identity.

`DriverProfile` remains a fleet-domain record. Its nullable, unique `user_id`
link is populated only after an exact WorkOS invitation is accepted. Removing a
login or membership never deletes or unlinks custody, PTIs, incidents, reviews,
or actor/subject attribution.

## Environment isolation

WorkOS Staging and Production are separate security boundaries. Creating a
second application inside Staging is not sufficient because applications in a
single WorkOS environment share users and organizations.

Local development uses only WorkOS Staging:

- Application: `Diesel Bridge Network`
- Client ID: `client_01KZMJ9VY45WFBHD5H736CBSZC`
- Callback: `http://localhost:8000/api/v1/auth/workos/callback`
- App homepage: `http://localhost:5173`
- Logout return: `http://localhost:5173/login`

Production uses only WorkOS Production credentials, users, organizations,
memberships, invitations, redirect registrations, and webhook secrets:

- Callback: `https://api.dieselbridge.com/api/v1/auth/workos/callback`
- App homepage: `https://www.dieselbridge.com`
- Logout return: `https://www.dieselbridge.com/login`

Never copy a WorkOS organization/user/membership ID between local and
production databases. Rebind an existing local User only through the exact
environment-specific invitation target; email is never a linking key.

## Environment

Required for the WorkOS path:

```text
WORKOS_AUTH_ENABLED=true
WORKOS_ENVIRONMENT=staging
WORKOS_API_KEY=<Diesel Bridge Network application-scoped secret>
WORKOS_CLIENT_ID=client_01KZMJ9VY45WFBHD5H736CBSZC
WORKOS_ISSUER=https://api.workos.com
WORKOS_REDIRECT_URI=http://localhost:8000/api/v1/auth/workos/callback
WORKOS_POST_LOGIN_URL=http://localhost:5173
WORKOS_WEBHOOK_SECRET=<endpoint secret once a public webhook URL exists>
WORKOS_ACCESS_TOKEN_MINUTES=5
WORKOS_SESSION_TTL_DAYS=7
```

Railway Production instead requires `WORKOS_ENVIRONMENT=production`, the
Production API key, Client ID and matching issuer, the HTTPS production URLs
above, and the Production webhook signing secret. Application startup fails
closed if production is paired with the Staging Client ID, a mismatched issuer,
or localhost URLs.

Legacy login remains available while `WORKOS_AUTH_ENABLED=false` and during the
tenant-by-tenant dual-run. A WorkOS-only user has `hashed_password = NULL` and is
rejected by legacy login, registration linking, password change, and password
reset.

## Roles

| Role | Permission intent |
| --- | --- |
| `garage_owner` | All 21 tenant operational/admin permissions, including `accountability:finalize` |
| `garage_admin` | 16 operational/admin permissions; no organization authority or accountability finalization |
| `fleet_manager` | Fleet view/manage/assign, inspection/incident management, accountability review, repair-order view/manage, reports |
| `mechanic` | Fleet view, repair-order view/work, inventory view, incident evidence/reporting |
| `receptionist` | Customer, repair-order, and billing workflow |
| `driver` | `driver_portal:use`, `inspections:perform`, `incidents:report` only; application resource checks enforce self-scope |

`platform_admin` remains locally governed in this phase. Customer portal access
is outside this WorkOS organization cutover.

## HTTP contract

- `GET /api/v1/auth/workos/login?tenant_id=<uuid>&return_to=/driver` starts AuthKit with
  browser-bound, one-time state and a validated relative return path.
- `GET /api/v1/auth/workos/callback` verifies the WorkOS-signed access token,
  resolves an active organization membership or exact accepted invitation,
  creates an opaque server session, and redirects to the app.
- `POST /api/v1/auth/workos/session/refresh` rotates the encrypted server-side
  WorkOS refresh token, revalidates membership, and issues a fresh five-minute
  local access cookie. It never enters the legacy refresh path.
- `POST /api/v1/auth/workos/logout` revokes and clears only the tenant WorkOS
  session; it does not clear a legacy/platform refresh session.
- `POST /api/v1/auth/workos/invitations` requires `members:manage`. A driver
  invitation also requires an explicitly selected unlinked `driver_profile_id`.
- `GET /api/v1/auth/workos/invitations/{id}` returns tenant-scoped invitation
  status.
- `POST /api/v1/auth/workos/organizations/provision` is local platform-admin
  only and idempotently creates/links a WorkOS organization using the immutable
  tenant UUID as `external_id`, then invites the first `garage_owner`.
- `POST /api/v1/auth/workos/organizations/rebind-production` is a one-tenant,
  platform-admin-only cutover path. It requires the exact existing Staging
  organization, user, and invitation IDs; archives those projections as
  superseded; and creates an exact-target Production owner invitation. It is
  idempotent and never changes the local User ID or domain history.
- `POST /api/v1/auth/workos/webhook` verifies `WorkOS-Signature` and processes
  events idempotently.

Endpoint guards continue to import:

```python
from app.core.workos_auth import CurrentPrincipal, require_permission
```

The principal contract remains:

```text
{local_user_id, workos_user_id, workos_org_id, tenant_id, permissions}
```

## Sessions and revocation

The browser never receives the WorkOS refresh token. It receives an opaque
`workos_session` cookie scoped to `/api/v1/auth/workos`; the encrypted refresh
credential is stored in Redis and rotated on every provider refresh. Local
access cookies are five minutes by default.

Signed, idempotent WorkOS webhooks are the sole continuous reconciliation path.
Membership/user/role changes increment the local token version immediately.
If webhook delivery is unavailable, the next provider refresh fails closed; the
maximum local access staleness is the five-minute access-cookie lifetime.

The Staging dashboard currently has no publicly reachable API origin, so its
webhook endpoint cannot be registered yet. Do not register localhost or invent a
staging hostname. Add the endpoint secret and public URL together when a real
staging or Production API origin exists.
