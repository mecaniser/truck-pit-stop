# DB-125: ETS provenance preservation

Owner: Backend & Integrations. Architecture direction: persistence only until payment date semantics and consumer contract are verified.

ETS embedded invoice data contains provider payment identifiers, QuickBooks references and datetime strings absent from the old rendered-text scrape. Dates alone do not prove settlement instants. Capture only allowlisted fields through `extractSourceEvidence`, then validate again using `scripts/easytruck_sync/source_evidence.py::normalize_source_evidence`.

Identity: actual navigated invoice route must match the requested service. Provider service ID/number must match that route; invoice service internal ID must equal service internal ID; provider invoice number must match the rendered invoice number. Provider invoice ID is distinct from its display number. Subsequent observations retain these identities or are held. Missing/mismatched embedded evidence fails the scrape entry and uses the existing nightly failure-rate guard.

Storage: nullable `Invoice.ets_source_evidence`, migration 171. Schema version 1, source `easy_truck_shop`, settlement semantics always `unverified`. IDs normalize to bounded strings; amounts preserve decimal textual value; datetime strings preserve source precision/offset and never gain a timezone. Payment datetime semantics always `source_datetime_unverified`. Each observation has at most 200 payment lines and 128 KiB; truncation is explicit. Notes, contacts, credentials and arbitrary payload fields are excluded.

Future normal importer runs append each distinct valid observation under an invoice row lock for the exact ETS invoice and service within the selected tenant and import source. Prior observations are immutable; unchanged replay is a no-op. The envelope is capped at 20 observations, with explicit warning and hold on saturation. Changed source facts can append; no prior observation is overwritten. No standalone backfill is run. Existing financial status, paid timestamps, payment rows and outbox remain unchanged by this capture. The existing import's other behavior is unchanged.

Audit read: query `Invoice.ets_source_evidence` with both `Invoice.tenant_id == tenant_id` and the exact invoice ID, plus source `easy_truck_shop_import`. This internal field is not exposed through existing invoice response models, signed history or Google delivery. No new public API and no producer wire change.

Rollback: roll back application code, retaining the nullable column/evidence. Downgrade drops provenance and should not be used during routine rollback. No automatic conversion eligibility promotion, source-history resend, payment correction or customer questions.

Local runtime: no servers listen on standard ports and this worktree has no approved local runtime configuration. Isolated backend and Node tests cover the change; no UI change and no claim of local browser acceptance. Focused tests cover source preservation, secret-field stripping, malformed/bounded data, actual SQLite tenant/source/service isolation, replay, and unchanged financial values. Protected CI and independent gates remain required.

Independent QA/security GO: 22 focused Python and 3 Node checks, additional identity-mismatch probes, single migration head and clean diff. Review did not edit implementation. Protected CI and deployed migration/runtime verification remain outstanding. This provenance policy is precautionary: it does not assert Google requires bank-settlement timestamps or that ETS facts cannot support a future completed-job contract. The current settlement contract is unchanged.
