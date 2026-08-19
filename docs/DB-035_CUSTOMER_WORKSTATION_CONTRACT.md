# DB-035C Customer Workstation Contract

Status: Accepted for implementation  
Accountable owner: Frontend & UX Recovery Owner  
Presentation boundary: existing authenticated presentation flag

## Outcome

Customers becomes the canonical, page-owned customer workspace in the new
presentation. Selecting a customer opens their real account, vehicle,
relationship, balance, contact, and repair-history capabilities without moving
the primary work into a Sidekick drawer. The legacy presentation retains the
existing Sidekick unchanged as immediate rollback.

## Interaction and URL ownership

- `/dashboard/customers` remains the only route.
- `?selected={customerId}` is additive stable selection state. Unrelated query
  parameters are preserved across selection and dismissal.
- Reload and browser Back/Forward restore selection from the URL.
- At wide desktop and tablet widths, the customer navigator and selected
  workspace remain visible together.
- Below 960px, selection transitions from the list to a full-page customer
  workspace with an explicit **Back to Customers** action. Back restores focus
  to the originating customer row.
- Vehicle drilldown stays inside the customer workspace and returns to the
  selected customer; it does not open another drawer.
- Every new-presentation navigator record exposes a **Details** disclosure.
  Inspection is local, read-only navigator state: it never changes `?selected`,
  navigates, replaces the canonical workspace, or starts a parallel query.
- At most one customer is inspected. The inspected customer may differ from the
  selected customer; explicit record activation or **Open customer** alone
  changes canonical selection. The flat brief reuses row facts and already
  cached contact, vehicle, and history results without nested-card styling.

## Source and capability ownership

The existing Customers page hooks, query keys, endpoints, permission checks,
and mutations remain authoritative. The workstation reuses the current:

- identity and account overview;
- balance and customer contacts;
- vehicles and relationship roles;
- customer and selected-vehicle repair history;
- permitted edit, merge, and delete actions.

Transactional create/edit/merge/delete confirmations may remain dialogs. No
backend, API, migration, auth, customer model, or business-logic change belongs
to DB-035C.

## Failure and accessibility contract

- Loading, empty, unavailable/deleted, forbidden, and error states are coherent
  and do not enumerate customer existence.
- The workspace is a labelled region with semantic tabs.
- Customer rows support pointer and keyboard activation; selection moves focus
  to the customer workspace heading.
- Details uses `aria-expanded`/`aria-controls`, toggles with native Enter/Space,
  preserves workspace focus, and restores disclosure focus when closed.
- Compact targets remain at least 44px with logical focus order.
- Themes, forced colors, reduced motion, and normal text contrast remain valid.

## Acceptance

- New presentation shows no customer Sidekick; legacy presentation still does.
- Selection, deep link, reload, Back/Forward, and unrelated query preservation
  are covered by focused tests.
- Existing customer, vehicle, contact, history, balance, mutation, and role
  behavior remains covered without duplicated query state.
- Selected and inspected customers can differ; one disclosure is open at a
  time, remains flat at compact widths, and causes no URL or request change.
- Authenticated checks at 1440, 960, 390, and 320 show no page overflow and a
  usable list-to-workspace hierarchy.
- Focused/full frontend checks, production build, changed-file lint/diff,
  computed contrast, and the final Impeccable detector complete before Product
  review. Independent QA remains a separate gate.
