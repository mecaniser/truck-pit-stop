# DB-064 stale tab renewal — 2026-10-16

Owner: Security & Identity (root). High-risk auth lane. Status: reviewed; runtime and release pending.

## Evidence and scope

Current main inspected: `4061aaa83935fb67723ac5fcd340957781aae850`.
The active production browser uses legacy auth. Read-only cookie metadata and
JWT expiry inspection found a 30-minute access credential and 30-day refresh
credential (remember-me). No credential values were emitted. A separate older
tab has `reason=session_ended`; that URL alone does not identify its cause.

Confirmed source defect: each tab retains a refresh token in memory. The
keepalive broadcast announces only a timestamp. The refresh endpoint prefers
that body token over the newer shared HttpOnly cookie. Once a sibling rotates
the token and the short replay grace passes, the stale tab receives 401 despite
holding a valid browser cookie. Exact correlation to the user's reported
10–15-minute incident is not yet established. WorkOS dashboard settings remain
unverified because its dashboard requires sign-in; they do not govern the
observed active legacy session.

## Architecture contract and acceptance

Architecture independently reviewed the contract before implementation:

- Keep request/response shapes, session durations, and token rotation unchanged.
- For differing body/cookie refresh credentials, verify both JWTs and their
  refresh type; require the same nonempty subject, tenant, version, and
  remember-me scope. Use the cookie as authority, the body as identity assertion.
- Reject mismatched or invalid paired credentials without rotating either
  identity or overwriting the browser's cookies. Never fall back to another
  account's body credential.
- Apply existing revocation, version, and active-user checks to the selected
  credential. Body-only clients and cookie-only clients remain supported.
- Prove stale-tab recovery after replay grace, 24-hour-equivalent stale access,
  rejection without a valid cookie, explicit logout/revocation, invalid cookie,
  and different user/tenant/version/remember-me rejection.
- Independent QA/security review required before release. No migration.

## Local runtime preflight

Fresh isolated worktree on `codex/session-continuity`; main parent above. Root's
unrelated dirty work preserved. Port 5173 PID 27324 serves another task at
`/Users/sergio_m1_promax/.codex/worktrees/motive-driver-records/truck-pit-stop/frontend`.
No port-8000 listener. Existing APIs 8001/8002/8003 belong to other worktrees.
This worktree has no approved `backend/.env`; full-stack local runtime is
blocked, not aligned or browser-verified. No services replaced, configuration
copied, database migrated, or provider settings changed. Isolated test fixtures
will supply regression evidence, separately from real signed-in acceptance.

## Release gate

No production change yet. Rollback is reverting the focused code change.
Require protected CI and signed-in stale-tab renewal acceptance after authorized
deployment. All-day continuity must not be claimed from a short smoke check.

## Verification

- Before the fix, the new API regression reproduced `401 Token has been
  revoked` with a stale body and a valid rotated browser cookie. Five
  mismatched-cookie negative cases also failed because the body took priority.
- After the fix, all 13 new API tests pass, including eight renewals over a
  simulated 24-hour clock with the original access token expired, selected
  cookie expiry/type rejection, inactive user, invalidated version, logout,
  five mismatched credential cases, and body-only/cookie-only compatibility.
- The original no-cookie replay regression remains unchanged in intent: clear
  the newly rotated cookie before testing a replay without current authority.
- 18 existing frontend renewal/retry/scheduler tests pass. No frontend changed.
- Compilation and `git diff --check` pass.
- An initial simulated-clock fixture failed because this python-jose version
  uses `utcnow`; the fixture now advances both `now` and `utcnow`. The final
  test asserts that the original access token truly fails expiry validation.
- Test infrastructure uses in-process HTTP, isolated SQLite and FakeRedis;
  it does not establish real Redis TTL, browser sleep, or production full-day
  continuity. No actual user's credentials were used in fixtures.

Independent Architecture fallback Security: GO, 13 final tests passed, no blocking findings. Independent QA: GO for focused backend candidate, 30 tests passed in 32.21s. Both reviewers made no implementation edits. Live runtime/release acceptance remains pending.
