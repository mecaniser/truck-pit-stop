# Handoff: Price Builder Drawer — Redesign (Truck Pit Stop)

## Context
This is a **redesign of the Price Builder drawer** inside the Truck Pit Stop repair-order / invoicing app (internal, shop staff use). The current production drawer works but is **visually overcrowded**: it nests bordered cards 3–4 levels deep ("box-in-box") and splits one job — *adding work to the order* — across three separate input boxes. This handoff describes the redesigned drawer.

**The design file (`Price Builder Redesign.html`) is a static design reference** — 4 annotated screens on a pan/zoom canvas showing the target states. It is **not production code**. Recreate it in the app's existing stack (React/Vue/etc.) using established components, form/state libraries, and the money/number formatting already in the codebase. Wire it to the real repair-order API.

## The one big idea
**A repair order is a single list of line items, not a stack of boxes.** Each *line item* is a unit of work (an Operation, an hourly Diagnostic, or standalone Labor) that carries its own labor cost and its own list of parts. All existing complexity is preserved — hourly diagnostics, repair operations with book-time labor, per-part customer-vs-stock pricing, savings, labor/order discounts — but presented as one scannable, collapsible list.

---

## Fidelity
**High-fidelity.** Colors, type, spacing, and interaction states are specified below and in the HTML. Match it closely. It is a **light theme** with an orange gradient header (the drawer sits over the app; assume it slides in from the right at ~680px wide, but it should be fluid/responsive down to a narrower width).

---

## Six design moves (what changed and why)
1. **Merge the three add-boxes** → Diagnostics, Repair Operation, and Services & Labor become **one line-item list** fed by **one smart add bar**.
2. **Collapse by default** → each operation renders as a **one-line summary**; expand only the one being edited (progressive disclosure).
3. **Hairlines, not nested cards** → dividers + indentation replace box-in-box. **The drawer is the only card.**
4. **Anchored price editing** → the customer-vs-stock unit-price editor is a **popover anchored to the price cell** (never a tooltip floating over the table, as it does today).
5. **Sticky totals footer** → a persistent, scannable breakdown + the primary action. Discounts move into a single popover instead of a cramped inline row.
6. **Context in the header** → customer + truck chips live in the header; the old "Customer & Vehicle" and "Recommended Services" boxes collapse to slim one-line rows.

---

## Anatomy (top → bottom)

### Header (orange gradient)
- Eyebrow "REPAIR ORDER" + RO number (`#RO-F90D5493-000054`, Barlow Condensed 800).
- Right cluster: prev/next arrows, `1 / 50` pager (mono), close ✕. All in translucent-white icon buttons.
- Meta row of chips: **status pill** ("Quoted", light-blue on white) + ghost chips for **customer** (Elis Logistica) and **truck** (TPS-118 · Freightliner Cascadia). This is the "context in the header" move.

### Workflow strip
Slim single row on a warm off-white band: `✓ Draft ready → [Send] → Approved → Technician`, with the current step as a filled orange badge, completed steps green, future steps muted. Right-aligned mono quote number (`Q-…`).

### Body — "Work & Labor" list
Section label `WORK & LABOR` + count pill (`3 lines`).

**Collapsed line item (`.li` default):**
`[chevron] [type icon] Name [type tag] · sub-line · ................ Line total`
- **Type icon + tag:** Operation (wrench, orange tint) / Hourly diagnostic (gauge, blue tint) / Labor / Part.
- **Sub-line** summarizes contents: `1.50 hr labor · 4 parts · saves $56.97` for an operation; `1.00 hr @ $100.00/hr · shop rate, no flat fee` for a diagnostic.
- **Line total:** Barlow Condensed 800, with an optional tiny mono breakdown beneath (`150 labor · 273 parts`).
- Rows separated by **hairline top-borders only** — no per-row card.

**Expanded line item (`.li.open`):** chevron rotates 90°; body reveals, indented ~60px under the name:
- **Labor row** — a single soft-grey pill: `LABOR [1.50 hr] × [$100.00 /hr] = $150.00`. The two boxed values are inline-editable mini-fields (mono).
- **Parts table** — flat, full width, header row `Part | Qty | Unit | Savings | Line`, then one hairline-separated row per part:
  - Part name + mono SKU beneath.
  - Qty (mono, centered).
  - **Unit price** = a button (`$16.50 ⌄`) that opens the **price popover** (below). When a custom customer price is set, the button gets an orange ring.
  - **Savings** — green `−$49.50` when customer price beats list, else muted `—`.
  - **Line** total (mono).
  - `+ Add part to this operation` (dashed ghost button) at the end.

### Unified add bar (collapsed state)
A dashed-border bar below the list: a **segmented type selector** (`Operation | Diagnostic | Part | Labor`) + a search input (`Add work — search operations, e.g. brake change, EGR…`). Focusing/typing opens the **command palette**.

### Command palette (add flow — screen 3)
A bordered, shadowed panel:
- Search input at top with `↵ to add` hint.
- **Grouped results**: "Repair operations", "Diagnostics · hourly", "Parts". Each result: type icon, name, mono meta (`3.5 hr book time · 6 parts bundled` / `$100.00/hr` / `SKU · 12 in stock`), a right-aligned price (`from $780.00` / `est. 0.5 hr` / `cust. $142.00`), and a `+` add button. Keyboard-selectable (selected row gets an orange inset bar + tinted bg).
- Helper line: operations arrive with book-time labor and parts pre-bundled.

### Collapsed context rows
Two slim rows (icon + label + value + chevron/plus): **Customer & Vehicle** (shows customer · unit · year/make/model · VIN tail) and **Recommended Services** (empty → "add from inspection" link).

### Sticky totals footer
Pinned to the bottom of the drawer:
- **Breakdown chips** row: `Parts $340.03` (blue) · `Labor $330.00` (orange) · `Discounts −$60.00` (red) · `Customer saves $56.97` (green), then a `Discounts & pricing` button (opens the discount popover) pushed to the right.
- **Main row:** left = `Recalculate` ghost button; right = `ORDER TOTAL` label + big total (Barlow Condensed 800, 34px) + primary **Send quote** button (orange, paper-plane icon).

### Danger zone
A slim red-tinted collapsible bar at the very bottom (not a big card).

---

## Popovers (screen 4)

### Unit-price editor (anchored to a price cell)
Small card, header = part name + ✕. Rows:
- `● Stock cost  $23.94` (grey dot, muted value)
- `List price  $27.00`
- `Margin at this price  +16.5%` (green badge — recompute live as the price changes: `(customer − stock) / customer`)
- **`● Customer price  [$16.50]`** — highlighted edit row, orange dot, bordered input (the field being set).
- Footer: `Reset to list` (ghost) + `Apply` (primary).

### Discounts & pricing editor
Card, header + ✕. Rows:
- **Parts pricing** (select): `Customer price | Stock + 20% | List price` — applies a pricing mode to *every* part at once (this is the old "Set all…" control, given room).
- **Labor discount** — `$` money input.
- **Order discount** — `$` money input.
- Footer: live `Customer saves $56.97` readout + `Apply`.

---

## Interactions & behavior
- **Expand/collapse** a line item on row click (chevron rotates). Multiple can be open; clicking the header again collapses.
- **Add flow:** add bar / segmented type → command palette → selecting a result appends a new line item (operations pre-fill labor book-time + bundled parts; you then tune).
- **Inline edit:** labor hrs, labor rate, part qty edit in place. Unit price edits via the anchored popover.
- **Pricing math:**
  - Part line total = `qty × customerUnitPrice`.
  - Part savings = `qty × max(0, listPrice − customerUnitPrice)` (green when > 0).
  - Operation total = labor (`hrs × rate`) + Σ part line totals.
  - Diagnostic total = `hrs × shopRate` (no parts, no flat fee).
  - Footer Parts = Σ all part line totals; Labor = Σ all labor; Discounts = labor discount + order discount; Total = Parts + Labor − Discounts; "Customer saves" = Σ part savings + discounts.
  - **Recalculate** re-runs the whole rollup (e.g. after a bulk "Parts pricing" mode change).
- **Persistence:** the real drawer edits a repair-order record via API; debounce/save on change, and keep the footer total live.
- **Responsive:** at narrow widths the parts-table columns tighten (Qty/Savings can hide first); the footer breakdown chips wrap; keep the total + Send quote always visible.
- **Empty state:** zero line items → the add bar/command palette is the focus with a "Start by adding an operation, diagnostic or part" prompt.

---

## Data model (shape the UI binds to)
```
repairOrder {
  id, roNumber, quoteNumber, status: "quoted" | ...,
  customer { id, name }, vehicle { unit, year, make, model, vin },
  workflow: [ { key, label, state: "done"|"active"|"todo" } ],
  lineItems: [
    { id, type: "operation" | "diagnostic" | "labor",
      name,
      labor: { hours, rate },                 // rate = shop hourly
      parts: [ { id, name, sku, qty,
                 unitPrice,   // customer price (editable)
                 stockCost, listPrice,
                 lineTotal, savings } ]        // derived
    }
  ],
  pricing: { partsMode: "customer"|"stockPlus20"|"list",
             laborDiscount, orderDiscount },
  totals: { parts, labor, discounts, customerSaves, total }  // derived
}
```
Operation catalog (for the command palette) provides: name, bookTimeHours, bundled part SKUs + default qty, category. Parts catalog provides: name, sku, stockQty, stockCost, listPrice.

---

## Design tokens

**Fonts:** Barlow Condensed (800) for RO number, line totals, order total, section headings; Archivo (400–700) for UI/body; JetBrains Mono for SKUs, quantities, prices, rates, pager.

**Colors:**
| Token | Hex | Use |
|---|---|---|
| header gradient | `#f7a823 → #e07c05` | drawer header (100° linear) |
| `--brand` | `#ef8a12` | primary buttons, active accents |
| `--brand-dk` | `#d4770a` | primary hover, links |
| `--ink` | `#1b1f24` | headings, order total |
| `--text` | `#20242b` | body text |
| `--muted` | `#6b7280` | secondary text |
| `--muted2` | `#9aa1ab` | labels, tertiary |
| `--line` | `#e9ebef` | hairline dividers/borders |
| `--line2` | `#dcdfe5` | input/button borders |
| `--field` | `#f5f6f8` | soft input/labor-row fill |
| `--blue` | `#2563eb` | Parts total, diagnostic accent |
| `--orange-a` | `#ea6a05` | Labor total, operation accent |
| `--green` | `#159a52` | savings, "customer saves", done steps |
| `--red` | `#dc2626` | discounts, danger zone |

Type tints use `color-mix(... 12–16%, transparent)` or the light hex tints in the CSS (`#fff4e6` operation, `#eaf1fe` diagnostic, `#eef7f0` part).

**Radii:** drawer 18px; cards/popovers 13–14px; buttons/inputs/segments 8–11px; pills 999px; icon tiles 8–9px.
**Spacing:** drawer body padding 20–24px; line-item row padding 14px; expanded indent ~60px; control height 44px (footer), 36–40px (inline).
**Shadows:** drawer `0 22px 60px rgba(20,25,35,.18)`; popovers/palette `0 10px 30px rgba(20,25,35,.10)`; primary button `0 6px 16px rgba(239,138,18,.32)`.

---

## Assets
- **No raster assets.** All icons are inline stroke SVGs (wrench, gauge, box, search, chevrons, plus, truck, building, send/paper-plane, refresh, alert). Swap for the codebase's icon set (Lucide matches this style).
- Fonts via Google Fonts in the reference; self-host in production.

## Files in this bundle
- `Price Builder Redesign.html` — the 4-screen annotated design reference (open in a browser; pan/zoom canvas). Screens: ① line-item overview + sticky footer, ② operation expanded (labor + parts inline), ③ unified add / command palette, ④ anchored price + discount popovers. A legend panel up top lists the six design moves.
- `current-drawer.png` — screenshot of the **existing** production drawer, for before/after reference.

## Build order (suggested)
1. Drawer shell + header + workflow strip + sticky footer scaffold.
2. Line-item list with collapse/expand (start with static data).
3. Expanded operation: inline labor row + flat parts table.
4. Pricing math + live footer totals.
5. Unit-price popover + discounts popover.
6. Command palette add flow wired to the operation/part catalogs.
7. Responsive passes + empty state.
