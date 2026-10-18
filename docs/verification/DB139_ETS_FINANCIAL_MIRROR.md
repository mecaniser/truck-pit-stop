# DB-139 ETS financial mirror — verification boundary

2026-10-18. Owner: Backend & Integrations. Branch: `codex/db139-ets-financial-mirror`, based on released main `46f73e3d83cf157e8b66c0c9698fbe2a83476beb`.

## Narrow safety slice

The authenticated Shop repair-order read uses authoritative order and invoice source identities. An imported order displays one same-tenant, unique active source invoice total when available, and otherwise holds the amount as unavailable. Imported work lines and parts have no asserted billed breakdown. Native invoice creation, mutation, resend, settlement/payment, direct QuickBooks export/charge, and historical native invoice review reject ETS-owned records. No collector, source financial row, QuickBooks record or native receivable was changed.

Source review: Architecture GO for a draft safety PR only. Independent QA/Security initially found API, UI pricing and tenant join gaps; the owner fixed them. QA/Security then gave source-only GO for the narrow draft. Neither review approves the full ETS/QuickBooks mirror or production acceptance.

Focused checks: backend imported-source guards and nearby invoice/repair-order tests, **14 passed**; imported PriceBuilder regression, **1 passed**; full PriceBuilder file before final part fixture, **75 passed**; TypeScript and changed-source ESLint completed with no errors (two existing hook warnings); `git diff --check` clean. Local browser acceptance is unavailable in this checkout: ports 5173/8000 belong to the separate DB-135 worktree, and DB-139 has no aligned `.env`/backend venv. Do not claim this branch is visible in the running local browser.

## Still open

- Verify the exact ETS invoice and payment source records for the reviewed imported PM order; owner's `$150` statement and screenshots are leads, not settlement proof.
- Specify and implement a read-only, tenant-scoped ETS payment allocation mirror with QuickBooks corroboration, including unpaid, partial, paid, reversals and review holds.
- Run protected PR CI, merge/deploy, fixed-cohort retention, and signed-in Light/Night desktop/mobile production checks. No payment state may be inferred from `completed` alone.
