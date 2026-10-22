# Deploy only to the Mac test apps

The workstation commands deploy an explicit **local Git branch's committed HEAD**.
They do not push Git, merge branches, call Railway, change DNS or deploy workers.
Dirty files are excluded. Commit intended app changes before deploying.

```sh
~/.local/bin/deploy-dieselbridge codex/my-feature
~/.local/bin/deploy-tph codex/my-feature
~/.local/bin/mac-test status
~/.local/bin/mac-test rollback dieselbridge
~/.local/bin/mac-test rollback tph
```

Equivalent entry points live in this directory. The defaults read DieselBridge
from `~/GitHub/truck-pit-stop` and TPH from `~/GitHub/TPH`; use `--repo /path/to/repo`
for another checkout. Branches must exist locally; fetching a remote branch into
an explicit local branch is a separate Git operation. No automatic pulls occur.
`--build-only` builds an image without updating either app.

The public test URLs and access gate stay unchanged. Native app login remains
required. Sources are archived from Git objects using application-path allowlists;
archives reject environment/key files, symlinks, special files and traversal.
Neither local checkout hooks nor repository deployment workflows run on the host.
Trusted Docker recipes build ARM64 web images with exact source/adapter labels.
Package installation/build scripts run inside Docker without runtime secrets.
Builds can download dependencies; runtime app/database/worker networks stay internal.

## Deployment and rollback

The remote controller recognizes only the two existing fixed test stacks. It
locks the shared operator, verifies accepted configuration/container fingerprints,
updates only the selected web image/source and refreshes its gateway's DNS target.
It verifies readiness and served source, preserving the other twelve containers
and original staging baseline. Workers, schedules, database images, queues,
volumes, provider flags and credentials stay unchanged. Deploying web code does
not deploy worker code or enable live providers.

Each operation has a unique private journal. The previous accepted image and full
Compose configuration remain available for rollback; rollback switches web code
and configuration, not database contents. A failed health/source check attempts a
scoped restoration. An uncertain operation or protected-state drift refuses new
mutations until investigated. Failed builds/deployments retain their evidence.
No automatic migration, downgrade, reseed, provider action or job enqueue occurs.

## Schema compatibility

Ordinary DieselBridge deployments require the candidate's complete migration
graph to exactly match the accepted synthetic database. A schema mismatch fails
before replacing the app. Schema-changing branches need a separately reviewed
database release; the command never guesses that a downgrade is safe.

The initial older branch `codex/fix-part-catalog-activity` has a separately
accepted clone database and restricted role, plus Redis14. Existing workers retain
original synthetic PostgreSQL/Redis13. The clone retains the current schema with
no migration/downgrade. Candidate acceptance checks mapped columns/types, enum/null
data, unmapped mandatory inserts, native logins, tenant denial, and actual price/
supplier activity writes. This proves the tested older-branch journeys on synthetic
data, not complete compatibility with every later application feature.

For the already reviewed initial branch, the exact command is:

```sh
~/.local/bin/deploy-dieselbridge codex/fix-part-catalog-activity --database-release 334dcf6fba3e4eb8b40e36c2af818b95
```

The command refuses an already-current image without changing state.
A reviewed clone can be selected using `--database-release TOKEN`. This token is
an identifier, not a password; its private manifest binds exact image/source,
original backup hash, clone revision, independent approvals and runtime checks.
Subsequent schema changes require new review rather than reusing stale approval.
Clone preparation is an operator tool, not part of ordinary deployment. Backups,
clones and old images are retained; no automatic garbage collection is included.

## Machine and evidence

Remote: `sergio@192.168.4.239`, root `~/mac-hosting/test-deploy`, using the existing
restricted SSH identity. Private files/logs are mode0600 under mode0700 roots.
`remote.py init` is exclusive and records the current accepted legacy images;
never rerun initialization or overwrite state to bypass a failed operation.
The edge/SSL access service and the original24-hour sampler stay running.
Railway production remains a separate release decision.
