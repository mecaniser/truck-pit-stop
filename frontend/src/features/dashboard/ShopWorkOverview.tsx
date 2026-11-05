import { arrivalDateLabel } from '@/features/appointments/visit-requests'
import WorkspaceRecordLink from '@/components/WorkspaceRecordLink'
import { ControlButton } from '@/components/ui/Controls'
import { type ReactNode, useEffect, useRef, useState } from 'react'
import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { ArrowRight, ArrowUpRight, CalendarClock, CheckCircle2, ChevronDown, CircleAlert, ClipboardList, CloudOff, Package, Receipt, RotateCcw, Truck, Wrench, X } from 'lucide-react'
import { shopWorkDestinationUrl, type ShopWorkDestination } from './shopWorkNavigation'
import { WIP_REASONS } from './wipAging'
import './shopWorkOverview.css'

export type OverviewSource = 'repairs' | 'schedule' | 'inventory' | 'purchasing' | 'returns' | 'cores' | 'receivables' | 'visits' | 'reservations' | 'payments'
export interface OverviewSourceStatus {
  id: OverviewSource
  state: 'loading' | 'ready' | 'partial' | 'unavailable' | 'restricted' | 'disabled'
  checked_at: string | null
  reason: string | null
  total: number | null
  shown: number
  has_more: boolean
}
export interface ShopWorkItem {
  id: string
  source: OverviewSource
  destination: ShopWorkDestination
  title: string
  reason: string
  action_label: string
  status: string
  created_at: string | null
  due_at: string | null
  due_kind: 'repair_promise' | 'repair_start' | 'expected_delivery' | 'visit_arrival' | 'reservation_start' | null
  evidence: 'verified' | 'review_required'
  quantity: number | null
  actionable?: boolean
  related_repair_order_ids: string[]
}
export interface ShopWorkOverviewData {
  as_of: string
  timezone: string | null
  scope: 'shop' | 'assigned'
  sources: OverviewSourceStatus[]
  actions: ShopWorkItem[]
  upcoming: ShopWorkItem[]
  active_jobs: number | null
  actions_total: number | null
  upcoming_total: number | null
  has_more_actions: boolean
  has_more_upcoming: boolean
}
const SOURCE = {
  visits: { label: 'Visit requests', icon: CalendarClock, path: '/dashboard/visit-requests' },
  reservations: { label: 'Reservations', icon: CalendarClock, path: '/dashboard/visit-requests?view=reservations' },
  payments: { label: 'Payment reviews', icon: Receipt, path: '/dashboard?work_view=closeout' },
  repairs: { label: 'Repair orders', icon: Wrench, path: '/dashboard/repair-orders' },
  schedule: { label: 'Repair commitments', icon: CalendarClock, path: '/dashboard/repair-orders' },
  inventory: { label: 'Inventory', icon: Package, path: '/dashboard/garage/inventory' },
  purchasing: { label: 'Purchasing', icon: Truck, path: '/dashboard/garage/purchasing?view=orders' },
  returns: { label: 'Returns', icon: RotateCcw, path: '/dashboard/garage/purchasing?view=returns' },
  cores: { label: 'Cores', icon: RotateCcw, path: '/dashboard/garage/purchasing?view=returns&custody=cores' },
  receivables: { label: 'Customer accounts', icon: Receipt, path: '/dashboard/customers' },
} as const
const REASONS: Record<string, string> = {
  ...WIP_REASONS,
  repair_promise_overdue: 'Promised completion has passed',
  stock_preparation: 'Stock or repair demand needs review',
  scheduled_repair_start: 'Scheduled start',
  repair_promise: 'Promised completion',
  delivery_review: 'Ordered parts are still outstanding',
  return_review: 'Prepare the supplier return',
  shipment_review: 'Review return shipment',
  supplier_credit_review: 'Supplier credit needs review',
  core_recovery: 'Core recovery needs review',
  core_return: 'Core is ready for return review',
  overdue_promise: 'Promised completion has passed',
  review_closeout: 'Completed work needs closeout review',
  review_payment: 'Payment needs verification',
  replenish_stock: 'Stock or repair demand needs review',
  stock_shortage: 'Stock or repair demand needs review',
  recommended_order: 'Stock or repair demand needs review',
  purchase_draft: 'Draft has not been ordered',
  review_delivery: 'Ordered parts are still outstanding',
  expected_delivery: 'Expected delivery',
  return_draft: 'Prepare the supplier return',
  return_submitted: 'Review return shipment',
  return_shipped: 'Supplier credit needs review',
  core_expected: 'Core recovery needs review',
  core_on_hand: 'Core is ready for return review',
  account_verification_required: 'Review invoices and verified balances in Account',
  scheduled_start: 'Scheduled start',
  promised_finish: 'Promised completion',
}
function overviewReason(item: ShopWorkItem): string {
  if (['visits', 'reservations', 'payments'].includes(item.source)) return item.reason
  return REASONS[item.reason] ?? item.reason.replace(/_/g, ' ')
}
function dateLabel(item: ShopWorkItem, timezone: string | null): string | null {
  if (item.due_kind === 'visit_arrival') return arrivalDateLabel(item.due_at)
  if (!item.due_at || !timezone || !Number.isFinite(Date.parse(item.due_at))) return null
  try {
    return new Intl.DateTimeFormat('en-US', { timeZone: timezone, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(item.due_at))
  } catch { return null }
}
function duePrefix(item: ShopWorkItem): string {
  if (item.due_kind === 'visit_arrival') return 'Arrival date'
  if (item.due_kind === 'reservation_start') return 'Scheduled'
  return item.due_kind === 'expected_delivery' ? 'Expected' : item.due_kind === 'repair_start' ? 'Starts' : 'Promised'
}
function sourceIssue(source: OverviewSourceStatus): string {
  if (source.reason === 'checking') return 'Checking this area…'
  if (source.state === 'unavailable') return 'Could not check this area.'
  if (source.reason === 'account_review_only') return 'Invoice balances are reviewed in each customer’s Account tab.'
  if (source.reason === 'classification_unavailable') return 'Invoice balances could not be checked. This board cannot confirm which payments are due.'
  if (source.has_more && source.total !== null) return 'More records are available in this workspace.'
  return 'Some records could not be verified. Review this workspace.'
}
const destinationArea: Record<ShopWorkDestination['kind'], string> = {
  visit_request: 'Service visits · Requests',
  reservation: 'Service visits · Reservations',
  payment_review: 'Payments · Zelle',
  repair_order: 'Repair Orders',
  inventory: 'My Shop · Inventory',
  purchase_order: 'My Shop · Purchasing',
  vendor_return: 'Purchasing · Returns',
  core: 'Purchasing · Cores',
  customer_account: 'Customers · Account',
}

type OpenRecord = (href: string, task: string) => void

function RecordLink({ item, section = 'attention', children, onOpen }: {
  item: ShopWorkItem
  section?: 'attention' | 'upcoming'
  children?: ReactNode
  onOpen: OpenRecord
}) {
  const task = `${section}:${item.id}`
  if (item.actionable === false) return <div id={task} tabIndex={-1} className="db-overview__task">{children}<span>Review unavailable</span></div>
  const href = shopWorkDestinationUrl(item.destination, task)
  return <WorkspaceRecordLink id={task} href={href} className={children ? 'db-overview__task' : 'db-overview__link'}
    aria-label={`${item.action_label}: ${item.title}`} onOpen={() => onOpen(href, task)}>
    {children ?? item.action_label}<ArrowRight aria-hidden="true" />
  </WorkspaceRecordLink>
}

export default function ShopWorkOverview({ data, loading, failed, refreshing, onRetry, onOpen, onWorkspace, resumeTask, visitsAvailable = false }: {
  visitsAvailable?: boolean
  data?: ShopWorkOverviewData
  loading: boolean
  failed: boolean
  refreshing: boolean
  onRetry: () => void
  onOpen: OpenRecord
  resumeTask?: string | null
  onWorkspace: (path: string) => void
}) {
  const [actionLimit, setVisibleCount] = useState(6)
  const [upcomingLimit, setUpcomingCount] = useState(5)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const restored = useRef<string | null>(null)
  const actionIndex = data?.actions.findIndex(item => `attention:${item.id}` === resumeTask) ?? -1
  const upcomingIndex = data?.upcoming.findIndex(item => `upcoming:${item.id}` === resumeTask) ?? -1
  const visibleCount = Math.max(actionLimit, Math.ceil((actionIndex + 1) / 6) * 6)
  const upcomingCount = Math.max(upcomingLimit, Math.ceil((upcomingIndex + 1) / 5) * 5)
  useEffect(() => {
    if (!resumeTask) { restored.current = null; return }
    if (!data || restored.current === resumeTask) return
    if (refreshing && actionIndex < 0 && upcomingIndex < 0) return
    const target = (actionIndex >= 0 || upcomingIndex >= 0) ? document.getElementById(resumeTask) : headingRef.current
    if (!target) return
    restored.current = resumeTask
    target.focus({ preventScroll: true })
    target.scrollIntoView?.({ block: 'nearest' })
  }, [data, resumeTask, actionIndex, upcomingIndex, refreshing])
  if (!data) return <section className="db-overview__state" aria-busy={loading} role={failed ? 'alert' : 'status'}>
    {failed ? <CloudOff aria-hidden="true" /> : <CalendarClock aria-hidden="true" />}
    <h2>{failed ? 'Shop overview is unavailable' : 'Checking what needs your attention'}</h2>
    <p>{failed ? 'Your work is still in its existing workspace. Try again to check the board.' : 'Checking repairs, stock, purchasing, and your authorized account reviews.'}</p>
    {failed && <ControlButton type="button" className="db-overview__primary" onClick={onRetry} disabled={refreshing}>Try again</ControlButton>}
  </section>

  const checking = data.sources.some(source => source.state === 'loading')
  const checkedTime = Number.isFinite(Date.parse(data.as_of)) ? new Date(data.as_of).toLocaleString() : 'time unavailable'
  const accountReviewOnly = data.sources.some(source => source.id === 'receivables' && source.state === 'partial' && source.reason === 'account_review_only')
  const issues = data.sources.filter(source => (source.state === 'partial' || source.state === 'unavailable') && !(source.id === 'receivables' && source.reason === 'account_review_only' && source.state === 'partial'))
  const actionOverflow = data.sources.filter(source => source.id !== 'schedule' && source.has_more && source.state === 'ready')
  const upcomingOverflow = data.sources.filter(source => (source.id === 'schedule' || source.id === 'purchasing') && source.has_more && source.state === 'ready')
  const shown = data.actions.slice(0, visibleCount)
  const [lead, ...remaining] = shown
  const allChecked = !checking && !failed && data.sources.some(source => source.state === 'ready') && issues.length === 0 && !accountReviewOnly
  const clock = Date.parse(data.as_of)
  const itemMeta = (item: ShopWorkItem) => {
    const date = dateLabel(item, data.timezone)
    return <>{overviewReason(item)}{date && <> · {duePrefix(item)} {date}</>}{item.quantity != null && item.quantity > 0 && <> · {item.quantity} {item.source === 'inventory' ? 'packages suggested' : 'remaining'}</>}</>
  }
  const overdue = (item: ShopWorkItem) => item.due_kind === 'repair_promise' && !!item.due_at && Date.parse(item.due_at) < clock
  return <div className="db-overview db-operating-surface__scroller" aria-label="Shop Work overview" aria-busy={refreshing}>
    {failed && <div className="db-overview__warning" role="alert"><CloudOff aria-hidden="true" /><div><strong>Refresh failed. Showing the last checked work.</strong><span>Last checked {checkedTime}. New or completed tasks may not be reflected.</span></div><ControlButton type="button" className="db-work-control" onClick={onRetry} disabled={refreshing}>Retry</ControlButton></div>}
    <div className="db-overview__grid">
      <section aria-labelledby="overview-attention-title">
        <header className="db-overview__section-heading db-overview__attention-heading">
          <h2 ref={headingRef} tabIndex={-1} id="overview-attention-title">Needs your attention</h2>
          <div className="db-overview__heading-meta">
            <span>{checking ? 'Checking work…' : data.actions_total == null ? `${data.actions.length} shown` : `${data.actions_total} ${data.actions_total === 1 ? 'task' : 'tasks'}`}</span>
            {issues.length > 0 && <Popover className="db-overview__status">
              {({ close }) => <>
                <PopoverButton data-db-control="action" className="db-overview__status-trigger">
                  <CircleAlert aria-hidden="true" />
                  {issues.length === 1 ? `${issues[0].id === 'receivables' ? 'Billing data' : SOURCE[issues[0].id].label} ${issues[0].state === 'unavailable' ? 'unavailable' : 'incomplete'}` : `${issues.length} areas need review`}
                  <ChevronDown aria-hidden="true" />
                </PopoverButton>
                <PopoverPanel focus className="db-overview__status-panel" role="dialog" aria-label="Areas needing review">
                  <div className="db-overview__status-heading"><strong>Board coverage</strong><ControlButton controlKind="icon" type="button" aria-label="Close verification details" onClick={() => close()}><X aria-hidden="true" /></ControlButton></div>
                  <ul>{issues.map(source => {
                    const Icon = SOURCE[source.id].icon
                    return <li key={source.id}><div className="db-overview__status-source"><Icon aria-hidden="true" /><strong>{SOURCE[source.id].label}</strong></div><p>{sourceIssue(source)}</p>{source.id !== 'receivables' && <ControlButton className="db-overview__link" type="button" onClick={() => { close(); onWorkspace(SOURCE[source.id].path) }}>Open {SOURCE[source.id].label}<ArrowUpRight aria-hidden="true" /></ControlButton>}</li>
                  })}</ul>
                </PopoverPanel>
              </>}
            </Popover>}
          </div>
        </header>
        {lead ? <>
          <article className="db-overview__lead" data-work-id={lead.id}>
            <RecordLink item={lead} onOpen={onOpen}>
              <div><div className="db-overview__lead-meta"><span>{destinationArea[lead.destination.kind]}</span>{overdue(lead) && <strong className="db-overview__overdue">Past promise</strong>}</div>
              <h3>{lead.action_label}</h3><strong>{lead.title}</strong><p>{itemMeta(lead)}</p></div>
            </RecordLink>
          </article>
          <div className="db-overview__rows">{remaining.map(item => {
            const Icon = SOURCE[item.source].icon
            return <article className="db-overview__row" key={item.id} data-work-id={item.id}>
              <RecordLink item={item} onOpen={onOpen}><Icon className="db-overview__domain-icon" aria-hidden="true" /><div><h3>{item.action_label} <span>· <span>{item.title}</span></span></h3><p>{destinationArea[item.destination.kind]} · {itemMeta(item)}</p>{overdue(item) && <span className="db-overview__overdue">Past promise</span>}</div></RecordLink>
            </article>
          })}</div>
        </> : <div className="db-overview__empty" role="status">{allChecked ? <CheckCircle2 aria-hidden="true" /> : <CircleAlert aria-hidden="true" />}<h3>{checking ? 'Checking what needs your attention' : allChecked ? 'You’re caught up in your available workspaces' : 'No confirmed actions in the checked work'}</h3><p>{checking ? 'Checking your available workspaces.' : allChecked ? 'No action is due in the areas you can access. Upcoming commitments stay alongside.' : issues.length ? 'Review the flagged areas before treating the shop as clear.' : 'No confirmed action is due in the checked areas. Invoice balances are reviewed separately.'}</p></div>}
        {visibleCount < data.actions.length && <ControlButton type="button" className="db-overview__more" onClick={() => setVisibleCount(visibleCount + 6)}>Show next {Math.min(6, data.actions.length - visibleCount)} tasks</ControlButton>}
        {data.has_more_actions && actionOverflow.length > 0 && visibleCount >= data.actions.length && <div className="db-overview__overflow"><p>{data.actions_total == null ? 'Some areas need review in their workspace.' : 'More work is available in the owning workspaces.'}</p>{actionOverflow.map(s => <ControlButton type="button" key={s.id} onClick={() => onWorkspace(SOURCE[s.id].path)}>{SOURCE[s.id].label}<ArrowUpRight aria-hidden="true" /></ControlButton>)}</div>}
      </section>
      <aside className="db-overview__upcoming" aria-labelledby="overview-upcoming-title"><header className="db-overview__section-heading"><h2 id="overview-upcoming-title">Coming up</h2>{visitsAvailable && <WorkspaceRecordLink className="db-overview__link" href="/dashboard/visit-requests?shop_work=overview" onOpen={() => onWorkspace('/dashboard/visit-requests')}>Service visits<ArrowUpRight aria-hidden="true" /></WorkspaceRecordLink>}</header>
        {data.upcoming.length ? <ol>{data.upcoming.slice(0, upcomingCount).map(item => <li key={item.id}>
          <span className="db-overview__event-time">{dateLabel(item, data.timezone) || 'Time unavailable'}</span><h3>{item.title}</h3><p>{duePrefix(item)} · {destinationArea[item.destination.kind]}</p>{['visits', 'reservations'].includes(item.source) && <p>{item.reason}</p>}
          <RecordLink item={item} section="upcoming" onOpen={onOpen} />
        </li>)}</ol> : <p className="db-overview__no-commitments">{checking ? 'Checking upcoming commitments…' : data.sources.some(s => (['schedule', 'purchasing', 'visits', 'reservations'].includes(s.id)) && (s.state === 'unavailable' || s.state === 'partial')) ? 'Upcoming commitments could not be fully checked.' : 'No dated commitments in the checked work.'}</p>}
        {data.upcoming.length > upcomingCount && <ControlButton type="button" className="db-overview__more" onClick={() => setUpcomingCount(upcomingCount + 5)}>Show more commitments</ControlButton>}
        {data.has_more_upcoming && upcomingOverflow.length > 0 && upcomingCount >= data.upcoming.length && <div className="db-overview__overflow"><p>{data.upcoming_total == null ? 'Review upcoming commitments in their workspace.' : 'More dated work is available in its workspace.'}</p>{upcomingOverflow.map(s => <ControlButton type="button" key={s.id} onClick={() => onWorkspace(SOURCE[s.id].path)}>{SOURCE[s.id].label}<ArrowUpRight aria-hidden="true" /></ControlButton>)}</div>}
        <p className="db-overview__scope"><ClipboardList aria-hidden="true" />{data.scope === 'assigned' ? 'Your assigned repair work' : 'Your shop · authorized workspaces'}</p>
        {accountReviewOnly && <p className="db-overview__scope">Invoice balances are reviewed in each customer’s Account tab.</p>}
      </aside>
    </div>
  </div>
}
