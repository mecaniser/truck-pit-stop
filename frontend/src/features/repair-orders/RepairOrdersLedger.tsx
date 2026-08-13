import { useEffect, useId, useRef, useState } from 'react'
import { ChevronDown, ChevronLeft, ChevronRight, Plus, Search } from 'lucide-react'
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
  showPagination = true,
  onSearchChange,
  onStatusChange,
  onOpenOrder,
  onCreateOrder,
  onShowAllOrders,
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
  showPagination?: boolean
  onSearchChange: (value: string) => void
  onStatusChange: (value: string) => void
  onOpenOrder: (id: string, options?: { focusWorkspace?: boolean }) => void
  onCreateOrder: () => void
  onShowAllOrders: () => void
  onPreviousPage: () => void
  onNextPage: () => void
}) {
  const queueLabel = queueOrigin ? REPAIR_ORDERS_QUEUE_LABEL[queueOrigin] : null
  const filtered = Boolean(searchQuery || statusFilter !== 'all')
  const [scopeMenuOpen, setScopeMenuOpen] = useState(false)
  const scopeControlRef = useRef<HTMLDivElement>(null)
  const scopeTriggerRef = useRef<HTMLButtonElement>(null)
  const scopeMenuId = useId()
  const scopeCount = queueLabel ? `${totalOrders} ${totalOrders === 1 ? 'order' : 'orders'}` : null

  useEffect(() => {
    if (!scopeMenuOpen) return

    const closeOnOutsidePointer = (event: PointerEvent) => {
      if (!scopeControlRef.current?.contains(event.target as Node)) setScopeMenuOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setScopeMenuOpen(false)
      scopeTriggerRef.current?.focus()
    }

    document.addEventListener('pointerdown', closeOnOutsidePointer)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePointer)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [scopeMenuOpen])

  return (
    <section className="db-repair-orders-new" aria-labelledby="repair-orders-title" aria-busy={isFetching}>
      <header className="db-repair-orders-new__header db-operating-page-header">
        <div>
          <h1 id="repair-orders-title">Repair Orders</h1>
          <p>Review and update repair work from check-in through payment.</p>
        </div>
        <button type="button" className="db-repair-orders-new__create" onClick={onCreateOrder} disabled={isFetching && rows.length === 0}>
          <Plus aria-hidden="true" />
          New repair order
        </button>
      </header>

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
          <span className="sr-only">Order status</span>
          <select value={statusFilter} onChange={(event) => onStatusChange(event.target.value)}>
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <ChevronDown aria-hidden="true" />
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
            {!queueLabel && <span>{filtered ? `${totalOrders} matching` : `${totalOrders} total`}</span>}
          </div>
          <div className="db-repair-orders-ledger__header-actions">
            {queueLabel && (
              <div ref={scopeControlRef} className="db-repair-orders-ledger__scope-control">
                <button
                  ref={scopeTriggerRef}
                  type="button"
                  aria-haspopup="menu"
                  aria-expanded={scopeMenuOpen}
                  aria-controls={scopeMenuId}
                  aria-label={`Repair Orders scope: ${queueLabel}${scopeCount ? `, ${scopeCount}` : ''}`}
                  onClick={() => setScopeMenuOpen((open) => !open)}
                >
                  <span>{queueLabel}</span>
                  {scopeCount && <span aria-hidden="true">· {scopeCount}</span>}
                  <ChevronDown aria-hidden="true" />
                </button>
                {scopeMenuOpen && (
                  <div id={scopeMenuId} role="menu" aria-label="Repair Orders scope" className="db-repair-orders-ledger__scope-menu">
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setScopeMenuOpen(false)
                        onShowAllOrders()
                      }}
                    >
                      All repair orders
                    </button>
                  </div>
                )}
              </div>
            )}
            {isFetching && <span className="db-repair-orders-ledger__sync" role="status">Updating…</span>}
          </div>
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
                onKeyDown={(event) => {
                  if (event.key !== 'Enter' && event.key !== ' ') return
                  // Handle keyboard activation ourselves so the browser's
                  // synthetic click cannot restore focus to this row after the
                  // selected workspace has asked to receive it.
                  event.preventDefault()
                  onOpenOrder(row.id, { focusWorkspace: true })
                }}
                onClick={() => {
                  // Pointer selection keeps the operator in the ledger. The
                  // keyboard path above deliberately advances into the named
                  // workspace so the next Tab reaches real repair controls.
                  onOpenOrder(row.id)
                }}
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

        {showPagination && totalOrders > 0 && (
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
