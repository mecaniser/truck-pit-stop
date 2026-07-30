# Handoff: Customer Portal — full redesign (6 screens)

## Overview
The customer-facing portal of a multi-tenant heavy-duty truck repair network (Truck Pit Stop). Users are fleet owner-operators (1–20 trucks) who log in to see what they owe, pay invoices, book services, and pull service history for compliance. This package redesigns the whole portal: **Dashboard, Services, Appointments, Vehicles, History, Account** — plus the previously-specified **Payment page** (see `design_handoff_customer_payment/`, option 1b, still valid and unchanged).

Reference file: `Customer Portal.dc.html`, section `1a`. It is one interactive prototype — **click the top nav to switch between all six screens**.

## About the Design Files
Both `.dc.html` files are **design references authored in HTML** — working prototypes of look and behavior, not production code. They use a custom streaming template runtime (`.dc.html` + `support.js`); **do not reuse that runtime**. Recreate the design in the target codebase's stack using its existing components. Read the prototype for layout, measurements, colors, copy, and logic. Screen markup is inside `<sc-if value="{{ isDash }}">`, `isServices`, `isAppts`, `isVehicles`, `isHistory`, `isProfile` blocks; data and style helpers live in the `class Component` block.

## Fidelity
**High-fidelity.** Match colors, sizes, spacing, and states closely. Where the codebase has design-system primitives, use them while preserving intent — especially the information hierarchy changes, which are the point of this redesign.

---

## What was wrong with the current portal (the brief)

Fix these five systemic problems; every screen decision below follows from them.

1. **Inconsistent chrome.** The top nav renders **light gray on Appointments / Vehicles / Account and dark on Dashboard / Services / History**. One dark shell everywhere.
2. **Three competing accent colors** with no rules — amber (Services, Appointments, Account), violet (History, Payment), green (Pay Now buttons). One accent system (below).
3. **Duplicate navigation.** Every page shows a breadcrumb (`‹ Dashboard / X`) *and* the top nav already contains those destinations. Breadcrumbs are deleted portal-wide; the top nav is the only navigation. A single labeled back pill appears **only on detail pages** that aren't in the nav (invoice/RO detail) — see the navigation rule in the payment handoff.
4. **The dashboard buries the only number that matters.** 8 unpaid invoices totalling **$1,127.00**, every one **past due** — and the total appears nowhere. The stat strip spends prime real estate on "Total Orders 14" while showing 8 identical small *Pay Now* buttons and rendering overdue dates in neutral gray.
5. **Repetition instead of structure.** The Services table repeats "Vehicle required" on all 20 rows (the customer has exactly one truck) and uses emoji as icons; Appointments shows two competing book CTAs; the Vehicles page shows a VIN and nothing actionable; Account wraps 4 read-only fields in a huge empty card behind an "Edit Profile" button.

---

## The design system (apply to all screens)

**Color roles — one meaning each, no exceptions**
- **Violet `#8b7cf7`** = primary action / current nav state. Text-on-violet `#0e1118`; light text `#c9bfff`; tint `rgba(139,124,247,0.12)`; link `#a78bfa`, hover `#c4b1ff`.
- **Green `#3ecf6f`** = money already collected (paid badges, paid totals). Tint `rgba(62,207,111,0.1)`, border `rgba(62,207,111,0.3)`. Never used for buttons — a green *Pay Now* button next to green *paid* badges is the current ambiguity.
- **Red `#ff6b6e`** (light text `#ff8b8d`) = overdue / owed. Tint `rgba(255,107,110,0.1)`, border `rgba(255,107,110,0.3)`.
- **Amber `#f0b959`** = warning / due soon. Tint `rgba(245,166,35,0.1)`.
- **Vehicle amber `#d9a521`** = vehicle identity text only (unit, plate, model line). Never a control.
- **Teal `#2dd4bf`** = fee-free / savings (Zelle).
- **Logo red `#e23b3b`** = brand mark only.

**Surfaces** — page/frame `#0d1018`; nav `#0a0d14`; card `#161a26`; inset/row `#12161f`; borders `#1e2432` (dividers), `#232939` (cards), `#272d3d` (controls); ring on hover `#343b52`.
**Text** — primary `#eceef4`; secondary `#9aa1b3`; muted `#8b92a5`; faint `#5c6375`.
**Type** — `'Helvetica Neue', Helvetica, Arial, sans-serif`. Page title 24/800 (-.01em); hero number 42/800 (-.02em); card title 14–18/800; body 13; meta 11–12; section label 10–11/800 letter-spacing .09–.1em uppercase. **All money and mileage `font-variant-numeric: tabular-nums`.**
**Radii** — 16 cards/frame, 14 sub-cards, 12 tiles, 11 rows, 9–10 buttons/inputs, 99 pills.
**Controls** — nav item h34 r9; pill/filter h34 r99; row button h34 r9; primary button h42–46 r11–12; input h44 r10.
**Density** — page padding `22px 24px 26px`; card gap 14–16px; row gap 6px; row padding `10–12px 14–16px`.
**States** — row hover: border `#343b52`, bg `#161b26`. Focus: 2px violet ring. No decorative animation.

**Shell (every screen)**
Nav h56, bg `#0a0d14`, bottom border `1px #1e2432`. Left: logo (`TRUCK` 15/900 italic `#e23b3b` + `PIT STOP` 9/700 tracking .28em `#8b92a5`) → Dashboard. Right: nav items `Dashboard · Services · Appointments · Vehicles · History` (active = violet tint bg + `#c9bfff`), then a 32px avatar circle (bg `#241f3d`, border `1px #8b7cf7`, initials `#c9bfff`) → **Account** (the account page is reached only via the avatar, not the nav). Content area scrolls under the fixed nav. **No breadcrumbs anywhere.**

---

## Screen 1 — Dashboard (money-first)

Order of the page = order of the customer's questions: *what do I owe → what's my truck's status → what's late → what did I pay.*

### 1.1 Balance hero (top-left, `flex:1.4`)
Card bg `#161a26`, **border `1px rgba(255,107,110,0.3)`** (red only while a balance is past due; `#232939` when current).
- Eyebrow: 7px red dot + `BALANCE DUE · ALL PAST DUE` (11/800, tracking .1em, `#ff8b8d`). When nothing is overdue: `BALANCE DUE` in `#8b92a5`.
- **Amount: `$1,127.00`** at 42/800, tabular-nums, with `across 8 invoices` (13, `#8b92a5`) baseline-aligned beside it.
- Sub-line: `Oldest unpaid: 3 days past due · Jul 21` (12, `#9aa1b3`).
- Actions (bottom of card): primary **`Pay all — $1,127.00`** (h46, r12, violet) → payment page with all invoices selected; secondary **`Pay oldest first`** (h46, r12, bg `#191d2a`, border `#272d3d`) → payment page with the oldest invoice selected.
- Zero-balance state: green check eyebrow `ALL PAID UP`, amount `$0.00`, sub-line = next PM due, single secondary action `Book a service`.

### 1.2 Status tiles (top-right, `flex:1`, 2×2 grid, gap 10)
Each: bg `#161a26`, border `#232939`, r14, padding `14px 16px`, label 10/800 tracking .09em `#8b92a5`, value 14/800, meta 11 `#8b92a5`.
`MY TRUCK` → Volvo VNR / Unit #603 · 589,745 mi (unit line in `#d9a521`) · `NEXT PM DUE` → `in 1,255 mi` in amber / `Level A · ~591,000` · `IN THE SHOP` → `Nothing today` / `0 active repairs` · `PAID YTD` → `$1,617.50` in green / `6 of 14 orders`.
**Removed from the old strip:** "My Vehicles 1", "Completed 6", "Total Orders 14" as standalone cards — vanity counts that answer nothing. (Counts survive as meta text.)

### 1.3 Unpaid invoices (replaces "Action Required")
Card, header row (padding `15px 18px`, bottom border `#1e2432`): `UNPAID INVOICES` (12/800 tracking .1em) + `8 past due` (12/800, `#ff8b8d`); right: `Sorted by days overdue` (12, `#8b92a5`) + **`Select & pay`** button (h34, violet tint bg, border `#8b7cf7`, text `#c9bfff`) which turns rows into checkbox multi-select and swaps the header for `n selected · $total` + `Pay selected`.
Rows (padding `10px 14px 10px 18px`, bg `#12161f`, border `#1e2432`, r11, relative):
- **Aging edge bar** absolute left, 4px, full height: amber `#f0b959` at 1–2 days, red `#ff6b6e` at ≥3 days.
- Left block (w210): RO id 13/700 + service name 11 `#8b92a5`.
- Middle: **days-overdue badge** — `3 days past due` (11/800, r6, padding 3px 8px, amber or red tone by the same threshold). This replaces the current gray `Invoice sent … Due Jul 22` string: the customer needs *lateness*, not send timestamps.
- Right: amount 14/800 tabular-nums (w84, right-aligned) + **`Pay`** button (h34, r9, violet).
- **Sort: most overdue first.** The current screen sorts by id, which buries the oldest debt.
- One threshold function `overdueLevel(days) → none | warn(1–2) | critical(≥3)` drives edge bar + badge; reuse it everywhere.

### 1.4 Recently paid
Card with header `RECENTLY PAID` + `View all history →` (violet text button). Rows: RO id (w210, 13/700), service list (12, `#8b92a5`, ellipsis), `PAID` badge (green tone, 10/800), amount (w84, 14/800). Max 3 rows.

---

## Screen 2 — Services ("Book a service")

- **Header:** title `Book a service` (24/800) + subtitle `All services are performed on 2020 Volvo VNR · Unit #603 — no need to pick a vehicle.` — this single line **replaces the "Vehicle required" note repeated on all 20 rows**. (With 2+ vehicles: show a vehicle selector here, once, not per row.)
- **Search field** (h40, r10, bg `#161a26`, border `#272d3d`, w250) filtering by name/description.
- **Category filter pills** (h34, r99): `All 20 · PM Services 4 · Brakes 4 · Inspections 4 · Tires 3 · Other services 4`, each with its count; active = violet tint + `#8b7cf7` border.
- **Grouped list, not a flat table.** For each category: header = color dot (PM violet `#8b7cf7`, Brakes red `#ff6b6e`, Inspections green `#3ecf6f`, Tires amber `#f0b959`, Other teal `#2dd4bf`) + name (11/800 tracking .1em) + **price range** (11, `#5c6375`, e.g. `$189 – $699`). Items in a **2-column grid** (gap 8), sorted by price ascending inside each group.
- **Service row** (bg `#161a26`, border `#232939`, r12, padding `12px 14px`): name 13/700 + description 11 `#8b92a5` (one line, ellipsis) · right block: price 14/800 tabular-nums + duration 11 `#5c6375` · **`Book`** button (h34, violet tint, border `#8b7cf7`).
- **Delete** the emoji icon column and the List/Cards toggle (two views of the same 20 rows is a maintenance cost with no user gain). If a visual browse mode is wanted later, make it a per-category hero, not a duplicate list.
- `Book` opens the scheduling flow (date/time + notes) prefilled with the service and the vehicle.

---

## Screen 3 — Appointments

- Header `Appointments` + `Scheduled visits for Unit #603`; filter pills `Upcoming · Past · All` on the right. **Remove the separate `+ Book New` button** — the empty state and the quick-book grid already lead to booking; two CTAs to the same place is the current redundancy.
- **Empty state** (card, centered, padding `36px 24px`): 46px rounded tile with a calendar glyph, `No upcoming visits` (16/800), then a *useful* line: `Your next PM is due in about 1,255 miles. Book it now and keep the truck earning.` (13, `#8b92a5`, max-width 420px).
- **`BOOK IN ONE CLICK`** — 3-column grid of quick-book cards: tag pill (`DUE SOON` amber / `COMPLIANCE` green / `POPULAR` violet), service name 14/800, `price · duration` 12 `#8b92a5`, full-width violet `Book <name>` button (h38, r10). Tags are data-driven: "due soon" from PM interval, "compliance" from DOT anniversary, "popular" from booking counts.
- Footer link `Browse all 20 services →` → Services.
- **Populated state** (not in the prototype — build from the same row grammar): rows with date block on the left (day 16/800 + month 10/700, same as History), service name, shop, time window, status pill (`CONFIRMED` violet / `IN SHOP` amber), and `Reschedule` / `Cancel` text buttons.

---

## Screen 4 — Vehicles ("My fleet")

The current page shows a VIN and nothing to do. Make the vehicle card a **status + action surface**.
- Header `My fleet` + `1 vehicle registered`; `+ Add vehicle` secondary button.
- **Vehicle card** (bg `#161a26`, border `#232939`, r16):
  - **Identity row** (padding `18px 20px`, bottom border `#1e2432`): 52px rounded tile (bg `#12161f`, border `#272d3d`, amber glyph), `2020 Volvo VNR` 18/800, `Unit #603 · Plate VW9328 · White` 12/600 `#d9a521`; right: odometer `589,745 mi` (20/800 tabular-nums) + `updated Jul 24, 2026` (11, `#5c6375`).
  - **3 status tiles** (grid, padding `16px 20px`, each bg `#12161f`, r12): `NEXT PM DUE` → `in 1,255 mi` amber + 5px progress bar at 88% (amber fill) · `OPEN BALANCE` → `$1,127.00` with **red border on the tile** + `8 unpaid invoices` · `LAST SERVICE` → `Jul 23, 2026` + service names.
  - **Detail + action footer** (bg `#12161f`, top border `#1e2432`, padding `14px 20px`): label/value pairs `VIN 4V4WC9EG2LN250022` · `ENGINE D13 · 455 hp` · `ORDERS 14 all-time` (label 10/800 `#5c6375`, value 12 `#c9cdd8`), then right-aligned `Book service` (violet) and `Service history` (secondary).
- Multi-vehicle: stack these cards; ≥4 vehicles → collapse each to the identity row + the three tile values inline, expanding on click.

---

## Screen 5 — History ("Repair history")

- Header `Repair history` + `6 completed orders · $1,617.50 paid in 2026` (paid figure green) — the current page shows no total, which is what customers actually need for bookkeeping.
- Filter pills `All · Paid · Completed · Cancelled` (drop `Declined` unless it occurs; keep the set to states that exist in data).
- **Group by month** with a group header: `JULY 2026` (11/800 tracking .1em) and right-aligned `5 orders · $1,419.50` (11/700 `#5c6375`).
- **Row** (bg `#161a26`, border `#232939`, r12, padding `12px 16px`): 52px **date block** (day 16/800 tabular-nums + month 10/700 `#5c6375`) — this replaces the tiny gray `Jul 23, 2026` line and makes the list scannable · service list 13/700 + RO id 11 `#8b92a5` · `PAID` badge (green tone) · amount 14/800 (w84) · **`Invoice ⬇`** link (12/700 violet) downloading the PDF.
- Add a `Download all (CSV)` action in the header once >12 records exist (fleet customers reconcile in spreadsheets).

---

## Screen 6 — Account (was "Profile Settings")

- Header `Account` + `Sergio Burca · elislogistics86@gmail.com`.
- **Horizontal tabs** (h38, 2px violet underline on active, `#c9bfff` text): `Profile · Security · Appearance · Payments · Vehicles · Shops · Notifications`. Replaces the vertical sidebar list, which cost a full column to show 6 short words next to a mostly empty card.
- **Two-column body:**
  - **Left (flex:1) — `CONTACT DETAILS` card:** header label + `Changes save as you type`; 2-column grid of **editable inputs** (h44, r10, bg `#12161f`, border `#272d3d`): First name, Last name, Email (spans both columns), Phone. Footer (top border): `Save changes` (violet, h42) + `Last updated Jul 24, 2026`. **Removes the read-only-then-`Edit Profile` round trip** — fields are directly editable; validate email/phone inline.
  - **Right (w320) rail:** account card (46px avatar, `Eli's Logistics`, `Customer since Feb 2026`) · **`DEFAULT PAYMENT`** card (`ZELLE` teal badge + `no processing fee`, and `Card on file: Visa ···4127 (adds 2.5% fee)`) · **`NOTIFICATIONS`** card with 3 toggles (`Invoice ready`, `Repair status`, `PM reminders`; 34×19 track, violet when on, `#272d3d` when off).
- The payment-method default set here is what the Payment page (option 1b) preselects.

---

## Implementation order

1. **Shell + tokens** — dark nav on all routes, delete every breadcrumb, token file with the color roles above, shared `Pill`, `RowCard`, `SectionLabel`, `StatTile`, `Money` (tabular-nums) primitives.
2. **`overdueLevel(days)`** + a `Money` formatter as shared utilities — Dashboard, Vehicles, and Payment all read them.
3. **Dashboard** — balance hero, status tiles, unpaid list (sorted by overdue, multi-select), recently paid.
4. **Payment page** — already specified in `design_handoff_customer_payment/README.md` (option 1b); wire `Pay all` / `Pay` / `Pay oldest first` into it.
5. **Services** → **Appointments** (they share the quick-book card and the booking flow).
6. **Vehicles**, **History** (share the date block and PAID badge), **Account**.
7. **Responsive pass** (below).
8. **Verify** against the prototype screen by screen.

## Data model (portal-relevant)
```
Customer { id, companyName, firstName, lastName, email, phone, createdAt,
           defaultPaymentMethod: 'zelle'|'card', notifications:{invoiceReady,repairStatus,pmReminders} }
Vehicle  { id, year, make, model, unitNumber, plate, color, vin, engine,
           odometer, odometerUpdatedAt, nextPmMiles, pmIntervalMiles, lastServiceAt }
RepairOrder { id, vehicleId, services[], status:'quoted'|'in_progress'|'completed'|'cancelled',
              createdAt, completedAt }
Invoice  { id, repairOrderId, subtotal, shopSupplies, tax, cardFee, total,
           status:'unpaid'|'paid'|'pending_verification', sentAt, dueAt, paidAt, method }
Appointment { id, vehicleId, serviceIds[], shopId, startAt, endAt, status }
Service  { id, name, description, category, priceCents, durationMinutes, popularity }
```
Derived: `balanceDue = Σ unpaid.total`; `overdueCount`; `oldestOverdueDays`; `paidYtd`; `nextPmRemaining = nextPmMiles − odometer`; per-month history totals. All queries scoped to the customer's tenant(s) — a customer may have orders at multiple shops in the network, so **surface the shop name on rows once multi-shop data exists** (not in the current data, hence absent from the prototype).

## Responsive
- **≥1200px:** as specified (hero + tiles side by side; 2-column service and field grids).
- **768–1199px:** hero and tile grid stack; service grid → 1 column; Account rail moves below the form.
- **<768px:** single column, 16px side padding; nav collapses to logo + avatar + hamburger; the balance hero stays first with `Pay all` full-width; invoice rows reflow to two lines (id + service / badge + amount + Pay); status tiles → 2×2 compact.

## Assets
None shipped. All glyphs are Unicode placeholders (`⌕ ▦ ▤ ⬇ ‹ →`) — replace with the codebase icon set (search, calendar, truck, download, chevron, arrow). **Do not reintroduce emoji as service-category icons** (the current Services table) — use the category color dot or a real icon set. Logo is styled text.

## Sample data
Reference logic class arrays: 8 unpaid invoices (1–3 days overdue, $1,127.00 total), 3 recently paid, 20 services in 5 categories with real prices/durations, history for Jul 2026 (5 orders, $1,419.50) and Feb 2026 (1 order, $198.00), one vehicle (2020 Volvo VNR, Unit #603, 589,745 mi), account = Sergio Burca / Eli's Logistics.

## Files
- `README.md` — this spec.
- `Customer Portal.dc.html` — prototype for all six screens (section `1a`; switch screens via the top nav).
- `Customer Payment.dc.html` — payment page prototype; build section `1b` per `design_handoff_customer_payment/README.md`.
