# DB048 historical export hold

Accountable: Backend & Integrations. User-authorized outcome: isolate historical/unreviewed records and show their list before any production-processing activation.

## Boundary

Add historical_export_hold as a distinct invoice accounting policy. Never substitute local_cash_only or mutate paid status/balance to suppress exports. New invoices default to standard. This release does not change provider environments, connections, feature flags, charge/refund state, or enable production workers.

## Application

An operator generates an exact tenant/invoice-ID/cutoff manifest with previous policy, QBO identifiers and fingerprints of financial records. Application requires the exact reviewed SHA256, locks settlement then invoice then financial outbox, rechecks every fingerprint and applies atomically. Reject linked/synced/successful exports, pending attempts/refunds, financial leases, local cash and out-of-scope records. Email notification locks are unrelated. Preserve original financial/outbox evidence. No automatic release; no release operation in this item.

## Writer guards

Fresh locked policy must stop invoice, customer/item creation, manual sync, direct legacy charge/refund, canonical accounting/refund/credit source and destination delivery before provider writes. Noncash creation/confirmation on a held invoice requires individual review. Existing real-money callbacks are not discarded. Existing eligible cash remains subject to unchanged full-cash/no-history checks; hold does not clear ambiguity or authorize receipt.

## Acceptance and negative cases

- Held invoice causes zero provider writes via all enumerated routes, regardless of rollout flags.
- Other tenants and new standard invoices retain behavior.
- Wrong tenant, changed fingerprint, duplicate IDs, active money/lease, successful export and wrong manifest hash fail without partial application.
- Payment totals/status/history remain unchanged; email events unchanged; failed/succeeded queue history retained.
- Repeated invocation cannot silently release or broaden the manifest; explicit already-held handling is required.
- No production activation accompanies schema/guard installation or hold application.

## Review evidence

Initial read-only snapshot: NC1381 nondeleted invoices;1376 proposed candidates,4 prior-sync-marker records and1 pending-card record excluded.509dead,2deferred,6succeeded QBO issuance events; zero NC pending/processing or canonical financial events; no legacy QBO charge/refund payments. Two other-tenant processing jobs prohibit an indiscriminate shared-worker environment change. Local full list is historical-export-inventory.csv, not public PR data.
