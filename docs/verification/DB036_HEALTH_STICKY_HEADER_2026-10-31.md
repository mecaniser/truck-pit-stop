# DB-036 Truck health sticky header — 2026-10-31

Owner: Frontend & UX. Fast UI lane: presentation-only existing telemetry/diagnostics contracts, no worker, migration or permission changes.

Acceptance: keep title, close control, mileage and engine hours visible while fault list scrolls; replace repeated provenance paragraphs with one information tooltip supporting pointer hover, focus, Escape, and touch toggle. Preserve per-field source and capture time, unknown observation time, zero, unavailable readings, and independent fault availability.

Implementation: the panel is a height-bounded flex column with a fixed header and min-height-zero scrollable diagnostics body. A shared information button describes each field separately; it never borrows one field timestamp for another. Escape dismisses the tooltip before the containing popup. Synthetic development fixture provides twelve codes to exercise overflow.

Validation: focused TruckDiagnostics tests11/11, changed-source ESLint, TypeScript and production build pass; git diff --check passes. Existing Browserslist age warning only. Playwright real-component checks at1440x900 and390x844 confirm unchanged header bounds while codes scroll, no horizontal overflow, hover dismissal, keyboard focus/Escape retaining popup, touchscreen two-tap toggle, and0h display. Screenshots local /tmp/health-sticky-desktop.png, /tmp/health-sticky-compact-scroll.png and /tmp/health-sticky-compact.png (tooltip).

Runtime receipt: branch codex/health-sticky-vitals from17608d101a66733a4f75fd88ec52f0dd4b3ef6c1, edits as recorded in diff. Synthetic frontend http://127.0.0.1:5207/tests/health-vitals-preview.html PID31083 serves this checkout frontend; configured runtime branch/SHA verified at startup and rendered changed header inspected. API proxy intentionally points to closed127.0.0.1:9 and fixture uses an in-memory Axios adapter. No backend or database is attached to this preview. Shared5173 PID74219 and8000 Docker belong to machined-sidebar checkout and were preserved. Target checkout lacks backend/.env. Synthetic frontend is aligned and browser-verified; authenticated full-stack runtime is blocked/mismatched. No live-provider action or customer write performed.

PR, CI, merge, deployment and signed-in production smoke evidence remain pending. This item is Review, not Done.
