# Deploying the Celery worker + beat service on Railway

`railway.json` at the repo root only defines the web process (`uvicorn`).
Scheduled tasks — including the pre-existing weekly fleet-inspection
compliance check and the new weekly description-library refresh — are
registered in `app/tasks/__init__.py`'s `beat_schedule`, but nothing runs
`celery beat` in production today, so none of them actually fire.

This adds a second Railway service in the same project, built from the same
Dockerfile, running Celery instead of Uvicorn.

## Steps (Railway dashboard)

1. Open the TruckPitStop project in Railway.
2. **New Service → GitHub Repo** → select this same repo.
3. On the new service's **Settings** tab:
   - **Build**: Dockerfile, path `backend/Dockerfile` (same as the web service).
   - **Deploy → Start Command**, override to:
     ```
     celery -A app.tasks worker --beat --loglevel=info --concurrency=2
     ```
     (`--beat` runs the scheduler in the same process as the worker — fine at
     this scale. Split into two services later only if task volume grows
     enough that beat's timing gets affected by worker load.)
4. **Variables** tab — copy every env var the web service already has
   (`DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ANTHROPIC_API_KEY`, etc.) or
   use Railway's "Reference variables from another service" so they stay in
   sync automatically instead of drifting out of sync over time.
5. **Networking**: none needed — this service doesn't serve HTTP, no public
   domain required.
6. Deploy. Check the service logs for:
   ```
   celery@... ready.
   Scheduler: Sending due task process-description-library-refresh-weekly ...
   ```
   (the second line only appears once a week, at the scheduled time — to
   verify sooner, temporarily change the schedule to `crontab(minute="*/5")`,
   confirm it fires, then revert to the weekly cadence before merging.)

## Provider outbox rollout

The application now has a durable provider outbox for quote emails. It is
intentionally **off by default** so deploying the schema and code cannot strand
customer emails before a worker exists. Enable it only in this order:

1. Deploy the web service release that contains Alembic revision `082`; its
   pre-deploy check confirms the `provider_outbox` table and due-event index.
2. Create/deploy the worker service above, with the same `DATABASE_URL`,
   `REDIS_URL`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, and `SECRET_KEY` as the
   web service. It needs no public networking.
3. Confirm worker logs show `celery@... ready` and that the
   `process_provider_outbox` task is registered.
4. Set **only on the web service**:
   ```
   PROVIDER_OUTBOX_ENABLED=true
   ```
   Redeploy the web service (or restart it after Railway applies the variable).

Once enabled, sending a quote returns immediately after its database commit.
Celery beat picks up the email within about ten seconds; Resend calls run from
the worker with a 20-second timeout, bounded retries, and a dead-letter state.
If the worker is unavailable, leave the flag false: the existing synchronous
email behavior remains in place rather than silently queueing customer mail.

## What this unblocks

Once deployed, these `beat_schedule` entries in `app/tasks/__init__.py`
actually run on their configured cadence for the first time:

| Task | Schedule | What it does |
|---|---|---|
| `process-invoice-reminders-daily` | Daily 9 AM UTC | Sends overdue invoice reminder emails |
| `process-pending-zelle-reminders-hourly` | Hourly :15 | Zelle payment reminder follow-ups |
| `process-mechanic-timer-maintenance` | Every 5 min | Mechanic clock-in/out session housekeeping |
| `process-fleet-inspection-compliance-weekly` | Mondays 8 AM UTC | Records missed weekly fleet inspections, emails fleet managers |
| `process-description-library-refresh-weekly` | Mondays 6 AM UTC | Refreshes every tenant's AI-canonicalized RO/service/parts suggestion libraries |

**Before this deploy**, none of the above were actually running in
production — only the web/API process was deployed. Worth confirming with
whoever owns the Railway account whether that was known/intentional, since
it means invoice reminders and fleet compliance emails likely haven't been
sending either.

## Cost note

The weekly description-library refresh calls the Anthropic API up to 4 times
per tenant that has ever generated a library before (RO descriptions, service
names, part names, part categories) — tenants who've never clicked "refresh"
manually are skipped, so this doesn't create surprise cost for shops that
haven't opted in to the feature at all.
