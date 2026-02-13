# Mechanic Timer V1.1 Tracker

Execution tracker for attendance, break mode, timer orchestration, and documentation rollout.

| Task ID | Scope | Owner | Status | Dependency | PR Link | Test Evidence | Started | Finished |
|---|---|---|---|---|---|---|---|---|
| MT-00 | Create tracking + documentation skeleton | TBC | done | none | TBD | docs files created | 2026-02-13 | 2026-02-13 |
| MT-01 | DB migration: attendance/break/audit tables + indexes | TBC | done | MT-00 | TBD | migration review + build/tests | 2026-02-13 | 2026-02-13 |
| MT-02 | Service layer: clock in/out, break start/end, auto clock-in, flex math | TBC | done | MT-01 | TBD | unit tests + API smoke | 2026-02-13 | 2026-02-13 |
| MT-03 | Mechanic self APIs for attendance/break + day summary extension | TBC | done | MT-02 | TBD | endpoint tests/manual verification | 2026-02-13 | 2026-02-13 |
| MT-04 | Manager APIs for attendance/break controls with reason enforcement | TBC | done | MT-02 | TBD | endpoint tests/manual verification | 2026-02-13 | 2026-02-13 |
| MT-05 | Repair-order and misc timer integration with auto clock-in flag | TBC | done | MT-02 | TBD | start-work/start-misc behavior checks | 2026-02-13 | 2026-02-13 |
| MT-06 | Midnight maintenance: auto-close timer + break + attendance | TBC | done | MT-02 | TBD | Celery maintenance path checks | 2026-02-13 | 2026-02-13 |
| MT-07 | WebSocket events: attendance + break + idle in-app wiring | TBC | done | MT-03, MT-04 | TBD | UI cache invalidation/manual realtime checks | 2026-02-13 | 2026-02-13 |
| MT-08 | Mechanic portal UI: clock controls, break controls, flex warnings | TBC | done | MT-03, MT-07 | TBD | frontend build + manual page checks | 2026-02-13 | 2026-02-13 |
| MT-09 | Manager board UI: attendance/break state + quick controls | TBC | done | MT-04, MT-07 | TBD | frontend build + manual board checks | 2026-02-13 | 2026-02-13 |
| MT-10 | Documentation finalization + release notes sync | TBC | done | MT-00..MT-09 | TBD | docs review | 2026-02-13 | 2026-02-13 |

## Notes
- Status vocabulary: `todo`, `in_progress`, `blocked`, `done`.
- Backfill policy remains disabled by design.
- Required manager reason is enforced for manager attendance/break actions.
