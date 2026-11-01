# DB-042 — full-width names and whole-row opening

Frontend & UX accountable; Fast UI; branch codex/inventory-full-width-names from f61fd271. User chose full-width names, retained compact sorting/all filters, then requested full-row opening and vertically centered checkbox/photo.

## Outcome

Names wrap without ellipsis. SKU stays beneath; labeled available/bin/cost/value/supplier/remarks facts wrap below. No dedicated empty Remarks column. Compact sticky desktop sorting preserves all six existing API sort keys and directions; mobile menu retains its twelve choices plus Catalog order and now displays the selected sort on its trigger. Existing search, stock/reorder, archive, density and top-level views remain. Supplier sorting is not added: the existing API does not offer it.

Checkbox uses28px desktop track,44px on coarse pointers. Checkbox and photo align to the whole-row midpoint; measured desktop centers453.81px versus row453.82px, mobile476.48px versus row476.49px. Photo effective touch target44×44. Full-row pointer opening excludes checkbox/labels, image preview and menu controls; a single native name button retains Enter/Space access and paints keyboard focus around the row. Portaled dialog clicks are excluded from row activation. No inner hotspot highlight.

No API, auth, tenant, payment, migration, dependency or feature-flag changes. Other workspaces untouched.

## Verification

62/62 inventory/Activity component tests pass, including added long-name/fact selection coverage, all six desktop sorts in both directions, mobile current-sort text, row fact/padding opening, independent checkbox/menu/media and portaled-image click isolation. Existing Save/Cancel, validation, async safety, read-only/archive/deep-link, pagination/reorder and Activity tests retained. Final production build and changed-source lint recorded below after commit.

Signed-in fictional local browser: all six desktop sort fields activate with focus restoration; stock and archive filters, debounced search and empty results, bulk check/clear, photo placeholder/actual preview and Escape, all four inspector tabs pass. Editor Cancel discards a name draft. Description Save persisted and reopened, then original blank restored. No production records touched.390px coarse-pointer layout has no page overflow; long name wraps across three lines, all facts retained, mobile sort choice closes/restores focus, fact tap opens details and Back restores list. Both density modes retain wrapping. Final whole-row and center alignment rechecked after user feedback.

Screenshots: [desktop](db042-full-width-names/desktop.png), [mobile](db042-full-width-names/mobile.png). Fictional fixtures only.

## Runtime receipt

2026-11-01: Vite5198 PID74576 cwd this checkout/frontend; API8015 dieselbridge_api_inventory-full-width mounts this checkout/backend. Branch/base above; dirty source verified through rendered name wrapping, fact cells and full-row activation. Proxy targets8015; direct/proxied readiness DB/Redis healthy. Existing fictional DB truckpitstop_db042_qa schema196_historical_owner_self_review matches source head; no migration/reseed. Redis12; no workers started. Backend env symlink to approved canonical local env. Prior8014/shared runtimes preserved. http://127.0.0.1:5198/dashboard/garage/inventory aligned and browser-verified. Per-tab touch/device overrides cleared.

Status Review; PR/CI/release state recorded in board. Local implementation and QA are distinct from production deployment.

Final arrow correction: row, checkbox, photo and cue share the complete-record center. Desktop controls452.3125px versus row452.3203px; mobile controls468.40625px versus row468.4141px. Reserved right-hand space prevents name/fact collisions with the cue and optional action menu. Desktop/390px screenshots refreshed.

Final local gates:62/62 focused tests pass; TypeScript/Vite production build passes; changed-source lint finds no new violations across2 changed TypeScript files; git diff --check passes. Draft PR #727 head39a19c4233a79b000e0a57603a70f54feda16648 is open. Protected CI pending; not merged/deployed. Final completion notes are local and mirrored in PR body.

## Superseding sorting control — 2026-11-01

User rejects header-style sorting because its alignment implies unrelated row facts are columns. Replace it and the separate mobile sort menu with one shared PlatformSelect labeled Sort by and a separate direction button. Choices: Catalog order, Part name, Available, Bin location, Unit cost, Stock value, Reorder urgency. All six existing server keys and both directions preserved; Catalog fixes asc and disables direction. Field changes use existing default directions; reselecting the same field preserves the chosen direction. Direction shows A–Z/Z–A, Lowest/Highest first, or Least/Most urgent. Static screen-reader table headers remain; no visible header-style sort buttons. Controls remain available during loading/empty results.

No changes to API/auth/tenant/financial contracts or shared dropdown source. Search, stock/reorder, archive and density controls retained.75/75 focused tests pass (63 inventory/Activity plus12 shared PlatformSelect), covering every sort pair, Catalog, pagination reset, checked/detail preservation, search+stock query preservation, same-field direction preservation, keyboard Home/End/Enter/Escape and focus return. TypeScript/Vite build passes. Final changed-source lint recorded after commit.

Signed-in desktop browser checks all six fields and direction toggles, keyboard Escape/focus restoration, stock filter combined with Unit cost, empty-search sorting, and restoring results. Open dropdown uses the shared styled, portaled listbox.320px and390px coarse-pointer checks: menu within viewport, all seven choices reachable, no page overflow; closed Reorder urgency fits at320px after local padding adjustment (text width112px/scroll width112px). Mobile QA also exposed a prior thumbnail/fact overlap: fact text now shares the name's left edge rather than running under the centered thumbnail; at320/390px photo target ends120px, facts begin122px. Full-row/photo/control centers preserved. All temporary emulation cleared; no production writes.

Screenshots: [desktop](db042-full-width-names/sort-desktop.png), [desktop menu](db042-full-width-names/sort-menu-desktop.png), [mobile](db042-full-width-names/sort-mobile.png), [mobile menu](db042-full-width-names/sort-menu-mobile.png). Fictional local fixtures.

Runtime refreshed: same worktree/branch, Vite5198 PID74576 source cwd verified; API8015 mount matches checkout, proxy and direct readiness healthy. Existing fictional truckpitstop_db042_qa schema196_historical_owner_self_review matches source, no migration/reseed or service restart. Changed-source dropdown and direction rendered in signed-in local tab. http://127.0.0.1:5198/dashboard/garage/inventory aligned and browser-verified. Extends draft PR #727; not deployed.

Final sorting gates:75 tests pass; TypeScript/Vite build passes; changed-source lint reports no new violations across2 changed TypeScript files; diff check clean. Code revision c71e60bc. Updated draft PR #727 CI remains integration gate; no merge/deployment.
