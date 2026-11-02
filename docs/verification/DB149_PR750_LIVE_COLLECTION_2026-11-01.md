# DB-149 PR750 release and exact invoice activation — November 1, 2026 (New York)

Backend & Integrations owns the collection release; Frontend & UX owns the final accounting-note refinement. The user explicitly approved merge/deploy and activation of ETS invoice1687/service1821 for268.44 under the existing DBN customer account, with no payment submission.

## Source and release evidence

PR750 all7 checks PASS in41360994357 at748e6f231f15cd805c914ad450e357720b102f2b; independent final admission delta100/100 PASS underUTC matchingCI (all6 new cases pass both timezone runs). Squash mergee28b92b5249a441fd9d4d4304e7f34e6494bdcc5.

Git auto-deployment metadata omitted required configuration. The queued collector exposed five-minute scheduling and Web omitted migration/predeploy safeguards. Those exact deployments were canceled before activation. No full importer or cron job was manually run. Replacements used a clean detached tree of the exact merge and each service's checked-in configuration:

- Webd16514fb-33df-4623-bd3c-df55c222f426 SUCCESS: migration197, financial guards, DB/Redis readiness; all60 changed backend/frontend source file hashes match the merge.
- Workerf91fda8b-d4df-4a18-b1fd-b127f9b3e063 SUCCESS: all42 changed backend files match. Image sha256:4e08e75fc1b3028481fb4c0e347ce6f648e20e38e4987ca689ec0d0e1db7e7e6.
- Collector3fd532a0-6175-4240-a53f-1a44df8e0b04 SUCCESS/buildOnly: effective and file daily00:00UTC, NEVER restart. Image sha256:ee5341b60d23cd4ec99534d7703381c5d494de01321a5329eab80a8a0a0bae55. Stopped cron container has no direct runtime hash canary; no run was started to obtain one.

Public build stamp is null for the manual upload; it is not claimed as SHA proof. Exact source hash read-back and clean merge input provide separate release identity evidence. Future Git deployment configuration drift remains an operational follow-up; do not apply unrelated staged environment changes.

## Exact live handoff

Two bounded read-only ETS captures verified total/balance268.44, zero allocations and immutable invoice468019/service506423/customer97052 identity. The second observation occurred after owner acknowledgement. Evidence-only bootstrap and versioned refresh ran dry first and then explicit commit, preserving scoped financial fingerprints. No normal importer ran.

Authenticated garage owner prepared handoff4a4f088b-bb53-4832-8bbd-f07108b29f5c with the user's exact same-legal-business review. Original source customer70755fe9-6dfd-4d17-9b1b-b86cc8ab973f remains unchanged; target portal customer1dd0a2cd-f621-47e9-b06c-14990c90e7fe owns only the linked collectible.

An initial activation correctly rejected the operator's stale pre-refresh capture identifier with409. No native invoice or payment was created. Fresh authenticated GET returned the effective capture identifier; the corrected request succeeded200. No guard or code was weakened.

Active handoff version2 links native invoice890f4fe6-4719-4bca-b8ba-8666cfabfddd / DBN-COL-4A4F088BBB5348328BBD. One settlement268.44, confirmed0/pending0/due268.44. Source invoice remains268.44/sent/unpaid under its original customer and original RO. Zero payments, attempts, ledger receipts, payment accounting links or native provider outbox events. Old314.02 invoice was excluded and unchanged.

Actual invoice-scoped readiness is ready/QuickBooksPayments, collection enabled, no holds. This verifies configuration and availability, not provider acceptance of a real charge. No checkout, tokenization, reservation or charge was initiated.

## Customer and accounting acceptance

Actual customer session Elis Logistics can open the linked invoice with268.44 due/available,0paid/0pending, original ETS1687 reference and original issued amount. QuickBooksPayments Continue and Zelle controls are enabled; neither was submitted. Customer-authorized PDF download succeeds and shows the DBN bill-to,268.44 transferred/due,0applied and review link/QR on one page. Original invoice dateOctober19 is displayed; imported source due_date is null, so no new due date is fabricated. Actual PDF and screenshots remain private local artifacts.

Independent actual feed comparisons before/after activation show identical IDs, revisions and snapshots: invoice feed20 records; complete financial feed15 authorized records. Their different existing scope counts were preserved, not conflated.

## Final presentation refinement

Runtime exposed external_reconciliation_pending falling through to a red QuickBooks error and a false already-recorded-payment sentence. The focused follow-up recognizes the existing backend status, uses neutral manualETS accounting copy and leaves actual failed accounting alerts intact. No backend, permission, payment, amount, tender or provider change. Failing-first2 failures/32 passes; after correction48 focused portal/settlement checks PASS, production build/TypeScript and independent34/34 delta review PASS. Changed-source lint, protected CI and final live copy acceptance are recorded at completion.

Mandatory local runtime preflight: clean merge checkout, then codex/collection-accounting-status-copy; approved backend configuration absent; unrelated Docker8000 preserved (PID3415, Docker data root). No aligned local app or local full-stack acceptance claimed. Component checks and final live acceptance are separate evidence.
