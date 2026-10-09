# DB-036 driver worker database journal

Architecture/internal recovery contract, 2026-10-09. Backend & Integrations owns
implementation; independent QA/Security owns the gate. The user selected the
existing PostgreSQL database for recovery storage so the separate Railway worker
does not require a persistent volume.

## Scope and acceptance

Migration 164 follows 163 and adds a private worker journal, without public API
or frontend changes. Each run stores its exact source document and SHA-256,
immutable tenant/actor/fleet customer/provider company identity, explicit commit
intent, immutable eligible-request attempt and hash, and append-only phase
receipts. Source and attempt are durable before any import commit. Every receipt
phase is committed independently, including `commit_pending` before committing
the application transaction. The journal connection never retains application
actor/member row locks, avoiding a lock cycle with the import session.

`MOTIVE_DRIVER_JOURNAL=database` explicitly selects database mode. It requires the
existing PostgreSQL `DATABASE_URL`, tenant/actor/customer/company configuration,
and migration 164. `MOTIVE_DRIVER_JOURNAL_KEY` defaults to `motive-driver`; it is a
stable service identity, not a per-run identifier. Once a key has saved a run,
its tenant/actor/customer/company identity cannot silently change. A dedicated
session advisory lock keyed by this service identity serializes collection and
recovery across containers. The first operation checks current actor authority,
customer tenancy, journal schema and existing identity binding. A missing table,
lost connection, failed checkpoint, held lock or identity mismatch fails closed.

`MOTIVE_DRIVER_COMMIT=false` remains the default. File mode remains compatible
for explicitly managed persistent files and source-only diagnostics; it does not
claim survival after container replacement. Database mode uses private ephemeral
files only as collector working copies. PostgreSQL is the recovery source of
truth; no recovery depends on those files surviving. Raw source, credentials,
provider values and exception text are never printed to worker logs.

## Phases and recovery

1. Collector output is saved as `source_saved` with immutable mode/identity/hash.
2. Whole-source validation and rollback-only import determine eligible request
   IDs. The immutable attempt and `validated` receipt are saved atomically.
3. Application transaction applies records and verifies unchanged replay.
   `commit_pending` receipt is durably appended on the independent journal
   connection, then the application transaction commits.
4. `committed` receipt is appended. A new application session verifies capture
   IDs and current fleet projection, then appends `verified`.

Before collecting anything new, database mode loads all unfinished commit runs
for its stable key, verifies exact identity and hashes, and reconciles them from
their stored source. A `source_saved` run with no attempt may be validated again
because no import has begun. Later phases retain the exact eligible set and
request IDs. An uncertain application commit is safely replayed: existing IDs
must return unchanged, and a rolled-back transaction may create those same
requests. A verified run is terminal. Pending commits block new collection if
saving is disabled. A dry run is never promoted to commit by a later setting.

No receipt can delete/rewrite earlier phases, and source/identity/attempt cannot
be overwritten. Populated journal downgrade refuses to destroy recovery
evidence. Rollback stops the new schedule/saving and retains the table.

## Required checks

Exercise loss of local files, interruption before application commit, uncertain
commit before the committed receipt, journal checkpoint failure, old-source
recovery, exact replay IDs, mismatched tenant/actor/customer/company, concurrent
locks, append-only database constraints, migration upgrade/downgrade and no
provider data in failures. PostgreSQL tests use an isolated database; no runtime
services are started or stopped by this work. Independent QA, migration/release,
controlled import and scheduling remain root-owned release steps.

## Operation and implementation evidence

Production configuration selects `MOTIVE_DRIVER_JOURNAL=database` and the stable
service key `MOTIVE_DRIVER_JOURNAL_KEY=db036-motive-driver-safety`. Working files
default to `/tmp/motive-driver`; no volume or alternate database is needed. The
worker logs only completion stage, journal run ID and commit state. The direct
collector command remains usable for no-database source acceptance.

The runner CLI honors database mode too. New imports require `--input`; explicit
recovery uses `--recover --commit --journal-run-id <uuid>` and reads the durable
source without requiring an input file. `--receipt` is a private working-copy
destination. If an optional input is also provided on recovery, its hash must
match the durable source. New direct imports are blocked while pending commit
runs exist; the scheduled worker reconciles all pending runs automatically.

Owner verification: 84 focused driver schema/service/importer/worker/journal tests
pass, including 13 new journal tests. Scoped Ruff and the single-head migration
check pass. A fresh isolated PostgreSQL database completed the full migration
chain through 164. The PostgreSQL integration test proves session-lock exclusion,
independent durable `commit_pending` while application rows remain uncommitted,
replacement-process replay retaining exact saved IDs, append-only evidence,
identity mismatch/lost-lock rejection and downgrade behavior. No production data
or runtime services were changed. Independent QA/Security remains a separate gate.
