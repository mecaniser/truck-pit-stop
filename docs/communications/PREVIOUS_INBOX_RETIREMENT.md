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
Protected CI and merge complete; production acceptance recorded below.

## Latest-main integration

Integrated main81fac6dc (PR673). Only PROJECT_BOARD.md conflicted; retained both
DB-COMMS-025 and DB-COMMS-026 entries. Application files merged cleanly and the
PR delta against latest main remains only legacy-inbox retirement, preserving
compact controls and sender placement. All 47 focused shell/inbox tests and
TypeScript pass on the integration candidate; staged diff check passes.

## Production release

PR674 merged as e74efc5f3d456bc1af624e5def46c6ecf5326f1f after all six
protected checks plus dependency preparation passed on exact head
2102f526e7ae5cef339c8f9cb17d02b53841a57c (run40949013207). This includes
latest main PR675; checked and merged trees both
6b56b9c2aab60bb005ffd3d2abfb61b8c4ec3287. Connected GitHub deployment
91ea43b0-9d68-4a85-b075-5158915cac94 started automatically and succeeded. The production build-version endpoint serves
exact e74efc5f (built 2026-10-29T20:35:17.709Z); DB and Redis readiness pass.
All three SMS flags remain unset/default false on both Web and Worker.
After the user signed in again, production browser acceptance passed:
Previous inbox is absent and /dashboard/messages/previous redirects to
/dashboard/messages. The selected conversation, empty draft, and derived
receiving-number reply route remained unchanged across navigation. All three
SMS flags were freshly verified false on both services. No messages sent,
settings changed, or drafts edited. Private screenshot: /tmp/comms026-live-verified.png.
DB-COMMS-026 is Done.
