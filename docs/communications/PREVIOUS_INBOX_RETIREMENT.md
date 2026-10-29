# DB-COMMS-026 — Retire previous inbox

Frontend & UX accountable; Fast UI lane. Removes the previous-inbox header and
empty-state links, their unused styling, and the standalone 888-line legacy page.
Old /dashboard/messages/previous bookmarks redirect to current Messages using
replace navigation and the existing shop messaging gate. Shared SMS APIs, models,
archives, customer records, messages and stored drafts are not deleted or changed.

47 focused shell/inbox tests pass, including authorized redirect, denied messaging
access, and absence of legacy links in populated/empty states. TypeScript,
changed-source ESLint and git diff checks pass. Signed-in local desktop/390x844
checks show the cleaned header; the old URL redirects to /dashboard/messages.
The existing synthetic inquiry draft remains intact; no provider sends.

October 29 runtime: codex/remove-previous-inbox at f178a287 plus scoped edits;
frontend5193 PID25019/backend8013 PID16781 cwd verified in callrail-inline-mms
worktree. Existing isolated communications_local_023_20261028 database and
Redis6386/db14 preserved; provider-deny guard and all three false SMS flags retained.
Proxied DB/Redis readiness passes; rendered branch and removed action verified.
http://127.0.0.1:5193/dashboard/messages is aligned and browser-verified.
Private synthetic screenshots /tmp/comms026-desktop.png and /tmp/comms026-mobile.png.

Independent of compact-control PR673; no application overlap in behavior.
Protected CI, merge and deployment pending. No production changes claimed.

## Latest-main integration

Integrated main81fac6dc (PR673). Only PROJECT_BOARD.md conflicted; retained both
DB-COMMS-025 and DB-COMMS-026 entries. Application files merged cleanly and the
PR delta against latest main remains only legacy-inbox retirement, preserving
compact controls and sender placement. All 47 focused shell/inbox tests and
TypeScript pass on the integration candidate; staged diff check passes.
