# Isolated real-data reader for TPH

Current execution evidence is in `docs/verification/DB_INFRA_006_REAL_DATA_COPY.md`.
The original preparation contract below is retained as history. Its former
Auth0 prerequisite has since been explicitly approved and configured through a
separate Mac-only SPA; the reviewed Phase 2 local reader/web/gateway is running.
Full archive comparison passed (78 collections, 136,410 documents, 556 indexes).
The corrected public HTTPS route is active and the user completed native admin
PIN plus Auth0 password sign-in. Exact receipts, the preserved failed first UI
cutover and rollback, and accepted protected backend read journeys are in the
verification document. The V2 `maintenance/` profile has separate source, exact-plan, runtime and
authenticated read acceptance. Its key-only host agent refreshes public keys every
900 seconds; a failed refresh preserves expiry and eventually fails closed.
Never replay preparation, restore, inventory, Phase2 or old cutover commands to
update an existing copy. Original deployment commands target the synthetic stack,
not this separate real-data reader.

The original preparation command creates files for a separate Mongo/web/gateway
project; it performs no Docker or source-export action. Separate reviewed one-shot
runners carry out their exact approved local actions and preserve their journals.
Production remains untouched. Current acceptance covers native admin sign-in and
the named read views; client/manager journeys are not yet proven. This is a
point-in-time copy for data inspection, not live failover or RPO0.

## v3 preservation and network capacity

Preserve the failed v2 root `~/mac-hosting/tph-real-data-v2`, project, volumes,
networks and restore logs unchanged. The parent observed136410 restored records
versus136376 remaining records before app/role start, and confirmed MongoDB TTL
`deletedDocuments=34`, exactly the deficit. This loss is not accepted or
normalized away. v3 starts Mongo with `--setParameter ttlMonitorEnabled=false`
before restoring into a fresh project and volumes. Verify that actual parameter
false before/after restore. No TTL index is deleted or modified; raw-document
comparison must still match every exported record. Never reimport/drop/repair
v2 as part of this plan.

The original prepared `~/mac-hosting/tph-real-data` plan (SHA prefix `a580`)
remains untouched and superseded; it never started a service. Docker's default
address pool was exhausted, so v3 prepares only a fresh
`~/mac-hosting/tph-real-data-v3` root. Its new isolated network explicitly uses
`10.240.64.0/24`; its new ingress network uses `10.240.65.0/24`. Both are new
project-owned networks; no existing network is reused, removed or changed.
Before Phase1 approval, the parent must inspect every current Docker subnet and
all host/LAN/VPN routes and confirm neither proposed subnet overlaps an existing
network or routed destination. The plan records that verification as REQUIRED;
source tests prove only the fixed network contract and mutual non-overlap, not
live routing availability. A conflict requires another independently reviewed
new plan, never automatic subnet selection or cleanup.

## Fixed input and identity

Parent-owned read-only export evidence:

- Archive: `/Users/sergio/mac-hosting/real-data/private/captures/20261022T214813Z/ParkRightDB.archive.gz`
- Bytes: `17398592`
- SHA256: `caf0a0fcdcbf70d9bcf7b237610327938687a0f8081907290f4eb025c5267fba`
- Source database `ParkRightDB`; target database `tph_local_test` on **new Mongo only**.
- Preserve every native document and index. No `--drop`, reseed, migration,
  native auto-index/auto-create, or restore into an existing database.

The accepted web image is the existing reviewed immutable TPH image with native
source `b369e9f5e28584ba99f1cbe35d8f65080a51aeda`. The input manifest must contain
exactly `images` (`web`, `mongo`, `gateway`, each full `sha256:` image ID), `source`
and a fresh random 32-hex `token`. Independently verify that the manifest web ID
is that accepted image, and inspect all three images as local Linux ARM64 before
approving any runtime operation. No mutable tags or production URI are inputs.

Install tools separately from the as-yet-absent runtime directory; prepare with:

```sh
python3 /path/to/reviewed/prepare.py < /private/reviewed-image-manifest.json
```

This creates only a **new** `~/mac-hosting/tph-real-data-v3` directory (0700), exact
Compose/adapter/gateway files, five fresh local secrets in `private/clone.env`
(0600), and a hash-bound `plan.json`. Existing directories are refused. The
adapter alone is 0644 for the container's unprivileged `node` user; it contains no
secret. Every artifact and the Compose plan must pass independent QA/Security
review before any Docker command. Preparing is not activation approval.

## Two independent runtime approval phases

Phase1 covers preparation, the **new Mongo only**, full restore and private
inventory. It does not approve creating an app role, starting web/gateway, exposing
data, or public cutover. Phase2 requires reviewed actual collection/credential
inventory, the narrow app role, source/plan hashes, native auth/data acceptance and
its own approval before web/gateway can start. The full raw archive stays complete
in both phases. No app is connected during restore/inventory.

## Exact staged runtime plan (parent executes after approval)

Use the fixed new project's `--env-file .../private/clone.env`, exact generated
`-f .../compose.json` and `-p <plan.project>` on every Compose call. Confirm no
container, network or volume with that project exists, port18221 is free, all
fourteen accepted original container identities match, and both original/new
monitor baselines and observations are unchanged. Snapshot identities before
and after each stage; do not redefine an acceptance snapshot to hide drift.

1. Start **mongo only** in the new project. Its fresh volume bootstraps its own
   local restore administrator; no application startup script is mounted in
   `/docker-entrypoint-initdb.d`. Capture the new container ID and volume IDs.
2. Recheck archive size/hash and target identity. Refuse any existing target
   application collection. Run `mongorestore` inside this exact new Mongo,
   through authenticated local access, with the fixed options below. The source
   archive is read from its existing private file; no production URI or provider
   credential is transferred. Never put passwords into command text or logs.

   ```text
   --archive --gzip --stopOnError
   --nsInclude=ParkRightDB.*
   --nsFrom=ParkRightDB.* --nsTo=tph_local_test.*
   ```

   `--archive` consumes stdin. Use a parent-owned private credential runner for
   the new local restore administrator. Restore into fresh volumes only, with no
   `--drop`, `--noIndexRestore` or data transformations. Preserve failure state
   and logs privately; never retry into a partially restored target.
3. Verify all native collection names, exact per-collection counts, indexes and
   representative native relationships against the export inventory. Verify
   `pins.pinHash`, enabled/type/name and related identifiers were preserved by
   hash, without displaying hashes, PINs, PII, documents or signing material.
   Restore all jobs/webhooks/outbox/session/history documents unchanged; they
   remain inert evidence, not a work queue to drain. Review actual collection
   and field inventory for embedded provider credentials. If any exist, stop
   before application access: the archive must remain complete, but credential
   collections/fields must be quarantined from the app through an independently
   reviewed narrower role or projection; never silently discard native data.
4. Execute the manually mounted `/run/clone/create-reader-role.js` **once** as
   the local restore administrator. Its stdin accepts only the fresh local
   `CLONE_READER_PASSWORD`. It refuses an empty target or preexisting role/user.
   Its custom role permits reads of the fixed reviewed manager-view collection
   allowlist (pins, parkingspaces, parkingbays, bookings, parkingspotchangelogs,
   sitesettings, blogposts, landlords), list metadata and **only `pins.update`**
   for legitimate `lastUsedAt`/`usageCount` changes through the allowed native PIN
   routes. Mongo privileges are collection-level, not field-level; validate native
   before/after PIN diffs. All other PIN mutations remain gateway-denied. It grants no insert/delete,
   queue claims, webhook/outbox transitions, index or migration privileges.
   The restore administrator password is never provided to web. Verify the
   actual role privileges and that representative job/outbox/business writes
   fail using the app credential, with transaction/rollback-safe negative probes.
   Do not probe a real provider or enqueue a job to demonstrate denial.
5. Start **web only**. The reviewed read-only adapter binds over the pinned
   image entrypoint; it disables native Mongoose auto-index/create before model
   import, requires all sandbox/scheduler/provider flags, and starts the native
   server as an imported module. No worker/identity service exists. Check the
   native DB identity, readiness, source, denied provider credentials and absence
   of schema/collection creation. Test DNS/TCP egress denial from web/Mongo to
   controlled external endpoints; do not contact payment/message providers.
6. Start **gateway only**, loopback `127.0.0.1:18221`. It bridges ingress to the
   internal network; web and Mongo have internal-only attachments and no host
   ports. Its only unsafe-method allowlist is native PIN verify-client/staff/
   admin. All other POST/PUT/PATCH/DELETE and provider/auth/customer/webhook/job
   prefixes are denied. API reads are an explicit allowlist for native spot-change/
   location views; all nested booking auth/session/magic/extension/dashboard routes
   are denied. Copied auth/session/job collections have no app read privilege. Browser CSP confines connections and forms to self,
   blocks frames/workers, and responses are not cached. Local static-bundle
   substitution rewrites only the compiled Mac test API origin to18221, so local
   QA cannot accidentally read the old synthetic public upstream.
7. Independent QA verifies actual existing manager PIN login with the native
   bcrypt path and fresh Mac manager token, wrong/disabled PIN denial, unauth
   and cross-role denials, native manager data views and no synthetic data mix.
   User credentials and returned session tokens remain private; no brute force
   or automatic PIN guessing. Confirm copied pending jobs/webhooks/outbox counts
   and states remain unchanged and no provider/job worker exists. Manager PIN
   usage statistics may change **only in this new copy**. Confirm every original
   container/config/baseline and existing public upstream remain unchanged.
8. Only after exact source/plan/data/QA/Security approval, prepare a distinct
   hash-bound public cutover receipt that records the previous Caddy upstream,
   gated host and every changed file hash. Use `nginx.public.DISABLED.conf` only
   through that separately approved new-gateway config swap; then point only
   `tph-test.elisprotech.com` to18221 through the existing host-bound access gate.
   Recheck all protected identities. The host contains real data: review access
   authorization and gate credentials before public access. Do not change
   production hosts, DNS, Railway, database, application or identity-provider
   settings as part of this step.

Rollback changes only the recorded test-host upstream to its exact prior value
and the new gateway config if needed. It does not copy data back, switch workers,
restore/drop any existing database, reset a monitor, or accept container drift.
Keep this project's dataset/volumes and receipts for diagnosis; stopping any of
its exact owned container IDs requires its separate approved runtime operation.
No broad `down`, prune, network cleanup or volume deletion is part of the plan.

## Existing admin password is a separate identity prerequisite

Native `Pin.verifyPinByType` compares bcrypt hashes from `pins`. The client PIN
path issues a manager JWT using **fresh Mac** `MANAGER_JWT_SECRET`; production
signing-secret reuse and imported sessions are unnecessary. Environment fallback
PIN maps/admin PINs are not copied. Admin PIN success alone grants no Auth0 token.
Native `ProtectedAdminRoute` redirects to Auth0's existing
`Username-Password-Authentication` connection. Those passwords are held by
Auth0, not Mongo. The current pinned bundle and server deliberately use
`auth.tph.invalid`, so admin password login remains unavailable and must be
reported as blocked, not simulated or bypassed.

A separately approved follow-up needs an Auth0 administrator to provide/confirm
public tenant domain and API audience and create a separate SPA client in the
same tenant, enabling the existing database connection and native role claims.
The exact test origin is `https://tph-test.elisprotech.com`, callback
`https://tph-test.elisprotech.com/callback`, and logout return origin the same
HTTPS test origin. Authorize no wildcard or production callback changes. The
native code asks for `openid profile email read:admin write:admin offline_access`
and the `https://trucksparkinghub.com/roles` claim. Confirm the new client gets
existing authorized admin roles without creating or promoting users. This needs
Auth0 dashboard/account authority, presently unavailable; no management token
or private signing key is needed merely for SPA config and RS256 verification.

That follow-up requires rebuilding frontend public config for the new client,
server domain/audience, exact-issuer/audience/RS256 validation, browser CSP for
only the exact tenant authorization/token endpoints and a separately constrained
server JWKS path `https://<tenant-domain>/.well-known/jwks.json`. Keep app egress
internal: use a reviewed JWKS-only broker/cache with exact host/path/TLS controls,
not general internet access. Preserve every payment/message/job block and the
readonly app role. Validate real password login, wrong tenant/audience/role/
expired token denial, logout, and no provider effects. This is not implemented by
this clone helper and cannot be inferred from Mongo copy success.

## Ownership and current verification

- Architecture/implementation owner: only `deploy/tph-real-data/` (this helper,
  adapter, role script generator, focused tests and plan).
- Parent: private export/transfer/inventory and runtime restore/controller/edge
  orchestration after exact approvals; root board/release evidence.
- Independent Security: identity, PII, role privileges, credential quarantine,
  network/browser isolation and eventual gate/upstream acceptance.
- Independent QA: real native PIN/data journey and protected-state proof.

Source tests use temporary empty local directories and generated local secrets;
they never call Docker, read the production dump, or run a provider. Runtime,
restore, browser, public cutover and admin-password acceptance remain pending.
