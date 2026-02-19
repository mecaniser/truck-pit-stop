import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, CheckCircle, ClipboardList, MapPinned, Truck, Wrench } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useTheme } from '../../contexts/ThemeContext'

const BRAND = {
  platformName: 'Diesel Bridge Network',
  networkName: 'Diesel Bridge',
  heroLine: 'Get from breakdown request to active repair in one shared flow.',
  supportLine: 'One request thread for dispatch, drivers, and garage teams.',
  networkLine: 'Cut handoff delays and keep every update in one place.',
}

interface UserGoal {
  label: string
  detail: string
}

interface FlowStep {
  step: string
  title: string
  detail: string
  icon: LucideIcon
}

const TOP_USER_GOALS: UserGoal[] = [
  {
    label: 'Reduce downtime across every repair handoff',
    detail: 'Dispatch, drivers, and garages stay aligned from first request to final closeout.',
  },
  {
    label: 'Give every stakeholder the same live status',
    detail: 'No separate call chains or disconnected updates when jobs are moving fast.',
  },
  {
    label: 'Move from request to active repair with less friction',
    detail: 'The workflow is built to keep trucks progressing instead of waiting between teams.',
  },
]

const FLOW_STEPS: FlowStep[] = [
  {
    step: '01',
    title: 'Request service once',
    detail: 'Dispatch shares truck, location, and issue details in one clear intake.',
    icon: MapPinned,
  },
  {
    step: '02',
    title: 'Run repair with shared visibility',
    detail: 'Garage teams diagnose and update progress while everyone follows the same status.',
    icon: Wrench,
  },
  {
    step: '03',
    title: 'Close out with confidence',
    detail: 'Approvals, invoices, and history stay in one record for faster final handoff.',
    icon: ClipboardList,
  },
]

export default function LandingPage() {
  const { accentColors } = useTheme()
  const accent400 = accentColors[400]
  const accent500 = accentColors[500]
  const accent600 = accentColors[600]

  useEffect(() => {
    const pageTitle = 'Diesel Bridge Network | 3-Step Breakdown-to-Repair Flow'
    const pageDescription = 'Diesel Bridge Network helps dispatch, drivers, and garages coordinate repairs in a clear three-step workflow that reduces downtime.'

    document.title = pageTitle

    const upsertMetaByName = (name: string, content: string) => {
      let metaTag = document.querySelector(`meta[name="${name}"]`) as HTMLMetaElement | null
      if (!metaTag) {
        metaTag = document.createElement('meta')
        metaTag.setAttribute('name', name)
        document.head.appendChild(metaTag)
      }
      metaTag.setAttribute('content', content)
    }

    const upsertMetaByProperty = (property: string, content: string) => {
      let metaTag = document.querySelector(`meta[property="${property}"]`) as HTMLMetaElement | null
      if (!metaTag) {
        metaTag = document.createElement('meta')
        metaTag.setAttribute('property', property)
        document.head.appendChild(metaTag)
      }
      metaTag.setAttribute('content', content)
    }

    const upsertCanonical = (href: string) => {
      let canonical = document.querySelector('link[rel="canonical"]') as HTMLLinkElement | null
      if (!canonical) {
        canonical = document.createElement('link')
        canonical.setAttribute('rel', 'canonical')
        document.head.appendChild(canonical)
      }
      canonical.setAttribute('href', href)
    }

    upsertMetaByName('description', pageDescription)
    upsertMetaByName('robots', 'index, follow')
    upsertMetaByProperty('og:title', pageTitle)
    upsertMetaByProperty('og:description', pageDescription)
    upsertCanonical(`${window.location.origin}/`)
  }, [])

  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(to top left, #162338 0%, #0f172a 50%, #111827 100%)' }}>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-[60] focus:px-4 focus:py-2 focus:rounded-md focus:bg-white focus:text-slate-950"
      >
        Skip to main content
      </a>

      <header className="sticky top-0 z-50 border-b border-gray-800 bg-gray-900/95 backdrop-blur-sm">
        <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6" aria-label="Primary">
          <div className="flex items-center gap-2">
            <div
              className="flex h-10 w-10 items-center justify-center rounded-lg"
              style={{ background: `linear-gradient(135deg, ${accent500} 0%, ${accent600} 100%)` }}
            >
              <Truck className="h-6 w-6 text-white" aria-hidden="true" />
            </div>
            <span className="text-base font-bold text-white sm:text-lg">{BRAND.platformName}</span>
          </div>
          <Link
            to="/login"
            className="rounded-md px-3 py-2 text-sm text-gray-300 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
          >
            Sign in
          </Link>
        </nav>
      </header>

      <main id="main-content">
        <section className="px-4 pb-16 pt-14 sm:px-6 sm:pt-20">
          <div className="mx-auto max-w-6xl">
            <div>
              <p className="mb-5 inline-flex items-center rounded-full border border-white/20 bg-white/10 px-4 py-1 text-sm font-semibold text-gray-200">
                {BRAND.networkName} | Founding Access
              </p>
              <h1 className="mb-5 text-4xl font-bold leading-tight text-white md:text-5xl lg:text-6xl">
                {BRAND.heroLine}
              </h1>
              <p className="mb-7 max-w-2xl text-lg text-gray-300">
                {BRAND.supportLine} {BRAND.networkLine}
              </p>

              <ul className="mb-8 space-y-3">
                {TOP_USER_GOALS.map((goal) => (
                  <li key={goal.label} className="flex items-start gap-3">
                    <CheckCircle className="mt-0.5 h-5 w-5 flex-shrink-0" style={{ color: accent400 }} aria-hidden="true" />
                    <div>
                      <p className="font-semibold text-white">{goal.label}</p>
                      <p className="text-sm text-gray-400">{goal.detail}</p>
                    </div>
                  </li>
                ))}
              </ul>

              <Link
                to="/enroll"
                aria-label="Apply for founding garage access"
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-7 py-3 text-base font-semibold text-white transition-all hover:opacity-95 hover:shadow-[0_0_24px_var(--accent-500)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/80"
                style={{ backgroundColor: accent500 }}
              >
                Apply for Founding Garage Access
                <ArrowRight className="h-5 w-5" aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>

        <section id="flow" className="border-y border-gray-800 bg-gray-900/40 px-4 py-16 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="mb-10 max-w-3xl">
              <h2 className="text-3xl font-bold text-white md:text-4xl">How Diesel Bridge works in 3 steps</h2>
              <p className="mt-3 text-gray-300">
                Capture the request, keep everyone aligned during repair, and close with clear records.
              </p>
            </div>

            <div className="grid gap-5 md:grid-cols-3">
              {FLOW_STEPS.map((stepItem) => {
                const StepIcon = stepItem.icon
                return (
                  <article key={stepItem.step} className="rounded-xl border border-gray-700 bg-gray-900/55 p-5">
                    <div className="mb-4 flex items-center justify-between">
                      <span className="text-sm font-semibold tracking-wide text-gray-400">{stepItem.step}</span>
                      <div
                        className="flex h-10 w-10 items-center justify-center rounded-lg"
                        style={{ backgroundColor: `${accent500}1f` }}
                      >
                        <StepIcon className="h-5 w-5" style={{ color: accent400 }} aria-hidden="true" />
                      </div>
                    </div>
                    <h3 className="text-lg font-semibold text-white">{stepItem.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-gray-300">{stepItem.detail}</p>
                  </article>
                )
              })}
            </div>
          </div>
        </section>

      </main>

      <footer className="border-t border-gray-800 bg-gray-900 px-4 py-10 sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ backgroundColor: accent500 }}>
              <Truck className="h-5 w-5 text-white" aria-hidden="true" />
            </div>
            <span className="font-semibold text-white">{BRAND.platformName}</span>
          </div>
          <p className="text-sm text-gray-400">
            © {new Date().getFullYear()} {BRAND.platformName}. All rights reserved.
          </p>
          <div className="flex items-center gap-4 text-sm text-gray-400">
            <Link to="/login" className="hover:text-white">Sign in</Link>
            <a href="mailto:support@dieselbridge.network" className="hover:text-white">Contact</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
