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

## Explicit acceptance after a Docker Desktop restart

`status.identity_matches` compares exact accepted container membership and every
accepted identity field except health: IDs, images, Config hashes, start times,
network fingerprints, running state and OOM state. Configuration, original soak
baseline and live served source have separate status fields. A false identity
match is not permission to deploy. `uncertain_recovery` blocks normal deployment
and rollback, as does an uncertain deployment journal.

Recovery is an explicit **new acceptance boundary**. The original accepted state
contains only opaque network hashes, so this process does not establish that
historical normalized network topology matched current topology. It preserves
those old hashes and the complete old state in a private immutable archive. It
never resets either the original soak baseline or the new observation monitor.
It performs no container start/restart, network change, migration, queue claim,
provider call, seed or application-data write.

Run only the proposal command first, under the controller's existing shared
operator lock (the CLI acquires it):

```sh
python3 remote.py recovery-propose --observation 20261022T192823Z
```

The resulting private `recovery-proposals/<ID>.json` (0400) freezes the old state
hash; approved Compose/nginx and helper hashes; all fourteen exact container
identities; and six current networks with exact members, endpoint aliases and
cross-checked IP/MAC/endpoint mappings. Isolated networks must remain internal;
only each gateway may join ingress; published ports must remain the fixed
loopback bindings. The helper checks actual mounts, host namespaces, privilege,
capabilities, resource/security settings, provider/scheduler environment and
native database bindings against the unchanged service contracts. The original
staging gateway bind is fixed to
`~/dieselbridge-staging/source/deploy/mac-staging/nginx.conf`; test gateways
retain their exact `~/mac-hosting/test-stacks/<project>/nginx.conf` binds. Validated mounts are sorted by destination, type, and full canonical object;
all metadata is retained. Duplicate mount destinations are refused even across
different mount types. Named volume sources must retain their exact Docker
volume data paths. Mount-list order alone does not invalidate evidence. Full current
HostConfig hashes are bound for independent inspection, without exporting raw
container environments or credentials. Original staging's Config hash and
baseline remain unchanged. Read-only checks require ready matching app sources,
accepted database revision, empty named Redis13/14 and Mongo blog queues, and
local ARM64 current/previous images. These queue checks cover the fixed test
worker contracts, not every possible application queue.

Independent QA and Security must inspect the exact proposal, actual runtime
security configuration and topology against the frozen service contracts, and
read-only health/schema/queues/rollback-image evidence. They must also confirm
the new observation monitor and original baseline were left untouched. The
implementer cannot supply their approval. An authorized operator places their
reviewed artifact at `private/recovery-approvals/<ID>.json`, owned by the current
user, regular single-link file, mode 0400. Its exact schema is:

```json
{
  "version": 1,
  "decision": "approve_new_acceptance",
  "proposal_sha256": "<SHA256 of exact proposal file bytes>",
  "observation": "20261022T192823Z",
  "old_state_sha256": "<proposal.evidence.old_state_sha256>",
  "snapshot_sha256": "<proposal.snapshot_sha256>",
  "topology_sha256": "<proposal.topology_sha256>",
  "helpers_sha256": {"remote.py": "<sha>", "recovery.py": "<sha>", "stackctl.py": "<sha>"},
  "files_sha256": {"<each exact approved Compose/nginx relative path>": "<sha>"},
  "container_ids": {"<each of the exact fourteen container names>": "<full CID>"},
  "qa": {"reviewer": "<independent reviewer>", "reference": "<review evidence>", "decision": "GO"},
  "security": {"reviewer": "<different independent reviewer>", "reference": "<review evidence>", "decision": "GO"},
  "expires_at": "<timezone-aware timestamp within the next 24 hours>",
  "checks": {
    "current_topology_against_frozen_contract": true,
    "runtime_security_and_mounts": true,
    "providers_schedulers_and_database_bindings": true,
    "read_only_schema_queues_and_health": true,
    "rollback_images_available": true,
    "historical_topology_continuity_not_claimed": true,
    "new_observation_baseline_untouched": true
  }
}
```

There is deliberately no approval-generation command. Pass the independently
verified approval file's SHA256 explicitly:

```sh
python3 remote.py recovery-commit --proposal <ID> --approval-sha256 <SHA256>
```

Commit rechecks exact evidence under the same lock, creates a durable uncertainty
marker, archives original state/proposal/approval plus planned new state and
receipt, and rechecks immediately before the atomic state replacement. Only the
`snapshot` field changes. App release/rollback history, current/previous config,
source, image, database approvals and every other state field remain equal; a
canonical non-snapshot hash documents that equality. File formats and full old
bytes are retained in the archive. Immutable completed receipts close the
marker only after the state write and archive are durable. The proposal is
single-use. Any incomplete recovery refuses retry and normal deployment until
independent inspection; there is no automatic resume, rollback, reset or drift
waiver. Docker administrator actions do not share this lock, so reviewers must
also ensure no concurrent Docker/network administration during acceptance.

Local controller tests use transactional files and realistic synthetic Docker
metadata. They do not constitute approval of a remote proposal or recovery.
