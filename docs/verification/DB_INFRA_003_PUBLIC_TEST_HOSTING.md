# DB-INFRA-003: public HTTPS test hosting

Owner: Release & Reliability. Status: public synthetic test hosting accepted.
Both sites have trusted HTTPS and verified native browser logins. Dedicated edge
login recovery is installed and running. Follow-up PR621 remains draft/unmerged, based on
PR619. Railway production is untouched.

## Authorized scope and contract

The user requested both existing synthetic test apps online through HTTPS test
subdomains under elisprotech.com. Exact hosts are
`dieselbridge-test.elisprotech.com` and `tph-test.elisprotech.com`.
Architecture approved exact-host Caddy ingress and a separate host-bound signed
cookie gate. Native app login remains required. No production app/domain/record,
nameserver, provider credential, seed, migration or business worker activation is
part of this item. Source is on `codex/mac-test-public`, based on PR619.

The local-runtime skill was read and controller dry-run executed after creating
the owned worktree. It refuses workstation development startup because backend
environment and frontend dependencies are absent. Runtime acceptance targets
the separate dedicated Mac, not workstation5173/8000.

## Source and runtime changes

DieselBridge retains app source65afe9b8 and its immutable existing image. Only
test-web frontend/CORS origin, secure host-only cookie settings and its gateway
change. TPH source remains b369e9f5; public web image is
`sha256:7b25bcd8c6688cf695ffed53f067e16528184b9a60e954d4d72121477f9d8690`.
It embeds the exact public HTTPS API origin while keeping fake identity,
payments off and analytics off. TPH workers retain their prior image/config.

Each gateway retains private8080 and adds8081, bound only to Mac loopback18210
or18211. Its public profile hardcodes HTTPS, preserves restrictive CSP/banner,
and denies health/readiness/metrics paths. Caddy alone binds LAN8088/8443. Its
admin API is disabled. Auth helper remains loopback18680. Unknown hosts and
private helper routes are denied. Native Bearer tokens are not replaced.

Gate access uses separate fresh private scrypt/HMAC secrets, host-bound eight-hour
`__Host-` cookies, Secure/HttpOnly/SameSiteStrict/Path=/ without Domain, exact
Origin and signed CSRF checks, bounded threads/body/timeouts and rate limits.
Passwords/cookies/request bodies are not logged or printed. App responses carry
noindex/noarchive instructions. The gate does not grant native app permissions.

## Local evidence

- 14 helper checks and seven configuration contract checks pass. The initial
  configuration test found a shared environment-object alias in generator input;
  the web override now explicitly detaches its environment. Remote JSON input
  had independent objects and the worker-preservation guard passed before apply.
- Independent QA rejected six rollout scope escapes, including worker/network,
  host mount, storage image, public binding and nginx changes.
- Scoped rollout recreated only each test web and gateway with `--no-deps`.
  Protected ten containers out of fourteen retained identity, start, image,
  configuration and network hashes. Original staging baseline hash unchanged.
- Actual TLS using the isolated local CA passed both hostnames, gate login,
  API/unsafe denial, cross-host cookie rejection, native DieselBridge secure
  cookies/Bearer and bidirectional tenant denial, native TPH manager PIN and
  wrong-PIN/admin/hidden-location negatives, readiness denial and logout.
- These are canonical-Origin fixtures on loopback18444. They do not prove public
  trust, public reachability or native browser authentication on public sites.
- Actual Caddy with helper absent returns502 for both apps and never bypasses
  authentication. The exact owned local child processes were stopped afterward.
- Read-only PostgreSQL counts: tenants2/users2/customers2/receipt1/executions1.
  Mongo: locations2/PIN1/job1/attempt1/completed/post1/published0/scheduled0.
  No worker was triggered by this verification.
- Independent QA and Security GO cover the scoped public activation after these
  local checks. Final public certificates, reachability and browser gates remain.

## Network and DNS acceptance

User saved eero reservation192.168.4.239 and confirmed WAN107.15.134.82.
TCP80 forwards to8088; TCP443 forwards to8443. Standard-port HTTP redirects and
trusted public HTTPS were verified through those rules. No other forwarding was
added. Squarespace verification was completed by the user. Only two A records,
`dieselbridge-test` and `tph-test`, were saved at107.15.134.82, TTL1800.
Authoritative DNS verified both. Existing apex/www, nameservers, mail and other
records remain unchanged; www still points to `l5clouc3.up.railway.app`.
See `dns-after.json`, `dns-records-saved.png` and `network-receipt.json`.

## Final runtime and independent acceptance

- Public certificates validate using ordinary DNS443 and system trust on both
  hostnames. No browser warning bypass or local CA was used for public acceptance.
- Native browser DieselBridge login reached Customers, active Staging Alpha,
  exactly one Synthetic Alpha Fleet customer and no remaining asset errors.
- Native TPH manager PIN, manager confirmation and manager tools reached
  `/spot-changes`. Zero operational yards is the expected synthetic fixture;
  this does not prove a populated parking operation or external SSO.
- Public HTTP fixtures verify secure native cookies, retained Bearer credentials,
  bidirectional tenant denials, query-bearing API requests, gate logout and
  cross-host rejection. Unknown hosts, readiness and private helper paths deny.
  TPH accepts only the exact HTTPS test Origin with both test/sandbox guards;
  HTTP and lookalike origins deny. Helper absence fails closed with502.
- Independent QA and Security accepted final source, image and browser evidence.
  All29 focused checks pass. A64-way100-asset test returned100/100 HTTP200.
- Final TPH web image is
  `sha256:95df264063f3224f9a2519fd68a99e537f7a8da26d17ff78b5e6a87267a798b0`.
  Its verified accepted frontend base is `sha256:7b25bcd8c6688cf695ffed53f067e16528184b9a60e954d4d72121477f9d8690`.
  Only the exact guarded native CORS callback was overlaid. Worker images remain
  unchanged. Repair recreated only TPH web/gateway; twelve other containers and
  original baseline retained identities, starts, configuration and network hashes.
- Dedicated `com.macapps.testpublic.edge` LaunchAgent bootstrapped successfully
  after recording current config digest and real TLS/browser acceptance. It runs
  only the helper/Caddy pair. Both native browser sessions survived reloading
  after transfer from the temporary runner. No reboot was performed.
- Final snapshot retains all fourteen container identities after edge recovery.
  PG counts remain2|2|2|1|1; Mongo locations2/PIN1/job1/attempt1/completed/post1,
  published0/scheduled0. Independent Security additionally verified zero messaging,
  notification, payment and hiring-send records. No job was enqueued or retriggered.

Evidence: `browser-receipt.json`, both public browser screenshots,
`public-tls-http-receipt.json`, `cors-overlay-build-receipt.json`,
`tph-image-repair-after.json`, `tph-image-repair-completed.json`,
`public-acceptance.json`, `recovery-receipt.json`, `final-snapshot.json`,
`counts-after.json` and `soak-at-public-acceptance.json`, all under
`mac-test-public/`. Private credentials and detailed failure logs stay on the Mac.

## Investigated failures retained

Initial ACME requests preceded DNS propagation and returned NXDOMAIN; after DNS
verified, one owned edge restart resolved a pending order/backoff. Logs and keys
were retained. Query-bearing forward-auth paths required normalized dispatch.
`no-referrer` caused browser Origin:null; same-origin referrer policy fixed login
while null Origin remains denied. Vite asset bursts exceeded initial general
limits and later helper concurrency; bounded general limits and Caddy transport
queues fixed429/502 without relaxing login limits or helper thread bounds.

Native TPH CORS lacked this new hostname. The exact test/sandbox guarded patch
fixed it. A full frontend rebuild hit the Node heap limit (SIGABRT, no container
OOM); a raw digest FROM attempt failed local image resolution. Both logs remain.
The final verified local base alias plus backend-only overlay avoided rebuilding
accepted frontend assets. The earlier alternative image was never deployed.
No failure reset the staging clock, erased worker evidence or changed production.

## Retained limits and review state

Synthetic-only data, provider egress/credentials/delivery blocks, absent recurring
business schedules and no live payments remain. External Auth0/WorkOS/provider
journeys are excluded. Existing HTTP loopback URLs remain health/operator paths;
the public-origin build and secure cookies require HTTPS for interactive login.

The original October21 7:09:59PM through October22 7:09:59PM Eastern staging
observation continues without reset. Final recovery checks observed157 samples and
zero issues. This public-hosting task does not complete that window.

Follow-up PR621 remains draft/unmerged on `codex/mac-test-public`, with PR619 as its base.
PR620 was independently merged at01:34:45UTC into the staging branch as
`59006bfd61aa080932af2398c6bca373481aa606`; its tree matched the initial
`08db1729` exactly. Final fixes are in PR621. No merge was performed by this
implementation run. PR619 into main remains open. Public test operation is accepted; production release and original24-hour
stability acceptance remain separate and pending. No production merge or deploy
is requested. The existing background monitor remains active.

FileVault still needs assisted unlock/login. WAN IP changes need a scoped DNS
update; no paid DDNS service or broad DNS API token was introduced. Backups remain
local, not off-device disaster recovery. Rollback removes only the new edge,
two test DNS/forwarding rules and web/gateway configuration changes, preserving
all databases, worker state and production.
