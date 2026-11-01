# DB-139 shared ETS invoice display

Owner: Backend & Integrations. Architecture contract approved 2026-11-01.

Exact ETS numeric service/customer/optional operation number groups are resolved within one tenant. All candidate rows must be imported, active and share nonnull customer/vehicle identity. Conflicting candidates fail closed. Exactly one supported invoice across the full group; owner may be suffixed. Existing source evidence verification runs against that actual owner unchanged. Missing/stale/refund/identity/manifest evidence never becomes paid or debt by inference.

ImportedBillingResponse adds invoice_repair_order_id, invoice_repair_order_number and shared_invoice (default false). RepairOrderResponse adds optional imported_billing using the same schema. Existing imported_invoice_total_amount remains compatible. List uses bounded batched queries and the same resolver as detail, including off-page owner lookup. All amounts are canonical invoice context, not operation receivables. Shared groups are explicitly labeled; remaining balance and payment status are visible.

Authorization remains selected-tenant/staff/assigned-mechanic guarded by existing endpoints; foreign rows and payments cannot supply evidence. Errors remain unverified response with reasons, without leaking foreign identity. No migration, financial writes, importer execution, native collection permission or export/aggregate changes. GET is write-free and idempotent. Rollback application code only; no data repair required.

Acceptance: paid/partial/unpaid owner/sibling parity; suffix owner; pagination; tenant/customer/vehicle/native/deleted/malformed/ambiguous safeguards; missing/stale/refund holds; exact cents; write-free tests; native UI unchanged; desktop/mobile shared context; independent QA/Security and protected CI. Merge/deploy and production acceptance tracked separately.
