# DB-148 platform dropdown consistency

Owner: Frontend & UX. Standard product lane for a broad existing-contract UI change. User explicitly selected Entire platform after the equipment popup screenshot.

## Result

Baseline main17608d10 contained57 native dropdowns in31 feature files. All57 now use the shared BaseSelect menu, directly or through PlatformSelect. Source inventory is output/dropdowns/native-dropdown-inventory.json. The only native select left in production source is the noninteractive, aria-hidden form bridge inside PlatformSelect; it never presents an OS menu.

PlatformSelect is controlled and retains original options/values, real native change events, required validation, form serialization and forwarded focus refs. The one React Hook Form role field uses Controller, so defaults/reset remain synchronized. Disabled choices and groups, explicit disabling and inherited disabled fieldsets are preserved. Keyboard selection, open-menu Escape, closed-field Escape, focus restoration and required errors are covered. Focus restores during the close commit so it cannot steal typing from the next field.

Menus use the same palette/component as the rest of the platform, adapt to the containing surface, use readable selected text, wrap long options, truncate long selections and remain within viewport bounds above their modal. No API, backend authorization, invoice, accounting or EDG export change belongs to this branch.

## Verification

Frozen implementation commit:b33ac7d5.

- Full frontend suite2188/2188PASS, including12 dedicated shared-control compatibility/keyboard/validation/ref/fieldset/viewport tests.
- Production TypeScript/Vite buildPASS.
- Changed-source lint: no new violations across53 TypeScript files.
- Diff integrityPASS; Impeccable detector[] on shared controls and equipment modal.
- Independent source/functional QA GO;12/12 tests independently reproduced. Final review includes refreshed desktop/mobile/theme evidence.
- Six batched browser casesPASS:1440×1000 and390×844, each light/dark/high-contrast with forced colors in the high-contrast case. Real staff app, test JWT and disposable API verify equipment dropdown selection/dismissal/cancellation. Fixture gallery verifies disabled options/fieldsets, native required validation, long labels and a z1200 modal. Menus were hit-tested above the modal and measured within viewport bounds. No page errors.
- Source/API request and permission assertions were retained when old native-select test drivers were replaced with visible-menu interactions. The browser pass samples representative shared states; full source inventory proves migration coverage.

Evidence: output/dropdowns/browser-results.json and twelve equipment/modal screenshots. All pictured companies and records are disposable fixtures. Temporary gallery files and generated JWT are excluded and removed after acceptance. Test frontend5187 and API8017 served this checkout and are stopped after verification; other local services were preserved. The base build identifier remained17608d10 during HMR; changed controls were directly exercised and then frozen inb33ac7d5.

## Release state

Local implementation verified. A follow-up PR description is prepared at output/dropdowns/pr-draft.md. Prior PR713 is already merged; the earlier handoff required explicit approval before PR publication. This broader follow-up is not pushed, published, merged or deployed. No production data changed.

Historical attribution work is isolated in a separate checkout and branch, outside this UI diff.
