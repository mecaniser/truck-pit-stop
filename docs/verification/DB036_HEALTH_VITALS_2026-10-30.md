**Health-vitals outcome released:** PR714 merged17608d10; exact web/API and worker production verification complete. [Final release evidence](DB036_HEALTH_VITALS_RELEASE_2026-10-30.md). Historical gate snapshots below are retained.

# DB-036 health vitals implementation — 2026-10-30

Owner: Backend & Integrations. Branch: `codex/health-truck-vitals`, base `9dea1f1ae58a62d10d741113275fae0a371085c5`. Contract: `docs/DB036_HEALTH_VITALS_CONTRACT.md`. No migration or external endpoint change.

## Changes

Health collector reads visible vehicle-summary odometer and engine-hours fields, verifies exact provider route and VIN before and after the read, parses explicit mi/km and hours, preserves zero and marks absent/ambiguous/invalid values unavailable. It reuses the existing verified vehicle summary reader. Vitals remain independent of fault availability.

Importer uses separate deterministic vitals request IDs inside the existing health receipt transaction. Existing telemetry contract enforces admin/tenant/VIN/current membership; source read must be within the same current membership. Dry-run savepoints leave no telemetry, commit/replay/recovery retain immutable source identity, and saved IDs are checked after commit. Provider observation time stays null; dashboard source read becomes snapshot capture time. Canonical vehicle mileage is untouched. Old source documents without vitals remain supported.

Popup receives existing detail telemetry and displays mileage and engine hours above fault codes with source/capture information and unknown observation-time copy. Missing vitals remain unavailable even when fault checks are healthy; fault-query failures do not hide vitals.

## Verification

- Backend diagnostics, worker and adjacent fleet telemetry: 63 passed (includes 34 diagnostics cases).
- Collector Node suite: 8 passed, including units, decimal/comma formatting, zero, missing, malformed, ambiguous, range limits and km conversion.
- Frontend popup and detail hardening: 22 passed, including vitals with failed fault query and unavailable vitals with an explicit empty fault check.
- Changed-source Ruff and ESLint, TypeScript, production Vite build (3328 modules) and diff integrity pass.
- Independent QA agent `/root/qa`: offline GO; independently 34 backend,22 frontend,8 collector passed. Independent Security/Architecture `/root/security`: local GO, no blocking finding. Implementer did not issue these gates.

## Local runtime receipt and limits

Preflight read/run before implementation. Intended worktree `/Users/sergio_m1_promax/GitHub/truck-health-vitals`, clean base above before edits. Shared frontend5173 PID74219 serves unrelated machined-sidebar worktree; Docker8000 mounts that same unrelated backend. Both preserved. Intended backend/.env absent; no secrets copied, no database migration or feature/provider changes. Authenticated full-stack runtime is blocked/mismatched.

Explicit alternate synthetic preview: `http://127.0.0.1:5206/tests/health-vitals-preview.html`, frontend PID11001 sourced from this worktree. Vite branch/SHA set to intended branch/base; proxy explicitly points closed local port9 and Axios fixture answers in memory. This is a real-component browser fixture, not authenticated backend acceptance. Playwright shows mileage692,224.14mi and engine-hours23,520h alongside SPN639/FMI2 at1280px desktop and390x844 mobile. Mobile document width390, panel bounds x16/right374/top168.8/bottom622.1; no overflow. Escape closes and restores trigger focus. Synthetic screenshots local `/tmp/health-vitals-desktop.png`, `/tmp/health-vitals-mobile.png`. No runtime claim for live Motive selectors or fleetwide collection; live provider read and a post-deploy committed source/readback remain required.

No production job trigger, retry, import, configuration change, merge or deployment occurred. Release and live acceptance remain pending; not Done.


## Authorized live candidate verification follow-up

User authorized live checks, then protected merge/deployment and production popup verification in that order. Main was merged without losing either board entry (`7d6bd39c`). Candidate live gate exposed a real source-layout gap: summary fields include mileage but omit engine hours. The incomplete collection was stopped without import. A small authenticated rendered-DOM probe confirmed Live > Other details uses visible `table.detail-table` label/value rows. Correction `b8d3b6d1` follows Live from the verified vehicle summary, validates exact provider route and table VIN, and reads both measurements. Fatal identity contradictions abort; unavailable Live falls back only to verified summary data. Both independent reviewers issued refreshed offline GO; collector9/9 passes. Backend63/63 and frontend22/22 pass after the main merge; changed-source lint passes.

Fresh corrected candidate collection finalized all21 source rows with company and directory checks before/after.20 rows expose both measurements; one source VIN unavailable remains unavailable. Exact source window is 2026-10-31T02:50:56.440Z through 2026-10-31T02:57:52.989Z. Source identity SHA256 `8a563943a0c1218707e52b4ae019fbe3a6c428a87a1c6830f6663e33cbf99960`. Raw artifacts remain private under local `/tmp/db036-health-vitals-live/`; no VINs or authenticated HTML committed.

A read-only production scope lookup verified the existing exact77 CARGO LLC fleet and21 active memberships. Existing health service has no `MOTIVE_HEALTH_FLEET_CUSTOMER_ID`; candidate validation deliberately pinned the verified fleet without mutating service configuration. One additional source vehicle failed that current-fleet scope and was excluded, never reassigned. The source read/import was executed using existing health-service credentials in child-process memory and candidate import modules loaded only in memory on the active API host; deployed files were not overwritten.

Candidate dry-run validated without committing. Explicitly authorized commit created19 vitals snapshots and17 diagnostic captures; three diagnostic source rows unavailable and two current fleet trucks source-missing remain distinct categories (counts must not be added as distinct trucks). Receipt reached verified, then exact-source recovery/replay returned19 vitals and17 diagnostic captures unchanged. Readback checked exact source values, source-read capture timestamps, null observation timestamps and canonical service mileage unchanged. Existing fleet projection for truck603 returned692,224.14mi and23,520h, matching authenticated Motive source observation. No identity/membership guard was bypassed.

Release remains held on the user's requested authenticated UI gate: parent session lacks a signed-in DieselBridge session and awaits the user's fresh sign-in/code. At b8d3b6d1, protected Frontend checks, Backend tests, dependencies and Migration graph passed; Playwright smoke remains running at this snapshot. A documentation-only evidence commit follows and needs current-head CI. No merge or deployment occurred.

For eventual worker rollout, preserve the verified candidate fleet scope by deliberately setting existing `MOTIVE_HEALTH_FLEET_CUSTOMER_ID` to the exact verified77 CARGO LLC fleet ID before activation; otherwise the optional default is broader than this validated import. That configuration mutation has not been performed. Preserve current cron, volume and other provider settings. After authorized merge/deploy, verify exact served web build, worker source revision and a committed scheduled/canary source plus signed-in popup603 values. Candidate import success alone is not deployment evidence.
