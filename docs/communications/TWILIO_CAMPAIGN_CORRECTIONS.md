# Twilio campaign corrections — draft for review

DB-COMMS-004 · 2026-10-16 · Owner: Backend & Integrations

Status: diagnosis complete; corrections drafted, not submitted. Deployment HOLD. No additional SMS, provider mutations, publication, or application changes in this investigation.

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
