# Dedicated Mac staging (DB-INFRA-001)

Release & Reliability owns this isolated environment. It does not replace or
connect to Railway production. The first stage runs the web/API, PostgreSQL 15,
and Redis 7 behind a fixed nginx ingress proxy. No collectors, Celery workers, beat, provider credentials, or
customer data belong here.

## Deployment boundary

- Dedicated ARM64 Mac, Docker Desktop Linux VM; staging Compose project name is
  `dieselbridge-staging`. Preserve unrelated containers and volumes.
- Archive only tracked `backend` and `frontend` files from a reviewed commit.
  Copy `build.dockerignore` into the archive root as `.dockerignore` before build.
  Never build from an operational checkout containing environment/session files.
- Copy this compose file to `source/deploy/mac-staging/compose.yaml`.
- Create `private/staging.env` outside `source`, directory mode 0700 and file
  mode 0600. Generate independent random `STAGING_DB_PASSWORD` and
  `STAGING_SECRET_KEY`; set `STAGING_SOURCE_SHA` to the archived source commit.
  Do not reuse credentials from another environment.
- Web, database and Redis use only an internal Docker network. Only nginx has
  a host port, bound to `127.0.0.1:18080`. Nginx bridges a normal ingress network
  to the internal network with a fixed web upstream. Gateway has outbound access;
  the application does not. Build-time network access downloads dependencies.
- Logs rotate at 3 x 10 MiB per service. PostgreSQL and Redis use dedicated
  named volumes. Never run `down --volumes` as routine maintenance.

From `source`, use this command prefix (never print the expanded environment):

```sh
docker compose --env-file ../private/staging.env -f deploy/mac-staging/compose.yaml
```

Build `web`, start `postgres redis`, then run `run --rm web alembic upgrade head`
before starting `gateway` (which starts web). Copy `nginx.conf` alongside Compose.
Inspect migration results before proceeding. Existing
staging data requires a backup before later migrations.

After replacing the web image, restart the gateway once web is healthy. Nginx
resolves its fixed upstream when it starts; a recreated web container can have
a different internal IP. Verify `/health/ready` through port 18080 afterward.

## Synthetic accounts

Run `seed.py` with `/app` on `PYTHONPATH` inside the isolated web container.
Supply JSON on stdin with `alpha` and `beta` independently generated passwords
of at least 24 characters. Store that JSON only in the private directory.
The seed refuses a non-staging environment, a different database identity, or
any database already containing tenants. It creates two verified garage owners
and one synthetic customer per tenant. Email addresses use `example.com`.
Provider egress remains blocked throughout authentication tests.

Access through an SSH tunnel to the Mac:

```sh
ssh -N -L 127.0.0.1:18080:127.0.0.1:18080 sergio@192.168.4.239
```

Open `http://localhost:18080`. This is private HTTP inside an SSH tunnel; do not
publish the port or use this configuration as an internet production server.

## Acceptance and recovery

Record image ID/source SHA and `/build-version`; require `/health/ready`,
Alembic head, both owner logins, cross-tenant customer denial, and an authenticated
browser pass. Inspect network attachments and test blocked outbound connections
from the application container. Check database and Redis persistence after a
scoped restart. Back up PostgreSQL with `pg_dump -Fc` into the private directory,
then verify restore into a separate disposable database without replacing staging.

Keep a timestamped record of checks and limitations. Desktop restart policies
do not prove unattended Mac recovery. Verify Docker startup after login, power
settings, and an approved reboot separately; FileVault must remain enabled.

Rollback: stop only the staging web service, preserve database volumes and backup,
and restore a previously validated application image if schema-compatible.
Do not downgrade a migrated database without a tested restore plan.
