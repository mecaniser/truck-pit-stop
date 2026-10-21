# Collector fixture preflight — 2026-10-21

Scope: local disposable archive of exact worker source
`576ce5a8a2c0bad7b8d33a236e6514bc448e8677`, actual Playwright Chromium,
synthetic DOM preload. **No database, no imports, no remote staging acceptance.**
No production files/services changed. Local browser fixture evidence is kept at
`/tmp/db-worker-fixture-check.vSKIhB`; it is temporary, not release evidence.

| Collector | Complete source | Actual process kill/restart |
|---|---|---|
| Location | 6 located vehicles | SIGKILL -9, restart 0; 1 saved task retained, 6 final |
| Health | 6 explicit empty fault captures | SIGKILL -9, restart 0; 1 saved task retained, 6 final |
| Drivers | 6 drivers; safety/fuel/coaching available, events explicitly empty | SIGKILL -9, restart 0; 1 saved task retained, 6 final |
| Trips | 18 rows across 3 daily windows | SIGKILL -9, restart 0; 1 saved task retained, 3 final |
| Fuel | 18 reports across 6 vehicles × 3 dates | SIGKILL -9, restart 0; 3 saved tasks retained, 18 final |

Each restart used the same source path and checkpoint. Assertions checked
unchanged checkpoint creation timestamp and exact saved task payload equality,
`collection_task_resumed` logs, completed final source, and event counts proving
saved payloads were not read again. Identity/directory rechecks remained active.
Browser child process groups were cleaned after the injected SIGKILL.

One fixture-only HTML charset defect was found and fixed before these results.
The production collector implementation was unchanged. The optional Python
first-verified-fleet kill hook was added afterward and has only syntax/static
validation here; its real DB proof belongs to the separate staging run.

Pending: remote ARM64 image build/runtime, all five actual worker supervisors,
committed receipts, three-fleet database journal recovery, source/read-model
parity, negative tenant/company/VIN cases, reboot recovery and 24-hour soak.
