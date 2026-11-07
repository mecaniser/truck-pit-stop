# DB-FLEET-MOBILE-NAV

Current status: **Done — released and signed-in production verified (2026-11-07)**.

Owner: Frontend & UX. Fast UI. Branch: `codex/fleet-mobile-navigation`. [PR824](https://github.com/mecaniser/truck-pit-stop/pull/824).

## Outcome and acceptance

The current revision uses a familiar labeled bottom bar at680px and narrower, and in short landscape viewports up to960px wide. Board/Map/Trips are primary fleet destinations; secondary account controls and the authorized Shop/Settings return are grouped under Profile. The fleet canvas takes full screen width; Profile opens above the bar. Desktop expansion preference is preserved and does not create a phone drawer/overlay. Add accessible destination labels/current-page state. No API, role/tenant permissions, data, migrations or dependency changes.

## Historical top-bar verification — 2026-11-06 (superseded design)

- 9 focused FleetApp shell tests pass, including navigation/current destination, detail/map/trip return context, manager permission exclusions, profile menu Escape/focus return and outside dismissal with an expanded preference.
- Signed-in production **candidate stylesheet preview only**: actual source CSS loaded as a temporary browser-local stylesheet. At320/375/390/430px the main surface matches screen width with zero horizontal overflow. At320px destination targets are61×48px and profile44×44px. The menu stays within the viewport and Escape returns focus to its trigger.
- At1307px collapsed/expanded rails remain74/172px. With desktop expansion remembered,320px renders the same56px top row, no overlay shadow and full-width main; phone expand control is hidden. Profile dropdown remains within screen bounds.
- Browser-local stylesheet removed after verification. Desktop expansion preference and viewport restored. No records, account data, integrations or settings saved. Production still runs the released side-rail version until this PR is merged/deployed.
- Private screenshot retained locally only: `frontend/output/playwright/fleet-map-phone/mobile-navigation-preview390.png`. Preview files excluded from Git.

## Local runtime receipt

Intended checkout `truck-fleet-map-phone`, branch above, base `b8a97499`. Mandatory runtime alignment attempted after branch switch: controller refuses pre-existing untracked preview output; approved `backend/.env` also absent. Existing8000 sandbox was not altered or used as an aligned backend;5173 unbound. Existing synthetic preview5193 is not claimed as this feature's full-stack acceptance. **Local full-stack runtime blocked**; signed-in presentation evidence above is a temporary browser-local CSS preview on production, not a deployed source change.

Standalone ESLint reports four existing no-explicit-any errors and one existing hook warning in FleetApp; use the repository baseline-aware changed-source lint gate to establish no new violations. Baseline-aware changed-source lint passes with no new violations across2 files. Shared-controls check, TypeScript and production build pass (existing large-chunk advisory). Protected CI/release status recorded on the board. Not Done until deployment and final signed-in acceptance.


## Jakob/Hick revision and local review — 2026-11-06

Design interpretation: Jakob’s Law supports familiar navigation conventions; use stable bottom destinations with icons and readable labels, current-page feedback and a conventional Profile menu. Hick’s Law informs grouping of decisions: the three fleet tasks stay visible, while Shop return/Settings/Integrations are grouped with account actions under Profile. This is a design application, not a measured claim of reduced task time. References: [NN/g Jakob](https://www.nngroup.com/videos/jakobs-law-internet-ux/) and [NN/g Hick](https://www.nngroup.com/videos/hicks-law-long-menus/).

User requests local review before any deployment. No merge/deployment performed.

- Interactive local UI preview: loopback5194, `/output/fleet-mobile-review/index.html`. Vite PID46051 command/cwd verified against this worktree’s frontend; HTTP200. Actual FleetApp source and styles served from `codex/fleet-mobile-navigation`; sample owner/fleet data and mock map projection are isolated to excluded local preview files. All write methods reject and provider fetches are intercepted. No production API/proxy, backend, tokens or records used.
- Full-stack runtime remains **blocked** as described above. This preview is **browser-verified sample-data UI**, not an aligned backend or live-map acceptance claim. Preview remains open at390×844 for user review.
- Local browser at320/375/390/430px and844×390: full-width main, bottom bar, no horizontal overflow. At320px all four destinations are73×48px. At1307×900 the original74px desktop rail and Shop return remain.
- Board/Map/Trips switching and current-page states work. Profile exposes Settings/Integrations/Shop dashboard/Log out for the sample owner; menu fits320px, Escape closes and returns focus. Read-only sample preview reports zero browser console errors.
- 10 focused tests pass, including owner Shop return through Profile, manager exclusions, destination state, detail return and profile dismissal/focus. Shared-control check, TypeScript and production build pass; existing large-chunk advisory unchanged. Baseline-aware changed-source lint remains the scoped gate for pre-existing FleetApp lint findings.
- iPhone safe-area padding included. Physical-device hardware acceptance is not claimed. Local screenshot `frontend/output/fleet-mobile-review/local-bottom-navigation390.png`; preview/config/fixtures/screenshots excluded from Git.


## Single-scroll refinement — 2026-11-06

User requests local review before deployment. The phone truck panel now grows to its full content height; remove its480px height, max-height cap, internal overflow and overscroll containment. Fleet shell `.scroll` is the sole vertical scroller for map/search/list. Apply the compact map layout to the same short-landscape breakpoint as bottom navigation. Desktop panel styles remain unchanged.

Local browser evidence on actual source/sample preview5194 (PID46051, command/cwd rechecked at the intended frontend checkout; HTTP200):

- 320/375/390/430px portrait and844×390 landscape each expose exactly one overflowing auto/scroll element: shell `.scroll`. Panel height599px accommodates all12 sample rows, inner list scrollTop stays0, and no horizontal overflow occurs.
- Native scroll over the list moves shell scrollTop0→586; final unit611 becomes visible. Header top stays0 and bottom nav remains at viewport bottom844. Unit611 remains selectable and selects its matching pin; Profile opens within the screen and Escape dismisses it.
- At1307×900, comparison panel retains `overflow-y:auto` and720px panel sizing. The short sample list fits; desktop internal scrolling style is preserved for longer lists.
- Zero browser console errors. Local screenshot: `frontend/output/fleet-mobile-review/single-scroll390.png`. Preview remains open at390px for user inspection. No synthetic preview files or screenshot committed.
- 16 existing focused FleetProximity tests and Vite production build pass; no new JS/API behavior. No CSS-mirroring unit test added; browser interaction/scroll-container checks establish this layout behavior.

This is browser-verified local sample-data UI only. Existing full-stack runtime blocker is unchanged; no backend alignment, production change, merge or deployment claimed.


## Release and production acceptance — 2026-11-07

User approved the local preview and explicitly authorized finishing verification, merging/deploying and checking production. Strict main protection required integrating the separate PR825/main change; fleet files remained identical to user-reviewed323f3fd1. All seven checks passed on6332354a1e49d1e2dba0782beca99f5ae03cdd98 in run42342694819. Focused local evidence remains10 FleetApp tests plus16 FleetProximity tests, scoped lint and production builds; protected CI provides the final integration gate.

PR824 squash-merged at2026-11-07T05:33:29Z as `cfd6723675a9a348f3ea6b056b61b9d8340c41e9`. Railway auto-deployment `5b51d83f-87da-4296-a8c8-0a9477e73dee` succeeded on that exact commit. Public www/API build stamps match; readiness reports healthy database/Redis. Six-file scope: fleet shell/CSS/tests and delivery documentation only; no preview fixture/config, API, auth/tenant contract, migration or dependency changes.

Reloaded the signed-in production `/fleet` on the deployed source (no browser stylesheet overrides):

- 320/375/390/430px portrait and844×390 landscape: main uses full viewport width,56px bottom navigation, no horizontal overflow, exactly one overflowing vertical auto/scroll element (`.scroll`); truck panel overflow remains visible. At320px all four navigation targets measure73×48px.
- Real25-unit overview: native scrolling over the list moves shell scrollTop0→844 while list scrollTop remains0. Header stays at top0 and navigation bottom at844. Final unit532 is reachable/selectable and shows no-coordinate fallback; located609 selects its matching pin.
- Fleet Board/Trips/Map navigation updates both destination content/title and current-page state. Profile exposes Settings/Integrations/contextual Return to Profile Settings/Log out. Menu fits320px and390px; Escape dismisses and returns focus to trigger.
- 1307×900 desktop retains74px collapsed and172px expanded rail plus independent `proximity-panel-content` scrolling for the real long list. Desktop-only/mobile-only controls remain correctly hidden. An expanded desktop preference still produces full-width320px content and56px bottom bar without overlay shadow.
- Zero new console errors during verification. Cleared selection/menu and restored original desktop expansion preference and viewport. No fleet/customer records, account settings, integrations or financial state changed.

Screenshot retained only locally: `frontend/output/fleet-mobile-review/production-mobile-nav390.png`; excluded from Git. Browser responsive testing, not physical-iPhone hardware acceptance. The historical full local-backend alignment limitation above is not a remaining production acceptance blocker.

Product item **Done — released**, Frontend & UX accountable. No required product follow-up hidden in this receipt.
