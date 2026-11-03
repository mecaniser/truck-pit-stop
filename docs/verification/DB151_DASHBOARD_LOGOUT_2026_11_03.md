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

## Genuine-backend gate returned: staff shell reads

First real normal sign-out under12s tab-scoped latency correctly hid Dashboard rows and started no Dashboard GETs, but the retained session caused login navigation to remount the staff shell and ThemeProvider. Request observation recorded appearance and conversation reads during pending logout. This returned the initial scoped GO to implementation.

Expanded client boundary: while logoutInProgress is true, actual App unmounts the provider/router/view tree and displays generic Signing out feedback. The actual authStore logout continues and new-session epoch protection remains unchanged. The Dashboard guard remains defense in depth for inactive/unauthenticated state and component cancellation. Staff unread summary was also found keyed globally; its read and inbox writer now share an authenticated-session key, reject stale writer callbacks and cancel the list request on scope changes. Query prefixes/invalidation and server API contracts remain intact; no backend/store policy change.

Failing-first actual-App/shell tests10fail/1pass and inbox-writer tests2fail. Fresh full regression, new independent review and genuine backend repeat required before release. Initial automated GO is historical until that repeat.

## Regression reconciliation

Canonical ConnectedInbox integration fixture previously replaced the entire authStore and lacked the newly used real session helper. Updated to partial import plus explicit authenticated demo identity only for the dashboard integration block; cache assertion now requires the full scoped key.25/25 integration cases pass; fresh independent expanded gate114/114 across10files with no skips. Application source unchanged after252fbf.

Final full frontend run exposed one pre-existing asynchronous inventory URL-cleanup assertion: it waited for filter=stock, already present in the initial URL, then checked selected was gone before the queued navigation committed. Both assertions now share waitFor, retaining exact filter and selected absence plus no-write checks. Inventory application source is unchanged. Focused2/2 pass; repeat full frontend required.

Main advanced only in release documentation to2f401615; merged preserving both board histories with no product/dependency/test changes. Full backend rerun in corrected, network-isolated Python3.11/Node22 image:5337passed/468skipped/0failures; skips remain explicit dedicated PostgreSQL/Redis and disabled-test exclusions, as previously inventoried.
