# DB-097 company equipment types

Owner: Backend & Integrations. Architecture reviewed; high-risk schema lane.

Keep vehicles, company relationships and all vehicle_id foreign keys. Existing repair orders identify the equipment; invoices follow the repair order. No new invoice target or bill-to authorization is introduced.

Add equipment_type: tractor | trailer | other | unknown. Database/application/legacy API default unknown; staff create UI explicitly defaults tractor. No historical classification from names, VIN decoding or unit numbers. Existing trailers remain unclassified until edited deliberately. Updates omit-to-preserve, explicit null/invalid return 422. Existing create/update auth, tenant and relationship predicates remain authoritative. No new tenant IDs accepted in bodies.

Expose on vehicle, nested customer and typeahead responses, staff company add/edit and asset list. Merge requires equal types; operators must explicitly reconcile classification first. All IDs/history remain stable.

DB094/v2 export shape is unchanged: the EDG consumer rejects additional fields. A coordinated version change is required to export equipment_type. Vehicle updated_at already participates in revisions; source VIN/vehicle corrections require fresh attribution review. Eligibility, money, bill-to and PDF authorization remain unchanged. This is not authorization to auto-import trailers: ELIS must consume the new type and reject mismatches before enabling trailer imports. Existing receiver contract is truck-only. Do not deploy the typed producer ahead of that coordination; silently filtering historical invoices would lose revision/removal reconciliation.

Migration157 adds the nonnull column/default/check only. No production migration executed. Rehearse PostgreSQL upgrade, populated legacy rows, constraints, downgrade (which discards classifications), and re-upgrade before release. Downgrade requires preserving classifications for later restoration.

Acceptance: typed CRUD, legacy/omitted/null/invalid cases, same-company tractors and trailers, distinct repair/invoice links, cross-tenant denial, cross-type merge rejection, unchanged export shape/revision parity; independent QA/Security, signed-in desktop/mobile runtime, protected PR CI and approved release required.
