# DB-048: inactive shop activation and new-invoice admission

Status: implementation contract; activation is **not authorized** by this item.
Owner: Backend & Integrations. Architecture owns this contract; Product & Delivery
owns the board and release. One backend owner implements production code and tests.

## Outcome and exclusions

Deploy disabled controls that can later admit only new Truck Pit Stop NC invoices
to its verified production QuickBooks company without switching the shared
worker's environment or replaying history. Existing historical-export holds,
including the 1,381 reviewed invoices, remain authoritative. Deploy schema and
helpers with zero activation rows by default. Do not create a management record,
assign a live cutoff, enroll invoices, enable processing, clear holds, record
payments, or change payment admission, flags, provider credentials, process
environments, fees, or account mappings during this deployment.

No payment-method, fee, cash-eligibility, UI, or cancelled-invoice lifecycle changes.
Other tenants retain their existing routes, environment selection, and worker
behavior; this feature cannot claim, refresh, or rewrite their work merely because
the NC pilot is configured.

## Persistent boundary

Implement a `QuickBooksShopActivation` record with these equivalent fields:

- UUID identity and exact tenant FK; one activation per tenant in this version.
- Exact realm ID, accounting environment (`sandbox` or `production`), and approved
  writer (`dieselbridge`); immutable after establishment.
- `enabled`, default false; `activated_at` UTC cutoff, nullable until the separately
  authorized first activation. Enabling requires a server-generated cutoff.
- Immutable version/identity and ordinary audit timestamps. Disabling/re-enabling
  cannot move the cutoff or change realm/environment. A later account migration
  needs a separate contract, not an update that reinterprets old operations.

Persist explicit invoice enrollment through a nullable activation FK or an
equivalent unique invoice-enrollment table. Enrollment binds tenant, invoice and
activation; it is not accepted from client input and cannot be reassigned.

Management and enablement are distinct after a management record exists. This
release seeds NO records: all currently unmanaged shops, including NC, preserve
their existing payment admission and flags. A missing row means unmanaged; do not
infer management from a mutable charge allowlist or silently fail existing new
payments because no activation has been established.

At a future separately authorized activation, verify exact NC tenant
`828acd84-38bf-4a66-8fa1-cdf076f4e241` and realm `9341456094535202`, then establish
the durable management row and immutable server cutoff atomically. Its existence
thereafter remains authoritative regardless of mutable flags. Disabling the
managed pilot sets enabled false while retaining the row, cutoff and enrollment;
deleting the row is not a supported disable/rollback operation. A disabled or
invalid existing row fails closed rather than falling back to legacy behavior.
No shop is claimed to be managed before that separately authorized transition.

Enrollment is permitted only during native invoice creation while the activation
is enabled, with `created_at > activated_at`, standard accounting policy, matching
tenant/realm and approved writer. Never enroll by payment date, worker encounter,
OAuth reconnect, or lazy backfill. Imported/source-tagged invoices are excluded.
Replacements (`supersedes_invoice_id`) require same-activation admitted ancestry;
held, pre-cutoff, foreign-tenant or unknown ancestry cannot become eligible merely
through a new creation timestamp. This version may conservatively reject all
replacement enrollment until ancestry is explicitly verified.

## Shared helper contract

Use `quickbooks_shop_activation.py` for the shared admission boundary. Equivalent
helper names may follow existing conventions; behavior is normative:

1. `load_shop_activation(db, tenant_id)` returns management status and activation;
   a disabled or invalid managed row is denied, not legacy.
2. `enroll_new_invoice(db, invoice, activation)` is creation-only, checks provenance
   and immutable snapshots, and never enrolls existing records opportunistically.
3. `require_shop_invoice_admission(db, invoice, operation, connection=None)` uses
   the existing settlement -> invoice serialization order and fresh policy reads.
   It returns legacy behavior for an unmanaged tenant, a validated immutable
   dispatch scope for an admitted managed invoice, or a structured denial.
4. A worker selection predicate excludes ineligible managed work before leasing;
   the admission helper rechecks immediately before provider IO. Neither step
   mutates excluded events' retries, timestamps, locks or statuses.
5. `accounting_dispatch_scope(admission, connection)` (or explicit immutable
   request arguments) selects the environment for that operation only. Validate
   tenant and realm again. Never change global settings, mutate a shared
   connection object with temporary environment attributes, or leave a context
   override behind on exception. Concurrent legacy and pilot calls must retain
   their independent base URLs and credentials.

Hold policy takes precedence over activation. Existing first-confirmed-noncash
receipt gating, gross composition, mapping validation and one-writer rules remain
in force. Activation is not evidence of a payment or bank settlement.

## Mandatory caller coverage

| Caller | Required behavior for managed shops |
|---|---|
| Staff, guest and portal payment creation | Require admitted invoice before provider capture or new manual reservation; use the same rule across routes. |
| Native invoice creation | Enroll only through the creation contract above. |
| Issuance enqueue, manual sync, issuance worker | Admission before enqueue/claim and fresh check before any customer/item/invoice write. |
| Canonical financial outbox | Admit source and every target invoice for payments, refunds, credits, reversals, disputes and adjustment journals. Do not rely solely on invoice-creation functions because some journals bypass them. |
| Maintenance | Select only admitted managed attempts for expiry/retrieval/cancellation. Historical reservations and excluded leases remain untouched. |
| Legacy payment/refund reconciliation | Exclude managed shops from legacy writers in this canonical-only pilot; unmanaged behavior remains unchanged. |
| CDC | Exact admitted company/environment, a pilot-specific cursor, and only admitted local lineage. Do not update historical invoice/payment sync timestamps or the legacy CDC cursor as a side effect. |
| Settlement/payout import | Import/post only provably admitted lineage; mixed historical or unmatched deposits require review rather than invented allocation or journals. |
| OAuth refresh | Refresh only the exact validated connection; no implicit historical enqueue or replay. |
| Provider outcomes/webhooks | Keep genuine verified provider facts. Export eligibility is separate from fact recording; a disabled pilot cannot erase or ignore a real accepted payment. Preserve existing cancelled-lifecycle behavior. |

If a provider payout/CDC path cannot safely partition admitted lineage in this
version, explicitly keep that managed-shop path disabled and report it as an
activation blocker. Do not silently use the global historical importer. The item
may deploy disabled controls but must not claim complete activation readiness
with a missing required path.

## Denials, concurrency and compatibility

Use stable domain denial codes distinguishing disabled/invalid existing activation,
unenrolled/pre-cutoff managed invoice, provenance/lineage mismatch and realm/environment
mismatch. Authenticated write routes return conflict/not-ready without provider
IO or financial mutation. Preserve existing tenant-safe not-found behavior before
revealing scope information. Readiness is advisory; dispatch repeats validation.

Retain existing outbox idempotency keys and fencing; never create a second writer
or resurrect suppressed/dead historical operations. Disable transitions must
serialize against dispatch admission so operations not yet accepted are stopped;
already accepted provider operations remain recorded for reconciliation. Late
verified outcomes may update their existing financial facts without enrolling or
exporting excluded invoices.

## Acceptance and independent gates

- Migration upgrades with zero activation rows and no invoice enrollment or
  financial backfill; existing new-charge admission and flags remain unchanged.
- Disabled or malformed existing managed activation, or missing enrollment for a
  managed invoice: zero new provider writes. Missing management row preserves
  legacy behavior and must not silently classify the tenant as managed.
- Explicit new native enrollment + confirmed noncash payment uses the exact
  production realm/environment; before confirmation first export still waits.
- Other tenant and concurrent unmanaged request retain their original environment
  and behavior; no cross-tenant token refresh or worker lease mutations.
- Old invoice with new payment, held invoice, import, held replacement ancestry,
  wrong realm/configuration, and mixed credit lineage cannot enter pilot export.
- Historical policy and financial fingerprints, including pending reservation,
  remain unchanged through migration, disabled deployment and worker cycles.
- Refund/journal/credit routes cannot bypass admission; payout mixes fail closed.
- Two workers preserve one-writer fencing and cannot expand scope on lease retry.
- Context/environment selection resets after success, exceptions and cancellation.
- Disabling prevents new dispatch but preserves genuine prior provider outcomes.

Independent QA and Security gate the exact implementation SHA. Release follows
migration -> guarded worker -> API, verifies source/configuration identity, and
performs read-only acceptance. No global environment flip. Final release evidence
must clearly distinguish **guards deployed disabled** from **shop activated**.

## Future activation and rollback

Separate authorization atomically creates the verified exact tenant/realm durable
management record, establishes its immutable server cutoff and enables it. Invoice enrollment begins
only afterward. Show expected candidate counts and held-history fingerprints
before enabling. Actual capture/refund testing requires separate financial-action
authorization. Rollback disables only pilot admission and retains guard-capable
code, immutable enrollment, all historical holds and financial facts.
