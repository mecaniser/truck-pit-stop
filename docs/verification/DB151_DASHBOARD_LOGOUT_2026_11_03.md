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

## Revised genuine-backend acceptance

Normal browser login against a newly seeded disposable PostgreSQL/Redis backend used two synthetic tenant owners, real cookies, real authorization and real response payloads. No auth-store injection or payment submission. Desktop1440px and phone390px slow logout both showed only `Signing out…`; browser Back to `/dashboard/settings` during the request also showed only that generic state. Desktop request trace contained the logout200 and subsequent public unauthenticated bootstrap401s, with no new dashboard, appearance, branding or conversation reads after intent. Completed logout reached normal login. The same tab then switched B→A with a warm B dashboard cache: only A shop, repair and stock appeared. A→B was also checked.

For reliable phone timing, an external QA-only ASGI wrapper delayed real response delivery12s, with assertions for `ENVIRONMENT=test` and the exact disposable database suffix. It leaves authentication, handler execution, contents and cookies unchanged and is excluded from product source/PR. A20s delay of real overview/daily-workset response delivery then proved both requests end in `net::ERR_ABORTED`, canceled=true, when navigating away. No delayed data reappeared. All12 financial/inventory table row fingerprints are identical before/after. No production data or financial writes.

Evidence in workspace `dashboard-lifecycle-evidence`: `final-desktop-pending-logout-ax.txt`, `final-desktop-pending-logout.png`, `final-desktop-back-pending-ax.txt`, `final-desktop-logout-network.json`, `final-mobile-pending-ax.txt`, `final-mobile-pending.png`, `final-mobile-back-pending-ax.txt`, `tenant-a-after-warm-b-ax.txt`, `tenant-b-isolation-ax.txt`, `real-delayed-refresh-cancellation.json`. Fingerprints: sibling `dashboard-lifecycle-runtime/before.json` and `after.json`. No credentials/headers are retained in request evidence.

Full frontend2518/2518 across230files and lint pass on d6f56120; full backend5337pass/468skip/0failures in network-isolated Python3.11/Node22 image.463 skips require dedicated PostgreSQL fixtures,2 require Redis fixtures,3 are explicitly disabled enrollment/Zelle/reporting cases; they remain coverage debt, not passes. Independent114/114 no-skip security/QA probes passed. Inactive actors, failed logout and late positive/negative response races are covered by actual-store/component probes; the browser exercise uses active synthetic owners and controlled transport latency, not actual provider failures.

Main then advanced to efc4cc94 (#763 cookie-control placement), integrated as ba289343 preserving both board histories. Logout-specific product source remains identical252fbf; global source is not identical because the main cookie changes are included. Final post-integration frontend/build/lint and independent checks are required before release; exact-head hosted CI, PR/merge and production acceptance remain pending. Rollback signals above still apply.

PR765 published as draft at a5021c1b. First post#763 full run:2523 assertions passed across230files, but one unhandled repair-order fixture error made the run fail. The create test asserted POST payload before selected-workspace navigation settled; file teardown reset API promise mocks while the component was mounted. Explicit cleanup now precedes mock resets; all16 focused assertions remain, no RepairOrders product change. Focused pre/post16pass; failure was full-run timing dependent. A clean full rerun is required; no error suppression or weakened assertion. Independent reviewer agrees with narrow cleanup scope. Final browser check after canceled B reads and completed logout/relogin shows only A data (`tenant-a-after-delayed-b-response-ax.txt`).


## Final integrated local gate

Full repeat after explicit fixture cleanup: **2523/2523 tests,230/230 files, zero unhandled errors**,175.72s. Changed-source lint passes12 files; integrated production build passes. Final backend5337pass/468skip remains applicable: backend/requirements unchanged throughout this frontend-only branch. Independent Security/QA accepted both the original client privacy scope and the latest main integration (47 focused tests), plus16/16 teardown cases with no unhandled errors; earlier114 adverse probes also passed. Implementation gate GO; protected exact-head CI and production release remain distinct pending gates. Normal genuine-backend Active empty state, Closeout PRIVATE-A row and Activity PRIVATE-A link also verified after switching tenants.

Independent receipt is retained in workspace `dashboard-lifecycle-evidence/INDEPENDENT_SECURITY_QA_EXPANDED.md`; no implementing agent submitted a GitHub PR review. The source diff contains no QA latency wrapper, seeded accounts, credentials, backend changes or held recovery work. Test-only fixture corrections preserve all prior assertions.

Latest main d6a76cfa (#766) adds only cookie-release documentation. Merged preserving both board histories; product, tests and dependencies are byte-identical to the clean2523-test run. Protected exact-head CI must run on the resulting conflict-free head.
