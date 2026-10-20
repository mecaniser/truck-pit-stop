# Automatic reply sender contract

DB-COMMS-015. Architecture & API Contracts reviewed; Backend & Integrations accountable. Frontend & UX owns the operator presentation. No migration, registration or provider configuration change.

## Route authority

Use one authoritative resolver for policy, JSON context, operation creation and dispatch. Never treat selected_for_sending or an arbitrary tenant inventory option as reply authority.

- Inquiry: keep its exact receiving binding and provider/identity checks.
- Customer with inbound history: validate the newest persisted inbound message's provider/account/binding and normalized receiving To against tenant, thread/customer, current recipient and binding. For CallRail resolve the historical exact binding/thread mapping regardless of old selection flag. Managed Twilio requires matching binding/account/service snapshots. Legacy Twilio requires provider SID and current authorized tenant sender; no arbitrary number inference.
- Persisted created_at is the ordering boundary; provider clocks differ, so this does not assert perfect cross-provider chronology. Equal newest timestamps with conflicting routes hold. Never skip newest invalid/disabled/foreign/malformed evidence to use an older route.
- No inbound: a most-recent conclusively provider-backed outbound may establish continuation. Pending/unknown/pre-provider failed rows do not. If no proven evidence exists, only the existing explicit validated shop default can initiate a conversation. Existing invalid/ambiguous evidence holds without defaulting.
- Keep consent, opt-out, ownership, held-operation and provider readiness checks. Preserve explicit CallRail mapping for DBN/ETS identity. A disabled or changed receiving number cannot switch silently to another.

Mixed history remains intact in the current customer thread; no migration to split histories by number is included.

## HTTP and client contract

Context retains sms_provider, sender_number and a derived selected_sender_id where appropriate; sender_selection_allowed is always false. Omit the tenant-wide sms_sender_options inventory (or at most return the single derived route for compatibility). Add sender_mode: reply | initiation | unavailable. Optional sender_route_reason mirrors a concise backend hold. Existing send_policy remains authoritative.

Use stable errors reply_route_unavailable or reply_route_ambiguous for automatic-route holds; UI should explain that the conversation's number needs review. Sender PATCH returns409 sender_managed_automatically and cannot toggle mappings, create workflow metadata or increment version. No hidden manual override in the current operator flow.

New operations snapshot the resolved provider, binding/account, sender and recipient. Dispatch revalidates under existing lock order and rejects a route change before provider I/O. Do not bind identity to the individual evidence message ID: another inbound on the same route is safe, but a changed route cannot silently reroute a queued draft. Idempotency returns the original operation. Accepted/unknown operations remain held/preserved.

## UI

Replace every number chooser with read-only “Replying from [number]”; use “Sending from [number]” for initiation. Provider may appear as secondary context. No inventory dropdown or sender-change handler. Unavailable routes show a concise hold and disabled sending. Preserve recipient/channel drafts and uncertain-send recovery as routes change. Show the receiving number in inquiry context as today.

## Tests and release boundary

Cover both directions of mixed Twilio/CallRail history, older delayed history, timestamp conflict, newest disabled/foreign/malformed evidence, arbitrary selected flags, inquiry/two-numbers-one-tracker pinning, explicit DBN/ETS identity, no-inbound continuation/default cases, pending-route change with zero provider calls, same-route arrivals, duplicate replay and rejected sender PATCH. UI checks: no selector, correct number/mode, hold, drafts and mobile layout. Use isolated synthetic data/providers, all customer flags false. Independent Security/QA and protected CI precede any release; no live SMS or deployment is authorized by this implementation step.
