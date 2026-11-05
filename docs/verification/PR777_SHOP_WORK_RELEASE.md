# PR777 Shop Work production release

Accountable: Frontend & UX. Fast UI lane. User authorized review, merge, deployment and verification of all four Shop Work views. Existing API, tenant and payment mutation contracts are unchanged.

## Review, CI and merge

- Reviewed final diff for exact record selection, role/session query scopes, cancellation, failed/partial read states, zero-job/zero-visit behavior, Back/reload, duplicate actions and integration with existing workspaces. No blocking findings.
- Head `d68b7940c9ccfc2e54b398bc415ebeb5d5e4990b`: all seven checks in [run41903326508](https://github.com/mecaniser/truck-pit-stop/actions/runs/41903326508) passed. Frontend critical partition456 and remaining full partition2322 pass (2778 total); production build, changed-source lint, shared controls and Playwright smoke pass. Backend jobs use the unchanged-source scope gate, not a newly executed full backend suite.
- [PR777](https://github.com/mecaniser/truck-pit-stop/pull/777) squash merged at2026-11-04T20:19:23Z as `bc48b668cdbbbf0b7504c96165f2b322bb22e0d9`. Merged and checked trees both `c91377ef21e3ee25c2d74a85ed4893636a0e094e`.

## Deployment

Railway Web deployment `0645d842-7db6-4ac1-942b-e21b9d385fb4` succeeded on the exact merge. Public `https://www.dieselbridge.com/build-version` reports the same SHA, built_at2026-11-04T20:21:12.074Z. `/health/ready` reports ready, production, database and Redis healthy. No manual redeployment, service setting, provider setting, migration or financial backfill was required. Prior healthy Web deployment `6144e8df-037a-4680-865f-04c190828d83` on e64c2e2f is the code-only rollback reference.

## Signed-in production acceptance

Verified in the existing authenticated Truck Pit Stop shop using the in-app browser after reloading the new build.

| Journey | Live result |
| --- | --- |
| Overview | Shop Work is the first heading; both old banners are absent. One exact Zelle review joins existing operational tasks. Active count0. No empty visit-review task. Service visits remains beside Coming up. |
| Payment task | Opens invoice TPS-1687, settlement890f4fe6-4719-4bca-b8ba-8666cfabfddd, selected attemptb5353c41-9632-4d33-920c-0c2fad7ce43b. Requested Zelle168.44, invoice balance268.44, pending268.44 and available0 match pre-deployment baseline. Reload keeps exact invoice; browser Back returns to the originating task and restores focus. |
| Active work | Displays No active jobs in this view and a direct Review Zelle payment next action. It opens the same TPS-1687 record. Closing returns to Active work and restores the action focus. |
| Closeout | Payment review is below the view switch, not above the heading. Its review opens the same invoice/amount. Existing repair row opens TPS-828ACD84-000052, vehicle unit8, in the existing workspace. Back restores Closeout. |
| Activity | Recent activity appears without either review banner. ETS-1917-85955 action opens its exact selected repair order. Shop Work breadcrumb returns to Activity. |
| Zero pending visits | Service visits opens Needs review with No pending visit requests. All requests also confirms no visit-request records. No production requests were created for testing. |
| Existing reservation | Reservations opens the pre-existing recorded PM Service Volvo3-F for unit609 (July28). Review opens appointment09a9dda2-256d-4d37-b206-65a86beafa25 with matching service/vehicle/date. Recorded visit is correctly not presented as an upcoming confirmed appointment. |
| Core review | Six-core task selects coreac00b58f-2d65-4d24-89ac-99664fb61a41, Trailer Tire Aufine, TPS-828ACD84-000038, directly in Purchasing/Cores. Back restores exact board-task focus. |
| Stock review | Brake pads front opens inventory9b0d398f-11fc-4bee-a12b-d7a8cfff5c29, matching part heading and SKU, without requiring another list selection. Back restores exact task. |
| Phone390 | Overview and payment-dialog screenshots inspected. document scrollWidth390 equals viewport390. No horizontal overflow. Temporary viewport reset to original1864 width. |

Browser console error log is empty after acceptance. Retained CDP network window contains no HTTP4xx/5xx or non-GET/non-OPTIONS business requests; two cancelled reads are expected during navigation. The event buffer was truncated, so this is not claimed as a full-session traffic audit. No payment confirmation, transfer report, invoice edit, visit mutation, stock recovery or notification was submitted. Existing payment display values remained unchanged. Browser left on Overview with the user's original viewport.

## Evidence limits

There are zero live visit-request records, so a populated board-to-request acceptance flow cannot be demonstrated in this production shop without creating business data. The genuine disposable-backend customer submission/review/accept/arrival, exact request and confirmed reservation reload/Back, cross-shop invalid-record isolation, and Day/Night desktop/phone evidence remain in [implementation receipt](DB151_REVIEW_BOARD_2026_11_04.md). Production screenshots were directly inspected via the browser tool; no standalone screenshot file is claimed.

This documentation receipt records the verified product release. It changes no runtime source.
