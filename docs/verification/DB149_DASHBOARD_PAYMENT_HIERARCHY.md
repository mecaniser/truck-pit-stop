# DB-149 dashboard payment hierarchy

Owner Frontend & UX; Fast UI lane, existing API/auth/payment contracts unchanged. Branch codex/customer-dashboard-payment-hierarchy stacked on PR756 at a076e428.

Acceptance: one informational balance summary, one Pay link per invoice, no invoice entries in Action required, multi-selection only with more than one current invoice. Authorization review alerts remain; current/overdue indicators truthful; historical invoices excluded as before.

Verification:11 focused dashboard tests passed (single/multiple invoice, historical exclusion, tenant alias, cash paid amount, allowed/denied/latest authorization cases). Production build passed; changed-source lint passed across2 files. Actual component preview using synthetic data inspected at1440px and390px, no horizontal overflow. Multiple invoice selection/deselection and selected destination verified in browser; no payment link submitted. Inspected desktop/mobile captures in local output/.

Runtime receipt 2026-11-02: intended tree/private/tmp/db149-dashboard-hierarchy, branch above, basea076e428 plus owned edits. Frontend5173 PID37620 serves this checkout, fixture-only API mocks and proxy127.0.0.1:9; no backend config copied. Prior owned frontend20178 gracefully stopped after cwd/PID check; unrelated Docker8000 preserved. Frontend fixture aligned and browser-verified; no authenticated full-stack local acceptance claim. Preview http://127.0.0.1:5173/invoice-preview.html?surface=dashboard.

User approved both previews and explicitly authorized merge/deployment with PR756 on2026-11-02. PR756 merged60b0be8d; dashboard rebased without source conflicts. Dashboard protected CI and combined deployment/live acceptance pending. No financial writes performed.
