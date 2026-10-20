# DB-VOID-003 local invoice action menu review

2026-10-20. Frontend & UX accountable. Fast UI lane. Branch `codex/invoice-actions-menu`, HEAD `8a81f9522cdc71cf0c0254fdba3aed50bd943798` with uncommitted UI/test edits. User requested local review before shipment.

The existing invoice row now contains a neutral 44px three-dot Invoice actions trigger. Its anchored Headless UI menu contains Void entire order… and opens the unchanged confirmation. Menu keyboard navigation, Escape and outside dismissal use the existing accessible library. Opening the confirmation restores its stable menu trigger as the return-focus target. Eligibility guards and all finance/API/step-up contracts are unchanged.

Runtime: Vite PID5536 serves this worktree frontend on http://127.0.0.1:5173 with current branch/SHA explicitly set and loopback API target 127.0.0.1:8000. Listener command and cwd verified after startup; HTTP preview is 200. No API listener exists. The runtime controller rejects the dirty checkout; prior full-stack schema blocker was left unchanged. This actual-component fixture intercepts all requests; no real records or financial actions were used. Fixture frontend is aligned and browser-verified; full-stack runtime remains unavailable.

Browser acceptance through the in-app browser: collapsed invoice stays70px at1440,390 and320 widths; trigger remains44px; menus fit within390/320 viewports; no page overflow at390. Independent invoice disclosure is retained. Menu selection opens confirmation, empty submit is disabled, reason receives focus, Escape closes confirmation only and restores focus to Invoice actions. Keyboard ArrowDown opens menu; Escape closes only menu and restores trigger focus; outside click dismisses menu. Mobile Cancel returns focus to trigger. Browser error logs empty. Temporary viewport overrides reset, preview tab kept open for user review. Screenshot: output/invoice-actions-menu/local-menu.png.

Automated checks: focused force-void suite13/13 passes, including hidden destructive action, menu keyboard dismissal, existing step-up contract, pending lock, failure/retry, success and role/import/deleted guards. Changed-source ESLint, TypeScript noEmit and git diff --check pass. Initial test invocation from repository root lacked the frontend alias config; rerunning from frontend completed successfully.

Local only. No PR, push, merge or deployment for this follow-up.
