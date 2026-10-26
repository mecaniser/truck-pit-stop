# DB-036 fuel lifecycle diagnostics

Backend & Integrations owns this focused high-risk change, codex/motive-fuel-lifecycle from450c8362. Parent approved the contract; independent diagnostic_gate required. No production actions.

Fuel execution b106a9d2 ended after23seconds with login_email as its last phase and no Node or Python failure classification. Inherited image metadata references087a284e but exact deployed bytes were unavailable. Railway exposes no exit/signal/OOM evidence; sampled0.569GB/8GB is not sampled pressure and does not exclude a brief spike or external termination. Root cause remains unknown.

Acceptance before implementation: fuel alone opts into fixed lifecycle stages and bounded exit/signal/elapsed metadata. Emit child outcome before cleanup, and SIGTERM/SIGINT shutdown request before existing descendant cleanup. Distinguish new import started from recovery and retain unknown import outcome after errors. Never output raw exception, command, environment, file paths, PIDs, credentials or provider values. Other workers retain default behavior. No changes to authentication, selectors, retry counts, timeouts, schedules, receipt recovery or import decisions. SIGKILL of the supervisor cannot emit diagnostics; never infer OOM from absent logs.

Tests: real child exit17, signal, timeout and process cleanup; parent SIGTERM/SIGINT event-before-cleanup; redaction; recovery failure blocks collection, collection failure blocks import, importer error stays ambiguous without retry. Independent security/QA and exact-head CI precede any release.

Local runtime: no5173/8000 listeners; mandatory controller dry-run blocked by missing backend/.env and Vite. No secrets copied or local browser claim.

Separate reliability follow-up: fuel dates() recalculates the most recent three dates (configurable1–7), ending yesterday at/after12UTC and the day before yesterday earlier. It has no durable per-day missing-date ledger. Thirty-minute read checkpoints and pending receipt recovery do not enqueue gaps older than that moving window. A prolonged outage can therefore leave older fuel dates uncollected. Durable fuel catchup is a separate outcome; this PR only improves observability and does not claim recovery completion.

Owner checks:62 Python tests passed across fuel lifecycle/importer, recovery and existing trip/driver/health process boundaries; changed-file Ruff, Python compile and diff checks passed. Real signal fixtures retain the existing macOS possibility of duplicate cleanup EPERM after the child has terminated; the new flushed shutdown event still identifies the signal. Cleanup behavior was not changed. Independent QA/security GO: the reviewer ran the same62 tests successfully and verified opt-in defaults, privacy, signal/child event ordering and unchanged import/retry semantics. PR/CI and runtime acceptance remain pending.
