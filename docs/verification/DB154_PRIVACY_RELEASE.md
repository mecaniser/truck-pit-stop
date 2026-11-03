# DB-154 / DB-155 — Privacy and dependency release

2026-11-03. Accountable owner: Frontend & UX. Release verification: Release & Reliability. Engineering delivery evidence; no legal compliance certification.

## Checked source and merge

[PR761](https://github.com/mecaniser/truck-pit-stop/pull/761) merged as `82ec76fb03c8c4e0486d0265b60e7fefc128dbc6`. Final checked head `bb6dbb06f3426970d66e140b7fd76190d168a201` and merged commit have identical tree `c95b83649fff159c43f64e425a8bf3b3288ef286`.

[Exact-head Quality gates41589185324](https://github.com/mecaniser/truck-pit-stop/actions/runs/41589185324) passed all seven jobs: migration graph, dependency preparation, critical backend, remaining backend, frontend checks, remaining frontend, and Playwright smoke. This repository intentionally uses protected PR checks rather than a duplicate push run on main; no separate main run is claimed.

Local integration evidence: frontend **226 files /2495 tests passing**; backend **5337 passing /468 skipped**, with backend source unchanged by main integration. Production build, shared controls, changed-source lint (26files), full-stack smoke5/5, actual isolated authenticated navigation and public policies passed. Registry audits of all four npm lock graphs and the89-package Python lock reported **0 known advisories**. This is not an OS/container-wide or future vulnerability guarantee.

Independent Security and QA GO apply to the final source. Earlier failures were fixed before merge: Router7 relative links; Vitest constructor/timer compatibility; real-shaped repair workspace fixtures and identity guard; FastAPI/Pillow test compatibility; stale CI HTTPX constraint; and a transient invalid ETS JSON edit. Final JSON parses, deployment configuration checks pass, ETS fixtures10/10 pass. The actual ETS image built and ran Node22.23.4, upgraded Python imports and Chromium with a synthetic page under `--network none`; no provider job was exercised.

## Production acceptance

All three Git-connected affected services report **SUCCESS** on exact merge82ec76fb:

| Service | Deployment | Verified behavior |
| --- | --- | --- |
| API/web | `210dc8cf-fccf-4a81-b76c-ee924adee294` | Dockerfile backend/Dockerfile, predeploy Alembic+schema preflight retained, uvicorn start and /health gate retained. |
| Main worker | `ef248a29-79e0-4887-94f2-49bbdb5cd1b0` | Same locked image; existing Celery beat/concurrency2 command retained. |
| ETS scheduled worker | `751c27a0-2e1b-4e7c-a078-59552eb74031` | Dockerfile.ets-sync, unchanged nightly00:00UTC cron/start/restart configuration; lockfile now included in watched paths. No manual sync triggered. |

Public `/build-version` on both www and API origins serves82ec76fb. `/health` reports alive; `/health/ready` reports production database and Redis OK. No new migration is introduced by this PR. Manually pinned Motive worker images, schedules, provider flags and existing reconciliation holds were not advanced or retriggered; no fleet-wide runtime patch claim is made.

Actual live browser verified privacy, terms, refunds, cookies and deletion pages with Elis Tech LLC identity/address and support@dieselbridge.com; correct monthly/non-refundable/cancel-future-renewal wording; keyboard skip link focuses policy-content; keyboard cookie dismissal returns focus to settings; settings reopens; enrollment disclosure precedes data entry and disclaims implied SMS/marketing consent. No console errors were observed in these policy journeys. Signed-in navigation was accepted in the isolated real-stack sandbox, not claimed as newly verified on a production customer session. No production form was submitted, email sent, payment made or customer data deleted.

## Email domain

Resend reports **dieselbridge.com verified**, sending enabled, with DKIM, return-path MX/SPF and CNAME all verified. Existing PrivateEmail root MX pair and SPF were preserved in authoritative/public DNS. Receiving mail remains with the existing provider.

Read-only inspection inside both deployed API and main worker confirms source82ec76fb, sender **noreply@dieselbridge.com**, public support **support@dieselbridge.com**, FastAPI0.162.0, PyJWT2.15.1, and rendered unsubscribe/deletion request footer links. The public contact API returns only configured business support details, with no administrator phone. No individual email-delivery claim is inferred from configuration or provider verification.

## Operational limits and rollback

Deletion, cancellation and optional-email unsubscribe are explicitly manual request channels. The operator must monitor support@dieselbridge.com and actually handle requests, identity verification, retention exceptions and suppression. Optional marketing requires enforceable consent/suppression before launch. Applicable legal obligations, processor contracts and complete retention/consent inventories remain business responsibilities; engineering cannot guarantee freedom from lawsuits.

Rollback signal: auth/enrollment failures, routing regressions, email-provider errors or failed readiness. Revert PR761 through a reviewed PR and verified deploy if required; preserve incoming DNS and keep the sender on a verified domain. No rollback or financial/provider reconciliation was needed during acceptance.
