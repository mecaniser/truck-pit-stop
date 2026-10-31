# DB-149 Invoice review links

Owner: Backend & Integrations. Architecture contract recorded before implementation.

- Add nullable `tenants.review_url` (2048 chars), no default/backfill. Existing shops keep current behavior until configured.
- Existing owner/admin GET/PUT `/admin/garage-profile` includes optional `review_url`. PUT omission preserves it for older clients; null/blank clears it. Validate HTTPS, hostname, no credentials/control/whitespace characters; never fetch it.
- Authorized invoice detail and token-resolved invoice responses expose optional `review_url` selected from the invoice tenant only, after existing access checks. Internal invoices return null. No list/projection change.
- PDF, issued email, paid email and reminder email use the same tenant/invoice resolver. Customer pages render the server value only (never query string). Missing/invalid config renders no invitation. All payment statuses use neutral copy without rating incentives or screening.
- New links escape HTML/PDF markup; browser links open a new tab with noopener/noreferrer. Printed PDF exposes readable URL. Pricing, immutable line snapshots, payment state, outbox, token rules and recipients are unchanged; no resends or live writes in QA.
- Verify schema upgrade/downgrade, validation and clear/omit behavior, tenant isolation/internal exclusion, real PDF hyperlink/text and multipage layout, email integration, both page layouts at desktop/390px. Independent QA/security after owner checks. Release pending separate authority.

## Shop activation after authorized release

The product owner supplied Truck Pit Stop's review URL on October 31, 2026:
`https://g.page/r/CXOAsgPjQkHvEAE/review`. After deployment/migration, save it through
that shop's existing Settings > Shop Profile > Review link, verify read-back, and
check one existing invoice page/PDF without changing its financial state or sending
mail. This is tenant configuration, not a platform-wide default. Other shops supply
their own links. Existing issued financial snapshots remain unchanged. Already-sent
email bodies and downloaded PDFs are not rewritten or resent.
