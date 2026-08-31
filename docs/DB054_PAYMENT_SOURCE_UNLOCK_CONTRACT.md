# DB-054 — Payment-source unlock hierarchy

## Outcome

Make the Payments & Accounting unlock message truthful without weakening the
server boundary:

- A valid `payment_sources.manage` grant authorizes tenant payment-source
  management for its existing short lifetime, including Stripe and QuickBooks
  disconnect and Zelle disable/QR removal.
- Without a valid manage grant, a destructive control requests one exact,
  short-lived, one-time grant for that action.
- A destructive consequence dialog is shown only after either grant has been
  issued. The provider mutation happens only after the user confirms it.
- Platform reset scopes and repair-order force-void remain exact-scope only.

## Server rules

- Reusable manage authority is accepted only for tenant payment-source scopes:
  `payment_sources.stripe.disconnect`,
  `payment_sources.quickbooks.disconnect`,
  `payment_sources.zelle.disable`, and
  `payment_sources.zelle.qr.remove`.
- User, tenant, session JTI, session version, token version, expiry, and target
  checks remain mandatory.
- A manage grant is never consumed by a destructive mutation. An exact
  destructive grant remains one-time and is consumed atomically with the
  mutation.
- Auditing records the requested mutation scope and the grant actually used.
  No provider credentials, passwords, or raw grant values are persisted.

## Interface rules

- When Payments & Accounting is unlocked, destructive controls open the final
  consequence dialog directly and never ask for the password a second time.
- When it is locked, selecting a destructive control opens password verification
  first. Only successful verification reveals the final consequence dialog.
- Cancel, Escape, and backdrop dismissal discard an action-specific grant from
  frontend memory and perform no provider mutation.
- Disconnect/disable buttons remain disabled while their mutation is pending.
- Verification and consequence dialogs inherit the active staff presentation;
  Day shop uses a light surface and Night shop uses a dark surface.

## Acceptance

- Manage grant authorizes each tenant payment-source destructive endpoint and
  remains reusable until expiry or explicit relock.
- Exact one-time grants still authorize only their matching action and cannot be
  replayed.
- Manage grants cannot authorize platform resets, repair-order force-void, a
  foreign tenant, another user/session, or an expired/revoked grant.
- Locked QuickBooks/Stripe disconnect never exposes the consequence dialog or
  calls the provider mutation before password verification succeeds.
- Unlocked QuickBooks/Stripe disconnect asks for no second password, preserves
  final confirmation, and sends the manage grant to the backend.
- The shared dialogs are keyboard-operable and visually correct in Day shop and
  Night shop.
