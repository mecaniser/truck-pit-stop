# DB-COMMS-021 shared CallRail budget and MMS cache release

Backend & Integrations accountable; Release & Reliability verifies deployment.
Status: Done. Functional release verified 2026-10-24 at 03:42 UTC; final
operations checks completed at 03:44 UTC (October 23 in New York).

## Released source and gates

- DieselBridge [PR #648](https://github.com/mecaniser/truck-pit-stop/pull/648)
  merged as `0cec39f976b7d6e45a1d44326a857ec5ce353794`.
  [Protected CI 40056057764](https://github.com/mecaniser/truck-pit-stop/actions/runs/40056057764)
  passed all seven jobs.
- ELIS [PR #317](https://github.com/mecaniser/elis-agency-os/pull/317)
  merged as `80dd940`; deployed Web and Worker include that change at
  `fc9747f2ffd62b383fb5eff05b9c191bf369faec`.
  [Main CI 40057926747](https://github.com/mecaniser/elis-agency-os/actions/runs/40057926747)
  passed. ELIS broker synthetic runtime checks and loaded binding/security checks
  passed; DieselBridge acceptance is recorded separately below.
- Fresh independent Security and QA approved both source trees. Independent
  evidence covers signed reservations, replay and completion, mixed-app last-slot
  races, late permits, tenant isolation, encrypted cache reuse, concurrent
  revocation, and definite unsent budget rejection without automatic resend.
  Cross-app tests exercise the actual DieselBridge client against ELIS ASGI with
  SQLite and PostgreSQL. Synthetic transports made no provider requests.
- Owner evidence: 237 focused DieselBridge tests passed / 40 skipped; final
  budget/media follow-up 170 passed. Five real PostgreSQL cache/concurrency/access/
  send cases and migration upgrade → downgrade → upgrade passed. ELIS full suite
  passed 2,234 tests / 81 skipped. These checks are source evidence, not proof of
  production behavior.

## Behavior and economics

Both applications reserve against one ELIS account ledger before CallRail API
requests. Manual SMS, MMS discovery pages, authenticated media retrieval and
tracker diagnostics share the allowance. Errors and uncertain attempts stay
counted. Missing coordinator configuration, replayed grants and expired permits
block dispatch; there is no unguarded fallback.

The existing account-wide paid override is unchanged and expires
**2026-10-28 at 04:00 UTC**. The next invoice period uses the strict **1,350-request
shared cap**, leaving margin below the configured 1,500-request allowance.
Historical use and later provider reporting remain separate from newly metered
requests; the release does not retroactively assign unexplained usage.

Validated MMS manifests retain encrypted resource identities and slots, never
provider URLs. Sanitized PNGs are encrypted with tenant/message/slot binding and
checksum, type and size checks. Both have a fixed 30-day expiry and daily local
purge. Current access is rechecked before every hit and after retrieval. Database
locking prevents duplicate concurrent downloads. Cache hits spend no API unit;
corrupt data or unavailable encryption keys fail without a paid refetch.

## Runtime and provider evidence

DieselBridge Web `8ae65274-a48b-4ea3-8b90-ffdf29f8535d` and Worker
`914097b1-0bee-4868-929c-689570d656bb` are the sole active SUCCESS deployments at
`0cec39f976b7d6e45a1d44326a857ec5ce353794`; old replicas drained. The live build
identity matches, and readiness reports database and Redis OK.

Both loaded runtimes passed configuration and encryption-keyring fingerprint
checks. The approved scope contains 16 bindings for one shop/account, with zero
other-tenant bindings. The cache table and purge schedule are present. These
checks made zero outbound HTTP requests. Final Worker checks confirmed the sole
Alembic revision is `188_callrail_media_cache` and an actual Celery process is
running with `--beat`/`-B`; process matching excluded the verification script.

The deployed Web synthetic cache canary passed: eight concurrent image opens
produced one synthetic discovery and one synthetic image retrieval; reopening
added zero retrievals. Encrypted tenant/message scope, cached reuse at an
exhausted cap, and foreign/revoked access denial passed. The isolated schema was
removed, with zero active customer mutations and zero outbound HTTP requests.
Synthetic retrieval counts describe injected fixtures, not CallRail traffic.

The deployed ELIS synthetic broker canary passed a mixed-app last-slot race with
exactly one grant, replay/completion checks, and canonical-owner override expiry.
Its isolated schema was removed; outbound HTTP requests were zero.

One explicitly metered account-identity lookup established the shared provider
account binding. No SMS was sent and no customer media was fetched for this
release verification. No provider key, account identifier, customer content,
locator, or private acceptance artifact belongs in this receipt.

Local full-app/browser acceptance was unavailable: the isolated development
checkout lacked approved backend configuration and frontend Vite dependencies.
Existing services were preserved. Isolated local tests and PostgreSQL rehearsals
remained source evidence; the deployed-runtime synthetic checks above separately
establish functional release.

## Rollback and closure

Retain the ELIS broker, shared ledger and DieselBridge predispatch guard. If
configuration, source identity, migration or synthetic runtime acceptance fails,
pause provider dispatch; do not restore an unmetered application version or an
independent allowance. Preserve already counted/uncertain reservations, the
current override expiry and retained encryption key versions. Never retry an
uncertain SMS to test recovery.

Functional release acceptance and final operations verification are complete.
No remaining approval or production check is required for this item. The
[versioned contract](CALLRAIL_SHARED_BUDGET_CONTRACT.md) defines the signed
protocol, authorization, cache and operational boundaries.
