import { ControlButton } from '@/components/ui/Controls'
import './repairOrderSchedule.css'
import './repairOrderControls.css'
import './repairOrderMotion.css'
import './importedBilling.css'
import { ImportedBillingSourceLink } from './ImportedBillingSourceLink'
import { importedBillingWarnings } from './importedBillingWarnings'
import { importedMoney, importedPaymentLabel, importedBillingSeverity, type ImportedBilling } from './importedBilling'
import { type ReactNode, useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, ChevronRight, Plus, TriangleAlert } from 'lucide-react'
import { RepairOrderListFilter, type OrderListView } from './RepairOrderListFilter'
import { StaffSearchField } from '@/components/ui'
import type { RepairOrdersQueueOrigin } from './repairOrdersPresentation'

export type RepairOrdersLedgerRow = {
  id: string
  orderNumber: string
  status: string
  statusTone: 'neutral' | 'warning' | 'active' | 'success' | 'danger'
  description: string
  total: string
  importedBilling?: ImportedBilling | null
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
  deadline?: string | null
  overdue?: boolean
  scheduledStart?: string | null
}

export default function RepairOrdersLedger({
  notice,
  rows,
  totalOrders,
  searchQuery,
  statusFilter,
  statusOptions,
  selectedId,
  queueOrigin,
  allowQueueViews = true,
  partialQueue = false,
  isFetching,
  errorMessage,
  loadedCount,
  hasMore,
  isLoadingMore,
  showPagination = true,
  autoLoadEnabled = true,
  onSearchChange,
  onStatusChange,
  onOpenOrder,
  onCreateOrder,
  onViewChange,
  onLoadMore,
  pageTitle = 'Repair Orders',
  pageDescription = 'Review and update repair work from check-in through payment.',
  sectionTitle = 'Order ledger',
  compact = false,
  valueSummary,
  valueSummaryLoading = false,
  valueSummaryError = false,
  valueSummaryLabel = 'Filtered order value',
  hideValueSummary = false,
  overdue = false,
  onOverdueChange,
}: {
  notice?: ReactNode
  rows: RepairOrdersLedgerRow[]
  totalOrders: number
  searchQuery: string
  statusFilter: string
  statusOptions: Array<{ value: string; label: string; count?: number }>
  selectedId: string | null
  queueOrigin: RepairOrdersQueueOrigin | null
  allowQueueViews?: boolean
  partialQueue?: boolean
  isFetching: boolean
  errorMessage?: string | null
  loadedCount: number
  hasMore: boolean
  isLoadingMore: boolean
  showPagination?: boolean
  /** The ledger may remain mounted behind intake or a compact record. */
  autoLoadEnabled?: boolean
  onSearchChange: (value: string) => void
  onStatusChange: (value: string) => void
  onOpenOrder: (id: string, options?: { focusWorkspace?: boolean }) => void
  onCreateOrder: () => void
  onViewChange: (view: OrderListView) => void
  onLoadMore: () => void
  pageTitle?: string
  pageDescription?: string
  /** A daily Shop Work navigator intentionally avoids restating the record
   * identity, status, and financial fields owned by the adjacent workspace. */
  sectionTitle?: string
  compact?: boolean
  valueSummary?: { order_count: number; order_value: string } | null
  valueSummaryLoading?: boolean
  valueSummaryError?: boolean
  overdue?: boolean
  onOverdueChange?: (enabled: boolean) => void
  valueSummaryLabel?: string
  hideValueSummary?: boolean
}) {
  const filtered = Boolean(queueOrigin || searchQuery || statusFilter !== 'all' || overdue)
  const loadMoreSentinelRef = useRef<HTMLDivElement | null>(null)
  const onLoadMoreRef = useRef(onLoadMore)
  useEffect(() => { onLoadMoreRef.current = onLoadMore }, [onLoadMore])
  // Use the viewport, which also clips through scrolling ancestors. On compact
  // screens the list wrapper grows with its content: using it as the root makes
  // the sentinel permanently intersect and drains every server page unseen.
  useEffect(() => {
    const node = loadMoreSentinelRef.current
    if (!node || !showPagination || !autoLoadEnabled || !hasMore || isFetching || isLoadingMore || errorMessage) return
    if (typeof IntersectionObserver === 'undefined') return
    let active = true
    const observer = new IntersectionObserver(
      (entries) => {
        if (!active || !entries.some((entry) => entry.isIntersecting)) return
        // One request per observed page, including callbacks already queued
        // when a dialog opens, filters change, or the observer disconnects.
        active = false
        observer.disconnect()
        onLoadMoreRef.current()
      },
      { root: null, rootMargin: '320px 0px' },
    )
    observer.observe(node)
    return () => { active = false; observer.disconnect() }
  }, [showPagination, autoLoadEnabled, hasMore, isFetching, isLoadingMore, errorMessage, loadedCount])

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
  return (
    <section className={`db-repair-orders-new db-repair-orders-controls${compact ? ' db-repair-orders-new--compact' : ''}`} aria-labelledby="repair-orders-title" aria-busy={isFetching}>
      {notice}
      <header className="db-repair-orders-new__header db-operating-page-header">
        <div>
          <h1 id="repair-orders-title">{pageTitle}</h1>
          <p>{pageDescription}</p>
        </div>
        <ControlButton controlKind="icon" type="button" className="db-repair-orders-new__create" aria-label="New repair order" onClick={onCreateOrder} disabled={isFetching && rows.length === 0}>
          <Plus aria-hidden="true" />
          <span className="db-repair-orders-new__create-label">New repair order</span>
        </ControlButton>
      </header>

      <div className="db-repair-orders-new__toolbar">
        <StaffSearchField
          accessibleLabel="Search repair orders"
          className="db-repair-orders-new__search"
          value={searchQuery}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Order, customer, or truck"
        />
          {compact && onOverdueChange && <ControlButton controlKind="action" type="button" className="db-order-overdue-filter" aria-pressed={overdue} onClick={() => onOverdueChange(!overdue)}>
            {overdue && <Check aria-hidden="true" />}
            <span>{queueOrigin || compact && !overdue ? 'All overdue work' : 'Overdue'}</span>
          </ControlButton>}
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
          <div className="db-repair-orders-ledger__caption">
            <h2 className={compact ? undefined : 'sr-only'}>{sectionTitle}</h2>
            {!compact && <RepairOrderListFilter
              view={queueOrigin ?? (overdue ? 'overdue' : 'all')}
              allowQueueViews={allowQueueViews}
              status={statusFilter}
              options={statusOptions}
              onViewChange={onViewChange}
              onStatusChange={onStatusChange}
            />}
            <span>{partialQueue ? `${totalOrders} shown` : queueOrigin ? `${totalOrders} ${totalOrders === 1 ? 'order' : 'orders'}` : filtered ? `${totalOrders} matching` : `${totalOrders} total`}</span>
          </div>
          <div className="db-repair-orders-ledger__totals">
            {!hideValueSummary && <div className="db-repair-orders-ledger__value-summary" aria-live="polite">
              <span className="sr-only">{valueSummaryLabel}</span>
              <strong>
                {valueSummaryLoading
                  ? 'Calculating…'
                  : valueSummaryError
                    ? 'Unavailable'
                    : Number.parseFloat(valueSummary?.order_value ?? '0').toLocaleString('en-US', {
                      style: 'currency',
                      currency: 'USD',
                    })}
              </strong>
            </div>}
            {isFetching && <span className="db-repair-orders-ledger__sync sr-only" role="status">Updating…</span>}
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
            <span>{filtered ? (partialQueue ? 'Try All repair orders to search beyond this queue.' : 'Change the view, status, or search.') : 'Create the first repair order when a truck checks in.'}</span>
          </div>
        ) : (
          <div
            className="db-repair-orders-ledger__rows"
            role="region"
            aria-label="Scrollable repair-order results"
            tabIndex={0}
          >
            {rows.map((row) => {
              const billingSeverity = row.importedBilling ? importedBillingSeverity(row.importedBilling) : null
              const briefId = `repair-order-brief-${row.id}`
              const workRequestId = `${briefId}-work-request`
              const isOpenInWorkspace = selectedId === row.id
              const isBriefOpen = expandedBriefId === row.id && !isOpenInWorkspace
              const isBriefMounted = mountedBriefId === row.id && !isOpenInWorkspace
              const briefFacts = [
                row.scheduledStart ? { label: 'Scheduled start', value: row.scheduledStart } : null,
                row.deadline ? { label: 'Promised finish', value: row.deadline } : null,
                row.internal ? { label: 'Order type', value: 'Internal fleet' } : null,
                row.technicianName ? { label: 'Technician', value: row.technicianName } : null,
                row.holdReason ? { label: 'Hold', value: row.holdReason } : null,
                row.quoteSent === true ? { label: 'Estimate', value: 'Sent' } : null,
                row.quoteSent === false ? { label: 'Estimate', value: 'Not sent' } : null,
              ].filter((fact): fact is { label: string; value: string } => fact !== null)
              const vehicleLine = [
                row.vehicleUnitNumber ? `Unit ${row.vehicleUnitNumber}` : null,
                [row.vehicleYear, row.vehicleMake, row.vehicleModel].filter(Boolean).join(' ').trim() || row.vehicleInfo || null,
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
                    <ControlButton controlKind="content"
                      type="button"
                      className="db-repair-orders-ledger__record"
                      data-has-deadline={!!row.deadline || undefined}
                      id={`repair-open-${row.id}`} aria-label={`Open repair order ${row.orderNumber}`}
                      aria-current={isOpenInWorkspace ? 'true' : undefined}
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
                          {row.internal && <small>Internal</small>}
                        </span>
                        {vehicleLine && <span className="db-repair-orders-ledger__vehicle">{vehicleLine}</span>}
                        <span className="db-queue-reference">
                          <span className={`db-repair-orders-ledger__status db-repair-orders-ledger__status--${row.statusTone}`}>{row.status}</span>
                          {row.customerName && <small className="db-repair-orders-ledger__reference">{row.orderNumber}</small>}
                        </span>
                      </span>
                      {requestOnRow && <span className="db-repair-orders-ledger__work">{row.description}</span>}
                      <span className="db-repair-orders-ledger__money">
                        <strong>{row.total}{billingSeverity?.tone === 'warning' && <span className="db-imported-billing-ledger-warning" role="img" aria-label={billingSeverity.description} title={billingSeverity.description}><TriangleAlert className="h-3.5 w-3.5" aria-hidden="true" /></span>}</strong>
                        {!row.deadline && <small>{row.updated}</small>}
                      </span>
                      {row.importedBilling && (row.importedBilling.payment_status !== 'unverified' || row.importedBilling.shared_invoice) && <span className="db-imported-billing-row" aria-label="ETS invoice payment status">
                        {row.importedBilling.payment_status !== 'unverified' && <span>{importedPaymentLabel(row.importedBilling.payment_status)}</span>}
                        {billingSeverity?.remaining !== 'Unavailable' && <span>Remaining <strong>{importedMoney(row.importedBilling.recorded_remaining_amount)}</strong></span>}
                        {row.importedBilling.shared_invoice && <span>Shared ETS invoice</span>}
                      </span>}
                      {row.deadline && <span className="db-order-schedule-deadline db-order-schedule-ledger-date" data-overdue={row.overdue || undefined} title={row.deadline}>{row.deadline}</span>}
                    </ControlButton>
                    {!isOpenInWorkspace && <ControlButton controlKind="action"
                      type="button"
                      className="db-repair-orders-ledger__details-toggle"
                      aria-expanded={isBriefOpen}
                      aria-controls={briefId}
                      aria-label={`${isBriefOpen ? 'Hide' : 'Show'} preview for ${row.orderNumber}`}
                      onClick={(event) => {
                        event.stopPropagation()
                        setExpandedBriefId((current) => current === row.id ? null : row.id)
                      }}
                    >
                      <span aria-hidden="true">Preview</span>
                      <ChevronDown aria-hidden="true" />
                    </ControlButton>}
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
                        {billingSeverity?.tone === 'warning' && <section className="db-imported-billing-review" aria-label="Why billing needs attention">
                          <h3><TriangleAlert className="h-4 w-4" aria-hidden="true" />Billing needs attention</h3>
                          <ul>{importedBillingWarnings(row.importedBilling).map(reason => <li key={reason}>{reason}</li>)}</ul>
                          <div className="mt-2"><ImportedBillingSourceLink url={row.importedBilling?.source_invoice_url} /></div>
                        </section>}
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
                      {selectedId !== row.id && <ControlButton
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
                      </ControlButton>}
                    </section>
                    </div>
                  )}
                </article>
              )
            })}
          </div>
        )}
        {/* Watched by the observer below: once this reaches the viewport the
            next page is already being fetched, so the list continues without
            the operator asking. The button in the footer stays as the explicit
            path for keyboards, screen readers, and any browser where the
            observer never fires. */}
        {showPagination && isLoadingMore && (
          <div className="db-repair-orders-ledger__pending" aria-hidden="true">
            {[0, 1, 2].map((index) => (
              <div key={index} className="db-repair-orders-ledger__skeleton">
                <span className="db-repair-orders-ledger__skeleton-line is-name" />
                <span className="db-repair-orders-ledger__skeleton-line is-vehicle" />
                <span className="db-repair-orders-ledger__skeleton-line is-reference" />
                <span className="db-repair-orders-ledger__skeleton-line is-amount" />
              </div>
            ))}
          </div>
        )}
        {showPagination && hasMore && <div ref={loadMoreSentinelRef} aria-hidden="true" style={{ blockSize: 1 }} />}
        </div>
        </div>

        {showPagination && totalOrders > 0 && (
          <footer>
            <span aria-live="polite">
              {hasMore ? `${loadedCount} of ${totalOrders} loaded` : `${totalOrders} order${totalOrders === 1 ? '' : 's'}`}
            </span>
            {hasMore && (
              <ControlButton
                type="button"
                onClick={onLoadMore}
                disabled={isFetching || isLoadingMore}
                aria-label={`Load more repair orders, ${loadedCount} of ${totalOrders} loaded`}
              >
                {isLoadingMore && <span className="db-repair-orders-ledger__spinner" aria-hidden="true" />}
                {isLoadingMore ? 'Loading' : 'Load more'}
              </ControlButton>
            )}
          </footer>
        )}
      </section>
    </section>
  )
}
