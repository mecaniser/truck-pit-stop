# Read-only admin and public-key maintenance

Source-only until independent source review. This profile preserves the original
Phase2/UI artifacts and all journals. It changes only web preload/binds and gateway
GET/HEAD routing, retaining the same image, environment, MongoDB, role, port18221,
internal network, provider blocks and zero workers. The public edge stays running.

Exactly four new paths permit GET/HEAD: `/api/admin/pins`, `/api/site-settings`,
`/api/site-settings/admin`, `/api/spot-changes/location-addition-requests`.
All other existing denials remain, including `/api/profile` (GET attempts a native
upsert), operations summaries, hiring, copied customer capabilities and business
mutations. Native protected GETs still require real RS256 Auth0 JWTs, exact issuer,
audience, expiry, Mac SPA azp, and admin/superadmin role. The existing sitesettings
`global` document and property-lead count16 are checked before any activation;
absence refuses without web/gateway/cache/job changes. No valid PIN is guessed.

The derived preload invokes the unchanged reviewed resolver on a newly opened
public snapshot for every key lookup. Directory binding makes atomic host renames
visible. Unknown, expired, malformed or private keys fail closed, without falling
back to previously accepted keys. No application process gains network egress.
A dedicated host LaunchAgent runs the exact public-only fetcher every900seconds
and at load, using `/opt/homebrew/bin/python3`. It accesses only the literal tenant
HTTPS JWKS URL, no redirects/proxies, normal system TLS, total5second deadline,
64KiB limit, RSA2048+ public RS256 keys, unique kids, 24hour lifetime, canonical
hash, and atomic replacement. Fetch failure never extends the previous expiry.
No Auth0 Management credentials or provider accounts are used. Public cache
material is0755directory/0644files; other state remains private.

After independent source GO, install this directory alongside the unchanged
frozen `runtime_phase2.py`, then run **preparation only**:

```sh
python3 maintenance/prepare.py
```

Independent QA and Security review the generated `maintenance-v1/plan.json`,
source hashes and exact actions. Their external approval goes in
`private/maintenance-approval.json` mode0400. See
`runtime.approval_contract(planSHA,runnerSHA,cloneEnvSHA)`; add distinct independent
`qa`/`security` objects `{reviewer,reference,decision:"GO"}` and timezone-aware
`expires_at` within24hours. The implementing owner cannot approve. Then the
operator may execute exactly once:

```sh
python3 maintenance/runtime.py PLAN_SHA APPROVAL_SHA
```

The shared accepted operator lock covers all work. Before any activation, preserve
all old app identities, baseline data/role hashes, exact protected18 and retained
v2/diagnostic evidence. The runner checks the proposed nginx through an exclusive
file in the old owned gateway tmpfs, creates a new public cache, fetches keys,
recreates web then gateway only, syntax-checks all172 actually served JS files,
checks native unauthenticated401 plus mutation/quarantine403, and installs only
`com.macapps.tph.auth0-public-keys`. No public edge restart or role replay.
All process identities/data/role/protected state must match afterward except the
explicit new web/gateway instances. Both original baselines remain immutable.

Journal `private/maintenance-runtime`, marker `maintenance-started.json`, and
completion `maintenance-completed.json` are exclusive. Any failure preserves
state and refuses retry; it never cleans up, resumes, resets, or auto-rolls back.
A failed run requires a separately reviewed new recovery plan. Completion is
host/tool evidence only. Actual authenticated browser acceptance must then prove
Default Leads/property16, Controls/settings and Settings→PIN Management200 using
the existing real user Bearer. No tokens, PINs, contacts or customer rows go in
public receipts. Source tests do not claim that browser proof.

## Separately reviewed v2 after preactivation nginx refusal

The original maintenance-v1 profile, runner, approval, journal and tmpfs test
file are immutable failure evidence. Its nginx test refused the longer map keys;
no started/completed marker, web/gateway/cache/LaunchAgent change occurred.
Version2 adds only `map_hash_bucket_size 128;` immediately inside the existing
`http` block. It retains the frozen public-key fetcher/preload and exact four
read routes. Original runner SHA3ab6..., plan64c9..., approval155136... and failed
stderr7b910... are explicitly bound; original started/completed/before markers
must remain absent. All current fixed old app IDs, protected identities, native
data/role and edge checks still run fresh. No state reset or retry bypass exists.

After fresh source GO, use **only** `maintenance/prepare_v2.py` to create the new
exclusive `maintenance-v2` profile. Review its exact new plan and runner, then
provide `private/maintenance-approval-v2.json`0400 using
`runtime_v2.approval_contract(...)`, distinct independent QA/Security GO and
24hour expiry. The only execution command is:

```sh
python3 maintenance/runtime_v2.py NEW_PLAN_SHA NEW_APPROVAL_SHA
```

New exclusive journal `private/maintenance-runtime-v2`, marker
`private/maintenance-started-v2.json`, completion
`private/maintenance-completed-v2.json`, tmpfs config
`/var/cache/nginx/mac-maintenance-v2.conf`, and refresh stdout/stderr-v2 paths
preserve all original failures. No v2 profile or runtime has been prepared by
the implementing agent; independent review is required before either action.
