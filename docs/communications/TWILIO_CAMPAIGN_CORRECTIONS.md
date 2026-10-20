# Twilio campaign corrections — draft for review

DB-COMMS-004 · 2026-10-16 · Owner: Backend & Integrations

Status: diagnosis complete; corrections drafted, not submitted. Deployment HOLD. No additional SMS, provider mutations, publication, or application changes in this investigation.

## Dedicated repair replies — current direction (2026-10-20)

Fresh provider GETs confirm two owned SMS-capable numbers, not a need to purchase a third:

| Number | Effective inbound | Registration | Proposed handling |
| --- | --- | --- | --- |
| +17755358774 | Service override to TrucksParkingHub hiring | VERIFIED sole-proprietor parking campaign | Preserve number membership, service, webhooks, forwarding, consent and hiring history. Do not repoint for repair replies. |
| +19129223939 | Service uses number webhook to DieselBridge `/api/v1/webhooks/twilio/sms/inbound` | Existing repair campaign FAILED30907, website/brand mismatch | Candidate dedicated repair sender after ownership/registration review; preserve existing message history. No purchase is proposed. |

The ten most recent outbound records from the912 sender are undelivered30034. It has historical inbound activity, so it is not an untouched spare. Inventory and these bounded logs do not prove that no other workflow references it. Verify current app/tenant use before changing any assignment.

A new phone number, a Messaging Service and an approved A2P campaign are different resources. A separate repair number prevents ambiguous cross-product reply delivery; buying a number does not grant campaign approval. Twilio allows only one campaign per number. The current parking campaign is specifically SOLE_PROPRIETOR; do not attach or move a repair sender into it. Use the existing repair campaign correction path only if its Brand actually belongs to the correct legal operator; otherwise prepare a correctly owned Brand and repair campaign under the ISV structure below. The user’s Elis Tech LLC clarification means the recorded Elis Logistics Brand is not an interchangeable identity. Do not assume a new Twilio account, company or Brand is required merely to obtain a second number.

### Review package before submission

1. The user identifies Elis Tech LLC as Truck Pit Stop’s legal operator. Prepare registration under Elis Tech LLC with the supported Truck Pit Stop trade-name relationship and matching repair website/consent. The existing Elis Logistics identity is a different legal entity and must not be relabeled or borrowed merely because ownership is shared. Reuse an existing correctly verified Elis Tech profile/Brand if present; otherwise prepare one. Leave the working parking registration intact.
2. Scope the campaign to the repair business's service updates and replies: work started, repair review/ready for pickup, and customer questions about that repair. Do not claim it covers every independent DieselBridge shop.
3. Replace platform-wide placeholder sample names with the actual shop brand. Proposed copy: “Truck Pit Stop: Work has started on repair order [order]. Reply STOP to unsubscribe.” and “Truck Pit Stop: Repair order [order] is ready for pickup. Reply HELP for help or STOP to unsubscribe.”
4. Describe only implemented, optional SMS consent, supported by actual website/check-in evidence and stored consent records. Do not submit an unimplemented checkbox or implied consent claim. Verify actual HELP contact, privacy and terms before including them.
5. Review correction eligibility and charges in Twilio before an explicitly approved resubmission. If the necessary account/Brand/use-case changes cannot be edited, review replacement registration first. Do not delete or edit the working parking campaign.
6. Once registration and dedicated assignment are approved, verify effective service-level inbound behavior and number-level status callback. The currently configured URL alone is not proof of public callback acceptance.

### Reply test and preservation

Architecture contract: [owner reply route](TWILIO_REPAIR_REPLY_CONTRACT.md). The approved tester has both DBN and ETS customer identities. Add an explicit, expiring reply-only account/receiving-number/sender/tenant/customer/thread approval. Pin the DBN conversation; preserve the ETS duplicate and TPH records. Reserved receiver mismatches must hold instead of guessing or creating a placeholder.

Prepare and independently test this in a separate synthetic database with all customer rollout flags false and no provider calls. Do not seed a live binding until reviewed registration, sender ownership and fresh test authorization exist. Actual send-and-reply acceptance remains pending. Previous two-event technical-send budgets are consumed and must never be reset. Customer automation remains a separate approval gate.

Twilio support question remains DRAFT ONLY per user. No registration submission, support outreach, number purchase, provider setting change or live SMS is performed by this preparation.

Sources: [multiple messaging use cases](https://help.twilio.com/articles/4403014741403-I-have-multiple-messaging-use-cases-How-should-I-register-my-use-cases-for-A2P-10DLC-), [associate numbers with a campaign](https://help.twilio.com/articles/4402888763803-How-can-I-associate-Twilio-numbers-to-an-A2P-10DLC-Campaign-), [correct rejected campaigns](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/troubleshooting-a2p-brands/troubleshooting-and-rectifying-a2p-campaigns).

## Confirmed cause

Live authenticated Twilio reads returned campaign FAILED with error30907 on MESSAGE_FLOW: website URL does not match the registered brand and campaign. Brand status is APPROVED, identity VERIFIED, type STANDARD. Underlying customer profile: business name Elis Logistics, identity direct_customer, industry TECHNOLOGY, website https://dieselbridge.com. No tax IDs, credentials, or personal profile details were retrieved for this report.

Campaign describes DieselBridge as a platform sending for auto/truck shops. Samples alternate between Diesel Bridge, Truck Pit Stop via DieselBridge, and [Shop Name]. Message flow claims verbal consent at shop check-in and an online portal opt-in checkbox, both logged before sending. This is a concrete identity/use-case inconsistency consistent with the rejection; Twilio does not identify a more specific rejected website element.

The sender already belongs to the campaign's Messaging Service. Merely attaching the number again is not the fix. The prior test returned undelivered30034 because an approved campaign association is absent.

## Multi-shop registration structure — revised direction

DieselBridge is the ISV (software provider). Independent repair-shop businesses are the messaging customers/senders. Truck Pit Stop is one tenant, not the scope of the platform.

Use Twilio ISV architecture #1: primary DieselBridge account, one subaccount per independent customer business, a Secondary Customer Profile and Brand for that business, and a Campaign plus Messaging Service per messaging use case. The primary profile must truthfully identify DieselBridge's legal operator. DieselBridge's own messages require separate appropriate registration; its brand does not cover independent shops. Source: [Twilio ISV overview](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/onboarding-isv).

Proposed DieselBridge mapping:

```text
DieselBridge primary account / legal operator
  Shop business A subaccount
    Customer profile → Brand A → Service-notification campaign
                              → Messaging Service A → dedicated sender(s)
  Shop business B subaccount
    Customer profile → Brand B → Service-notification campaign
                              → Messaging Service B → dedicated sender(s)
```

The arrows after each brand represent that business's campaign/service/sender association. Our recommended initial product configuration is one service-notification program per business, covering the accurately declared repair-service messages. Confirm the appropriate available campaign use case during onboarding; add separate programs for materially different purposes such as marketing.

Registration follows the legal customer business, not blindly every physical location. For a chain under one legal entity, model business ownership separately from shop locations and confirm brand/location treatment with Twilio before creating duplicate registrations. Independently owned shops must not share a catch-all DieselBridge brand or sender.

### Platform configuration and tenant boundaries — proposed implementation

- Add a messaging-business record linked to authorized shop tenants, with subaccount SID, Customer Profile/Trust Product/Brand/Campaign SIDs, Messaging Service SID, sender SID/number, registration state, last provider verification, and secret-manager credential reference. Store no credentials or tax IDs in ordinary app logs or review documents.
- Resolve provider credentials and Messaging Service from the authenticated tenant's approved business binding. Eliminate the global Twilio client/sender fallback for customer traffic. Snapshot the provider binding on each durable send operation so retries and reconciliation cannot switch business accounts.
- Require tenant permission, active approved registration/sender, and valid scoped consent before a manual or automated dispatch. Pending, rejected, suspended, or unmapped tenants remain blocked with an actionable inbox status.
- Validate incoming webhook signatures with the correct account credential and verify AccountSid, destination sender, and message-operation ownership. Never trust a tenant ID supplied by the webhook caller. Deduplicate events with provider-account context.
- Keep consent and suppression scoped to the appropriate shop business/program. A shared customer's phone number does not transfer consent across businesses. Define shared-chain location access explicitly; never infer access merely from a shared brand.
- Preserve existing idempotency and uncertain-outcome holds. Add cross-account sender, forged callback, unapproved-registration, cross-tenant consent, and mismatched receipt tests before enabling live tenant traffic.

These are architecture requirements to implement and review, not claims that the current prototype already supports subaccounts.

### Repeatable shop onboarding

1. Collect the business's legal identity, trade name, website, authorized representative, eligibility details, expected volume, and authorization to register on its behalf through a secure onboarding process.
2. Select the appropriate Brand type for that business. Use the separate Sole Proprietor path when eligible; do not invent an EIN or reuse DieselBridge's registration for another business.
3. Create/verify the customer's profile and required A2P trust resources, register its Brand, then its accurate use-case Campaign and Messaging Service in the correct account context. Follow the [ISV API guide](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/onboarding-isv-api).
4. Fill the reusable draft below with that shop's actual identity, support contact, URLs, samples, and evidenced consent flow. Hosted DieselBridge consent pages must clearly identify the particular shop; a generic platform landing page alone is not customer-business evidence.
5. Surface draft/submitted/in-review/approved/rejected/suspended states per business. Retain rejection reasons and an audit trail; expose registration and recurring messaging costs before submission rather than silently provisioning paid resources.
6. Associate dedicated sender(s), verify readiness, then run controlled end-to-end acceptance before enabling the tenant. A successful pilot does not automatically enable every other shop.

### Existing failed registration and migration

Keep the existing failed campaign unchanged pending review; it cannot become an umbrella for independent shops by rewriting its description. Confirm who legally operates DieselBridge, then plan the supported direct-customer-to-ISV transition with Twilio if the existing profile requires correction. Do not delete the approved brand, recreate campaigns, buy numbers, or transfer the current sender in this planning step.

Inventory existing account/service/sender ownership and both provider/application suppression records before any approved migration. Twilio warns that moving to subaccounts resets its account-scoped opt-out mechanisms; preserve and re-enforce existing opt-outs before sending from the new context. Keep queued operations on their original binding or cancel/recreate through an audited process; never blindly replay old sends under new credentials. Use a cutover/rollback plan covering sender ownership, webhooks, credentials, and in-flight receipts.

## Findings requiring correction before resubmission

| Field / surface | Current issue | Proposed correction |
|---|---|---|
| Business identity | Elis Logistics direct_customer versus multi-shop platform campaign | Register DieselBridge as the ISV and each independent business as its own customer brand |
| Website | dieselbridge.com represents the platform in the submission | Provide actual sender's public business site, truthful legal/trade-name relationship, contact details, and matching consent evidence |
| Campaign description / samples | Three sender identities | Use one verified customer-facing shop identity consistently |
| Message flow | Claims two consent paths and recorded consent | Include only implemented, evidenced paths; remove unsupported portal and audit claims |
| Terms SMS section | Source says providing a phone number constitutes consent | Replace with an explicit optional SMS agreement and documented acceptance |
| Privacy | General non-sale statement; no SMS-specific non-sharing text in inspected section | Add precise SMS consent/mobile-data handling text consistent with actual practice |
| Help response | Only STOP and rates; no identified support contact | Identify sender and a verified support contact |
| Opt-in response | Describes collection process rather than customer confirmation | Use a real confirmation message if supported; align configured keywords with actual behavior |

Source inspection: frontend/src/features/landing/TermsOfServicePage.tsx; PrivacyPolicyPage.tsx; backend/app/db/models/customer.py; customer/auth UI searches. Customer model has opt-out fields; this inspection did not establish affirmative-consent evidence or the claimed portal checkbox. Treat those as unverified, not implemented. Public dieselbridge.com/privacy and /terms could not be retrieved by the web reader; production availability/content is not certified by local source inspection.

## Reusable campaign fields — instantiate separately for each shop business

Bracketed fields must be resolved and evidence published before submission. These are proposed behaviors, not claims about current production.

**Description**

[VERIFIED SHOP NAME], operated by [VERIFIED LEGAL ENTITY], sends service-related texts to customers who explicitly choose SMS updates for their vehicle repairs. Messages cover appointment confirmations/reminders, repair progress, vehicle pickup, invoices/payment links, and two-way service questions. DieselBridge supplies the software. This campaign is limited to this shop's customers and does not send promotional messages.

**Message flow**

Customers opt in at [EXACT IMPLEMENTED CHECK-IN LOCATION OR FORM URL]. An optional, unchecked SMS consent field displays the disclosure below. Customers can receive repair service without agreeing to SMS. Before sending, the shop records the customer's affirmative choice, phone number, timestamp, disclosure version, and collection source. Public evidence of this exact form is available at [PUBLIC EVIDENCE URL]; the shop website is [SHOP URL], privacy policy [PRIVACY URL], and SMS terms [TERMS URL]. Messages vary with the customer's service activity. Customers can reply STOP to opt out and HELP for support. Only implement and describe START resubscription if verified end to end. No purchased lists or consent transferred between independent shops.

**Consent disclosure**

I agree to receive service-related text messages from [VERIFIED SHOP NAME] about appointments, repairs, pickup, invoices, payment links, and my service questions at the number provided. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. SMS consent is optional and is not a condition of receiving service or making a purchase. See [PRIVACY LINK] and [SMS TERMS LINK].

**Sample messages**

1. [VERIFIED SHOP NAME]: Your appointment is confirmed for [date/time]. Reply with any questions. Reply STOP to opt out.
2. [VERIFIED SHOP NAME]: Your vehicle is ready for pickup. Contact us at [VERIFIED SUPPORT PHONE] for pickup details. Reply STOP to opt out.
3. [VERIFIED SHOP NAME]: Your invoice is ready: [ACTUAL BRANDED INVOICE URL WITH EXAMPLE TOKEN]. Reply STOP to opt out.

Use a real, representative branded URL in the final sample, without a live customer's token. Because sample2 includes a phone number, set has_embedded_phone=true if that sample/content is retained; links remain true. Confirm LOW_VOLUME fits expected actual traffic; no use-case change is proposed solely to address30907.

**Opt-in confirmation, if implemented**

[VERIFIED SHOP NAME]: You subscribed to service-related text updates. Message frequency varies. Message and data rates may apply. Reply HELP for help or STOP to opt out.

**Help**

[VERIFIED SHOP NAME]: For help, contact [VERIFIED SUPPORT PHONE OR EMAIL]. Message and data rates may apply. Reply STOP to opt out.

**Opt-out**

[VERIFIED SHOP NAME]: You are unsubscribed from text messages. You will receive no further messages from this program.

Align these with the actual Twilio default/Advanced Opt-Out or application response owner before submitting; do not create duplicate automated responses. Current registration lists ACCEPT/YES/AGREE but describes START resubscription. Verify actual keyword settings rather than assuming registration text configures runtime behavior.

## Proposed website wording

Platform identity draft: “DieselBridge, operated by [VERIFIED PLATFORM LEGAL ENTITY], provides software that repair businesses use to communicate with their own customers. Each participating business is identified in its messages and obtains its own customer SMS consent.” Verify the legal operator before publication. Keep platform terms/privacy and each shop’s program disclosures consistent about these roles.

Identity: “[VERIFIED SHOP NAME] is operated by [VERIFIED LEGAL ENTITY]. We use DieselBridge software to manage repair services and customer communications.” Publish only if factually correct.

Terms replacement: “SMS updates are optional. We send service-related texts only after you affirmatively agree through our stated consent process. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for assistance at [SUPPORT CONTACT]. Consent is not a condition of purchase or service.” Include the actual messaging scope and verified resubscription process.

Privacy addition: “Mobile numbers and SMS opt-in consent data are not sold or shared with third parties or affiliates for marketing or promotional purposes. We use service providers to deliver the messages you request. SMS consent is specific to [VERIFIED SHOP NAME].” Confirm this accurately describes actual data practices before publication.

## Implementation and acceptance needed

1. Confirm DieselBridge’s legal operator and adopt the ISV structure above. Collect each customer business’s legal identity, trade name, website, and support contact; instantiate a separate registration package for each independent business.
2. Implement/verify optional consent collection and evidence storage. Gate manual and automated sends on consent for that tenant/recipient/purpose; a phone number or absence of opt-out alone is insufficient evidence. Test missing consent, withdrawal, foreign-tenant consent, and historical customers without evidence.
3. Prepare public website, privacy, terms, and redacted consent evidence matching the chosen sender. User reviews the completed copy before publication/submission. Deployment hold remains in place; publication requires a separately approved path.
4. Implement and independently review tenant-to-subaccount routing and the migration safeguards above. Confirm the supported ISV onboarding/transition workflow with Twilio before any profile change. Preserve the existing failed campaign and approved brand until an explicit migration plan is reviewed.
5. After approval, verify sender registration/association is active. Authorize a new bounded test to the same approved recipient; preserve the consumed previous test ledger.
6. Verify handset receipt, reply, signed public callbacks into the new implementation, duplicate safety, and opt-out behavior before any release decision. Campaign approval alone does not authorize deployment.

## Sources

- Multi-customer account structure: https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/onboarding-isv
- Customer profile, trust resources, and Brand onboarding: https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/onboarding-isv-api

- Exact rejection and correction guidance: https://www.twilio.com/docs/api/errors/30907
- Consent-flow evidence: https://www.twilio.com/docs/api/errors/30909
- Privacy guidance: https://www.twilio.com/docs/api/errors/30908
- Editing eligibility and cautions: https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/troubleshooting-a2p-brands/troubleshooting-and-rectifying-a2p-campaigns

This is a review draft, not a submitted registration or certification of production consent compliance. No runtime test is applicable to these documentation-only corrections.

## Business ownership clarification and platform growth

The user identified Elis Tech LLC as the legal repair-business operator. Registration represents the legal entity behind the messages; common personal ownership does not combine Elis Logistics LLC and Elis Tech LLC into one Brand. Keep current approved programs intact rather than changing their identity in place.

Resource model for review:

| Resource | Meaning | Direction |
| --- | --- | --- |
| Twilio account/login/billing | Container and commercial relationship | A separate login/account is not inherently required per company. Preserve current account/programs while planning profiles/subaccounts. Do not silently change its primary legal owner. |
| Customer Profile and A2P Brand | Verified business identity | Elis Tech LLC for its own repair program; Elis Logistics for its own programs. A public trade name must be supported by the correct legal business and website. |
| Campaign and Messaging Service | Message purpose, consent and effective reply handler | Separate repair-status program from the existing parking/hiring flow. Do not treat the currently approved parking samples as repair approval. |
| Phone number | Customer-facing calling/texting identity | Preserve775 for current TPH replies. Review reusing owned912 for repair after correct approval and routing; no new purchase proposed. |

If Elis Tech LLC also operates DieselBridge as the software provider, use its truthful primary ISV profile in the long-term structure. Independently owned repair businesses receive their own customer profiles/Brands and scoped subaccounts/services. Multiple locations of the same legal business need not be treated as unrelated legal entities. Audit existing account ownership and opt-out retention before any restructure; Twilio warns that moving to subaccounts resets provider-managed account-level opt-outs. No restructure is performed here.

Voice configuration is separate from SMS A2P registration. A suitably capable number can serve both calls and texts with separate handlers. A repair SMS campaign is not approval for every voice, WhatsApp or future messaging use case. Preserve current voice URLs and forwarding when reviewing any number move.

Sources: [ISV profiles and account architectures](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/onboarding-isv), [Brand onboarding](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/onboarding-isv-api), [Voice and messaging webhooks](https://www.twilio.com/docs/usage/webhooks). All registrations, identity/account changes, provider settings and customer automation remain held for review.

## Current sender distinction — 2026-10-20 review update

Read-only production/provider verification separates two numbers that must not be conflated:

- Truck Pit Stop's legacy sender **+17755358774** is SMS-capable and belongs to a VERIFIED campaign without provider-reported errors. However, that campaign describes **Right Solution Truck Parking reservation updates**, with booking/START consent, and parking-specific sample messages. Its Messaging Service inbound URL remains TrucksParkingHub. Working transport and VERIFIED state do not establish approval for Truck Pit Stop repair-status automation or unrelated shops.
- The separate global configured sender **+19129223939** belongs to the other service with FAILED campaign/error30907 (website does not match brand/campaign). This earlier rejection remains unresolved.

Do not move either sender, replace the parking campaign, change inbound forwarding or reuse its purpose as a platform-wide repair registration. Preserve existing parking conversations and suppression. Prepare the repair business's truthful service-notification registration, sender ownership and consent binding for review using the existing multi-shop plan above. No submission, provisioning, legal-identity change or customer activation occurred in this update.

The authorized owner-only technical pilot uses explicitly simulated status events and no real order transitions. Its results can establish only limited transport/outbox behavior. Campaign-purpose approval, genuine tenant binding/consent, canonical customer reply identity and controlled production producer rollout remain gates before customer repair automation.
