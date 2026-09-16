# DB-064 session recovery contract

Security & Identity owns implementation; Architecture & API Contracts specified
this contract. Authentication/tenant changes require independent final gates.

- Keep `POST /api/v1/auth/workos/session/refresh` and its successful response
  unchanged. Never expose provider credentials. No migration or duration change.
- Return 503 with `detail.code=session_refresh_unavailable` for provider transport,
  rate-limit, server, malformed-success, signing-key availability, and ambiguous
  authentication failures; retain the server session and existing cookies, mint
  no access token. Return 409 with `session_refresh_in_progress` for contention.
- Return 401 with `session_expired` for absent sessions, and `session_ended` for
  explicit provider refresh rejection, failed JWT verification, changed identity,
  inactive membership, or authorization loss. Never turn an ordinary API 403
  into session revocation. Preserve all verified tenant/user/permission checks.
- Every provider refresh requires an exclusively owned lock and a fresh session
  read. Release atomically in finally; stale owners cannot delete newer locks.
  Atomic session updates must not resurrect deleted sessions or overwrite another
  rotation. Save an issued encrypted rotated credential before downstream
  verification, but grant access only after every verification/identity check.
- Temporary membership-lookup failures propagate as temporary; missing/inactive
  memberships remain authorization failures. No indefinite authorization grace.
- Frontend retains session/drafts after temporary renewal errors, retries with
  backoff, and displays a non-blocking recovery status with a retry action.
  An operation rejected by the server remains failed; no automatic success claim.
- Definitive expiry routes staff and drivers to login with visible expiration
  copy. Revocation uses neutral session-ended copy. Never claim inactivity unless
  the server explicitly proves idle timeout; this change adds no inactivity rule.
- Late renewal results must not restore tokens or redirect a newer login: guard
  by authSessionEpoch. Timer and reactive renewal use the same terminal semantics.

Required negative fixtures: provider 429/5xx/network timeout; malformed responses;
JWKS and membership outages after rotation followed by recovery; explicit invalid
refresh; invalid signature/wrong org/wrong user; inactive membership; concurrent
renewals and lock expiry; logout during renewal without session resurrection;
legacy temporary vs terminal failures; staff/driver reason messages; renewal
around 9:45 does not sign out on a temporary failure or assert inactivity.

Local preflight: root inspected dedicated worktree `codex/session-recovery` at
`e02e19e7`; shared local API belongs to another task. Backend owner runs isolated
tests only, with no server/provider mutation. Runtime acceptance remains separate.

Provider semantics are grounded in [WorkOS refresh guidance](https://workos.com/docs/authkit/cli-auth)
and the [authentication API](https://workos.com/docs/reference/authkit/authentication):
`invalid_grant` requires new authentication; transport/server failures are retried.
A provider credential that rotated but was never received (or could not be saved)
cannot be reconstructed locally; subsequent explicit rejection still requires login.

Implementation details: Redis compare-and-set guards rotation, conditional deletion,
and lock release. A heartbeat renews the lease during downstream verification;
lease loss cancels the operation. Busy contenders return 409 without contacting
WorkOS. The terminal HTTP exception attaches an actual access-cookie deletion
header (injected Response cookies are discarded on HTTPException). The deleted
opaque session handle may remain as an inert cookie until the next login.

Owner validation (2026-09-12): isolated Docker `truck-pit-stop-api` with temporary
pytest dependencies, SQLite fixtures, and Redis in a `--network none` namespace:
67 passed / 1 pre-existing PostgreSQL-only skip across session recovery, real
Redis scripts/lease, refresh concurrency, WorkOS lifecycle/auth, invoice-access
compatibility. The real Redis lease fixture now uses a per-run UUID after parallel
owner/reviewer runs revealed a test-only fixed-key collision; isolated reruns pass.
`git diff --check` passed. These are owner checks, not an independent gate or a
browser/production acceptance claim. No existing service or database was mutated.
