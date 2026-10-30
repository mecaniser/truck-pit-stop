# DB-COMMS-028 — Messages settings center

Owner: Frontend & UX. Fast UI; existing API and permission contracts only.

## Acceptance

One Settings entry combines Channels and role-restricted SMS setup. Registration edits survive section switches; inbox remains mounted. Preserve drafts, reply identity, provider holds and all automation flags. No provider submissions or messages.

## Local verification — 2026-10-30

Original stopped communications Postgres/Redis containers restarted with preserved volumes. Dedicated synthetic database `communications_local_023_20261028`, schema `190_messages_contact_context`, Redis database14; no reset, seed or migration. Approved isolated configuration referenced in memory; no production secrets copied. API8013 PID81140 and frontend5193 PID80715 both serve the callrail-inline-mms worktree, branch codex/messages-settings-center (base903db866 plus reviewed overlay fix). API/proxy database and Redis readiness pass. All three SMS flags false; external HTTP and Twilio network denied.

Authenticated synthetic owner sees channel status and full registration form. Unsaved synthetic field persisted across section switches and was cleared without saving. Inbox draft and reply sender retained after closing settings; synthetic test draft cleared afterward. Desktop and390px browser accepted. Compact integration found app chrome covering the dialog header; settings-specific z-index corrected and reverified. Private screenshots `/tmp/comms028-local-desktop.png` and `/tmp/comms028-local-mobile.png`.

42 focused component tests, changed-source ESLint and TypeScript pass. No backend/application contract changes. Release gates were subsequently completed as recorded below.

## Clarity refinement

User clarified that consolidation must explain why registration exists and what staff should do. The Repair texting section names its purpose, preparation-only boundary, next action and remaining required items. Business details, customer permission evidence and sample messages have separate concise guidance. Field requirements replace the raw blocker wall; provider details remain available in an accessible disclosure. Configured number is explicitly distinct from repair-texting approval. All server actions, permissions and submission holds remain unchanged. 43 focused tests pass, including the legacy-number/no-approval case; TypeScript/lint pass. Signed-in desktop/compact visual checks cover the revised guidance.

## Release and live acceptance — 2026-10-30

PR695 merged as `48058a8fcd165f0e6fec9e529c91c84fa1ad38bd` after all six protected checks and dependency preparation passed on exact head `d22aeaa60a57b16d34d3ed365f9f1a418a850610`, run41118349553. Checked and merged trees both `1f8e9f9f9c2a78e1692a1c60e99dd016988b119d`. Latest-main integrations retained the activity cap and repair-history export changes; no checks bypassed.

Automatic Railway Web deployment `4d0fe448-3bf6-467f-89d5-54b05b329113` reached SUCCESS. Public build-version reports the exact merge SHA, build time `2026-10-30T19:57:50.692Z`; production readiness confirms database and Redis healthy. No duplicate deployment requested. All effective SMS_TENANT_ROUTING_ENABLED, SMS_AUTOMATION_OUTBOX_ENABLED and SMS_RECOVERY_ENABLED flags remain false/unset on both Web and Worker.

Authenticated live inbox shows one Settings entry. Channels describes the existing conversation reply number; Repair texting presents purpose, preparation-only notice, next action, required-item count and grouped fields. Closing settings preserves the selected conversation, existing empty draft and exact sending number. No form saved, registration submitted, consent changed or message sent. Private live screenshot: `/tmp/comms028-live-settings.png`. Production customer details are excluded from this receipt. Local tests and desktop/compact acceptance are separate evidence from this live verification.
