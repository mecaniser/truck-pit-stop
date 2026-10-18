# DB-036 recurring driver identity mismatch

Owner: Backend & Integrations. High-risk worker follow-up, branch `codex/driver-identity-reconcile`, base `363cedb11fa960765ca47fada44986117fc1b681`. Acceptance is defined in the delivery board.

## Source diagnosis

Oct18 scheduled driver run `1601cc6a-cc40-4edd-b228-c2e9f5459c98` crashed after633seconds on deployment `5b8d2779-c801-45db-95f3-875f315fe450`. Three diagnostics identify the same reviewed truck26 path, two before summary and one after summary. Public reason `vehicle_identity_changed` originates from rendered unit/breadcrumb validation in `summaryIdentity`; it is not sufficient evidence of a VIN change. Import was blocked, and the guard remains required. Current signed-in provider observation confirms the expected company, directory assignment, exact summary/Live routes, unit26 and model breadcrumb, with no displayed VIN. Three fresh headless pages using the exact deployed vehicle-identity module hash passed after normal empty startup snapshots; the repeated12-page headless sequence then reproduced the failure twice: complete profile and exact route, but a singleton empty breadcrumb node. The existing parser rejected that loading frame as a different unit. This is a rendered readiness race, not proof of a provider identity/VIN change. Private source evidence stays under output/identity-reconcile.

## Three-second location run

The cooperating Troubleshoot failing workers chat independently verified run `db4c4f86-0d34-4d17-9a5b-137b8ac08a91` was created20:00:10.440UTC and completed20:00:14.416UTC, EXITED. Preceding run `513e0303-205e-454c-9376-9ce153a0b2e9` completed after171seconds and recorded22/22 collection with4updates,12unchanged,3prior-time-unknown,3unavailable. The short run has no collection/import/receipt/worker-complete evidence. Existing mounted state contains preceding19:57 and following20:05 directories, and no20:00 run directory. Since run_worker creates a directory after acquiring the lock, this narrows the short run to a pre-directory/startup exit. Lock refusal is plausible but unproven; logs omit its reason. It must not be counted as a successful import or retried based on EXITED alone. No lock was acquired/released for diagnosis and no worker was triggered.

## Runtime alignment

Existing local5173 belongs to another checkout and was preserved;8000 is unbound and this worktree lacks approved backend config. Worker-only tests use isolated fixtures. Local fullstack browser serving is blocked; no local source visibility claim. Existing provider browser and bounded headless provider reads are read-only and separate from local fullstack acceptance.

## Focused repair and owner verification

Three source lines classify only a singleton blank breadcrumb as overview-not-ready. The existing60-read/250ms wait budget remains unchanged. A later fully matching breadcrumb is still mandatory before returning identity. Wrong or duplicate breadcrumbs, wrong unit/routes/Live links, VIN ambiguity and real-VIN transition safeguards remain fail-closed. No identity is inferred and no provider, binding, database, or allowlist value changes.

The two focused regressions failed on the previous source and pass with the correction. All79 driver/location Node tests pass; captured genuine DOM replay classifies both observed false mismatches as waiting, with no identity accepted from either frame. Guard tests include persistent whitespace blank timeout, blank→wrong/duplicate identity, wrong route/Live, ambiguous VIN and real-VIN transition. Independent Security/QA reviewer identity_guard_review returned GO: independently48 checked-in cases plus10 boundary challenges and replay of both actual source snapshots against old/candidate parser. No reviewer source edits or remote operations. Protected CI and production acceptance remain pending.
