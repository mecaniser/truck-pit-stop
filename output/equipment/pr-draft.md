Title: Support company equipment types and separate trailer maintenance

Target repository: mecaniser/truck-pit-stop
Base: main
Head: codex/company-equipment-types
Status: LOCAL DRAFT ONLY — not pushed or published

Companies currently have unclassified vehicle records and truck-oriented controls, so operators cannot explicitly distinguish a trailer from a tractor when maintaining each asset. Add Tractor / Truck, Trailer, Other equipment and Unclassified to company equipment creation and editing, and show/search the type in company lists. Repairs and invoices retain their existing asset-specific vehicle_id links.

Existing rows and omitted legacy requests default to Unclassified. Omitted updates preserve the value; null/invalid types are rejected. Merges require matching classifications. Migration157 adds only the field, default and check; it performs no historical classification or financial reassignment. The mobile VIN row now fits the Decode control within the form.

The current EDG v2 financial manifest remains unchanged. Architecture confirmed EDG already handles truck/trailer VIN matching and reviewed equipment allocation; no receiver change is required here. Future exported fields need a versioned contract. Correcting a source vehicle/VIN requires fresh reviewed attribution; imported costs require explicit financial reclassification. The confirmed Aufine invoice000023 → T1003130 correction is separate from this feature.

Validation:
- 24 focused backend tests pass: equipment5, identity/merge11, invoice export8.
- 17 frontend tests pass: equipment modal2 and company workstation15.
- Production build, TypeScript and changed-source ESLint pass.
- PostgreSQL15 migration rehearsal passed defaults, typed writes, invalid/null constraints and downgrade/re-upgrade in a rolled-back isolated schema.
- Signed-in browser acceptance against this checkout and a disposable in-memory API passed at1440×1000 and390×844: create trailer/other equipment, edit trailer preserving type/unit, distinct trailer history, actual repair-workspace invoice display, four real repair/invoice API links, no horizontal overflow or page errors.
- Independent source and browser-evidence QA/security passed.

Evidence: docs/verification/DB097_COMPANY_EQUIPMENT_2026-10-31.md and output/equipment/browser-results.json.

Release: no production migration, data correction, deployment, branch push or PR publication performed. Publish only after explicit approval; protected CI, merge and release remain separate gates.
