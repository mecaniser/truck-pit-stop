# DB-109 Customer workspace recovery

Accountable: Frontend & UX. Fast UI, existing authenticated GET contracts only. Source branch `codex/customer-workspace-recovery`, base `e18fddcd` / PR507. No merge/deployment authorization.

## Acceptance before implementation

- Customer, truck and contact loading failures remain explicit, with in-place retry and a return path.
- Failed lists never claim zero trucks, no contacts, or invite an Add First Vehicle action.
- Pending retries disable repeat clicks and indicate progress; successful retry restores the same customer/job/queue.
- Switching customer identity cannot retain the previous customer in the workspace; late prior responses cannot substitute records.
- Existing successful empty states and editing controls remain functional. No API, tenant, authorization, schema, data mutation, timer or payment behavior change.
- Focused component/host regressions, changed-source lint, build, actual signed-in desktop/390px/320px UI with request blocking and restoration.

## Runtime startup receipt

2026-10-13. New source checkout is intentionally integrated into the combined preview for runtime acceptance. Preview branch `codex/ets-parity-preview` HEAD `3ea3c7d4460790dfe87d5884965b22608edb6b73`; only unrelated untracked verification/output files. Vite PID23640 serves preview/frontend on127.0.0.1:5174, branch/SHA env verified in rendered badge, API origin127.0.0.1:8001. Existing container `dieselbridge_api_ets-workflow-parity` mounts preview/backend. DB postgres / truckpitstop_ets_workflow_parity_20261012, Redis9, Alembic167_merge_checklist_conversion. Direct and proxied ready200, database/Redis healthy. Signed-in Performance Lab customer workspace renders. No backend restart, migration, reseed or provider change.

## Audit evidence

Read-only ETS active job1764 now directly exposes per-operation status, time, technicians, notes, attachments and Complete, plus job-level Assign/On Hold/Complete All. No buttons that change work, timers or records were submitted. Customer navigation exposes trucks and contacts while retaining the originating job link. This confirms capability presence, not hold/timer execution semantics.

REA approved web subset analyzed four browser-loaded modules (ServiceItem, ServiceItemProgress, CustomerNavigation, VehicleCard): 12,646 bytes, 2,706 AST nodes,48 static findings,0 parse failures.451 semantic unknowns remain; this is partial static evidence, not full parity. Artifact digest b7d1e5363a316f71b3e066c74ec643368272943f7f32ec0259c70b2286701a99. Vendor source remains only under /tmp/dieselbridge-rea-customer-recovery-20261013. No authenticated payloads or credentials captured.

Confirmed local defect: block customer vehicles/contacts requests and reload; one-truck customer displays Truck relationships0, No vehicles on file, Add First Vehicle and Using company contact details above. Base embedded customer GET lacks an error/loading fallback. Recovery is this increment; per-operation technician/completion, staff hold/resume, external-history provenance and capacity scheduling remain separate contracts.

## Implementation and verification

Code source `ddbf4ffc`; combined preview `b4e406c9` incorporates it. The preview retains its pre-existing global-search links and legacy deep-link support when integrating CustomersPage; neither was overwritten.49 focused tests pass in three files; combined preview36 host tests pass including its three additional search regressions. Final production build and changed-source lint pass. Raw scoped lint has0 errors and two pre-existing RepairOrdersPage hook-dependency warnings. No backend test rerun locally for unchanged GET contracts; broader suites run in PR Quality gates.

Actual Codex Chromium browser acceptance, signed-in Performance Lab,2026-10-13 approximately13:03–13:11 America/New_York:

- Desktop1280x720, then1280x800: blocked truck/contact reads render explicit errors and unknown truck count; no false zero, no Add First Vehicle. Unblock plus each Retry restores one real truck and the successful contact-empty message. Embedded base-customer failure shows retry and Back to the exact original order; successful retry retains customer/order/queue parameters.
- Phone390x844: error rows remain inside the scrollable full-height workspace above the pinned controls; Retry trucks/contacts measure44px. Both retries restore their data. Width and scrollWidth both390.
- Narrow phone320x740: base-customer failure and keyboard Enter retry exercised. During delayed retry, loading replaces the failed action so it cannot be repeated; Back remains available. Success restores the exact customer; Back returns to the same selected order and on_floor queue. Width and scrollWidth both320.
- Canonical Customers phone path exposed two additional defects: failed directory read claimed no customers, and the old centered fallback consumed vertical space. Corrected by explicit directory retry and using the regular SlidePanel workspace shell. Browser recheck shows the recovery state at the top, no false-empty prompt,44px retry, and a complete successful customer → Back → directory retry → customer journey. Existing truck/history navigation also works after recovery.
- Pending cached-read retry controls are disabled; late-prior-customer and failed-next-selection identity cases are covered by host tests. All recovery operations use GET only; no record, payment, timer, provider or destructive write performed.
- Browser viewport capability did not alter this hidden tab's actual dimensions. Responsive proof uses tab-scoped CDP metrics and verifies innerWidth/innerHeight directly. Full viewport screenshots use CDP captureBeyondViewport with explicit clips to avoid the in-app thumbnail capture limitation. This is actual responsive Chromium, not physical-phone or native mobile Safari verification.

Final runtime: Vite PID23640 still serves combined preview/frontend on5174, proxy8001, same backend mount/database/schema and sandbox settings. Proxied readiness200; changed loading/retry elements visibly corroborate HMR code despite the startup badge still showing3ea3c7d. Preview is aligned and browser-verified, not deployed.

## Delivery state

[Draft PR508](https://github.com/mecaniser/truck-pit-stop/pull/508), stacked on PR507. Owner verification passed (Fast UI lane); remote Quality gates run38436364915 for product source ddbf4ffc. Final result is tracked separately from local browser acceptance. No merge or deployment. Full ETS parity is not claimed.

## Remaining workflow priorities

1. Per-operation technician ownership and completion: now directly observed in an active ETS job. Define multiple-mechanic assignment, timer attribution and order-finalization rules before implementation.
2. Staff hold/resume: ETS exposes a job-level control. Keep reason and affected timer explicit; do not silently copy its documented move-to-Upcoming behavior into DieselBridge's in-progress hold state.
3. External history and capacity scheduling: provenance/deduplication and resource/conflict contracts remain needed. Customer attachments/recurrence still require deeper workflow evidence before an absence claim.
