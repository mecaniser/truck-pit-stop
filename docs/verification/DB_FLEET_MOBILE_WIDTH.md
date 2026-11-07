# DB-FLEET-MAP-EDGE — mobile fleet width refinement

[Draft PR827](https://github.com/mecaniser/truck-pit-stop/pull/827). Owner: Frontend & UX. Fast UI. Branch: `codex/fleet-map-edge-to-edge`, base498ffed7.

Acceptance: use the available phone width on Map and Fleet Board, retaining a visible Fleet Board scrollbar per user clarification. Preserve single-page native scrolling, readable/control/safe-area insets and desktop framing. CSS only; no API/auth/role/data/dependency change. Local review before deployment.

## Implementation

- Phone map removes page padding, frame border/radius and reserved custom scrollbar width. Scrolling stays native; text and controls retain their own safe-area-aware padding.
- Phone Fleet Board removes outer card gutters, retains a native thin visible scrollbar with contrasting thumb, and keeps header/control padding. Cards fill the content width beside the scrollbar. Board itself respects safe-area insets.
- Scope uses the existing680px portrait /960px short-landscape breakpoints. Desktop and other fleet journeys retain their existing framing.

## Local verification — 2026-11-07

Actual-source sample preview5194, route `/output/fleet-mobile-review/index.html`, PID67125 command/cwd verified at this checkout’s frontend, HTTP200. Existing provider/API fixture adapter and blocked writes preserved. Mandatory runtime switch was attempted after branch change; controller rejects existing untracked preview files, and full backend alignment is not claimed. **Browser-verified sample UI only**; no production calls or records.

- Map at320/375/390/430 and844 landscape: left0, right equals viewport width, no horizontal overflow, one shell scroller.390px map expands349→390px. Native list scrolling still reaches final611 and selection works; Profile remains within bounds.
- Fleet Board at320/375/390/430px: cards fill309/364/379/419px content widths beside the visible native thin scrollbar, with zero outer card padding and no horizontal overflow.390px cards expand351→379px.844 landscape retains the full833px content area for its two-column grid.
- Dragging the visible board scrollbar moves shell scrollTop0→1414. Exactly one vertical scroll container remains. Header/bottom navigation remain anchored. Local preview left open on Fleet Board390px for review.
- Desktop1307: original32px page padding, framed map border and normal scrollbar treatment remain. Local browser reports zero console errors.
- 16 FleetProximity tests plus14 FleetBoard PM/order-view tests pass; Vite production build and diff check pass. No JS source/lint change or CSS-mirroring test added. Existing large-chunk advisory unchanged.
- Private screenshots remain local/excluded: `frontend/output/fleet-mobile-review/edge-to-edge390.png` and `full-width-board390.png`. Physical-phone safe-area acceptance is not claimed.

Not merged/deployed or Done. User review and protected release checks remain pending.
