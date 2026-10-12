# DB-103 repair-order workspace refinement

Frontend & UX owns this Fast UI item. Desktop is the primary operating surface. Phone support preserves the same workflows with a different layout. No API, migration, auth, tenant, payment processing or provider changes. Draft PR502 remains stacked on DB-099 / PR498.

## Corrected acceptance, 2026-10-12

The user rejected the first visual pass. Its earlier local UX acceptance is superseded by this correction. Source `01f9c51e` includes the density correction, anchored truck details, responsive parts and viewport-aware part pricing.

- Truck/customer details open in a Headless UI popover anchored beneath the header trigger, including VIN, contact, mileage, PO and type. The former below-the-services disclosure is removed. Opening moves focus into visible content; Escape/close returns focus to the trigger without jumping to the bottom.
- Desktop header, workflow, intake, service metadata and supporting recommendations are compact. Empty Savings columns disappear only when every part has zero savings. Parts retain quantity, unit price, stock overrides, pending states, delete and all existing edit/lock guards; no indentation steals their name column.
- Phone detail uses the staff content as its single scrolling surface. Parts reflow into named fields with visible quantity, unit price and total; no horizontal table navigation is required. Full toolbar labels fit. Quantity and labor step buttons measure 44px in both directions. Part pricing uses anchored, viewport-bounded positioning instead of estimating popup height; close/Escape cancels a draft and restores focus.
- Queue and stage-based actions from the first pass remain intact. No messages, payments, invoice-state changes or part-price mutations were submitted during browser verification.

### Measured desktop density

Same authenticated fixture and 1248x1185 CSS viewport, before versus after this correction:

| Element | Before | After |
| --- | ---: | ---: |
| Job header | 112px | 75px |
| Workflow band | 61px | 37px |
| Collapsed service row | 55px | 40px |
| Standalone part row | 69px | 52px |
| Part controls | 44px | 28px |
| First service starts | 448px | 343px |

All six labor operations, all six standalone parts and the two prior recommendations fit in the desktop viewport. Parts names fit without the prior table indentation and line wrapping. Truck popover was observed about 8px below its trigger with body scroll unchanged.

### Verification

- 101 focused tests pass across PriceBuilderPanel.pending-feedback, RecommendedWorkPanel, WorkflowInfoStep, RepairOrdersPage.authorization and RepairOrdersPage.void-revision. New regressions cover truck disclosure focus/Escape, zero versus nonzero Savings, cancellation without a price write, draft reset, and explicit price application. Earlier queue/stage coverage is retained.
- Changed-source ESLint, TypeScript/Vite production build and git diff check pass. Impeccable layout scan reports no findings.
- Signed-in in-app browser verification: desktop 1248x1185, phone 355x767 and narrow phone 320x680 CSS dimensions. Requested 390x844 and 352x748 overrides reflect the existing browser zoom. Actual viewport and geometry were read from the rendered DOM.
- Phone verification covers whole-document scrolling; visible part quantity/price/total; part-price popup containment and dismissal; expanded labor controls; header truck disclosure and focus; pricing totals/footer reachability; and return to desktop. At 320px, staff content, workspace, sheet, body and parts have equal client/scroll widths after fixing a 7px navigation overflow. Desktop header remains visible after resizing back.
- This is responsive browser evidence. Physical iPhone/Android touch behavior, virtual keyboard and native mobile browser chrome were not tested. The local development identity is crowded at the 320px shell width; this is outside the order workspace and is not a production mobile-device acceptance claim.

Current local screenshots in `output/db103/`: `dense-desktop-final.jpg`, `anchored-truck-details-final.jpg`, `mobile-part-price-final.jpg`, `mobile-parts-final.jpg`, `mobile-320-parts-final.jpg`, `mobile-320-labor-final.jpg`, `mobile-320-footer-final.jpg`. Earlier captures are retained for comparison; the two 320px parts/labor captures precede the final 7px header navigation correction, which was confirmed by DOM geometry and the footer screenshot.

## Current runtime receipt

Approved frontend http://127.0.0.1:5174 and API http://127.0.0.1:8001. Intended implementation checkout is `repair-order-workspace/truck-pit-stop`, branch `codex/repair-order-workspace`, source `01f9c51e`. Deliberately integrated into `ets-parity-preview/truck-pit-stop`, branch `codex/ets-parity-preview`, source `4d02ce6374cbce6071015f4d277f874e454b6965` to preserve DB098–102.

Vite PID68993 serves the preview frontend and explicitly proxies to API8001. It booted at preview07275e9; the last CSS-only merges were applied through Vite HMR and corroborated by rendered control/overflow measurements. The build indicator therefore records the boot commit, while the checkout/served source is 4d02ce6. API container `dieselbridge_api_ets-workflow-parity`, identity da0d8e5e2be1, mounts that same preview backend at /app and maps localhost8001:8000. Dedicated PostgreSQL database `truckpitstop_ets_workflow_parity_20261012`, host postgres, schema165, Redis9 and disabled Resend/Twilio settings are preserved. No schema, provider or data changes for this UI task. Frontend-proxied /health/ready returns200 with database and Redis healthy. Original dirty checkout, populated original database and unrelated5173 service are preserved.

The previous tab entered a connection-error document during a local server restart; verification continued in a fresh authenticated tab of the same browser. That final tab is left at desktop size on the active order.

## Delivery state

Local corrected implementation and the responsive journeys above are verified. [PR502](https://github.com/mecaniser/truck-pit-stop/pull/502) remains draft and unmerged; no deployment. The previous head5b577d53 passed [Quality gates](https://github.com/mecaniser/truck-pit-stop/actions/runs/38284765064); the corrected head requires a fresh dispatch because automatic PR checks only target main. Board status: Review, not Done.

## First-pass history

Before user rejection, source bafd9752 in preview38f88c80 passed129 focused tests, lint/build and desktop/355px checks. It tightened the queue and introduced truck-first identity, expandable services and stage-based invoice actions, but left excessive control sizing, misplaced truck disclosure and insufficient phone behavior. That earlier visual acceptance is not the current acceptance record.
