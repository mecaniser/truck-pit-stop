# DB-139 — source invoice verification navigation

Owner: Frontend & UX. Standard read-only contract extension. Architecture review
GO2026-11-01; independent final QA required. No migration or financial writer.

Existing staff GET /repair-orders/{id}/imported-billing and list imported_billing
summary gain optional source_invoice_url (string|null, default null). Existing
permissions, tenant scope, native409/deleted/foreign404, amounts, payment states,
review reasons and reconciliation semantics stay unchanged. Old clients ignore
this optional field; new clients hide links for absent/unsafe URLs.

Only _source_summary may generate a URL after existing digest, source, tenant,
shop, order/service, invoice identity and complete-manifest checks. Fixed origin
https://easytruck.shop, path /{trusted_shop}/services/{source_service}/invoice.
Shop must match [A-Za-z0-9_-]{1,160}; service ASCII digits1..160, preserving leading
zeros. URL validation failure hides navigation without introducing a payment
hold or changing any amount/status. No URL is inferred from display order names.
Shared siblings inherit the canonical invoice-owner source route. Identity-held
siblings receive no invoice URL; a supported direct owner retains its own context.

UI: Verify in ETS in expanded billing-warning Details and alongside the footer
warning. No interactive anchor inside the read-only tooltip. New tab,
noopener noreferrer, visible keyboard focus and accessible new-tab indication.
Link activation must not open the internal repair-order workspace. HTTPS fixed
origin/path allowlist is repeated in the UI; reject credentials, alternative
origins, traversal, encoding, query and fragment. Hide source link during failed
footer loads and healthy compact summaries. No provider API is called by rendering.

The ETS collector verifies this route in 05_scrape_invoices.js:44-45. Source
verification uses the previous platform's existing authenticated session; the
link neither bypasses ETS authentication nor grants additional access.
