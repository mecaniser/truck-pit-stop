# DB-157 independent QA

Accountable implementation owner: Backend & Integrations; root frontend, asset_contract backend. Independent reviewer: asset_qa. No product changes by reviewer. The return-context regression test was added during independent acceptance verification.

## Scope and evidence

User acceptance: trailers retain their own existing asset IDs and service history; board supports equipment filters; attachment links connect independent tractor/trailer pages; no missing engine-hours flag for trailers; real readings, including zero, stay visible.

- Independent final focused frontend run: 47/47 passing across FleetAssets (8), TruckDiagnostics, FleetBoard.pmSort, ClosedRepairOrders, TruckDetailHarden, and the additional FleetApp return-context regression.
- Independent additional FleetApp return-context regression: 1/1 passing; trailer filter survives asset detail -> board and full FleetApp remount. The initial probe exceeded the existing 5-second test deadline because broad role queries traverse the full CSS-heavy shell; specific text/ARIA queries made the same assertions pass in 1.74 seconds. No deadline increase or product workaround.
- Independent Playwright CLI inspection of the synthetic source harness at desktop 1280x900 and phone 375x812: trailer filter shows only 24/42, attachment picker offers only classified opposite assets, trailer health uses Not applicable for absent engine hours. Phone document width equals 375 pixels with no horizontal overflow, and all equipment-filter buttons measure 44 pixels tall. Screenshots retained locally under output/playwright/db157/qa-*.png; they contain synthetic fixtures only.
- Independent final targeted backend rerun2/2 passes for the corrected separate repair/maintenance/readings history assertion and active-attachment lifecycle guards.
- Separate service records: static inspection of history/repair endpoints and MaintenanceSection confirms original vehicle ID remains the query/mutation scope. Attachment mutation writes only the new dated pairing table. Backend synthetic tests exercise separate repair orders, maintenance programs, and readings before attach/swap/detach.

## Returned findings

- Equipment filter originally reset when opening an asset and returning. Root moved it into FleetApp persisted state; independent regression passes.
- Keyboard focus returns to the originating visible card; independent regression passes. When a counterpart link leads outside the active equipment filter, Back focuses the current queue heading. Final targeted regression run22/22 passes, including both card-focus and heading-fallback journeys; no frontend findings remain.
- First backend run: 10 passing, 1 failed because existing API lifetime_spend is a float while the test expected Decimal equality. Owner corrected the assertion to compare Decimal(str(value)); the corrected assertion preserves the existing API float contract. Independent final PostgreSQL run6/6 passes in24.25 seconds against fresh disposable local schemas, covering actual migration roundtrip, cross-tenant FK denial, competition for each asset role, and attachment versus remove/merge/classify serialization.

## Local runtime limits and source gate

Normal local full-stack runtime remains blocked/mismatched: 8000 is an unrelated privacy-safety Docker checkout, 5173 is absent, and intended checkout lacks approved backend configuration. Runtime preflight was run read-only; no existing service was replaced. Browser evidence is a synthetic component harness, not a signed-in end-to-end production acceptance claim.

Frozen backend attachment service SHA256 `008649b5ae17be93b014987b7b3b21e02d9af594350f9284b8426872e7ff6f21`.

Frontend and backend source QA GO after independent final PostgreSQL6/6 acceptance and the focused checks above. Independent Security reports44 focused backend tests passing after lifecycle and lock-order corrections. At source handoff, protected CI, migration/deployment identity and signed-in production acceptance remained required release gates. The production acceptance below supersedes that pending status without implying the blocked local full-stack runtime was aligned.


## Production runtime acceptance — QA GO

Independent reviewer inspected the retained production evidence, with no test
reruns or production writes during this release review:

- [PR788](https://github.com/mecaniser/truck-pit-stop/pull/788) merged as
  `29a47bf2bc2512fe1278dbb8fcf93d5c9892e179`. All seven checks in
  [CI41963626631](https://github.com/mecaniser/truck-pit-stop/actions/runs/41963626631)
  passed on checked head `5b60eda2149d3f9d5fac735c5e6c4ac5c8100b0d`.
  Independent Git comparison confirms checked and merged trees are identical.
- API deployment `40aeb0b3` succeeded. The retained deployment receipt and a fresh
  independent public build read identify the merged SHA; a fresh readiness read
  reports production ready with database and Redis checks OK. Build time is
  2026-11-05 03:57:16 UTC (Nov4 10:57 PM Eastern).
- Production readback confirms migration `202_fleet_asset_attachments`, all25
  fleet assets, and21 assets with both available Motive readings. Classification
  counts are2 tractors,2 trailers,21 unclassified and0 other. The deployed
  attachment service and migration hashes match the independently approved
  source; unclassified equipment was not guessed or bulk reclassified.
- After the user separately confirmed the current assignments, the root operator
  saved only609↔24 and603↔42 through the signed-in production UI. The subsequent
  read-only acceptance artifact verifies reciprocal board/detail DTOs for all
  four assets, exactly two dated pairing rows, and matching actor/asset tenant
  context. The pairing readback script uses a read-only transaction and checks
  counterpart IDs against the original four records, not unit labels alone.
- Reviewer directly inspected the retained production screenshots: Trailers
  filter shows24 and42 with their respective attached tractor numbers; both
  trailer health panels show Engine hours Not applicable; both tractor health
  panels show mileage and engine hours, with their correct trailer links. The
  phone capture at375px shows trailer24 health and Tractor609 attachment controls
  within the viewport. Root's measured phone document width is375px with no
  horizontal overflow. Screenshots remain private outside the repository.
- Six protected identity/membership/relationship fingerprint groups are byte
  identical before and after pairing. Six repair/inspection/incident/PM and
  maintenance-program/reading fingerprint groups are also byte identical.
  Reviewer recomputed both file comparisons: protected SHA256
  `3d12926b7e1eeb9862b217b47e7397f976e26e78b2894fb6264cace372021230`;
  service-history SHA256
  `72fbe4874228dc3ba7c36ad3d7861bc26e3cebfd666fff873fe197afc83716a0`.
  Only the two authorized attachment rows were added; no service history,
  ownership, canonical mileage or maintenance record was moved.

Production runtime QA GO for the DB-157 acceptance scope. No unresolved
functional acceptance finding remains. This approves the reviewed deployment
and current assignments; future attachment changes remain explicit operator
choices. The local synthetic harness is not substituted for production evidence,
and no future Motive reading availability is promised by this release.
