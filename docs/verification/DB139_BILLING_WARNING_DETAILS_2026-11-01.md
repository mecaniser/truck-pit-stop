# DB-139 — explicit billing warning details and release correction

Frontend & UX accountable, Fast UI; existing read-only billing contract.

User acceptance: expanding a row with a warning triangle explains exactly why it
needs attention. Preserve all distinct reported reasons, payment/unknown holds,
normal Details behavior and desktop/mobile containment. Footer and row must use
the same explanation. No data, financial calculation or API changes.

PR740 merged8021b355 after7/7 checks on8c017110, run41345626701.
Railway deployment8bc21a4a-ce7f-4e71-913a-136e2de7bf84 failed at
`npm run lint:controls`: new tooltip used a native button. Production stayed on
ce756d23, healthy. This correction uses ControlButton with forwarded ref and icon
geometry; does not disable or bypass the build check.

The expanded brief now shows Billing needs attention and every distinct reason,
plus a supported positive unpaid balance or unavailable-data explanation. Unknown
source reasons receive an explicit human-readable fallback. A flagged invoice
without a reason says ETS did not provide one. Healthy invoices show no warning.
The footer uses the same list instead of silently selecting the first known code.

Local runtime re-aligned2026-11-01: same worktree, branch
codex/ets-billing-warning-details, base8021b355; frontend5203 PID8578, API8043
container backend bind to this worktree, DBtruckpitstop_db042_qa/Redis12,
migration196 current=head, proxied readiness ready. Other runtimes preserved.
Real ledger/footer component fixtures at /footer-qa.html: Details expands without
opening an order; all three expected reasons visible. At390px warning content
bounds x28..348, viewport390; no horizontal overflow. Temporary emulation cleared.
No production records changed; fictional fixtures used because local DB has no ETS
orders. Prior signed-in native-order regression and final production acceptance
are tracked separately in the footer release evidence.

176 focused tests pass across imported billing, ledger, PriceBuilderPanel and page.
Full npm build includes shared-control lint, TypeScript and Vite bundle; changed
source lint and final CI/release recorded with the PR. Screenshots kept locally
in output/ets-billing-warning-details (fictional data only).
