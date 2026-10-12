# DB-106: customer and repair-order workflow continuity

2026-10-12. Accountable owner: Frontend & UX. Fast UI lane: existing authenticated read contracts, no schema, permission, financial or provider changes. Source `codex/customer-workflow-parity`, stacked on PR504 (`codex/customer-workspace`). Local acceptance complete; review/CI are separate from merge and deployment.

## Audit evidence and decisions

Read-only authenticated ETS navigation exercised company → linked vehicle → Service History. Company navigation exposed Vehicles, Contacts, Transactions, PM Services, Services and Attachments. Vehicle navigation exposed Service History, PM Services, Invoices, Attachments and Issues. Service history showed descriptions, duration, charges, completion/mileage, status and source numbers. No ETS record was edited or submitted.

The approved REA web subset analyzed five browser-observed JavaScript modules: VehicleCard, CustomerNavigation, VehicleInfoModal, VehicleCell and ServiceItem. `analyze-javascript-application` and `inspect-analysis-view` succeeded: 15,694 bytes, 5 parsed files, 3,633 AST nodes and 59 static findings; zero parse failures. The semantic analysis remains partial/unknown, with 614 semantic unknowns. These are navigation clues, not 59 product gaps or proof of complete parity. Artifact SHA256 `703ac89db8d1bd1c81c481c686589d61b34ae3b85283d4c4308429e3e1b71e44`. Bounded provenance and asset hashes are in `DB106_ETS_CAPTURE.json`. Vendor code remains in `/tmp/dieselbridge-rea-customer-20261012`; no vendor code or private payload was copied into this repository.

| Confirmed DieselBridge gap | Change and process improvement |
|---|---|
| Shop Work embedded customer truck click was a no-op | Shared truck record opens in the same workspace, with exact identity and return to the customer/job |
| Embedded customer history expanded an empty component | Shared labor/parts/payment-summary details, plus direct opening of the exact historical order |
| Truck history silently stopped at the default endpoint limit | Existing paginated endpoint, 25 records per request, explicit Previous/Next; keyboard-accessible rows |
| Failed history requests looked empty or showed misleading default totals | Customer, truck and individual repair details have explicit error/retry states |
| Truck actions differed between customer hosts | Shared footer keeps edit, connections, delete and guarded merge in one consistent place; 44px two-row phone controls |
| Narrow expanded history overlapped later records | Override the inherited fixed table-cell height only where records reflow into a grid; expanded content now determines row height |
| Long open-order labels clipped on small phones | Short visible action with full order number retained in the accessible name |
| Canonical truck Back label used the contact first name instead of the displayed company | Return action now uses the same customer display-name function as the workspace |

This retains DieselBridge's work-first flow. Looking at a customer, truck or history never creates/edits an order. Opening another order retains the selected Shop Work queue; returning from a truck restores the same customer and original job. Existing tax settings, customer facts and full-height workspace behavior are preserved.

## Acceptance and regression evidence

Acceptance was defined on the board before implementation: exact customer/truck/order identity; existing GET contracts only; no stale-truck substitution; truthful failed/loading states; queue-preserving returns; bounded paging; desktop and narrow-screen actions visible and operable. Frontend guards preserve the owner/admin and complete-VIN requirement for vehicle merging. No auth/tenant contract was changed; backend authorization remains authoritative.

RED evidence: embedded truck click showed zero repair-history headings; expanded history had no repair-details region. Two host regressions failed before wiring. Focused detail/retry tests were introduced before the shared components; the canonical return-label test failed before the naming correction. Browser RED: a 52px mobile detail cell allowed 854px of content to overlap following records. Browser GREEN: row height876px, next record starts after detail bottom; width320/scrollWidth320. A long action initially measured244px inside225px; final action115px with parent scrollWidth225.

Final source code968ad34d: **51 tests pass in 7 files**, including shared details, customer history, truck footer, customer host, embedded repair-order host, tax concurrency/permission safeguards and vehicle-merge controls. Combined preview: **54 tests pass in the same 7 files**, including three pre-existing search deep-link regressions. The preview required its search test's old `Back to Nora` expectation to follow the corrected company name; preview-only integration commit68298b2c records that adjustment. It must travel with the combined landing of PR500 and this item. Both source and combined production builds pass. Changed-source ESLint: zero errors, two unchanged RepairOrdersPage hook-dependency warnings.

Local outputs: source `output/db106/{final-tests.txt,final-build.txt,final-lint.txt}`, preview `output/db106-combined-{tests,build}.txt`. No backend suite was rerun locally for this read-only UI change; protected CI supplies the broader gates.

## Actual browser acceptance

Signed-in Codex in-app browser, local API data, 2026-10-12 approximately18:03–18:14 America/New_York. Existing synthetic performance/QA fixtures; no record, tax, timer, merge, delete, invoice or provider writes.

- Desktop1295×900: customer → truck → history works in both Shop Work and Customers. Embedded panel top18/bottom882; footer bottom882, height49. Document scrollWidth1295. Edit Vehicle and Manage Connections forms open from the new footer; Cancel returns without submitting.
- Keyboard: Enter opens the selected truck/history order. Back returns through customer to the queued job. Canonical truck Back label names the displayed company.
- History details show real labor, parts, mechanic, totals and unknown payment as an em dash. Opening a different historical order changes selected ID and retains `queue=on_floor`; verified from both history details and truck history.
- Phone390×844 and320×740: actual rendered innerWidth verified; no document horizontal overflow. Truck actions have44px heights, complete labels and two rows. Scrolling stays inside the workspace above its footer/navigation. Expanded history grows normally and its shortened action fits; actual screenshots inspected, not just DOM presence.
- Network failure injection used tab-scoped request blocking. Customer history hides lifetime statistics on failure; truck history does not claim zero records; repair details do not claim no work. All three retry actions restored the real API response after removing the block.
- Console had an existing Headless UI/StartWorkAction list-key warning. No new uncaught application exception observed. Injected failures were deliberate; blockers removed afterwards.
- Temporary ETS/local tabs closed and viewport/network overrides reset; the user's tabs retained.

Screenshots (synthetic local fixtures only): `output/db106/desktop-truck.png`, `desktop-customers-truck.png`, `phone-truck.png`, `phone-history-320.png`; hashes in `screenshots-sha256.json`. Physical phones, native mobile Safari, mobile OS keyboard behavior, all staff roles and destructive action submission were not tested. Paging over25 rows is covered by automated API-contract tests; the actual browser fixture has6 orders.

## Runtime receipt

Intentional source/runtime split preserves the combined DB098–105 preview. Source branch code968ad34d is included in preview06132a3e; preview68298b2c adds the integration-test expectation above. Vite PID68993 serves `/Users/sergio_m1_promax/.codex/worktrees/ets-parity-preview/truck-pit-stop/frontend` on5174, proxy to8001. API `dieselbridge_api_ets-workflow-parity` mounts preview/backend. Database `postgres/truckpitstop_ets_workflow_parity_20261012`, Redis hostredis/database9; schema165_service_checklists retained, no migrations or service restarts. `/health/ready` via5174 returned ready with database/Redis healthy at18:13. Boot badge07275e9 remains stale under HMR; process directory plus rendered changes corroborate current source.

## Remaining parity gaps

The earlier DB104 audit remains the source for documented ETS behaviors versus directly exercised ones. Prior checklists, recommendations visibility, intake editing and held-state display remain implemented; they are not counted as missing again.

1. Tracked recommendation → operation conversion remains the highest-value next contract: source provenance, idempotent creation, template application, recovery and deliberate resolution. Copying text alone would lose the operational link.
2. Per-service technician assignment/completion and staff hold/resume require explicit assignment, timer, permission and finalization rules. ETS's scheduling transition is not equivalent to DieselBridge's current mechanic hold state.
3. External service-history import requires provenance/deduplication; current history contains shop repair orders.
4. Bay/technician capacity scheduling needs resource/conflict rules beyond appointments.
5. Customer PM recurrence, attachments and transaction equivalence need deeper behavior verification. Seeing an ETS tab does not establish its full workflow or a missing DieselBridge capability.
6. Existing embedded base-customer/vehicle/contact fetch-error handling deserves a separate recovery audit; this item explicitly covers the three history request paths.

Full ETS parity is not claimed. Payment/provider actions and destructive writes remain outside this local read-workflow verification.

## Review handoff

[Draft PR505](https://github.com/mecaniser/truck-pit-stop/pull/505) is stacked on PR504. Final-head Quality gates are dispatched manually after this evidence commit; local acceptance does not substitute for those checks. Parent PR504 run38313246736 completed successfully across all six jobs, separately from this item's gates. No merge or deployment performed.
