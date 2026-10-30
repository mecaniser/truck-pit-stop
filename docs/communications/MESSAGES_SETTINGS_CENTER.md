# DB-COMMS-028 — Messages settings center

Owner: Frontend & UX. Fast UI; existing API and permission contracts only.

## Acceptance

One Settings entry combines Channels and role-restricted SMS setup. Registration edits survive section switches; inbox remains mounted. Preserve drafts, reply identity, provider holds and all automation flags. No provider submissions or messages.

## Local verification — 2026-10-30

Original stopped communications Postgres/Redis containers restarted with preserved volumes. Dedicated synthetic database `communications_local_023_20261028`, schema `190_messages_contact_context`, Redis database14; no reset, seed or migration. Approved isolated configuration referenced in memory; no production secrets copied. API8013 PID81140 and frontend5193 PID80715 both serve the callrail-inline-mms worktree, branch codex/messages-settings-center (base903db866 plus reviewed overlay fix). API/proxy database and Redis readiness pass. All three SMS flags false; external HTTP and Twilio network denied.

Authenticated synthetic owner sees channel status and full registration form. Unsaved synthetic field persisted across section switches and was cleared without saving. Inbox draft and reply sender retained after closing settings; synthetic test draft cleared afterward. Desktop and390px browser accepted. Compact integration found app chrome covering the dialog header; settings-specific z-index corrected and reverified. Private screenshots `/tmp/comms028-local-desktop.png` and `/tmp/comms028-local-mobile.png`.

42 focused component tests, changed-source ESLint and TypeScript pass. No backend/application contract changes. PR695 protected CI, merge, deployment and live acceptance are separate pending release gates.
