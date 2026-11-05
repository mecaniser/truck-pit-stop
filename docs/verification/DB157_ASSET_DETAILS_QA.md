# DB-157 follow-up independent QA

Reviewer: asset_qa. Implementers: root frontend and operational classification;
asset_contract backend. Reviewer has made no product changes or production
writes. Reviewer later owns the narrow fake-clock teardown correction described
below; that test-only correction needs a fresh independent review. This record covers the follow-up requiring equipment settings inside
Truck details and a tractor for every active fleet trailer. It supersedes only
the earlier optional-detach behavior, preserving the original asset identities
and independent service histories.

## Independent automated acceptance

- Frontend42/42 passing across FleetAssets, TruckDetailHarden,
  FleetApp.return-context, FleetAssets.return-context.qa, ClosedRepairOrders and
  TruckDiagnostics. Cases cover settings absent from the normal detail surface
  and contained in Truck details, no standalone Detach, required tractor when
  creating/classifying a trailer, combined four-field stale-state preconditions,
  conflict handling, actual zero readings, trailer engine-hours applicability,
  independent closed-history selection and filter/focus return behavior.
- Backend21/21 passing in48.80 seconds across test_fleet_asset_settings and
  test_fleet_assets_postgres. This includes11 settings/admission cases and ten
  actual PostgreSQL migration/concurrency cases in disposable schemas on the
  isolated db157_details database. Foreign/occupied targets do not change type;
  stale requests cannot reassign; legacy type editors cannot create an unpaired
  fleet trailer; off-fleet customer trailers remain registered; explicit create
  and admission require a tractor atomically; removal and future memberships
  preserve the invariant. Four parallel real-entrypoint tests verify tenant
  lock acquisition before FK-bearing flushes.
- Security independently reports33 settings/assets/PostgreSQL tests, four
  external real-entrypoint lock-order probes and one future-membership probe
  passing on frozen service2b861dc5; no unresolved security finding.

## Reviewed operational classification

Reviewer independently compared the retained frozen inventory, committed
receipt and fresh readback. Exactly20 authorized unknown assets became tractors;
533 and the other existing classified records were preserved. Final counts are
23 tractors,2 trailers and0 unclassified. All25 protected asset fingerprints and
eight service/history/membership/relationship fingerprint domains match before,
after and readback. Pairing-row fingerprint and both confirmed assignments
609↔24 and603↔42 match all three snapshots. No private asset IDs or screenshots
are copied into this record.

## Browser acceptance and closed focus finding

The source-based synthetic harness uses actual TruckDetail,
TruckDetailsModal and SidekickPanel with intercepted synthetic API data. The
initial harness did not compile Tailwind utilities when launched from the
repository root; the drawer appeared statically below the viewport. Root
corrected the harness working directory, without a product CSS workaround.
Reviewer rejected the first screenshot and verified the corrected drawer is
fixed at560px wide on1280px desktop and375px wide on375px phone.

Corrected browser checks pass: exactly one Equipment settings region inside
Truck details, no standalone Detach, required current tractor, free-tractor
picker, atomic synthetic reassignment609→T1 with Equipment saved confirmation
and updated counterpart link, focus held inside the open dialog, no phone
horizontal overflow, and44px phone equipment controls. Screenshots remain local
under output/playwright/db157b-qa-*.png and use synthetic records only.

Returned P2: following a counterpart link opened the correct independent asset
but focus fell to BODY. Owner fixed this with the actual details-trigger ref and
a pending target asset ID, restoring focus after the new asset data commits.
The new regression reuses TruckDetail exactly as production does. Reviewer
verified603→42 at desktop and42→603 at phone in the actual source harness: the
dialog closes and Open truck details on the newly selected asset has focus.
The P2 is closed.

## Runtime boundary

Mandatory local runtime dry-run repeated on branch codex/fleet-asset-details:
target dirty;5173 absent and8000 still belongs to the preserved privacy-safety
Docker checkout. Normal local full-stack runtime remains blocked/mismatched;
no configuration was copied or invented and no existing service was replaced.
Synthetic browser/DB acceptance is distinct from deployed signed-in behavior.

Backend and frontend source QA GO for the reviewed settings and compact
location/speed popover candidate. Protected CI and exact-source signed-in
production acceptance remain pending; the worker repair is a separate outcome.
This follow-up is not yet Done.


## Compact address and speed popover acceptance

New user steering requires one compact map-pin per unit, with address and speed
shown only after opening it. The source keeps each field's existing timestamp
and freshness rule. Independent checks cover the actual board integration and
header as well as the isolated component.

- Earlier independent combined run47/47 and Harden14/14 passed, but the later
  narrowed fake-clock configuration exposed deterministic cross-test RAF
  interference. Status-menu focus passed alone and failed when run after the
  speed-clock case. jsdom's Window implementation keeps its RAF callback queue
  behind an internal setInterval; restoring real timers immediately after an
  open popover unmounted stranded that queue, so later focus frames did not run.
  Reviewer corrected only the test teardown: unmount, advance the still-fake
  clock32ms inside act to drain the final frames, then restore real timers.
  The same two-case sequence now passes. Assertions, deadlines, product source
  and the independent stale-speed rule are unchanged. Root reviewed this narrow
  correction; fresh independent review is separately required because QA owns
  the test change.
- The corrected seven-suite run including TruckTelemetry passed57/57 in20.71
  seconds. The final exact59-case acceptance set replaces that unchanged9-case
  telemetry suite with the11-case TruckDiagnostics suite:59/59 passed in20.70
  seconds, all seven files passing. This final result supersedes the earlier
  source-candidate counts without erasing the test-harness failure history.
- At375px, board and header each show one44px marker with no inline address or
  speed. Popup width320px stays within the viewport, with the long synthetic
  address wrapping naturally. The measured phone document width stays375px.
  Desktop1280px compact header and popup were also inspected.
- Synthetic603's fresh zero is shown as0mph. Synthetic609's older zero is shown
  as Unavailable with Last observed time, independently of its newer address.
  Unknown readings do not become zero.
- Clicking the marker leaves the board card closed. Enter opens it from marker
  focus; Escape closes it and returns focus to the marker. A real mouse click on
  the transparent outside backdrop closes it, consumes that click, retains the
  board and returns marker focus. Header popup Escape behaves the same way.
- Local screenshots use only synthetic records. The first attempted609 phone
  click could not reach a card below the unscrollable outer harness viewport;
  reviewer used the actual board search to bring609 into view, then verified
  the interaction. This outer harness limitation is not a production scrolling
  claim and was not bypassed with a forced click.

No unresolved functional acceptance finding remains in this source scope.

Reviewed frontend/src/features/fleet/UnitLocationPopover.tsx SHA256 `30c08259ef15680d2c450fa177b6a80a164cd67e448fdcacf405234e356c78be`.

Reviewed frontend/src/features/fleet/TruckDetail.tsx SHA256 `b677407fcf9e64ee978420bc95d45229fbb43cfbbef5f32024bc90075c16d3a9`.

Reviewed frontend/src/features/fleet/AssetAttachment.tsx SHA256 `b84a5e8665b408350a3755a5fd9c6e80025113ba7b6f8172052cbd06fcea0be2`.

Final test-teardown candidate frontend/src/features/fleet/__tests__/TruckDetailHarden.test.tsx SHA256 `583c6fe6dbbb4308bfbaf80911077f8d3fdeb3c33b663970a796f925e9bd8601`.


## Subsequent CI return — trailer admission fixture optimization

Full frontend CI41973025675 passed2348/2349 cases and returned only the new
requires-tractor case for exceeding its unchanged5000ms deadline. QA owns the
narrow test-only correction in FleetApp.return-context: direct make/model fixture
change events instead of per-character typing, title/named-panel lookups, and
label-scoped button queries. Real dropdown selection, disabled/no-POST before a
tractor is chosen, and the original correct tractor/customer POST assertion are
preserved. The test still exercises the actual creation guard; it does not mock
away the invariant. Product source and API contracts are unchanged.

Focused admission case passes; the exact seven-suite59 cases pass in9.71 seconds
using two isolated workers, matching CI concurrency. Final test candidate SHA256
`46886f2d7b48d003659ee5210cfb46e496eb109ff16aa911ed00a429fb7d275a`.
Fresh independent review of this QA-owned test correction and protected CI are
pending; prior source/runtime outcomes remain separately recorded.
