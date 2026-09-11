# DB-048 Fleet Check / Code — canonical tender v1

Status: Architecture contract acknowledged by root; backend implementation in progress.
Owner: root accountable; Architecture & Backend owns Fleet backend; root owns UI.

## Outcome and existing evidence

Restore the legacy Fleet Check / Code choice under the inline expanded More tender
grid. The previous panel offers EFS / MoneyCode (`EFS`), Comchek (`Comchek`),
T-Chek (`T-Chek`) and Other provider (`Other`). Canonical settlement currently
omits Fleet; this is a distinct `fleet_payment` rail, never relabeled Check.
Staff verify an externally received instrument. This does not redeem an EFS code,
initiate a provider charge, or claim the instrument has cleared a bank.

## API v1 additive shape

Existing staff POST `/payments/invoices/{id}/attempts` accepts:

```json
{
  "amount": "50.00",
  "rail": "fleet_payment",
  "expected_settlement_version": 2,
  "sender_evidence": {
    "fleet_provider": "EFS",
    "fleet_provider_name": null,
    "reference_number": "verified-instrument-trace",
    "authorization_number": "optional-approval-trace",
    "note": "optional staff note"
  }
}
```

`fleet_provider` is one of the exact four values above. `fleet_provider_name`
(1–100 characters) is required only for Other. `reference_number` (1–255)
is required; the existing `reference` alias is accepted when unambiguous.
`authorization_number` (1–255) is optional, for an already issued approval trace,
not a reusable account secret or provider credential. Note retains the existing
1000-character bound. Text is trimmed and blank optional values become null.
Contradictory aliases, missing provider/trace or malformed input return 422.

The pending attempt, reserved principal and staff confirmation use existing
endpoints and versions. Confirm uses the frozen trace; a different explicit trace
returns 409 rather than silently replacing its instrument. Partial or full positive
amounts are supported; fees and fee tax are always zero. Quote accepts Fleet and
returns the existing authoritative principal-only quote. Customer/guest creation
and confirmation remain denied, and their advertised rails remain card/Zelle.
Fleet confirmation must use exactly the reserved amount (or omit received_amount);
if the verified amount differs, cancel and recreate the pending attempt. This
preserves the immutable gross-receipt snapshot and does not restrict partial
invoice payments.

Staff allocations expose additive `fleet_provider`, `fleet_provider_name` and
`authorization_number` values. Customer/guest views get no staff-only Fleet
provider/approval fields and continue to receive masked references. Existing
`provider` remains `manual`, not the Fleet brand. Payment compatibility projection
uses `PaymentMethod.FLEET_PAYMENT`, provider label, reference and optional approval.

## Immutable identity, duplicates and accounting

Fleet evidence is frozen on creation, with actor/time retained in existing attempt
and ledger snapshots. One verified instrument can fund exactly one canonical
receipt/attempt (which may partially pay one invoice). Same-tenant/provider/trace
reuse on another attempt, including another customer or refunded/reversed receipt,
returns 409. Replaying the original idempotency key returns the original receipt;
changing evidence with that key returns idempotency conflict. Different tenants
or different providers may independently use the same reference. Other-provider
name is part of the normalized provider identity. Pending abandoned attempts do
not count as received money; confirmation performs duplicate serialization and
the database independently enforces the received-reference identity.

Fleet uses the existing snapshotted `check_deposit_account` because it represents
a bank-deposited instrument, not cash and not an electronic transfer. Missing
mapping fails closed. Provider/reference remain distinct in QBO PaymentRefNum
(existing 21-character cap) and complete private memo; no silent loss of the full
trace. Both legacy-principal and gross receipt writers, refunds/recovery and credit
source-account mappings use this same destination. Historical export holds and
new-receipt admission guards remain unchanged; no historical backfill/export is
performed. Cash remains full-only and local-only, incompatible with prior Fleet
or other noncash allocations.

## Migration, gates and rollback

Migration146 follows charge-adjustment145. Add Fleet to the rail CHECK, add a
tenant-wide Fleet reference unique index and a Fleet-only frozen-evidence guard;
no existing attempt, reservation or history rewrite. Downgrade refuses while any
Fleet attempt exists. Deploy migration, guarded workers, API/UI in that order;
after Fleet data exists, disable its entry point and forward-fix rather than
rolling a writer back to code that cannot process the rail.

Acceptance: partial/full confirmation; all four providers; optional approval;
required Other name; fee-free quote and receipt; evidence survives allocations,
Payment and QBO memo/reference; original idempotent replay and conflicting replay;
duplicate reference within/across customers and after refund; distinct provider
and tenant reference reuse; foreign tenant and customer/guest/no-permission denial;
stale version; pending reservation and cash-mixing exclusion; immutable evidence;
preserved historical holds; selected deposit mapping in legacy/gross/refund paths;
PostgreSQL migration/unique-index/immutable-guard/downgrade rehearsal. Independent
QA/Security gate required. Tests must not redeem an instrument or write production.
