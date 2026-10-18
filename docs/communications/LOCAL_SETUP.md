# Isolated shared inbox verification

DB-COMMS-002 uses a newly created synthetic PostgreSQL database, never a copy of
customer data. The user authorized isolated data and simulated SMS on 2026-10-16.
No provider/carrier delivery claim follows from this environment.

## Identity and launch

- Worktree: `/Users/sergio_m1_promax/.codex/worktrees/communications-foundation/truck-pit-stop`
- Branch: `codex/shared-inbox-backend`
- API: `http://127.0.0.1:8006`, production FastAPI router/auth via a local-only ASGI entry point.
- Browser prototype: `http://127.0.0.1:5186`; root owner connects its proxy to API8006.
- PostgreSQL16: `dieselbridge-comms-002-postgres`, loopback55460, database
  `communications_local`, user `comms_local`, dedicated volume
  `dieselbridge-comms-002-pgdata`.
- Redis7: `dieselbridge-comms-002-redis`, loopback6386, isolated from other tasks.
- Generated credentials: ignored `.env.communications.local`, mode0600. They are
  local sandbox credentials only. No existing `.env` is copied or inherited.
- Example interpreter used in this session: `/tmp/db128-backend-venv/bin/python`.
  A normal backend environment with `backend/requirements.txt` also works.

From the worktree, run the following with the backend Python interpreter:

```sh
python scripts/communications_local.py up
python scripts/communications_local.py migrate
python scripts/communications_local.py seed
python scripts/communications_local.py serve
```

`up` creates only named dedicated services. `migrate` explicitly upgrades the
isolated schema, while `seed` creates synthetic tenants, staff, contacts and SMS
history once. Subsequent seeds preserve all existing inbox state. There is no
reset, clone, delete-volume, or production command.

The usual runtime controller rejects this worktree's absent `backend/.env`.
This harness is the explicit task-specific configuration, not a reused default
runtime. Preserve all other development servers and volumes.

## Authentication and simulation

Sign in through the normal `/api/v1/auth/login` JSON endpoint. Seeded staff:
`alex@communications.example.com` (owner), `jordan@communications.example.com` (receptionist).
`foreign@communications.example.com` belongs to the second synthetic tenant;
`customer@communications.example.com` has a disallowed customer role. Each uses the
local `LOCAL_STAFF_PASSWORD` from the ignored file. No auth override is installed.
Do not print credentials in shared receipts.

`communications_local_app.py` overrides only the SMS provider dependency. It
requires the exact isolated DB identity and refuses a Twilio account SID. The
only Twilio auth token is a generated local webhook signing secret, validated
against the ignored configuration. A
second guard rejects all Twilio HTTP requests, including legacy sending paths.
The simulator returns queued acceptance; it never represents carrier delivery.
Provider invocations are durably counted in ignored
`.communications-provider.sqlite`, outside application transactions, so rollback
and restart cannot hide a duplicate invocation. Bodies and phone numbers are
not written to that ledger. There is no public simulation-control endpoint.

## Verification scope

A clean PostgreSQL migration from empty schema through176 succeeded before
application changes. The shared inbox migration, runtime readiness, authenticated
browser checks and concurrency tests are recorded separately by the implementing
owner and independent reviewer. HTTP readiness alone is not browser acceptance.
Real Twilio delivery, carrier callbacks and approved-number testing remain a
required pre-deployment gate.

## Signed webhook fixtures

The helper sends only to the fixed localhost API and uses the same Twilio
signature validator as production (no validation bypass):

```sh
python scripts/communications_local.py exec python ../scripts/communications_local_webhook.py inbound --body 'Synthetic reply'
python scripts/communications_local.py exec python ../scripts/communications_local_webhook.py status --sid SM_FROM_SEND_RESPONSE --status delivered
```

These are simulated signed provider events, not evidence of carrier delivery.
Use the same `--sid` to exercise inbound/callback replay.

## Runtime receipt — 2026-10-16 19:35 UTC

- API process77525 listens only on127.0.0.1:8006. Its command is
  `python -m uvicorn communications_local_app:app --host 127.0.0.1 --port 8006`
  and cwd is this worktree's `backend/`. It imports changed sources without
  auto-reload; restart this identified process after further backend edits.
- Branch `codex/shared-inbox-backend`, work in progress. Existing5173 and5186
  servers were preserved by this runtime task.
- `/health/ready`:200, PostgreSQL and Redis both OK.
- Explicit177 upgrade/downgrade-to176/upgrade succeeded. Existing synthetic
  counts remained2tenants,4users,6customers,6threads,6messages.
- Normal staff login200 using `alex@communications.example.com`; no auth bypass.
  Seed email TLD `.test` was rejected by the production email validator and was
  corrected to reserved example.com subdomain in seed and isolated rows.
- Signed synthetic inbound callback returned200, subsequently adding one local
  message. This proves normal signature processing, not carrier traffic.
- Three launcher/adapter safety tests pass; script compilation passes.
- API is aligned but browser-unverified at this receipt. Root owns frontend
  proxy verification and authenticated browser acceptance. This receipt expires
  on process/source/configuration changes.

Use `python scripts/communications_local.py simulate-next accepted|rejected|unknown`
to control exactly the next simulated provider call. The SQLite control row is
consumed transactionally. Unknown records an accepted SID then raises a timeout;
rejected raises a Twilio400/21211. Replays should not consume another control row
or increase the durable call count. This is CLI-only and absent production routes.

## Explicit bounded recovery

After an API restart, recover committed pending simulated sends with:

```sh
python scripts/communications_local.py exec python ../scripts/communications_local_recover.py
```

This imports the guarded local-only provider and dispatches at most50 pending
operations. It marks sufficiently stale dispatching operations unknown; it never
reclaims them for another provider attempt. Production scheduling is a rollout
gate, not enabled by this local script.
