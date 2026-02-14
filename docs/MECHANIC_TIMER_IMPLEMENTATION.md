# Mechanic Timer V1.1 Implementation

## Overview
Mechanic Timer V1.1 adds explicit attendance (`clock in/out`) and break sessions on top of session-based timer tracking.

Goals:
- Preserve repair-order and misc timer behavior.
- Make daily attendance state explicit.
- Track flex usage (late, break, idle, early leave) without hard blocking.
- Keep owner/admin and mechanic workflows separated.

## Lifecycle Architecture

```text
Clock In -> Attendance Active

Attendance Active + Start Misc/RO -> Timer Active
Timer Active + Start RO/Misc -> auto switch prior timer
Timer Active + Start Break -> timer auto-stops (break_start)
Break Active + End Break -> idle state

Clock Out -> attendance ends
Clock Out side effects:
- auto-stop active timer (clock_out)
- auto-end active break (clock_out)

Midnight maintenance (tenant local):
- auto-stop active timer
- auto-end active break
- auto-clock-out active attendance
```

## Data Model

### `mechanic_attendance_sessions`
- One active attendance per mechanic max (partial unique index).
- Stores snapshot fields used for stable day calculations:
  - timezone
  - core target minutes
  - shift start/end

### `mechanic_break_sessions`
- One active break per mechanic max (partial unique index).
- Linked to parent attendance session.

### `mechanic_attendance_audit`
- Immutable audit rows for clock in/out and break start/end.
- Includes manager reason where required.

## API Contracts

## Mechanic Self
- `POST /mechanics/me/attendance/clock-in`
- `POST /mechanics/me/attendance/clock-out`
- `POST /mechanics/me/break/start`
- `POST /mechanics/me/break/end`

## Manager
- `POST /dashboard/mechanics/{mechanic_id}/attendance/clock-in`
- `POST /dashboard/mechanics/{mechanic_id}/attendance/clock-out`
- `POST /dashboard/mechanics/{mechanic_id}/break/start`
- `POST /dashboard/mechanics/{mechanic_id}/break/end`

Manager endpoints require `manager_reason`.

### Sample Requests and Responses

Clock in (mechanic self):

```http
POST /api/v1/mechanics/me/attendance/clock-in
Content-Type: application/json

{
  "note": "Started morning shift"
}
```

```json
{
  "success": true,
  "attendance_session_id": "c5dc5af0-4988-4b75-b4a8-5f15df6f1546",
  "message": "Clocked in"
}
```

Start misc timer with auto clock-in:

```http
POST /api/v1/mechanics/me/timer/start-misc
Content-Type: application/json

{
  "misc_category": "shop_cleanup",
  "note": "Opening bay prep"
}
```

```json
{
  "success": true,
  "session_id": "70d8fc31-fdf9-4736-a7de-1e00757dd8e4",
  "auto_clocked_in": true,
  "message": "Misc timer started"
}
```

Start break (manager):

```http
POST /api/v1/dashboard/mechanics/{mechanic_id}/break/start
Content-Type: application/json

{
  "manager_reason": "Assigned lunch rotation",
  "note": "Lunch break"
}
```

```json
{
  "success": true,
  "session_id": "4f1089d8-a913-45af-aad7-b02390018107",
  "break_session_id": "4f1089d8-a913-45af-aad7-b02390018107",
  "auto_stopped_timer_session_id": "5d9ea58f-7b9e-4ea9-8e88-644cc95b9b80",
  "message": "Break started"
}
```

Clock out (manager) with auto-close side effects:

```http
POST /api/v1/dashboard/mechanics/{mechanic_id}/attendance/clock-out
Content-Type: application/json

{
  "manager_reason": "Shift complete",
  "note": "Clocked out by supervisor"
}
```

```json
{
  "success": true,
  "session_id": "c5dc5af0-4988-4b75-b4a8-5f15df6f1546",
  "attendance_session_id": "c5dc5af0-4988-4b75-b4a8-5f15df6f1546",
  "auto_stopped_timer_session_id": "70d8fc31-fdf9-4736-a7de-1e00757dd8e4",
  "auto_ended_break_session_id": null,
  "message": "Mechanic clocked out"
}
```

## Extended Responses

`GET /mechanics/me/day-summary` and manager board responses now include:
- attendance state: `attendance_active`, `attendance_started_at`, `attendance_ended_at`
- break state: `break_active`, `break_started_at`
- time buckets: `attendance_minutes`, `break_minutes`, `idle_minutes`
- flex: `flex_budget_minutes`, `flex_used_minutes`, `flex_remaining_minutes`, `flex_overrun_minutes`
- gap metrics: `core_gap_minutes`, `late_arrival_minutes`, `early_leave_minutes`

Timer start responses include `auto_clocked_in` where applicable.

## Time Math

- Core target: fixed configured value (default 480 minutes).
- Tracked time: repair-order + misc timer session overlaps.
- Utilization: `min(tracked/core_target, 100%)`.
- Overtime: `max(tracked - core_target, 0)`.
- Flex budget: `(shift_duration - core_target)` clamped to 0.
- Flex used: `late + early + break + idle`.
- Break does not count as tracked utilization.

## V1.2 Focus UX Fields

`GET /mechanics/me/day-summary` and manager board payloads include additional computed fields for focus-mode UI:

- `core_countdown_elapsed_minutes = min(attendance_minutes, core_target_minutes)`
- `core_countdown_remaining_minutes = max(core_target_minutes - attendance_minutes, 0)`
- `tracked_vs_attendance_gap_minutes = max(attendance_minutes - tracked_minutes, 0)`
- `work_coverage_percent = (tracked_minutes / attendance_minutes) * 100` (or `null` when attendance is zero)

Manager board payloads also include recommendation metadata:

- `assigned_ready_orders_count`
- `untimed_in_progress_orders_count`
- `recommended_order_id`
- `recommended_order_number`
- `suggested_next_action` (`clock_in|end_break|continue_ro|stop_misc_pick_ro|start_assigned_ro|start_misc`)

Mechanic focus-mode behavior:

- Pre-clock-in: single morning `Clock In` card.
- Post-clock-in: prominent core countdown + quick picks + one primary timer toggle.
- Advanced metrics move to collapsed details.

## Idle Alerts

Idle alert eligibility:
- Mechanic is clocked in.
- Mechanic is not on break.
- Within shift window.
- No active timer.
- Core target not yet reached.

Threshold: 30 minutes.

Delivery:
- WebSocket `mechanic_idle_alert`.
- SMS to mechanic + owner/admin (best effort).

## Realtime Events

Added:
- `mechanic_attendance_update`
- `mechanic_break_update`

Retained:
- `mechanic_timer_update`
- `mechanic_idle_alert`

## Migration and Backfill

- No historical backfill.
- Existing untimed jobs remain untimed until resumed.
- Auto clock-in on first timer start prevents workflow blocking for missed manual clock-in.

## Migration Safety Checks

Pre-deploy checks:
- Ensure DB can apply revisions `032` then `033` in order.
- Confirm partial unique indexes exist for active timer, active attendance, and active break.
- Confirm all new columns on `tenants` and `users` are readable by API serializers.

Post-deploy checks:
- `POST /mechanics/me/attendance/clock-in` creates one active attendance row.
- `POST /mechanics/me/break/start` creates one active break row and auto-stops active timer.
- `POST /mechanics/me/attendance/clock-out` ends attendance and side-effect closes timer/break.

## Rollback Notes

- Application rollback can be done first while keeping data tables intact.
- If schema rollback is required, close active attendance/break sessions before downgrade.
- Downgrading from `033` drops attendance/break/audit tables; downgrade from `032` drops timer/workforce settings structures.
