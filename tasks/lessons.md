# Lessons

## 2026-03-02
- Correction: User requested explicit use of the `seo` skill after initial SEO assessment.
- Rule: When the user names a skill directly, open that skill first and execute the implementation through that workflow before additional changes.
- Prevention: Confirm skill activation in the first status update and reflect the skill-driven plan in `tasks/todo.md` before coding.

## 2026-03-16
- Correction: User wanted the dashboard section order adjusted again so Team Capacity sits below Work Queue, not above it.
- Rule: When the user gives explicit positional UI instructions like "above", "below", or "last", implement that literal render order rather than inferring a priority order from earlier context.
- Prevention: Before patching layout sections, map the intended final DOM order in `tasks/todo.md` and compare it against the current order.
- Correction: User clarified that collapsibility was intended for Revenue KPIs, not Work Queue.
- Rule: When a user says a UI behavior applies to a specific section, bind the behavior only to that named section and do not generalize it to adjacent panels.
- Prevention: Before implementing toggles/collapse state, restate the exact target section in `tasks/todo.md` and verify the state variable name matches that target.
- Correction: User rejected the fixed Work Queue height reduction and asked for dynamic viewport-aware sizing instead.
- Rule: When the user asks for viewport fit, prefer responsive or measured sizing tied to available space over hardcoded height reductions.
- Prevention: Before shrinking a major dashboard section, decide whether the constraint should be fixed or derived from viewport/section measurements, and note that choice in `tasks/todo.md`.
- Correction: User hit a runtime error because a new `useEffect` was placed after conditional loading/error returns in `DashboardHome`.
- Rule: Never place React hooks after any possible early return path.
- Prevention: After adding hooks to a component with loading/error guards, do a quick hook-order scan from top to first `return`.
- Correction: User asked to reduce the Danger Zone "size," but meant height only; I changed width/footprint instead.
- Rule: When a user asks to make a UI element "smaller," identify whether they mean width, height, padding, or overall footprint before changing layout direction.
- Prevention: In `tasks/todo.md`, spell out the specific dimension being changed for any sizing request and compare it against the current implementation before patching.
