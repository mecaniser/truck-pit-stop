# CI and release receipt

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
