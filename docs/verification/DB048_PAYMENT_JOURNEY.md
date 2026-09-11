# DB-048 payment journey: local reviewed candidate

Accountable owner: root. Branch `codex/db048-payment-journey`.
Implementation candidate `a83f302cdef62b246f25bdb11fea9f0450edf8cd`, tree
`e5c4cd9f39876edc18a72b62a6c288339e296825`, base `d2a37545`.
Not pushed, merged or deployed. Production data/holds/reservations unchanged.

## Delivered for local review

- Compact QBO Payments, Zelle and Cash. More/Less expands the same grid with
  Check, ACH and Fleet Check / Code, below the options at left; partial amount
  control remains right. Hidden selected secondary tender remains accessible.
- Conditional settlement figures; full amount default, explicit partial editor,
  authoritative invoice/fee breakdown and final collection amount. Vehicle
  release is collapsed, not removed. Cash remains full-only, local-only, unmixed.
- Reversible saved sales-tax exemption and shop-supplies controls with explicit
  Update invoice / Discard changes, optional reference on demand and frozen
  same-key retry after uncertain responses. Original invoice money/audits are
  retained; paid/pending/unsafe historical invoice adjustment guards remain.
- Customer-profile tax default for new invoices, separately audited144.
- Fleet canonical staff rail146: EFS/MoneyCode, Comchek, T-Chek, Other; fee-free
  full/partial, verified instrument/approval evidence, exact reserved amount,
  tenant/provider duplicate protection and banked accounting mapping.
- Staff pending Zelle review receives saved sender/contact/reference/note and
  confirms that same attempt. Missing bank references are never fabricated.
  Customer/guest allocations exclude submitted evidence. Portal creation can
  include optional transfer details using the existing evidence payload.

## Verification

Owner: frontend payment/customer suites **94 passed**, TypeScript, changed-source
ESLint, production build and diff checks passed. Backend implementation evidence:
customer/charges128 passed1 skipped, charge13, PostgreSQL8; Fleet/checkout/cash78,
adjacent financial/accounting281, Fleet PostgreSQL3. Overlapping suites are not
summed as unique tests. Separate Fleet handoff provides exact boundaries.

Independent QA/Security **GO at a83f302c**: Fleet39, Fleet PostgreSQL3, focused UI79;
previous independently verified charges60 and combined customer/charge PostgreSQL8
carry on unchanged source fingerprints. No unresolved P0/P1/P2 finding. Reviewer
did not implement or edit code. Production acceptance remains a separate gate.

In-app synthetic preview5196: saved exemption lowers fixture1160.49→1072.05;
tax restore with supplies off produces1134.51; re-enabling supplies restores
1160.49 exactly. Saved toggles remain enabled where safe. Fleet submenu lists
all four providers; noncard has no card fee. Pending Zelle fixture shows its
existing500 reservation, submitted contact, EXAMPLE-ZELLE-500 reference and note.
No payment submission or provider call was performed in browser acceptance.

Independent local automated viewport390x844 and320x740: six expanded tenders,
44px targets, no horizontal overflow (scrollWidth equals viewport), More below
grid and left of partial control; Fleet Other reveals required provider name.
Screenshot: local `output/playwright/db048-journey/expanded-320.png`. Only console
error was synthetic preview favicon404; no application exception. User's in-app
preview was not resized. Preview/fixture/output files remain outside the commit.

## Remaining release work

User is reviewing local development. Keep preview5196 running. Next release is
one focused PR, protected CI, migrations144→145→146, matching guarded workers,
then API/UI, followed by signed-in non-mutating acceptance. No bulk cash receipts,
historical export release, shop activation or real-money pilot is authorized by
this UI review. Once Fleet data exists, do not downgrade146 or roll writers back
to code that rejects Fleet; disable admission and forward-fix if necessary.
