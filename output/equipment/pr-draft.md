Title: Support company equipment types and separate trailer maintenance

Target repository: mecaniser/truck-pit-stop
Base: main
Head: codex/company-equipment-types
Status: Published with user approval as https://github.com/mecaniser/truck-pit-stop/pull/713; merge/deployment not authorized

Companies currently have unclassified vehicle records and truck-oriented controls, so operators cannot explicitly distinguish a trailer from a tractor when maintaining each asset. Add Tractor / Truck, Trailer, Other equipment and Unclassified to company equipment creation and editing, and show/search the type in company lists. Repairs and invoices retain their existing asset-specific vehicle_id links.

Existing rows and omitted legacy requests default to Unclassified. Omitted updates preserve the value; null/invalid types are rejected. Merges require matching classifications. Migration193 adds only the field, default and check; it performs no historical classification or financial reassignment. The mobile VIN row now fits the Decode control within the form.

The current EDG v2 financial manifest remains unchanged. Architecture confirmed EDG already handles truck/trailer VIN matching and reviewed equipment allocation; no receiver change is required here. Future exported fields need a versioned contract. Correcting a source vehicle/VIN requires fresh reviewed attribution; imported costs require explicit financial reclassification. The confirmed Aufine invoice000023 → T1003130 correction is separate from this feature.

Validation (refreshed onto main9dea1f1a):
- 31 focused backend equipment, vehicle identity/merge and invoice-export tests pass on current main.
- 30 frontend equipment-modal and company-workstation tests pass on current main.
- Production build, TypeScript and changed-source ESLint pass.
- PostgreSQL15 migration rehearsal passed defaults, typed writes, invalid/null constraints and downgrade/re-upgrade in a rolled-back isolated schema.
- Signed-in browser acceptance against this checkout and a disposable in-memory API passed at1440×1000 and390×844: create trailer/other equipment, edit trailer preserving type/unit, distinct trailer history, actual repair-workspace invoice display, four real repair/invoice API links, no horizontal overflow or page errors.
- Independent source and browser-evidence QA/security passed.

Evidence: docs/verification/DB148_COMPANY_EQUIPMENT_2026-10-31.md and output/equipment/browser-results.json.

Release: PR publication explicitly approved; merge/deployment and production data changes are not authorized. Protected CI remains the next gate. No production migration or data correction performed.
