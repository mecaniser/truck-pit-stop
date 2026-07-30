# Handoff: Customer Payment Page — "Payment-first" (option 1b)

## Overview
The customer-facing invoice payment page for a heavy-duty truck repair shop network (Truck Pit Stop). A fleet customer arrives from an emailed/SMS invoice link (or from their History list), sees what they owe, picks a payment method, and pays. Two methods: **Zelle** (no processing fee) and **Card via QuickBooks** (+$2.57 card processing fee).

**Build option `1b` ("Payment-first · total as hero")** — the middle column of the reference canvas. 1a and 1c are alternates kept for context; do not build them.

**Why 1b:** it is a checkout, not a workspace. Customers arrive on mixed devices (largely mobile) to do one thing. The single centered column is the same layout at every width — 1a's desktop side-rail would have to collapse into exactly this on mobile, so 1b is one layout instead of two. The amount due and the fee-saving choice sit above the fold.

Two details carried over from 1a into this spec: the **flat charge list** (no nested card-in-card) and the **trust line** under the CTA.

## About the Design Files
`Customer Payment.dc.html` is a **design reference authored in HTML** — a working prototype of look and behavior, not production code. It uses a custom streaming template runtime (`.dc.html` + `support.js`); **do not reuse that runtime**. Recreate the design in the target codebase's stack using its existing components and tokens. The 1b markup is inside `<div id="1b">…` (`data-screen-label="1b Payment first"`); the method/fee logic is the `pay()` method in the `class Component` block.

## Fidelity
**High-fidelity.** Match colors, sizes, spacing, and states closely. Where the codebase has design-system primitives (buttons, inputs, segmented control), use them while preserving intent: total as the largest element on the page, method choice visibly changing the amount, one unambiguous back control.

---

## THE NAVIGATION DECISION (implement this first — it applies app-wide)

The current page has **two competing back paths**: a breadcrumb (`‹ Dashboard / History`) and a separate back arrow next to the title. Resolve it with one rule:

1. **Delete the breadcrumb row entirely.**
2. **Dashboard is reachable only from the app logo / top nav** (top-left). It is never a second back affordance.
3. **One back control per page: a single labeled pill that names its destination** — `‹ History`. Placed top-left of the page content, above the title/hero. Label comes from the actual entry point:
   - navigated from History list → `‹ History`
   - opened from a dashboard widget → `‹ Dashboard`
   - opened from an emailed/SMS deep link (no in-app history) → **hide the pill** (there is nowhere to go back to); show nothing in its place.
4. Implement as one shared `<BackPill destination>` component so the label is always the truthful origin. Use the router's previous entry, falling back to History for invoice pages.

Result: one click back, one meaning, no duplicate navigation.

---

## Step-by-step implementation plan

### Step 1 — Page scaffold
- Page background `#10131c` (app frame). Reference frame 1280×760; in production the page fills the viewport and scrolls.
- **Top nav** (h 52px, bg `#0d1018`, bottom border `1px #1e2432`): left = logo (`TRUCK` 14px/900 italic `#e23b3b` + `PIT STOP` 9px/700 letter-spacing .28em `#8b92a5`) linking to Dashboard; right = 30px avatar circle (bg `#241f3d`, border `1px #8b7cf7`, initials 10px/800 `#c9bfff`).
- **Back pill row**: padding `16px 24px 0`. Pill: h 36px, padding 0 14px, radius 99px, bg `#191d2a`, border `1px #272d3d`, text 13px/700 `#c9cdd8`, content `‹ History`. (See navigation rule above.)
- **Content column**: centered, `width:640px; max-width:100%`, vertical flex, gap 16px, padding `10px 0 24px`. On viewports < 680px use full width with 16px side padding.

### Step 2 — Hero block (centered)
1. **Context line** (13px, `#8b92a5`, centered): `TPSW-2B45A36A-000014 · ` + unit in amber (`#d9a521`) `Unit #603` + status pill `invoiced` (11px/700, color `#a78bfa`, bg `rgba(167,139,250,0.12)`, border `1px rgba(167,139,250,0.35)`, radius 99px, padding 2px 9px).
2. **Total due** — the largest element on the page: 46px/800, `#eceef4`, letter-spacing -.02em, tabular-nums, margin-top 10px. **Value depends on the selected method** (Step 3).
3. **Fee line** directly under it, 13px, margin-top 4px:
   - Zelle selected → `No card fee with Zelle — you save $2.57` in teal `#2dd4bf`, weight 700.
   - Card selected → `Includes $2.57 card processing fee` in `#8b92a5`.
   Reserve the line's height so the layout does not shift when switching methods.

### Step 3 — Method selector (segmented, 2 options)
Row, gap 10px, each segment `flex:1 1 0`, h 56px, radius 12px, column-centered content, gap 3px, cursor pointer:
- **Selected:** bg `rgba(139,124,247,0.12)`, border `1px #8b7cf7`, text `#c9bfff`.
- **Unselected:** bg `#161a26`, border `1px #272d3d`, text `#8b92a5`.
- **Zelle segment:** line 1 `Zelle · $109.49` (14px/800), line 2 `NO FEE` (10px/700, `#2dd4bf`).
- **Card segment:** line 1 `Card · $112.06` (14px/800), line 2 `QUICKBOOKS` (10px/700, inherit at 70% opacity).
- Each segment always shows **its own** price so the cost of choosing is visible before selecting.
- Default selection: **Zelle** (cheaper for the customer). Selection is local UI state; nothing is charged until the CTA.
- Keyboard: arrow keys move between segments, Space/Enter selects; expose as `role="radiogroup"` with `aria-checked`.

### Step 4 — Primary CTA
Full-width button, h 54px, radius 13px, bg `#8b7cf7`, text `#0e1118` 15px/800. **Label states the method and amount:**
- Zelle → `Get Zelle details — $109.49`
- Card → `Pay $112.06 by card`

Behavior:
- **Zelle** → opens a panel/sheet with the shop's Zelle recipient, the exact amount, and the memo/reference (the RO id) with copy buttons, plus `I've sent it` to mark as pending-verification. No card form.
- **Card** → opens the QuickBooks card flow (hosted fields / redirect per the existing integration).
- Disabled + spinner while a payment is in flight; never allow double submit.

### Step 5 — Charge breakdown (below the fold, flat list — no nested cards)
One card: bg `#161a26`, border `1px #232939`, radius 14px, padding `16px 20px`.
- Header row: label `A/C SERVICE · CHARGES` (11px/800, letter-spacing .1em, `#8b92a5`) — service name is the customer concern — and right `⬇ Invoice PDF` link (12px/700, `#a78bfa`, hover `#c4b1ff`) downloading the invoice PDF.
- Rows (`space-between`, padding 9px 0, divider `1px #1e2432` between rows, none after the last): label 13px `#9aa1b3`, amount 13px `#eceef4` tabular-nums.
  `Labor / Services $100.00` · `Parts $0.00` · `Shop Supplies $2.90` · `Tax $6.59`
- **`Card Processing Fee $2.57` renders only when Card is selected** (own row, top border `1px #1e2432`).
- Do NOT repeat the total here — the hero owns it. Do NOT wrap this list in a second inner card (the flaw in the current design).

### Step 6 — Trust line
Centered, 11px, `#5c6375`: `🔒 Secure payment · Receipt emailed instantly`.

### Step 7 — Fee math (single source of truth)
Implement one function used by the hero, both segments, the breakdown, and the CTA:
```
subtotal 100.00 + shopSupplies 2.90 + tax 6.59 = 109.49        // Zelle total
cardFee = 2.57 (from shop settings: % and/or flat)              // card only
cardTotal = 109.49 + 2.57 = 112.06
```
- Never display a stale total; every amount derives from `selectedMethod`.
- The fee rate is shop-configurable (multi-tenant) — read from the shop's payment settings, not hard-coded.
- If a shop has Zelle disabled, render a **single** method (no segmented control) and drop the savings line. If card is disabled, likewise.

### Step 8 — States
- **Loading:** skeleton the context line, total, segments, CTA.
- **Already paid:** replace segments + CTA with a `Paid` confirmation block (amount, date, method, `⬇ Receipt`); keep the breakdown.
- **Payment pending (Zelle sent, unverified):** amber banner `Awaiting confirmation from the shop`; CTA becomes `View Zelle details`.
- **Failed card:** inline red error above the CTA, keep the entered method selected, allow retry.
- **Deep-link arrival:** no back pill (Step 4 of nav rule).
- Amounts never wrap; use tabular-nums everywhere.

### Step 9 — Responsive
- **≥ 680px:** centered 640px column exactly as specified.
- **< 680px:** full width, 16px side padding; total scales to ~38px; segments stay side-by-side (they are short); CTA becomes sticky to the bottom of the viewport once scrolled past, so it is always reachable while reading the breakdown.

### Step 10 — Verify against the reference
Open `Customer Payment.dc.html`, section **1b**. Click each method and confirm: hero total switches 109.49 ↔ 112.06, teal savings line ↔ gray fee line, `Card Processing Fee` row appears/disappears, CTA label and amount update, and no layout shift. Confirm one back pill and no breadcrumb.

---

## Design tokens
**Colors** — page/frame `#10131c`; top nav `#0d1018`; card `#161a26`; inset/segment-unselected `#161a26`, deeper inset `#12161f`; borders `#1e2432` (dividers), `#232939` (cards), `#272d3d` (controls); text primary `#eceef4`, secondary `#9aa1b3`, muted `#8b92a5`, faint `#5c6375`; brand violet `#8b7cf7` (tint `rgba(139,124,247,0.08–0.12)`, text-on-violet `#0e1118`, light text `#c9bfff`); status violet `#a78bfa`; success/no-fee teal `#2dd4bf` (tint `rgba(45,212,191,0.1)`, border `rgba(45,212,191,0.35)`); vehicle amber `#d9a521`; logo red `#e23b3b`.
**Type** — `'Helvetica Neue', Helvetica, Arial, sans-serif`; all money `font-variant-numeric: tabular-nums`; sizes 9 / 10 / 11 / 12 / 13 / 14 / 15 / 46 px; weights 600–800.
**Radii** — 16 frame, 14 cards, 13 CTA, 12 segments, 99 pills.
**Spacing** — content gap 16px; card padding `16px 20px`; row padding 9px 0; page padding `16px 24px`.
**Motion** — method switch is instant (no transition on totals — the number must read as authoritative); button hover brightness only.

## Sample data
RO `TPSW-2B45A36A-000014`, invoice `INV-2B45A36A-000034`, `2020 Volvo VNR · Unit #603`, July 24 2026, concern `A/C Service`, status `invoiced`. Labor $100.00, Parts $0.00, Shop Supplies $2.90, Tax $6.59, Card fee $2.57 → Zelle $109.49 / Card $112.06.

## Assets
None. Glyphs are Unicode (`‹ ⬇ 🔒`) — replace with the codebase's icon set (chevron-left, download, lock). Logo is styled text. If real Zelle / QuickBooks brand marks are required, source them from those brands' official brand kits and follow their usage rules.

## Files
- `README.md` — this spec.
- `Customer Payment.dc.html` — reference prototype; build section **1b** only.
