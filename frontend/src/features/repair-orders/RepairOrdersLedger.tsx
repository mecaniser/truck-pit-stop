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
  statusOptions: Array<{ value: string; label: string; count?: number }>
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
  const statusMenu = useRef<HTMLDivElement>(null)
  const [statusOpen, setStatusOpen] = useState(false)
  // A menu closes when you look away from it, not only on a second click.
  useEffect(() => {
    if (!statusOpen) return
    const closeOutside = (event: MouseEvent | FocusEvent) => {
      const target = event.target as Node | null
      if (target && statusMenu.current?.contains(target)) return
      setStatusOpen(false)
    }
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setStatusOpen(false)
      statusMenu.current?.querySelector('button')?.focus()
    }
    document.addEventListener('pointerdown', closeOutside)
    document.addEventListener('focusin', closeOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOutside)
      document.removeEventListener('focusin', closeOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [statusOpen])
  const [expandedBriefId, setExpandedBriefId] = useState<string | null>(null)
  // A brief unmounted the instant it closed, so it could only ever animate in.
  // Keeping the closing one mounted until its transition ends lets it leave
  // along the path it arrived on, which is what makes the list stop jumping.
  const [mountedBriefId, setMountedBriefId] = useState<string | null>(null)
  useEffect(() => {
    if (expandedBriefId) setMountedBriefId(expandedBriefId)
  }, [expandedBriefId])
  const prefersReducedMotion = typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  // transitionend is the fast path, not the guarantee: it never fires when
  // motion is reduced, and it can be missed if the element is hidden or the
  // transition is interrupted. Without a floor the closed brief would stay in
  // the DOM for the rest of the session.
  useEffect(() => {
    if (expandedBriefId || mountedBriefId === null) return
    const timer = window.setTimeout(() => setMountedBriefId(null), prefersReducedMotion ? 0 : 320)
    return () => window.clearTimeout(timer)
  }, [expandedBriefId, mountedBriefId, prefersReducedMotion])
  // The work request belongs to whichever surface has room for it. With no
  // workspace open the list owns the page and the row carries it; once one
  // opens the column is too narrow, so the brief takes it back. Rendered rather
  // than hidden in CSS, so it is never read out twice by assistive tech.
  // The daily Shop Work navigator is a narrow column too, so it reads like an
  // open workspace here.
  const requestOnRow = !selectedId && !compact
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
        <button type="button" className="db-repair-orders-new__create" aria-label="New repair order" onClick={onCreateOrder} disabled={isFetching && rows.length === 0}>
          <Plus aria-hidden="true" />
          <span className="db-repair-orders-new__create-label">New repair order</span>
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
            {/* The narrow column used a native select, which renders OS chrome
                that ignores the appearance mode and states the current filter
                only after you open it. A listbox keeps the control on one line,
                names the active status on its face, and is themed like the rest
                of the surface. */}
            <div className="db-repair-orders-new__status-select" ref={statusMenu}>
              <button
                type="button"
                aria-haspopup="listbox"
                aria-expanded={statusOpen}
                aria-label="Order status"
                onClick={() => setStatusOpen((current) => !current)}
              >
                <span>{statusOptions.find((option) => option.value === statusFilter)?.label ?? 'All'}</span>
                <ChevronDown aria-hidden="true" />
              </button>
              {statusOpen && (
                <ul role="listbox" aria-label="Order status options">
                  {statusOptions.map((option) => (
                    <li key={option.value} role="presentation">
                      <button
                        type="button"
                        role="option"
                        aria-selected={option.value === statusFilter}
                        onClick={() => {
                          onStatusChange(option.value)
                          setStatusOpen(false)
                        }}
                      >
                        <span>{option.label}</span>
                        {option.count !== undefined && <span className="db-repair-orders-new__status-count">{option.count}</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="db-repair-orders-new__status-tabs" role="group" aria-label="Filter repair orders by status">
              {statusOptions.map((option) => (
                <button
                  type="button"
                  key={option.value}
                  aria-pressed={statusFilter === option.value}
                  onClick={() => onStatusChange(option.value)}
                >
                  {option.label}
                  {option.count !== undefined && <span className="db-repair-orders-new__status-count">{option.count}</span>}
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
              const isOpenInWorkspace = selectedId === row.id
              const isBriefOpen = expandedBriefId === row.id && !isOpenInWorkspace
              const isBriefMounted = mountedBriefId === row.id && !isOpenInWorkspace
              const briefFacts = [
                row.internal ? { label: 'Order type', value: 'Internal fleet' } : null,
                row.technicianName ? { label: 'Technician', value: row.technicianName } : null,
                row.holdReason ? { label: 'Hold', value: row.holdReason } : null,
                row.quoteSent === true ? { label: 'Estimate', value: 'Sent' } : null,
                row.quoteSent === false ? { label: 'Estimate', value: 'Not sent' } : null,
              ].filter((fact): fact is { label: string; value: string } => fact !== null)
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
                      {requestOnRow && <span className="db-repair-orders-ledger__work">{row.description}</span>}
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
                  {isBriefMounted && (
                    <div
                      className="db-repair-orders-ledger__brief-reveal"
                      data-closing={!isBriefOpen || undefined}
                      // The brief is on its way out: stop announcing it and stop
                      // it taking clicks while it plays the exit.
                      aria-hidden={!isBriefOpen || undefined}
                      onTransitionEnd={(event) => {
                        if (event.target !== event.currentTarget) return
                        if (event.propertyName !== 'grid-template-rows') return
                        if (!isBriefOpen) setMountedBriefId((current) => current === row.id ? null : current)
                      }}
                    >
                    <section id={briefId} className="db-repair-orders-ledger__brief" aria-label={`Order brief for ${row.orderNumber}`}>
                      <div className="db-repair-orders-ledger__brief-content">
                        {!requestOnRow && (
                          <section className="db-repair-orders-ledger__work-request" aria-labelledby={workRequestId}>
                            <h3 id={workRequestId}>Work requested</h3>
                            <p>{row.description}</p>
                          </section>
                        )}
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
                    </div>
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
