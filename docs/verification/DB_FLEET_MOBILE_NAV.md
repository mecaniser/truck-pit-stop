# DB-FLEET-MOBILE-NAV

Owner: Frontend & UX. Fast UI. Branch: `codex/fleet-mobile-navigation`. [Draft PR824](https://github.com/mecaniser/truck-pit-stop/pull/824).

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
