# Private Mac application hosting

DB-INFRA-001; Release & Reliability owns this subsystem. It runs independently
of DieselBridge's monitored staging stack and Railway production.

## What this host supports

Deploy multiple **stateless Linux ARM64 HTTP apps** from locally built immutable
image IDs. Apps listen on an unprivileged port (8080 by default), run as UID65532,
have read-only root filesystems and writable `/tmp`, and expose a readiness path
returning HTTP200. Each app has its own internal Docker network and fixed nginx
ingress. Only nginx has outbound connectivity; app egress is blocked. Up to four
apps, each capped at256MiB/0.5CPU plus32MiB/0.25CPU ingress, with rotated logs.

All app ports bind to Mac loopback,18100–18199. Access uses SSH encryption and
SSH account authorization. This is usable private hosting; public domain/TLS
routing and stateful database applications require separate explicit contracts.
No production data, live provider keys, payments, outbound workers or arbitrary
Compose files belong in this subsystem.

## Operator commands

From this owned worktree:

```sh
./deploy/mac-hosting/mac-host status
./deploy/mac-hosting/mac-host deploy my-app \
  --image sha256:FULL_64_CHARACTER_APP_IMAGE_ID \
  --gateway-image sha256:FULL_64_CHARACTER_NGINX_IMAGE_ID \
  --revision REVIEWED_SOURCE_COMMIT --port 18101 --container-port 8080 --health /health
./deploy/mac-hosting/mac-host tunnel my-app
./deploy/mac-hosting/mac-host rollback my-app
./deploy/mac-hosting/mac-host backup
```

`tunnel` keeps running; open its printed localhost URL. Stop that tunnel with
Ctrl-C. The operator wrapper uses the dedicated staging SSH key and fixed Mac.
The controller pins Docker's `desktop-linux` context, uses no registry credentials,
and never calls Railway or changes Docker's global settings.

Build images on the ARM64 Mac from reviewed source. Start with a `git archive`
of an explicit commit and allowlisted app paths, transferred into a new directory
under `~/mac-hosting/builds/`. Never copy working directories, `.env` files,
browser sessions or provider credentials. A typical operator sequence is:

```sh
# On the Mac, in that reviewed build directory:
docker --context desktop-linux build -t my-app:REVIEWED_SOURCE_COMMIT .
docker --context desktop-linux image inspect my-app:REVIEWED_SOURCE_COMMIT --format '{{.Id}}'
docker --context desktop-linux image inspect nginx:stable-alpine --format '{{.Id}}'
```

The nginx image is currently pinned by controller policy to
`sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5`.
A gateway upgrade requires review of that policy.

Use the returned full image IDs with `deploy`; mutable tags are refused. A new
image must support the nonroot/read-only contract. Apps using privileged ports,
root-owned writable directories, database migrations or persistent app storage
need an adapted image or a separately reviewed hosting contract.

## Update, failure and rollback

A successful health gate records current/previous accepted releases. Updates have
a short app-specific interruption; nginx restarts to resolve the new internal IP.
A failed update automatically restores the previous image/configuration and checks
health again. Failure events stay in private `events.jsonl`. Explicit rollback
uses the same health gate. No database rollback or volume deletion is performed.

A first-release failure stops only that new project's containers. An interrupted
deployment or failed rollback leaves `pending.json` and refuses later deployments
until an operator inspects the exact app, state and events. Do not delete pending
markers or retry blindly. Containers with unexpected ownership are never adopted.
Logs may contain application data; inspect bounded own-app logs locally on the Mac
rather than pasting them into chat:

```sh
docker --context desktop-linux logs --tail 100 macapps-my-app-app-1
```

`backup` saves registry/configuration/release/event history in
`~/mac-hosting/backups/`, mode0600 under a mode0700 root. These are local
configuration backups, not off-device disaster recovery or application database
backups. The initial contract is stateless and has no app data volumes.

## Recovery and installation

Install `hostctl.py` as `~/mac-hosting/bin/hostctl.py`, run `init`, then install
`install-login-agent.py`. The independent `com.macapps.hosting.recover` user
LaunchAgent retries after login until accepted apps recover and pass health.
Existing Docker restart policies also restore running containers. This job does
not start/restart Docker, reboot macOS, change FileVault, or touch staging jobs.
Docker Desktop must already start after login. FileVault still requires local
unlock/login after reboot. Unattended power-loss recovery is not claimed.

Every operation uses a global lock; only generated `macapps-<slug>` projects are
managed. Root markers, symlink checks, ownership labels, port reservation, image
identity, free-space floor25GiB and a four-app ceiling fail closed. No host paths
are mounted into apps; only a generated nginx configuration is mounted read-only
into ingress. No socket mounts, privileged containers or global cleanup exist.

The existing four `dieselbridge-staging-*` containers, port18080, networks,
database volumes, worker results, baseline and monitor remain separate.

## Synthetic example

`example/serve.py` supplies a tiny HTTP app with `/health`, `/version` and a
landing page. Copy the three example files into a new reviewed build directory
and create `revision` containing `v1`. Build and deploy; change only that file to
`v2` for update/rollback acceptance. A revision of `unhealthy` makes `/health`
return503 to verify scoped automatic rollback. This image contains no accounts,
credentials, user data or writable application storage.
