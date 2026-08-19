# DB-035 Utility Inbox Navigation Decision

**Status:** Product-selected implementation contract (2026-08-14)  
**Owner:** Frontend & UX Recovery Owner  
**Scope:** New authenticated presentation shell only

## Decision

The authenticated rail distinguishes three user intents rather than presenting
every destination as one flat workflow:

1. **Operate:** Shop Work, Repair Orders, Customers.
2. **Manage the shop:** My Shop, visually separated from operating work.
3. **Communicate:** Messages, placed as an account-adjacent utility above the
   Profile & settings control.

Messages remains an inbox with the existing message-square icon and unread
count. It is not represented by a bell, because alerts/notifications are a
different product concept.

## Responsive contract

- At 960px and above, the rail lists the operating destinations in the order
  **Shop Work → Repair Orders → Customers**. A quiet `Manage shop` boundary
  precedes My Shop. Messages is an account utility with its existing unread
  affordance.
- Below 960px, the primary navigation contains Shop Work, Repair Orders,
  Customers, and More. Messages, My Shop, and Profile are reachable from the
  existing More page; the Messages unread affordance remains visible.
- The compact rail keeps icon-only navigation with accessible names and titles;
  the expanded rail reveals the corresponding labels.

## Non-goals and invariants

- No route changes: `/dashboard`, `/dashboard/repair-orders`,
  `/dashboard/customers`, `/dashboard/messages`, `/dashboard/garage`, and
  `/dashboard/settings` remain authoritative.
- No API, data, notification, or permission change. The existing
  `canAccessMessaging` gate and `/messages/unread-summary` query remain the
  only authority for exposing Messages and its unread count.
- The legacy presentation retains its incumbent navigation order and labels as
  the immediate rollback path.
- No backend, schema, migration, authentication, or tenant-boundary work is
  included.

## Acceptance criteria

- New desktop/compact rail has contiguous Shop Work, Repair Orders, Customers
  order; Messages is not a primary operating item.
- My Shop is visibly separated as management; Messages is accessible from the
  account utility and carries the current unread count when non-zero.
- New mobile primary navigation has Shop Work, Repair Orders, Customers, More;
  Messages and My Shop retain their existing accessible routes under More.
- Legacy navigation and every existing route/permission condition remain
  unchanged.
- Focused shell tests, build, changed-file lint, and bounded browser evidence
  cover desktop, compact rail, and mobile grouping.
