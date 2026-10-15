# DB-130 outside-shop history search

Accountable: Backend & Integrations. Standard product lane; additive read contract, no migration or new access.

## Runtime alignment — 2026-10-15
Implementation checkout `ets-checkpoint-merge/truck-pit-stop`, branch `codex/outside-history-search`, starting `b6080f46`. Intentional existing preview overlay at `ets-parity-preview/truck-pit-stop` (`codex/ets-parity-preview`, `846360c3` plus prior parity changes), Vite PID35642 at127.0.0.1:5174, API origin127.0.0.1:8001. Docker `dieselbridge_api_ets-workflow-parity` mounts preview/backend at/app. Development database `postgres/truckpitstop_ets_workflow_parity_20261012`, schema172 head, ready database/Redis through frontend proxy. Existing provider/config/data unchanged. Authenticated preview rendered Performance Owner and runtime indicator. Changed-source overlay and feature-specific rendering pending.

## Audit evidence
REA6.4.0 reanalyzed the four previously captured public ETS history/filter assets from2026-10-14 (no new vendor code or data copied into product). Evidence `ev_bb4bcd33bfc3289d94b1c9d03159b0e9a35c4ec80fa154f0bddeead83855327a`, artifact analysis at `/tmp/db130-qa/rea-analysis.json`. Existing authenticated ETS history search evidence is documented in DB123; current read-only ETS navigation reconfirmed vehicle directory/search. Static analysis is capability corroboration, not successful vendor-write evidence. Current DieselBridge source exposes only paging/Show voided for outside records; native repair history already has search.

## Acceptance
Search all pages by provider/work/reference; literal wildcard characters; filtered count and stable ordering; empty and whitespace baseline; role/tenant/vehicle/voided/deleted isolation; no billing/mileage writes. Preserve search through edit/cancel; protect draft if concurrent edit removes a match; clear and error/retry states; current results only after query changes. Light/Night desktop,320/390 portrait and landscape actual browser checks.

## Implementation and automated gate
Added optional bounded search to the existing scoped GET, parameterized literal substring matching across provider/work/reference before count/paging. UI debounces 300ms, hides superseded results, resets pages, preserves the query through editor Cancel/Escape and protects conflicting drafts; all scoped query variants invalidate after save. No schema or dependency changes.

Independent source/automated QA passes: 46 backend tests, 91 frontend history/receipt tests; TypeScript and focused ESLint pass. See DB130_INDEPENDENT_REVIEW.md. Initial new cache header assertion was corrected to allow the existing middleware's additional private directive.

Four source files copied to the intentional preview overlay only after byte-checking their prior contents against this branch baseline; Uvicorn reload exposes the 200-character search contract, database/Redis ready through the frontend /health/ready proxy. Actual authenticated desktop reference search, editor lock/Escape return, and 390x700 Night no-match state passed. Remaining theme/mobile acceptance and production gate pending.
