# Communications assessment and starting plan

Date: 2026-10-16. Board: DB-COMMS-001. Accountable owner: Product & Delivery Lead.
Status: Initial discovery plan, retained as baseline. Follow-on assessment, contract and fixture prototype are now in `docs/communications/`; SMS callback correction is separate draft PR559. Shared backend persistence/outbox remain proposed.

## Outcome and scope

Give shop staff one inbox for customer/driver conversations across SMS, WhatsApp,
and Telegram, connected to the relevant customer, fleet, vehicle and repair order.
Initial assumption: external service communication, not internal staff chat or
marketing campaigns. Preserve existing SMS history and automated repair updates.

## Evidence and limits

- Authenticated production `/dashboard/messages` inspected in Chrome for Truck
  Pit Stop, including the rendered layout. Three threads were visible. Selected
  history included manual and automated messages, delivered/sent statuses, older
  failed/undelivered statuses, and repeated pickup notices for the same order.
- Repetition is an investigation lead, not proof of unintended duplicate sends.
  No provider receipts or new end-to-end send/receive tests were obtained.
- No messages were sent, retried, archived or deleted. Opening the page can mark
  the automatically selected thread read under the current API behavior.
- Source reviewed on local branch `codex/fix-part-catalog-activity`; source is not
  asserted to be identical to the deployed revision. Existing dirty work preserved.
- Read-only discovery/documentation: local services and runtime alignment were
  not needed. No automated tests were run or implementation/release claimed.

## Current foundation

`frontend/src/features/messages/MessagesInboxPage.tsx` supplies a two-pane inbox,
customer selection, replies, unread updates, archive/restore and manager deletion.
The production view is dominated by automatic notifications; it lacks channel
filters, assignment, resolution status, customer/order context and attachments.
Wide-screen message bubbles sit far from the thread list; bounded conversation
width and an optional context panel would make the space more useful.

`backend/app/api/v1/endpoints/messages.py` enforces staff/grant permissions and
the tenant messaging switch. `messaging_service.py` provides Twilio sends,
inbound processing, STOP/START handling, delivery callbacks and realtime events.
The Twilio webhook endpoint validates signatures. Existing messaging tests exist.

The schema is SMS-specific: one thread per tenant/customer, phone-number routing,
SMSMessage records and Twilio SID fields. Unknown inbound numbers create placeholder
customers; phone matches select an existing recent customer/thread. This needs an
explicit identity policy before introducing handles and shared fleet contacts.

Reliability issues to validate before expansion:

- Provider send occurs before the final DB commit, creating an ambiguous outcome
  if the provider accepts but persistence fails. A durable send operation and
  reconciliation path are needed; a blind retry must not duplicate a send.
- Status callbacks overwrite status without an ordering guard in the inspected
  function. Delayed events must not regress a delivered message to sent.
- Callback processing exceptions are logged but the endpoint returns success;
  durable capture/reprocessing is needed to avoid losing status updates.
- Existing inbound SID deduplication is useful but does not establish outbound
  operation idempotency or business-event notification deduplication.

## Product shape

One Messages destination, with All / SMS / WhatsApp / Telegram filters and
Unread / Assigned to me / Open / Resolved views. Separate automated updates from
human conversation through a filter and badges without discarding history.
Show channel, responsible staff member, last activity and clear delivery state.
Keep Archive separate from Resolved; put permanent deletion behind a secondary
manager action rather than beside the routine reply workflow.

The composer explicitly selects an available channel and recipient identity.
Switching channels preserves separate drafts and never sends automatically.
Show restrictions at the composer: disconnected, opted out, template required,
or Telegram not linked. Customer context shows verified identities, company,
vehicles and linked repair orders. Unknown senders enter a reviewable unlinked
contact queue; do not silently merge customers by name, handle or phone alone.

## Delivery sequence

| Step | Accountable owner | Deliverable and exit criterion |
|---|---|---|
| 1. Establish SMS baseline | Backend & Integrations | Trace current sender/webhook configuration and sampled delivery failures/repeated notices; define acceptance fixtures and approved pilot contacts. Distinguish provider acceptance from actual delivery. |
| 2. Shared messaging contract and SMS foundation | Architecture & API Contracts for contract; Backend & Integrations for implementation | Add channel accounts, verified contact identities, generic conversations/messages, durable events and send operations. Migrate/read existing SMS history compatibly; no resend on migration. Existing SMS is the first adapter. |
| 3. Inbox v1 | Frontend & UX | Channel-aware list/composer, search, unread/open/resolved, assignment, context and useful failure states. Existing SMS remains usable on desktop/mobile. |
| 4. WhatsApp pilot | Backend & Integrations | Use Twilio as the initial integration candidate, subject to account/sender eligibility and cost review. Complete business/sender onboarding; support inbound replies and approved service templates; pilot one shop. |
| 5. Telegram pilot | Backend & Integrations | Shop bot with explicit customer start/link flow, secure identity binding and inbound/reply support in the same inbox. Pilot one shop. |
| 6. Extend after pilot | Product & Delivery Lead | Prioritize images/documents, saved replies and controlled service automation using adoption and operational evidence; evaluate email/Messenger only with demonstrated demand. |

Do not build every channel simultaneously. WhatsApp onboarding can proceed while
the shared foundation is built. If WhatsApp approvals delay the pilot, Telegram
can be the first new adapter after the common contract is ready.

## Contract requirements before implementation

Architecture owns request/response shapes, tenant/role rules, error semantics,
idempotency, migration compatibility, fixtures and rollout. Proposed records:
channel account (tenant/provider/sender/configuration), contact identity
(channel/external identity/verification/consent), conversation (participants,
channel account/owner/status), message (direction/source/content/provider ID),
delivery event, and durable outbound operation. Link customer history across
channels without conflating the individual channel conversation or participants.

Use provider/account-scoped IDs and tenant-bound webhook routing. Keep credentials
encrypted on the server. Deduplicate inbound events and outbound intents, retain
delivery-event history, and reconcile ambiguous sends rather than retry blindly.
Do not invent read/delivered receipts when a provider does not expose them.
Consent/preferences remain channel-specific; no silent SMS fallback or fan-out.
An approved estimate link stays the authority for approval; a chat reply does
not silently authorize work or change financial state.

## First implementation slice and acceptance

Start with the SMS foundation plus a channel-ready inbox. Split independently
releasable outcomes into focused branches/PRs and child board items at intake.
Acceptance before adding a new live channel:

1. Existing histories, timestamps, customer links and opt-outs survive migration.
2. Authorized staff can receive/reply and distinguish queued/sent/delivered/failed.
3. Repeated clicks, webhook replay and process restarts do not cause duplicate
   outbound operations; ambiguous provider acceptance is visible for reconciliation.
4. Out-of-order status callbacks do not regress final delivery evidence.
5. Wrong tenant, unauthorized role, disconnected account and channel opt-out
   cases reject safely; shared phone numbers do not silently merge identities.
6. Unknown inbound contacts can be reviewed and explicitly linked.
7. Drafts survive thread/channel switching; assignment/resolution and mobile
   navigation work; automated updates remain distinguishable from staff replies.
8. Focused API/migration/worker/UI checks, independent Security/QA, runtime
   acceptance and tenant-scoped rollout/rollback evidence exist before release.

This is a high-risk implementation lane because it changes schema, external
delivery, credentials and tenant routing. Disable each new channel independently;
preserve existing SMS during rollout. Use controlled test recipients for sends.

## Provider constraints checked

- WhatsApp permits free-form replies during the 24-hour customer service window
  after a customer message; outside it an approved template is required. Account
  onboarding, sender eligibility, consent and pricing need confirmation before
  activation. Source: https://www.twilio.com/docs/whatsapp/api
- Standard Telegram bots cannot initiate conversations with users: users must
  message the bot or add it to a group first. Start with private shop-bot chats,
  a link/QR onboarding flow and verified binding, not arbitrary phone-number
  outreach or personal Telegram account synchronization.
  Source: https://core.telegram.org/bots

Next concrete work: SMS configuration/reliability baseline, then the Architecture
contract and a reviewable inbox prototype. No provider purchase, onboarding
submission, live outreach or deployment is part of this discovery approval.
