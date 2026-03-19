import { Link } from 'react-router-dom'
import BrandLogo from '../../components/brand/BrandLogo'

const BRAND_NAME = 'Diesel Bridge Network'
const CONTACT_EMAIL = 'support@dieselbridge.com'
const EFFECTIVE_DATE = 'March 19, 2026'

export default function PrivacyPolicyPage() {
  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(to top left, #162338 0%, #0f172a 50%, #111827 100%)' }}>
      <header className="sticky top-0 z-50 border-b border-gray-800 bg-gray-900/95 backdrop-blur-sm">
        <nav className="mx-auto flex h-16 max-w-4xl items-center justify-between px-4 sm:px-6">
          <Link to="/" className="flex items-center">
            <BrandLogo alt={BRAND_NAME} variant="landing" className="h-7 sm:h-8 w-auto" />
          </Link>
          <Link
            to="/login"
            className="rounded-md px-3 py-2 text-sm text-gray-300 transition-colors hover:text-white"
          >
            Sign in
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-14 sm:px-6">
        <h1 className="mb-2 text-3xl font-bold text-white sm:text-4xl">Privacy Policy</h1>
        <p className="mb-10 text-sm text-gray-400">Effective date: {EFFECTIVE_DATE}</p>

        <div className="space-y-10 text-gray-300 leading-7">

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">1. Overview</h2>
            <p>
              {BRAND_NAME} ("DieselBridge", "we", "us", or "our") operates a shop management platform that enables
              auto and truck repair shops to manage repair orders, communicate with customers, process payments, and
              coordinate service operations. This Privacy Policy explains how we collect, use, and protect information
              when you use our platform, whether as a shop operator, staff member, or end customer.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">2. Information We Collect</h2>
            <h3 className="mb-2 font-semibold text-gray-100">From shop operators and staff:</h3>
            <ul className="mb-4 list-disc pl-6 space-y-1">
              <li>Name, email address, and account credentials</li>
              <li>Business name, address, phone number, and website</li>
              <li>Payment and billing information (processed via Stripe)</li>
              <li>Usage data and activity logs within the platform</li>
            </ul>
            <h3 className="mb-2 font-semibold text-gray-100">From end customers (vehicle owners):</h3>
            <ul className="mb-4 list-disc pl-6 space-y-1">
              <li>Name, phone number, and email address</li>
              <li>Vehicle information (make, model, year, VIN, license plate)</li>
              <li>Repair history, service records, and invoice data</li>
              <li>SMS communication history</li>
            </ul>
            <h3 className="mb-2 font-semibold text-gray-100">Automatically collected:</h3>
            <ul className="list-disc pl-6 space-y-1">
              <li>IP address, browser type, and device information</li>
              <li>Pages visited and actions taken within the platform</li>
              <li>Session identifiers and authentication tokens</li>
            </ul>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">3. SMS Messaging</h2>
            <p className="mb-3">
              Our platform enables repair shops to send SMS notifications to their customers, including appointment
              reminders, repair order status updates, invoice notifications, and payment links. These messages are
              sent on behalf of the repair shop using our platform infrastructure.
            </p>
            <p className="mb-3">
              <strong className="text-white">Opt-in:</strong> Customers provide their phone number at the point of
              service or through the customer portal and consent to receive SMS updates before messages are sent.
            </p>
            <p className="mb-3">
              <strong className="text-white">Opt-out:</strong> Customers can opt out at any time by replying{' '}
              <strong className="text-white">STOP</strong> to any message. Once opted out, no further SMS messages
              will be sent until the customer re-subscribes by replying <strong className="text-white">START</strong>.
            </p>
            <p>
              <strong className="text-white">Help:</strong> Customers can reply <strong className="text-white">HELP</strong>{' '}
              at any time to receive support contact information. Message and data rates may apply.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">4. How We Use Your Information</h2>
            <ul className="list-disc pl-6 space-y-1">
              <li>To provide, operate, and improve the platform</li>
              <li>To send SMS notifications and service updates on behalf of repair shops</li>
              <li>To process payments and manage billing</li>
              <li>To authenticate users and maintain account security</li>
              <li>To respond to support requests and inquiries</li>
              <li>To comply with legal obligations and enforce our Terms of Service</li>
            </ul>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">5. Third-Party Services</h2>
            <p className="mb-3">We use the following third-party services to operate the platform:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong className="text-white">Twilio</strong> — for SMS delivery and phone number management.
                Messages sent through Twilio are subject to{' '}
                <a href="https://www.twilio.com/en-us/legal/privacy" target="_blank" rel="noopener noreferrer" className="text-amber-400 hover:text-amber-300 underline">
                  Twilio's Privacy Policy
                </a>.
              </li>
              <li>
                <strong className="text-white">Stripe</strong> — for payment processing. Payment data is handled
                directly by Stripe and subject to{' '}
                <a href="https://stripe.com/privacy" target="_blank" rel="noopener noreferrer" className="text-amber-400 hover:text-amber-300 underline">
                  Stripe's Privacy Policy
                </a>.
                We do not store full card numbers on our servers.
              </li>
              <li>
                <strong className="text-white">Cloudinary</strong> — for image and media storage (e.g., shop logos).
              </li>
            </ul>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">6. Data Sharing</h2>
            <p>
              We do not sell your personal information. We share data only as necessary to operate the platform
              (with the third-party services listed above), when required by law, or to protect the rights and
              safety of our users and the public.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">7. Data Retention</h2>
            <p>
              We retain account and service data for as long as your account is active or as needed to provide
              services. Customer records and repair history are retained per the shop operator's account lifecycle.
              You may request deletion of your data by contacting us at{' '}
              <a href={`mailto:${CONTACT_EMAIL}`} className="text-amber-400 hover:text-amber-300 underline">{CONTACT_EMAIL}</a>.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">8. Security</h2>
            <p>
              We implement industry-standard security measures including encrypted connections (HTTPS), hashed
              passwords, token-based authentication, and rate limiting. No system is completely secure; we encourage
              users to use strong passwords and report any suspected security issues promptly.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">9. Your Rights</h2>
            <p className="mb-3">Depending on your location, you may have the right to:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Access the personal information we hold about you</li>
              <li>Request correction of inaccurate data</li>
              <li>Request deletion of your data</li>
              <li>Opt out of SMS communications at any time by replying STOP</li>
            </ul>
            <p className="mt-3">
              To exercise these rights, contact us at{' '}
              <a href={`mailto:${CONTACT_EMAIL}`} className="text-amber-400 hover:text-amber-300 underline">{CONTACT_EMAIL}</a>.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">10. Changes to This Policy</h2>
            <p>
              We may update this Privacy Policy from time to time. Changes will be posted on this page with an
              updated effective date. Continued use of the platform after changes constitutes acceptance of the
              revised policy.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">11. Contact</h2>
            <p>
              If you have questions about this Privacy Policy, please contact us at{' '}
              <a href={`mailto:${CONTACT_EMAIL}`} className="text-amber-400 hover:text-amber-300 underline">{CONTACT_EMAIL}</a>.
            </p>
          </section>

        </div>
      </main>

      <footer className="border-t border-gray-800 bg-gray-900 px-4 py-8 sm:px-6">
        <div className="mx-auto flex max-w-4xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-gray-400">&copy; {new Date().getFullYear()} {BRAND_NAME}. All rights reserved.</p>
          <div className="flex items-center gap-4 text-sm text-gray-400">
            <Link to="/privacy" className="hover:text-white">Privacy Policy</Link>
            <Link to="/terms" className="hover:text-white">Terms of Service</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
