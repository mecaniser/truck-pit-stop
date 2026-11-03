# DB-154 — Privacy, public policies and accessibility

2026-11-03. Accountable owner: Frontend & UX. High-risk privacy lane. Branch: `codex/privacy-safety`. Base: `24790dd3` (origin/main at intake). Status: implementation reviewed; [draft PR761](https://github.com/mecaniser/truck-pit-stop/pull/761) open at implementation commit `0f3ea542`; unmerged/undeployed, protected CI/release gates pending. This is engineering evidence, not legal advice or a compliance certification.

## Verified operator decisions

The operator supplied: Elis Tech LLC, doing business as Diesel Bridge Network; 1002 Yearden Ln, Monroe, NC 28110, United States; privacy/contact email elis@elisprotech.com. Subscriptions are month-to-month, non-refundable except where applicable law requires a refund; cancellation stops future monthly renewals. The operator also confirmed ownership or permission for current site logos/images. No independent chain-of-title search or legal review was performed. A North Carolina mailing address does not establish the entity's formation jurisdiction or select governing law.

## Implementation and audit coverage

| Requested safeguard | Result and limits |
| --- | --- |
| Privacy policy | Existing notice updated with operator identity/contact, feature-provider disclosures, disabled analytics, shop-controlled records and deletion-request link. Blanket “industry-standard” security claim removed. |
| Terms | Existing terms corrected: providing a phone number and accepting terms do not grant SMS/marketing consent. Optional marketing must be separate and not a purchasing condition. Added refund/fee references. |
| Refund policy | `/refunds` states approved monthly/non-refundable rule with statutory exception and email cancellation route. Repair-shop purchases remain the supplying shop's responsibility. Policy does not itself automate billing cancellation. |
| Cookie policy/banner | `/cookies` plus global nonmodal, keyboard-accessible necessary-only notice and persistent settings action. No fabricated Accept-all choice for nonexistent optional collection. Preference lasts up to 180 days; blocked/malformed/old acceptance storage does not enable tracking. Callback UI remains absent. |
| Data minimization | Removed EIN/business-license inputs and omitted their values from enrollment payloads. Existing historical records were not deleted. Legacy API still accepts those optional fields for older clients; this is not a system-wide field/retention reduction. |
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

### Dependency audit — unresolved findings

`npm audit --omit=dev --json` against the existing lockfile reports **22 package entries: 2 critical, 16 high, 4 moderate**. These are registry dependency findings, not proof of reachable exploitation. Not changed by this PR.

Direct packages flagged: axios (high), jspdf (critical), react-pdf (high), react-router-dom (high), serve (high), zod (high). Transitive critical entry includes tar under the react-pdf dependency graph. Registry proposes major upgrades for jspdf (4.2.1), react-pdf (11.0.0) and zod (4.6.7); compatible updates exist for other entries. Remediation is tracked as DB-155 and needs a separate focused change covering generated PDFs, PDF previews, schema validation, HTTP behavior, routing and production serving. Do not infer security clearance from this PR's tests. Raw local audit: `/tmp/db154-dependency-audit.json` (not committed).

## Verification

- Focused frontend: 24/24 passing across PrivacyControls, PublicPolicies, LandingPage and mechanic toaster compatibility.
- Backend direct email and provider outbox: 13/13 passing, provider transport mocked; includes footer placement, manual-request wording and outbox bypass regression.
- Production build and shared controls check pass. Changed-source ESLint passes with zero warnings. `git diff --check` passes.
- Axe 4.14.0 on `/`, `/privacy`, `/terms`, `/cookies`, `/refunds`, `/data-deletion`, `/enroll`: zero reported WCAG A/AA violations in final fixture pass. Gradient/overlap contrast and some ARIA checks marked incomplete; manual contrast calculations and independent semantic review supplement, rather than override, those limits.
- Enrollment fixture browser journey reached final review, verified no EIN/license fields and terms link; application was not submitted.
- Browser public route fixture pass: no external origins observed. All five policy routes carry supplied identity. Mobile 375×812 fits without horizontal overflow; cookie actions work with keyboard, retain focus on settings, and have 44px targets. Legal skip link focuses policy main.
- Independent Security initially NO-GO: failed-withdrawal storage case, automatic analytics history leakage, outbox footer bypass. All corrected and independently source-approved GO. Independent QA GO for the bounded public UI; implementing agent did not approve its own gates.
- Independent QA did not certify real billing, actual delivered email, provider configuration, legal sufficiency or the complete authenticated app.

## Local runtime receipt

Local startup skill read and preflight attempted at intake and repeated on the new local day. Isolated worktree initially lacked approved `backend/.env`; no secrets copied, defaults invented, migrations applied or shared services replaced. Later controller dry run rejects the dirty checkout. Existing other stacks preserved.

Vite frontend served `http://127.0.0.1:5173`, PID 21988 during evidence collection, cwd `/Users/sergio_m1_promax/.codex/worktrees/privacy-safety/truck-pit-stop/frontend`; source branch `codex/privacy-safety`, base HEAD `24790dd3e605e960bfaf00e6e2c88c5166ec8a32`. Exact served changed source and rendered features checked. API/proxy target `127.0.0.1:8000` unavailable; public browser tests intercepted API with fictional partner/contact and unauthorized-auth fixtures. **Frontend source/browser verified; full stack blocked/unverified.** No database identity or payment readiness inferred. Receipt expires with source/process/config/date changes.

## Release and operational gates

1. Keep as draft until legal review confirms applicable jurisdictions, statutory privacy rights, processor/retention inventory, SMS consent and monthly cancellation/refund wording. Engineering cannot guarantee freedom from lawsuits.
2. The operator must monitor `elis@elisprotech.com`, verify data-rights requests with minimal information, route shop-controlled records, record retention exceptions and process deletion requests. Do not claim a deletion occurred merely because a mailto opened.
3. Record and honor optional-email opt-outs. No optional marketing campaign should launch until suppression is enforceable and tested. The footer is a manual request channel, not automatic suppression. Mandatory security/transaction notices are separate.
4. Address dependency findings in focused follow-up work; do not label them resolved.
5. Backend-aligned runtime acceptance, protected PR checks, explicit release authorization, merge/deploy and production verification remain outstanding. Do not mark DB-154 Done or treat this audit as a production release.

## Primary guidance consulted

- [FTC CAN-SPAM business guide](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business): opt-out mechanism and actual honoring of requests; transaction/relationship classification depends on message purpose.
- [FTC consumer-review rule Q&A](https://www.ftc.gov/business-guidance/resources/consumer-reviews-testimonials-rule-questions-answers): honest testimonials and review practices.
- [ICO cookies overview](https://ico.org.uk/for-the-public/online/cookies): optional vs strictly necessary storage. Applicability depends on audience/jurisdiction.
- [W3C contrast minimum](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum): 4.5:1 normal text and 3:1 large text thresholds.
- [Google GA4 page views](https://developers.google.com/analytics/devguides/collection/ga4/views): `send_page_view:false` does not disable enhanced history events; informed removing SDK rather than relying on React effects.
- Font licensing/provenance: bundled per-family upstream OFL text and `frontend/public/fonts/manifest.json`.
