# DB119 independent security and privacy gate

Reviewer: Security & Identity, independent of DB119 implementation and contract
design. Date: 2026-10-14. Scope: private outside-shop vehicle service records,
their audit history, replay/version behavior, vehicle merge and client isolation.

## Decision

**GO for the reviewed DB119 security and privacy scope**, renewed after the
final `GET /vehicles/{id}` correction. The reviewed working tree on
`codex/external-service-history` has no unresolved security blocker. This is
not a workflow, release or production acceptance sign-off.

## Reviewed boundaries

- The dedicated routes use the existing active-user dependency. The service
  positively allows garage owner/admin/receptionist before any data query and
  requires an authenticated tenant. Customer, driver, mechanic, fleet manager
  and super-admin are denied. Vehicle and record queries require tenant and
  exact current vehicle identity; missing, foreign and archived targets have a
  common 404 message. Customer ownership does not grant private-record access.
- New storage is separate from repair orders, invoices, payments, vehicle
  telemetry and PM. Source search found no new record body in generic vehicle,
  customer/fleet/driver, invoice/PDF, authorization or repair-order history
  serializers. The only shared projection addition is an aggregate count in
  existing owner/admin-only vehicle merge endpoints. No new broadcast, receipt
  URL, file upload or outbound notification is present.
- Input schemas reject extra server-owned fields, invalid date/datetime input,
  blank/oversize text, fractional/bool odometer, nonfinite/negative/oversize or
  overprecision cost, and invalid optimistic versions. Dates are bounded by
  the shop's current date. Cost is a decimal string and remains distinct from
  an invoice amount; null and zero preserve their separate meanings.
- Writes lock the active vehicle first, then an existing record. They recheck
  ownership and use a tenant/request UUID plus canonical action, target and
  normalized payload hash. Replay requires the original actor and returns the
  current record; it does not overwrite later revisions. A savepoint makes the
  record and event atomic through a cross-vehicle request-ID collision. Stale
  versions and invalid void/restore states return 409 without a new event.
- The migration is additive, with composite tenant/vehicle and tenant/record
  restrictive foreign keys, numeric/version/action checks and request/revision
  uniqueness. No existing financial rows are backfilled. The supported rollback
  leaves tables and existing records intact; do not execute the destructive
  migration downgrade after user writes.
- Vehicle merge already locks both vehicles in stable ID order. The new move
  changes only current vehicle identity, retaining original vehicle ID, version,
  timestamps, attribution and historical event snapshots, including voided
  records. Old archived routes fail rather than silently redirecting a write.
- The external-service component is allowlisted before mounting/fetching. Its
  remount and query keys include tenant, actor, role, session epoch and vehicle;
  list pagination/filter and audit record/version are additionally scoped.
  Queries accept abort signals. Old-session callbacks close only their old
  component and invalidate the old scope. Text renders through React text
  nodes. Failed list/history reads suppress cached private content.
- Application-wide `CacheControlMiddleware` already sets API responses to
  `no-store, private`. The dedicated router now also applies an explicit
  `no-store` dependency; its final source and actual HTTP assertions were
  reviewed independently.
- The repair-order vehicle-history entry now resolves the exact vehicle through
  the existing authenticated vehicle endpoint instead of depending on a current
  customer-list entry. The new query requires matching response vehicle and
  tenant IDs, has a tenant/actor/role/session-epoch cache key and abort signal,
  and suppresses cached detail on failure. Its URL vehicle context clears on
  back/open-order/close-order actions. This does not widen the dedicated private
  history role allowlist or bypass its active-vehicle check.
- The final vehicle getter excludes soft-deleted vehicles before returning any
  response fields. Existing tenant and customer access checks remain in force.
  Current owner/operator names are enriched only for owner/admin/receptionist;
  relationship rows and related customers must both match the vehicle tenant
  and be undeleted, and relationships must be unended. Fallback owner lookup
  is also tenant scoped and undeleted. Foreign or inconsistent legacy links
  cannot supply names; customer/driver payload enrichment is not widened.

## Automated evidence

- Independently ran `test_external_service.py`: **39 passed in 7.15 seconds**,
  using the established Python environment and the implementation backend.
- Independently ran four supplemental backend cases covering actual HTTP
  authorization/cache/replay/stale responses, existing serializer exclusion,
  customer relink/merge retention and injected audit-write rollback. **All four
  passed.** The serializer case initially could not reach the fleet projection
  because its fixture lacked active fleet membership; that fixture was corrected
  without changing product code, then the case passed independently.
- Reviewed `/tmp/db119-backend-focused.log`: **55 passed in 12.12 seconds**
  across external-service and existing vehicle merge/identity regressions.
- After the getter correction, independently ran the seven new direct-vehicle
  cases in `test_vehicle_identity_relationships.py`: **7 passed in 6.71 seconds**.
  They cover the three enriched staff roles, current primary-owner selection,
  ended/deleted/foreign relationships and deleted customers, tenant/customer
  denial, archived-vehicle 404, unchanged customer fields and actual HTTP
  archived response. Reviewed final `/tmp/db119-vehicle-getter.log`: **62 passed
  in 17.58 seconds**, including all prior backend focused cases.
- Independently ran the final `ExternalServiceHistory.test.tsx`: **30 passed in
  3.15 seconds**. This includes denied roles, vehicle/tenant/actor/session draft
  reset, an old pending save completing after vehicle or same-account session
  epoch changes, failed-refresh cache suppression, malformed financial/date/
  mileage responses, literal source-text rendering, safe exact retry, access-loss
  dismissal, stale edit reconciliation and void/restore.
- Independently ran the final `RepairOrdersPage.customer.test.tsx`: **23 passed
  in 6.43 seconds**. Direct navigation covers a transferred/unlisted truck, reload
  and return context, loading/failure/retry, mismatched vehicle/tenant rejection
  and new actor/role/session cache isolation, enriched owner/operator display and
  archived-vehicle recovery with no live truck controls. Two assertions initially
  ran before the new async vehicle/history loads; the owner corrected the waits,
  and the complete file then passed independently without product workarounds.
- Reviewed `/tmp/db119-migration.log`: PostgreSQL upgrade from
  `168_operation_execution` to `169_external_service_history` completed.
- Reviewed `/tmp/db119-postgres-tests.log`: **9 passed**, covering same-request
  create contention, correction/correction and correction/void races,
  cross-vehicle collision without an orphan or aborted outer transaction,
  create/correction versus merge in both orders, and real migration FK/check/
  unique constraints including cross-tenant composite FK rejection.
- `git diff --check` passed at the final core-feature review. Existing
  SQLAlchemy/Pydantic, fixture cleanup and Browserslist-data warnings are not
  failed assertions.

## Resolved findings and remaining delivery gates

The reviewer reported an access-loss recovery issue: hiding an editor on 403/404
left its parent state armed with no dismissal. The owner added an outer named
Close service editor action while keeping private fields hidden; the final
regression passed independently. QA's stricter malformed-response date/cost/
mileage validation is also implemented and passing.

The two requested late-save regressions now pass and demonstrate that an old
request cannot clear the new draft or show a success message in a new vehicle or
new session context. Workflow QA subsequently identified that the existing
direct vehicle getter returned archived vehicles and omitted current company
context. Its correction, the seven new backend cases and complete 23-case
navigation file have been independently rechecked after the owner reported them
stable. No security follow-up remains for this reviewed scope.

Independent workflow QA, protected CI, exact deployment/migration and production
browser checks remain separate gates. This reviewer has written only this
document and has not changed application/test code, browser state, local runtime
configuration or production data.
