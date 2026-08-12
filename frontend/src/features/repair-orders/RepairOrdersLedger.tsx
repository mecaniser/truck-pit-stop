import { ArrowLeft, ChevronLeft, ChevronRight, Plus, Search } from 'lucide-react'
import { REPAIR_ORDERS_QUEUE_LABEL, type RepairOrdersQueueOrigin } from './repairOrdersPresentation'

export type RepairOrdersLedgerRow = {
  id: string
  orderNumber: string
  status: string
  statusTone: 'neutral' | 'warning' | 'active' | 'success' | 'danger'
  description: string
  customer: string
  vehicle: string
  total: string
  updated: string
  internal: boolean
}

export default function RepairOrdersLedger({
  rows,
  totalOrders,
  searchQuery,
  statusFilter,
  statusOptions,
  selectedId,
  queueOrigin,
  isFetching,
  errorMessage,
  page,
  pageSize,
  hasMore,
  isPlaceholder,
  canGoPrevious,
  onSearchChange,
  onStatusChange,
  onOpenOrder,
  onCreateOrder,
  onReturnToShopWork,
  onPreviousPage,
  onNextPage,
}: {
  rows: RepairOrdersLedgerRow[]
  totalOrders: number
  searchQuery: string
  statusFilter: string
  statusOptions: Array<{ value: string; label: string }>
  selectedId: string | null
  queueOrigin: RepairOrdersQueueOrigin | null
  isFetching: boolean
  errorMessage?: string | null
  page: number
  pageSize: number
  hasMore: boolean
  isPlaceholder: boolean
  canGoPrevious: boolean
  onSearchChange: (value: string) => void
  onStatusChange: (value: string) => void
  onOpenOrder: (id: string) => void
  onCreateOrder: () => void
  onReturnToShopWork: () => void
  onPreviousPage: () => void
  onNextPage: () => void
}) {
  const queueLabel = queueOrigin ? REPAIR_ORDERS_QUEUE_LABEL[queueOrigin] : null
  const filtered = Boolean(searchQuery || statusFilter !== 'all')

  return (
    <section className="db-repair-orders-new" aria-labelledby="repair-orders-title" aria-busy={isFetching}>
      <header className="db-repair-orders-new__header">
        <div>
          <h1 id="repair-orders-title">Repair Orders</h1>
          <p>One canonical record from check-in through paid invoice.</p>
        </div>
        <button type="button" className="db-repair-orders-new__create" onClick={onCreateOrder} disabled={isFetching && rows.length === 0}>
          <Plus aria-hidden="true" />
          New repair order
        </button>
      </header>

      {queueLabel && (
        <div className="db-repair-orders-origin" role="status">
          <div>
            <span>Shop Work handoff</span>
            <strong>{queueLabel}</strong>
            <small>Queue origin is navigation context, not repair-order state.</small>
          </div>
          <button type="button" onClick={onReturnToShopWork}>
            <ArrowLeft aria-hidden="true" />
            Return to {queueLabel}
          </button>
        </div>
      )}

      <div className="db-repair-orders-new__toolbar">
        <label className="db-repair-orders-new__search">
          <span className="sr-only">Search repair orders</span>
          <Search aria-hidden="true" />
          <input
            type="search"
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Order, work, customer, or vehicle"
          />
        </label>
        <label className="db-repair-orders-new__status-select">
          <span>Order status</span>
          <select value={statusFilter} onChange={(event) => onStatusChange(event.target.value)}>
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <div className="db-repair-orders-new__status-tabs" role="group" aria-label="Filter repair orders by status">
          {statusOptions.map((option) => (
            <button
              type="button"
              key={option.value}
              aria-pressed={statusFilter === option.value}
              onClick={() => onStatusChange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <section className="db-repair-orders-ledger" aria-label="Repair order ledger">
        <header>
          <div>
            <h2>Order ledger</h2>
            <span>{filtered ? `${totalOrders} matching` : `${totalOrders} total`}</span>
          </div>
          {isFetching && <span className="db-repair-orders-ledger__sync" role="status">Updating…</span>}
        </header>

        {errorMessage ? (
          <div className="db-repair-orders-ledger__empty" role="alert">
            <strong>Repair orders could not be loaded</strong>
            <span>{errorMessage}</span>
          </div>
        ) : rows.length === 0 ? (
          <div className="db-repair-orders-ledger__empty" role="status">
            <strong>{filtered ? 'No repair orders match this view' : 'No repair orders yet'}</strong>
            <span>{filtered ? 'Adjust the search or status filter.' : 'Create the first repair order when a truck checks in.'}</span>
          </div>
        ) : (
          <div className="db-repair-orders-ledger__rows">
            {rows.map((row) => (
              <button
                type="button"
                key={row.id}
                className="db-repair-orders-ledger__row"
                aria-pressed={selectedId === row.id}
                onClick={() => onOpenOrder(row.id)}
                data-order-id={row.id}
              >
                <span className="db-repair-orders-ledger__order">
                  <strong>{row.orderNumber}</strong>
                  {row.internal && <small>Internal</small>}
                </span>
                <span className={`db-repair-orders-ledger__status db-repair-orders-ledger__status--${row.statusTone}`}>{row.status}</span>
                <span className="db-repair-orders-ledger__work">
                  <strong>{row.description}</strong>
                  <small>{row.customer}</small>
                </span>
                <span className="db-repair-orders-ledger__vehicle">{row.vehicle}</span>
                <span className="db-repair-orders-ledger__money">
                  <strong>{row.total}</strong>
                  <small>{row.updated}</small>
                </span>
              </button>
            ))}
          </div>
        )}

        {totalOrders > 0 && (
          <footer>
            <span>{page * pageSize + 1}–{Math.min((page + 1) * pageSize, totalOrders)} of {totalOrders}</span>
            <div>
              <button type="button" onClick={onPreviousPage} disabled={!canGoPrevious || isPlaceholder} aria-label="Previous repair-order page">
                <ChevronLeft aria-hidden="true" /> Previous
              </button>
              <button type="button" onClick={onNextPage} disabled={!hasMore || isPlaceholder} aria-label="Next repair-order page">
                Next <ChevronRight aria-hidden="true" />
              </button>
            </div>
          </footer>
        )}
      </section>
    </section>
  )
}
