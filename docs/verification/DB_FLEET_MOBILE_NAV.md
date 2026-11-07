# DB-FLEET-MOBILE-NAV

Owner: Frontend & UX. Fast UI. Branch: `codex/fleet-mobile-navigation`. [Draft PR824](https://github.com/mecaniser/truck-pit-stop/pull/824).

## Outcome and acceptance

At680px and narrower, the existing fleet rail becomes a single56px horizontal navigation bar. The same Board/Map/Trips, authorized Shop/Settings return and profile controls remain; the fleet canvas takes full screen width. Profile dropdown opens below the bar. Desktop expansion preference is preserved and does not create a phone drawer/overlay. Add accessible destination labels/current-page state. No API, role/tenant permissions, data, migrations or dependency changes.

## Verification — 2026-11-06

- 9 focused FleetApp shell tests pass, including navigation/current destination, detail/map/trip return context, manager permission exclusions, profile menu Escape/focus return and outside dismissal with an expanded preference.
- Signed-in production **candidate stylesheet preview only**: actual source CSS loaded as a temporary browser-local stylesheet. At320/375/390/430px the main surface matches screen width with zero horizontal overflow. At320px destination targets are61×48px and profile44×44px. The menu stays within the viewport and Escape returns focus to its trigger.
- At1307px collapsed/expanded rails remain74/172px. With desktop expansion remembered,320px renders the same56px top row, no overlay shadow and full-width main; phone expand control is hidden. Profile dropdown remains within screen bounds.
- Browser-local stylesheet removed after verification. Desktop expansion preference and viewport restored. No records, account data, integrations or settings saved. Production still runs the released side-rail version until this PR is merged/deployed.
- Private screenshot retained locally only: `frontend/output/playwright/fleet-map-phone/mobile-navigation-preview390.png`. Preview files excluded from Git.

## Local runtime receipt

Intended checkout `truck-fleet-map-phone`, branch above, base `b8a97499`. Mandatory runtime alignment attempted after branch switch: controller refuses pre-existing untracked preview output; approved `backend/.env` also absent. Existing8000 sandbox was not altered or used as an aligned backend;5173 unbound. Existing synthetic preview5193 is not claimed as this feature's full-stack acceptance. **Local full-stack runtime blocked**; signed-in presentation evidence above is a temporary browser-local CSS preview on production, not a deployed source change.

Standalone ESLint reports four existing no-explicit-any errors and one existing hook warning in FleetApp; use the repository baseline-aware changed-source lint gate to establish no new violations. Baseline-aware changed-source lint passes with no new violations across2 files. Shared-controls check, TypeScript and production build pass (existing large-chunk advisory). Protected CI/release status recorded on the board. Not Done until deployment and final signed-in acceptance.
