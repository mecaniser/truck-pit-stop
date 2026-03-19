import { Link } from 'react-router-dom'
import BrandLogo from '../../components/brand/BrandLogo'

const BRAND_NAME = 'Diesel Bridge Network'
const CONTACT_EMAIL = 'support@dieselbridge.com'
const EFFECTIVE_DATE = 'March 19, 2026'

export default function TermsOfServicePage() {
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
        <h1 className="mb-2 text-3xl font-bold text-white sm:text-4xl">Terms of Service</h1>
        <p className="mb-10 text-sm text-gray-400">Effective date: {EFFECTIVE_DATE}</p>

        <div className="space-y-10 text-gray-300 leading-7">

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">1. Acceptance of Terms</h2>
            <p>
              By accessing or using the {BRAND_NAME} platform ("DieselBridge", "the Service"), you agree to be
              bound by these Terms of Service. If you do not agree, do not use the Service. These terms apply to
              all users including shop operators, staff members, and end customers.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">2. Description of Service</h2>
            <p>
              DieselBridge is a shop management platform that enables auto and truck repair shops to manage repair
              orders, communicate with customers via SMS, process payments, generate invoices and quotes, and
              coordinate service operations. The platform is provided as a software-as-a-service (SaaS) product.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">3. Accounts and Access</h2>
            <ul className="list-disc pl-6 space-y-2">
              <li>You are responsible for maintaining the confidentiality of your login credentials.</li>
              <li>You must provide accurate and complete information when creating an account.</li>
              <li>You are responsible for all activity that occurs under your account.</li>
              <li>
                You must notify us immediately at{' '}
                <a href={`mailto:${CONTACT_EMAIL}`} className="text-amber-400 hover:text-amber-300 underline">{CONTACT_EMAIL}</a>{' '}
                if you suspect unauthorized access to your account.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">4. SMS Communications</h2>
            <p className="mb-3">
              By providing a phone number through the platform — whether as a shop operator or as an end customer
              of a repair shop — you consent to receive SMS messages related to your service, including appointment
              reminders, repair status updates, invoice notifications, and payment links.
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong className="text-white">Opt-out:</strong> Reply <strong className="text-white">STOP</strong> to
                any SMS message to unsubscribe. You will receive a confirmation and no further messages will be sent.
              </li>
              <li>
                <strong className="text-white">Opt-in:</strong> Reply <strong className="text-white">START</strong> to
                resubscribe after opting out.
              </li>
              <li>
                <strong className="text-white">Help:</strong> Reply <strong className="text-white">HELP</strong> for
                support contact information.
              </li>
              <li>Message and data rates may apply depending on your carrier plan.</li>
            </ul>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">5. Payments</h2>
            <p className="mb-3">
              Payment processing is handled by Stripe. By using payment features within the platform, you agree to
              Stripe's Terms of Service. DieselBridge does not store full payment card details on its servers.
            </p>
            <p>
              Shop operators are responsible for ensuring accurate pricing, tax information, and customer billing
              within their account. DieselBridge is not liable for billing disputes between shops and their customers.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">6. Acceptable Use</h2>
            <p className="mb-3">You agree not to:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Use the platform for any unlawful purpose or in violation of any applicable regulations</li>
              <li>Send unsolicited or spam SMS messages through the platform</li>
              <li>Attempt to gain unauthorized access to any part of the Service or its infrastructure</li>
              <li>Interfere with or disrupt the integrity or performance of the Service</li>
              <li>Harvest or collect user data without authorization</li>
              <li>Impersonate another person or entity</li>
            </ul>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">7. Data and Privacy</h2>
            <p>
              Your use of the Service is also governed by our{' '}
              <Link to="/privacy" className="text-amber-400 hover:text-amber-300 underline">Privacy Policy</Link>,
              which is incorporated into these Terms by reference. By using the Service, you consent to the
              collection and use of information as described therein.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">8. Intellectual Property</h2>
            <p>
              All content, trademarks, logos, and software comprising the DieselBridge platform are the property
              of {BRAND_NAME} or its licensors. You may not reproduce, distribute, or create derivative works
              without our express written consent.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">9. Termination</h2>
            <p>
              We reserve the right to suspend or terminate your access to the Service at any time for violation of
              these Terms, fraudulent activity, or any conduct we determine to be harmful to users or the platform.
              You may terminate your account at any time by contacting us at{' '}
              <a href={`mailto:${CONTACT_EMAIL}`} className="text-amber-400 hover:text-amber-300 underline">{CONTACT_EMAIL}</a>.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">10. Disclaimer of Warranties</h2>
            <p>
              The Service is provided "as is" and "as available" without warranties of any kind, either express or
              implied, including but not limited to warranties of merchantability, fitness for a particular purpose,
              or non-infringement. We do not warrant that the Service will be uninterrupted, error-free, or free
              of viruses or other harmful components.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">11. Limitation of Liability</h2>
            <p>
              To the fullest extent permitted by applicable law, {BRAND_NAME} shall not be liable for any indirect,
              incidental, special, consequential, or punitive damages arising out of or related to your use of the
              Service, even if advised of the possibility of such damages. Our total liability shall not exceed the
              amount paid by you for the Service in the twelve months preceding the claim.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">12. Changes to Terms</h2>
            <p>
              We may update these Terms at any time. Changes will be posted on this page with an updated effective
              date. Continued use of the Service after changes constitutes acceptance of the revised Terms.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">13. Governing Law</h2>
            <p>
              These Terms are governed by the laws of the United States. Any disputes shall be resolved in the
              applicable courts of competent jurisdiction.
            </p>
          </section>

          <section>
            <h2 className="mb-3 text-xl font-semibold text-white">14. Contact</h2>
            <p>
              For questions about these Terms, contact us at{' '}
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
