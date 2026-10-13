# DB-111: ETS parity checkpoint merge

Owner: Release & Reliability. User authorized starting checkpoint merges on 2026-10-13. The local review preview remains unchanged at port 5174/API 8001 while focused branches land through protected PRs.

## Acceptance

- Merge focused PRs in dependency order; use the exact reviewed head and all six required GitHub checks, including the two suites named informational.
- Preserve unrelated source, local databases, branch work, and collected checklist/operation evidence.
- Include additive checklist 165, recommendation 166, merge 167 and operation 168 in one valid migration graph before the respective code is served.
- Explain integration differences against the already verified combined preview. Preserve later focused QA/security documents that are not in its foundation history.
- Record merge commit, CI, automatic Railway deployment and actual runtime acceptance separately. A merged item is not automatically release-Done.

## Initial inventory and independent review

Main began at `91045a625f89d84221aaf8ed74d1cdc7d92438b6`. Railway Web and application worker were running that commit. Both services are connected to this GitHub repository's main branch; the first merge triggered automatic builds. No Railway settings were changed and no manual deployment was requested.

Fresh independent reviewer `checkpoint_release_audit` inspected PRs #498–509, protected branch settings, source migrations, individual workflow jobs and combined-tree differences. Required main checks are Migration graph, Frontend checks, Frontend full suite (informational), Backend tests, Backend full suite (informational), and Playwright smoke. Strict up-to-date checks and linear history are enabled. No branch-protection bypass is used.

| PR | Outcome | Dependency / intake finding |
| --- | --- | --- |
| 498 | Recommendation carry-forward | All six checks, independent QA/security and authenticated local journeys passed. |
| 500 | Staff search | Existing-contract UI; current-main integration CI required. |
| 499 | Recorded cost contribution | Independent financial-data/security and QA, actual desktop/390px evidence present. |
| 501 | Service checklists | Four standalone test expectations/fakes corrected in `1b8833bf`; application/schema unchanged; 61 focused tests passed. |
| 502 | Dense repair-order workspace and manual duration | Text-scale regression backported from 503 in `344e331b`; 85 tests/build passed; same CSS as verified preview. |
| 503 | Editable intake and held-work display | Depends on 502; existing six-job acceptance verified. |
| 504 | Customer workspace | Depends on 503; existing six-job acceptance verified. |
| 505 | Customer history and trucks | Depends on 504; preserve staff-search deep links. |
| 506 | Tracked recommendation conversion | Depends on 505 and must include migration 167 after checklist 165 is present. |
| 507 | Contextual order creation / total alignment | Depends on 506; preserve focus/failed drafts and search entry. |
| 508 | Customer read recovery | Depends on 507. |
| 509 | Per-operation technician execution | Depends on combined prior features and migration 167. All six checks passed on c5aedbd6; a1733df2 records evidence only. |

Integration-only changes identified: no-op migration 167 (`25fdec64`), checklist aggregate notification fixture (`b25bafc1`, absorbed by the focused 501 correction), and search return-label expectation (`68298b2c`). Checklist rendering/completion errors and search/customer navigation must be retained during conflicts. The final operation source and preview application/test trees match exactly before checkpoint merging.

## Merge and runtime receipts

- PR #498: exact reviewed head `790a0715c95392d279938f35dc8b8c909f9638f1`; all six protected jobs passed, no unresolved review thread, mergeable. Squash merged at 2026-10-13T19:41:42Z as `8bc82cd458ecf728ead5e64d99689376928f64a3`.
- PR #500: refreshed against 8bc82cd4 as `1b32e78fa06513655aef3ef1adb9726ce0e32da0`. Conflict only in concurrent board entries; both retained. All six current-head jobs passed: https://github.com/mecaniser/truck-pit-stop/actions/runs/38457066584. Squash merged at 2026-10-13T20:01:02Z as `6cd51f6e4818f1ac1632a35e87f4cef7f5bd9705`.
- Production after #498: Web deployment `cb721251-0a0b-4989-8b55-bf5a2b421e0b` and worker `871b1387-90b8-4600-93cb-f105e6c0d296` succeeded at `8bc82cd4`. Readiness returned 200 with database and Redis healthy. Authenticated read-only UI loaded the recommendation panel and its canonical empty state on an existing completed order.
- Production after #500: Web deployment `1ec5aef6-895a-41ab-9ce4-b16520f1e2a4` succeeded at `6cd51f6e`; the worker remained successfully deployed at `8bc82cd4` (frontend-only change). Authenticated production search returned a customer and repair-order results, and selecting the customer opened the exact selected customer workspace. No customer/order data was changed.

## Rollback and boundaries

Railway executes `alembic upgrade head` and exact-head schema preflight before serving. After migrations 165/167/168, redeploying an old image without those revisions would fail. Rollback must be a forward application revert that retains migration files and additive schema. Do not downgrade away task history, assignment, completion or time attribution.

Stop rollout on failed readiness/migration, tenant disclosure, completion bypass, lost timer attribution or historical-order regression. Production acceptance is read-only; no real invoice, payment, notification, technician assignment or completion is changed for testing. No source-data backfill or provider configuration is authorized by the merge checkpoint.

## Optional combined candidate: composition gate

Prepared locally while awaiting the user's merge-method preference. Fresh independent reviewer `checkpoint_release_audit` gave composition GO: application/tests/configuration equal accepted `a1733df2` except a trailing blank-line deletion in `repairOrderEntry.ts`; all 28 restored focused evidence/contract/audit documents match their intended feature heads; unrelated current-main files preserved; migration graph has one head at 168; no unresolved conflicts or whitespace errors. This is not CI or release approval.

PR #500 subsequently merged after all six current-main jobs passed, at 2026-10-13T20:01:02Z as `6cd51f6e4818f1ac1632a35e87f4cef7f5bd9705`. PR #499 was refreshed with board-only conflicts resolved and pushed as `d68ce6514343bb888d7a630aa72fb403510e1aa3`; protected CI run 38459541333 is in progress. No reporting product changes were made during that refresh.
