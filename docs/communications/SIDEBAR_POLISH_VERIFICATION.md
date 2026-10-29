# DB-COMMS-024 — Contact details and dropdown polish

Frontend & UX accountable; Fast UI lane. Existing APIs and permissions unchanged.

## Acceptance

- One contact card above Contact/Fleet history contains identity, company, role,
  phone, link action and existing consent controls. No repeated SMS-contact block.
- Consistent menus for repair status, person, assignment and reply channel;
  keyboard operation, Escape/focus return and unclipped mobile menus.
- Preserve customer confirmation/retry behavior, transport routing, per-channel
  drafts, history scopes, consent and automation flags.

## Verification

43 focused component/inbox tests pass; changed-source ESLint, TypeScript and
Git diff checks pass. Existing tests now interact with styled menus; no assertions
or timeouts removed. A regression verifies one identity card and resetting link
confirmation when changing the selected person. jsdom ResizeObserver stub covers
its missing layout API; actual menu layout verified in browser.

Signed-in local browser: contact history/status switch, separate fleet view,
customer person menu, Escape restores focus, cancel preserves draft, mobile
390x844 drawer/menu and sticky close header. Original synthetic draft retained;
no provider send. Private desktop/mobile screenshots under `/tmp/comms024-sidebar-*`.

## Local runtime receipt — October 29, 2026

Worktree callrail-inline-mms/truck-pit-stop; branch codex/messages-sidebar-polish,
base b6cb2e4c, scoped uncommitted UI changes. Frontend5193 PID40013 and backend8013
PID39978 serve this checkout; source cwd verified. Frontend API proxy reaches8013;
direct and proxied readiness both DB/Redis OK. Approved isolated synthetic database
communications_local_023_20261028 on loopback55460, Redis6386/db14; no migration or
reseed. Launcher forces all three SMS flags false and denies external provider
network. Rendered branch indicator and revised card/menus confirmed. Aligned and
browser-verified at http://127.0.0.1:5193/dashboard/messages. This receipt expires
on source/process/config change; local rendering is not production deployment.

PR/protected CI, merge and production deployment pending. No production UI
changes are claimed; the separately authorized repair associations are recorded
in CONTACT_REPAIR_CONTEXT_VERIFICATION.md.

PR668 opened; integrated main3fdafd12 (fleet map fix) cleanly after owner gates.
Messages source remains identical to the tested UI commit ee7a078f. Runtime
receipt above records the tested source; the displayed development stamp predates
this integration and is not a claim of final-head alignment. Protected CI pending.
