# DB133 worker schema readiness handoff

Owner: Backend & Integrations. Independent QA/Security: separate gate required.
Implementation base: `e315ed166ddef71e977c27d31835dbdb3b6ee69d`.

The Celery worker now waits for the installed Alembic head and required physical schema before its Beat, Pool or Consumer bootsteps are built. This closes the Worker-before-Web migration race without giving Worker migration authority. The private manual migration experiment is abandoned and must not be executed; the normal Web startup remains the sole migration owner.

## Implementation boundary

- `backend/app/commands/worker_schema_readiness.py`: import-safe read-only gate, loaded Alembic heads, existing schema preflight plus explicit C1/contact columns.
- `backend/app/tasks/__init__.py`: lazy `worker_init` receiver for this app only. Terminal and unexpected failures raise `SystemExit(78)` because Celery signal dispatch catches ordinary exceptions.
- `backend/tests/test_worker_schema_readiness.py`: startup ordering, deadline, child cleanup, configuration and privacy tests.
- `backend/tests/test_worker_schema_readiness_postgres.py`: dedicated disposable PostgreSQL proof.

No task schedule, collector, provider, migration, infrastructure setting, preview database or production data changed. Importing `app.tasks` from Web does not run readiness or create a probe. The gate itself does not import application settings, tasks or providers.

The total wait is 120 seconds measured monotonically. Each probe uses the same interpreter and a fixed module invocation, with no shell. A supervised child is limited to the lesser of 10 seconds or the remaining deadline and is killed/reaped on timeout. Credentials travel over private stdin rather than process arguments or logs. The child has a 3-second connect timeout, 2-second PostgreSQL statement timeout, 1-second lock timeout, read-only transaction and non-pooled disposed connection. Retry sleeps are at most 2 seconds and bounded by the remaining deadline. Invalid configuration or malformed child status fails closed; logs contain fixed sanitized status only.

## Focused verification

Run from `backend/` with the repository test interpreter:

```text
python -m pytest tests/test_worker_schema_readiness.py tests/test_schema_preflight.py tests/test_conversion_worker_registration.py -q
```

Result: **28 passed**, 2.77 seconds. Evidence: `/tmp/db133-worker-gate-focused.log`.

This includes actual installed Celery **5.3.4** `WorkController` and signal dispatch. A blueprint spy prevents real Beat/Pool/Consumer startup during the test. Delayed success permits blueprint application once; deadline and unexpected failures exit 78 before blueprint application. A genuinely hung child is killed/reaped; an unreachable database probe is bounded and sanitized. Existing conversion worker registrations and schedules remain registered.

Real PostgreSQL command uses `WORKER_SCHEMA_POSTGRES_TEST_URL` privately, and the test fixture refuses any non-local database or name outside the dedicated `db133_test_merge_worker_gate_` prefix:

```text
python -m pytest tests/test_worker_schema_readiness_postgres.py -q
```

Result: **4 passed**, 5.25 seconds, on `db133_test_merge_worker_gate_7b63b002`. Evidence: `/tmp/db133-worker-gate-evidence/postgres-tests.log`.

- The actual probe transaction reports read-only with effective statement `2s` and lock `1s`; an attempted write fails with PostgreSQL `25006`.
- Correct Alembic head with a missing physical C1 column remains unavailable.
- An exclusive schema lock is bounded by the actual connection lock timeout, then readiness succeeds after lock release.
- A deliberately slow inspection is interrupted by the actual statement timeout.

The disposable end-to-end runner `/tmp/db133-worker-gate-pg-evidence.py` starts an actual Celery worker lifecycle while the database is at contact-only 175. It observes `schema_not_ready` with no bootsteps, performs a separate normal Web-style `alembic upgrade 176_merge_contact_pricing`, and observes `ready` followed by exactly one `bootsteps`. The gate performs no migration. Full normalized row hashes for all ten retained tables remain identical before/after upgrade and after the negative probes, including existing RO, labor, parts, inventory, invoices and counter-sale values. Receipt: `/tmp/db133-worker-gate-evidence/result.json`.

`compileall`, `git diff --check`, and the narrow undefined-global check pass. The latter is a global-name check, not a full linter.

## Frozen implementation identity and remaining release work

Four-file manifest: `/tmp/db133-worker-gate-evidence/source-manifest.json`.
Aggregate SHA256: `102174f86d7d052cecfce0d3ffcdf6a8786ed3b06239ca2b6007606a1a00783f`.

| File | SHA256 |
| --- | --- |
| gate module | `55b231ce9a6a8047437cd506ab5414fa5572c4ba5b221dab379752338fce85fd` |
| tasks registration | `914b365bc1ff23f9897e1d13f17c0efaca1b0474099ba23d42dc0369cde4ed38` |
| focused tests | `4b69612a8d29345d1c55c50468ef92fb02d3a8a2cc829a064fedaed4fb6c8438` |
| PostgreSQL tests | `2b616cb63a4db70494e3bd17b1e8c658ac176cebd33e10617daf9a2ada0c6dae` |

Independent approval, final exact-head protected CI, merge/deploy, read-only production schema/retention checks and desktop/mobile acceptance remain separate required gates. During deployment, require Web readiness at the checked schema and Worker readiness-pass/startup evidence. A worker timeout or exit is a failed startup, not permission to stamp or migrate from Worker. Investigate the Web migration/deployment result; preserve the read-only boundary.
