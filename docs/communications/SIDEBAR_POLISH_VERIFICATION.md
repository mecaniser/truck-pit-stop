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

## Permissions disclosure and pinned footer — October 29

PR668 follow-up: SMS permissions start collapsed. Opt-out and withdrawal warnings
remain outside the disclosure; consent evidence and write handlers are unchanged.
Assigned to, Status and Channel now occupy a fixed sidebar footer, with contact
and repair content scrolling independently.

48 focused tests pass across SMSSetup, CustomerRepairContext, communications and
ConnectedInbox; changed-source ESLint, TypeScript and diff checks pass. Regression
coverage verifies collapsed withdrawal visibility and no consent writes.
Desktop and 390x844 browser checks verified disclosure, visible opt-out state,
footer visibility while scrolling, and retained inquiry draft and receiving-number
reply route. No messages or consent changes were submitted. Private screenshots:
`/tmp/comms024-permissions-footer-desktop.png` and
`/tmp/comms024-permissions-footer-mobile.png`.

Runtime re-aligned on branch codex/messages-sidebar-polish at 3f3eee6d plus these
scoped changes: frontend5193 PID46306, backend8013 PID39978, both cwd verified in
this worktree. Rendered branch stamp and changed UI confirmed. Direct and proxied
readiness report DB/Redis OK; isolated database/provider-deny/false-flags setup
above retained. This is local acceptance; merge and production release pending.


## Released — October 29, 2026

PR668 merged as `c52ddc6ec011fcae7bb70da5d301521287223d9b` after all six
strict protected checks plus dependency preparation passed on
`fd5c31186c37385bfa56f734d85826d6e1e2754d`, run40822081177.
Checked and merged trees both `33763b00620ed5c438c9d3f50efa5e867c011a44`.
Automatic Web deployment `40882250-009b-499f-80fd-f27f32059ff7` succeeded;
website build-version serves the exact merge SHA and production DB/Redis
readiness passes. No duplicate deployment requested.

Signed-in live acceptance: SMS permissions initially collapsed, expands and
collapses without consent changes. Assigned to/Status/Channel footer retains
identical vertical bounds while the contact repair history scrolls. Existing
receiving-number route, contact/truck links, conversation selection and empty
draft preserved. No send, assignment, status, consent or service-update mutation.
All three SMS flags remain unset/default false on Web and Worker after release.
Private evidence: `/tmp/comms024-live-sidebar.png` and
`/tmp/comms024-live-footer-scrolled.png`; customer content excluded from repository.
Opt-out/withdrawal warning coverage remains the focused automated and synthetic
browser evidence above; no real opt-out was manufactured for this UI release.

DB-COMMS-024 Done. Frontend & UX accountable; existing-contract Fast UI lane.
Earlier pending notes above are historical and superseded by this release record.
