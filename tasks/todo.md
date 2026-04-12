# Founding Garage Business Email Overflow - Task Plan (2026-04-12)

## Plan
- [x] Audit the garage information review card and confirm why long business emails still escape the container.
- [x] Update the garage information summary layout so the business email stays inside the card at review-step widths.
- [x] Run targeted verification and capture review notes plus residual risk.

## Progress Notes
- [x] Overflow owner confirmed: the garage information review card still placed `Business Email` in the right column of a `sm:grid-cols-2` summary row with no wrapping utility on the value text.
- [x] Patched `frontend/src/features/auth/GarageEnrollmentPage.tsx` so the contact row now stacks `Business Email` beneath `Phone` and wraps the email with `break-all`.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The garage information review card no longer forces long business emails into a narrow right-side column.
- `Business Email` now renders beneath `Phone` and wraps inside the card boundary instead of overflowing past it.
- Residual risk: this was validated by production build only; a quick live pass on the enrollment review step is still the final visual check.

---

# Founding Garage Owner Email Overflow - Task Plan (2026-04-12)

## Plan
- [x] Audit the review-step owner account layout and confirm why long owner login emails escape the card.
- [x] Move the owner login email under the owner name in the review summary and add wrapping protection so long addresses stay inside the container.
- [x] Run targeted verification and capture review notes plus any residual risk.

## Progress Notes
- [x] Overflow owner confirmed: the review card's `sm:grid-cols-2` owner account summary put the long email in a constrained right column with no wrapping utility on the value text.
- [x] Patched `frontend/src/features/auth/GarageEnrollmentPage.tsx` so the owner name spans the full review row and the owner login email now renders directly beneath it with `break-all`.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The owner account review card now stacks the login email under the owner name instead of forcing it into a separate right-side summary column.
- Long owner login emails now wrap within the card instead of overflowing past the container edge.
- Residual risk: this was validated by production build only; a quick live pass on the enrollment review step is still the final confirmation for the exact visual spacing.

---

# Garage Services Nested Scroll Follow-up - Task Plan (2026-03-23)

## Plan
- [x] Confirm the remaining desktop nested scrollbar pair shown in the Services screenshot.
- [x] Remove the garage content-pane scrollbar for Services and Inventory routes while preserving their intended internal scrolling.
- [x] Make Services fill the garage pane cleanly so only its list area scrolls on desktop.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] User screenshot confirmed the remaining nested pair is `MyGaragePage` desktop content scrolling plus the Services list scrollbar.
- [x] Patched `MyGaragePage` overflow ownership by garage sub-route so desktop `services` and `inventory` stop using the garage content-pane scrollbar.
- [x] Refit `ServicesManagementPage` to a height-aware desktop flex layout so the services list remains the sole vertical scrollbar.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Desktop Services now removes the extra garage-pane scrollbar and keeps scrolling inside the services content area instead.
- Desktop Inventory uses the same route-level overflow rule, so it no longer inherits a second garage-pane scrollbar either.
- Residual risk: this was verified by build and screenshot-driven analysis only; a live browser pass is still the final check for confirming the rightmost page scrollbar is gone on `/dashboard/garage/services`.

---

# Garage Inventory Scroll Ownership - Task Plan (2026-03-23)

## Plan
- [x] Audit the dashboard route wrapper and garage page nesting to confirm which container owns vertical overflow on inventory/services.
- [x] Remove the unintended parent desktop scrollbar introduced by the dashboard route wrapper for `garage/*` pages.
- [x] Preserve a single intentional page-level scrollbar inside the garage workspace content pane.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] Confirmed `DashboardLayout` wraps all dashboard routes in `overflow-y-auto`, including `garage/*`.
- [x] Confirmed `MyGaragePage` already provides its own desktop content scroll region, so garage routes currently have nested scroll ownership.
- [x] Patched `DashboardLayout` so `garage/*` keeps the shared route scroller on mobile but switches to `lg:overflow-hidden`, removing the desktop parent scrollbar.
- [x] Added `scrollbar-dark` to the garage content pane so the remaining desktop scrollbar stays on the garage workspace itself.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Desktop garage routes now use a single outer scroll owner at the garage content pane instead of also inheriting the dashboard route wrapper scrollbar.
- Mobile garage routes keep the dashboard wrapper scroll, avoiding regressions from the desktop-only overflow change.
- Residual risk: this was verified by build only; a quick live pass on `/dashboard/garage/inventory` and `/dashboard/garage/services` is still worth doing to confirm the gear menus no longer trigger a parent scrollbar.

---

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

---

# Railway Alembic Command Diagnosis (2026-03-16)

## Plan
- [x] Reproduce the `railway run alembic upgrade head` failure from the repo context.
- [x] Verify whether the missing path is the local `alembic` executable, the Alembic config location, or another environment assumption.
- [x] Apply the smallest corrective change needed, if any, and document the correct invocation path.
- [x] Verify the corrected workflow and record review notes.

## Progress Notes
- [x] Confirmed the repository’s Alembic config and migration scripts live under `backend/`.
- [x] Confirmed current project docs already instruct migration commands from within `backend/` after activating a Python virtual environment.
- [x] Reproduced the exact Railway CLI failure from the repo root: `railway run alembic upgrade head` returns `No such file or directory (os error 2)` because `railway run` tries to execute a local `alembic` binary and none is present on the root PATH.
- [x] Verified `railway run /bin/sh -lc 'command -v alembic || echo missing'` prints `missing`, which proves the missing file is the executable itself, not the migration folder.
- [x] Verified the repo-root `.venv/bin/alembic` wrapper is also unusable in this checkout because its shebang points at `/Users/sergio/TruckPitStop/.venv/bin/python`, a stale path that no longer exists.
- [x] Verified the backend virtualenv is valid and the safe Railway-backed command works when run from the backend directory context:
  `railway run /bin/sh -lc 'cd backend && venv/bin/python -m alembic heads'`
- [x] Verified root execution with `-c backend/alembic.ini` is still cwd-sensitive in the current config, so the reliable command is to `cd backend` before invoking Alembic.

## Review
- Root cause is local command resolution, not a missing migration file in Railway.
- `railway run` injects Railway environment variables into a command that still runs on the local machine, so the command must reference a real local Python/Alembic executable.
- Correct migration command for this checkout:
  `railway run /bin/sh -lc 'cd backend && venv/bin/python -m alembic upgrade head'`
- Residual risk: if `backend/venv` does not exist on another machine, the virtualenv must be created first with the documented backend setup steps.
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

# Work Queue Header Status Cleanup (2026-03-16)

## Plan
- [x] Confirm where the duplicate work-order status badge is rendered inside the work queue.
- [x] Remove the duplicate status badge from the queue card header while preserving lane-level readiness signals.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the duplicate is the order-level status badge rendered inside each `OrderCard`, even though the three work-queue lanes already categorize the orders by status/actionability.
- [x] Removed the per-card status pill and the now-unused badge-color mapping so the queue cards rely on lane placement plus elapsed/mechanic details instead of repeating status in the header.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The work queue header/cards no longer repeat status information that is already conveyed by the lane structure.
- `Needs Action`, `On the Floor`, and `Ready to Close` remain the primary status framing, which makes the queue header and cards less noisy.

---

# Work Queue Header Chip Correction (2026-03-16)

## Plan
- [x] Reconfirm the exact duplicated status indicators the user meant in the Work Queue header.
- [x] Remove the top-right summary chips from the Work Queue header while preserving the refresh/last-updated control.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the correction: the user meant the header-level summary chips (`Needs Action`, `On Floor`, `Ready`) next to `Just Updated`, not the per-card status pill.
- [x] Removed the header-level summary chip row and the now-unused `workQueueSummary` data, leaving the header with only title, info tooltip, and refresh/last-updated status.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The `WORK QUEUE` header no longer repeats the same lane summary chips that are already implied by the three queue columns below.
- The refresh/last-updated control remains in place, so the header still communicates live status without the duplicated category pills.

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

---

# Detached Worktree Merge Audit (2026-03-16)

## Plan
- [x] Inventory all git worktrees and identify detached ones.
- [x] Inspect detached worktrees for dirty state, unique commits, and practical merge candidates.
- [x] Verify whether detached worktree behaviors are already present on `main` in newer form.
- [x] Decide whether to merge, port selected deltas, or explicitly skip stale worktree edits.
- [x] Record the audit result and commit only the audit if no safe code merge remains.

## Progress Notes
- [x] Confirmed the active branch is `main` at `a317fe4` before the audit started.
- [x] Found many detached worktrees under `~/.codex/worktrees` and `~/.cursor/worktrees`, but every detached HEAD inspected is already an ancestor of `main`; there are no unique detached commits to merge.
- [x] Narrowed the problem to uncommitted edits inside a subset of detached worktrees.
- [x] Compared those edits against current `main` and confirmed the substantive feature areas are already present in newer form on `main`, including mechanic workflow statuses, mechanic portal routing, points/PTO flows, quote resend/approval behavior, and customer-linking during registration.

## Review
- No detached worktree produced a clean, non-stale code delta that should be merged into `main` without risking regression.
- As a result, no detached worktree code was ported into the active tree during this audit.
- The only commit created from this task is the audit record itself so the repository history reflects why no code merge was performed.

---

# Detached Worktree Cleanup (2026-03-16)

## Plan
- [x] Preserve any dirty detached worktree edits before removal.
- [x] Remove all auxiliary git worktrees and prune stale metadata.
- [x] Verify that only the main checkout remains and record the preservation path.

## Progress Notes
- [x] Stashed dirty detached worktrees with `pre-remove worktree backup` messages that include the original path and detached HEAD for traceability.
- [x] Removed all auxiliary worktrees under `~/.codex/worktrees` and `~/.cursor/worktrees`, then pruned worktree metadata.
- [x] Verified `git worktree list --porcelain` now reports only `/Users/sergio/GitHub/TruckPitStop` on `refs/heads/main`.

## Review
- Detached worktrees have been removed from the machine; only the primary checkout remains attached to `main`.
- Dirty detached worktree contents were not discarded: 19 preservation stashes were created in the main repository before removal.
- Residual risk: those preservation stashes remain in `git stash list` until they are manually reviewed and dropped.

---

# My Garage Left-Rail Navigation (2026-03-16)

## Plan
- [x] Audit the current `MyGaragePage` shell and pin the target render order.
- [x] Replace the top horizontal tab strip with a desktop left-side vertical navigation rail.
- [x] Preserve a compact top navigation pattern on smaller screens so the layout remains usable on mobile.
- [x] Refine the navigation styling so the garage sections read as a dedicated control rail, not generic stacked buttons.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] Confirmed the current shell order in `frontend/src/features/garage/MyGaragePage.tsx` is `horizontal tabs -> routed content`.
- [x] Locked the requested desktop target order for this pass to `left navigation rail -> routed content pane`, with the section list remaining `Mechanics -> Services -> Inventory -> Suppliers -> Analytics`.
- [x] Rebuilt the garage shell around a shared section config so desktop now renders a dedicated left navigation rail with icon-backed items and the content pane shows the active module context above routed content.
- [x] Preserved a compact horizontal module strip for smaller screens so the new navigation pattern does not consume excessive vertical space on mobile.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- My Garage now uses a clearer desktop workspace layout: navigation lives on the left, content stays on the right, and the active module is reinforced with a dedicated header instead of a thin top tab row.
- Mobile keeps the section switcher compact and horizontal, which preserves usability where a permanent left rail would crowd the viewport.
- Residual risk: this is compile-verified, but a live browser pass is still worth doing to confirm the left rail feels balanced against the longest Mechanics and Inventory content states.

---

# My Garage Settings UX Alignment (2026-03-16)

## Plan
- [x] Capture the corrected UX target using the Settings page as the shell reference.
- [x] Refactor `MyGaragePage` so its mobile and desktop navigation patterns match the Settings page behavior.
- [x] Remove custom garage-shell framing that does not exist in the Settings page flow.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] User clarified the issue is UX, not aesthetics: My Garage should follow the Settings page interaction model shown in the screenshot.
- [x] Locked the target shell for this pass to the Settings layout pattern: compact horizontal nav on mobile, sticky left sidebar on desktop, and direct routed content on the right without extra workspace headers.
- [x] Replaced the custom My Garage hero and active-section header with a Settings-style shell that uses the same nav density, grouping, and active-state treatment as `UnifiedSettingsPage`.
- [x] Kept My Garage route-driven so Mechanics, Services, Inventory, Suppliers, and Analytics still deep-link correctly while using the simpler Settings-style sidebar UX.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- My Garage now follows the same interaction structure as Settings instead of a custom workspace shell: compact mobile tabs, sticky desktop sidebar, and direct content rendering on the right.
- The UX is flatter and more predictable because the extra “Shop control” and “Garage workspace” framing has been removed.
- Residual risk: compile verification passed, but a browser pass is still worth doing to confirm the narrower Settings-style shell feels right for the widest Mechanics and Inventory states.

---

# My Garage Docked Sidebar And Settings Access (2026-03-16)

## Plan
- [x] Document the requested docked-sidebar behavior and settings access path.
- [x] Expand the desktop My Garage sidebar so it fills the available viewport-height workspace and can hold a bottom-anchored utility action.
- [x] Add a separate navigation action that routes tenants to `/dashboard/settings`.
- [x] Run targeted frontend verification and summarize which existing Settings sections are the best candidates for future My Garage integration.

## Progress Notes
- [x] Confirmed the current My Garage shell already follows the Settings page interaction model, so this pass can stay focused on vertical sizing and settings access.
- [x] Reviewed the existing Settings sections in `frontend/src/features/dashboard/UnifiedSettingsPage.tsx` to identify which ones are tenant-garage controls versus personal account controls.
- [x] Expanded the desktop My Garage rail into a docked sidebar that fills the workspace height and reserves a dedicated bottom utility zone.
- [x] Added `Profile & Settings` navigation affordances to both desktop and mobile so users can jump from My Garage to `/dashboard/settings`.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- My Garage now reads as a docked workspace: the left rail fills the viewport-height garage area on desktop, while `Profile & Settings` is separated from operational garage modules as a utility action at the bottom.
- Mobile keeps the garage modules in a compact horizontal scroller but now also exposes the same settings jump as a separate action below the module strip.
- After inspecting `UnifiedSettingsPage`, the best candidates to bring closer to My Garage later are garage-scoped controls only: `Garage Profile`, `Workforce`, `Notifications`, `Tax & Fees`, and optionally `Stripe Payments` / `Zelle` if the goal is an operations cockpit. Personal controls such as `Profile`, `Security`, and `Appearance` should stay in the dedicated Settings page.
- Residual risk: viewport-height sizing is compile-verified, but a live browser pass is still worth doing to confirm the dock height feels correct against the actual breadcrumb/header stack on shorter laptop screens.

---

# My Garage Full-Page Sidebar Stretch (2026-03-16)

## Plan
- [x] Capture the correction that the desktop garage rail should stretch to the bottom of the page, not just the viewport.
- [x] Remove the viewport-capped sticky sizing from the desktop garage rail.
- [x] Keep garage module navigation pinned to the top of the rail and account/settings access anchored to the bottom.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] User clarified the desired behavior: the garage options belong at the top, while the account/profile settings route belongs at the true bottom of the page column.
- [x] Confirmed the current issue in `frontend/src/features/garage/MyGaragePage.tsx`: the desktop rail uses `sticky` plus `h-[calc(100vh-9rem)]`, which caps it to viewport height instead of stretching with the page.
- [x] Replaced the viewport-capped sticky rail with a full-height flex column so the sidebar now stretches with the page/content column while still respecting the minimum workspace height.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The desktop My Garage rail now stretches to the bottom of the page column instead of stopping at viewport height.
- Garage modules stay grouped at the top of the rail, while the `Account` section with `Profile & Settings` remains anchored at the bottom.
- Residual risk: compile verification passed, but a live browser pass is still worth doing to confirm the stretched rail looks correct on especially tall or especially short content states.

---

# My Garage Page-Floor Rail Fill (2026-03-16)

## Plan
- [x] Capture the correction that the rail must fill the remaining dashboard page column, not just rely on min-height.
- [x] Make the My Garage route root participate in the dashboard flex layout as a filling child.
- [x] Make the sidebar card inherit that full page-column height so `Account` stays at the true bottom.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] User clarified the remaining issue with the red outline: the left rail itself must reach the page floor, with `Profile & Settings` at the bottom of that full-height column.
- [x] Confirmed the current shell still relies on `min-h-[calc(100vh-9rem)]`, which can leave a gap because the page wrapper is not growing as a true flex remainder inside `DashboardLayout`.
- [x] Changed the My Garage route root to `flex-1` so it fills the remaining dashboard column and lets the desktop rail inherit that real page height.
- [x] Replaced the desktop rail sizing with `min-h-full`/`flex-1` inheritance so the `Account` section now sits at the bottom of the full-height rail instead of a min-height approximation.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The left My Garage rail now fills the remaining dashboard page column, which matches the full-height outline you pointed out.
- Garage navigation remains at the top of the rail, and the `Account` divider with `Profile & Settings` now sits at the bottom of that same full-height column.
- Residual risk: compile verification passed, but I have not done a live browser pass to visually confirm the rail against the exact page chrome in your local viewport.

---

# My Garage Viewport-Constrained Rollback (2026-03-16)

## Plan
- [x] Capture the correction that the My Garage workspace should stay within the viewport and not expand with right-side content.
- [x] Roll back the content-driven height behavior in the My Garage shell.
- [x] Keep the left rail full-height within the visible workspace while making the right content pane scroll internally on desktop.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] User clarified that the prior page-floor fill should be rolled back because the right-side content should not exceed the viewport height.
- [x] Confirmed the current shell issue in `frontend/src/features/garage/MyGaragePage.tsx`: the route root fills available space, but the right pane still grows with content instead of becoming the scroll container.
- [x] Constrained the desktop My Garage workspace to `calc(100vh - 9rem)` and moved overflow ownership to the right content pane with `lg:overflow-y-auto`.
- [x] Kept the desktop rail full-height within that visible workspace so the garage menu remains top-aligned and the `Account` section stays anchored at the bottom.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Desktop My Garage no longer expands with its routed content; the workspace stays within the viewport and the right pane scrolls internally.
- The left rail still fills the visible workspace height, with garage navigation at the top and `Profile & Settings` at the bottom.
- Residual risk: compile verification passed, but a live browser pass is still worth doing to confirm the new internal scrolling feels right in the Mechanics and Inventory pages.

---

# My Garage Content-Driven Height Restore (2026-03-16)

## Plan
- [x] Capture the correction that the My Garage page height should again follow the right-side content.
- [x] Roll back the viewport-constrained shell introduced in the last pass.
- [x] Keep the garage rail structure while restoring page-level expansion based on content height.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] User clarified that the intended behavior is the earlier content-driven page expansion, where the right-side content determines page height.
- [x] Confirmed the current issue in `frontend/src/features/garage/MyGaragePage.tsx`: the desktop shell uses a fixed `lg:h-[calc(100vh-9rem)]` plus internal right-pane scrolling, which conflicts with that model.
- [x] Removed the fixed desktop workspace height and internal right-pane scrolling so My Garage once again expands based on the routed content height.
- [x] Kept the garage rail structure and bottom-anchored `Account` / `Profile & Settings` action intact while restoring page-level height growth.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- My Garage is back to content-driven page height on desktop, matching the earlier implementation you referenced.
- The right pane no longer owns its own desktop scroll container; page height now follows the routed content again.
- Residual risk: compile verification passed, but I have not done a live browser pass to confirm the rail still visually lands where you want for both short and very tall garage pages.

---

# My Garage Screenshot Overflow Correction (2026-03-16)

## Plan
- [x] Capture the correction indicated by the screenshot: right-side My Garage content should not push the page below the viewport.
- [x] Reapply a viewport-constrained desktop shell for My Garage.
- [x] Keep the left rail full-height within the visible workspace while restoring internal right-pane scrolling.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] The screenshot confirms the problem with the last restore: tall Services content is stretching the full page below the viewport.
- [x] Locked the intended overflow owner for this pass to the desktop My Garage content pane, not the overall page.
- [x] Reapplied the desktop workspace height constraint and internal right-pane scrolling in `frontend/src/features/garage/MyGaragePage.tsx`.
- [x] Kept the left rail full-height within that visible workspace, with garage options at the top and `Account` / `Profile & Settings` anchored at the bottom.
- [x] Used Playwright against the live local app with a seeded garage-owner session and mocked tall Services data to verify the rendered page behavior directly.
- [x] Identified the remaining overflow root cause in Playwright: the My Garage route root was still computed as `flex: 1 1 0%` and rendered at `1187px` tall, so the fixed shell height was not actually taking effect.
- [x] Fixed that conflict by switching the My Garage root to `lg:flex-none` and tightening the desktop shell height to `calc(100vh - 9.25rem)`.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The screenshoted overflow issue is corrected: Playwright measured the Services page at `1301px` on a `1300px` viewport, which no longer exceeds the viewport beyond measurement noise, and the My Garage shell now computes to `1152px` instead of `1187px`.
- My Garage now behaves as a contained desktop workspace again, with scrolling owned by the right content pane instead of the overall page.
- Verification completed with real browser automation on the live local app plus `npm run build`; no further code-only assumption remains on this point.

---

# My Garage Width Cap Rollback (2026-03-16)

## Plan
- [x] Record the rollback of the unintended My Garage width cap.
- [x] Remove the centered max-width wrapper so My Garage fills the available dashboard width again.
- [x] Verify the change with frontend build and a Playwright width check.

## Progress Notes
- [x] Confirmed the current width reduction is caused by `mx-auto max-w-[1400px]` on `frontend/src/features/garage/MyGaragePage.tsx`.
- [x] Locked the rollback scope to width only: preserve the left rail and current overflow behavior, remove the unrequested workspace narrowing.
- [x] Removed the centered max-width wrapper from `frontend/src/features/garage/MyGaragePage.tsx` while leaving the rail width and desktop overflow behavior intact.
- [x] Verified with Playwright on the live Services page: on a `1920px` viewport, the My Garage wrapper now renders at `1845px` wide inside a `1909px` main content area, confirming the prior width cap is gone.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The unintended garage workspace narrowing has been rolled back; My Garage now fills the available dashboard width again.
- The left rail remains in place, but the right content area is no longer constrained by the old `max-w-[1400px]` wrapper.
- Residual risk: none specific to width after the Playwright check; any remaining spacing concerns would now be about the intentional left-rail footprint rather than a hidden outer width cap.

---

# Dashboard Mobile Work Queue Header Alignment (2026-03-16)

## Plan
- [x] Capture the correction that the Work Queue status update should stay on the same row as the section title on mobile.
- [x] Adjust the Work Queue header layout so the title row and refresh/last-updated chip remain inline on small screens.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] Confirmed the current issue in `frontend/src/features/dashboard/DashboardHome.tsx`: the Work Queue header uses a mobile `flex-col` layout, which drops the refresh/last-updated status chip below the title instead of keeping it inline.
- [x] Reworked the Work Queue header to use a single `justify-between` row on smaller screens, while keeping the title block flexible and the refresh/last-updated control fixed-width.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The Work Queue title and refresh/last-updated status chip now stay on the same header row on mobile instead of splitting into stacked rows.
- The change is intentionally narrow: only the Work Queue header flex behavior was adjusted, so the queue lanes and larger-screen layout remain intact.
- Residual risk: compile verification passed, but I have not done a live mobile browser pass to confirm the row still feels balanced with your exact font scaling and device width.

---

# Team Capacity Mobile UX Narrative Pass (2026-03-16)

## Plan
- [x] Audit the current Team Capacity mobile UX in code and against the supplied screenshot.
- [x] Capture the intended mobile narrative before editing: summary first, mechanic board second, no abstract utilization framing or nested mobile scroll trap.
- [x] Refactor Team Capacity so mobile uses a clearer floor snapshot and simplified mechanic cards.
- [x] Run targeted verification and capture review notes, including the UX-audit limitation if browser automation stays blocked.

## Progress Notes
- [x] Activated the `frontend-design` and `ux-audit` skills for this pass.
- [x] UX audit finding: the current mobile stack tells the same story three ways (`31 assigned`, `Team utilization`, per-mechanic load/status cards), but each block uses different language, which creates narrative conflict instead of clarity.
- [x] UX audit finding: the internal mechanic-list scrollbar adds a second scroll context on mobile, so users have to parse both a summary card and a nested board in a compressed space.
- [x] Locked the target mobile structure for this pass to `Team Capacity header -> Floor Snapshot summary -> Mechanic board list`, with concrete labels like jobs queued / techs ready instead of an abstract utilization percentage.
- [x] Replaced the `Team utilization` percentage slab with a `Floor Snapshot` card, clarified the header total to `jobs assigned`, and added a dedicated `Mechanic Board` subheading so the section reads top-to-bottom instead of as three competing summaries.
- [x] Simplified mechanic cards to one status pill plus `Active` / `Queued` stat tiles, prioritized the list by operational relevance, and removed the nested internal scroll behavior on mobile while preserving contained scrolling from `md` upward.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)
- [x] Attempted live browser UX verification with Playwright on the running local app, but the tool could not launch because Chrome immediately exited with `Opening in existing browser session`.

## Review
- Team Capacity now tells a clearer mobile story: the top card answers “what is happening on the floor right now,” and the mechanic list below answers “who should I tap next.”
- The old utilization percentage is gone because it was abstract and contradictory on mobile, especially in states like `0%` utilization with a large queued count.
- Mobile no longer traps the mechanic list inside its own scrollbar, which removes the nested-scroll friction you called out.
- Residual risk: compile verification passed, but the live mobile UX audit had to stop at code/screenshot analysis because Playwright could not take control of the browser in this environment.

---

# Team Capacity Desktop De-Emphasis Correction (2026-03-16)

## Plan
- [x] Capture the correction that the Team Capacity redesign should have remained mobile-only.
- [x] Identify which current desktop Team Capacity elements are taking too much height away from Work Queue.
- [x] Keep the clearer mobile narrative but compress desktop Team Capacity back to a low-emphasis summary and shorter mechanic cards.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the current desktop regression in `frontend/src/features/dashboard/DashboardHome.tsx`: the large `Floor Snapshot` block and the taller mobile stat-tile mechanic cards both apply at `lg+`, so Team Capacity is consuming vertical space that should go back to Work Queue.
- [x] Locked the corrected scope for this pass to `mobile keeps the new summary/card treatment`, `desktop gets compact snapshot chips plus denser mechanic cards`.
- [x] Moved the `Floor Snapshot` detail card back to mobile-only and converted desktop into compact inline snapshot chips in the Team Capacity header.
- [x] Recompressed desktop mechanic cards into shorter rows with inline active/queued/load text and a thinner load bar, while leaving the taller stat-tile layout in place below `lg`.
- [x] Tightened the desktop mechanic-board height cap so the section gives more vertical space back to Work Queue on larger screens.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Desktop Team Capacity is de-emphasized again: the snapshot metrics no longer occupy a full card, and mechanic cards no longer use the taller mobile treatment.
- Mobile keeps the clearer summary-first narrative from the previous pass, so the rollback is scoped to desktop density rather than a full reversion.
- Residual risk: compile verification passed, but I have not done a live desktop browser pass against your exact monitor width to confirm the reclaimed height feels right next to Work Queue.

---

# Team Capacity Header Count Deduplication (2026-03-16)

## Plan
- [x] Confirm whether the Team Capacity header count is duplicating the new summary metrics.
- [x] Remove the redundant top-right assigned count from the Team Capacity header.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the duplication in `frontend/src/features/dashboard/DashboardHome.tsx`: the header-level `assigned` count now repeats workload information already expressed by the Team Capacity snapshot pills/cards, especially when queued work is the primary operational signal.
- [x] Removed the top-right Team Capacity header count so the snapshot pills/cards are now the only workload-summary layer in that section.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The duplicated header count is gone, so Team Capacity no longer repeats workload totals in both the header and the summary pills/cards.
- The section header is cleaner and the remaining snapshot pills carry the summary role by themselves.

---

# Team Capacity Header Pill Alignment (2026-03-16)

## Plan
- [x] Confirm why the Team Capacity summary pills are not occupying the old top-right header slot.
- [x] Move the Team Capacity summary pills to the right side of the header on desktop.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the current issue in `frontend/src/features/dashboard/DashboardHome.tsx`: after removing the header count, the summary-pill wrapper still uses `lg:flex-1` with `lg:justify-center`, so the pills remain centered instead of shifting into the top-right header slot.
- [x] Replaced the centered desktop pill wrapper with a right-aligned `lg:ml-auto` / `lg:justify-end` header group so the summary pills now occupy the same top-right slot as the old header count.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The Team Capacity summary pills now sit on the right side of the desktop header, which matches the slot previously occupied by the removed count.
- The change is layout-only: the same summary pills remain, but they now anchor to the correct part of the header.

---

# Tenant Logo Import Flow (2026-03-16)

## Plan
- [x] Audit the current enrollment flow, tenant profile API, and any existing remote-image storage patterns.
- [x] Implement backend website-logo discovery/import during garage enrollment, with graceful fallback when no logo can be found.
- [x] Expose tenant logo management in the post-enrollment garage profile flow, including a manual import action from the saved website.
- [x] Add focused backend and frontend tests for the new behavior.
- [x] Run targeted verification and capture residual risks.

## Progress Notes
- [x] Confirmed enrollment already collects optional `website`, the tenant model already stores `website` and `logo_url`, and the garage profile API already persists `logo_url`.
- [x] Confirmed the settings UI currently exposes `website` but not `logo_url`, so post-enrollment editing is incomplete.
- [x] Confirmed Cloudinary is available in the backend and is the cleanest existing place to copy remote logos instead of hotlinking tenant sites.
- [x] Added `backend/app/services/website_logo_service.py` to discover likely tenant logos from explicit logo images, JSON-LD logo fields, touch icons, manifest icons, and favicon fallback, with SSRF guards against private/local hosts.
- [x] Wired automatic best-effort logo import into `/api/v1/auth/enroll-garage`; enrollment now continues even if logo discovery fails.
- [x] Added `POST /api/v1/admin/garage-profile/import-logo` so garage owners/admins can re-import a logo from the saved website later.
- [x] Extended `frontend/src/features/dashboard/UnifiedSettingsPage.tsx` with tenant logo preview, manual `logo_url` editing, clear action, and website-driven import action.
- [x] Added focused tests:
  `backend/tests/test_website_logo_service.py`
  `backend/tests/test_tenant_logo_import.py`
  `frontend/src/__tests__/UnifiedSettingsPage.test.tsx`
- [x] Passed targeted verification:
  `venv/bin/python -m pytest tests/test_website_logo_service.py tests/test_tenant_logo_import.py -q`
  `npm run test -- --run src/__tests__/UnifiedSettingsPage.test.tsx`
  `npm run build` (from `frontend/`)

## Review
- Tenant logos now import automatically during enrollment when a public website is provided, and garage owners/admins can re-import or override the logo later from Garage Profile settings.
- The discovery logic prefers explicit logo signals first and falls back through icons safely, while rejecting private/local network fetches to avoid turning website import into an SSRF hole.
- Residual risk: when Cloudinary is not configured, imported logos fall back to the discovered source URL instead of a copied hosted asset, so third-party hotlinking behavior still depends on the tenant site.

---

# Tenant Logo Import Heuristic Fix (2026-03-16)

## Plan
- [x] Reproduce why the current importer picks a secondary brand/logo asset instead of the lazy-loaded site header logo on `truckpitstop.com`.
- [x] Update website logo discovery to read lazy-load image attributes and prefer explicit site-logo containers over generic downstream brand images.
- [x] Add regression tests for lazy-loaded logo selection.
- [x] Run targeted backend verification and capture the remaining best-effort limitation.

## Progress Notes
- [x] Confirmed `truckpitstop.com` renders the desired header logo via `data-src=\"...Trasp-white-1080x400-1.png\"`, while the current importer only scores `<img src=...>` candidates.
- [x] Confirmed the current ranking gives generic `img.logo` hits the top priority, so a later page image like `Freightliner-Logo.png` can win when the actual header logo is lazy-loaded.
- [x] Updated `backend/app/services/website_logo_service.py` to read lazy-load image attributes (`data-src`, `data-lazy-src`, `data-original`, related WordPress file attrs, and srcset variants) instead of relying only on `src`.
- [x] Split image scoring so explicit site-logo class/id signals outrank generic filename matches, with a small bonus for wide wordmark-style aspect ratios.
- [x] Added a regression test proving a lazy-loaded header logo beats `Freightliner-Logo.png`.
- [x] Verified against the live tenant site markup with:
  `venv/bin/python - <<'PY' ... parse_website_logo_candidates('https://truckpitstop.com') ... PY`
  which now ranks `https://truckpitstop.com/wp-content/uploads/2025/01/Trasp-white-1080x400-1.png` first.
- [x] Passed targeted backend verification:
  `venv/bin/python -m pytest tests/test_website_logo_service.py tests/test_tenant_logo_import.py -q`

## Review
- `truckpitstop.com` now imports the intended lazy-loaded header logo instead of a downstream brand logo image.
- This remains a best-effort import heuristic, not a guarantee of the exact browser-rendered logo for every site. Sites that render logos through CSS backgrounds, JS-only hydration, shadow DOM, canvas, or viewport-conditional swaps can still differ from what static HTML inspection finds.

---

# Dashboard Attention Banner Work Queue Reclaim (2026-03-16)

## Plan
- [x] Inspect the dashboard manager layout and determine why dismissing `Attention Required` does not let `Work Queue` reclaim the freed viewport space.
- [x] Move the alert-dismiss visibility state into `DashboardHome` so dismissing the banner invalidates the queue height measurement immediately.
- [x] Verify the queue expands after dismissal with `npm run build` and a live Playwright check on the dashboard page.

## Progress Notes
- [x] Confirmed `DashboardHome` already measures the queue against the viewport, but the `Attention Required` dismissal lives inside `AlertsBanner`, so closing it never re-runs the parent measurement effect.
- [x] Lifted the attention-banner dismissal state into `DashboardHome` and wired `AlertsBanner` to an `onDismiss` callback so the queue height recalculates when the banner is removed.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)
  Playwright on mocked `http://localhost:5173/dashboard` measured `Work Queue` at `736px` tall with the banner present, then `852px` tall after dismissing `Attention Required`, while the queue bottom alignment stayed pinned to the same viewport floor.

## Review
- `Attention Required` now behaves like a temporary layout participant instead of a dead-end height cap: when it is visible it consumes vertical space, and when it is dismissed the queue expands immediately into that reclaimed area.
- The fix is state ownership, not new height math. `DashboardHome` now owns the banner visibility state, so the existing viewport-fit measurement reruns at the correct time.

---

# Inventory Toolbar And Overflow Cleanup (2026-03-16)

## Plan
- [x] Inspect the inventory page layout and identify which elements own overflow on desktop.
- [x] Move the desktop `Search in` filters into the same top toolbar as the search input so the header consumes less vertical space.
- [x] Constrain the desktop inventory workspace to the available page height so the list/cards area owns the only intended scroll region.
- [x] Verify with `npm run build` and local browser inspection that the extra page scrollbar is gone in desktop inventory.

## Progress Notes
- [x] Confirmed `InventoryPage` rendered a separate desktop `Search in` row above a second desktop table/card shell, while list view also used its own `overflow-y-auto max-h-[calc(100vh-260px)]`.
- [x] Rebuilt the desktop toolbar so the search input, `Search in` filters, and `Add part` action live in one row when space allows.
- [x] Switched the desktop inventory shell to a `flex-1 min-h-0` layout so cards/list content owns the vertical scroll instead of stacking a nested max-height container on top of the garage pane scroll.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)
  Playwright on mocked `http://localhost:5173/dashboard/garage/inventory` confirmed the desktop toolbar renders on a single 42px row and the garage content pane no longer overflows (`clientHeight=1023`, `scrollHeight=1023`) while the inventory list remains the sole vertical scroller (`clientHeight=908`, `scrollHeight=1228`).

## Review
- Desktop inventory now uses one top toolbar for search context and action controls, which frees vertical space before the list shell.
- The double-scroll issue is resolved by making the inventory workspace height-aware and giving the list/cards region the only intentional desktop overflow.

---

# Inventory Toolbar Height Refinement (2026-03-16)

## Plan
- [x] Remove the `Search in:` label from the desktop inventory toolbar.
- [x] Normalize the quick-filter control height to match the search field and `Add part` button.
- [x] Verify the refined toolbar layout in build output and browser rendering.

## Progress Notes
- [x] Removed the standalone `Search in:` label so the segmented quick filters read as a direct companion control to the search input.
- [x] Set the desktop filter group and `Add part` button to the same 42px control rail as the search field.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)
  Playwright on mocked `http://localhost:5173/dashboard/garage/inventory` confirmed the label is gone and the visible desktop search field, filter rail, and `Add part` button all render at `42px` tall.

## Review
- The desktop inventory toolbar is now visually cleaner: the segmented quick filters sit directly beside the search field without a redundant label.
- All three adjacent controls now share the same 42px height, so the toolbar reads as one aligned control rail instead of mixed-sized elements.

---

# Tenant Branding Cycle (2026-03-16)

## Plan
- [x] Audit every tenant-facing logo render point and confirm which payloads already expose tenant branding.
- [x] Add a shared tenant-logo rendering path with Diesel Bridge fallback and permanent super-admin override.
- [x] Expose tenant logo data to quote/invoice/customer-facing flows that currently lack it.
- [x] Update garage settings cache invalidation so tenant branding changes propagate through active sessions.
- [x] Add focused tests for tenant-logo fallback behavior.
- [x] Run targeted verification and capture residual risks.

## Progress Notes
- [x] Confirmed the current hardcoded platform-logo render points are `DashboardLayout`, `CustomerPortalPage`, and `QuoteApprovalPage`.
- [x] Confirmed `InvoiceAccessPage` does not render the Diesel Bridge mark today, but it is a tenant-branded customer flow and should use tenant branding in its header.
- [x] Confirmed tenant logo storage already exists on `tenant.logo_url`, while customer-facing quote/invoice token responses do not yet expose that field.
- [x] Confirmed Super Admin can remain on the existing Diesel Bridge path by short-circuiting tenant-branding lookup for `super_admin`.
- [x] Added `/api/v1/auth/tenant-branding` plus `tenant_logo_url` on `/api/v1/auth/me`, so authenticated tenant users can resolve branding from one shared source.
- [x] Added `TenantBrandLogo` + `useTenantBranding` on the frontend and wired them into the garage dashboard shell and customer portal nav.
- [x] Extended quote token and invoice-access responses with `shop_name` and `shop_logo_url`, then rendered tenant branding on quote approval and invoice pages.
- [x] Extended invoice access links with `shop_logo_url` query params so the invoice error state can still show tenant branding when the token cannot resolve.
- [x] Updated Garage Profile saves/imports to refresh the shared tenant-branding cache and persisted auth user branding fields immediately.
- [x] Added focused tests:
  `backend/tests/test_auth_endpoints.py`
  `backend/tests/test_tenant_branding_surfaces.py`
  `frontend/src/__tests__/TenantBrandLogo.test.tsx`
- [x] Passed targeted verification:
  `cd backend && venv/bin/python -m pytest tests/test_auth_endpoints.py tests/test_tenant_branding_surfaces.py tests/test_tenant_logo_import.py -q`
  `cd frontend && npm run test -- --run src/__tests__/TenantBrandLogo.test.tsx src/__tests__/UnifiedSettingsPage.test.tsx`
  `cd frontend && npm run build`

## Review
- Tenant branding is now a full-cycle fallback model: garage staff and customer portal users see the tenant logo when one exists, quote/invoice customer flows receive the tenant logo from their token payloads, and Diesel Bridge remains the fallback when no tenant logo is available.
- Super Admin stays permanently on the Diesel Bridge brand because tenant-branding fetches are disabled for that role and the dashboard shell still renders the platform mark explicitly in that path.
- Residual risk: imported website logos can still be visually mismatched for some surfaces if the tenant site only exposes a light-on-transparent header asset. The product fallback is still functional, but those tenants may need to replace the imported logo with a more universal asset in Garage Profile.

---

# Playwright Localhost Diagnosis (2026-03-16)

## Plan
- [x] Inspect the repo's Playwright configuration and determine whether a project-specific MCP server is required.
- [x] Check the frontend/backend local host bindings and ports that Playwright depends on.
- [x] Document the likely cause of the flaky localhost access and the stable setup path.

## Progress Notes
- [x] Confirmed the repo already has Playwright test-runner config at `e2e/playwright.config.ts`; it does not depend on a project-defined MCP server.
- [x] Confirmed Playwright test config expects the frontend at `http://localhost:5173` and starts the backend on port `8000` plus the frontend Vite dev server automatically via `webServer`.
- [x] Confirmed `frontend/vite.config.ts` sets port `5173` but does not pin `server.host`, while its proxy targets `http://127.0.0.1:8000`.
- [x] Observed the active local frontend listener on `[::1]:5173` and backend listeners on `127.0.0.1:8000`, which means the stack is currently split between IPv6 localhost and IPv4 loopback.
- [x] Captured the operational conclusion: the flaky browser-tool behavior is more consistent with startup timing and localhost resolution mismatch than with missing Playwright/MCP infrastructure.

## Review
- This project does not need an extra MCP server for normal Playwright tests. Running `cd e2e && npx playwright test` should be sufficient once Playwright browsers are installed.
- If an AI browser tool is being used instead of the Playwright test runner, the tool still needs the app servers to be reachable from the same environment; `localhost` can fail intermittently when frontend and backend bind to different loopback families.
- The stable fix path is to bind both dev servers explicitly to the same host, preferably `127.0.0.1`, and use that exact host in Vite, the backend launch command, and Playwright `baseURL`.

---

# Playwright Host Pinning (2026-03-16)

## Plan
- [x] Update the Playwright config to use `127.0.0.1` consistently for `baseURL` and the managed backend server command.
- [x] Update the Vite dev server config to bind explicitly to `127.0.0.1`.
- [x] Run focused verification and capture any residual risk.

## Progress Notes
- [x] Confirmed the required pinning points are `e2e/playwright.config.ts` and `frontend/vite.config.ts`.
- [x] Changed Playwright `baseURL` to `http://127.0.0.1:5173`.
- [x] Updated the Playwright-managed backend launch to `venv/bin/python -m uvicorn ... --host 127.0.0.1 --port 8000` so it uses the repo's actual backend interpreter instead of relying on a missing bare `python` binary.
- [x] Updated the Playwright-managed frontend launch to pass `--host 127.0.0.1` explicitly.
- [x] Added `server.host = '127.0.0.1'` to `frontend/vite.config.ts` so manual `npm run dev` sessions bind to IPv4 loopback consistently.
- [x] During verification, fixed two stale Playwright expectations that no longer matched the current UI:
  `e2e/tests/staff-login.spec.ts`
  `e2e/tests/invoice-access.spec.ts`
- [x] Passed focused verification:
  `cd frontend && npm run build`
  `cd e2e && npx playwright test --list`
  `cd e2e && npx playwright test tests/staff-login.spec.ts --project=chromium --grep "shows login form"`
  `cd e2e && npx playwright test`

## Review
- Playwright is now pinned to a single loopback address family end-to-end instead of mixing `localhost`, IPv6, and IPv4 bindings.
- The e2e runner is more reliable in this repo because it now uses the checked-in backend virtualenv rather than assuming `python` exists on the shell PATH.
- Residual risk: local commands or docs elsewhere in the repo that still reference plain `localhost` may continue to work, but they will not benefit from this stricter IPv4 pinning unless updated separately.

---

# Scoped Commit Shipping (2026-03-16)

## Plan
- [x] Inspect the mixed working tree and generate draft scopes with the `scoped-commit-assistant` skill.
- [x] Refine the draft into atomic commit boundaries based on the actual diffs.
- [x] Re-run targeted validation so each commit message can cite real commands.
- [x] Stage and commit each scope with structured commit messages.
- [x] Record the shipped commit order and validation summary.

## Progress Notes
- [x] Ran `python3 /Users/sergio/.agents/skills/scoped-commit-assistant/scripts/suggest_scoped_commits.py --mode all` and treated the output as a draft, not the final boundary.
- [x] Refined the plan into four commits: inventory desktop layout, garage-logo copy cleanup, Playwright/Vite host pinning, and task documentation.
- [x] Re-ran targeted verification before staging:
  `cd frontend && npm run build`
  `cd e2e && npx playwright test --list`
  `cd e2e && npx playwright test`
- [x] Shipped the scoped commits in this order:
  `fix(inventory): unify desktop toolbar and scroll ownership`
  `fix(settings): remove misleading garage logo status copy`
  `fix(e2e): pin local test servers to 127.0.0.1`
  `docs(tasks): capture scoped shipping notes`

## Review
- The mixed working tree is now split into atomic commits instead of one broad checkpoint, so inventory UI work, garage copy cleanup, Playwright host pinning, and task docs each have their own history entry.
- Validation cited in the commit bodies comes from commands re-run during this shipping pass, not placeholder text from the planner output.

---

# Repair Operation Memory Zero-Hour Correction (2026-03-19)

## Plan
- [x] Audit the repair-operation search/apply/update flow and confirm why new custom operations are being reused with `0.00` hours.
- [x] Update the labor-memory rules so only positive-hour repair operations are learned and reused.
- [x] Ignore previously stored zero-hour memory rows during search/recalc so existing bad data stops surfacing.
- [x] Add targeted backend tests for the zero-hour custom-operation path.
- [x] Run focused verification and capture review notes.

## Progress Notes
- [x] Confirmed the current internal flow: library defaults seed known operations, tenant-specific `labor_operation_memory` stores learned hours by normalized vehicle signature, and unknown searches fall back to a custom operation with `0.00` hours.
- [x] Confirmed the bug: `add_repair_operation_line()` immediately upserts internal memory even when a brand-new custom operation still has `0.00` hours, so the system "learns" and reuses an empty estimate before staff enter real hours.
- [x] Updated `PriceBuildService` so labor memory only reads and writes positive-hour entries; zero-hour rows are ignored during search, apply, and recalc.
- [x] Added regression tests covering both the new custom-operation path and legacy zero-hour memory rows.
- [x] Passed focused verification:
  `cd backend && venv/bin/python -m pytest tests/test_price_build_service.py -q`

## Review
- Custom repair operations now behave as "unlearned" until someone enters real hours on the RO line; only then do they become reusable memory for matching vehicles.
- Existing zero-hour memory rows no longer win search/apply/recalc decisions, so they stop poisoning the internal labor library without requiring an immediate data cleanup.
- Residual risk: the UX still applies unknown custom operations at `0.00` hours first and expects staff to edit the line afterward; the next refinement should be a custom-operation hours prompt in the repair-order UI so teaching happens at apply time instead of as a second step.

---

# Frontend Mobile UX Shipping (2026-03-20)

## Plan
- [x] Inspect the staged and unstaged frontend diffs and define clean commit boundaries instead of pushing one mixed change set.
- [x] Confirm how the shared select-component changes are consumed so they land with the right feature scope.
- [x] Record the final commit scopes and push plan.
- [x] Run targeted frontend verification for the combined shipping state.
- [x] Commit each scope with structured messages and push to `origin/main`.

## Progress Notes
- [x] Confirmed the current worktree is almost fully staged, with one extra unstaged follow-up in `frontend/src/features/dashboard/DashboardHome.tsx`.
- [x] The scoped-commit planner suggested one broad frontend refactor, but diff review shows three better scopes:
  `messages` for the inbox/compose redesign plus shared customer select support,
  `dashboard` for shell overflow management and mobile work-queue behavior,
  `repair-orders` for the filter rail and price-builder input refinements.
- [x] Confirmed the new `CustomerSelect` dark-mode and phone-capture props are currently consumed by `MessagesInboxPage`, while the repair-orders diff is limited to layout/scroll and price input behavior.
- [x] Re-ran targeted verification for the combined shipping state:
  `cd frontend && npm run build`
  `git diff --check`
- [x] Shipped the scoped commits in this order:
  `fix(dashboard): tighten shell overflow and mobile cockpit`
  `feat(messages): redesign inbox and outbound compose flow`
  `fix(repair-orders): streamline filters and rate editing`
  `docs(tasks): capture mobile frontend shipping notes`

## Review
- The frontend shipping set is now split by user-facing intent instead of one oversized checkpoint, which keeps dashboard shell work, inbox UX, and repair-order refinements independently reviewable.
- Validation for the shipped state is a fresh frontend build plus a clean diff check, which is appropriate for this UI-only batch.

---

# Mobile KPI Hide (2026-03-20)

## Plan
- [x] Identify the dashboard KPI section and its current responsive wrapper.
- [x] Hide the KPI section on mobile screens at the outer container level.
- [x] Verify the responsive behavior with build output and a browser check.

## Progress Notes
- [x] Confirmed the KPI section is the manager-only `Revenue KPIs` card at the bottom of `DashboardHome`.
- [x] Updated the KPI wrapper to stay hidden below `lg`, which removes the entire section from mobile instead of only hiding inner content.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)
  Playwright on mocked `http://localhost:5173/dashboard` confirmed `Revenue KPIs` is not visible at `390px` width and becomes visible again at `1280px`.

## Review
- The KPI section is now absent from mobile screens because the entire outer card is hidden below `lg`.
- Desktop behavior is preserved: the same `Revenue KPIs` card still renders once the viewport reaches desktop width.

---

# Mobile Work Queue Priority Layout (2026-03-20)

## Plan
- [x] Inspect the current mobile dashboard shell and identify why Work Queue does not own the remaining viewport space above Team Capacity.
- [x] Refactor the mobile dashboard layout so transient top sections stay above a remaining-space frame, with Work Queue as `flex-1` and Team Capacity anchored below it.
- [x] Verify on mobile that dismissing `Attention Required` expands Work Queue while Team Capacity stays pinned to the same bottom slot.

## Progress Notes
- [x] Confirmed the mobile dashboard still flowed as content: `DashboardHome` was not a viewport-bounded flex item on mobile, `Work Queue` only had `flex-1` at `lg`, and the active mobile lane used fixed pixel heights instead of filling the remaining queue area.
- [x] Updated `DashboardHome` to be a full flex child of the dashboard viewport on mobile, wrapped `Work Queue` + `Team Capacity` in a `flex-1 min-h-0` frame, and switched mobile lane sizing from fixed heights to active-lane flex expansion.
- [x] Verified on a mocked mobile dashboard in Playwright (`390x844`) that dismissing `Attention Required` increased `Work Queue` height from `377.25px` to `516.25px` while `Team Capacity` stayed pinned at the same bottom position (`bottom: 775px` before and after).
- [x] Confirmed the mobile dashboard shell itself did not start page-scrolling after the change: the route scroller stayed `clientHeight=767` and `scrollHeight=767` before and after dismissing the banner.

## Review
- `DashboardHome` now treats mobile the same way as desktop in terms of section priority: `Work Queue` owns the remaining viewport space, and `Team Capacity` remains the bottom sibling inside that shared frame.
- Dismissing `Attention Required` no longer leaves dead space on mobile; the queue immediately reclaims the banner footprint while keeping `Team Capacity` anchored below it.
- Verification completed with `npm run build` in `frontend/` plus Playwright mobile layout checks against mocked dashboard data.

---

# Dashboard Profile Trigger Refresh (2026-03-20)

## Plan
- [x] Inspect the shared dashboard header to locate the outdated profile icon treatment and compare it against the current application UI language.
- [x] Replace the old animated circular profile trigger with a cleaner profile control that matches the dashboard and Settings styling.
- [x] Verify the updated profile trigger in-browser and with a frontend build.

## Progress Notes
- [x] Confirmed the stale treatment lives in `frontend/src/components/layout/DashboardLayout.tsx`: the desktop settings trigger still renders a custom animated circular SVG ring that no longer matches the card-based industrial styling used elsewhere in the app.
- [x] Replaced the ringed icon with a compact rounded profile tile that uses the signed-in user’s monogram, a subtle accent wash, and a small live-status dot derived from the same visual language as the Settings avatar.
- [x] Verified on the live desktop dashboard in Playwright that the header now exposes `Open profile settings for Alexandru Popescu` with `AP` rendered inside a rounded tile, and that the trigger contains no legacy SVG ring markup (`hasSvg: false`, `pathCount: 0`).

## Review
- The outdated animated circle is gone from the shared dashboard header; the settings trigger now reads like a native part of the app instead of a standalone ornament.
- The new profile control preserves the existing nav footprint while aligning with the card-based industrial styling used in Settings and the rest of the dashboard.
- Verification completed with `npm run build` in `frontend/` plus a Playwright desktop inspection against the live dashboard.

---

# Landing Page Approved Partners (2026-04-11)

## Plan
- [x] Confirm the minimal public partner metadata the app already stores and identify the extra landing-page fields each approved business needs to control from the garage dashboard.
- [x] Add backend storage and response models for partner-display metadata plus a public endpoint that returns approved active businesses for the landing page.
- [x] Extend the garage profile settings so each garage owner/admin can edit the public partner details that appear on the landing page.
- [x] Implement a landing-page partner section that shows all approved businesses in a moving rail plus a static detail grid without hardcoded placeholders.
- [x] Run targeted backend/frontend verification and capture residual risks in this file.

## Progress Notes
- [x] Confirmed the current garage profile already persists `website` and `logo_url`, so the partner section can reuse existing backlink/logo fields instead of inventing a second branding source.
- [x] Added tenant-level partner metadata fields: `partner_summary` and `partner_services`, plus Alembic migration `044_add_landing_partner_fields.py`.
- [x] Added public endpoint `GET /api/v1/auth/landing-partners` that returns approved active businesses only.
- [x] Extended `Garage Profile` settings so garage owners/admins can edit the landing-page summary and service-focus copy for their own business.
- [x] Added a landing-page partner band with an auto-scrolling rail plus a static partner grid driven entirely by approved businesses from the backend.
- [x] Passed targeted verification:
  `./.venv/bin/python -m pytest backend/tests/test_landing_partners_endpoint.py backend/tests/test_tenant_logo_import.py -q`
  `npm run test -- --run src/__tests__/LandingPage.test.tsx src/__tests__/UnifiedSettingsPage.test.tsx` (from `frontend/`)
  `npm run build` (from `frontend/`)
  `curl -I http://127.0.0.1:4173/`
- [x] Added stable backend test defaults for Twilio env vars in `backend/tests/conftest.py` so admin endpoint tests do not require real credentials during collection.

## Review
- Approved active businesses now feed a concrete landing-page partner section without hardcoded placeholders.
- Garage owners/admins can control the public partner copy from `Garage Profile`, while approval status remains the gate for inclusion on the landing page.
- Residual risk: approved businesses without curated `partner_summary` or `partner_services` fall back to generic copy until those new profile fields are filled in.
