# DB-048 cash choice at payment time

Owner: Backend & Integrations. Follow-up to PR369, baseline3ada1122.

## Accepted contract

- In shops with the effective DB048 split-payment flow enabled, issuing or
  emailing an invoice does not cause its first QuickBooks accounting export.
- A confirmed noncash payment (including the first partial payment) allows the
  full invoice and applied payment to be exported. Staff and customer checkout
  use the same confirmation/accounting flow. Pending/failed attempts are not
  payment confirmation. Existing legacy completed noncash evidence is recognized.
- Preserve legacy export timing for shops outside this rollout. Local-cash-only
  invoices remain nonexportable regardless of rollout switches.
- Existing linked QuickBooks invoice updates/voids retain their lifecycle;
  never remove or shrink an existing accounting invoice to make cash possible.
- Producers, retry workers and direct accounting paths enforce first-export
  eligibility. Manual sync responds truthfully when awaiting payment.
- Cash permits native or reconciled legacy unpaid baselines, only with zero
  settlement balances and no actual payment/attempt/ledger/accounting-link history.
  Unknown legacy reconciliation states fail closed with an accurate reason.
- Known ordinary invoice email/SMS events neither block cash nor get suppressed
  when cash is confirmed. Unknown financial/delivery events remain reviewable.
- Prior ambiguous export attempts, processing leases, company changes and linked
  QBO records remain blockers. Deferral does not rewrite uncertain history as
  proven no-dispatch evidence.
- Deferral must not overwrite an orphan error/syncing/synced status into a
  clean awaiting-payment status when that status is the only evidence of earlier
  accounting activity. Preserve the review blocker and cover before/after enqueue.
- Cash remains full-only, staff-confirmed, tenant-scoped, idempotent and local.
  No real financial records will be edited to demonstrate acceptance.

## Verification

Positive: issuance+notification then cash eligibility; clean reconciled legacy;
confirmed noncash partial permits full invoice+receipt; linked invoice lifecycle.
Negative: pending/failed payment, mixed/historical activity, wrong tenant,
unknown legacy state, nonallowlisted events, ambiguous export, active lease,
local-cash export through producer/worker/direct path. Preserve nonpilot behavior.
Independent Security/QA review required before release. No migration expected.

## Observed production examples (read-only)

The newly issued example has native zero-payment state, an email notification,
and a processing QBO export. The older example has reconciled zero balances,
an email notification, and five historical failed export attempts. Correcting
email/legacy gates alone must not claim these export histories are safe.
