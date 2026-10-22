# Historical creation commands — do not replay

The real-data copy already exists. This document preserves the original creation
contract; these commands are not an update or rollback procedure. Do not rerun
restore, role creation, or old one-shot activation helpers. Current receipts and
limitations are in `docs/verification/DB_INFRA_006_REAL_DATA_COPY.md`.

For a future separately approved fresh copy, the owner must verify private
source/plan/image hashes and target emptiness before
running these. These commands are **not executed** by preparation. They refer
only to the new project; do not substitute an existing test project/container.
Shell variables below contain no production URI or credentials.

```sh
CLONE_ROOT=/Users/sergio/mac-hosting/tph-real-data-v3
CLONE_ARCHIVE=/Users/sergio/mac-hosting/real-data/private/captures/20261022T214813Z/ParkRightDB.archive.gz
CLONE_PROJECT=$(python3 -c 'import json; print(json.load(open("/Users/sergio/mac-hosting/tph-real-data-v3/plan.json"))["project"])')
```

Verify exact archive bytes17398592 and SHA256
`caf0a0fcdcbf70d9bcf7b237610327938687a0f8081907290f4eb025c5267fba`, fixed
root owner marker, plan artifacts, full image IDs/source/ARM64, no previous
project objects and no18221 listener. Independently inspect all Docker subnets
and host/LAN/VPN routes for overlap with the fixed `10.240.64.0/24` internal and
`10.240.65.0/24` ingress networks. Hold Phase1 if any overlap or route uncertainty
exists. These are fresh new networks; do not reuse or delete an existing network.
Preserve the superseded original `~/mac-hosting/tph-real-data` prepared root and
its original plan SHA; v3 preparation refuses any preexisting v3 root. Acquire the original shared operator lock
through the parent reviewed controller; do not interfere with its edge lifetime
lock or monitors. Establish all protected pre-operation identities.

Phase1 approval permits only preparation, the next Mongo start, full restore and
private inventory. It does not approve an app user or web/gateway start.

Preserve the failed v2 project/volumes/logs at
`~/mac-hosting/tph-real-data-v2`; no in-place reimport or cleanup. This v3 Mongo
must start with `--setParameter ttlMonitorEnabled=false`. Independently verify
that actual server parameter false before restore and again before comparison.
No TTL index is dropped or rewritten. Use a fresh project token and volumes.

First start only this project's fresh Mongo:

```sh
docker --context desktop-linux compose --env-file "$CLONE_ROOT/private/clone.env" -p "$CLONE_PROJECT" -f "$CLONE_ROOT/compose.json" up -d --no-deps --wait --wait-timeout 120 mongo
```

The parent must record the exact new Mongo CID and volumes, verify
`tph_local_test` has **zero application collections**, and verify this is not any
existing Mongo. Restore all documents/indexes with stdin streaming. The config
file contains only the new local administrator password; it avoids password
command arguments and is mounted only in this new Mongo.

```sh
docker --context desktop-linux compose --env-file "$CLONE_ROOT/private/clone.env" -p "$CLONE_PROJECT" -f "$CLONE_ROOT/compose.json" exec -T mongo mongorestore --config /run/clone/restore-config.yml --username clone_restore_admin --authenticationDatabase admin --archive --gzip --stopOnError '--nsInclude=ParkRightDB.*' '--nsFrom=ParkRightDB.*' '--nsTo=tph_local_test.*' < "$CLONE_ARCHIVE"
```

Stop on any restore error and preserve this failed volume; do not retry into it.
Compare all restored collection counts/indexes against the parent export
inventory. No index omissions or native document filtering is allowed. Review
embedded credentials before granting application reads. No database password,
PIN/hash, document, PII or provider secret belongs in a public receipt.

STOP after inventory. Obtain distinct Phase2 source/role/data/privacy approval
before any remaining command.

Create the narrowly scoped app role **after** full restore validation. The
following private pipe reads only fresh local secrets and does not print them to
the terminal. The role script authenticates against the new Mongo's own local
administrator using its existing container environment; it never accepts a
production connection string or changes any production user.

```sh
python3 -c 'import json; p="/Users/sergio/mac-hosting/tph-real-data-v3/private/clone.env"; d=dict(line.rstrip("\n").split("=",1) for line in open(p)); print(json.dumps({"password":d["CLONE_READER_PASSWORD"]}))' | docker --context desktop-linux compose --env-file "$CLONE_ROOT/private/clone.env" -p "$CLONE_PROJECT" -f "$CLONE_ROOT/compose.json" exec -T mongo mongosh --quiet --file /run/clone/create-reader-role.js
```

Independently inspect role privileges and prove no job/outbox/booking/index write
is permitted using app credentials. Confirm target database binding, no provider
credentials, preserved native PIN hashes, protected containers/monitors unchanged,
and no pending native work was advanced. Then start only web:

```sh
docker --context desktop-linux compose --env-file "$CLONE_ROOT/private/clone.env" -p "$CLONE_PROJECT" -f "$CLONE_ROOT/compose.json" up -d --no-deps --wait --wait-timeout 120 web
```

Verify exact source/Mongo identity, readiness5051, no startup schema or native
job writes, and actual controlled-endpoint egress denial. Then start gateway:

```sh
docker --context desktop-linux compose --env-file "$CLONE_ROOT/private/clone.env" -p "$CLONE_PROJECT" -f "$CLONE_ROOT/compose.json" up -d --no-deps --wait --wait-timeout 120 gateway
```

Native manager PIN/browser acceptance is only at
`http://127.0.0.1:18221` via an authorized private tunnel from the workstation.
No production PIN is recorded in the command or receipt. There is **no public
upstream switch command here**. That requires its separate exact edge activation
hash/recovery receipt and native-data/privacy/identity QA. The previous public
upstream remains unchanged. Admin password login remains blocked until the
separate Auth0 prerequisite is met.
