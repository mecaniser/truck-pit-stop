# Elis Tech / Truck Pit Stop A2P registration package

DB-COMMS-004 · 2026-10-20 · Backend & Integrations accountable · **Review draft; no provider submission**

## Decision and current account evidence

Truck Pit Stop's repair texts should identify **Truck Pit Stop, operated by Elis Tech LLC**. DieselBridge supplies software. Elis Logistics LLC is a separate legal identity despite common ownership; its verified Brand cannot represent Elis Tech or independent shops.

Read-only Twilio inventory on 2026-10-20, using the configured account: one active account (friendly name “RSTC App Twilio”) and no listed subaccounts; two approved Customer Profiles, **Elis Logistics** and **Right Solution Truck Care**; one approved Standard Brand linked to Elis Logistics and one approved Sole Proprietor Brand linked to Right Solution Truck Care. No Elis Tech Customer Profile or Brand appeared in this account. The account friendly name does **not** establish its billing/legal owner or whether another Twilio account exists. Confirm the primary account's legal owner and ISV eligibility in Console before choosing a profile/account restructure.

| Existing resource | Present state | Hold |
| --- | --- | --- |
| +17755358774 | DieselBridgeConnect service; TrucksParkingHub hiring inbound override; attached Sole Proprietor campaign `VERIFIED` in fresh GET | Keep service membership, inbound route, voice, suppression and conversations intact. |
| +19129223939 | Owned SMS-capable number in separate Low Volume Mixed service; number-level inbound enabled; attached `LOW_VOLUME` campaign `FAILED` with 30907 website/Brand mismatch in fresh GET | Candidate repair sender after correctly owned registration. Preserve number, voice, callback, suppression and history until an approved cutover. Recent outbound 30034 is delivery failure, not an accepted repair registration. |

No third number is proposed. Do not edit the failed Elis Logistics campaign into an Elis Tech identity. Preserve it for audit and decide its disposition only after Twilio-supported account/Brand transition is reviewed. The two previous owner technical sends from 775 were delivered once each; their permanent budgets are consumed. A new live repair reply test needs fresh authorization after registration and routing review.

## Proposed registration fields — submission blocked until evidence is true

| Field | Draft value or required evidence |
| --- | --- |
| Legal sender | **Elis Tech LLC**; verify legal name, registration details and authorized representative privately against business records. Never put tax IDs in this document. |
| Public brand / DBA | **Truck Pit Stop**; verify the trade-name relationship and publish it on the shop site and relevant policies. |
| Business website | https://truckpitstop.com/ — public repair business site. It currently does not identify Elis Tech LLC. |
| Privacy | https://truckpitstop.com/privacy-policy/ — describes repair-status texts and non-sharing for marketing, but has no Elis Tech identity and has inconsistent support phone numbers across site sections. Review and correct before submission. |
| Terms | https://truckpitstop.com/terms-and-conditions/ — currently treats contacting the shop as agreement to SMS; replace with the actual optional affirmative opt-in process before submission. |
| Sender | Existing +19129223939, only after approved Brand/Campaign association and verified exclusive repair routing. |
| Brand class | Evaluate **Low-Volume Standard** against actual expected volume and eligibility; use Standard if required. Elis Tech LLC should not use the existing Sole Proprietor Brand. |
| Campaign use case | Repair-status / customer-care service messages; confirm Twilio's available category and actual volume at submission. No marketing, recruiting, or texts on behalf of independent shops. |
| Support | manager@truckpitstop.com is public; verify the monitored help contact and one canonical support phone before using it in replies or samples. |
| Links/phone in message content | Proposed samples below contain neither links nor embedded phone numbers. Set campaign content flags from actual planned messages; do not claim a future payment link is covered without adding it to samples and disclosures. |

**Campaign description (draft):** “Truck Pit Stop, operated by Elis Tech LLC, sends opted-in customers service-related text updates about their truck repairs. Messages include work-started and ready-for-pickup notices and replies to customer questions about that repair. DieselBridge is the software provider. This program is for Truck Pit Stop customers only; it does not send marketing or recruiting messages.”

**Message flow (conditional draft):** “At [verified Truck Pit Stop check-in or other exact collection point], a customer may actively choose optional SMS repair updates after seeing [the exact disclosure and linked privacy/terms]. The shop records the affirmative choice, phone number, time, disclosure version and collection source before any program text. Declining SMS does not prevent repair service. Public evidence: [URL showing the actual opt-in flow or a hosted redacted screenshot]. Customers may reply STOP to opt out and HELP for assistance. No purchased lists or consent borrowed from another shop.” This paragraph must **not** be submitted until the described flow, record and evidence exist; the prior portal checkbox/verbal logging claims were not established by source inspection.

**Proposed optional consent disclosure:** “I agree to receive service-related text messages from Truck Pit Stop, operated by Elis Tech LLC, about my truck repair and my questions at the number I provide. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. SMS is optional and is not a condition of service or purchase. See our [Privacy Policy] and [SMS Terms].” Confirm this text against the actual collection surface before publication.

**Representative samples, after consent exists:**

1. “Truck Pit Stop: Work has started on repair order [example order]. Reply with repair questions. Reply STOP to opt out.”
2. “Truck Pit Stop: Repair order [example order] is ready for pickup. Reply HELP for help or STOP to opt out.”
3. “Truck Pit Stop: We received your question about repair order [example order]. Our team will follow up. Reply STOP to opt out.”

**HELP draft:** “Truck Pit Stop: For help with repair texts, contact manager@truckpitstop.com. Message and data rates may apply. Reply STOP to opt out.” Verify the mailbox is staffed and Twilio/app response ownership so one HELP request yields one response.

**STOP draft:** “Truck Pit Stop: You are unsubscribed from repair texts. No further messages will be sent from this program.” Keep Twilio-managed and app suppression aligned; avoid duplicate STOP confirmations. Do not promise START resubscription until its actual behavior is verified.

## Evidence needed before any submission

1. Confirm the current Twilio account's billing/legal owner and primary Customer Profile identity, whether an approved ISV primary profile exists in another account, and whether Elis Tech may be onboarded under that primary account. Do not overwrite Elis Logistics or Right Solution Truck Care identities. Choose the supported account path **before** creating any paid resource.
2. Obtain private Elis Tech business evidence: exact legal name, verified trade name, business website, address, registration identifier, authorized representative, and expected SMS volume. Record sensitive values only in Twilio's approved secure intake.
3. Publish a truthful Truck Pit Stop/Elis Tech relationship, corrected SMS terms/privacy, consistent support contact, and an actual optional opt-in surface. Retain a public or redacted screenshot URL and real consent record evidence. Publication requires its own review.
4. Verify the existing 912 service/campaign association, number ownership and effective inbound/status/voice handlers; inventory Twilio and application STOP state and in-flight messages before any move. Moving a number across accounts may reset account-scoped opt-outs. No old send is replayed.
5. Have the user review exact business fields, message flow, samples, fees, account/resource changes and cutover/rollback plan. Provider registration, support contact and number/service changes remain on hold until explicit approval.

## Scalable structure after ownership review

If Elis Tech is the legal DieselBridge ISV, use a truthful Elis Tech **primary ISV** profile in an account confirmed to belong to that operator; register Elis Tech's own Truck Pit Stop repair program with its own Brand/Campaign/Service. For independently owned shops, use one business-scoped subaccount, Secondary Customer Profile and Brand, campaign and Messaging Service per actual shop business/use case. Same-entity locations can share a legal Brand subject to Twilio and consent/routing review. Do not use one DieselBridge/Elis Tech Brand to cover unrelated shops. If the existing account legally belongs to Elis Logistics or cannot be changed safely, preserve it and review an Elis Tech-owned primary account/ISV path and an audited 912 transfer separately. This is a decision tree, not an account change performed here.

## Fee estimate for review (USD; verify at submission)

Twilio's current detailed fee page lists **$4.50** to register a new Low-Volume Standard Brand or **$46** for a Standard Brand, **$15** for a new Campaign vetting, and recurring **$1.50/month** for Low-Volume Mixed or **$10/month** for a Standard campaign. Thus a new low-volume path starts at approximately **$19.50 plus $1.50/month**, or a Standard path **$61 plus $10/month**, before message, carrier, number, taxes or optional vetting charges. The already-owned 912 number does not require a purchase. These are estimates, not charges authorized or a quote from the account. Twilio says an edit/resubmit of the same failed Campaign avoids a second vetting fee, but its Brand belongs to Elis Logistics; that saving does not justify using the wrong legal identity. A new correctly owned Brand/Campaign is the working expectation unless a valid existing Elis Tech registration is found in another account.

## Evidence and references

- Provider GET inventory and both service Campaign statuses: 2026-10-20, configured Twilio account, business-only filtered output; no mutation. Account legal ownership remains unverified.
- Public site inspected 2026-10-20: [shop](https://truckpitstop.com/), [privacy](https://truckpitstop.com/privacy-policy/), [terms](https://truckpitstop.com/terms-and-conditions/). Publication state may change after this date.
- Twilio: [30907 mismatch](https://www.twilio.com/docs/api/errors/30907), [ISV architecture](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/onboarding-isv), [ISV API prerequisites](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/onboarding-isv-api), [failed Campaign corrections](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/troubleshooting-a2p-brands/troubleshooting-and-rectifying-a2p-campaigns), [current detailed fees](https://help.twilio.com/articles/1260803965530-What-pricing-and-fees-are-associated-with-the-A2P-10DLC-service).
- Existing diagnosis and isolation contract: [campaign corrections](TWILIO_CAMPAIGN_CORRECTIONS.md), [repair reply contract](TWILIO_REPAIR_REPLY_CONTRACT.md).

No application/runtime test applies to this documentation-only package. There was no registration submission, support outreach, new number, SMS send, provider setting change, production route, automation, merge or deployment.
