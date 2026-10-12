# DB-098 shop-wide search verification

2026-10-12. Owner: Frontend & UX. Fast UI lane, existing APIs only.

## Implemented

Staff-shell Search shop button and Cmd/Ctrl+K dialog compose existing customer, vehicle, repair-order and inventory searches. Requests are debounced, bounded to five per source, canceled on unmount, and keyed to the authenticated session/query. Closed and short queries do not fetch. Sources fail independently with retries. Role-aware navigation opens the actual customer, truck, job or part in existing workspaces; customer and inventory deep links now resolve off-page records. Keyboard navigation, Escape and focus restoration are supported. No API/schema/auth/provider changes.

The functional comparison and priority rationale are in `docs/ETS_FUNCTIONALITY_AUDIT.md` (DB-101).

## Automated evidence

- 84 focused tests pass: shop search21, shell9, customer workspace18, parts workspace34, legacy inventory2.
- TypeScript passes. Changed-source strict ESLint passes apart from `InventoryPage.tsx`'s unchanged baseline of 10 errors and 2 warnings, compared against HEAD by the implementation owner.
- Production build passed before final singleton-copy and same-part mobile reopening fixes; final combined-tree build will be recorded with preview acceptance.
- No independent specialist gate required for this existing-contract UI change; protected PR CI remains the integration gate.

## Signed-in local browser evidence

IAB desktop and 390×844 responsive viewport, using a new synthetic tenant created by the repository's `seed_performance_environment.py` inside the isolated clone. No real record/provider writes.

- Search “Performance” returns grouped customer, repair-order and inventory results with five-result bounds and source-empty states.
- Customer result opens the matching customer detail.
- “C-0001” returns the exact truck and RO. ArrowDown then Enter opens truck detail with the expected unit, VIN and repair history.
- Mobile “PERF-PART-0001” fits at390px (`scrollWidth === innerWidth`) and opens the matching legacy inventory management dialog. No save/stock action submitted.
- Screenshots retained locally under `output/ets-parity/`; fixture-only, not committed.
- New staff presentation and combined-preview regression evidence follows in the integration receipt. Component tests cover both presentations and same-part reopening.

## Runtime receipt

2026-10-12, branch `codex/ets-workflow-parity`, baseline `91045a6`, uncommitted feature edits at observation. Frontend `http://127.0.0.1:5174`, PID48293, cwd this checkout's `frontend`; Vite API target explicitly `http://127.0.0.1:8001`. API container `dieselbridge_api_ets-workflow-parity` (`236ab61b…`), image `truck-pit-stop-api`, binds this checkout's `backend` to `/app`, localhost8001→8000. Both direct8001 and proxied5174 `/health/ready` return200 with database/Redis healthy. Login and search travel through the frontend proxy and return the newly seeded tenant's records. Rendered branch indicator and new search corroborate source ownership.

Database `truckpitstop_ets_workflow_parity_20261012` was cloned from local `truckpitstop` and migrated149→164; original database retained at149. Redis database9. Existing provider sandbox settings retained; no live rails, worker or tenant-flag activation. Default5173 belongs to another worktree and was preserved. User explicitly approved5174/8001. This receipt expires when the combined preview replaces these task-owned services.

Status: source and scoped signed-in browser acceptance, pending combined preview, PR/CI, merge and deployment. Not Done or live.

## Combined preview completion — 2026-10-12

Final TypeScript/Vite production build passed on preview `b03cf1f9` containing DB098 `4462851a`, DB099 `724c4249` and DB100 `6b1eac5b`. Updated API/frontend both serve `/Users/sergio_m1_promax/.codex/worktrees/ets-parity-preview/truck-pit-stop` at approved5174/8001, VitePID52233/API container42e9f351, same isolated DB at164/Redis9. Direct and proxied readiness200 plus rendered branch indicator confirmed.

Additional signed-in acceptance switched only the synthetic QA tenant to Modern using the normal settings UI. Search opens the actual selected-part inspector on desktop and390px. Back to parts → search the same part → choose it reopens the inspector. Escape closes search and restores focus to Search shop. Singular result count corrected. No customer/provider/financial mutation. Existing Classic customer/truck/part checks and new Modern checks pass. PR/CI, merge and release remain separate.
