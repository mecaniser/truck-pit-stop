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

## V1.4 — Dynamic Core Target, Clock-In Cutoff & RO Time Stamping

| Task ID | Scope | Owner | Status | Dependency | Started | Finished |
|---|---|---|---|---|---|---|
| MT-22 | Migration 036: `minimum_clock_in_remaining_minutes` (default 60) on `tenants` table | TBC | done | — | 2026-02-14 | 2026-02-14 |
| MT-23 | Migration 037: `estimated_labor_minutes`, `actual_tracked_minutes`, `total_hold_minutes`, `assigned_at`, `acknowledged_at` on `repair_orders` | TBC | done | — | 2026-02-14 | 2026-02-14 |
| MT-24 | Tenant model: add `minimum_clock_in_remaining_minutes` column | TBC | done | MT-22 | 2026-02-14 | 2026-02-14 |
| MT-25 | RepairOrder model: add 5 new fields (estimated/actual/hold minutes + transition timestamps) | TBC | done | MT-23 | 2026-02-14 | 2026-02-14 |
| MT-26 | Dynamic core target: `clock_in` computes `min(full_core, remaining_shift)` and snapshots adjusted value | TBC | done | MT-24 | 2026-02-14 | 2026-02-14 |
| MT-27 | Clock-in cutoff: reject clock-in when remaining shift < tenant cutoff (managers bypass) | TBC | done | MT-24, MT-26 | 2026-02-14 | 2026-02-14 |
| MT-28 | `compute_day_summary`: prefer attendance session `snapshot_core_target_minutes` over full core target | TBC | done | MT-26 | 2026-02-14 | 2026-02-14 |
| MT-29 | Auto-populate `estimated_labor_minutes` from `selected_services.duration_minutes` on RO update | TBC | done | MT-25 | 2026-02-14 | 2026-02-14 |
| MT-30 | Stamp `actual_tracked_minutes` + `total_hold_minutes` at `complete_work` endpoint | TBC | done | MT-25 | 2026-02-14 | 2026-02-14 |
| MT-31 | Set `assigned_at` in `assign_mechanic`, `acknowledged_at` in `acknowledge_job` endpoints | TBC | done | MT-25 | 2026-02-14 | 2026-02-14 |
| MT-32 | Frontend: add new fields to `RepairOrder` TypeScript interface | TBC | done | MT-25 | 2026-02-14 | 2026-02-14 |
| MT-33 | Frontend: Time Tracking section in RO detail panel (Est / Actual / Non-work + transition timeline) | TBC | done | MT-32 | 2026-02-14 | 2026-02-14 |
| MT-34 | Backend schema: add new fields to `RepairOrderResponse` Pydantic model | TBC | done | MT-25 | 2026-02-14 | 2026-02-14 |

## V1.5 — Bug Fixes & Mobile-First UX

| Task ID | Scope | Owner | Status | Dependency | Started | Finished |
|---|---|---|---|---|---|---|
| MT-35 | Single attendance session per day: `clock_in` reopens the most recent completed session instead of creating duplicates | TBC | done | MT-26 | 2026-02-14 | 2026-02-14 |
| MT-36 | `compute_day_summary`: filter attendance sessions strictly to current day before resolving `snapshot_core_target_minutes` | TBC | done | MT-28 | 2026-02-14 | 2026-02-14 |
| MT-37 | Prevent misc timer reset: `start_session` raises error when starting an already-active identical job | TBC | done | MT-05 | 2026-02-14 | 2026-02-14 |
| MT-38 | Recommendation engine: handle active misc session explicitly so `start_misc` is not suggested when misc is running | TBC | done | MT-37 | 2026-02-14 | 2026-02-14 |
| MT-39 | Hide "Start Misc" sticky bar when misc timer is already active (`isActiveMisc` guard) | TBC | done | MT-38 | 2026-02-14 | 2026-02-14 |
| MT-40 | Collapsed timer panel: tappable tile expands panel (removed separate "Show/Hide Timer" link) | TBC | done | MT-08 | 2026-02-14 | 2026-02-14 |
| MT-41 | Collapsed timer tile: two-row layout — status badges top, prominent `text-3xl` timer below | TBC | done | MT-40 | 2026-02-14 | 2026-02-14 |
| MT-42 | Collapsed panel: quick action buttons (Start Misc, Break, End Break) below tap-to-expand area | TBC | done | MT-40 | 2026-02-14 | 2026-02-14 |
| MT-43 | Mobile-first: `touch-manipulation` on Container (eliminates 300ms iOS tap delay) | TBC | done | — | 2026-02-14 | 2026-02-14 |
| MT-44 | Mobile-first: `safe-area-inset-bottom` on Container + bottom nav for notched phones | TBC | done | — | 2026-02-14 | 2026-02-14 |
| MT-45 | Mobile-first: bottom nav targets enlarged to `min-h-[48px] min-w-[64px]`, icons `w-7 h-7` | TBC | done | — | 2026-02-14 | 2026-02-14 |
| MT-46 | Mobile-first: all buttons upgraded to `py-3`–`py-5` with `active:` states replacing `hover:` | TBC | done | — | 2026-02-14 | 2026-02-14 |
| MT-47 | Mobile-first: misc category pills, hold reason chips, camera button enlarged to 44px+ targets | TBC | done | — | 2026-02-14 | 2026-02-14 |
| MT-48 | Mobile-first: header points badge & clock-out icon enlarged; back buttons `p-3` | TBC | done | — | 2026-02-14 | 2026-02-14 |
| MT-49 | Mobile-first: clock-in button upgraded to `py-5 text-xl font-bold rounded-2xl` with shadow | TBC | done | — | 2026-02-14 | 2026-02-14 |
| MT-50 | Mobile-first: clock-out modal buttons enlarged to `py-3.5 text-base rounded-xl` | TBC | done | — | 2026-02-14 | 2026-02-14 |
| MT-51 | Auto-hold previous RO when switching RO→RO: `start_session` sets `hold_reason=switched_to_other_ro` on previous RO | TBC | done | MT-11 | 2026-02-14 | 2026-02-14 |
| MT-52 | WebSocket broadcast for auto-held RO state change | TBC | done | MT-51 | 2026-02-14 | 2026-02-14 |
| MT-53 | Frontend: `switched_to_other_ro` hold reason label in all hold reason displays | TBC | done | MT-51 | 2026-02-14 | 2026-02-14 |

## Notes
- Status vocabulary: `todo`, `in_progress`, `blocked`, `done`.
- Backfill policy remains disabled by design.
- Required manager reason is enforced for manager attendance/break actions.
- `hold` and `resume_from_hold` are valid `TIMER_STOP_REASONS` — timers auto-stop on hold and can auto-start on resume.
- Dynamic core target: late clock-in adjusts core hours to remaining shift time. Full core target only applies when mechanic clocks in with enough shift remaining.
- Clock-in cutoff is configurable per tenant (`minimum_clock_in_remaining_minutes`, default 60). Managers can bypass.
- Single attendance session per day enforced: re-clock-in reopens the most recent ended session rather than creating a new row.
- Mechanic portal is mobile-only: all touch targets ≥ 44px, `touch-manipulation` enabled, `safe-area-inset-bottom` respected, `active:` states used instead of `hover:`.
- Auto-hold on RO switch: when mechanic switches from one in-progress RO to another, the previous RO is automatically placed on hold with reason `switched_to_other_ro`.
