# DB-157 independent QA

Accountable implementation owner: Backend & Integrations; root frontend, asset_contract backend. Independent reviewer: asset_qa. No product changes by reviewer. The return-context regression test was added during independent acceptance verification.

## Scope and evidence

User acceptance: trailers retain their own existing asset IDs and service history; board supports equipment filters; attachment links connect independent tractor/trailer pages; no missing engine-hours flag for trailers; real readings, including zero, stay visible.

- Independent final focused frontend run: 47/47 passing across FleetAssets (8), TruckDiagnostics, FleetBoard.pmSort, ClosedRepairOrders, TruckDetailHarden, and the additional FleetApp return-context regression.
- Independent additional FleetApp return-context regression: 1/1 passing; trailer filter survives asset detail -> board and full FleetApp remount. The initial probe exceeded the existing 5-second test deadline because broad role queries traverse the full CSS-heavy shell; specific text/ARIA queries made the same assertions pass in 1.74 seconds. No deadline increase or product workaround.
- Independent Playwright CLI inspection of the synthetic source harness at desktop 1280x900 and phone 375x812: trailer filter shows only 24/42, attachment picker offers only classified opposite assets, trailer health uses Not applicable for absent engine hours. Phone document width equals 375 pixels with no horizontal overflow, and all equipment-filter buttons measure 44 pixels tall. Screenshots retained locally under output/playwright/db157/qa-*.png; they contain synthetic fixtures only.
- Separate service records: static inspection of history/repair endpoints and MaintenanceSection confirms original vehicle ID remains the query/mutation scope. Attachment mutation writes only the new dated pairing table. Backend synthetic tests exercise separate repair orders, maintenance programs, and readings before attach/swap/detach.

## Returned findings

- Equipment filter originally reset when opening an asset and returning. Root moved it into FleetApp persisted state; independent regression passes.
- Keyboard focus returns to the originating visible card; independent regression passes. When a counterpart link leads outside the active equipment filter, Back focuses the current queue heading. Final targeted regression run22/22 passes, including both card-focus and heading-fallback journeys; no frontend findings remain.
- First backend run: 10 passing, 1 failed because existing API lifetime_spend is a float while the test expected Decimal equality. Owner corrected the assertion to compare Decimal(str(value)); backend final candidate and PostgreSQL tests pending.

## Limits and release gate

Normal local full-stack runtime remains blocked/mismatched: 8000 is an unrelated privacy-safety Docker checkout, 5173 is absent, and intended checkout lacks approved backend configuration. Runtime preflight was run read-only; no existing service was replaced. Browser evidence is a synthetic component harness, not a signed-in end-to-end production acceptance claim.

Frontend source QA GO. Final backend PostgreSQL checks and production acceptance pending. Do not mark Done from this interim receipt.
