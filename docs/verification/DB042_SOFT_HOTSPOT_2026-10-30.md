# DB-042 — Soft hotspot part-row interaction

Owner: Frontend & UX. Lane: Fast UI, existing selection and API contracts. User approved Soft hotspot and authorized QA, merge and deployment when gates pass. Branch `codex/part-row-soft-hotspot`, base `a0150ba165228b67871b06f770b459df73f3e19c`.

## Acceptance and implementation

- Only the existing part button gains an inset fill/border and decorative chevron. Available, Bin, prices, purchase checkbox, and optional action menu keep their existing behavior. No full-row hover rule or new click handler.
- Hover uses120ms opacity/transform transitions, with a reserved16px cue slot and2px chevron movement; labels do not shift during hover. Fill/border derive from currentColor for existing appearance modes.
- Native button name, Tab order, Enter/Space and aria-controls remain unchanged. Chevron is aria-hidden and not focusable. Keyboard focus shows the fill/chevron immediately and an inset solid outline.
- Reduced motion disables transitions/movement; coarse pointers keep a static chevron. No hover dependency for selection; target remains over44px tall in compact layout.
- No new dependency, auth, tenant, API/data, stock/pricing/payment writer, or migration change.

## Automated verification

Before implementation, new decorative-cue test failed because the cue was missing; existing keyboard/noninteractive-cell behavior passed. After implementation: inventory suite52/52 passed, followed by the additional optional-row-menu isolation/Escape-focus test1/1. Total53 unique passing cases. Existing read-only/archive, editing, selection and pricing protections remain in the focused suite.

Changed-source ESLint with max-warnings0, TypeScript/Vite production build, and git diff checks pass. Existing React Router future warnings and outdated Browserslist notice remain. Quick pre-landing source review found no remaining issue in this UI scope. Protected exact-head CI is still required before merge.

## Actual signed-in browser acceptance

Normal fictional-owner session on the actual application/API/database, no mocked API adapter. Reused retained fictional part and added one disposable long-name part in the isolated local database; no production writes.

- Pointer hover over part button: overlay opacity1, chevron opacity0.8 after120ms; same target rectangle before/after animation (no layout movement).
- Pointer moved to Available/Bin/unit cost/checkbox: button:hover=false, overlay0 and cue0. No row-wide feedback.
- Clicking a purchase checkbox leaves selected inspector unchanged. Native Tab from checkbox reaches part button; focus-visible=true, solid outline, overlay1/cue0.8 and transition0s.
- Enter and Space each open the requested part. Optional row-menu isolation and Escape focus restoration verified by component test (counter-sales menu is not enabled in this fixture).
- prefers-reduced-motion:reduce emulation: transition0s and identity transform, visible feedback. Emulation cleared after test.
- Actual touch emulation yields pointer:coarse and hover:none: static chevron opacity0.6. At390x844 target54.23px high, no document horizontal overflow, selection opens detail, Back to parts works. Touch/viewport overrides restored.
- Long label truncates within existing cell while full accessible button name remains available. Console: zero errors.

[Hover](db042-soft-hotspot/hover.png) · [Keyboard focus](db042-soft-hotspot/keyboard.png) · [Compact/touch](db042-soft-hotspot/touch.png).

## Runtime receipt — October30,2026

Intended checkout: part-row-soft-hotspot worktree, branch codex/part-row-soft-hotspot, base a0150ba1 plus verified uncommitted feature. Vite5198 PID60193 cwd is this checkout/frontend; API8014 container dieselbridge_api_part-hotspot binds this checkout/backend at/app. Approved canonical backend environment symlink used, no copied secrets. DB postgres/truckpitstop_db042_qa, Redis index12; both already configured for the retained fictional environment. Schema sole192 before startup, upgrade-head no-op. No new flags, providers or workers enabled. Direct and frontend-proxied readiness return ready with database/Redis OK. Rendered cue and computed new hover/focus/reduced/touch styles corroborate source identity. Local URL http://127.0.0.1:5198/dashboard/garage/inventory is aligned and browser-verified for the recorded process/source. Shared5173/8000 and unrelated worktrees unchanged.

## Release state

Local implementation/acceptance complete; PR, protected CI, merge and exact deployment/browser proof pending. Not Done until release evidence exists. No production inventory mutations authorized for verification.
