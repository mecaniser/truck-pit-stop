# Communications plan and current status

Updated October 28, 2026. Accountable owner: Product & Delivery Lead.

This is the canonical communications status and roadmap. PROJECT_BOARD.md links here;
older chronological board entries and verification documents are historical evidence,
not current task status. Source checked against main 4595998c and current open PRs.

## Released

| Scope | Status and evidence |
|---|---|
| Shared SMS inbox and reliability foundation | Released in PR560, dashboard integration579 and correction580. Search, assignment, unread/open/resolved workflow, drafts, delivery history and durable send operations. Reuses SMS history; not a complete channel-neutral data model. |
| Manual CallRail and new inquiries | Released in PR584/586/587. Incoming inquiries and manual replies retain tenant/account identity and existing history. |
| Automatic reply number | PR594 foundation and PR596 UI released. Receiving-number routing replaces sender selection; new Twilio repair routes remain disabled. |
| MMS receipt and inline images | PR615 recovered only the approved missing receipt. PR627–629 delivered inline/expanded images and provider format compatibility; authenticated ordinary-photo acceptance passed. Never replay the recovery. |
| Loading presentation | PR593 and PR631–636 released. Accessible loading, responsive shimmer placeholder, original caption without obsolete CallRail instruction, preserved draft/reply route. |
| Shared provider allowance and MMS cache | PR648 released on Web/Worker with independent gates and deployed synthetic acceptance. Encrypted 30-day cache; one ELIS-owned account ledger shared by both applications. See budget release receipt. |

## Built, activation held

- Automated outbox and bounded recovery: implemented with duplicate and uncertain-send protection. Customer activation remains held. Legacy immediate notifications are a separate existing path.
- Multi-shop onboarding and consent/routing foundation: incorporated in the released foundation. Provider registration and individual shop activation are not complete.
- Owner-only Twilio pilot: PR591 merged; exactly two simulated status messages delivered. Old verification text saying the PR is unmerged is superseded. This is not approval for customer automation, repair inbound routing or production repair-event acceptance.
- Elis Tech registration package: PR595 merged as documentation only. Business/campaign identity, consent evidence, public disclosures, explicit submission/fees and repair-specific reply routing remain prerequisites. No provider approval is claimed.

## Deferred roadmap

1. Complete the registration, consent and reply-routing prerequisites; then run an explicitly bounded repair conversation pilot.
2. Consider customer automation activation only after end-to-end event, delivery, reply and suppression acceptance and separate activation authority.
3. Complete the channel-neutral identity/account architecture and pilot one new channel: WhatsApp or Telegram. Current labels/contracts are not live adapters.
4. Prioritize outbound attachments/documents and richer media after operational evidence. Email/Messenger remain discovery candidates.

DB-COMMS-023 is released: [contact/customer linking and repair sidebar](communications/CONTACT_REPAIR_CONTEXT_PLAN.md). Contact-linked repairs are the approved default; fleet history is separate. The [frozen contract](communications/CONTACT_REPAIR_CONTEXT_CONTRACT.md) separates CRM links from transport identity; independent gates and PR665 protected checks passed; exact004a49b4 deployed and live customer/person plus16 explicitly authorized repair associations verified. DB-COMMS-024 refines contact detail grouping and dropdown styling; its UI release is pending.

No messaging implementation PR was open at reconciliation. Hosting PR619/622/623 and638 are separate work, not communications blockers. No new channel implementation is started by this reconciliation.

## Controls and evidence

All three SMS rollout controls must remain false: SMS_TENANT_ROUTING_ENABLED,
SMS_AUTOMATION_OUTBOX_ENABLED and SMS_RECOVERY_ENABLED. Preserve forwarding,
consent, existing conversations, automatic receiving-number replies and legacy notifications.

The shared paid override was scheduled to expire October 28 at 04:00 UTC
(midnight America/New_York). The configured strict cap is 1,350 requests per invoice
period across both apps. Cached reads spend no provider request. Other external uses
of provider credentials remain outside this application guard.

- [Budget contract](communications/CALLRAIL_SHARED_BUDGET_CONTRACT.md)
- [Budget release evidence](communications/CALLRAIL_SHARED_BUDGET_RELEASE_20261023.md)
- [Post-expiry verification](communications/CALLRAIL_BUDGET_CHECK_20261028.md)
- [Inline image verification](communications/CALLRAIL_INLINE_MMS_VERIFICATION.md)
- [Registration package](communications/ELIS_TECH_A2P_REGISTRATION_PACKAGE.md)
- [Owner-only pilot evidence](communications/TWILIO_STATUS_PILOT_VERIFICATION.md)

## Reconciliation acceptance

DB-COMMS-022, Product & Delivery Lead: consolidate current status while preserving
historical receipts; verify expired override and current budget read-only; retain false
SMS flags; publish a documentation-only PR. No migration, application change,
provider request, SMS, budget reservation or production write is needed.
