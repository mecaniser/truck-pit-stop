# DB-130 outside-shop history search

Accountable: Backend & Integrations. Standard product lane; additive read contract, no migration or new access.

## Runtime alignment — 2026-10-15
Implementation checkout `ets-checkpoint-merge/truck-pit-stop`, branch `codex/outside-history-search`, starting `b6080f46`. Intentional existing preview overlay at `ets-parity-preview/truck-pit-stop` (`codex/ets-parity-preview`, `846360c3` plus prior parity changes), Vite PID35642 at127.0.0.1:5174, API origin127.0.0.1:8001. Docker `dieselbridge_api_ets-workflow-parity` mounts preview/backend at/app. Development database `postgres/truckpitstop_ets_workflow_parity_20261012`, schema172 head, ready database/Redis through frontend proxy. Existing provider/config/data unchanged. Authenticated preview rendered Performance Owner and runtime indicator. Changed-source overlay and feature-specific rendering verified below.

## Audit evidence
REA6.4.0 reanalyzed the four previously captured public ETS history/filter assets from2026-10-14 (no new vendor code or data copied into product). Evidence `ev_bb4bcd33bfc3289d94b1c9d03159b0e9a35c4ec80fa154f0bddeead83855327a`, artifact analysis at `/tmp/db130-qa/rea-analysis.json`. Existing authenticated ETS history search evidence is documented in DB123; current read-only ETS navigation reconfirmed vehicle directory/search. Static analysis is capability corroboration, not successful vendor-write evidence. Current DieselBridge source exposes only paging/Show voided for outside records; native repair history already has search.

## Acceptance
Search all pages by provider/work/reference; literal wildcard characters; filtered count and stable ordering; empty and whitespace baseline; role/tenant/vehicle/voided/deleted isolation; no billing/mileage writes. Preserve search through edit/cancel; protect draft if concurrent edit removes a match; clear and error/retry states; current results only after query changes. Light/Night desktop,320/390 portrait and landscape actual browser checks.

## Implementation and automated gate
Added optional bounded search to the existing scoped GET, parameterized literal substring matching across provider/work/reference before count/paging. UI debounces 300ms, hides superseded results, resets pages, preserves the query through editor Cancel/Escape and protects conflicting drafts; all scoped query variants invalidate after save. No schema or dependency changes.

Independent source/automated QA passes: 46 backend tests, 91 frontend history/receipt tests; TypeScript and focused ESLint pass. See DB130_INDEPENDENT_REVIEW.md. Initial new cache header assertion was corrected to allow the existing middleware's additional private directive.

Four source files copied to the intentional preview overlay only after byte-checking their prior contents against this branch baseline; Uvicorn reload exposes the 200-character search contract, database/Redis ready through the frontend /health/ready proxy. Actual authenticated desktop reference search, editor lock/Escape return, and 390x700 Night no-match state passed. Full local and production acceptance are recorded below.

## Local runtime acceptance completed — 2026-10-15
Authenticated Performance Owner used the actual preview with its PostgreSQL API. Light and Night Shop checked at 1280x720 desktop, 390x700 and 320x700 portrait, and 740x400 landscape using browser viewport/touch emulation. Shop/work/reference searches returned the synthetic record; a no-match term displayed zero matching and the specific empty state; Clear restored the unfiltered count. Character-by-character typing settled on the current query. Edit locked filters; Cancel and Escape retained the exact query. Customer → truck → customer and repair order → truck → customer → originating #PERF-0000001 navigation passed. A later save/filter check temporarily changed only the synthetic DB119 reference from DB119-LOCAL-CONCURRENT-B to DB130-LOCAL-SEARCH-EDIT: the old search immediately showed zero matches. Clear exposed the record for restoration; saving its original reference restored one matching result. The two QA reference edits remain in audit history; original record content, cost, mileage and status are restored. Original Night Shop appearance restored and temporary viewport/touch overrides cleared.

At 320px, rendered document width equaled viewport width; input font was 16px and compact touch controls measured 44px. Saved captures under `/tmp/db130-qa`: local-light-desktop.png, local-light-320.png, local-light-landscape.png, local-night-mobile-empty.png, local-night-320.png, local-night-landscape.png, plus local-night-desktop.png from the final save/restoration check. Fresh independent visual review passed all six with no clipping/readability findings. This is browser emulation, not physical-device testing. The 390px Light editor was exercised successfully, but its intermediate screenshot had a viewport-transition artifact and is not used as visual proof.

PR #537 candidate `1c70243a7b970a2f8ef94e7491d2ee6904280f56`, CI run38763719757. All six protected CI checks and deployment/production acceptance subsequently passed as recorded below. Production synthetic fixture baseline reconfirmed: DB115 QA vehicle has zero native repair history and two voided outside-shop records (DB119 and DB129); no production records changed during baseline inspection.

Release baseline: public `/build-version` reports `1a7b629872cd0231aa90a16f83ebeedf5eabd123`; Railway Web deployment `bb9eeb6a-fc30-4c68-8a5e-b1cdc955db4b` SUCCESS at that exact SHA. (`/build-version.json` is a frontend fallback, not the authoritative API endpoint.)

## Production acceptance plan (completed below)
Use only the existing DB115 synthetic customer/vehicle; baseline is two voided records and no active outside service. Verify shop, work and exact-reference searches, zero matches, Clear and Show voided count transitions on deployed code. Exercise edit Cancel/Escape and a reference save/filter transition on the synthetic DB119 record, restoring its original fields and voided status afterward. Check Light/Night desktop and touch-emulated portrait/landscape, customer return, feature asset/build identity and API readiness. Preserve the original Day Shop preference.

## Merge gate
All six protected contexts passed CI run38763719757 for candidate1c70243a. PR537 squash-merged2026-10-15T16:32:19Z as9ec5d0916fcf3a9e837c12e96ad4465f85778867. Fetched main tree is identical to tested head. Railway Web deployment `e39117c0-6def-40d2-93a4-cfa7cd789ff0` succeeded at that exact commit. Public `/build-version` matches `9ec5d0916fcf3a9e837c12e96ad4465f85778867`, built at `2026-10-15T16:37:00.389Z`; `/health` is alive and `/health/ready` reports database and Redis OK. Full backend CI: 3,197 passed, 162 skipped. No code changed after the successful CI run.

## Production browser acceptance completed — 2026-10-15

Delivery owner exercised the deployed application in the authenticated in-app browser. The independent source/automated/local visual gate is recorded separately; these production interactions and images are delivery-owner evidence.

| Environment | Completed checks |
| --- | --- |
| Light desktop, 1280 × 720 | Exact reference search with Show voided, restore the synthetic DB119 record, editor filter lock, Escape dismissal with the exact query retained |
| Light portrait, 390 × 700 | Edit/Cancel retained the query; saving a different reference immediately removed the record from the old search with zero matching; Clear exposed the record for restoring its original reference; work search then matched it |
| Light portrait, 320 × 700 | Work search/result and controls readable; document width 320px equaled viewport; search input 16px font and 44px height |
| Light landscape, 740 × 400 | Clear restored the unfiltered count; search and whole controls fit between the fixed header/footer with the existing single workspace scroll |
| Night desktop, 1280 × 720 | Full provider-name search returned the correct record and matching count; theme/readability checked visually |
| Night portrait, 320/390 × 700 | No-match state and Clear, character-by-character work search, void confirmation and filtered 1→0 transition, Show voided 0→1 transition; original reference/cost/mileage visible |
| Night landscape, 740 × 400 | Clear showed both voided records, disabling Show voided showed zero active records; Back returned to the original synthetic customer with $0 balance |

Production screenshots were saved and visually inspected under `/tmp/db130-qa/`: `production-light-desktop.png`, `production-light-mobile-save.png`, `production-light-320.png`, `production-light-landscape.png`, `production-night-desktop.png`, `production-night-320.png`, `production-night-mobile.png`, and `production-night-landscape.png`. No horizontal clipping, unreadable search controls or extra search scroll region was observed. Mobile checks use real production UI with browser viewport/touch emulation; no physical-device or software-keyboard certification is claimed. Customer return was exercised in production; the originating repair-order return was exercised locally.

Only the existing DB115 synthetic customer's QA vehicle was mutated. DB119 was temporarily restored, its reference changed to `DB130-PRODUCTION-SEARCH-QA`, then restored to `DB119-PRODUCTION-RETRY` and voided again with an explicit QA-cleanup reason. Original provider, description, service date, 98,000 miles and $240.50 reported cost are retained. Final baseline: zero active/two voided outside services; DB129 receipt fixture unchanged; native repair history zero, vehicle mileage blank, customer balance $0. The restore, two reference edits and cleanup void remain in the audit trail. No actual customer work or billing occurred. Original production Day Shop appearance confirmed applied; viewport/touch overrides cleared and the temporary local QA tab closed.

DB-130 is Done: approved additive contract, independent QA, local acceptance, all six CI contexts, merged/deployed source identity, health and production acceptance complete. No required follow-up for this scoped search outcome.
