import { Link } from 'react-router-dom'
import BusinessContact from './BusinessContact'
import { BUSINESS } from './business'
import './PublicPolicyPage.css'

type PolicyKind = 'cookies' | 'refunds' | 'deletion'
const titles = { cookies: 'Cookie Policy', refunds: 'Refund & Cancellation Policy', deletion: 'Request Data Deletion' }

export function PolicyLinks() {
  return <nav className="policy-links" aria-label="Policies">
    <Link to="/privacy">Privacy Policy</Link><Link to="/terms">Terms of Service</Link>
    <Link to="/refunds">Refund Policy</Link><Link to="/cookies">Cookie Policy</Link>
    <Link to="/data-deletion">Data deletion request</Link>
  </nav>
}

export default function PublicPolicyPage({ kind }: { kind: PolicyKind }) {
  const supportEmail = BUSINESS.email
  const deletionHref = `mailto:${supportEmail}?subject=${encodeURIComponent('Personal data deletion request')}&body=${encodeURIComponent('Please help me request deletion of my personal data.\n\nAccount email or shop name (if applicable):\n\nPlease explain any identity verification and records that must be retained.\n\nDo not include passwords, payment details, or identity documents in this message.')}`
  return <div className="public-policy">
    <a className="policy-skip" href="#policy-content">Skip to policy</a>
    <header><Link to="/">DieselBridge</Link><Link to="/login">Sign in</Link></header>
    <main id="policy-content" tabIndex={-1}>
      <h1>{titles[kind]}</h1>
      {kind === 'cookies' && <>
        <p>DieselBridge uses cookies and similar browser storage for the purposes described below.</p>
        <h2>Necessary storage</h2><p>Sign-in cookies protect your session. Local storage remembers appearance settings and your cookie choice. These support the service you request and are separate from optional analytics. Removing sign-in cookies may sign you out.</p>
        <h2>Optional analytics</h2><p>Google Analytics and advertising trackers are disabled. Earlier versions of the site may have set identifiers such as <code>_ga</code> and <code>_ga_*</code>, which we remove when you visit. Our necessary-only cookie preference lasts up to 180 days. Your browser may delete storage sooner. We do not send analytics page views, query strings, account records, or token access links to Google Analytics.</p>
        <h2>Change your choice</h2><p>Use Cookie settings at the bottom of any page to review necessary storage and keep optional cookies off. Optional analytics stays disabled regardless of browser signals or previously stored consent. We remove analytics cookies accessible to this site; this does not erase information already held by Google. If optional tracking is added in future, it will require a separate opt-in choice before it loads.</p>
        <h2>Feature providers</h2><p>Payment flows use Stripe for payment processing and fraud prevention. Map features contact Mapbox when used. Those providers may use storage or receive device and network information to deliver their features. Rejecting optional analytics does not disable a payment or map feature you request. See our <Link to="/privacy">Privacy Policy</Link>.</p>
      </>}
      {kind === 'refunds' && <>
        <h2>Software subscriptions</h2><p>DieselBridge subscriptions are billed month-to-month and renew monthly until cancelled. Subscription payments are non-refundable, except where applicable law requires a refund. Cancellation stops future monthly renewals; it does not refund the current billing period. You retain access through the end of the paid subscription period.</p>
        <p>To cancel before your next renewal, report an incorrect charge, or request a refund required by law, email <a href={`mailto:${supportEmail}?subject=Billing%20or%20cancellation%20request`}>{supportEmail}</a>. Include your shop name and the charge date or invoice reference. Do not send full card numbers or passwords. A request is not confirmation of cancellation or refund; ask support to confirm the outcome and effective date.</p>
        <h2>Repair-shop payments</h2><p>For repairs, parts, deposits, and other purchases from a repair shop, contact the shop named on your estimate or invoice. That shop supplies the service and handles its cancellation and refund decisions, subject to applicable law. DieselBridge support can help identify the relevant shop.</p>
        <h2>Prices and fees</h2><p>Review the itemized estimate or invoice and the final payment amount before authorizing payment. Ask the billing business to explain any tax, surcharge, processing fee, or other charge you do not recognize. You may decline to authorize a payment while a charge is unresolved.</p>
      </>}
      {kind === 'deletion' && <>
        <p>You can ask for access, correction, or deletion of your personal information without creating an account.</p>
        <h2>Send a request</h2><p><a className="policy-action" href={deletionHref}>Email a data deletion request</a></p><p>If an email app does not open, email <a href={`mailto:${supportEmail}`}>{supportEmail}</a> with the subject “Personal data deletion request”. This link prepares an email; it does not submit a request until you send it.</p>
        <p>Provide only the email address associated with your account and, if relevant, the shop name. Do not include passwords, bank or card details, government ID numbers, or copies of identity documents. We may need to verify your identity before releasing or deleting data.</p>
        <h2>What happens next</h2><p>Support will review your request and explain its outcome, any additional verification, and any records that must be retained for legal, security, tax, dispute, or accounting purposes. Deletion is not automatic. If a repair shop controls the records, contact that shop; support can help route the request.</p>
        <p>Withdrawing cookie consent and deleting an account are separate actions. Use Cookie settings to stop optional analytics immediately.</p>
      </>}
      <section><h2>Business contact</h2><BusinessContact /></section>
    </main>
    <footer><PolicyLinks /></footer>
  </div>
}
