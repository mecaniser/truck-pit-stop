# DB126: originating call at repair intake

Staff may select the originating call once. Qualification and values remain
separate authoritative records; no requalification or value-entry form is added.

DieselBridge POST `/repair-orders/originating-call-options` takes a tenant-scoped
customer UUID and uses existing create-order authorization. Its backend signs a
request to the configured ELIS origin, never a caller-supplied destination.
`/events/repair-intake/candidates` and `/events/repair-intake/reserve` use separate
operation names in the signed body, the existing shop binding and HMAC headers.

Candidate requests carry schema_version 1, event_type repair_intake.candidates,
shop_id, request_id and optional stored customer_phone. Responses contain options
with call_id, opportunity_id, started_at, contact_label, service_summary,
reference_token and expires_at; no transcript or advertising identifiers.
Phone narrows options; it never automatically identifies a repair.

The token is domain-separated, expiring and shop/tenant/call/opportunity bound,
with a planned repair-order UUID. The create request supplies only
originating_call_reference, not raw attribution IDs. Backend reservation checks
current qualification and active membership again, preserves manual decisions
and rejects a conflicting job. The response supplies the validated
repair_order_uuid, elis_opportunity_id and callrail_call_id.

Reservation precedes local creation and is retryable for the same token/repair.
A lost local response must not create another order. An existing local UUID can
be returned only for the same tenant and matching creation identity; changed
customer/vehicle input is a conflict. A reservation is an audited pending intent, not a source shop job. Refresh can
resume the same planned UUID. Actual source ingestion applies the staff choice;
no invoice, financial outcome or conversion exists merely from reservation. No historical hold is released.

Errors: 404 unavailable customer; 409 unconfigured/paused connection or identity
conflict; 502 sanitized provider failure. Ordinary repair creation remains
available with no selection. Frontend never automatically selects an option,
invalidates selection on customer changes and ignores stale async results.

ETS currently uses the existing explicit ELIS association against imported jobs.
A verified source identity/canonical alias and financial evidence contract are
required before ETS revenue can be enabled; this change does not invent an ETS
write integration, sum duplicate invoice copies or assert payment semantics.

Required gates: synthetic tenant, signature, expiry, manual rejection, retired
request, duplicate/retry and no-financial-mutation tests; explicit-selection and
customer-change UI tests; independent security/QA; CI and deployment evidence.
Rollback disables new intake selection/connection usage while preserving source
orders, existing attribution, reservations, audits and previously sent outcomes.
