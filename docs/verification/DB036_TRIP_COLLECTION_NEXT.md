# DB-036 next collection architecture

Status: researched proposal, not implemented or account-enabled. Current authorized repair retains dashboard-derived imports and their tenant, membership, reviewed-placeholder, immutable-row, and receipt checks.

## Preferred provider transport

Motive documents `GET /v1/driving_periods`, with stable driving-period IDs, vehicle IDs, start/end times, origin/destination, distance, status, date-range filters, pagination, `updated_after`, and an `X-Time-Zone` header. The documented OAuth read scope is `driving_periods.read`. This is a better candidate for the dashboard trip data than the IFTA endpoint, which represents jurisdiction/tax reports. Equivalence to the dashboard's trip segment semantics is not yet proven, and current account entitlement/credential availability has not been verified. No credentials, OAuth permissions, webhook settings or production API requests were changed for this research.

Official sources checked 2026-10-26:
- https://developer-docs.gomotive.com/reference/fetch-a-list-of-the-vehicles-driving-periods
- https://developer-docs.gomotive.com/docs/oauth-scopes
- https://developer-docs.gomotive.com/reference/fetch-a-list-of-companys-ifta-trip-reports

## Proposed acceptance before migration

Verify approved read access, company binding and source semantics on representative VIN and reviewed-placeholder vehicles. Compare complete, interrupted, ongoing, edited, cross-midnight and DST examples against accepted dashboard receipts. Do not equate IFTA trips or reconstructed GPS travel with dashboard segments. Preserve the current importer identity and immutable-row protection until an explicit correction/versioning contract is reviewed.

Use durable tenant-scoped date jobs for historical gaps and a separate incremental watermark for provider updates. Page to exhaustion before advancing either cursor; persist the page/source receipt before import, and reconcile ambiguous commits before issuing another write. Use stable provider IDs plus current authorized vehicle bindings for duplicate protection. Keep a small overlapping date window to catch late completions and periodic full-day reconciliation to catch missing updates. A failed job remains pending or rejected with evidence; other safe dates may proceed. Authentication, identity contradictions and uncertain commits remain stop conditions.

Bound each invocation by time and page count. Retry only recognized transient transport failures with bounded backoff; honor provider rate limits and retain the same logical job identity. Use webhooks, if separately enabled and verified, as wake-up signals rather than the sole completeness guarantee. Monitor oldest unresolved eligible date, time since last complete receipt, rejected-day count and source/readback mismatch; scheduler status alone is insufficient.

Until API access and parity are established, retain one browser login and directory read per bounded batch, exact per-day receipts, fresh company/identity checks, and independent source/readback acceptance. Browser failures can still occur; durable progress and explicit gaps prevent those failures from silently losing days.

## Production readiness checked 2026-10-26

Independent read-only inspection of the already running Web service confirms the production Motive OAuth connector is disabled; client ID, client secret, redirect and active encryption key are absent, and the target fleet company has no OAuth connection. No provider request, refresh, login or mutation was performed. Evidence: `/tmp/db036-api-readiness-result.jsonl`. API adoption therefore requires approved connector configuration and a scoped company connection before parity testing; current vendor approval status remains unverified. This later readback supersedes only the earlier statement that production configuration was unverified.
