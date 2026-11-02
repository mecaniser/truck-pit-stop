# DB-149 tenant invoice identity

Owner: Frontend & UX. Branch: codex/tenant-invoice-identity.

Customer references use the exact invoice tenant prefix plus its established source invoice number (Truck Pit Stop: TPS-1687). Canonical keys, native allocator, UUIDs, accounting references, provider requests, amounts and receipts remain unchanged. No migration or backfill.

Additive source_collection.display_invoice_number covers reviewed collections and linked history; absent metadata hides reserved internal references. Ordinary invoices preserve existing references. Customer subjects, PDFs, download names, headers, shares and Zelle memo displays use the same identity. Memo strings remain presentation only; attempt requests contain invoice UUID, amount, version and tender, not the display alias.

PDF customer company uses original_bill_to_name only for a hash-validated owner_same_legal_entity authorization with affirmative same-entity attestation after exact invoice/tenant/target binding. No record-name mutation or suffix stripping. Escaped legal names remain intact.

Customer copy omits source-transfer/platform implementation explanations. Shop logo errors/missing logos show the shop name. Customer errors use actionable wording. Staff reconciliation details remain available.

## Verification

- Backend focused identity, source-collection and PDF/review tests: 62 passed. Includes another tenant prefix, leading zero, invalid source/header content, ordinary compatibility, exact linked history, unlinked imports, foreign tenant and tampered authorization.
- Frontend focused identity/branding/dashboard/history/payment tests: 63 passed.
- Production frontend build passed. Changed-source lint passed across14 files.
- Browser fixture at http://127.0.0.1:5173/invoice-preview.html serves this worktree's actual components with synthetic data and API origin loopback port9; writes rejected. Guest title/header TPS-1687, full268.44 and partial100.00 showing remaining168.44; dashboard one268.44 invoice/TPS-1687 and no internal identifier or duplicated subtitle.390px layout no horizontal overflow. Inspected local screenshots in output/.
- Runtime receipt 2026-11-02: branch codex/tenant-invoice-identity base7a76258d, dirty owned changes; frontend5173 PID20178 cwd/private/tmp/db149-tenant-invoice-identity/frontend. Unrelated Docker8000 preserved. Backend configuration absent; no local full-stack claim. Aligned and browser-verified frontend fixture only.
- Independent Architecture contract GO. Independent QA/Security GO:62 backend and64 frontend tests across the reviewer-selected scope; no blockers.
- PR756 opened at6d784630; protected CI, merge and deployed acceptance pending. No payment submitted or financial records changed.
