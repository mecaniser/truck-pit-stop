# DB-148 company equipment types

Owner: Backend & Integrations. Architecture reviewed; high-risk schema lane.

Keep vehicles, company relationships and all vehicle_id foreign keys. Existing repair orders identify the equipment; invoices follow the repair order. No new invoice target or bill-to authorization is introduced.

Add equipment_type: tractor | trailer | other | unknown. Database/application/legacy API default unknown; staff create UI explicitly defaults tractor. No historical classification from names, VIN decoding or unit numbers. Existing trailers remain unclassified until edited deliberately. Updates omit-to-preserve, explicit null/invalid return 422. Existing create/update auth, tenant and relationship predicates remain authoritative. No new tenant IDs accepted in bodies.

Expose on vehicle, nested customer and typeahead responses, staff company add/edit and asset list. Merge requires equal types; operators must explicitly reconcile classification first. All IDs/history remain stable.

`equipment_type` is a DBN asset-management field. This change does not alter `db094-repair-financial-v2`, its exact row keys, canonical revisions, snapshot hashes, authorization, settlement facts, or invoice financial state. EDG already supports truck and trailer VIN matching plus explicit reviewed equipment allocation. The earlier truck-only v1 recommendation does not describe the current v2 receiver. DBN company equipment types can ship independently with v2 unchanged. Any future exported type field requires a separately versioned manifest and coordinated source/consumer tests.

Architecture cross-checked EDG `dieselbridge_financial.validate_manifest` (exact SNAPSHOT_FIELDS/ROW_FIELDS/INVOICE_FIELDS) and `dieselbridge_equipment.resolve` (truck/trailer VIN matches and tenant-scoped reviewed allocations pinned to source vehicle ID and normalized VIN). No receiver change is necessary for this DBN feature.

Changing an RO's source vehicle ID or VIN invalidates prior reviewed attribution and requires fresh review against the authorized revision. Imported costs require explicit financial reclassification; no silent reassignment or reserve/accounting rewrite occurs. Repaired equipment identity remains separate from its towing tractor. The owner-confirmed Aufine invoice000023 → T1003130 correction is a separate audited source-data action, not part of this schema/UI change. This equipment fact establishes no price, payment, funding, date or billing-access claim. Mixed-equipment invoices require line-specific amounts/identities before splitting.


Migration193 adds the nonnull column/default/check only. No production migration executed. Rehearse PostgreSQL upgrade, populated legacy rows, constraints, downgrade (which discards classifications), and re-upgrade before release. Downgrade requires preserving classifications for later restoration.

Acceptance: typed CRUD, legacy/omitted/null/invalid cases, same-company tractors and trailers, distinct repair/invoice links, cross-tenant denial, cross-type merge rejection, unchanged export shape/revision parity; independent QA/Security, signed-in desktop/mobile runtime, protected PR CI and approved release required.
