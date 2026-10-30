import { scheduleDeadline, type OrderScheduleSummary } from '../repair-orders/repairOrderSchedule'
import '../repair-orders/repairOrderSchedule.css'
import { type ReactNode, useEffect, useMemo, useState } from 'react'
import {
  History,
  LayoutList,
  Plus,
  RefreshCw,
  Search,
  Zap,
} from 'lucide-react'
import { elapsedSince, shortDuration } from '@/lib/elapsed'

export type ActionQueueLane = 'needs_action' | 'on_floor' | 'ready_to_close' | 'closed_today'
type ActionQueueFilter = 'all' | ActionQueueLane

export interface ActionQueueOrder extends OrderScheduleSummary {
  id: string
  order_number: string
  status: string
  source?: string | null
  pending_zelle_confirmation?: boolean
  description: string | null
  customer_name: string
  vehicle_info: string
  vehicle_unit_number?: string | null
  total_cost: string
  updated_at: string
  mechanic_name: string | null
  work_started_at: string | null
  hold_reason: string | null
  held_at: string | null
  quote_sent: boolean | null
  paid_at?: string | null
}

export interface ActionQueueProjection {
  orders_needing_action: ActionQueueOrder[]
  orders_needing_action_has_more: boolean
  orders_on_floor: ActionQueueOrder[]
  orders_on_floor_has_more: boolean
  orders_ready_to_close: ActionQueueOrder[]
  orders_ready_to_close_has_more: boolean
  orders_closed_today?: ActionQueueOrder[]
  orders_closed_today_has_more?: boolean
}

type LaneDefinition = {
  key: ActionQueueLane
  label: string
  orders: ActionQueueOrder[]
  hasMore: boolean
}

const LANE_LABEL: Record<ActionQueueLane, string> = {
  needs_action: 'Needs Action',
  on_floor: 'On the Floor',
  ready_to_close: 'Ready to Close',
  closed_today: 'Closed Today',
}

const statusLabel = (order: ActionQueueOrder) => {
  if (order.source === 'easy_truck_shop_import' && ['completed', 'invoiced'].includes(order.status)) return 'ETS history'
  if (order.pending_zelle_confirmation) return 'Zelle Review'
  if (order.status === 'pending_review') return 'Needs Review'
  if (order.status === 'in_progress' && order.hold_reason) return 'On Hold'
  if (order.status === 'completed') return 'Invoice Customer'
  if (order.status === 'invoiced') return 'Payment Due'
  if (order.status === 'paid') return 'Paid'
  if (order.status === 'acknowledged') return "Ack'd"
  return order.status.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

const updatedLabel = (value: string) => {
  const elapsed = elapsedSince(value)
  if (elapsed == null || elapsed < 0) return 'Updated recently'
  if (elapsed < 60_000) return 'Updated just now'
  return `Updated ${shortDuration(elapsed)} ago`
}

const currency = (value: string) => {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed)
    ? parsed.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
    : value
}

export default function ShopCockpitActionLedger({
  projection,
  isManager,
  canViewActivity,
  queueView,
  activityCount,
  isRefreshing,
  lastUpdatedLabel,
  quickOrderExpanded,
  notificationRegion,
  quickOrderForm,
  activityFeed,
  onQueueViewChange,
  onToggleQuickOrder,
  onFullOrder,
  onRefresh,
  onOpenRecord,
  valueSummary,
  valueSummaryLoading = false,
  valueSummaryError = false,
  onValueScopeChange,
  initialLaneFilter = 'all',
  activeWork,
  workView = 'active',
  onWorkViewChange,
}: {
  projection: ActionQueueProjection
  isManager: boolean
  canViewActivity: boolean
  queueView: 'queue' | 'activity'
  activityCount: number | string | null
  isRefreshing: boolean
  lastUpdatedLabel: string
  quickOrderExpanded: boolean
  notificationRegion: ReactNode
  quickOrderForm: ReactNode
  activityFeed: ReactNode
  onQueueViewChange: (view: 'queue' | 'activity') => void
  onToggleQuickOrder: () => void
  onFullOrder: () => void
  onRefresh: () => void
  onOpenRecord: (id: string, lane: ActionQueueLane) => void
  valueSummary?: { order_count: number; order_value: string } | null
  valueSummaryLoading?: boolean
  valueSummaryError?: boolean
  onValueScopeChange?: (scope: { lane: ActionQueueFilter; search: string }) => void
  initialLaneFilter?: ActionQueueFilter
  activeWork?: ReactNode
  workView?: 'active' | 'closeout'
  onWorkViewChange?: (view: 'active' | 'closeout') => void
}) {
  const baseLanes = useMemo<LaneDefinition[]>(() => [
    {
      key: 'needs_action',
      label: LANE_LABEL.needs_action,
      orders: projection.orders_needing_action,
      hasMore: projection.orders_needing_action_has_more,
    },
    {
      key: 'on_floor',
      label: LANE_LABEL.on_floor,
      orders: projection.orders_on_floor,
      hasMore: projection.orders_on_floor_has_more,
    },
    {
      key: 'ready_to_close',
      label: LANE_LABEL.ready_to_close,
      orders: projection.orders_ready_to_close,
      hasMore: projection.orders_ready_to_close_has_more,
    },
    {
      key: 'closed_today',
      label: LANE_LABEL.closed_today,
      orders: projection.orders_closed_today ?? [],
      hasMore: projection.orders_closed_today_has_more ?? false,
    },
  ], [projection])
  const hasActiveWork = Boolean(activeWork)
  const lanes = useMemo(() => hasActiveWork ? [
    { ...baseLanes[2] },
    { ...baseLanes[0], label: 'Payment review', orders: baseLanes[0].orders.filter(order => order.pending_zelle_confirmation), hasMore: false },
    { ...baseLanes[3] },
  ] : baseLanes, [hasActiveWork, baseLanes])
  // Keep pending closeout visible even while Active work or Activity is open.
  // Closed Today is history, not outstanding work. Deduplicate projected IDs.
  const pendingPaymentOrders = projection.orders_needing_action.filter(order => order.pending_zelle_confirmation)
  const closeoutCount = new Set([...projection.orders_ready_to_close, ...pendingPaymentOrders].map(order => order.id)).size
  // Payment reviews lead needs_action. If its capped page contains only payment
  // reviews, unseen entries may include more; never claim an exact count then.
  const closeoutHasMore = projection.orders_ready_to_close_has_more || (
    projection.orders_needing_action_has_more
    && pendingPaymentOrders.length === projection.orders_needing_action.length
  )
  const closeoutCountLabel = `${closeoutCount}${closeoutHasMore ? '+' : ''}`
  const showingActive = hasActiveWork && workView === 'active' && queueView === 'queue'
  const allRows = useMemo(
    () => lanes.flatMap((lane) => lane.orders.map((order) => ({ order, lane: lane.key }))),
    [lanes],
  )
  const [laneFilter, setLaneFilter] = useState<ActionQueueFilter>(activeWork && !['needs_action', 'ready_to_close', 'closed_today'].includes(initialLaneFilter) ? 'ready_to_close' : initialLaneFilter)
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    onValueScopeChange?.({ lane: laneFilter, search: searchQuery.trim() })
  }, [laneFilter, onValueScopeChange, searchQuery])

  // A return from Repair Orders carries only a transient navigation state. The
  // cockpit instance stays mounted under the authenticated shell, so sync that
  // state whenever the user returns instead of treating it as construction-time
  // default data.
  useEffect(() => {
    setLaneFilter(hasActiveWork && !['needs_action', 'ready_to_close', 'closed_today'].includes(initialLaneFilter) ? 'ready_to_close' : initialLaneFilter)
  }, [initialLaneFilter, hasActiveWork])
  const normalizedSearch = searchQuery.trim().toLocaleLowerCase()
  const visibleRows = allRows.filter(({ order, lane }) => {
    if (laneFilter !== 'all' && lane !== laneFilter) return false
    if (!normalizedSearch) return true
    return [order.order_number, order.customer_name, order.vehicle_info, order.description, order.mechanic_name]
      .some((value) => value?.toLocaleLowerCase().includes(normalizedSearch))
  })
  const totalCount = allRows.length

  const selectLane = (filter: ActionQueueFilter) => {
    setLaneFilter(filter)
  }

  return (
    <section className={`db-shop-work-new db-operating-surface${activeWork ? ' db-shop-work-new--compact' : ''}`} aria-labelledby="shop-work-title">
      <header className="db-shop-work-new__header db-operating-page-header">
        <div>
          <h1 id="shop-work-title">Shop Work</h1>
          {!activeWork && <p>Open a repair order to review work, approvals, history, and payment.</p>}
        </div>
        <div className="db-shop-work-new__header-actions">
          <button
            type="button"
            className="db-shop-work-new__quiet-action"
            onClick={onRefresh}
            disabled={isRefreshing}
            aria-label={isRefreshing ? 'Refreshing Shop Work' : `Refresh Shop Work, ${lastUpdatedLabel || 'updated recently'}`}
            title={isRefreshing ? 'Refreshing Shop Work' : 'Refresh Shop Work'}
          >
            <RefreshCw aria-hidden="true" className={isRefreshing ? 'animate-spin' : ''} />
          </button>
          {isManager && (
            <>
              <button
                type="button"
                className="db-shop-work-new__quick-action"
                onClick={onToggleQuickOrder}
                aria-expanded={quickOrderExpanded}
                aria-label="Lightning Order"
                title="Lightning Order"
              >
                <Zap aria-hidden="true" />
                <span className="db-shop-work-new__action-full">Lightning Order</span>
              </button>
              <button type="button" className="db-shop-work-new__primary-action" aria-label="Full Order" title="Full Order" onClick={onFullOrder}>
                <Plus aria-hidden="true" />
                <span className="db-shop-work-new__action-full">Full Order</span>
              </button>
            </>
          )}
        </div>
      </header>

      {notificationRegion}
      {quickOrderForm}

        {/* Section header for the whole queue block. The view switch leads the
            left gutter -- the page's right gutter already carries three action
            buttons and the search -- and sits above the chips it outranks, so
            switching views never moves it. */}
        <header className="db-action-ledger__caption">
          <div className="db-action-ledger__caption-text">
            <div className="db-shop-work-new__view-switch" aria-label="Shop Work view">
              {activeWork && <button type="button" aria-pressed={showingActive} onClick={() => { onWorkViewChange?.('active'); onQueueViewChange('queue') }}><LayoutList aria-hidden="true" />Active work</button>}
              <button
                type="button"
                aria-pressed={queueView === 'queue' && !showingActive}
                onClick={() => { onWorkViewChange?.('closeout'); onQueueViewChange('queue') }}
              >
                {!activeWork && <LayoutList aria-hidden="true" />}
                {activeWork ? 'Closeout' : 'Queue'}
                {activeWork && <span>{closeoutCountLabel}</span>}
              </button>
              {canViewActivity && (
                <button
                  type="button"
                  aria-pressed={queueView === 'activity'}
                  onClick={() => onQueueViewChange('activity')}
                >
                  <History aria-hidden="true" />
                  Activity
                  {activityCount != null && <span title="Recent activity; + means more events are available">{activityCount}</span>}
                </button>
              )}
            </div>
            {!activeWork && <h2>{queueView === 'activity' ? 'Activity' : 'Action Ledger'}</h2>}
          </div>
          <div className="db-action-ledger__caption-summary" aria-live="polite">
            {!showingActive && (!activeWork || laneFilter !== 'needs_action') && <span className="db-action-ledger__caption-value">
              <span>{activeWork ? 'Closeout work value' : searchQuery.trim() ? 'Matching work value' : 'Work value'}</span>
              <strong>
                {valueSummaryLoading
                  ? 'Calculating…'
                  : valueSummaryError
                    ? 'Unavailable'
                    : currency(valueSummary?.order_value ?? '0.00')}
              </strong>
            </span>}
            <span className="db-action-ledger__caption-meta">{lastUpdatedLabel || 'Updated recently'}</span>
          </div>
        </header>

        {/* Queue-only controls: the chips and search filter the queue, so
            they leave with it. */}
        {queueView === 'queue' && !showingActive && (
          <div className="db-shop-work-new__toolbar">
            <div className="db-shop-work-new__lane-tabs" role="tablist" aria-label="Work queues">
            {!activeWork && <button
              type="button"
              role="tab"
              aria-selected={laneFilter === 'all'}
              onClick={() => selectLane('all')}
            >
              All work <span>{totalCount}</span>
            </button>}
            {lanes.map((lane) => (
              <button
                type="button"
                role="tab"
                key={lane.key}
                aria-selected={laneFilter === lane.key}
                onClick={() => selectLane(lane.key)}
                data-lane={lane.key}
              >
                {lane.label} <span>{lane.orders.length}{activeWork && lane.key === 'needs_action' && lane.orders.length >= 50 ? ' shown' : lane.hasMore ? '+' : ''}</span>
              </button>
            ))}
          </div>
          <label className="db-shop-work-new__search">
            <span className="sr-only">Search work queue</span>
            <Search aria-hidden="true" />
            <input
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Order, customer, truck, or technician"
            />
            </label>
          </div>
        )}


      {queueView === 'activity' ? (
        <div className="db-shop-work-new__activity db-operating-surface__scroller">{activityFeed}</div>
      ) : showingActive ? activeWork : (
        <>
          {/* The scroller wraps the card so the scrollbar sits outside the
              border; the caption above stays pinned. */}
          <div className="db-operating-surface__scroller">
          <section className="db-action-ledger db-operating-surface__card" aria-label="Server-backed work queue">
            <div className="db-action-ledger__rows">
              {visibleRows.length === 0 ? (
                <div className="db-action-ledger__empty" role="status">
                  <strong>{activeWork ? 'No closeout matches this view' : totalCount === 0 ? 'No work is waiting' : 'No work matches this view'}</strong>
                  <span>{totalCount === 0 ? 'New repair orders will appear in their canonical queue.' : 'Choose another queue or clear the search.'}</span>
                </div>
              ) : visibleRows.map(({ order, lane }) => {
                return (
                  <button
                    type="button"
                    key={`${lane}-${order.id}`}
                    className="db-action-ledger__row"
                    aria-label={`Open ${order.order_number} in Repair Orders`}
                    onClick={() => onOpenRecord(order.id, lane)}
                    data-order-id={order.id}
                    data-lane={lane}
                  >
                    <span className={`db-action-ledger__lane db-action-ledger__lane--${lane}`}>{activeWork && lane === 'needs_action' ? 'Payment review' : LANE_LABEL[lane]}</span>
                    <span className="db-action-ledger__identity">
                      <strong>{order.customer_name}</strong>
                      <span>{[order.vehicle_info, order.vehicle_unit_number ? `Unit ${order.vehicle_unit_number}` : null].filter(Boolean).join(' · ')}</span>
                      <small className="db-action-ledger__number">{order.order_number}</small>
                    </span>
                    <span className="db-action-ledger__status">
                      <strong>{statusLabel(order)}</strong>
                      <span className={order.promised_finish_at ? "db-order-schedule-deadline" : undefined} data-overdue={order.is_overdue || undefined}>{scheduleDeadline(order) || order.mechanic_name || updatedLabel(order.updated_at)}</span>
                    </span>
                    <span className="db-action-ledger__amount">
                      <strong>{currency(order.total_cost)}</strong>
                      <span aria-hidden="true">Open</span>
                    </span>
                  </button>
                )
              })}
            </div>
          </section>
          </div>
        </>
      )}
    </section>
  )
}
