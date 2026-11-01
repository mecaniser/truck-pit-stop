# DB-139 identity repair and billing indicator

2026-11-01: Backend & Integrations accountable. User authorizes source-proven correction of conflicting vehicle links, no invoice/balance duplication; frontend footer hides redundant unknown status/remaining and exposes severity via accessible indicator/details.

Runtime: codex/ets-identity-status base4645ea6a; frontend5202 PID71774 cwd this checkout/frontend; dedicated API18021 container mounts this checkout/backend. Preserved approved root .env, isolated fictional postgres/truckpitstop_db139_shared and Redis11; direct/proxy readiness200. Actual signed-in browser shows branch4645ea6 and selected unknown billing fixture. Aligned and browser-verified before edits; final changed-feature checks pending. No migrations, worker, provider or production financial mutation.

## UI verification

166 focused frontend tests, TypeScript and changed-source ESLint pass. Independent QA reproduced88 tests and approved status severity/unknown handling. Actual signed-in Day desktop and390px mobile: unknown footer shows one Unavailable plus warning icon; opened explanation identifies identity conflict; healthy paid shows green check/Payment verified and zero remaining; partial amount remains visible. Night warning icon, heading and ledger contrast inspected; ledger no longer duplicates Payment unverified/Remaining Unavailable. Keyboard Escape dismisses; mobile popovers stay within viewport. Fictional account appearance restored to Day and viewport reset. No production UI changes yet.

## Source and repair plan

Architecture and independent Security/QA confirm preserved vehicle-scoped Aug24 ETS capture proves original historical service association. The owner legacy vehicle lacked ETS ID; three siblings already use source vehicle106566. Correct owner-only; no vehicle merge or invoice reassignment. Source/proof hashes and operational guards are recorded in [contract](../contracts/db139-ets-0662-identity-repair.md).21 operational guard tests independently pass. Read-only production plan passed; final apply pending rehearsal/independent gate.
