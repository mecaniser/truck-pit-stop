# DB-COMMS-002 local acceptance

Owner: Product & Delivery Lead; implementation evidence is not an independent gate.

Environment: dedicated synthetic PostgreSQL and Redis, backend port 8006, connected inbox port 5186. No customer database copies, live credentials, or real messages. Run the production authentication and communications router using an explicitly injected simulated provider.

Required evidence:

- Additive migration upgrades clean isolated PostgreSQL and retains history; graph has one head.
- Authenticate two permitted users, a different tenant, and a user without messaging permission.
- Conversation reads do not mark messages read. Explicit read updates only the requesting user's watermark. Later inbound messages remain unread.
- Assignment and resolve/reopen survive page reload. Stale versions fail without partial mutation. Inbound reply reopens resolved conversation.
- Same-key concurrent requests persist one operation and message and produce one simulated provider call; changed payload with the same key fails. A newly intended identical body uses a new key.
- Delivery callbacks progress accepted to sent/delivered, reject stale/duplicate regressions, and preserve evidence. Invalid signatures fail.
- Confirmed rejection is visible; accepted-but-timeout stays unknown/held and never causes another provider call on replay/restart.
- Pending operations can recover after restart; dispatching/unknown are never reclaimed for another provider send.
- Opted-out, conflicting recipient identity, tenant-disabled, unauthorized, and foreign conversation/assignment/message/operation requests fail closed.
- Browser desktop and mobile: backend mode label, persisted list/history, assignment/resolution, reply/status refresh, drafts across selection/channel/reload, unavailable-channel disabled send, error/recovery affordances and no overflow.

Independent QA/Security must review the exact implementation after these checks. Real carrier delivery, protected CI, production migration and deployment remain separate gates. Duplicate-safety claims apply only to new communications send operations; legacy sending and notifications are not silently certified.
