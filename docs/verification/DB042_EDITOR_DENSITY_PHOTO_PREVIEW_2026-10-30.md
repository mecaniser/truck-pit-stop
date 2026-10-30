# DB-042 — dense part editor, photo preview and hotspot padding

Accountable owner: Frontend & UX. Fast UI lane; branch `codex/part-editor-density` from `5d78c9fb` (PR #706). User authorized follow-up implementation, hover/keyboard QA, protected merge and deployment after passing gates. Existing API, permissions, tenant, inventory mutations, financial validation, schema and dependencies are unchanged.

## Acceptance and evidence

- The photo has breathing room inside the hotspot. Before: content inset4.8px minus highlight4px =0.8px; after:12px minus4px =8px. Hover remains limited to the identity area; Available/Bin/prices are sibling cells.
- Photo and placeholder previews open from independent native buttons in the ledger and selected inspector, with no nested button. The enlarged image uses contain sizing. Existing part→shop logo→icon fallback is preserved in the preview. Opening another row's media does not select it or write data.
- User follow-up replaces the added photo hover outline with140ms scale1.08 on image/icon content only, clipped by the unchanged frame. Real signed-in pointer QA confirms matrix1.08 for actual image and placeholder, outline:none, unchanged46px frame; reduced-motion and coarse-pointer transforms:none, keyboard focus solid. [Hover capture](db042-editor-density/photo-hover-zoom.png).
- Headless UI Dialog (already installed) provides modal focus handling, Escape/outside dismissal and focus restoration. Signed-in real browser pointer opening, native Tab to preview, Space opening, Tab containment, Escape, close button and restored trigger focus pass. Reduced motion retains0s hotspot transition.
- Follow-up compact-ledger check found the new spacer and preview trigger must follow the existing hidden-photo mode. Both now use display:none in Compact; signed-in verification confirms52px rows with no invisible photo keyboard stop.
- Every selected-part editor field remains. Desktop selected section is810.5px tall versus1209.4px baseline at1920×1080 with437px inspector (33% shorter). Smaller identity photo, no redundant selected label row while editing, compact field gaps, paired Unit/Description, reduced fieldset spacing, and pricing policy beside its heading produce the reduction.
- Desktop blank cost still reports the explicit validation error. Escape returns focus to Edit details. Wide-layout Cancel is visible/clickable and discards a changed name; reopening returns saved identity.
- At390×844 with coarse pointer, fields are >=44px high, page width fits, and actual image preview is358px wide with no horizontal overflow. Header and close target remain contained. Desktop/compact screenshots contain only fictional fixture data: [desktop](db042-editor-density/desktop.png), [mobile](db042-editor-density/mobile.png).

## Runtime alignment

2026-10-30 EDT: frontend `http://127.0.0.1:5198`, Vite PID67014, cwd this worktree's frontend. API `http://127.0.0.1:8014`, container `dieselbridge_api_part-editor-density`, /app bind this worktree/backend. Branch/base as above; modified source browser-verified. Existing fictional `truckpitstop_db042_qa`, Redis12, Alembic `192_vehicle_issues`; upgrade was no-op. Direct/proxied readiness passes DB/Redis. Shared5173/8000 preserved. Fictional fitting image_url set to local bundled logo solely to exercise actual image rendering; second fictional row retains icon placeholder. No production record writes, uploads, messages or payments.

## Checks and release

Focused inventory component tests56/56 pass, including three new preview regressions (initial missing preview tests failed before implementation); changed-source ESLint and TypeScript/Vite build pass. Protected CI pending. Mechanical design detector found seven warnings in unchanged CSS lines7023–7061; no changed-line findings (new CSS starts after7210). No auth/data/security boundary change requiring independent Security. Protected PR CI is the integration gate. Deployment and live route check remain pending.
