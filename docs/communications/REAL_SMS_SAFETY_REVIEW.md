# DB-COMMS-004 independent real-SMS safety review

Reviewed 2026-10-16 by a fresh independent Security/QA reviewer, with no implementation participation. Scope: `scripts/communications_live_acceptance.py`, its guard tests, and referenced sending, isolation, and inbound/status projection code. Deployment remains on hold.

## Initial gate

**NO-GO pending correction:** initial `prepare` accepted any E.164 recipient, although user authorization covers only the number ending0486. Pin that authorization independently of the generated plan, enforce it before prepare/provider use, and validate the immutable ledger binding before status/reply polling as well as sending. Returned to implementation; reviewer does not edit implementation.

## Final pre-send gate

**GO for the single authorized test attempt; deployment remains HOLD.** Implementation corrected the finding with an independently pinned recipient hash checked before preparation, guard initialization, send/status entry, and provider-call claim. Ledger validation binds the entire plan before send or polling. Status also rejects a changed configured sender. The reviewer independently verified that the pinned hash matches the user-authorized number ending0486.

Independent focused rerun: `/tmp/db128-backend-venv/bin/python -m pytest backend/tests/test_live_sms_acceptance_guard.py -q --noconftest` — **7 passed**. Coverage includes other recipient/sender/body rejection, changed-plan rejection, concurrent/restarted permanent budget, a new plan failing to authorize another recipient, and polling-plan body immutability. The run bypassed application conftest intentionally; it used temporary SQLite only and made no provider or application database calls. The earlier eight-caller concurrency probe independently covered the underlying permanent slot before the authorization correction.

This GO permits only the existing acceptance command through the isolated launcher with its unchanged pinned recipient and one-call ledger. It does not authorize clearing/replacing the ledger for another attempt, running production recovery, changing routing, or deployment. A provider rejection/timeout does not reopen the spent call budget.

## Verified safeguards

- The dedicated launcher scrubs inherited provider configuration. The acceptance entry point requires the isolated development database identity and rejects live server account credentials or enabled recovery.
- Existing provider credentials are loaded in memory from their existing source; this script does not copy them into the worktree, start a worker, deploy, or change production routing.
- Outbound payload must exactly match the persisted recipient, sender, and body. SQLite consumes a single permanent call slot before provider I/O; concurrent callers, crashes, and uncertain outcomes cannot obtain a second slot.
- The Twilio client disables retries. Dispatch uses the actual durable automated operation; identical-event replay reuses its key and does not reset dispatch state.
- Configuration/ledger files are ignored by Git. The ledger and plan are restricted to mode0600. Exceptions are reported without raw messages or tracebacks that could expose credentials or phone values.
- Status fetch is limited to the operation SID and checks the returned sender, recipient, and body. Reply search is limited to the test pair/time window; only the exact nonce is imported into the isolated inbox.

Independent synthetic concurrency probe: eight parallel claims against a temporary ledger produced one winner and seven blocked attempts; mode0600 verified. No application database imports, credentials access, or provider/network calls were made by this reviewer.

## Evidence limits

Provider polling and direct application of the fetched receipt/reply verify provider state and isolated inbox projection. They do **not** prove that a public endpoint received and validated a signed Twilio callback. Existing production inbound routing remains unchanged; real replies may therefore also reach that existing route. No live delivery, reply, merge, or deployment is certified by this pre-send review.
