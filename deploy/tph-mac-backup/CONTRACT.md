# TPH Mac backup preparation contract

DB-INFRA-005, Release & Reliability owner. User requires RPO0: no lost bookings.
Prepare a synthetic rehearsal without changing the actual Railway primary.
Both “Railway simulation” and “Mac backup” run on the dedicated Mac. No real
Railway switchover, native payment/message/job protection or production readiness
claim follows from this rehearsal.

Two native TPH apps share a freshly restored synthetic Mongo database. One
loopback18310 router admits only reviewed public reads and native manager PIN
verification. No other native mutation, webhook, payment, message or enqueue
route is accessible. No direct app ports, providers, business workers, public
DNS/edge changes or production credentials/data enter the rehearsal.

Durable control: active(site,epoch), drain admission, wait for known outcomes,
verify exact old rehearsal container stopped, verify fresh shared data authority
and checkpoint, then promote target at a new epoch. No timed forced promotion or
automatic expiry. Unknown outcomes and stale/unreadable data refuse transition.

Separate explicit fake provider effects use durable kind/business IDs and payload
hashes. Concurrent/repeated operations produce one known effect; conflicting
payloads refuse. Lost acknowledgement leaves unknown state and blocks switching.
Read-only authoritative reconciliation records an already accepted effect without
resending. This ledger does not wrap native production Square/email/SMS/jobs.

Acceptance includes actual synthetic mongodump/restore into a new owned database,
row/index hash checks, native read/PIN metadata through both directions, denied
stale/inflight/unknown/data transitions, controller restart persistence and
concurrency. Every existing14container identity and original soak baseline stays
unchanged. Live activation always refuses until a separate approved release
integrates primary fencing, zero-loss data authority, durable native provider
operation IDs/reconciliation and domain/provider authorization.
