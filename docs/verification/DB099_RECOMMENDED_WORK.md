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
