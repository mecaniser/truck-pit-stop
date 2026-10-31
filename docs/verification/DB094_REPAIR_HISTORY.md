# DB-094 production repair-history receipt

Completed 2026-10-30. All 15 authorized DBN completed repair orders are imported into Elis Logistics truck history: truck 603 has 6 and truck 609 has 9. Every source RO ID, unique VIN truck assignment and service-completion date matched the prior read-only audit. No missing, duplicate, unmatched, unavailable or review-required records.

The initial dry-run found 15 new records and saved none. The actual sync created 15; immediate replay created 0, updated 0 and left 15 unchanged. All 15 persisted in state `imported`. Snapshot `3fc1953abbba71a27d49fd4580e625a01fa0aaea3a94fd978542787bb8a48da4`.

Row fingerprints and counts remained identical for all existing repair expenses (58), finance events/postings/lines, repair reserve ledger, journal entries/lines and invoice staging. No payments, costs, accounting entries, credentials or historical invoice/PDF grants were added by this history release. A previously excluded historical PDF still returned 404 through the existing customer key.

## Releases

- Source PR https://github.com/mecaniser/truck-pit-stop/pull/696 merged as `fd0a8a143a23a9343e0706fcc790f50708d10a84`; Railway deployment `b2b5d378-6820-4106-8c49-69cef58fc5e7` SUCCESS. Public health 200; new route without key 401.
- EDG PR https://github.com/mecaniser/elis-logistics-manager/pull/158 merged as `b690044477fa8d608ff4849fcd598e37c7f18a02`; Railway deployment `fd85c1c5-ac84-4252-a901-e6499f8833dd` SUCCESS.
- All seven protected source checks passed on head `7534825684e5450556a20f0ef70c324a94b0b373`, workflow https://github.com/mecaniser/truck-pit-stop/actions/runs/41117141943. Full source backend log: 4099 passed, 406 skipped in 300.97s. Earlier complete runs also passed; concurrent main merges required fresh checks, rather than a CI stall.
- EDG local full backend 556 passed, 3 skipped; those 3 opt-in PostgreSQL checks separately passed. Frontend 61 tests, production build and focused lint passed. Independent QA and Security GO. Synthetic browser verified preview, import, replay and truck 6/9 pages.

## Evidence and limits

Protected task-local machine receipts: `db094-ro-live-preview.json`, `db094-ro-live-import.json`, `db094-source-ci-final.json`. They contain no API key. The import receipt retains financial row hashes, not private row contents.

Live signed-in UI acceptance could not finish: the browser session expired during deployment and the production page redirected to sign-in. No credentials were entered or changed. Runtime source fetch, complete-snapshot validation, actual production persistence, source scope/PDF denial, exact dates/links, repeat behavior and financial non-mutation were verified. After signing in, open https://www.elisprotech.com/repairs and the DBN repair history section; truck pages have their respective entries. Future manual updates use Sync repair history; no recurring schedule was requested or created.
