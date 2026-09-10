# DB-048 sandbox acceptance — 2026-09-10

Owner: Backend & Integrations. Status: Bounded sandbox acceptance passed;
not a production release or bank-payout approval.
Base candidate: `186ea1978dc3b11444db4e8865d91e0651213eee`.
Realm: `9341457819957473`. Production was not mutated.

## Capture and refund: actual Intuit sandbox calls

Run ID: `5a8b45c7-dc13-4b5f-a6d3-bb7c94ec2026`.
Fixed amount: $1.03, public synthetic Intuit test card.

| Operation | Result |
| --- | --- |
| Create token | HTTP201; token not retained in evidence |
| Capture | HTTP201; `MT0359488296`, $1.03, CAPTURED |
| Repeat identical capture key | HTTP200; same charge identity |
| GET charge | HTTP200; amount and identity matched |
| Full refund of that new charge | HTTP201; `MT7353020517`, $1.03, ISSUED |
| Repeat identical refund key | HTTP400; test stopped |
| Independent GET charge | `MT0359488296`, $1.03, CANCELLED |
| Independent GET refund | `MT7353020517`, $1.03, ISSUED |

The independent readback used two GETs and zero writes. A refund was issued;
this is not evidence of a bank payout or settlement. No additional capture or
refund is needed to investigate the observed replay behavior.

Independent review reproduced a P1 in the existing QBP refund worker: ISSUED
was not recognized, its ID was not persisted before a retryable exception,
and a subsequent HTTP400 could finalize the accepted refund as failed. The
bounded correction now passes independent QA/Security: 146/146 checks,
including 24 new refund cases. Final reviewed reconciliation blob is
`c2f94f5c3450ca49e21e6888cc87e701ea453d23`; Payments client
`9f7ac44e0de28b5ef0e2fe2ffb54b11f70548261`; tests
`2e0a7455e663f2e9e7321411387a4864b487f871`.

The corrected production client and outbox worker were then exercised against
the exact already-created refund in disposable SQLite. Company GET and refund
GET returned200; the worker retained the refund ID and accepted/pending state,
with zero POSTs and zero shared DB writes. The final six-hour polling schedule
and fourteen-day actionable deadline are independently tested. Intuit's
documented `SETTLED` and `DECLINED` outcomes are fixture-tested; the actual
sandbox refund still reports `ISSUED`, so neither settlement nor failure is
claimed for it. Runtime harness blob:
`0ec04240c7312151b45b696901c0984b285f9a37`.

## Fee-tax signed adjustment: actual Accounting sandbox calls

GET preflight verified active TaxCode2 with single TaxRate3 at 8%, service
Item19, fee Item1, and sandbox clearing mappings. Intended fixture:
$100 principal + $3 customer card fee + $0.24 fee tax = $103.24.

First attempt created only Customer62 (`TPS-DB048-SBX-77ad791`). Invoice
creation returned HTTP400 before an invoice or payment was returned. The
original client discarded fault details, so that response alone does not
establish the cause. The US tax-payload correction and a sanitized fault
observer are under independent review before another controlled test.

Second attempt (after independently approved TAX/NON + transaction tax-code
correction): Customer63, Invoice158 (`TPS-DB048-SBX-6f1d19a`), Payment159.
Invoice/payment $103.24, tax $0.24, zero balance, and zero-POST replay passed.
The signed -$3 fee/-$0.24 tax invoice adjustment passed, returning total $100.
The following payment update failed with the now-observable provider code5010
(Stale Object Error). A separate read-only check showed:

- Invoice158: SyncToken2, total $100, balance $0, tax $0.
- Payment159: SyncToken1, total $103.24, allocated $100 to Invoice158,
  unapplied $3.24.

QuickBooks automatically clipped the allocation and incremented the receipt
version when its linked invoice shrank. The fix must reread that receipt,
permit only the exact mathematically justified clipping, and reject all
foreign identity/money/allocation changes. Genuine concurrent stale responses
must retain numeric fault code5010 for the existing bounded retry logic.
This partial test is retained as evidence, not represented as a passed
reversal/recovery scenario. No cleanup or manual balancing was performed.

Third attempt: Customer64, Invoice160 (`TPS-DB048-SBX-0a522dc`), Payment161.
Initial $103.24/tax $0.24/zero balance and replay passed. The invoice adjusted
to $100, then the payment update to zero returned HTTP200. The readback guard
stopped because QuickBooks omits `DepositToAccountRef` on the zero-value
payment. Separate GETs confirmed payment total/unapplied0, empty lines,
unchanged customer/currency/reference/memo, and invoice balance100. This
requires a zero-only omission rule while retaining the original clearing
account for positive recovery. It does not justify accepting missing accounts
on positive receipts. This run is retained without manual repair.

Existing Invoice153 and all prior accounting records remain untouched.
New fixtures are intentionally retained; no cleanup/delete was performed.

## Final fee-tax reversal/recovery acceptance: PASSED

Customer65; Invoice162 `TPS-DB048-SBX-4ac70dd`; Payment163.
Real Intuit Accounting sandbox calls, with synthetic dispute/recovery events
in the isolated local domain fixture (not a real Stripe dispute).

| Phase | Invoice total | Tax | Payment | Balance | Replay POSTs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial fee-tax payment | 103.24 | 0.24 | 103.24 | 0 | 0 |
| Dispute compensation | 100.00 | 0 | 0 | 100.00 | 0 |
| Recovery | 103.24 | 0.24 | 103.24 | 0 | 0 |

All phases passed provider readback. Seven POSTs total: one customer, one
invoice, one payment, two invoice updates, two payment updates. No fee journal
was created. Original posted attempt components remained unchanged; signed
fee history is +3/-3/+3, with final tax0.24 and restored clearing1150040000.
An independent reviewer separately performed exactly two GETs: Invoice162
and Payment163. Customer65, invoice reference, sales lines100/+3/-3/+3,
tax0.24, total103.24, zero balance, full single-invoice allocation, zero
unapplied money, USD, and clearing1150040000 all matched. No writes occurred.

Final reviewed blobs:

- Gross writer: `5ae926615392e3ebe95c8b0e209f44794ff63b63`.
- Accounting client: `7a6294ba3b131eb41e95a356673c6aa46af2a412`.
- Gross tests: `245e3d42fc21231c26d7f9adb594c27ed50dd9bc`.
- Fee harness: `db9fb1933509c2f40f8109725a2f434752b9ec60`.

Independent fee gate passed197 checks before the final zero-shape correction,
then71 focused checks and13 independent exact-zero probes (2 positive,
11 negative), plus the unchanged ten-case harness fence. Author combined
fee-related suites passed212. Final root regression on the complete frozen
source passed419/419 across twelve DB-048 modules in97.04s; only existing38
deprecation warnings. PostgreSQL-only integration suites were not rerun:
this correction adds no schema or migration and isolated SQLite/runtime
tests cover changed behavior. Production deployment is not implied.

## Isolation and limits

- Candidate backend mounted read-only into a disposable container, no ports.
- Existing sandbox OAuth credential read from a read-only local transaction.
- Test business records live only in in-memory SQLite; no shared DB writes.
- Exact sandbox hosts/realm and newly returned IDs are fenced.
- No production feature activation, migration, deployment, or money movement.
- These tests do not establish native bank-payout matching for the new charge.
