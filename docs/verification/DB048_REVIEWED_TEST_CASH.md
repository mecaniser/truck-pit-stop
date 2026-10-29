# DB-048 audited test history and Cash

Accountable owner: Backend & Integrations (root). Branch codex/reviewed-test-cash-ancestry from refresh merge44575250. Architecture contract: ../contracts/db048-owner-attested-test-cash-ancestry.md v1.1. No schema, migration, API or provider-dispatch contract change.

The user's explicitly authorized internal test-reservation reconciliation preserves its cancelled ancestor and immutable ledger. Noncash readiness recovered, but Cash's generic historical-row guard still blocked it. The separate reader recognizes only a single failed customer-portal QuickBooks-card test with trusted privileged audit evidence, coherent same-tenant/order/customer links, no received/provider/accounting/credit/dispute rows, zero balances and complete conserved creation/maintenance/failure history. It skips only generic row/history-sequence rejection, after existing accounting/export checks. Existing signed owner-cash reviews are unchanged. Cash confirmation re-evaluates the same helper under its existing financial lock.

Acceptance includes actual fixture receipt creation with predecessor history unchanged, arbitrary code/no marker rejection, malformed/nested/contradictory provider evidence, actor revocation/tenant mismatch, new attempts/history, ledger/time/snapshot drift and retained accounting denial. Missing or boolean money is not zero. Ledger timestamp and wall-clock failure time allow only the documented five-minute offset. No code or fixtures hardcode production IDs or private financial facts.

## Gates

Owner136 focused tests passed across new reviewed-test cash, existing cash, owner-attested cash and sandbox review suites. Independent Security136/136 GO; independent QA138/138 GO includes both original private denial reproductions. See DB048_REVIEWED_TEST_CASH_QA.md. New-source Ruff passes; changed-source diff check clean. Original NO-GOs for time mismatch/nested provider identity were corrected before release, along with contradictory creation/terminal evidence and states. Security evidence is retained privately outside committed docs.

A read-only production shadow evaluation of the proposed helper qualifies the exact owner-attested existing history with provider_contacted=false. That does not change production code/eligibility or record a receipt. The prior operational release has fresh independent persisted-state GO: only old attempt/reservation and one failure audit changed; invoices/order/config/outbox unchanged; no real receipt/provider call. Private customer evidence remains local.

Runtime: shared5173/8000 belong to a2 and remain untouched. This worktree lacks approved backend/.env; isolated SQLite fixtures exercise eligibility and actual cash receipt semantics without a provider. Full-stack local browser mutations are not claimed. Frontend UI/contracts are unchanged; live signed-in Cash availability after the exact backend deploy is the remaining acceptance.

Status: REVIEW. Protected CI, exact merge/deployment, rollback readiness and live read-only Cash selection remain pending. No real payment should be submitted to test this release. Roll back this application-only helper if it admits history outside its strict evidence contract; retained audit rows and financial state require no rollback.

## Release — 2026-10-29 UTC

PR677 head1b030e800b7b6951f36dcee019db1bd3c90cf090 passed all seven checks in40952418679, including full backend/frontend and browser smoke. Squash merge e8f5feae146b6209e1a4e06de85a822ef88ecb99 at20:57:06UTC has identical tree f494d97461f09e9fe45664797a1717dcbac5776e. Railway Web4e193df5-0783-4301-bc3e-a3a36aa2a74c is SUCCESS; both www/api build-version serve e8f5feae and readiness reports database/Redis OK. No migration/provider/configuration/worker rollout was needed for this API reader change.

Independent fresh production read-only postgate GO confirms deployed reviewed source fingerprints, actual staff settlement_summary confirm_cash=true with no unavailable reason, existing noncash methods admitted, and current invoice/order still unpaid/invoiced. Original retired attempt failed/zero reservation/three immutable ledger events, preserved invoices/order/outbox/configuration/other settlement hashes, and zero payment/refund/overpayment/accounting/dispute/provider settlement entries before and after summary. No payment/provider/token call occurred. Private evidence is retained under output/payment51/ and excluded from source commits.

Final signed-in visual Cash-button check is temporarily blocked because macOS locked before native controls could continue; user was asked to unlock. This is the sole remaining acceptance gate, not a failure of deployed eligibility. Original in-app browser returned to sign-in; an existing signed-in Chrome session was used successfully for prior workspace/payment inspection without credentials/session copying. The browser is never allowed to submit a real payment for acceptance. Do not mark the Cash outcome Done until final visual acceptance is recorded, or the product owner explicitly accepts the server/domain evidence in its place.

## Final signed-in visual acceptance — 2026-10-29

PASS; this supersedes the temporary locked-Mac visual gate above. After the user unlocked macOS, the existing staff Chrome session was restored and the exact selected repair-order workspace opened. The live payment dialog shows Cash enabled and no predecessor-payment warning. Selecting Cash shows the full invoice principal, removes the card fee and enables the cash-received confirmation button. The confirmation button was not clicked; no real payment was submitted. The invoice remained Unpaid. Native accessibility evidence directly identified the enabled radio and confirmation controls; no browser injection, session copying, payment-submission request or payment-provider action was used for this acceptance.

Fresh build-version still equals e8f5feae146b6209e1a4e06de85a822ef88ecb99 and database/Redis readiness passes. All required implementation, automated/independent gates, checked-tree merge, deployment, live read-only server and signed-in visual evidence now exist. Status: DONE / RELEASED AND VERIFIED. Actual payment collection remains the user's separate action.

## Submission acceptance reopened — 2026-10-29

The preceding visual check verified availability only. The user's subsequent
actual Cash submission failed before commit with MissingGreenlet while loading
the customer for paid-outcome enqueue. Fresh production read-only evidence
confirms no saved payment and unchanged unpaid/order/queue state. The payment
workflow is reopened under [fresh-request correction](DB048_CASH_FRESH_REQUEST.md);
no agent resubmission or production financial mutation.
