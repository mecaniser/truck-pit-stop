# DB128 — Outside-shop receipt attachments

Accountable owner: Backend & Integrations. High-risk lane: private documents and additive schema.

## Audit

Read-only ETS customer → vehicle → More → Add External Service exposes Attachments / Upload Files beside historical provider/date/odometer/work. No vendor form submitted or file uploaded. CUA captured three already-loaded public static scripts (external service, attachment button and thumbnail); REA6.4.0 analyzed39,401bytes/9,506ASTnodes with zero parse failures. Evidence `ev_8c62aaba7f205ccdbdeb37e0588ee4902f012ad7ee69865d2970e91ccceb64f5`; local artifacts `/tmp/dieselbridge-rea-receipts-20261014`. Static syntax corroborates the UI; it does not prove vendor write behavior. No vendor code reused.

DB119 already records outside work but explicitly deferred receipt files. Selected improvement: attach once to the exact outside-work entry, private staff download, duplicate detection and recoverable removal with attribution. No external bill reconstruction or accounting effects.

## Runtime preflight

2026-10-14 local: implementation `codex/external-service-receipts`, base1c1e34cf with only intake documentation dirty. Approved intentional split preview `codex/ets-parity-preview`846360c3 retains prior overlays. Vite5174 PID97270 cwd preview/frontend; API target127.0.0.1:8001. Docker `dieselbridge_api_ets-workflow-parity`, image truck-pit-stop-api, preview/backend→/app, localhost8001→8000. Database postgres/truckpitstop_ets_workflow_parity_20261012 at169_external_service_history. Proxied readiness confirms database/Redis healthy. User restored authentication; local customer dashboard and production staff dashboard render. No new feature is yet visible. Additive migration170/171 plus the forthcoming receipt schema will be explicitly applied to this preserved local database after contract verification; no reset, provider flags or live payment changes. Exact changed-file overlay and browser proof required before claiming alignment for DB128.

## Required acceptance

Upload valid bounded PDF/PNG/JPEG, download after reload with matching bytes, duplicate retry and explicit duplicate detection, remove/show removed/restore with immutable actor/time events, and voided-record read-only behavior. Reject role/tenant/vehicle/record mismatch, invalid/oversize content, stale mutations and tampered request IDs. Preserve parent customer/order return context and compact desktop/390/320portrait/740x400landscape controls with no horizontal overflow. Independent QA/Security, protected CI, exact deployment and synthetic production workflow remain pending.
