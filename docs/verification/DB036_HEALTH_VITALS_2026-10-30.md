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
- Changed-source Ruff and ESLint, TypeScript and diff integrity pass. Production build result recorded by parent if still running at handoff.
- Independent QA agent `/root/qa`: offline GO; independently 34 backend,22 frontend,8 collector passed. Independent Security/Architecture `/root/security`: local GO, no blocking finding. Implementer did not issue these gates.

## Local runtime receipt and limits

Preflight read/run before implementation. Intended worktree `/Users/sergio_m1_promax/GitHub/truck-health-vitals`, clean base above before edits. Shared frontend5173 PID74219 serves unrelated machined-sidebar worktree; Docker8000 mounts that same unrelated backend. Both preserved. Intended backend/.env absent; no secrets copied, no database migration or feature/provider changes. Authenticated full-stack runtime is blocked/mismatched.

Explicit alternate synthetic preview: `http://127.0.0.1:5206/tests/health-vitals-preview.html`, frontend PID11001 sourced from this worktree. Vite branch/SHA set to intended branch/base; proxy explicitly points closed local port9 and Axios fixture answers in memory. This is a real-component browser fixture, not authenticated backend acceptance. Playwright shows mileage692,224.14mi and engine-hours23,520h alongside SPN639/FMI2 at1280px desktop and390x844 mobile. Mobile document width390, panel bounds x16/right374/top168.8/bottom622.1; no overflow. Escape closes and restores trigger focus. Synthetic screenshots local `/tmp/health-vitals-desktop.png`, `/tmp/health-vitals-mobile.png`. No runtime claim for live Motive selectors or fleetwide collection; live provider read and a post-deploy committed source/readback remain required.

No production job trigger, retry, import, configuration change, merge or deployment occurred. Release and live acceptance remain pending; not Done.
