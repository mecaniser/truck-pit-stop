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

## Shared browser handoff

The first correction hid Closeout in the tab initiating logout. A second warm tab still rendered shop A’s row while the real logout was held open. The revised client persists a signed-out projection immediately and observes session changes across tabs, including Back, reload and late cookie-bootstrap responses. Each authenticated identity receives its own React Query client. Global notifications are cleared when an identity changes, and late Lightning Order responses cannot announce A’s order to B.

Organization sign-in after explicit logout has a narrow, backwards-compatible contract. An optional UUID is bound to the one-time server-side OAuth state. Only successful fresh exchange appends the completion marker to the return path. The initiating tab consumes that marker before rendering, checks its original logout generation, and still requires the existing authenticated cookie-user read. A stale callback, an identity under review, an injected return parameter, a sibling tab and a replacement session do not grant access. No migration or token lifetime change.

At 1440 px and 390 px, Playwright logged into two separate synthetic shops in the same browser. A second tab showed A’s real Closeout row. While logout was held, the private row disappeared, Back/reload stayed private, and no new shop reads were observed. B then saw its own repair and stock. The old selected repair returned 403/404 under B. A DOM observer watched for A’s work across navigation. The test delays the genuine logout POST, then lets it reach the backend; it does not inject authentication state. A separate regression holds B’s inventory report response to detect cached A rows and notifications.

Independent Security/QA accepted the client isolation, previously unscoped report cache, notification cleanup, and callback handling. The reviewer independently repeated both real browser cases. The WorkOS provider itself was not used: callback and cookie races are covered with controlled exchange responses, including successful exchange, replay and identity review. The backend WorkOS auth suite passed all 26 tests.

Runtime: isolated Vite on 5297 proxies the same checkout’s mounted backend on 8197. The database is dashboard_lifecycle_disposable; PostgreSQL and Redis passed readiness. Earlier localhost smoke on 5285 was against the prior frontend candidate and is historical. To run again, supply DB151_SIGNOUT_QA_URL (loopback only) and DB151_SIGNOUT_QA_PASSWORD for the two lifecycle fixture owners, then run Playwright from e2e with playwright.db151-local.config.ts and the db151-signout filter.
