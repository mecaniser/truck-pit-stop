import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  FileText,
  History,
  Users,
  Wrench,
} from 'lucide-react'
import type {
  KeyboardEvent,
  MutableRefObject,
  PointerEvent as ReactPointerEvent,
  ReactNode,
} from 'react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

import {
  CUSTOMERS,
  INITIAL_LOCAL_STATE,
  INVOICES,
  MODULES,
  REPAIR_STORY,
  SHOP_ORDERS,
  VEHICLES,
  formatStoryCurrency,
  formatStoryMiles,
  getContextSheet,
  getEventSheet,
} from './repairStory'
import type {
  CustomerDetailTab,
  InputMode,
  ModuleId,
  PreviewLocalState,
  PreviewState,
  RepairEvidenceId,
  SheetModel,
  ShopWorkTab,
} from './repairStory'
import { buildEventRoute, buildModuleRoute, resolveEventRailY } from './routeGeometry'
import type { OrthogonalRoute, Rect } from './routeGeometry'
import './ProductWorkspace.css'

const MODULE_ICONS = {
  'repair-orders': ClipboardList,
  customers: Users,
  'shop-work': Wrench,
  invoices: FileText,
  'vehicle-history': History,
} satisfies Record<ModuleId, typeof ClipboardList>

const INITIAL_STATE: PreviewState = {
  activeModule: 'repair-orders',
  inputMode: 'programmatic',
  transitionEpoch: 0,
}

const createInitialLocalState = (): PreviewLocalState => ({
  repairOrders: { ...INITIAL_LOCAL_STATE.repairOrders },
  customers: { ...INITIAL_LOCAL_STATE.customers },
  shopWork: { ...INITIAL_LOCAL_STATE.shopWork },
  invoices: { ...INITIAL_LOCAL_STATE.invoices },
  vehicleHistory: { ...INITIAL_LOCAL_STATE.vehicleHistory },
})

interface RouteState {
  width: number
  height: number
  module: OrthogonalRoute | null
  event: OrthogonalRoute | null
}

interface AnnouncementIntent {
  epoch: number
  message: string
}

const EMPTY_ROUTES: RouteState = { width: 1, height: 1, module: null, event: null }

const routeLength = (route: OrthogonalRoute) => route.points.slice(1).reduce((total, point, index) => {
  const previous = route.points[index]
  return total + Math.abs(point.x - previous.x) + Math.abs(point.y - previous.y)
}, 0)

function toLocalRect(rect: DOMRect, root: DOMRect): Rect {
  return { x: rect.left - root.left, y: rect.top - root.top, width: rect.width, height: rect.height }
}

function prefers(query: string) {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(query).matches
}

function Sheet({ model, kind, sheetRef }: {
  model: SheetModel
  kind: 'context' | 'event'
  sheetRef: MutableRefObject<HTMLElement | null>
}) {
  const Icon = kind === 'context' ? FileText : CheckCircle2
  return (
    <aside
      ref={sheetRef}
      className={`repair-preview__sheet repair-preview__sheet--${kind} repair-preview__sheet--${model.tone}`}
      aria-label={`${kind === 'context' ? 'Module context' : 'Selected evidence'}: ${model.title}`}
      data-sheet-kind={kind}
    >
      <span className="repair-preview__sheet-icon" aria-hidden="true"><Icon /></span>
      <div className="repair-preview__sheet-copy">
        <span className="repair-preview__eyebrow">{model.eyebrow}</span>
        <h3>{model.title}</h3>
        <p>{model.summary}</p>
        <dl>
          {model.facts.map((fact) => <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}
        </dl>
        <span className="repair-preview__sheet-status">{model.status}</span>
      </div>
    </aside>
  )
}

function EvidenceButton({
  selected,
  onClick,
  children,
  className = '',
  label,
}: {
  selected: boolean
  onClick: () => void
  children: ReactNode
  className?: string
  label?: string
}) {
  return (
    <button
      type="button"
      className={`preview-evidence-control ${className}`}
      aria-pressed={selected}
      aria-label={label}
      data-event-selected={selected || undefined}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

function RepairOrdersSurface({ local, update }: {
  local: PreviewLocalState['repairOrders']
  update: (next: Partial<PreviewLocalState['repairOrders']>, label: string) => void
}) {
  const select = (selectedEvidence: RepairEvidenceId, patch: Partial<PreviewLocalState['repairOrders']>, label: string) => {
    update({ selectedEvidence, ...patch }, label)
  }
  const invoiceSelected = local.selectedEvidence === 'invoice'
  const historySelected = local.selectedEvidence === 'history'
  return (
    <section className="mini-surface mini-ro" aria-label="Repair order detail preview">
      <header className="mini-header">
        <div><span>Repair order</span><h2>{REPAIR_STORY.repairOrder.number}</h2></div>
        <div className="mini-statuses"><span className="mini-pill mini-pill--success">{REPAIR_STORY.repairOrder.state}</span><span className="mini-pill">{REPAIR_STORY.repairOrder.lifecycle}</span></div>
      </header>
      <div className="mini-identity-strip">
        <span>{REPAIR_STORY.customer.company}</span>
        <span>{REPAIR_STORY.vehicle.year} {REPAIR_STORY.vehicle.make} {REPAIR_STORY.vehicle.model}</span>
        <span>Unit {REPAIR_STORY.vehicle.unit}</span>
      </div>
      <div className="mini-work-requested" data-route-obstacle>
        <span className="mini-label">Work Requested</span>
        <strong>{REPAIR_STORY.repairOrder.concern}</strong>
        <small>Received {REPAIR_STORY.repairOrder.received.display} · {formatStoryMiles(REPAIR_STORY.vehicle.meterMiles)}</small>
      </div>
      <div className="mini-ro-grid">
        <div className="mini-ro-primary">
          <EvidenceButton
            selected={invoiceSelected}
            onClick={() => select('invoice', { invoiceExpanded: !local.invoiceExpanded }, `Invoice ${REPAIR_STORY.invoice.number}`)}
            className="mini-invoice-card"
          >
            <span className="mini-invoice-top"><span><FileText aria-hidden="true" /> Invoice {REPAIR_STORY.invoice.number}</span><span>{REPAIR_STORY.invoice.state}</span></span>
            <span className="mini-invoice-total">{formatStoryCurrency(REPAIR_STORY.invoice.totalCents)}</span>
            <span className="mini-invoice-meta">Created {REPAIR_STORY.invoice.created.short} · Balance {formatStoryCurrency(REPAIR_STORY.payment.balanceCents)}</span>
            <ChevronDown className={local.invoiceExpanded ? 'is-open' : ''} aria-hidden="true" />
          </EvidenceButton>
          {local.invoiceExpanded ? (
            <dl className="mini-invoice-breakdown" data-route-obstacle>
              <div><dt>Repair subtotal</dt><dd>{formatStoryCurrency(REPAIR_STORY.money.laborCents + REPAIR_STORY.money.partsCents)}</dd></div>
              <div><dt>Shop supplies</dt><dd>{formatStoryCurrency(REPAIR_STORY.money.shopSuppliesCents)}</dd></div>
              <div><dt>Tax</dt><dd>{formatStoryCurrency(REPAIR_STORY.money.taxCents)}</dd></div>
              <div><dt>Invoice total</dt><dd>{formatStoryCurrency(REPAIR_STORY.money.totalCents)}</dd></div>
            </dl>
          ) : null}
          <EvidenceButton
            selected={historySelected}
            onClick={() => select('history', { historyExpanded: !local.historyExpanded }, 'Repair order history')}
            className="mini-disclosure"
          >
            <span><History aria-hidden="true" /><span><strong>Repair order history</strong><small>6 events retained with this order</small></span></span>
            <ChevronDown className={local.historyExpanded ? 'is-open' : ''} aria-hidden="true" />
          </EvidenceButton>
          {local.historyExpanded ? (
            <ol className="mini-history-list" data-route-obstacle>
              <li><time>{REPAIR_STORY.payment.recorded.short}</time><span>Payment recorded · {REPAIR_STORY.payment.method}</span></li>
              <li><time>{REPAIR_STORY.invoice.created.short}</time><span>Invoice finalized · {REPAIR_STORY.invoice.number}</span></li>
              <li><time>{REPAIR_STORY.repairOrder.approvalRecorded.short}</time><span>Estimate approved · {REPAIR_STORY.customer.authorizationContact}</span></li>
            </ol>
          ) : null}
        </div>
        <div className="mini-work-lines">
          <div className="mini-section-title"><span>Work &amp; Labor</span><small>2 lines</small></div>
          <EvidenceButton
            selected={local.selectedEvidence === 'work-def'}
            onClick={() => select('work-def', {}, REPAIR_STORY.shopWork.keyOperation)}
            className="mini-work-line"
          >
            <span className="mini-work-line__icon"><Wrench aria-hidden="true" /></span>
            <span><strong>{REPAIR_STORY.shopWork.keyOperation}</strong><small>2.5 hr labor · 2 parts</small></span>
            <span><strong>{formatStoryCurrency(362_542)}</strong><small>{formatStoryCurrency(75_000)} labor</small></span>
            <ChevronRight aria-hidden="true" />
          </EvidenceButton>
          <EvidenceButton
            selected={local.selectedEvidence === 'work-diagnostic'}
            onClick={() => select('work-diagnostic', {}, 'Aftertreatment system diagnostic')}
            className="mini-work-line"
          >
            <span className="mini-work-line__icon"><ClipboardList aria-hidden="true" /></span>
            <span><strong>Aftertreatment system diagnostic</strong><small>2 hr labor · diagnostic line</small></span>
            <span><strong>{formatStoryCurrency(50_000)}</strong><small>{REPAIR_STORY.shopWork.leadTechnician}</small></span>
            <ChevronRight aria-hidden="true" />
          </EvidenceButton>
          <footer className="mini-total-bar" data-route-obstacle>
            <span>Parts <strong>{formatStoryCurrency(REPAIR_STORY.money.partsCents)}</strong></span>
            <span>Labor <strong>{formatStoryCurrency(REPAIR_STORY.money.laborCents)}</strong></span>
            <span>Order Total <strong>{formatStoryCurrency(REPAIR_STORY.money.totalCents)}</strong></span>
          </footer>
        </div>
      </div>
    </section>
  )
}

function CustomersSurface({ local, update }: {
  local: PreviewLocalState['customers']
  update: (next: Partial<PreviewLocalState['customers']>, label: string) => void
}) {
  const customer = CUSTOMERS.find((item) => item.id === local.selectedCustomerId) ?? CUSTOMERS[0]
  const switchTab = (detailTab: CustomerDetailTab) => update({ detailTab }, `${customer.company} ${detailTab}`)
  return (
    <section className="mini-surface mini-customers" aria-label="Customers list and detail preview">
      <header className="mini-header"><div><span>Customer records</span><h2>Customers</h2></div><span className="mini-count">{CUSTOMERS.length} shown</span></header>
      <div className="mini-search" data-route-obstacle><span aria-hidden="true">⌕</span> Search by name, email, or phone…</div>
      <div className="mini-customer-layout">
        <div className="mini-table-wrap">
          <table className="mini-table">
            <thead><tr><th>Customer</th><th>Email</th><th>Phone</th><th>DOT / MC</th><th>Vehicles</th><th>Balance</th><th>Actions</th></tr></thead>
            <tbody>{CUSTOMERS.map((item) => {
              const selected = item.id === customer.id && local.detailTab === 'overview'
              return <tr key={item.id} data-selected={item.id === customer.id || undefined}>
                <td><EvidenceButton selected={selected} onClick={() => update({ selectedCustomerId: item.id, detailTab: 'overview' }, item.company)} className="mini-table-link">{item.company}</EvidenceButton></td>
                <td>{item.email}</td><td>{item.phone}</td><td>{item.dotMc}</td><td>{item.vehicleCount}</td><td>{formatStoryCurrency(item.balanceCents)}</td><td><button type="button" onClick={() => update({ selectedCustomerId: item.id, detailTab: 'overview' }, item.company)}>View</button></td>
              </tr>
            })}</tbody>
          </table>
        </div>
        <article className="mini-customer-detail" data-route-obstacle>
          <header><div className="mini-avatar">{customer.company.split(' ').map((word) => word[0]).join('').slice(0, 2)}</div><div><span>Customer detail</span><h3>{customer.company}</h3></div></header>
          <div className="mini-local-tabs" role="tablist" aria-label="Customer detail sections">
            {(['overview', 'history'] as const).map((tab) => <button key={tab} type="button" role="tab" aria-selected={local.detailTab === tab} onClick={() => switchTab(tab)} data-event-selected={local.detailTab === tab && tab === 'history' || undefined}>{tab === 'overview' ? 'Overview' : 'History'}</button>)}
          </div>
          {local.detailTab === 'overview' ? <dl className="mini-detail-grid"><div><dt>Contact</dt><dd>{customer.contact}</dd></div><div><dt>Phone</dt><dd>{customer.phone}</dd></div><div><dt>Vehicles</dt><dd>{customer.vehicleCount}</dd></div><div><dt>Balance</dt><dd>{formatStoryCurrency(customer.balanceCents)}</dd></div></dl> : <div className="mini-customer-history"><div className="mini-history-metrics"><span>Completed ROs<strong>{customer.history.length}</strong></span><span>Lifetime spend<strong>{formatStoryCurrency(customer.history.reduce((sum, event) => sum + event.amountCents, 0))}</strong></span></div>{customer.history.map((event) => <div key={event.id}><span>{event.label}</span><small>{event.at} · {formatStoryCurrency(event.amountCents)}</small></div>)}</div>}
        </article>
      </div>
    </section>
  )
}

function ShopWorkSurface({ local, update }: {
  local: PreviewLocalState['shopWork']
  update: (next: Partial<PreviewLocalState['shopWork']>, label: string) => void
}) {
  const lanes = ['Needs Action', 'On the Floor', 'Ready to Close'] as const
  const switchTab = (activeTab: ShopWorkTab) => update({ activeTab }, activeTab === 'queue' ? 'Work Queue' : 'Activity')
  const selected = SHOP_ORDERS.find((order) => order.id === local.selectedOrderId) ?? SHOP_ORDERS[0]
  return (
    <section className="mini-surface mini-shop" aria-label="Shop Cockpit work queue preview">
      <header className="mini-header"><div><span>Shop Cockpit</span><h2>Work Queue</h2></div><span className="mini-count">{SHOP_ORDERS.length} active</span></header>
      <div className="mini-local-tabs" role="tablist" aria-label="Shop Cockpit sections">
        {(['queue', 'activity'] as const).map((tab) => <button key={tab} type="button" role="tab" aria-selected={local.activeTab === tab} onClick={() => switchTab(tab)}>{tab === 'queue' ? 'Queue' : 'Activity'}</button>)}
      </div>
      {local.activeTab === 'queue' ? <div className="mini-lanes">{lanes.map((lane) => <section key={lane} className="mini-lane" data-route-obstacle><header><span>{lane}</span><small>{SHOP_ORDERS.filter((order) => order.lane === lane).length}</small></header>{SHOP_ORDERS.filter((order) => order.lane === lane).map((order) => <EvidenceButton key={order.id} selected={order.id === selected.id} onClick={() => update({ selectedOrderId: order.id }, order.orderNumber)} className="mini-order-card"><span className="mini-order-card__top"><strong>{order.orderNumber}</strong><small>{order.status}</small></span><span>{order.customer} · {order.vehicle}</span><span>{order.summary}</span><span className="mini-order-card__bottom"><small>{order.technician}</small><strong>{formatStoryCurrency(order.totalCents)}</strong></span></EvidenceButton>)}</section>)}</div> : <div className="mini-activity-list">{SHOP_ORDERS.map((order) => <EvidenceButton key={order.id} selected={order.id === selected.id} onClick={() => update({ selectedOrderId: order.id }, order.orderNumber)} className="mini-activity-row"><span>{order.orderNumber}</span><strong>{order.activity}</strong><small>{order.status}</small></EvidenceButton>)}</div>}
    </section>
  )
}

function InvoicesSurface({ local, update }: {
  local: PreviewLocalState['invoices']
  update: (next: Partial<PreviewLocalState['invoices']>, label: string) => void
}) {
  return (
    <section className="mini-surface mini-invoices" aria-label="Invoice cards preview">
      <header className="mini-header"><div><span>Billing records</span><h2>Invoices</h2></div><span className="mini-count">3 states</span></header>
      <div className="mini-invoice-list">{INVOICES.map((invoice) => {
        const selected = invoice.id === local.selectedInvoiceId
        const expanded = invoice.id === local.expandedInvoiceId
        return <article key={invoice.id} className="mini-invoice-record" data-selected={selected || undefined}>
          <EvidenceButton selected={selected} onClick={() => update({ selectedInvoiceId: invoice.id, expandedInvoiceId: expanded ? null : invoice.id }, invoice.number)} className="mini-invoice-card">
            <span className="mini-invoice-top"><span><FileText aria-hidden="true" /> Invoice {invoice.number}</span><span>{invoice.state}</span></span>
            <span className="mini-invoice-total">{formatStoryCurrency(invoice.totalCents)}</span>
            <span className="mini-invoice-meta">{invoice.customer} · {invoice.orderNumber}</span>
            <ChevronDown className={expanded ? 'is-open' : ''} aria-hidden="true" />
          </EvidenceButton>
          {expanded ? <dl className="mini-invoice-breakdown"><div><dt>Repair subtotal</dt><dd>{formatStoryCurrency(invoice.totalCents - (invoice.state === 'Paid' ? REPAIR_STORY.money.taxCents : 5_900))}</dd></div><div><dt>Tax</dt><dd>{formatStoryCurrency(invoice.state === 'Paid' ? REPAIR_STORY.money.taxCents : 5_900)}</dd></div><div><dt>Invoice total</dt><dd>{formatStoryCurrency(invoice.totalCents)}</dd></div><div><dt>Balance</dt><dd>{formatStoryCurrency(invoice.balanceCents)}</dd></div></dl> : null}
        </article>
      })}</div>
    </section>
  )
}

function VehicleHistorySurface({ local, update }: {
  local: PreviewLocalState['vehicleHistory']
  update: (next: Partial<PreviewLocalState['vehicleHistory']>, label: string) => void
}) {
  const vehicle = VEHICLES.find((item) => item.id === local.selectedVehicleId) ?? VEHICLES[0]
  return (
    <section className="mini-surface mini-vehicle" aria-label="Vehicle detail and repair history preview">
      <header className="mini-header"><div><span>Vehicle record</span><h2>{vehicle.label}</h2></div><span className="mini-pill">Unit {vehicle.unit}</span></header>
      <div className="mini-vehicle-owner" data-route-obstacle><span className="mini-avatar">NS</span><div><span>Owner</span><strong>{vehicle.owner}</strong></div></div>
      <div className="mini-section-title"><span>Key Details</span><small>Vehicle identity</small></div>
      <div className="mini-vehicle-grid" data-route-obstacle><div><span>VIN</span><strong>{vehicle.maskedVin}</strong></div><div><span>Plate</span><strong>NC •••• 1047</strong></div><div><span>Mileage</span><strong>{formatStoryMiles(vehicle.meterMiles)}</strong></div><div><span>Unit Number</span><strong>{vehicle.unit}</strong></div></div>
      <div className="mini-section-title"><span>Repair History</span><small>{vehicle.repairs.length}</small></div>
      <div className="mini-vehicle-history">{vehicle.repairs.map((repair) => {
        const expanded = local.expandedRepairId === repair.id
        return <EvidenceButton key={repair.id} selected={expanded} onClick={() => update({ expandedRepairId: expanded ? null : repair.id }, repair.orderNumber)} className="mini-repair-row"><span><strong>{repair.orderNumber}</strong><small>{repair.title}</small></span><span><small>{repair.date}</small><strong>{formatStoryCurrency(repair.amountCents)}</strong></span><span className="mini-pill mini-pill--success">{repair.status}</span><ChevronDown className={expanded ? 'is-open' : ''} aria-hidden="true" />{expanded ? <span className="mini-repair-detail">Completed service remains attached to this vehicle, its meter, and the original repair order.</span> : null}</EvidenceButton>
      })}</div>
    </section>
  )
}

export default function ProductWorkspace() {
  const [preview, setPreview] = useState<PreviewState>(INITIAL_STATE)
  const [local, setLocal] = useState<PreviewLocalState>(createInitialLocalState)
  const [routes, setRoutes] = useState<RouteState>(EMPTY_ROUTES)
  const [announcement, setAnnouncement] = useState('')
  const latestPreviewRef = useRef<PreviewState>(INITIAL_STATE)
  const latestLocalRef = useRef<PreviewLocalState>(local)
  const sceneRef = useRef<HTMLDivElement | null>(null)
  const workspaceRef = useRef<HTMLDivElement | null>(null)
  const contextSheetRef = useRef<HTMLElement | null>(null)
  const eventSheetRef = useRef<HTMLElement | null>(null)
  const panelRef = useRef<HTMLElement | null>(null)
  const moduleRefs = useRef(new Map<ModuleId, HTMLButtonElement>())
  const animationRefs = useRef<Animation[]>([])
  const frameRef = useRef<number | null>(null)
  const announcementTimerRef = useRef<number | null>(null)
  const announcementIntentRef = useRef<AnnouncementIntent | null>(null)
  const latestEpochRef = useRef(0)
  const lastSpokenRef = useRef('')
  const lastSelectionRef = useRef<'module' | 'event'>('module')
  const inputModeRef = useRef<InputMode>('programmatic')

  const contextSheet = useMemo(() => getContextSheet(preview.activeModule), [preview.activeModule])
  const eventSheet = useMemo(() => getEventSheet(preview.activeModule, local), [preview.activeModule, local])

  const cancelAnimations = useCallback(() => {
    animationRefs.current.forEach((animation) => {
      try { if (typeof animation.commitStyles === 'function') animation.commitStyles() } catch { /* detached Safari node */ }
      animation.cancel()
    })
    animationRefs.current = []
  }, [])

  const queueAnnouncement = (message: string, epoch: number) => {
    announcementIntentRef.current = { message, epoch }
  }

  const measureRoutes = useCallback(() => {
    const scene = sceneRef.current
    const workspace = workspaceRef.current
    const context = contextSheetRef.current
    const event = eventSheetRef.current
    const moduleControl = moduleRefs.current.get(preview.activeModule)
    const eventControl = scene?.querySelector<HTMLElement>('[data-event-selected="true"]')
    if (!scene || !workspace || !context || !moduleControl) {
      setRoutes(EMPTY_ROUTES)
      return
    }
    const root = scene.getBoundingClientRect()
    const enhanced = typeof window.matchMedia === 'function' && window.matchMedia('(min-width: 1200px)').matches
    if (!enhanced || root.width <= 0 || root.height <= 0) {
      setRoutes({ width: Math.max(root.width, 1), height: Math.max(root.height, 1), module: null, event: null })
      return
    }
    const workspaceBox = workspace.getBoundingClientRect()
    const contextBox = context.getBoundingClientRect()
    const moduleBox = moduleControl.getBoundingClientRect()
    const obstacles = [...scene.querySelectorAll<HTMLElement>('[data-route-obstacle]')]
      .filter((element) => element !== eventControl && element !== context && element !== event)
      .map((element) => toLocalRect(element.getBoundingClientRect(), root))
    const moduleSource = { x: moduleBox.left - root.left, y: moduleBox.top - root.top + moduleBox.height / 2 }
    const moduleTarget = { x: contextBox.right - root.left, y: contextBox.top - root.top + contextBox.height / 2 }
    const leftRailX = (contextBox.right + workspaceBox.left) / 2 - root.left
    let eventRoute: OrthogonalRoute | null = null
    if (event && eventControl) {
      const eventBox = event.getBoundingClientRect()
      const eventBoxSource = eventControl.getBoundingClientRect()
      const eventSource = { x: eventBoxSource.left - root.left + eventBoxSource.width / 2, y: eventBoxSource.top - root.top }
      const eventTarget = { x: eventBox.left - root.left, y: eventBox.top - root.top + eventBox.height / 2 }
      const rightRailX = (workspaceBox.right + eventBox.left) / 2 - root.left
      const usesLocalRunway = Boolean(eventControl.closest('.mini-ro-grid, .mini-invoice-list'))
      const eventRailY = resolveEventRailY({
        sourceY: eventSource.y,
        workspaceTop: workspaceBox.top - root.top,
        usesLocalRunway,
      })
      eventRoute = buildEventRoute({ source: eventSource, target: eventTarget, eventRailY, rightRailX, obstacles, obstaclePadding: 8 })
    }
    setRoutes({
      width: root.width,
      height: root.height,
      module: buildModuleRoute({ source: moduleSource, target: moduleTarget, leftRailX, obstacles, obstaclePadding: 8 }),
      event: eventRoute,
    })
  }, [preview.activeModule])

  const scheduleMeasure = useCallback(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    frameRef.current = requestAnimationFrame(() => { frameRef.current = null; measureRoutes() })
  }, [measureRoutes])

  useLayoutEffect(() => {
    setRoutes((current) => ({ ...current, module: null, event: null }))
    measureRoutes()
  }, [measureRoutes, preview.transitionEpoch])

  useEffect(() => {
    const observed = [sceneRef.current, workspaceRef.current, contextSheetRef.current, eventSheetRef.current, panelRef.current]
      .filter((element): element is HTMLElement => Boolean(element))
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(scheduleMeasure) : null
    observed.forEach((element) => observer?.observe(element))
    window.addEventListener('resize', scheduleMeasure)
    const fonts = 'fonts' in document ? document.fonts : null
    void fonts?.ready.then(scheduleMeasure)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', scheduleMeasure)
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    }
  }, [scheduleMeasure])

  useEffect(() => {
    latestEpochRef.current = preview.transitionEpoch
    const intent = announcementIntentRef.current
    if (!intent || intent.epoch !== preview.transitionEpoch || preview.transitionEpoch === 0) return
    if (announcementTimerRef.current !== null) window.clearTimeout(announcementTimerRef.current)
    announcementTimerRef.current = window.setTimeout(() => {
      if (latestEpochRef.current !== intent.epoch || lastSpokenRef.current === intent.message) return
      lastSpokenRef.current = intent.message
      setAnnouncement(intent.message)
    }, 120)
    return () => { if (announcementTimerRef.current !== null) window.clearTimeout(announcementTimerRef.current) }
  }, [preview.transitionEpoch])

  useEffect(() => {
    if (preview.transitionEpoch === 0 || preview.inputMode === 'keyboard' || prefers('(prefers-reduced-motion: reduce)')) {
      cancelAnimations()
      return
    }
    cancelAnimations()
    const source = lastSelectionRef.current === 'module'
      ? moduleRefs.current.get(preview.activeModule)
      : sceneRef.current?.querySelector<HTMLElement>('[data-event-selected="true"]')
    const destination = lastSelectionRef.current === 'module' ? panelRef.current : eventSheetRef.current
    const route = lastSelectionRef.current === 'module' ? routes.module : routes.event
    const routeKind = lastSelectionRef.current
    const routePath = sceneRef.current?.querySelector<SVGPathElement>(`[data-route-path="${routeKind}"]`)
    if (source?.animate) animationRefs.current.push(source.animate([{ transform: 'scale(.97)' }, { transform: 'scale(1)' }], { duration: 120, easing: 'cubic-bezier(.16,1,.3,1)' }))
    if (destination?.animate) animationRefs.current.push(destination.animate([{ opacity: 0.74, transform: 'translateY(8px)', clipPath: 'inset(0 0 10% 0 round 18px)' }, { opacity: 1, transform: 'translateY(0)', clipPath: 'inset(0 0 0 0 round 18px)' }], { duration: lastSelectionRef.current === 'module' ? 360 : 480, delay: 80, easing: 'cubic-bezier(.16,1,.3,1)' }))
    if (routePath?.animate && route) animationRefs.current.push(routePath.animate([{ opacity: 0, strokeDashoffset: routeLength(route) }, { opacity: 1, strokeDashoffset: 0 }], { duration: 360, delay: 80, easing: 'cubic-bezier(.16,1,.3,1)' }))
    return cancelAnimations
  }, [cancelAnimations, preview.transitionEpoch, preview.inputMode, preview.activeModule, routes.module, routes.event])

  const selectModule = (moduleId: ModuleId, inputMode: InputMode) => {
    const current = latestPreviewRef.current
    if (moduleId === current.activeModule) return
    cancelAnimations()
    lastSelectionRef.current = 'module'
    setRoutes((current) => ({ ...current, module: null, event: null }))
    const epoch = current.transitionEpoch + 1
    const context = getContextSheet(moduleId)
    const module = MODULES.find((item) => item.id === moduleId)
    const next = { activeModule: moduleId, inputMode, transitionEpoch: epoch }
    latestPreviewRef.current = next
    queueAnnouncement(`${module?.label ?? moduleId} preview selected. ${context.title}. ${context.summary}.`, epoch)
    setPreview(next)
  }

  const updateLocal = <K extends keyof PreviewLocalState>(key: K, patch: Partial<PreviewLocalState[K]>, controlLabel: string) => {
    const currentLocal = latestLocalRef.current
    const currentPreview = latestPreviewRef.current
    const currentSlice = currentLocal[key]
    const changed = Object.entries(patch).some(([field, value]) => currentSlice[field as keyof typeof currentSlice] !== value)
    if (!changed) return
    cancelAnimations()
    lastSelectionRef.current = 'event'
    const nextLocal = { ...currentLocal, [key]: { ...currentSlice, ...patch } }
    const event = getEventSheet(currentPreview.activeModule, nextLocal)
    const module = MODULES.find((item) => item.id === currentPreview.activeModule)
    const epoch = currentPreview.transitionEpoch + 1
    const nextPreview = { ...currentPreview, inputMode: inputModeRef.current, transitionEpoch: epoch }
    latestLocalRef.current = nextLocal
    latestPreviewRef.current = nextPreview
    setLocal(nextLocal)
    queueAnnouncement(`${module?.label ?? currentPreview.activeModule}: ${controlLabel} selected. ${event?.title ?? controlLabel}.`, epoch)
    setPreview(nextPreview)
  }

  const handleModuleKeys = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | null = null
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') nextIndex = (index + 1) % MODULES.length
    if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') nextIndex = (index - 1 + MODULES.length) % MODULES.length
    if (event.key === 'Home') nextIndex = 0
    if (event.key === 'End') nextIndex = MODULES.length - 1
    if (nextIndex === null) return
    event.preventDefault()
    const target = MODULES[nextIndex]
    selectModule(target.id, 'keyboard')
    moduleRefs.current.get(target.id)?.focus()
  }

  const notePointer = (event: ReactPointerEvent<HTMLButtonElement>) => { event.currentTarget.dataset.pressed = 'true' }

  const renderSurface = () => {
    if (preview.activeModule === 'repair-orders') return <RepairOrdersSurface local={local.repairOrders} update={(patch, label) => updateLocal('repairOrders', patch, label)} />
    if (preview.activeModule === 'customers') return <CustomersSurface local={local.customers} update={(patch, label) => updateLocal('customers', patch, label)} />
    if (preview.activeModule === 'shop-work') return <ShopWorkSurface local={local.shopWork} update={(patch, label) => updateLocal('shopWork', patch, label)} />
    if (preview.activeModule === 'invoices') return <InvoicesSurface local={local.invoices} update={(patch, label) => updateLocal('invoices', patch, label)} />
    return <VehicleHistorySurface local={local.vehicleHistory} update={(patch, label) => updateLocal('vehicleHistory', patch, label)} />
  }

  return (
    <div
      ref={sceneRef}
      className="repair-preview"
      aria-label="Interactive DieselBridge product preview"
      data-transition-epoch={preview.transitionEpoch}
      onKeyDownCapture={() => { inputModeRef.current = 'keyboard' }}
      onPointerDownCapture={() => { inputModeRef.current = 'pointer' }}
      onClickCapture={(event) => {
        inputModeRef.current = event.detail === 0 ? 'keyboard' : 'pointer'
      }}
    >
      <div ref={workspaceRef} className="repair-preview__workspace">
        <nav className="repair-preview__modules" aria-label="DieselBridge product areas">
          <span className="repair-preview__mark" aria-hidden="true">DB</span>
          <div className="repair-preview__module-list" role="tablist" aria-label="Product areas" aria-orientation="vertical">
            {MODULES.map((module, index) => {
              const Icon = MODULE_ICONS[module.id]
              const selected = module.id === preview.activeModule
              return <button
                key={module.id}
                ref={(element) => { if (element) moduleRefs.current.set(module.id, element); else moduleRefs.current.delete(module.id) }}
                id={`repair-preview-module-${module.id}`}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls="repair-preview-operational-panel"
                tabIndex={selected ? 0 : -1}
                onPointerDown={notePointer}
                onPointerUp={(event) => { delete event.currentTarget.dataset.pressed }}
                onPointerCancel={(event) => { delete event.currentTarget.dataset.pressed }}
                onClick={(event) => selectModule(module.id, event.detail === 0 ? 'keyboard' : 'pointer')}
                onKeyDown={(event) => handleModuleKeys(event, index)}
              ><Icon aria-hidden="true" /><span>{module.label}</span></button>
            })}
          </div>
        </nav>
        <main
          ref={panelRef}
          id="repair-preview-operational-panel"
          className="repair-preview__main"
          role="tabpanel"
          aria-labelledby={`repair-preview-module-${preview.activeModule}`}
        >
          {renderSurface()}
        </main>
      </div>

      <Sheet model={contextSheet} kind="context" sheetRef={contextSheetRef} />
      {eventSheet ? <Sheet model={eventSheet} kind="event" sheetRef={eventSheetRef} /> : null}

      <svg className="repair-preview__routes" viewBox={`0 0 ${routes.width} ${routes.height}`} preserveAspectRatio="none" aria-hidden="true">
        {routes.module ? <g data-route-valid="module"><path data-route-path="module" d={routes.module.path} pathLength={routeLength(routes.module)} style={{ strokeDasharray: routeLength(routes.module) }} /><circle r="4" cx={routes.module.points[routes.module.points.length - 1]?.x} cy={routes.module.points[routes.module.points.length - 1]?.y} /></g> : null}
        {routes.event ? <g data-route-valid="event"><path data-route-path="event" d={routes.event.path} pathLength={routeLength(routes.event)} style={{ strokeDasharray: routeLength(routes.event) }} /><circle r="4" cx={routes.event.points[routes.event.points.length - 1]?.x} cy={routes.event.points[routes.event.points.length - 1]?.y} /></g> : null}
      </svg>

      <p className="repair-preview__announcement" role="status" aria-live="polite" aria-atomic="true">{announcement}</p>
    </div>
  )
}
