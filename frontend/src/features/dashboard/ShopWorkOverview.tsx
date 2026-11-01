import { useState } from 'react'
import { ArrowRight, ArrowUpRight, CalendarClock, CheckCircle2, ClipboardList, CloudOff, Package, Receipt, RotateCcw, Truck, Wrench } from 'lucide-react'
import type { ShopWorkDestination } from './shopWorkNavigation'
import { WIP_REASONS } from './wipAging'
import './shopWorkOverview.css'

export type OverviewSource = 'repairs' | 'schedule' | 'inventory' | 'purchasing' | 'returns' | 'cores' | 'receivables'
export interface OverviewSourceStatus {
  id: OverviewSource
  state: 'ready' | 'partial' | 'unavailable' | 'restricted' | 'disabled'
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
  due_kind: 'repair_promise' | 'repair_start' | 'expected_delivery' | null
  evidence: 'verified' | 'review_required'
  quantity: number | null
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
  repairs: { label: 'Repair orders', icon: Wrench, path: '/dashboard/repair-orders' },
  schedule: { label: 'Repair commitments', icon: CalendarClock, path: '/dashboard/repair-orders' },
  inventory: { label: 'Inventory', icon: Package, path: '/dashboard/garage/inventory' },
  purchasing: { label: 'Purchasing', icon: Truck, path: '/dashboard/garage/purchasing?view=orders' },
  returns: { label: 'Returns', icon: RotateCcw, path: '/dashboard/garage/purchasing?view=returns' },
  cores: { label: 'Cores', icon: RotateCcw, path: '/dashboard/garage/purchasing?view=returns' },
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
  return REASONS[item.reason] ?? item.reason.replace(/_/g, ' ')
}
function dateLabel(item: ShopWorkItem, timezone: string | null): string | null {
  if (!item.due_at || !timezone || !Number.isFinite(Date.parse(item.due_at))) return null
  try {
    return new Intl.DateTimeFormat('en-US', { timeZone: timezone, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(item.due_at))
  } catch { return null }
}
function duePrefix(item: ShopWorkItem): string {
  return item.due_kind === 'expected_delivery' ? 'Expected' : item.due_kind === 'repair_start' ? 'Starts' : 'Promised'
}
function sourceIssue(source: OverviewSourceStatus): string {
  if (source.state === 'unavailable') return 'Could not check this area.'
  if (source.reason === 'account_review_only') return 'Account review candidates only. Collectible balances require verification in Account.'
  if (source.reason === 'classification_unavailable') return 'Account verification is unavailable. Review invoices in Customer accounts.'
  if (source.has_more && source.total !== null) return 'More records are available in this workspace.'
  return 'Some records could not be verified. Review this workspace.'
}
export default function ShopWorkOverview({ data, loading, failed, refreshing, onRetry, onOpen, onWorkspace }: {
  data?: ShopWorkOverviewData
  loading: boolean
  failed: boolean
  refreshing: boolean
  onRetry: () => void
  onOpen: (destination: ShopWorkDestination) => void
  onWorkspace: (path: string) => void
}) {
  const [visibleCount, setVisibleCount] = useState(6)
  const [upcomingCount, setUpcomingCount] = useState(5)
  if (!data) return <section className="db-overview__state" aria-busy={loading} role={failed ? 'alert' : 'status'}>
    {failed ? <CloudOff aria-hidden="true" /> : <CalendarClock aria-hidden="true" />}
    <h2>{failed ? 'Shop overview is unavailable' : 'Checking what needs your attention'}</h2>
    <p>{failed ? 'Your work is still in its existing workspace. Try again to check the board.' : 'Checking repairs, stock, purchasing, and your authorized account reviews.'}</p>
    {failed && <button type="button" className="db-overview__primary" onClick={onRetry} disabled={refreshing}>Try again</button>}
  </section>

  const checkedTime = Number.isFinite(Date.parse(data.as_of)) ? new Date(data.as_of).toLocaleString() : 'time unavailable'
  const issues = data.sources.filter(source => source.state === 'partial' || source.state === 'unavailable')
  const shown = data.actions.slice(0, visibleCount)
  const [lead, ...remaining] = shown
  const allChecked = !failed && data.sources.some(source => source.state === 'ready') && issues.length === 0
  const clock = Date.parse(data.as_of)
  const itemMeta = (item: ShopWorkItem) => {
    const date = dateLabel(item, data.timezone)
    return <>{overviewReason(item)}{date && <> · {duePrefix(item)} {date}</>}{item.quantity != null && item.quantity > 0 && <> · {item.quantity} {item.source === 'inventory' ? 'packages suggested' : 'remaining'}</>}</>
  }
  const overdue = (item: ShopWorkItem) => item.due_kind === 'repair_promise' && !!item.due_at && Date.parse(item.due_at) < clock
  return <div className="db-overview db-operating-surface__scroller" aria-label="Shop Work overview" aria-busy={refreshing}>
    {failed && <div className="db-overview__warning" role="alert"><CloudOff aria-hidden="true" /><div><strong>Refresh failed. Showing the last checked work.</strong><span>Last checked {checkedTime}. New or completed tasks may not be reflected.</span></div><button type="button" onClick={onRetry}>Retry</button></div>}
    {issues.length > 0 && <details className="db-overview__coverage" open={issues.some(source => source.state === 'unavailable')}>
      <summary>{issues.some(source => source.state === 'unavailable') ? 'Some areas could not be checked' : 'Some work needs source review'} <span>{issues.map(source => SOURCE[source.id].label).join(' · ')}</span></summary>
      <ul>{issues.map(source => <li key={source.id}><div><strong>{SOURCE[source.id].label}</strong><span>{sourceIssue(source)}</span></div><button type="button" onClick={() => onWorkspace(SOURCE[source.id].path)}>Open {SOURCE[source.id].label}<ArrowUpRight aria-hidden="true" /></button></li>)}</ul>
    </details>}
    <div className="db-overview__grid">
      <section aria-labelledby="overview-attention-title">
        <header className="db-overview__section-heading"><h2 id="overview-attention-title">Needs your attention</h2><span>{data.actions_total == null ? `${data.actions.length} shown` : `${data.actions_total} ${data.actions_total === 1 ? 'task' : 'tasks'}`}</span></header>
        {lead ? <>
          <article className="db-overview__lead" data-work-id={lead.id}>
            <div className="db-overview__lead-meta"><span>{(() => { const Icon = SOURCE[lead.source].icon; return <Icon aria-hidden="true" /> })()}{SOURCE[lead.source].label}</span>{overdue(lead) && <strong className="db-overview__overdue">Past promise</strong>}</div>
            <h3>{lead.title}</h3><p>{itemMeta(lead)}</p>
            <button type="button" className="db-overview__primary" aria-label={`${lead.action_label}: ${lead.title}`} onClick={() => onOpen(lead.destination)}>{lead.action_label}<ArrowRight aria-hidden="true" /></button>
          </article>
          <div className="db-overview__rows">{remaining.map(item => {
            const Icon = SOURCE[item.source].icon
            return <article className="db-overview__row" key={item.id} data-work-id={item.id}>
              <Icon className="db-overview__domain-icon" aria-hidden="true" /><div><h3>{item.title}</h3><p>{SOURCE[item.source].label} · {itemMeta(item)}</p>{overdue(item) && <span className="db-overview__overdue">Past promise</span>}</div>
              <button type="button" className="db-overview__link" aria-label={`${item.action_label}: ${item.title}`} onClick={() => onOpen(item.destination)}>{item.action_label}<ArrowUpRight aria-hidden="true" /></button>
            </article>
          })}</div>
        </> : <div className="db-overview__empty" role="status"><CheckCircle2 aria-hidden="true" /><h3>{allChecked ? 'You’re caught up in your available workspaces' : 'No confirmed actions in the checked work'}</h3><p>{allChecked ? 'No action is due in the areas you can access. Upcoming commitments stay alongside.' : 'Review the source notices before treating the shop as clear.'}</p></div>}
        {visibleCount < data.actions.length && <button type="button" className="db-overview__more" onClick={() => setVisibleCount(count => count + 6)}>Show next {Math.min(6, data.actions.length - visibleCount)} tasks</button>}
        {data.has_more_actions && visibleCount >= data.actions.length && <div className="db-overview__overflow"><p>{data.actions_total == null ? 'Some areas need review in their workspace.' : 'More work is available in the owning workspaces.'}</p>{data.sources.filter(s => s.has_more && s.state !== 'restricted' && s.state !== 'disabled').map(s => <button type="button" key={s.id} onClick={() => onWorkspace(SOURCE[s.id].path)}>{SOURCE[s.id].label}<ArrowUpRight aria-hidden="true" /></button>)}</div>}
      </section>
      <aside className="db-overview__upcoming" aria-labelledby="overview-upcoming-title"><header className="db-overview__section-heading"><h2 id="overview-upcoming-title">Coming up</h2></header>
        {data.upcoming.length ? <ol>{data.upcoming.slice(0, upcomingCount).map(item => <li key={item.id}>
          <span className="db-overview__event-time">{dateLabel(item, data.timezone) || 'Time unavailable'}</span><h3>{item.title}</h3><p>{duePrefix(item)} · {SOURCE[item.source].label}</p>
          <button type="button" className="db-overview__link" aria-label={`${item.action_label}: ${item.title}`} onClick={() => onOpen(item.destination)}>{item.action_label}<ArrowUpRight aria-hidden="true" /></button>
        </li>)}</ol> : <p className="db-overview__no-commitments">{data.sources.some(s => (s.id === 'schedule' || s.id === 'purchasing') && (s.state === 'unavailable' || s.state === 'partial')) ? 'Upcoming commitments could not be fully checked.' : 'No dated commitments in the checked work.'}</p>}
        {data.upcoming.length > upcomingCount && <button type="button" className="db-overview__more" onClick={() => setUpcomingCount(count => count + 5)}>Show more commitments</button>}
        {data.has_more_upcoming && upcomingCount >= data.upcoming.length && <div className="db-overview__overflow"><p>{data.upcoming_total == null ? 'Review upcoming commitments in their workspace.' : 'More dated work is available in its workspace.'}</p>{data.sources.filter(s => (s.id === 'schedule' || s.id === 'purchasing') && s.state !== 'restricted' && s.state !== 'disabled').map(s => <button type="button" key={s.id} onClick={() => onWorkspace(SOURCE[s.id].path)}>{SOURCE[s.id].label}<ArrowUpRight aria-hidden="true" /></button>)}</div>}
        <p className="db-overview__scope"><ClipboardList aria-hidden="true" />{data.scope === 'assigned' ? 'Your assigned repair work' : 'Your shop · authorized workspaces'}</p>
      </aside>
    </div>
  </div>
}
