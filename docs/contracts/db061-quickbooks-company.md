# DB-061 connected QuickBooks company

Architecture & API Contracts: root. Backend & Integrations accountable.

Add GET `/quickbooks/company-identity`, using the same admin/permission guard
and current-user tenant connection lookup as GET `/quickbooks/status`.
No user-supplied tenant/realm. Existing status response remains unchanged.

Response: `{status: "available" | "not_connected" | "unavailable",
environment: "production" | "sandbox" | "unknown", realm_id: string|null,
company: {name: string|null, legal_name: string|null, address_lines: string[],
email: string|null, phone: string|null}|null}`.
Only expose allowlisted business identity, never raw CompanyInfo, tax IDs,
credentials or exception details. Strings bounded; missing values omitted in UI.
Name/address must come from Intuit, never the local shop profile.

GET CompanyInfo through existing accounting client, with realm from the current
tenant connection. The approved refresh correction reuses `_refresh_connection_if_needed`
before the read: existing row lock/recheck, encrypted token persistence and refresh
health updates are permitted for routine credential renewal. No reconnect, scope
changes or financial/provider business writes. Failed renewal returns unavailable
without attempting CompanyInfo; do not expose the helper's exception details. Missing
connection returns not_connected without provider request. Provider failure,
invalid payload or insufficient accounting scope returns unavailable, leaving
existing connection health/settings intact. Environment from existing accounting
environment configuration, not an inference from hostname or tenant name.

Frontend fetches only for connected/open QuickBooks panel. Query identity binds
user/tenant/realm/connection timestamp; no previous-data fallback across identity
changes. Five-minute stale time, no retry loop. Show company name, legal name if
different, company address, optional business email/phone, environment; existing
connection status and a quiet copyable company ID (user-approved disclosure correction).
Processing rates use one disclosure; connection management uses a separate button/footer.
Graceful loading
and unavailable state must not hide existing controls or claim disconnection.

Acceptance: company field mapping and filtered secret fields; missing/partial/
malformed/provider-failure cases; permission and second-tenant separation;
healthy-token no-write behavior, expired-token renewal before lookup, lock recheck
and failed-refresh no-lookup cases. Frontend loading, identity, missing/error/disconnected
and scoped cache tests; focused existing connection regression. Independent
QA/security; runtime acceptance before release completion. No bank balances,
payouts, contact edits, connection change or financial mutation in this item.
