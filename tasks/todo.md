# Customer Zelle Panel Price Builder Redesign (2026-07-06)

## Plan
- [x] Extract the duplicated customer Zelle payment UI into one shared panel.
- [x] Redesign the panel with Price Builder-style dense sections, status pills, copy rows, and separated sender details.
- [x] Apply the shared panel to both standalone invoice and embedded portal invoice flows.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] User requested a redesign using the Price Builder UI philosophy.
- [x] Added shared `ZellePaymentPanel` with compact header, status pills, copy-ready payment rows, and a separated sender-details submission section.
- [x] Replaced duplicated inline Zelle UI in both standalone invoice and embedded portal invoice flows.
- [x] Correction: remove remaining box-in-box framing, remove duplicate payment amount display, and make copy controls live inline with the values they copy.
- [x] Hide/avoid the card payment CTA after the customer submits Zelle payment and pending confirmation owns the payment state.
- [x] Passed focused lint:
  `npx eslint src/features/customer-portal/CustomerInvoicePage.tsx src/features/customer-portal/CustomerPortalPage.tsx src/features/customer-portal/ZellePaymentPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed full frontend TypeScript:
  `npx tsc --noEmit --pretty false` (from `frontend/`)
- [x] After correction, passed focused lint again:
  `npx eslint src/features/customer-portal/CustomerInvoicePage.tsx src/features/customer-portal/CustomerPortalPage.tsx src/features/customer-portal/ZellePaymentPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] After correction, passed full frontend TypeScript again:
  `npx tsc --noEmit --pretty false` (from `frontend/`)

## Review
- The customer Zelle payment UI now uses one flat payment surface with inline copy actions, no duplicate amount display, edit-gated sender details, and card payment hidden while Zelle is pending confirmation.

---

# Zelle Sender Details Edit Gate (2026-07-06)

## Plan
- [x] Split Zelle UI into garage payment instructions and customer sender details.
- [x] Make sender email/phone/note editable only after an Edit action.
- [x] Apply the pattern to both customer invoice Zelle surfaces.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] User clarified sender mobile/account details should be editable, but hidden behind an Edit button, with clear color separation between payment instructions and submitted sender details.
- [x] Kept garage payment instructions/copy targets in the existing blue section.
- [x] Added an amber `Your sender details` section with read-only prefilled fields and an `Edit` / `Done` toggle.
- [x] Applied the pattern to both `CustomerInvoicePage` and the embedded invoice view in `CustomerPortalPage`.
- [x] Passed focused frontend lint:
  `npx eslint src/features/customer-portal/CustomerInvoicePage.tsx src/features/customer-portal/CustomerPortalPage.tsx --max-warnings 0` (from `frontend/`)

## Review
- Customers now clearly see which values to use for paying the garage versus which sender details will be submitted to staff, and sender fields cannot be changed without explicitly choosing `Edit`.

---

# Customer Invoice Zelle Copy/Prefill (2026-07-06)

## Plan
- [x] Add copy-ready Zelle amount and invoice memo to customer invoice payment UI.
- [x] Pre-populate Zelle sender email and phone from known customer/user details.
- [x] Ensure customer/guest Zelle submissions send sender details to staff even when fields are left unchanged.
- [x] Run focused frontend/backend verification and document the result.

## Progress Notes
- [x] Found both invoice Zelle surfaces: standalone `CustomerInvoicePage` and embedded invoice payment UI in `CustomerPortalPage`.
- [x] Confirmed backend already stores `sender_email` and `sender_phone` and forwards them in pending-Zelle staff alerts, but customer portal submission accepts nulls when the UI fields are blank.
- [x] Added copy-ready rows for exact Zelle amount and Zelle memo on both customer invoice surfaces.
- [x] Pre-populated sender email/phone from the logged-in customer user and defaulted the staff note to the invoice memo.
- [x] Backend customer and guest Zelle submit endpoints now fall back to known customer email/phone when the sender fields are omitted.
- [x] Pending-Zelle staff alerts now use the no-fee Zelle amount instead of the card total.
- [x] Passed focused backend verification:
  `./.venv/bin/python -m pytest backend/tests/test_zelle_websocket_updates.py backend/tests/test_payments_submit_zelle_rate_limit.py -q`
- [x] Passed focused frontend lint:
  `npx eslint src/features/customer-portal/CustomerInvoicePage.tsx src/features/customer-portal/CustomerPortalPage.tsx --max-warnings 0` (from `frontend/`)
- [x] Full frontend TypeScript remains blocked by existing unrelated `QuoteApprovalPage.tsx` errors for missing quote-fee variables (`shop_supplies_amount`, `service_fee_amount`, `tax_amount`, `estimated_card_total`, `estimated_zelle_total`, `zelle_savings_amount`).

## Review
- Zelle instructions now make the exact payment amount and invoice memo copy-ready, and customer sender details are submitted to staff even when the customer does not edit the prefilled fields.

---

# Price Builder Repair Order History Timeline (2026-07-06)

## Plan
- [x] Inspect available repair-order, quote, invoice, technician, and payment timestamps/actor fields.
- [x] Add a redesigned action-history section to the Price Builder drawer.
- [x] Include created date/time and key workflow events such as sent, approved, assigned, started, completed, invoiced, and paid when data exists.
- [x] Wire parent page data into the panel without reviving legacy blocks.
- [x] Move the history into the add-bar tab row after `Labor Book Time` and keep it hidden by default.
- [x] Run focused frontend verification.

## Progress Notes
- [x] User reported the repair order created date is not visible and requested a history of completed actions with dates/times and approver context.
- [x] Confirmed current data includes repair-order created/assigned/acknowledged/started/completed timestamps, quote created/sent/updated timestamps, and invoice created/paid/Zelle-pending timestamps.
- [x] Confirmed the quote model does not currently store a dedicated `approved_at` or customer approver id; approval history uses quote `updated_at` when `is_approved` is true and displays the customer/company as actor.
- [x] Added a `Repair order history` timeline section to `PriceBuilderPanel`.
- [x] Built and passed history events from `RepairOrdersPage` into the redesigned drawer.
- [x] User asked to keep history collapsed by default and place it inline with the operation/part/labor book time selector.
- [x] Removed the always-visible history card from the top of the drawer content.
- [x] Added `History` as the fourth add-bar tab after `Labor Book Time`; selecting it shows the timeline and hides the search palette.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx src/features/repair-orders/RepairOrdersPage.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Repair-order history is now collapsed by default because the drawer opens on `Operation`; selecting the `History` tab displays the timeline inline with the add-bar controls.

---

# Quote Fees And Invoice Drawer Details (2026-07-06)

## Plan
- [x] Trace current quote totals, invoice totals, and repair-order drawer invoice controls.
- [x] Add up-front estimated shop supplies, service fee, tax, and payment-option totals to quote surfaces.
- [x] Show actual invoice details in the redesigned Price Builder drawer for invoiced/paid repair orders.
- [x] Move invoice controls to the Price Builder drawer footer and remove the standalone invoice action card from the body.
- [x] Hide recommended services for invoice-state repair orders where they no longer belong in the billing view.
- [x] Run focused backend/frontend verification.

## Progress Notes
- [x] Started from the confirmed current behavior: quote total is repair net total only, while invoice creation later adds shop supplies, service fee, and tax.
- [x] Added shared checkout-fee math using the net repair total, shop supplies, service fee, tax, card total, Zelle total, and Zelle savings.
- [x] Updated invoice creation and invoice portal Zelle amount to use shared checkout math.
- [x] Added estimated checkout totals to quote email and quote approval page.
- [x] Expanded the redesigned Price Builder shell to `invoiced` and `paid`, with invoice detail rows in the panel body.
- [x] Moved invoice action entry points to the panel footer and added a compact payment-method modal for the redesigned shell.
- [x] Hid recommended services in invoice-state drawer views.
- [x] Passed focused backend tests:
  `./.venv/bin/python -m pytest backend/tests/test_pricing.py backend/tests/test_price_locking_rules.py -q`
- [x] Passed focused frontend lint:
  `npx eslint src/features/quote-approval/QuoteApprovalPage.tsx src/features/repair-orders/PriceBuilderPanel.tsx src/features/repair-orders/RepairOrdersPage.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Quote approvals now show estimated checkout totals up front, and invoice-state repair orders use the redesigned drawer with invoice details and footer actions instead of the old standalone invoice card.

---

# Price Builder Legacy Time Tracking Header Cleanup (2026-07-06)

## Plan
- [x] Confirm the top `Time Tracking` block is rendered outside the redesigned Price Builder panel.
- [x] Hide that legacy block when the redesigned panel owns the repair-order shell.
- [x] Run focused frontend verification.

## Progress Notes
- [x] Found the `Time Tracking` block in `RepairOrdersPage.tsx` immediately before `PriceBuilderPanel`, so it is legacy content above the redesigned drawer.
- [x] Added a `priceBuilderOwnsShell` guard so legacy time tracking does not render above the redesigned drawer.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/RepairOrdersPage.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- The redesigned Price Builder shell now starts at its own orange header without the old `Time Tracking` header block above it.

---

# Customer Portal Assigned Repair Visibility (2026-07-06)

## Plan
- [x] Compare staff customer profile repair-order visibility with customer portal dashboard filters.
- [x] Include technician-assigned workflow statuses in customer portal active repairs.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed staff `CustomersPage` fetches `/repair-orders?customer_id=...` with no status filter, so assigned repair orders should be returned.
- [x] Confirmed customer portal dashboard active repair filters excluded `assigned` and `acknowledged`, so an RO disappeared after assignment until work started or moved to pending review.
- [x] Added shared customer active repair statuses including `approved`, `assigned`, `acknowledged`, `in_progress`, `pending_review`, and `completed`.
- [x] Added customer portal badge colors for `assigned` and `acknowledged`.
- [x] Passed focused frontend verification:
  `npx eslint src/features/customer-portal/CustomerPortalPage.tsx --max-warnings 0 && npx tsc --noEmit -p .` (from `frontend/`)

## Review
- Assigned and acknowledged repair orders now remain visible in the customer portal dashboard's Active Repairs section and count.

---

# Quote Approval Portal Open 500 (2026-07-06)

## Plan
- [x] Trace quote approval portal resolve/create flow from the customer email page.
- [x] Reproduce the `/quotes/portal/create` database error with focused backend coverage.
- [x] Patch the portal-create account/link handling so approved quote customers can open the portal.
- [x] Run focused backend verification and document the result.

## Progress Notes
- [x] User reported `POST /api/v1/quotes/portal/create` returns 500 with generic `Database error` after quote approval.
- [x] Confirmed frontend calls `/quotes/token/{token}/portal-resolve`, then `/quotes/portal/create` with the returned portal enrollment token.
- [x] Found backend portal create inserts `UserCustomerLink` for existing customer users without checking whether that link already exists first.
- [x] Added a regression test for an approved quote customer who already has both a portal `User` and `UserCustomerLink`; it reproduced the backend crash via async SQLAlchemy object expiration after rollback.
- [x] Added `_ensure_user_customer_link` in the quote endpoint and switched existing-user portal create branches to check for the link before inserting.
- [x] Passed focused reproduction:
  `./.venv/bin/python -m pytest backend/tests/test_price_locking_rules.py::test_approved_quote_existing_portal_user_with_link_can_open_portal -q`
- [x] Passed focused quote-flow tests:
  `./.venv/bin/python -m pytest backend/tests/test_price_locking_rules.py -q`
- [x] User later reported approved quotes still did not appear on the customer profile.
- [x] Reproduced the duplicate-customer case: an existing portal user was linked to an older customer record with the same email, while the approved quote belonged to a newer duplicate customer.
- [x] Updated quote portal handoff so the active tenant `UserCustomerLink` and `users.customer_id` are retargeted to the approved quote's customer record.
- [x] Passed duplicate-customer focused test:
  `./.venv/bin/python -m pytest backend/tests/test_price_locking_rules.py::test_approved_quote_existing_portal_user_relinks_duplicate_customer -q`
- [x] Re-ran focused quote-flow tests:
  `./.venv/bin/python -m pytest backend/tests/test_price_locking_rules.py -q`

## Review
- Existing quote portal users can now click `Open My Portal` after approval without the duplicate-link rollback that caused `/quotes/portal/create` to return a generic 500.
- New customer portal creation and quote approval API coverage still pass.
- If a quote was created on a duplicate customer record with the same email, opening the portal from that approved quote now points the customer's portal profile at the quote customer so the approved repair order appears.

---

# Unsent Quote CTA Label (2026-07-06)

## Plan
- [x] Confirm why an unsent draft quote changes from `Send quote` to `Update quote` after pricing changes.
- [x] Keep the pre-send CTA customer-action oriented as `Send quote`.
- [x] Preserve the existing behavior that updates the draft before sending when pricing changed.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed `quoteActionLabel` showed `Update quote` for an existing unsent quote whose total differed from the draft.
- [x] Changed unsent existing quotes to keep `Send quote` as the primary action, even when pricing changed.
- [x] Preserved the click behavior: if the unsent draft changed, the handler updates the quote draft first and then sends it.
- [x] Aligned the older workflow block so it no longer shows a separate `Update` step before the first send.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/RepairOrdersPage.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed TypeScript verification:
  `npx tsc --noEmit -p .` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Before the quote is sent to the customer, the CTA stays `Send quote`; pricing changes are saved into the quote automatically as part of that send action.

---

# Customer Portal Repair History Savings (2026-07-06)

## Plan
- [x] Trace customer portal repair history detail payload and UI total calculation.
- [x] Display pre-savings amount, customer savings, and final total in repair history detail.
- [x] Include part savings plus labor/order discounts in the customer-facing savings total.
- [x] Run focused frontend/backend verification and document the result.

## Progress Notes
- [x] Confirmed the customer portal detail view recalculated total from labor + parts before using backend `total_cost`, which hid discounted/net totals.
- [x] Confirmed `RepairOrderDetail` already includes part-level `savings`; added labor/order discount fields to the shared frontend `RepairOrder` type.
- [x] Updated customer portal totals to show `Total before savings`, `Best savings`, and `Final total`.
- [x] Final total now uses backend `total_cost` first, so discounted repair orders display the true customer amount.
- [x] Passed focused frontend lint:
  `npx eslint src/features/customer-portal/CustomerPortalPage.tsx src/types/index.ts --max-warnings 0` (from `frontend/`)
- [x] Passed TypeScript verification:
  `npx tsc --noEmit -p .` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Customer repair details now tell the full pricing story: the undiscounted amount, the customer's savings, and the final amount due/paid.

---

# Price Builder Workflow Status Copy (2026-07-06)

## Plan
- [x] Trace the quote workflow strip and disabled-edit messaging in the repair order detail panel.
- [x] Keep workflow behavior unchanged while making the visible statuses reflect quote approval and technician assignment.
- [x] Replace developer-facing price-lock copy with user-facing disabled-action guidance.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed the redesigned `PriceBuilderPanel` workflow strip hard-coded `Send`, `Approved`, and `Technician` instead of using the parent page's quote/assignment state.
- [x] Passed quote sent/approved state, disabled CTA reason, and assigned technician name from `RepairOrdersPage` into `PriceBuilderPanel`.
- [x] Updated the workflow strip so sent quotes show `Sent`, customer-approved quotes show `Approved`, and assigned orders show the technician name.
- [x] Replaced `Pricing locked (reason). Edit is disabled.` with customer-facing lock copy.
- [x] Added hover guidance to the disabled quote CTA explaining why `Quote approved` / `Awaiting approval` cannot be clicked.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx src/features/repair-orders/RepairOrdersPage.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed TypeScript verification:
  `npx tsc --noEmit -p .` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- The quote workflow UI now changes with the real quote/customer/technician state, and locked quote actions explain the customer-facing reason instead of exposing internal lock metadata.

---

# Mechanic Dashboard Repair Scope Visibility (2026-07-06)

## Plan
- [x] Trace the mechanic dashboard API and UI to confirm why assigned jobs show `0 services`.
- [x] Surface the actual repair-order work scope from current structured labor/parts/PM data instead of only legacy selected services.
- [x] Add focused regression coverage for assigned mechanic jobs with structured repair-order lines.
- [x] Run focused verification and document the result.

## Progress Notes
- [x] Confirmed `/mechanics/my-jobs`, `/mechanics/my-history`, and `/mechanics/my-jobs/{order_id}` only counted/rendered legacy `internal_notes.selected_services`.
- [x] Added mechanic-safe scope assembly from structured labor lines, PM service entries, parts fallback, repair-order description fallback, and legacy selected services fallback.
- [x] Eager-loaded labor and parts rows for mechanic job/history/detail endpoints and loaded PM service entries by repair order.
- [x] Added `backend/tests/test_mechanic_job_scope.py` covering an assigned mechanic RO with structured labor scope.
- [x] Passed focused backend tests:
  `./.venv/bin/python -m pytest backend/tests/test_mechanic_job_scope.py backend/tests/test_repair_order_assign_mechanic_notifications.py -q`

## Review
- Mechanic dashboard cards now count current structured repair-order work scope, and expanded job details show the actual work item names instead of an empty services section for assigned ROs built through Price Builder.

---

# Tenant-Branded Quote Emails (2026-07-06)

## Plan
- [x] Trace quote email send content, subject, SMS footer, and sender headers.
- [x] Add tenant garage name to quote email header/title/subject and email From display name.
- [x] Add regression coverage proving quote emails use the tenant name rather than DieselBridge.
- [x] Run focused backend verification and document the result.

## Progress Notes
- [x] Found quote approval and auto-approval emails in `backend/app/api/v1/endpoints/quotes.py` hard-code `DieselBridge Network` in header and subject.
- [x] Found `send_email` always sends from the global configured email address with no tenant-specific display name.
- [x] Added optional `sender_name` support to `send_email`, formatting the Resend From header as `"Tenant Name" <configured-sender@example.com>`.
- [x] Quote approval and auto-approval emails now load the order tenant and use `Tenant.name` for email subject, visible email heading, and sender display name.
- [x] Quote-send SMS footer also uses the tenant name for consistency with the customer quote notification.
- [x] Added regression coverage for quote-send email branding and email sender formatting.
- [x] Passed focused backend tests:
  `./.venv/bin/python -m pytest backend/tests/test_price_locking_rules.py backend/tests/test_email_service.py -q`

## Review
- Quote emails sent from repair orders now present the Garage Profile tenant name instead of DieselBridge Network in customer-facing quote email branding.
- The underlying sender email address still comes from `RESEND_FROM_EMAIL`; this change sets the display name to the tenant name for quote emails.

---

# Repair Order Price Builder Send Quote Flow (2026-07-06)

## Plan
- [x] Trace the redesigned Price Builder side drawer quote controls against the pre-existing parent quote mutations.
- [x] Restore the customer quote action from the redesigned drawer without changing backend quote semantics.
- [x] Verify with focused frontend checks and document the result.

## Progress Notes
- [x] Confirmed `RepairOrdersPage.tsx` still owns working `createQuoteMutation`, `updateQuoteMutation`, and `sendQuoteMutation` handlers.
- [x] Confirmed the redesigned `PriceBuilderPanel.tsx` footer renders `Send quote` with no click handler or quote workflow props beyond display-only `quoteNumber`.
- [x] Added quote action props to `PriceBuilderPanel` and wired the footer CTA to the parent's existing create/update/send quote mutations.
- [x] Updated the redesigned workflow strip so it shows `Create draft` before a quote exists instead of incorrectly showing `Draft ready`.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx src/features/repair-orders/RepairOrdersPage.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed TypeScript verification:
  `npx tsc --noEmit -p .` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- The redesigned Price Builder side drawer can now create a quote draft, update a changed draft, and send/resend the quote to the customer through the existing backend flow.
- Backend quote semantics were left unchanged; this restores the frontend event wiring that the redesign dropped.

---

# Branch Merge Audit - Task Plan (2026-07-06)

# Price Builder Approve Completion Action (2026-07-06)

## Plan
- [x] Confirm the completion approval UI is still coming from the legacy detail panel.
- [x] Move mileage-out/review-notes inputs into the redesigned Price Builder panel for `pending_review`.
- [x] Make the panel footer primary action become `Approve Completion` in `pending_review`.
- [x] Hide the legacy Labor Breakdown/Approve Completion block when the redesigned panel owns the shell.
- [x] Run focused frontend verification.

## Progress Notes
- [x] Confirmed `Labor Breakdown` and `Approve Completion` render outside `PriceBuilderPanel`, so they appear as old-design content under the redesigned drawer.
- [x] Added a `pending_review` completion review card to `PriceBuilderPanel` using the existing mileage-out and review-notes state.
- [x] Replaced the footer quote CTA with `Approve Completion` only while the redesigned panel is in completion mode.
- [x] Hid the legacy labor breakdown and old orange completion block whenever `priceBuilderOwnsShell` is true.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/RepairOrdersPage.tsx src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Pending-review repair orders now keep completion review inside the redesigned panel: mileage/review notes live in the panel body and `Approve Completion` uses the footer's primary action slot instead of the old standalone section.

---

# Price Builder Technician Assignment CTA (2026-07-06)

## Plan
- [x] Confirm why the technician step stopped being engageable after showing the redesigned panel for approved/assigned states.
- [x] Add assign/reassign technician controls into the redesigned Price Builder panel.
- [x] Wire the controls to the existing assignment mutation and mechanic workload data.
- [x] Run focused frontend verification.

## Progress Notes
- [x] Confirmed the old assign/reassign UI lives in the legacy workflow block hidden when `priceBuilderOwnsShell` is true.
- [x] Confirmed the redesigned workflow strip currently renders `Assign technician` as text only.
- [x] Added a technician picker to the redesigned panel for approved active orders, including reassignment when a technician is already assigned.
- [x] Wired the picker to existing `assignMechanicMutation` and mechanic workload percentages.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/RepairOrdersPage.tsx src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- The assigned technician step is engageable again inside the redesigned Price Builder/detail panel.

---

# Approved Assigned RO Detail Visibility (2026-07-06)

## Plan
- [x] Confirm why approved/assigned repair orders show the sparse legacy detail panel.
- [x] Keep the redesigned Price Builder/detail panel visible for active post-approval states.
- [x] Preserve edit restrictions for approved/assigned work while making line details readable.
- [x] Run focused frontend verification.

## Progress Notes
- [x] Confirmed `PRICE_BUILDER_STATUSES` only included `draft` and `quoted`, so approved/assigned orders fell back to the old sparse workflow panel.
- [x] Expanded the redesigned detail panel to `approved`, `assigned`, `acknowledged`, `in_progress`, and `pending_review`.
- [x] Confirmed Price Builder mutations remain gated to `draft`/`quoted`, so post-approval orders are readable but not editable from the pricing controls.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/RepairOrdersPage.tsx src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Approved and assigned repair orders now keep the redesigned detail/line-item view so staff can see what work is being performed after customer approval.

---

# Quote Approval Portal Login 500 (2026-07-06)

## Plan
- [x] Trace the approved quote portal-account flow from frontend to backend.
- [x] Reproduce `/api/v1/quotes/portal/create` through the actual API route.
- [x] Fix the root cause that can leave the customer approved but not logged in.
- [x] Add regression coverage and run focused verification.

## Progress Notes
- [x] Confirmed quote approval calls `/quotes/token/{token}/approve`, then portal access uses `/quotes/token/{token}/portal-resolve` followed by `/quotes/portal/create`.
- [x] Confirmed the failing request in the screenshot is the portal account creation/login step, not necessarily the quote approval step.
- [x] Reproduced the 500 in the API sequence test: one-time quote portal token consumption called Redis `eval`, but the active Redis client in this environment did not expose `eval`.
- [x] Added a non-Lua fallback for one-time token consumption so portal creation returns auth instead of crashing when `eval` is unavailable.
- [x] Added regression coverage for approve -> portal resolve -> portal create.
- [x] Passed focused backend tests:
  `./.venv/bin/python -m pytest backend/tests/test_price_locking_rules.py backend/tests/test_quote_access_service.py backend/tests/test_pricing.py backend/tests/test_tenant_branding_surfaces.py -q`

## Review
- Customer quote approval still moves the repair order to approved, and the following portal account creation step now succeeds instead of returning 500 when Redis Lua `eval` is unavailable.

---

# Quote Email Savings Section (2026-07-06)

## Plan
- [x] Inspect quote email generation and current savings data available on repair orders.
- [x] Add a customer savings section to quote emails for part savings, labor discounts, and order discounts.
- [x] Include tests proving the quote email renders savings details when discounts exist.
- [x] Run focused backend verification.

## Progress Notes
- [x] Confirmed quote email currently renders parts, labor, parts total, and quote total, but no savings block.
- [x] Confirmed part savings can be derived the same way as Price Builder: `(list_price - unit_price) * quantity` when list is greater than actual unit price.
- [x] Added a quote email `Customer savings` section with part savings rows, labor discount row, order discount row, and total savings.
- [x] Added regression coverage for quote-send email savings content.
- [x] Passed focused backend tests:
  `./.venv/bin/python -m pytest backend/tests/test_price_locking_rules.py backend/tests/test_pricing.py backend/tests/test_tenant_branding_surfaces.py -q`

## Review
- Quote emails now show customer savings when part discounts, labor discounts, or order discounts are present.

---

# Reversible Quote Dirty State (2026-07-06)

## Plan
- [x] Confirm how the app currently decides that a sent quote needs resend.
- [x] Make the quote CTA return to `Awaiting approval` when the RO total matches the last quote again.
- [x] Keep resend enabled when the unapproved RO total differs from the quote.
- [x] Run focused frontend verification.

## Progress Notes
- [x] Confirmed the quote record currently stores `total_amount`, not a full line-item snapshot.
- [x] Confirmed the current local `quoteNeedsUpdate` flag can stay true even after temporary pricing changes are reverted.
- [x] Removed the one-way local dirty flag and made the CTA derive resend state from current RO total versus quote total.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/RepairOrdersPage.tsx src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- If a temporary price change is reverted so the repair order total matches the last quote again, the quote CTA returns to disabled `Awaiting approval`.

---

# Price Builder Quote Awaiting Approval CTA (2026-07-06)

## Plan
- [x] Confirm current side-drawer quote CTA labels and dirty-state behavior.
- [x] Show a disabled `Awaiting approval` state after a quote is sent and unchanged.
- [x] Re-enable the quote action only when an unapproved sent quote has changed pricing/content.
- [x] Notify the parent page when Price Builder drawer mutations change the order.
- [x] Run focused frontend verification.

## Progress Notes
- [x] Confirmed the side drawer currently labels sent quotes as `Resend quote` even when nothing changed.
- [x] Confirmed the parent page already has `quoteNeedsUpdate`, but drawer-internal pricing mutations do not consistently set it.
- [x] Updated the quote CTA state machine: create quote, send unsent quote, awaiting approval for sent-and-unchanged, resend for sent-and-changed, disabled after approval/non-editable status.
- [x] Added a quote total mismatch fallback so stale/reloaded pages can still detect that the order differs from the last quote total.
- [x] Wired Price Builder drawer updates into the parent quote dirty flag.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/RepairOrdersPage.tsx src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- The quote action now waits after a sent quote unless the unapproved repair order changes. Changed sent quotes update the quote first and then resend it.

---

# Sent Quote Discount Revision Unlock (2026-07-06)

## Plan
- [x] Confirm why a sent quote disables discount/price edits.
- [x] Make quote-sent pricing locks non-blocking while the repair order is still quoted and unapproved.
- [x] Keep approved/finalized orders protected by status/real lock rules.
- [x] Update tests and run focused verification.

## Progress Notes
- [x] Confirmed quote send sets `pricing_locked_at` / `pricing_lock_reason="quote_sent"`.
- [x] Confirmed Price Builder summary and backend edit guards treat any `pricing_locked_at` as non-editable, even for still-quoted orders.
- [x] Updated repair-order summary/edit guards and `PriceBuildService` so `quote_sent` is not a blocking lock while status is still `quoted`.
- [x] Updated the hard-lock test to use an approval lock reason and added coverage for quote-sent service and discount revisions.
- [x] Passed focused backend tests:
  `./.venv/bin/python -m pytest backend/tests/test_price_locking_rules.py backend/tests/test_ro_pricing_discounts.py backend/tests/test_pricing.py backend/tests/test_tenant_branding_surfaces.py -q`
- [x] Passed frontend lint:
  `npx eslint src/features/quote-approval/QuoteApprovalPage.tsx src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Sent-but-unapproved quotes can now be revised in Price Builder and resent with discounted pricing. `quote_sent` remains recorded as pricing metadata, but only non-revision lock reasons or finalized statuses block edits.

---

# Quote Resend Discounted Total Fix (2026-07-06)

## Plan
- [x] Trace quote create/update/send total calculation after price-builder discounts.
- [x] Add shared pricing helper for net order total after labor/order discounts.
- [x] Use the discounted net total for quote create/update/send.
- [x] Expose discount amounts in quote-token details and render discount rows on the customer quote page.
- [x] Run focused backend/frontend verification and document the result.

## Progress Notes
- [x] Confirmed quote create/update/send use `get_order_subtotal(order)`, which returns gross parts + gross labor and ignores `labor_discount_amount` / `order_discount_amount`.
- [x] Confirmed customer quote page shows labor and parts rows with no discount rows, so a discounted quote total would otherwise look inconsistent.
- [x] Added `get_order_total(order)` for the customer-facing net total after labor/order discounts.
- [x] Updated quote create/update/send to use the discounted net total.
- [x] Added labor/order discount amounts to quote token details and rendered those discount rows on the customer quote approval page.
- [x] Fixed quote-send `shop_name` lookup in the send path, caught by focused tests.
- [x] Passed focused backend tests:
  `./.venv/bin/python -m pytest backend/tests/test_pricing.py backend/tests/test_price_locking_rules.py backend/tests/test_tenant_branding_surfaces.py -q`
- [x] Passed focused frontend lint:
  `npx eslint src/features/quote-approval/QuoteApprovalPage.tsx src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Resent quotes now use the discounted repair-order total, and customer-facing quote math shows discount rows so labor + parts minus discounts equals the displayed total.

---

# Price Builder Discounts Draft Savings Preview (2026-07-06)

## Plan
- [x] Confirm the Discounts & pricing customer-saves amount currently uses persisted totals.
- [x] Calculate a draft customer-saves preview from staged parts pricing and discount inputs.
- [x] Keep backend recalculation/write behavior behind the Apply button.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed the popover currently displays persisted `customerSavesTotal`, so staged dropdown/input changes do not update the savings preview until Apply/refetch.
- [x] Added a draft savings calculation for the popover using staged Parts pricing mode plus typed labor/order discount values.
- [x] Kept footer savings and backend totals tied to persisted values until Apply is clicked.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Discounts & pricing now previews customer savings immediately while still applying the actual pricing changes only from the Apply action.

---

# Price Builder Unified Discounts Apply Flow (2026-07-06)

## Plan
- [x] Confirm current mixed behavior between Parts pricing and discount fields.
- [x] Stage Parts pricing dropdown changes until Apply is clicked.
- [x] Apply parts pricing mode and labor/order discounts together from one action.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed Parts pricing currently applies immediately on select, while labor/order discounts only apply after `Apply`.
- [x] Added a draft Parts pricing mode so dropdown selection changes only update local popover state.
- [x] Updated Apply to commit the staged Parts pricing mode and labor/order discount fields together.
- [x] Reopening the popover resets the dropdown to the currently applied mode, so un-applied selections do not linger.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Discounts & pricing now has one consistent commit point: changing any field stages the value, and `Apply` saves the pricing changes.

---

# Price Builder Order Total Inline Calculating Label (2026-07-06)

## Plan
- [x] Replace the extra calculating badge with an inline Order Total label state.
- [x] Preserve the total digit animation without adding footer width/height clutter.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] User clarified the calculating component should replace the `Order Total` verbiage rather than taking extra space beside it.
- [x] Removed the separate calculating badge and made the label switch between `Order Total` and `Calculating` with the spinner inline.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- The total animation now uses the existing label slot instead of adding visual clutter.

---

# Price Builder Order Total Minimum Motion Window (2026-07-06)

## Plan
- [x] Confirm why the Order Total animation reads as flicker on fast updates.
- [x] Add a minimum visible calculating/settle window so fast updates still feel intentional.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] User confirmed production updates can complete so quickly that the animation appears as flicker.
- [x] Added a separate visual motion state so the total animation is not tied directly to very short backend pending windows.
- [x] Kept the calculating animation visible briefly and gave the settle animation priority when the total changes.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Fast total updates should now read as a deliberate calculate-and-settle motion instead of a quick flicker.

---

# Price Builder Order Total Motion Feedback (2026-07-06)

## Plan
- [x] Choose an animation pattern appropriate for money totals.
- [x] Animate the Order Total while pricing is updating and when the new total lands.
- [x] Avoid adding a motion dependency for a localized effect.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Chose recirculating/calculating motion over flicker because flicker can make a money total feel unstable.
- [x] Confirmed the app does not currently include Motion/framer-motion, so this should be CSS-only.
- [x] Added an updating animation to the total digits while pricing work is in flight.
- [x] Added a short settle animation when the new total value arrives.
- [x] Added a subtle glow to the `Calculating` status pill and respected `prefers-reduced-motion`.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Order Total now uses a calm recalculating motion rather than a harsh flicker, keeping the value feeling reliable while still visibly updating.

---

# Price Builder Loading Indicators (2026-07-06)

## Plan
- [x] Identify price-affecting mutations and query refetches that should show near Order Total.
- [x] Add a compact updating indicator beside Order Total while pricing data is saving/refetching.
- [x] Add visible loading indicators for backend-backed operation, part, and Labor Book Time search states.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed operation and Labor Book Time search had plain text loading states, while part inventory/suggestion loading had no visible state.
- [x] Confirmed the Order Total area does not currently show when mutations or summary/parts refetches are in flight.
- [x] Added an `Updating` spinner beside Order Total while summary/parts are refetching or price-affecting mutations are pending.
- [x] Added spinner-backed loading rows for operation search, Labor Book Time search, and Part inventory/suggestion loading.
- [x] Added an applying state to the Discounts & pricing Apply button.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Production-slower price-builder actions now provide visible feedback both at the search surface and at the Order Total focus point.

---

# Price Builder Footer Metric Detail Popovers (2026-07-06)

## Plan
- [x] Confirm available line-level data for Parts, Labor, Discounts, and Customer saves.
- [x] Convert the footer metric pills into interactive detail popovers.
- [x] Include discount source details and customer-savings breakdown.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed footer data is already available from `partsUsed`, `summary.lines`, `summary.labor_discount_amount`, `summary.order_discount_amount`, and each part's `savings`.
- [x] Converted Parts, Labor, Discounts, and Customer saves pills into clickable buttons.
- [x] Parts popover lists part name, quantity/unit, unit price, and line total.
- [x] Labor popover lists labor line, hours, hourly rate, and line total.
- [x] Discounts popover lists labor discount and order discount separately when applied.
- [x] Customer saves popover combines per-part list-price savings with labor/order discounts.
- [x] Added outside click/focus and Escape handling for the footer detail popovers.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Footer metric pills now expose useful accounting detail without adding more permanent footer clutter.

---

# Price Builder Discount Reset Controls (2026-07-06)

## Plan
- [x] Confirm how labor/order discounts are currently cleared.
- [x] Add explicit reset controls for labor discount and order discount in the Discounts & pricing popover.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed blank discount fields are already submitted as `0`, but the UI does not expose a clear reset action.
- [x] Added per-field Reset buttons for labor discount and order discount that clear the field before Apply persists the reset.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Labor and order discounts can now be explicitly reset from the Discounts & pricing popover without requiring users to know that blank means zero.

---

# Price Builder Remove Recalculate Footer Action (2026-07-06)

## Plan
- [x] Confirm whether the visible Recalculate button still has a clear role in the redesigned drawer.
- [x] Remove the obsolete footer button and unused frontend mutation/import while keeping backend recalculation support intact.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed the button calls `/price-build/recalculate`, which recomputes labor/service-derived lines and totals but does not apply parts pricing modes.
- [x] Confirmed current add/update/discount/pricing flows already invalidate and refresh totals after mutations.
- [x] Removed the footer Recalculate button, its frontend mutation, and the unused `RefreshCcw` icon import.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- The redesigned Price Builder footer now focuses on totals, discounts/pricing, send quote, and danger actions without exposing a misleading manual refresh control.
- The backend recalculation endpoint remains available for API/internal use.

---

# Price Builder Part Price Reset Toggle (2026-07-06)

## Plan
- [x] Confirm current part price reset behavior.
- [x] Make the reset action toggle between list price and stock cost where stock cost is available.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed the item price popover reset action always sets the draft price to list price.
- [x] Updated the reset action so when the draft price matches list price and stock cost exists, it shows `Reset to stock`; otherwise it shows `Reset to list`.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- The part price popover reset control now toggles between stock cost and list price from the editable draft price.

---

# Price Builder Part Price Margin Draft Sync (2026-07-06)

## Plan
- [x] Confirm why the item price popover margin does not change when Customer price changes.
- [x] Update margin calculation to follow the editable draft price, including Reset to list.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed the popover computes margin from saved `unit_price`, while the input and Reset button only change local `draft` until Apply.
- [x] Changed margin calculation to use the editable draft price first, falling back to saved `unit_price` only when the draft is not numeric.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- The margin preview now updates when the Customer price field changes and when Reset to list changes the draft back to list price.

---

# Price Builder Drawer Viewport Width (2026-07-06)

## Plan
- [x] Confirm whether `90vw` is relative to viewport or a parent container.
- [x] Confirm why the current drawer does not visually occupy 90% of a wide screen.
- [x] Update the repair-order drawer width to use actual desktop 90vw without the 1100px cap.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] `vw` is browser viewport-relative.
- [x] Confirmed `SlidePanel` renders an absolute panel inside a fixed full-screen overlay with `w-full ${width}`, so width classes resolve against the viewport-sized overlay.
- [x] Confirmed the repair-order drawer currently uses `max-w-[max(400px,_min(90vw,_1100px))]`, which caps wide screens at 1100px instead of actual 90vw.
- [x] User confirmed actual 90vw is too wide on desktop.
- [x] Updated the repair-order drawer width to `max-w-full sm:max-w-[90vw] xl:max-w-[72vw] 2xl:max-w-[1400px]`, keeping mobile/smaller screens roomy while bounding large desktop layouts.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/RepairOrdersPage.tsx src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- The drawer no longer stops at the old 1100px cap, but it also no longer expands to full 90vw on large desktop screens.

---

# Price Builder Discounts Popover Focus Close (2026-07-06)

## Plan
- [x] Confirm current Discounts & pricing popover close behavior.
- [x] Add outside focus/click handling without breaking interactions inside the popover.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed the popover only closes from the close button or Apply action; moving focus/click outside does not close it.
- [x] Added trigger/popover refs and document-level `mousedown`, `focusin`, and Escape handling that closes only when the event target is outside both elements.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Discounts & pricing now stays open while interacting with its select/inputs/buttons, and closes when focus or click moves outside the popover.

---

# Price Builder Sticky Parts Pricing Mode (2026-07-06)

## Plan
- [x] Confirm whether Recalculate applies the selected parts pricing mode.
- [x] Confirm how new parts are priced after the user selects Stock price.
- [x] Ensure new part additions respect the active Stock/List pricing mode during the price-builder session.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed Recalculate calls `/price-build/recalculate`, which recomputes labor/service-derived lines and totals but does not rewrite part unit prices.
- [x] Confirmed `/parts/pricing-mode` bulk-updates existing parts only.
- [x] Confirmed new part additions currently omit `unit_price`, so customer repair orders default new parts back to inventory selling/list price.
- [x] Updated the shared add-part mutation so when the active mode is `stock`, newly added standalone and operation-level parts post inventory `cost` as `unit_price`.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Recalculate remains a totals/labor refresh action, not a pricing-policy apply button.
- Parts pricing mode now applies to future part additions while the panel is open, matching the visible dropdown state.
- Longer-term improvement: persist an explicit order-level parts pricing mode if the rule must survive closing/reopening an order before any parts exist.

---

# Price Builder Price Popover Width Check (2026-07-06)

## Plan
- [x] Confirm current price adjustment popover layout and identify why the custom price field overflows.
- [x] Confirm current Price Builder drawer width after branch/rebase work.
- [x] Patch the popover so the customer-price row fits inside the card at narrow widths.
- [x] Run focused frontend verification and document results.

## Progress Notes
- [x] Current source still passes `width="max-w-[max(400px,_min(90vw,_1100px))]"` to the repair-order `SlidePanel`, so the drawer keeps the intended max 90vw behavior with an 1100px cap.
- [x] Found the popover uses a fixed `w-[280px]` card with a single-line label plus a fixed `w-24` input inside a padded label row; that can exceed the available inner width in production rendering/zoom.
- [x] Changed the popover to a responsive `min(320px, calc(100vw - 32px))` width and clamped its fixed-position right edge inside the viewport.
- [x] Reworked the customer-price row from flex sizing to a two-column grid with a bounded input column so the field cannot overflow the card.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- The production overflow was a popover internal sizing issue, not evidence that the Price Builder drawer width change was lost.
- Price Builder drawer width is still configured to fill up to 90vw with an 1100px maximum.

---

## Follow-up: Stale Branch Ancestry Closeout
- [x] Confirm GitHub's `feat/fleet-multi-wo-lifecycle` comparison is stale ancestry, not missing code.
- [x] Record an ancestry-only merge for `origin/feat/fleet-multi-wo-lifecycle` into `main` without changing files.
- [x] Record an ancestry-only merge for the related stale `origin/feat/fleet-work-order-cost-lines` branch.
- [x] Verify `main` tree is unchanged except this task note and confirm stale branches are now ancestors locally.
- [ ] Push the closeout merge to `main`.

## Plan
- [x] Protect current local work by confirming staged/uncommitted state and identifying the active branch commit that still needs integration.
- [x] Bring merge baseline up to date with `origin/main` without losing the active branch work.
- [x] Audit every local and remote branch not merged into `main`/`origin/main`, including whether its commits are already represented by newer merged work.
- [x] Merge or cherry-pick only branch changes that are still accurate and current.
- [x] Run targeted verification after integration.
- [x] Push the resulting `main`.

## Progress Notes
- [x] Confirmed source repo branch was `feat/fractional-part-quantity` and only `tasks/todo.md` was locally modified by this audit plan.
- [x] Used detached worktree `/tmp/TruckPitStop-main-audit` at `origin/main` to avoid disturbing current branch changes.
- [x] Confirmed `feat/fleet-truck-details-modal` unique local commits are patch-equivalent to commits already merged into `origin/main`.
- [x] Confirmed old fleet lifecycle branch tips are stale: the same combined work is represented by merged commit `f169275 feat(fleet): phase 3 — multiple work orders, fleet lifecycle, internal invoice`.
- [x] Cherry-picked the only current missing commit onto `origin/main`: `a1115c7 feat(repair-orders): unify operation/service search, add part suggestions`.
- [x] Verification passed:
  `/Users/sergio/GitHub/TruckPitStop/backend/venv/bin/python -m pytest tests/test_price_build_service.py tests/test_fractional_part_quantity.py tests/test_price_locking_rules.py -q` (26 passed)
- [x] Verification passed:
  `npm test -- --run` from `frontend/` (57 passed)
- [x] Verification passed:
  `npm run build` from `frontend/`

## Review
- The only branch content merged into `main` was the still-current repair-order search/part suggestion work.
- The stale fleet branches were not merged because their relevant content is already on `origin/main` through the later reland/PR sequence.
- Residual risk: remote stale branch refs still exist unless cleaned up separately; they are not needed for `main` correctness.

---

# Notification Position Preference - Task Plan (2026-07-05)

## Plan
- [x] Confirm current toast positioning and existing Appearance preference storage.
- [x] Add a persisted Appearance setting for notification location with top, bottom, and center-top options.
- [x] Wire the global toaster to the saved setting without changing individual toast call sites.
- [x] Run targeted frontend verification and document residual risk.

## Progress Notes
- [x] Confirmed `frontend/src/App.tsx` owns the single global `react-hot-toast` `<Toaster>` and currently pins notifications to `bottom-right`.
- [x] Confirmed `frontend/src/contexts/ThemeContext.tsx` already stores Appearance preferences in `localStorage`, making it the least invasive place for this UI preference.
- [x] Added `theme-notification-position` with `Top`, `Bottom`, and `Center Top` choices in the Appearance panel.
- [x] Updated the global toaster to map the saved preference to `top-right`, `bottom-right`, or `top-center`.
- [x] Passed targeted verification:
  `npm test -- UnifiedSettingsPage --run` (from `frontend/`)
- [x] Passed production build:
  `npm run build` (from `frontend/`)

## Review
- Notification location is now a user Appearance preference and applies globally to all existing toast notifications.
- Default behavior remains bottom-right for users without a saved preference.
- Residual risk: verification covered TypeScript/build and the existing settings test; a live visual pass is still useful to confirm exact placement against dashboard chrome.

---

# Notification Position Preview Toast - Task Plan (2026-07-05)

## Plan
- [x] Confirm the existing Appearance notification-location control can trigger a preview without changing global toast call sites.
- [x] Add a preview toast when selecting `Top`, `Bottom`, or `Center Top`, using the selected position immediately.
- [x] Verify frontend build/test and document results.

## Progress Notes
- [x] User clarified that selecting the notification location should actually play a toast preview.
- [x] Added a per-toast preview override so `Top` plays at `top-right`, `Bottom` plays at `bottom-right`, and `Center Top` plays at `top-center` immediately after selection.
- [x] Passed targeted verification:
  `npm test -- UnifiedSettingsPage --run` (from `frontend/`)
- [x] Passed production build:
  `npm run build` (from `frontend/`)

## Review
- The Appearance location buttons now save the selected preference and immediately play a preview toast in that selected location.
- Existing app notifications still inherit the global saved preference after selection.
- Residual risk: automated checks prove compile/test health; exact visual placement was not browser-screenshot verified in this turn.

---

# Founding Garage Business Email Overflow - Task Plan (2026-04-12)

## Plan
- [x] Audit the garage information review card and confirm why long business emails still escape the container.
- [x] Update the garage information summary layout so the business email stays inside the card at review-step widths.
- [x] Run targeted verification and capture review notes plus residual risk.

## Progress Notes
- [x] Overflow owner confirmed: the garage information review card still placed `Business Email` in the right column of a `sm:grid-cols-2` summary row with no wrapping utility on the value text.
- [x] Patched `frontend/src/features/auth/GarageEnrollmentPage.tsx` so the contact row now stacks `Business Email` beneath `Phone` and wraps the email with `break-all`.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The garage information review card no longer forces long business emails into a narrow right-side column.
- `Business Email` now renders beneath `Phone` and wraps inside the card boundary instead of overflowing past it.
- Residual risk: this was validated by production build only; a quick live pass on the enrollment review step is still the final visual check.

---

# Founding Garage Owner Email Overflow - Task Plan (2026-04-12)

## Plan
- [x] Audit the review-step owner account layout and confirm why long owner login emails escape the card.
- [x] Move the owner login email under the owner name in the review summary and add wrapping protection so long addresses stay inside the container.
- [x] Run targeted verification and capture review notes plus any residual risk.

## Progress Notes
- [x] Overflow owner confirmed: the review card's `sm:grid-cols-2` owner account summary put the long email in a constrained right column with no wrapping utility on the value text.
- [x] Patched `frontend/src/features/auth/GarageEnrollmentPage.tsx` so the owner name spans the full review row and the owner login email now renders directly beneath it with `break-all`.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The owner account review card now stacks the login email under the owner name instead of forcing it into a separate right-side summary column.
- Long owner login emails now wrap within the card instead of overflowing past the container edge.
- Residual risk: this was validated by production build only; a quick live pass on the enrollment review step is still the final confirmation for the exact visual spacing.

---

# Garage Services Nested Scroll Follow-up - Task Plan (2026-03-23)

## Plan
- [x] Confirm the remaining desktop nested scrollbar pair shown in the Services screenshot.
- [x] Remove the garage content-pane scrollbar for Services and Inventory routes while preserving their intended internal scrolling.
- [x] Make Services fill the garage pane cleanly so only its list area scrolls on desktop.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] User screenshot confirmed the remaining nested pair is `MyGaragePage` desktop content scrolling plus the Services list scrollbar.
- [x] Patched `MyGaragePage` overflow ownership by garage sub-route so desktop `services` and `inventory` stop using the garage content-pane scrollbar.
- [x] Refit `ServicesManagementPage` to a height-aware desktop flex layout so the services list remains the sole vertical scrollbar.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Desktop Services now removes the extra garage-pane scrollbar and keeps scrolling inside the services content area instead.
- Desktop Inventory uses the same route-level overflow rule, so it no longer inherits a second garage-pane scrollbar either.
- Residual risk: this was verified by build and screenshot-driven analysis only; a live browser pass is still the final check for confirming the rightmost page scrollbar is gone on `/dashboard/garage/services`.

---

# Garage Inventory Scroll Ownership - Task Plan (2026-03-23)

## Plan
- [x] Audit the dashboard route wrapper and garage page nesting to confirm which container owns vertical overflow on inventory/services.
- [x] Remove the unintended parent desktop scrollbar introduced by the dashboard route wrapper for `garage/*` pages.
- [x] Preserve a single intentional page-level scrollbar inside the garage workspace content pane.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] Confirmed `DashboardLayout` wraps all dashboard routes in `overflow-y-auto`, including `garage/*`.
- [x] Confirmed `MyGaragePage` already provides its own desktop content scroll region, so garage routes currently have nested scroll ownership.
- [x] Patched `DashboardLayout` so `garage/*` keeps the shared route scroller on mobile but switches to `lg:overflow-hidden`, removing the desktop parent scrollbar.
- [x] Added `scrollbar-dark` to the garage content pane so the remaining desktop scrollbar stays on the garage workspace itself.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Desktop garage routes now use a single outer scroll owner at the garage content pane instead of also inheriting the dashboard route wrapper scrollbar.
- Mobile garage routes keep the dashboard wrapper scroll, avoiding regressions from the desktop-only overflow change.
- Residual risk: this was verified by build only; a quick live pass on `/dashboard/garage/inventory` and `/dashboard/garage/services` is still worth doing to confirm the gear menus no longer trigger a parent scrollbar.

---

# Driver Recruiting Agent SOP - Task Plan

## Plan
- [x] Draft ATS-ready SOP scope, objectives, and role responsibilities.
- [x] Define end-to-end pipeline stages with explicit entry/exit criteria and SLAs.
- [x] Create copy-ready candidate message scripts (SMS + fallback email) by stage.
- [x] Define standardized screening questionnaire with answer options and capture fields.
- [x] Implement deterministic pass/fail logic with weighted scoring and disposition rules.
- [x] Map logic to ATS statuses, tags, tasks, and automation triggers.
- [x] Add operational guardrails, QA checks, and KPI dashboard definitions.
- [x] Review for clarity and plug-and-play usability.

## Progress Notes
- Initialized planning artifact for this deliverable.
- Added ATS-ready SOP at `docs/DRIVER_RECRUITING_AGENT_SOP.md`.
- Added import templates:
  - `docs/templates/driver_message_scripts.csv`
  - `docs/templates/driver_screening_questions.csv`
  - `docs/templates/driver_decision_rules.json`
- Verified template formatting and schema consistency against SOP sections.

## Review
- Deliverable is implementation-ready for most ATS automation builders.
- Remaining adaptation required: map exact field names/status IDs to your specific ATS vendor.

---

# SEO Improvements - Task Plan (2026-03-02)

## Plan
- [x] Audit existing SEO assets (sitemap, robots, metadata, canonical tags).
- [x] Improve public page metadata with consistent tags for title, description, canonical, robots, Open Graph, and Twitter.
- [x] Add structured data for crawlable public pages.
- [x] Ensure `/sitemap.xml` is served from production backend static routes.
- [x] Align sitemap contents with canonical, indexable public pages and include `lastmod`.
- [x] Verify changes with targeted checks and frontend build.
- [x] Add review notes and residual risks.

## Progress Notes
- [x] Initialized SEO implementation plan using the `seo` skill workflow.
- [x] Added reusable page-level SEO utility: `frontend/src/lib/seo.ts`.
- [x] Upgraded public page tags and JSON-LD on landing and enrollment pages.
- [x] Added `noindex, nofollow` metadata for login.
- [x] Updated root static SEO tags in `frontend/index.html`.
- [x] Updated crawl directives in `frontend/public/robots.txt`.
- [x] Updated sitemap URLs and `lastmod` in `frontend/public/sitemap.xml`.
- [x] Added backend static route serving for `/sitemap.xml` in `backend/app/main.py`.
- [x] Verified frontend build succeeds with `npm run build`.

## Review
- SEO foundation is now in place for indexable marketing pages (`/` and `/enroll`).
- Login and private application surfaces are explicitly de-prioritized for indexing.
- Residual risk: static sitemap `lastmod` values require manual updates when content changes.

---

# Internal Labor Memory - Task Plan (2026-03-15)

## Plan
- [x] Audit the existing price-builder flow and identify all active MOTOR/provider runtime references.
- [x] Replace the external-provider lookup path with an internal operation library plus persistent learned labor memory.
- [x] Remove active MOTOR-specific runtime modules/config/model exports from the internal-only flow.
- [x] Upsert learned labor memory from applied and edited repair-operation lines so future matching jobs reuse saved hours.
- [x] Add/adjust backend tests for library search, custom fallback, and learned-memory reuse behavior.
- [x] Run targeted backend verification and capture residual risks.

## Progress Notes
- [x] Confirmed active working-tree edits in price-builder files so implementation must preserve those changes.
- [x] Added `labor_operation_memory` model and updated Alembic migration `039_add_labor_operation_memory.py` to replace the obsolete cache table.
- [x] Reworked `PriceBuildService` to use internal library suggestions, custom-operation fallback, and saved internal memory only.
- [x] Removed active provider-specific runtime files and config entries tied to MOTOR integration.
- [x] Upserted learned memory from applied and edited repair-operation lines using tenant + year/make/model + operation key.
- [x] Passed targeted verification:
  `venv/bin/python -m pytest tests/test_price_build_service.py -q`
- [x] Passed endpoint import sanity check:
  `venv/bin/python -c "from app.api.v1.endpoints.repair_orders import router; print('ok')"`

## Review
- The active price-builder path is now internal-only: built-in repair-operation suggestions for first use, then tenant-specific learned memory for repeat jobs.
- Matching is intentionally scoped to tenant + vehicle year/make/model + operation identity, so similar fleet vehicles can reuse learned estimates even when VIN differs.
- Residual risk: learned memory currently stores hours only; repair-operation recalc still normalizes the hourly rate back to the tenant labor rate.
- Residual risk: historical migration `038_add_price_builder_and_motor_cache.py` still exists as part of the chain, but migration `039` now removes the obsolete cache on upgrade.

---

# NHTSA-Normalized Labor Memory - Task Plan (2026-03-16)

## Plan
- [x] Audit vehicle create/update paths and the current labor-memory signature.
- [x] Persist decoded NHTSA vehicle attributes on `vehicles` during create/update flows.
- [x] Update labor-memory signature generation to prefer decoded NHTSA attributes with fallback for legacy/manual vehicles.
- [x] Add focused backend tests for NHTSA persistence and decoded-signature matching.
- [x] Run targeted verification and capture residual risks.

## Progress Notes
- [x] Confirmed NHTSA is currently integrated only for VIN decode endpoint/UI, not persisted into `vehicles`.
- [x] Identified all relevant vehicle write paths: `customers`, `vehicles`, and quick repair-order vehicle creation fallback.
- [x] Added persisted `nhtsa_*` snapshot columns on `vehicles` plus migration `040_add_vehicle_nhtsa_snapshot_fields.py`.
- [x] Added `vehicle_nhtsa_service.py` and wired automatic snapshot sync into customer/global vehicle create/update flows.
- [x] Updated labor-memory signature generation to prefer normalized NHTSA attributes while still reading legacy manual signatures.
- [x] Passed targeted verification:
  `venv/bin/python -m pytest tests/test_price_build_service.py tests/test_vehicle_nhtsa_snapshot.py tests/test_vin_decoder.py -q`
- [x] Passed import sanity check:
  `venv/bin/python -c "from app.api.v1.endpoints.customers import router as customers_router; from app.api.v1.endpoints.vehicles import router as vehicles_router; from app.services.price_build_service import PriceBuildService; from app.services.vehicle_nhtsa_service import sync_vehicle_nhtsa_snapshot; print('ok')"`

## Review
- Vehicle records now persist decoded NHTSA attributes so labor-memory matching can use normalized truck specs instead of raw manual text entry.
- Labor-memory reads are backward-compatible with previously stored legacy signatures and will normalize rows to the new signature format on reuse.
- Residual risk: existing vehicles do not auto-backfill NHTSA snapshot fields until they are edited or otherwise re-synced, so older records still rely on manual fallback until refreshed.

---

# Dashboard Readability - Team Capacity (2026-03-16)

## Plan
- [x] Audit the dashboard cockpit and confirm the specific readability bottlenecks in Team Capacity.
- [x] Increase typography and spacing in the Team Capacity panel for shop-floor readability without broad layout churn.
- [x] Adjust any adjacent cockpit text density that still feels visually inconsistent after the Team Capacity uplift.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] Identified the main issue in `frontend/src/features/dashboard/DashboardHome.tsx`: Team Capacity relies on several `text-[11px]` labels with tight vertical spacing, which compresses names, statuses, and load summaries.
- [x] Reworked Team Capacity summary and mechanic cards with larger type, clearer active/queued wording, taller progress bars, and roomier click targets.
- [x] Bumped the adjacent Revenue KPI microtext so the lower cockpit band reads consistently after the Team Capacity uplift.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Team Capacity now prioritizes readability over density: mechanic names, status text, active/queued counts, and utilization summaries all render at a more practical operations-dashboard size.
- Adjacent Revenue KPI labels and helper text were raised slightly to avoid one readable panel sitting next to another still using microtext.
- Residual risk: a live pass with production-length mechanic names and a fully populated team list is still worth checking to confirm the scroll area feels right on the shop's actual display hardware.

---

# Dashboard Layout Priority Pass (2026-03-16)

## Plan
- [x] Confirm the current manager dashboard structure and identify the minimal layout shift that keeps Team Capacity visible at all times.
- [x] Move Team Capacity out of the bottom split layout into a persistent standalone section.
- [x] Make the lower-priority Work Queue section collapsible with a concise summary when collapsed.
- [x] Move Revenue KPIs to the end of the page and simplify them into a more minimal strip.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] Confirmed the current issue: Team Capacity and Revenue KPIs still share the bottom bar, so critical staffing visibility competes with secondary financial metrics for screen space.
- [x] Promoted Team Capacity into its own full-width section above the queue and widened the mechanic grid so staffing stays visible without depending on the page footer.
- [x] Converted Work Queue into a collapsible section with summary chips and refresh controls in the header, defaulting it closed so detail lanes are available on demand instead of consuming fixed vertical space.
- [x] Reduced Revenue KPIs to a compact bottom strip with only four finance numbers plus paid-order context.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Team Capacity now stays visible as a first-class operational panel, while finance information is pushed down and visually de-emphasized.
- The manager dashboard hierarchy is clearer: staffing first, workflow second, revenue last.
- Residual risk: a live usage pass should confirm whether the collapsed-by-default queue matches the shop’s day-to-day rhythm or whether managers want it opened automatically on larger wall displays.

---

# Dashboard Order Follow-up (2026-03-16)

## Plan
- [x] Confirm the current section order in the manager dashboard.
- [x] Move Team Capacity below Work Queue while keeping Revenue KPIs last.
- [x] Run targeted frontend verification and capture the result.

## Progress Notes
- [x] Confirmed the current render order is `Team Capacity -> Work Queue -> Revenue KPIs`, and the requested follow-up is a direct swap of the first two manager sections.
- [x] Moved the Team Capacity panel render block below the collapsible Work Queue without changing its behavior or styling.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Manager dashboard order is now `Work Queue -> Team Capacity -> Revenue KPIs`.
- The change is intentionally minimal: same Team Capacity component, only a lower placement in the page flow.

---

# Dashboard Collapse Correction (2026-03-16)

## Plan
- [x] Confirm the current collapse behavior and the corrected target section.
- [x] Make Work Queue always visible again.
- [x] Move collapse behavior to the bottom Revenue KPI section.
- [x] Run targeted frontend verification and capture the result.

## Progress Notes
- [x] Confirmed the current mistake: Work Queue is the collapsible section, but the user intended collapsibility for Revenue KPIs instead.
- [x] Removed collapse state from Work Queue so the operational lanes stay visible at all times.
- [x] Added the collapse toggle to the bottom Revenue KPI section and kept it collapsed by default for minimal visual weight.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Work Queue is visible again as the always-open operational section.
- Revenue KPIs are now the only collapsible dashboard section in this area, which matches the clarified intent.

---

# Dashboard Work Queue Height Tuning (2026-03-16)

## Plan
- [x] Inspect the current Work Queue height behavior and identify the smallest viewport-fit adjustment.
- [x] Reduce the Work Queue height slightly so Team Capacity and Revenue KPIs fit more reliably within the viewport.
- [x] Run targeted frontend verification and capture the result.

## Progress Notes
- [x] Confirmed the main constraint is the queue lanes' reserved vertical space in `frontend/src/features/dashboard/DashboardHome.tsx`, which still reads tall enough to crowd the sections below on shared dashboard screens.
- [x] Added a modest desktop max-height cap to the Work Queue wrapper and reduced per-lane minimum heights so the queue gives back space without becoming cramped.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Work Queue now takes slightly less vertical space on desktop, which should make Team Capacity and the Revenue footer fit the viewport more reliably.
- The change is intentionally conservative: same layout and content, only tighter queue height constraints.

---

# Dashboard Dynamic Queue Fit (2026-03-16)

## Plan

---

# Railway Alembic Command Diagnosis (2026-03-16)

## Plan
- [x] Reproduce the `railway run alembic upgrade head` failure from the repo context.
- [x] Verify whether the missing path is the local `alembic` executable, the Alembic config location, or another environment assumption.
- [x] Apply the smallest corrective change needed, if any, and document the correct invocation path.
- [x] Verify the corrected workflow and record review notes.

## Progress Notes
- [x] Confirmed the repository’s Alembic config and migration scripts live under `backend/`.
- [x] Confirmed current project docs already instruct migration commands from within `backend/` after activating a Python virtual environment.
- [x] Reproduced the exact Railway CLI failure from the repo root: `railway run alembic upgrade head` returns `No such file or directory (os error 2)` because `railway run` tries to execute a local `alembic` binary and none is present on the root PATH.
- [x] Verified `railway run /bin/sh -lc 'command -v alembic || echo missing'` prints `missing`, which proves the missing file is the executable itself, not the migration folder.
- [x] Verified the repo-root `.venv/bin/alembic` wrapper is also unusable in this checkout because its shebang points at `/Users/sergio/TruckPitStop/.venv/bin/python`, a stale path that no longer exists.
- [x] Verified the backend virtualenv is valid and the safe Railway-backed command works when run from the backend directory context:
  `railway run /bin/sh -lc 'cd backend && venv/bin/python -m alembic heads'`
- [x] Verified root execution with `-c backend/alembic.ini` is still cwd-sensitive in the current config, so the reliable command is to `cd backend` before invoking Alembic.

## Review
- Root cause is local command resolution, not a missing migration file in Railway.
- `railway run` injects Railway environment variables into a command that still runs on the local machine, so the command must reference a real local Python/Alembic executable.
- Correct migration command for this checkout:
  `railway run /bin/sh -lc 'cd backend && venv/bin/python -m alembic upgrade head'`
- Residual risk: if `backend/venv` does not exist on another machine, the virtualenv must be created first with the documented backend setup steps.
- [x] Confirm why the fixed queue reduction felt too aggressive.
- [x] Replace the fixed queue cap with viewport-aware sizing tied to the actual available space.
- [x] Run targeted frontend verification and capture the result.

## Progress Notes
- [x] Confirmed the issue: the previous queue reduction was a fixed desktop trim, but the user wanted the queue height to respond to the viewport and the sections below it.
- [x] Added a measured queue max-height based on viewport height, queue top position, and the live Team Capacity / Revenue section heights.
- [x] Replaced the hard lane-height reduction with a softer `clamp(...)`-based minimum so lane cards shrink more gracefully on shorter screens.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Work Queue height is now dynamic on desktop instead of being forced to a single reduced size.
- Team Capacity and Revenue keep their space, while the queue adapts to what is actually left in the viewport.

---

# Dashboard Hook Order Fix (2026-03-16)

## Plan
- [x] Identify the cause of the runtime hook-order error in `DashboardHome`.
- [x] Move all hooks ahead of loading/error early returns while preserving the dynamic queue sizing logic.
- [x] Run targeted frontend verification and capture the result.

## Progress Notes
- [x] Confirmed the error cause: the dynamic queue sizing `useEffect` was added after conditional early returns, so the component rendered a different number of hooks between loading/error and loaded states.
- [x] Moved the derived dashboard values and dynamic queue sizing `useEffect` above the loading/error returns so hook order stays stable on every render.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The hook-order runtime error is resolved by keeping all hooks ahead of conditional returns.
- Dynamic queue sizing remains in place; only the hook placement changed.

---

# Repair Order Price Builder Status Gating (2026-03-16)

## Plan
- [x] Confirm the current repair-order detail render path and the exact target status mapping for pricing UI.
- [x] Implement full price builder rendering only for `draft` and `quoted`.
- [x] Implement a read-only labor breakdown view for `pending_review` and `completed`.
- [x] Hide the pricing panel entirely for `invoiced` and `paid`.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the current issue: `PriceBuilderPanel` was always rendered in the repair-order detail, even after the order moved into non-editable workflow states.
- [x] Added explicit status gating so `draft` and `quoted` keep the full pricing workflow while `pending_review` and `completed` swap to a compact read-only labor breakdown.
- [x] Hid the remaining builder-related pricing cluster for statuses outside the editable workflow, including `invoiced` and `paid`.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Repair-order pricing UI now follows workflow state instead of rendering the same builder in every status.
- Pending review and completed orders show only a read-only labor breakdown, which keeps historical labor context without exposing dead controls.
- Invoiced and paid orders no longer show the builder area on the repair-order detail view.

---

# Dashboard Scrollbar Refinement (2026-03-16)

## Plan
- [x] Inspect the current scrollbar styling entry points used by the dashboard.
- [x] Reduce scrollbar width and remove the visible track while preserving existing hide behavior.
- [x] Run targeted frontend verification and capture the result.

## Progress Notes
- [x] Confirmed the active scrollbar styling lives in `frontend/src/index.css`, with `.scrollbar-dark` supplying the main custom rail/thumb treatment used by dashboard overflow regions.
- [x] Reworked the scrollbar styling to use a slimmer shared size and a transparent track so only the thumb remains visually prominent.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Dashboard scrollbars now read lighter and take less horizontal space, which better fits the dense operations layout.
- The visible scrollbar track has been removed so the UI shows only the thumb, while existing `.scrollbar-hide` behavior stays intact.

---

# Repair Order Danger Zone Sizing (2026-03-16)

## Plan
- [x] Inspect the current repair-order detail footer and identify why the Danger Zone spans too much horizontal space.
- [x] Reduce the Danger Zone container so it wraps its content instead of stretching across the full footer.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the current issue: the Danger Zone footer used a full-width red wrapper and a full-width toggle button, which made the section read larger than the actual actions required.
- [x] Reworked the footer into a right-aligned inline card with its own border/background so the red area now hugs the toggle and actions instead of spanning the full panel width.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The repair-order Danger Zone now occupies approximately its content width instead of reading like a full-width footer banner.
- The visual emphasis remains intact, but the footer is less heavy and no longer dominates the bottom of the detail panel.

---

# Repair Order Danger Zone Height Correction (2026-03-16)

## Plan
- [x] Reconfirm the intended Danger Zone layout after the user's correction.
- [x] Restore the full-width footer strip and reduce only its vertical padding/height.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the correction: the user wanted the Danger Zone to stay full-width across the repair-order side panel, with only the height reduced.
- [x] Restored the full-width footer strip and tightened its vertical footprint with smaller top/bottom padding, tighter internal spacing, and smaller icon padding.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The Danger Zone is again a full-width strip across the repair-order side panel.
- Only the vertical bulk was reduced, so the footer reads shorter without changing its full-width layout.

---

# Repair Order Danger Action Gating (2026-03-16)

## Plan
- [x] Confirm all current cancel/delete entry points and the statuses they affect.
- [x] Hide the repair-order Danger Zone in the frontend outside the intended pre-billing statuses.
- [x] Add backend guards so cancel/delete requests are rejected once a repair order reaches protected financial/work-complete statuses.
- [x] Run targeted verification and capture review notes.

## Progress Notes
- [x] Confirmed the current issue: the detail view still rendered the Danger Zone broadly, and the backend allowed generic cancel/delete flows without completed-status workflow guards.
- [x] Limited the frontend Danger Zone to `draft` and `quoted` repair orders only.
- [x] Added backend guards so cancel and hard delete are only allowed when the repair order is still `draft` or `quoted`.
- [x] Passed targeted verification:
  `venv/bin/python -m pytest tests/test_repair_order_danger_action_rules.py -q` (from `backend/`)
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The repair-order detail view no longer exposes cancel/delete controls once the order has moved beyond the early pre-billing workflow.
- The API now enforces the same rule, so completed, invoiced, and paid orders cannot be cancelled or deleted through the generic endpoints.

---

# Completed Order Invoice Flow Compaction (2026-03-16)

## Plan
- [x] Inspect the current completed-order invoice card and confirm which controls are truly optional.
- [x] Collapse optional invoice fields behind a compact disclosure while keeping the primary create-invoice action visible.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the current issue: the completed-order card always showed optional due-date and discount fields, which made secondary settings feel mandatory.
- [x] Reworked the card so the primary create-invoice action stays visible while due date and discount live behind an "Optional invoice settings" disclosure with a compact summary.
- [x] Reset the optional invoice state when switching orders, closing the detail panel, or after successful invoice creation so the card reopens in a minimal state.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The completed-order invoice flow is now visually aligned with the underlying logic: optional settings are hidden by default instead of reading like required inputs.
- Staff can still set due date or discount when needed, but the default path is now a simpler single-action invoice creation flow.

---

# Work Queue Header Status Cleanup (2026-03-16)

## Plan
- [x] Confirm where the duplicate work-order status badge is rendered inside the work queue.
- [x] Remove the duplicate status badge from the queue card header while preserving lane-level readiness signals.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the duplicate is the order-level status badge rendered inside each `OrderCard`, even though the three work-queue lanes already categorize the orders by status/actionability.
- [x] Removed the per-card status pill and the now-unused badge-color mapping so the queue cards rely on lane placement plus elapsed/mechanic details instead of repeating status in the header.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The work queue header/cards no longer repeat status information that is already conveyed by the lane structure.
- `Needs Action`, `On the Floor`, and `Ready to Close` remain the primary status framing, which makes the queue header and cards less noisy.

---

# Work Queue Header Chip Correction (2026-03-16)

## Plan
- [x] Reconfirm the exact duplicated status indicators the user meant in the Work Queue header.
- [x] Remove the top-right summary chips from the Work Queue header while preserving the refresh/last-updated control.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the correction: the user meant the header-level summary chips (`Needs Action`, `On Floor`, `Ready`) next to `Just Updated`, not the per-card status pill.
- [x] Removed the header-level summary chip row and the now-unused `workQueueSummary` data, leaving the header with only title, info tooltip, and refresh/last-updated status.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The `WORK QUEUE` header no longer repeats the same lane summary chips that are already implied by the three queue columns below.
- The refresh/last-updated control remains in place, so the header still communicates live status without the duplicated category pills.

---

# Scoped Commit And Push (2026-03-16)

## Plan
- [x] Inspect the working tree with `scoped-commit-assistant` and generate proposed commit boundaries from the existing changes.
- [x] Refine the generated scopes where needed so each commit remains independently reviewable.
- [x] Run the smallest relevant verification for each staged scope and avoid claiming checks that were not run.
- [x] Commit each scope with structured commit messages that explain why, validation, and residual risk.
- [x] Push the resulting commit set from `main` to `origin`.
- [x] Document the final commit list, verification, and push result in this review section.

## Progress Notes
- [x] Confirmed the repo is currently on `main` and the user explicitly asked to commit and push the existing changes.
- [x] Ran the `scoped-commit-assistant` planner against the full working tree to derive an initial six-commit proposal.
- [x] Refined the initial proposal into four reviewable scopes by splitting backend pricing/memory work, repair-order workflow behavior, dashboard layout/readability updates, and task documentation.
- [x] Created commit 1:
  `feat(pricing): internalize labor memory with NHTSA matching`
- [x] Created commit 2:
  `feat(repair-orders): align detail actions with workflow status`
- [x] Created commit 3:
  `feat(dashboard): improve queue fit and team readability`

## Review
- Verification completed before final push:
  `venv/bin/python -m pytest tests/test_price_build_service.py tests/test_pricing.py tests/test_vehicle_nhtsa_snapshot.py tests/test_repair_order_danger_action_rules.py -q` (from `backend/`)
- Verification completed before final push:
  `npm run build` (from `frontend/`)
- Final commit order:
  `feat(pricing): internalize labor memory with NHTSA matching`
  `feat(repair-orders): align detail actions with workflow status`
  `feat(dashboard): improve queue fit and team readability`
  `docs(tasks): capture task history and commit workflow`
- Push target: `origin/main`

---

# Detached Worktree Merge Audit (2026-03-16)

## Plan
- [x] Inventory all git worktrees and identify detached ones.
- [x] Inspect detached worktrees for dirty state, unique commits, and practical merge candidates.
- [x] Verify whether detached worktree behaviors are already present on `main` in newer form.
- [x] Decide whether to merge, port selected deltas, or explicitly skip stale worktree edits.
- [x] Record the audit result and commit only the audit if no safe code merge remains.

## Progress Notes
- [x] Confirmed the active branch is `main` at `a317fe4` before the audit started.
- [x] Found many detached worktrees under `~/.codex/worktrees` and `~/.cursor/worktrees`, but every detached HEAD inspected is already an ancestor of `main`; there are no unique detached commits to merge.
- [x] Narrowed the problem to uncommitted edits inside a subset of detached worktrees.
- [x] Compared those edits against current `main` and confirmed the substantive feature areas are already present in newer form on `main`, including mechanic workflow statuses, mechanic portal routing, points/PTO flows, quote resend/approval behavior, and customer-linking during registration.

## Review
- No detached worktree produced a clean, non-stale code delta that should be merged into `main` without risking regression.
- As a result, no detached worktree code was ported into the active tree during this audit.
- The only commit created from this task is the audit record itself so the repository history reflects why no code merge was performed.

---

# Detached Worktree Cleanup (2026-03-16)

## Plan
- [x] Preserve any dirty detached worktree edits before removal.
- [x] Remove all auxiliary git worktrees and prune stale metadata.
- [x] Verify that only the main checkout remains and record the preservation path.

## Progress Notes
- [x] Stashed dirty detached worktrees with `pre-remove worktree backup` messages that include the original path and detached HEAD for traceability.
- [x] Removed all auxiliary worktrees under `~/.codex/worktrees` and `~/.cursor/worktrees`, then pruned worktree metadata.
- [x] Verified `git worktree list --porcelain` now reports only `/Users/sergio/GitHub/TruckPitStop` on `refs/heads/main`.

## Review
- Detached worktrees have been removed from the machine; only the primary checkout remains attached to `main`.
- Dirty detached worktree contents were not discarded: 19 preservation stashes were created in the main repository before removal.
- Residual risk: those preservation stashes remain in `git stash list` until they are manually reviewed and dropped.

---

# My Garage Left-Rail Navigation (2026-03-16)

## Plan
- [x] Audit the current `MyGaragePage` shell and pin the target render order.
- [x] Replace the top horizontal tab strip with a desktop left-side vertical navigation rail.
- [x] Preserve a compact top navigation pattern on smaller screens so the layout remains usable on mobile.
- [x] Refine the navigation styling so the garage sections read as a dedicated control rail, not generic stacked buttons.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] Confirmed the current shell order in `frontend/src/features/garage/MyGaragePage.tsx` is `horizontal tabs -> routed content`.
- [x] Locked the requested desktop target order for this pass to `left navigation rail -> routed content pane`, with the section list remaining `Mechanics -> Services -> Inventory -> Suppliers -> Analytics`.
- [x] Rebuilt the garage shell around a shared section config so desktop now renders a dedicated left navigation rail with icon-backed items and the content pane shows the active module context above routed content.
- [x] Preserved a compact horizontal module strip for smaller screens so the new navigation pattern does not consume excessive vertical space on mobile.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- My Garage now uses a clearer desktop workspace layout: navigation lives on the left, content stays on the right, and the active module is reinforced with a dedicated header instead of a thin top tab row.
- Mobile keeps the section switcher compact and horizontal, which preserves usability where a permanent left rail would crowd the viewport.
- Residual risk: this is compile-verified, but a live browser pass is still worth doing to confirm the left rail feels balanced against the longest Mechanics and Inventory content states.

---

# My Garage Settings UX Alignment (2026-03-16)

## Plan
- [x] Capture the corrected UX target using the Settings page as the shell reference.
- [x] Refactor `MyGaragePage` so its mobile and desktop navigation patterns match the Settings page behavior.
- [x] Remove custom garage-shell framing that does not exist in the Settings page flow.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] User clarified the issue is UX, not aesthetics: My Garage should follow the Settings page interaction model shown in the screenshot.
- [x] Locked the target shell for this pass to the Settings layout pattern: compact horizontal nav on mobile, sticky left sidebar on desktop, and direct routed content on the right without extra workspace headers.
- [x] Replaced the custom My Garage hero and active-section header with a Settings-style shell that uses the same nav density, grouping, and active-state treatment as `UnifiedSettingsPage`.
- [x] Kept My Garage route-driven so Mechanics, Services, Inventory, Suppliers, and Analytics still deep-link correctly while using the simpler Settings-style sidebar UX.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- My Garage now follows the same interaction structure as Settings instead of a custom workspace shell: compact mobile tabs, sticky desktop sidebar, and direct content rendering on the right.
- The UX is flatter and more predictable because the extra “Shop control” and “Garage workspace” framing has been removed.
- Residual risk: compile verification passed, but a browser pass is still worth doing to confirm the narrower Settings-style shell feels right for the widest Mechanics and Inventory states.

---

# My Garage Docked Sidebar And Settings Access (2026-03-16)

## Plan
- [x] Document the requested docked-sidebar behavior and settings access path.
- [x] Expand the desktop My Garage sidebar so it fills the available viewport-height workspace and can hold a bottom-anchored utility action.
- [x] Add a separate navigation action that routes tenants to `/dashboard/settings`.
- [x] Run targeted frontend verification and summarize which existing Settings sections are the best candidates for future My Garage integration.

## Progress Notes
- [x] Confirmed the current My Garage shell already follows the Settings page interaction model, so this pass can stay focused on vertical sizing and settings access.
- [x] Reviewed the existing Settings sections in `frontend/src/features/dashboard/UnifiedSettingsPage.tsx` to identify which ones are tenant-garage controls versus personal account controls.
- [x] Expanded the desktop My Garage rail into a docked sidebar that fills the workspace height and reserves a dedicated bottom utility zone.
- [x] Added `Profile & Settings` navigation affordances to both desktop and mobile so users can jump from My Garage to `/dashboard/settings`.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- My Garage now reads as a docked workspace: the left rail fills the viewport-height garage area on desktop, while `Profile & Settings` is separated from operational garage modules as a utility action at the bottom.
- Mobile keeps the garage modules in a compact horizontal scroller but now also exposes the same settings jump as a separate action below the module strip.
- After inspecting `UnifiedSettingsPage`, the best candidates to bring closer to My Garage later are garage-scoped controls only: `Garage Profile`, `Workforce`, `Notifications`, `Tax & Fees`, and optionally `Stripe Payments` / `Zelle` if the goal is an operations cockpit. Personal controls such as `Profile`, `Security`, and `Appearance` should stay in the dedicated Settings page.
- Residual risk: viewport-height sizing is compile-verified, but a live browser pass is still worth doing to confirm the dock height feels correct against the actual breadcrumb/header stack on shorter laptop screens.

---

# My Garage Full-Page Sidebar Stretch (2026-03-16)

## Plan
- [x] Capture the correction that the desktop garage rail should stretch to the bottom of the page, not just the viewport.
- [x] Remove the viewport-capped sticky sizing from the desktop garage rail.
- [x] Keep garage module navigation pinned to the top of the rail and account/settings access anchored to the bottom.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] User clarified the desired behavior: the garage options belong at the top, while the account/profile settings route belongs at the true bottom of the page column.
- [x] Confirmed the current issue in `frontend/src/features/garage/MyGaragePage.tsx`: the desktop rail uses `sticky` plus `h-[calc(100vh-9rem)]`, which caps it to viewport height instead of stretching with the page.
- [x] Replaced the viewport-capped sticky rail with a full-height flex column so the sidebar now stretches with the page/content column while still respecting the minimum workspace height.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The desktop My Garage rail now stretches to the bottom of the page column instead of stopping at viewport height.
- Garage modules stay grouped at the top of the rail, while the `Account` section with `Profile & Settings` remains anchored at the bottom.
- Residual risk: compile verification passed, but a live browser pass is still worth doing to confirm the stretched rail looks correct on especially tall or especially short content states.

---

# My Garage Page-Floor Rail Fill (2026-03-16)

## Plan
- [x] Capture the correction that the rail must fill the remaining dashboard page column, not just rely on min-height.
- [x] Make the My Garage route root participate in the dashboard flex layout as a filling child.
- [x] Make the sidebar card inherit that full page-column height so `Account` stays at the true bottom.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] User clarified the remaining issue with the red outline: the left rail itself must reach the page floor, with `Profile & Settings` at the bottom of that full-height column.
- [x] Confirmed the current shell still relies on `min-h-[calc(100vh-9rem)]`, which can leave a gap because the page wrapper is not growing as a true flex remainder inside `DashboardLayout`.
- [x] Changed the My Garage route root to `flex-1` so it fills the remaining dashboard column and lets the desktop rail inherit that real page height.
- [x] Replaced the desktop rail sizing with `min-h-full`/`flex-1` inheritance so the `Account` section now sits at the bottom of the full-height rail instead of a min-height approximation.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The left My Garage rail now fills the remaining dashboard page column, which matches the full-height outline you pointed out.
- Garage navigation remains at the top of the rail, and the `Account` divider with `Profile & Settings` now sits at the bottom of that same full-height column.
- Residual risk: compile verification passed, but I have not done a live browser pass to visually confirm the rail against the exact page chrome in your local viewport.

---

# My Garage Viewport-Constrained Rollback (2026-03-16)

## Plan
- [x] Capture the correction that the My Garage workspace should stay within the viewport and not expand with right-side content.
- [x] Roll back the content-driven height behavior in the My Garage shell.
- [x] Keep the left rail full-height within the visible workspace while making the right content pane scroll internally on desktop.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] User clarified that the prior page-floor fill should be rolled back because the right-side content should not exceed the viewport height.
- [x] Confirmed the current shell issue in `frontend/src/features/garage/MyGaragePage.tsx`: the route root fills available space, but the right pane still grows with content instead of becoming the scroll container.
- [x] Constrained the desktop My Garage workspace to `calc(100vh - 9rem)` and moved overflow ownership to the right content pane with `lg:overflow-y-auto`.
- [x] Kept the desktop rail full-height within that visible workspace so the garage menu remains top-aligned and the `Account` section stays anchored at the bottom.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Desktop My Garage no longer expands with its routed content; the workspace stays within the viewport and the right pane scrolls internally.
- The left rail still fills the visible workspace height, with garage navigation at the top and `Profile & Settings` at the bottom.
- Residual risk: compile verification passed, but a live browser pass is still worth doing to confirm the new internal scrolling feels right in the Mechanics and Inventory pages.

---

# My Garage Content-Driven Height Restore (2026-03-16)

## Plan
- [x] Capture the correction that the My Garage page height should again follow the right-side content.
- [x] Roll back the viewport-constrained shell introduced in the last pass.
- [x] Keep the garage rail structure while restoring page-level expansion based on content height.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] User clarified that the intended behavior is the earlier content-driven page expansion, where the right-side content determines page height.
- [x] Confirmed the current issue in `frontend/src/features/garage/MyGaragePage.tsx`: the desktop shell uses a fixed `lg:h-[calc(100vh-9rem)]` plus internal right-pane scrolling, which conflicts with that model.
- [x] Removed the fixed desktop workspace height and internal right-pane scrolling so My Garage once again expands based on the routed content height.
- [x] Kept the garage rail structure and bottom-anchored `Account` / `Profile & Settings` action intact while restoring page-level height growth.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- My Garage is back to content-driven page height on desktop, matching the earlier implementation you referenced.
- The right pane no longer owns its own desktop scroll container; page height now follows the routed content again.
- Residual risk: compile verification passed, but I have not done a live browser pass to confirm the rail still visually lands where you want for both short and very tall garage pages.

---

# My Garage Screenshot Overflow Correction (2026-03-16)

## Plan
- [x] Capture the correction indicated by the screenshot: right-side My Garage content should not push the page below the viewport.
- [x] Reapply a viewport-constrained desktop shell for My Garage.
- [x] Keep the left rail full-height within the visible workspace while restoring internal right-pane scrolling.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] The screenshot confirms the problem with the last restore: tall Services content is stretching the full page below the viewport.
- [x] Locked the intended overflow owner for this pass to the desktop My Garage content pane, not the overall page.
- [x] Reapplied the desktop workspace height constraint and internal right-pane scrolling in `frontend/src/features/garage/MyGaragePage.tsx`.
- [x] Kept the left rail full-height within that visible workspace, with garage options at the top and `Account` / `Profile & Settings` anchored at the bottom.
- [x] Used Playwright against the live local app with a seeded garage-owner session and mocked tall Services data to verify the rendered page behavior directly.
- [x] Identified the remaining overflow root cause in Playwright: the My Garage route root was still computed as `flex: 1 1 0%` and rendered at `1187px` tall, so the fixed shell height was not actually taking effect.
- [x] Fixed that conflict by switching the My Garage root to `lg:flex-none` and tightening the desktop shell height to `calc(100vh - 9.25rem)`.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The screenshoted overflow issue is corrected: Playwright measured the Services page at `1301px` on a `1300px` viewport, which no longer exceeds the viewport beyond measurement noise, and the My Garage shell now computes to `1152px` instead of `1187px`.
- My Garage now behaves as a contained desktop workspace again, with scrolling owned by the right content pane instead of the overall page.
- Verification completed with real browser automation on the live local app plus `npm run build`; no further code-only assumption remains on this point.

---

# My Garage Width Cap Rollback (2026-03-16)

## Plan
- [x] Record the rollback of the unintended My Garage width cap.
- [x] Remove the centered max-width wrapper so My Garage fills the available dashboard width again.
- [x] Verify the change with frontend build and a Playwright width check.

## Progress Notes
- [x] Confirmed the current width reduction is caused by `mx-auto max-w-[1400px]` on `frontend/src/features/garage/MyGaragePage.tsx`.
- [x] Locked the rollback scope to width only: preserve the left rail and current overflow behavior, remove the unrequested workspace narrowing.
- [x] Removed the centered max-width wrapper from `frontend/src/features/garage/MyGaragePage.tsx` while leaving the rail width and desktop overflow behavior intact.
- [x] Verified with Playwright on the live Services page: on a `1920px` viewport, the My Garage wrapper now renders at `1845px` wide inside a `1909px` main content area, confirming the prior width cap is gone.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The unintended garage workspace narrowing has been rolled back; My Garage now fills the available dashboard width again.
- The left rail remains in place, but the right content area is no longer constrained by the old `max-w-[1400px]` wrapper.
- Residual risk: none specific to width after the Playwright check; any remaining spacing concerns would now be about the intentional left-rail footprint rather than a hidden outer width cap.

---

# Dashboard Mobile Work Queue Header Alignment (2026-03-16)

## Plan
- [x] Capture the correction that the Work Queue status update should stay on the same row as the section title on mobile.
- [x] Adjust the Work Queue header layout so the title row and refresh/last-updated chip remain inline on small screens.
- [x] Run targeted frontend verification and capture residual risks.

## Progress Notes
- [x] Confirmed the current issue in `frontend/src/features/dashboard/DashboardHome.tsx`: the Work Queue header uses a mobile `flex-col` layout, which drops the refresh/last-updated status chip below the title instead of keeping it inline.
- [x] Reworked the Work Queue header to use a single `justify-between` row on smaller screens, while keeping the title block flexible and the refresh/last-updated control fixed-width.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The Work Queue title and refresh/last-updated status chip now stay on the same header row on mobile instead of splitting into stacked rows.
- The change is intentionally narrow: only the Work Queue header flex behavior was adjusted, so the queue lanes and larger-screen layout remain intact.
- Residual risk: compile verification passed, but I have not done a live mobile browser pass to confirm the row still feels balanced with your exact font scaling and device width.

---

# Team Capacity Mobile UX Narrative Pass (2026-03-16)

## Plan
- [x] Audit the current Team Capacity mobile UX in code and against the supplied screenshot.
- [x] Capture the intended mobile narrative before editing: summary first, mechanic board second, no abstract utilization framing or nested mobile scroll trap.
- [x] Refactor Team Capacity so mobile uses a clearer floor snapshot and simplified mechanic cards.
- [x] Run targeted verification and capture review notes, including the UX-audit limitation if browser automation stays blocked.

## Progress Notes
- [x] Activated the `frontend-design` and `ux-audit` skills for this pass.
- [x] UX audit finding: the current mobile stack tells the same story three ways (`31 assigned`, `Team utilization`, per-mechanic load/status cards), but each block uses different language, which creates narrative conflict instead of clarity.
- [x] UX audit finding: the internal mechanic-list scrollbar adds a second scroll context on mobile, so users have to parse both a summary card and a nested board in a compressed space.
- [x] Locked the target mobile structure for this pass to `Team Capacity header -> Floor Snapshot summary -> Mechanic board list`, with concrete labels like jobs queued / techs ready instead of an abstract utilization percentage.
- [x] Replaced the `Team utilization` percentage slab with a `Floor Snapshot` card, clarified the header total to `jobs assigned`, and added a dedicated `Mechanic Board` subheading so the section reads top-to-bottom instead of as three competing summaries.
- [x] Simplified mechanic cards to one status pill plus `Active` / `Queued` stat tiles, prioritized the list by operational relevance, and removed the nested internal scroll behavior on mobile while preserving contained scrolling from `md` upward.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)
- [x] Attempted live browser UX verification with Playwright on the running local app, but the tool could not launch because Chrome immediately exited with `Opening in existing browser session`.

## Review
- Team Capacity now tells a clearer mobile story: the top card answers “what is happening on the floor right now,” and the mechanic list below answers “who should I tap next.”
- The old utilization percentage is gone because it was abstract and contradictory on mobile, especially in states like `0%` utilization with a large queued count.
- Mobile no longer traps the mechanic list inside its own scrollbar, which removes the nested-scroll friction you called out.
- Residual risk: compile verification passed, but the live mobile UX audit had to stop at code/screenshot analysis because Playwright could not take control of the browser in this environment.

---

# Team Capacity Desktop De-Emphasis Correction (2026-03-16)

## Plan
- [x] Capture the correction that the Team Capacity redesign should have remained mobile-only.
- [x] Identify which current desktop Team Capacity elements are taking too much height away from Work Queue.
- [x] Keep the clearer mobile narrative but compress desktop Team Capacity back to a low-emphasis summary and shorter mechanic cards.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the current desktop regression in `frontend/src/features/dashboard/DashboardHome.tsx`: the large `Floor Snapshot` block and the taller mobile stat-tile mechanic cards both apply at `lg+`, so Team Capacity is consuming vertical space that should go back to Work Queue.
- [x] Locked the corrected scope for this pass to `mobile keeps the new summary/card treatment`, `desktop gets compact snapshot chips plus denser mechanic cards`.
- [x] Moved the `Floor Snapshot` detail card back to mobile-only and converted desktop into compact inline snapshot chips in the Team Capacity header.
- [x] Recompressed desktop mechanic cards into shorter rows with inline active/queued/load text and a thinner load bar, while leaving the taller stat-tile layout in place below `lg`.
- [x] Tightened the desktop mechanic-board height cap so the section gives more vertical space back to Work Queue on larger screens.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- Desktop Team Capacity is de-emphasized again: the snapshot metrics no longer occupy a full card, and mechanic cards no longer use the taller mobile treatment.
- Mobile keeps the clearer summary-first narrative from the previous pass, so the rollback is scoped to desktop density rather than a full reversion.
- Residual risk: compile verification passed, but I have not done a live desktop browser pass against your exact monitor width to confirm the reclaimed height feels right next to Work Queue.

---

# Team Capacity Header Count Deduplication (2026-03-16)

## Plan
- [x] Confirm whether the Team Capacity header count is duplicating the new summary metrics.
- [x] Remove the redundant top-right assigned count from the Team Capacity header.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the duplication in `frontend/src/features/dashboard/DashboardHome.tsx`: the header-level `assigned` count now repeats workload information already expressed by the Team Capacity snapshot pills/cards, especially when queued work is the primary operational signal.
- [x] Removed the top-right Team Capacity header count so the snapshot pills/cards are now the only workload-summary layer in that section.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The duplicated header count is gone, so Team Capacity no longer repeats workload totals in both the header and the summary pills/cards.
- The section header is cleaner and the remaining snapshot pills carry the summary role by themselves.

---

# Team Capacity Header Pill Alignment (2026-03-16)

## Plan
- [x] Confirm why the Team Capacity summary pills are not occupying the old top-right header slot.
- [x] Move the Team Capacity summary pills to the right side of the header on desktop.
- [x] Run targeted frontend verification and capture review notes.

## Progress Notes
- [x] Confirmed the current issue in `frontend/src/features/dashboard/DashboardHome.tsx`: after removing the header count, the summary-pill wrapper still uses `lg:flex-1` with `lg:justify-center`, so the pills remain centered instead of shifting into the top-right header slot.
- [x] Replaced the centered desktop pill wrapper with a right-aligned `lg:ml-auto` / `lg:justify-end` header group so the summary pills now occupy the same top-right slot as the old header count.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)

## Review
- The Team Capacity summary pills now sit on the right side of the desktop header, which matches the slot previously occupied by the removed count.
- The change is layout-only: the same summary pills remain, but they now anchor to the correct part of the header.

---

# Tenant Logo Import Flow (2026-03-16)

## Plan
- [x] Audit the current enrollment flow, tenant profile API, and any existing remote-image storage patterns.
- [x] Implement backend website-logo discovery/import during garage enrollment, with graceful fallback when no logo can be found.
- [x] Expose tenant logo management in the post-enrollment garage profile flow, including a manual import action from the saved website.
- [x] Add focused backend and frontend tests for the new behavior.
- [x] Run targeted verification and capture residual risks.

## Progress Notes
- [x] Confirmed enrollment already collects optional `website`, the tenant model already stores `website` and `logo_url`, and the garage profile API already persists `logo_url`.
- [x] Confirmed the settings UI currently exposes `website` but not `logo_url`, so post-enrollment editing is incomplete.
- [x] Confirmed Cloudinary is available in the backend and is the cleanest existing place to copy remote logos instead of hotlinking tenant sites.
- [x] Added `backend/app/services/website_logo_service.py` to discover likely tenant logos from explicit logo images, JSON-LD logo fields, touch icons, manifest icons, and favicon fallback, with SSRF guards against private/local hosts.
- [x] Wired automatic best-effort logo import into `/api/v1/auth/enroll-garage`; enrollment now continues even if logo discovery fails.
- [x] Added `POST /api/v1/admin/garage-profile/import-logo` so garage owners/admins can re-import a logo from the saved website later.
- [x] Extended `frontend/src/features/dashboard/UnifiedSettingsPage.tsx` with tenant logo preview, manual `logo_url` editing, clear action, and website-driven import action.
- [x] Added focused tests:
  `backend/tests/test_website_logo_service.py`
  `backend/tests/test_tenant_logo_import.py`
  `frontend/src/__tests__/UnifiedSettingsPage.test.tsx`
- [x] Passed targeted verification:
  `venv/bin/python -m pytest tests/test_website_logo_service.py tests/test_tenant_logo_import.py -q`
  `npm run test -- --run src/__tests__/UnifiedSettingsPage.test.tsx`
  `npm run build` (from `frontend/`)

## Review
- Tenant logos now import automatically during enrollment when a public website is provided, and garage owners/admins can re-import or override the logo later from Garage Profile settings.
- The discovery logic prefers explicit logo signals first and falls back through icons safely, while rejecting private/local network fetches to avoid turning website import into an SSRF hole.
- Residual risk: when Cloudinary is not configured, imported logos fall back to the discovered source URL instead of a copied hosted asset, so third-party hotlinking behavior still depends on the tenant site.

---

# Tenant Logo Import Heuristic Fix (2026-03-16)

## Plan
- [x] Reproduce why the current importer picks a secondary brand/logo asset instead of the lazy-loaded site header logo on `truckpitstop.com`.
- [x] Update website logo discovery to read lazy-load image attributes and prefer explicit site-logo containers over generic downstream brand images.
- [x] Add regression tests for lazy-loaded logo selection.
- [x] Run targeted backend verification and capture the remaining best-effort limitation.

## Progress Notes
- [x] Confirmed `truckpitstop.com` renders the desired header logo via `data-src=\"...Trasp-white-1080x400-1.png\"`, while the current importer only scores `<img src=...>` candidates.
- [x] Confirmed the current ranking gives generic `img.logo` hits the top priority, so a later page image like `Freightliner-Logo.png` can win when the actual header logo is lazy-loaded.
- [x] Updated `backend/app/services/website_logo_service.py` to read lazy-load image attributes (`data-src`, `data-lazy-src`, `data-original`, related WordPress file attrs, and srcset variants) instead of relying only on `src`.
- [x] Split image scoring so explicit site-logo class/id signals outrank generic filename matches, with a small bonus for wide wordmark-style aspect ratios.
- [x] Added a regression test proving a lazy-loaded header logo beats `Freightliner-Logo.png`.
- [x] Verified against the live tenant site markup with:
  `venv/bin/python - <<'PY' ... parse_website_logo_candidates('https://truckpitstop.com') ... PY`
  which now ranks `https://truckpitstop.com/wp-content/uploads/2025/01/Trasp-white-1080x400-1.png` first.
- [x] Passed targeted backend verification:
  `venv/bin/python -m pytest tests/test_website_logo_service.py tests/test_tenant_logo_import.py -q`

## Review
- `truckpitstop.com` now imports the intended lazy-loaded header logo instead of a downstream brand logo image.
- This remains a best-effort import heuristic, not a guarantee of the exact browser-rendered logo for every site. Sites that render logos through CSS backgrounds, JS-only hydration, shadow DOM, canvas, or viewport-conditional swaps can still differ from what static HTML inspection finds.

---

# Dashboard Attention Banner Work Queue Reclaim (2026-03-16)

## Plan
- [x] Inspect the dashboard manager layout and determine why dismissing `Attention Required` does not let `Work Queue` reclaim the freed viewport space.
- [x] Move the alert-dismiss visibility state into `DashboardHome` so dismissing the banner invalidates the queue height measurement immediately.
- [x] Verify the queue expands after dismissal with `npm run build` and a live Playwright check on the dashboard page.

## Progress Notes
- [x] Confirmed `DashboardHome` already measures the queue against the viewport, but the `Attention Required` dismissal lives inside `AlertsBanner`, so closing it never re-runs the parent measurement effect.
- [x] Lifted the attention-banner dismissal state into `DashboardHome` and wired `AlertsBanner` to an `onDismiss` callback so the queue height recalculates when the banner is removed.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)
  Playwright on mocked `http://localhost:5173/dashboard` measured `Work Queue` at `736px` tall with the banner present, then `852px` tall after dismissing `Attention Required`, while the queue bottom alignment stayed pinned to the same viewport floor.

## Review
- `Attention Required` now behaves like a temporary layout participant instead of a dead-end height cap: when it is visible it consumes vertical space, and when it is dismissed the queue expands immediately into that reclaimed area.
- The fix is state ownership, not new height math. `DashboardHome` now owns the banner visibility state, so the existing viewport-fit measurement reruns at the correct time.

---

# Inventory Toolbar And Overflow Cleanup (2026-03-16)

## Plan
- [x] Inspect the inventory page layout and identify which elements own overflow on desktop.
- [x] Move the desktop `Search in` filters into the same top toolbar as the search input so the header consumes less vertical space.
- [x] Constrain the desktop inventory workspace to the available page height so the list/cards area owns the only intended scroll region.
- [x] Verify with `npm run build` and local browser inspection that the extra page scrollbar is gone in desktop inventory.

## Progress Notes
- [x] Confirmed `InventoryPage` rendered a separate desktop `Search in` row above a second desktop table/card shell, while list view also used its own `overflow-y-auto max-h-[calc(100vh-260px)]`.
- [x] Rebuilt the desktop toolbar so the search input, `Search in` filters, and `Add part` action live in one row when space allows.
- [x] Switched the desktop inventory shell to a `flex-1 min-h-0` layout so cards/list content owns the vertical scroll instead of stacking a nested max-height container on top of the garage pane scroll.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)
  Playwright on mocked `http://localhost:5173/dashboard/garage/inventory` confirmed the desktop toolbar renders on a single 42px row and the garage content pane no longer overflows (`clientHeight=1023`, `scrollHeight=1023`) while the inventory list remains the sole vertical scroller (`clientHeight=908`, `scrollHeight=1228`).

## Review
- Desktop inventory now uses one top toolbar for search context and action controls, which frees vertical space before the list shell.
- The double-scroll issue is resolved by making the inventory workspace height-aware and giving the list/cards region the only intentional desktop overflow.

---

# Inventory Toolbar Height Refinement (2026-03-16)

## Plan
- [x] Remove the `Search in:` label from the desktop inventory toolbar.
- [x] Normalize the quick-filter control height to match the search field and `Add part` button.
- [x] Verify the refined toolbar layout in build output and browser rendering.

## Progress Notes
- [x] Removed the standalone `Search in:` label so the segmented quick filters read as a direct companion control to the search input.
- [x] Set the desktop filter group and `Add part` button to the same 42px control rail as the search field.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)
  Playwright on mocked `http://localhost:5173/dashboard/garage/inventory` confirmed the label is gone and the visible desktop search field, filter rail, and `Add part` button all render at `42px` tall.

## Review
- The desktop inventory toolbar is now visually cleaner: the segmented quick filters sit directly beside the search field without a redundant label.
- All three adjacent controls now share the same 42px height, so the toolbar reads as one aligned control rail instead of mixed-sized elements.

---

# Tenant Branding Cycle (2026-03-16)

## Plan
- [x] Audit every tenant-facing logo render point and confirm which payloads already expose tenant branding.
- [x] Add a shared tenant-logo rendering path with Diesel Bridge fallback and permanent super-admin override.
- [x] Expose tenant logo data to quote/invoice/customer-facing flows that currently lack it.
- [x] Update garage settings cache invalidation so tenant branding changes propagate through active sessions.
- [x] Add focused tests for tenant-logo fallback behavior.
- [x] Run targeted verification and capture residual risks.

## Progress Notes
- [x] Confirmed the current hardcoded platform-logo render points are `DashboardLayout`, `CustomerPortalPage`, and `QuoteApprovalPage`.
- [x] Confirmed `InvoiceAccessPage` does not render the Diesel Bridge mark today, but it is a tenant-branded customer flow and should use tenant branding in its header.
- [x] Confirmed tenant logo storage already exists on `tenant.logo_url`, while customer-facing quote/invoice token responses do not yet expose that field.
- [x] Confirmed Super Admin can remain on the existing Diesel Bridge path by short-circuiting tenant-branding lookup for `super_admin`.
- [x] Added `/api/v1/auth/tenant-branding` plus `tenant_logo_url` on `/api/v1/auth/me`, so authenticated tenant users can resolve branding from one shared source.
- [x] Added `TenantBrandLogo` + `useTenantBranding` on the frontend and wired them into the garage dashboard shell and customer portal nav.
- [x] Extended quote token and invoice-access responses with `shop_name` and `shop_logo_url`, then rendered tenant branding on quote approval and invoice pages.
- [x] Extended invoice access links with `shop_logo_url` query params so the invoice error state can still show tenant branding when the token cannot resolve.
- [x] Updated Garage Profile saves/imports to refresh the shared tenant-branding cache and persisted auth user branding fields immediately.
- [x] Added focused tests:
  `backend/tests/test_auth_endpoints.py`
  `backend/tests/test_tenant_branding_surfaces.py`
  `frontend/src/__tests__/TenantBrandLogo.test.tsx`
- [x] Passed targeted verification:
  `cd backend && venv/bin/python -m pytest tests/test_auth_endpoints.py tests/test_tenant_branding_surfaces.py tests/test_tenant_logo_import.py -q`
  `cd frontend && npm run test -- --run src/__tests__/TenantBrandLogo.test.tsx src/__tests__/UnifiedSettingsPage.test.tsx`
  `cd frontend && npm run build`

## Review
- Tenant branding is now a full-cycle fallback model: garage staff and customer portal users see the tenant logo when one exists, quote/invoice customer flows receive the tenant logo from their token payloads, and Diesel Bridge remains the fallback when no tenant logo is available.
- Super Admin stays permanently on the Diesel Bridge brand because tenant-branding fetches are disabled for that role and the dashboard shell still renders the platform mark explicitly in that path.
- Residual risk: imported website logos can still be visually mismatched for some surfaces if the tenant site only exposes a light-on-transparent header asset. The product fallback is still functional, but those tenants may need to replace the imported logo with a more universal asset in Garage Profile.

---

# Playwright Localhost Diagnosis (2026-03-16)

## Plan
- [x] Inspect the repo's Playwright configuration and determine whether a project-specific MCP server is required.
- [x] Check the frontend/backend local host bindings and ports that Playwright depends on.
- [x] Document the likely cause of the flaky localhost access and the stable setup path.

## Progress Notes
- [x] Confirmed the repo already has Playwright test-runner config at `e2e/playwright.config.ts`; it does not depend on a project-defined MCP server.
- [x] Confirmed Playwright test config expects the frontend at `http://localhost:5173` and starts the backend on port `8000` plus the frontend Vite dev server automatically via `webServer`.
- [x] Confirmed `frontend/vite.config.ts` sets port `5173` but does not pin `server.host`, while its proxy targets `http://127.0.0.1:8000`.
- [x] Observed the active local frontend listener on `[::1]:5173` and backend listeners on `127.0.0.1:8000`, which means the stack is currently split between IPv6 localhost and IPv4 loopback.
- [x] Captured the operational conclusion: the flaky browser-tool behavior is more consistent with startup timing and localhost resolution mismatch than with missing Playwright/MCP infrastructure.

## Review
- This project does not need an extra MCP server for normal Playwright tests. Running `cd e2e && npx playwright test` should be sufficient once Playwright browsers are installed.
- If an AI browser tool is being used instead of the Playwright test runner, the tool still needs the app servers to be reachable from the same environment; `localhost` can fail intermittently when frontend and backend bind to different loopback families.
- The stable fix path is to bind both dev servers explicitly to the same host, preferably `127.0.0.1`, and use that exact host in Vite, the backend launch command, and Playwright `baseURL`.

---

# Playwright Host Pinning (2026-03-16)

## Plan
- [x] Update the Playwright config to use `127.0.0.1` consistently for `baseURL` and the managed backend server command.
- [x] Update the Vite dev server config to bind explicitly to `127.0.0.1`.
- [x] Run focused verification and capture any residual risk.

## Progress Notes
- [x] Confirmed the required pinning points are `e2e/playwright.config.ts` and `frontend/vite.config.ts`.
- [x] Changed Playwright `baseURL` to `http://127.0.0.1:5173`.
- [x] Updated the Playwright-managed backend launch to `venv/bin/python -m uvicorn ... --host 127.0.0.1 --port 8000` so it uses the repo's actual backend interpreter instead of relying on a missing bare `python` binary.
- [x] Updated the Playwright-managed frontend launch to pass `--host 127.0.0.1` explicitly.
- [x] Added `server.host = '127.0.0.1'` to `frontend/vite.config.ts` so manual `npm run dev` sessions bind to IPv4 loopback consistently.
- [x] During verification, fixed two stale Playwright expectations that no longer matched the current UI:
  `e2e/tests/staff-login.spec.ts`
  `e2e/tests/invoice-access.spec.ts`
- [x] Passed focused verification:
  `cd frontend && npm run build`
  `cd e2e && npx playwright test --list`
  `cd e2e && npx playwright test tests/staff-login.spec.ts --project=chromium --grep "shows login form"`
  `cd e2e && npx playwright test`

## Review
- Playwright is now pinned to a single loopback address family end-to-end instead of mixing `localhost`, IPv6, and IPv4 bindings.
- The e2e runner is more reliable in this repo because it now uses the checked-in backend virtualenv rather than assuming `python` exists on the shell PATH.
- Residual risk: local commands or docs elsewhere in the repo that still reference plain `localhost` may continue to work, but they will not benefit from this stricter IPv4 pinning unless updated separately.

---

# Scoped Commit Shipping (2026-03-16)

## Plan
- [x] Inspect the mixed working tree and generate draft scopes with the `scoped-commit-assistant` skill.
- [x] Refine the draft into atomic commit boundaries based on the actual diffs.
- [x] Re-run targeted validation so each commit message can cite real commands.
- [x] Stage and commit each scope with structured commit messages.
- [x] Record the shipped commit order and validation summary.

## Progress Notes
- [x] Ran `python3 /Users/sergio/.agents/skills/scoped-commit-assistant/scripts/suggest_scoped_commits.py --mode all` and treated the output as a draft, not the final boundary.
- [x] Refined the plan into four commits: inventory desktop layout, garage-logo copy cleanup, Playwright/Vite host pinning, and task documentation.
- [x] Re-ran targeted verification before staging:
  `cd frontend && npm run build`
  `cd e2e && npx playwright test --list`
  `cd e2e && npx playwright test`
- [x] Shipped the scoped commits in this order:
  `fix(inventory): unify desktop toolbar and scroll ownership`
  `fix(settings): remove misleading garage logo status copy`
  `fix(e2e): pin local test servers to 127.0.0.1`
  `docs(tasks): capture scoped shipping notes`

## Review
- The mixed working tree is now split into atomic commits instead of one broad checkpoint, so inventory UI work, garage copy cleanup, Playwright host pinning, and task docs each have their own history entry.
- Validation cited in the commit bodies comes from commands re-run during this shipping pass, not placeholder text from the planner output.

---

# Repair Operation Memory Zero-Hour Correction (2026-03-19)

## Plan
- [x] Audit the repair-operation search/apply/update flow and confirm why new custom operations are being reused with `0.00` hours.
- [x] Update the labor-memory rules so only positive-hour repair operations are learned and reused.
- [x] Ignore previously stored zero-hour memory rows during search/recalc so existing bad data stops surfacing.
- [x] Add targeted backend tests for the zero-hour custom-operation path.
- [x] Run focused verification and capture review notes.

## Progress Notes
- [x] Confirmed the current internal flow: library defaults seed known operations, tenant-specific `labor_operation_memory` stores learned hours by normalized vehicle signature, and unknown searches fall back to a custom operation with `0.00` hours.
- [x] Confirmed the bug: `add_repair_operation_line()` immediately upserts internal memory even when a brand-new custom operation still has `0.00` hours, so the system "learns" and reuses an empty estimate before staff enter real hours.
- [x] Updated `PriceBuildService` so labor memory only reads and writes positive-hour entries; zero-hour rows are ignored during search, apply, and recalc.
- [x] Added regression tests covering both the new custom-operation path and legacy zero-hour memory rows.
- [x] Passed focused verification:
  `cd backend && venv/bin/python -m pytest tests/test_price_build_service.py -q`

## Review
- Custom repair operations now behave as "unlearned" until someone enters real hours on the RO line; only then do they become reusable memory for matching vehicles.
- Existing zero-hour memory rows no longer win search/apply/recalc decisions, so they stop poisoning the internal labor library without requiring an immediate data cleanup.
- Residual risk: the UX still applies unknown custom operations at `0.00` hours first and expects staff to edit the line afterward; the next refinement should be a custom-operation hours prompt in the repair-order UI so teaching happens at apply time instead of as a second step.

---

# Frontend Mobile UX Shipping (2026-03-20)

## Plan
- [x] Inspect the staged and unstaged frontend diffs and define clean commit boundaries instead of pushing one mixed change set.
- [x] Confirm how the shared select-component changes are consumed so they land with the right feature scope.
- [x] Record the final commit scopes and push plan.
- [x] Run targeted frontend verification for the combined shipping state.
- [x] Commit each scope with structured messages and push to `origin/main`.

## Progress Notes
- [x] Confirmed the current worktree is almost fully staged, with one extra unstaged follow-up in `frontend/src/features/dashboard/DashboardHome.tsx`.
- [x] The scoped-commit planner suggested one broad frontend refactor, but diff review shows three better scopes:
  `messages` for the inbox/compose redesign plus shared customer select support,
  `dashboard` for shell overflow management and mobile work-queue behavior,
  `repair-orders` for the filter rail and price-builder input refinements.
- [x] Confirmed the new `CustomerSelect` dark-mode and phone-capture props are currently consumed by `MessagesInboxPage`, while the repair-orders diff is limited to layout/scroll and price input behavior.
- [x] Re-ran targeted verification for the combined shipping state:
  `cd frontend && npm run build`
  `git diff --check`
- [x] Shipped the scoped commits in this order:
  `fix(dashboard): tighten shell overflow and mobile cockpit`
  `feat(messages): redesign inbox and outbound compose flow`
  `fix(repair-orders): streamline filters and rate editing`
  `docs(tasks): capture mobile frontend shipping notes`

## Review
- The frontend shipping set is now split by user-facing intent instead of one oversized checkpoint, which keeps dashboard shell work, inbox UX, and repair-order refinements independently reviewable.
- Validation for the shipped state is a fresh frontend build plus a clean diff check, which is appropriate for this UI-only batch.

---

# Mobile KPI Hide (2026-03-20)

## Plan
- [x] Identify the dashboard KPI section and its current responsive wrapper.
- [x] Hide the KPI section on mobile screens at the outer container level.
- [x] Verify the responsive behavior with build output and a browser check.

## Progress Notes
- [x] Confirmed the KPI section is the manager-only `Revenue KPIs` card at the bottom of `DashboardHome`.
- [x] Updated the KPI wrapper to stay hidden below `lg`, which removes the entire section from mobile instead of only hiding inner content.
- [x] Passed targeted verification:
  `npm run build` (from `frontend/`)
  Playwright on mocked `http://localhost:5173/dashboard` confirmed `Revenue KPIs` is not visible at `390px` width and becomes visible again at `1280px`.

## Review
- The KPI section is now absent from mobile screens because the entire outer card is hidden below `lg`.
- Desktop behavior is preserved: the same `Revenue KPIs` card still renders once the viewport reaches desktop width.

---

# Mobile Work Queue Priority Layout (2026-03-20)

## Plan
- [x] Inspect the current mobile dashboard shell and identify why Work Queue does not own the remaining viewport space above Team Capacity.
- [x] Refactor the mobile dashboard layout so transient top sections stay above a remaining-space frame, with Work Queue as `flex-1` and Team Capacity anchored below it.
- [x] Verify on mobile that dismissing `Attention Required` expands Work Queue while Team Capacity stays pinned to the same bottom slot.

## Progress Notes
- [x] Confirmed the mobile dashboard still flowed as content: `DashboardHome` was not a viewport-bounded flex item on mobile, `Work Queue` only had `flex-1` at `lg`, and the active mobile lane used fixed pixel heights instead of filling the remaining queue area.
- [x] Updated `DashboardHome` to be a full flex child of the dashboard viewport on mobile, wrapped `Work Queue` + `Team Capacity` in a `flex-1 min-h-0` frame, and switched mobile lane sizing from fixed heights to active-lane flex expansion.
- [x] Verified on a mocked mobile dashboard in Playwright (`390x844`) that dismissing `Attention Required` increased `Work Queue` height from `377.25px` to `516.25px` while `Team Capacity` stayed pinned at the same bottom position (`bottom: 775px` before and after).
- [x] Confirmed the mobile dashboard shell itself did not start page-scrolling after the change: the route scroller stayed `clientHeight=767` and `scrollHeight=767` before and after dismissing the banner.

## Review
- `DashboardHome` now treats mobile the same way as desktop in terms of section priority: `Work Queue` owns the remaining viewport space, and `Team Capacity` remains the bottom sibling inside that shared frame.
- Dismissing `Attention Required` no longer leaves dead space on mobile; the queue immediately reclaims the banner footprint while keeping `Team Capacity` anchored below it.
- Verification completed with `npm run build` in `frontend/` plus Playwright mobile layout checks against mocked dashboard data.

---

# Dashboard Profile Trigger Refresh (2026-03-20)

## Plan
- [x] Inspect the shared dashboard header to locate the outdated profile icon treatment and compare it against the current application UI language.
- [x] Replace the old animated circular profile trigger with a cleaner profile control that matches the dashboard and Settings styling.
- [x] Verify the updated profile trigger in-browser and with a frontend build.

## Progress Notes
- [x] Confirmed the stale treatment lives in `frontend/src/components/layout/DashboardLayout.tsx`: the desktop settings trigger still renders a custom animated circular SVG ring that no longer matches the card-based industrial styling used elsewhere in the app.
- [x] Replaced the ringed icon with a compact rounded profile tile that uses the signed-in user’s monogram, a subtle accent wash, and a small live-status dot derived from the same visual language as the Settings avatar.
- [x] Verified on the live desktop dashboard in Playwright that the header now exposes `Open profile settings for Alexandru Popescu` with `AP` rendered inside a rounded tile, and that the trigger contains no legacy SVG ring markup (`hasSvg: false`, `pathCount: 0`).

## Review
- The outdated animated circle is gone from the shared dashboard header; the settings trigger now reads like a native part of the app instead of a standalone ornament.
- The new profile control preserves the existing nav footprint while aligning with the card-based industrial styling used in Settings and the rest of the dashboard.
- Verification completed with `npm run build` in `frontend/` plus a Playwright desktop inspection against the live dashboard.

---

# Landing Page Approved Partners (2026-04-11)

## Plan
- [x] Confirm the minimal public partner metadata the app already stores and identify the extra landing-page fields each approved business needs to control from the garage dashboard.
- [x] Add backend storage and response models for partner-display metadata plus a public endpoint that returns approved active businesses for the landing page.
- [x] Extend the garage profile settings so each garage owner/admin can edit the public partner details that appear on the landing page.
- [x] Implement a landing-page partner section that shows all approved businesses in a moving rail plus a static detail grid without hardcoded placeholders.
- [x] Run targeted backend/frontend verification and capture residual risks in this file.

## Progress Notes
- [x] Confirmed the current garage profile already persists `website` and `logo_url`, so the partner section can reuse existing backlink/logo fields instead of inventing a second branding source.
- [x] Added tenant-level partner metadata fields: `partner_summary` and `partner_services`, plus Alembic migration `044_add_landing_partner_fields.py`.
- [x] Added public endpoint `GET /api/v1/auth/landing-partners` that returns approved active businesses only.
- [x] Extended `Garage Profile` settings so garage owners/admins can edit the landing-page summary and service-focus copy for their own business.
- [x] Added a landing-page partner band with an auto-scrolling rail plus a static partner grid driven entirely by approved businesses from the backend.
- [x] Passed targeted verification:
  `./.venv/bin/python -m pytest backend/tests/test_landing_partners_endpoint.py backend/tests/test_tenant_logo_import.py -q`
  `npm run test -- --run src/__tests__/LandingPage.test.tsx src/__tests__/UnifiedSettingsPage.test.tsx` (from `frontend/`)
  `npm run build` (from `frontend/`)
  `curl -I http://127.0.0.1:4173/`
- [x] Added stable backend test defaults for Twilio env vars in `backend/tests/conftest.py` so admin endpoint tests do not require real credentials during collection.

## Review
- Approved active businesses now feed a concrete landing-page partner section without hardcoded placeholders.
- Garage owners/admins can control the public partner copy from `Garage Profile`, while approval status remains the gate for inclusion on the landing page.
- Residual risk: approved businesses without curated `partner_summary` or `partner_services` fall back to generic copy until those new profile fields are filled in.

---

# Price Builder Sidekick Panel Redesign (2026-07-05)

## Plan
- [x] Inspect `docs/design_handoff_price_builder` and the current `PriceBuilderPanel` implementation to separate already-started work from missing redesign work.
- [x] Rework the panel into the designed sidekick structure: gradient header, workflow strip, collapsed line-item list, unified add bar, contextual rows, sticky totals footer, and compact danger zone.
- [x] Preserve existing repair-order API wiring for operation search/apply, service labor, line edits, part quantity/price edits, pricing mode, discounts, recalculate, and invalidation.
- [x] Add anchored unit-price and discounts/pricing popovers that match the handoff interactions without floating/clipping issues.
- [x] Verify TypeScript/build output and update this review with what was proven and any residual gaps.

## Progress Notes
- [x] Confirmed the handoff calls for a full high-fidelity redesign, while the current code still mostly uses the old three-box drawer layout.
- [x] Found existing partial work in `PriceBuilderPanel.tsx`: live operation search, binary part price dropdown, bulk parts pricing, and manager discounts.
- [x] Replaced the old three-box drawer presentation with one segmented add bar, one work/labor list, collapsed line summaries, expanded labor/parts editing, anchored unit-price popovers, contextual rows, and a sticky totals footer.
- [x] Passed targeted lint: `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0`.
- [x] Full `npm run build` remains blocked by existing unrelated `FleetApp.tsx` TypeScript errors; filtered output showed no `PriceBuilderPanel.tsx` or `RepairOrdersPage.tsx` TypeScript errors.

## Review
- The redesigned sidekick now follows the handoff structure while preserving the existing repair-order API paths and query invalidation behavior.
- Residual gap: standalone Part and Labor segments display constrained helper states because this panel currently has operation apply and service-labor APIs, while standalone part/labor creation still lives elsewhere in the repair-order detail UI.
- Full build verification is blocked by unrelated fleet profile/password compile errors in `frontend/src/features/fleet/FleetApp.tsx`.

---

# Price Builder Shell Deduplication (2026-07-05)

## Plan
- [x] Confirm which duplicated surfaces are coming from the parent repair-order detail panel versus the redesigned price-builder component.
- [x] Let the redesigned price-builder own its shell by suppressing the parent panel header/navigation/footer in price-builder mode.
- [x] Suppress old workflow, customer/vehicle, recommended-services, legacy totals, and parent danger-zone sections when the redesigned builder is active.
- [x] Verify the touched files with targeted lint/build output and record remaining blockers.

## Progress Notes
- [x] Screenshot and code inspection confirm duplicate header, pagination, workflow, context rows, totals/danger surfaces are parent-rendered around the new `PriceBuilderPanel`.
- [x] Added `hideHeader` to `SlidePanel`, passed real close/prev/next handlers into `PriceBuilderPanel`, and gated parent-only sections behind `!priceBuilderOwnsShell`.
- [x] Passed targeted lint: `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx src/features/repair-orders/RepairOrdersPage.tsx src/components/SlidePanel.tsx --max-warnings 0`.
- [x] Full `npm run build` remains blocked by existing unrelated `FleetApp.tsx` TypeScript errors; filtered output showed no `PriceBuilderPanel.tsx`, `RepairOrdersPage.tsx`, or `SlidePanel.tsx` TypeScript errors.

## Review
- The redesigned price builder now owns the visible shell in price-builder statuses, preventing duplicate repair-order header, pagination, workflow, customer/recommended rows, legacy totals, and danger zone.
- Non-price-builder statuses keep the existing `SlidePanel` header/footer and legacy detail sections.
- Full build verification remains blocked by unrelated fleet profile/password compile errors in `frontend/src/features/fleet/FleetApp.tsx`.

---

# Price Builder Sidekick Functionality Restore (2026-07-05)

## Plan
- [x] Identify which suppressed parent controls still need to exist inside the redesigned sidekick.
- [x] Restore real danger-zone expand/cancel/delete behavior inside the sidekick footer.
- [x] Restore expandable customer/vehicle details and recommended-service add/resolve/delete behavior inside the sidekick.
- [x] Make the sidekick occupy the full drawer height so the work list owns the middle and totals/danger stay at the bottom.
- [x] Verify touched files and record remaining blockers.

## Progress Notes
- [x] Confirmed the static sidekick rows replaced working parent sections for danger zone, customer details, and recommended services.
- [x] Passed the existing parent danger-zone mutation handlers and delete-confirm flow into `PriceBuilderPanel`.
- [x] Passed recommended-service state and add/resolve/delete mutations into `PriceBuilderPanel`.
- [x] Converted the sidekick to a full-height flex layout with the center content scrolling and the totals/danger footer anchored at the bottom.
- [x] Passed targeted lint: `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx src/features/repair-orders/RepairOrdersPage.tsx src/components/SlidePanel.tsx --max-warnings 0`.
- [x] Full `npm run build` remains blocked by existing unrelated `FleetApp.tsx` TypeScript errors; filtered output showed no `PriceBuilderPanel.tsx`, `RepairOrdersPage.tsx`, or `SlidePanel.tsx` TypeScript errors.

## Review
- Danger zone, customer/vehicle details, and recommended services are functional inside the redesigned sidekick instead of being static placeholders.
- The sidekick now uses the full panel height: header/workflow at top, work and expandable context in the middle, totals and danger zone at the bottom.
- Full build verification remains blocked by unrelated fleet profile/password compile errors in `frontend/src/features/fleet/FleetApp.tsx`.

---

# Price Builder Labor Book Time Add Tab (2026-07-05)

## Plan
- [x] Verify the learned labor catalog path and confirm whether it differs from one-off manual labor.
- [x] Add a dedicated Labor Book Time tab to the sidekick add bar that uses the internal labor-memory search/apply flow.
- [x] Remove the manual Labor add-bar tab so labor entry flows through Labor Book Time.
- [x] Verify frontend lint/build and document the behavior distinction.

## Progress Notes
- [x] Confirmed learned labor is implemented through `price-build/repair-ops/search`, `price-build/repair-ops/apply`, and `price-build/lines/{line_id}` hour edits, which upsert `LaborOperationMemory`.
- [x] Added `Labor Book Time` as a fifth add-bar tab. It uses the learned operation-memory search/apply path and explains that entering hours teaches future matches.
- [x] Removed the separate `Labor` tab and defaulted new Labor Book Time entries to `1` book hour, editable before adding.
- [x] Passed verification: `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` and `npm run build`.

## Review
- The add bar now uses Labor Book Time as the single labor-entry path, so repeatable shop labor and simple one-hour labor are both reusable.
- Labor Book Time is the path for examples like DPF filter replacement where hours should be reused next time; new entries default to one hour and can be adjusted before adding.

---

# My Garage Labor Book Time Library (2026-07-05)

## Plan
- [x] Confirm where learned Labor Book Time records are stored and how My Garage routes are structured.
- [x] Add tenant-scoped backend endpoints to list, update, and delete Labor Book Time library entries.
- [x] Add a dedicated My Garage tab/page for managing Labor Book Time entries without mixing them into Services.
- [x] Verify backend tests and frontend build/lint, then document residual risk.

## Progress Notes
- [x] Confirmed learned Labor Book Time is stored in `labor_operation_memory`, separate from service catalog rows.
- [x] Confirmed `MyGaragePage` owns the garage navigation and routed sections, making a sibling tab the right placement.
- [x] Added `GET/PATCH/DELETE /api/v1/labor-book-time` endpoints scoped to the current garage owner/admin tenant.
- [x] Added `Labor Book Time` as a My Garage navigation tab after Services, with search, inline edit, and delete controls.
- [x] Passed backend verification:
  `./.venv/bin/python -m pytest backend/tests/test_labor_book_time_endpoint.py -q`
- [x] Passed combined learned-memory regression verification:
  `./.venv/bin/python -m pytest backend/tests/test_labor_book_time_endpoint.py backend/tests/test_price_build_service.py -q`
- [x] Passed frontend lint:
  `npx eslint src/features/garage/LaborBookTimePage.tsx src/features/garage/MyGaragePage.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)
- [x] Passed API router import sanity check:
  `../.venv/bin/python -c "from app.api.v1.router import api_router; print(any(getattr(r, 'path', '') == '/labor-book-time' for r in api_router.routes))"` (from `backend/`)

## Review
- Labor Book Time now has its own My Garage management surface and remains separate from customer-facing Services.
- Garage owner/admin users can search learned entries, edit the reusable name/description/book hours, and delete incorrect entries.
- Residual risk: verification covered tests, lint, build, and route registration; a live browser pass is still useful to confirm exact spacing against real tenant data.

---

# Structured Labor Book Time Creation Form (2026-07-06)

## Plan
- [x] Confirm current Labor Book Time storage fields and existing VIN decode API path.
- [x] Add structured truck/application scope fields to labor-memory storage and expose them through the Labor Book Time API.
- [x] Add a create endpoint that saves operation, book hours, and truck scope without requiring a customer vehicle record.
- [x] Add a My Garage creation form matching the adopted redesigned garage UI, with manual fields and optional VIN decode.
- [x] Verify backend tests, price-builder memory regressions, frontend lint, and production build.

## Progress Notes
- [x] Confirmed existing entries store reusable matching data in `labor_operation_memory` but lack explicit year/make/model/engine fields for admin-created library records.
- [x] Confirmed the app already exposes VIN decode through the customer vehicle API and persists NHTSA snapshots for real vehicles.
- [x] Added structured Labor Book Time fields for vehicle year/make/model/type/body, engine/application data, GVWR, and optional VIN sample.
- [x] Added migration `063_add_structured_labor_book_time_scope.py`.
- [x] Added `POST /api/v1/labor-book-time` for manual book-time creation with required year/make/model scope and duplicate protection.
- [x] Updated price-builder matching to also consider a broad year/make/model application signature so manually-created records can appear for matching repair-order trucks.
- [x] Added the My Garage creation form with service/book-hour fields, truck application fields, and optional VIN decode to fill NHTSA data.
- [x] Passed backend verification:
  `./.venv/bin/python -m pytest backend/tests/test_labor_book_time_endpoint.py backend/tests/test_price_build_service.py -q`
- [x] Passed focused frontend lint:
  `npx eslint src/features/garage/LaborBookTimePage.tsx src/features/garage/MyGaragePage.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)
- [x] Passed backend import sanity:
  `../.venv/bin/python -c "from app.api.v1.router import api_router; from app.db.models.labor_operation_memory import LaborOperationMemory; print(any(getattr(r, 'path', '') == '/labor-book-time' for r in api_router.routes), hasattr(LaborOperationMemory, 'vehicle_year'))"` (from `backend/`)

## Review
- Admins can now create a Labor Book Time record without a customer truck by entering the job, book hours, and truck application scope.
- Optional VIN decode fills known NHTSA fields, but the form still supports manual motor-information-system or historical-data entry.
- Price Builder can find manually-created records by the repair order truck's year/make/model application signature while keeping engine details visible in the library.
- Residual risk: live browser verification with real VIN decode is still useful because the automated build verifies code health but not the visual spacing or external NHTSA response quality.

---

# Price Builder Labor Book Time Search Focus Fix (2026-07-06)

## Plan
- [x] Confirm why typing in the Labor Book Time search moves focus into the Book hrs field.
- [x] Remove the focus-stealing behavior while keeping book-hour entry available for the add-new row.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Found `autoFocus` on the add-new candidate row's Book hrs input in `PriceBuilderPanel.tsx`; search result updates can remount that row and steal focus from the search input.
- [x] Removed `autoFocus` from that Book hrs input so the search box keeps focus while typing.
- [x] Confirmed remaining `autoFocus` usages in the component are limited to explicit edit modes, not the search candidate row.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Labor Book Time search no longer has a focus-stealing auto-focus path into the Book hrs field.
- Book hrs is still available on the add-new row by click/tab when the user is ready to save the new labor book time.

---

# Price Builder Inline Labor Book Time Form (2026-07-06)

## Plan
- [x] Pass structured repair-order truck scope into `PriceBuilderPanel`.
- [x] Make the Labor Book Time search tab display existing Labor Book Time library entries.
- [x] Show the structured Labor Book Time creation form inline when no existing entry matches the search.
- [x] Save a new Labor Book Time record and add it to the current repair order in one flow.
- [x] Run focused frontend verification and document results.

## Progress Notes
- [x] Confirmed `PriceBuilderPanel` currently receives only display vehicle fields, while `RepairOrdersPage` has year/make/model/VIN available.
- [x] Confirmed existing Labor Book Time add flow still uses repair-operation search candidates, not the dedicated `/labor-book-time` library API.
- [x] Added `vehicleYear`, `vehicleMake`, and `vehicleModel` props from `RepairOrdersPage` into `PriceBuilderPanel`.
- [x] Changed the Labor Book Time tab to query `/labor-book-time`, showing existing saved book-time entries when the tab opens and filtering them as the user types.
- [x] Added an inline no-match form with labor name, book hours, source notes, year/make/model, engine/fuel/displacement, VIN helper, VIN decode, and `Save & add`.
- [x] Existing library entries can be added directly to the current repair order.
- [x] New no-match entries are saved to the Labor Book Time database and then applied to the current repair order.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx src/features/repair-orders/RepairOrdersPage.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- The Price Builder Labor Book Time search now behaves like a mini Labor Book Time library: it shows existing entries, filters by typed text, and opens the structured create form when no entry matches.
- The inline create flow saves the verified book-time record and adds it to the RO in one action.
- Residual risk: automated verification covered lint/build; a live browser pass should confirm the compact inline form spacing inside the sidekick panel.

---

# Price Builder Labor Book Time Variant Add (2026-07-06)

## Plan
- [x] Confirm the current inline form only appears when no Labor Book Time matches exist.
- [x] Add an explicit way to create another truck/engine variant even when matching book-time entries are displayed.
- [x] Verify focused frontend lint/build and document result.

## Progress Notes
- [x] Confirmed the current form is gated by `laborBookEntries.length === 0`, so existing matches hide the create flow.
- [x] Added `Add another truck / engine variant` below matching Labor Book Time entries when the user has typed a search term.
- [x] Reused the same inline structured form for variant creation, with a close control when it is opened alongside matches.
- [x] The variant form closes after `Save & add`.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Existing Labor Book Time entries remain selectable, and users can now add a new truck/engine variant for the same labor name without needing zero matches.
- Residual risk: this was verified by lint/build only; a live click-through should confirm the extra button placement works well with longer result lists.

---

# Price Builder Internal Order Quote UI Guard (2026-07-06)

## Plan
- [x] Pass the internal repair-order flag into the redesigned `PriceBuilderPanel`.
- [x] Hide customer quote workflow UI for internal repair orders.
- [x] Hide the `Send quote` footer CTA for internal repair orders.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed the legacy workflow block still has `!selectedOrder.is_internal`, but the redesigned sidekick bypassed it with unconditional workflow/send-quote UI.
- [x] Added `isInternalOrder` prop to `PriceBuilderPanel` and passed it from `(orderDetail ?? selectedOrder).is_internal`.
- [x] Wrapped the redesigned quote workflow strip with `!isInternalOrder`.
- [x] Wrapped the footer `Send quote` CTA with `!isInternalOrder`.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx src/features/repair-orders/RepairOrdersPage.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Internal repair orders keep the redesigned price-builder controls but no longer show the customer quote workflow strip or `Send quote` CTA.
- Backend quote protection was already present; this restores the matching UI behavior in the redesigned sidekick.

---

# Price Builder Parts Stepper Unit Alignment (2026-07-06)

## Plan
- [x] Confirm why fluid-part unit labels shift standalone part steppers out of alignment.
- [x] Reserve a consistent unit-label slot for all part steppers.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Found `PartQtyStepper` only renders a unit label for fluid parts and uses a wider input for fluids than discrete parts.
- [x] Added `ea` as the unit label for discrete parts.
- [x] Normalized the quantity input width for all part steppers and reserved a fixed unit-label slot.
- [x] Updated read-only quantity display to include unit labels consistently.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Standalone part steppers now keep a consistent width and unit-label slot across fluids and discrete parts, so rows should align vertically.

---

# Reusable Quantity Stepper Component (2026-07-06)

## Plan
- [x] Extract the price-builder part quantity control into a reusable component with unit labels, fractional steps, keyboard handling, and optional delete-at-min behavior.
- [x] Replace existing price-builder part-line quantity controls with the reusable component.
- [x] Replace the price-builder part-search add quantity input with the reusable component.
- [x] Run focused frontend lint/build and document the result.

## Progress Notes
- [x] User requested this starts with Price Builder, especially the part search list where quantity is currently a plain number input.
- [x] Added reusable `QuantityStepper` component with unit-label slot, typed input, plus/minus controls, Ctrl/Cmd +/- keyboard stepping, and optional remove-at-min support.
- [x] Replaced the existing standalone/service part-line quantity stepper wrapper with `QuantityStepper` while preserving debounced API saves.
- [x] Replaced the Part search list's plain quantity input with `QuantityStepper`.
- [x] Clamped the shared part-search quantity per row so fractional fluid quantities do not carry into discrete `ea` parts.
- [x] Passed focused frontend lint:
  `npx eslint src/components/QuantityStepper.tsx src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Price Builder now uses a reusable quantity stepper for both existing part lines and part search/add rows.
- The component is ready to migrate other quantity controls incrementally without duplicating stepper UI behavior.

---

# Price Builder Part Search Per-Row Stepper State (2026-07-06)

## Plan
- [x] Confirm the part-search list uses one shared quantity state across all rows.
- [x] Store part-search quantities by inventory item id.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] User screenshot confirmed changing one Part search stepper updates every visible row.
- [x] Replaced the shared `partQuantity` state with `partQuantitiesByItemId`.
- [x] Part search steppers now read/write quantities by inventory item id.
- [x] Add success resets only the added item's quantity state.
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx src/components/QuantityStepper.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Each Part search result row now owns its displayed quantity, so changing one stepper no longer updates every row in the list.

---

# Price Builder Add Parts To Service Operation (2026-07-06)

## Plan
- [x] Confirm how parts are currently grouped under service labor operations.
- [x] Allow manual part adds to carry the service-operation grouping id.
- [x] Replace the disabled `Add part to this operation` placeholder with a per-operation part picker.
- [x] Run backend/frontend verification and document result.

## Progress Notes
- [x] Confirmed existing bundled parts are grouped by `PartsUsage.source_service_id` matching the service labor line's `source_service_id`.
- [x] Confirmed manual part creation currently accepts only standalone `inventory_id`, `quantity`, and optional `unit_price`, so operation grouping is not persisted yet.
- [x] Added `source_service_id` to manual part creation and persisted it in `PartsUsage`.
- [x] Replaced the disabled operation-row placeholder with an inline inventory picker that searches available stock, excludes parts already on that operation, supports the reusable quantity stepper, and attaches the selected part to the service operation.
- [x] Added regression coverage for manual part creation with `source_service_id`.
- [x] Passed focused backend verification:
  `./.venv/bin/python -m pytest backend/tests/test_fractional_part_quantity.py -q`
- [x] Passed focused frontend lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx src/components/QuantityStepper.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- `Add part to this operation` is now active for service-backed operation rows and saves parts under that operation instead of adding them as standalone parts.
- Existing standalone Part tab behavior remains unchanged.
- Residual risk: custom labor rows without `source_service_id` still cannot own grouped parts until the data model gains a separate labor-line grouping key such as `source_labor_id`.

---

# Unify Operation/Diagnostic Search + Part Suggestions (2026-07-06)

## Plan
- [x] Merge the tenant's Service catalog into the Repair Operation search so package services (PM Level A, kingpin replacement, etc.) are searchable and still bundle their parts when applied.
- [x] Remove the Diagnostic tab — it only showed a dropdown of every active Service with no diagnostic-specific filtering, and its search box was disconnected from that dropdown.
- [x] Fix the Part/Operation/Labor Book Time palettes staying open after a successful add.
- [x] Add most-used and per-order part suggestions to the Part tab's empty state.

## Progress Notes
- [x] Investigated Service vs. Repair Operation data models: Service is a priced catalog item with bundled parts (booking/fleet PM facing); Repair Operation is a labor-hours estimator with learned memory, no parts, no price.
- [x] `price_build_service.py`: added `_search_service_catalog`, merged into `search_repair_operations` results; `add_repair_operation_line` now routes `service:<uuid>` candidates to the existing `add_flat_service_line` so parts bundling/pricing is preserved.
- [x] New `GET /repair-orders/{id}/parts/suggestions` endpoint: `for_this_order` (parts that co-occurred with this RO's already-applied services/operations elsewhere) and `most_used` (tenant-wide frequency), both excluding parts already on the order and out-of-stock items.
- [x] `PriceBuilderPanel.tsx`: dropped the Diagnostic tab, `serviceOptions`/`serviceId`/`serviceHours`/`addServiceLaborLine`, and the now-dead `services` prop (also removed from `RepairOrdersPage.tsx`'s call site). Down to 3 tabs: Operation, Part, Labor Book Time.
- [x] Service-backed operation candidates show a "bundles parts" tag in the search results.
- [x] `setPaletteOpen(false)` added to the `addPart`/`applyRepairOp`/`applyLaborBookEntry` mutation `onSuccess` handlers.
- [x] Backend: `python -m pytest tests/` — 296 passed, 3 skipped (17 pre-existing unrelated failures in `test_auth_endpoints.py`/`test_security_middlewares.py`, confirmed present on a clean stash).
- [x] Frontend: `npx tsc --noEmit -p .` clean.
- [x] Verified live in browser: typing "EGR" surfaces the library candidate; typing "tire rotation" now surfaces the real "Tire Rotation" Service (tagged bundles parts) instead of offering to create a duplicate; applying it adds a labor line correctly; Part tab shows "Most used parts" before typing and closes after adding.

## Review
- Repair Operation search is now the single place to find any billable work — library estimates, learned hours, and the shop's own Service catalog — instead of a separate, partially-broken Diagnostic tab.
- Part-add UX no longer leaves a stale full-inventory list open after adding; Part tab's empty state now surfaces relevant suggestions instead of nothing.

---

# Price Builder Post-Approval Drawer Cleanup (2026-07-06)

## Plan
- [x] Remove the persistent approved-quote lock warning from the redesigned drawer body.
- [x] Keep lock/next-step rationale available only where the disabled action appears, preferably as hover/title context.
- [x] Default the add-bar to `History` for post-approval, completion, invoice, and paid states, and hide editing tabs where edits no longer make sense.
- [x] Collapse the invoice awaiting payment section into a compact summary row and leave invoice actions in the footer.
- [x] Run focused frontend lint/build verification and document the result.

## Progress Notes
- [x] User reported the approved-quote lock message is unnecessary as persistent body content and should be dismissible/contextual at its workflow step.
- [x] User also clarified that completion/invoice stages should prioritize history over operation/part/labor-book editing, and the invoice awaiting payment block should not expand by default.
- [x] Removed the body-level `pricing_locked` warning and kept lock context on disabled quote/pricing controls.
- [x] Post-build states now force the add-bar into `History` and suppress operation/part/labor-book tabs.
- [x] Invoice-state drawer now shows a compact invoice row by default with optional expanded invoice breakdown; invoice actions remain in the footer.
- [x] Passed focused lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed full frontend TypeScript:
  `npx tsc --noEmit --pretty false` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- The post-approval drawer no longer competes with persistent warning or edit-entry UI; history becomes the default contextual section once price building is no longer the active workflow.

---

# Price Builder Completed-State Shell Migration (2026-07-06)

## Plan
- [x] Confirm why completed repair orders still render legacy Labor Breakdown, Work Completed invoice card, and Recommended Services blocks.
- [x] Add `completed` to the redesigned Price Builder shell status ownership.
- [x] Move the completed-state Create Invoice control into the redesigned drawer footer.
- [x] Keep completed-state add-bar read-only/history-first and hide irrelevant recommended services.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] Confirmed `completed` was omitted from `PRICE_BUILDER_STATUSES`, so the old completed body rendered after work approval.
- [x] Added `completed` to the redesigned shell status list.
- [x] Passed existing invoice due-date and discount settings into `PriceBuilderPanel`.
- [x] Added completed-state invoice settings and `Create Invoice` action to the redesigned drawer footer.
- [x] Guarded the legacy completed internal-cost and create-invoice body cards behind `!priceBuilderOwnsShell`.
- [x] Hid recommended services for completed/invoiced/paid drawer states.
- [x] Passed focused lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx src/features/repair-orders/RepairOrdersPage.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed full frontend TypeScript:
  `npx tsc --noEmit --pretty false` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Completed repair orders now stay inside the redesigned Price Builder drawer. The old completed body step was legacy UI, and invoice creation is now handled from the drawer footer.

---

# Price Builder History Collapse (2026-07-06)

## Plan
- [x] Make the drawer History section collapsed by default.
- [x] Expand/collapse history from its section header.
- [x] Limit the expanded event list to roughly 10 visible events and scroll the rest.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] User clarified history should not show every event open by default and should become scrollable when long.
- [x] Added `historyOpen` state that resets closed when switching repair orders.
- [x] Replaced the always-open timeline with a compact summary row and explicit expand/collapse control.
- [x] Capped the expanded timeline with an internal scroll area.
- [x] Correction: bounded the expanded history panel itself so the event list owns the scrollbar instead of letting history stretch the drawer content.
- [x] Passed focused lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed full frontend TypeScript:
  `npx tsc --noEmit --pretty false` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- History remains available in the read-only drawer states but opens collapsed by default and scrolls independently when expanded.

---

# Remove Invoice Creation Discount (2026-07-06)

## Plan
- [x] Remove invoice discount input from the completed-state invoice creation UI.
- [x] Stop sending `discount_amount` from the repair-order create-invoice mutation.
- [x] Simplify invoice option summary to due-date only.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] User confirmed invoice discount should be removed because it does not affect the Price Builder order total.
- [x] Removed invoice discount props and input from the redesigned Price Builder footer.
- [x] Removed invoice discount state, summary text, payload, and reset calls from `RepairOrdersPage`.
- [x] Removed the dormant legacy completed-card invoice discount field.
- [x] Kept display-only existing invoice discount rows so older invoices with stored discounts still render accurately.
- [x] Passed focused lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx src/features/repair-orders/RepairOrdersPage.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed full frontend TypeScript:
  `npx tsc --noEmit --pretty false` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- New invoices can no longer receive an invoice-only discount from the repair-order drawer. Discounts now need to be applied through Price Builder before invoice creation.

---

# Create Invoice Due-Date Popover (2026-07-06)

## Plan
- [x] Replace the completed-state invoice settings row with a popover opened from `Create Invoice`.
- [x] Offer `Due today` as the default immediate path.
- [x] Offer `Choose due date` with an inline date picker and create action.
- [x] Keep the footer compact and avoid adding a persistent settings section.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] User chose the popover direction for invoice due-date selection.
- [x] Removed the persistent completed-state invoice settings strip from the drawer footer.
- [x] Changed `Create Invoice` to open a compact due-date popover.
- [x] Added `Due today` and `Choose due date` actions inside the popover.
- [x] Updated the parent `onCreateInvoice` callback so the popover can submit an explicit date or default to today.
- [x] Passed focused lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx src/features/repair-orders/RepairOrdersPage.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed full frontend TypeScript:
  `npx tsc --noEmit --pretty false` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- Completed-state invoice creation now keeps the footer compact and asks for due-date intent only when the user starts creating an invoice.

---

# Price Builder History Load More (2026-07-06)

## Plan
- [x] Remove the internal history scrollbar.
- [x] Show the latest 5 history events first.
- [x] Add a `Show older events` control that reveals 5 more events at a time.
- [x] Add `Show less` to collapse the timeline back to the latest 5 events.
- [x] Run focused frontend verification and document the result.

## Progress Notes
- [x] User rejected the double-scroll history design and chose progressive disclosure instead.
- [x] Sorted history newest-first for the timeline view.
- [x] Replaced the scroll-capped list with `historyVisibleCount`, defaulting to 5.
- [x] Added `Show older events` and `Show less` controls below the timeline.
- [x] Removed internal `overflow-y-auto` from the history section so the drawer remains the only scroll surface.
- [x] Passed focused lint:
  `npx eslint src/features/repair-orders/PriceBuilderPanel.tsx --max-warnings 0` (from `frontend/`)
- [x] Passed full frontend TypeScript:
  `npx tsc --noEmit --pretty false` (from `frontend/`)
- [x] Passed frontend production build:
  `npm run build` (from `frontend/`)

## Review
- History now uses progressive disclosure instead of nested scrolling: latest 5 events first, then older events in 5-event batches.
