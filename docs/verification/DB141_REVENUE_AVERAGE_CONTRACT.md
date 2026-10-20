# DB-141 revenue average contract

Architecture & API Contracts record, 2026-10-19. One sequential implementation owner: Backend & Integrations.

- Request: existing authenticated `GET /reports/dashboard?range=<preset>` or `range=custom&from_date=YYYY-MM-DD&to_date=YYYY-MM-DD`. Validation and errors remain unchanged.
- Response: existing `revenue.value` remains the selected range's cash-basis net revenue. `revenue.trend` keeps `{label, value}` points but now uses daily buckets for week/month presets, weekly buckets for quarter presets, and monthly buckets for year presets. Custom ranges use days for up to 31 inclusive days, weeks for 32–120 days, and months above 120 days. Add `revenue_interval: "day" | "week" | "month"` so the UI labels the average precisely. Other metric trends remain weekly.
- Average: arithmetic mean of every displayed revenue bucket, including zero buckets and partial first/last buckets. Empty trend has no line. The mean is a presentation calculation; it does not change `revenue.value` or financial records.
- Boundary: existing owner/admin and tenant checks, payment tenant filter, completed-payment cash basis, tax exclusion, shop-local dates and exclusive UTC end remain authoritative. No writes, idempotency, concurrency, migration, or new permissions.
- Compatibility: adding `revenue_interval` is additive. An older response without it remains interpretable as weekly by the new UI; the backend must deploy before relying on daily/monthly bars. Fixture tests cover presets, custom thresholds, empty/zero buckets, tenant-local dates, and the mean-line label/value.


## Release accepted — 2026-10-19

All six checks passed in run `39308700891`, with no failed steps; full backend
3,917 passed / 314 skipped. Merge `7eb078e314e5c7826509ba9965aa089d2bf90007` has
the exact checked tree. Web `bb789d7d-af78-4546-b82a-049f86814fd4` and Worker
`36642022-fc83-4971-b889-60582ea7703a` deployed that revision; served SHA and
database/Redis readiness match. Signed-in production verifies September daily
30 buckets including five zero days, unchanged historical hero total, weekly
four buckets including partial boundaries and one zero bucket, and monthly
ten buckets. The 390px mobile all-zero year has twelve monthly buckets. Each
visible mean equals the normal authenticated API response sum/count, the trend
sum equals the hero, the dashed reference line is present and there is no
horizontal overflow. Screenshots and response comparisons are retained privately.
No financial record was changed for acceptance.
