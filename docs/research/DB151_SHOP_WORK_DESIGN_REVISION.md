# DB-151 — Connected Shop Work revision

Status: reviewable concept, not implemented. Accountable owner: Product & Delivery Lead. Updated November 1, 2026.

## Decision before layout

Shop Work answers two questions in order: **what needs my action now, and what is coming next?** It is an entry point into existing workspaces. Each domain retains its records, editing rules, permissions, and history.

This revision supersedes the four summary tiles and repeated supporting cards in section 5 of [the research brief](DB151_SHOP_WORK_STARTING_BOARD.md). The research and data cautions remain applicable. The rejected concept repeated action counts, made all surfaces equally prominent, and used navigation messages instead of demonstrating destination continuity.

## Acceptance criteria

1. No large active-job metric tile. Counts live beside their work-view labels.
2. One prioritized action stream. An obligation appears once on Overview, even if several domains contribute evidence.
3. The first task states the object, consequence, and next action. Remaining tasks use compact rows. The screen has a clear first, second, and third reading position.
4. Copper identifies the primary action and selected navigation. Neutral surfaces carry most content; amber/red/green have operational meaning and text labels. No rainbow domain cards.
5. Upcoming commitments are chronological and do not repeat actionable rows. A commitment promoted to the action stream leaves the upcoming list.
6. Every action opens its owning workspace with the object selected where supported. Origin, filters, and return path survive the trip.
7. Stock preparation flows Inventory → Purchasing. Receipt changes stock in Purchasing; Shop Work never implements its own receiving form.
8. Services and Labor Book Time support an RO estimate. Catalog administration stays under My Shop. Reference hours remain distinct from technician timers.
9. Quiet, busy, truly clear, and incomplete-data states are explicit. Unavailable information is never represented by zero or an all-clear claim.
10. The concept has working local navigation, keyboard-accessible controls, a usable narrow layout, and no network or live write behavior. Demonstration data is visibly labeled.

## Composition and component decisions

| Component | Why it earns its space | Rule |
|---|---|---|
| Compact work-view navigation | Keeps the existing operational lanes reachable | Overview, Active work, Closeout; counts adjacent to labels, no duplicate summary cards |
| Leading action | Makes the highest-priority controllable next step immediately obvious | One task with a clear consequence and verb; no carousel or decorative metric |
| Remaining action rows | Combines cross-domain obligations without scattering the same work around the page | Object, deadline/age, owner workspace, contextual value, one action |
| Upcoming commitments | Gives purpose when the floor is quiet and supports preparation | Actual promised work/dated commitments; no invented appointment scheduler or unverified ETA |
| My Shop navigation | Provides stable ownership for inventory, purchasing, templates, reference labor | Existing hierarchy; no separate dashboard-only tools |
| Source-specific unavailable state | Prevents a falsely reassuring board | Identify missing scope; retain verified work and allow navigation to the source |

No daily revenue hero, repeated unpaid/parts mini-cards, generic activity feed, unassigned catalog-cleanup chores, or employee utilization claim is included. Those either repeat work, distract from the next decision, or lack a reliable immediate action. Detailed analytics remains in My Shop.

## Ownership and connection contract

Routes below were checked against local `origin/main` at `8234f727` on November 1. Merge evidence is not deployment evidence. The new shared ETS payment display in PR #731 does not by itself establish a deduplicated receivables aggregate.

| Board intent | Canonical destination already present | Context carried | Required boundary |
|---|---|---|---|
| Continue, assign, review, or close a repair | `/dashboard/repair-orders?selected=<id>&queue=<lane>` | RO identity, applicable lane, origin | Existing repair workflow and permissions decide allowed actions |
| Review stock or a part requirement | `/dashboard/garage/inventory?selected=<part-id>` | Part, linked demand when known, return context | Available stock, allocations and outstanding supply must be reconciled before suggesting purchase quantity |
| Review a supplier order | `/dashboard/garage/purchasing?view=orders&purchase_order=<id>` | PO identity, originating task | Draft, submitted, partial receipt and completed are different states |
| Receive ordered parts | `/dashboard/garage/purchasing?view=receiving&purchase_order=<id>` | PO identity | Receiving owns receipt and stock mutation; selection handling for this combined mode needs runtime verification |
| Resolve a return/core | `/dashboard/garage/purchasing?view=returns` | Origin plus return identity if supported later | Exact return selection is an extension, not a verified current URL contract |
| Review customer balance | `/dashboard/customers?selected=<customer-id>` | Account identity, invoice context | Receivable subview/invoice focus requires a verified binding; customer selection exists. Preserve financial permissions and source confidence |
| Use a service template | RO estimate → `/dashboard/garage/services` | Draft RO and selected operation | Contextual picker/return binding is proposed; current module exists, URL preselection is not verified |
| Look up reference labor | RO estimate → `/dashboard/garage/labor-book-time` | Vehicle signature, operation, draft RO | Contextual picker is proposed; hours are reference estimates, not employee time clocks |
| Assign current work | `/dashboard/mechanics` | RO/assignment context | Do not confuse this with `/dashboard/garage/mechanics`, which administers team members |
| Respond to a conversation | `/dashboard/messages` | Thread only when binding verified | Messaging permission required; unread alone does not establish a response obligation |

The concept demonstrates target continuity, including proposed contextual pickers; it does not claim these integrations are already shipped. Actual destinations must use route builders and the platform's existing return-navigation patterns. Do not implement a parallel record editor in Shop Work.

## Deduplication and priority

Action identity is tenant + canonical obligation type + canonical record identity, not the component or source that discovered it. One stock shortage can link several affected ROs; it is one procurement decision. One source invoice shared by imported operations is one financial obligation, not one debt per operation.

Order deterministically by overdue repair promises or safety-critical release holds, blocked repairs threatening a current promise, overdue verified collections, due-today obligations, then preparation/replenishment. A blocked truck due this shift leads the busy example because resolving its parts shortage protects the promised release; an overdue invoice leads the quiet example when no floor work needs intervention. Within a band use due time, then age, then stable identity. Where a due time, assignee, supplier confirmation, or balance is unknown, preserve that uncertainty. A domain status is evidence, not sufficient proof of a task: 'invoiced' does not prove collectible money; 'waiting for parts' does not prove nothing has been ordered.

Future commitments belong in the side timeline until they require an action now. Global work-view totals may overlap task counts because they count different things; label units and never sum them into a misleading 'total work' metric.

## Data and authorization prerequisites

- Build a tenant- and permission-scoped action projection over existing domain read models. Do not derive obligations from capped dashboard lists or replicate status logic in the UI.
- Each action needs stable identity, object links, owning module, reason, permitted next action, due time/age, source freshness/completeness, and any verified amount/quantity.
- Refresh and reconcile after returning from the owning workspace; a fulfilled obligation disappears after confirmed source state, not merely after clicking its CTA.
- Inventory preparation is currently session-local. Promoting a selection into a shared purchasing task needs an explicit persistence contract, not an inferred shared state.
- Existing customer payment access is more restrictive than generic front-desk access. Apply server-side domain policy; hiding cards is insufficient.
- Historical issued documents and RO snapshots must not silently change when service templates or book-time references are edited.
- Clear means all relevant authorized sources were successfully checked and have no actionable obligations. Partial failures remain visible and scoped.

## Delivery sequence

1. Approve the visual/interaction direction through this connected concept; implementation remains separate.
2. Architecture & API Contracts defines action identity, tenant/permission projection, source completeness, return navigation and contextual picker contracts.
3. Implement Overview as a read layer using existing destination owners; preserve Active work and Closeout.
4. Add only missing destination selection/return adapters. Purchasing, inventory, payments, and labor rules stay in their domains.
5. Verify quiet/busy/partial/clear states, duplicate source invoices, partially ordered shortages, role/tenant isolation, and return navigation against real app data. Follow payment/security gates if those boundaries change.

No product code, services, financial records, supplier orders, messages, or production settings are changed by this revision.

## Built concept and verification

The connected `shop-work-connected.html` concept uses theme-aware navy and neutral surfaces with copper for the primary action, links, and selection. Semantic badges retain text labels. Overview presents one leading action followed by compact task rows and a chronological Coming up timeline; work-view counts remain beside their labels. There are no top metric tiles or repeated floor summary. The narrow layout stacks the timeline below the action stream.

Local navigation demonstrates Inventory → Purchasing with stock or linked-repair context, distinct purchase draft/order/receiving states, matching record destinations, and return paths. Services and Labor Book Time remain under My Shop; entering them from the estimate allows matching brake-inspection scope and reference hours to return to that draft. This contextual selection is a proposed integration, not an already shipped application capability. Standalone catalog browsing does not apply changes to an estimate. Fictional scenario data and the demonstration boundary remain visible; supplier submission, customer messaging, and live saves are outside the concept.

Verification reported by the concept owner: 27 jsdom assertions passed across quiet, busy, clear, and partial-data states, purchasing context, matching service/labor selection, and corrected return paths, with no runtime errors observed in that harness. An independent source/interaction review found all six specified corrections resolved; that review explicitly did not provide visual approval. The owner inspected dark rendered screenshots at 1024px, 375px, and 320px and observed no horizontal clipping, with the narrow timeline stacked. These checks are bounded concept evidence, not exhaustive responsive coverage or product runtime QA. No application implementation, live changes, PR, merge, or deployment was performed for this concept.
