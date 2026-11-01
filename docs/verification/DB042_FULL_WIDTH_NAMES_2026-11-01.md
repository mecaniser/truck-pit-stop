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
