# Connected shared inbox — local verification

DB-COMMS-002; 2026-10-16, 15:40 America/New_York. Backend & Integrations accountable. Local simulated acceptance only; draft [PR562](https://github.com/mecaniser/truck-pit-stop/pull/562), stacked on560; no merge or deployment.

## Runtime receipt

Branch `codex/shared-inbox-backend`, implementation `aeea4a88`, independent final gate recorded at `952c4487`. Frontend PID56726 serves this worktree's `frontend/prototypes/communications/vite.config.ts`, `http://127.0.0.1:5186/`, `/api` proxy to8006. Backend PID82043 runs `uvicorn communications_local_app:app` from this worktree's `backend` directory. Explicit local harness overrides only SMS provider; normal application authentication and routers execute. PostgreSQL16 container `dieselbridge-comms-002-postgres`, localhost55460, database `communications_local`, migration `177_shared_inbox`; dedicated Redis6386. Readiness database/Redis both pass. Other tasks' servers and databases remain untouched.

The standard controller cannot launch the missing backend/.env; this task uses the explicitly authorized isolated harness documented in LOCAL_SETUP.md. No production data was copied. All contacts, staff, messages and provider events are synthetic. Environment secrets are generated, ignored and not included here. Simulation rejects nondevelopment environments and all actual Twilio HTTP calls.

## Automated and HTTP evidence

- 86 focused backend tests:10 PostgreSQL cases and76 messaging/callback regressions. Includes concurrency, durable pending recovery, dispatch rechecks, unknown/stale dispatch holds, deleted-record handling, normalized inbound identity matching and distinct-SID concurrent placeholder creation.
- 16 frontend tests, TypeScript, changed-source ESLint and standalone production build pass. Real Axios interceptor regression verifies signed-out login, cookie-only sessions and WorkOS renewal; persisted send intent reuses exact key/body after a failed response and reload.
- 4 local-harness safety tests pass, including actual production-environment import rejection.
- Fresh isolated migrations through176,177 upgrade/downgrade/upgrade preserve existing synthetic records. Downgrade refuses populated operations rather than destroying delivery evidence.
- `scripts/verify_communications_local.py` completed against authenticated HTTP APIs. Local machine receipt: `.impeccable/review/http-acceptance.json`. Final concurrency operation `fd502a6c-23a5-4781-a3a1-6c75db550cb9`: four simultaneous same-key requests produced one operation, one history row and exactly one durable simulated provider invocation. Changed payload409; replay no new invocation.
- HTTP checks: tenant-only list; foreign conversation detail/history/send/read/workflow/operation/assignee denied; foreign through-message ID denied; unauthorized mutations403; per-user read watermarks; assignment and stale-version conflict; opted-out send denied; invalid signature400; sent/delivered/duplicate/stale callbacks preserve delivered; duplicated inbound SID creates one reply and reopens resolved conversation with unread state.
- Initial HTTP run freshly exercised confirmed rejection and accepted-then-timeout unknown. Repeated run explicitly retained the existing Maria unknown fixture and checked the new-intent hold; it did not pretend to rerun a fresh timeout. Durable provider ledger remains external to app transactions and survives API restarts.

## Browser acceptance

Signed in at5186 with the seeded owner via ordinary login. Source is aligned and browser-verified. Held mobile send control measured top772/bottom803 within844px viewport after layout settled; refreshed held screenshot includes full composer.

- Persisted conversations load without fixture adapter; server supplies simulated-delivery banner and staff list.
- Daniel's SMS draft survives switching to WhatsApp, switching back, and a full page reload. WhatsApp send disabled. Assignment to Alex persists and updates Mine count. One simulated reply becomes queued, clears only submitted draft, then displays delivered after signed synthetic callback.
- Ava reply submitted from UI, survives reload. Resolve persists across reload in Resolved view. Signed inbound reply reopens it and appears on polling; signed delivery callback updates queued to delivered.
- Desktop1280x900 three-column view inspected. Mobile390x844 conversation/composer fit; document scrollWidth390 equals viewport390. Back-to-list navigation works. Unknown delivery detail visible on mobile with disabled send. Restored default viewport and left Ava open. No browser console errors at completion.
- Screenshots: `.impeccable/review/connected-desktop.png`, `connected-mobile.png`, `connected-mobile-held.png` (local ignored artifacts).

Independent backend/security and frontend test review is recorded in INDEPENDENT_BACKEND_REVIEW.md. Browser evidence review is appended there separately.

## Boundaries before deployment

Real SMS/carrier delivery remains an explicit pre-deployment test. Protected CI, merge, rollout and production migration are not claimed. New communications send operations are duplicate-safe within this contract; legacy manual/automated send paths have not been migrated. Existing SMS threads only; new-contact creation, WhatsApp/Telegram onboarding and repair context integration remain follow-on work. Empty repair context is shown honestly. Pending recovery is a bounded callable processor; production scheduling/operational reconciliation must be wired and approved before rollout. Never replay dispatching/unknown operations. Disable new entry points to roll back; retain operation history.
