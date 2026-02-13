# Mechanic Timer V1.1 Operations Runbook

## Scope
Operational guidance for attendance/timer/break maintenance, alerting, and incident handling.

## Periodic Maintenance

Celery task:
- `process_mechanic_timer_maintenance`
- Schedule: every 5 minutes

Responsibilities:
1. Auto-stop timers that cross tenant-local midnight.
2. Auto-end breaks that cross tenant-local midnight.
3. Auto-clock-out attendance sessions that cross tenant-local midnight.
4. Evaluate idle alert streaks and emit one alert per streak.

## Midnight Boundary Rules

Boundary source: tenant timezone.

At first midnight boundary after session start:
- Timer stop reason: `auto_midnight`
- Break end source: `auto_midnight`
- Attendance end source: `auto_midnight`

## Alerting Channels

Idle alert channels:
- In-app WebSocket event (`mechanic_idle_alert`)
- SMS to mechanic + owner/admin

SMS behavior:
- Best effort only
- Timer/attendance actions must succeed even if SMS fails

## Troubleshooting

### Symptom: Mechanic appears stuck “clocked in” overnight
1. Verify Celery beat and worker are running.
2. Check maintenance task result payload for `closed_attendance` > 0.
3. Inspect `mechanic_attendance_sessions` for active rows with old `started_at`.
4. Trigger maintenance task manually if needed.

### Symptom: Idle alerts not firing
1. Confirm mechanic is clocked in.
2. Confirm mechanic is not on break.
3. Confirm no active timer exists.
4. Confirm shift window and core target settings.
5. Verify websocket connection and event processing.

### Symptom: Idle alerts firing during break
1. Confirm break session exists and is active.
2. Check break start/end API logs and audit rows.
3. Verify frontend reflects `break_active` from day-summary.

## Manual Recovery Patterns

- Manager clock-out API can safely close active attendance and stop timer/break side effects.
- Manager break-end API can clear stale break state.
- Session correction endpoints remain available for timer records.

## Validation Checklist After Deployment

1. Mechanic can clock in/out and start/end break.
2. First timer start auto clocks in when needed.
3. Clock out auto stops timer and ends break.
4. RO start/complete still start/stop timer correctly.
5. Day summary returns attendance/flex fields.
6. Team and detail boards render new state correctly.
7. Midnight maintenance closes all active entities.
8. Idle alerts appear in-app and via SMS.

## Rollback Notes

If rollback required:
1. Revert application deployment first.
2. Keep migration data intact unless full schema rollback is necessary.
3. If rolling back DB migration, ensure no active attendance/break references remain.
4. Communicate temporary loss of attendance/break controls to operators.
