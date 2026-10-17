# DB-127 legacy artifact correction — 2026-10-15

Backend & Integrations is accountable. PR540 passed its gates, but rollback-only production acceptance found that all verified canceled operation invoice copies were soft-deleted. No financial transaction was committed by that failed acceptance.

[PR541](https://github.com/mecaniser/truck-pit-stop/pull/541) permits soft deletion only on those exactly verified canceled legacy copies. Canonical invoice and repair-order deletion guards remain intact, as do tenant/customer/vehicle/service, amount, bill-to, canonical UUID and exact legacy naming checks. Unknown or active copies remain conflicts. Fresh source evidence must still prove a complete singleton invoice manifest.

- 63 focused tests passed, including same-event replay with one outbox addition, soft-deleted positives and active/unknown/name/amount/deleted-canonical negatives. Independent QA/Security repeated the suite and approved head `1c7b989de2c3cbb9e33661d246bdfb597576121e`.
- All six protected [CI checks](https://github.com/mecaniser/truck-pit-stop/actions/runs/38813974112) passed; no protection, runner capacity or spending settings changed.
- Protected merge: `13d5c86750b26fcedeed515e4a730236a1be2c84`. Web deployment `e073d072-8570-4e06-be71-939b2b901f14` and Worker deployment `45d67228-5344-4a47-bcb7-81ddb5819e14` succeeded. SSH confirmed that exact runtime commit on both services.
- Both running source-module SHA-256 values match reviewed local source: `cc7741c26f1c213b54af523149532a34d9c0373adb231f5fbcf7bfc8b7162166`. Public `/health/ready` reports ready, with database and Redis healthy.
- A read-only evaluation against actual canonical/sibling records retained exactly one root. The source release itself performed no financial, manual-qualification or Google delivery writes; bounded capture and provider receipts are separate acceptance evidence.

Rollback: redeploy the prior exact revision to Web/Worker to restore the conservative hold behavior; preserve evidence, immutable events and existing provider reservations. Do not reverse financial records or blindly resend conversions. No cron import was manually invoked for this release.
