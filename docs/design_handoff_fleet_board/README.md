# Handoff: Fleet Manager Board (Truck Pit Stop — internal ops)

## Overview
An **internal, staff-only** operations dashboard for the Truck Pit Stop repair shop to monitor the shop owner's own fleet (~24 trucks). It is **not customer-facing** and is a separate portal from the marketing site.

The Fleet Manager opens it to answer, in order:
1. **Which trucks are DOWN / in the shop right now?**
2. **Which trucks have preventive maintenance (PM) due soon (by mileage)?**
3. **What open work orders exist and what's their status?**

From the board, the manager drills into any truck to see its full record: identity (VIN, year, make/model, plate), assigned driver, every mechanic who worked on it, full service history, incidents on the road, parts & warranty status, and current location on a regional map (with distances to the nearest units).

---

## About the Design Files
The files in this bundle are **design references created in HTML/React (Babel-in-browser)** — prototypes showing the intended look and behavior. **They are not production code to copy directly.**

The task is to **recreate these designs in the target codebase's existing environment** (React/Next, Vue, etc.) using its established component library, routing, data layer, and styling patterns. If no front-end environment exists yet, choose an appropriate framework (React + a CSS solution is a natural fit here) and implement the designs there.

The mock data layer (`fleet-data.jsx`) is **illustrative only** — replace it with real API/DB calls. Its *shape* (the fields on each truck object) is a useful starting contract for the backend; see **Data Model** below.

## Fidelity
**High-fidelity.** Final colors, typography, spacing, and interactions are all specified. Recreate the UI pixel-faithfully using the codebase's libraries. Exact tokens are in **Design Tokens**.

---

## Screens / Views

The app is a single shell: a **fixed left icon rail** (74px) + a **sticky topbar** (64px) + a scrolling content area (max-width 1680px, centered, 26–28px padding). Five primary views are reachable from the rail; a sixth (truck **Detail**) is reached by clicking any truck.

### 1. Fleet Board (default, rail icon: grid)
**Purpose:** Triage all trucks at a glance, filter, and jump into any record.

**Layout (top → bottom):**
- **KPI strip** — CSS grid, `repeat(6, 1fr)`, 12px gap, 20px bottom margin. Six stat cards (see Components). Each is also a **filter toggle**.
- **Toolbar** — flex row, space-between, wraps. Left: search field (340px) + filter chips. Right: "Sort" label + sort `<select>`.
- **Truck grid** — `repeat(auto-fill, minmax(310px, 1fr))`, 14px gap.

**Default sort:** "Needs attention" — a ranking function floats overdue PM, awaiting-parts, and in-shop trucks to the top (see Interactions → Sorting).

**KPI cards (left→right):** Trucks in fleet (24) · On the road · In the shop · PM due soon · Awaiting parts · Open work orders. Each: 40px rounded icon tile tinted with the stat's accent, big Barlow-Condensed number (30px/800), label (12.5px muted). Active state: accent left-border (3px) + tinted surface. Clicking a KPI sets the corresponding status filter.

**Truck card (`.tcard`):** rounded 14px, surface bg, 1px border, 18px padding, 11px gap, **4px status-colored left spine** (`::before`). Hover: lifts 3px, border lightens, shadow `0 16px 40px rgba(0,0,0,.34)`, chevron fades in bottom-right.
Contents in order:
- **Top row:** unit number (`TPS-101`, Barlow Condensed 24px/800) + make/model sub (12.5px muted) on the left; **status badge** pill on the right (uppercase 11.5px/700, tinted with status color, with a status dot — dot **pulses** if the truck is moving).
- **Body type** label (uppercase 11.5px, 1.5px letter-spacing, muted).
- **Location row** — pin icon + truncating text (`I-85 N · Charlotte, NC` or `TPS Yard · Bay 3`).
- **Driver row** — user icon + driver name; if moving, right-aligned mono `58 mph NE` in green.
- **Odometer row** — top border, "ODO" label + mono value + "mi".
- **PM progress bar** — 5px track + fill colored by urgency (green `pm-ok` / yellow `pm-soon` / red `pm-over`) + label (`12,400 mi to PM` / `Due in 1,800 mi` / `OVERDUE 600 mi`).
- **Work-order footer** — inset chip: wrench icon + WO id (mono) + status, OR a green check + "No open work orders".

### 2. Live Map (rail icon: map)
Full-width `FleetMap` component (see Components → FleetMap). All trucks plotted, click a marker to open that truck.

### 3. PM Schedule (rail icon: calendar)
Trucks sorted by `pmRemaining` ascending. Card grid (`minmax(260px,1fr)`) of the 12 most urgent — unit, make/model, big urgency label (overdue red / soon yellow / ok green), odometer + "next at" mileage. Click → Detail.

### 4. Work Orders (rail icon: clipboard)
List of all trucks with an open work order. Each row: status dot + unit + WO id (mono) + summary + status (yellow) + assigned mechanic. Click → Detail.

### 5. Drivers (rail icon: user)
Card grid of all trucks: driver avatar (initials) + driver name + unit/make/model + status dot. Click → Detail.

### 6. Truck Detail (click any truck)
**Purpose:** The complete record for one truck.

**Layout (top → bottom):**
- **Back button** ("← Fleet board").
- **Header** — flex space-between. Left: unit number (Barlow Condensed 46px/800, `white-space:nowrap`) + status badge + make/model/type sub. Right: two buttons — "New work order" (ghost) and "Schedule PM" (yellow solid).
- **Metric row** — 4 cards (`repeat(4,1fr)`): Odometer · Next PM (+ urgency note) · Lifetime service spend · Incidents on record.
- **Two-column grid** (`1.55fr 1fr`, 16px gap):
  - **Left (main):**
    - **Service history** — vertical timeline. Each item: colored marker (green PM / yellow Repair / blue Inspection) + connecting line; row of kind-tag, date, right-aligned mono mileage; summary text; meta row (mechanic + mono cost).
    - **Incidents on the road** — cards with severity spine (red/yellow/blue), type + date, location (pin), note. Empty state: shield icon + "No incidents recorded."
  - **Right (side):**
    - **Truck identity** — 2-col bordered grid: VIN (mono), Plate (mono), Year, Body type, Make, Model.
    - **Driver & crew** — assigned driver (avatar + call button), lead mechanic, plus other mechanics pulled from history.
    - **Parts & warranty** — list; each: part name + meta (date · mileage · mechanic) + warranty pill (green "Warranty to <date>" / grey "Expired").
- **Location & nearby units** (full width) — section header shows current location + speed/heading or "parked Nd". Body is a `1fr 248px` grid: the `FleetMap` (focused on this truck) + a "Nearest units" list (clickable rows: status dot, unit, city, mono miles).

---

## Key Component: FleetMap (`fleet-map.jsx`)
A **stylized schematic** regional map (NOT real GPS tiles — see Assets/Next Steps). 100×100 SVG coordinate field, `16/9` aspect (or fixed height on the full Live Map page).
- Faint grid lines + a handful of schematic "highway" polylines (I-77, I-85, I-485, US-74, I-40) with mono labels.
- **HQ marker** — yellow rotated-45° diamond + "TPS YARD" label, centered (~50,62). Parked trucks cluster near it.
- **Truck markers** — 13px status-colored dots with dark border; moving trucks emit an animated expanding ring. Hover shows a tooltip (unit, status, location, and distance-from-focus when a truck is focused).
- **Focus mode** (Detail view): the focused truck enlarges; dashed yellow connectors run to its 3 nearest units with **mileage pills** at the midpoints; all other markers dim to 34%.
- **Legend** below the field maps each status color + the yard diamond.

Distance math: schematic units → miles at ~5.4 mi/unit, with y scaled 0.85 (`dist()` in `fleet-data.jsx`).

---

## Interactions & Behavior
- **Navigation:** rail buttons switch top-level view; clicking a truck card/row anywhere opens Detail and scrolls content to top; "← Fleet board" returns to the board.
- **Filtering:** KPI cards and chips set a single status filter (`all | active | shop | pm | parts`). Search box matches across unit, VIN, plate, driver, make, model, type (case-insensitive substring).
- **Sorting:** select with options — *Needs attention* (default), *Unit number*, *PM soonest*, *Highest mileage*. "Needs attention" rank: overdue PM = 6, in-shop = 5, awaiting-parts = 4.5, in-shop = 4, PM-due = 3, on-road = 1.
- **Status → color** mapping is the core visual signal (see tokens). A truck is "moving" when `status === 'active'`; moving state drives the pulsing dot/ring animations.
- **PM urgency:** `pmRemaining = nextPm − odometer`. `≤ 0` → overdue (red); `< 2500 mi` → due soon (yellow); else ok (green). Bar fill `% = 100 − (remaining / pmInterval)*100`, clamped 4–100.
- **Animations:** card hover lift/shadow (.15s); moving-dot pulse (1.8s loop) and map ring (1.8s loop). Keep decorative loops only on "moving" indicators. Respect `prefers-reduced-motion`.
- **Persistence:** current `view`, selected truck `selId`, `filter`, and `sort` are saved to `localStorage` under key `tps-fleet-state` and restored on load. (In the real app, prefer URL routes — `/fleet`, `/fleet/:unit`, `/map`, etc. — so views are linkable and back/forward works.)
- **Responsive:** ≤1180px → KPIs 3-col, detail grid collapses to 1-col, metrics 2-col, map side-stacks; ≤680px → KPIs 2-col, identity grid 1-col, search full-width.

## State Management
Top-level UI state needed: `view` ('board' | 'map' | 'schedule' | 'orders' | 'drivers' | 'detail'), `selId` (selected truck id | null), `filter`, `query`, `sort`. Detail/Map/Schedule/Orders/Drivers all derive from the same truck collection — no per-view fetching in the prototype. In production these become routes + a trucks query (list) and a truck-by-id query (detail), ideally with the status counts computed server-side for the KPI strip.

---

## Data Model (shape of one truck — from `fleet-data.jsx`)
Use as a starting contract; trim/extend to your backend.
```
truck {
  id, unit ("TPS-101"), year, make, model, brandShort, type (body type),
  vin, plate,
  status: "active" | "shop" | "pm" | "parts",
  driver (name),
  odometer (int mi), pmInterval (25000), nextPm (int mi), pmRemaining (derived),
  location { label, city, since },
  pos { x, y, moving },              // map coords + moving flag
  mph, heading,
  assignedMechanic,
  workOrder: null | { id ("WO-4471"), opened, status, summary, mechanic, eta, laborHrs },
  history: [ { date, kind: "PM"|"Repair"|"Inspection", odo, summary, mechanic, cost } ],
  parts:   [ { name, date, odo, mechanic, warrantyUntil, warrantyMiles, active } ],
  incidents: [ { date, type, sev: "high"|"med"|"low", location, note } ]
}
```
Fleet-level rollups for KPIs: total, active, shop, pm, parts, openWO, incidents30.

---

## Design Tokens

**Fonts** (Google Fonts):
- Display: **Barlow Condensed** (800/900 for unit numbers, headings — uppercase, ~0.5px letter-spacing).
- Body: **Archivo** (400–700).
- Mono: **JetBrains Mono** (VIN, plate, mileage, costs, WO ids).

**Colors:**
| Token | Hex | Use |
|---|---|---|
| `--bg` | `#0a0b0d` | app background |
| `--ink` | `#0d0e11` | topbar, inset chips |
| `--surface` | `#16181d` | cards |
| `--surface-2` | `#1d2026` | hover / active surface |
| `--surface-3` | `#23262e` | icon tiles, avatars |
| `--line` | `#2a2e36` | borders |
| `--line-2` | `#363b45` | hover borders, scrollbar |
| `--yellow` | `#f5b301` | brand accent / primary |
| `--yellow-dim` | `#c9920a` | — |
| `--text` | `#f2f1ee` | primary text |
| `--muted` | `#99a0aa` | secondary text |
| `--muted-2` | `#6f7682` | tertiary |
| `--muted-3` | `#565c66` | faint |
| `--red` | `#e63946` | overdue / high severity |
| **Status — active** | `#22c55e` | on the road (green) |
| **Status — shop** | `#38bdf8` | in the shop (blue) |
| **Status — pm** | `#f5b301` | PM due (yellow) |
| **Status — parts** | `#a78bfa` | awaiting parts (purple) |

Status tints use `color-mix(in srgb, <status> 13–16%, transparent)` for badge/pill backgrounds.

**Radii:** cards 13–14px; chips/buttons/fields 10px; icon tiles 10–11px; pills/tags 6–8px; dots/avatars 999px (avatars 10px square).

**Spacing:** page padding 26–28px; card padding 16–20px; grid gaps 12–16px; control height 42px; rail 74px; topbar 64px.

**Shadows:** card hover `0 16px 40px rgba(0,0,0,.34)`; tooltips `0 10px 30px rgba(0,0,0,.5)`.

**Typography scale (key):** detail unit 46/800; card unit 24/800; KPI value 30/800; section h3 20/700 uppercase; metric value 27/800; body 13–14px; labels 11.5–12.5px (often uppercase, 1–1.5px tracking).

---

## Assets
- **No raster assets.** All icons are inline stroke SVGs defined in `fleet-icons.jsx` (truck, grid, map, wrench, calendar, clipboard, user, search, bell, gauge, pin, alert, clock, shield, phone, cog, box, nav, route, fuel, chevrons, etc.). Swap for the codebase's existing icon set (e.g. Lucide — these match Lucide's visual style closely).
- **Map is schematic**, drawn with SVG — there are no map tiles or real coordinates. For production, integrate a real map (Mapbox/Google/Leaflet) fed by telematics/GPS; the focus + distance-to-nearest UX should be preserved.
- Fonts load from Google Fonts; self-host in production.

## Files (in this bundle)
- `Fleet Board.html` — app shell: rail, topbar, routing, secondary views (Map/Schedule/Orders/Drivers), localStorage persistence.
- `fleet-data.jsx` — **mock** data layer + helpers (`STATUS_META`, `fleetStats`, `nearest()`, `dist()`, formatters). Replace with real API.
- `fleet-icons.jsx` — inline SVG icon set.
- `fleet-map.jsx` — `FleetMap` schematic map component.
- `fleet-board.jsx` — KPI strip, toolbar, truck-card grid, sort/filter logic.
- `truck-detail.jsx` — full single-truck record view.
- `fleet.css` — all styles + tokens (CSS custom properties at `:root`).

Open `Fleet Board.html` in a browser to interact with the working reference.
