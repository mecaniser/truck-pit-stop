import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Building2,
  Check,
  ClipboardCheck,
  ExternalLink,
  FileCheck2,
  History,
  Receipt,
  RefreshCw,
  Wrench,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { usePlatformContact } from '../../hooks/usePlatformContact'
import { applySeo, removeStructuredData } from '../../lib/seo'
import api from '../../lib/api'
import './LandingPage.css'

const BRAND = {
  platformName: 'Diesel Bridge Network',
  shortName: 'DieselBridge',
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

interface WorkflowStage {
  id: 'intake' | 'estimate' | 'approval' | 'invoice' | 'history'
  label: string
  title: string
  detail: string
  action: string
  icon: LucideIcon
}

const WORKFLOW_STAGES: WorkflowStage[] = [
  {
    id: 'intake',
    label: 'Intake',
    title: 'Capture the write-up once.',
    detail: 'Keep the customer, unit, issue, meter reading, and attachments together from the start.',
    action: 'Create repair order',
    icon: ClipboardCheck,
  },
  {
    id: 'estimate',
    label: 'Estimate',
    title: 'Build the price from the work.',
    detail: 'Organize parts, labor, fees, and recommended work inside the repair order.',
    action: 'Review estimate',
    icon: Wrench,
  },
  {
    id: 'approval',
    label: 'Approval',
    title: 'Keep authorization beside the estimate.',
    detail: 'Share the work for customer review and keep the decision attached to the job.',
    action: 'Share for approval',
    icon: Check,
  },
  {
    id: 'invoice',
    label: 'Invoice',
    title: 'Carry completed work into the invoice.',
    detail: 'Move the repair forward without rebuilding its parts, labor, and service record.',
    action: 'Create invoice',
    icon: Receipt,
  },
  {
    id: 'history',
    label: 'Payment & history',
    title: 'Close the balance. Keep the record.',
    detail: 'Record payment and preserve the completed repair for the next visit.',
    action: 'View vehicle history',
    icon: History,
  },
]

const getPartnerMonogram = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || '')
    .join('') || 'DB'

function LandingWordmark() {
  return (
    <span className="landing-wordmark" aria-label={BRAND.platformName}>
      <svg viewBox="0 0 42 30" role="img" aria-hidden="true">
        <path d="M4 22C8 7 34 7 38 22" />
        <path d="M8 22h26" />
        <path d="M13 22v-7m8 7V11m8 11v-7" />
      </svg>
      <span>Diesel<span>Bridge</span></span>
    </span>
  )
}

function ProductWorkspace() {
  const [activeStageId, setActiveStageId] = useState<WorkflowStage['id']>('approval')
  const activeStage = WORKFLOW_STAGES.find((stage) => stage.id === activeStageId) ?? WORKFLOW_STAGES[2]

  return (
    <div className="landing-product-scene" aria-label="Interactive DieselBridge repair-order workflow preview">
      <aside className={`landing-context-sheet landing-context-sheet--approval ${activeStageId === 'approval' ? 'is-active' : ''}`}>
        <span className="landing-context-icon landing-context-icon--success"><Check aria-hidden="true" /></span>
        <div>
          <strong>Customer approval</strong>
          <span>Decision stays with the repair order.</span>
        </div>
      </aside>

      <div className="landing-workspace-frame">
        <aside className="landing-workspace-nav" aria-label="Product preview navigation">
          <LandingWordmark />
          <span className="is-current"><ClipboardCheck aria-hidden="true" /> Repair orders</span>
          <span><Building2 aria-hidden="true" /> Customers</span>
          <span><Wrench aria-hidden="true" /> Shop work</span>
          <span><Receipt aria-hidden="true" /> Invoices</span>
          <span><History aria-hidden="true" /> Vehicle history</span>
        </aside>

        <div className="landing-workspace-main">
          <div className="landing-workspace-toolbar">
            <div>
              <span className="landing-workspace-back">Repair orders</span>
              <strong>Repair order workspace</strong>
            </div>
            <span className="landing-status">In progress</span>
          </div>

          <dl className="landing-workspace-summary">
            <div><dt>Customer</dt><dd>Customer account</dd></div>
            <div><dt>Unit</dt><dd>Truck or trailer</dd></div>
            <div><dt>Vehicle details</dt><dd>VIN · meter · history</dd></div>
          </dl>

          <div className="landing-stage-tabs" aria-label="Repair workflow stages">
            {WORKFLOW_STAGES.map((stage) => (
              <button
                key={stage.id}
                type="button"
                aria-pressed={stage.id === activeStageId}
                onClick={() => setActiveStageId(stage.id)}
              >
                {stage.label}
              </button>
            ))}
          </div>

          <div className="landing-workspace-content" key={activeStage.id}>
            <section>
              <span className="landing-content-label">{activeStage.label}</span>
              <h2>{activeStage.title}</h2>
              <p>{activeStage.detail}</p>
              <span className="landing-preview-guidance">
                <strong>Next action</strong>
                {activeStage.action}
              </span>
            </section>
            <div className="landing-work-list" aria-label="Repair order contents">
              <span><Check aria-hidden="true" /> Customer and unit details</span>
              <span><Check aria-hidden="true" /> Work, parts, and labor</span>
              <span><Check aria-hidden="true" /> Notes and attachments</span>
            </div>
          </div>
        </div>
      </div>

      <aside className={`landing-context-sheet landing-context-sheet--invoice ${activeStageId === 'invoice' ? 'is-active' : ''}`}>
        <span className="landing-context-icon"><FileCheck2 aria-hidden="true" /></span>
        <div>
          <strong>Invoice ready</strong>
          <span>Completed work carries forward.</span>
        </div>
      </aside>

      <aside className={`landing-context-sheet landing-context-sheet--history ${activeStageId === 'history' ? 'is-active' : ''}`}>
        <span className="landing-context-icon landing-context-icon--success"><History aria-hidden="true" /></span>
        <div>
          <strong>Paid history</strong>
          <span>The completed repair remains searchable.</span>
        </div>
      </aside>
    </div>
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
          <a className="landing-brand-link" href="#main-content"><LandingWordmark /></a>
          <div className="landing-nav-links">
            <a href="#workflow">How it works</a>
            <a href="#approved-shops">Approved shops</a>
          </div>
          <div className="landing-nav-actions">
            <Link to="/login" className="landing-sign-in">Sign in</Link>
            <Link to="/enroll" className="landing-nav-cta">Apply for shop access</Link>
          </div>
        </nav>
      </header>

      <main id="main-content">
        <section className="landing-hero" aria-labelledby="landing-title">
          <div className="landing-hero-copy">
            <h1 id="landing-title">Every repair, moving in one clear flow.</h1>
            <p>DieselBridge gives repair shops one workspace for intake, estimates, approvals, invoices, payments, and vehicle history.</p>
            <Link to="/enroll" className="landing-primary-cta">
              Apply for Founding Shop Access
              <ArrowRight aria-hidden="true" />
            </Link>
          </div>
          <ProductWorkspace />
        </section>

        <section id="workflow" className="landing-workflow" aria-labelledby="workflow-title">
          <div className="landing-section-heading">
            <h2 id="workflow-title">One repair order. Five connected outcomes.</h2>
            <p>Each step keeps the shop’s work moving without splitting the record across separate tools.</p>
          </div>
          <ol className="landing-workflow-list">
            {WORKFLOW_STAGES.map((stage) => {
              const StageIcon = stage.icon
              return (
                <li key={stage.id}>
                  <span><StageIcon aria-hidden="true" /></span>
                  <div><strong>{stage.label}</strong><p>{stage.detail}</p></div>
                </li>
              )
            })}
          </ol>
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
            Apply for Founding Shop Access
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
