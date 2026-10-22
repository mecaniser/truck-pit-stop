# HTTPS edge acceptance and public activation boundary

Local acceptance serves only two synthetic apps through Caddy at loopback18443.
`Caddyfile.local-test` uses `.test` names, isolated private CA storage,
`skip_install_trust`, disabled admin API and disabled automatic HTTP redirects.
`test_tls.py` explicitly trusts only that test CA for this process and verifies
chain, hostname, v1/v2 routing, wrong TLS hostname denial and unknown Host404.
No machine trust-store changes, public certificates, DNS changes or public binds.

The local test process stops after acceptance. It is not a login service.
`Caddyfile.public.DISABLED` is prepared syntax only and is never loaded by the
hosting recovery job. Public activation remains blocked on:

1. Authorized access to the DNS management account for `elisprotech.com`.
2. New `apps.elisprotech.com` A record only, pointing to the verified WAN address.
   Preserve existing `www`, apex, nameservers, mail and Railway records.
3. A reserved Mac LAN address, router access and verified inbound reachability.
   Check CGNAT/double NAT/ISP restrictions before making changes.
4. Router TCP80 to Mac8088 and TCP443 to Mac8443, then explicit LAN bind in Caddy.
   Do not add AAAA without verified end-to-end IPv6.
5. Independent review of public exposure, external trusted TLS/redirect/unknown
   host tests, renewal/recovery evidence, DNS retention and a scoped rollback.

October21 read-only DNS: `www.elisprotech.com` CNAME points to
`l5clouc3.up.railway.app`; `apps.elisprotech.com` has no observed A/AAAA/CNAME.
Nameservers are Google's ns-cloud-c1 through c4; registry RDAP lists Squarespace
Domains LLC. Registrar identity does not prove which authenticated account can
edit DNS. No existing record changed.

Official references: [automatic HTTPS](https://caddyserver.com/docs/automatic-https),
[port/bind/trust options](https://caddyserver.com/docs/caddyfile/options),
[validation commands](https://caddyserver.com/docs/command-line).
Caddy obtains/renews certificates after the domain and external80/443 reach it.
The prepared template uses high internal ports behind those router forwards.
Local test certificates do not prove public trust or internet reachability.
