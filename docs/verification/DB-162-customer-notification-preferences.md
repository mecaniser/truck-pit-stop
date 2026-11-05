# DB-162: Customer notification preferences

Accountable: Backend & Integrations. High-risk lane. Branch `codex/customer-notification-preferences`; base1365e583.

## Outcome and boundaries

Four saved shop/customer choices cover invoice email/text and repair email/text. The UI is server-backed, protects unsaved edits and reports uncertain saves without automatic retries. Delivery gates apply at synchronous send and durable queue dispatch. Essential, staff and manual notices retain existing paths; global STOP and consent stay authoritative. Maintenance reminders have no existing customer send path and remain unavailable. See the contract for explicit templates and rollout/rollback requirements.

## Isolated runtime receipt — 2026-11-05

Source `/private/tmp/customer-notification-preferences`, branch above, additive edits initially uncommitted at base1365e583. Frontend `http://127.0.0.1:5188`, PID14164, cwd that source's frontend, pinned dependency install. API `http://127.0.0.1:8126`, own container `customer-notification-api`, source bind mount that checkout's backend. Frontend proxy targets8126; both direct/proxied `/health/ready` report ready with database/Redis healthy. Own database `customer-notification-pg/customer_notification_preferences`, own Redis `customer-notification-redis`, migration `204_customer_notif_preferences(head)`. Provider keys disabled; no scheduler/delivery worker running. Other local sessions preserved. Synthetic fixture only; no production data copied or real messages sent.

Independent QA verified actual signed-in persistence after browser reload, dirty departure alertdialog with initial Keep editing focus/inert background/Escape preservation, and390px mobile layout with no horizontal overflow. Screenshot locally `output/playwright/notification-preferences-independent-mobile.png` (synthetic data).

## Automated verification and gates

- Focused backend preferences/provider-outbox/email suite:26 passed, including real-payer snapshot/fleet-contact queued coverage and explicit isolated PostgreSQL concurrent save (one success, one409), queued text suppression and STOP preservation.
- Frontend notification/navigation/profile behavior suite:27passed.
- Full TypeScript check, production build, shared-controls guard and new-source ESLint pass with freshly installed lockfile dependencies. Saved-card profile regression adds5passed; total focused frontend32passed.
- Independent Security/Architecture:GO after fixing the migration revision length and binding Notification tenant identity at queue load/success/failure. Negative test proves no cross-tenant provider call or audit mutation. Evidence local `/tmp/notif-security-regate.log` and `/tmp/notif-security-pg.log`.
- Broader isolated automated-SMS regression:77passed, one existing staff Zelle fixture failure. The fixture creates a mechanic but expects `pending_zelle_staff_submit_sms` to send; the unchanged base guard restricts that financial notice to owner/admin/receptionist. This does not involve customer preferences. No guard weakened to make it pass.

- Independent QA:GO after signed-in desktop/mobile save/reload, dirty-departure dialog, real409 conflict preserving the draft, explicit reload restoring server truth and trapped keyboard focus.

## Release state

Implementation and local gates are recorded here. PR/CI/merge/deploy evidence is added below as it becomes available. Not a production acceptance or provider-delivery receipt. No migration or customer-preference mutation has been run in production.

PR: https://github.com/mecaniser/truck-pit-stop/pull/809. Implementation5aa487cd. Changed-source lint confirms no new violations across5files; protected CI pending.

Final backend snapshot qualification: real payer address snapshots remain policy-bound; legacy internal-fleet external contacts remain separate. Four queued regression cases cover both enabled/disabled states.26 focused backend tests pass after the correction; independent Security/Architecture and QA re-gates both GO. Independent logs: `/tmp/notif-security-final-snapshot.log` and `/tmp/notif-independent-snapshot-regate.log`.

CI qualification on1133f43b: migration/contract, required backend/frontend, full frontend and browser smoke checks passed. Full backend had4504passed/470skipped and one pre-existing calendar-sensitive scheduling fixture failure: its `NOW +20days` future version became past on2026-11-05 at22:00UTC. The unchanged scheduling implementation correctly uses max(current time, previous version+1µs). Freeze the test clock to its existing NOW so the intended version/stale-retry checks remain deterministic; no scheduling production change. Full scheduling file62passed locally and62passed independently (`/tmp/notif-independent-schedule.log`); independent QA GO. Updated CI must pass before release.

Production rollout explicitly approved by the user. Notification item renumbered162 after merging portal-navigation DB161 from main9fc64b39. Prior candidate95fd9ba6 had all seven CI checks green (run42121397961); reconciled candidate must pass before deployment.

## Authorized production release — 2026-11-05

User explicitly approved deploying PR809, including new preference storage and email/text worker enforcement. Item renumbered toDB-162 because DB-161 belongs to portal navigation.

All seven checks passed on final linear candidate `a67111a3de95e6a2d18737b529c0e764b59a59d9`, run [42129674443](https://github.com/mecaniser/truck-pit-stop/actions/runs/42129674443). Normal protected rebase merged [PR809](https://github.com/mecaniser/truck-pit-stop/pull/809) as `56b5d7331003dd701ab3f89ef9264f86d4fe12d4` at2026-11-05T23:47:01Z. Complete checked/merged tree `2ea1889da387397842f06e8630725eee03cec52c` is identical. GitHub squash endpoints returned500; linearizing the same complete tree preserved the old branch history and allowed the repository's permitted rebase path. Required checks, linear-history protection and admin enforcement stayed enabled. No direct main push or override.

Migration204 was applied before worker/UI exposure. SSH port22 timed out, so independent Security reviewed a constrained fallback: authenticate with Railway's existing production database configuration, match the API's database identity to the PostgreSQL service, require TLS and verify `pg_stat_ssl`, lock the revision row in a transaction, require203 plus absent table, execute the exact Alembic-generated204 SQL, and read back204/table/columns separately. Already204 is a no-op. No customer/invoice record rewrite, preference save, consent/provider configuration change, replay or test message.

The frozen, fully checked worker94dde29d was staged first. Concurrent main releases required re-staging it; its runtime source matched the final candidate. Final automatic Git deployments both succeeded on the merge SHA:

- API: `0abd2fff-2cfc-4ee6-a282-87f377c36f74`.
- Celery worker/beat: `c33bd8f3-04b3-4765-856f-f0dc65027cab`.

Public `/build-version` reports the exact merge SHA. `/health/ready` reports production ready with database and Redis healthy, including a later check more than five minutes after startup. Celeryready was observed. Checked startup/canary windows showed no schema/import exceptions. A `process_quickbooks_invoice_sync`/`QuickBooksConfigurationError` also appeared in old worker logs repeatedly before release; this existing integration configuration issue is separate and was not changed. Do not interpret service health or these checks as a provider-delivery receipt.

### Remaining customer browser gate

The previously authenticated production tab showed the old Notifications placeholder. After refreshing onto the released build, it redirected to sign-in. A valid customer session was requested from the user; no credentials were retrieved or authentication bypassed. The final signed-in production desktop/mobile controls check is pending that session. Local authenticated persistence, conflict/reload/modal and mobile QA remain passed, but do not substitute them for the uncompleted production browser gate. Release is live; the item is not marked Done yet.

Rollback retains table204 and backend/worker suppression. Do not revert to pre-preferences senders after customers save choices; forward-fix or pause affected optional dispatch while preserving essential-notice handling. No replay/backfill.
