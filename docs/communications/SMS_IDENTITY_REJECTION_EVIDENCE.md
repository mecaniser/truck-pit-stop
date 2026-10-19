# Invalid-recipient rejection and conversation identity

2026-10-18. Owner: Backend & Integrations. State: Review.

Contract/acceptance: send_policy must ignore a historical address as identity evidence only when its SMS row is outbound, delivery_status failed, error_code exactly21211, and twilio_message_sid is SQL NULL. Twilio describes21211 as an invalid To number: https://www.twilio.com/docs/api/errors/21211 . Such a rejected request does not establish conversation identity. This does not authorize retrying the rejected row.

Every inbound, provider-SID-bearing row, pending/queued/sent/delivered/undelivered row, unknown/other error, and existing competing customer identity remains relevant and blocking when conflicting. Tenant/thread/deleted filters stay unchanged. Preserve all historical rows; no migration, payload rewrite, data correction, flag enablement, provider call or deployment in this implementation. Empty-string SID is conservatively retained as evidence.

Acceptance tests use synthetic in-memory SQLite rows: conclusive rejection allows canonical address; all negative boundaries remain blocked; foreign tenant/thread rows ignored; opt-out/competing customer/held operations still blocked; read policy leaves history unchanged. Independent Security/QA and protectedCI required before release. Parent coordinates production pilot.

Local-runtime preflight: intended clean branch codex/sms-invalid-recipient-identity at1cb16a7f. Port5173 belongs to nodePID71004, ets-checkpoint-merge frontend; preserved. No8000 listener and no approved configuration copied. Local app/browser alignment is blocked; no local preview claim. Focused tests run sealed isolated SQLite only.

Verification:90 passed across test_communications_identity_evidence.py (20 new SQL integration cases), test_sms_callback_reliability.py, test_automated_sms_guards.py, and test_live_sms_acceptance_guard.py. Executed with inherited environment removed, in-memory SQLite, Redis127.0.0.1:1/15 and empty Twilio credentials; no network/provider requests. Existing SQLAlchemy/Pydantic deprecation warnings only. Git diff whitespace check passed. Local app/browser acceptance remains unavailable; parent owns exact deployed preflight and authorized send/reply acceptance. No implementation self-approval of independent gates.
