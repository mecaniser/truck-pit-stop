import { Link } from 'react-router-dom'
import { 
  Truck, 
  Clock, 
  Users, 
  BarChart3, 
  MessageSquare, 
  Shield,
  CheckCircle,
  ArrowRight,
  Wrench
} from 'lucide-react'
import { useTheme } from '../../contexts/ThemeContext'

const BRAND = {
  platformName: 'Diesel Bridge Network',
  networkName: 'Diesel Bridge',
  heroLine: 'Dispatch smarter. Repair faster. Drive on.',
  supportLine: 'Connect drivers to qualified repair, fast.',
  networkLine: 'Nationwide garages, one operating network.',
}

export default function LandingPage() {
  const { accentColors } = useTheme()
  const accent400 = accentColors[400]
  const accent500 = accentColors[500]
  const accent600 = accentColors[600]

  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(to top left, #162338 0%, #0f172a 50%, #111827 100%)' }}>
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-gray-900/95 backdrop-blur-sm border-b border-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <div className="flex items-center gap-2">
              <div 
                className="w-10 h-10 rounded-lg flex items-center justify-center"
                style={{ background: `linear-gradient(135deg, ${accent500} 0%, ${accent600} 100%)` }}
              >
                <Truck className="w-6 h-6 text-white" />
              </div>
              <span className="text-xl font-bold text-white">
                {BRAND.platformName}
              </span>
            </div>

            {/* Nav Links */}
            <div className="hidden md:flex items-center gap-8">
              <a href="#audiences" className="text-gray-400 hover:text-[var(--accent-400)] transition-colors">
                Who It's For
              </a>
              <a href="#features" className="text-gray-400 hover:text-[var(--accent-400)] transition-colors">
                Platform
              </a>
              <a href="#pricing" className="text-gray-400 hover:text-[var(--accent-400)] transition-colors">
                Access
              </a>
            </div>

            {/* CTA Buttons */}
            <div className="flex items-center gap-3">
              <Link
                to="/login"
                className="px-4 py-2 text-sm font-medium rounded-lg transition-colors text-gray-300 hover:text-[var(--accent-400)]"
              >
                Sign In
              </Link>
              <Link
                to="/enroll"
                className="px-4 py-2 text-sm font-medium text-white rounded-lg transition-all hover:opacity-95 hover:shadow-[0_0_24px_var(--accent-500)]"
                style={{ backgroundColor: accent500 }}
              >
                Get Started
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-20 px-4">
        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <p className="inline-flex items-center rounded-full border border-white/20 bg-white/10 px-4 py-1 text-sm font-semibold text-gray-200 mb-6">
                {BRAND.networkName} Network
              </p>
              <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-white leading-tight mb-6">
                {BRAND.heroLine}
              </h1>
              <p className="text-lg text-gray-300 mb-8 max-w-xl">
                {BRAND.supportLine} {BRAND.networkLine} Manage your garage, team,
                and customers in one workflow while giving dispatch and drivers a
                faster path to qualified repair.
              </p>
              <div className="flex flex-col sm:flex-row gap-4">
                <Link
                  to="/enroll"
                  className="inline-flex items-center justify-center gap-2 px-6 py-3 text-lg font-semibold rounded-lg transition-all hover:opacity-95 hover:shadow-[0_0_24px_var(--accent-500)]"
                  style={{ backgroundColor: accent500 }}
                >
                  Join as a Garage
                  <ArrowRight className="w-5 h-5" />
                </Link>
                <a
                  href="#audiences"
                  className="inline-flex items-center justify-center gap-2 px-6 py-3 text-lg font-semibold text-white rounded-lg border-2 border-white/30 hover:bg-white/10 transition-colors"
                >
                  See Who It's For
                </a>
              </div>
            </div>

            {/* Hero Visual */}
            <div className="hidden lg:block">
              <div className="relative">
                <div 
                  className="absolute inset-0 rounded-2xl opacity-20"
                  style={{ backgroundColor: accent500 }}
                />
                <div className="relative bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20">
                  <div className="space-y-4">
                    {/* Mock Dashboard Preview */}
                    <div className="flex items-center gap-3 p-3 bg-white/10 rounded-lg">
                      <div className="w-10 h-10 rounded-full bg-green-500/20 flex items-center justify-center">
                        <CheckCircle className="w-5 h-5 text-green-400" />
                      </div>
                      <div>
                        <p className="text-white font-medium">New repair order received</p>
                        <p className="text-gray-400 text-sm">Peterbilt 579 - Brake inspection</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 p-3 bg-white/10 rounded-lg">
                      <div className="w-10 h-10 rounded-full bg-blue-500/20 flex items-center justify-center">
                        <Wrench className="w-5 h-5 text-blue-400" />
                      </div>
                      <div>
                        <p className="text-white font-medium">Job in progress</p>
                        <p className="text-gray-400 text-sm">Freightliner Cascadia - Engine repair</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 p-3 bg-white/10 rounded-lg">
                      <div 
                        className="w-10 h-10 rounded-full flex items-center justify-center"
                        style={{ backgroundColor: `${accent500}33` }}
                      >
                        <MessageSquare className="w-5 h-5" style={{ color: accent400 }} />
                      </div>
                      <div>
                        <p className="text-white font-medium">Quote approved via SMS</p>
                        <p className="text-gray-400 text-sm">Customer approved repair quote</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Audience Section */}
      <section id="audiences" className="py-12 px-4 bg-gray-900/50 border-y border-gray-800">
        <div className="max-w-7xl mx-auto px-4">
          <div className="text-center mb-10">
            <h2 className="text-3xl md:text-4xl font-bold mb-3 text-white">
              Built for Both Sides of the Breakdown
            </h2>
            <p className="text-gray-400 max-w-3xl mx-auto">
              One side runs the garage. The other side needs fast routing when trucks
              go down. Diesel Bridge Network connects both.
            </p>
          </div>
          <div className="grid md:grid-cols-2 gap-6">
            <div className="rounded-2xl border border-gray-700 bg-gray-900/45 p-6">
              <h3 className="text-xl font-semibold text-white mb-4">For Garage Owners</h3>
              <ul className="space-y-3 text-gray-300">
                <li className="flex items-start gap-2">
                  <CheckCircle className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: accent400 }} />
                  <span>Run intake, repair orders, time tracking, and invoicing in one place.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: accent400 }} />
                  <span>Use two-way texting and quote approvals to reduce phone tag.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: accent400 }} />
                  <span>Give fleet customers clear status updates through a shared portal.</span>
                </li>
              </ul>
              <Link
                to="/enroll"
                className="mt-6 inline-flex items-center justify-center gap-2 rounded-lg px-5 py-2.5 font-semibold text-white transition-all hover:opacity-95 hover:shadow-[0_0_24px_var(--accent-500)]"
                style={{ backgroundColor: accent500 }}
              >
                Join as a Garage
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
            <div className="rounded-2xl border border-gray-700 bg-gray-900/45 p-6">
              <h3 className="text-xl font-semibold text-white mb-4">For Drivers and Dispatchers</h3>
              <ul className="space-y-3 text-gray-300">
                <li className="flex items-start gap-2">
                  <CheckCircle className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: accent400 }} />
                  <span>Find nearby qualified garages based on service needs and location.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: accent400 }} />
                  <span>Send repair context early so shops can diagnose faster on arrival.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: accent400 }} />
                  <span>Track progress in one thread until the truck is back on route.</span>
                </li>
              </ul>
              <a
                href="#features"
                className="mt-6 inline-flex items-center justify-center gap-2 rounded-lg border border-white/30 px-5 py-2.5 font-semibold text-white transition-colors hover:bg-white/10"
              >
                Explore the Platform
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-20 px-4">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4 text-white">
              Simple Tools That Keep Repairs Moving
            </h2>
            <p className="text-gray-400 max-w-2xl mx-auto">
              Clear workflows for your team, clear updates for your customers, and
              clearer routing decisions for dispatch.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {/* Feature 1 */}
            <div className="p-6 rounded-xl bg-gray-800/50 border border-gray-700 hover:border-gray-600 hover:bg-gray-800/70 transition-all">
              <div 
                className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
                style={{ backgroundColor: `${accent500}20` }}
              >
                <Clock className="w-6 h-6" style={{ color: accent400 }} />
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Live Job and Time Tracking
              </h3>
              <p className="text-gray-400">
                Keep every order visible by status, mechanic, and labor time so your
                team knows what to do next.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="p-6 rounded-xl bg-gray-800/50 border border-gray-700 hover:border-gray-600 hover:bg-gray-800/70 transition-all">
              <div 
                className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
                style={{ backgroundColor: `${accent500}20` }}
              >
                <MessageSquare className="w-6 h-6" style={{ color: accent400 }} />
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Two-Way Texting and Quote Approval
              </h3>
              <p className="text-gray-400">
                Send estimates by text, capture approvals, and answer follow-up
                questions without leaving the workflow.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="p-6 rounded-xl bg-gray-800/50 border border-gray-700 hover:border-gray-600 hover:bg-gray-800/70 transition-all">
              <div 
                className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
                style={{ backgroundColor: `${accent500}20` }}
              >
                <Users className="w-6 h-6" style={{ color: accent400 }} />
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Customer and Fleet Portal
              </h3>
              <p className="text-gray-400">
                Give customers and fleet managers a single place to view repair
                history, current status, and invoices.
              </p>
            </div>

            {/* Feature 4 */}
            <div className="p-6 rounded-xl bg-gray-800/50 border border-gray-700 hover:border-gray-600 hover:bg-gray-800/70 transition-all">
              <div 
                className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
                style={{ backgroundColor: `${accent500}20` }}
              >
                <Wrench className="w-6 h-6" style={{ color: accent400 }} />
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Mechanic Productivity Board
              </h3>
              <p className="text-gray-400">
                Mechanics get clear assignments, timer controls, and status updates
                tied directly to each order.
              </p>
            </div>

            {/* Feature 5 */}
            <div className="p-6 rounded-xl bg-gray-800/50 border border-gray-700 hover:border-gray-600 hover:bg-gray-800/70 transition-all">
              <div 
                className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
                style={{ backgroundColor: `${accent500}20` }}
              >
                <BarChart3 className="w-6 h-6" style={{ color: accent400 }} />
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Dispatch and Network Insights
              </h3>
              <p className="text-gray-400">
                Route jobs faster by seeing service capability and turnaround patterns
                across network garages.
              </p>
            </div>

            {/* Feature 6 */}
            <div className="p-6 rounded-xl bg-gray-800/50 border border-gray-700 hover:border-gray-600 hover:bg-gray-800/70 transition-all">
              <div 
                className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
                style={{ backgroundColor: `${accent500}20` }}
              >
                <Shield className="w-6 h-6" style={{ color: accent400 }} />
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Notifications and Payments
              </h3>
              <p className="text-gray-400">
                Automate customer notifications and keep billing records in the same
                system as your repair workflow.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="py-20 px-4 bg-gray-900/50">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4 text-white">
              How the Network Flow Works
            </h2>
            <p className="text-gray-400 max-w-2xl mx-auto">
              Keep setup simple while connecting garage operations and roadside repair
              requests in one flow.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {/* Step 1 */}
            <div className="text-center">
              <div 
                className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6 text-2xl font-bold"
                style={{ backgroundColor: accent500, color: '#0b1220' }}
              >
                1
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Garages Publish Capabilities
              </h3>
              <p className="text-gray-400">
                Enroll your shop, define service coverage, and set who handles each
                type of repair.
              </p>
            </div>

            {/* Step 2 */}
            <div className="text-center">
              <div 
                className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6 text-2xl font-bold"
                style={{ backgroundColor: accent500, color: '#0b1220' }}
              >
                2
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Drivers or Dispatch Request Service
              </h3>
              <p className="text-gray-400">
                Share truck details and issue context so the nearest qualified garage
                can respond faster.
              </p>
            </div>

            {/* Step 3 */}
            <div className="text-center">
              <div 
                className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6 text-2xl font-bold"
                style={{ backgroundColor: accent500, color: '#0b1220' }}
              >
                3
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Everyone Tracks the Same Job Thread
              </h3>
              <p className="text-gray-400">
                Coordinate diagnosis, approvals, and updates in one place until the
                truck is back on route.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="py-20 px-4">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4 text-white">
              Founding Garage Access
            </h2>
            <p className="text-gray-400 max-w-2xl mx-auto">
              Keep onboarding simple while the network expands market by market.
            </p>
          </div>

          <div className="max-w-lg mx-auto">
            <div 
              className="rounded-2xl p-8 text-center bg-gray-800/50 border-2"
              style={{ borderColor: `${accent500}66` }}
            >
              <div 
                className="inline-block px-4 py-1 rounded-full text-sm font-medium mb-4"
                style={{ backgroundColor: `${accent500}20`, color: accent400 }}
              >
                Early Access
              </div>
              <h3 className="text-2xl font-bold mb-2 text-white">
                Garage Enrollment Program
              </h3>
              <p className="text-gray-300 mb-6">
                Built for early partners that want to shape the workflow and grow with
                Diesel Bridge Network.
              </p>
              <ul className="text-left space-y-3 mb-8">
                <li className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: accent400 }} />
                  <span className="text-gray-300">Repair orders, labor tracking, and workflow controls</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: accent400 }} />
                  <span className="text-gray-300">Two-way texting and quote approval links</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: accent400 }} />
                  <span className="text-gray-300">Customer and fleet status visibility</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: accent400 }} />
                  <span className="text-gray-300">Invoicing and payment collection tools</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: accent400 }} />
                  <span className="text-gray-300">Direct onboarding support from the founding team</span>
                </li>
              </ul>
              <Link
                to="/enroll"
                className="block w-full py-3 text-lg font-semibold text-white rounded-lg transition-all hover:opacity-95 hover:shadow-[0_0_24px_var(--accent-500)]"
                style={{ backgroundColor: accent500 }}
              >
                Apply for Garage Access
              </Link>
              <p className="text-sm text-gray-500 mt-4">
                Rolling out by market and service coverage
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-4 bg-gray-900/70 border-t border-gray-800">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-6">
            Keep Your Shop Ready for the Next Breakdown
          </h2>
          <p className="text-gray-400 text-lg mb-8 max-w-2xl mx-auto">
            {BRAND.networkLine} Bring your shop online, reduce downtime, and deliver a
            faster, more transparent repair experience for fleets and drivers.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              to="/enroll"
              className="inline-flex items-center justify-center gap-2 px-8 py-4 text-lg font-semibold rounded-lg transition-all hover:opacity-95 hover:shadow-[0_0_24px_var(--accent-500)]"
              style={{ backgroundColor: accent500 }}
            >
              Join as a Garage
              <ArrowRight className="w-5 h-5" />
            </Link>
            <Link
              to="/login"
              className="inline-flex items-center justify-center gap-2 px-8 py-4 text-lg font-semibold text-white rounded-lg border-2 border-gray-600 hover:bg-gray-800 transition-colors"
            >
              Sign In to Your Account
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-4 bg-gray-900">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-2">
              <div 
                className="w-8 h-8 rounded-lg flex items-center justify-center"
                style={{ backgroundColor: accent500 }}
              >
                <Truck className="w-5 h-5 text-white" />
              </div>
              <span className="text-white font-semibold">{BRAND.platformName}</span>
            </div>
            <div className="flex items-center gap-6 text-gray-400 text-sm">
              <a href="#" className="hover:text-[var(--accent-400)] transition-colors">Privacy Policy</a>
              <a href="#" className="hover:text-[var(--accent-400)] transition-colors">Terms of Service</a>
              <a href="#" className="hover:text-[var(--accent-400)] transition-colors">Contact</a>
            </div>
            <p className="text-gray-500 text-sm">
              © {new Date().getFullYear()} {BRAND.platformName}. All rights reserved.
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}
