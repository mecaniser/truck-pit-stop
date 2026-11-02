# Shop Work: the starting board for DieselBridge

Research and product decision brief · November 1, 2026 · DB-151  
Accountable owner: Product & Delivery Lead  
Status: Research complete; proposed design, not an implemented or released feature.

**Design revision:** The initial composition below was superseded after user review. Use the [connected Shop Work revision](DB151_SHOP_WORK_DESIGN_REVISION.md) for current hierarchy, component selection, destination contracts, and concept verification. Research evidence remains historical to the source snapshot stated here.

## 1. Decision

Make **Overview** the default Shop Work view. It should answer four questions: What needs my attention? What is blocking work? What money or parts need follow-up? What should I prepare next?

Keep Active work, Closeout and Activity as focused views. Add an overview across those views and the existing purchasing, staffing, scheduling and communication workflows. Use compact, actionable components with counts, short previews and precise destinations. Do not make staff infer their next action from revenue charts or a row of zeroes.

The board's central component should be **Next actions**, a ranked list of concrete records. Supporting components explain the state of the shop. Every displayed item must have an authorized owner or responsible role, a reason for appearing, a trustworthy status, and a destination where the task can be completed.

This is a product recommendation based on the evidence below. Competitor documentation establishes patterns and capabilities, not proof that their interface is optimal for this shop.

## 2. Research coverage and limits

### Evidence collected

- The user's screenshot and a signed-in production read of DieselBridge Shop Work and its Closeout view.
- Signed-in ETS reads of On Site, Priority, Reports Dashboard and Out of stock. No orders, payments, messages, stock or settings were changed.
- Official product/help sources for ETS, Fullbay, Tekmetric, Shopmonkey, Shop-Ware, Mitchell 1 Manager SE/TruckEdition and AutoLeap.
- DieselBridge source at `origin/main` commit `9d72b77788edee7d54394df43d82d52c01943202`, plus the existing local delivery board and current GitHub PR inventory. The working checkout itself is older (`04f05175`); findings about current contracts below use the newer main source, not that checkout.
- Open PR #731 concerns shared ETS invoice display across related imported operations. It was draft/open during research. Its description explicitly excludes accounting aggregate changes. It does not establish that shop-wide receivables are ready.

Local startup is exempt because this work is research and documentation. No application implementation or local product QA occurred. Production navigation was read-only. Two direct Closeout click attempts timed out before dispatch; the existing `work_view=closeout` URL then loaded successfully. No claim of comprehensive production interaction testing follows from those reads.

### What “popular platforms” means here

The comparison deliberately covers established general repair products and truck-specific products. Tekmetric reports more than 15,000 shops; Shopmonkey reports 10,000+ customers. These are vendor claims, with different denominators, not an independently audited market-share ranking. Fullbay and Mitchell 1 TruckEdition supply heavy-duty relevance; ETS supplies a directly observable reference. Shop-Ware and AutoLeap broaden workflow comparison. No numerical vendor score or unsupported “best in market” ranking is assigned. [Tekmetric adoption](https://www.tekmetric.com/feature/estimate-building), [Shopmonkey adoption](https://www.shopmonkey.io/about-us).

Other vendors were assessed through official public material, not authenticated trials. Their response times, permission enforcement, usability and financial accuracy were not tested. Missing documentation is not evidence that a product lacks a feature.

### Concept validation

The accompanying interactive concept uses fictional records and amounts. It covers no-active-work, busy, all-clear and unavailable-financial-data scenarios, with manager and technician views. JavaScript syntax and DOM interaction checks passed for scenario changes, role-specific content, unknown-versus-zero handling, no invented all-clear tasks and exact destination disclosure. Desktop rendering was visually inspected. Browser automation could not operate controls inside the preview iframe; interaction checks therefore used a DOM harness. Mobile visual acceptance and authenticated product acceptance are not claimed. No concept button reaches a live business endpoint.

## 3. What is wrong with the current landing experience

### Confirmed in DieselBridge

1. The default view shows Active work with zero jobs while the Closeout control shows one. The user must notice a small alternate-view count to find remaining work.
2. Most of the page becomes empty when the active-work projection is empty. There is no visible cross-workflow next step.
3. Active categories are all repair-order categories. They cannot tell staff about purchasing, supplier returns, upcoming appointments or customer account follow-up.
4. Activity is historical context. Its badge does not identify unfinished work or responsibility.
5. The observed Closeout row says “Payment Due” while displaying `$0.00`. Source derives that label from `status === 'invoiced'`; the displayed work value is not an authoritative collectible balance. This does **not** prove the underlying invoice is payable, settled or incorrect. It proves the board cannot safely interpret that row as “collect money.”

The current active-work projection has useful safeguards: canonical categories, assignment scope, explicit unknown timing and exclusion of imported historical billing. Preserve those. The problem is its use as the whole landing board, not the existence of the focused active-work view.

### Confirmed in ETS

ETS On Site was also empty. Its Priority page remained structured around unassigned items and technician columns. The Reports Dashboard offered a separate set of financial and labor metrics with period/basis controls and report links. Its Out of stock page grouped demand by Services, Parts Sales and Inventory and exposed the origin of each demand row.

The visible Out of stock results also included old entries, archived parts and locked service references. The total result count therefore cannot be interpreted as a count of urgent current purchase decisions. This is an important lesson: make demand visible, but classify current actionable work separately from historical cleanup.

The ETS reports observation occurred on the first day of a new month. Zero current-period values do not establish a lack of backlog or poor shop performance. A Shop Work board must not apply the reporting period to unresolved work.

## 4. Market comparison: what to adopt and why

| Platform | Verified pattern | DieselBridge decision | Boundary or tradeoff |
|---|---|---|---|
| **ETS** | Separate Upcoming, On Site, Completed and Invoiced views; Priority organizes service items by technician. Parts demand exposes its service/sale/restock origin. | Keep distinct work stages and show who or what is waiting for each part. Add an overview above these work areas. | The observed empty On Site view still requires navigation elsewhere. Old demand must not become an urgent purchase recommendation. |
| **Fullbay** | Heavy-duty product covers WIP, A/R aging, labor, inventory, cores and fleet PM; inventory supports reorder thresholds and purchase orders. | Treat purchasing, money follow-up and cores as normal shop work, visible alongside repairs. | A collection of reporting capabilities does not establish one shared landing layout. Avoid assuming every feature is part of its homepage. |
| **Tekmetric** | Job reporting distinguishes unsent authorization, pending approval, work not started, parts to order, parts awaited, balance due and ready to post. Separate tech/job boards support role-specific work. | Name the exact next stage. “Need to order” and “Waiting for delivery” must produce different actions. | Its real-time dashboard notes that RO-level fees/discounts are excluded from certain reports. Do not copy monetary labels or totals without DieselBridge's own definitions. |
| **Shopmonkey** | Shop/personal dashboard views; customer aging, unpaid invoices, workflow status and upcoming appointments. Those operational sections are not limited by its selected reporting period. Parts workflow includes linked orders and returns/cores. | Use role-aware defaults. Keep unresolved backlog independent of Today/This month. Link each preview to its record. | Personal customization should not let mandatory exceptions disappear. Financial and operational dates must remain explicit. |
| **Shop-Ware** | Documented workflow, workload capacity, parts/core handling, accounts receivable and unfulfilled recommendations. Reports distinguish customer payments and closed sales. | Give role-specific work and deferred recommendations distinct homes. Separate collection activity from sales outcomes. | “Unfulfilled” recommendations are follow-up opportunities, not approved repair jobs. |
| **Mitchell 1 Manager SE / TruckEdition** | WIP functions as a service-advisor control surface. User profiles retain display choices. Technician time tools separate job and shift clocks; reporting includes outstanding POs and low inventory. | Persist useful personal views and expose staffing context. Preserve a dense working list once staff drill in. | Assigned job count alone cannot establish availability or utilization. |
| **AutoLeap** | Work Board connects estimates/ROs, technician assignments, payment status, inspection progress and overdue-job alerts. | Use deadlines and blocking reasons beside work. Make the next destination direct. | Do not adopt drag-to-change lifecycle status without DieselBridge's existing workflow and authorization checks. |

Sources for this table: [ETS boards](https://support.easytruckshop.io/en/articles/16515161-service-flow-what-the-service-statuses-and-boards-mean), [ETS demand origin](https://support.easytruckshop.io/en/articles/16500687-parts-flow-what-the-out-of-stock-page-is-for), [Fullbay capabilities](https://www.fullbay.com/pricing/), [Fullbay inventory](https://www.fullbay.com/products/inventory-management-software/), [Tekmetric dashboard](https://support.tekmetric.com/hc/en-us/articles/360042280134-Shop-Dashboard-Real-Time-Reporting), [Tekmetric job board](https://www.tekmetric.com/post/repairs-management-software-job-board), [Shopmonkey dashboard](https://support.shopmonkey.io/hc/en-us/articles/50553221357972-Dashboards), [Shopmonkey parts workflow](https://support.shopmonkey.io/hc/en-us/articles/38743651197332-Parts-Tires-Workflow), [Shop-Ware training index](https://support.shop-ware.com/s/training-guides-page), [Shop-Ware report index](https://support.shop-ware.com/s/article/Reporting-In-Shop-Ware-Report-Index), [Mitchell 1 WIP](https://mitchell1.com/shopconnection/manager-se-8-5-1-wip-screen-enhancements-now-have-it-even-more-your-way/), [Mitchell 1 time management](https://mitchell1.com/shopconnection/time-manager-brings-tools-for-managers-technicians/), [Mitchell 1 TruckEdition](https://mitchell1.com/press/latest-release-of-mitchell-1s-manager-se-truckedition-shop-management-system-now-includes-online-reports/), [AutoLeap Work Board](https://autoleap.com/features/work-board/).

## 5. Recommended page structure

1. **Header:** Shop Work, selected shop, business date/timezone, data freshness, existing Lightning Order and Full Order actions.
2. **Views:** Overview (default), Active work, Closeout, Activity. Keep existing deep links and selected-record behavior. Preserve explicit view URLs on return navigation.
3. **Compact status strip:** Active jobs; closeout items; parts needing action; commitments today. Each count names its unit and opens the corresponding list. These are independent counts, never a sum called “total tasks.”
4. **Main area:** Next actions takes the largest share. Adjacent components summarize work blockers, closeout/collections and purchasing. Show at most three preview rows per supporting component with an exact “View all” count.
5. **Planning area:** Today's commitments, team state and customer messages, according to role. Returns/cores live within Parts, with urgent exceptions also appearing in Next actions.
6. **Secondary outcomes:** Completed work and confirmed collections today for authorized managers. Full trends remain in Analytics. Recent activity stays available as history.

Desktop: task list approximately three-fifths of the main area, supporting components two-fifths. Tablet: stack Next actions first, then two-column supporting groups where readable. Phone: one column, task-first; hide unauthorized components rather than showing misleading zeroes. No forced carousel for urgent work, horizontal dashboard scrolling or huge empty panels.

Keep component order stable. Re-rank items inside the task list; do not move whole panels while someone reads or clicks. Avoid a freeform drag-and-drop dashboard builder in the first release. Offer role defaults and a small number of optional secondary panels after usage evidence exists.

## 6. Component definitions and inclusion decisions

These are component responsibilities, not eleven equally prominent rectangles. Several are sections within a larger component.

### A. Next actions — mandatory, first screen

**Why:** A status count says what exists. Staff need to know what to do next, including when no repairs are active.

**Who:** Every staff member, filtered by actual permissions and assignment scope. Owners/admins see their shop; mechanics see their authorized assigned work; reception sees permitted coordination tasks.

**Content:** Five highest-priority actionable records, then View all. Each row contains a verb, record/vehicle or supplier identity, factual reason, responsible person/role, deadline or known waiting time, and one destination. Examples: Review completed repair; prepare an unsent estimate; review an uncertain payment; follow up an overdue PO; allocate approved work.

**Eligibility/count:** One primary action per canonical record. Additional reasons remain visible on that row. Invoice actions deduplicate by canonical invoice, not imported operation. Count unresolved eligible records across all dates before pagination. Separate “ready to act” from “waiting on someone else.” Show waiting rows when a follow-up is due or staff explicitly inspect the waiting list.

**Destination:** Existing canonical RO, invoice/account, purchasing or messaging workspace. First version navigates; it does not silently send, order, charge, acknowledge or close anything.

**Empty/error:** “No actions waiting in your scope” only when every required authorized source is complete. Otherwise “Some work could not be checked,” naming affected sources. A filtered empty list says “No matches,” with Clear filters.

**Readiness:** New shared projection/ranking contract needed. Existing feature lists are not a complete task service.

### B. Active work and blockers — mandatory

**Why:** Lets advisors resolve delays and prevents an active repair from getting lost among financial or stock work.

**Content:** Active job count; approval, parts, technician, quality review, other hold, preparation and in-progress counts. Preview overdue promises and oldest known waits. Distinguish “approval hold recorded” from “quote sent, awaiting decision.”

**Definition:** Reuse the current WIP eligibility and category precedence. Completed, invoiced, paid, released, cancelled and historical imported jobs are excluded. Category counts are disjoint; overdue and unknown-timing counts overlap categories. Do not sum them. A recorded in-progress state is not proof of a running timer or physical bay occupancy.

**Action:** Open the exact active category or RO. The overview never substitutes a guessed lifecycle change.

**Empty/error:** Zero active jobs compresses this component to one line and leaves the other work visible. Unknown wait is “Timing unknown,” never zero minutes.

**Readiness:** Existing `/dashboard/wip-aging` supplies this contract. Preserve its mechanic scope and explicit evidence states.

### C. Closeout and customer money — mandatory for authorized staff

**Why:** Finishing a repair, issuing an invoice, confirming payment and collecting overdue money are separate unfinished tasks.

**Sections:** Ready for invoice/closeout; payment review; verified receivables. “Payment review” includes uncertain/pending outcomes and has a review action, not a collection prompt. Verified receivables separate not-yet-due, due today and overdue.

**Metrics:** Count closeout orders independently from collectible invoices. For authorized financial users, show verified outstanding principal, overdue principal, invoice count and oldest valid due date. Use authoritative settlement/attestation remaining principal, applied credits and source ownership. Do not derive debt from RO status, work value, original invoice total minus an arbitrary payment sum, or service-fee residuals.

**Scope:** Customer money owed to the shop. Supplier bills owed by the shop are a different capability; see rejected/deferred decisions below. Imported ETS history cannot enter native collectible totals. Shared imported invoice context must not multiply debt across operations.

**Action:** Open Closeout for repair closure; open payment review for ambiguity; open the permitted account/invoice for collections. A follow-up opens a reviewed workflow, not an automatic message or retry.

**Empty/error:** “No verified outstanding balance” plus an explicit review count when incomplete. Only complete evidence allows “Nothing outstanding.” A zero-dollar invoiced order routes to closeout/review, never a request to collect $0.

**Readiness:** Closeout navigation exists. Customer account reconciliation exists per customer. A trustworthy shop-wide rollup, invoice counts and drill-down need a new contract. Current account access requires owner/admin plus payments permission; reception must not gain financial visibility merely because the new board exists.

### D. Parts to order — mandatory for purchasing-capable roles

**Why:** Missing parts block repairs; replenishment is useful work even when the bays are empty.

**Sections:** Current job shortages; shelf replenishment; unresolved supplier/part setup. Display part, required quantity/unit, covered incoming quantity, supplier and the job or restock reason.

**Metrics:** Distinct actionable SKUs and distinct blocked jobs, labeled separately. Reuse the server recommendation that considers current shortage, shelf need and incoming supply. Do not count quantities across incompatible units. Do not treat draft POs as received or confirmed incoming supply. Separate order preparation already in progress so the board does not invite duplicate POs.

**Action:** Open demand/part or existing purchase preparation. “Review reorder” is appropriate until quantities, supplier and pack/minimum rules are validated. No automatic supplier submission.

**Empty/error:** “No uncovered parts demand” only after authoritative demand loads. Unknown supplier or stale stock produces a review task, not a suggested purchase with invented cost or quantity.

**Readiness:** Existing parts summary/demand and supplier sources are reusable. Aggregate and list must share the same retired/deleted/placeholder filters. A hold reason alone does not prove which part must be purchased or how many jobs a PO will unblock.

### E. Incoming deliveries — a separate section within Parts

**Why:** Ordering a part does not make it available. Staff need to receive arrivals and chase missed promises.

**Definition:** Submitted or partially received POs with positive remaining quantity. Separate past expected dates, expected today and no expected date. Count distinct POs; show lines remaining inside the detail. Draft orders stay under preparation. A missing ETA is “ETA needed,” not “Late.”

**Action:** Open the exact PO in Purchasing/Receiving. “Follow up delivery” and “Receive parts” are different actions. Never imply receipt from an elapsed ETA.

**Empty/error:** “No open deliveries” on complete data; unavailable supplier or PO data remains visible as unknown.

**Readiness:** PO statuses, line receipts and `expected_at` exist. A bounded dashboard aggregate is needed. ETA precision/timezone semantics must be respected.

### F. Returns and cores — persistent Parts subsection; urgent items enter Next actions

**Why:** These tasks survive repair completion and recover money that an active-job board misses.

**Content:** Cores still expected from work; cores on hand; returns ready to send; shipped returns awaiting credit; verified expected versus actual credit differences.

**Definition:** Each core obligation/return has one current action. Exclude waived/cancelled/credited or reversed records as applicable. Avoid counting a core and its linked return as two independent tasks. Expected credit is a potential recovery, not cash received or a verified supplier receivable.

**Action:** Open Returns & cores and the relevant record. Do not assume an on-hand core has been returned or a shipped return credited.

**Empty/error:** “No returns or cores waiting” only on full coverage. Existing core records do not establish a return deadline; show “Deadline not recorded” rather than manufactured overdue days.

**Readiness:** Core and vendor-return models and endpoints exist, including expected/actual credits and event timestamps. Deadline-based escalation requires additional verified terms or fields.

### G. Today's commitments and next business day — mandatory when scheduling is used

**Why:** A quiet current queue can coexist with upcoming arrivals, promised finishes or work that should start soon.

**Content:** Scheduled starts, appointment arrivals and promised finishes, each labeled by type. Show today's commitments first and next business day's work second. Identify blocked jobs due today using recorded facts; avoid unsupported completion-time predictions.

**Definition:** Use shop timezone and valid source deadlines. Deduplicate an appointment already linked to an RO. Exclude cancellations, no-shows and released work according to source semantics. Appointment `pending` currently means awaiting payment, so it cannot be displayed as a confirmed arrival. Do not call all open ROs “trucks on site.”

**Action:** Open appointment or exact RO. Add pickup-ready tasks only after readiness/customer-contact/release evidence has an explicit contract.

**Empty/error:** “No commitments recorded today” plus next business day. If scheduling is not in use, say so once; do not show a permanent empty calendar or infer an open shop day without configured hours.

**Readiness:** RO scheduled start/promised finish/release fields and appointments exist. A combined, deduplicated projection and business-calendar rules need definition.

### H. Team now / My work — role-dependent

**Why:** Managers need to allocate ready work; technicians need their next approved operation and current timer context.

**Content:** Manager: currently working, on break, clocked in without an active job, off shift/unknown, and ready-but-unassigned work. Mechanic: own current work and assigned ready operations.

**Definition:** Attendance and timer evidence determine labels. “No active timer” is not proof that someone is idle or available. Assigned jobs are not remaining labor hours. Do not add utilization percentages until valid paid/available hours and job-time denominators exist.

**Action:** Open technician board or assigned operation. Preserve assignment and action permissions; the board is not authority to reassign someone.

**Empty/error:** Missing attendance data says “Status unavailable.” An off-shift user gets upcoming assigned work, not pressure to start a timer.

**Readiness:** Existing mechanics board supports attendance, sessions and assigned-ready counts. New overview must preserve its access rules; use personal scope for mechanics.

### I. Customer messages and follow-up — compact, permission-gated

**Why:** A reply can unblock approval, clarify a job or start new work. Messages should not be hidden when the repair queue is empty.

**Content:** Unread conversations initially. Later: explicitly assigned reply-needed threads, new service inquiries and scheduled follow-ups, once those states are durable.

**Definition:** Existing `unread_count_staff` establishes unread messages only. It does not prove a response is owed. Read-but-unanswered messages require separate workflow state before they can be called “Needs reply.” Failed delivery is not proof the customer ignored a message.

**Action:** Open the exact conversation. Maintain channel permissions and draft/review behavior. The overview never sends messages or retries uncertain delivery.

**Empty/error:** “No unread conversations” is accurate for the initial contract; “All customers answered” is not. Messaging-disabled shops see no zero-valued message card.

**Readiness:** Unread/thread data exists. Ownership, reply-needed state, next-follow-up date and deduplication with approval tasks need a defined contract.

### J. Shop outcomes — secondary, owner/admin default

**Why:** Confirms what the team accomplished and helps managers spot operational drift without occupying the main action area.

**Initial measures:** Jobs that reached the defined work-completion event today; invoices settled today; confirmed principal collected today. Label each event basis. Closing an invoice, releasing a vehicle and completing physical work are different events.

**Action:** Open the corresponding activity/report with identical date, timezone and source scope. Operational backlog above remains unfiltered by this date selector.

**Empty/error:** Unknown accounting coverage means “Incomplete,” not `$0`. Separate refunds from confirmed receipts and state whether a value is gross or net. Never label current work value as sales, profit or cash.

**Readiness:** Events and financial services exist, but definitions and reconciliation must precede a new shared monetary widget. The existing daily `closed_today` projection uses invoice `paid_at`; it must not be reused as “repairs completed today.”

### K. Fleet/PM, recommendations and source problems — conditional

**Why:** These can supply legitimate work when active jobs are empty, but only within the shop's responsibility.

**Fleet/PM:** Show known overdue maintenance or reviewed incidents only for authorized linked fleet relationships. Deduplicate linked open ROs. No platform-wide truck counts or inferred emergencies from unknown telemetry.

**Recommendations:** Show an explicitly scheduled customer follow-up for previously deferred work. A declined job alone does not justify repeated outreach or a new repair order.

**Source health:** Show a small actionable notice only when stale/unavailable data prevents a decision. Name what could not be checked and the safe destination. Do not flood ordinary staff with infrastructure health metrics.

**Readiness:** Fleet functions exist outside this initial shop overview. Cross-audience scope and shop ownership need separate contract review. Recommendations need follow-up ownership and dates. Source status is required from the first release even if fleet/recommendation cards are deferred.

## 7. Explicit exclusions and deferred options

| Option | Decision and reason |
|---|---|
| Large revenue/ARO/profit chart above tasks | Keep in Analytics. It describes performance but cannot reliably name the next operational action. |
| Lifetime customers, vehicles, total repair orders | Exclude from default overview. They consume attention without identifying unfinished work. |
| Inventory value as a prominent card | Keep in owner analytics. It is not the quantity or urgency of parts that need ordering. |
| Supplier invoices to pay | Include only after a verified accounts-payable source exists. A PO or goods receipt is not evidence of an unpaid vendor bill. This audit did not establish a complete AP ledger. |
| Technician leaderboard or efficiency score | Defer. A fair metric needs validated time, labor, sublet and attribution rules. Prefer current operational state. |
| Bay utilization / trucks physically on site | Defer until location/arrival/occupancy evidence exists. Active RO status is insufficient. |
| Predicted completion times and AI priority scores | Defer. Use factual blockers and promises first. No unsupported ETA or opaque ranking. |
| AI-written daily summary | Optional later, grounded in the same verified projection. It cannot replace counts, reasons or direct actions. |
| Generic tasks/to-do widget | Defer unless recurring shop duties have a real owner, due date and completion log. Do not invent work to fill empty space. |
| Full activity feed in the main slot | Keep in Activity. History informs investigation but does not establish current obligations. |
| Drag-and-drop status changes from Overview | Exclude initially. Existing record workflows own authorization, completion and financial effects. |
| Arbitrary widget builder | Defer until validated role defaults exist. Personalization must not hide required review or change permissions. |

## 8. Ranking, scope and quiet-day behavior

### Deterministic ranking

1. Recorded safety/release restrictions or uncertain financial outcomes requiring review, if present and within the user's responsibility. Do not manufacture either from missing information.
2. Overdue customer promises, plus due-today work with a recorded blocker.
3. Work another person can perform immediately after this action: review, approval preparation, assignment, receiving.
4. Due/overdue collections and supplier-credit follow-up using valid due dates and trustworthy balances.
5. Routine replenishment and next-business-day preparation.

Within a band: earliest valid deadline, then oldest known waiting timestamp, then stable record ID. Unknown timing is a separate visible state, not infinitely old or zero. Show the reason, such as “Promised finish passed,” rather than an unexplained priority score. Do not re-sort while a row has keyboard focus or an open action.

The order is a proposed default, not a claim that every shop shares one urgency policy. It is reviewable without arbitrary numerical weights. True safety incidents and financial uncertainty are review tasks, never automated mutation instructions.

Do not introduce a four-hour customer-response SLA or supplier-return deadline merely because a competitor or legacy UI uses one. Existing contractual deadlines and explicit follow-up dates take precedence. Without them, report elapsed waiting time without calling it overdue.

### Required states

| State | Required result |
|---|---|
| No active repairs; closeout exists | Next actions surfaces closeout. Parts, commitments and authorized financial work remain visible. |
| No active repairs; verified debts exist | Collections appears with due date and source-correct balance. No repair needs to be reopened to find it. |
| No repairs; restock or cores exist | Purchasing/returns remains actionable. No giant empty-job area. |
| New month or date filter changes | Unresolved work from prior months remains. Only outcome reports change period. |
| Everything checked, no work waiting | Explicit scoped all-clear; next recorded commitment and existing new-order actions remain. No fabricated tasks. |
| A source fails or is stale | Healthy components render; affected component shows unavailable/last-checked state. Never show all-clear or convert missing values to zero. |
| Search/filter matches nothing | Show filter-specific empty state and Clear filters. Do not imply the shop is empty. |
| Mechanic has no assigned work | Show personal all-clear, permitted team/contact destination and upcoming assigned work. No shop-wide finance or unrelated jobs. |
| Role/tenant changes | Clear old previews immediately; new scope drives counts and actions before rendering. No stale financial flash. |

## 9. Source feasibility and engineering handoff

The source links below are pinned to the inspected main revision. They prove available implementation, not independent production acceptance of every endpoint.

| Area | Owning source | Implication |
|---|---|---|
| Landing composition | [DashboardHome](https://github.com/mecaniser/truck-pit-stop/blob/9d72b77788edee7d54394df43d82d52c01943202/frontend/src/features/dashboard/DashboardHome.tsx), [Action ledger](https://github.com/mecaniser/truck-pit-stop/blob/9d72b77788edee7d54394df43d82d52c01943202/frontend/src/features/dashboard/ShopCockpitActionLedger.tsx) | Preserve existing views and canonical selected-order route. Status-derived Payment Due is not collectible money. |
| Work aging | [DB-145 contract](https://github.com/mecaniser/truck-pit-stop/blob/9d72b77788edee7d54394df43d82d52c01943202/docs/contracts/db145-shop-work-aging.md), [service](https://github.com/mecaniser/truck-pit-stop/blob/9d72b77788edee7d54394df43d82d52c01943202/backend/app/services/wip_aging.py) | Reuse category/clock/assignment rules. The endpoint supplies counts before paging. |
| Legacy dashboard/daily work | [dashboard endpoints](https://github.com/mecaniser/truck-pit-stop/blob/9d72b77788edee7d54394df43d82d52c01943202/backend/app/api/v1/endpoints/dashboard.py) | Some queues are capped and expose `has_more`. Legacy `pending_invoices` counts completed ROs; low-stock count is length of a list limited to ten. Neither is an accurate substitute for the new proposed metric. |
| Purchasing | [parts operations](https://github.com/mecaniser/truck-pit-stop/blob/9d72b77788edee7d54394df43d82d52c01943202/backend/app/api/v1/endpoints/parts_operations.py), [models](https://github.com/mecaniser/truck-pit-stop/blob/9d72b77788edee7d54394df43d82d52c01943202/backend/app/db/models/parts_operations.py), [workspace](https://github.com/mecaniser/truck-pit-stop/blob/9d72b77788edee7d54394df43d82d52c01943202/frontend/src/features/inventory/PurchasingWorkspace.tsx) | Summary, demand, POs, receipts, cores and returns exist. `view` and `purchase_order` are existing navigation inputs. Current purchase preparation is browser-session state, not a shared cross-user task source. |
| Customer accounts | [receivables service](https://github.com/mecaniser/truck-pit-stop/blob/9d72b77788edee7d54394df43d82d52c01943202/backend/app/services/customer_receivables.py), [authorization](https://github.com/mecaniser/truck-pit-stop/blob/9d72b77788edee7d54394df43d82d52c01943202/backend/app/api/v1/endpoints/customer_receivables.py) | Native collectible totals carry completeness flags; ETS history has unavailable/noncollectible balance. Reuse semantics, not an N+1 scan of every customer account on landing. |
| Scheduling | [repair order model](https://github.com/mecaniser/truck-pit-stop/blob/9d72b77788edee7d54394df43d82d52c01943202/backend/app/db/models/repair_order.py), [appointment model](https://github.com/mecaniser/truck-pit-stop/blob/9d72b77788edee7d54394df43d82d52c01943202/backend/app/db/models/appointment.py) | Scheduled starts, promises and linked appointments can support a combined view after deduplication and lifecycle rules. |
| Messages | [thread model](https://github.com/mecaniser/truck-pit-stop/blob/9d72b77788edee7d54394df43d82d52c01943202/backend/app/db/models/message_thread.py) | Unread is supported. Reply obligation cannot be inferred from unread alone. |

### Proposed overview contract

Architecture & API Contracts should own a new bounded, read-only projection before frontend/backend implementation. It should return:

- `as_of`, shop timezone/business date, actual authorized scope and capabilities;
- per-component `available`, `partial`, `unavailable` or `not_enabled` state, source timestamp and coverage;
- authoritative totals independent of preview length, `has_more`/cursor and explicit units;
- task identity, canonical record identity, type, reason, responsible role/person, due/wait evidence, destination and safe action availability;
- money as decimal strings with currency, financial basis, source owner and completeness;
- separate preview lists and an exact drill-down contract, with matching filters and count semantics.

Apply tenant and permission scope before every join, count and preview. Financial values must be absent from unauthorized responses, not merely hidden by CSS. Mechanic aggregates must retain the narrow assignment scope; do not copy a broader legacy endpoint's result and filter only its displayed rows. Cache keys include tenant, user and relevant capabilities. Clear caches on scope change.

Reuse canonical read services. Do not duplicate workflow status or financial balance logic in React. Do not fetch every account or thousands of inventory rows to assemble landing metrics in the browser. Financial snapshots and their previews must be internally consistent; if component snapshots have different timestamps, expose that instead of claiming global atomicity.

A source failure should degrade one component rather than blank the page. Refresh on relevant existing invalidation events and use bounded background refresh. Opening the overview must not mark messages read, acknowledge tasks, run reconciliation, retry providers or mutate workflow state.

### Delivery sequence

1. **Truth and navigation foundation:** Overview shell, canonical action model, scope/freshness states, existing active-work/closeout destinations and no-active-work behavior. Frontend & UX owns composition; Architecture owns any new projection.
2. **Daily operations:** Parts demand/deliveries/returns, deduplicated commitments, role-aware team and unread messages. Backend & Integrations owns aggregates; independent QA verifies changed journeys.
3. **Financial overview:** Source-correct shop-wide receivables and outcome metrics. Requires financial contract review, independent Security/QA, ledger parity, safe fixtures and explicit release evidence. Do not make unsafe totals a prerequisite for shipping useful operational visibility; show the honest unavailable state until ready.
4. **Measured additions:** Persistent reply-needed tasks, supplier AP, fleet/PM, recommendation follow-up and limited personalization only after their sources and ownership are real.

This sequencing is not permission to ship a shell with empty promises. The first usable release must show real closeout and real purchasing work when active jobs are zero, or explicitly identify unavailable sources. Each slice requires its own acceptance evidence and focused PR. No merge/deployment approval is requested by this document.

## 10. Acceptance before implementation is considered complete

1. A new staff user identifies their next permitted action within ten seconds in busy, quiet and exception fixtures. Treat ten seconds as a proposed usability target, not a measured result.
2. The supplied zero-active/one-closeout scenario leads directly to the existing closeout record from Overview.
3. A zero-dollar invoiced record never creates a collectible amount or a “collect $0” action.
4. A genuine partial invoice uses verified remaining principal; cash fee residuals, pending attempts, refunds, credits and superseded/cancelled invoices follow canonical financial rules.
5. Imported/shared ETS invoice context appears once and never becomes native collectible debt by inference. Unknown stays unknown.
6. Counts remain correct beyond the preview limit and match the complete destination filter. No summed overlapping categories or page-length totals.
7. Covered stock, draft/submitted POs, partial receipts, missing supplier, archived parts and unknown ETA produce distinct, correct actions.
8. Returns/core obligations do not double-count; expected credits never appear as received cash. Missing return deadlines are not overdue.
9. Appointment/RO links deduplicate; cancelled/no-show/pending-payment appointments are not confirmed arrivals. Promises follow shop timezone, including daylight-saving boundaries.
10. Mechanic, receptionist, owner/admin-without-payments, authorized financial user, cross-tenant and role-switch tests prove rows and counts cannot leak.
11. Partial failure, stale data, not-enabled modules, filtered empty and complete all-clear states remain visibly distinct.
12. Unread messages are not labeled unanswered. Opening Overview sends nothing and changes no message/task/payment state.
13. A record action opens the exact authorized destination in one activation; Back retains useful scope and filters. No dead or generic homepage links.
14. Desktop, short laptop, tablet and 390/320px mobile layouts preserve readable priorities, keyboard access, focus and touch targets without page overflow.
15. Changed components pass focused tests and signed-in runtime acceptance. Financial/tenant-sensitive additions require independent gates. Board state records actual PR, merge and deployment evidence before Done.

### Measure usefulness after rollout

Measure time to first relevant record, overview-to-record task completion, stale-task rate, false or duplicate action reports and time spent searching other modules. Compare overdue promises, closeout age, uncovered-parts age and supplier-credit age over equivalent working periods. Segment by role and workload. Set improvement targets after a baseline; do not claim a revenue uplift from dashboard design alone.

## 11. Final product recommendation

Build a **task-first Overview with compact supporting components**. Keep current focused work views. Make closeout, parts, commitments and communication visible independently of active repairs. Use financial totals only when their source and completeness justify them.

The inclusion test is strict: if a component cannot identify a decision, responsible user, reliable source and next destination, it does not belong on the starting board.
