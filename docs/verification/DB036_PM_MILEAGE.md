# DB-036 PM mileage realignment

2026-10-01. Owner: Backend & Integrations. Standard product lane; independent QA GO from pm_review (read-only, no implementation participation).

## Calculation contract
Existing response fields, no schema or migration changes. After existing tenant/company/membership-scoped telemetry selection, both board paths (legacy and read model) and truck detail derive pm_remaining = existing next_pm_miles minus eligible mileage. Board status/statistics derive after this calculation. Existing frontend PM labels, progress, urgency/sorting, queues and detail actions consume that value.

Eligible: retained manual dashboard odometer with dashboard_unspecified basis (explicitly authorized interim snapshots), or calibrated API odometer, in miles, finite/nonnegative and at least recorded service mileage. Maximum age 30 days matching telemetry retention; allow existing five-minute clock tolerance. API observation timestamp takes priority over receipt time. No extrapolation of old mileage. Missing, expired, virtual, nonfinite or lower-than-service readings fall back to service mileage. Fractional miles floor before integer countdown. Missing target stays unscheduled by mileage; calendar deadlines still apply. Zero says PM due, negative says overdue.

Canonical vehicle mileage, target, interval and service history are never written. Service completion continues to advance targets through existing workflow; a newer higher service reading supersedes a lower old snapshot. Work-order states and explicit status overrides retain priority.

## Evidence
- 52 backend tests: PM eligibility/countdown boundaries; telemetry authorization/isolation; board/detail/read-model parity; derived status/statistics; service reset; board regressions. Example 677767 - 660951 = 16816, canonical 652767 unchanged.
- 27 frontend tests: PM state/progress/urgency, board sorting and truck details.
- Changed frontend ESLint, TypeScript/production build and diff check pass.
- CUA Playwright actual-component synthetic board/detail: service120000, Motive124567, target145000, remaining20433; iPad820x1180 document/scroll width820, no overflow. Preview serves fixture responses, not the real backend.
- Independent QA read-only review GO; no blockers. Added status/statistics/service-reset integration test after review also passes.

## Runtime / release
Branch codex/motive-pm-mileage from main94c579a2. Runtime preflight refused retained untracked output; approved backend configuration absent, 8000 unbound. Synthetic Vite5173 PID10420 source verified as this worktree/frontend; rendered changes verified. Local authenticated full-stack acceptance remains blocked. Preview stopped after verification. No production data changes, merge or deployment performed. API approval/configuration and automatic collection remain separate gates.
