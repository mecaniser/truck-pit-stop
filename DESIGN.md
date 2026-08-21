---
name: "DieselBridge Product Presentation"
description: "The public product preview and authenticated staff presentation system."
colors:
  canvas: "#07101d"
  raised-canvas: "#0b1728"
  product-navy: "#13233d"
  road-white: "#f6f8fb"
  ink: "#f7f9fc"
  steel-muted: "#91a2b8"
  copper: "#df5a13"
  copper-bright: "#ff7a2e"
  service-green: "#087252"
typography:
  family: "ui-sans-serif, -apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, sans-serif"
  display: "clamp(2.65rem, 5vw, 4.6rem) / 1.02 / 700"
  headline: "clamp(2rem, 4.5vw, 3.65rem) / 1.03 / 700"
  body: "1rem / 1.65 / 400"
rounded:
  control: "0.75rem"
  card: "0.9rem"
  workspace: "1.45rem"
  pill: "999px"
---

# DieselBridge public homepage design system

## Product story

The homepage demonstrates DieselBridge through one internally consistent, presentation-only repair story. It does not claim that the sample is a real customer record and does not show a visible fictional or illustrative disclaimer. Values use reserved example data, masked vehicle identity, reconciled totals, and a strict event chronology.

The product tour contains five source-grounded surfaces in the order used by the public preview:

1. **Repair Orders** — paid/closed repair order, Work Requested, authentic invoice evidence, repair-order history, Work & Labor, parts, labor, and total.
2. **Customers** — customer list columns and a compact Overview/History detail.
3. **Shop Work** — Shop Cockpit, Work Queue/Activity, and the Needs Action, On the Floor, and Ready to Close lanes.
4. **Invoices** — embedded invoice cards in Paid, Pending Zelle confirmation, and Awaiting payment states.
5. **Vehicle History** — vehicle identity, owner, key details, masked VIN, and expandable repair history.

Selecting a module replaces the whole miniature. Each module owns only its authentic local controls and remembers its local selection when the user changes modules. There is no global workflow-stage selector and no invented cross-module state matrix.

## Composition

The dark page field frames one road-white product workspace. At enhanced desktop widths the scene reserves this reading order:

`module context sheet → reserved rail → product workspace → reserved rail → selected evidence sheet`

The context sheet always describes the selected module. The evidence sheet exists only when an authentic row, card, disclosure, or history record is selected. Vehicle History intentionally renders no evidence sheet until a repair record is opened.

At widths below `1200px`, sheets follow the workspace in semantic order and every connector is absent. At `960px` and below the module selector becomes a contained grid. At `390px` and `320px` it wraps rather than producing page-level horizontal scrolling; tables become compact selectable records and the primary CTA fills the available width.

The workspace height is content-driven. Surfaces may be short or tall according to their real information density; do not reserve a large fixed empty canvas.

## Routed evidence

Enhanced routed mode requires both `(min-width: 1200px)` and valid measured geometry. Exactly two possible routes exist:

- selected module left-edge center to context-sheet right-edge center;
- selected authentic control anchor to evidence-sheet left-edge center.

Routes are measured after committed content using live rectangles relative to the scene. Obstacles are inflated by `8px`. An invalid, missing, zero-sized, crowded, or colliding route is suppressed together with its travelling node; content and controls remain complete. Resize, font readiness, and content changes coalesce into one new measurement. Old animation is cancelled before the latest state is presented.

## Material and color

- Deep navy creates the calm operating field.
- Road white belongs to authentic product surfaces rather than generic marketing cards.
- Copper/orange is scarce: selected product context, the primary enrollment action, route signals, and focus.
- Service green communicates completed or paid operational state.
- Context and evidence sheets may use restrained navy glass only when backdrop transparency is supported. Reduced-transparency, high-contrast, and forced-colors modes use opaque surfaces and explicit edges.

The enrollment CTA is a layered copper/orange control with an inner light edge, restrained specular face, dark copper offset shadow, and responsive arrow. It is not a flat generic rectangle.

## Motion

Pointer interaction may use an authored focal sequence of immediate compression, source confirmation, route reveal, and destination morph. It settles within `520ms`, is interruptible, and animates only transform, opacity, clip-path, or route presentation.

Keyboard activation commits selection, focus, semantic content, and the queued status message without spatial sheet or connector animation. Reduced-motion mode also removes travel and morphing. There is no ambient, looping, bounce, shimmer, or parallax motion.

## Accessibility

- The module selector is one vertical tablist with roving focus and automatic Up/Down, Home/End activation.
- Authentic local tab systems retain their native product orientation and selection semantics.
- Controls are at least `44px` in both axes and do not depend on hover.
- One visually hidden, atomic polite status announces committed module or authentic local selection. It is silent on initial render, focus-only movement, resize, font readiness, and route remeasurement; rapid changes announce only the latest state.
- Focus remains visibly identifiable in normal and forced-color modes.
- Supporting metadata has an `11px` mobile floor and must wrap rather than overflow.

## Integrity and scope

- The preview is a deep-frozen typed fixture. It performs no auth, API, storage, WebSocket, tenant, payment, or mutation work.
- Runtime approved-shop loading remains isolated to its existing public endpoint and retains loading, empty, failure, and retry behavior.
- `/login`, `/enroll`, privacy, terms, SEO, favicon behavior, and the approved-shops route remain unchanged.
- Do not add testimonials, customer outcomes, performance metrics, pricing promises, real PII, or partner endorsements.

## Craft rules

- Show the real information architecture, not a generic feature-card catalogue.
- Let interaction hierarchy, spacing, and typography explain the product before decoration.
- Keep the product tour responsive to interruption: the latest action always wins.
- Suppress a bad connector rather than drawing through a label, control, or card.
- Keep context and evidence visually related but structurally independent.
- Preserve compactness without reducing field legibility or touch safety.

## Authenticated staff presentation (DB-035)

The authenticated staff app extends the same DieselBridge product language without copying the public preview or creating a second application. Legacy and new presentations share one router, one domain state, one API client, and the same permissions and mutations. The server resolves the presentation; Appearance never acts as a hidden rollout switch.

### Brand hierarchy

DieselBridge is the primary product identity in the new staff shell. The active shop logo and name are subordinate workspace context, not a replacement product brand. Long or absent tenant branding must compress or fall back without displacing navigation.

### Staff surfaces

The new presentation applies only inside the authenticated staff shell across Dashboard, Customers, Repair Orders, Messages, My Shop, and Profile/Settings. Public, login, customer, driver, fleet, mechanic, and platform-admin surfaces retain their independent presentations. DB-035 may recompose these six staff surfaces around their real work, but it never invents a queue, selected record, route, permission, mutation, or status. Each canonical page keeps ownership of its existing domain state—for example, selected repair work remains owned by Repair Orders, not Dashboard.

At 1280px and above, the new shell uses a full product rail. From 960–1279px it uses the same route links in a compact rail. Below 960px, the existing mobile navigation owns route changes so the work surface is not squeezed. The legacy presentation retains its existing tenant-led header and navigation.

### Personalization boundaries

Appearance is a reversible preference editor with separate draft and committed values. It offers five curated accents, four font families, three font sizes, four densities, three surface modes, and three notification locations. Accent colors may express neutral selection, links, and focus enhancement only. Success, warning, danger, authorization, payment, financial, and operational-risk meanings always use immutable semantic tokens.

Density controls spacing and information rhythm rather than browser zoom. Compact/default/comfortable/large rows are at least 48/52/56/64px; controls remain at least 44px, or 48px in large density. Small/default/large body text is 14/16/18px, while touch-first editable fields remain at least 16px.

### Material and accessibility

Authenticated surfaces use deep navy operating fields, restrained raised layers, road-white light surfaces, explicit edges, and low-noise depth. High contrast and forced colors replace decorative material with opaque system-safe boundaries. Reduced transparency removes blur. There is no ambient animation; preview changes are immediate and reversible, preserve focus, and never animate every descendant.

Notifications use the shared toaster and respect safe areas, mobile navigation, modals, and fixed repair-order actions. At 320px and 390px they wrap within the viewport and retain an accessible 44px dismiss target.
