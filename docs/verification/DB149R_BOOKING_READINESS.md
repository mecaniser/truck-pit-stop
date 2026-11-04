# Booking readiness correction

Status: implementation frozen; independent verification in progress. Backend & Integrations owns DB149R; Release & Reliability owns rollout. This follows the authorized PR767 release and preserves its approved booking interface.

The correction excludes only proven same-tenant raw imported mirrors from the tenant-wide missing-settlement prerequisite. Direct mirror collection remains unavailable. Native invoice, source-handoff, payer, payment, Zelle, ancestry and tenant protections remain required. Both booking capability and new-charge binding evaluate current readiness for their exact immutable provider configuration; historical readiness snapshots are retained unchanged.

No migration, financial backfill, configuration-row rewrite, charge, refund, application or bookkeeping acknowledgment belongs to this change. The accountant owns manual bookkeeping. A normal same-company OAuth credential refresh restored connection health; protected financial and provider-configuration fingerprints were unchanged. Credentials and customer details are omitted here.

Owner checks: 71 focused, expanded 39-case matrix, 150 matching provider/readiness/collection tests and 7 actual PostgreSQL tests pass, including read-only fingerprints and cached authority. The owned sandbox API was restarted on frozen source; database and Redis health pass, frontend proxy reaches it, and all protected local table fingerprints are unchanged. Actual signed-in fictional-customer service discovery and the enabled reservation choice were verified in the aligned runtime without submission. Production acceptance remains separate. Release still requires independent Security/QA, exact-head protected CI, matching Web/Worker deployment and fresh provider readiness. Booking admission stays disabled until those conditions pass. Activation is restricted to the authorized shop. Live desktop/mobile verification stops before request submission, checkout-hold creation or payment.

Rollback: disable booking admission on Web and Worker, retain provider-fact recovery and immutable evidence, then use a schema-compatible corrective release. Never downgrade booking migrations or delete audit/financial records to roll back. Failed readiness, wrong tenant/provider binding, expiry-task failure or changed protected records blocks activation.

Final source, checks, deployment and live acceptance are recorded in the release receipt after verification. Production payment success is outside this no-payment verification.
