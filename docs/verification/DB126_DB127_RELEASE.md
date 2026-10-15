# DB-126 / DB-127 release receipt — 2026-10-15

Backend & Integrations is accountable. This record distinguishes deployed native and ETS intake, verified source receipt, and the first eligible Google provider receipt that remains pending.

## Released and verified

- [PR532](https://github.com/mecaniser/truck-pit-stop/pull/532) merged at `9fe12abacd04722e4afbf4c2c6476160a18eca96`, including native intake work from [PR531](https://github.com/mecaniser/truck-pit-stop/pull/531), which closed as superseded. All six [CI checks](https://github.com/mecaniser/truck-pit-stop/actions/runs/38674373435) passed. A failed container pull was retried without changing checks or spending limits; full backend results were 3,155 passed and 152 skipped.
- Production source Web, Worker and ETS sync were verified at that exact merge. ETS deployment was build-only; verification did not manually invoke the normal financial importer or change cron scheduling.
- Authenticated native repair intake displayed 30 call choices, including both reported example calls. Selecting a call and then cancelling created no repair order. This verifies discovery/selection/cancellation, not a completed production repair creation.
- [ELIS PR258](https://github.com/mecaniser/elis-agency-os/pull/258) merged as `fd23092b9a60f3b333799d0d056e3bf146c6338c`. Its [main CI](https://github.com/mecaniser/elis-agency-os/actions/runs/38680065841) and production release succeeded; `/ready` confirms that exact revision on receiver Web and Worker.
- Authenticated ETS intake displayed 90 qualified call choices, including both reported examples. The service number and call selections started blank; the form has no value or qualification fields. The default unlinked list displayed 10 of 2,378 records, and exact lookup returned one correct held ETS sample. No form was submitted and no repair job was written during this acceptance.
- All 96 rematch pages completed. Hash verification preserved all 606 human decisions, the original 605-decision subset and both locked associations. There remain 2,360 historical holds.
- One actual ETS completion reached the receiver exactly once, matched its source value, and reused existing canonical job/invoice aliases. Its historical hold was preserved. Google provider attempts were zero; no Google revenue receipt is claimed.
- The source Worker ETS activation is restricted to the exact reviewed tenant/shop. Receiver activation has an audit record. No caller identifiers, source invoice identifiers, private amounts or credentials are included here. Human qualification and locked associations remain authoritative.

## Remaining acceptance

Deployment and authenticated intake discovery are complete. A newly linked eligible completed repair must still demonstrate the existing Google validation, stable once-per-repair reservation and provider receipt. The historical acceptance record remains held and cannot serve as Google delivery proof. No missing call/job association or repair value was guessed, and no manual decision was overridden.

## Rollback and preservation

Disable `ETS_COMPLETED_OUTCOMES_ENABLED` on the source Worker to stop ETS capture/delivery through this path. Preserve immutable source observations, outbox records, receiver revisions, manual decisions, historical holds and any provider reservations/receipts. Keep native outcomes and the approved secondary Google destination unchanged. Unknown provider outcomes must be reconciled, not blindly resent.

This documentation update performs no deployment, production mutation or configuration change. It records the release owner's verified receipts and their practical limits.
