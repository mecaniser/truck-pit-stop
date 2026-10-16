# DB-COMMS-002 independent backend and security review

Reviewer: independent `inbox_security_gate`; no implementation participation. Scope: communications model/router/service/migration177, callback changes, connected frontend data boundary and isolated harness. Review is against the working tree on `codex/shared-inbox-backend`, not a deployed build.

Initial gate: **HOLD — implementation still changing and findings under correction.**

Findings returned to accountable owner:

1. The local ASGI harness checked the isolated database, explicit opt-in and lack of real credentials, but did not explicitly reject production configuration. Contract requires startup rejection in production even if the other local checks match.
2. Inbound normalization improvement initially locked by provider SID only. Concurrent distinct SIDs from the same previously unknown phone could create separate placeholder customers and make later sends fail identity ambiguity. Needs concurrent identity-creation evidence.
3. Conversation lookup initially excluded deleted threads but not deleted customers, unlike list queries and the contract's deleted-ID404 boundary. Historical detail/read/workflow mutations remained accessible by ID for a deleted customer.
4. PostgreSQL concurrency test used the global pending processor against a shared acceptance database. This can process another scenario's pending rows using the test sender. Independent rerun waits for scoped fixture processing or a quiet window.

Independent checks completed:

- `python -m pytest tests/test_sms_callback_reliability.py tests/test_messaging_service.py -q`: **76 passed**, two existing deprecation warnings. Synthetic offline service/ASGI checks; no carrier-delivery claim.
- Source inspected: server-derived tenant/actor; permission and tenant feature gate; tenant-qualified list/message/assignment/watermark/operation reads; thread locking and optimistic versions; durable operation + SMS commit before dispatch; dispatch claim commit before provider I/O; same-tenant/key advisory lock plus unique constraint; unknown outcomes and stale dispatching never automatically retried; terminal callback stickiness and opt-out preservation.
- Migration is additive; populated send-operation downgrade refuses deletion. Foreign keys are single-column, so isolation currently relies on service predicates for cross-table tenant consistency.
- Simulation is outside production application imports, default sender is live and fails closed when credentials are missing. Launcher strips inherited application/provider credentials and binds dedicated containers/API to loopback. No test-control HTTP endpoint.

Final gate requires final source reinspection, independently reproduced PostgreSQL tests and reviewed authenticated HTTP/browser acceptance. Real SMS delivery, protected CI, merge and deployment remain separate gates.

## Final backend/security gate

**GO for the isolated backend implementation and simulated acceptance; not a deployment approval.** Initial findings above are resolved and independently rechecked. Full UI QA remains pending the connected-login correction and desktop/mobile browser pass owned by the delivery lead.

Corrections inspected:

- Harness now rejects every environment except explicit development before application import. Independent subprocess negative regression confirms production import is rejected.
- Inbound tenant+normalized-phone transaction advisory lock prevents separate receipts creating duplicate unknown identities. Concurrent distinct-SID PostgreSQL regression passes.
- `thread_for` requires a same-tenant nondeleted customer, including idempotency replay lookup.
- Recovery tests now scope processing to their random test tenant. New deletion lifecycle finding was also corrected: pending operations whose conversation/customer disappears become conclusively rejected before I/O instead of remaining pending and aborting recovery.

Independent final execution:

- Callback and existing messaging tests: **76 passed**.
- Dedicated PostgreSQL communications tests after final corrections: **10 passed**, including same-key concurrent creation/dispatch and pending recovery; unknown held without replay; consent, tenant enablement, actor access, changed sender/recipient, shared phone, deleted customer/thread pre-I/O rejection; normalized inbound duplicate and distinct-SID concurrency; deleted-customer404.
- Local harness safety tests: **4 passed**, including actual production import rejection, credential isolation and durable simulated timeout call evidence.
- Parent reports authenticated HTTP acceptance passing eight scenario groups through production auth/router and signed callbacks. This is owner-executed evidence, not an independently rerun HTTP/browser claim. I inspected its assertions for tenant/permission negatives, per-user reads, assignment/resolve/inbound reopen, four concurrent identical intents yielding one persisted message and provider call, replay conflicts, signed delivery progression, rejection and unknown no-retry.

No unresolved backend security blocker found in this reviewed slice. Existing legacy sends/notifications are outside its duplicate-safety guarantee. Recovery is an explicit bounded processor, not a newly scheduled production worker. Real carrier verification, protected CI, final browser QA, migration rollout and deployment authorization remain required before release.

Final inbound-version delta: inspected creation of workflow version2 when inbound arrives on a metadata-free legacy conversation, under the thread lock. Independently reran the inbound normalized identity/duplicate receipt PostgreSQL regression after this change: **1 passed**. Sequential distinct inbound arrivals now advance that workflow to version3; backend/security GO remains unchanged.

## Connected frontend source gate

Independent reinspection of final `ConnectedInbox`, transport adapter, shared preview changes and actual Axios interceptor tests found no blocking frontend security or send-recovery issue. `npx vitest run src/features/communications --run`: **16 tests passed across four files**. Coverage includes signed-out401 without invalid refresh, cookie-only session acceptance, WorkOS renewal, exact stored send recovery after network loss/reload, double-click suppression, preservation of a newer draft, corrupt recovery fail-closed behavior, cross-contact/channel drafts and unavailable-channel blocking. Server data maps explicitly; no fixture conversations enter the connected adapter. Current session epoch guards and tenant/user storage keys prevent late response/draft mixing across sessions. Shared `lib/api.ts` behavior is reused rather than changed globally.

Awaiting final desktop/mobile screenshots and delivery-lead browser receipt before the overall local workflow QA gate.

## Final isolated workflow QA gate

**GO — DB-COMMS-002 isolated simulated workflow acceptance. This is not production release approval.**

Independently inspected the desktop1280×900, mobile390×844 and refreshed mobile held-delivery screenshots using the image tool. Desktop list/history/contact panels, readable delivery states and simulation label are coherent. Mobile normal and unknown-detail views preserve readable history and composer controls without horizontal clipping. The initial held-state capture showed an incomplete footer; the delivery lead rechecked exact DOM bounds (Send button772–803 within844) and replaced the mid-layout capture. The refreshed image independently confirms the disabled Send SMS button and full footer are visible. No source change was required for that capture issue.

Reviewed `CONNECTED_INBOX_VERIFICATION.md` and `.impeccable/review/http-acceptance.json`: the final HTTP pass adds the previously missing foreign send/read/history/workflow/message-ID and unauthorized mutation checks. It explicitly separates the initial fresh unknown timeout from the retained held fixture in subsequent runs. Browser execution remains delivery-lead evidence; screenshot inspection, source review and focused automated reruns are independent evidence.

Also inspected the final local recovery CLI: it imports the guarded isolated sender and invokes the already-reviewed bounded processor with limit50; it adds no production route or scheduling and does not reclaim held operations.

No unresolved blocker for the authorized isolated workflow remains. Real SMS/carrier verification, protected CI, production scheduling/reconciliation readiness, merge and deployment are still required before release. Legacy sending and notifications remain outside the new operations' duplicate-safety guarantee.
