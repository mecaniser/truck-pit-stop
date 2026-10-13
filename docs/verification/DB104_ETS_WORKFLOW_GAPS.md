# DB-104: remaining repair-order workflow audit

2026-10-12. Accountable owner: Frontend & UX. Existing-contract refinements use the Fast UI lane. Source branch `codex/repair-order-intake`, stacked on `codex/repair-order-workspace` / PR502. No merge or deployment claim.

## Evidence and limitations

Read-only authenticated ETS New Service form showed company, contact, vehicle, check-in notes, pricing defaults, scheduled/due dates, PO number, and complaint/service selection. Settings were expanded; no records were saved. On Site and Upcoming were empty in this account, so held-job execution and finalization were not exercised in ETS.

Six JavaScript assets observed in the browser were captured through the browser CDP capability and analyzed offline with the approved `rea-agents@6.4.0` web subset. `analyze-javascript-application` and `inspect-analysis-view` returned ok: 26,338 bytes, six parsed files, 6,076 AST nodes, 120 findings, zero parse failures or integrity contradictions. Separate `trace-javascript-semantics` queries for `po_number` and `recommendations` each found one seed, one node, zero traversed relations, one relevant unknown, ambiguous status and partial coverage. This is useful navigation evidence, not end-to-end runtime proof. The captured artifact digest is `ca02584a89e3d33a9d80f9b5251fc3bf1a1c62eb11e005e15ed03d739916895b`.

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

Regression first: eight targeted failures reproduced missing intake editing and misleading held state. After implementation: 105 tests pass across PriceBuilderPanel, WorkflowInfoStep and RecommendedWorkPanel. TypeScript/Vite build passes. Raw scoped lint has zero errors and two hooks warnings verified unchanged from the base in RepairOrdersPage; changed-source regression lint passes across eight files. Final hold-priority correction adds one regression: 106 unique focused tests pass (71 rerun on the last code change plus 35 unchanged recommendation-panel tests).

Implementation and preview are intentionally separate: source commits are integrated into the combined ETS preview to preserve DB098–103. Approved runtime is frontend5174/API8001 with isolated `truckpitstop_ets_workflow_parity_20261012`, Redis9; providers not changed. Signed-in browser acceptance is recorded below; PR and CI remain separate gates.

## Improve the process while implementing parity

ETS is the capability reference, not a mandatory interaction model. For each remaining item, identify the operator outcome, remove repeated entry and unnecessary steps, surface blockers at the decision point, retain recoverable drafts, and preserve supported desktop density plus phone touch targets. Do not copy behavior that regresses existing workflows or changes permissions, financial state or timer accounting without an explicit contract.

This implementation improves the transfer: intake corrections stay beside the truck identity; only edited fields are sent; failed saves retain drafts; the hold reason precedes elapsed-time details. Keep DieselBridge's work-first flow and optional estimates. Future recommendation conversion should reuse the selected template with a source link and duplicate protection, then resolve only at the agreed successful-work boundary. A separate quick text-copy button would create an incomplete, untracked substitute and is intentionally not presented as parity.

## Browser acceptance and runtime receipt

2026-10-12, approximately 16:44–16:49 America/New_York. Source commits `e1c28447` and `5c64494d`; combined preview `4314f1b6` includes both. Vite PID68993 serves `/Users/sergio_m1_promax/.codex/worktrees/ets-parity-preview/truck-pit-stop/frontend` on http://127.0.0.1:5174 with explicit API8001 target. Container `dieselbridge_api_ets-workflow-parity` mounts the same preview backend at `/app`; database host postgres, database `truckpitstop_ets_workflow_parity_20261012`; Redis host redis, database9. Readiness200 confirms DB/Redis healthy. No migrations, flags, providers or service restarts. The boot-time build badge remains07275e9; process source and rendered new editor corroborate the HMR-served code.

- Desktop1280x800: truck-anchored editor, all fields and Save/Cancel visible; synthetic PO/mileage submitted through one PUT200 and confirmed after reload. Existing $988 work total remains unchanged.
- Phone390x844: invalid negative mileage blocked; simulated blocked network request shows inline error and retains the exact draft; unblocking plus explicit retry succeeds and persists after reload. A separate offline probe showed React Query pauses the pending save and resumes on connectivity restoration; it was not counted as a rejected-request test.
- Narrow phone320x740: document scrollWidth320; panel x16/width288; each input/button44px high; all edit controls in viewport, no horizontal overflow. Escape returns focus to truck trigger and produces zero PUT requests. All intake fields restored to their original null values through the same editor and confirmed after reload and DB readback.
- Held job: disposable same-tenant fixture with real API reads; desktop header/stage/footer agree with the queue. Phone inspection found reason below timing details; regression added and corrected. Reason now occupies y581–601 within844px viewport, immediately below status. Footer remains readable and reachable by scrolling. No hold/resume endpoint or mechanic timer was invoked.
- Completed QA-PRIOR-VISIT: truck disclosure has no intake editor. Existing read-only metadata remains visible.
- Cleanup: temporary viewport/network overrides reset. Disposable `QA-DB104-HOLD` removed after verifying no parts/labor/invoice children. Original PERF-0000001 total988, no hold, null PO/mileage, carried=false preserved. Physical devices, mobile OS keyboards and native mobile Safari are not tested.

Local screenshots: `output/db104/intake-desktop-edit.png`, `intake-mobile-validation.png`, `intake-mobile-retry.png`, `intake-mobile-320.png`, `hold-desktop.png`, `hold-mobile-details.png`, `hold-mobile-footer.png`. These contain only synthetic local fixtures. File hashes are in `output/db104/sha256-manifest.json`.

## Review handoff

[Draft PR503](https://github.com/mecaniser/truck-pit-stop/pull/503) is stacked on PR502. Both implementation and combined-preview builds pass. Earlier PR501/502 final runs38304209375/38304581908 independently finished successfully; they do not substitute for this PR’s checks. Quality workflow must be manually dispatched because automatic PR checks target main only. Merge/deployment are not performed.

## CI correction

Run38306918765 passed required frontend, backend, migration and Playwright jobs, but the informational full frontend suite failed `staffTypeScale` (1failure/1239passes). Root cause was an inherited desktop parts-quantity `font-size:13px` rule from DB103, not the new intake labels. Reproduced locally before changing it. Source `dae34c87` uses `calc(var(--font-size-body) * 0.8125)` to preserve default13px and honor the staff text scale.73affected tests pass (108unique focused checks including the unchanged recommendation tests). Combined preview0613cff2 reverified desktop13px/28px quantity input and phone16px/44px input,390px scrollWidth390; fresh capture also confirms12orders after fixture cleanup. Final code CI is attached to PR503. This correction changes no API or data behavior.
