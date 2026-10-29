# DB-048 fresh-request cash confirmation

Accountable owner: Backend & Integrations (root). High-risk payment lane.
Branch: codex/cash-confirmation-customer-load. Existing API, permissions,
financial locks, eligibility proof, idempotency, and commit boundary unchanged.
No migration or provider change.

## Failure and correction

The first actual user submission after PR677 returned MissingGreenlet before
commit. Production read-only verification found no receipt or current attempt,
an unpaid invoice/invoiced order, and unchanged Ready-to-Close count and work
value. No agent retried or confirmed a financial request.

The reviewed-ancestry proof refreshes RepairOrder with populate_existing,
expiring its customer relationship. Same-session fixtures retained the Customer
in the identity map and masked lazy async I/O during paid-outcome enqueue. A
new AsyncSession calling the actual endpoint reproduced MissingGreenlet before
the fix. The service now explicitly awaits loading the customer after locked
eligibility and retains those references through closeout and outcome enqueue.
The strict ancestry proof and all monetary decisions remain intact.

## Acceptance

New fresh-request regression exercises the actual cash endpoint and commit,
checks Ready-to-Close presence/nonzero value before payment, a single receipt
and paid invoice/order afterward, exclusion/zero value and Closed Today presence,
and same-key replay from another session without a duplicate receipt. A separate
injected precommit outcome failure verifies rollback leaves no receipt, paid_at,
or closed order. These are synthetic memory-database payments only.

Independent QA/Security and protected CI are required. Local full stack remains
unavailable without approved backend configuration; shared a2 servers remain
untouched. No real payment will be submitted for acceptance. Postdeploy checks
will use exact build/source and a read-only database transaction. The user's
actual collection remains a separate action after release.

Rollback: revert the focused application change if async loading fails, paid
closeout diverges, replay duplicates, or eligibility broadens. No schema rollback.
A live submission error or uncertain result requires receipt/state inspection
before any user retry. Do not mark the actual order paid from deployment evidence.

## Owner verification

189 focused cases pass across fresh-request cash, reviewed test/sandbox/owner
cash, ordinary cash, timing/panel availability, and paid-invoice webhook suites.
New test lint and changed source lint pass excluding five pre-existing UP017
datetime-alias findings in the cash service; no new lint finding. Diff check clean.
Independent reviews and CI remain pending.

## Independent gates and PR

[QA GO](DB048_CASH_FRESH_REQUEST_QA.md):198 permanent cases and pinned prior
deployed-code red reproduction1/1. [Security GO](DB048_CASH_FRESH_REQUEST_SECURITY.md):
138 cases, no expanded financial/permission/tenant/provider boundary. Reviewed
source hashes unchanged. PR679 integrates docs-only maincf11290e without source
conflict. Full protected CI and deployment remain required before release.
