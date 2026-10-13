# DB-100 cost and margin evidence

Board state: REVIEW / implementation checks passed; independent QA, financial-data review and runtime acceptance pending.
Accountable owner: Backend & Integrations.
Branch: `codex/report-cost-evidence`, baseline `91045a625f89d84221aaf8ed74d1cdc7d92438b6`.
Contract: [db100-profitability-evidence.md](../contracts/db100-profitability-evidence.md).
Evidence timestamp: 2026-10-12 16:17 UTC (12:17 America/New_York).

## Outcome and scope

The analytics profitability endpoint previously subtracted customer-facing labor and parts charges as though they were shop expenses. An ordinary $300 order ($100 labor/$200 parts) consequently claimed a 0% whole-job margin, although labor expense was not captured.

Both existing analytics endpoints now retain `marginPct` as an explicitly nullable field and return null. The profitability endpoint provides current parts and sublet contributions with complete/partial/unavailable/not-applicable coverage, string decimal amounts and nullable percentage/contribution. Parts expense uses the stored cost-at-use snapshot times quantity; sublet vendor expense is the whole line, never hours times vendor cost. Ordinary labor expense stays unavailable. Aggregation retains precision until serialization. No whole-job or net-profit claim is made.

Frontend analytics replaces the unsupported scatter with a linked per-RO component breakdown. Missing and partial expenses show coverage, known zero remains zero, losses remain signed, and old-backend fields show `Cost breakdown unavailable`. Request failures have a separate error display. Account revenue/Pareto remains available with null margins. Layout stacks component columns below the small breakpoint; actual compact browser acceptance remains pending.

Parent-approved additions to the Architecture contract: expose the existing `order_number` for readable links; enforce independent tenant-equality and deleted-row guards on account invoice/RO/customer joins while preserving valid invoice selection, revenue, ranking and cumulative share. Parts/labor joins independently require tenant equality and active children. No financial writes, schema changes, inventory-cost fallback, wage estimates, provider calls or feature-flag changes.

## Focused verification

- Backend: **29 passed** across `test_analytics_cost_evidence.py` (20), `test_reports_source_tenant_defense.py` (2) and `test_report_timezone_boundaries.py` (7). Only existing SQLAlchemy/Pydantic deprecation warnings.
- Backend fixtures cover the original false-0% bug; 200 revenue/120 cost => 80/40%; known zero => 100%; 100/120 => -20/-20%; zero revenue/20 cost => -20/null; negative revenue => signed amount/null; missing and partial snapshots => null contribution/margin; 300/220 sublet with four hours => 80/26.67%; unknown ordinary labor expense; no component lines; fractional quantities and aggregate-only rounding; retained line discount and unallocated order/labor discounts; null schema; foreign/deleted/orphaned child defense; source RO/date/positive-subtotal selection; unchanged manager-only access; account ranking and invalid-label defense.
- Frontend: **22 passed** across `CostContributionBreakdown.test.tsx` (8), `GarageAnalyticsCostEvidence.test.tsx` (2) and existing `GarageAnalyticsRange.test.tsx` (12). Covers old-backend fallback, missing component fields, complete/partial/missing/zero/negative costs, no positive-revenue percentage, cost basis, links, null account margins, request failures and existing range/cash behavior.
- Scoped ESLint: pass for the changed page, component and two new test files.
- TypeScript + Vite production build: pass (`npm run build`, 3,210 modules). Existing Browserslist stale-data notice; no build errors.
- Python source compilation and `git diff --check`: pass.

Commands (from this checkout, frontend commands from `frontend/`):

```sh
/Users/sergio_m1_promax/GitHub/truck-pit-stop/backend/venv/bin/python -m pytest backend/tests/test_analytics_cost_evidence.py backend/tests/test_reports_source_tenant_defense.py backend/tests/test_report_timezone_boundaries.py -q
npm test -- --run src/features/garage/__tests__/CostContributionBreakdown.test.tsx src/features/garage/__tests__/GarageAnalyticsCostEvidence.test.tsx src/features/garage/__tests__/GarageAnalyticsRange.test.tsx
npx eslint src/features/garage/GarageAnalyticsPage.tsx src/features/garage/CostContributionBreakdown.tsx src/features/garage/__tests__/CostContributionBreakdown.test.tsx src/features/garage/__tests__/GarageAnalyticsCostEvidence.test.tsx --max-warnings 0
npm run build
```

## Local-runtime boundary

Read AGENTS, delivery-team/local-runtime skills and ran `scripts/local_runtime/controller.py status --json` before implementation. This checkout is `codex/report-cost-evidence` at `91045a6`; only the supplied contract was untracked at intake. The controller returned its old managed root/main receipt and migration147, which does not attest this checkout. Approved frontend5174 (node PID48293) and API8001 (Docker listener PID24097) were occupied by the parent integration task; the parent reported the approved isolated clone at migration164. This agent neither started nor switched servers, copied secrets, migrated, reseeded nor touched provider settings.

This implementation checkout is **not served or browser-verified**. Parent owns integration into the approved 5174/8001 preview and fresh process/source/API/browser proof. Focused DB fixtures used isolated in-memory SQLite only. No production/customer data mutation.

## Required handoff

From Backend & Integrations to independent QA/financial-data reviewer and parent integration owner:

1. Review exact Decimal basis, nullable legacy fields, line coverage and tenant guards independently.
2. Integrate the scoped files into the approved preview; refresh local-runtime receipt.
3. Verify signed-in analytics desktop/compact states, RO navigation, explicit unknowns/losses/zero, old-backend fallback and error distinction. Only authorized synthetic fixtures may be mutated.
4. Record independent gate outcome, focused PR/protected CI, merge and deployment proof before Done. No commit, PR, merge or deployment exists for this work at this receipt.

Rollback is source rollback only; old code restores the known inaccurate display. The existing positive-subtotal RO selection remains unchanged, so free/negative whole-order inclusion and revenue recognition remain separate product/accounting decisions.

## Independent gate and signed-in acceptance — 2026-10-12T16:24Z

Fresh independent reviewer `independent_gates` reran the focused negative suites and inspected source/contracts plus all four desktop/390px screenshots. **Financial-data/security review and final QA GO**, no blocking findings. Approval covers local reviewed source, not protected CI, merge or deployment.

Combined preview branch `codex/ets-parity-preview` HEAD `b03cf1f9` contains DB098 `4462851a`, DB099 `724c4249`, DB100 `6b1eac5b`; application source merged without conflict. Vite5174 PID52233 cwd is the preview checkout frontend; API8001 container `42e9f351…` binds the same checkout backend. Direct/proxied `/health/ready`200, isolated local DB `truckpitstop_ets_workflow_parity_20261012` at164, Redis9. Real UI login into new synthetic tenant; no endpoint mocking, production or provider writes. Original local DB/other5173 task preserved. User approved alternate ports.

Recommendation journey: prior urgent/monitor issues appear with original dates; resolved fixture absent; source navigation opens original RO and excludes its own recommendations; mobile controls fit390px. Reporting journey:200/120→80/40%;300/220 sublet with4hours→80/26.67%; partial1of2 leaves profit unavailable;100/120→−20/−20%; source RO link works. Mobile no document overflow. Screenshots and full runtime receipt retained in the combined preview checkout under `output/ets-parity/` and `docs/verification/ETS_PARITY_PREVIEW.md`. Zero, failure and old-backend cases are automated evidence, not fabricated browser outcomes.

Feature implementation is locally verified and ready for protected PR CI. No merge or deployment is authorized by this receipt.
