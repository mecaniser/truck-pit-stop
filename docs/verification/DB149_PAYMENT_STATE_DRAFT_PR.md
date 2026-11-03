# DB-149 payment-state draft PR verification

2026-11-03. Draft publication is authorized; merge, deployment and GitHub PR approval are outside this step. Branch `codex/customer-payment-state-fix` is based directly on current main `7b56fe254e02b3bf9910ff356f3d08e1f4626b90` (#756/#757). Product commits `30590a39` and `615a15c5` are exact cherry-picks of independently reviewed `97016cee` and `977aabaf`.

## Result

Invoice-list summaries use current authorized invoice facts and bounded read-only settlement/payment evidence. Dashboard balances and selections use remaining principal in integer cents; missing/invalid/read-error balances are unavailable, not original total or zero. Paid guest/portal pages keep refund and unapplied-credit notices visible. Collection applied principal includes prior plus confirmed native exactly once and excludes pending/unknown tender. A failed fresh settlement read, including unavailable-feature responses after cached success, hides stale split controls until recovery; initial no-data legacy fallback remains.

Tenant-prefixed references/reviewed bill-to identity from #756 and single-Pay/informational-balance hierarchy from #757 are retained. No enrollment repair, unrelated test-infrastructure changes, migration, provider/request change, financial write or v2-manifest change is included.

## Independent review

Fresh independent complete source/security review passed on combined local integration `9b459d49`. Independent payment-only publication review then inspected this complete branch at `615a15c5071237e69f500033fb117592e6e70bd1`: every changed payment product/test file byte-matches that reviewed subset; enrollment and original test-repair paths explicitly match main. Local GO for draft publication only, no remaining material finding in payment diff. Local receipts: sibling `payment-security-gaps/PAYMENT_ONLY_DRAFT_PUBLICATION_REVIEW.md`, `FINAL_PAYMENT_INDEPENDENT_REVIEW.md`, and source-hash manifests. These are independent agent QA assessments, not GitHub PR approvals.

## Actual regression evidence

- Exact payment-only branch focused backend: **96 passed**, including list/projector/identity/v2 exports. No skips/failures. `payment-security-gaps/pr-exact-backend-focused.log`.
- Full frontend: **2,445 passed across 220 files**; production build/TypeScript/shared-controls and changed-source lint passed. Entire frontend git tree is identical to the tree actually tested, not merely its changed files. Exact tree IDs are retained in `pr-exact-tree-regression-receipt.json`; full logs `frontend-full-final.log`, `frontend-build-final.log`, `frontend-lint-final.log`.
- Stale-unavailable failing-first: eight actual guest/portal code variants fail on unpatched source (48 other matrix cases pass). Fixed canonical matrix56 passes; independent66 component cases additionally prove initial no-data fallback, recovery and null-tender behavior. Overlapping counts are not added.
- Exact payment-only branch full backend (Python3.12.13, explicit test settings/memory SQLite): **5,279 passed / 466 skipped / 4 failed**,236.97s. Not a green full suite. All four match the previously reproduced baseline: CallRail deep JSON404vs502 runtime expectation; denied local TLS socket bind; legacy source-collection revenue host/UTC-day fixture; denied `ps` process-cleanup assertion. All affected tests and corresponding product paths are unchanged from main. No new payment failure is present in this run. Log: `payment-security-gaps/pr-exact-backend-full.log`.
- Earlier combined QA run: **5,392 passed/371 skips/0 failures** in complete bounded file batches. It included separately reviewed test-only repairs excluded from this PR; it is **not** represented as an exact-this-branch green full suite. Those repairs and skip classifications remain separate artifacts.

## Isolated real-backend/browser acceptance

Prior disposable PostgreSQL/Redis service, explicit synthetic accounts, normal customer authentication, real API and desktop/mobile390 browser checks covered native unpaid100, partial60 with confirmed40/pending20, paid refund20/credit15, and unknown balances. Dashboard total160, selection60, one Pay per invoice, reload, blocked fresh-read/retry recovery and both paid notices were observed. Two reviewed fictional collection lineages with prior0/20 and native40 showed applied40/60 against original100/120 without duplication and retained source-admission holds. Current payment runtime product bytes are unchanged by this draft; the later unavailable-feature response cases are actual component checks, not a claimed new browser replay.

Full financial-row fingerprints before/after reads and recovery matched, with zero payments/attempts/ledger events. Fixture construction was separate and synthetic; trusted source-proof stub existed only while constructing fictional collection fixtures, not in the serving runtime. Native/collection source guards remained enabled. Runtime receipts: sibling `payment-reconcile-runtime` and `payment-reconcile-evidence`, including financial fingerprints, API snapshots, browser screenshots/AX, source and cleanup evidence.

## Known limits

No live charge/refund/provider operation, trusted ETS capture/source admission, production customer acceptance, protected CI, new proxy/TLS/SameSite enrollment or unbounded concurrency claim. First-time enrollment security fixes and tenant-local reporting tests remain on distinct local work, excluded here. Preexisting legacy `/dashboard/stats` host/session-date drift and portal browser-local overdue/DST handling remain separate; this payment PR does not claim all reporting dates fixed. Every gated skip is a coverage limit, not a pass.

Synthetic services and network have been removed; all receipts/checkouts and shared dependency installation preserved. No production changes, merge/deploy or PR approval were performed. Current main and branch mergeability must be refreshed before any later release.

## Publication blocker

The attempted exact branch push was rejected by automatic approval review before command execution: publishing an external branch creates an organizational commitment, and the reviewer did not accept delegation context as explicit trusted user authorization for this exact destination/change. No remote branch or PR was created, no alternate publication path was attempted, and nothing was merged/deployed. Prepared source/docs remain local. The next step requires explicit trusted user authorization to publish the payment-only draft to `mecaniser/truck-pit-stop`; that does not authorize merge/deployment or formal PR approval. Exact rejection is retained in sibling `payment-security-gaps/draft-publication-blocker.json`.

## Explicit publication authorization and retry

The user subsequently answered “yes” to the exact payment-only draft publication request for `mecaniser/truck-pit-stop`, expressly excluding merge/deployment. Current main was fetched again as7b56fe25; dry merge succeeds, no existing remote branch or PR was found. One exact previously denied push retry is authorized; if denied again it will stop without an alternate path. Product/test bytes remain615a15c5. Earlier rejection above is historical, not silently discarded.
