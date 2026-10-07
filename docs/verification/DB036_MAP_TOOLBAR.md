# Map toolbar and pinned legend — 2026-10-07

Frontend & UX, Fast UI. Header map controls align over geography; search occupies the list column. CSS grid shares column sizing between toolbar and workspace. Mobile places search between map and list. Scrollable list content is separate from the nonshrinking footer so rows never cover the distance legend. Mobile list capped at 560px; desktop at 720px.

14 FleetProximity tests, changed-source ESLint, TypeScript and diff checks pass. CUA desktop 31-row synthetic fixture scrolled to TEST-24 with search/footer retained and last row unobscured; narrow viewport confirms controls remain whole and search sits above list. Production not changed.

Runtime: codex/fleet-map-toolbar, base 232dcd14bb84670446794853471412cfea8ba310. Vite PID45590 serves this worktree on http://127.0.0.1:5187 with current source and branch identity; backend absent, no database/configuration copied. Synthetic preview is browser-verified; authenticated local runtime remains unavailable. Prior PR477 release receipt is preserved in local commit 52dba09f on codex/compact-map-markers.

Follow-up: search now fills the entire header cell without an inset border; focus outlines the cell. Map toolbar vertical padding reduced from 12px to 4px while retaining 44px controls. Desktop and 390px browser rendering verified; CSS-only change, diff check passes.

Home/Recenter follow-up: removed individual button boxes, reduced horizontal padding to 8px and icon gap to 6px; retained 44px targets, focus outlines and pointer hover feedback.

Footer alignment: home-distance footer uses the same 43px desktop height as the map legend, aligning its top divider with the bottom of the map canvas.

Release CI repair: replaced footer :has selector with an explicit conditional class after jsdom failed seven FleetTelemetry tests. FleetTelemetry + FleetProximity now pass 38/38; ESLint, TypeScript and local visual alignment pass. Runtime 5187 PID45590 still serves this checkout; backend unavailable.
