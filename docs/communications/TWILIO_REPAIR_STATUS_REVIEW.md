# Twilio repair-status review package

DB-COMMS-012 · 2026-10-20 · Draft only. No submission or live pilot send.

## Decision to review

Preserve the existing parking sender/program and its TrucksParkingHub inbound route. Establish a correctly scoped Truck Pit Stop repair-service messaging program before enabling customer repair automation. The working legacy number does not by itself resolve campaign-purpose approval.

## Current evidence

| Sender | Observed status | Scope and limitation |
| --- | --- | --- |
| +17755358774 | Owned, SMS-capable; VERIFIED campaign, no reported errors | Existing campaign describes Right Solution Truck Parking reservation notifications with booking/START consent. Service inbound points to TrucksParkingHub. Approval for Truck Pit Stop repair updates is not established. |
| +19129223939 | Separate default sender; FAILED campaign30907 | Website/brand/campaign mismatch; does not provide an alternative approved repair route. |

Truck Pit Stop has no current tenant-specific Twilio binding. All three new routing/outbox/recovery flags remain false. Existing legacy notification behavior remains unchanged; those flags do not globally suppress historical legacy sends.

## Proposed repair registration correction

Use the actual repair business's legal/trade identity, public website, implemented optional SMS consent and service-notification samples. DieselBridge remains the software provider; independent shops require correctly owned business/account/campaign mappings. Do not treat a parking campaign or a generic platform brand as approval for unrelated shop traffic. See the existing multi-shop correction plan for the complete registration structure.

Draft sample copy for review, with no assertion that an actual repair occurred:

- Truck Pit Stop: Work has started on repair order [order number] for [vehicle]. Reply STOP to stop SMS updates. [verified support contact]
- Truck Pit Stop: Your vehicle for repair order [order number] is ready for pickup. [verified support contact]. Reply STOP to stop SMS updates.

Only include a consent channel after its implementation and stored evidence are verified. Preserve current parking consent, suppression, conversations, sender membership and inbound routing. Do not submit this draft, transfer/buy a number or edit the existing campaign as part of the technical pilot.

## Draft question for Twilio support — not sent

We operate DieselBridge as software for independent repair businesses. Existing sender +17755358774 belongs to a verified parking-reservation campaign and its current inbound behavior must stay intact. We want to evaluate two explicitly labeled simulated repair-status messages to the account owner's consenting test phone before implementing the correct repair-business registration. Does the existing campaign permit this tightly limited technical test, or must we first register a separate repair-service campaign/sender? Please confirm the supported ISV/business mapping and a route that preserves all existing parking traffic. We are not requesting a campaign or sender change in this inquiry.

Twilio's [campaign information requirements](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/collect-business-info#message_samples) require representative samples aligned with campaign description/use case. No documented owner-test exception was established in this review. Independent Security/QA therefore holds live repair-status texts pending provider confirmation or a matching approved route. This is an evidence gate, not a legal determination.

## Pilot acceptance after the live gate clears

Exactly two immutable event slots, fixed approved owner phone ending0486, reviewed sender, explicit simulated status copy and no production repair-order changes. Permanent per-event call claims precede I/O. Replays, restarts, timeouts and lost receipts cannot reopen a budget. Verify each provider receipt and handset delivery; verify exact-token reply separately. Managed routing/consent and producer tests use fake provider and synthetic identities until genuinely approved tenant configuration exists. Keep customer activation behind a separate results review.
