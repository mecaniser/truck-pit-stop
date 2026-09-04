/**
 * The FleetBoard repair-order builder.
 *
 * Same job as the shop's price builder — scope the work, pick the parts,
 * estimate the labor — and the same server: every mutation here goes through
 * the /repair-orders/{id}/price-build/* endpoints, so operation search, learned
 * book time, at-cost fleet parts and the internal labor rate are the shop's
 * implementations, not second copies.
 *
 * Two things make it a different component rather than a mode on the other one:
 *
 *  - The scene. /fleet is an iPad held one-handed next to a truck (PRODUCT.md,
 *    confirmed 2026-08-28). Touch targets clear 44px, overlays are bottom
 *    sheets rather than anchored popovers that a momentum scroll would dismiss,
 *    and nothing depends on hover or a keyboard.
 *  - The money. A fleet manager scopes work; they do not set prices. Lines show
 *    hours and quantities, and the dock shows one cost total for the visit.
 *    There are no per-line prices, no rates, and no discount controls.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, Box, Check, ClipboardList, History, Play, Plus,
  RotateCcw, Search, Trash2, X,
} from 'lucide-react'
import { Spinner } from '@/components/ui'

import BaseSelect from '@/components/BaseSelect'
import DurationStepper from '@/components/DurationStepper'
import QuantityStepper from '@/components/QuantityStepper'
import { formatHoursMinutes } from '@/lib/durationFormat'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import type { PartsUsage, PriceBuildLine, RepairOperationCandidate } from '@/types'

import { SidekickPanel, WO_DRAWER_WIDTH, WO_STATUS_LABEL } from './FleetModals'
import { money } from './helpers'
import {
  useAddAdHocPart, useAddPart, useApplyOperation, useAssignMechanic,
  useCompleteWork, useFleetMechanics, useOperationSearch, usePartSearch,
  usePmServiceCatalog, usePmServices, usePriceBuildSummary, useRemoveLine,
  useRemovePart, useRepairOrderDetail, useSaveDescription, useSetPmServices, useStartWork,
  useUpdateLine, useUpdatePartQuantity,
  type FleetHistoryEvent, type FleetPartOption, type FleetRepairOrderDetail,
} from './priceBuild'

const num = (value: number | string | null | undefined): number =>
  value == null ? 0 : Number(value)

/**
 * Which pricing the truck is on. Both shapes bill parts at cost; they differ
 * only in the labor rate, and that is a per-truck policy set in truck settings,
 * so this is a statement of fact rather than a control.
 */
function pricingChip(detail: FleetRepairOrderDetail): { label: string; tone: string } {
  if (!detail.is_internal) {
    const carrier = detail.customer_company_name
      || [detail.customer_first_name, detail.customer_last_name].filter(Boolean).join(' ')
    return { label: `Billed to ${carrier || 'customer'}`, tone: 'var(--st-shop)' }
  }
  if (detail.bill_labor_at_customer_rate) {
    return { label: 'At-cost parts · customer labor rate', tone: 'var(--yellow)' }
  }
  return { label: 'House account · at cost', tone: 'var(--yellow)' }
}

/** A bottom sheet. Overlays on a scrolling touch surface must not be anchored. */
function Sheet({ title, onClose, children }: {
  title: string; onClose: () => void; children: React.ReactNode
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fleet-sheet-backdrop" role="presentation" onClick={onClose}>
      <div
        className="fleet-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="fleet-sheet-head">
          <strong>{title}</strong>
          <button type="button" className="icon-hit" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="fleet-sheet-body">{children}</div>
      </div>
    </div>
  )
}

type AddMode = 'operation' | 'part'

export default function FleetPriceBuilderPanel({ repairOrderId, onClose, onChanged }: {
  repairOrderId: string
  onClose: () => void
  onChanged: () => void
}) {
  const detailQuery = useRepairOrderDetail(repairOrderId)
  const summaryQuery = usePriceBuildSummary(repairOrderId)
  const { data: mechanics } = useFleetMechanics()

  const detail = detailQuery.data
  const summary = summaryQuery.data

  const [addMode, setAddMode] = useState<AddMode>('operation')
  const [term, setTerm] = useState('')
  const [adHocOpen, setAdHocOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [completeOpen, setCompleteOpen] = useState(false)

  const debouncedTerm = useDebouncedValue(term, 250)

  const notify = () => onChanged()

  const operationSearch = useOperationSearch(repairOrderId)
  const partResults = usePartSearch(addMode === 'part' ? debouncedTerm : '')
  const applyOperation = useApplyOperation(repairOrderId, () => { setTerm(''); notify() })
  const addPart = useAddPart(repairOrderId, () => { setTerm(''); notify() })
  const addAdHoc = useAddAdHocPart(repairOrderId, () => { setAdHocOpen(false); notify() })
  const updateLine = useUpdateLine(repairOrderId)
  const removeLine = useRemoveLine(repairOrderId)
  const updatePart = useUpdatePartQuantity(repairOrderId)
  const removePart = useRemovePart(repairOrderId)
  const assignMechanic = useAssignMechanic(repairOrderId)
  const startWork = useStartWork(repairOrderId)
  const completeWork = useCompleteWork(repairOrderId, () => { notify(); onClose() })

  // Operation search is a POST, so it runs on a settled term rather than on
  // every keystroke.
  const searchRef = useRef(operationSearch)
  searchRef.current = operationSearch
  useEffect(() => {
    if (addMode !== 'operation') return
    const query = debouncedTerm.trim()
    if (query.length < 2) return
    searchRef.current.mutate(query)
  }, [debouncedTerm, addMode])

  const candidates: RepairOperationCandidate[] = operationSearch.data?.candidates ?? []
  const canEdit = summary?.can_edit_work ?? false
  const lines = summary?.lines ?? []
  const parts = summary?.parts ?? []

  /** Parts hang off the line they were added for; the rest stand alone. */
  const partsByLine = useMemo(() => {
    const grouped = new Map<string | null, PartsUsage[]>()
    for (const part of summary?.parts ?? []) {
      const key = part.source_line_id ?? null
      grouped.set(key, [...(grouped.get(key) ?? []), part])
    }
    return grouped
  }, [summary?.parts])

  const loose = partsByLine.get(null) ?? []
  const itemCount = lines.length + parts.length

  if (detailQuery.isLoading || summaryQuery.isLoading) {
    return (
      <Shell title="Repair order" onClose={onClose}>
        <div className="loader"><Spinner size="sm" /></div>
      </Shell>
    )
  }

  if (detailQuery.isError || summaryQuery.isError || !detail || !summary) {
    return (
      <Shell title="Repair order" onClose={onClose}>
        <div className="query-failure" role="alert">
          <AlertTriangle size={20} aria-hidden="true" />
          <div className="query-failure-copy">
            <strong>Repair order could not be loaded</strong>
            <span>Your work was not changed. Check the connection and try again.</span>
          </div>
          <button
            type="button"
            className="query-retry"
            onClick={() => { void detailQuery.refetch(); void summaryQuery.refetch() }}
          >
            <RotateCcw size={14} /> Try again
          </button>
        </div>
      </Shell>
    )
  }

  const chip = pricingChip(detail)
  const started = !['draft', 'quoted'].includes(detail.status)
  const historyEvents: FleetHistoryEvent[] = detail.history_events ?? []

  return (
    <Shell
      title={`${detail.order_number}${detail.is_pm ? ' · PM' : ''}`}
      onClose={onClose}
      footer={(
        // One number: what this visit costs. No per-line money anywhere above.
        <div className="fleet-ro-dock">
          <div className="fleet-ro-dock-total">
            <small>This visit</small>
            <strong>{money(num(summary.total_cost))}</strong>
          </div>
          {!started ? (
            <button
              type="button"
              className="dbtn dbtn-yellow"
              disabled={startWork.isPending}
              onClick={() => startWork.mutate()}
            >
              {startWork.isPending ? <Spinner size="xs" /> : <Play size={16} />} Start work
            </button>
          ) : detail.status === 'in_progress' ? (
            <button
              type="button"
              className="dbtn dbtn-yellow"
              onClick={() => setCompleteOpen(true)}
            >
              <Check size={16} /> Complete
            </button>
          ) : null}
        </div>
      )}
    >
      <div className="wo-drawer-body">
        {/* Which pricing applies, stated where the work is being scoped. */}
        <div className="wo-truckstrip">
          <span style={{ color: chip.tone, fontWeight: 700 }}>{chip.label}</span>
          <span>{WO_STATUS_LABEL[detail.status] || detail.status}</span>
          {detail.vehicle_unit_number && <span>Unit {detail.vehicle_unit_number}</span>}
        </div>

        <div className="wo-builder-grid">
          <div className="wo-builder-main">
            {/* What is wrong with the truck, first — an order opened from the
                yard arrives with nothing said, and the complaint is what the
                mechanic reads before any of the work lines. */}
            <ComplaintSection
              orderId={repairOrderId}
              description={detail.description}
              canEdit={canEdit}
            />

            {/* PM scope is a curated package that drives the odometer roll
                forward on completion, so it stays its own control. The list
                below is for work found while doing the PM. */}
            {detail.is_pm && (
              <PmScopeSection
                orderId={repairOrderId}
                canEdit={detail.status === 'draft'}
              />
            )}

            {/* ---- add ---- */}
            {canEdit && (
              <section className="wo-builder-add">
                <div className="wo-builder-section-head">
                  <h3>Add work</h3>
                  <div className="wo-builder-tabs" role="tablist" aria-label="What to add">
                    {(['operation', 'part'] as AddMode[]).map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        role="tab"
                        aria-selected={addMode === mode}
                        className={addMode === mode ? 'is-active' : undefined}
                        onClick={() => { setAddMode(mode); setTerm('') }}
                      >
                        {mode === 'operation' ? 'Operation' : 'Part'}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="wo-svc-search">
                  <Search size={16} aria-hidden="true" />
                  <input
                    value={term}
                    onChange={(event) => setTerm(event.target.value)}
                    placeholder={addMode === 'operation'
                      ? 'Search operations — brake change, EGR…'
                      : 'Search parts by name or number'}
                    aria-label={addMode === 'operation' ? 'Search operations' : 'Search parts'}
                  />
                  {(operationSearch.isPending || partResults.isFetching) && <Spinner size="xs" />}
                </div>

                {addMode === 'operation' ? (
                  <OperationResults
                    term={debouncedTerm}
                    candidates={candidates}
                    pending={applyOperation.isPending}
                    onAdd={(candidate) => applyOperation.mutate(candidate)}
                  />
                ) : (
                  <PartResults
                    term={debouncedTerm}
                    options={partResults.data ?? []}
                    pending={addPart.isPending}
                    onAdd={(option) => addPart.mutate({
                      inventoryId: option.id,
                      quantity: 1,
                      // A fleet manager standing at the truck can hold a part the
                      // count does not know about; the shortage is recorded, and
                      // stock is still never driven negative.
                      allowStockShortage: option.stock_quantity <= 0,
                    })}
                    onAdHoc={() => setAdHocOpen(true)}
                  />
                )}
              </section>
            )}

            {/* ---- work ---- */}
            <section>
              <div className="wo-draft-section-head">
                <h3>Work &amp; parts</h3>
                <span>{itemCount} item{itemCount === 1 ? '' : 's'}</span>
              </div>

              {itemCount === 0 ? (
                <div className="wo-builder-empty">
                  Nothing added yet. Work you add above lands here.
                </div>
              ) : (
                <div className="wo-builder-lines">
                  {lines.map((line: PriceBuildLine) => (
                    <LineRow
                      key={line.id}
                      line={line}
                      parts={partsByLine.get(line.id) ?? []}
                      canEdit={canEdit}
                      onHours={(hours) => updateLine.mutate({ lineId: line.id, hours })}
                      onRemove={() => removeLine.mutate(line.id)}
                      onPartQuantity={(partUsageId, quantity) =>
                        updatePart.mutate({ partUsageId, quantity })}
                      onPartRemove={(partUsageId) => removePart.mutate(partUsageId)}
                    />
                  ))}
                  {loose.map((part) => (
                    <PartRow
                      key={part.id}
                      part={part}
                      canEdit={canEdit}
                      onQuantity={(quantity) =>
                        updatePart.mutate({ partUsageId: part.id, quantity })}
                      onRemove={() => removePart.mutate(part.id)}
                    />
                  ))}
                </div>
              )}
            </section>

            {/* ---- who / when ---- */}
            <section className="wo-builder-scope">
              <div className="wo-builder-section-head">
                <h3>Assignment</h3>
              </div>
              <div className="fleet-ro-field">
                <span id="fleet-ro-mechanic-label">Mechanic</span>
                <div aria-labelledby="fleet-ro-mechanic-label">
                  <BaseSelect
                    variant="dark"
                    value={detail.assigned_mechanic_id || ''}
                    onChange={(value) => assignMechanic.mutate(value)}
                    options={[
                      { value: '', label: 'Unassigned' },
                      ...(mechanics ?? []).map((m) => ({ value: m.id, label: m.name })),
                    ]}
                  />
                </div>
              </div>
              <button
                type="button"
                className="dbtn dbtn-ghost"
                style={{ marginTop: 12 }}
                onClick={() => setHistoryOpen(true)}
              >
                <History size={15} /> History
                {historyEvents.length > 0 && ` · ${historyEvents.length}`}
              </button>
            </section>
          </div>
        </div>
      </div>

      {adHocOpen && (
        <AdHocPartSheet
          pending={addAdHoc.isPending}
          onClose={() => setAdHocOpen(false)}
          onSubmit={(draft) => addAdHoc.mutate(draft)}
        />
      )}

      {historyOpen && (
        <Sheet title="History" onClose={() => setHistoryOpen(false)}>
          {historyEvents.length === 0 ? (
            <p className="wo-builder-empty-note">Nothing has happened on this order yet.</p>
          ) : (
            <ul className="fleet-ro-history">
              {historyEvents.map((event) => (
                <li key={event.id}>
                  <strong>{event.label}</strong>
                  {event.detail && <small>{event.detail}</small>}
                  <small>
                    {[event.actor_name, new Date(event.created_at).toLocaleString('en-US', {
                      month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
                    })].filter(Boolean).join(' · ')}
                  </small>
                </li>
              ))}
            </ul>
          )}
        </Sheet>
      )}

      {completeOpen && (
        <CompleteSheet
          currentMileage={detail.mileage_in}
          pending={completeWork.isPending}
          onClose={() => setCompleteOpen(false)}
          onSubmit={(mileageOut) => completeWork.mutate(mileageOut)}
        />
      )}
    </Shell>
  )
}

function Shell({ title, onClose, footer, children }: {
  title: string; onClose: () => void; footer?: React.ReactNode; children: React.ReactNode
}) {
  return (
    <SidekickPanel
      onClose={onClose}
      width={WO_DRAWER_WIDTH}
      subtitle="Repair order"
      title={title}
      icon={<ClipboardList size={18} className="text-[var(--yellow)]" />}
      variant="builder"
      tone="repair"
      footer={footer}
    >
      {children}
    </SidekickPanel>
  )
}

/* Complaints a fleet manager writes over and over, standing at the truck.
   Tapping one beats spelling it out on a tablet keyboard; all stay editable. */
const COMPLAINT_CHIPS = [
  'Air leak', 'Brakes', 'Check engine light', 'DOT inspection due', 'Tires',
  'Lights out', 'Coolant leak', 'A/C not cooling', "Won't start", 'Oil leak',
]

/**
 * The complaint: what is wrong with this truck.
 *
 * An order opened from the yard arrives with none — the server no longer
 * stamps a placeholder into the field, because a placeholder looks like
 * someone already described the problem when nobody has.
 */
function ComplaintSection({ orderId, description, canEdit }: {
  orderId: string
  description: string | null
  canEdit: boolean
}) {
  const saveDescription = useSaveDescription(orderId)
  const [draft, setDraft] = useState<string | null>(null)
  const value = draft ?? description ?? ''
  const dirty = draft != null && draft.trim() !== (description ?? '').trim()

  const append = (chip: string) => setDraft((current) => {
    const base = (current ?? description ?? '').trim()
    const already = base.split(/[;,\n]+/).some(
      (token) => token.trim().toLocaleLowerCase() === chip.toLocaleLowerCase(),
    )
    if (already) return base
    return base ? `${base}; ${chip}` : chip
  })

  if (!canEdit) {
    if (!description) return null
    return (
      <section>
        <div className="wo-draft-section-head"><h3>Complaint</h3></div>
        <p className="fleet-ro-complaint-read">{description}</p>
      </section>
    )
  }

  return (
    <section>
      <div className="wo-draft-section-head">
        <h3>Complaint</h3>
        {dirty && <span>Unsaved</span>}
      </div>
      <div className="fleet-ro-field">
        <textarea
          className="fleet-ro-complaint"
          value={value}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="What is wrong with this truck?"
          rows={3}
          aria-label="Complaint"
        />
      </div>
      <div className="wo-chips">
        {COMPLAINT_CHIPS.map((chip) => (
          <button
            type="button"
            key={chip}
            className="wo-chip"
            onClick={() => append(chip)}
          >
            <Plus size={13} /> {chip}
          </button>
        ))}
      </div>
      {dirty && (
        <button
          type="button"
          className="dbtn dbtn-yellow"
          style={{ marginTop: 10 }}
          disabled={saveDescription.isPending}
          onClick={() => saveDescription.mutate(value, {
            onSuccess: () => setDraft(null),
          })}
        >
          {saveDescription.isPending ? <Spinner size="xs" /> : <Check size={15} />} Save complaint
        </button>
      )}
    </section>
  )
}

/**
 * Which services this PM covers. Editable only while the order is a draft —
 * the server rebuilds the PM's seeded labor and parts from this selection, and
 * refuses to do so once work has started.
 */
function PmScopeSection({ orderId, canEdit }: { orderId: string; canEdit: boolean }) {
  const { data: catalog } = usePmServiceCatalog(true)
  const { data: current } = usePmServices(orderId, true)
  const setPmServices = useSetPmServices(orderId)
  const [draft, setDraft] = useState<string[] | null>(null)

  const saved = (current ?? []).map((entry) => entry.service_id)
  const selected = draft ?? saved
  const dirty = draft != null
    && (selected.length !== saved.length || selected.some((id) => !saved.includes(id)))

  const toggle = (id: string) => setDraft(
    selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id],
  )

  return (
    <section>
      <div className="wo-draft-section-head">
        <h3>PM scope</h3>
        <span>{selected.length} selected</span>
      </div>
      <div className="pm-svc-list">
        {(catalog ?? []).length === 0 ? (
          <div className="pm-svc-empty">No PM services in the catalog yet.</div>
        ) : (catalog ?? []).map((service) => {
          const on = selected.includes(service.service_id)
          return (
            <button
              type="button"
              key={service.service_id}
              className={'pm-svc-row' + (on ? ' on' : '')}
              disabled={!canEdit}
              aria-pressed={on}
              onClick={() => toggle(service.service_id)}
            >
              <span className="pm-svc-check">{on && <Check size={13} />}</span>
              <span className="pm-svc-name">{service.name}</span>
              {service.duration_minutes
                ? <span className="pm-svc-dur">{service.duration_minutes}m</span>
                : null}
            </button>
          )
        })}
      </div>
      {canEdit ? (
        dirty && (
          <button
            type="button"
            className="dbtn dbtn-yellow"
            style={{ marginTop: 10 }}
            disabled={setPmServices.isPending}
            onClick={() => setPmServices.mutate(selected, {
              onSuccess: () => setDraft(null),
            })}
          >
            {setPmServices.isPending ? <Spinner size="xs" /> : <Check size={15} />} Save PM scope
          </button>
        )
      ) : (
        <p className="wo-builder-empty-note">
          PM scope is set before work starts. Anything found since goes in the list below.
        </p>
      )}
    </section>
  )
}

function LineRow({ line, parts, canEdit, onHours, onRemove, onPartQuantity, onPartRemove }: {
  line: PriceBuildLine
  parts: PartsUsage[]
  canEdit: boolean
  onHours: (hours: number) => void
  onRemove: () => void
  onPartQuantity: (partUsageId: string, quantity: number) => void
  onPartRemove: (partUsageId: string) => void
}) {
  const [open, setOpen] = useState(false)
  const hours = num(line.hours)

  return (
    <div>
      <div className="wo-builder-line">
        <span className="wo-builder-kind">Work</span>
        <div>
          <button
            type="button"
            className="fleet-ro-line-open"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
          >
            <strong>{line.description}</strong>
            <small>
              {formatHoursMinutes(hours)}
              {parts.length > 0 && ` · ${parts.length} part${parts.length === 1 ? '' : 's'}`}
            </small>
          </button>
        </div>
        <b>{formatHoursMinutes(hours)}</b>
        {canEdit ? (
          <button type="button" className="icon-hit" onClick={onRemove} aria-label={`Remove ${line.description}`}>
            <Trash2 size={16} />
          </button>
        ) : <span />}
      </div>

      {open && (
        <div className="fleet-ro-line-body">
          {canEdit && (
            <div className="fleet-ro-field">
              <span>Labor time</span>
              {/* Debounced: a flurry of taps on glass becomes one request. */}
              <DurationStepper
                hours={hours}
                onChange={onHours}
                theme="dark"
                size="lg"
                commitDebounceMs={600}
                ariaLabel={`Labor time for ${line.description}`}
              />
            </div>
          )}
          {parts.map((part) => (
            <PartRow
              key={part.id}
              part={part}
              canEdit={canEdit}
              nested
              onQuantity={(quantity) => onPartQuantity(part.id, quantity)}
              onRemove={() => onPartRemove(part.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function PartRow({ part, canEdit, nested, onQuantity, onRemove }: {
  part: PartsUsage
  canEdit: boolean
  nested?: boolean
  onQuantity: (quantity: number) => void
  onRemove: () => void
}) {
  return (
    <div className="wo-builder-line" style={nested ? { paddingLeft: 12 } : undefined}>
      <span className="wo-builder-kind">Part</span>
      <div>
        <strong>{part.inventory_name}</strong>
        <small>{part.inventory_sku}</small>
      </div>
      {canEdit ? (
        <QuantityStepper
          value={num(part.quantity)}
          onChange={onQuantity}
          theme="dark"
          size="lg"
          commitDebounceMs={600}
          // Fluids are measured, not counted, so they step fractionally.
          step={part.unit_type === 'each' ? 1 : 0.25}
          ariaLabel={`Quantity of ${part.inventory_name}`}
        />
      ) : (
        <b>{num(part.quantity)}</b>
      )}
      {canEdit ? (
        <button type="button" className="icon-hit" onClick={onRemove} aria-label={`Remove ${part.inventory_name}`}>
          <Trash2 size={16} />
        </button>
      ) : <span />}
    </div>
  )
}

function OperationResults({ term, candidates, pending, onAdd }: {
  term: string
  candidates: RepairOperationCandidate[]
  pending: boolean
  onAdd: (candidate: RepairOperationCandidate) => void
}) {
  if (term.trim().length < 2) {
    return <p className="wo-service-search-empty">Type at least two characters to search.</p>
  }
  if (candidates.length === 0) {
    return <p className="wo-service-search-empty">No operations matched.</p>
  }
  return (
    <ul className="fleet-ro-results">
      {candidates.map((candidate) => (
        <li key={candidate.operation_id}>
          <div>
            <strong>{candidate.name}</strong>
            <small>{formatHoursMinutes(num(candidate.estimated_hours))} book time</small>
          </div>
          <button type="button" className="dbtn dbtn-ghost" disabled={pending} onClick={() => onAdd(candidate)}>
            <Plus size={15} /> Add
          </button>
        </li>
      ))}
    </ul>
  )
}

function PartResults({ term, options, pending, onAdd, onAdHoc }: {
  term: string
  options: FleetPartOption[]
  pending: boolean
  onAdd: (option: FleetPartOption) => void
  onAdHoc: () => void
}) {
  return (
    <>
      {term.trim().length < 2 ? (
        <p className="wo-service-search-empty">Type at least two characters to search.</p>
      ) : options.length === 0 ? (
        <p className="wo-service-search-empty">No parts matched.</p>
      ) : (
        <ul className="fleet-ro-results">
          {options.map((option) => (
            <li key={option.id}>
              <div>
                <strong>{option.name}</strong>
                {/* Availability, not price: it says whether work can start today. */}
                <small>
                  {option.sku} · {option.stock_quantity > 0
                    ? `${option.stock_quantity} on hand`
                    : option.on_order_quantity > 0
                      ? `on order (${option.on_order_quantity})`
                      : 'none on hand'}
                </small>
              </div>
              <button type="button" className="dbtn dbtn-ghost" disabled={pending} onClick={() => onAdd(option)}>
                <Plus size={15} /> Add
              </button>
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="dbtn dbtn-ghost" style={{ marginTop: 10 }} onClick={onAdHoc}>
        <Box size={15} /> Part not in inventory
      </button>
    </>
  )
}

function AdHocPartSheet({ pending, onClose, onSubmit }: {
  pending: boolean
  onClose: () => void
  onSubmit: (draft: { name: string; sku?: string | null; quantity: number; cost: number }) => void
}) {
  const [name, setName] = useState('')
  const [sku, setSku] = useState('')
  const [quantity, setQuantity] = useState(1)
  const [cost, setCost] = useState('')

  const costValue = Number(cost)
  const valid = name.trim().length > 0 && quantity > 0 && cost.trim() !== ''
    && Number.isFinite(costValue) && costValue >= 0

  return (
    <Sheet title="Part not in inventory" onClose={onClose}>
      <label className="fleet-ro-field">
        <span>Part name</span>
        <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Air line fitting" />
      </label>
      <label className="fleet-ro-field">
        <span>Part number <small>optional</small></span>
        <input value={sku} onChange={(event) => setSku(event.target.value)} placeholder="e.g. 0532668000" />
      </label>
      <div className="fleet-ro-field">
        <span>Quantity</span>
        <QuantityStepper
          value={quantity}
          onChange={setQuantity}
          theme="dark"
          size="lg"
          align="start"
          ariaLabel="Quantity"
        />
      </div>
      <label className="fleet-ro-field">
        {/* This creates a real catalogue row, so the number has to be the real
            one — a zero would leave a zero-priced part behind for whoever uses
            it next, and understate what this truck cost. */}
        <span>What it cost</span>
        <input
          value={cost}
          onChange={(event) => setCost(event.target.value)}
          inputMode="decimal"
          placeholder="0.00"
        />
      </label>
      <button
        type="button"
        className="dbtn dbtn-yellow"
        style={{ width: '100%', marginTop: 8 }}
        disabled={!valid || pending}
        onClick={() => onSubmit({
          name, sku: sku || null, quantity, cost: costValue,
        })}
      >
        {pending ? <Spinner size="xs" /> : <Plus size={16} />} Add part
      </button>
    </Sheet>
  )
}

function CompleteSheet({ currentMileage, pending, onClose, onSubmit }: {
  currentMileage: number | null
  pending: boolean
  onClose: () => void
  onSubmit: (mileageOut: number | null) => void
}) {
  const [mileage, setMileage] = useState('')
  const parsed = mileage.trim() === '' ? null : Number(mileage)
  const invalid = parsed != null && (!Number.isFinite(parsed) || parsed < 0)

  return (
    <Sheet title="Complete repair order" onClose={onClose}>
      <label className="fleet-ro-field">
        <span>
          Odometer out <small>optional</small>
        </span>
        <input
          value={mileage}
          onChange={(event) => setMileage(event.target.value)}
          inputMode="numeric"
          placeholder={currentMileage != null ? String(currentMileage) : 'Miles'}
        />
      </label>
      {invalid && <p className="wo-builder-empty-note">Enter a whole number of miles.</p>}
      <button
        type="button"
        className="dbtn dbtn-yellow"
        style={{ width: '100%', marginTop: 8 }}
        disabled={pending || invalid}
        onClick={() => onSubmit(parsed)}
      >
        {pending ? <Spinner size="xs" /> : <Check size={16} />} Complete
      </button>
    </Sheet>
  )
}
