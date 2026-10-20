# Frontend verification

For DieselBridge work, follow the repository's `AGENTS.md` and delivery lane in
`docs/DELIVERY_TEAM.md`. Run the local runtime alignment skill before implementation
or local browser QA; confirm the frontend and API serve the intended checkout.

For an existing-contract UI candidate, run focused Vitest tests for the affected
components, changed-source lint, the production build, and a signed-in desktop
and compact browser pass. The changed-lint command compares committed Git refs;
run it after committing the candidate:

```sh
cd frontend
# Install once for a new checkout or after package-lock.json changes.
npm ci
# Replace this example with the affected test files.
npm test -- --run src/features/garage/__tests__/revenueAverage.test.ts
BASE_SHA=origin/main HEAD_SHA=HEAD npm run lint:changed
npm run build
```

The build includes TypeScript checking. Protected PR CI is the integration gate;
do not repeat the full backend suite locally for a UI-only change without a
specific backend risk or failure. CI preserves the six required check names and
omits backend pytest for frontend plus optional documentation changes. Backend,
shared, CI, unknown-scope and main/manual runs retain the backend suites.

Batch related code and evidence before pushing. Once a PR is running CI, keep its
head stable unless a failure or required base integration needs a change. Land
PRs in order and integrate main into only the next PR being landed. A read-only
release receipt is available from the repository root:

```sh
python3 scripts/release_receipt.py <PR_NUMBER>
```

The receipt distinguishes check results, merge identity, Railway revision and
served build. Browser acceptance for the changed journey remains separate.

## Recover one failed check

Read the failed step and its log first. Completed-job logs can be read before
the whole workflow finishes:

```sh
gh run view <RUN_ID> --json jobs
gh api repos/mecaniser/truck-pit-stop/actions/jobs/<JOB_ID>/logs
```

Keep the PR head stable while its other jobs finish. For a diagnosed transient failure at the same source revision,
rerun only that job after the workflow completes:

```sh
gh run rerun <RUN_ID> --job <JOB_ID>
```

GitHub retains the other successful results. Check the rerun's actual test step,
including jobs named informational, before merging. If the failure repeats,
investigate and fix it; do not rely on repeated retries. A test waiting on a
loading screen is different evidence from a failed business assertion.

A merge creates a new SHA. Compare the tested and merged trees and observe the
production revision/readiness separately. Every main/manual workflow still runs
full suites by policy; a release operator must distinguish a duplicate
main run from missing PR checks before cancelling any work.
