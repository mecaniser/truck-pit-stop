# DB-139 compact ETS billing summary

Owner: Frontend & UX. Fast UI lane; existing read-only billing contract. Branch `codex/ets-billing-compact` from released main `aa9fbe24`.

The footer keeps ETS invoice total and supported paid/partial/unpaid/unverified status visible. An info-button popover holds source paid and remaining amounts, invoice availability/no-new-invoice explanation, source/QuickBooks disclaimer, observation time and review note. The shared component also covers full History detail. Failure alerts remain visible. Native invoice/payment controls and every amount/status calculation are unchanged.

Focused checks:100 tests passed across importedBilling, PriceBuilderPanel pending feedback and RepairOrdersPage imported billing. Tests cover default collapsed details, status variants and missing values, keyboard activation, Escape/focus restoration and outside dismissal, full History and native-action exclusion. Changed-source ESLint passed with no output; TypeScript and production build passed. No backend, migration, provider, collector or financial write change.

Local runtime 2026-10-19: dedicated checkout/frontend PID27914 serves localhost5173 with branch and baseline SHA stamps. No5173/8000 listener existed at preflight; no shared server was stopped. No approved backend environment exists in this checkout, so no backend/database configuration was invented or copied. A temporary synthetic HTML entry renders the actual changed component and existing CSS, with no API requests. Actual browser checks at desktop1280 and390px mobile verify collapsed summary, opening above footer, readable content, Enter/Escape/outside dismissal and no horizontal overflow (390px document/viewport). This is component browser evidence, **not** full signed-in local-app acceptance. Temporary preview files are excluded from the commit. Production browser authorization is available again; actual signed-in deployed journey remains a release gate.

Protected CI, PR/merge and deployment evidence remain pending. No financial records or invoices were created or changed. The importer branch stays on hold; DB-135 review remains separate.
