# DB-048 audited test history and Cash

Accountable owner: Backend & Integrations (root). Branch codex/reviewed-test-cash-ancestry from refresh merge44575250. Architecture contract: ../contracts/db048-owner-attested-test-cash-ancestry.md v1.1. No schema, migration, API or provider-dispatch contract change.

The user's explicitly authorized internal test-reservation reconciliation preserves its cancelled ancestor and immutable ledger. Noncash readiness recovered, but Cash's generic historical-row guard still blocked it. The separate reader recognizes only a single failed customer-portal QuickBooks-card test with trusted privileged audit evidence, coherent same-tenant/order/customer links, no received/provider/accounting/credit/dispute rows, zero balances and complete conserved creation/maintenance/failure history. It skips only generic row/history-sequence rejection, after existing accounting/export checks. Existing signed owner-cash reviews are unchanged. Cash confirmation re-evaluates the same helper under its existing financial lock.

Acceptance includes actual fixture receipt creation with predecessor history unchanged, arbitrary code/no marker rejection, malformed/nested/contradictory provider evidence, actor revocation/tenant mismatch, new attempts/history, ledger/time/snapshot drift and retained accounting denial. Missing or boolean money is not zero. Ledger timestamp and wall-clock failure time allow only the documented five-minute offset. No code or fixtures hardcode production IDs or private financial facts.

## Gates

Owner136 focused tests passed across new reviewed-test cash, existing cash, owner-attested cash and sandbox review suites. Independent Security136/136 GO; independent QA138/138 GO includes both original private denial reproductions. See DB048_REVIEWED_TEST_CASH_QA.md. New-source Ruff passes; changed-source diff check clean. Original NO-GOs for time mismatch/nested provider identity were corrected before release, along with contradictory creation/terminal evidence and states. Security evidence is retained privately outside committed docs.

A read-only production shadow evaluation of the proposed helper qualifies the exact owner-attested existing history with provider_contacted=false. That does not change production code/eligibility or record a receipt. The prior operational release has fresh independent persisted-state GO: only old attempt/reservation and one failure audit changed; invoices/order/config/outbox unchanged; no real receipt/provider call. Private customer evidence remains local.

Runtime: shared5173/8000 belong to a2 and remain untouched. This worktree lacks approved backend/.env; isolated SQLite fixtures exercise eligibility and actual cash receipt semantics without a provider. Full-stack local browser mutations are not claimed. Frontend UI/contracts are unchanged; live signed-in Cash availability after the exact backend deploy is the remaining acceptance.

Status: REVIEW. Protected CI, exact merge/deployment, rollback readiness and live read-only Cash selection remain pending. No real payment should be submitted to test this release. Roll back this application-only helper if it admits history outside its strict evidence contract; retained audit rows and financial state require no rollback.
