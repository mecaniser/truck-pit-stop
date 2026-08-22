# DB-037 Local Runtime Candidate Controller — MVP Contract v1

Status: Architecture GO for bounded implementation
Date: 2026-08-21
Accountable implementation owner: Release & Reliability
Contributing owner: Frontend & UX, limited to the development identity indicator
Base: `origin/main` at `4cbaec940c8ed6bb7b7bdf04950f5a5eb3d11c89`

## 1. Outcome and boundary

DB-037 provides one small controller for the single user-visible local
DieselBridge runtime. It prevents the frontend on port 5173 and backend on port
8000 from being served from different worktrees or candidates. A developer can
inspect, stop, or switch that runtime to an existing clean registered worktree,
and can immediately see `branch@shortSHA` in the development-only app shell.

MVP v1 is deliberately limited to macOS/zsh, the repository's current Vite and
Docker development setup, and the already configured local PostgreSQL and Redis
services. It does not create, clone, isolate, migrate, seed, or delete data.

This contract authorizes implementation and local automated tests only. It does
not authorize changing the currently running runtime during contract work,
pulling, pushing, opening a PR, merging, deploying, or mutating production.

## 2. Source-grounded constraints

- `frontend/vite.config.ts` binds Vite to `127.0.0.1:5173` and proxies API and
  WebSocket traffic to `127.0.0.1:8000`.
- `docker-compose.dev.yml` bind-mounts `./backend:/app` and publishes API port
  8000. The controller must always invoke it from the selected worktree and
  verify the resulting mount rather than trusting the terminal cwd.
- FastAPI exposes `/health/ready`, which checks PostgreSQL and Redis, in
  `backend/app/main.py`.
- The authenticated shell is
  `frontend/src/components/layout/DashboardLayout.tsx`.
- DB-035 PR #264 is included in the base SHA. DB-037 does not modify or recover
  the dirty DB-035 recovery worktree.

## 3. Command and file contract

The only command surface is:

```text
./bin/dieselbridge-local status [--json]
./bin/dieselbridge-local switch <worktree> [--dry-run]
./bin/dieselbridge-local switch-main [--dry-run]
./bin/dieselbridge-local stop
```

No `prepare`, dirty-worktree authorization, volume-management, install,
migration, or cleanup command exists in v1.

Release-owned implementation paths:

```text
bin/dieselbridge-local
scripts/local_runtime/controller.py
scripts/local_runtime/controller_test.py
```

Frontend-owned paths after Release freezes the environment fixture:

```text
frontend/src/components/dev/DevRuntimeIdentity.tsx
frontend/src/components/dev/__tests__/DevRuntimeIdentity.test.tsx
frontend/src/components/layout/DashboardLayout.tsx
```

The implementation adds no dependency. Python standard-library code and the
repository's existing Git, Docker, Compose, Node/npm, Vite, `curl`, and `lsof`
tools are sufficient.

## 4. Persistent local state

Controller configuration and state live outside every repository worktree:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/dieselbridge/local-runtime/v1/config.json
${XDG_STATE_HOME:-$HOME/.local/state}/dieselbridge/local-runtime/v1/state.json
${XDG_STATE_HOME:-$HOME/.local/state}/dieselbridge/local-runtime/v1/controller.lock
```

The files use absolute validated paths, atomic replace, mode 0600, and a parent
directory with mode 0700. State survives terminal restarts. The controller
refuses configuration or state paths that resolve inside a git worktree.

`config.json` contains only:

- schema version;
- canonical repository common-git-dir identity;
- absolute registered main worktree path;
- the existing local Compose project and API service identity; and
- the absolute existing local env-file path used by the development stack.

`state.json` contains only:

- schema version and controller state;
- active absolute worktree, named branch, full and short HEAD;
- clean/dirty result;
- Vite PID, process-group ID, start time, and URL;
- API container ID, Compose project/service, start time, and URL;
- repository Alembic head and current local database revision;
- last readiness result and check time; and
- the prior verified runtime snapshot needed for one rollback attempt.

Neither file may contain env values, database/Redis URLs, credentials, cookies,
tokens, request headers, or command output containing those values. The env-file
path may be stored; its contents may not be copied or printed.

## 5. Target validation

Before stopping anything, `switch` and `switch-main` require all of the
following:

1. `realpath(target)` is exactly a root listed by
   `git worktree list --porcelain` for the configured DieselBridge common git
   directory.
2. The target is not `/`, `$HOME`, a repository parent, a symlink escape, a
   bare repository, or a nested non-root directory.
3. The target has a named branch and readable full HEAD.
4. `git status --porcelain=v2` is empty. Every dirty target is refused in v1,
   regardless of who owns the changes.
5. The target contains the expected frontend, backend, lockfiles, Compose, and
   Alembic files.
6. The required installed runtimes and dependencies already exist. The
   controller never installs them.

`switch-main` resolves only the configured registered `main` worktree. It also
requires clean state and `HEAD == refs/remotes/origin/main` as known locally. It
never fetches, pulls, checks out, rebases, or resets main.

## 6. Existing database and migration policy

MVP v1 uses the one existing configured local PostgreSQL and Redis environment.
It does not introduce per-worktree projects, databases, Redis instances,
volumes, registrations, or lifecycle management.

Before a switch:

- the configured PostgreSQL and Redis services must already be reachable;
- `alembic heads` from the target must return exactly one repository head;
- the existing local database's `alembic_version` must contain exactly that
  revision; and
- `/health/ready` on the active API, when one is managed, must confirm the
  configured PostgreSQL and Redis are healthy.

A missing, multiple, ahead, behind, unknown, or unreadable revision is a hard
refusal before stopping the active runtime. The controller never runs Alembic,
seeds, copies, downgrades, creates, or deletes data. Status prints only the
repository head, current revision, and compatible/incompatible result; it never
prints the database host, user, password, URL, or env contents.

This shared local data policy is acceptable for v1 because only schema-compatible
clean worktrees may be selected and the controller performs no data mutation of
its own. Per-worktree data isolation is deferred hardening, not implicit scope.

## 7. Process ownership and mixed-source refusal

The controller may stop only a runtime recorded in `state.json` whose current
identity is independently reverified.

Vite ownership requires all of:

- recorded PID, process-group ID, and process start time;
- expected executable/command;
- cwd exactly `<active-worktree>/frontend`; and
- `lsof` confirmation that the same PID owns TCP 5173.

API ownership requires all of:

- recorded container ID, Compose project, and API service;
- Docker inspection showing the container owns host TCP 8000; and
- the backend bind-mount source resolving exactly to
  `<active-worktree>/backend`.

Before cutover, both listeners must be free or jointly resolve to the same
recorded active worktree and recorded HEAD. A free/occupied split, mismatched
Vite cwd, mismatched API bind mount, unexpected container, stale PID, unknown
listener, or frontend/backend worktree disagreement is refused unchanged.

`stop` sends `TERM` only to the reverified Vite process group and stops only the
reverified API container. It may use `KILL` after ten seconds only if Vite's
complete identity still matches. It never kills by port alone, uses `pkill`,
stops a broad Compose project, or stops PostgreSQL, Redis, workers, beat, or an
unrelated process/container.

## 8. Switch and rollback protocol

An exclusive local lock serializes `switch`, `switch-main`, and `stop`.

### Preflight

Before stopping anything, the controller:

1. validates the target worktree, branch, HEAD, and clean status;
2. verifies required existing dependencies without installing;
3. verifies the existing PostgreSQL/Redis and exact migration compatibility;
4. inspects ports 5173/8000 and verifies current ownership;
5. verifies that the currently recorded frontend and backend resolve to the
   same prior worktree; and
6. captures the exact prior verified runtime snapshot for rollback.

`--dry-run` performs this validation and prints a secret-redacted plan, then
exits without starting/stopping processes, writing controller state, changing
Git, or touching data.

### Cutover

For a real switch, the controller:

1. records `switching` plus the prior and target identities atomically;
2. stops only the verified prior Vite process group and API container;
3. starts the API from the target worktree using the existing local Compose
   configuration and env file;
4. inspects the new API container and requires its bind mount to resolve to
   `<target>/backend`;
5. starts Vite with cwd `<target>/frontend` and the frozen non-secret identity
   environment described below;
6. requires `/health/ready` to return HTTP 200 and frontend `/` to return HTTP
   200 without redirect; and
7. rechecks both listeners, target paths, branch, and SHA before recording
   `healthy` and the start time.

Readiness has a 90-second total deadline. Individual HTTP probes use a
two-second connection timeout and five-second total timeout.

### One-attempt rollback

If startup or readiness fails, the controller stops only the verified failed
target processes and makes one attempt to restart the exact prior runtime from
its recorded worktree, HEAD, commands, Compose identity, and shared configured
data services. The prior worktree must still be clean and match the snapshot.

If rollback passes the same health checks, state becomes `rolled_back` and the
switch exits non-zero. If it cannot be safely attempted or does not become
healthy within 90 seconds, the controller leaves ports 5173/8000 stopped,
records `rollback_failed`, and reports a redacted manual next action. It does
not retry in waves or choose another worktree automatically.

## 9. Status contract

`status` and `status --json` read persistent state and reverify live reality.
They report:

```text
controller_state
worktree
branch
sha_full / sha_short
dirty
frontend_url / frontend_pid / frontend_pgid / frontend_started_at
backend_url / backend_container_id / compose_project / backend_started_at
migration_head / migration_current / migration_compatible
health / last_checked_at
```

Status works from a new terminal and any cwd. It compares live Vite cwd, API
mount/container, port ownership, Git branch/HEAD/clean status, migration state,
and `/health/ready` with the persisted expectation. Missing/corrupt state or an
identity disagreement reports `unmanaged`, `mismatch`, or `unhealthy`; it never
adopts, kills, or repairs a listener.

All human, JSON, error, and captured diagnostic output redacts URL credentials,
query strings, and bearer/cookie/token/key/secret/password patterns. It never
prints `backend/.env`, database URLs, request headers, or credential values.

## 10. Development identity indicator

Release freezes two non-secret Vite development environment values when
starting the selected frontend:

```text
VITE_DIESELBRIDGE_RUNTIME_BRANCH=<validated named branch>
VITE_DIESELBRIDGE_RUNTIME_SHA=<validated short HEAD>
```

They come only from validated Git output. The browser supplies no path,
filename, command, query, or runtime-controller input. There is no supervisor,
filesystem endpoint, metadata API, signature, key, or browser command channel
in v1.

`DevRuntimeIdentity` displays `branch@shortSHA` beside the authenticated
product/shop identity. It uses text nodes, is keyboard/screen-reader legible,
does not cover navigation at compact sizes, and is guarded by
`import.meta.env.DEV`. It is not mounted in landing or customer portal surfaces.

Production tests must prove the indicator test ID, fixture branch/SHA, and
environment key strings are absent from the production DOM and generated
JavaScript. The indicator is startup identity, while live health and mismatch
remain authoritative in `./bin/dieselbridge-local status` for v1.

## 11. Lifecycle and explicit non-actions

- The selected candidate remains active until an explicit successful `switch`,
  `switch-main`, or `stop`.
- Main is the default only between reviews; no terminal startup or timer changes
  the selection.
- QA and agent runtimes use other ephemeral ports and never claim 5173/8000.
- The controller never automatically fetches, pulls, checks out, rebases,
  stashes, resets, cleans, installs, migrates, seeds, copies, or deletes.
- The controller never manages workers or beat.
- No runtime process or application state is changed by the contract commit.

## 12. Acceptance and negative matrix

| Case | Required result |
|---|---|
| Dry-run | Full redacted preflight; no process, state, Git, dependency, or data mutation |
| Same-worktree success | Vite cwd and API mount equal target; ports 5173/8000 healthy; branch/SHA exact |
| Mixed worktree | Refused before stop; existing listeners unchanged |
| Unknown port occupant | Refused; occupant remains alive and unchanged |
| Dirty target | Refused before stop; files and runtime unchanged |
| Migration mismatch or multiple heads | Refused before stop; no Alembic/data command run |
| Startup failure | One exact prior-runtime restart succeeds, or ports remain safely stopped with `rollback_failed` |
| Terminal restart | `status` reconstructs and revalidates the exact expected runtime from any cwd |
| `switch-main` | Only configured clean and locally current main accepted; no Git mutation |
| `stop` | Only reverified Vite/API stopped; PostgreSQL, Redis, workers, beat, and unrelated processes remain |
| Development indicator | Authenticated dev shell shows exact injected `branch@shortSHA`; no browser-controlled input |
| Production absence | Indicator and development identity strings are absent from production bundle and DOM |
| Secret canary | Env, DB URL, token, cookie, password, header, and query canaries absent from stdout/stderr/state/errors |

Tests use disposable worktrees and fake/disposable process/container identities.
Runtime tests must not stop the developer's actual listeners or connect to
production data.

## 13. Implementation handoff

### Release & Reliability

Deliver one focused tooling commit implementing the controller, persistent
state, exact ownership checks, shared-local-service migration gate, one-attempt
rollback, redaction, frozen Vite environment fixture, and focused tests. Return
with exact changed paths, test results, macOS runtime evidence using disposable
listeners, `git diff --check`, and proof no real runtime/database was touched.

### Frontend & UX

After Release freezes the two environment values, deliver one small commit for
the indicator, one authenticated-shell mount, responsive/accessibility styling,
focused tests, and production-bundle absence. Do not add controls, paths, logs,
health polling, filesystem access, or a browser-to-controller channel.

### Independent gates

- Security & Identity reviews path/process ownership, secret redaction,
  environment allowlisting, and production exclusion.
- QA independently executes the acceptance matrix, including actual mixed
  worktrees, unknown listeners, rollback, terminal restart, and production
  absence.
- Release may implement but may not self-approve QA. Product authorizes any
  eventual push, PR, or merge. DB-037 has no production deployment.

## 14. Deferred hardening

Not part of MVP v1:

- dirty-worktree authorization;
- per-worktree PostgreSQL/Redis isolation or volume lifecycle;
- database registration or cloning;
- supervisor/daemon and live source-change monitoring;
- signed metadata, browser metadata endpoints, or local key management;
- multi-attempt or multi-wave rollback;
- worker/beat control; and
- cross-platform or framework abstractions beyond the current macOS/zsh,
  Docker, and Vite environment.

Any implementation need for these items returns to Product and Architecture as
a separate follow-up rather than expanding DB-037.
