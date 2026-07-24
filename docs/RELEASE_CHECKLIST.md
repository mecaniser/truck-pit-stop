# Production Release Checklist

Use this for every `main` deployment until staging promotion is available.

## Before merge

- [ ] PR has one focused objective and no active overlap.
- [ ] `Migration graph`, `Backend tests`, and `Frontend checks` are green.
- [ ] Migration status is declared in the PR.
- [ ] Rollout signal and rollback trigger are recorded.
- [ ] Secrets, tokens, customer data, and production URLs are not in the diff.

## During deployment

- [ ] Railway build completes.
- [ ] Alembic upgrade and schema preflight complete successfully.
- [ ] API health check succeeds.
- [ ] No unexpected startup/restart loop appears in Railway logs.

## After deployment

- [ ] Exercise the changed staff/customer flow once.
- [ ] For performance-sensitive work, run the read-only production k6 canary.
- [ ] Watch Grafana/Platform Analytics for 10-15 minutes.
- [ ] Confirm API P95, database P95, Redis latency, errors, and alerts remain
      within their expected range.
- [ ] Add the deployment outcome and commit SHA to the PR.

## Rollback

- [ ] Stop related merges.
- [ ] Revert the responsible PR or disable its feature flag/configuration.
- [ ] Confirm the rollback deployment and retest the affected flow.
- [ ] Record the incident and the follow-up needed before retrying.
