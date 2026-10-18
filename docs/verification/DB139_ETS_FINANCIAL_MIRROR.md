# DB-139 ETS financial mirror — verification boundary

2026-10-18. Owner: Backend & Integrations. Branch: `codex/db139-ets-financial-mirror`. [PR #576](https://github.com/mecaniser/truck-pit-stop/pull/576). Status: source/test approved; not released or Done.

## Root cause and read-only source inspection

The reviewed imported PM repair order has a $150 labor header, zero saved labor-line value and zero saved work total. The old footer calculates `0 + (0 - 150) = -150`. Its linked ETS invoice is $534.41: $150 labor, $339.52 parts, $4.50 supplies and $40.39 tax. Preserved ETS source evidence reports a completed allocation and zero balance. Read-only QuickBooks inspection corroborated invoice total, zero balance, customer and vehicle identity, and a directly allocated payment. Work completion alone was not used as payment proof.

A second example has stale imported invoice columns suggesting a $63.66 remainder. Its latest validated ETS snapshot and QuickBooks both show $2,202.96 paid, zero balance. A partial example shows $9,658 total, $2,115.87 allocated and $7,542.13 remaining in ETS and QBO; customer matched, but vehicle identity was unavailable in the QBO document. Other bounded QBO samples matched customer and amounts without vehicle proof. These observations do not establish blanket QuickBooks reconciliation.

Read-only repeatable-read production audit, same tenant and active imported orders: **3,560 orders**, 1,643 with a source invoice and 1,917 without; 595 labor-header/line mismatches, **585 negative old-footer calculations**, 674 zero work totals with positive source invoice totals, and 607 completed work orders linked to locally paid invoices. These categories overlap.

A candidate reader was evaluated in memory against preserved production source observations without deploying code, modifying rows, invoking an importer or calling financial writers. With the explicitly verified tenant/shop binding supplied in memory: **1,532 paid, 24 unpaid, 1 partial, 2,003 unverified**; 1,559 used validated source snapshots and 2,001 retained imported-record evidence only. Snapshot freshness can change these counts. The PM and stale-total examples returned paid/zero remainder; the partial returned $7,542.13. This is candidate evaluation, not HTTP/browser or deployment evidence.

Private 0600 audit receipts and cohort hashes are outside Git under the operator's private audit directory. Public documentation intentionally omits customer, vehicle, tenant, shop and row identifiers. Normal OAuth credential renewal was required for QBO GET access; no QBO accounting mutation occurred. No invoice, payment, receivable, service, inventory or provider financial record was created or rewritten by this inspection.

## Implemented behavior

- Tenant- and permission-scoped read-only imported billing endpoint; native orders reject, foreign/deleted orders remain unavailable.
- A fresh, identity/digest/manifest/shop-bound source snapshot supplies total, unique completed allocations, balance and observed state. Unsupported, stale, incomplete or conflicting evidence stays unverified. Imported financial columns alone never assert paid/partial/unpaid or a remaining debt.
- Batched list/workspace total enrichment; full-filter imported-row metadata hides misleading mixed aggregates even when imported rows are on unloaded pages. Daily queue endpoints already exclude imported orders.
- Imported detail, including full-detail History, hides unsupported zero labor/parts prices and native invoice/edit/payment/QBO actions. Source-paid and remaining amounts retain exact decimal cents. Source observations and imported-row update timestamps have distinct labels. QuickBooks remains explicitly not checked by the runtime reader.
- Future operational/financial insert changes are preserved separately on `codex/db139-importer-money-held` at `06086f72`. They are excluded from the reader-only #576 release; no importer code, image or configuration is changed by this release.

## Independent gates and checks

Architecture approved the exact read contract and dedicated Web display binding. Independent QA/Security source/test GO followed corrections for stale payment claims, source confirmation binding, tenant joins, paged totals, detail pricing leaks, labor endpoint scope, disputed future splits, exact cents and timestamp semantics. Review did not execute browser tests or production writers.

Focused backend: **111 passed**, covering imported money, source reader and tenant/permission failures, invoice guards, workspace projection and filtered value summaries. Focused frontend: **140 passed** across billing reader/display, panel, paged ledger and full History detail regressions. TypeScript and production build passed. Changed-source ESLint: no errors, two existing page hook warnings. Source fixtures/fake cursors only; importer was never executed. `git diff --check` clean at review.

Old PR head `77e4e1f4` protected Backend tests failed on an unrelated Motive test: its substring assertion found `9999` inside a generated UUID, rather than stored provider speed. Job `117789230599`, run `39163987124`. No CI jobs were cancelled or changed. A new exact-head protected run remains required; this failure is not waived.

## Release blockers and exclusions

The Web-only `ETS_IMPORTED_BILLING_SHOPS` binding is prepared privately from existing verified collector configuration but **not applied**. Default/missing mapping safely holds source status. It changes presentation trust only, not collection or outcome delivery. Collector configuration and active watch exclusions remain untouched.

Local runtime preflight found another task's frontend at port 5173 and no aligned DB139 backend/configuration. No service was replaced or restarted. Browser inventory still reports **Local browser use is disabled in Work settings**. No signed-in Light/Night desktop/mobile or touch acceptance is claimed, locally or in production.

**Independent GO excludes `_sync_payments_for_existing_invoices`, the unchanged existing-payment writer. It does not authorize importer/collector execution or claim global sync safety.** Guarding that path requires separate review before importer rollout. No source financial apply or QuickBooks reconciliation is approved by this item.

Current-head CI found one legacy presentation test with a pre-extension value-summary fixture. The native fixture now explicitly returns `has_imported_orders=false`; its two-total assertion remains intact. Mixed/missing-metadata regressions continue to require aggregate suppression. No production behavior or CI configuration was relaxed. Corrected fixture file: **16 passed**; full local critical frontend gate: **210 passed**. Browser permission remained disabled after a fresh tool connection despite the operator reporting enabled.

Remaining: final exact-head protected CI, approved Web binding/release configuration, aligned runtime and signed-in browser acceptance, merge/deploy identity and health, fixed-cohort financial/source-capture retention, and production Light/Night desktop/mobile checks. Roll back application code/binding on false paid status, tenant leakage, source identity failure or native-action exposure. Preserve financial/source records during rollback. DB-135 native receivable reconciliation remains a separate outcome.

## Reader-only release correction

Live effective ETS manifest confirms `/railway.ets-sync.json` and collector watch patterns including `backend/scripts/easytruck_sync/**`; the service-level empty watch list is not the effective deployed file configuration. Architecture therefore approved splitting all importer changes and their dedicated test out of #576. Exact proposed changes remain on the pushed held branch above. The existing-payment sync must receive a guard and independent review before any importer rollout. The reader/API/UI and native-action protections remain in #576. No collector watched path may differ from released main. Capture collector deployment/image/configuration before merge and prove retention afterward.

Driver release #577 passed all six checks and merged as `1cb16a7f`; coordinator acceptance/explicit slot handback precedes this reader release. PR576 previously passed all six on `06086f72`; integrated reader-only head requires fresh protected CI. Browser inventory and direct in-app browser access both still reject with the Work-settings disabled error. No browser acceptance is claimed.

## Released-main integration and selected-shop correction

Driver coordinator accepted #577 and explicitly handed back the slot. Integrated exact released main `1cb16a7f` in `6795a85d`, preserving both board histories and the coordinator's task-owned two-document acceptance patch. No reviewed driver application file changes are introduced by #576. One Alembic head remains `181_sms_maintenance_merge`; #576 adds no migration. Current local frontend5173 still serves the separate checkpoint worktree;8000 is unbound and DB139 has no approved backend environment. No local service/configuration was replaced.

Independent integration review found pre-existing selected-shop omissions in two fallback read paths reached by this feature. Legacy invoice list/count now join invoice/order tenant identity and scope customer reads to the selected tenant and customer; completed payment summaries also require that tenant. Repair-order source/projection filters now require the same selected tenant/customer. Missing selected identity returns empty results. Six actual SQLite regressions cover projection-gap fallback, cross-tenant invoice/order linkage, a newer foreign-tenant payment, source/projection pages and counts, and missing identity. All changes are read-side filters; no production records were created or rewritten.

Integrated frontend:210 critical regressions and65 additional reader/ledger/page regressions passed; production build passed. Focused backend before isolation correction:97 passed. New isolation tests:6 passed; nearby suite85 passed/1 skipped (skip provenance not established), plus7 status-count tests passed. Final combined backend: **103 passed** in9.11s. Independent Security/QA re-review gave source/test GO for reader-only integration and the selected-tenant corrections; reviewer inspected source/assertions without implementing or claiming browser acceptance. Final source diff has zero ETS collector watched paths.
