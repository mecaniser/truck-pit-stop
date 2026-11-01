# DB-153 UI failure recovery — 2026-11-01

Owner: Frontend & UX. Branch: `codex/ui-state-recovery`, base `5d5a0a136589cd83cb5f1929ddb44e4f44c3018a`.

## Scope and contract

- Preserve the customer recovery already on main; fix remaining inventory, supplier, technician and technician-work read failures. Pending offline queries must not appear empty. Retry controls repeat reads only.
- Shared browser offline notice and API-request notice after eight seconds; completion/failure/cancellation clears tracking. No new mutation replay, queue, or retry policy.
- Typed opt-in customer create/edit and repair-order intake drafts. Capture synchronously before session identity is cleared. Versioned sessionStorage, 100KB maximum envelope, two-hour TTL; key by form kind and validate exact tenant/user/role/customer identity. Restore requires server `/auth/me` validation plus current identity and TTL checks at application time. No credentials, card data, pricing confirmations, customer approval thresholds or fleet permission settings are saved. New records and current permissions/pricing remain authoritative.
- Explicit Restore/Discard. Submitted-but-unconfirmed drafts require acknowledgement that existing records were checked. Capture is suppressed after successful completion or cancellation. Explicit logout purges drafts. A new editor, identity change, or delayed old validation cannot resurrect/replace another form.
- Repair intake recovers editable fields and fresh customer/vehicle references. Service names are guidance only: operator reselects services and reviews current pricing. No automatic write or reuse of approval decisions.
- Coverage is these two form families, not every editor in the application. Storage denial/quota failure never prevents session termination and does not claim a draft was saved.
- No API, migration, auth-provider contract, production-data or payment changes.

Architecture: `recovery_contract` reviewed boundaries before draft implementation. Implementer: root. Independent Security: `recovery_security` GO after identity-binding, completed-draft suppression, TTL/restore-time checks and delayed-validation fixes. Independent QA: `recovery_qa` source/automated conditional GO; newer-editor and portal placement findings corrected.

## Verification

- Focused recovery/auth/API tests: 43/43 passed (7 suites).
- Independent adjacent customer workstation and repair-order customer tests: 68/68 passed on rerun; initial concurrent run had two transient failures, retained rather than claimed as an uninterrupted pass.
- Inventory deep-link and existing technician editing checks passed in the earlier focused run.
- TypeScript and production Vite build passed. Existing Browserslist age warning retained.
- Broad changed-file ESLint exposes existing baseline violations in inventory/suppliers/technicians. No unrelated lint cleanup; baseline-aware check recorded below.
- Synthetic Playwright actual CustomerFormModals: entered first-name and notes, invoked actual clearSession, unmounted as logout would, reestablished synthetic same-user identity through mocked `/auth/me`, and restored exact values without a write. Recovery notice is inside viewport at1440x1000 (y832–968). Mobile and final evidence recorded below. This validates actual components with synthetic data, not provider login or real backend authorization.
- Shared notices: offline detection/return online; delayed request appears after threshold; uncertain Restore disabled until acknowledgement;390px layout has no horizontal overflow. Only initial fixture favicon404 and expected React Router warnings, no application exception. Initial unstyled fixture launch was corrected to use the frontend working directory; only corrected rendering is acceptance evidence.

## Runtime and release limits

Startup skill preflight: new worktree lacks approved backend/.env. Default5173 belongs to my-shop-nav-stability;8000 mounts machined-sidebar. Neither service was stopped or changed. Isolated synthetic frontend5197 PID55262 serves this worktree/frontend, its own Vite cache, HTTP200. Proxy deliberately targets unused localhost18997; customer fixture intercepts every API call. No database or provider connected. Full-stack runtime remains BLOCKED, not aligned/browser-verified. Synthetic component rendering is verified separately. No merge/deployment or production writes. This item is not Done until required authenticated acceptance and release evidence exist.

Final local receipt: baseline-aware lint passes21 changed TypeScript files with no new violations. Actual customer portal restore also passes390x844: notice x32/y646/bottom812, viewport844, scrollWidth390. First name restored exactly; desktop first-name and notes restored exactly. A repeat expiry after restoration offers recovery again. Screenshots retained locally in `.playwright-cli/page-2026-11-01T21-22-21-278Z.png` (desktop) and `.playwright-cli/page-2026-11-01T21-23-59-272Z.png` (mobile). No customer writes were issued. Customer fixture had zero browser console errors and two existing router warnings. Final source committed asd9719e43; this note only adds verification evidence.

Independent QA subsequently reviewed actual desktop/mobile customer screenshots and restored-field snapshot: GO for source, automated and synthetic component runtime. PR748 remains draft. Current main d28882de integrated without conflicts; frontend source identity against reviewed dd09bc00 passes. Temporary fixture source/cache and its own5197 server were removed after verification. Existing shared services remain running. Full authenticated backend acceptance and release are still open.
