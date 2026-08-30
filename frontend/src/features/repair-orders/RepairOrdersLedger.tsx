import { useEffect, useId, useRef, useState } from 'react'
import { ChevronDown, ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { StaffSearchField } from '@/components/ui'
import { REPAIR_ORDERS_QUEUE_LABEL, type RepairOrdersQueueOrigin } from './repairOrdersPresentation'

export type RepairOrdersLedgerRow = {
  id: string
  orderNumber: string
  status: string
  statusTone: 'neutral' | 'warning' | 'active' | 'success' | 'danger'
  description: string
  total: string
  updated: string
  internal: boolean
  customerName?: string | null
  vehicleYear?: string | number | null
  vehicleMake?: string | null
  vehicleModel?: string | null
  vehicleUnitNumber?: string | null
  vehicleInfo?: string | null
  technicianName?: string | null
  holdReason?: string | null
  quoteSent?: boolean | null
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
  pageTitle = 'Repair Orders',
  pageDescription = 'Review and update repair work from check-in through payment.',
  sectionTitle = 'Order ledger',
  compact = false,
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
  pageTitle?: string
  pageDescription?: string
  /** A daily Shop Work navigator intentionally avoids restating the record
   * identity, status, and financial fields owned by the adjacent workspace. */
  sectionTitle?: string
  compact?: boolean
}) {
  const queueLabel = !compact && queueOrigin ? REPAIR_ORDERS_QUEUE_LABEL[queueOrigin] : null
  const filtered = Boolean(searchQuery || statusFilter !== 'all')
  const [scopeMenuOpen, setScopeMenuOpen] = useState(false)
  const scopeControlRef = useRef<HTMLDivElement>(null)
  const scopeTriggerRef = useRef<HTMLButtonElement>(null)
  const scopeMenuId = useId()
  const [expandedBriefId, setExpandedBriefId] = useState<string | null>(null)
  const [lastLedgerInteractionWasPointer, setLastLedgerInteractionWasPointer] = useState(false)
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
    <section className={`db-repair-orders-new${compact ? ' db-repair-orders-new--compact' : ''}`} aria-labelledby="repair-orders-title" aria-busy={isFetching}>
      <header className="db-repair-orders-new__header db-operating-page-header">
        <div>
          <h1 id="repair-orders-title">{pageTitle}</h1>
          <p>{pageDescription}</p>
        </div>
        <button type="button" className="db-repair-orders-new__create" onClick={onCreateOrder} disabled={isFetching && rows.length === 0}>
          <Plus aria-hidden="true" />
          New repair order
        </button>
      </header>

      <div className="db-repair-orders-new__toolbar">
        <StaffSearchField
          accessibleLabel="Search repair orders"
          className="db-repair-orders-new__search"
          value={searchQuery}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Order, work, customer, or vehicle"
        />
        {!compact && (
          <>
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
          </>
        )}
      </div>

      <section
        className={`db-repair-orders-ledger${compact ? ' db-repair-orders-ledger--compact' : ''}`}
        aria-label="Repair order ledger"
        data-has-pagination={(showPagination && totalOrders > 0) || undefined}
        data-pointer-interaction={lastLedgerInteractionWasPointer || undefined}
        onPointerDownCapture={() => setLastLedgerInteractionWasPointer(true)}
        onKeyDownCapture={() => setLastLedgerInteractionWasPointer(false)}
      >
        <header>
          <div>
            <h2>{sectionTitle}</h2>
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

        {/* The scroller wraps the bordered card so the scrollbar sits outside the
            border; the ledger header and pagination footer stay pinned outside
            the scroller. */}
        <div className="db-operating-surface__scroller">
        <div className="db-repair-orders-ledger__card db-operating-surface__card">
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
          <div
            className="db-repair-orders-ledger__rows"
            role="region"
            aria-label="Scrollable repair-order results"
            tabIndex={0}
          >
            {rows.map((row) => {
              const briefId = `repair-order-brief-${row.id}`
              const workRequestId = `${briefId}-work-request`
              const vehicleGroupId = `${briefId}-vehicle`
              const isOpenInWorkspace = selectedId === row.id
              const isBriefOpen = expandedBriefId === row.id && !isOpenInWorkspace
              const briefFacts = [
                row.customerName ? { label: 'Customer', value: row.customerName } : null,
                row.internal ? { label: 'Order type', value: 'Internal fleet' } : null,
                row.technicianName ? { label: 'Technician', value: row.technicianName } : null,
                row.holdReason ? { label: 'Hold', value: row.holdReason } : null,
                row.quoteSent === true ? { label: 'Estimate', value: 'Sent' } : null,
                row.quoteSent === false ? { label: 'Estimate', value: 'Not sent' } : null,
              ].filter((fact): fact is { label: string; value: string } => fact !== null)
              const vehicleFacts = [
                row.vehicleYear ? { label: 'Year', value: String(row.vehicleYear) } : null,
                row.vehicleMake ? { label: 'Make', value: row.vehicleMake } : null,
                row.vehicleModel ? { label: 'Model', value: row.vehicleModel } : null,
                row.vehicleUnitNumber ? { label: 'Unit number', value: row.vehicleUnitNumber } : null,
              ].filter((fact): fact is { label: string; value: string } => fact !== null)
              const fallbackVehicleInfo = vehicleFacts.length === 0 ? row.vehicleInfo : null
              const vehicleLine = [
                [row.vehicleYear, row.vehicleMake, row.vehicleModel].filter(Boolean).join(' ').trim() || row.vehicleInfo || null,
                row.vehicleUnitNumber ? `Unit ${row.vehicleUnitNumber}` : null,
              ].filter(Boolean).join(' · ') || null

              return (
                <article
                  key={row.id}
                  className="db-repair-orders-ledger__row-shell"
                  aria-label={`Repair order ${row.orderNumber}`}
                  data-order-id={row.id}
                  data-selected={selectedId === row.id}
                  data-inspected={isBriefOpen || undefined}
                >
                  <div className="db-repair-orders-ledger__row">
                    <button
                      type="button"
                      className="db-repair-orders-ledger__record"
                      aria-label={`Open repair order ${row.orderNumber}`}
                      onKeyDown={(event) => {
                        if (event.key !== 'Enter' && event.key !== ' ') return
                        event.preventDefault()
                        onOpenOrder(row.id, { focusWorkspace: true })
                      }}
                      onClick={() => onOpenOrder(row.id)}
                    >
                      <span className="db-repair-orders-ledger__order">
                        <span className="db-repair-orders-ledger__order-line">
                          {/* The shop identifies work by who it is for and which
                              truck, so those lead. The order number stays on the
                              row as reference, below the identity. */}
                          <strong>{row.customerName || row.orderNumber}</strong>
                          <span className={`db-repair-orders-ledger__status db-repair-orders-ledger__status--${row.statusTone}`}>{row.status}</span>
                          {row.internal && <small>Internal</small>}
                        </span>
                        {vehicleLine && <span className="db-repair-orders-ledger__vehicle">{vehicleLine}</span>}
                        {row.customerName && <small className="db-repair-orders-ledger__reference">{row.orderNumber}</small>}
                      </span>
                      {/* The work itself belongs between the identity and the
                          money, where the row was otherwise empty. One clipped
                          line only — the full request stays in the brief. */}
                      <span className="db-repair-orders-ledger__work">{row.description}</span>
                      <span className="db-repair-orders-ledger__money">
                        <strong>{row.total}</strong>
                        <small>{row.updated}</small>
                      </span>
                    </button>
                    {!isOpenInWorkspace && <button
                      type="button"
                      className="db-repair-orders-ledger__details-toggle"
                      aria-expanded={isBriefOpen}
                      aria-controls={briefId}
                      aria-label={`${isBriefOpen ? 'Hide' : 'Show'} details for ${row.orderNumber}`}
                      onClick={(event) => {
                        event.stopPropagation()
                        setExpandedBriefId((current) => current === row.id ? null : row.id)
                      }}
                    >
                      <span aria-hidden="true">Details</span>
                      <ChevronDown aria-hidden="true" />
                    </button>}
                  </div>
                  {isBriefOpen && (
                    <section id={briefId} className="db-repair-orders-ledger__brief" aria-label={`Order brief for ${row.orderNumber}`}>
                      <div className="db-repair-orders-ledger__brief-content">
                        <section className="db-repair-orders-ledger__work-request" aria-labelledby={workRequestId}>
                          <h3 id={workRequestId}>Work requested</h3>
                          <p>{row.description}</p>
                        </section>
                        {briefFacts.length > 0 && (
                          <dl className="db-repair-orders-ledger__brief-facts">
                            {briefFacts.map((fact) => (
                              <div key={fact.label}>
                                <dt>{fact.label}</dt>
                                <dd>{fact.value}</dd>
                              </div>
                            ))}
                          </dl>
                        )}
                        {(vehicleFacts.length > 0 || fallbackVehicleInfo) && (
                          <section className="db-repair-orders-ledger__vehicle-group" aria-labelledby={vehicleGroupId}>
                            <h3 id={vehicleGroupId}>Vehicle</h3>
                            {vehicleFacts.length > 0 ? (
                              <dl>
                                {vehicleFacts.map((fact) => (
                                  <div key={fact.label}>
                                    <dt>{fact.label}</dt>
                                    <dd>{fact.value}</dd>
                                  </div>
                                ))}
                              </dl>
                            ) : (
                              <p className="db-repair-orders-ledger__vehicle-fallback">{fallbackVehicleInfo}</p>
                            )}
                          </section>
                        )}
                      </div>
                      {/* The workspace beside the list is already showing this
                          order, so the control would take you where you are.
                          The ledger is hidden entirely at widths where the
                          workspace is not visible, so a selected row here always
                          means an open workspace. */}
                      {selectedId !== row.id && <button
                        type="button"
                        className="db-repair-orders-ledger__open-workspace"
                        aria-label={`Open repair order ${row.orderNumber} from details`}
                        onKeyDown={(event) => {
                          if (event.key !== 'Enter' && event.key !== ' ') return
                          event.preventDefault()
                          onOpenOrder(row.id, { focusWorkspace: true })
                        }}
                        onClick={(event) => {
                          event.stopPropagation()
                          onOpenOrder(row.id)
                        }}
                      >
                        Open repair order
                        <ChevronRight aria-hidden="true" />
                      </button>}
                    </section>
                  )}
                </article>
              )
            })}
          </div>
        )}
        </div>
        </div>

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
