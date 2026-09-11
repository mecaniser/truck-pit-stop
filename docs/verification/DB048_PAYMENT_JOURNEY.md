# DB-048 payment journey: local reviewed candidate

## Inline charge switches and card surcharge waiver

Exact implementation `a0754cc248f8b57cf67e29ff10245fe3894c7e5a` supersedes the separate controls layout below. All three switches sit beside their breakdown amounts. ON applies Sales tax, Shop supplies or Card processing fee; OFF retains the row at zero. Card-fee OFF also removes fee tax, but never invents or changes the actual processor cost borne by the shop. Saves persist through the existing145 audited adjustment flow, with original frozen pricing restored on reversal and unchanged history/payment/export locks.

Independent QA/Security GO: backend65, PostgreSQL6, UI74, no unresolved P0/P1/P2. Owner backend107/PG6, UI83, TypeScript and changed-source lint pass. Browser fixture checks use250ms latency for writes/quotes, sampling every frame through18 on/off saves at1280/390/320: stable rows/dialog/breakdown height, no horizontal overflow, submission disabled during updates. In-app local preview also verified fee/tax zero and exact restoration without height change. Runtime data are synthetic; production acceptance is separate. No new migration for surcharge setting; reviewed144→145→146 remain the rollout requirement.

The query may retain a prior same-invoice/same-tender quote for display during recalculation; it is never eligible for submission. Version/amount/rail match, successful fresh quote, and completed invoice save are still required. Failed/uncertain saves remain visible, retry the same request, and never unlock collection optimistically.

## One-click autosave successor — 2026-09-11

User removes the extra Update invoice step. Successor
`0b249edaaef8613089db2f71b5bf4af3ac55394e` saves each tax/supplies switch immediately;
there is no normal Save/Discard action. Reference remains optional/on-demand and
saves on blur or Enter. Payment is paused while saving or awaiting resolution.
The server response updates invoice totals and triggers a fresh fee quote.
Explicit rejection restores saved state; uncertain responses retain their exact
key/body for Retry; stale versions offer refresh rather than overwriting.

Owner tests99/type/lint passed. Independent QA/Security GO40/40, including10 new
autosave cases, no unresolved P0/P1/P2. Review found and cleared a reference-blur
race: a held pointer could start a reference-only save before the toggle click.
Pointerdown now preserves reference focus until click submits both values;
separated down/up and canceled-click regressions pass. No mutation on pointerdown.

In-app synthetic acceptance: one click removes supplies; one click applies or
reverses tax; restoring supplies and tax returns1160.49. Typing EXAMPLE-CERT and
clicking supplies saves both correctly. No Update/Discard controls remain.
Backend, migration, guards and accounting behavior unchanged from the prior gate.
This supersedes the explicit-update UX described in the historical receipt below.
Still local only, not pushed, merged or deployed.

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
