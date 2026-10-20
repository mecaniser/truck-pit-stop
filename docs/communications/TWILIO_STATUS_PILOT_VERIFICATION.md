# Twilio repair-status pilot verification

2026-10-20. DB-COMMS-012. Backend & Integrations accountable. Offline verified; live and deployment held.

## Runtime and isolation

Initial branch codex/twilio-status-pilot at5fdcb3ce9a7bc3e43a4d209672562b48bce96c9b. Standard local controller refused missing backend/.env and Vite. Existing explicit synthetic communications configuration was referenced without copying provider credentials. Fresh database twilio_status_pilot_20261020 uses loopback PostgreSQL55460/user comms_local, sole schema185; populated communications_local remained184 and unchanged. Redis6386/index12. API32341 at127.0.0.1:8006 and frontend32379 at127.0.0.1:5186 serve this checkout; process/cwd corroborated. Direct and proxied readiness pass; actual browser renders the base app. No product UI changed; automated operator integration exercises the changed journey against real PostgreSQL with fake transport.

Local servers have no live Twilio account and all three routing/outbox/recovery flags false. Production read-only preflight verified5fdcb3ce/schema185 and the same three false flags. Existing legacy notification behavior is unchanged: these new flags do not globally suppress historical immediate legacy sends.

## Provider evidence and live gate

Owned SMS-capable +17755358774 belongs to a VERIFIED campaign without reported errors. Its campaign description/samples specifically cover Right Solution Truck Parking reservations with booking/START consent. Service inbound remains TrucksParkingHub; number-level inbound/status URLs remain DieselBridge. The separate global +19129223939 belongs to the FAILED30907 campaign. No current Truck Pit Stop tenant-specific Twilio binding exists. No provider setting was changed.

Independent Security/QA holds repair-status live messages until Twilio confirms scope or a matching approved repair route is available. VERIFIED parking transport does not establish repair campaign approval. The source-locked LIVE_CAMPAIGN_SCOPE_APPROVED=False guard rejects real provider access before settings, credentials or network. No environment/CLI bypass exists. No live plan, prepare, SMS send, real order/status/customer edit, deployment or new customer automation activation occurred.

## Final owner checks

84 combined tests passed (9 existing warnings,4.78s):46 pilot tests plus38 managed-routing, automated guard and producer/transport compatibility cases. Checks cover two explicitly simulated event slots, permanent call budgets, cross-process/restart/crash holds, duplicate event/dispatch replay, strict receipts, timeout outcomes, canonical reply identity and consent/tenant changes. Private authorization must be an owned0600 regular non-symlink file with bounded size, exact schema, matching private hash and approved phone. Source cannot create/edit it; no public personal phone or authorization hash is stored. Missing/unsafe/malformed authorization fails before provider access. All test contact values are fictional. Compile and diff checks pass.

Frozen script SHA256 b600bf101cf79a909a077697103a0c09898459da27e2a5368fd214dfbe56cadf. Test SHA256 ef774f0502590d3c186e88689e41b97dcdfadfe8ba946b4b5277216672902e10. Final independent gate is recorded below. This evidence does not certify real repair-order event progression, carrier/handset delivery, production managed registration, or signed public callbacks.

## Independent final gate

Fresh independent Security/QA and full staged privacy review returned GO for the public draft/source only. Final46 pilot plus4 additional adversarial cases passed:50 independent checks on the exact hashes above. Review verified index/working source identity, no full personal recipient/phone hash/encoded equivalent or new host username in the added diff, strict private authorization, immutable budgets, credential isolation and exact reply ownership. Live remains NO-GO pending campaign-purpose confirmation. This gate does not imply removal of previously cached remote objects or approve any production/provider action.
