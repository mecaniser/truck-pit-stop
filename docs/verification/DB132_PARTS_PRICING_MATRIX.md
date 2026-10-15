# DB132 / P1 parts pricing matrix

Accountable: Backend & Integrations. State: **In progress — accepted contract incorporation and runtime alignment**. Selected second in the [parity tracker](../ETS_PARITY_TRACKER.md), after R1 production closure.

## Scope and acceptance
[Architecture contract](../contracts/db132-parts-pricing-matrix.md) defines acceptance, writer coverage, privacy, tenant/concurrency boundaries and production verification limits. Reuse existing inventory settings and price controls; preserve compact desktop and complete mobile journeys. No existing prices, inventory valuation, financial records or shop defaults change merely from deployment.

## Source and preparation
Branch `codex/ets-parts-pricing-matrix` begins at R1 merge7b3dc4b3. Preparation reviewed21546789; full application tree is identical. Backend/frontend integration handoffs and later C1/M1/B1/A1 drafts are preserved in `/Users/sergio_m1_promax/Documents/Codex/ets-priority-preparation-20261015/`; those are preparation, not completion receipts. Canonical tracker retains all29 discoveries and selected order.

## Remaining gates
Runtime alignment before any application implementation or local QA; focused implementation and automated checks; independent Architecture/QA/Security as applicable; actual Light/Night desktop/mobile workflows; focused PR and protected CI; exact release; authorized production acceptance with no invented real-shop pricing activation. No P1 code, tests, PR, deployment or pricing-policy mutation claimed.

## DB137 prerequisite closure and implementation handoff — 2026-10-15
Compact controls DB137 are Done after PR539 exact deployment and Light/Night desktop/mobile production acceptance. P1 now continues on `codex/ets-parts-pricing-matrix-implementation` from `fc92c7b9944a0d07db80399b9f6e1eda13840b87`; the older preparation branch is preserved. Architecture owns canonical incorporation of four accepted wire/deletion clarifications before frontend/backend work begins. Backend owns all backend integration writers and migration together; Frontend owns the shared configuration and workflow UI. Independent gates remain separate.

Local runtime realigned after branch switch: frontend PID52183 serves this checkout/frontend on5174 with explicit API origin8001 and matching served branch/SHA stamps. Docker `dieselbridge_api_ets-workflow-parity`, image `bde2e27ba1f9353127cca22d4643b6fa0dd47336223c739c3bc5e83c9f480ea4`, binds the same checkout/backend on8001. Database identity remains `postgres/truckpitstop_ets_workflow_parity_20261012`, migration173. Direct and proxied readiness database/Redis healthy. Backend/config/flags/data untouched. Preview is aligned but currently browser-unverified for P1: session expired; user asked to restore sign-in. No new feature rendering or policy activation claimed.

Runtime sign-in restored by user; actual Performance Owner / Diesel Bridge Performance Lab dashboard renders `codex/ets-parts-pricing-matrix-implementation@fc92c7b`. Local5174 is aligned and browser-verified for the baseline; P1 feature acceptance awaits completed implementation/migration. Architecture accepted the canonical projection/deletion contract; backend and frontend began assigned implementation. Additional exact configuration/preview envelopes are being finalized before those adapter edits. No P1 completion or release claim.

## Acceptance ledger
All entries below are pending; update from actual evidence rather than inferring runtime success from component tests. Local mobile means responsive/touch browser emulation, not physical devices.

| Journey | Local Light/Night desktop,390,320,740 landscape | Automated boundary evidence | Production permitted acceptance |
| --- | --- | --- | --- |
| Settings entry, empty state, Back/cancel | Pending | Role/feature-gate independence pending | Read-only entry/empty/history |
| Matrix draft preview/save/reload | Pending | Bands/precision/bounds/idempotency pending | Draft preview only; no real policy save/default |
| Default, revision, clear, archive/restore | Pending | CAS/ABA/immutable history pending | Authorized reads; no guessed activation |
| Fixed price, pricing-cost floor, minimum sale price | Pending | Distinct precedence/null/invalid combo pending | Authorized policy read/draft preview |
| RO direct + bundle add; retained price after revision | Pending | All writer/stock/financial snapshot coverage pending | Historical value unchanged; cancel previews |
| Manual, List/Stock, discount rejection and409 review | Pending | Role/CAS/minimum/atomic rollback pending | Existing editor and cancel; no real price edits |
| Internal/external fleet and restricted roles | Pending | Projection/tenant/assignment negatives pending | Scope/read-only/cancel |
| Counter-sale retained draft and additions | Pending | Immutable IDs/snapshots/tax/return regression pending | Existing gate respected; no real sale |
| Legacy/locked history and account/tenant switch | Pending | Serializer/replay/cache boundaries pending | Read-only historical checks |

Local database checkpoint before any P1 schema changes: `Documents/Codex/ets-priority-preparation-20261015/db132-local-before-migration.dump`, custom pg_dump,3967918bytes, mode0600. Preserves existing populated local database; do not commit or upload database data. Disposable migration proof precedes a coordinated preview upgrade. No production database checkpoint or production financial mutation performed.

## Additive migration174 — local evidence
Backend tested full disposable upgrade,174→173→174 and a seeded173 legacy row: original cost12.34, sale24.68 and stock7 preserved; floorsNULL/fixedfalse/version0, no matrix/default seeded. Logs `/tmp/db132-backend-evidence/{upgrade,downgrade174-173,upgrade173-174,compat-down,compat-seed,compat-up,compat-check}.log`. Root reviewed migration then revalidated the preserved local DB identity and applied173→174 on the backed-up preview database. Alembic confirms174, readiness database/RedisOK. No matrices, default policies, events, configured inventory policies or nonNULL usage snapshots existed immediately after upgrade. ORM implementation now proceeds. This is local schema proof, not production or independent gate approval.
