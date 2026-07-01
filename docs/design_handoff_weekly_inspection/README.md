# Handoff: Weekly Truck Inspection — "Pass-first" flow (option 1c)

## Overview
A weekly DOT-style pre-trip / safety inspection form for a fleet-management app. An inspector walks a truck (Freightliner Cascadia, "Unit 4471"), marks 12 checks across 6 categories as **Pass / Fail / N-A**, records the odometer, and submits. The screen is optimized for a **fast, one-handed, gloved, outdoor** workflow. This package documents the **1c "Pass-first"** direction: a big green PASS target with small Fail/N-A buttons, and category sections that auto-collapse to a green summary once complete so the inspector only sees what's left.

Two other directions (1a compact toggles, 1b traffic-light + auto-advance) exist in the same reference file for context but are **not** the ones to build.

## About the Design Files
The files in this bundle are **design references authored in HTML** — a working prototype showing intended look and behavior. They are **not production code to copy directly**. The task is to **recreate this design in the target codebase's existing environment** (React, Vue, SwiftUI, Flutter, native, etc.) using that project's established components, tokens, and patterns. If no environment exists yet, pick the most appropriate framework for the product and implement it there.

The prototype is built as a single streaming "Design Component" (`.dc.html`) with a custom template runtime — **do not** try to reuse that runtime. Read it for layout, measurements, colors, copy, and interaction logic only.

## Fidelity
**High-fidelity.** Final colors, typography, spacing, sizing, states, and interactions are specified below and are intended to be reproduced closely. Match the hex values, sizes, and behaviors. Where the target app has an existing design system, prefer its equivalents (e.g. its own button/input primitives) while preserving the intent (target sizes, three states, pass-first hierarchy).

---

## Screens / Views

### 1. Weekly Inspection (single scrolling screen)
**Purpose:** Complete all 12 checks, log odometer, submit.

**Frame:** Prototype is drawn in a fixed `432 × 856px` phone frame. In production this is a **responsive full-screen view** (see Responsive below).

**Vertical structure (3 regions):**
1. **Sticky header** (does not scroll)
2. **Scrollable body** (the checklist + odometer)
3. **Sticky footer** (status line + primary CTA)

Root container: `display:flex; flex-direction:column; height:100%; background:#0c0e0d; border:1px solid #242927; border-radius:22px` (the border/radius are frame chrome — in a real full-screen view drop them and let it fill the viewport).

---

#### Header (sticky)
- Padding `15px 16px 13px`, background `#0f1211`, bottom border `1px solid #1e2320`.
- **Row 1 — brand + voice:**
  - Left: a `26×26px`, `border-radius:7px`, `background:#f5a623` square containing a `✓` glyph (`color:#0c0d0c; font-weight:900; font-size:15px`). Beside it, two lines:
    - Title `WEEKLY INSPECTION` — `14px / 800 / letter-spacing .06em / #f4f5f3`.
    - Subtitle `Unit 4471 · Freightliner Cascadia` — `11px / #7c827d`, margin-top 2px.
  - Right: **Voice** pill button. Default: `height:30px; padding:0 11px; border-radius:99px; border:1px solid #2a2f2b; background:transparent; color:#8b918d; font-size:10px; weight:800; letter-spacing:.06em`, content `● VOICE`. Active (listening) state: `background:#f5a623; border-color:#f5a623; color:#0c0d0c`.
- **Row 2 — progress bar** (margin-top 13px, flex row, gap 12px):
  - Track: `flex:1; height:7px; border-radius:99px; background:#1c211e; overflow:hidden`.
  - Fill: `height:100%; background:#43b25f; border-radius:99px; width:<done/12 %>; transition:width .25s ease`.
  - Count: `<done>` in `#f4f5f3` + `/12` in `#5a605b`, `13px / 800`, tabular-nums.
- **Row 3 — bulk actions** (margin-top 11px, flex row, gap 8px):
  - **Mark all pass** (flex:1): `height:38px; border-radius:9px; background:rgba(67,178,95,0.12); border:1px solid rgba(67,178,95,0.35); color:#43b25f; font:12px/800; letter-spacing:.03em`, content `✓ MARK ALL PASS`.
  - **Reset** (`40×38px`): `border-radius:9px; background:#141817; border:1px solid #262b27; color:#8b918d; font-size:16px`, content `↺`.

#### Body (scrollable)
`flex:1; overflow:auto; padding:8px 15px 16px`. Custom scrollbar: 8px wide, thumb `#262b27`, transparent track.

- **Voice banner** (shown only while listening): margin `6px 0 2px`, padding `10px 12px`, `border-radius:10px; background:rgba(245,166,35,0.1); border:1px solid rgba(245,166,35,0.3)`. Contains an 8px `#f5a623` dot pulsing (opacity 1→.2→1 over 1s, `blink` keyframe) + text `Listening — say "pass", "fail", or "skip"` in `12px / 600 / #f0b959`.

- **Category section** (repeated per category; margin-top 11px; `border:1px solid #20251f; border-radius:14px; overflow:hidden`):
  - **Section header** (clickable, toggles collapse): `display:flex; justify-content:space-between; align-items:center; padding:13px 14px; cursor:pointer; user-select:none`.
    - Incomplete: `background:transparent; color:#8b918d`.
    - Complete: `background:rgba(67,178,95,0.08); color:#43b25f`.
    - Left: category name uppercase — `11px / 800 / letter-spacing .09em` (inherits header color).
    - Right: **summary** — `11px / 800`, tabular-nums:
      - Incomplete → `"<done>/<total>"` in `#565b57`.
      - Complete, no flags, no N-A → `"All passed ✓"` in `#43b25f`.
      - Complete with N-A → `"<passCount> pass · <naCount> N/A"` in `#43b25f`.
      - Complete with any Fail → `"<failCount> flagged"` in `#e5545a`.
  - **Section body** (only rendered when section is expanded): padding `8px 10px 10px`, flex column, gap 8px. Contains one **item row** per check.

- **Item row** (`padding:10px 11px; background:#141817; border:1px solid #20251f; border-radius:12px`):
  - Label: `14px / 600 / #e9ebe7 / line-height 1.2`, margin-bottom 9px.
  - Button row (flex, gap 8px) — **the pass-first control**:
    - **PASS** (big, `flex:1 1 0; height:50px; border-radius:12px; gap:8px; font:14px/800; letter-spacing:.04em`), content `✓ PASS`.
      - Inactive: `background:rgba(67,178,95,0.1); color:#43b25f; border:1px solid rgba(67,178,95,0.35)`.
      - Active: `background:#43b25f; color:#08110c; border:1px solid #43b25f`.
    - **Fail** (`50×50px; border-radius:12px; font-size:17px`), content `✕`.
      - Inactive: `background:#0f1211; color:#6b716d; border:1px solid #262b27`.
      - Active: `background:rgba(229,84,90,0.16); color:#e5545a; border:1px solid rgba(229,84,90,0.55)`.
    - **N-A** (`50×50px; border-radius:12px; font-size:17px`), content `–`.
      - Inactive: same as Fail inactive.
      - Active: `background:rgba(154,160,155,0.14); color:#9aa09b; border:1px solid rgba(154,160,155,0.4)`.
  - **Flag panel** — rendered **only when the item's status is Fail** (margin-top 10px, flex column, gap 8px):
    - Note input: `height:40px; border-radius:9px; background:#0f1211; border:1px solid #3a2a2b; color:#f4f5f3; font-size:13px; padding:0 12px`, placeholder `"What's wrong? (quick note)"`.
    - Add-photo button (self-start): `height:34px; padding:0 12px; border-radius:8px; background:#1a1412; border:1px dashed #5a4a3a; color:#e0a56b; font:12px/700`, content `+ Add photo`. After a photo is attached, label becomes `+ Photo attached`.

- **Odometer block** (margin-top 18px):
  - Previous-reading card: `padding:12px 14px; background:#141817; border:1px solid #20251f; border-radius:12px`, flex space-between. Left label `PREVIOUS ODOMETER` (`10px/800/letter-spacing .09em/#7c827d`); right value `586,230 mi` (`#e9ebe7`) + `· Jul 1` (`#6a706b`), 13px, tabular-nums.
  - Field label `NEW ODOMETER (MI)` — `10px/800/letter-spacing .09em/#7c827d`, margin-top 10px.
  - Input: `height:46px; border-radius:11px; background:#0f1211; border:1px solid #262b27; color:#f4f5f3; font-size:15px; padding:0 14px`, tabular-nums, placeholder `"Enter current reading"`, numeric keyboard (`inputmode="numeric"`).

#### Footer (sticky)
`padding:12px 14px; background:#0f1211; border-top:1px solid #1e2320`.
- **Status line** (centered, `11px / #8b918d`, margin-bottom 9px):
  - `done < 12` → `"<12-done> checks remaining"`.
  - all done, ≥1 fail → `"<n> item(s) flagged — ready to review"`.
  - all done, no fail → `"All clear — ready to submit"`.
- **Primary CTA**: `width:100%; height:52px; border-radius:13px; background:#f5a623; color:#0c0d0c; font:15px/800; letter-spacing:.02em`, centered, content `✓ Review & complete`.

---

## Interactions & Behavior
- **Tap PASS / Fail / N-A** sets that item's status. Tapping the **already-active** status again clears it (toggle back to un-inspected).
- **Auto-collapse:** when the last item in a category gets a status (section becomes complete), that section auto-collapses to its summary line — *unless the user has manually toggled that section*, in which case respect their choice. If a completed section later becomes incomplete (status cleared), it auto-expands.
- **Manual collapse:** tapping a section header toggles it open/closed and marks it as user-controlled.
- **Mark all pass:** sets every item to Pass and collapses all sections; clears the "user-controlled" flags. **Reset** clears all statuses, notes, photos, and collapse state.
- **Flag reveal:** setting an item to Fail reveals the note + add-photo controls inline. Clearing Fail hides them (note text may be preserved in state but is hidden).
- **Voice toggle:** toggles a listening banner. In the prototype this is a visual affordance only — in production wire it to the platform speech API; recognized "pass/fail/skip" should apply to the current/next un-inspected item.
- **Progress bar** animates width over `.25s ease` as items are completed.
- **Transitions:** buttons have no elaborate animation; keep state changes instant except the progress fill and (optionally) a section expand/collapse height transition.

## State Management
Per inspection instance:
- `items: Record<itemId, { status: 'pass'|'fail'|'na'|null, note: string, photo: boolean }>` — 12 items (see Data below).
- `collapsedSections: Record<categoryId, boolean>`
- `userToggledSections: Record<categoryId, boolean>` — so auto-collapse doesn't override manual intent.
- `listening: boolean`
- `odometer: string` (numeric input; validate ≥ previous reading, 586,230, on submit).

Derived: `doneCount`, `failCount`, per-section `done/total/complete`, progress `%`, status line text, CTA enablement (optionally require all 12 + odometer before enabling submit).

## Design Tokens
**Colors**
- Canvas / app bg: `#080a09`
- Panel bg: `#0c0e0d`; header/footer bg: `#0f1211`; row bg / inactive small buttons: `#141817` / `#0f1211`
- Borders: `#242927` (frame), `#20251f` (rows), `#262b27` (inputs), `#1e2320` (header divider)
- Text: primary `#f4f5f3` / `#e9ebe7`; muted `#8b918d` / `#9aa09b`; faint `#7c827d` / `#6a706b` / `#565b57`
- Brand amber: `#f5a623` (on-amber text `#0c0d0c`)
- Pass green: `#43b25f`; tint `rgba(67,178,95,0.1–0.16)`; border `rgba(67,178,95,0.35–0.55)`; on-green text `#08110c`
- Fail red: `#e5545a`; tint `rgba(229,84,90,0.16)`; border `rgba(229,84,90,0.55)`
- N-A gray: `#9aa09b`; tint `rgba(154,160,155,0.14)`; border `rgba(154,160,155,0.4)`
- Flag panel accents: input border `#3a2a2b`; photo btn bg `#1a1412`, dashed border `#5a4a3a`, text `#e0a56b`

**Typography**
- Family: `'Helvetica Neue', Helvetica, Arial, sans-serif`. Numeric readouts use `font-variant-numeric: tabular-nums`.
- Sizes/weights used: 10/800 (labels), 11/800 (section + summary), 12/800 (bulk btns), 13/600 (note), 14/600 (item label), 14/800 (PASS), 15/800 (CTA/title-ish), 15 (inputs), 16–17 (glyph buttons).

**Radii:** 22 (frame), 14 (section), 12 (row / small buttons), 11 (odo input), 10 (banner), 9 (bulk btn / note input), 8 (photo btn), 7 (brand square), 99 (pills / progress).

**Spacing:** section gap 8px; body padding `8px 15px 16px`; header padding `15px 16px 13px`; row padding `10px 11px`.

**Target sizes (accessibility):** PASS 50px tall; Fail/N-A 50×50; bulk buttons 38px; CTA 52px; odo input 46px. Keep all interactive targets ≥ 44px for gloved use.

**Motion:** progress fill `width .25s ease`; voice dot `blink` keyframe (opacity 1→.2→1, 1s infinite).

## Data (12 checks, 6 categories)
- **Brakes:** Air brake system / lines · Brake pads & rotors
- **Fluids:** Coolant level · Engine oil level · Leaks under vehicle
- **Lights:** Brake & marker lights · Headlights & turn signals
- **Safety:** Horn, wipers & mirrors · Seatbelts & fire extinguisher
- **Steering:** Steering & suspension play
- **Tires:** Tire pressure · Tread depth & wear

## Responsive behavior
Target devices: **phone + tablet**.
- **Phone (≤ ~600px):** single column exactly as documented; header and footer sticky, body scrolls.
- **Tablet (≥ ~768px):** widen the content; lay category sections out in a **2-column grid** to cut scrolling, keep header/footer full-width, and consider docking the odometer + status/CTA in a right-hand rail. Increase touch targets slightly. The prototype's fixed 432px frame is for the comparison board only — do not hard-code it.

## Assets
No image or icon-font assets. All glyphs are Unicode text (`✓ ✕ – ↺ ● +`) — replace with the codebase's icon set (e.g. check, x, minus, refresh, mic, camera/plus) as appropriate. The Freightliner unit name and odometer values are placeholder sample data.

## Files
- `Weekly Inspection.dc.html` — the HTML reference prototype. Contains all three explored directions side by side; **build option `1c` (the third column, "Pass-first · sections auto-collapse")**. Its logic lives in the `class Component` block: `buildC()`, `cPass()`, `cSmall()`, `setStatus()`, `markAllPass()`, `toggleCollapse()`, and `progressOf()` are the functions that define 1c's behavior.
