# DB-139 remaining unavailable ETS link audit

Accountable: Backend & Integrations. User authorizes source-proven historical vehicle-link corrections only; financial evidence remains immutable. Full production census and finite manifest under independent Architecture/Security/QA review. No production mutations yet.

## Runtime preflight
2026-11-01: codex/ets-link-audit base29f0b21f. Dedicated frontend5202 PID98700 cwd this checkout/frontend, API18021 container bind this checkout/backend; approved root .env mechanism retained with isolated fictional postgres/truckpitstop_db139_shared, Redis11, no worker. Existing schema preserved. Proxy readiness200, actual signed-in browser confirms C3 Fictional Shop1 and branch29f0b21. Local aligned and browser-verified. No UI/API behavior change planned; operational script tests and production transaction rehearsal supply feature acceptance.

## Discovery and bounded scope

Production READ ONLY census:3739active ETS repair orders,1574null invoice totals. Reasons:460shared-job identity conflict,1076deleted-invoice evidence,10group-source conflict,16missing/ambiguous invoice,12invalid source identity. Payment status is distinct:1882paid,1825unverified,4partial,28unpaid.

Preserved vehicle-scoped source evidence independently supports243explicit vehicle FK corrections (238invoice-owning rows,5nonowner operation rows),243groups/698related orders,193connected components(max5groups).233groups account for429identity-held nulls;10more groups contain36nulls whose deleted-invoice hold remains after proper link correction.16structural groups excluded for unresolved customer/unit conflicts. Prior0662group excluded/protected. No alias overlap or dual order/vehicle reference found.

Candidate financial/reference footprint:269invoices(including26historical copies),312payments,243settlements,274ledger events,1146labor lines,634parts,269history observations. These existing records must remain unchanged; duplicates/deleted evidence are not cleaned or recreated. Exact private manifest binds each operation row, original/proven target, original source capture mapping, full group membership and expected current identities. Final independent implementation/rehearsal gate pending; no writes yet.
