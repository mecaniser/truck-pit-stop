# DieselBridge Home Page Impeccable Audit

Date: 2026-08-11  
Board item: DB-027  
Owner: Frontend & UX  
Surface: public `/` route, `frontend/src/features/landing/LandingPage.tsx`  
Mode: Persuade  
Contract impact: none; this audit changes no API, data, auth, tenant, or migration contract.

## Implementation integrity verdict

**Pass with significant gaps.** The page uses real DieselBridge positioning,
semantic structure, and a coherent breakdown-to-repair flow, so it is not a
generic template. However, the public experience inherits private-app theme
preferences, its proof section can silently turn an API failure into an empty
network, and its only conversion path addresses founding shops while the product
serves fleets and shops equally. Those gaps keep the surface from operating as a
trustworthy product-specific marketing system.

The bundled Impeccable detector reported zero deterministic findings against
`LandingPage.tsx`. Live URL detector scans could not run because the optional
Puppeteer package is not installed; no dependency was added for this audit.
Direct in-app browser measurements at 1440×1000, 390×844, and 320×568 replace
that missing scan.

## Audit health score

| # | Dimension | Score | Key finding |
|---|---|---:|---|
| 1 | Accessibility | 2/4 | Primary CTA contrast is 2.43:1 and mobile theme scaling shrinks text and targets |
| 2 | Performance | 2/4 | The landing chunk is small, but two visible logo SVGs total 2.23 MB |
| 3 | Responsive design | 3/4 | No horizontal overflow at 320/390 px; compact scaling weakens readability and touch targets |
| 4 | Theming | 1/4 | A public marketing page inherits signed-in app accent, font, and font-size preferences |
| 5 | Implementation integrity | 2/4 | Real product copy is undermined by ambiguous proof/error states and one-sided conversion paths |
| **Total** | | **10/20** | **Acceptable — significant work needed** |

## Executive summary

- Total verified findings: **4 P1, 5 P2, 1 P3; no P0**.
- The most urgent defect is the primary CTA: white text on the default cyan is
  2.43:1. Every selectable app accent fails the 4.5:1 normal-text threshold:
  cyan 2.43, indigo 4.47, emerald 2.54, rose 3.67, amber 2.15.
- At widths below 1024 px, `ThemeProvider` defaults the entire document to a
  14 px root. Browser evidence showed 12.25 px navigation/footer text, a 42 px
  CTA at 390 px, a 32 px Sign in target, and 18 px-high footer links.
- The partner query exposes loading but not error state. A failed request and a
  legitimate empty result both render “Approved businesses appear here as they
  go live” beneath “Shops already active,” making infrastructure failure look
  like a weak network.
- The header and footer logo SVGs are 1,994,824 and 235,328 bytes respectively.
  The page downloads oversized raster-in-SVG artwork for marks displayed at
  roughly 56 px and 28 px high.
- The page is technically responsive and builds cleanly. Its own lazy chunk is
  only 11.96 kB (4.19 kB gzip), and the focused landing test passes.

## Detailed findings

### [P1] Primary action fails WCAG AA contrast in every theme

- **Location:** `LandingPage.tsx:226-234`; accent definitions in
  `ThemeContext.tsx:17-23`.
- **Category:** Accessibility / Theming.
- **Impact:** The only primary conversion action is difficult to read for users
  with low vision or in bright yard/shop conditions.
- **Standard:** WCAG 2.2 1.4.3 Contrast (Minimum).
- **Recommendation:** Give the public page a fixed brand CTA pairing with at
  least 4.5:1 contrast; do not derive it from user-selectable app accents.
- **Suggested command:** `$impeccable colorize`.

### [P1] Public marketing inherits private-app theme state

- **Location:** `LandingPage.tsx:99-103`; `ThemeContext.tsx:82-132`.
- **Category:** Theming / Accessibility / Responsive.
- **Impact:** A visitor's previous app settings or mobile viewport change the
  brand color, font family, typography scale, and touch geometry of the public
  page. The brand is therefore inconsistent and mobile defaults become smaller
  rather than more legible.
- **Recommendation:** Isolate the public site behind fixed, documented landing
  tokens while preserving browser zoom and user accessibility preferences.
- **Suggested command:** `$impeccable typeset` followed by `$impeccable colorize`.

### [P1] Partner failure is indistinguishable from an empty network

- **Location:** `LandingPage.tsx:104-113` and `239-313`.
- **Category:** Implementation integrity.
- **Impact:** An API outage silently becomes a credibility-damaging empty proof
  section. Even a legitimate zero result contradicts “Shops already active.”
- **Recommendation:** Model loading, error, empty, and populated states
  separately. Hide or truthfully reframe the section when no verified partners
  exist; use a retryable, non-claiming failure state on request errors.
- **Suggested command:** `$impeccable harden`.

### [P1] Oversized logo assets dominate landing-page transfer cost

- **Location:** header at `LandingPage.tsx:185-189`; footer at
  `LandingPage.tsx:417-420`; `BrandLogo.tsx:3-15`.
- **Category:** Performance.
- **Impact:** The visible SVG logo assets total 2.23 MB before partner media,
  despite being rendered at small sizes. This delays first paint on mobile and
  poor roadside connections.
- **Recommendation:** Export clean vector paths or tightly sized WebP/AVIF
  variants, remove embedded base64 rasters, and use one consistent horizontal
  mark with explicit dimensions.
- **Suggested command:** `$impeccable optimize`.

### [P2] Touch targets and supporting text are too small on mobile

- **Location:** header link `LandingPage.tsx:191-196`, CTA `226-234`, footer
  `425-429`; compact scale `ThemeContext.tsx:100-104`.
- **Category:** Accessibility / Responsive.
- **Impact:** At 390 px the Sign in target measured 60×32 px, the CTA 292×42 px,
  footer links only 18 px high, and supporting copy commonly computed to
  12.25 px. These are fragile for one-handed and outdoor use.
- **Recommendation:** Keep public body copy at a 16 px base and give every
  interactive target at least a 44×44 px hit area.
- **Suggested command:** `$impeccable adapt`.

### [P2] The conversion architecture addresses shops but not fleets

- **Location:** hero and CTA at `LandingPage.tsx:200-234`.
- **Category:** Implementation integrity.
- **Impact:** DieselBridge's product record weights garage owners and fleet
  managers equally, but the only action is “Apply for Founding Shop Access.” A
  fleet or dispatcher can understand the promise without knowing what to do.
- **Recommendation:** During shaping, define the primary visitor and add an
  honest secondary path for fleets/breakdown coordination without inventing
  availability or claims.
- **Suggested command:** `$impeccable shape`, then `$impeccable clarify`.

### [P2] Partner content is duplicated as marquee and cards

- **Location:** `LandingPage.tsx:113`, `249-379`; marquee CSS
  `index.css:391-415`.
- **Category:** Performance / Responsive / Implementation integrity.
- **Impact:** The same proof appears in an animated rail and a full card grid,
  increasing DOM/media work and page length without adding evidence.
- **Recommendation:** Choose one proof format. Prefer a static, scannable partner
  grid or compact rail that remains useful without motion.
- **Suggested command:** `$impeccable distill`.

### [P2] Continuous marquee retains GPU promotion and lacks non-hover pause

- **Location:** `index.css:400-415`.
- **Category:** Performance / Accessibility.
- **Impact:** `will-change` remains active at rest, and the infinite motion can
  only be paused by hover. Reduced-motion users are protected, but keyboard and
  touch users cannot intentionally pause populated content.
- **Recommendation:** Remove the duplicated motion surface or add focus/touch
  controls and scope GPU promotion to active movement.
- **Suggested command:** `$impeccable animate`.

### [P2] Tests cover only the populated partner happy path

- **Location:** `LandingPage.test.tsx:40-93`.
- **Category:** Implementation integrity.
- **Impact:** Empty, error, loading, theme isolation, CTA contrast semantics,
  keyboard focus, and responsive behavior can regress without a failing test.
- **Recommendation:** Add focused state tests plus browser acceptance at mobile
  and desktop after the direction is approved.
- **Suggested command:** `$impeccable harden`.

### [P3] Footer uses a mismatched, visually weak logo variant

- **Location:** `LandingPage.tsx:417-420`; `BrandLogo.tsx:8-11`.
- **Category:** Implementation integrity.
- **Impact:** The header uses the horizontal `public_B` mark while the footer's
  `landing` variant maps to the square public SVG, rendering as a tiny partial
  mark and weakening brand continuity.
- **Recommendation:** Use one optimized, documented public brand lockup.
- **Suggested command:** `$impeccable polish`.

## Patterns and systemic issues

- Public and authenticated surfaces share personalization state even though
  their design responsibilities differ.
- Trust evidence is data-driven but does not have truthful failure/empty-state
  semantics.
- Assets are source exports rather than delivery assets sized for their actual
  use.
- Mobile layouts avoid overflow, but global compact scaling makes controls and
  supporting text smaller at the moment touch usability matters most.
- There is no `DESIGN.md` or home-page surface brief, so brand tokens, audience
  priority, proof rules, and responsive typography are not durable decisions.

## Positive findings

- Semantic landmarks, one H1, skip navigation, descriptive logo alt text, and
  visible focus treatment exist for the primary navigation and CTA.
- No horizontal overflow was measured at 320 or 390 px; sections stack cleanly.
- The partner animation honors `prefers-reduced-motion`.
- SEO title, description, canonical URL, Open Graph data, and JSON-LD are applied.
- The landing route is lazy-loaded; its production chunk is 11.96 kB / 4.19 kB
  gzip. The focused landing test passed and the production build succeeded.

## Recommended Impeccable sequence

1. **[P1] `$impeccable shape`** — decide the visitor hierarchy, shop/fleet
   conversion paths, proof rules, and replacement visual world before coding.
2. **[P1] `$impeccable clarify`** — make the value proposition and calls to
   action specific, truthful, and role-aware without fabricating claims.
3. **[P1] `$impeccable harden`** — separate partner loading/error/empty/populated
   states and add the missing state/accessibility tests.
4. **[P1] `$impeccable optimize`** — replace multi-megabyte logo exports and
   remove duplicate partner media work.
5. **[P1] `$impeccable typeset` + `$impeccable colorize`** — establish fixed
   public typography and an AA-safe brand palette independent of app settings.
6. **[P2] `$impeccable adapt`** — verify 320, 390, tablet, desktop, 200% zoom,
   keyboard order, and 44 px targets.
7. **[P2] `$impeccable distill`** — choose one partner proof pattern and remove
   redundant page weight.
8. **[P2] `$impeccable animate`** — add only purposeful, controllable motion
   after the static hierarchy works.
9. **[P3] `$impeccable polish`** — run the final bounded desktop/mobile craft
   pass, then re-audit.

Re-run `$impeccable audit` after implementation to measure the score again.
