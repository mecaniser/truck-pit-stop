# DB-141 revenue average contract

Architecture & API Contracts record, 2026-10-19. One sequential implementation owner: Backend & Integrations.

- Request: existing authenticated `GET /reports/dashboard?range=<preset>` or `range=custom&from_date=YYYY-MM-DD&to_date=YYYY-MM-DD`. Validation and errors remain unchanged.
- Response: existing `revenue.value` remains the selected range's cash-basis net revenue. `revenue.trend` keeps `{label, value}` points but now uses daily buckets for week/month presets, weekly buckets for quarter presets, and monthly buckets for year presets. Custom ranges use days for up to 31 inclusive days, weeks for 32–120 days, and months above 120 days. Add `revenue_interval: "day" | "week" | "month"` so the UI labels the average precisely. Other metric trends remain weekly.
- Average: arithmetic mean of every displayed revenue bucket, including zero buckets and partial first/last buckets. Empty trend has no line. The mean is a presentation calculation; it does not change `revenue.value` or financial records.
- Boundary: existing owner/admin and tenant checks, payment tenant filter, completed-payment cash basis, tax exclusion, shop-local dates and exclusive UTC end remain authoritative. No writes, idempotency, concurrency, migration, or new permissions.
- Compatibility: adding `revenue_interval` is additive. An older response without it remains interpretable as weekly by the new UI; the backend must deploy before relying on daily/monthly bars. Fixture tests cover presets, custom thresholds, empty/zero buckets, tenant-local dates, and the mean-line label/value.
