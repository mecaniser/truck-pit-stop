# Driver record dismissal

Owner: Frontend & UX. Fast UI lane, existing API/data contracts unchanged.

## Acceptance

- Close with pointer, touch activation, Enter, Space or Escape without truck navigation.
- Outside dismissal consumes the first click above a truck; a subsequent intentional card click still opens details.
- Return focus to the score trigger after dismissal.
- Preserve driver loading, unavailable, identity context and source data behavior.
- Verify desktop and 390px compact layout; protected PR checks and deployed signed-in smoke before Done.

## Implementation and local evidence (2026-10-16)

The portaled panel now has a transparent, portaled backdrop above the clickable cards. Outside clicks close the record and restore focus instead of reaching an underlying card. The explicit Close button consumes its click and prevents a mouse-down focus change before dismissal. No data or identity contract changes.

- DriverRecord component suite:39/39, including pointer press/release, touch-event activation, Enter, Space, Escape, outside dismissal and intentional card opening afterward.
- Changed-source ESLint, TypeScript and git diff checks pass.
- CUA fixture browser: desktop1280×900 close and coordinate click over TEST-3 leave all9 cards displayed; no detail navigation and trigger focus restored. Compact390×844 close/reopen/Escape pass; panel bounds12..378 ×192..832, document width390.
- Mobile physical touch injection is unsupported by the in-app browser; touch-event regression is covered by the component suite, compact runtime uses browser pointer/keyboard input.
- Baseline reproduction: temporarily loading the unmodified component from main and clicking the same TEST-3 coordinates dismissed the panel AND opened truck details (0 cards, Back to fleet visible). Restoring the fix made that exact click dismiss only (9 cards, no details).
- Direct Close reproduction was intermittent in earlier live acceptance and did not recur during this fixture investigation; outside-card dismissal exposed the reliable unguarded path. Both dismissal paths are covered by the change.
- Screenshot and browser evidence are private in `output/driver-dismiss/`.

## Runtime alignment

Intended checkout: driver-identity-timeout-retry, branch `codex/driver-record-dismiss`, base683a4c85 plus scoped changes. Frontend fixture5177 PID38102 serves this checkout, confirmed by command/cwd and HTTP200; fixture adapter blocks every live request. Frontend5173 remains owned by motive-driver-records checkout. Backend8000 is unbound; approved local backend config absent. Synthetic fixture is aligned and browser-verified; authenticated local full-stack is blocked. Production smoke remains required after deployment.

## Release

Pending. Queue after #558 and #556; preserve #556 stable-build idle acceptance window. Prior #555 production receipts are carried forward as documentation only.
