# Messages contact, customer and repair context

DB-COMMS-023. October 28, 2026. Product & Delivery Lead accountable.
Status: scoped discovery; implementation not started. Architecture owns the API/data contract.

## Approved product behavior

The user chose contact-linked repairs by default, with a separate fleet history view.
The right sidebar provides:

- Unlinked inquiry: Link existing customer or Add customer, with an optional named contact role.
- Linked person: customer/company, contact name/role, and a link to the customer record.
- Active repairs: only explicitly linked repairs, showing order, status, truck/unit and concern.
- Repair history: paginated past linked repairs and serviced trucks, with direct navigation.
- Fleet history: a separately labelled, permission-checked view of the billing customer's repairs.
- Returning from an order preserves conversation selection and unsent draft.

A driver, dispatcher or owner is a Contact under a Customer. A new private owner
may require both records. Do not create a new billing customer for every phone number.
Offer existing-customer search before creation; duplicates require review, never an automatic merge.

## Existing data and missing relationships

Customer has Contact records. Vehicle and RepairOrder reference Customer;
RepairOrder also references Vehicle. Vehicle driver name/phone are loose fields.
There is no reliable contact-to-repair relationship today. Matching a current driver
phone must not attribute all prior repairs on that truck to that person.

The sidebar has a Current repair placeholder, but the live communications context
currently returns routing fields, not a repair-history query. UI labels alone do not
establish a working repair-context integration.

## Architecture boundary

Keep CRM context separate from the SMS transport identity. An inquiry must retain
its original thread kind, receiving binding, phone and CallRail conversation mapping.
The database and routing validators require inquiry customer_id to remain NULL.
Do not convert or merge the inquiry thread to attach customer context.

Add an explicit tenant-scoped conversation-to-customer/contact association and
explicit contact-to-repair associations. Record who linked each association and when;
permit audited correction without rewriting messages or moving financial ownership.
Vehicle history derives from explicitly linked repairs; fleet history derives from the
customer relation and is always separately labelled. A future direct contact-to-vehicle
assignment needs temporal semantics, not retroactive historical ownership.

## Delivery sequence

1. Freeze Architecture contract for link/create/context APIs, optimistic versioning,
   permissions, pagination, duplicate handling and reversible association changes.
2. Implement customer/contact linking and the read-only sidebar using explicit repair links.
3. Verify independent tenant/identity/security and full workflow acceptance.
4. Protected CI, authorized release and signed-in live acceptance before Done.

## Acceptance

- Foreign tenant, missing customer/repair permission and mismatched customer-contact-order links fail safely.
- Same phone across contacts/customers does not silently select, merge or expose fleet history.
- Duplicate clicks/retries do not create duplicate customers or associations.
- Multiple active repairs, no repairs, historical trucks and reassigned drivers render accurately.
- Link/unlink retains message IDs/history, receiving-number reply route, draft, opt-outs and send restrictions.
- No customer linkage grants consent, enables sending or changes invoice ownership.
- Desktop/mobile navigation and return-to-conversation preserve drafts.
- All three SMS rollout flags remain false. No provider send is needed for this feature's tests.

## Runtime preparation

No frontend5193/backend8013 listeners were present on inspection. The former temporary
inline-MMS launcher is gone and backend/.env is absent. The checked-in isolated harness
exists but defaults its synthetic outbox flag to true; do not launch it unmodified for
this task. Re-establish the approved sandbox with all three flags explicitly false,
provider sends denied, and verified database/source alignment before implementation QA.
No services, provider settings or production records were changed during discovery.
