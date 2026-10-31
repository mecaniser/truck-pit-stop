# DB-042 — coherent inventory list surfaces with rounded row edges

Owner Frontend & UX, Fast UI. Branch `codex/inventory-continuous-surface` frome749b452. User asks to remove the patchwork between white rows and blue-gray gaps/side padding, then clarifies that rounded row edges must remain visible and the header corner must match.

## Final implementation and acceptance

Use the existing surface-overlay token on the Parts body, ledger workspace/scroller, row backing, sticky header and list footer. Add a1px inset outline in workspace-border to the existing10px rounded rows. This paints the rounded boundary without changing row geometry or introducing another fill between records. Selected/hover/focus styling remains; other workspaces are untouched. No API, data, permission, dependency, migration or financial behavior changes.

Before: ledger/workspace rgb(232,237,244), resting row rgb(255,255,255), footer rgb(246,248,251). After: body, workspace, ledger, rows backing, header and footer all rgb(255,255,255); resting rows match, with outline1px and radius10px. Selected row remains rgb(236,231,220). Existing theme tokens retain theme support without hardcoded white.

Signed-in real desktop/mobile QA confirms matching surfaces, visible rounded outlines, retained selection, preview opening/Escape closing, and no390px page overflow. At1920×520 and scrollTop65px, sticky header still covers thumbnail (hit test returns header). Native coarse pointer behavior remains. All temporary per-tab emulation cleared. Screenshots use fictional data: [desktop](db042-list-surface/desktop.png), [mobile](db042-list-surface/mobile.png).

61/61 focused inventory/Activity tests pass. CSS-only change: changed-source lint/build/diff checks used; no implementation-mirroring CSS unit test added. Mechanical detector findings are confined to pre-existing CSS, outside these rules. Protected CI/merge/deployment/live acceptance pending; item Review.

## Runtime receipt

2026-10-31: Vite5198 PID26431 cwd this checkout/frontend; API8014 `dieselbridge_api_inventory-surface` binds this checkout/backend. Existing fictional truckpitstop_db042_qa, Redis12, schema196_historical_owner_self_review verified before startup; upgrade no-op. Direct/proxied readiness passes. Prior owned PID96068/API source-checked and gracefully replaced; shared5173/8000/8018 sessions preserved. Branch/base above, changed source browser-verified. http://127.0.0.1:5198/dashboard/garage/inventory aligned and browser-verified. No production record writes.

## Superseding user direction — white surrounding page, gray Parts section

User rejected the continuous white list and added row outlines. Final implementation replaces that treatment: the Parts route main canvas uses surface-overlay (white in Day), while body/list/header/gutters/footer use surface-canvas (rgb(232,237,244) in Day). Existing rounded white records and beige selection remain; no added row outlines. Other routes remain untouched.

Updated signed-in desktop and390px QA confirms white page, gray ledger/header/footer, retained rounded rows and selection, no page horizontal overflow. Screenshots above replaced with this final direction. Prior preview/Escape/sticky-header journey remains applicable because only background paint changed. Updated-head lint/build and protected CI required before release. PR #726 held during revision.
