# CI and release receipt

GitHub coordinates same-repository quality jobs on disposable local Linux
workers; fork PRs use hosted runners. Railway builds and deploys production
Web/Worker remotely.

For a pull request that changes only `frontend/**` and optional documentation,
the two backend pytest jobs report success without installing dependencies or
running pytest. Migration/config checks, frontend checks, and Playwright smoke
still run. The six existing protected check names remain stable. On a backend,
shared, CI, deployment, or ambiguous change, all backend tests run. Every push to
`main` and manual workflow dispatch runs the full suites. The scope check uses
the PR merge base, includes both sides of renames, and requires backend tests if
it cannot determine scope. The workflow loads the classifier from the protected
base commit. If that version does not exist, backend tests run; the PR that
introduces the classifier therefore receives the full suite.

Run a read-only release receipt from this repository:

```sh
python3 scripts/release_receipt.py 583
```

Replace `583` with the PR number. The command uses the existing `gh` and
`railway` CLI sign-ins. It reads the latest exact-head PR workflow run, the
exact-merge `main` run when merged, the production web deployment's source SHA,
and the production API's `/build-version` and `/health` responses. It marks a
missing or unavailable observation unknown; it does not merge, deploy, change
settings, or perform authenticated browser acceptance. Do that browser check
for the changed journey according to `docs/DELIVERY_TEAM.md`.

The receipt currently targets the Diesel Bridge Network production project,
environment, and `diesel-bridge-network` web service. Worker or performance
revisions still require their own evidence when the change affects them.


## Release evidence — 2026-10-19

PR #585 passed all six protected checks in run `39298040878` and independent
QA/Security, then merged as `9fe69414f388deca1d7aac0cb2930ba7bacae1c5`. Its checked
and merged trees match. Web deployment `849a8bee-ab08-4341-a59e-91501c527685` served
that exact SHA with database/Redis readiness and a signed-in analytics smoke
check. Worker application source was unchanged for this CI-only outcome.

PR #583 exercised the backend-required route; PR #575 also retained both
backend suites. In #575 one existing asynchronous customer-list test reached
its one-second wait deadline in the loading state. Independent review found
the test and list query unchanged from released main. The isolated case and
all 28 file tests passed with CI-equivalent provider configuration. After the
other jobs finished, only the failed frontend job was rerun at the unchanged
head: 191 files / 1,986 tests passed. The successful backend, migration, build
and Playwright results were retained. No test was disabled or assertion removed.

See [frontend verification](../frontend/README.md) for the shorter operator path.
This documentation-only follow-up also provides a real frontend-plus-docs
classification case; its final PR checks are the evidence for backend omission.
