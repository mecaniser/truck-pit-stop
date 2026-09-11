# DB-048 Zelle submission to staff review

Root accountable and implementation owner. Additive read contract, no migration.
Existing same-tenant staff allocations return `sender_evidence` for manual
attempts, limited to sender_name/email/phone, reference/reference_number and note.
Only populated string values are returned; internal markers and arbitrary JSON
never leave the service. Customer/guest allocations return null evidence and
retain existing masked provider references. No cross-invoice lookup is added.

Staff review prefills the existing attempt's reference and note and displays its
submitted sender contact. Provider-confirmed reference takes precedence over
customer-submitted reference. Missing information remains blank. Submitted notes
are attributed as submitted information, not proof of bank receipt. Confirmation
still requires the actual amount, reference and existing attempt version; reading
or prefilling never creates another attempt, releases a reservation or confirms
money. Original submission evidence remains unchanged after staff verification.

Customer/guest Zelle reservation form can include an optional transfer reference
and note using the already-supported create payload. No bank reference is invented
from an invoice number. Acceptance: real pending-attempt read roundtrip, staff
prefill and same-attempt confirm, missing reference remains blocked, sender contact
visible, user edits preserved across rerenders, no auto-submit, customer/guest
evidence redaction and existing same-tenant allocation scoping retained.
