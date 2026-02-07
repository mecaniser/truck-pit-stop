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

// Colors: Dark Gold (#B8860B), Dark Blue (#1e3a5f), White
const COLORS = {
  darkGold: '#B8860B',
  darkBlue: '#1e3a5f',
  white: '#ffffff',
}

export default function LandingPage() {
  return (
    <div className="min-h-screen" style={{ background: `linear-gradient(to top left, ${COLORS.darkBlue} 0%, #0f172a 50%, #1a1a2e 100%)` }}>
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-gray-900/95 backdrop-blur-sm border-b border-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <div className="flex items-center gap-2">
              <div 
                className="w-10 h-10 rounded-lg flex items-center justify-center"
                style={{ backgroundColor: COLORS.darkBlue }}
              >
                <Truck className="w-6 h-6 text-white" />
              </div>
              <span className="text-xl font-bold text-white">
                Truck Pit Stop
              </span>
            </div>

            {/* Nav Links */}
            <div className="hidden md:flex items-center gap-8">
              <a href="#features" className="text-gray-400 hover:text-white transition-colors">
                Features
              </a>
              <a href="#how-it-works" className="text-gray-400 hover:text-white transition-colors">
                How It Works
              </a>
              <a href="#pricing" className="text-gray-400 hover:text-white transition-colors">
                Pricing
              </a>
            </div>

            {/* CTA Buttons */}
            <div className="flex items-center gap-3">
              <Link
                to="/login"
                className="px-4 py-2 text-sm font-medium rounded-lg transition-colors text-gray-300 hover:text-white"
              >
                Sign In
              </Link>
              <Link
                to="/enroll"
                className="px-4 py-2 text-sm font-medium text-white rounded-lg transition-all hover:opacity-90"
                style={{ backgroundColor: COLORS.darkGold }}
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
              <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-white leading-tight mb-6">
                Streamline Your{' '}
                <span style={{ color: COLORS.darkGold }}>Truck Repair</span>{' '}
                Operations
              </h1>
              <p className="text-lg text-gray-300 mb-8 max-w-xl">
                The all-in-one platform that connects shop owners, mechanics, and customers 
                for seamless heavy-duty truck repair management.
              </p>
              <div className="flex flex-col sm:flex-row gap-4">
                <Link
                  to="/enroll"
                  className="inline-flex items-center justify-center gap-2 px-6 py-3 text-lg font-semibold rounded-lg transition-all hover:opacity-90"
                  style={{ backgroundColor: COLORS.darkGold, color: COLORS.white }}
                >
                  Register Your Garage
                  <ArrowRight className="w-5 h-5" />
                </Link>
                <a
                  href="#features"
                  className="inline-flex items-center justify-center gap-2 px-6 py-3 text-lg font-semibold text-white rounded-lg border-2 border-white/30 hover:bg-white/10 transition-colors"
                >
                  Learn More
                </a>
              </div>
            </div>

            {/* Hero Visual */}
            <div className="hidden lg:block">
              <div className="relative">
                <div 
                  className="absolute inset-0 rounded-2xl opacity-20"
                  style={{ backgroundColor: COLORS.darkGold }}
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
                        style={{ backgroundColor: `${COLORS.darkGold}33` }}
                      >
                        <MessageSquare className="w-5 h-5" style={{ color: COLORS.darkGold }} />
                      </div>
                      <div>
                        <p className="text-white font-medium">Quote approved via SMS</p>
                        <p className="text-gray-400 text-sm">Customer approved $2,450 quote</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Bar */}
      <section className="py-8 bg-gray-900/50 border-y border-gray-800">
        <div className="max-w-7xl mx-auto px-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            <div className="text-center">
              <p className="text-3xl font-bold" style={{ color: COLORS.darkGold }}>500+</p>
              <p className="text-gray-400">Repair Shops</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold" style={{ color: COLORS.darkGold }}>50K+</p>
              <p className="text-gray-400">Repairs Completed</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold" style={{ color: COLORS.darkGold }}>98%</p>
              <p className="text-gray-400">Customer Satisfaction</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold" style={{ color: COLORS.darkGold }}>24/7</p>
              <p className="text-gray-400">Support Available</p>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-20 px-4">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4 text-white">
              Everything You Need to Run Your Shop
            </h2>
            <p className="text-gray-400 max-w-2xl mx-auto">
              From quote management to payment processing, we've got every aspect of your 
              truck repair business covered.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {/* Feature 1 */}
            <div className="p-6 rounded-xl bg-gray-800/50 border border-gray-700 hover:border-gray-600 hover:bg-gray-800/70 transition-all">
              <div 
                className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
                style={{ backgroundColor: `${COLORS.darkGold}20` }}
              >
                <Clock className="w-6 h-6" style={{ color: COLORS.darkGold }} />
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Real-Time Tracking
              </h3>
              <p className="text-gray-400">
                Track repair progress in real-time. Keep customers informed with automatic 
                status updates via SMS.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="p-6 rounded-xl bg-gray-800/50 border border-gray-700 hover:border-gray-600 hover:bg-gray-800/70 transition-all">
              <div 
                className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
                style={{ backgroundColor: `${COLORS.darkGold}20` }}
              >
                <MessageSquare className="w-6 h-6" style={{ color: COLORS.darkGold }} />
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                SMS Quote Approval
              </h3>
              <p className="text-gray-400">
                Send quotes directly to customers' phones. They can approve or decline 
                with a single tap.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="p-6 rounded-xl bg-gray-800/50 border border-gray-700 hover:border-gray-600 hover:bg-gray-800/70 transition-all">
              <div 
                className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
                style={{ backgroundColor: `${COLORS.darkGold}20` }}
              >
                <Users className="w-6 h-6" style={{ color: COLORS.darkGold }} />
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Customer Portal
              </h3>
              <p className="text-gray-400">
                Give customers their own portal to view repair history, track current 
                jobs, and manage their fleet.
              </p>
            </div>

            {/* Feature 4 */}
            <div className="p-6 rounded-xl bg-gray-800/50 border border-gray-700 hover:border-gray-600 hover:bg-gray-800/70 transition-all">
              <div 
                className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
                style={{ backgroundColor: `${COLORS.darkGold}20` }}
              >
                <Wrench className="w-6 h-6" style={{ color: COLORS.darkGold }} />
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Mechanic Dashboard
              </h3>
              <p className="text-gray-400">
                Mechanics get their own view with assigned jobs, time tracking, and 
                easy status updates.
              </p>
            </div>

            {/* Feature 5 */}
            <div className="p-6 rounded-xl bg-gray-800/50 border border-gray-700 hover:border-gray-600 hover:bg-gray-800/70 transition-all">
              <div 
                className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
                style={{ backgroundColor: `${COLORS.darkGold}20` }}
              >
                <BarChart3 className="w-6 h-6" style={{ color: COLORS.darkGold }} />
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Business Analytics
              </h3>
              <p className="text-gray-400">
                Track revenue, monitor mechanic productivity, and identify trends with 
                powerful reporting tools.
              </p>
            </div>

            {/* Feature 6 */}
            <div className="p-6 rounded-xl bg-gray-800/50 border border-gray-700 hover:border-gray-600 hover:bg-gray-800/70 transition-all">
              <div 
                className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
                style={{ backgroundColor: `${COLORS.darkGold}20` }}
              >
                <Shield className="w-6 h-6" style={{ color: COLORS.darkGold }} />
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Flexible Payments
              </h3>
              <p className="text-gray-400">
                Accept credit cards, Zelle, or cash. Send invoices with automatic 
                payment reminders.
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
              Get Started in Minutes
            </h2>
            <p className="text-gray-400 max-w-2xl mx-auto">
              Simple onboarding process to get your shop up and running quickly.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {/* Step 1 */}
            <div className="text-center">
              <div 
                className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6 text-2xl font-bold"
                style={{ backgroundColor: COLORS.darkGold, color: COLORS.darkBlue }}
              >
                1
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Register Your Garage
              </h3>
              <p className="text-gray-400">
                Fill out a simple form with your business details. We'll review and 
                approve within 1-2 business days.
              </p>
            </div>

            {/* Step 2 */}
            <div className="text-center">
              <div 
                className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6 text-2xl font-bold"
                style={{ backgroundColor: COLORS.darkGold, color: COLORS.darkBlue }}
              >
                2
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Set Up Your Shop
              </h3>
              <p className="text-gray-400">
                Add your team members, configure payment options, and customize your 
                settings.
              </p>
            </div>

            {/* Step 3 */}
            <div className="text-center">
              <div 
                className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6 text-2xl font-bold"
                style={{ backgroundColor: COLORS.darkGold, color: COLORS.darkBlue }}
              >
                3
              </div>
              <h3 className="text-xl font-semibold mb-2 text-white">
                Start Taking Orders
              </h3>
              <p className="text-gray-400">
                Create repair orders, send quotes, and manage your workflow from day one.
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
              Simple, Transparent Pricing
            </h2>
            <p className="text-gray-400 max-w-2xl mx-auto">
              Start free and scale as you grow. No hidden fees.
            </p>
          </div>

          <div className="max-w-lg mx-auto">
            <div 
              className="rounded-2xl p-8 text-center bg-gray-800/50 border-2"
              style={{ borderColor: COLORS.darkGold }}
            >
              <div 
                className="inline-block px-4 py-1 rounded-full text-sm font-medium mb-4"
                style={{ backgroundColor: `${COLORS.darkGold}20`, color: COLORS.darkGold }}
              >
                Limited Time Offer
              </div>
              <h3 className="text-2xl font-bold mb-2 text-white">
                Free During Beta
              </h3>
              <p className="text-4xl font-bold mb-4 text-white">
                $0<span className="text-lg font-normal text-gray-400">/month</span>
              </p>
              <ul className="text-left space-y-3 mb-8">
                <li className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: COLORS.darkGold }} />
                  <span className="text-gray-300">Unlimited repair orders</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: COLORS.darkGold }} />
                  <span className="text-gray-300">SMS notifications included</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: COLORS.darkGold }} />
                  <span className="text-gray-300">Customer portal access</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: COLORS.darkGold }} />
                  <span className="text-gray-300">Payment processing</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: COLORS.darkGold }} />
                  <span className="text-gray-300">Priority support</span>
                </li>
              </ul>
              <Link
                to="/enroll"
                className="block w-full py-3 text-lg font-semibold text-white rounded-lg transition-all hover:opacity-90"
                style={{ backgroundColor: COLORS.darkGold }}
              >
                Get Started Free
              </Link>
              <p className="text-sm text-gray-500 mt-4">
                No credit card required
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-4 bg-gray-900/70 border-t border-gray-800">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-6">
            Ready to Transform Your Shop?
          </h2>
          <p className="text-gray-400 text-lg mb-8 max-w-2xl mx-auto">
            Join hundreds of truck repair shops already using Truck Pit Stop to 
            streamline their operations and delight their customers.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              to="/enroll"
              className="inline-flex items-center justify-center gap-2 px-8 py-4 text-lg font-semibold rounded-lg transition-all hover:opacity-90"
              style={{ backgroundColor: COLORS.darkGold, color: COLORS.white }}
            >
              Register Your Garage
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
                style={{ backgroundColor: COLORS.darkGold }}
              >
                <Truck className="w-5 h-5 text-white" />
              </div>
              <span className="text-white font-semibold">Truck Pit Stop</span>
            </div>
            <div className="flex items-center gap-6 text-gray-400 text-sm">
              <a href="#" className="hover:text-white transition-colors">Privacy Policy</a>
              <a href="#" className="hover:text-white transition-colors">Terms of Service</a>
              <a href="#" className="hover:text-white transition-colors">Contact</a>
            </div>
            <p className="text-gray-500 text-sm">
              © {new Date().getFullYear()} Truck Pit Stop. All rights reserved.
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}
