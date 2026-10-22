# DB-INFRA-003: public HTTPS test hosting

Owner: Release & Reliability. Status: public activation in progress; external
trusted TLS and browser acceptance are pending. Railway production is untouched.

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

## Network and DNS state

Squarespace authenticated domain access is available. DNS baseline is saved in
`mac-test-public/dns-before.json`. Existing www CNAME remains
`l5clouc3.up.railway.app`; apex/nameservers/mail/other records must be retained.
The requested two test names initially have no A/AAAA/CNAME.

User confirmed eero, saved the server reservation at192.168.4.239, and confirmed
WAN IPv4 matches observed107.15.134.82. Two exact TCP rules were provided:
external80 to Mac8088 and443 to8443. Rule completion and external path verification
remain pending. No IPv6 rule/AAAA, DMZ, SSH, database, app or worker forwarding is
authorized by this configuration.

Squarespace requires fresh passkey reauthentication before adding a record.
The user has the verification prompt. No new DNS record has been saved as of
this receipt. Public ingress is prepared/running on the approved LAN ports;
externally trusted certificates and internet access are not yet accepted.

## Retained limits and next gates

Synthetic-only data, provider egress/credentials/delivery blocks, absent recurring
business schedules and no live payments remain. External Auth0/WorkOS/provider
journeys are excluded. Existing HTTP loopback URLs remain health/operator paths;
the public-origin build and secure cookies require HTTPS for interactive login.

The original October21 7:09:59PM through October22 7:09:59PM Eastern staging
observation continues without reset. Independent checks observed110 samples and
zero issues. This public-hosting task does not complete that window.

Next: finish authorized DNS verification and only two A records; verify external
path and trusted TLS, then native browser journeys. Install independent edge login
recovery only after public acceptance. Preserve all original staging/worker/data
identities and counts. Record exact final source/PR state. No production merge or
deployment is requested.

FileVault still needs assisted unlock/login. WAN IP changes need a scoped DNS
update; no paid DDNS service or broad DNS API token was introduced. Backups remain
local, not off-device disaster recovery. Rollback removes only the new edge,
two test DNS/forwarding rules and web/gateway configuration changes, preserving
all databases, worker state and production.
