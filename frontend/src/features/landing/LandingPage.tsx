import { useEffect, type CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Building2,
  ExternalLink,
  RefreshCw,
} from 'lucide-react'

import { usePlatformContact } from '../../hooks/usePlatformContact'
import { applySeo, removeStructuredData } from '../../lib/seo'
import api from '../../lib/api'
import ProductWorkspace from './ProductWorkspace'
import './LandingPage.css'

const BRAND = {
  platformName: 'Diesel Bridge Network',
  shortName: 'DieselBridge',
}

const WORDMARK_LETTERS = Array.from(BRAND.shortName)
const WORDMARK_DROP_MOTION = [
  { y: '-0.42rem', delay: '520ms' },
  { y: '-0.54rem', delay: '380ms' },
  { y: '-0.34rem', delay: '640ms' },
  { y: '-0.49rem', delay: '460ms' },
  { y: '-0.38rem', delay: '340ms' },
  { y: '-0.55rem', delay: '600ms' },
  { y: '-0.44rem', delay: '420ms' },
  { y: '-0.52rem', delay: '680ms' },
  { y: '-0.32rem', delay: '500ms' },
  { y: '-0.5rem', delay: '360ms' },
  { y: '-0.4rem', delay: '660ms' },
  { y: '-0.47rem', delay: '480ms' },
] as const

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

const getPartnerMonogram = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || '')
    .join('') || 'DB'

function LandingWordmark({ animated = false }: { animated?: boolean }) {
  return (
    <span
      className={`landing-wordmark${animated ? ' landing-wordmark--animated' : ''}`}
      aria-label={BRAND.platformName}
    >
      <svg className="landing-wordmark__bridge" viewBox="0 0 42 30" role="img" aria-hidden="true">
        <path className="landing-wordmark__bridge-base" d="M8 22h26" />
        <path className="landing-wordmark__bridge-pillars" d="M13 22v-7m8 7V11m8 11v-7" />
        <path className="landing-wordmark__bridge-arch" d="M4 22C8 7 34 7 38 22" />
      </svg>
      <span className="landing-wordmark__name">
        <span className="landing-wordmark__letters" aria-hidden="true">
          {WORDMARK_LETTERS.map((letter, index) => (
            <span
              key={`${letter}-${index}`}
              className={`landing-wordmark__letter${index >= 6 ? ' landing-wordmark__letter--bridge' : ''}`}
              style={{
                '--letter-drop-y': WORDMARK_DROP_MOTION[index].y,
                '--letter-drop-delay': WORDMARK_DROP_MOTION[index].delay,
              } as CSSProperties}
            >
              {letter}
            </span>
          ))}
        </span>
      </span>
    </span>
  )
}

export default function LandingPage() {
  const { mailtoHref } = usePlatformContact()
  const {
    data: partners = [],
    isLoading: partnersLoading,
    isError: partnersError,
    isFetching: partnersFetching,
    refetch: refetchPartners,
  } = useQuery<LandingPartner[]>({
    queryKey: ['landing-partners'],
    queryFn: async () => {
      const response = await api.get('/auth/landing-partners')
      return response.data as LandingPartner[]
    },
    staleTime: 5 * 60 * 1000,
    retry: 1,
  })

  useEffect(() => {
    const pageTitle = 'DieselBridge | Repair Shop Workflow From Intake to Paid History'
    const pageDescription = 'DieselBridge gives heavy-duty repair shops one workflow for intake, estimates, approvals, invoices, payments, and vehicle history.'
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
            { '@type': 'Organization', '@id': `${siteOrigin}/#organization`, name: BRAND.platformName, url: siteOrigin, logo: ogImage },
            { '@type': 'WebSite', '@id': `${siteOrigin}/#website`, url: siteOrigin, name: BRAND.platformName, publisher: { '@id': `${siteOrigin}/#organization` } },
            { '@type': 'WebPage', '@id': `${canonicalUrl}#webpage`, url: canonicalUrl, name: pageTitle, description: pageDescription, isPartOf: { '@id': `${siteOrigin}/#website` } },
          ],
        },
      },
    })

    return () => removeStructuredData(structuredDataId)
  }, [])

  return (
    <div className="landing-shell">
      <a className="landing-skip" href="#main-content">Skip to main content</a>

      <header className="landing-header">
        <nav className="landing-nav" aria-label="Primary navigation">
          <a className="landing-brand-link" href="#main-content"><LandingWordmark animated /></a>
          <div className="landing-nav-links">
            <a href="#product-preview">Product tour</a>
            <a href="#approved-shops">Approved shops</a>
          </div>
          <div className="landing-nav-actions">
            <Link to="/login" className="landing-sign-in">Sign in</Link>
            <Link to="/enroll" className="landing-nav-cta">Apply for shop access</Link>
          </div>
        </nav>
      </header>

      <main id="main-content">
        <section id="product-preview" className="landing-hero" aria-labelledby="landing-title">
          <div className="landing-hero-copy">
            <h1 id="landing-title">Every repair, moving in one clear flow.</h1>
            <p>DieselBridge gives repair shops one workspace for intake, estimates, approvals, invoices, payments, and vehicle history.</p>
            <Link to="/enroll" className="landing-primary-cta">
              Bring DieselBridge to my shop
              <ArrowRight aria-hidden="true" />
            </Link>
          </div>
          <ProductWorkspace />
        </section>

        <section id="approved-shops" className="landing-partners" aria-labelledby="partners-title">
          <div className="landing-section-heading">
            <h2 id="partners-title">Built with working repair shops in view.</h2>
            <p>Approved Diesel Bridge shops appear here as their public partner profiles go live.</p>
          </div>

          {partnersLoading ? (
            <div className="landing-partner-state" role="status">
              <span className="landing-state-spinner" aria-hidden="true" />
              Loading approved shops…
            </div>
          ) : partnersError ? (
            <div className="landing-partner-state landing-partner-state--error" role="alert">
              <div>
                <strong>Approved shops could not be loaded.</strong>
                <span>The product overview is still available. Try the shop list again.</span>
              </div>
              <button type="button" onClick={() => refetchPartners()} disabled={partnersFetching}>
                <RefreshCw aria-hidden="true" />
                {partnersFetching ? 'Trying again…' : 'Try again'}
              </button>
            </div>
          ) : partners.length === 0 ? (
            <div className="landing-partner-state">
              <Building2 aria-hidden="true" />
              Approved shop profiles will appear here as they go live.
            </div>
          ) : (
            <div className="landing-partner-list">
              {partners.map((partner) => {
                const content = (
                  <>
                    {partner.logo_url ? (
                      <img src={partner.logo_url} alt="" referrerPolicy="no-referrer" />
                    ) : (
                      <span className="landing-partner-monogram" aria-hidden="true">{getPartnerMonogram(partner.name)}</span>
                    )}
                    <span className="landing-partner-copy">
                      <strong>{partner.name}</strong>
                      <span>{partner.partner_services || partner.address || 'Approved repair shop'}</span>
                    </span>
                    {partner.website ? <ExternalLink aria-hidden="true" /> : null}
                  </>
                )

                return partner.website ? (
                  <a key={partner.id} href={partner.website} target="_blank" rel="noopener noreferrer" aria-label={`Visit ${partner.name} website`}>
                    {content}
                  </a>
                ) : (
                  <article key={partner.id}>{content}</article>
                )
              })}
            </div>
          )}
        </section>

        <section className="landing-final-cta" aria-labelledby="final-cta-title">
          <h2 id="final-cta-title">Give the shop one place to run the repair.</h2>
          <p>Bring intake, work, approval, invoicing, payment, and vehicle history into one operating flow.</p>
          <Link to="/enroll" className="landing-primary-cta">
            Bring DieselBridge to my shop
            <ArrowRight aria-hidden="true" />
          </Link>
        </section>
      </main>

      <footer className="landing-footer">
        <LandingWordmark />
        <p>© {new Date().getFullYear()} {BRAND.platformName}</p>
        <div>
          <Link to="/privacy">Privacy</Link>
          <Link to="/terms">Terms</Link>
          <a href={mailtoHref || 'mailto:support@dieselbridge.network'}>Contact</a>
        </div>
      </footer>
    </div>
  )
}
