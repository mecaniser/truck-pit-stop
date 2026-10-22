# TPH Mac backup rehearsal

This prepares and tests a synthetic backup/restore and switch in both directions. It does **not** make the Mac an approved live backup. Railway production, its database, domains, jobs, provider settings and credentials remain unchanged.

Both native application copies run on the Mac. The first is explicitly named `railway-simulation`; it is not the real Railway service. Their database is synthetic, restored using real MongoDB backup tools, and shared as one authority. No production records or credentials are copied. No native booking, message, payment, webhook or job mutation is admitted. Native PIN verification is the only admitted application mutation, to prove continuity across switches. A separate fake provider tests operation deduplication; native live providers do not yet consume this ledger.

## Operator commands

Run `deploy/tph-mac-backup/tph-backup status` from this checkout, or install that file as `~/.local/bin/tph-backup`.

```sh
tph-backup status
tph-backup switch mac
tph-backup switch railway
tph-backup tunnel
```

`mac` and `railway` select **rehearsal copies on the Mac**. They never change production. With the tunnel running, open <http://localhost:18310>. The page banner and `/__backup/status` identify the simulation and active owner. The private synthetic PIN is stored on the server in `~/mac-hosting/tph-backup-rehearsal-v3/private/credentials.json`; do not publish it.

`rehearse` is a one-shot acceptance run. It refuses a repeat rather than deleting failures, resetting state or replaying uncertain work. `activate-live` always refuses. Never edit the sealed manifest, remove an initialization marker or rebuild an accepted container to force a retry. Investigate retained evidence first.

The operator serializes changes, drains admissions, refuses any pending/unknown result, stops the exact old container, checks the exact ready target, and verifies current authority/watermark before promotion. A lost acknowledgment freezes the rehearsal until definitive fake-provider reconciliation. There is no automatic timeout takeover. Reversal preserves the same database and operation ledger. A native request with an uncertain outcome needs investigation; the synthetic cancellation command cannot cancel it.

## Zero-loss requirement for a future live backup

The user requires zero lost records. Stale, unavailable or unprovably current data must block activation. Periodic snapshots alone do not meet this requirement.

Live readiness requires a separate reviewed production release:

1. Establish a durable data authority that survives the intended Railway outage, with demonstrably current records and any required files. Include transactional write admission and recovery evidence.
2. Put both real hosts, workers and webhook consumers behind a shared fencing mechanism. Stop new primary work, settle admitted/inflight work, and prove the old owner cannot write or dispatch. An unreachable primary is not proof that it stopped.
3. Integrate stable business-operation identifiers, payload binding, durable outcomes and provider reconciliation into native payments, email, SMS and jobs. The fake ledger is not a replacement for this integration. Never retry an unknown payment or message blindly.
4. Prepare production credentials, host/domain/callback settings and a controlled public routing change. Do not expose this synthetic rehearsal or repoint the production domain to the test app.
5. Test failover and failback against that exact release and data model, including split-brain, stale data, provider uncertainty and recovery of writes made on the Mac. DNS reversal alone cannot reconcile records.

Until these prerequisites pass, keep Railway authoritative and live activation locked. This work deliberately cannot claim a tested switch of the actual live service while leaving its safeguards unchanged.

## Evidence and isolation

Private receipts live under the dedicated server root, mode 0700. No Docker socket is mounted. The four rehearsal containers use one internal-only network; the router has no working published port on Docker Desktop’s internal network. A reviewed host relay binds loopback18310 and uses fixed-container Docker exec transport. Existing fourteen application/staging container identities, configuration and accepted monitor baseline are checked before and after operator changes. Redacted verification belongs in `docs/verification/TPH_INFRA_005_MAC_BACKUP.md`.

The initial Mongo permission failure (v1), native invalid-index seed failure (v2), and Docker internal-network transport failure (v3 first harness) are retained in separate private receipts. The corrected `rehearse_v2.py` uses the same sealed v3 instances and a separately hashed transport extension. Backup index equality covers created fixture indexes before native application startup, not complete production schema/index compatibility. The unsupported native monthlySquareLocationId index is outside this change.
