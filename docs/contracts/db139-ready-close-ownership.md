# DB-139 Ready to Close ownership

Owner: Backend & Integrations. Architecture GO, 2026-10-19. Standard product lane with independent QA and targeted tenant/source security review.

Ready to Close contains native DBN billing work only. One SQL predicate requires RO source NULL/non-ETS and no same-tenant, same-order invoice with ETS source or historical_export_hold accounting policy. Retain cancelled/deleted provenance as an ownership veto. Apply in all three dashboard query paths before ordering, limits, has_more, count and value; preserve status and pending-Zelle rules.

Add nullable default-None RecentOrder.source, explicitly load it and populate every serializer. Completed/invoiced ETS records reaching another projection say ETS history. No migration, payment/provider/snapshot fetch, B1 classification-policy coupling, financial or stored status change, collector change, or inferred Closed Today.

Acceptance: native completed/invoiced and Zelle positives unchanged; ETS zero/positive/all payment states and missing/stale snapshots excluded; linked ETS/hold provenance vetoes native-looking orders; cross-tenant invoice cannot veto local order; cancelled/deleted provenance still vetoes; rows/count/value/pagination agree; history stays reachable and source loads without async deferred IO. Existing staff authorization/schedule masking preserved. Focused backend/frontend checks, independent gates, actual desktop/mobile Light/Night, protected CI and normal deployment required.

Read-only intake: 48 ETS and 11 nominal-native old queue candidates. Native historical-hold and standard invoice groups overlap. Standard SENT invoices with zero-remaining recorded settlement are a separate state-consistency discovery: no Paid inference or financial repair in this outcome. Private identities remain outside Git.
