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

Independent final QA GO: a1ecb1264f00515848eaa4ba45baef50e7d6d58b; no blocking
findings. Reviewer independently checked source isolation/URL safety/unchanged
financial semantics,23 backend and7 frontend tests, actual Tab access and
desktop34px/mobile44px component geometry. Final full npm build and changed-source
lint pass. [Draft PR746](https://github.com/mecaniser/truck-pit-stop/pull/746).
Subsequent commit records only this documentation/board evidence; application
source is byte-identical to independently approved candidate. No release claimed.

## Authorized release integration — 2026-11-01

Release & Reliability resumes PR746 under the user's release-queue authorization.
Original owner task **Find editing bugs** is idle at published bf6a21e5; its
untracked fixture/screenshot/audit files are preserved in the original worktree.
All integration work uses a separate clone/branch codex/pr746-release-integration.

Main d15aa737 is integrated at 0e488ec68eca902d5604ef494675e65ae8680496.
The sole application conflict retains both the provenance-validated URL helper
and main's `_source_summary(..., allow_paid_unapplied=False)` contract. All
financial calculations and retired/shared handling remain current-main behavior.
Both board histories remain intact. B4/importer remains held; this navigation
extension does not increase parity completion or authorize financial writes.

Owner integration checks: 210 focused backend tests and 100 frontend tests pass;
production build/control guard/TypeScript/Vite pass. Changed-source lint is
recorded separately against the actual origin/main baseline. Counts overlap.

Fresh independent integration GO at exact 0e488ec6: 181 backend tests (including
10 EDG export-contract cases) and 105 frontend tests passed; source, tenant,
digest, manifest, identity, fixed-origin/path, canonical sibling, keyboard,
new-tab/rel and no-row-open boundaries reviewed. Mechanical comparison confirms
main financial logic unchanged after excluding the URL helper/response field;
EDG manifest/export/settlement source remains byte-identical to main. No edits,
production actions, browser/service changes or formal PR approval by gatekeeper.

Exact-head protected CI, signed-in production desktop/mobile warning links and
correct ETS navigation, deployment SHA and readiness remain required before Done.
Rollback is code revert/redeploy; no migration/data rollback is required.
