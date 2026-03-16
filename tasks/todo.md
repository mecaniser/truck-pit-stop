# Driver Recruiting Agent SOP - Task Plan

## Plan
- [x] Draft ATS-ready SOP scope, objectives, and role responsibilities.
- [x] Define end-to-end pipeline stages with explicit entry/exit criteria and SLAs.
- [x] Create copy-ready candidate message scripts (SMS + fallback email) by stage.
- [x] Define standardized screening questionnaire with answer options and capture fields.
- [x] Implement deterministic pass/fail logic with weighted scoring and disposition rules.
- [x] Map logic to ATS statuses, tags, tasks, and automation triggers.
- [x] Add operational guardrails, QA checks, and KPI dashboard definitions.
- [x] Review for clarity and plug-and-play usability.

## Progress Notes
- Initialized planning artifact for this deliverable.
- Added ATS-ready SOP at `docs/DRIVER_RECRUITING_AGENT_SOP.md`.
- Added import templates:
  - `docs/templates/driver_message_scripts.csv`
  - `docs/templates/driver_screening_questions.csv`
  - `docs/templates/driver_decision_rules.json`
- Verified template formatting and schema consistency against SOP sections.

## Review
- Deliverable is implementation-ready for most ATS automation builders.
- Remaining adaptation required: map exact field names/status IDs to your specific ATS vendor.

---

# SEO Improvements - Task Plan (2026-03-02)

## Plan
- [x] Audit existing SEO assets (sitemap, robots, metadata, canonical tags).
- [x] Improve public page metadata with consistent tags for title, description, canonical, robots, Open Graph, and Twitter.
- [x] Add structured data for crawlable public pages.
- [x] Ensure `/sitemap.xml` is served from production backend static routes.
- [x] Align sitemap contents with canonical, indexable public pages and include `lastmod`.
- [x] Verify changes with targeted checks and frontend build.
- [x] Add review notes and residual risks.

## Progress Notes
- [x] Initialized SEO implementation plan using the `seo` skill workflow.
- [x] Added reusable page-level SEO utility: `frontend/src/lib/seo.ts`.
- [x] Upgraded public page tags and JSON-LD on landing and enrollment pages.
- [x] Added `noindex, nofollow` metadata for login.
- [x] Updated root static SEO tags in `frontend/index.html`.
- [x] Updated crawl directives in `frontend/public/robots.txt`.
- [x] Updated sitemap URLs and `lastmod` in `frontend/public/sitemap.xml`.
- [x] Added backend static route serving for `/sitemap.xml` in `backend/app/main.py`.
- [x] Verified frontend build succeeds with `npm run build`.

## Review
- SEO foundation is now in place for indexable marketing pages (`/` and `/enroll`).
- Login and private application surfaces are explicitly de-prioritized for indexing.
- Residual risk: static sitemap `lastmod` values require manual updates when content changes.

---

# Internal Labor Memory - Task Plan (2026-03-15)

## Plan
- [x] Audit the existing price-builder flow and identify all active MOTOR/provider runtime references.
- [x] Replace the external-provider lookup path with an internal operation library plus persistent learned labor memory.
- [x] Remove active MOTOR-specific runtime modules/config/model exports from the internal-only flow.
- [x] Upsert learned labor memory from applied and edited repair-operation lines so future matching jobs reuse saved hours.
- [x] Add/adjust backend tests for library search, custom fallback, and learned-memory reuse behavior.
- [x] Run targeted backend verification and capture residual risks.

## Progress Notes
- [x] Confirmed active working-tree edits in price-builder files so implementation must preserve those changes.
- [x] Added `labor_operation_memory` model and updated Alembic migration `039_add_labor_operation_memory.py` to replace the obsolete cache table.
- [x] Reworked `PriceBuildService` to use internal library suggestions, custom-operation fallback, and saved internal memory only.
- [x] Removed active provider-specific runtime files and config entries tied to MOTOR integration.
- [x] Upserted learned memory from applied and edited repair-operation lines using tenant + year/make/model + operation key.
- [x] Passed targeted verification:
  `venv/bin/python -m pytest tests/test_price_build_service.py -q`
- [x] Passed endpoint import sanity check:
  `venv/bin/python -c "from app.api.v1.endpoints.repair_orders import router; print('ok')"`

## Review
- The active price-builder path is now internal-only: built-in repair-operation suggestions for first use, then tenant-specific learned memory for repeat jobs.
- Matching is intentionally scoped to tenant + vehicle year/make/model + operation identity, so similar fleet vehicles can reuse learned estimates even when VIN differs.
- Residual risk: learned memory currently stores hours only; repair-operation recalc still normalizes the hourly rate back to the tenant labor rate.
- Residual risk: historical migration `038_add_price_builder_and_motor_cache.py` still exists as part of the chain, but migration `039` now removes the obsolete cache on upgrade.

---

# NHTSA-Normalized Labor Memory - Task Plan (2026-03-16)

## Plan
- [x] Audit vehicle create/update paths and the current labor-memory signature.
- [x] Persist decoded NHTSA vehicle attributes on `vehicles` during create/update flows.
- [x] Update labor-memory signature generation to prefer decoded NHTSA attributes with fallback for legacy/manual vehicles.
- [x] Add focused backend tests for NHTSA persistence and decoded-signature matching.
- [x] Run targeted verification and capture residual risks.

## Progress Notes
- [x] Confirmed NHTSA is currently integrated only for VIN decode endpoint/UI, not persisted into `vehicles`.
- [x] Identified all relevant vehicle write paths: `customers`, `vehicles`, and quick repair-order vehicle creation fallback.
- [x] Added persisted `nhtsa_*` snapshot columns on `vehicles` plus migration `040_add_vehicle_nhtsa_snapshot_fields.py`.
- [x] Added `vehicle_nhtsa_service.py` and wired automatic snapshot sync into customer/global vehicle create/update flows.
- [x] Updated labor-memory signature generation to prefer normalized NHTSA attributes while still reading legacy manual signatures.
- [x] Passed targeted verification:
  `venv/bin/python -m pytest tests/test_price_build_service.py tests/test_vehicle_nhtsa_snapshot.py tests/test_vin_decoder.py -q`
- [x] Passed import sanity check:
  `venv/bin/python -c "from app.api.v1.endpoints.customers import router as customers_router; from app.api.v1.endpoints.vehicles import router as vehicles_router; from app.services.price_build_service import PriceBuildService; from app.services.vehicle_nhtsa_service import sync_vehicle_nhtsa_snapshot; print('ok')"`

## Review
- Vehicle records now persist decoded NHTSA attributes so labor-memory matching can use normalized truck specs instead of raw manual text entry.
- Labor-memory reads are backward-compatible with previously stored legacy signatures and will normalize rows to the new signature format on reuse.
- Residual risk: existing vehicles do not auto-backfill NHTSA snapshot fields until they are edited or otherwise re-synced, so older records still rely on manual fallback until refreshed.

---

# Dashboard Readability - Team Capacity (2026-03-16)

## Plan
- [x] Audit the dashboard cockpit and confirm the specific readability bottlenecks in Team Capacity.
- [x] Increase typography and spacing in the Team Capacity panel for shop-floor readability without broad layout churn.
- [x] Adjust any adjacent cockpit text density that still feels visually inconsistent after the Team Capacity uplift.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] Identified the main issue in `frontend/src/features/dashboard/DashboardHome.tsx`: Team Capacity relies on several `text-[11px]` labels with tight vertical spacing, which compresses names, statuses, and load summaries.
- [x] Reworked Team Capacity summary and mechanic cards with larger type, clearer active/queued wording, taller progress bars, and roomier click targets.
- [x] Bumped the adjacent Revenue KPI microtext so the lower cockpit band reads consistently after the Team Capacity uplift.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Team Capacity now prioritizes readability over density: mechanic names, status text, active/queued counts, and utilization summaries all render at a more practical operations-dashboard size.
- Adjacent Revenue KPI labels and helper text were raised slightly to avoid one readable panel sitting next to another still using microtext.
- Residual risk: a live pass with production-length mechanic names and a fully populated team list is still worth checking to confirm the scroll area feels right on the shop's actual display hardware.

---

# Dashboard Layout Priority Pass (2026-03-16)

## Plan
- [x] Confirm the current manager dashboard structure and identify the minimal layout shift that keeps Team Capacity visible at all times.
- [x] Move Team Capacity out of the bottom split layout into a persistent standalone section.
- [x] Make the lower-priority Work Queue section collapsible with a concise summary when collapsed.
- [x] Move Revenue KPIs to the end of the page and simplify them into a more minimal strip.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] Confirmed the current issue: Team Capacity and Revenue KPIs still share the bottom bar, so critical staffing visibility competes with secondary financial metrics for screen space.
- [x] Promoted Team Capacity into its own full-width section above the queue and widened the mechanic grid so staffing stays visible without depending on the page footer.
- [x] Converted Work Queue into a collapsible section with summary chips and refresh controls in the header, defaulting it closed so detail lanes are available on demand instead of consuming fixed vertical space.
- [x] Reduced Revenue KPIs to a compact bottom strip with only four finance numbers plus paid-order context.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Team Capacity now stays visible as a first-class operational panel, while finance information is pushed down and visually de-emphasized.
- The manager dashboard hierarchy is clearer: staffing first, workflow second, revenue last.
- Residual risk: a live usage pass should confirm whether the collapsed-by-default queue matches the shop’s day-to-day rhythm or whether managers want it opened automatically on larger wall displays.

---

# Dashboard Order Follow-up (2026-03-16)

## Plan
- [x] Confirm the current section order in the manager dashboard.
- [x] Move Team Capacity below Work Queue while keeping Revenue KPIs last.
- [x] Run targeted frontend verification and capture the result.

## Progress Notes
- [x] Confirmed the current render order is `Team Capacity -> Work Queue -> Revenue KPIs`, and the requested follow-up is a direct swap of the first two manager sections.
- [x] Moved the Team Capacity panel render block below the collapsible Work Queue without changing its behavior or styling.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Manager dashboard order is now `Work Queue -> Team Capacity -> Revenue KPIs`.
- The change is intentionally minimal: same Team Capacity component, only a lower placement in the page flow.

---

# Dashboard Collapse Correction (2026-03-16)

## Plan
- [x] Confirm the current collapse behavior and the corrected target section.
- [x] Make Work Queue always visible again.
- [x] Move collapse behavior to the bottom Revenue KPI section.
- [x] Run targeted frontend verification and capture the result.

## Progress Notes
- [x] Confirmed the current mistake: Work Queue is the collapsible section, but the user intended collapsibility for Revenue KPIs instead.
- [x] Removed collapse state from Work Queue so the operational lanes stay visible at all times.
- [x] Added the collapse toggle to the bottom Revenue KPI section and kept it collapsed by default for minimal visual weight.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Work Queue is visible again as the always-open operational section.
- Revenue KPIs are now the only collapsible dashboard section in this area, which matches the clarified intent.

---

# Dashboard Work Queue Height Tuning (2026-03-16)

## Plan
- [x] Inspect the current Work Queue height behavior and identify the smallest viewport-fit adjustment.
- [x] Reduce the Work Queue height slightly so Team Capacity and Revenue KPIs fit more reliably within the viewport.
- [x] Run targeted frontend verification and capture the result.

## Progress Notes
- [x] Confirmed the main constraint is the queue lanes' reserved vertical space in `frontend/src/features/dashboard/DashboardHome.tsx`, which still reads tall enough to crowd the sections below on shared dashboard screens.
- [x] Added a modest desktop max-height cap to the Work Queue wrapper and reduced per-lane minimum heights so the queue gives back space without becoming cramped.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Work Queue now takes slightly less vertical space on desktop, which should make Team Capacity and the Revenue footer fit the viewport more reliably.
- The change is intentionally conservative: same layout and content, only tighter queue height constraints.

---

# Dashboard Dynamic Queue Fit (2026-03-16)

## Plan
- [x] Confirm why the fixed queue reduction felt too aggressive.
- [x] Replace the fixed queue cap with viewport-aware sizing tied to the actual available space.
- [x] Run targeted frontend verification and capture the result.

## Progress Notes
- [x] Confirmed the issue: the previous queue reduction was a fixed desktop trim, but the user wanted the queue height to respond to the viewport and the sections below it.
- [x] Added a measured queue max-height based on viewport height, queue top position, and the live Team Capacity / Revenue section heights.
- [x] Replaced the hard lane-height reduction with a softer `clamp(...)`-based minimum so lane cards shrink more gracefully on shorter screens.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Work Queue height is now dynamic on desktop instead of being forced to a single reduced size.
- Team Capacity and Revenue keep their space, while the queue adapts to what is actually left in the viewport.

---

# Dashboard Hook Order Fix (2026-03-16)

## Plan
- [x] Identify the cause of the runtime hook-order error in `DashboardHome`.
- [x] Move all hooks ahead of loading/error early returns while preserving the dynamic queue sizing logic.
- [x] Run targeted frontend verification and capture the result.

## Progress Notes
- [x] Confirmed the error cause: the dynamic queue sizing `useEffect` was added after conditional early returns, so the component rendered a different number of hooks between loading/error and loaded states.
- [x] Moved the derived dashboard values and dynamic queue sizing `useEffect` above the loading/error returns so hook order stays stable on every render.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The hook-order runtime error is resolved by keeping all hooks ahead of conditional returns.
- Dynamic queue sizing remains in place; only the hook placement changed.

---

# Repair Order Price Builder Status Gating (2026-03-16)

## Plan
- [x] Confirm the current repair-order detail render path and the exact target status mapping for pricing UI.
- [x] Implement full price builder rendering only for `draft` and `quoted`.
- [x] Implement a read-only labor breakdown view for `pending_review` and `completed`.
- [x] Hide the pricing panel entirely for `invoiced` and `paid`.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the current issue: `PriceBuilderPanel` was always rendered in the repair-order detail, even after the order moved into non-editable workflow states.
- [x] Added explicit status gating so `draft` and `quoted` keep the full pricing workflow while `pending_review` and `completed` swap to a compact read-only labor breakdown.
- [x] Hid the remaining builder-related pricing cluster for statuses outside the editable workflow, including `invoiced` and `paid`.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Repair-order pricing UI now follows workflow state instead of rendering the same builder in every status.
- Pending review and completed orders show only a read-only labor breakdown, which keeps historical labor context without exposing dead controls.
- Invoiced and paid orders no longer show the builder area on the repair-order detail view.

---

# Dashboard Scrollbar Refinement (2026-03-16)

## Plan
- [x] Inspect the current scrollbar styling entry points used by the dashboard.
- [x] Reduce scrollbar width and remove the visible track while preserving existing hide behavior.
- [x] Run targeted frontend verification and capture the result.

## Progress Notes
- [x] Confirmed the active scrollbar styling lives in `frontend/src/index.css`, with `.scrollbar-dark` supplying the main custom rail/thumb treatment used by dashboard overflow regions.
- [x] Reworked the scrollbar styling to use a slimmer shared size and a transparent track so only the thumb remains visually prominent.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Dashboard scrollbars now read lighter and take less horizontal space, which better fits the dense operations layout.
- The visible scrollbar track has been removed so the UI shows only the thumb, while existing `.scrollbar-hide` behavior stays intact.

---

# Repair Order Danger Zone Sizing (2026-03-16)

## Plan
- [x] Inspect the current repair-order detail footer and identify why the Danger Zone spans too much horizontal space.
- [x] Reduce the Danger Zone container so it wraps its content instead of stretching across the full footer.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the current issue: the Danger Zone footer used a full-width red wrapper and a full-width toggle button, which made the section read larger than the actual actions required.
- [x] Reworked the footer into a right-aligned inline card with its own border/background so the red area now hugs the toggle and actions instead of spanning the full panel width.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The repair-order Danger Zone now occupies approximately its content width instead of reading like a full-width footer banner.
- The visual emphasis remains intact, but the footer is less heavy and no longer dominates the bottom of the detail panel.

---

# Repair Order Danger Zone Height Correction (2026-03-16)

## Plan
- [x] Reconfirm the intended Danger Zone layout after the user's correction.
- [x] Restore the full-width footer strip and reduce only its vertical padding/height.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the correction: the user wanted the Danger Zone to stay full-width across the repair-order side panel, with only the height reduced.
- [x] Restored the full-width footer strip and tightened its vertical footprint with smaller top/bottom padding, tighter internal spacing, and smaller icon padding.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The Danger Zone is again a full-width strip across the repair-order side panel.
- Only the vertical bulk was reduced, so the footer reads shorter without changing its full-width layout.

---

# Repair Order Danger Action Gating (2026-03-16)

## Plan
- [x] Confirm all current cancel/delete entry points and the statuses they affect.
- [x] Hide the repair-order Danger Zone in the frontend outside the intended pre-billing statuses.
- [x] Add backend guards so cancel/delete requests are rejected once a repair order reaches protected financial/work-complete statuses.
- [x] Run targeted verification and capture review notes.

## Progress Notes
- [x] Confirmed the current issue: the detail view still rendered the Danger Zone broadly, and the backend allowed generic cancel/delete flows without completed-status workflow guards.
- [x] Limited the frontend Danger Zone to `draft` and `quoted` repair orders only.
- [x] Added backend guards so cancel and hard delete are only allowed when the repair order is still `draft` or `quoted`.
- [x] Passed targeted verification:
  `venv/bin/python -m pytest tests/test_repair_order_danger_action_rules.py -q` (from `backend/`)
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The repair-order detail view no longer exposes cancel/delete controls once the order has moved beyond the early pre-billing workflow.
- The API now enforces the same rule, so completed, invoiced, and paid orders cannot be cancelled or deleted through the generic endpoints.

---

# Completed Order Invoice Flow Compaction (2026-03-16)

## Plan
- [x] Inspect the current completed-order invoice card and confirm which controls are truly optional.
- [x] Collapse optional invoice fields behind a compact disclosure while keeping the primary create-invoice action visible.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the current issue: the completed-order card always showed optional due-date and discount fields, which made secondary settings feel mandatory.
- [x] Reworked the card so the primary create-invoice action stays visible while due date and discount live behind an "Optional invoice settings" disclosure with a compact summary.
- [x] Reset the optional invoice state when switching orders, closing the detail panel, or after successful invoice creation so the card reopens in a minimal state.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The completed-order invoice flow is now visually aligned with the underlying logic: optional settings are hidden by default instead of reading like required inputs.
- Staff can still set due date or discount when needed, but the default path is now a simpler single-action invoice creation flow.

---

# Scoped Commit And Push (2026-03-16)

## Plan
- [x] Inspect the working tree with `scoped-commit-assistant` and generate proposed commit boundaries from the existing changes.
- [x] Refine the generated scopes where needed so each commit remains independently reviewable.
- [x] Run the smallest relevant verification for each staged scope and avoid claiming checks that were not run.
- [x] Commit each scope with structured commit messages that explain why, validation, and residual risk.
- [x] Push the resulting commit set from `main` to `origin`.
- [x] Document the final commit list, verification, and push result in this review section.

## Progress Notes
- [x] Confirmed the repo is currently on `main` and the user explicitly asked to commit and push the existing changes.
- [x] Ran the `scoped-commit-assistant` planner against the full working tree to derive an initial six-commit proposal.
- [x] Refined the initial proposal into four reviewable scopes by splitting backend pricing/memory work, repair-order workflow behavior, dashboard layout/readability updates, and task documentation.
- [x] Created commit 1:
  `feat(pricing): internalize labor memory with NHTSA matching`
- [x] Created commit 2:
  `feat(repair-orders): align detail actions with workflow status`
- [x] Created commit 3:
  `feat(dashboard): improve queue fit and team readability`

## Review
- Verification completed before final push:
  `venv/bin/python -m pytest tests/test_price_build_service.py tests/test_pricing.py tests/test_vehicle_nhtsa_snapshot.py tests/test_repair_order_danger_action_rules.py -q` (from `backend/`)
- Verification completed before final push:
  `npm run build` (from `frontend/`)
- Final commit order:
  `feat(pricing): internalize labor memory with NHTSA matching`
  `feat(repair-orders): align detail actions with workflow status`
  `feat(dashboard): improve queue fit and team readability`
  `docs(tasks): capture task history and commit workflow`
- Push target: `origin/main`
