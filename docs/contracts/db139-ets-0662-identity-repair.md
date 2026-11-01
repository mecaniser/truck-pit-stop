# DB-139 historical ETS association correction

Accountable owner: Backend & Integrations. Architecture accepts historical source provenance; Security/QA reviews exact script and production dry-run before any apply.

## Evidence and direction

The preserved August 24 vehicle-scoped source capture binds all four service 0662 operations to source vehicle 106566/customer 91612. Its SHA-256 is `f72882d175406468af2ba22d80c734b11b0ce818062c6a00dfdab86cfc4a404a`. The scraper fetches service history from the specific vehicle route and the importer uses that vehicle's source identity. Current database evidence still binds service 0662/internal 348595 to source invoice 321290/invoice 0625. The July legacy owner is on an imported vehicle without external ID; the August three siblings already use the uniquely mapped source vehicle. This proves original historical association, not current physical ownership inferred from a reused unit number.

Correct **only the invoice-owning repair order's vehicle link** to the existing source-mapped vehicle. Preserve all three sibling links, both vehicle records, customer links, other seven repair orders, invoice ownership, payments, settlement, ledger and source evidence. Do not merge vehicles, rerun imports, recapture source observations, or repair other historical jobs.

## Guarded procedure

`backend/scripts/repair_ets_0662_vehicle_link.py` has five explicit stages:

1. `source-proof --capture PRIVATE_CAPTURE --out PRIVATE_PROOF`: offline hash and exact four-operation binding validation. Exports only source identifiers/count/digests, never raw capture/PII.
2. `plan --proof PRIVATE_PROOF --tenant-id TENANT --out PRIVATE_PLAN`: SERIALIZABLE READ ONLY production transaction. Validates exact four-order set; tenant/customer/source/active identities; unique source target; legacy missing source ID; invoice/service continuity; zero unexpected dual RO/vehicle references; seven untouched neighbors and projections; active projection triggers. Records full before-state hashes and returns plan digest.
3. `rehearse --plan PRIVATE_PLAN --expected-sha256 DIGEST`: guarded apply and postcondition verification inside a transaction that always rolls back.
4. `apply --plan PRIVATE_PLAN --expected-sha256 DIGEST`: SERIALIZABLE transaction; lock four orders, both vehicles, neighboring orders, invoices and all direct invoice/RO dependent rows. Abort on any drift, including a legitimate source refresh between plan and apply. Update only owner vehicle_id and updated_at. Verify full financial/dependent/neighbor hashes, exact three sibling projections, and owner projection changes limited to vehicle_id/time. This pair has no fleet-board rows; require that invariant before and after normal triggers. Insert a durable repair_order_history_events audit with system attribution (`actor_user_id=null`, Owner-authorized ETS repair), source/plan digests and before/after fingerprints. No impersonated staff actor. Commit only after all checks.
5. `rollback --plan PRIVATE_PLAN --expected-sha256 DIGEST`: only restores the exact repaired owner link after matching original audit and exact expected repaired state. Protects the same financial/dependent invariants and appends a rollback audit. Refuse intervening drift; never force rollback.

Both apply and rollback are no-ops only at their exact audited target state. Unexplained target state is a failure. No automatic retries. Any exception rolls back. Private outputs are exclusive-create mode0600. Do not commit proof/plan files or database row data.

The plan fingerprints full invoices, payments, settlements, invoice payment ledger events, invoice read model, labor, historical mappings/evidence (if any), shop-history observation, both vehicles, customer, neighboring repair orders/projections and trigger definitions. Expected financial/source rows remain byte-equivalent within the transaction. Native payment/collection authority and shared-reader verification rules are untouched.

## Acceptance

Offline source hash/binding validation; dry-run produces no writes; plan/source/identity drift rejects; same-tenant unique target and exact group membership; no duplicate invoices or balances; bounded one-link update; audit/no-op/rollback; protected money/history/projections; exception rollback. Production acceptance reads all four billing contexts after apply and confirms the same invoice/status/remaining balance, with unchanged financial hashes and preserved other seven repair orders. A stale source observation remains unverified; this correction never invents payment state.
