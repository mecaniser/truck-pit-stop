import { type ReactNode, useEffect, useMemo, useState } from 'react'
import {
  ArrowRight,
  Clock3,
  History,
  LayoutList,
  Plus,
  RefreshCw,
  Search,
  Zap,
} from 'lucide-react'

export type ActionQueueLane = 'needs_action' | 'on_floor' | 'ready_to_close'
type ActionQueueFilter = 'all' | ActionQueueLane

export interface ActionQueueOrder {
  id: string
  order_number: string
  status: string
  pending_zelle_confirmation?: boolean
  description: string | null
  customer_name: string
  vehicle_info: string
  total_cost: string
  updated_at: string
  mechanic_name: string | null
  work_started_at: string | null
  hold_reason: string | null
  held_at: string | null
  quote_sent: boolean | null
}

export interface ActionQueueProjection {
  orders_needing_action: ActionQueueOrder[]
  orders_needing_action_has_more: boolean
  orders_on_floor: ActionQueueOrder[]
  orders_on_floor_has_more: boolean
  orders_ready_to_close: ActionQueueOrder[]
  orders_ready_to_close_has_more: boolean
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
}

const statusLabel = (order: ActionQueueOrder) => {
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
  const elapsed = Date.now() - new Date(value).getTime()
  if (!Number.isFinite(elapsed) || elapsed < 0) return 'Updated recently'
  const minutes = Math.floor(elapsed / 60000)
  if (minutes < 1) return 'Updated just now'
  if (minutes < 60) return `Updated ${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `Updated ${hours}h ago`
  return `Updated ${Math.floor(hours / 24)}d ago`
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
  initialLaneFilter = 'all',
}: {
  projection: ActionQueueProjection
  isManager: boolean
  canViewActivity: boolean
  queueView: 'queue' | 'activity'
  activityCount: number
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
  initialLaneFilter?: ActionQueueFilter
}) {
  const lanes = useMemo<LaneDefinition[]>(() => [
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
  ], [projection])
  const allRows = useMemo(
    () => lanes.flatMap((lane) => lane.orders.map((order) => ({ order, lane: lane.key }))),
    [lanes],
  )
  const [laneFilter, setLaneFilter] = useState<ActionQueueFilter>(initialLaneFilter)
  const [searchQuery, setSearchQuery] = useState('')
  const [selected, setSelected] = useState<{ id: string; lane: ActionQueueLane } | null>(() => {
    const first = initialLaneFilter === 'all'
      ? allRows[0]
      : allRows.find(({ lane }) => lane === initialLaneFilter)
    return first ? { id: first.order.id, lane: first.lane } : null
  })

  useEffect(() => {
    if (selected && allRows.some(({ order, lane }) => order.id === selected.id && lane === selected.lane)) return
    const first = allRows[0]
    setSelected(first ? { id: first.order.id, lane: first.lane } : null)
  }, [allRows, selected])

  const selectedRow = selected
    ? allRows.find(({ order, lane }) => order.id === selected.id && lane === selected.lane) ?? null
    : null
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
    if (filter === 'all') return
    const first = lanes.find((lane) => lane.key === filter)?.orders[0]
    if (first) setSelected({ id: first.id, lane: filter })
  }

  const invoicePaymentState = (order: ActionQueueOrder) => {
    if (order.pending_zelle_confirmation) return 'Payment confirmation pending'
    if (order.status === 'paid') return 'Paid'
    if (order.status === 'invoiced') return 'Payment due'
    if (order.status === 'completed') return 'Invoice action available'
    return 'Not included in Shop Work'
  }

  return (
    <section className="db-shop-work-new" aria-labelledby="shop-work-title">
      <header className="db-shop-work-new__header">
        <div>
          <h1 id="shop-work-title">Shop Work</h1>
          <p>Three canonical queues. One connected repair record.</p>
        </div>
        <div className="db-shop-work-new__header-actions">
          <button
            type="button"
            className="db-shop-work-new__quiet-action"
            onClick={onRefresh}
            disabled={isRefreshing}
            aria-label={isRefreshing ? 'Refreshing Shop Work' : `Refresh Shop Work, ${lastUpdatedLabel || 'updated recently'}`}
          >
            <RefreshCw aria-hidden="true" className={isRefreshing ? 'animate-spin' : ''} />
            <span>{isRefreshing ? 'Refreshing…' : 'Refresh'}</span>
          </button>
          {isManager && (
            <>
              <button
                type="button"
                className="db-shop-work-new__quick-action"
                onClick={onToggleQuickOrder}
                aria-expanded={quickOrderExpanded}
              >
                <Zap aria-hidden="true" />
                <span>Lightning Order</span>
              </button>
              <button type="button" className="db-shop-work-new__primary-action" onClick={onFullOrder}>
                <Plus aria-hidden="true" />
                <span>Full Order</span>
              </button>
            </>
          )}
        </div>
      </header>

      {notificationRegion}
      {quickOrderForm}

      <div className="db-shop-work-new__view-switch" aria-label="Shop Work view">
        <button
          type="button"
          aria-pressed={queueView === 'queue'}
          onClick={() => onQueueViewChange('queue')}
        >
          <LayoutList aria-hidden="true" />
          Queue
        </button>
        {canViewActivity && (
          <button
            type="button"
            aria-pressed={queueView === 'activity'}
            onClick={() => onQueueViewChange('activity')}
          >
            <History aria-hidden="true" />
            Activity
            {activityCount > 0 && <span>{activityCount}</span>}
          </button>
        )}
      </div>

      {queueView === 'activity' ? (
        <div className="db-shop-work-new__activity">{activityFeed}</div>
      ) : (
        <>
          <div className="db-shop-work-new__toolbar">
            <div className="db-shop-work-new__lane-tabs" role="tablist" aria-label="Work queues">
              <button
                type="button"
                role="tab"
                aria-selected={laneFilter === 'all'}
                onClick={() => selectLane('all')}
              >
                All work <span>{totalCount}</span>
              </button>
              {lanes.map((lane) => (
                <button
                  type="button"
                  role="tab"
                  key={lane.key}
                  aria-selected={laneFilter === lane.key}
                  onClick={() => selectLane(lane.key)}
                  data-lane={lane.key}
                >
                  {lane.label} <span>{lane.orders.length}{lane.hasMore ? '+' : ''}</span>
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

          <section className="db-action-ledger" aria-label="Server-backed work queue">
            <header>
              <h2>Action Ledger</h2>
              <span>{lastUpdatedLabel || 'Updated recently'}</span>
            </header>
            <div className="db-action-ledger__rows">
              {visibleRows.length === 0 ? (
                <div className="db-action-ledger__empty" role="status">
                  <strong>{totalCount === 0 ? 'No work is waiting' : 'No work matches this view'}</strong>
                  <span>{totalCount === 0 ? 'New repair orders will appear in their canonical queue.' : 'Choose another queue or clear the search.'}</span>
                </div>
              ) : visibleRows.map(({ order, lane }) => {
                const isSelected = selected?.id === order.id && selected.lane === lane
                return (
                  <button
                    type="button"
                    key={`${lane}-${order.id}`}
                    className="db-action-ledger__row"
                    aria-pressed={isSelected}
                    onClick={() => setSelected({ id: order.id, lane })}
                    data-order-id={order.id}
                    data-lane={lane}
                  >
                    <span className={`db-action-ledger__lane db-action-ledger__lane--${lane}`}>{LANE_LABEL[lane]}</span>
                    <strong className="db-action-ledger__number">{order.order_number}</strong>
                    <span className="db-action-ledger__identity">
                      <strong>{order.customer_name}</strong>
                      <span>{order.vehicle_info}</span>
                    </span>
                    <span className="db-action-ledger__status">
                      <strong>{statusLabel(order)}</strong>
                      <span>{order.mechanic_name || updatedLabel(order.updated_at)}</span>
                    </span>
                    <strong className="db-action-ledger__amount">{currency(order.total_cost)}</strong>
                  </button>
                )
              })}
            </div>
          </section>

          {selectedRow && (
            <aside className="db-connected-record" aria-labelledby="connected-record-title">
              <header>
                <div>
                  <span>Selected repair record · read only</span>
                  <h2 id="connected-record-title">{selectedRow.order.order_number}</h2>
                </div>
                <strong className={`db-connected-record__lane db-connected-record__lane--${selectedRow.lane}`}>
                  {LANE_LABEL[selectedRow.lane]}
                </strong>
              </header>
              <div className="db-connected-record__cell">
                <span>Customer / vehicle</span>
                <strong>{selectedRow.order.customer_name}</strong>
                <small>{selectedRow.order.vehicle_info}</small>
              </div>
              <div className="db-connected-record__cell">
                <span>Work</span>
                <strong>{selectedRow.order.description || 'Work scope available in Repair Orders'}</strong>
                <small>{selectedRow.order.hold_reason ? `Hold: ${selectedRow.order.hold_reason.replace(/_/g, ' ')}` : selectedRow.order.mechanic_name || 'Technician not included'}</small>
              </div>
              <div className="db-connected-record__cell">
                <span>Authorization / history</span>
                <strong>{selectedRow.order.quote_sent === true ? 'Quote sent' : selectedRow.order.quote_sent === false ? 'Quote not sent' : 'Not included in Shop Work'}</strong>
                <small>History is available in Repair Orders</small>
              </div>
              <div className="db-connected-record__cell">
                <span>Invoice / payment</span>
                <strong className={selectedRow.order.status === 'paid' ? 'db-connected-record__success' : undefined}>
                  {invoicePaymentState(selectedRow.order)}
                </strong>
                <small>Financial detail is available in Repair Orders</small>
              </div>
              <div className="db-connected-record__handoff">
                <p>Repair Orders owns detail, history and every mutation.</p>
                <button
                  type="button"
                  onClick={() => onOpenRecord(selectedRow.order.id, selectedRow.lane)}
                >
                  Open {selectedRow.order.order_number}
                  <ArrowRight aria-hidden="true" />
                </button>
              </div>
              <span className="sr-only" role="status" aria-live="polite" aria-atomic="true">
                Selected {selectedRow.order.order_number} from {LANE_LABEL[selectedRow.lane]}
              </span>
            </aside>
          )}

          {!selectedRow && totalCount === 0 && (
            <aside className="db-connected-record db-connected-record--empty" aria-label="Connected repair record">
              <Clock3 aria-hidden="true" />
              <div>
                <strong>Select a repair order when work arrives</strong>
                <span>Customer, vehicle and canonical Repair Orders handoff will appear here.</span>
              </div>
            </aside>
          )}
        </>
      )}
    </section>
  )
}
