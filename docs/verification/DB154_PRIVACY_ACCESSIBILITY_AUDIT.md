# DB-154 — Privacy, public policies and accessibility

2026-11-03. Accountable owner: Frontend & UX. High-risk privacy lane. Branch: `codex/privacy-safety`. Base: `24790dd3` (origin/main at intake). Status: implementation reviewed; [draft PR761](https://github.com/mecaniser/truck-pit-stop/pull/761) open at implementation commit `0f3ea542`; unmerged/undeployed, protected CI/release gates pending. This is engineering evidence, not legal advice or a compliance certification.

## Verified operator decisions

The operator supplied: Elis Tech LLC, doing business as Diesel Bridge Network; 1002 Yearden Ln, Monroe, NC 28110, United States; privacy/contact email support@dieselbridge.com (confirmed replacement on 2026-11-03). Subscriptions are month-to-month, non-refundable except where applicable law requires a refund; cancellation stops future monthly renewals. The operator also confirmed ownership or permission for current site logos/images. No independent chain-of-title search or legal review was performed. A North Carolina mailing address does not establish the entity's formation jurisdiction or select governing law.

## Implementation and audit coverage

| Requested safeguard | Result and limits |
| --- | --- |
| Privacy policy | Existing notice updated with operator identity/contact, feature-provider disclosures, disabled analytics, shop-controlled records and deletion-request link. Blanket “industry-standard” security claim removed. |
| Terms | Existing terms corrected: providing a phone number and accepting terms do not grant SMS/marketing consent. Optional marketing must be separate and not a purchasing condition. Added refund/fee references. |
| Refund policy | `/refunds` states approved monthly/non-refundable rule with statutory exception and email cancellation route. Repair-shop purchases remain the supplying shop's responsibility. Policy does not itself automate billing cancellation. |
| Cookie policy/banner | `/cookies` plus global nonmodal, keyboard-accessible necessary-only notice and persistent settings action. No fabricated Accept-all choice for nonexistent optional collection. Preference lasts up to 180 days; blocked/malformed/old acceptance storage does not enable tracking. Callback UI remains absent. |
| Data minimization | Removed EIN/business-license inputs and omitted their values from enrollment payloads. Existing historical records were not deleted. Legacy API rejects nonempty EIN/license fields with safe400 before tenant/user/provider writes; empty/null legacy fields remain compatible. This is not a system-wide retention reduction. |
| Form consent | Privacy disclosure appears before personal-data entry and terms link at review. Explicitly explains that phone details do not grant SMS or marketing consent. Existing SMS systems have opt-out enforcement; full affirmative opt-in provenance/enforcement is not certified by this work. No new messaging enabled. |
| SDK audit | GA loader removed, including automatic history listener exposure; no page/title/query/token/account tracking remains in app source. Existing Stripe pure lazy loader retained. Feature-triggered Mapbox, Stripe and server providers inventoried below. Third-party font requests replaced with local licensed files. |
| Dark patterns | No optional tracker acceptance pressure, no prechecked marketing box, no false automatic deletion/unsubscribe receipt, and fictional demo data labeled. No exhaustive audit of every authenticated workflow. |
| Fees | Public invoice source itemizes subtotal, supplies, card fee, tax and total before payment; refund page directs users to review final charges. No new financial calculations or fee removals. Actual live checkout variants and individual merchant fee lawfulness remain unverified. |
| Reviews/claims | Landing renders approved partner records, not hardcoded customer ratings/testimonials. Demo explicitly labeled fictional. No fabricated reviews identified in the inspected landing source. Authenticity of all external/user-supplied review content is not established. |
| Alt/accessibility | All 31 production JSX `<img>` elements inspected have an alt attribute. Adjacent-name/decorative logos correctly retain empty alt where appropriate. Wordmark now has `role=img` and accessible label; header link named. Added legal skip links and 44px privacy actions. Alt attribute presence alone is not proof of image-description quality. |
| Contrast | Landing/enrollment primary gradients darkened: white against brightest normal stop improves from 3.09:1 to 6.34:1; hover brightest stop 5.68:1. Enrollment low-contrast labels lightened. New policy text/nav and banner pairs exceed 4.5:1. Gradients/overlap still require manual evaluation; no app-wide WCAG certification. |
| Business identity | Public footer and policy contacts use supplied legal/trading name, address and email. |
| Email unsubscribe | Both direct Resend and provider-outbox paths include mailto **request** link, business address and data-deletion request. Wording explicitly states no automatic unsubscribe and distinguishes essential security/transaction notices. No one-click header or recipient suppression registry added; requests require actual operator processing. |
| Font/image rights | Eight locally hosted WOFF2 files across Inter, DM Sans, Plus Jakarta Sans and Geist; upstream OFL license texts, package versions and SHA256 manifest in `frontend/public/fonts/`. Existing font choices preserved. Site images authorized by operator confirmation; shop/customer uploads still require appropriate rights. |
| Deletion option | `/data-deletion` prepares an email to the supplied privacy contact, with copyable fallback and minimum verification guidance. No login, ID upload or automatic destructive action. Actual mailbox handling/retention decisions remain operational obligations. |

## Third-party inventory

| Provider | Source/use and privacy boundary |
| --- | --- |
| Google Analytics | Removed from `App.tsx`; earlier cookie identifiers accessible on this origin cleared. Historical Google-held data not deleted. Reintroduction requires fresh consent design and proof that automatic events cannot observe private navigation. |
| Fonts | Previously Google Fonts/jsDelivr on initial load; now own-origin font CSS/files, callback excluded. OFL notices shipped with unmodified binaries. |
| Stripe | `frontend/src/lib/stripe.ts` uses pure loader when payment/card flow requests it. Relevant payment/device information goes to Stripe. Cookie notice does not disable a user-requested payment feature. No payment sent in testing. |
| Mapbox | Map/address-search features send requested location/search data to Mapbox. No map resources observed on inspected public routes. Provider contractual/billing/license setup not independently verified. |
| WorkOS | Configured identity integration; authentication provider distinct from optional analytics. No provider/session settings changed. |
| Resend | Direct and outbox email delivery; recipient and message contents processed by provider. No real email sent. |
| Twilio / CallRail | Messaging/call integrations and opt-out handling. No messages sent; positive-consent provenance remains separate from a phone number. |
| Cloudinary | Media hosting integration. Uploaded/remote media permissions and retention require business controls. |
| Google Business Profile / Motive / Anthropic | Connected review/fleet data and AI review drafting; provider scopes, operator authorization, retention and data handling require their own controls. No integration triggered or data resynchronized. |

### Dependency remediation — DB-155

The earlier 22 production npm findings were remediated in this authorized release. Unused jspdf/react-pdf and their vulnerable graphs were removed; serving moved from serve to sirv-cli. Router7, Zod4, Vite8, Vitest5 and ESLint10 compatibility is covered by build, full suites and actual authenticated navigation. Node22 is selected in Docker/CI. Registry URLs/integrity remain in the lockfile.

All frontend dependencies including development tools: **0 known vulnerabilities**. E2E, Motive importer and ETS importer npm lockfiles independently audit **0**. Python resolved to **89 exact locked packages**, with **0 pip-audit findings**; main/development and all six integration worker builders install that lock. PyJWT replaces python-jose while preserving explicit algorithm/authority validation. These are registry advisory results at verification time, not proof that no vulnerability exists.

## Verification

- Focused frontend: 24/24 passing across PrivacyControls, PublicPolicies, LandingPage and mechanic toaster compatibility.
- Backend direct email and provider outbox: 13/13 passing, provider transport mocked; includes footer placement, manual-request wording and outbox bypass regression.
- Production build and shared controls check pass. Changed-source ESLint passes with zero warnings. `git diff --check` passes.
- Axe 4.14.0 on `/`, `/privacy`, `/terms`, `/cookies`, `/refunds`, `/data-deletion`, `/enroll`: zero reported WCAG A/AA violations in final fixture pass. Gradient/overlap contrast and some ARIA checks marked incomplete; manual contrast calculations and independent semantic review supplement, rather than override, those limits.
- Enrollment fixture browser journey reached final review, verified no EIN/license fields and terms link; application was not submitted.
- Browser public route fixture pass: no external origins observed. All five policy routes carry supplied identity. Mobile 375×812 fits without horizontal overflow; cookie actions work with keyboard, retain focus on settings, and have 44px targets. Legal skip link focuses policy main.
- Independent Security initially NO-GO: failed-withdrawal storage case, automatic analytics history leakage, outbox footer bypass. All corrected and independently source-approved GO. Independent QA GO for the bounded public UI; implementing agent did not approve its own gates.
- Independent QA did not certify real billing, actual delivered email, provider configuration, legal sufficiency or the complete authenticated app.

## Final remediation verification — 2026-11-03

- Full frontend: **225 files / 2477 tests passing**. Full backend: **5337 passing / 468 skipped**, no failures. Skips are recorded, not claimed as exercised.
- Production build and shared-control check pass. Final changed-source lint and exact-head CI remain release gates.
- Full-stack smoke: **5/5 passing**. Actual sandbox browser verifies all five policy contacts, authenticated login, canonical Inventory navigation, Services active state, and no external resource origins in those journeys.
- FastAPI route tests use public OpenAPI/real ASGI dispatch; Pillow13 tests cover valid multi-frame/orientation handling plus deliberately corrupt MPF metadata. Vitest constructor/timer compatibility fixtures corrected without removing assertions.
- Independent final source Security **GO**: lock adoption, explicit JWT algorithms, enrollment pre-write rejection, public contact minimization, response identity guard, Docker context exclusions. Independent final QA pending at this checkpoint.

## Local runtime receipt

The initially missing local configuration was resolved with an isolated credential-free sandbox based on the existing approved CI/sandbox launch pattern. Project `db761-sandbox` uses disposable database `db761_disposable`, Redis, ENVIRONMENT=test, empty messaging/payment/provider keys and disabled WorkOS. Migrations apply only to this disposable database; other stacks and populated volumes remain untouched.

Frontend `http://127.0.0.1:5173` serves this privacy-safety checkout; backend `http://127.0.0.1:8000` uses the same checkout mounted read-only with the new locked image. API readiness and frontend proxy report database/Redis ready. Actual rendered policy contacts and authenticated My Shop navigation corroborate source alignment. **Aligned and browser-verified**, distinct from production release. No real emails, payments, customer-data deletion or financial mutations were performed.

## Release and operational obligations

The operator explicitly authorizes PR761 merge/deploy after passing technical gates. PR remains unmerged at this checkpoint; exact pushed-source CI, production source/readiness and changed-route acceptance must be recorded before Done. Rollback: revert the merge through a reviewed PR if auth, enrollment, routing, email provider errors or health regress; retain sender configuration consistent with verified domain. No database migration is introduced by this release.

The operator must monitor **support@dieselbridge.com**, verify requests with minimal information, route shop-controlled records, honor retention exceptions and process deletion/cancellation/optional-email opt-outs. The mailto links do not automatically execute these operations. No marketing launch is authorized by this release; enforceable suppression and affirmative consent remain required for future marketing. Applicable jurisdictions, legal sufficiency, processor contracts and full retention/consent inventories remain business/legal obligations. Engineering does not certify freedom from lawsuits.

## Primary guidance consulted

- [FTC CAN-SPAM business guide](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business): opt-out mechanism and actual honoring of requests; transaction/relationship classification depends on message purpose.
- [FTC consumer-review rule Q&A](https://www.ftc.gov/business-guidance/resources/consumer-reviews-testimonials-rule-questions-answers): honest testimonials and review practices.
- [ICO cookies overview](https://ico.org.uk/for-the-public/online/cookies): optional vs strictly necessary storage. Applicability depends on audience/jurisdiction.
- [W3C contrast minimum](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum): 4.5:1 normal text and 3:1 large text thresholds.
- [Google GA4 page views](https://developers.google.com/analytics/devguides/collection/ga4/views): `send_page_view:false` does not disable enhanced history events; informed removing SDK rather than relying on React effects.
- Font licensing/provenance: bundled per-family upstream OFL text and `frontend/public/fonts/manifest.json`.
