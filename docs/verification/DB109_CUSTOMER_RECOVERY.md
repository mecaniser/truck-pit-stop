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
