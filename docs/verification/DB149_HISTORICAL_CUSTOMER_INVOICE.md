# DB149 historical customer invoice guidance — November 1, 2026

Owner: Frontend & UX. Existing-contract Fast UI correction, branch `codex/historical-invoice-readonly` from `4645ea6a`.

## Reproduction and correction

The authorized archived Easy Truck Shop invoice has readable invoice detail, payment summary and PDF, while the payment-action contract intentionally rejects archived repair orders. Known imported invoices cannot use DieselBridge payment actions regardless of archive status. The customer page nevertheless queried settlement, archived repair-order details and provider availability, then showed the resulting payment-control404 as if the invoice could not be found.

Use existing `InvoiceDetailResponse.source` to recognize `easy_truck_shop_import`. Keep the real invoice summary, PDF and review link. Show a historical read-only/contact-shop explanation. Do not request settlement, allocations, archived order details, Zelle destination or card-provider availability; no online payment controls. Charge breakdown uses the available invoice subtotal rather than inventing labor/parts from unavailable archived details. An older response missing payment_summary labels its amount as recorded invoice total, not a verified balance. Native/null/unknown sources retain their original settlement error handling.

No backend, auth, tenant, source-ownership, payment, financial record or archive contract changed. No provider call, restored repair order, payment attempt or message send.

## Owner checks

- Historical real-hook regression7/7: paid/unpaid/cancelled, unknown balance, older response without summary, and native/null-source404. Imported cases assert invoice-detail is the only API request and no mutation occurred; summary/PDF/review remain visible.
- Existing cash5/5 and shared payment-summary7/7: total19/19 focused assertions pass.
- TypeScript noEmit passes; changed-source ESLint0 errors; Vite production build passes; diff check clean.
- Fictional actual-component preview available at `http://127.0.0.1:4181/?status=sent` (paid/cancelled variants), axios adapter rejects all endpoints except fictional invoice detail. Parent CUA acceptance passes actual-component desktop1280/mobile390: confirmed0, balance654.89, historical read-only/contact-shop guidance, PDF retained, no payment/error UI and no horizontal overflow. Screenshots: local `output/playwright/historical-guidance-desktop.png` and `historical-guidance-phone.png`. Preview uses no backend/database/provider and owned4181 server stopped after verification.

## Runtime receipt and release limits

Nov1 intended worktree `/Users/sergio_m1_promax/.codex/worktrees/invoice-review-link/truck-pit-stop`, branch above, base4645ea6a with task-local changes and pre-existing output/tmp preserved. Local full app alignment is **blocked**: approved backend/.env absent. Frontend5173 PID3456 belongs to my-shop-nav-stability worktree; Docker8000 PID3415 binds machined-sidebar backend. Existing services/settings preserved; default frontend proxy remains127.0.0.1:8000. No migration or database operation. Standalone4181 is only a fictional component preview, not an aligned full-stack application.

Configured/signed-in runtime acceptance, protected CI, merge and deployment are not claimed here; parent coordinates release authority and live customer verification. This fix remains reviewable, not Done.
