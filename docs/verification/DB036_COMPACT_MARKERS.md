# DB-036 compact markers — 2026-10-07

Owner: Frontend & UX. Fast UI; no API, tenant, migration or security boundary changes.

Individual badges use 28px height instead of 36px and 2px vertical padding. Logo remains 20×22px. Layout fallback matches the badge height; geographic anchors and selection behavior are unchanged.

Validation: 12/12 FleetMapCanvas and mapLabelLayout tests; changed-source ESLint; git diff --check. Playwright CSS fixture at desktop and 390×844 verifies all four samples at 28px, logos loaded at 22px, and no label clipping. Includes selected, last-known, W900 and unbranded labels. This is synthetic CSS acceptance, not authenticated map acceptance. Screenshot retained locally at output/playwright/compact-markers-mobile.png. Only browser error was an absent fixture favicon.

Runtime receipt: branch codex/compact-map-markers, base d0311ffd2971bab0b9758eea141e745ed3931122 with scoped uncommitted edits during verification. Vite PID 31628 served this worktree frontend on http://127.0.0.1:5187. Shared 5173 belongs to motive-server-worker and was preserved. Controller dry-run blocked: backend/.env unavailable. Backend/database/sandbox identity, migrations and signed-in journey cannot be verified; no configuration copied or services replaced. Full application alignment is blocked; preview verifies changed CSS only. Merge/deployment and protected CI remain pending.
