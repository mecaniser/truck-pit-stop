# DB-147: Machined staff sidebar release evidence

Owner: Frontend & UX. Fast UI lane. User selected Machined and requested Atelier's slim trailing copper current-page indicator.

## Scope and acceptance

Expanded and compact staff navigation uses raised metal-like icon keys, 22px glyphs and distinct copper, sky, lavender and sand category colors. The selected row is recessed and carries one 3px by 18px copper marker. Category identity remains visible while selected. Messages keeps its existing independent unread badge. Search and Messages utility glyphs are 20px.

The style is explicitly scoped to the existing new staff presentation using `data-nav-style="machined"`. Legacy and platform navigation retain their original markup/style path; no route order, authorization, API, tenant boundary, persisted appearance setting, migration, dependency or provider contract changes.

Hover is a pointer-only 1px lift and 3-degree tilt. Press feedback scales to .96. Reduced motion disables glyph movement and its transition; high contrast and forced colors have opaque system-compatible glyphs and current-page boundaries. Native accessible route labels and `aria-current="page"` remain the navigation contract.

## Local runtime receipt

2026-10-30, approximately 16:39 America/New_York (20:39 UTC).

- Worktree: `/Users/sergio_m1_promax/.codex/worktrees/machined-sidebar/truck-pit-stop`.
- Branch: `codex/machined-sidebar`; base HEAD `18255c03dac148a3326ca95d334cda03365139a6`. UI changes are uncommitted.
- Original checkout's unrelated dirty board and untracked work were preserved. This work uses a separate branch/worktree.
- Frontend: `http://127.0.0.1:5173`; Vite PID 17535, verified frontend cwd in this worktree. Runtime branch and SHA were passed by the local controller.
- API: `http://127.0.0.1:8000`; `dieselbridge_api_dev`, container `24654a0ac3fb9a15e964bfa5a312ca3cf8dcb17e523f5eed037698132fa21c3a`. Verified `/app` source mount points at this worktree's backend.
- Existing local database: `truckpitstop_db146_c3`; repository and DB both at `192_vehicle_issues`. Original controller configuration pointed to an older schema; task-specific controller config selected this already-compatible fixture database. No migration, reseed or existing global-controller configuration change.
- Existing approved local environment and dependencies are referenced through local symlinks. No credential copy was created in the worktree.
- API readiness and the Vite readiness proxy both returned HTTP 200. Signed-in page requests use this local API and existing fictional owner/tenant records. The headed review browser received a local fixture session using the repository's existing UI-snapshot token-mint pattern. No authentication code or permission changes. The temporary intermediate session file was removed; the final review keeps its session in the temporary review-browser profile, without credentials embedded in code or evidence.
- No worker/scheduler was started. No customer, payment or provider write was performed. Payment readiness is not asserted.

Status: **aligned and browser-verified** at `/dashboard/customers`; user-facing headed Chromium preview remains open in expanded mode.

## Verification

- Existing focused DashboardLayout suite: **13/13 pass**, covering current-page routing, compact persistence, permissions, legacy behavior and independent unread messaging affordance.
- Exact changed-source ESLint: pass. Production TypeScript/Vite build: pass. `git diff --check`: pass.
- Signed-in runtime batch: 1440x900 expanded, 1440x900 collapsed, 960x900 automatic compact, 390x844 and 320x844 mobile.
- Each desktop route target measured 54px high; glyphs measured 22px. Four distinct category colors. Exactly one visible current-page marker on Customers. No document overflow in tested widths. Existing mobile navigation owns smaller viewports.
- Expanded/collapsed controls work and desktop preference survives the compact breakpoint. Search opens and dismisses with Escape. Keyboard navigation has a visible solid focus outline with 2px offset.
- Reduced-motion computed glyph transition is `0s` and transform is `none`. Forced-colors screenshot captured. No JavaScript page errors.
- First search harness assertion used the zero-size fixed-position dialog wrapper; corrected assertion checks the visible dialog panel. No product defect was inferred from that harness mismatch.
- Runtime gate then found a real reduced-motion specificity conflict (`.16s` transition survived). The owner corrected selector specificity, strengthened high-contrast/forced-colors overrides, and reran the batch successfully.
- Impeccable detector: no findings in DashboardLayout. Full stylesheet scan reports seven existing gray-on-color warnings in unchanged Price Builder rules, outside this diff; no new sidebar findings. Existing warnings were preserved rather than broadening scope.

Evidence directory: `/Users/sergio_m1_promax/.codex/visualizations/2026/10/30/01a18e7d-68d0-7420-a357-f190993f8409/`.

Files: `sidebar-runtime-checks.json`, `sidebar-tests.log`, `sidebar-build.log`, `sidebar-expanded.png`, `sidebar-collapsed.png`, `sidebar-forced-colors.png`, `sidebar-mobile-390.png`, `sidebar-mobile-320.png`, `rail-expanded.png`, `rail-collapsed.png`. `local-review.mjs` is the local-only review harness; it retains no literal credentials.

## Delivery state

Initial local-review state is superseded by the authorized merge and production acceptance below. DB-147 is now Done.

## In-app browser access correction

The initial link opened an in-app browser without the separately tested Chromium fixture session, so the user encountered an unregistered-credentials/login dead end. Corrected by creating one dedicated `sidebar-preview@example.com` demo owner in the existing fictional `C3 Fictional Shop 1` tenant of `truckpitstop_db146_c3`. The setup asserted the exact local database and fictional tenant before inserting. No existing account/password or production data was changed; no application authentication code was altered. The password is not recorded here.

Signed in through the ordinary Email/Password form in the user's actual in-app tab 3, unchecked Remember me, opened Customers, expanded the rail, and reloaded. Selected-tab inspection confirms the visible tab remains at `http://127.0.0.1:5173/dashboard/customers` with the Sidebar Preview account and Machined rail. The tab is retained as the deliverable. Local preview verification now includes the actual browser handoff and normal login, not just a separate automation browser.

## Shipping gate (2026-10-30)

Product accepted the local UI and authorized delivery. Candidate incorporates `origin/main` `cdc61be8bb92cdf22c5652bba18a433120e02026`; the board-only merge conflict was resolved by preserving the complete current main board and prepending the DB-147 item. No unrelated work was overwritten.

Pre-landing code and design review: no unresolved issues. One mechanical refinement removes the new reduced-motion `!important` by matching hover/active specificity. No VERSION or CHANGELOG convention exists in this repository; release information stays in the delivery board, verification receipt and focused PR.

Post-integration focused DashboardLayout tests pass **13/13**; changed TSX ESLint, TypeScript/production build and diff integrity pass. The prior signed-in expanded/compact/mobile acceptance and actual in-app login handoff remain the runtime evidence for this unchanged presentation. Protected PR CI and deployment verification are the remaining release gates.

Protected CI run `41126201495` on candidate `f70ab13ccae2a888f8f63f0c5316e9230858f391` initially failed in the unchanged Motive fixture `pending slow provider navigation receives no second click` (`login.test.cjs:130`, 0 observed navigation requests versus 1 expected). This prevented frontend prerequisites from running. The file is identical to main, whose preceding PR701 passed the fixture. Requested one exact-head failed-jobs rerun; no application/provider code or workflow change. Merge remains held until required checks pass.

Attempt 2 passed all seven checks on `f70ab13c`. During CI, main advanced to `5b6f989d` (PR700). Integrated that approved release; only the delivery board conflicted. Preserved all current main records and moved DB-147's update to its own appended section to avoid competing with concurrent intake entries. Sidebar source remains unchanged. Fresh protected checks are required on the integrated candidate.

## Merge and deployment

Integrated candidate `4bcb6045adcf4b47f84bd826a9a12e4793cb5ff1` passed all seven protected/informational checks in run `41127457438`. Fresh focused tests remain **13/13**, ESLint and production build pass. PR702 normally squash-merged at 2026-10-30 21:05:24 UTC as `2b53a706e6665555d737a7554c1f3c47238b863d`. No admin bypass, protection change or direct main push.

Railway automatically started Web deployment `fdda4aa5-7446-4fa3-beb7-5d0459c6b380` from that exact merge SHA. Deployment and actual changed-route acceptance are pending. No manual worker or provider action is required for this frontend change.

## Production acceptance — DONE

Verified at 2026-10-30 21:11 UTC. Railway Web deployment `fdda4aa5-7446-4fa3-beb7-5d0459c6b380` is **SUCCESS**, with exact source `2b53a706e6665555d737a7554c1f3c47238b863d`. Public `https://www.dieselbridge.com/build-version` reports the same SHA and `built_at` `2026-10-30T21:07:58.160Z`.

The existing signed-in NC owner session opened `https://www.dieselbridge.com/dashboard` in the actual in-app browser and was reloaded after that public build match. The live shell reports `data-nav-style="machined"`.

- At 1280px, compact state measured four distinct category glyph colors: copper `rgb(255,172,119)`, sky `rgb(136,201,255)`, lavender `rgb(195,178,255)`, sand `rgb(223,200,160)`; each glyph is22px and each route target54px.
- Shop Work alone has `aria-current="page"` and copper marker opacity1; the other three markers have opacity0.
- Expanded state shows all four route labels with positive visible widths, exactly one current-page marker, and no document overflow. Compact state also has no document overflow.
- Browser error log is empty. A full production screenshot was captured in the review session; the cropped screenshot API temporarily renders at its requested width and was not used as acceptance evidence. Actual DOM and the full1280px capture confirm the desktop rail.
- Expanded and collapsed controls worked; the original collapsed preference was restored. Day appearance and all product records remain unchanged. No production account or credential was created; no customer, payment or provider mutation was tested.

The authenticated changed-route smoke, exact deployment and public build evidence complete the Fast UI release gate. Worker release verification and extended canaries are not required for this frontend-only change. Release records are being closed in a separate documentation-only PR; the delivered UI source is PR702's merge.
