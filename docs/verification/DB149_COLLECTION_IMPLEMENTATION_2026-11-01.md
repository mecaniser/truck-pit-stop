# DB-149 collection implementation verification — November 1, 2026

Status: independent local PostgreSQL/security gate GO at8275f16b; final frontend delta, protected CI, deployment and live activation remain separate gates. Backend & Integrations is accountable. No production financial records were written and no payment/provider request or customer message was sent.

## Exact user outcome and source facts

Create one collection copy of the existing debt, not another sale. Correct target is ETS displayed invoice1687/internal468019, service1821/internal506423, DBN original5f491f59-1092-4c5b-97a7-3372299f5edc. Current ETS balance268.44 with zero source allocations; QBO transaction7104 shows invoice1687, original268.44/open268.44 and only original/system-edit audit activity. QBO API auth remains separately expired; the authenticated UI read establishes these facts, not API401. Source original314.02 was excluded and not cleared.

The user explicitly confirmed the two customer records represent the same legal business and requested the existing DBN portal account. The handoff records that exact reviewed billing binding while preserving original source customer, RO, User, vehicle ownership and original financial facts. The existing source customer and target portal customer differ; no current-vehicle-owner inference substitutes for the review.

A fresh full ETS page reload confirmed embedded service.customer public ID97052, UUID02104722-a300-48a5-ba98-0eab3b2fb32e and deleted=false, linked to exact service/invoice identity. No internal customer ID is invented. The prior persisted capture lacks this newer remote customer proof and cannot activate the cross-customer handoff; a reviewed bounded evidence refresh is required first, then another trusted observation after prepare. This read-only observation was not persisted as production source evidence.

## Owner verification

- Frontend:31 focused tests across source collection review/tasks, customer account, historical customer invoice and guest invoice payment clarity pass. TypeScript and new-feature ESLint pass. Production build passed before the final billing extension; repeat on the integrated final head remains required.
- Backend owner:210 focused checks and final15 DB149 scenarios passed on the billing-extension head. Earlier importer partition36 Python/6 Node/12 disposable PostgreSQL tests passed. These counts describe their respective suites, not a single disjoint total.
- Independent reviewer found and returned dashboard cross-join, export, source-payment reparenting, source-date, source-echo attribution, stale-read, A/R and customer-audience issues; owner corrections are committed. Earlier PostgreSQL migration/concurrency proof belongs to the earlier schema and is not substituted for the new billing-extension gate.

## Local runtime / visual receipt

Intended worktree is `.codex/worktrees/ets-native-collection/truck-pit-stop`, branch `codex/ets-native-collection`, initial main baseaa549f2e. Mandatory local runtime preflight was read/run. Full app remains blocked: this worktree has no approved backend/.env and ports5173/8000 belong to other work; existing services/databases were preserved. No secrets copied, live rails enabled or shared populated database migrated.

An explicitly fictional standalone actual-component preview served at `http://127.0.0.1:4179/collection-preview.html`, Node PID32122 with cwd matching this worktree/frontend. Its Axios adapter answers only fixture routes and denies any other request; API proxy points at an unavailable local port. This is not a connected backend/auth acceptance claim. Browser checks cover review→acknowledgment→prepare→activation as fictional transitions, tenant customer picker, same-business review, receipt marker instructions and current versus historical balance. Phone content width equals viewport width, and action labels stay on one44px control line. The account menu fits390px and retains distinct source/portal choices. Temporary viewport overrides were restored.

Local fictional screenshots are under output/db149-collection: desktop-fictional.png, mobile-fictional.png, mobile-reconciliation-fictional.png, mobile-billing-menu-fictional.png and mobile-billing-review-fictional.png. These are generated QA artifacts, not real customer invoices or source evidence.

Actual PDF renderer fixtures were rendered with Poppler and visually inspected: partial original1000/prior400/transferred600 unpaid; same copy paid600/current0; historical original with linked current0; target-amount preview268.44. Collection copies have a dedicated transferred-balance line and no fabricated labor/hours/new tax. Original history is clearly nonpayable, paid DBN funds stay recorded, and review QR/link remain visible. Preview is fictional/not issued. The target preview keeps original dueOctober19 and completedOctober20; no payment terms were extended.

## Required release / activation boundaries

Current main b28bac1a was integrated in0104e81d. Independent PostgreSQL/security GO at8275f16b covers62 focused tests, fresh migration197 and empty down/up, archived evidence bootstrap, reviewed A→B prepare/activation, native receipt/task/exact echo/external receipt, concurrent exact-once attempts, six SQL adversarial denials and populated-downgrade refusal. Full authenticated browser acceptance and protected PR CI remain required; final frontend build is being recorded separately. Migration197 is unreleased and introduces immutable handoff/receipt linkage and source-money fences. Populated downgrade must refuse rather than erase debt history.

Deploying code is not activation. Verify API/frontend and ETS collector fence versions before any prepare. Do not run full nightly sync to refresh one invoice. Use reviewed target-only read and evidence-only persistence with exact tenant/source/customer/version/digest checks, no importer financial writers. Activation needs source proof after collector ownership acknowledgment, positive verified remaining debt, no uncertain provider/source payment and the exact reviewed target.

DBN is the primary collector. Confirmed DBN receipts create a durable manual ETS task. Staff enters only principal with DBN-RECEIPT:<payment UUID> in ETS notes; DBN verifies exact immutable allocation IDs and marker before acknowledging. A distinct trusted ETS receipt is applied once without provider charge. Stale source cannot reopen paid DBN principal. Existing ETS/QBO payment links need an explicit operational cutover; no cross-system atomic exclusion is claimed. No automatic ETS mark-paid, customer send or new QBO sale follows from activation.

Incremental accounting feeds suppress original handed-off debt and collection copies without tombstones. Complete-feed holds are constrained to a source row that was already financially authorized by that key's existing query; a target customer alone cannot pause unrelated records. The configured target production feed has20 unrelated eligible invoice identities; before/after snapshot continuity must be verified. No downstream successful cost import was inferred from key usage.

Before activation, ordinary code rollback with zero handoffs can leave schema197 unused. After a handoff/receipt exists, retain source/importer/payment fences and financial rows; do not blindly downgrade, delete links or retry provider/ETS entries. Recovery must preserve confirmed provider results and use audited reconciliation/forward fixes.

## Final integration delta

Frontend56 focused tests across8 files and TypeScript pass. Tax UI/CSV warnings and explicit gross/net/unapplied/profit scope were independently reviewed. Reviewer returned unqualified partial chart/average wording; the owner corrected shared series/tooltip, average and insight labels and added rendered assertions. Final delta checks and exact PR head remain recorded at release, not inferred from these earlier passes. The final268.44 fictional PDF was rendered and visually inspected with original October19 due and October20 service dates. No production writes or provider calls occurred.

## PR review checkpoint

Draft PR750: https://github.com/mecaniser/truck-pit-stop/pull/750. Current-main1c9c5cb9 integrated inc6864b11; board-only conflict preserved both histories. Independent merge delta GO:186 backend and64 frontend regression tests pass; migration197 unchanged and prior actual PostgreSQL gate remains applicable. Independent final reporting delta20/20 tests GO. Final build (shared controls, TypeScript, Vite) and baseline-aware lint across18 changed frontend files pass atc6864b11. Required GitHub Quality gates run41357782091 is in progress, not passing evidence yet.

No source or customer mutation has occurred. Current review output remains fictional/not issued. Live customer sign-in, bounded fresh evidence, source ownership cutover and actual invoice-specific readiness are distinct outstanding acceptance steps; never submit a payment to prove a control works.

## Required CI failure and correction

Run41357867159 at0a077784 failed the existing empty-dashboard query-budget assertion (13queries versus12) while598 checks passed in that partition. Commit259fad50 skips the unnecessary collection Payment query when no collection payment IDs exist. The original budget is unchanged; owner29 dashboard and collection reporting checks pass. Independent delta review and a new exact-head CI result remain required.

## Full-suite compatibility gate

Run41358449881 atc8ac2239 passed migration graph, critical backend, frontend checks, full frontend and Playwright smoke. Full backend failed12 with4600pass: older owner-attested cash/tax audit snapshot compatibility, incomplete customer/invoice notification/import guard fixtures and cash-report row contract mocks. Backend owner is investigating; independent Security is checking the legacy hash correction. This is a release blocker, not dismissed as informational. No production actions occurred.

Correctioncdb2e7d3: owner119 tests across failing files plusDB149 pass. Independent security65 checks pass for persisted pre142/null compatibility and explicit nonNULL/changed lineage hash denial. Current canonical digest stays unchanged; legacy omission of source_debt_handoff_id is allowed only whileNULL, retaining ancestor snapshot/tax/money/tenant checks. Other fixes align ordinary fixture attributes and cash-report4-column row contract. Fresh full CI pending; no release claim.

## P1 follow-up: source-total drift at payment admission

Independent review of a249da70 found that activation and explicit reconciliation checked source-total drift, but subsequent payment admission checked allocation identities only. A fresh lower or higher source-issued total with unchanged allocations could therefore leave readiness enabled and allow an attempt against the old opening principal.

The shared `invoice_handoff(check_source=True)` gate now rejects a verified source-issued total different from immutable `original_issued_total`, using `source_invoice_total_changed`. This covers invoice-specific provider readiness, collection summaries and new attempts. Attempt admission still acquires the existing tenant financial lock before reading proof. It deliberately does not compare current ETS and DBN remaining balances: a confirmed native receipt awaiting manual ETS acknowledgement must neither reopen debt nor block an otherwise valid next attempt. The existing verified-provider-fact confirmation path retains already-confirmed money even after source drift; new collection remains held.

Six new regressions initially produced five expected failures and one passing acknowledgement-lag control. After the four-line guard, all100 tests across `test_db048_invoice_settlements.py`, `test_db149_collection_admission.py`, `test_db149_source_collection.py` and `test_ets_handoff_ingestion.py` pass (39 existing deprecation warnings). Tests exercise fresh total increases/decreases, readiness and summary holds, source recheck after the financial lock, zero attempt/payment/ledger/task writes on rejection, idempotent attempts with an unacknowledged native receipt, and retention of a fictional verified provider outcome. Tests use isolated SQLite fixtures; no provider request or business-data operation occurs.

Migration197, source/customer identity checks, allocation reconciliation, existing money writers and the tenant advisory-lock implementation are unchanged. Real two-session PostgreSQL concurrency was not rerun in this task; the new ordering regression is not represented as that gate. Fresh independent financial/security review and exact-head CI are required for this delta. Approved authenticated runtime, preview review, bounded source proof, collector cutover, invoice readiness and customer acceptance remain outstanding. No merge, deployment or live collection is authorized by this test receipt.
