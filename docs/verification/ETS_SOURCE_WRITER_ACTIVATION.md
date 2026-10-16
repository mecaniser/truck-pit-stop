# ETS source writer activation

Status: prepared, not deployed or accepted. Owner: Backend & Integrations.

## Existing configuration evidence

Read-only Railway service-instance inspection on2026-10-16 confirmed the existing ETS cron is `*/5 * * * *`. Latest successful source image remains9fe12abacd04722e4afbf4c2c6476160a18eca96. The old deployment manifest and repository incorrectly retain `0 0 * * *`; this change reconciles the repository to existing runtime policy so activation does not revert it. Command, image builder, restart policy, environment, capacity and storage are unchanged.

## Frequency and serialization

A five-minute trigger is not a five-minute full refresh. The collector processes all stages before gated import; the previously observed complete cycle took about2h10m. `nightly_sync.py` acquires a database advisory lock before backing up files, scraping or importing. A competing tick logs that another run holds the lock and exits successfully. The owning connection remains open for the full cycle and releases on process exit. Do not interrupt an active owner to install the new image.

## Ordered activation and acceptance

1. Verify PR551 corrected Web and actual Worker revision, schema175 and natural export task success. No competing release may be in progress.
2. Check actual ETS instances and lock ownership. Preserve any active collection. Deploy the exact reviewed merged writer revision while retaining existing five-minute trigger and NEVER restart.
3. Verify deployed revision and effective cadence. Wait for a natural scheduled collector run; launching/building is not acceptance.
4. Inspect aggregate current source observations without caller data: contact completeness/failure reasons, source account/shop binding and observation timestamp; verify importer commits them without editing protected customer fields.
5. Verify natural DBN history schema2 and completed-invoice schema2 outbox delivery. Distinguish held evidence from eligible completed value, and source observation time from export time.
6. Verify corresponding authenticated ELIS provider receipts and projected account/contact/job evidence. Compare manual decisions and repair delivery ledger to the existing baseline; do not replay revenue to demonstrate health.

Current limitations: no fresh contact capture accepted yet; no live unpaid-completed ETS example established. A failed/filtered/ambiguous source page must remain explicit incomplete evidence. Completion requires observed collection/import/export/receipt, not just tests or deployment.

Rollback: stop subsequent releases; restore the prior verified source image if collector or ingestion safety fails. Keep schema175 additive and reader deployment compatible. Never change cadence, overwrite manual decisions or resend revenue as rollback.
