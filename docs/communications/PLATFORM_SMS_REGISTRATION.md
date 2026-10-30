# DB-COMMS-029 — Platform-managed registration

Owner: Backend & Integrations. Architecture contract approved before implementation. High-risk authorization lane; independent Security and QA required.

## Contract and acceptance

Super-admin Shops owns registration for an explicitly selected shop. GET/PUT `/admin/tenants/{tenant_id}/sms/onboarding`, POST `/review`, GET `/review-package` retain existing request/response/version semantics. Require active authenticated super_admin before tenant lookup; unknown/deleted target404, inactive non-deleted shop permitted for preparation. Actor tenant never chooses target. Legacy communications onboarding endpoints deny all authenticated roles403. Customer consent endpoints are unchanged.

Tenant Messages exposes channel status only, no registration requests. Existing shop-owned drafts retained; no migration, provider submit, binding change or activation. Body tenant/credential/status injection rejected; stale versions and locked records retain guards. Selected-shop form remounts by ID; unsaved close requires explicit discard. Late results cannot cross shops. Test all registration actions for tenant-role denial, A/B isolation, missing/deleted targets and provider-free operations. Preserve inbox draft, selected conversation and reply number, all SMS flags false.

## Runtime

2026-10-30: branch codex/platform-sms-registration, base18255c03, isolated API8013 and Vite5193 restarted from this worktree. Direct/proxied DB+Redis readiness and signed-in Messages verified. Existing communications_local_023_20261028 database and Redis14 preserved, no migration/reseed; approved synthetic-only config and external HTTP deny guard retained.

## Release

Implementation and independent Security/automated QA passed; protected CI, merge and live deployment remain pending. No production configuration changes. Rollback must not restore tenant registration access: if UI fails, retain backend denial and disable new admin entry until corrected. No automated rollout or provider actions authorized by this change.

## Verification — 2026-10-30

Architecture: registration_contract; backend implementation: platform_registration_backend; frontend implementation/runtime: parent; independent gate: platform_registration_gate (no implementation participation). Independent Security and automated QA GO: 64 endpoint/persistence cases and36 frontend cases passed. Owner additionally ran18 existing onboarding cases against isolated PostgreSQL. TypeScript and changed-source ESLint pass. Existing normalization/review coverage retained.

Signed-in tenant owner: Settings shows channel status without registration; opening/closing retained synthetic draft, selected conversation and exact reply number. Draft cleared after check. Signed-in tenantless super-admin: Shops opens registration for explicit selected shop; actual API returns draft. Unsaved edit requires Keep editing or Discard changes; keeping retains edit and discarding closes/restores focus. Opening second shop shows second shop identity and clean fields. Desktop and390px layout accepted, dialog width390/no horizontal overflow; viewport restored. Screenshots are synthetic/private `/tmp/comms029-tenant.png`, `/tmp/comms029-platform-desktop.png`, `/tmp/comms029-platform-mobile.png`. No browser form saved or provider action performed.

Runtime rechecked after backend change: API PID14173/Vite PID11715, same worktree/branch, direct and proxied readiness healthy. Existing isolated database retained; new synthetic tenantless super-admin fixture added without changing existing users. No real keys or provider calls; three SMS flags remain false in guarded launcher. Production was not modified.
