# DB-COMMS-011: CallRail success response handling

Owner: Backend & Integrations. Accept HTTP 200 and 201 only after the existing conversation, company, recipient, current sender and tracker validation passes. Malformed or foreign bodies and ambiguous statuses remain held after one attempt. Preserve definitive client rejection, signed receipt reconciliation and duplicate protection. No schema, feature flag or provider configuration changes.

## Local runtime

2026-10-19: intended branch `codex/callrail-response-success`, base `b0b35567940cc7c03deae517539f1c5c2dce7127`. The standard controller dry-run refused absent backend/.env. The approved isolated communications harness was used instead, referencing its existing ignored configuration by symlink without copying secrets. Existing node_modules were reused.

PostgreSQL `communications_local` on loopback 55460 remains at schema183; Redis is on6386. No migration or reseed occurred. Prior task-owned Vite45395/API51385 ownership was checked before graceful stop. New Vite21801/frontend and API21916/backend both serve this checkout at5186/8006. Direct and frontend-proxied readiness returned200 with database/Redis OK. All three new SMS flags are false. Source/process aligned; no changed UI journey exists for this backend-only correction. Other task servers were preserved.

## Verification

- Default adapter run:34 passed;15 database cases skipped without explicit opt-in.
- Explicit isolated PostgreSQL run of CallRail service, CallRail dispatch and shared communications service:64 passed, no skips.
- Independent Security/QA repeated those64 and added eight HTTP-to-durable-dispatch challenges:72 passed. Valid200/201 accepted once without inventing a message SID; malformed/foreign200 and202 held once;403 rejected once; signed FAILED callback before either success response retained its terminal result.
- Independent source review confirmed the only production change is accepting the two success statuses. Strict body scope checks are unchanged. Diff check passed.

Reviewed source SHA256: `b7c5e561f459b2fc0a56bf16d1528f0f41ca5c2ddd43d7d67d67d03f9254393c`; test SHA256: `3069ec132b4b9ec7559e1a1e775eecf17ab8cf149da55149c0d6747986e9b20d`.

The old real HTTP200 body was not retained; this correction does not claim it was observed. A success body that fails the existing checks still requires reconciliation. Protected CI, exact merge/deployment and runtime evidence remain release gates. No live provider send or configuration change was performed for local verification.
