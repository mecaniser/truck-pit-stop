# DB-099 recommended work carry-forward

## Implementation handoff — 2026-10-12

- Board ID: DB-099.
- From / To: Backend & Integrations implementation agent `/root/recommended_work` → Product & Delivery Lead for fresh independent QA/Security assignment.
- Branch: `codex/recommended-work-carry-forward`, base `91045a6`; worktree `/Users/sergio_m1_promax/.codex/worktrees/recommended-work-carry-forward/truck-pit-stop`.
- Contract: [v1 approved aggregate read](../contracts/db099-recommended-work-carry-forward.md). No schema migration, source mutation, pricing or payer change.
- User outcome: owner/admin/receptionist can see unresolved recommendations on a selected truck's other orders, ordered by urgency/date, and open the source order.

## Scope implemented

Static `GET /api/v1/repair-orders/recommended-work` route, before dynamic order routes; bounded pages, exact canonical truck and optional customer/context-order filters, generic context errors, reduced response, and `no-store` (existing security middleware adds `private`). Role gating uses the existing active-user dependency with the contract's explicit three-role allowlist and `Access denied` response. Existing per-order role behavior is unchanged.

Every source join enforces tenant identity, active source/customer/vehicle state, and unresolved unlinked recommendations. Current customer linkage uses tenant-scoped `EXISTS` for active effective owner/operator relationships or the legacy pointer. Count and page use identical predicates; source PK joins and EXISTS cannot multiply IDs. No per-row ORM fetches.

New staff-only `RecommendedWorkPanel` is supplied to the current PriceBuilder shell through an optional ReactNode slot inside its scroll area and rendered directly in the legacy shell. It displays priority, description, recorded date and whole source-order link. It has explicit loading/empty/error/refresh/paging states, 25-row pages, cancellation signals and context-keyed remounts to clear old rows immediately. Query keys include tenant, truck, customer, context order, skip and limit. Returning refetches; existing add/resolve/delete invalidates the recommended-work prefix. No new mutation controls or requests.

## Automated evidence

All commands below run in the worktree above, with frontend commands run in its `frontend/` directory.

```sh
/Users/sergio_m1_promax/GitHub/truck-pit-stop/backend/venv/bin/python -m pytest backend/tests/test_db099_recommended_work.py backend/tests/test_db003_recommended_service_tenant_boundary.py -q --disable-warnings --maxfail=1
# 32 passed (31 DB-099 + existing per-order tenant-boundary regression).

npx vitest run src/features/repair-orders/__tests__/RecommendedWorkPanel.test.tsx src/features/repair-orders/__tests__/RepairOrdersPage.abort.test.tsx src/features/repair-orders/__tests__/RepairOrdersPage.authorization.test.tsx src/features/repair-orders/__tests__/PriceBuilderPanel.pending-feedback.test.tsx
# 81 passed across four files; 14 new panel tests.

npm run build
# TypeScript and Vite production build passed.

npx eslint src/features/repair-orders/RecommendedWorkPanel.tsx src/features/repair-orders/PriceBuilderPanel.tsx src/features/repair-orders/RepairOrdersPage.tsx src/features/repair-orders/__tests__/RecommendedWorkPanel.test.tsx
# Zero errors; two existing RepairOrdersPage exhaustive-deps warnings.
```

The two lint warnings were independently reproduced against `git show HEAD:frontend/src/features/repair-orders/RepairOrdersPage.tsx` using ESLint stdin, so neither is introduced by this item. Existing React Router/act and Browserslist-age warnings occur in the regression/build output.

Backend fixtures cover technical continuity after payer change without exposing payer/notes/estimates, all roles and unauthenticated/no-tenant users, foreign/malformed joined tenants, exact same-VIN truck identity, resolved/linked/deleted/cancelled exclusions, final and declined source inclusion, relationship duplicates/effective dates/types/legacy pointer, indistinguishable invalid contexts, pagination validation, stable priority/date/ID ordering, identical descriptions as separate IDs, beyond-end and empty pages. Repeated aggregate GETs and opening the source workspace preserve complete snapshots of recommendations, orders, vehicles, customers, seeded labor/parts/stock/invoice/settlement/outbox plus history; no websocket broadcast occurs.

Frontend coverage checks context request/key fields, signal cancellation, source route, no mutation controls/calls, all role classes, retry versus empty, pages beyond 25, late-response suppression, immediate displayed-row clearing/reset on context change, return refetch and shared prefix invalidation. API tests prove current-order exclusion.

## Runtime and remaining gates

Implementation agent read and ran the local-runtime preflight/controller status before implementation: controller pointed at the root/main checkout with a dirty source, no API listener and migration receipt 147; it was **blocked/mismatched** for this branch. It did not restart or change servers. Parent separately owns approved ports `http://127.0.0.1:5174` / API 8001 and isolated local database fixtures. That evolving setup is not browser evidence for this handoff.

Required next actions: fresh independent Security review of aggregate visibility; independent QA against a synthetic authenticated full-stack desktop/compact journey, including open-source navigation and no overflow; record current process/source/database alignment. No browser acceptance, PR, merge or deployment is claimed by this implementation agent. Do not mark Done until required evidence exists.

Return condition: any contract mismatch, tenant/role exposure, stale-context rows, source navigation failure, or layout issue returns to the implementation owner with reproduction evidence.

## Independent gate and signed-in acceptance — 2026-10-12T16:24Z

Fresh independent reviewer `independent_gates` reran the focused negative suites and inspected source/contracts plus all four desktop/390px screenshots. **Security and final QA GO**, no blocking findings. Approval covers local reviewed source, not protected CI, merge or deployment.

Combined preview branch `codex/ets-parity-preview` HEAD `b03cf1f9` contains DB098 `4462851a`, DB099 `724c4249`, DB100 `6b1eac5b`; application source merged without conflict. Vite5174 PID52233 cwd is the preview checkout frontend; API8001 container `42e9f351…` binds the same checkout backend. Direct/proxied `/health/ready`200, isolated local DB `truckpitstop_ets_workflow_parity_20261012` at164, Redis9. Real UI login into new synthetic tenant; no endpoint mocking, production or provider writes. Original local DB/other5173 task preserved. User approved alternate ports.

Recommendation journey: prior urgent/monitor issues appear with original dates; resolved fixture absent; source navigation opens original RO and excludes its own recommendations; mobile controls fit390px. Reporting journey:200/120→80/40%;300/220 sublet with4hours→80/26.67%; partial1of2 leaves profit unavailable;100/120→−20/−20%; source RO link works. Mobile no document overflow. Screenshots and full runtime receipt retained in the combined preview checkout under `output/ets-parity/` and `docs/verification/ETS_PARITY_PREVIEW.md`. Zero, failure and old-backend cases are automated evidence, not fabricated browser outcomes.

Feature implementation is locally verified and ready for protected PR CI. No merge or deployment is authorized by this receipt.

## CI correction — 2026-10-12

PR498 full frontend CI exposed a malformed200 payload crash in RecommendedWorkPanel that broke existing void/revision test workspaces. The query now validates the full reduced response with existing Zod before caching/rendering; invalid initial data produces an unavailable state, never empty/all-clear. Invalid refresh retains only validated prior rows with a visible error, and clears an empty/all-clear claim. Exact endpoint mocks and a malformed-response RO regression were added.

Full frontend suite:136files/1195tests passed; final additional cached-empty regression:35panel tests passed. Fresh independent reviewer reran41panel/force-void/void-revision tests plus scoped ESLint/diff check: Security and automated QA GO. TypeScript/Vite build pass. API/schema/permissions unchanged. Corrected real-API preview smoke remains required before final runtime GO; earlier approval applies only to the earlier source.
