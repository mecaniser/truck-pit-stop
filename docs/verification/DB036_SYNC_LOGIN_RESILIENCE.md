# DB-036 sync login resilience — October 30, 2026

Backend & Integrations owns this worker change. Independent source QA/Security, protected CI, deployment parity and post-deploy retained receipt acceptance passed. Source eligibility exceptions remain explicit below.

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

## Operational decision rules

1. Classify the exact failed execution and phase. A redeploy on the same image is not evidence of a source fix.
2. Retry only the reviewed anonymous preparation state: one discarded context, one fresh context, no copied session, original deadline. Credential or post-submit failures remain terminal.
3. Preserve incomplete/import-uncertain evidence. Inspect saved source, receipts and exact persisted request identities before considering another capture; never treat a crash as proof of no writes.
4. Require independent negative-case review and protected actual-collector fixtures before deployment. Verify exact deployed module bytes and full service configuration after build success.
5. Use normal scheduled activity for receipt inspection. Verify complete source/company guards, receipt source identities, saved IDs/membership, actual persisted-value digests and unique request keys. This SELECT-only audit establishes replay-key consistency, not a fresh replay invocation or current UI projection after later readings advance it.
6. Keep source-unavailable, history-review, membership and unknown-time dispositions explicit. A successful worker run does not mean all source entries became new telemetry.
7. Keep Codex automations off. Bounded observers belong only to the active release turn and stop after acceptance or a concrete failure.

## Release record

PR #683 passed all seven CI checks on `4dc08fbf8b38ff69688cb4558cd79c072cc3a223` and merged as `46b5dfed9f7bbc0849b1a5591fab53f185b06cd2`. Independent QA/Security reran 121 focused checks with zero failures or skips. Initial runtime module hashes matched the relevant pre-change main source; the failure was a provider legacy redirect loop, not a missing release or database outage. Deployment `2589dcb4-25e5-4176-b4ff-0a2f19c3a7b1` is build-only with the canonical service manifest and mount. Deployment readiness and post-release natural receipt acceptance passed; see the exact evidence below.


## Production acceptance

- Deployment `2589dcb4-25e5-4176-b4ff-0a2f19c3a7b1` SUCCESS, image `984362ef553618461caa3294dff73390e270dc6a45386024fdbf38aa7cd365c0`. All twelve relevant module SHA-256 values equal exact merge `46b5dfed`; scope digest `1d71fb130f529edae3802eed76cbada66efac417e34e706b0e976d9b3c1a519a` is unchanged.
- Full manifest and mount equal baseline: `python -m scripts.motive_sync.run_worker`, cron `*/5 * * * *`, restart `NEVER`, one replica, `/data`. No variable, credential, schedule or restart-policy changes; no manual cron trigger.
- Natural run `20261030T153254Z-abd053e2-d0f8-4739-bac1-85ab81202fd6` completed collection at 15:36:55 UTC and worker completion at 15:37:00 UTC. It used the normal legacy path; fresh-context recovery has real isolated Chromium coverage, not a claim that a provider loop recovered live in this run.
- During the next natural active container at 15:40 UTC, the SELECT-only audit checked the complete directory/source and company guards, exact receipt source-prefix identities, all saved IDs, membership/VIN/actor/tenant, actual persisted-value digests and unique saved request keys. Twelve module hashes were verified again. Audit and transport exited zero; bounded observers finished.
- Source SHA-256 `96e10061fac9bba319d2eeb59b58cd9dd7b2b8b84066ffd603d1a5c0ae370ca2`; receipt SHA-256 `eda0f25c309c5ec7d72a5f684bbe24246e307800006e6f5ad6ecbfe3af3b49db`. Nine saved readbacks passed. This proves exact replay-key consistency, not a fresh capture/replay call or the UI's current projection after later runs advance it.

| Receipt classification | Entries |
| --- | ---: |
| Saved update, exact readback accepted | 9 |
| History review required | 7 |
| Prior source time unknown | 2 |
| Source unavailable | 3 |
| Unchanged | 1 |
| Outside current fleet | 1 |
| **Total source / receipt entries** | **23 / 23** |

The login failure is remediated and the bounded process is verified. This does not override history-review limits, membership eligibility or missing source timestamps, nor claim every truck produced new telemetry or sustained all-five-worker recovery. Backend & Integrations retains ownership of those explicit data eligibility cases; do not remove safeguards to make a successful job look fleet-complete. Codex automations remain off; existing paused Motive automations were checked, and no scheduler was created.
