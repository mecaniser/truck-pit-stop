# DB-FLEET-MAP-EDGE — mobile fleet width refinement

[PR827](https://github.com/mecaniser/truck-pit-stop/pull/827). Current status: **Done — released and signed-in production verified (2026-11-07)**.

Owner: Frontend & UX. Fast UI. Branch: `codex/fleet-map-edge-to-edge`, base498ffed7.

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

Historical local-review status: release remained pending until explicit user approval; current release proof follows.


## Release and signed-in production acceptance — 2026-11-07

User approved the full-width local preview and explicitly authorized verification, merge/deploy and production checks. All seven protected CI checks passed on172c23693f0e6ed7143425d98506b890ba7b2e08 (run42344840945); strict main protection was satisfied. Final source scope is32 lines of phone-only fleet CSS plus board/evidence documentation, with no fixtures/config/dependencies or JS/API/auth/tenant changes. Local focused checks remain30 tests and production build.

PR827 squash-merged at2026-11-07T06:29:12Z as `bcb4fc0d1618485eb645cc691727e40eaf4d6458`. Railway auto-deployment `9c6e0a6b-0a04-49fb-bcf9-3a9a4fca0c7f` succeeded on the exact SHA. Public www/API build stamps match; readiness reports healthy database and Redis.

Reloaded signed-in production `/fleet` on deployed source, with no browser stylesheet override:

- Map at320/375/390/430px portrait and844×390 landscape: canvas left0, right equals viewport width; zero outer padding/border, no horizontal overflow. At390px canvas/client width390. Exactly one shell vertical scroller remains; native scrolling over list moves outer0→844 while inner scrollTop stays0.
- Fleet Board at320/375/390/430px: cards fill309/364/379/419px content area beside the visible native thin scrollbar, with no extra outer card gutters or horizontal overflow.844 landscape uses833px content area with its two-column grid.
- Dragging the actual production Board scrollbar moves shell scrollTop0→3380; header top stays0 and nav bottom844. One shell scrollbar remains.
- Final map unit532 is reachable/selectable; located609 selects its matching pin. Profile fits320px and Escape closes it. Normal map Recenter and Board/Map navigation remain usable.
- Desktop1307 retains32px page padding,1px framed map border, original card grid and normal scrollbar treatment. No phone-only full-width rule applies there.
- Zero new browser console errors during live verification. Verification selection/menu cleared and viewport restored. No records, account settings, integrations or financial state saved.

Private production screenshot stays local only: `frontend/output/fleet-mobile-review/production-full-width-map390.png`; excluded from Git. Responsive browser checks, not physical-device hardware acceptance. Historical local-backend alignment limitation remains unrelated to successful deployed acceptance.

Product item **Done — released**, Frontend & UX accountable. No required product follow-up hidden in completion.
