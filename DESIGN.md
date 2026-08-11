---
name: "DieselBridge Public Homepage"
description: "A calm operating view that carries a repair shop from intake to paid vehicle history."
colors:
  diesel-canvas: "#07101d"
  diesel-canvas-raised: "#0b1728"
  diesel-navy: "#13233d"
  road-white: "#f7f9fc"
  paper-white: "#ffffff"
  diesel-ink: "#f9fafb"
  steel-muted: "#b7c2d2"
  signal-orange: "#c74700"
  signal-orange-hover: "#a93b00"
  service-green: "#067454"
  document-blue: "#1e66c4"
typography:
  display:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, sans-serif"
    fontSize: "clamp(2.65rem, 6.8vw, 5.65rem)"
    fontWeight: 700
    lineHeight: 0.98
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, sans-serif"
    fontSize: "clamp(2rem, 4.5vw, 3.65rem)"
    fontWeight: 700
    lineHeight: 1.03
    letterSpacing: "-0.035em"
  body:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.65
    letterSpacing: "normal"
  label:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    lineHeight: 1.45
    letterSpacing: "normal"
rounded:
  compact: "0.55rem"
  control: "0.75rem"
  card: "0.9rem"
  frame: "1.15rem"
  pill: "999px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1rem"
  xl: "1.25rem"
  section: "clamp(4.5rem, 9vw, 7rem)"
components:
  button-primary:
    backgroundColor: "{colors.signal-orange}"
    textColor: "{colors.paper-white}"
    rounded: "{rounded.control}"
    padding: "0.85rem 1.2rem"
    height: "48px"
    typography: "{typography.label}"
  button-primary-hover:
    backgroundColor: "{colors.signal-orange-hover}"
    textColor: "{colors.paper-white}"
    rounded: "{rounded.control}"
  workspace-frame:
    backgroundColor: "{colors.road-white}"
    textColor: "{colors.diesel-navy}"
    rounded: "{rounded.frame}"
  context-sheet:
    backgroundColor: "rgba(13, 28, 48, 0.76)"
    textColor: "{colors.diesel-ink}"
    rounded: "{rounded.card}"
    padding: "0.9rem"
  navigation-glass:
    backgroundColor: "rgba(12, 25, 43, 0.72)"
    textColor: "{colors.diesel-ink}"
    rounded: "1rem"
    padding: "0.55rem 0.6rem 0.55rem 1rem"
    height: "4rem"
  stage-tab:
    backgroundColor: "transparent"
    textColor: "#5c6b7f"
    padding: "0.6rem 0.7rem"
    height: "44px"
    typography: "{typography.label}"
  stage-tab-selected:
    backgroundColor: "#fff7f2"
    textColor: "{colors.signal-orange-hover}"
    padding: "0.6rem 0.7rem"
    height: "44px"
    typography: "{typography.label}"
  partner-state:
    backgroundColor: "rgba(19, 35, 61, 0.62)"
    textColor: "{colors.steel-muted}"
    rounded: "{rounded.card}"
    padding: "1.25rem"
---

# Design System: DieselBridge Public Homepage

## Overview

**Creative North Star: "The Calm Operating View"**

DieselBridge turns the entire shop repair into one calm operating view. The public world is precise, shop-only, and product-led: a deep Diesel navy field holds one dominant road-white repair-order workspace, while signal-orange identifies the next consequential action. The first impression is not a generic grid of feature cards; it is the software itself, showing one repair move from intake through approval, invoice, payment, and durable vehicle history.

Operational glass expresses context, not decoration. A floating navigation shell and three source-anchored sheets sit above the workspace only where approval, invoice, and paid history need visible relationship to the underlying repair order. Fleet information may appear inside this world only as contextual shop-work data attached to the same repair record; the public promise remains for repair shops.

**Key Characteristics:**

- Deep Diesel navy atmosphere with road-white product surfaces.
- One dominant repair-order workspace instead of interchangeable feature cards.
- Signal-orange reserved for selection and founding-access actions.
- Restrained, source-anchored glass that explains workflow relationships.
- Verified product language and runtime partner data in place of marketing fabrication.

## Colors

The palette behaves like a night shop around an illuminated operating surface: navy establishes trust and focus, road white carries dense product truth, and orange marks the decision path.

### Primary

- **Signal Orange:** The scarce action color for founding-access buttons, the selected workflow stage, and small brand emphasis. Its darker hover state signals response without changing the hierarchy.

### Secondary

- **Service Green:** Confirms in-progress, approved, and paid states inside the product story.
- **Document Blue:** Identifies invoice/document context when green would imply completion.

### Neutral

- **Deep Diesel Canvas:** The page field and darkest visual anchor.
- **Raised Diesel Canvas:** A subtle secondary navy used when the page needs tonal separation.
- **Diesel Navy:** Navigation, product sidebar, contextual containers, and strong ink on road-white surfaces.
- **Road White:** The dominant repair-order workspace; slightly cooler than pure paper white so internal white cards remain legible.
- **Diesel Ink:** Primary text on the dark canvas.
- **Steel Muted:** Supporting copy and metadata on navy.

**The Signal Is Scarce Rule.** Orange marks the current stage or the primary shop-access action; it does not become ambient decoration.

**The Product Is the Light Rule.** Large light surfaces belong to authentic product workflow, not generic marketing cards.

## Typography

**Display Font:** Native system sans (`ui-sans-serif`, Apple system, BlinkMacSystemFont, SF Pro Text, Segoe UI, sans-serif)

**Body Font:** The same native system sans stack

**Character:** System typography keeps the world immediate, legible, and operational. Very tight display tracking and compact line heights create the calm Apple-like promise; body copy remains generous enough for working-shop clarity.

### Hierarchy

- **Display:** Heavy, tightly tracked, and balanced across a short measure; reserved for the centered first-viewport promise.
- **Headline:** Large, tightly tracked section statements with a short, composed line length.
- **Title:** Compact product and card headings, typically between `1.05rem` and `1.8rem`, that stay subordinate to the public story.
- **Body:** Regular weight with open leading; marketing explanations stay near `62–66ch` while product-preview copy stays near `48ch`.
- **Label:** Small and semibold-to-bold for stage tabs, statuses, metadata, and actions; sentence case is the default.

**The System Voice Rule.** The homepage explicitly uses its native system stack even though shared document head imports make other font families available. The accepted global-font warning is not permission to change this surface's type world; resolve shared imports separately if the wider application later removes them.

## Layout

The homepage uses a centered `72rem` content rail, with the hero widening to `80rem` so the product scene can dominate the first viewport. Horizontal padding is fluid from `1rem` to `2rem`; major sections breathe on a fluid vertical rhythm. The floating navigation, centered promise, primary action, and repair-order workspace form one axial composition.

The desktop workspace is a two-column product shell: a narrow navy product rail and a flexible road-white main area. Summary facts appear in three equal cells, five stage controls share one horizontally scrollable row, and the selected-stage content pairs a primary narrative card with a compact work checklist. Three contextual glass sheets overlap the frame and connect back to their source with one-pixel rules.

At `960px` and below, the product rail disappears, the workspace becomes a single column, and contextual sheets leave the overlap plane to stack beneath the frame in approval, invoice, and history order. Workflow steps become a two-column list. At `640px` and below, the navigation reduces to brand plus sign-in, the hero action becomes full width, nonessential workspace facts and the checklist are removed, workflow steps become a single vertical sequence, and partner/error surfaces stack. Stage tabs remain horizontally scrollable so their semantic order survives narrow screens without shrinking to illegibility. Desktop stage controls are explicitly `44px` high and increase to `48px` on mobile. Runtime regression checks at `320px` and `390px` lock both target sizing and the absence of horizontal page overflow.

**The One Repair Spine Rule.** Every section must reinforce the same intake-to-history sequence; do not split the story into unrelated capability islands.

## Elevation & Depth

Depth is a hybrid of tonal layering and two deliberate elevation families. The road-white workspace uses a deep ambient shadow to feel like the singular operating surface above the navy canvas. Navigation and contextual sheets use blur, saturation, translucent navy, a faint light edge, and softer ambient shadow. Ordinary workflow and partner containers stay tonal and quiet.

### Shadow Vocabulary

- **Workspace Lift** (`0 38px 100px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.7)`): The single dominant product frame.
- **Floating Navigation** (`0 18px 50px rgba(0, 0, 0, 0.22)`): The restrained glass header.
- **Context Sheet** (`0 22px 55px rgba(0, 0, 0, 0.34)`): Source-linked approval, invoice, and history context; the active sheet lifts slightly more.
- **Action Glow** (`0 12px 28px rgba(153, 52, 0, 0.32)`): Reserved for signal-orange primary action.

**The Glass Has a Source Rule.** A glass sheet must explain a visible relationship to product content. Never apply translucent blur to every card.

**The Solid Fallback Rule.** Reduced-transparency and increased-contrast environments replace glass with solid navy and an explicit light edge; information hierarchy must not depend on blur.

## Shapes

The form language is gently engineered rather than soft or playful. Frames and public containers use medium rounded rectangles, controls use tighter corners, and status indicators alone use full pills. The workspace's outer radius is the largest recurring corner, giving it object-like presence; nested cards step down in radius. One-pixel dividers and source rules provide precision without boxing every region.

Brand and workflow icons are lightweight line SVGs. The DieselBridge mark is an authored SVG bridge silhouette and must remain vector, semantic at the wordmark level, and free of decorative raster substitutions. General interface icons may use the established line-icon vocabulary; decorative or fabricated partner marks are prohibited.

On the `/` route, the favicon manager selects only the lightweight authored `/dieselbridge-mark.svg`; the homepage does not add a PNG fallback or retain stale public/admin favicon links. Route changes may select their own established asset sets, but returning home must restore the single lightweight SVG.

## Components

### Buttons

- **Shape:** Confident rounded rectangle with an explicit `48px` minimum height for primary actions, independent of compact root scaling; mobile actions fill the available width.
- **Primary:** Signal-orange with paper-white text, a quiet warm shadow, and a right-facing arrow for founding access.
- **Hover / Focus:** Hover deepens orange and the shadow; active press scales immediately to `0.975`. Keyboard focus uses a three-pixel white outline with a three-pixel offset.
- **Secondary:** Sign-in remains a quiet text action. Retry is a compact paper-white button on a navy proof-state container and reports its disabled/fetching state in copy.

### Cards / Containers

- **Workspace Frame:** Road-white, deeply elevated, and the largest light object on the page.
- **Content Card:** Paper white with a quiet cool shadow inside the workspace.
- **Context Sheet:** Translucent navy glass with an icon tile, strong title, compact explanation, and a line anchored toward the relevant workspace source on desktop.
- **Partner Card:** A low-contrast navy tile for API-returned shop identity; it may render the runtime logo or a generated text monogram when no logo exists.

### Navigation

The public navigation is a floating translucent navy shell. Desktop presents the authored DieselBridge wordmark, two in-page wayfinding links, sign-in, and one shop-access action. At mobile width it preserves only the wordmark and sign-in because the full-width founding-access action immediately follows in the hero. The product-preview navigation is intentionally different: a solid navy rail with repair orders selected, and it disappears below the desktop workspace breakpoint.

Every public navigation, partner, footer, and text-link target is explicitly at least `44px` in the relevant axis; target size does not depend on inherited line height or compact density settings.

### Repair Workflow Stage Selector

Five buttons preserve the order `Intake → Estimate → Approval → Invoice → Payment & history`. Each button exposes selected state with `aria-pressed`; selection replaces the stage narrative, detail, and next action without navigating away. The active tab receives pale orange backing and a signal-orange underline. Approval, invoice, and history selections also elevate their matching context sheet; intake and estimate change the workspace content without falsely activating a downstream proof sheet. The row scrolls horizontally when needed and remains keyboard-operable.

Motion gives immediate press response and uses critically damped `0.3–0.4s` swaps and sheet emphasis. Scene entry is a one-time materialization, and interactions stay interruptible. `prefers-reduced-motion` collapses animation and transition durations to `1ms`, preserving state changes without spatial travel.

### Partner Proof States

- **Loading:** A live status container pairs “Loading approved shops…” with a lightweight spinner.
- **Empty:** A neutral building icon and direct sentence explain that approved profiles will appear as they go live.
- **Error:** An alert keeps the product overview usable, states that shops could not be loaded, and offers a clear retry action.
- **Retrying:** The retry control disables, changes to “Trying again…”, and avoids duplicate requests.
- **Loaded:** Only API-returned partner records may render. Use the runtime `logo_url` when supplied, otherwise derive a text monogram; never bake partner logos, endorsements, or fabricated shops into the public artifact.

The regression contract covers loading, empty, error, successful retry, loaded partners, and stage selection at the unit level. Homepage browser coverage locks `320px` and `390px` target sizing, no-overflow behavior, and the route-specific lightweight favicon contract.

## Do's and Don'ts

### Do:

- **Do** position DieselBridge publicly for repair shops and keep fleet information contextual to shop work on the same repair record.
- **Do** make one authentic repair-order workspace the primary visual proof.
- **Do** use signal-orange only for the selected stage, brand accent, and highest-priority shop-access action.
- **Do** preserve semantic landmarks, labels, `aria-pressed` stage controls, a skip link, visible keyboard focus, explicit `44px` public-link and desktop-stage targets, `48px` primary controls, and `48px` mobile stage targets.
- **Do** preserve reduced-motion, reduced-transparency, increased-contrast, and forced-colors fallbacks whenever the world expands.
- **Do** use authored SVG for the DieselBridge mark and established line icons for interface meaning.
- **Do** keep `/` on the single lightweight `/dieselbridge-mark.svg` favicon without a homepage PNG fallback.
- **Do** keep unit proof for loading, empty, error, successful retry, loaded partners, and stage selection, plus homepage browser proof at `320px` and `390px` for target size, no overflow, and favicon behavior.
- **Do** prove partner loading, empty, error, retrying, and loaded states with runtime data.

### Don't:

- **Don't** turn the homepage into a generic feature-card catalogue or a standalone fleet-product pitch.
- **Don't** fabricate testimonials, customer outcomes, metrics, pricing, partner endorsements, shops, or workflow facts.
- **Don't** hard-code partner logos or treat a local shop name as an endorsement; partner identity arrives from the public partner endpoint at runtime.
- **Don't** spread glass across ordinary cards; glass is reserved for navigation and source-anchored workflow context.
- **Don't** use orange as ambient decoration, a large background field, or a substitute for information hierarchy.
- **Don't** replace the native system type world merely because shared global font imports are present.
- **Don't** make the active workflow state depend on color or motion alone.
