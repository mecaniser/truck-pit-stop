# Mechanic Timer Tracker

Execution tracker for attendance, break mode, timer orchestration, hold/resume, and board UX.

## V1.1 — Attendance & Break Mode

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

## V1.2 — Hold/Resume & RO Time Tracking

| Task ID | Scope | Owner | Status | Dependency | Started | Finished |
|---|---|---|---|---|---|---|
| MT-11 | Hold/resume RO: `hold_reason`, `held_at` fields on repair_order; hold/resume endpoints auto-stop/start timer with `hold`/`resume_from_hold` stop reasons | TBC | done | MT-05 | 2026-02-14 | 2026-02-14 |
| MT-12 | WebSocket: broadcast `hold_reason` + `held_at` in `repair_order_update`; frontend WS handler patches RO list, detail, and invalidates dashboard | TBC | done | MT-11 | 2026-02-14 | 2026-02-14 |
| MT-13 | Manager dashboard: `RecentOrder` schema + `OrderCard` show "on hold" badge (orange) + reason; hide elapsed timer for held ROs | TBC | done | MT-12 | 2026-02-14 | 2026-02-14 |
| MT-14 | RO list page: `on_hold` status filter, `resolveOrderDisplayStatus` helper, "On Hold" badge in table/card/detail header | TBC | done | MT-12 | 2026-02-14 | 2026-02-14 |
| MT-15 | Mechanic board + detail: `held_orders` array in `compute_next_action_recommendation`; `HeldOrderSummary` schema; board cards and detail page display held orders with reasons | TBC | done | MT-11 | 2026-02-14 | 2026-02-14 |
| MT-16 | `ro_today_tracked_minutes`: backend `_compute_ro_today_tracked_minutes_map` for mechanic job list/detail; mechanic portal `LiveTimer` shows total RO time today | TBC | done | MT-05 | 2026-02-14 | 2026-02-14 |
| MT-17 | Unit tests: `TIMER_STOP_REASONS` includes hold/resume_from_hold; `compute_next_action_recommendation` returns `held_orders` metadata | TBC | done | MT-11, MT-15 | 2026-02-14 | 2026-02-14 |

## V1.3 — Board UX Redesign

| Task ID | Scope | Owner | Status | Dependency | Started | Finished |
|---|---|---|---|---|---|---|
| MT-18 | Navigation: "Time Board" button on My Garage > Mechanics page linking to `/dashboard/mechanics` | TBC | done | MT-09 | 2026-02-14 | 2026-02-14 |
| MT-19 | Tabbed detail page: split `MechanicBoardDetailPage` into Overview (default) and Admin Controls tabs | TBC | done | MT-09 | 2026-02-14 | 2026-02-14 |
| MT-20 | Today Sessions: computed duration badge per session row; time-only display (toLocaleTimeString) | TBC | done | MT-19 | 2026-02-14 | 2026-02-14 |
| MT-21 | Session summary footer: Total RO / Misc / Break / Idle aggregation below session list | TBC | done | MT-20 | 2026-02-14 | 2026-02-14 |

## Notes
- Status vocabulary: `todo`, `in_progress`, `blocked`, `done`.
- Backfill policy remains disabled by design.
- Required manager reason is enforced for manager attendance/break actions.
- `hold` and `resume_from_hold` are valid `TIMER_STOP_REASONS` — timers auto-stop on hold and can auto-start on resume.
