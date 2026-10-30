# DB-036 sync login resilience — October 30, 2026

Backend & Integrations owns this worker change. Independent QA/Security and release acceptance remain required.

## Contract and acceptance

The 15:05 UTC sync run failed at `login_legacy_redirect_loop` after two completed legacy-link redirects, before email/password filling. A same-image redeployment does not fix that failure.

Extract the already reviewed health anonymous-context recovery into one shared internal helper. Health retains its wrapper and diagnostic names. Sync opts into the same policy through its own wrapper; other collectors and the low-level legacy form helper are unchanged.

- Return `{context, page}` only after the unique legacy email/password form is ready on the exact allowed authentication origin/path, with no credentials submitted by this helper.
- Only a confirmed `login_legacy_redirect_loop` on `/login/lookup` with neither credential field visible can replace the anonymous context. Dispose the original before creating one replacement. Never copy cookies, storage or a session.
- Preserve locale/timezone options. Reuse the original 15-second monotonic form-readiness deadline for disposal, replacement creation/page/navigation and form preparation. Initial navigation timeouts retain their existing bounds. No third context, retry of credential submission, or recovery after returning the form.
- Origin/path, ambiguous/partial fields, unsafe/duplicate links, missing form, timeout and unknown errors fail closed. Errors after credential submission are terminal and cannot enter anonymous recovery.
- Sync grants its existing clipboard permissions to the returned context before filling credentials. Permission failure is terminal. No permission expansion or source/tenant/company/import/receipt/idempotency change.
- Preserve all existing worker commands, schedules, restart policy and credentials. No Codex automation and no container start solely for SSH.

## Verification plan

Run existing health and legacy-helper regressions plus actual sync-collector fixtures: direct/lookup forms, confirmed-loop replacement ordering, exactly one credential submission, clipboard permission binding, persistent replacement loop, foreign origin, ambiguous/partial fields, disposal/create/navigation failures, deadlines and post-submit failure. Use network-isolated Chromium fixtures for completed navigation loops, remaining-time bounds and wrong-origin replacements. Protected PR checks and deployed module/configuration parity precede a natural run source/receipt/readback/replay gate.

Local runtime controller dry-run on `codex/motive-sync-login-recovery` reports missing approved `backend/.env` and Vite; no frontend/backend listeners or local services were started. Isolated browser fixtures do not establish an aligned local product runtime.

## Owner verification

Focused run: **121 Node tests passed**, including both actual collector harnesses, shared legacy-helper diagnostics and network-isolated Chromium fixtures. Existing health diagnostic names and behavior pass unchanged. The protected workflow now includes the sync recovery fixture, so this shared failure class remains covered after this release. `git diff --check` passes. No Python importer, receipt, migration, tenant or provider credential change. Independent QA/Security and production acceptance are pending; fixture recovery is not evidence that a provider loop recovered live.
