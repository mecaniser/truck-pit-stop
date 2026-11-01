# DB-139 — ETS source verification link

Owner Frontend & UX; Standard read-only API extension. Architecture contract GO;
independent final QA recorded with PR. No financial repair, migration, provider
mutation or production record write. Contract: db139-ets-source-verification-link.

Optional source_invoice_url comes only from existing validated ETS evidence and
trusted shop binding. Fixed HTTPS origin/path, safe path IDs, preserved leading
zeros, shared canonical invoice route. Invalid/missing identities hide navigation;
financial amounts/status/holds are unchanged. UI repeats an origin/path allowlist,
uses new tab/noopener/noreferrer, keeps keyboard focus visible, and cannot trigger
row opening. Link is outside the read-only tooltip to preserve keyboard semantics.

Local alignment2026-11-01: branch codex/ets-billing-source-link, baseaa549f2e,
worktree ets-footer-clarity/truck-pit-stop. Frontend5203 PID34635 and API8043
container backend bind point to this checkout; DBtruckpitstop_db042_qa/Redis12,
migration196 current=head. Frontend proxy readiness ready and served OpenAPI
contains the optional field. Real-component fixture /footer-qa.html verifies
expanded warning Details and footer source action. At390px, both links are44px
high, x43..170.54 and218.47..346, no horizontal overflow. Tab moves from tooltip
trigger to external link, and tooltip dismisses normally. Viewport reset.

172 focused backend tests pass: source paid/unpaid/mismatch, path safety, leading
zeros, missing/foreign/digest/manifest/ambiguous identity, unchanged financial
outputs, shared and retired invoice semantics.100 focused frontend tests pass:
link destination/rel/target, keyboard access, unsafe URL rejection, failure/healthy
hiding and no row-open activation. Full npm build including control lint,
TypeScript/Vite and changed-source lint pass. Independent reviewer separately
ran23 backend and7 frontend link-focused checks, all pass, no blocker reported.

Local preview uses explicit fictional component props because retained local DB
has no ETS orders; no signed-in imported runtime journey is claimed locally.
Live previous-platform route was independently verified via normal authenticated
browser access to the requested invoice. Private production comparison/screenshot
remain in output/ets1887-audit and are not part of Git. No production changes.

This feature is not merged or deployed until separately released. Financial
reconciliation of the existing stored invoice is outside this implementation.
