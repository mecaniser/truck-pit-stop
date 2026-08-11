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
  facts: Array<{ label: string; value: string }>
  icon: LucideIcon
}

const WORKFLOW_STAGES: WorkflowStage[] = [
  {
    id: 'intake',
    label: 'Intake',
    title: 'Capture the write-up once.',
    detail: 'Keep the customer, unit, issue, meter reading, and attachments together from the start.',
    action: 'Create repair order',
    facts: [
      { label: 'Concern', value: 'Loss of power under load' },
      { label: 'Received', value: 'May 14 · 8:52 AM' },
      { label: 'Written by', value: 'Jason Miller' },
    ],
    icon: ClipboardCheck,
  },
  {
    id: 'estimate',
    label: 'Estimate',
    title: 'Build the price from the work.',
    detail: 'Organize parts, labor, fees, and recommended work inside the repair order.',
    action: 'Review estimate',
    facts: [
      { label: 'Estimate total', value: '$4,494.62' },
      { label: 'Line items', value: '7 priced items' },
      { label: 'Prepared', value: 'May 14 · 9:31 AM' },
    ],
    icon: Wrench,
  },
  {
    id: 'approval',
    label: 'Approval',
    title: 'Keep authorization beside the estimate.',
    detail: 'Share the work for customer review and keep the decision attached to the job.',
    action: 'Approval recorded',
    facts: [
      { label: 'Status', value: 'Approved' },
      { label: 'Approved', value: 'May 14 · 9:47 AM' },
      { label: 'Approved by', value: 'Sarah Johnson' },
    ],
    icon: Check,
  },
  {
    id: 'invoice',
    label: 'Invoice',
    title: 'Carry completed work into the invoice.',
    detail: 'Move the repair forward without rebuilding its parts, labor, and service record.',
    action: 'Invoice ready to send',
    facts: [
      { label: 'Invoice', value: 'INV-2025-0417' },
      { label: 'Balance', value: '$4,494.62' },
      { label: 'Created', value: 'May 14 · 10:15 AM' },
    ],
    icon: Receipt,
  },
  {
    id: 'history',
    label: 'Payment & history',
    title: 'Close the balance. Keep the record.',
    detail: 'Record payment and preserve the completed repair for the next visit.',
    action: 'View vehicle history',
    facts: [
      { label: 'Payment', value: '$4,494.62' },
      { label: 'Method', value: 'ACH •••• 5521' },
      { label: 'Recorded', value: 'May 14 · 10:32 AM' },
    ],
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
      <div className="landing-sample-label">
        <span>Illustrative sample</span>
        <span>Fictional repair-order data</span>
      </div>

      <svg className="landing-workflow-connectors" viewBox="0 0 1440 590" preserveAspectRatio="none" aria-hidden="true">
        <g className={`landing-connector landing-connector--approval ${activeStageId === 'approval' ? 'is-active' : ''}`}>
          <path d="M 206 318 H 302 Q 326 318 344 300 H 455" />
          <circle className="landing-connector-node" cx="206" cy="318" r="4" />
          <circle className="landing-connector-node landing-connector-node--source" cx="455" cy="300" r="5" />
        </g>
        <g className={`landing-connector landing-connector--invoice ${activeStageId === 'invoice' ? 'is-active' : ''}`}>
          <path d="M 882 300 H 1112 Q 1140 300 1152 272 L 1190 220 H 1230" />
          <circle className="landing-connector-node landing-connector-node--source" cx="882" cy="300" r="5" />
          <circle className="landing-connector-node" cx="1230" cy="220" r="4" />
        </g>
        <g className={`landing-connector landing-connector--history ${activeStageId === 'history' ? 'is-active' : ''}`}>
          <path d="M 1055 300 H 1134 Q 1160 300 1160 328 V 438 H 1230" />
          <circle className="landing-connector-node landing-connector-node--source" cx="1055" cy="300" r="5" />
          <circle className="landing-connector-node" cx="1230" cy="438" r="4" />
        </g>
      </svg>

      <aside className={`landing-context-sheet landing-context-sheet--approval ${activeStageId === 'approval' ? 'is-active' : ''}`}>
        <span className="landing-context-icon landing-context-icon--success"><Check aria-hidden="true" /></span>
        <div>
          <strong>Customer approval</strong>
          <span>NorthStar Logistics approved the estimate.</span>
          <dl>
            <div><dt>Approved</dt><dd>May 14, 2025 · 9:47 AM</dd></div>
            <div><dt>Approved by</dt><dd>Sarah Johnson</dd></div>
          </dl>
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
              <span className="landing-workspace-back">← Repair orders</span>
              <strong>RO-2025-0417</strong>
            </div>
            <span className="landing-status">In progress</span>
          </div>

          <dl className="landing-workspace-summary">
            <div>
              <dt>Customer</dt>
              <dd>NorthStar Logistics</dd>
              <span>dispatch@northstar.example</span>
              <span>(614) 555-0187</span>
            </div>
            <div>
              <dt>Vehicle</dt>
              <dd>2021 Freightliner Cascadia 126</dd>
              <span>VIN: 3AKJHHDR5MSMR1234</span>
              <span>Unit: NSL-1047</span>
            </div>
            <div>
              <dt>Meter</dt>
              <dd>412,358 mi</dd>
              <span>Engine hours: 8,742 hrs</span>
              <span>Last service: 398,102 mi</span>
            </div>
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

          <div className="landing-workspace-content">
            <section className="landing-estimate-summary" aria-labelledby="estimate-summary-title">
              <div className="landing-panel-heading">
                <h2 id="estimate-summary-title">Estimate summary</h2>
                <span>Approved</span>
              </div>
              <dl className="landing-money-list">
                <div><dt>Labor</dt><dd>$1,250.00</dd></div>
                <div><dt>Parts</dt><dd>$2,875.42</dd></div>
                <div><dt>Shop supplies</dt><dd>$85.00</dd></div>
                <div><dt>Tax (6.75%)</dt><dd>$284.20</dd></div>
                <div className="landing-money-total"><dt>Estimated total</dt><dd>$4,494.62</dd></div>
              </dl>
            </section>

            <section className="landing-recommended-work" aria-labelledby="recommended-work-title">
              <h2 id="recommended-work-title">Recommended work</h2>
              <ul>
                <li><span>Replace DEF dosing unit</span><strong>$1,125.00</strong></li>
                <li><span>Turbocharger inspection</span><strong>$650.00</strong></li>
                <li><span>EGR valve cleaning</span><strong>$475.00</strong></li>
              </ul>
            </section>

            <section className="landing-stage-panel" key={activeStage.id} aria-labelledby="active-stage-title">
              <span className="landing-content-label">{activeStage.label} status</span>
              <h2 id="active-stage-title">{activeStage.title}</h2>
              <dl>
                {activeStage.facts.map((fact) => (
                  <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>
                ))}
              </dl>
              <span className="landing-preview-guidance">
                <strong>Next action</strong>
                {activeStage.action}
              </span>
            </section>
          </div>
        </div>
      </div>

      <aside className={`landing-context-sheet landing-context-sheet--invoice ${activeStageId === 'invoice' ? 'is-active' : ''}`}>
        <span className="landing-context-icon"><FileCheck2 aria-hidden="true" /></span>
        <div>
          <strong>Invoice ready</strong>
          <span>Invoice INV-2025-0417 is ready to send.</span>
          <dl>
            <div><dt>Total</dt><dd>$4,494.62</dd></div>
            <div><dt>Created</dt><dd>May 14, 2025 · 10:15 AM</dd></div>
          </dl>
        </div>
      </aside>

      <aside className={`landing-context-sheet landing-context-sheet--history ${activeStageId === 'history' ? 'is-active' : ''}`}>
        <span className="landing-context-icon landing-context-icon--success"><History aria-hidden="true" /></span>
        <div>
          <strong>Paid history</strong>
          <span>Payment of $4,494.62 was recorded.</span>
          <dl>
            <div><dt>Recorded</dt><dd>May 14, 2025 · 10:32 AM</dd></div>
            <div><dt>Method</dt><dd>ACH •••• 5521</dd></div>
          </dl>
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
