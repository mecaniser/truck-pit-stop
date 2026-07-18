import { useEffect } from 'react'
import { Spinner } from '@/components/ui'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, CheckCircle, ClipboardList, Globe, MapPin, MapPinned, Wrench } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useTheme } from '../../contexts/ThemeContext'
import BrandLogo from '../../components/brand/BrandLogo'
import { usePlatformContact } from '../../hooks/usePlatformContact'
import { applySeo, removeStructuredData } from '../../lib/seo'
import api from '../../lib/api'

const BRAND = {
  platformName: 'Diesel Bridge Network',
  networkName: 'Diesel Bridge',
  heroLine: 'Get from breakdown request to active repair in one shared flow.',
  supportLine: 'One request thread for dispatch, drivers, and shop teams.',
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

interface LandingPartner {
  id: string
  name: string
  slug: string
  address: string | null
  website: string | null
  logo_url: string | null
  partner_summary: string | null
  partner_services: string | null
}

const TOP_USER_GOALS: UserGoal[] = [
  {
    label: 'Reduce downtime across every repair handoff',
    detail: 'Dispatch, drivers, and shops stay aligned from first request to final closeout.',
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
    detail: 'Shop teams diagnose and update progress while everyone follows the same status.',
    icon: Wrench,
  },
  {
    step: '03',
    title: 'Close out with confidence',
    detail: 'Approvals, invoices, and history stay in one record for faster final handoff.',
    icon: ClipboardList,
  },
]

const PARTNER_SUMMARY_FALLBACK = 'Approved Diesel Bridge repair partner.'

const getPartnerMonogram = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || '')
    .join('') || 'DB'

const getPartnerWebsiteLabel = (website: string | null) => {
  if (!website) return null
  try {
    return new URL(website).hostname.replace(/^www\./, '')
  } catch {
    return website
  }
}

export default function LandingPage() {
  const { accentColors } = useTheme()
  const { mailtoHref } = usePlatformContact()
  const accent400 = accentColors[400]
  const accent500 = accentColors[500]
  const { data: partners = [], isLoading: partnersLoading } = useQuery<LandingPartner[]>({
    queryKey: ['landing-partners'],
    queryFn: async () => {
      const response = await api.get('/auth/landing-partners')
      return response.data as LandingPartner[]
    },
    staleTime: 5 * 60 * 1000,
    retry: 1,
  })
  const partnerRail = partners.length > 0 ? [...partners, ...partners] : []

  useEffect(() => {
    const pageTitle = 'Diesel Bridge Network | 3-Step Breakdown-to-Repair Flow'
    const pageDescription = 'Diesel Bridge Network helps dispatch, drivers, and shops coordinate repairs in a clear three-step workflow that reduces downtime.'
    const siteOrigin = (import.meta.env.VITE_SITE_URL || window.location.origin).replace(/\/+$/, '')
    const canonicalUrl = `${siteOrigin}/`
    const ogImage = `${siteOrigin}/DB_bridge_logo_favi_figma_public_B.png`
    const structuredDataId = 'seo-jsonld-landing'

    applySeo({
      title: pageTitle,
      description: pageDescription,
      canonicalUrl,
      robots: 'index, follow',
      ogUrl: canonicalUrl,
      ogImage,
      ogSiteName: BRAND.platformName,
      twitterImage: ogImage,
      structuredData: {
        id: structuredDataId,
        data: {
          '@context': 'https://schema.org',
          '@graph': [
            {
              '@type': 'Organization',
              '@id': `${siteOrigin}/#organization`,
              name: BRAND.platformName,
              url: siteOrigin,
              logo: ogImage,
            },
            {
              '@type': 'WebSite',
              '@id': `${siteOrigin}/#website`,
              url: siteOrigin,
              name: BRAND.platformName,
              publisher: {
                '@id': `${siteOrigin}/#organization`,
              },
            },
            {
              '@type': 'WebPage',
              '@id': `${canonicalUrl}#webpage`,
              url: canonicalUrl,
              name: pageTitle,
              description: pageDescription,
              isPartOf: {
                '@id': `${siteOrigin}/#website`,
              },
            },
          ],
        },
      },
    })

    return () => {
      removeStructuredData(structuredDataId)
    }
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
          <div className="flex items-center">
            <img
              src="/DB_bridge_logo_favi_figma_public_B.svg"
              alt={BRAND.platformName}
              className="h-[52px] sm:h-[56px] w-auto"
            />
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
                aria-label="Apply for founding shop access"
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-7 py-3 text-base font-semibold text-white transition-all hover:opacity-95 hover:shadow-[0_0_24px_var(--accent-500)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/80"
                style={{ backgroundColor: accent500 }}
              >
                Apply for Founding Shop Access
                <ArrowRight className="h-5 w-5" aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>

        <section id="partners" className="border-t border-gray-800 bg-gray-950/35 px-4 py-16 sm:px-6">
          <div className="mx-auto max-w-6xl">
            <div className="mb-10 max-w-3xl">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-400">Approved Network Partners</p>
              <h2 className="mt-3 text-3xl font-bold text-white md:text-4xl">Shops already active in Diesel Bridge</h2>
              <p className="mt-3 text-gray-300">
                Approved shops and service partners go live here as they join the network.
              </p>
            </div>

            <div className="partner-marquee-shell overflow-hidden rounded-lg border border-gray-800 bg-gray-950/50">
              {partnersLoading ? (
                <div className="flex items-center gap-3 px-4 py-4 text-sm text-gray-400">
                  <Spinner size="xs" />
                  Loading approved partners...
                </div>
              ) : partnerRail.length > 0 ? (
                <div className="partner-marquee-track px-3 py-3">
                  {partnerRail.map((partner, index) => {
                    const websiteLabel = getPartnerWebsiteLabel(partner.website)
                    const tileContent = (
                      <>
                        {partner.logo_url ? (
                          <img
                            src={partner.logo_url}
                            alt={`${partner.name} logo`}
                            className="h-10 w-10 rounded-lg bg-white p-1 object-contain"
                            referrerPolicy="no-referrer"
                          />
                        ) : (
                          <div
                            className="flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 text-sm font-semibold text-white"
                            style={{ backgroundColor: `${accent500}22` }}
                            aria-hidden="true"
                          >
                            {getPartnerMonogram(partner.name)}
                          </div>
                        )}
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-white">{partner.name}</p>
                          <p className="truncate text-xs text-gray-400">{websiteLabel || partner.slug}</p>
                        </div>
                      </>
                    )

                    const tileClassName =
                      'flex min-w-[220px] shrink-0 items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 transition-colors hover:border-white/20 hover:bg-white/[0.05]'

                    if (partner.website) {
                      return (
                        <a
                          key={`${partner.id}-${index}`}
                          href={partner.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={tileClassName}
                        >
                          {tileContent}
                        </a>
                      )
                    }

                    return (
                      <div key={`${partner.id}-${index}`} className={tileClassName}>
                        {tileContent}
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="px-4 py-4 text-sm text-gray-400">
                  Approved businesses appear here as they go live.
                </div>
              )}
            </div>

            {partners.length > 0 && (
              <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {partners.map((partner) => {
                  const websiteLabel = getPartnerWebsiteLabel(partner.website)
                  return (
                    <article key={partner.id} className="rounded-lg border border-gray-800 bg-gray-900/55 p-5">
                      <div className="flex items-start gap-3">
                        {partner.logo_url ? (
                          <img
                            src={partner.logo_url}
                            alt={`${partner.name} logo`}
                            className="h-12 w-12 rounded-lg bg-white p-1 object-contain"
                            referrerPolicy="no-referrer"
                          />
                        ) : (
                          <div
                            className="flex h-12 w-12 items-center justify-center rounded-lg border border-white/10 text-sm font-semibold text-white"
                            style={{ backgroundColor: `${accent500}22` }}
                            aria-hidden="true"
                          >
                            {getPartnerMonogram(partner.name)}
                          </div>
                        )}

                        <div className="min-w-0 flex-1">
                          <h3 className="text-lg font-semibold text-white">{partner.name}</h3>
                          {partner.partner_services ? (
                            <p className="mt-1 text-xs font-semibold uppercase tracking-[0.16em] text-gray-400">
                              {partner.partner_services}
                            </p>
                          ) : null}
                        </div>
                      </div>

                      <p className="mt-4 text-sm leading-6 text-gray-300">
                        {partner.partner_summary || PARTNER_SUMMARY_FALLBACK}
                      </p>

                      <div className="mt-5 space-y-3 text-sm text-gray-400">
                        {partner.address ? (
                          <div className="flex items-start gap-2">
                            <MapPin className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
                            <span>{partner.address}</span>
                          </div>
                        ) : null}

                        {partner.website ? (
                          <div className="flex items-center gap-2">
                            <Globe className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                            <a
                              href={partner.website}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="truncate text-gray-200 underline decoration-white/20 underline-offset-4 hover:text-white"
                            >
                              {websiteLabel || partner.website}
                            </a>
                          </div>
                        ) : null}
                      </div>
                    </article>
                  )
                })}
              </div>
            )}
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
          <div className="flex items-center">
            <BrandLogo alt={BRAND.platformName} variant="landing" className="h-7 sm:h-8 w-auto" />
          </div>
          <p className="text-sm text-gray-400">
            © {new Date().getFullYear()} {BRAND.platformName}. All rights reserved.
          </p>
          <div className="flex items-center gap-4 text-sm text-gray-400">
            <Link to="/privacy" className="hover:text-white">Privacy Policy</Link>
            <Link to="/terms" className="hover:text-white">Terms of Service</Link>
            <Link to="/login" className="hover:text-white">Sign in</Link>
            <a href={mailtoHref || 'mailto:support@dieselbridge.network'} className="hover:text-white">Contact</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
