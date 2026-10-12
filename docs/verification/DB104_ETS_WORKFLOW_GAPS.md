# DB-104: remaining repair-order workflow audit

2026-10-12. Accountable owner: Frontend & UX. Existing-contract refinements use the Fast UI lane. Source branch `codex/repair-order-intake`, stacked on `codex/repair-order-workspace` / PR502. No merge or deployment claim.

## Evidence and limitations

Read-only authenticated ETS New Service form showed company, contact, vehicle, check-in notes, pricing defaults, scheduled/due dates, PO number, and complaint/service selection. Settings were expanded; no records were saved. On Site and Upcoming were empty in this account, so held-job execution and finalization were not exercised in ETS.

Six JavaScript assets observed in the browser were captured through the browser CDP capability and analyzed offline with the approved `rea-agents@6.4.0` web subset. `analyze-javascript-application` and `inspect-analysis-view` returned ok: 26,338 bytes, six parsed files, 6,076 AST nodes, 120 findings, zero parse failures or integrity contradictions. Separate `trace-javascript-semantics` queries for `po_number` and `recommendations` each found one seed, one node, zero traversed relations, one relevant unknown, ambiguous status and partial coverage. This is useful navigation evidence, not end-to-end runtime proof. The source graph hash is `ca02584a89e3d33a9d80f9b5251fc3bf1a1c62eb11e005e15ed03d739916895b`.

Source capture: `/tmp/dieselbridge-rea-workflow-20261012`. Reproducible asset hashes/URLs and bounded REA outputs are in local `output/db104`. Vendor code is not copied into application source. No private payloads, credentials, or auth headers were recorded. Full REA native/Linux/Android tools remain outside this approved web subset.

## Workflow comparison and decisions

| Workflow | ETS evidence | DieselBridge evidence | Decision |
|---|---|---|---|
| Intake corrections | PO and check-in settings observed in New Service | Existing PUT accepts PO, intake and return mileage; modern anchored details were display-only | Implement compact explicit Save/Cancel editor inside existing truck details |
| Held-work visibility | Documented On Hold/Check In workflow | Existing mechanic hold/resume API and timer rules; RO workspace still labeled held work In the bay / Work in progress | Implement truthful held state and human-readable reason; preserve mechanic-only transitions |
| Recommendation carry-forward and conversion | Documentation describes prior truck issues and Transform into complaint/template-backed service | DB099 already reads unresolved same-truck recommendations. No source-to-operation conversion contract | Next high-value workflow: tracked conversion with idempotency, provenance, failure recovery and deliberate resolution. Copying text must not masquerade as conversion |
| Checklist completion | Documented service tasks/completion | DB102 already implements template snapshots, completion gates and save handling in PR501 | Preserve; not a missing feature. Prior audit's generic-checklist absence is superseded |
| Per-service technician and completion | Documented per-item assignment and completion | Current RO has one assigned mechanic; timer/quality workflow is order-oriented | Separate contract for multi-technician work and finalization gating; do not infer parity from lead assignment |
| Staff hold/resume | Documented ETS staff flow moves job to Upcoming and checks out technicians | DBN hold remains an in-progress mechanic substate, stops own timer, resume starts work | Product/contract gap; adopting ETS semantics would change scheduling, permissions and time accounting |
| External service history | Earlier audit documented ETS records made outside shop | Current history is owned RO history | Separate import/provenance model; retain as backlog |
| Bay/technician capacity scheduling | Earlier audit documented ETS planning | Current appointments do not provide resource capacity/conflict enforcement | Separate scheduling contract; retain as backlog |

Primary sources: [ETS work-order flow](https://support.easytruckshop.io/en/articles/11655319-how-to-create-a-new-service-work-order-complete-flow-from-complaint-to-invoice-original), [ETS recommendations](https://support.easytruckshop.io/en/articles/16515197-recommendations-issues-how-they-work). Documented behaviors above are distinguished from observed UI. Original baseline: `docs/ETS_FUNCTIONALITY_AUDIT.md` in the combined preview; this follow-up reconciles later DB098–103 implementation.

## Implementation acceptance

- Explicit intake editor uses existing authenticated PUT and role guard, active/unlocked/nondeleted UI guards; no endpoint, schema, permission, status, financial or timer changes.
- Only changed fields are submitted. Blank values clear to null; intake reading changes clear `mileage_in_carried`; changing only PO does not alter mileage provenance.
- Whole nonnegative mileage constrained to database integer range; PO max 100 characters. Draft survives a failed save. Duplicate clicks while saving do not submit twice. Escape/Cancel dismiss without writes.
- Save is bound to the captured order ID; a delayed completion cannot select a different order.
- On hold is shown only for `in_progress` plus a hold reason. Human-readable reason appears in the footer and bay disclosure; completed orders with historical reasons remain complete.

## Local evidence

Regression first: eight targeted failures reproduced missing intake editing and misleading held state. After implementation: 105 tests pass across PriceBuilderPanel, WorkflowInfoStep and RecommendedWorkPanel. TypeScript/Vite build passes. Raw scoped lint has zero errors and two pre-existing hooks warnings in RepairOrdersPage; changed-source regression lint and signed-in browser checks pending.

Implementation and preview are intentionally separate: source commits are integrated into the combined ETS preview to preserve DB098–103. Approved runtime is frontend5174/API8001 with isolated `truckpitstop_ets_workflow_parity_20261012`, Redis9; providers not changed. Browser acceptance, PR and CI evidence to be appended before handoff.
