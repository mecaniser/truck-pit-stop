# C1 / DB133 readiness notes

Status: read-only preparation. P1 must finish production acceptance before C1 implementation begins. User selected C1 after P1; no C1 source, data or runtime changes have been made.

Architecture inspected the P1 candidate at 9441edf0:

- Reuse Customer → Business settings, extracting the disclosure from CustomerTaxExemptionControl without broadening tax permissions.
- Add a dedicated owner/admin pricing-policy endpoint. Generic customer PUT supports self-service and must not accept account pricing changes.
- Add optional labor-rate and parts-matrix defaults with CAS and audit. Pin policy snapshots on new external orders, including typed same-tenant matrix revision references and source-policy identity.
- Reuse parts_pricing.selected_policy and PricePolicy, extending planner selection while retaining P1 math and already saved lines.
- Route standard, quick and fleet creation, seven labor writers, recalculation, recommendation conversion, parts previews and counter drafts through the pinned-order policy.
- Preserve manual labor overrides during service reapply; the existing service reapply currently resets rate and auto_recalc.
- Preserve restricted fleet projection; provide manager configuration, safe shop terms and fleet total-only confirmation separately.
- Customer merge must not orphan invoice bill-to identity. Preserve a conservative conflict for a loser with financial references; full financial merge is outside C1.

Product decision approved by the user on 2026-10-16 UTC: NEW external fleet PM/staged orders use the customer agreed labor rate, otherwise the shop billing rate. Existing orders retain saved rates. This deliberately replaces the current internal-rate fallback for new external orders and must be explicit in the C1 contract and acceptance tests.

Key source locations in the implementation checkout: backend/app/db/models/customer.py; frontend/src/features/customers/CustomerTaxExemptionControl.tsx:87; backend/app/services/parts_pricing_planner.py:279; backend/app/services/price_build_service.py:308; backend/app/api/v1/endpoints/customers.py:698; backend/app/db/models/invoice.py:38; backend/app/api/v1/endpoints/fleet.py:3188.
