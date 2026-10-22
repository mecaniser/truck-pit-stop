# Public HTTPS for isolated Mac test apps

DB-INFRA-003. Release & Reliability owns this ingress. It depends on the accepted
synthetic test stacks from PR619 and never manages Railway production.

| Application | Approved public origin | Private HTTPS-profile upstream |
|---|---|---|
| DieselBridge | https://dieselbridge-test.elisprotech.com | 127.0.0.1:18210 |
| Trucks Parking Hub | https://tph-test.elisprotech.com | 127.0.0.1:18211 |

These are test addresses. Production domains, apex/www, nameservers and mail
records must remain unchanged. No wildcard or AAAA record is part of this setup.

## Access and isolation

Caddy terminates HTTPS and checks a separate test password gate before forwarding
any app page, asset, API or WebSocket. A successful gate login sets an eight-hour
host-bound `__Host-test-access` cookie. Native app authentication remains required;
the gate never replaces a Bearer token or impersonates an app user.

The private gate listens on loopback18680 only. Login/logout use exact Origin and
expiring CSRF checks, bounded request bodies, rate limits, and private scrypt/HMAC
credentials. Unknown hosts, private gate endpoints and public health/readiness
routes are denied. Test pages carry noindex/noarchive headers. The app CSP still
blocks browser requests to external providers.

The original private nginx8080 profiles remain. Each existing test gateway adds
nginx8081 bound to a distinct Mac loopback port; this public profile hardcodes the
verified HTTPS scheme. No forwarded scheme header from a client is trusted.
Only the two test web services and gateways are recreated. Databases, Redis,
workers, queues, volumes, provider credentials and original staging remain intact.

DieselBridge uses its exact public frontend/CORS origin, secure host-only cookies
and the existing staging environment. The new TPH web image embeds its exact HTTPS
API origin. TPH workers retain the previous image and configuration. No migration,
seed, enqueue, scheduler, provider enablement or stack-wide recovery is performed.

## Preparation and gates

`configure.py IMAGE_ID` runs only on the dedicated Mac. It creates
`~/mac-hosting/test-public` once, snapshots original Compose/nginx bytes privately,
and writes pending configurations. It does not start services or edit DNS.
Build `Dockerfile.tph` from the same explicit pinned TPH source archive as the
private stack; preserve synthetic identity, payment and analytics settings.

Create the gate credentials only on the Mac under private0700 directories and
mode0600 files. Never commit, print or put passwords in URLs, arguments or logs.
`access_gate.py` documents the precise private configuration format.

Before activation, require independent source and runtime QA/Security. The local
TLS profile binds only127.0.0.1:18444 and uses a process-local CA without installing
machine trust. Canonical-Origin HTTP fixture checks do not prove browser trust or
public reachability. Final browser acceptance requires real public certificates.

## Router and DNS

Reserve the dedicated Mac's LAN address192.168.4.239 in eero. Verify the router's
WAN IPv4 equals the observed public IPv4, inspect existing forwarding rules, and
confirm inbound reachability rather than assuming it from an outbound request.
Forward only TCP80 to Mac8088 and TCP443 to Mac8443. Do not forward SSH,
databases, Redis, app/gateway ports, the auth helper or Docker.

After local gates and router verification, add only the two exact new A records
to the current authoritative DNS. Existing `www.elisprotech.com` must retain
`l5clouc3.up.railway.app`; preserve all other records. Enable the public Caddy
profile only after the activation receipt records the approved configuration.

External acceptance requires trusted certificate chains and hostnames for both
sites, correct standard-port HTTP redirects, unknown-host denial, gate login and
negative cases, native app login/API behavior, helper-down denial and unchanged
worker/database identities and synthetic job/publication counts. Keep the original
24-hour staging observation and its accepted baseline untouched.

## Recovery and rollback limits

Use only the scoped rollout/edge tools in this directory. Their private journals
and snapshots retain failures; inspect an uncertain operation before resuming.
Rollback restores only the two test web/gateway configurations and stops only the
edge's own child processes. Remove only the two added DNS/forwarding rules when
withdrawing public access. Never delete databases or change production.

FileVault still needs assisted unlock/login after reboot. A changing residential
WAN address can require an update to these two records; no persistent DNS API
credential or automatic DNS updater is included. Local backups remain on the Mac.
