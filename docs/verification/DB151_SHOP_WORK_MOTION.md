# DB-151-MOTION — local acceptance, 2026-11-05

Owner: Frontend & UX. Fast UI; existing contracts. Branch `codex/shop-work-motion`.

Implemented: 200ms ease-out view entrances; anchored .95-scale popovers/dropdowns
with masked reveal and 160ms exits; 30ms row stagger capped at150ms; .97 press
feedback; ease-in-out color/chevron movement. Native Headless UI transitions keep
focus/dismissal behavior. Popovers portal outside board scrollers, with shared
light/dark/high-contrast tokens and viewport bounds. No dependencies added.

Applicability: no knobs, draggable objects, or shared moving objects exist in this
board; no invented animations for those rules. No success pulse was added to
refresh: completion is not proof all sources succeeded. No outgoing work snapshot
is retained, so auth clearing remains immediate. View changes cancel previous
animations rather than preserving old sensitive rows. Reduced motion disables
spatial animations, stagger and transitions; keyboard-focused view entrance skips.

Acceptance:
-79 focused tests pass across ledger, overview, active work, activity, auth lifecycle
 and new motion cancellation/reduced-motion tests.
- Changed TS/TSX lint clean; production typecheck/build and shared-controls checks
 pass. Existing bundle-size advisory remains.
- Signed-in browser: Overview, Active work (zero jobs with exact closeout next
 action), Closeout (two order rows/payment reviews), Activity (three records).
- All four viewed in Night shop and reduced motion; computed row animation `none`
 and menu transition `0s` under reduced motion.
-390px all four views: no document horizontal overflow. Found and fixed Activity
 filter panel clipping. Final dark panel opaque, full date controls visible,
 bounded x36–376 and y300–689 at390x844.
- Nested dropdown200ms, trigger origin top-left; outer filter origin top-right.
 Escape returns focus to dropdown and then filter trigger. No stale portal after
 switching views. Row delays0/30/60/90/120ms observed.
- Activity opens exact BOARD-PAYMENT-1 repair workspace. Close returns to Activity.
 No financial submissions. Settings appearance route remains usable. No console
 errors in final browser inspection.
- Preview retained with normal motion and Night shop enabled on synthetic account.

Runtime: frontend5298 PID3934 serves owned worktree/frontend, backend8198
container db151reviewboard-api-1 binds same checkout/backend. Base ae688a07 plus
working diff; database postgres/dashboard_lifecycle_disposable at204; readiness
ready, database+redis healthy, frontend proxy/authenticated board verified. No
production changes. Source is local; PR, merge and deployment not performed.

## Release review
User authorized merge/deploy2026-11-05. Review caught nested calendar clipping risk inside the scrollable portal; calendar now expands in-flow. Actual browser verified November dates and bounded291px width. No retained outgoing data or changed record destinations. Release pending protected CI.
