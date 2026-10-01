# DB-036 telemetry copy cleanup

2026-10-01 — Frontend & UX, Fast UI. Base main fd4eb1eb (merged PR450).

Acceptance: cards/header say Updated with readable relative age; tooltips contain capture date/time only; remove source/basis/debug prose; remove Add reading from the truck details surface and remove the manual-entry fallback instruction from Pull from Motive. Stored provenance, backend import endpoints, retention, motion and service mileage remain unchanged.

Verification: 35 focused tests pass across FleetTelemetry, TruckTelemetry, TruckDetailHarden and PullMotiveReading. Changed-source ESLint and TypeScript/production build pass. Real TruckDetail/board synthetic preview inspected with CUA Playwright: Updated 2 minutes ago; tooltip Captured plus localized date/time only; no Add reading or manual textboxes in details; unconfigured pull returns connection-required notice. iPad 820x1180 has document width/scroll width 820, tooltip visible within viewport. Escape dismissal works.

Runtime receipt: branch codex/telemetry-time-labels, base fd4eb1eb, task-owned edits plus retained output directory. Controller dry-run refused dirty worktree; approved backend/.env absent and port8000 unbound. Frontend preview localhost5173 PID38630 served this worktree/frontend; source alignment corroborated by changed rendered text. Preview fixture handles API requests; no production proxy calls or data mutation. Authenticated full-stack local runtime remains blocked. Preview process stopped after checks. This is not production deployment evidence.

Provider approval and real API collection remain separate outstanding work. This change adds no collector and does not promise unattended browser refresh.
