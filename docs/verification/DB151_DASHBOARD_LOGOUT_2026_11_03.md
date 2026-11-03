# DB-151 Dashboard session lifecycle correction

Owner: Frontend & UX. Branch: codex/dashboard-lifecycle-current-main, base82ec76fb. High-risk client identity boundary; independent QA/Security and real-backend acceptance required. Not released.

## Contract and scope

Use the existing getAuthenticatedSessionIdentity contract: pending logout, inactive and unauthenticated actors have no private DashboardHome surface. Pending logout displays only generic Signing out… feedback. Key the mounted dashboard by authenticated identity and payment permission, resetting private local selections after tenant/user/role/customer/epoch/permission changes. Keep canonical query prefixes for existing invalidation; pass AbortSignal to all four dashboard reads so unmount cancels requests. No backend API, cookie/auth policy, token lifetime, schema, migration, provider or financial writer change. Other local audit fixes are excluded; held619/622/623/638/748 remain untouched.

## Acceptance before release

- Real authStore and persistent QueryClient: no new reads, private cached data, selected repair or late-response revival after logout intent; signed-out and inactive cold/warm states fail closed; different tenant/session cannot inherit prior rows. Active user Overview/Active/Closeout/Activity retain normal behavior.
- Genuine normal synthetic login and real isolated backend: desktop/phone slow logout including browser Back into dashboard, aborted delayed dashboard reads, completed logout and subsequent different-tenant login. No auth-state injection or real financial action. Backend inactive/revoked identity checks remain unchanged and tested.
- Full frontend, affected backend authorization/session regression, build/lint, exact-head CI and fresh independent security/QA. Report skipped integration tests explicitly; do not treat skips as passes.

## Failing-first and initial correction

Existing lifecycle suite on current main:9 failed/1 passed; failures include extra reads and private surfaces during invalid session states, while tenant-change isolation already passes. Apply only the existing69ac5cdb dashboard correction and its10 real-store lifecycle tests. Initial correction10/10 passed on current locked dependencies (Node22/Vitest5). Pending feedback assertions retain explicit private-content and selected-workspace absence checks. Full regression, independent review and runtime evidence pending.

Rollback: revert this frontend correction and redeploy; no data/schema rollback. Stop release for any stale private display/read, cross-scope revival, active-user regression, failed required CI or material independent finding.
