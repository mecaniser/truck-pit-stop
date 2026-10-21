# Owner-only repair reply route contract

DB-COMMS-014. Architecture & API Contracts reviewed; Backend & Integrations owns implementation. This is isolated preparation, not customer rollout or a live callback acceptance claim.

## Sender and approval boundary

Keep +17755358774, its Messaging Service, TPH inbound route, hiring records and existing conversations unchanged. Candidate repair sender +19129223939 is already owned and SMS capable. Its existing repair campaign is FAILED30907; its effective service uses the number webhook pointing at DieselBridge. Registration correction and confirmation that this sender is dedicated remain live gates. No purchase or provider submission is part of this implementation. A different number does not fix registration by itself.

## Additive identity contract

Add an explicit Twilio reply route with immutable provider account SID, canonical dedicated To, approved From, tenant, customer and existing thread. Include approving actor, private approval reference, approval/expiry timestamps, disabled default, revocation time/reason. No route API, production seed or outbound capability. Do not store actual tester values in public artifacts; use fictional contacts for tests.

Any route history reserves its receiving number for pilot handling, including disabled/expired/revoked rows. Do not filter inactive rows out and fall through. Wrong/missing account, unknown From or inactive route fails without generic lookup, placeholder creation or cross-product forwarding. Normal nonpilot routing outside reserved receivers is preserved.

The public endpoint authenticates the supplied configured legacy AccountSid and Twilio signature before lookup or mutation for this pilot, independently of customer rollout flags. A route row cannot select credentials or approve an unknown provider account. Do not confuse authenticated legacy account with managed tenant routing enablement.

Under route row lock revalidate enabled/approved/unexpired/unrevoked state, active tenant, nondeleted customer/thread, exact same-tenant thread ownership and current normalized customer phone. Approval pins the chosen DBN identity despite a same-phone ETS duplicate; never merge/delete contacts or rewrite history. Require a valid same-tenant active staff approver. Serialize revocation and ingest. Preserve pinned customer STOP semantics; START does not fabricate managed consent.

Persist route identity on inbound receipt. Serialize account+MessageSid before insert. Duplicate acceptance requires inbound direction, account, To, From, tenant, customer, thread and immutable route identity to match. Conflict rejects without disclosing another receipt. Valid concurrent duplicate creates one message/unread increment. Referenced route deletion is restricted; revoke rather than erase.

## Acceptance

Signed API integration to a synthetic pinned DBN thread with duplicate ETS customer; reject wrong signature/account/To/From, disabled/expired/revoked route, changed phone and foreign/deleted subject. Receiver history must prevent fallback. Concurrent duplicates are idempotent; conflicting SID fails. ETS and separate TPH fixtures remain unchanged. Flags remain false, no outbound/provider calls, and previously consumed pilot budgets are untouched. Fresh isolated migration rehearsal plus independent Security/QA required.

Live gate: review registration correction and dedicated sender ownership, explicitly approve provider setup/registration, establish a fresh reply-only test authorization, then verify real signed public callback using the owner's phone. Old two-event outbound budgets remain consumed and must not be reset. Customer automation requires separate review.

## Rollback and release boundary

This candidate creates no route rows on deployment and exposes no route-writing endpoint. Code rollback before any live route approval can retain the additive schema. Once a real receiver is reserved, revoke the approval to hold ingress and retain its history. Do not roll back to a reader that lacks reservation checks while that receiver remains publicly active. Provider routing and activation are separately reviewed operations; the isolated test does not perform them.
