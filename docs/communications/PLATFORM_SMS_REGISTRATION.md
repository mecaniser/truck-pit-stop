# DB-COMMS-029 — Platform-managed registration

Owner: Backend & Integrations. Architecture contract approved before implementation. High-risk authorization lane; independent Security and QA required.

## Contract and acceptance

Super-admin Shops owns registration for an explicitly selected shop. GET/PUT `/admin/tenants/{tenant_id}/sms/onboarding`, POST `/review`, GET `/review-package` retain existing request/response/version semantics. Require active authenticated super_admin before tenant lookup; unknown/deleted target404, inactive non-deleted shop permitted for preparation. Actor tenant never chooses target. Legacy communications onboarding endpoints deny all authenticated roles403. Customer consent endpoints are unchanged.

Tenant Messages exposes channel status only, no registration requests. Existing shop-owned drafts retained; no migration, provider submit, binding change or activation. Body tenant/credential/status injection rejected; stale versions and locked records retain guards. Selected-shop form remounts by ID; unsaved close requires explicit discard. Late results cannot cross shops. Test all registration actions for tenant-role denial, A/B isolation, missing/deleted targets and provider-free operations. Preserve inbox draft, selected conversation and reply number, all SMS flags false.

## Runtime

2026-10-30: branch codex/platform-sms-registration, base18255c03, isolated API8013 and Vite5193 restarted from this worktree. Direct/proxied DB+Redis readiness and signed-in Messages verified. Existing communications_local_023_20261028 database and Redis14 preserved, no migration/reseed; approved synthetic-only config and external HTTP deny guard retained.

## Release

Implementation and independent Security/automated QA passed; protected CI, merge and deployment completed below; authenticated live super-admin acceptance completed. No production configuration changes. Rollback must not restore tenant registration access: if UI fails, retain backend denial and disable new admin entry until corrected. No automated rollout or provider actions authorized by this change.

## Verification — 2026-10-30

Architecture: registration_contract; backend implementation: platform_registration_backend; frontend implementation/runtime: parent; independent gate: platform_registration_gate (no implementation participation). Independent Security and automated QA GO: 64 endpoint/persistence cases and36 frontend cases passed. Owner additionally ran18 existing onboarding cases against isolated PostgreSQL. TypeScript and communications/new-dialog ESLint pass. Full GaragesPage lint reports4 existing no-explicit-any errors and1 existing hook warning, reproduced unchanged against base; no new lint issue added. Existing normalization/review coverage retained.

Signed-in tenant owner: Settings shows channel status without registration; opening/closing retained synthetic draft, selected conversation and exact reply number. Draft cleared after check. Signed-in tenantless super-admin: Shops opens registration for explicit selected shop; actual API returns draft. Unsaved edit requires Keep editing or Discard changes; keeping retains edit and discarding closes/restores focus. Opening second shop shows second shop identity and clean fields. Desktop and390px layout accepted, dialog width390/no horizontal overflow; viewport restored. Screenshots are synthetic/private `/tmp/comms029-tenant.png`, `/tmp/comms029-platform-desktop.png`, `/tmp/comms029-platform-mobile.png`. No browser form saved or provider action performed.

Runtime rechecked after backend change: API PID14173/Vite PID11715, same worktree/branch, direct and proxied readiness healthy. Existing isolated database retained; new synthetic tenantless super-admin fixture added without changing existing users. No real keys or provider calls; three SMS flags remain false in guarded launcher. Production was not modified.

## Release — 2026-10-30

PR700 integrated latest-main documentation while preserving both board histories; application tree remained unchanged from independent GO. All seven checks passed in41125877709 on exact head `fbe49be5aeee49f1d0e1a1ef1497fcc64bbff7d3`. Normal merge `5b6f989d326dd1ec3326d8bd6f14cf3af048dd43` at20:54:32UTC; checked and merged trees both `45e336624baeddda03a4b6018d168e95b27f534f`.

Automatic Railway Web `2bd014f9-9e0c-4f7f-b232-cf110720ff4b` and Worker `1821056d-1c35-4dd4-b9c9-4bddacc52a7f` both SUCCESS exact merge. Public build-version matches; database and Redis ready. All three effective SMS flags false/unset on both services. No duplicate deployment requested or provider action performed.

Authenticated live tenant inbox: Settings shows channel status only, no registration controls. Legacy onboarding GET returns platform_registration_required; explicit admin onboarding GET rejects tenant session with Super admin access required. Selected conversation, existing empty draft and exact sender retained across refresh/settings roundtrip. Private screenshot `/tmp/comms029-live-tenant.png`. Customer content and identifiers excluded from this receipt.

Final live acceptance: authenticated Platform Admin opened Shops, then Repair texting registration for the selected shop. The draft loaded with the correct shop identity, business/customer-permission/sample-message sections, and preparation-only notice explicitly stating no Twilio submission or automatic messages. Closed without edits, save, review, export, number changes or provider actions. Private screenshot `/tmp/comms029-live-platform.png`. Tenant Messages exclusion and draft/reply-route preservation were verified above. DB-COMMS-029 is Done; rollback retains backend tenant denial.
