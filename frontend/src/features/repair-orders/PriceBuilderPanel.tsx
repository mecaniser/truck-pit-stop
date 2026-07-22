import { type ChangeEvent, type MouseEvent as ReactMouseEvent, useEffect, useRef, useState } from 'react'
import { Spinner } from '@/components/ui'
import { createPortal } from 'react-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import {
  AlertTriangle,
  Box,
  Building2,
  Camera,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  CreditCard,
  FileText,
  Gauge,
  History,
  Mail,
  Play,
  Plus,
  RotateCcw,
  Search,
  Tag,
  Trash2,
  Truck,
  Wrench,
  X,
} from 'lucide-react'

import api from '@/lib/api'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import QuantityStepper from '@/components/QuantityStepper'
import DurationStepper from '@/components/DurationStepper'
import { formatHoursMinutes } from '@/lib/durationFormat'
import { formatFileSize, isSupportedPhotoFile, runPhotoUploadQueue, uploadDirectPhoto, type PhotoUploadStatus } from '@/lib/photoUpload'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'
import {
  PartsUsage,
  PartSuggestionsResponse,
  PriceBuildSummary,
  InventoryItem,
  Invoice,
  RecommendedService,
  RecommendedServicePriority,
  RepairOrderPhoto,
  RepairOperationCandidate,
  RepairOrderStatus,
} from '@/types'

// Human labels for the Payment.method enum.
const PAYMENT_METHOD_LABELS: Record<string, string> = {
  stripe: 'Card',
  cash: 'Cash',
  check: 'Check',
  ach: 'ACH transfer',
  zelle: 'Zelle',
  fleet_payment: 'Fleet payment',
  other: 'Other',
}

type TechnicianOption = {
  mechanic_id: string
  mechanic_name: string
  assigned_count?: number
  in_progress_count?: number
}

export type PriceBuilderHistoryEvent = {
  id: string
  label: string
  at: string
  detail?: string
  actor?: string
}

type AddBarType = 'operation' | 'saved_labor' | 'part' | 'history'

type RepairPhotoUploadItem = {
  id: string
  file: File
  name: string
  size: number
  status: PhotoUploadStatus
  progress: number
  error?: string
}

type InventoryTypeaheadItem = Pick<
  InventoryItem,
  'id' | 'sku' | 'name' | 'stock_quantity' | 'on_order_quantity' | 'unit_type' | 'cost' | 'selling_price'
>

type PartAddRequest = {
  inventoryId: string
  quantity: number
  sourceServiceId?: string | null
  sourceLineId?: string | null
  quantityKey?: string
  allowStockShortage?: boolean
}

type StockShortage = {
  inventoryId: string
  requestedQuantity: string
  requiredPackages: number
  availablePackages: number
  shortfallPackages: number
}

type LineWarning = {
  code: string
  message: string
  line_id?: string | null
}

type Props = {
  orderId: string
  orderStatus: RepairOrderStatus
  canEdit: boolean
  isInternalOrder?: boolean
  defaultLaborRate?: number
  description?: string | null
  orderNumber?: string
  navigationLabel?: string
  customerName?: string
  vehicleLabel?: string
  vehicleUnit?: string | null
  vehicleVin?: string | null
  vehicleYear?: number | null
  vehicleMake?: string | null
  vehicleModel?: string | null
  customerEmail?: string | null
  customerPhone?: string | null
  vehiclePlate?: string | null
  mileageIn?: number | null
  mileageOut?: number | null
  poNumber?: string | null
  orderTypeLabel?: string
  quoteNumber?: string | null
  quoteIsSent?: boolean
  quoteIsApproved?: boolean
  quoteActionLabel?: string
  quoteActionPending?: boolean
  quoteActionDisabled?: boolean
  quoteDisabledReason?: string
  onQuoteAction?: () => void
  assignedTechnicianName?: string | null
  assignedTechnicianId?: string | null
  technicianOptions?: TechnicianOption[]
  technicianAssignmentPending?: boolean
  onAssignTechnician?: (mechanicId: string) => void
  technicianOverridePending?: boolean
  onOverrideTechnicianAssignment?: () => void
  completionMode?: boolean
  completionPending?: boolean
  mileageOutValue?: string
  onMileageOutChange?: (value: string) => void
  reviewNotesValue?: string
  onReviewNotesChange?: (value: string) => void
  showReviewNotes?: boolean
  onToggleReviewNotes?: () => void
  onApproveCompletion?: () => void
  onStartWorkOrder?: () => void
  startWorkOrderPending?: boolean
  onCompleteWorkOrder?: (mileageOut: number | null) => void
  completeWorkOrderPending?: boolean
  onAdminCompleteWork?: () => void
  adminCompleteWorkPending?: boolean
  invoiceCreatePending?: boolean
  invoiceDueDateValue?: string
  showInvoiceCreateOptions?: boolean
  onToggleInvoiceCreateOptions?: () => void
  onInvoiceDueDateChange?: (value: string) => void
  onCreateInvoice?: (dueDate?: string | null) => void
  invoice?: Invoice | null
  invoiceActionPending?: boolean
  onResendInvoice?: () => void
  onRecordPayment?: () => void
  onVoidInvoice?: () => void
  historyEvents?: PriceBuilderHistoryEvent[]
  onClose?: () => void
  onPrev?: () => void
  onNext?: () => void
  prevDisabled?: boolean
  nextDisabled?: boolean
  showDangerActions?: boolean
  onToggleDangerActions?: () => void
  onDeleteOrder?: () => void
  deletePending?: boolean
  isDeleted?: boolean
  deletedByName?: string | null
  deletedAt?: string | null
  onRestoreOrder?: () => void
  restorePending?: boolean
  onReopenWorkOrder?: () => void
  reopenPending?: boolean
  recommendedServices?: RecommendedService[]
  recommendedServicesLoading?: boolean
  showAddRecommendedService?: boolean
  recommendedServiceForm?: {
    description: string
    priority: RecommendedServicePriority
    estimated_cost: string
    notes: string
  }
  onToggleAddRecommendedService?: () => void
  onRecommendedServiceFormChange?: (next: {
    description: string
    priority: RecommendedServicePriority
    estimated_cost: string
    notes: string
  }) => void
  onAddRecommendedService?: () => void
  onResolveRecommendedService?: (serviceId: string) => void
  onDeleteRecommendedService?: (serviceId: string) => void
  addRecommendedPending?: boolean
  resolveRecommendedPending?: boolean
  deleteRecommendedPending?: boolean
  onRecommendedServicesOpenChange?: (open: boolean) => void
  onUpdated?: () => void
  initialLineWarnings?: LineWarning[]
}

type SearchResponse = {
  candidates: RepairOperationCandidate[]
  warnings: { code: string; message: string }[]
}

type LaborBookTimeEntry = {
  id: string
  operation_name: string
  operation_description: string | null
  normalized_hours: string
  vehicle_year: number | null
  vehicle_make: string | null
  vehicle_model: string | null
  vehicle_type: string | null
  body_class: string | null
  engine: string | null
  fuel_type: string | null
  engine_cylinders: number | null
  engine_displacement_l: number | null
  gvwr: string | null
  vin_sample: string | null
  vehicle_signature: string
  component_signature: string | null
  operation_key: string
  provider_operation_id: string | null
  source_provider: string
  usage_count: number
  last_used_at: string
}

type LaborBookTimeForm = {
  operation_name: string
  operation_description: string
  normalized_hours: string
  vehicle_year: string
  vehicle_make: string
  vehicle_model: string
  vehicle_type: string
  body_class: string
  engine: string
  fuel_type: string
  engine_cylinders: string
  engine_displacement_l: string
  gvwr: string
  vin_sample: string
}

type VinDecodeResult = {
  vin: string
  make?: string | null
  model?: string | null
  year?: number | null
  vehicle_type?: string | null
  body_class?: string | null
  fuel_type?: string | null
  engine_cylinders?: number | null
  engine_displacement_l?: number | null
  gvwr?: string | null
  error_text?: string | null
}

function money(value: number | string | null | undefined) {
  const parsed = typeof value === 'number' ? value : parseFloat(value || '0')
  return `$${(Number.isFinite(parsed) ? parsed : 0).toFixed(2)}`
}

function errorDetail(error: unknown, fallback: string) {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: unknown } } }).response
    const detail = response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
  }
  return fallback
}

function partAddKey(inventoryId: string, sourceLineId?: string | null) {
  return `${sourceLineId || 'standalone'}:${inventoryId}`
}

function partQuantityKey(partId: string) {
  return `usage:${partId}`
}

function stockShortageFromError(error: unknown): StockShortage | null {
  if (typeof error !== 'object' || error === null || !('response' in error)) return null
  const response = (error as { response?: { data?: { detail?: unknown } } }).response
  const detail = response?.data?.detail
  if (typeof detail !== 'object' || detail === null || Array.isArray(detail)) return null
  const payload = detail as Record<string, unknown>
  if (payload.code !== 'insufficient_stock' || typeof payload.inventory_id !== 'string') return null

  const requiredPackages = Number(payload.required_packages)
  const availablePackages = Number(payload.available_packages)
  const shortfallPackages = Number(payload.shortfall_packages)
  if (
    typeof payload.requested_quantity !== 'string' ||
    !Number.isFinite(requiredPackages) ||
    !Number.isFinite(availablePackages) ||
    !Number.isFinite(shortfallPackages)
  ) return null

  return {
    inventoryId: payload.inventory_id,
    requestedQuantity: payload.requested_quantity,
    requiredPackages,
    availablePackages,
    shortfallPackages,
  }
}

function nullableText(value: string) {
  return value.trim() || null
}

function nullableNumber(value: string) {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

function laborBookTimeCandidate(entry: LaborBookTimeEntry): RepairOperationCandidate {
  return {
    operation_id: entry.provider_operation_id || entry.operation_key,
    name: entry.operation_name,
    description: entry.operation_description || [
      [entry.vehicle_year, entry.vehicle_make, entry.vehicle_model].filter(Boolean).join(' '),
      entry.engine,
    ].filter(Boolean).join(' · '),
    estimated_hours: entry.normalized_hours,
    provider: 'internal_memory',
  }
}

function laborBookTimeScope(entry: LaborBookTimeEntry) {
  const primary = [entry.vehicle_year, entry.vehicle_make, entry.vehicle_model].filter(Boolean).join(' ')
  const secondary = [entry.engine, entry.fuel_type, entry.engine_displacement_l ? `${entry.engine_displacement_l}L` : null]
    .filter(Boolean)
    .join(' · ')
  return {
    primary: primary || entry.vehicle_signature,
    secondary: secondary || entry.component_signature || 'Vehicle application',
  }
}

const UNIT_ABBR: Record<string, string> = { each: 'ea', gallon: 'gal', quart: 'qt', liter: 'L' }

/**
 * Amazon-style quantity stepper for a part line. `[−] N [+]` increments/
 * decrements optimistically and debounce-saves the new quantity. When the
 * quantity is at the step floor, the decrement button becomes a delete (trash)
 * that removes the part from the order — so stepping down past the floor
 * removes the line rather than setting an invalid qty of 0.
 *
 * Fluid parts (unit_type != "each", e.g. oil/coolant/DEF) step by quarter
 * increments (0.25) since they're dispensed in fractional gallons/quarts/liters,
 * not whole units like a filter or belt.
 */
function PartQtyStepper({
  part, quantityOverride, disabled, onChangeQty, onDelete,
}: {
  part: PartsUsage
  quantityOverride?: number
  disabled?: boolean
  onChangeQty: (next: number) => Promise<void>
  onDelete: () => Promise<void>
}) {
  const isFluid = part.unit_type && part.unit_type !== 'each'
  const step = isFluid ? 0.25 : 1
  const unitAbbr = UNIT_ABBR[part.unit_type] || ''
  const currentQuantity = quantityOverride ?? (parseFloat(part.quantity) || 0)

  return (
    <QuantityStepper
      value={currentQuantity}
      min={step}
      step={step}
      unitLabel={unitAbbr}
      disabled={disabled}
      ariaLabel={`Quantity for ${part.inventory_name}`}
      removeAtMin
      onRemove={onDelete}
      onChange={(next) => { void onChangeQty(next) }}
      commitDebounceMs={500}
    />
  )
}

// Debounced hours-or-rate field for a labor line. Same shape as PartQtyStepper:
// keep an optimistic local value so the stepper advances instantly on each
// click, and coalesce the flurry of clicks into a single PATCH ~500ms after the
// user settles — otherwise rapid stepping bursts past the API rate limit (429).
// Server writes go through the steppers' built-in commitDebounceMs, so a flurry
// of clicks coalesces into one PATCH (avoids the rate-limit 429).
const STEPPER_COMMIT_DEBOUNCE_MS = 500

function LaborLineEditor({
  line, canMutate, onUpdate, onLocalChange,
}: {
  line: { id: string; description: string; hours: string; hourly_rate: string; total_cost: string }
  canMutate: boolean
  onUpdate: (body: { description?: string; hours?: number; hourly_rate?: number }) => void
  // Fires with the optimistic hours/rate on every step, ahead of the
  // debounced `onUpdate` write, so the parent can recompute rollups
  // (operation card total, Labor chip, order total) live instead of only
  // after the write lands and `line` is refetched.
  onLocalChange: (patch: { hours?: number; hourly_rate?: number }) => void
}) {
  const lineHours = parseFloat(line.hours) || 0
  const lineRate = parseFloat(line.hourly_rate) || 0

  // Read-only order (invoiced / paid / any customer order past quoted): the labor
  // can't be changed, so show a clean static read-out instead of disabled
  // steppers and a greyed input that look broken.
  if (!canMutate) {
    return (
      <div className="space-y-1">
        {line.description && (
          <p className="text-sm font-medium text-gray-800">{line.description}</p>
        )}
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <span className="tabular-nums">{formatHoursMinutes(lineHours)}</span>
          <span className="text-gray-400">×</span>
          <span className="tabular-nums">${lineRate.toFixed(2)}/hr</span>
          <span className="text-gray-400">=</span>
          <span className="font-semibold text-gray-900">${parseFloat(line.total_cost || '0').toFixed(2)}</span>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="mb-2 flex items-center gap-1.5">
        <input
          defaultValue={line.description}
          onBlur={(e) => {
            const value = e.target.value.trim()
            if (value !== line.description) onUpdate({ description: value })
          }}
          className="flex-1 rounded-md border border-gray-300 px-2 py-1.5 text-sm"
        />
      </div>
      {/* Duration + rate use the shared steppers (step time by 15m, rate by $1).
          Writes are debounced so rapid stepping doesn't trip the rate limit. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-gray-700">
        <label className="inline-flex items-center gap-1.5">
          <span className="text-[11px] font-medium uppercase tracking-wide text-gray-400">Duration</span>
          <DurationStepper
            hours={lineHours}
            onChange={(h) => onUpdate({ hours: h })}
            onLocalChange={(h) => onLocalChange({ hours: h })}
            stepMinutes={15}
            minMinutes={0}
            ariaLabel="Labor duration"
            commitDebounceMs={STEPPER_COMMIT_DEBOUNCE_MS}
          />
        </label>
        <span className="text-gray-400">×</span>
        <label className="inline-flex items-center gap-1.5">
          <span className="text-[11px] font-medium uppercase tracking-wide text-gray-400">Rate</span>
          <span className="text-gray-500">$</span>
          <QuantityStepper
            value={lineRate}
            onChange={(r) => onUpdate({ hourly_rate: r })}
            onLocalChange={(r) => onLocalChange({ hourly_rate: r })}
            min={0}
            step={25}
            unitLabel="/hr"
            ariaLabel="Labor hourly rate"
            align="start"
            commitDebounceMs={STEPPER_COMMIT_DEBOUNCE_MS}
          />
        </label>
        <span className="text-gray-400">=</span>
        <span className="font-semibold text-gray-900">${parseFloat(line.total_cost || '0').toFixed(2)}</span>
      </div>
    </>
  )
}

/**
 * Keeps an asynchronous picker from briefly reading as empty while its result
 * set is still on the wire. The shape intentionally mirrors the compact picker
 * rows instead of shifting the Price Builder layout with a full panel loader.
 */
function PickerLoadingRows({ message }: { message: string }) {
  return (
    <div aria-live="polite">
      <p className="inline-flex items-center gap-2 px-2 py-3 text-xs font-semibold text-gray-500">
        <Spinner size="xs" label={message} />
        {message}
      </p>
      <div aria-hidden="true" className="space-y-1.5 px-2 pb-2 animate-pulse">
        {[0, 1].map((index) => (
          <div key={index} className="flex items-center gap-3 rounded-xl border border-gray-100 bg-gray-50/70 px-3 py-2.5">
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="h-3.5 w-2/5 rounded bg-gray-200" />
              <div className="h-2.5 w-3/5 rounded bg-gray-100" />
            </div>
            <div className="h-8 w-8 rounded-full bg-gray-200" />
          </div>
        ))}
      </div>
    </div>
  )
}

/** A compact destination placeholder for a new operation or part mutation. */
function PendingWorkRows({ message }: { message: string }) {
  return (
    <div aria-live="polite" className="rounded-xl border border-dashed border-orange-200 bg-orange-50/40 px-3 py-3">
      <p className="inline-flex items-center gap-2 text-sm font-semibold text-gray-700">
        <Spinner size="xs" label={message} />
        {message}
      </p>
      <div aria-hidden="true" className="mt-3 flex items-center gap-3 animate-pulse">
        <div className="h-9 w-9 shrink-0 rounded-lg bg-orange-100" />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="h-3.5 w-2/5 rounded bg-orange-100" />
          <div className="h-2.5 w-3/5 rounded bg-orange-50" />
        </div>
        <div className="h-5 w-16 rounded bg-orange-100" />
      </div>
    </div>
  )
}

function StockShortageCallout({
  shortage,
  unitLabel,
  overridePending,
  addPending,
  action,
  onOverride,
}: {
  shortage: StockShortage
  unitLabel: string
  overridePending: boolean
  addPending: boolean
  action: 'add' | 'update'
  onOverride: () => void
}) {
  const availableLabel = unitLabel
    ? `${shortage.availablePackages} ${unitLabel}`
    : `${shortage.availablePackages} package${shortage.availablePackages === 1 ? '' : 's'}`
  const requestedLabel = unitLabel
    ? `${shortage.requestedQuantity} ${unitLabel}`
    : `${shortage.requestedQuantity} package${shortage.requestedQuantity === '1' ? '' : 's'}`
  const shortfallLabel = unitLabel
    ? `${shortage.shortfallPackages} ${unitLabel}`
    : `${shortage.shortfallPackages} package${shortage.shortfallPackages === 1 ? '' : 's'}`
  const packageNote = shortage.requiredPackages !== Number(shortage.requestedQuantity)
    ? ` (${shortage.requiredPackages} packages required)`
    : ''
  const actionLabel = action === 'update' ? 'Override & update' : 'Override & add'
  const pendingLabel = action === 'update' ? 'Updating…' : 'Adding…'
  const spinnerLabel = action === 'update' ? 'Updating quantity with stock override' : 'Adding with stock override'

  return (
    <div role="alert" className="mt-2 flex flex-col gap-2 rounded-lg border border-red-200 bg-red-50 px-2.5 py-2 text-xs text-red-800 sm:flex-row sm:items-center sm:justify-between">
      <p className="flex min-w-0 items-start gap-1.5">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600" />
        <span>
          <span className="font-bold">Stock count needs attention.</span>{' '}
          Inventory shows {availableLabel}; this order requests {requestedLabel}{packageNote}. Short by {shortfallLabel}.
        </span>
      </p>
      <button
        type="button"
        onClick={onOverride}
        disabled={overridePending || addPending}
        className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md border border-red-300 bg-white px-2.5 py-1.5 font-bold text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {overridePending && <Spinner size="xs" label={spinnerLabel} />}
        {overridePending ? pendingLabel : actionLabel}
      </button>
    </div>
  )
}

/**
 * Order number in the panel header. On mobile the value is truncated to fit
 * the narrow header; tapping it reveals the full number in a small popover so
 * it stays reachable. Desktop hover also gets a native title.
 */
function OrderNumberHeader({ value }: { value: string }) {
  const [open, setOpen] = useState(false)
  const [truncated, setTruncated] = useState(false)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const h3Ref = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    const el = h3Ref.current
    if (!el) return
    const check = () => setTruncated(el.scrollWidth > el.clientWidth + 1)
    check()
    const ro = new ResizeObserver(check)
    ro.observe(el)
    return () => ro.disconnect()
  }, [value])

  useEffect(() => {
    if (!open) return
    const close = () => setOpen(false)
    window.addEventListener('pointerdown', close)
    window.addEventListener('resize', close)
    window.addEventListener('scroll', close, true)
    return () => {
      window.removeEventListener('pointerdown', close)
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', close, true)
    }
  }, [open])

  const toggle = (e: ReactMouseEvent) => {
    e.stopPropagation()
    const el = h3Ref.current
    if (el) {
      const r = el.getBoundingClientRect()
      setPos({ top: r.bottom + 8, left: r.left })
    }
    setOpen((v) => !v)
  }

  return (
    <div className="min-w-0">
      <h3
        ref={h3Ref}
        title={truncated ? value : undefined}
        onClick={truncated ? toggle : undefined}
        className={`truncate font-['Barlow_Condensed',sans-serif] text-3xl font-extrabold leading-none tracking-wide${
          truncated ? ' cursor-pointer' : ''
        }`}
      >
        {value}
      </h3>
      {open && pos &&
        createPortal(
          <div
            onPointerDown={(e) => e.stopPropagation()}
            style={{ position: 'fixed', top: pos.top, left: pos.left }}
            className="z-[70] max-w-[calc(100vw-1rem)] break-all rounded-lg bg-white px-3 py-2 font-['JetBrains_Mono',monospace] text-sm font-semibold text-gray-900 shadow-xl ring-1 ring-black/10"
          >
            {value}
          </div>,
          document.body,
        )}
    </div>
  )
}

function PartPricePopover({
  part, disabled, saving, onApply,
}: {
  part: PartsUsage
  disabled?: boolean
  saving?: boolean
  onApply: (value: number) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [menuPos, setMenuPos] = useState<{ top: number; left: number; openUp: boolean } | null>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const unit = parseFloat(part.unit_price || '0')
  const stock = part.unit_cost != null ? parseFloat(part.unit_cost) : null
  const list = part.list_price != null ? parseFloat(part.list_price) : unit
  const draftPrice = parseFloat(draft || String(unit))
  const marginPrice = Number.isFinite(draftPrice) ? draftPrice : unit
  const margin = stock != null && marginPrice > 0 ? ((marginPrice - stock) / marginPrice) * 100 : null
  const isSameMoney = (a: number | null, b: number | null) => (
    a != null && b != null && Math.abs(a - b) < 0.005
  )
  const resetToStock = stock != null && isSameMoney(marginPrice, list)
  const resetLabel = resetToStock ? 'Reset to stock' : 'Reset to list'
  const resetValue = resetToStock ? stock : list
  const isCustom = Number.isFinite(list) && Math.abs(unit - list) >= 0.005

  const computePosition = () => {
    if (!buttonRef.current) return
    const rect = buttonRef.current.getBoundingClientRect()
    const estimatedMenuHeight = 250
    const estimatedMenuWidth = Math.min(320, window.innerWidth - 32)
    const spaceBelow = window.innerHeight - rect.bottom
    const openUp = spaceBelow < estimatedMenuHeight && rect.top > estimatedMenuHeight
    setMenuPos({
      top: openUp ? rect.top - 4 : rect.bottom + 4,
      left: Math.min(window.innerWidth - 16, Math.max(16 + estimatedMenuWidth, rect.right)),
      openUp,
    })
  }

  const toggleOpen = () => {
    if (!open) {
      setDraft(unit.toFixed(2))
      computePosition()
    }
    setOpen((o) => !o)
  }

  // Rendered via a portal to document.body (position: fixed) so the menu can
  // never be clipped by an ancestor's overflow — e.g. the RO detail modal's
  // own max-h-[90vh] overflow-y-auto scroll box. Close on any scroll/resize
  // since a fixed menu would otherwise visually detach from the button.
  useEffect(() => {
    if (!open) return
    const onClickOutside = (e: MouseEvent) => {
      const target = e.target as Node
      if (buttonRef.current?.contains(target) || menuRef.current?.contains(target)) return
      setOpen(false)
    }
    // Ignore the reflow/scroll that can fire in the same tick the menu mounts
    // (e.g. the modal's scrollbar appearing) — otherwise the menu closes the
    // instant it opens. Only user-driven scroll/resize after that should close.
    const openedAt = Date.now()
    const onScrollOrResize = () => { if (Date.now() - openedAt > 150) setOpen(false) }
    document.addEventListener('mousedown', onClickOutside)
    window.addEventListener('scroll', onScrollOrResize, true)
    window.addEventListener('resize', onScrollOrResize)
    return () => {
      document.removeEventListener('mousedown', onClickOutside)
      window.removeEventListener('scroll', onScrollOrResize, true)
      window.removeEventListener('resize', onScrollOrResize)
    }
  }, [open])

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        disabled={disabled}
        onClick={toggleOpen}
        className={`h-8 min-w-[84px] whitespace-nowrap rounded-lg border bg-white px-2 text-right font-['JetBrains_Mono',monospace] text-xs text-gray-900 shadow-sm disabled:opacity-60 ${
          isCustom ? 'border-orange-400 ring-2 ring-orange-100' : 'border-gray-200'
        }`}
      >
        {money(unit)} <ChevronDown className="ml-1 inline h-3 w-3 text-gray-400" />
      </button>
      {open && menuPos && createPortal(
        <div
          ref={menuRef}
          style={{
            position: 'fixed',
            top: menuPos.openUp ? undefined : menuPos.top,
            bottom: menuPos.openUp ? window.innerHeight - menuPos.top : undefined,
            left: menuPos.left,
            transform: 'translateX(-100%)',
          }}
          className="z-[70] w-[min(320px,calc(100vw-32px))] rounded-[14px] border border-gray-200 bg-white p-3 text-sm shadow-[0_10px_30px_rgba(20,25,35,.10)]"
        >
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <p className="font-semibold text-gray-900">{part.inventory_name}</p>
              <p className="font-['JetBrains_Mono',monospace] text-[11px] text-gray-500">{part.inventory_sku}</p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between rounded-lg px-2 py-1.5 text-gray-600">
              <span><span className="mr-2 inline-block h-2 w-2 rounded-full bg-gray-300" />Stock cost</span>
              <span className="font-['JetBrains_Mono',monospace]">{stock == null ? '—' : money(stock)}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg px-2 py-1.5 text-gray-700">
              <span>List price</span>
              <span className="font-['JetBrains_Mono',monospace]">{money(list)}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg px-2 py-1.5 text-gray-700">
              <span>Margin at this price</span>
              <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                {margin == null ? '—' : `${margin >= 0 ? '+' : ''}${margin.toFixed(1)}%`}
              </span>
            </div>
            <label className="grid grid-cols-[minmax(0,1fr)_104px] items-center gap-3 rounded-xl border border-orange-200 bg-orange-50/70 px-2.5 py-2">
              <span className="min-w-0 whitespace-nowrap font-medium text-gray-900">
                <span className="mr-2 inline-block h-2 w-2 rounded-full bg-orange-500" />Customer price
              </span>
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value.replace(/[^0-9.]/g, ''))}
                inputMode="decimal"
                className="h-9 min-w-0 rounded-lg border border-orange-200 bg-white px-2 text-right font-['JetBrains_Mono',monospace] text-sm outline-none focus:ring-2 focus:ring-orange-300"
              />
            </label>
          </div>
          <div className="mt-3 flex items-center justify-between gap-2 border-t border-gray-100 pt-3">
            <button
              type="button"
              disabled={saving || disabled}
              onClick={() => setDraft(resetValue.toFixed(2))}
              className="rounded-lg px-2 py-1.5 text-xs font-semibold text-gray-600 hover:bg-gray-100 disabled:opacity-60"
            >
              {resetLabel}
            </button>
            <button
              type="button"
              disabled={saving || disabled}
              onClick={async () => {
                const next = parseFloat(draft || '0')
                if (!Number.isFinite(next) || next < 0) {
                  toast.error('Customer price must be 0 or more')
                  return
                }
                await onApply(next)
                setOpen(false)
              }}
              className="rounded-lg bg-orange-500 px-3 py-1.5 text-xs font-bold text-white shadow-[0_6px_16px_rgba(239,138,18,.32)] disabled:opacity-60"
            >
              {saving ? 'Applying…' : 'Apply'}
            </button>
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}

export default function PriceBuilderPanel({
  orderId,
  orderStatus,
  canEdit,
  isInternalOrder = false,
  defaultLaborRate,
  description,
  orderNumber,
  navigationLabel,
  customerName,
  vehicleLabel,
  vehicleUnit,
  vehicleVin,
  vehicleYear,
  vehicleMake,
  vehicleModel,
  customerEmail,
  customerPhone,
  vehiclePlate,
  mileageIn,
  mileageOut,
  poNumber,
  orderTypeLabel,
  quoteNumber,
  quoteIsApproved = false,
  quoteActionLabel = 'Create estimate',
  quoteActionPending = false,
  quoteActionDisabled = false,
  quoteDisabledReason,
  onQuoteAction,
  assignedTechnicianName,
  assignedTechnicianId,
  technicianOptions = [],
  technicianAssignmentPending = false,
  onAssignTechnician,
  technicianOverridePending = false,
  onOverrideTechnicianAssignment,
  completionMode = false,
  completionPending = false,
  mileageOutValue = '',
  onMileageOutChange,
  reviewNotesValue = '',
  onReviewNotesChange,
  showReviewNotes = false,
  onToggleReviewNotes,
  onApproveCompletion,
  onStartWorkOrder,
  startWorkOrderPending = false,
  onCompleteWorkOrder,
  completeWorkOrderPending = false,
  onAdminCompleteWork,
  adminCompleteWorkPending = false,
  invoiceCreatePending = false,
  invoiceDueDateValue = '',
  showInvoiceCreateOptions = false,
  onToggleInvoiceCreateOptions,
  onInvoiceDueDateChange,
  onCreateInvoice,
  invoice,
  invoiceActionPending = false,
  onResendInvoice,
  onRecordPayment,
  onVoidInvoice,
  historyEvents = [],
  onClose,
  onPrev,
  onNext,
  prevDisabled,
  nextDisabled,
  showDangerActions,
  onToggleDangerActions,
  onDeleteOrder,
  deletePending,
  isDeleted = false,
  deletedByName,
  deletedAt,
  onRestoreOrder,
  restorePending = false,
  onReopenWorkOrder,
  reopenPending = false,
  recommendedServices,
  recommendedServicesLoading = false,
  showAddRecommendedService,
  recommendedServiceForm,
  onToggleAddRecommendedService,
  onRecommendedServiceFormChange,
  onAddRecommendedService,
  onResolveRecommendedService,
  onDeleteRecommendedService,
  addRecommendedPending,
  resolveRecommendedPending,
  deleteRecommendedPending,
  onRecommendedServicesOpenChange,
  onUpdated,
  initialLineWarnings = [],
}: Props) {
  const queryClient = useQueryClient()
  const [searchTerm, setSearchTerm] = useState('')
  const [candidates, setCandidates] = useState<RepairOperationCandidate[]>([])
  const [searchWarnings, setSearchWarnings] = useState<{ code: string; message: string }[]>([])
  const [addType, setAddType] = useState<AddBarType>(() => (
    !['completed', 'invoiced', 'paid', 'cancelled'].includes(orderStatus) ? 'operation' : 'history'
  ))
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [invoiceDetailsOpen, setInvoiceDetailsOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyVisibleCount, setHistoryVisibleCount] = useState(5)
  const [openLineIds, setOpenLineIds] = useState<Set<string>>(new Set())
  const [discountsOpen, setDiscountsOpen] = useState(false)
  const [footerDetailsOpen, setFooterDetailsOpen] = useState<'parts' | 'labor' | 'discounts' | 'savings' | null>(null)
  const [totalJustChanged, setTotalJustChanged] = useState(false)
  const [totalMotionActive, setTotalMotionActive] = useState(false)
  const previousTotalRef = useRef<string | null>(null)
  const totalMotionTimerRef = useRef<number | null>(null)
  const [customerOpen, setCustomerOpen] = useState(false)
  const [recommendedOpen, setRecommendedOpen] = useState(false)
  const [photosOpen, setPhotosOpen] = useState(false)
  const [technicianAssignmentOpen, setTechnicianAssignmentOpen] = useState(true)
  const [photoCaption, setPhotoCaption] = useState('')
  const [photoUploadItems, setPhotoUploadItems] = useState<RepairPhotoUploadItem[]>([])
  const [armWoComplete, setArmWoComplete] = useState(false)
  const [woMileageOut, setWoMileageOut] = useState('')
  const [partQuantitiesByItemId, setPartQuantitiesByItemId] = useState<Record<string, number>>({})
  const [stockShortages, setStockShortages] = useState<Record<string, StockShortage>>({})
  const [lineWarnings, setLineWarnings] = useState<Record<string, LineWarning[]>>({})
  const [partQuantityOverrides, setPartQuantityOverrides] = useState<Record<string, number>>({})
  const [partQuantitySavingKey, setPartQuantitySavingKey] = useState<string | null>(null)
  const [operationPartPickerLineId, setOperationPartPickerLineId] = useState<string | null>(null)
  const [operationPartSearchByLineId, setOperationPartSearchByLineId] = useState<Record<string, string>>({})
  const [bookTimeHours, setBookTimeHours] = useState('1')

  // Accordions belong to the selected order. Resetting them on navigation
  // prevents a panel opened for one order from silently triggering optional
  // reads for the next order in the work queue.
  useEffect(() => {
    setRecommendedOpen(false)
    setPhotosOpen(false)
    onRecommendedServicesOpenChange?.(false)
  }, [orderId, onRecommendedServicesOpenChange])

  useEffect(() => {
    setStockShortages({})
    setLineWarnings({})
    setPartQuantityOverrides({})
    setPartQuantitySavingKey(null)
  }, [orderId])

  useEffect(() => {
    const targetedWarnings = initialLineWarnings.filter((warning) => warning.line_id)
    if (!targetedWarnings.length) return
    setLineWarnings((current) => {
      const next = { ...current }
      for (const warning of targetedWarnings) {
        const lineId = warning.line_id as string
        next[lineId] = [...(next[lineId] || []).filter((item) => item.code !== warning.code || item.message !== warning.message), warning]
      }
      return next
    })
    setOpenLineIds((current) => {
      const next = new Set(current)
      targetedWarnings.forEach((warning) => {
        if (warning.line_id) next.add(warning.line_id)
      })
      return next
    })
  }, [initialLineWarnings])
  const initialLaborBookTimeForm = (): LaborBookTimeForm => ({
    operation_name: searchTerm.trim(),
    operation_description: '',
    normalized_hours: '1',
    vehicle_year: vehicleYear ? String(vehicleYear) : '',
    vehicle_make: vehicleMake || '',
    vehicle_model: vehicleModel || '',
    vehicle_type: '',
    body_class: '',
    engine: '',
    fuel_type: '',
    engine_cylinders: '',
    engine_displacement_l: '',
    gvwr: '',
    vin_sample: vehicleVin || '',
  })
  const [laborBookTimeForm, setLaborBookTimeForm] = useState<LaborBookTimeForm>(() => initialLaborBookTimeForm())
  const [showLaborBookTimeForm, setShowLaborBookTimeForm] = useState(false)
  // Inline result of a VIN decode (auto or manual), shown next to the VIN field
  // instead of a toast.
  const [vinDecodeStatus, setVinDecodeStatus] = useState<{ ok: boolean; message: string } | null>(null)
  const { data: summary, refetch: refetchSummary, isLoading, isError: summaryErrored, isFetching: summaryFetching } = useQuery<PriceBuildSummary>({
    queryKey: ['price-build', orderId],
    queryFn: async ({ signal }) => {
      const response = await api.get(`/repair-orders/${orderId}/price-build`, { signal })
      return response.data
    },
    // A soft-deleted order's work/labor endpoints 404 (the order is hidden from
    // them), so don't fetch when deleted — the panel shows the Restore state.
    enabled: !!orderId && !isDeleted,
  })

  const { data: repairPhotosData, isFetching: repairPhotosFetching } = useQuery<RepairOrderPhoto[]>({
    queryKey: ['repair-order-photos', orderId],
    queryFn: async ({ signal }) => {
      const response = await api.get(`/repair-orders/${orderId}/photos`, { signal })
      return response.data
    },
    // The photos section starts collapsed. Do not spend a request on thumbnails
    // and Cloudinary URLs until the operator opens that optional panel.
    enabled: !!orderId && !isDeleted && photosOpen,
  })
  const repairPhotos = repairPhotosData ?? []

  const isUploadingRepairPhotos = photoUploadItems.some((item) => !['done', 'error'].includes(item.status))

  const updateRepairPhotoUpload = (id: string, patch: Partial<RepairPhotoUploadItem>) => {
    setPhotoUploadItems((items) => items.map((item) => item.id === id ? { ...item, ...patch } : item))
  }

  const deletePhotoMutation = useMutation({
    mutationFn: async (photoId: string) => {
      await api.delete(`/repair-orders/${orderId}/photos/${photoId}`)
    },
    onSuccess: () => {
      toast.success('Photo deleted')
      queryClient.invalidateQueries({ queryKey: ['repair-order-photos', orderId] })
    },
    onError: (error: unknown) => {
      toast.error(errorDetail(error, 'Failed to delete photo'))
    },
  })

  const handleRepairPhotoSelect = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    if (files.length === 0) return

    const validFiles: File[] = []
    for (const file of files) {
      if (!isSupportedPhotoFile(file)) {
        toast.error(`${file.name} is not an image file`)
        continue
      }
      if (file.size > 10 * 1024 * 1024) {
        toast.error(`${file.name} is too large. Max 10MB`)
        continue
      }
      validFiles.push(file)
    }
    if (validFiles.length === 0) return

    const caption = photoCaption.trim()
    const uploadItems = validFiles.map((file) => ({
      id: crypto.randomUUID(),
      file,
      name: file.name,
      size: file.size,
      status: 'queued' as PhotoUploadStatus,
      progress: 0,
    }))
    setPhotoUploadItems((items) => [...uploadItems, ...items.filter((item) => item.status === 'error')])
    setPhotosOpen(true)

    let uploadedCount = 0
    await runPhotoUploadQueue(uploadItems, async (item) => {
      try {
        const photo = await uploadDirectPhoto<RepairOrderPhoto>({
          file: item.file,
          signEndpoint: `/repair-orders/${orderId}/photos/direct-upload-signature`,
          recordEndpoint: `/repair-orders/${orderId}/photos/direct`,
          fallbackEndpoint: `/repair-orders/${orderId}/photos`,
          caption,
          onProgress: (progress) => updateRepairPhotoUpload(item.id, progress),
        })
        uploadedCount += 1
        queryClient.setQueryData<RepairOrderPhoto[]>(['repair-order-photos', orderId], (current = []) => [photo, ...current])
      } catch (error) {
        updateRepairPhotoUpload(item.id, {
          status: 'error',
          error: errorDetail(error, 'Upload failed'),
        })
      }
    })
    if (uploadedCount > 0) {
      toast.success(`${uploadedCount} photo${uploadedCount === 1 ? '' : 's'} uploaded`)
      setPhotoCaption('')
      setPhotoUploadItems((items) => items.filter((item) => item.status === 'error'))
      queryClient.invalidateQueries({ queryKey: ['repair-order-photos', orderId] })
    }
  }

  const visiblePhotoThumbs = repairPhotos.slice(0, 5)
  const hiddenPhotoThumbCount = Math.max(0, repairPhotos.length - visiblePhotoThumbs.length)

  // Labor duration/rate steppers debounce their server writes and coalesce
  // into a single PATCH, so `summary.lines[].total_cost` (and everything
  // rolled up from it — the operation card total, the Labor chip, the order
  // total) lags behind what the steppers show on screen while a write is
  // pending. Track each line's live optimistic hours/rate here so those
  // rollups can be recomputed from what's actually displayed instead of the
  // stale server aggregate.
  const [laborOverrides, setLaborOverrides] = useState<Record<string, { hours: number; hourly_rate: number }>>({})
  const setLaborOverride = (lineId: string, patch: { hours?: number; hourly_rate?: number }) => {
    setLaborOverrides((prev) => {
      const base = prev[lineId] || {
        hours: parseFloat(summary?.lines.find((l) => l.id === lineId)?.hours || '0') || 0,
        hourly_rate: parseFloat(summary?.lines.find((l) => l.id === lineId)?.hourly_rate || '0') || 0,
      }
      return { ...prev, [lineId]: { ...base, ...patch } }
    })
  }
  // Once the server value catches up to a line's override, drop the override
  // so the line goes back to tracking `summary` directly (and doesn't get
  // stuck showing a stale optimistic value forever if the write failed).
  useEffect(() => {
    if (!summary?.lines?.length || !Object.keys(laborOverrides).length) return
    setLaborOverrides((prev) => {
      let changed = false
      const next = { ...prev }
      for (const line of summary.lines) {
        const override = next[line.id]
        if (!override) continue
        const serverHours = parseFloat(line.hours) || 0
        const serverRate = parseFloat(line.hourly_rate) || 0
        if (Math.abs(serverHours - override.hours) < 0.001 && Math.abs(serverRate - override.hourly_rate) < 0.001) {
          delete next[line.id]
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [summary?.lines, laborOverrides])

  const effectiveLaborLines = (summary?.lines || []).map((line) => {
    const override = laborOverrides[line.id]
    if (!override) return line
    const total_cost = (override.hours * override.hourly_rate).toFixed(2)
    return { ...line, hours: String(override.hours), hourly_rate: String(override.hourly_rate), total_cost }
  })
  const effectiveLaborTotal = effectiveLaborLines.reduce((sum, l) => sum + (parseFloat(l.total_cost || '0') || 0), 0)

  useEffect(() => {
    if (!summary?.lines) return
    const activeLineIds = new Set(summary.lines.map((line) => line.id))
    setLineWarnings((current) => {
      let changed = false
      const next: Record<string, LineWarning[]> = {}
      for (const [lineId, warnings] of Object.entries(current)) {
        if (!activeLineIds.has(lineId)) {
          changed = true
          continue
        }
        next[lineId] = warnings
      }
      return changed ? next : current
    })
  }, [summary?.lines])

  const { data: partsUsed, isFetching: partsFetching } = useQuery<PartsUsage[]>({
    queryKey: ['price-build-parts', orderId],
    queryFn: async ({ signal }) => {
      const response = await api.get(`/repair-orders/${orderId}/parts`, { signal })
      return response.data
    },
    enabled: !!orderId && !isDeleted,
  })

  const partSearchTerm = useDebouncedValue(searchTerm.trim(), 250)
  const operationPartSearchTerm = useDebouncedValue(
    operationPartPickerLineId ? (operationPartSearchByLineId[operationPartPickerLineId] || '').trim() : '',
    250,
  )
  const inventorySearchTerm = addType === 'part' ? partSearchTerm : operationPartSearchTerm
  const shouldSearchInventory = (
    (addType === 'part' || !!operationPartPickerLineId) && inventorySearchTerm.length >= 2
  )
  const { data: inventory = [], isFetching: inventoryFetching, isError: inventoryErrored } = useQuery<InventoryTypeaheadItem[]>({
    queryKey: ['inventory-typeahead', inventorySearchTerm],
    queryFn: async ({ signal }) => {
      const response = await api.get('/inventory/typeahead', {
        signal,
        params: { q: inventorySearchTerm, limit: 20, in_stock: false },
      })
      return response.data
    },
    // Searching a part is explicit user intent. Include zero-stock rows so a
    // verified physical part that has not been recorded yet can use the explicit
    // shortage override; the endpoint remains tenant-scoped and capped.
    enabled: !!orderId && !isDeleted && shouldSearchInventory,
    staleTime: 30 * 1000,
  })

  const { data: partSuggestions, isFetching: partSuggestionsFetching } = useQuery<PartSuggestionsResponse>({
    queryKey: ['price-build-part-suggestions', orderId],
    queryFn: async ({ signal }) => {
      const response = await api.get(`/repair-orders/${orderId}/parts/suggestions`, { signal })
      return response.data
    },
    enabled: !!orderId && !isDeleted && addType === 'part' && partSearchTerm.length === 0,
  })

  const laborBookSearchTerm = searchTerm.trim()
  const { data: laborBookEntries = [], isFetching: laborBookEntriesFetching } = useQuery<LaborBookTimeEntry[]>({
    queryKey: ['labor-book-time', laborBookSearchTerm],
    queryFn: async ({ signal }) => {
      const response = await api.get('/labor-book-time', {
        signal,
        params: laborBookSearchTerm ? { q: laborBookSearchTerm } : undefined,
      })
      return response.data
    },
    enabled: addType === 'saved_labor',
  })

  const [editingPartsSaving, setEditingPartsSaving] = useState(false)
  const [priceSavingId, setPriceSavingId] = useState<string | null>(null)


  const isLocked = !!summary?.pricing_locked
  const hasInvoice = !!invoice && ['invoiced', 'paid'].includes(orderStatus)
  const invoiceDisplayTotal = invoice
    ? Math.max(
        0,
        parseFloat(invoice.total_amount || '0')
          - (invoice.pending_zelle_confirmation ? parseFloat(invoice.service_fee_amount || '0') : 0),
      )
    : 0
  const canCreateInvoice = !isInternalOrder && orderStatus === 'completed' && !!onCreateInvoice
  const showRecommendedServicesPanel = !['completed', 'invoiced', 'paid'].includes(orderStatus)
  // Work-first: the repair order is editable throughout active shop work. The
  // server capability is authoritative; the fallback supports older responses.
  const INTERNAL_FROZEN_STATUSES: RepairOrderStatus[] = ['completed', 'invoiced', 'paid', 'cancelled']
  const isEditableStatus = summary?.can_edit_work ?? !INTERNAL_FROZEN_STATUSES.includes(orderStatus)
  const canMutate = canEdit && !isLocked && isEditableStatus
  // The add bar must follow the same editable-status rule as canMutate, or an
  // internal in-progress order shows "start by adding…" with no add controls.
  const addBarReadOnly = !canEdit || isLocked || !isEditableStatus || completionMode || hasInvoice || orderStatus === 'completed'
  // An empty work order has nothing to estimate.
  const isEmptyOrder = effectiveLaborLines.length === 0 && (partsUsed?.length ?? 0) === 0
  const hasAssignedTechnician = !!assignedTechnicianName
  const technicianAssignmentBypassed = !hasAssignedTechnician && ['in_progress', 'pending_review', 'completed', 'invoiced', 'paid'].includes(orderStatus)
  const canAdminCompleteBypassedWork = !isInternalOrder && technicianAssignmentBypassed && orderStatus === 'in_progress' && !!onAdminCompleteWork
  // A finalized order is closed: the work is done and billed/settled. No more
  // photo uploads, and the quote pipeline is just clutter (the single status
  // chip already says it all).
  const isFinalized = ['completed', 'invoiced', 'paid', 'cancelled'].includes(orderStatus)
  const canManageTechnician = !isInternalOrder && (summary?.can_assign_technician ?? !['pending_review', 'completed', 'invoiced', 'paid', 'cancelled'].includes(orderStatus))
  const canOverrideTechnicianAssignment = !isInternalOrder && !hasAssignedTechnician && ['draft', 'quoted', 'declined', 'approved'].includes(orderStatus) && !!onOverrideTechnicianAssignment
  const availableTechnicians = technicianOptions
    .filter((tech) => tech.mechanic_id !== assignedTechnicianId)
    .map((tech) => {
      const assigned = tech.assigned_count ?? 0
      const inProgress = tech.in_progress_count ?? 0
      const load = assigned > 0 ? Math.min((inProgress / assigned) * 100, 100) : 0
      return { ...tech, assigned, inProgress, load }
    })
    .sort((a, b) => a.load - b.load)
  // Sending a quote/creating a draft only makes sense once there's something to
  // bill. Block the action (and explain why) while the order is empty.
  const quoteActionBlocked = quoteActionDisabled || isEmptyOrder
  const quoteButtonDisabledReason = quoteDisabledReason || (
    isEmptyOrder
      ? 'Add at least one operation, labor line, or part before creating an estimate.'
      : quoteIsApproved
        ? 'This estimate is authorized. The live repair order remains editable until finalization.'
        : !canMutate
          ? 'Estimates are unavailable after the repair order is finalized.'
          : undefined
  )
  const lockContextMessage = quoteButtonDisabledReason || (
    'Pricing is locked because this repair order has been finalized.'
  )
  const formatHistoryDate = (value: string) => {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return value
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  }
  const formatHistoryTime = (value: string) => {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ''
    return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  }
  const sortedHistoryEvents = [...historyEvents].sort((a, b) => {
    return new Date(b.at).getTime() - new Date(a.at).getTime()
  })
  const visibleHistoryEvents = sortedHistoryEvents.slice(0, historyVisibleCount)
  const hiddenHistoryCount = Math.max(0, sortedHistoryEvents.length - visibleHistoryEvents.length)

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['price-build', orderId] }),
      queryClient.invalidateQueries({ queryKey: ['price-build-parts', orderId] }),
      queryClient.invalidateQueries({ queryKey: ['price-build-part-suggestions', orderId] }),
      queryClient.invalidateQueries({ queryKey: ['inventory-typeahead'] }),
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', orderId] }),
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] }),
    ])
    onUpdated?.()
  }

  const updatePartQuantity = async (part: PartsUsage, next: number, allowStockShortage = false) => {
    const shortageKey = partQuantityKey(part.id)
    setPartQuantityOverrides((current) => ({ ...current, [shortageKey]: next }))
    setPartQuantitySavingKey(shortageKey)
    setEditingPartsSaving(true)
    try {
      await api.patch(`/repair-orders/${orderId}/parts/${part.id}`, {
        quantity: next,
        allow_stock_shortage: allowStockShortage,
      })
      setStockShortages((current) => {
        const updated = { ...current }
        delete updated[shortageKey]
        return updated
      })
      setPartQuantityOverrides((current) => {
        const updated = { ...current }
        delete updated[shortageKey]
        return updated
      })
      await invalidate()
    } catch (err: unknown) {
      const shortage = stockShortageFromError(err)
      if (shortage && shortage.inventoryId === part.inventory_id) {
        setStockShortages((current) => ({ ...current, [shortageKey]: shortage }))
        toast.error('Inventory count is short — review the inline stock check.')
        return
      }
      setPartQuantityOverrides((current) => {
        const updated = { ...current }
        delete updated[shortageKey]
        return updated
      })
      toast.error(errorDetail(err, 'Failed to update part quantity'))
      await invalidate()
    } finally {
      setPartQuantitySavingKey(null)
      setEditingPartsSaving(false)
    }
  }

  useEffect(() => {
    setAddType((current) => {
      if (addBarReadOnly) return 'history'
      return current === 'history' ? 'operation' : current
    })
    if (addBarReadOnly) {
      setPaletteOpen(false)
      setSearchTerm('')
      setSearchWarnings([])
    }
  }, [addBarReadOnly, orderId])

  useEffect(() => {
    setHistoryOpen(false)
    setHistoryVisibleCount(5)
  }, [orderId])

  useEffect(() => {
    setTechnicianAssignmentOpen(!technicianAssignmentBypassed)
  }, [orderId, technicianAssignmentBypassed])

  useEffect(() => {
    if (!['in_progress', 'pending_review'].includes(orderStatus)) {
      setArmWoComplete(false)
    }
  }, [orderStatus])

  // --- Bulk parts pricing (Stock ⇄ List) + manager discounts ---
  const [laborDiscount, setLaborDiscount] = useState('')
  const [orderDiscount, setOrderDiscount] = useState('')
  const [discountsSaving, setDiscountsSaving] = useState(false)
  const [partsPricingMode, setPartsPricingMode] = useState<'stock' | 'list'>('list')
  const [draftPartsPricingMode, setDraftPartsPricingMode] = useState<'stock' | 'list'>('list')
  const discountsButtonRef = useRef<HTMLButtonElement>(null)
  const discountsPopoverRef = useRef<HTMLDivElement>(null)
  const footerDetailsRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const l = parseFloat(summary?.labor_discount_amount || '0')
    const o = parseFloat(summary?.order_discount_amount || '0')
    setLaborDiscount(l > 0 ? l.toFixed(2) : '')
    setOrderDiscount(o > 0 ? o.toFixed(2) : '')
  }, [summary?.labor_discount_amount, summary?.order_discount_amount])

  useEffect(() => {
    if (!discountsOpen) return
    const isInsideDiscountsPopover = (target: EventTarget | null) => {
      const node = target as Node | null
      return !!node && (
        discountsButtonRef.current?.contains(node) ||
        discountsPopoverRef.current?.contains(node)
      )
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (!isInsideDiscountsPopover(event.target)) setDiscountsOpen(false)
    }
    const handleFocusIn = (event: FocusEvent) => {
      if (!isInsideDiscountsPopover(event.target)) setDiscountsOpen(false)
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDiscountsOpen(false)
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('focusin', handleFocusIn)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('focusin', handleFocusIn)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [discountsOpen])

  useEffect(() => {
    if (!footerDetailsOpen) return
    const isInsideFooterDetails = (target: EventTarget | null) => {
      const node = target as Node | null
      return !!node && footerDetailsRef.current?.contains(node)
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (!isInsideFooterDetails(event.target)) setFooterDetailsOpen(null)
    }
    const handleFocusIn = (event: FocusEvent) => {
      if (!isInsideFooterDetails(event.target)) setFooterDetailsOpen(null)
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setFooterDetailsOpen(null)
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('focusin', handleFocusIn)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('focusin', handleFocusIn)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [footerDetailsOpen])

  useEffect(() => {
    const parts = partsUsed || []
    if (!parts.length) return
    const isSameMoney = (a: string | number | null | undefined, b: string | number | null | undefined) => (
      Math.abs((parseFloat(String(a ?? '0')) || 0) - (parseFloat(String(b ?? '0')) || 0)) < 0.005
    )
    if (parts.every((part) => isSameMoney(part.unit_price, part.list_price ?? part.unit_price))) {
      setPartsPricingMode('list')
      setDraftPartsPricingMode('list')
      return
    }
    if (parts.every((part) => part.unit_cost != null && isSameMoney(part.unit_price, part.unit_cost))) {
      setPartsPricingMode('stock')
      setDraftPartsPricingMode('stock')
    }
  }, [partsUsed])

  const savePricingAdjustments = async () => {
    setDiscountsSaving(true)
    try {
      if (draftPartsPricingMode !== partsPricingMode) {
        await api.post(`/repair-orders/${orderId}/parts/pricing-mode`, { mode: draftPartsPricingMode })
        setPartsPricingMode(draftPartsPricingMode)
      }
      await api.patch(`/repair-orders/${orderId}/discounts`, {
        labor_discount_amount: laborDiscount.trim() === '' ? '0' : laborDiscount,
        order_discount_amount: orderDiscount.trim() === '' ? '0' : orderDiscount,
      })
      await invalidate()
    } catch (err: unknown) {
      toast.error(errorDetail(err, 'Failed to apply pricing adjustments'))
    } finally {
      setDiscountsSaving(false)
    }
  }

  const addPart = useMutation({
    mutationFn: async ({
      inventoryId,
      quantity,
      sourceServiceId,
      sourceLineId,
      allowStockShortage = false,
    }: PartAddRequest) => {
      const inventoryItem = inventory?.find((item) => item.id === inventoryId)
      const body: {
        inventory_id: string
        quantity: number
        source_service_id: string | null
        source_line_id: string | null
        unit_price?: string
        allow_stock_shortage: boolean
      } = {
        inventory_id: inventoryId,
        quantity,
        source_service_id: sourceServiceId || null,
        source_line_id: sourceLineId || null,
        allow_stock_shortage: allowStockShortage,
      }
      if (partsPricingMode === 'stock' && inventoryItem?.cost != null) {
        body.unit_price = inventoryItem.cost
      }
      await api.post(`/repair-orders/${orderId}/parts`, body)
    },
    onSuccess: async (_data, variables) => {
      setStockShortages((current) => {
        const next = { ...current }
        delete next[partAddKey(variables.inventoryId, variables.sourceLineId)]
        return next
      })
      setSearchTerm('')
      setPartQuantitiesByItemId((current) => {
        const next = { ...current }
        delete next[variables.quantityKey || variables.inventoryId]
        return next
      })
      setPaletteOpen(false)
      setOperationPartPickerLineId(null)
      await invalidate()
      toast.success('Part added')
    },
    onError: (err: unknown, variables) => {
      const shortage = stockShortageFromError(err)
      if (shortage && shortage.inventoryId === variables.inventoryId) {
        setStockShortages((current) => ({
          ...current,
          [partAddKey(variables.inventoryId, variables.sourceLineId)]: shortage,
        }))
        toast.error('Inventory count is short — review the inline stock check.')
        return
      }
      toast.error(errorDetail(err, 'Unable to add part'))
    },
  })

  const searchOps = useMutation({
    mutationFn: async (query: string): Promise<SearchResponse> => {
      const response = await api.post(`/repair-orders/${orderId}/price-build/repair-ops/search`, {
        query,
      })
      return response.data
    },
    onSuccess: (data) => {
      setCandidates(data.candidates || [])
      setSearchWarnings(data.warnings || [])
    },
    onError: () => toast.error('Repair operation search failed'),
  })

  useEffect(() => {
    if (addType !== 'saved_labor') return
    setLaborBookTimeForm((current) => ({
      ...current,
      operation_name: searchTerm.trim(),
      vehicle_year: current.vehicle_year || (vehicleYear ? String(vehicleYear) : ''),
      vehicle_make: current.vehicle_make || vehicleMake || '',
      vehicle_model: current.vehicle_model || vehicleModel || '',
      vin_sample: current.vin_sample || vehicleVin || '',
    }))
  }, [addType, searchTerm, vehicleMake, vehicleModel, vehicleVin, vehicleYear])

  // Live suggestions as the user types, debounced so we don't hit the API on every keystroke.
  useEffect(() => {
    if (addType !== 'operation') {
      setCandidates([])
      setSearchWarnings([])
      return
    }
    const trimmed = searchTerm.trim()
    if (trimmed.length < 3) {
      setCandidates([])
      setSearchWarnings([])
      return
    }
    const timer = setTimeout(() => {
      searchOps.mutate(trimmed)
    }, 350)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchTerm])

  const isNoMatchCandidate = searchWarnings.some((w) => w.code === 'no_saved_match')

  const applyRepairOp = useMutation({
    mutationFn: async ({ candidate, estimatedHours }: { candidate: RepairOperationCandidate; estimatedHours?: string }) => {
      const hours = estimatedHours != null ? parseFloat(estimatedHours || '0') : parseFloat(candidate.estimated_hours || '0')
      if (estimatedHours != null && (!Number.isFinite(hours) || hours <= 0)) {
        throw new Error('Book time hours must be greater than 0')
      }
      const response = await api.post(`/repair-orders/${orderId}/price-build/repair-ops/apply`, {
        operation_id: candidate.operation_id,
        name: candidate.name,
        description: candidate.description,
        estimated_hours: estimatedHours != null ? hours : candidate.estimated_hours,
        provider: candidate.provider,
        auto_recalc_enabled: true,
      })
      return response.data as PriceBuildSummary
    },
    onSuccess: async (data) => {
      const targetedWarnings = (data.warnings || []).filter((warning) => warning.line_id)
      if (targetedWarnings.length) {
        setLineWarnings((current) => {
          const next = { ...current }
          for (const warning of targetedWarnings) {
            const lineId = warning.line_id as string
            next[lineId] = [...(next[lineId] || []).filter((item) => item.code !== warning.code || item.message !== warning.message), warning]
          }
          return next
        })
        setOpenLineIds((current) => {
          const next = new Set(current)
          targetedWarnings.forEach((warning) => {
            if (warning.line_id) next.add(warning.line_id)
          })
          return next
        })
      }
      setSearchTerm('')
      setBookTimeHours('1')
      setCandidates([])
      setSearchWarnings([])
      setPaletteOpen(false)
      await invalidate()
      if (!targetedWarnings.length) toast.success('Repair operation applied')
    },
    onError: (err: unknown) => toast.error(err instanceof Error ? err.message : 'Unable to apply operation'),
  })

  // Fork from the simple "new operation" row into the full Labor Book Time form:
  // for complex jobs whose hours depend on the specific truck/engine. Carries
  // over the typed name + hours; truck fields prefill from the RO's vehicle.
  const forkToLaborBookTime = () => {
    setLaborBookTimeForm({
      ...initialLaborBookTimeForm(),
      operation_name: searchTerm.trim(),
      normalized_hours: bookTimeHours || '1',
    })
    setAddType('saved_labor')
    setShowLaborBookTimeForm(true)
    setPaletteOpen(true)
  }

  // Reverse of forkToLaborBookTime: go back to the simple ad-hoc operation,
  // carrying the labor name + hours the user has entered so far.
  const forkBackToOperation = () => {
    setSearchTerm(laborBookTimeForm.operation_name.trim())
    setBookTimeHours(laborBookTimeForm.normalized_hours || '1')
    setShowLaborBookTimeForm(false)
    setAddType('operation')
    setPaletteOpen(true)
  }

  const applyLaborBookEntry = useMutation({
    mutationFn: async (entry: LaborBookTimeEntry) => {
      const candidate = laborBookTimeCandidate(entry)
      await api.post(`/repair-orders/${orderId}/price-build/repair-ops/apply`, {
        operation_id: candidate.operation_id,
        name: candidate.name,
        description: candidate.description,
        estimated_hours: candidate.estimated_hours,
        provider: candidate.provider,
        auto_recalc_enabled: true,
      })
    },
    onSuccess: async () => {
      setSearchTerm('')
      setLaborBookTimeForm(initialLaborBookTimeForm())
      setPaletteOpen(false)
      await invalidate()
      toast.success('Labor book time added')
    },
    onError: (err: unknown) => toast.error(errorDetail(err, 'Unable to add labor book time')),
  })

  const createAndApplyLaborBookTime = useMutation({
    mutationFn: async () => {
      const hours = Number(laborBookTimeForm.normalized_hours)
      const year = Number(laborBookTimeForm.vehicle_year)
      if (!laborBookTimeForm.operation_name.trim()) throw new Error('Labor name is required')
      if (!Number.isFinite(hours) || hours <= 0) throw new Error('Book hours must be greater than zero')
      if (!Number.isInteger(year) || year < 1900 || !laborBookTimeForm.vehicle_make.trim() || !laborBookTimeForm.vehicle_model.trim()) {
        throw new Error('Year, make, and model are required')
      }
      const response = await api.post('/labor-book-time', {
        operation_name: laborBookTimeForm.operation_name.trim(),
        operation_description: nullableText(laborBookTimeForm.operation_description),
        normalized_hours: hours,
        vehicle_year: year,
        vehicle_make: laborBookTimeForm.vehicle_make.trim(),
        vehicle_model: laborBookTimeForm.vehicle_model.trim(),
        vehicle_type: nullableText(laborBookTimeForm.vehicle_type),
        body_class: nullableText(laborBookTimeForm.body_class),
        engine: nullableText(laborBookTimeForm.engine),
        fuel_type: nullableText(laborBookTimeForm.fuel_type),
        engine_cylinders: nullableNumber(laborBookTimeForm.engine_cylinders),
        engine_displacement_l: nullableNumber(laborBookTimeForm.engine_displacement_l),
        gvwr: nullableText(laborBookTimeForm.gvwr),
        vin_sample: nullableText(laborBookTimeForm.vin_sample.toUpperCase()),
      })
      const entry = response.data as LaborBookTimeEntry
      const candidate = laborBookTimeCandidate(entry)
      await api.post(`/repair-orders/${orderId}/price-build/repair-ops/apply`, {
        operation_id: candidate.operation_id,
        name: candidate.name,
        description: candidate.description,
        estimated_hours: candidate.estimated_hours,
        provider: candidate.provider,
        auto_recalc_enabled: true,
      })
      return entry
    },
    onSuccess: async (entry) => {
      queryClient.invalidateQueries({ queryKey: ['labor-book-time'] })
      setSearchTerm('')
      setLaborBookTimeForm(initialLaborBookTimeForm())
      setShowLaborBookTimeForm(false)
      await invalidate()
      toast.success(`${entry.operation_name} saved and added`)
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : errorDetail(err, 'Unable to save labor book time'))
    },
  })

  const decodeLaborBookVin = useMutation({
    mutationFn: async () => {
      const vin = laborBookTimeForm.vin_sample.trim().toUpperCase()
      if (vin.length < 11) throw new Error('Enter at least 11 VIN characters to decode')
      const response = await api.get(`/customers/vin/decode/${encodeURIComponent(vin)}`, {
        params: laborBookTimeForm.vehicle_year.trim() ? { model_year: laborBookTimeForm.vehicle_year.trim() } : undefined,
      })
      return response.data as VinDecodeResult
    },
    onSuccess: (decoded) => {
      if (decoded.error_text && !decoded.make && !decoded.model) {
        setVinDecodeStatus({ ok: false, message: decoded.error_text })
        return
      }
      setLaborBookTimeForm((current) => ({
        ...current,
        vin_sample: decoded.vin || current.vin_sample,
        vehicle_year: decoded.year ? String(decoded.year) : current.vehicle_year,
        vehicle_make: decoded.make || current.vehicle_make,
        vehicle_model: decoded.model || current.vehicle_model,
        vehicle_type: decoded.vehicle_type || current.vehicle_type,
        body_class: decoded.body_class || current.body_class,
        fuel_type: decoded.fuel_type || current.fuel_type,
        engine_cylinders: decoded.engine_cylinders ? String(decoded.engine_cylinders) : current.engine_cylinders,
        engine_displacement_l: decoded.engine_displacement_l ? String(decoded.engine_displacement_l) : current.engine_displacement_l,
        gvwr: decoded.gvwr || current.gvwr,
      }))
      setVinDecodeStatus({ ok: true, message: 'Decoded' })
    },
    onError: (err: unknown) => {
      setVinDecodeStatus({ ok: false, message: err instanceof Error ? err.message : errorDetail(err, 'Failed to decode VIN') })
    },
  })

  // Auto-decode a full (17-char) VIN when it's typed or prefilled, so the user
  // doesn't have to click "Decode VIN". A ref tracks the last VIN we auto-decoded
  // so onSuccess writing the VIN back doesn't retrigger this.
  const lastAutoDecodedVin = useRef<string>('')
  const vinToDecode = laborBookTimeForm.vin_sample.trim().toUpperCase()
  useEffect(() => {
    if (addType !== 'saved_labor' || !showLaborBookTimeForm) return
    if (vinToDecode.length !== 17) return
    if (vinToDecode === lastAutoDecodedVin.current) return
    if (decodeLaborBookVin.isPending) return
    lastAutoDecodedVin.current = vinToDecode
    decodeLaborBookVin.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vinToDecode, addType, showLaborBookTimeForm])

  const updateLine = useMutation({
    mutationFn: async ({
      lineId,
      body,
    }: {
      lineId: string
      body: { description?: string; hours?: number; hourly_rate?: number }
    }) => {
      await api.patch(`/repair-orders/${orderId}/price-build/lines/${lineId}`, body)
    },
    onSuccess: async () => {
      await invalidate()
    },
    onError: () => toast.error('Unable to update line'),
  })

  const removeLine = useMutation({
    mutationFn: async (lineId: string) => {
      await api.delete(`/repair-orders/${orderId}/price-build/lines/${lineId}`)
    },
    onSuccess: async () => {
      await invalidate()
      toast.success('Line removed')
    },
    onError: () => toast.error('Unable to remove line'),
  })

  const lineTypeLabel = (line: { line_type: string; source_service_id?: string | null }) => {
    if (line.source_service_id) return 'service labor'
    return line.line_type.replace('_', ' ')
  }

  const toggleLine = (lineId: string) => {
    setOpenLineIds((current) => {
      const next = new Set(current)
      if (next.has(lineId)) next.delete(lineId)
      else next.add(lineId)
      return next
    })
  }

  const discountTotal = (
    (parseFloat(summary?.labor_discount_amount || '0') || 0) +
    (parseFloat(summary?.order_discount_amount || '0') || 0)
  )
  const partsSavingsTotal = (partsUsed || []).reduce(
    (sum, pu) => sum + (parseFloat(pu.savings || '0') || 0),
    0,
  )
  const customerSavesTotal = partsSavingsTotal + discountTotal
  const laborLines = effectiveLaborLines
  const footerParts = partsUsed || []
  const laborDiscountAmount = parseFloat(summary?.labor_discount_amount || '0') || 0
  const orderDiscountAmount = parseFloat(summary?.order_discount_amount || '0') || 0
  const draftPartsSavingsTotal = footerParts.reduce((sum, part) => {
    const quantity = parseFloat(part.quantity || '0') || 0
    const listPrice = part.list_price != null ? parseFloat(part.list_price) : parseFloat(part.unit_price || '0')
    const stockCost = part.unit_cost != null ? parseFloat(part.unit_cost) : null
    if (draftPartsPricingMode === 'stock' && stockCost != null && Number.isFinite(listPrice)) {
      return sum + Math.max(0, (listPrice - stockCost) * quantity)
    }
    if (draftPartsPricingMode === 'list') return sum
    return sum + (parseFloat(part.savings || '0') || 0)
  }, 0)
  const draftDiscountTotal = (
    (parseFloat(laborDiscount || '0') || 0) +
    (parseFloat(orderDiscount || '0') || 0)
  )
  const draftCustomerSavesTotal = draftPartsSavingsTotal + draftDiscountTotal
  const priceUpdating = (
    summaryFetching ||
    partsFetching ||
    discountsSaving ||
    editingPartsSaving ||
    !!priceSavingId ||
    addPart.isPending ||
    applyRepairOp.isPending ||
    applyLaborBookEntry.isPending ||
    createAndApplyLaborBookTime.isPending ||
    updateLine.isPending ||
    removeLine.isPending
  )
  const isApplyingOperationCandidate = (candidate: RepairOperationCandidate) => (
    applyRepairOp.isPending && applyRepairOp.variables?.candidate.operation_id === candidate.operation_id
  )
  const isApplyingLaborBookEntry = (entry: LaborBookTimeEntry) => (
    applyLaborBookEntry.isPending && applyLaborBookEntry.variables?.id === entry.id
  )
  const isAddingPartFor = (inventoryId: string, sourceLineId: string | null) => (
    addPart.isPending &&
    addPart.variables?.inventoryId === inventoryId &&
    (addPart.variables?.sourceLineId ?? null) === sourceLineId
  )
  const isAddingStandalonePart = addPart.isPending && !addPart.variables?.sourceLineId
  const isAddingPartToLine = (lineId: string) => (
    addPart.isPending && addPart.variables?.sourceLineId === lineId
  )
  const pendingWorkMessage = applyRepairOp.isPending
    ? 'Adding operation to work & labor…'
    : applyLaborBookEntry.isPending
      ? 'Adding labor book time to work & labor…'
      : createAndApplyLaborBookTime.isPending
        ? 'Saving and adding labor book time…'
        : addPart.isPending
          ? 'Adding part to work & labor…'
          : null
  // `summary.total_cost` bakes in the server's (possibly stale) labor_total;
  // shift it by however far our optimistic labor total has diverged so the
  // order total moves in lockstep with the steppers instead of waiting for
  // the debounced write + refetch to land.
  const serverLaborTotal = parseFloat(summary?.labor_total || '0') || 0
  const orderTotalValue = summary
    ? String((parseFloat(summary.total_cost || '0') || 0) + (effectiveLaborTotal - serverLaborTotal))
    : '0'
  // Totals genuinely default to zero for a brand-new order, but they also
  // read as zero while `summary` hasn't loaded yet for a just-opened order —
  // those are different states. The old signal for "still loading" was a
  // fixed 720ms animation timer (totalMotionActive), which times out before
  // a slow/rate-limited fetch actually finishes, so a real order would flash
  // $0.00 / "start by adding an operation" before its real total arrived.
  // Key this off the query's own state instead.
  const isInitialSummaryLoad = isLoading && !summary && !isDeleted
  // A failed fetch (e.g. 429 from fast prev/next navigation outrunning the
  // rate limit) also leaves `summary` undefined once the query settles into
  // an error — without this, that renders identically to a real empty order
  // ($0.00, "start by adding an operation"), silently showing wrong totals
  // for an order that may have real line items the fetch never returned.
  // Not a failure when the order is deleted — we intentionally don't fetch then.
  const summaryLoadFailed = summaryErrored && !summary && !isDeleted

  useEffect(() => {
    if (!priceUpdating) return
    setTotalMotionActive(true)
    if (totalMotionTimerRef.current) window.clearTimeout(totalMotionTimerRef.current)
    totalMotionTimerRef.current = window.setTimeout(() => {
      setTotalMotionActive(false)
      totalMotionTimerRef.current = null
    }, 720)
  }, [priceUpdating])

  useEffect(() => () => {
    if (totalMotionTimerRef.current) window.clearTimeout(totalMotionTimerRef.current)
  }, [])

  useEffect(() => {
    if (!summary?.total_cost) return
    if (previousTotalRef.current == null) {
      previousTotalRef.current = summary.total_cost
      return
    }
    if (previousTotalRef.current === summary.total_cost) return
    previousTotalRef.current = summary.total_cost
    setTotalJustChanged(true)
    setTotalMotionActive(true)
    if (totalMotionTimerRef.current) window.clearTimeout(totalMotionTimerRef.current)
    totalMotionTimerRef.current = window.setTimeout(() => {
      setTotalMotionActive(false)
      totalMotionTimerRef.current = null
    }, 720)
    const timer = window.setTimeout(() => setTotalJustChanged(false), 1250)
    return () => window.clearTimeout(timer)
  }, [summary?.total_cost])

  const renderFooterDetailRows = (rows: Array<{ label: string; meta?: string; value: string; valueClassName?: string }>, emptyText: string) => (
    rows.length ? (
      <div className="max-h-72 overflow-y-auto pr-1">
        {rows.map((row, index) => (
          <div key={`${row.label}-${index}`} className="flex items-start justify-between gap-3 border-b border-gray-100 py-2 last:border-0">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-gray-800">{row.label}</p>
              {row.meta && <p className="truncate font-['JetBrains_Mono',monospace] text-[11px] text-gray-500">{row.meta}</p>}
            </div>
            <span className={`shrink-0 font-['JetBrains_Mono',monospace] text-sm font-semibold ${row.valueClassName || 'text-gray-900'}`}>
              {row.value}
            </span>
          </div>
        ))}
      </div>
    ) : (
      <p className="rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-500">{emptyText}</p>
    )
  )

  const renderFooterDetails = (metric: typeof footerDetailsOpen) => {
    if (!metric) return null
    if (metric === 'parts') {
      const rows = footerParts.map((part) => ({
        label: part.inventory_name,
        meta: `${part.quantity} ${UNIT_ABBR[part.unit_type] || part.unit_type} × ${money(part.unit_price)}`,
        value: money(part.total_price),
      }))
      return (
        <>
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-blue-500">Parts total</p>
          {renderFooterDetailRows(rows, 'No parts added yet.')}
        </>
      )
    }
    if (metric === 'labor') {
      const rows = laborLines.map((line) => ({
        label: line.description || lineTypeLabel(line),
        meta: `${formatHoursMinutes(line.hours)} × ${money(line.hourly_rate)}/hr`,
        value: money(line.total_cost),
      }))
      return (
        <>
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-orange-500">Labor total</p>
          {renderFooterDetailRows(rows, 'No labor lines added yet.')}
        </>
      )
    }
    if (metric === 'discounts') {
      const rows = [
        ...(laborDiscountAmount > 0 ? [{ label: 'Labor discount', meta: 'Applied against labor subtotal', value: `-${money(laborDiscountAmount)}`, valueClassName: 'text-red-600' }] : []),
        ...(orderDiscountAmount > 0 ? [{ label: 'Order discount', meta: 'Applied against final order total', value: `-${money(orderDiscountAmount)}`, valueClassName: 'text-red-600' }] : []),
      ]
      return (
        <>
          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-red-500">Discounts</p>
          {renderFooterDetailRows(rows, 'No labor or order discounts applied.')}
        </>
      )
    }
    const partSavingsRows = footerParts
      .filter((part) => (parseFloat(part.savings || '0') || 0) > 0)
      .map((part) => ({
        label: part.inventory_name,
        meta: `${part.quantity} ${UNIT_ABBR[part.unit_type] || part.unit_type} saved from list price`,
        value: money(part.savings),
        valueClassName: 'text-emerald-700',
      }))
    const discountRows = [
      ...(laborDiscountAmount > 0 ? [{ label: 'Labor discount', meta: 'Direct labor savings', value: money(laborDiscountAmount), valueClassName: 'text-emerald-700' }] : []),
      ...(orderDiscountAmount > 0 ? [{ label: 'Order discount', meta: 'Direct order savings', value: money(orderDiscountAmount), valueClassName: 'text-emerald-700' }] : []),
    ]
    return (
      <>
        <p className="mb-2 text-xs font-bold uppercase tracking-wide text-emerald-600">Customer saves</p>
        {renderFooterDetailRows([...partSavingsRows, ...discountRows], 'No savings applied yet.')}
      </>
    )
  }

  useEffect(() => {
    if (!defaultLaborRate || !canMutate) return
    // No-op placeholder: keeps default labor rate available for future quick-add UX.
  }, [defaultLaborRate, canMutate])

  return (
    <div className="relative flex h-full min-h-full flex-col overflow-hidden bg-white">
      <div
        className="px-5 py-4 text-white"
        style={{
          background: isInternalOrder
            ? 'linear-gradient(100deg,#1e3a8a,#0f172a)'
            : 'linear-gradient(100deg,#f7a823,#e07c05)',
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            {/* Internal fleet gets a small qualifier; a plain repair order needs
                no label — the #number is self-evidently the order. */}
            {isInternalOrder && (
              <p className="hidden text-[11px] font-bold uppercase tracking-[0.18em] text-white/75 sm:block">
                Internal Fleet Order
              </p>
            )}
            <OrderNumberHeader value={`#${orderNumber || orderId.slice(0, 8)}`} />
            {quoteNumber && (
              <p className="mt-1 truncate font-['JetBrains_Mono',monospace] text-[11px] font-semibold text-white/70">
                {quoteNumber}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {onPrev && (
              <button
                type="button"
                onClick={onPrev}
                disabled={prevDisabled}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-white/14 text-white ring-1 ring-white/20 disabled:opacity-35"
                aria-label="Previous repair order"
              >
                <ChevronRight className="h-4 w-4 rotate-180" />
              </button>
            )}
            {navigationLabel && (
              <span className="whitespace-nowrap rounded-full bg-white/14 px-3.5 py-1.5 font-['JetBrains_Mono',monospace] text-sm font-semibold tabular-nums text-white/90">
                {navigationLabel}
              </span>
            )}
            {onNext && (
              <button
                type="button"
                onClick={onNext}
                disabled={nextDisabled}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-white/14 text-white ring-1 ring-white/20 disabled:opacity-35"
                aria-label="Next repair order"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            )}
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-white/14 text-white ring-1 ring-white/20 hover:bg-white/20"
                aria-label="Close repair order"
              >
                <X className="h-5 w-5" />
              </button>
            )}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs font-semibold">
          <span className="rounded-full bg-white px-3 py-1.5 text-blue-700">{orderStatus === 'draft' ? 'checked in' : orderStatus.replace('_', ' ')}</span>
          <span className="inline-flex items-center gap-1 rounded-full bg-white/14 px-3 py-1.5 text-white ring-1 ring-white/20">
            <Building2 className="h-3.5 w-3.5" />
            {customerName || 'Customer'}
          </span>
          {/* Vehicle chip is the least critical here — hide it on mobile so the
              status + company stay on one tidy row. */}
          <span className="hidden items-center gap-1 rounded-full bg-white/14 px-3 py-1.5 text-white ring-1 ring-white/20 sm:inline-flex">
            <Truck className="h-3.5 w-3.5" />
            {[vehicleUnit, vehicleLabel].filter(Boolean).join(' · ') || 'Truck'}
          </span>
        </div>
      </div>

      {/* Operational workflow is primary. Estimates are optional authorization
          records and appear as a secondary action, never as a work gate. */}
      {!isInternalOrder && !isFinalized && (
        <>
        <div className="flex items-center border-b border-orange-100 bg-orange-50/60 px-5 py-2.5 text-xs">
          <div className="flex w-full min-w-0 items-center gap-2 overflow-x-auto whitespace-nowrap">
            <span className={`rounded-full px-2.5 py-1 font-semibold ${
              orderStatus !== 'draft' ? 'bg-emerald-100 text-emerald-700' : 'bg-orange-500 text-white'
            }`}>
              {orderStatus === 'draft' ? 'Checked in' : '✓ Checked in'}
            </span>
            <span className="text-gray-300">→</span>
            <span className={`rounded-full px-2.5 py-1 font-semibold ${
              hasAssignedTechnician || technicianAssignmentBypassed
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-white text-amber-700 ring-1 ring-amber-200'
            }`}>
              {hasAssignedTechnician ? `✓ ${assignedTechnicianName}` : technicianAssignmentBypassed ? '✓ Shop-managed' : 'Assign technician'}
            </span>
            <span className="text-gray-300">→</span>
            <span className={`rounded-full px-2.5 py-1 font-semibold ${
              ['in_progress', 'pending_review'].includes(orderStatus)
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-transparent text-gray-400'
            }`}>
              {orderStatus === 'in_progress' ? 'In the bay' : ['pending_review'].includes(orderStatus) ? '✓ Work complete' : 'In the bay'}
            </span>
            <span className="text-gray-300">→</span>
            <span className={`rounded-full px-2.5 py-1 font-semibold ${
              orderStatus === 'pending_review'
                ? 'bg-orange-500 text-white'
                : 'bg-transparent text-gray-400'
            }`}>
              Quality review
            </span>
            {onQuoteAction && canMutate && (
              <button
                type="button"
                onClick={onQuoteAction}
                disabled={quoteActionBlocked || quoteActionPending}
                title={quoteButtonDisabledReason}
                className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-lg border border-amber-200 bg-white px-2.5 font-semibold text-amber-800 hover:bg-amber-50 disabled:opacity-50"
              >
                {quoteActionPending ? <Spinner size="xs" /> : <FileText className="h-3.5 w-3.5" />}
                {quoteActionPending ? 'Working…' : quoteActionLabel}
              </button>
            )}
          </div>
        </div>
        {canManageTechnician && ((onAssignTechnician && availableTechnicians.length > 0) || canOverrideTechnicianAssignment) && (
          <div className="border-t border-orange-100 bg-white px-5 py-3">
            <button
              type="button"
              onClick={() => setTechnicianAssignmentOpen((open) => !open)}
              className={`flex w-full items-center justify-between gap-2 text-left ${technicianAssignmentOpen ? 'mb-2' : ''}`}
              aria-expanded={technicianAssignmentOpen}
            >
              <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-gray-500">
                {hasAssignedTechnician ? 'Reassign technician' : 'Assign technician'}
              </span>
              {hasAssignedTechnician && assignedTechnicianName && (
                <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                  Current: {assignedTechnicianName}
                </span>
              )}
              {!hasAssignedTechnician && (
                <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${technicianAssignmentOpen ? 'rotate-180' : ''}`} />
              )}
            </button>
            {technicianAssignmentOpen && onAssignTechnician && availableTechnicians.length > 0 && (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {availableTechnicians.map((tech) => (
                  <button
                    key={tech.mechanic_id}
                    type="button"
                    onClick={() => onAssignTechnician(tech.mechanic_id)}
                    disabled={technicianAssignmentPending || technicianOverridePending}
                    className="rounded-lg border border-gray-200 bg-white p-2.5 text-left transition hover:border-orange-300 hover:bg-orange-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-semibold text-gray-900">{tech.mechanic_name}</span>
                      <span className={`text-xs font-bold ${tech.load < 50 ? 'text-emerald-600' : tech.load < 80 ? 'text-orange-600' : 'text-red-600'}`}>
                        {tech.load.toFixed(0)}%
                      </span>
                    </div>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-100">
                      <div
                        className={`h-full rounded-full ${tech.load < 50 ? 'bg-emerald-500' : tech.load < 80 ? 'bg-orange-500' : 'bg-red-500'}`}
                        style={{ width: `${tech.load}%` }}
                      />
                    </div>
                  </button>
                ))}
              </div>
            )}
            {technicianAssignmentOpen && canOverrideTechnicianAssignment && (
              <div className="mt-3 rounded-lg border border-dashed border-amber-300 bg-amber-50/70 p-3">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-amber-900">Start without assigning a technician</p>
                    <p className="mt-0.5 text-xs text-amber-700">Admin override for work handled verbally or outside the mechanic portal.</p>
                  </div>
                  <button
                    type="button"
                    onClick={onOverrideTechnicianAssignment}
                    disabled={technicianOverridePending || technicianAssignmentPending}
                    className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-lg bg-amber-600 px-3 text-sm font-bold text-white hover:bg-amber-700 disabled:bg-gray-300"
                  >
                    {technicianOverridePending ? <Spinner size="xs" /> : <Play className="h-4 w-4" />}
                    {technicianOverridePending ? 'Starting...' : 'Override & start'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
        </>
      )}

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5 pb-4">

      {description && description.trim() && (
        <div>
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-1">Work Requested</p>
          <div className="rounded-lg bg-gray-50 p-3 text-sm text-gray-800 whitespace-pre-wrap">
            {description}
          </div>
        </div>
      )}

      {!!summary?.warnings?.filter((w) => !w.line_id).length && (
        <div className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          {summary.warnings.filter((w) => !w.line_id).map((w) => (
            <p key={`${w.code}-${w.message}`} className="text-xs text-amber-800">
              {w.message}
            </p>
          ))}
        </div>
      )}

      {(addType === 'operation' || addType === 'saved_labor') && !!searchWarnings.length && (
        <div className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          {searchWarnings.map((w) => (
            <p key={`${w.code}-${w.message}`} className="text-xs text-amber-800">
              {w.message}
            </p>
          ))}
        </div>
      )}

      {hasInvoice && invoice && (
        <div className="rounded-2xl border border-purple-200 bg-purple-50/70 p-3">
          <button
            type="button"
            onClick={() => setInvoiceDetailsOpen((open) => !open)}
            className="flex w-full items-center justify-between gap-3 text-left"
            aria-expanded={invoiceDetailsOpen}
          >
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-purple-100 text-purple-700">
                <FileText className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <p className="truncate font-semibold text-purple-950">Invoice {invoice.invoice_number}</p>
                <p className="text-sm text-purple-700">
                  {orderStatus === 'paid' ? 'Paid' : invoice.pending_zelle_confirmation ? 'Pending Zelle confirmation' : 'Awaiting payment'}
                </p>
              </div>
            </div>
            <span className="flex shrink-0 items-center gap-3">
              <span className="text-right">
                {invoice.due_date && (
                  <span className="block text-[11px] font-semibold uppercase tracking-wide text-purple-500">
                    Due {new Date(invoice.due_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                  </span>
                )}
                <span className="font-['Barlow_Condensed',sans-serif] text-2xl font-extrabold leading-none text-purple-950">
                  {money(invoiceDisplayTotal)}
                </span>
              </span>
              <ChevronRight className={`h-4 w-4 text-purple-500 transition-transform ${invoiceDetailsOpen ? 'rotate-90' : ''}`} />
            </span>
          </button>

          {invoice.pending_zelle_confirmation && (
            <div className="mt-3 rounded-xl border border-yellow-200 bg-yellow-50 px-3 py-2 text-sm text-yellow-900">
              Customer marked this invoice as paid via Zelle. Confirm receipt from the footer payment action.
            </div>
          )}

          {invoiceDetailsOpen && (
          <div className="mt-3 space-y-2 rounded-xl bg-white p-3 text-sm ring-1 ring-purple-100">
            <div className="flex items-center justify-between">
              <span className="text-gray-500">Repair subtotal</span>
              <span className="font-semibold text-gray-900">{money(invoice.subtotal)}</span>
            </div>
            {parseFloat(invoice.shop_supplies_amount || '0') > 0 && (
              <div className="flex items-center justify-between">
                <span className="text-gray-500">Shop supplies</span>
                <span className="font-semibold text-gray-900">{money(invoice.shop_supplies_amount)}</span>
              </div>
            )}
            {!invoice.pending_zelle_confirmation && parseFloat(invoice.service_fee_amount || '0') > 0 && (
              <div className="flex items-center justify-between">
                <span className="text-gray-500">Card processing fee</span>
                <span className="font-semibold text-gray-900">{money(invoice.service_fee_amount)}</span>
              </div>
            )}
            {parseFloat(invoice.tax_amount || '0') > 0 && (
              <div className="flex items-center justify-between">
                <span className="text-gray-500">Tax</span>
                <span className="font-semibold text-gray-900">{money(invoice.tax_amount)}</span>
              </div>
            )}
            {parseFloat(invoice.discount_amount || '0') > 0 && (
              <div className="flex items-center justify-between text-emerald-700">
                <span>Invoice discount</span>
                <span className="font-semibold">-{money(invoice.discount_amount)}</span>
              </div>
            )}
            <div className="flex items-center justify-between border-t border-purple-100 pt-2">
              <span className="font-semibold text-purple-950">
                {invoice.pending_zelle_confirmation ? 'Zelle total' : 'Invoice total'}
              </span>
              <span className="font-['Barlow_Condensed',sans-serif] text-2xl font-extrabold text-purple-950">{money(invoiceDisplayTotal)}</span>
            </div>
            {invoice.payment && (
              <div className="mt-2 flex items-start justify-between gap-3 rounded-xl bg-emerald-50 px-3 py-2 ring-1 ring-emerald-100">
                <div className="min-w-0">
                  <p className="text-[11px] font-bold uppercase tracking-wide text-emerald-700">Paid</p>
                  <p className="text-xs text-emerald-800">
                    {PAYMENT_METHOD_LABELS[invoice.payment.method] || invoice.payment.method}
                    {invoice.payment.paid_at && ` · ${new Date(invoice.payment.paid_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}`}
                    {invoice.payment.recorded_by_name && ` · by ${invoice.payment.recorded_by_name}`}
                  </p>
                  {(invoice.payment.payment_provider || invoice.payment.reference_number) && (
                    <p className="mt-0.5 break-all text-[11px] text-emerald-700">
                      {[
                        invoice.payment.payment_provider,
                        invoice.payment.reference_number && `Ref ${invoice.payment.reference_number}`,
                        invoice.payment.authorization_number && `Auth ${invoice.payment.authorization_number}`,
                      ].filter(Boolean).join(' · ')}
                    </p>
                  )}
                </div>
                <span className="shrink-0 font-['Barlow_Condensed',sans-serif] text-xl font-extrabold text-emerald-700">
                  {money(invoice.payment.amount)}
                </span>
              </div>
            )}
          </div>
          )}
        </div>
      )}

      {canAdminCompleteBypassedWork && armWoComplete && (
        <div className="rounded-2xl border border-yellow-200 bg-yellow-50/70 p-4">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-yellow-100 text-yellow-700">
              <CheckCircle className="h-4 w-4" />
            </div>
            <div>
              <p className="font-semibold text-yellow-950">Mark work completed</p>
              <p className="text-sm text-yellow-700">Moves this admin-started order to review so it can be approved and invoiced.</p>
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setArmWoComplete(false)}
              className="inline-flex h-9 items-center rounded-lg border border-gray-200 px-3 text-sm font-semibold text-gray-600 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={adminCompleteWorkPending}
              onClick={onAdminCompleteWork}
              className="inline-flex h-9 items-center gap-2 rounded-lg bg-yellow-500 px-3 text-sm font-bold text-white hover:bg-yellow-600 disabled:bg-gray-300"
            >
              {adminCompleteWorkPending ? <Spinner size="xs" /> : <CheckCircle className="h-4 w-4" />}
              {adminCompleteWorkPending ? 'Completing...' : 'Mark completed'}
            </button>
          </div>
        </div>
      )}

      {isInternalOrder && armWoComplete && (
        <div className="rounded-2xl border border-yellow-200 bg-yellow-50/70 p-4">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-yellow-100 text-yellow-700">
              <CheckCircle className="h-4 w-4" />
            </div>
            <div>
              <p className="font-semibold text-yellow-950">Complete work order</p>
              <p className="text-sm text-yellow-700">Enter the truck's odometer, then complete. Generates the internal cost record.</p>
            </div>
          </div>

          <label className="mb-3 block text-sm">
            <span className="mb-1 block font-semibold text-yellow-800">Mileage out</span>
            <input
              type="text"
              inputMode="numeric"
              value={woMileageOut}
              onChange={(e) => { const v = e.target.value; if (v === '' || /^\d+$/.test(v)) setWoMileageOut(v) }}
              placeholder={mileageIn != null ? `Odometer at return (in: ${mileageIn.toLocaleString()} mi)` : 'Odometer reading at vehicle return'}
              className="h-10 w-full rounded-lg border border-yellow-200 bg-white px-3 text-sm text-gray-900 placeholder-gray-400 outline-none focus:border-yellow-400 focus:ring-2 focus:ring-yellow-200"
            />
          </label>

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setArmWoComplete(false)}
              className="inline-flex h-9 items-center rounded-lg border border-gray-200 px-3 text-sm font-semibold text-gray-600 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={completeWorkOrderPending}
              onClick={() => onCompleteWorkOrder?.(woMileageOut.trim() === '' ? null : Number(woMileageOut))}
              className="inline-flex h-9 items-center gap-2 rounded-lg bg-yellow-500 px-3 text-sm font-bold text-white hover:bg-yellow-600 disabled:bg-gray-300"
            >
              {completeWorkOrderPending ? <Spinner size="xs" /> : <CheckCircle className="h-4 w-4" />}
              {completeWorkOrderPending ? 'Completing…' : 'Complete work order'}
            </button>
          </div>
        </div>
      )}

      {completionMode && (
        <div className="rounded-2xl border border-orange-200 bg-orange-50/70 p-4">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-orange-100 text-orange-600">
              <CheckCircle className="h-4 w-4" />
            </div>
            <div>
              <p className="font-semibold text-orange-950">Technician completed work</p>
              <p className="text-sm text-orange-700">Review and approve to notify customer.</p>
            </div>
          </div>

          <label className="mb-3 block text-sm">
            <span className="mb-1 block font-semibold text-orange-800">Mileage out</span>
            <input
              type="text"
              inputMode="numeric"
              value={mileageOutValue}
              onChange={(e) => onMileageOutChange?.(e.target.value)}
              placeholder={mileageIn != null ? `Odometer at return (in: ${mileageIn.toLocaleString()} mi)` : 'Odometer reading at vehicle return'}
              className="h-10 w-full rounded-lg border border-orange-200 bg-white px-3 text-sm text-gray-900 placeholder-gray-400 outline-none focus:border-orange-400 focus:ring-2 focus:ring-orange-200"
            />
          </label>

          <button
            type="button"
            onClick={onToggleReviewNotes}
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-orange-800 hover:text-orange-900"
          >
            <ChevronRight className={`h-4 w-4 transition-transform ${showReviewNotes ? 'rotate-90' : ''}`} />
            Add review notes <span className="font-normal text-orange-500">(optional)</span>
          </button>
          {showReviewNotes && (
            <textarea
              value={reviewNotesValue}
              onChange={(e) => onReviewNotesChange?.(e.target.value)}
              placeholder="Add any notes about the review, additional work needed, quality observations..."
              rows={3}
              className="mt-2 w-full resize-none rounded-lg border border-orange-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 outline-none focus:border-orange-400 focus:ring-2 focus:ring-orange-200"
            />
          )}
        </div>
      )}

      {/* Editable orders get the dashed "add" shell around the tab strip + search.
          Read-only orders only surface History, so drop the shell entirely and let
          the History card stand on its own (styled like the invoice card). */}
      <div className={addBarReadOnly ? '' : 'rounded-2xl border border-dashed border-gray-300 bg-gray-50/70 p-3'}>
        <div className="flex flex-wrap items-center gap-3">
          {/* Read-only orders only have History — the single tab switches to
              nothing, and on mobile it wraps above the panel wasting a row. Drop
              the tab strip entirely; the History panel below carries its own
              header. */}
          {!addBarReadOnly && (
          <div className="grid w-full grid-cols-4 shrink-0 rounded-xl bg-white p-1 text-xs font-bold shadow-sm ring-1 ring-gray-200 sm:w-auto">
            {([
              ['operation', Wrench, 'Operation'],
              ['part', Box, 'Part'],
              ['saved_labor', Tag, 'Labor'],
              ['history', History, 'History'],
            ] as const).map(([key, Icon, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setAddType(key)
                  setPaletteOpen(key !== 'history')
                }}
                className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-2.5 py-2 ${
                  addType === key ? 'bg-orange-500 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                <Icon className="h-3.5 w-3.5 shrink-0" />
                <span>{label}</span>
              </button>
            ))}
          </div>
          )}
          {addType !== 'history' && (
          <div className="relative min-w-[240px] flex-1 basis-[240px]">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={searchTerm}
              onFocus={() => setPaletteOpen(true)}
              onChange={(e) => {
                setSearchTerm(e.target.value)
                setPaletteOpen(true)
              }}
              placeholder={
                addType === 'operation' ? 'Add operation — search jobs or services, e.g. brake change, EGR, PM Level A…' :
                addType === 'saved_labor' ? 'Search labor book time — e.g. DPF filter replacement…' :
                'Add part — search inventory by name or SKU…'
              }
              className="h-11 w-full rounded-xl border border-gray-200 bg-white pl-9 pr-10 text-sm outline-none focus:border-orange-300 focus:ring-2 focus:ring-orange-100"
            />
            {searchTerm && (
              <button
                type="button"
                onClick={() => {
                  // Clear the search and cancel any in-progress new-labor entry.
                  setSearchTerm('')
                  setSearchWarnings([])
                  setShowLaborBookTimeForm(false)
                }}
                aria-label="Clear search"
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
          )}
        </div>

        {addType === 'history' && (
          // Same card shape as the invoice display (icon circle · title/subtitle ·
          // chevron), so a read-only order shows History and Invoice as two
          // matching buttons.
          <div className="rounded-2xl border border-gray-200 bg-gray-50/70 p-3">
            <button
              type="button"
              onClick={() => {
                setHistoryOpen((open) => !open)
                setHistoryVisibleCount(5)
              }}
              className="flex w-full items-center justify-between gap-3 text-left"
              aria-expanded={historyOpen}
            >
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gray-200 text-gray-600">
                  <History className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <p className="truncate font-semibold text-gray-900">Repair order history</p>
                  <p className="text-sm text-gray-500">
                    {historyEvents.length ? `${historyEvents.length} recorded events` : 'No recorded events'}
                  </p>
                </div>
              </div>
              <span className="flex shrink-0 items-center gap-3">
                <span className="rounded-full bg-gray-200 px-2 py-0.5 text-[11px] font-bold text-gray-600">
                  {historyEvents.length} events
                </span>
                <ChevronRight className={`h-4 w-4 text-gray-400 transition-transform ${historyOpen ? 'rotate-90' : ''}`} />
              </span>
            </button>
            {historyOpen && (
              <div className="border-t border-gray-100 p-3">
                {sortedHistoryEvents.length ? (
                  <>
                  <ol className="space-y-3">
                    {visibleHistoryEvents.map((event, index) => (
                      <li key={event.id} className="grid grid-cols-[88px_1fr] gap-3">
                        <div className="pt-0.5 text-right">
                          <p className="text-xs font-bold text-gray-700">{formatHistoryDate(event.at)}</p>
                          <p className="font-['JetBrains_Mono',monospace] text-[11px] text-gray-400">{formatHistoryTime(event.at)}</p>
                        </div>
                        <div className="relative min-w-0 pb-1 pl-4">
                          {index < visibleHistoryEvents.length - 1 && (
                            <span className="absolute left-[5px] top-4 h-[calc(100%+0.75rem)] w-px bg-gray-200" />
                          )}
                          <span className="absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full bg-orange-500 ring-4 ring-orange-50" />
                          <p className="text-sm font-semibold text-gray-900">{event.label}</p>
                          {(event.actor || event.detail) && (
                            <p className="mt-0.5 text-xs text-gray-500">
                              {event.actor && <span className="font-semibold text-gray-700">{event.actor}</span>}
                              {event.actor && event.detail ? ' · ' : ''}
                              {event.detail}
                            </p>
                          )}
                        </div>
                      </li>
                    ))}
                  </ol>
                  {(hiddenHistoryCount > 0 || historyVisibleCount > 5) && (
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-3">
                      <p className="text-xs font-medium text-gray-500">
                        Showing {visibleHistoryEvents.length} of {sortedHistoryEvents.length} events
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {historyVisibleCount > 5 && (
                          <button
                            type="button"
                            onClick={() => setHistoryVisibleCount(5)}
                            className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-bold text-gray-600 hover:bg-gray-50"
                          >
                            Show less
                          </button>
                        )}
                        {hiddenHistoryCount > 0 && (
                          <button
                            type="button"
                            onClick={() => setHistoryVisibleCount((count) => Math.min(count + 5, sortedHistoryEvents.length))}
                            className="rounded-lg bg-orange-50 px-3 py-1.5 text-xs font-bold text-orange-700 hover:bg-orange-100"
                          >
                            Show {Math.min(5, hiddenHistoryCount)} older events
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                  </>
                ) : (
                  <p className="px-2 py-3 text-sm text-gray-500">No repair order history has been recorded yet.</p>
                )}
              </div>
            )}
          </div>
        )}

        {paletteOpen && addType !== 'history' && (
          <div className="mt-3 rounded-[14px] border border-gray-200 bg-white p-2 shadow-[0_10px_30px_rgba(20,25,35,.10)]">
            <div className="mb-2 flex items-center justify-between border-b border-gray-100 px-2 pb-2">
              <span className="text-xs font-bold uppercase tracking-[0.16em] text-gray-400">
                {addType === 'operation' ? 'Repair operations & services' : addType === 'saved_labor' ? 'Labor book time' : 'Parts'}
              </span>
              <span className="font-['JetBrains_Mono',monospace] text-[11px] text-gray-400">↵ to add</span>
            </div>
            {addType === 'operation' ? (
              <>
                {searchOps.isPending && (
                  <p className="inline-flex items-center gap-2 px-2 py-3 text-xs font-semibold text-gray-500">
                    <Spinner size="xs" />
                    Searching operations…
                  </p>
                )}
                {!searchOps.isPending && !candidates.length && (
                  <p className="px-2 py-3 text-sm text-gray-500">
                    Start by typing an operation name. Saved operations reuse learned labor hours when available.
                  </p>
                )}
                {!searchOps.isPending && candidates.map((c, index) => {
                  const isAddNew = isNoMatchCandidate && candidates.length === 1
                  const isAddingThisOperation = isApplyingOperationCandidate(c)
                  return (
                    <div
                      key={c.operation_id}
                      className={`flex items-center justify-between gap-3 rounded-xl px-3 py-2.5 ${
                        index === 0 ? 'bg-orange-50 shadow-[inset_3px_0_0_#ef8a12]' : 'hover:bg-gray-50'
                      }`}
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-gray-900">
                          {isAddNew ? `Add "${c.name}" as new operation` : c.name}
                          {isAddNew && (
                            <>
                              {' · '}
                              <button
                                type="button"
                                onClick={forkToLaborBookTime}
                                className="font-semibold text-orange-700 hover:text-orange-800 hover:underline"
                              >
                                or save it as labor book time →
                              </button>
                            </>
                          )}
                          {c.provider === 'service_catalog' && (
                            <span className="ml-1.5 rounded-full bg-blue-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-blue-700">
                              bundles parts
                            </span>
                          )}
                        </p>
                        <p className="truncate font-['JetBrains_Mono',monospace] text-[11px] text-gray-500">
                          {isAddNew
                            ? 'enter book hours to save this time'
                            : `${formatHoursMinutes(c.estimated_hours)} book time`} · {c.description || c.operation_id}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {isAddNew ? (
                          <DurationStepper
                            ariaLabel="Book time"
                            hours={Number(bookTimeHours) || 0}
                            onChange={(h) => setBookTimeHours(String(h))}
                          />
                        ) : (
                          <span className="hidden font-['JetBrains_Mono',monospace] text-xs font-semibold text-gray-600 sm:inline">
                            est. {formatHoursMinutes(c.estimated_hours)}
                          </span>
                        )}
                        <button
                          type="button"
                          onClick={() => applyRepairOp.mutate({
                            candidate: c,
                            estimatedHours: isAddNew ? bookTimeHours : undefined,
                          })}
                          disabled={!canMutate || applyRepairOp.isPending || (isAddNew && !bookTimeHours)}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-gray-900 text-white disabled:bg-gray-300"
                          aria-label={isAddingThisOperation ? `Adding ${c.name}` : isAddNew ? 'Add operation' : 'Apply operation'}
                        >
                          {isAddingThisOperation ? <Spinner size="xs" label={`Adding ${c.name}`} /> : <Plus className="h-4 w-4" />}
                        </button>
                      </div>
                    </div>
                  )
                })}
              </>
            ) : addType === 'saved_labor' ? (
              <>
                {laborBookEntriesFetching && (
                  <p className="inline-flex items-center gap-2 px-2 py-3 text-xs font-semibold text-gray-500">
                    <Spinner size="xs" />
                    Searching labor book time…
                  </p>
                )}
                {!laborBookEntriesFetching && laborBookEntries.length > 0 && laborBookEntries.slice(0, 8).map((entry, index) => {
                  const scope = laborBookTimeScope(entry)
                  const isAddingThisLaborBookEntry = isApplyingLaborBookEntry(entry)
                  return (
                    <div
                      key={entry.id}
                      className={`flex items-center justify-between gap-3 rounded-xl px-3 py-2.5 ${
                        index === 0 ? 'bg-orange-50 shadow-[inset_3px_0_0_#ef8a12]' : 'hover:bg-gray-50'
                      }`}
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-gray-900">{entry.operation_name}</p>
                        <p className="truncate font-['JetBrains_Mono',monospace] text-[11px] text-gray-500">
                          {formatHoursMinutes(entry.normalized_hours)} · {scope.primary} · {scope.secondary}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => applyLaborBookEntry.mutate(entry)}
                        disabled={!canMutate || applyLaborBookEntry.isPending}
                        className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-900 text-white disabled:bg-gray-300"
                        aria-label={isAddingThisLaborBookEntry ? `Adding ${entry.operation_name}` : `Add ${entry.operation_name}`}
                      >
                        {isAddingThisLaborBookEntry ? <Spinner size="xs" label={`Adding ${entry.operation_name}`} /> : <Plus className="h-4 w-4" />}
                      </button>
                    </div>
                  )
                })}
                {!laborBookEntriesFetching && laborBookEntries.length > 0 && laborBookSearchTerm.length >= 2 && !showLaborBookTimeForm && (
                  <button
                    type="button"
                    onClick={() => {
                      setShowLaborBookTimeForm(true)
                      setLaborBookTimeForm((current) => ({
                        ...current,
                        operation_name: laborBookSearchTerm,
                      }))
                    }}
                    className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-orange-300 bg-orange-50 px-3 py-2 text-xs font-bold text-orange-700 hover:bg-orange-100"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add another truck / engine variant
                  </button>
                )}
                {!laborBookEntriesFetching && laborBookSearchTerm.length >= 2 && (laborBookEntries.length === 0 || showLaborBookTimeForm) && (
                  <div className="rounded-xl bg-orange-50 p-3 shadow-[inset_3px_0_0_#ef8a12]">
                    <div className="mb-3 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-gray-900">
                          Add "{laborBookTimeForm.operation_name || laborBookSearchTerm}" as new labor book time
                          {' · '}
                          <button
                            type="button"
                            onClick={forkBackToOperation}
                            className="font-semibold text-orange-700 hover:text-orange-800 hover:underline"
                          >
                            or keep it as a regular service →
                          </button>
                        </p>
                        <p className="mt-0.5 text-xs text-gray-500">
                          Save the verified book hours and truck application, then add it to this repair order.
                        </p>
                      </div>
                      {showLaborBookTimeForm && laborBookEntries.length > 0 && (
                        <button
                          type="button"
                          onClick={() => setShowLaborBookTimeForm(false)}
                          className="rounded-lg p-1 text-gray-400 hover:bg-white hover:text-gray-700"
                          aria-label="Close new labor book time form"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                    <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                      <input
                        value={laborBookTimeForm.operation_name}
                        onChange={(e) => setLaborBookTimeForm((current) => ({ ...current, operation_name: e.target.value }))}
                        placeholder="Labor name"
                        className="h-9 rounded-lg border border-orange-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-orange-200"
                      />
                      {/* One control: reads out as "1h 45m", steps by 15 min,
                          stores decimal hours under the hood. */}
                      <DurationStepper
                        ariaLabel="Book time"
                        hours={Number(laborBookTimeForm.normalized_hours) || 0}
                        onChange={(h) => setLaborBookTimeForm((current) => ({ ...current, normalized_hours: String(h) }))}
                      />
                    </div>
                    <textarea
                      value={laborBookTimeForm.operation_description}
                      onChange={(e) => setLaborBookTimeForm((current) => ({ ...current, operation_description: e.target.value }))}
                      placeholder="Source notes, e.g. motor information system or historical shop data"
                      rows={2}
                      className="mt-2 w-full rounded-lg border border-orange-200 bg-white px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-orange-200"
                    />
                    <div className="mt-2 grid gap-2 sm:grid-cols-3">
                      <input
                        value={laborBookTimeForm.vehicle_year}
                        onChange={(e) => setLaborBookTimeForm((current) => ({ ...current, vehicle_year: e.target.value }))}
                        placeholder="Year"
                        className="h-9 rounded-lg border border-orange-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-orange-200"
                      />
                      <input
                        value={laborBookTimeForm.vehicle_make}
                        onChange={(e) => setLaborBookTimeForm((current) => ({ ...current, vehicle_make: e.target.value }))}
                        placeholder="Make"
                        className="h-9 rounded-lg border border-orange-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-orange-200"
                      />
                      <input
                        value={laborBookTimeForm.vehicle_model}
                        onChange={(e) => setLaborBookTimeForm((current) => ({ ...current, vehicle_model: e.target.value }))}
                        placeholder="Model"
                        className="h-9 rounded-lg border border-orange-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-orange-200"
                      />
                    </div>
                    <div className="mt-2 grid gap-2 sm:grid-cols-3">
                      <input
                        value={laborBookTimeForm.engine}
                        onChange={(e) => setLaborBookTimeForm((current) => ({ ...current, engine: e.target.value }))}
                        placeholder="Engine"
                        className="h-9 rounded-lg border border-orange-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-orange-200"
                      />
                      <input
                        value={laborBookTimeForm.fuel_type}
                        onChange={(e) => setLaborBookTimeForm((current) => ({ ...current, fuel_type: e.target.value }))}
                        placeholder="Fuel"
                        className="h-9 rounded-lg border border-orange-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-orange-200"
                      />
                      <input
                        value={laborBookTimeForm.engine_displacement_l}
                        onChange={(e) => setLaborBookTimeForm((current) => ({ ...current, engine_displacement_l: e.target.value }))}
                        placeholder="Displacement L"
                        className="h-9 rounded-lg border border-orange-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-orange-200"
                      />
                    </div>
                    <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
                      <input
                        value={laborBookTimeForm.vin_sample}
                        onChange={(e) => {
                          setLaborBookTimeForm((current) => ({ ...current, vin_sample: e.target.value.toUpperCase() }))
                          setVinDecodeStatus(null)
                        }}
                        placeholder="Optional VIN helper"
                        className="h-9 min-w-0 flex-1 rounded-lg border border-orange-200 bg-white px-3 text-sm uppercase outline-none focus:ring-2 focus:ring-orange-200"
                      />
                      {(decodeLaborBookVin.isPending || vinDecodeStatus) && (
                        <span
                          className={`inline-flex items-center gap-1 whitespace-nowrap text-xs font-medium ${
                            decodeLaborBookVin.isPending ? 'text-gray-500' : vinDecodeStatus?.ok ? 'text-green-700' : 'text-red-600'
                          }`}
                        >
                          {decodeLaborBookVin.isPending ? (
                            <>
                              <Spinner size="xs" /> Decoding…
                            </>
                          ) : vinDecodeStatus?.ok ? (
                            <>
                              <CheckCircle className="h-3.5 w-3.5" /> {vinDecodeStatus.message}
                            </>
                          ) : (
                            <>
                              <X className="h-3.5 w-3.5" /> {vinDecodeStatus?.message}
                            </>
                          )}
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => decodeLaborBookVin.mutate()}
                        disabled={decodeLaborBookVin.isPending}
                        className="h-9 rounded-lg border border-orange-200 bg-white px-3 text-xs font-bold text-gray-700 hover:bg-orange-100 disabled:opacity-60"
                      >
                        {decodeLaborBookVin.isPending ? 'Decoding…' : 'Decode VIN'}
                      </button>
                      <button
                        type="button"
                        onClick={() => createAndApplyLaborBookTime.mutate()}
                        disabled={!canMutate || createAndApplyLaborBookTime.isPending}
                        className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-gray-900 px-3 text-xs font-bold text-white disabled:bg-gray-300"
                      >
                        {createAndApplyLaborBookTime.isPending && <Spinner size="xs" label="Saving labor book time" />}
                        {createAndApplyLaborBookTime.isPending ? 'Saving…' : 'Save & add'}
                      </button>
                    </div>
                  </div>
                )}
                {!laborBookEntriesFetching && laborBookSearchTerm.length < 2 && laborBookEntries.length === 0 && (
                  <p className="px-2 py-3 text-sm text-gray-500">
                    Start typing a labor book time, or choose from existing saved book times.
                  </p>
                )}
              </>
            ) : addType === 'part' ? (
              <>
                {(() => {
                  const term = searchTerm.trim().toLowerCase()
                  const pickerLoading = inventoryFetching || partSuggestionsFetching
                  const pickerHasNoResultsYet = term.length >= 2 ? inventory.length === 0 : !partSuggestions

                  if (pickerLoading && pickerHasNoResultsYet) {
                    return <PickerLoadingRows message={term.length >= 2 ? 'Searching inventory…' : 'Loading suggested parts…'} />
                  }

                  const renderItemRow = (item: { id: string; name: string; sku: string; stock_quantity: number; unit_type: string; selling_price: string }, index: number) => {
                    const isFluid = item.unit_type && item.unit_type !== 'each'
                    const step = isFluid ? 0.25 : 1
                    const unitAbbr = UNIT_ABBR[item.unit_type] || ''
                    const rowQuantity = Math.max(step, partQuantitiesByItemId[item.id] ?? 1)
                    const isAddingThisPart = isAddingPartFor(item.id, null)
                    const shortage = stockShortages[partAddKey(item.id, null)]
                    const addRequest: PartAddRequest = { inventoryId: item.id, quantity: rowQuantity }
                    return (
                      <div
                        key={item.id}
                        className={`rounded-xl px-3 py-2.5 ${
                          index === 0 ? 'bg-orange-50 shadow-[inset_3px_0_0_#ef8a12]' : 'hover:bg-gray-50'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-gray-900">{item.name}</p>
                            <p className="truncate font-['JetBrains_Mono',monospace] text-[11px] text-gray-500">
                              {item.sku} · {item.stock_quantity} in stock{unitAbbr ? ` (${unitAbbr})` : ''} · list {money(item.selling_price)}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            <QuantityStepper
                              value={rowQuantity}
                              min={step}
                              step={step}
                              unitLabel={unitAbbr}
                              disabled={!canMutate || addPart.isPending}
                              ariaLabel={`Quantity for ${item.name}`}
                              onChange={(next) => {
                                setPartQuantitiesByItemId((current) => ({
                                  ...current,
                                  [item.id]: next,
                                }))
                                setStockShortages((current) => {
                                  const updated = { ...current }
                                  delete updated[partAddKey(item.id, null)]
                                  return updated
                                })
                              }}
                            />
                            <button
                              type="button"
                              onClick={() => addPart.mutate(addRequest)}
                              disabled={!canMutate || addPart.isPending}
                              className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-gray-900 text-white disabled:bg-gray-300"
                              aria-label={isAddingThisPart ? `Adding ${item.name}` : `Add ${item.name}`}
                            >
                              {isAddingThisPart ? <Spinner size="xs" label={`Adding ${item.name}`} /> : <Plus className="h-4 w-4" />}
                            </button>
                          </div>
                        </div>
                        {shortage && (
                          <StockShortageCallout
                            shortage={shortage}
                            unitLabel={unitAbbr}
                            overridePending={isAddingThisPart}
                            addPending={addPart.isPending}
                            action="add"
                            onOverride={() => addPart.mutate({ ...addRequest, allowStockShortage: true })}
                          />
                        )}
                      </div>
                    )
                  }

                  if (!term) {
                    const forThisOrder = partSuggestions?.for_this_order || []
                    const mostUsed = (partSuggestions?.most_used || [])
                      .filter((s) => !forThisOrder.some((f) => f.inventory_id === s.inventory_id))

                    if (!forThisOrder.length && !mostUsed.length) {
                      return (
                        <p className="px-2 py-3 text-sm text-gray-500">
                          Start typing at least two characters to search inventory.
                        </p>
                      )
                    }

                    return (
                      <>
                        {!!forThisOrder.length && (
                          <div className="mb-2">
                            <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-gray-400">
                              Suggested for this order
                            </p>
                            {forThisOrder.map((s, index) => renderItemRow(
                              { id: s.inventory_id, name: s.name, sku: s.sku, stock_quantity: s.stock_quantity, unit_type: s.unit_type, selling_price: s.selling_price },
                              index,
                            ))}
                          </div>
                        )}
                        {!!mostUsed.length && (
                          <div>
                            <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-gray-400">
                              Most used parts
                            </p>
                            {mostUsed.map((s, index) => renderItemRow(
                              { id: s.inventory_id, name: s.name, sku: s.sku, stock_quantity: s.stock_quantity, unit_type: s.unit_type, selling_price: s.selling_price },
                              forThisOrder.length ? -1 : index,
                            ))}
                          </div>
                        )}
                      </>
                    )
                  }

                  if (term.length < 2) {
                    return <p className="px-2 py-3 text-sm text-gray-500">Type at least two characters to search inventory.</p>
                  }

                  if (inventoryErrored) {
                    return (
                      <p className="px-2 py-3 text-sm text-red-600">
                        Couldn't search inventory.{' '}
                        <button
                          type="button"
                          onClick={() => queryClient.invalidateQueries({ queryKey: ['inventory-typeahead', inventorySearchTerm] })}
                          className="font-semibold underline hover:no-underline"
                        >
                          Retry
                        </button>
                      </p>
                    )
                  }
                  const matches = inventory.filter((item) => (
                    item.name.toLowerCase().includes(term) || item.sku.toLowerCase().includes(term)
                  ))
                  if (!matches.length) {
                    return <p className="px-2 py-3 text-sm text-gray-500">No parts match this search.</p>
                  }
                  return matches.map((item, index) => renderItemRow(item, index))
                })()}
              </>
            ) : null}
          </div>
        )}
      </div>

      {(() => {
        const allParts = partsUsed || []
        const lines = effectiveLaborLines
        // A part attaches to a line either directly (source_line_id, used for any
        // operation incl. free-form ones) or, for legacy service-bundled parts, via
        // the line's source_service_id. Build lookups for both so groupedPartsForLine
        // can resolve either way.
        const partsByService = new Map<string, typeof allParts>()
        const partsByLine = new Map<string, typeof allParts>()
        const lineIdsWithLinkedParts = new Set<string>()
        const orphanParts: typeof allParts = []
        for (const pu of allParts) {
          if (pu.source_line_id) {
            const bucket = partsByLine.get(pu.source_line_id) || []
            bucket.push(pu)
            partsByLine.set(pu.source_line_id, bucket)
            lineIdsWithLinkedParts.add(pu.source_line_id)
          } else if (pu.source_service_id) {
            const bucket = partsByService.get(pu.source_service_id) || []
            bucket.push(pu)
            partsByService.set(pu.source_service_id, bucket)
          } else {
            orphanParts.push(pu)
          }
        }
        const groupedPartsForLine = (line: typeof lines[number]) => {
          const byLine = partsByLine.get(line.id) || []
          const byService = line.source_service_id ? partsByService.get(line.source_service_id) || [] : []
          return byLine.length ? [...byLine, ...byService] : byService
        }

        const renderPartsRows = (parts: typeof allParts) => (
          <div className="overflow-x-auto rounded-md border border-gray-200 bg-gray-50/50">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] text-gray-500 border-b border-gray-200">
                  <th className="py-1.5 px-2.5 font-medium">Part</th>
                  <th className="py-1.5 px-2.5 font-medium text-right">Qty</th>
                  <th className="py-1.5 px-2.5 font-medium text-right">Unit</th>
                  <th className="py-1.5 px-2.5 font-medium text-right">Savings</th>
                  <th className="py-1.5 px-2.5 font-medium text-right">Line total</th>
                </tr>
              </thead>
              <tbody>
                {parts.map((pu) => {
                  const shortageKey = partQuantityKey(pu.id)
                  const shortage = stockShortages[shortageKey]
                  const quantityOverride = partQuantityOverrides[shortageKey]
                  const retryQuantity = quantityOverride ?? (shortage ? Number(shortage.requestedQuantity) : parseFloat(pu.quantity) || 0)
                  const quantityUpdatePending = partQuantitySavingKey === shortageKey
                  return (
                    <tr key={pu.id} className="border-b border-gray-100 last:border-0">
                      <td className="py-1.5 px-2.5 text-gray-800">
                        <div className="font-medium">{pu.inventory_name}</div>
                        <div className="flex flex-wrap items-center gap-1.5 text-xs text-gray-500">
                          <span>{pu.inventory_sku}</span>
                          {pu.stock_shortage_override && (
                            <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-800">
                              Stock override
                            </span>
                          )}
                        </div>
                        {shortage && (
                          <StockShortageCallout
                            shortage={shortage}
                            unitLabel={UNIT_ABBR[pu.unit_type] || pu.unit_type}
                            overridePending={quantityUpdatePending}
                            addPending={editingPartsSaving && !quantityUpdatePending}
                            action="update"
                            onOverride={() => { void updatePartQuantity(pu, retryQuantity, true) }}
                          />
                        )}
                      </td>
                      <td className="py-1.5 px-2.5 text-right text-gray-800">
                        {canMutate ? (
                          <span className="inline-flex justify-end">
                            <PartQtyStepper
                              part={pu}
                              quantityOverride={quantityOverride}
                              disabled={editingPartsSaving || priceSavingId === pu.id}
                              onChangeQty={(next) => updatePartQuantity(pu, next)}
                              onDelete={async () => {
                                setEditingPartsSaving(true)
                                try {
                                  await api.delete(`/repair-orders/${orderId}/parts/${pu.id}`)
                                  setStockShortages((current) => {
                                    const updated = { ...current }
                                    delete updated[shortageKey]
                                    return updated
                                  })
                                  setPartQuantityOverrides((current) => {
                                    const updated = { ...current }
                                    delete updated[shortageKey]
                                    return updated
                                  })
                                  await invalidate()
                                  toast.success(`${pu.inventory_name} removed`)
                                } catch (err: unknown) {
                                  toast.error(errorDetail(err, 'Failed to remove part'))
                                } finally {
                                  setEditingPartsSaving(false)
                                }
                              }}
                            />
                          </span>
                        ) : (
                          (() => {
                            const isFluid = pu.unit_type && pu.unit_type !== 'each'
                            const unitAbbr = UNIT_ABBR[pu.unit_type] || ''
                            const qtyNum = parseFloat(pu.quantity) || 0
                            return `${isFluid ? qtyNum.toFixed(2) : qtyNum} ${unitAbbr}`
                          })()
                        )}
                      </td>
                      <td className="py-1.5 px-2.5 text-right text-gray-600">
                        {canMutate ? (
                          (() => {
                            const saving = priceSavingId === pu.id
                            return (
                              <PartPricePopover
                                part={pu}
                                disabled={saving}
                                saving={saving}
                                onApply={async (next) => {
                                  setPriceSavingId(pu.id)
                                  try {
                                    await api.patch(`/repair-orders/${orderId}/parts/${pu.id}`, { unit_price: next })
                                    await invalidate()
                                    toast.success(`${pu.inventory_name} price set to $${next.toFixed(2)}`)
                                  } catch (err: unknown) {
                                    toast.error(errorDetail(err, 'Failed to update price'))
                                  } finally {
                                    setPriceSavingId(null)
                                  }
                                }}
                              />
                            )
                          })()
                        ) : (
                          <>${parseFloat(pu.unit_price).toFixed(2)}</>
                        )}
                      </td>
                      <td className="py-1.5 px-2.5 text-right">
                        {parseFloat(pu.savings || '0') > 0 ? (
                          <span className="text-emerald-600 font-medium">
                            −${parseFloat(pu.savings).toFixed(2)}
                          </span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td className="py-1.5 px-2.5 text-right text-gray-900 font-medium">${parseFloat(pu.total_price).toFixed(2)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )

        const renderOperationPartPicker = (line: typeof lines[number], groupedParts: typeof allParts) => {
          if (operationPartPickerLineId !== line.id) return null
          const term = (operationPartSearchByLineId[line.id] || '').trim().toLowerCase()
          const hasSearchTerm = term.length >= 2
          const groupedInventoryIds = new Set(groupedParts.map((part) => part.inventory_id))
          const matches = inventory
            .filter((item) => !groupedInventoryIds.has(item.id))
            .filter((item) => item.name.toLowerCase().includes(term) || item.sku.toLowerCase().includes(term))
            .slice(0, 6)
          const inventoryLoadingWithoutResults = inventoryFetching && inventory.length === 0

          return (
            <div className="rounded-xl border border-dashed border-orange-200 bg-orange-50/50 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-orange-500">Add part to operation</span>
                <button
                  type="button"
                  onClick={() => setOperationPartPickerLineId(null)}
                  className="rounded-md p-1 text-gray-400 hover:bg-white hover:text-gray-700"
                  aria-label="Close part picker"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="relative mb-2">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <input
                  value={operationPartSearchByLineId[line.id] || ''}
                  onChange={(e) => setOperationPartSearchByLineId((current) => ({ ...current, [line.id]: e.target.value }))}
                  placeholder="Search inventory for this operation..."
                  className="h-10 w-full rounded-lg border border-orange-200 bg-white pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-orange-200"
                />
              </div>
              {!hasSearchTerm ? (
                <p className="px-1 py-2 text-sm text-gray-500">Type at least two characters to search inventory.</p>
              ) : inventoryLoadingWithoutResults ? (
                <PickerLoadingRows message="Searching inventory…" />
              ) : inventoryErrored ? (
                <p className="px-1 py-2 text-sm text-red-600">
                  Couldn't search inventory.{' '}
                  <button
                    type="button"
                    onClick={() => queryClient.invalidateQueries({ queryKey: ['inventory-typeahead', inventorySearchTerm] })}
                    className="font-semibold underline hover:no-underline"
                  >
                    Retry
                  </button>
                </p>
              ) : !matches.length ? (
                <p className="px-1 py-2 text-sm text-gray-500">No parts match this operation search.</p>
              ) : (
                <div className="space-y-1">
                  {matches.map((item) => {
                    const isFluid = item.unit_type && item.unit_type !== 'each'
                    const step = isFluid ? 0.25 : 1
                    const unitAbbr = UNIT_ABBR[item.unit_type] || ''
                    const quantityKey = `${line.id}:${item.id}`
                    const rowQuantity = Math.max(step, partQuantitiesByItemId[quantityKey] ?? 1)
                    const isAddingThisPart = isAddingPartFor(item.id, line.id)
                    const shortage = stockShortages[partAddKey(item.id, line.id)]
                    const addRequest: PartAddRequest = {
                      inventoryId: item.id,
                      quantity: rowQuantity,
                      sourceServiceId: line.source_service_id,
                      sourceLineId: line.id,
                      quantityKey,
                    }
                    return (
                      <div key={item.id} className="rounded-lg bg-white px-2.5 py-2">
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-gray-900">{item.name}</p>
                            <p className="truncate font-['JetBrains_Mono',monospace] text-[11px] text-gray-500">
                              {item.sku} · {item.stock_quantity} in stock ({unitAbbr}) · list {money(item.selling_price)}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            <QuantityStepper
                              value={rowQuantity}
                              min={step}
                              step={step}
                              unitLabel={unitAbbr}
                              disabled={!canMutate || addPart.isPending}
                              ariaLabel={`Quantity for ${item.name}`}
                              onChange={(next) => {
                                setPartQuantitiesByItemId((current) => ({
                                  ...current,
                                  [quantityKey]: next,
                                }))
                                setStockShortages((current) => {
                                  const updated = { ...current }
                                  delete updated[partAddKey(item.id, line.id)]
                                  return updated
                                })
                              }}
                            />
                            <button
                              type="button"
                              onClick={() => addPart.mutate(addRequest)}
                              disabled={!canMutate || addPart.isPending}
                              className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-gray-900 text-white disabled:bg-gray-300"
                              aria-label={isAddingThisPart ? `Adding ${item.name} to ${line.description}` : `Add ${item.name} to ${line.description}`}
                            >
                              {isAddingThisPart ? <Spinner size="xs" label={`Adding ${item.name} to ${line.description}`} /> : <Plus className="h-4 w-4" />}
                            </button>
                          </div>
                        </div>
                        {shortage && (
                          <StockShortageCallout
                            shortage={shortage}
                            unitLabel={unitAbbr}
                            overridePending={isAddingThisPart}
                            addPending={addPart.isPending}
                            action="add"
                            onOverride={() => addPart.mutate({ ...addRequest, allowStockShortage: true })}
                          />
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        }

        const renderLaborEditor = (line: typeof lines[number]) => (
          <LaborLineEditor
            line={line}
            canMutate={canMutate}
            onLocalChange={(patch) => setLaborOverride(line.id, patch)}
            onUpdate={(body) => updateLine.mutate({ lineId: line.id, body })}
          />
        )

        if (isDeleted) {
          return (
            <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 px-4 py-6 text-center">
              <p className="font-semibold text-gray-900">This order is deleted.</p>
              <p className="mt-1 text-sm text-gray-500">Restore it from the Danger zone below to view and edit its work &amp; labor.</p>
            </div>
          )
        }
        if (isLoading) {
          // Skeleton that mirrors the Work & Labor list, so a slow fetch (prod)
          // reads as "loading" in the open drawer rather than an empty panel.
          return (
            <div className="animate-pulse">
              <div className="mb-1 flex items-center justify-between">
                <span className="inline-flex items-center gap-2">
                  <div className="h-3 w-24 rounded bg-gray-200" />
                  <div className="h-4 w-12 rounded-full bg-gray-100" />
                </span>
              </div>
              <div className="divide-y divide-gray-100 border-y border-gray-100">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="flex items-center gap-3 px-2 py-3">
                    <div className="h-9 w-9 shrink-0 rounded-lg bg-gray-200" />
                    <div className="min-w-0 flex-1 space-y-2">
                      <div className="h-3.5 w-1/2 rounded bg-gray-200" />
                      <div className="h-2.5 w-1/3 rounded bg-gray-100" />
                    </div>
                    <div className="space-y-2 text-right">
                      <div className="ml-auto h-5 w-16 rounded bg-gray-200" />
                      <div className="ml-auto h-2.5 w-20 rounded bg-gray-100" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        }
        if (summaryLoadFailed) {
          return (
            <div className="rounded-xl border border-dashed border-red-200 bg-red-50/40 px-4 py-6 text-center">
              <p className="font-semibold text-gray-900">Couldn't load this order's work &amp; labor.</p>
              <p className="mt-1 text-sm text-gray-500">This isn't necessarily an empty order — the request failed.</p>
              <button
                type="button"
                onClick={() => refetchSummary()}
                className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-700"
              >
                Retry
              </button>
            </div>
          )
        }
        if (!lines.length && !orphanParts.length) {
          if (pendingWorkMessage || (partsFetching && !partsUsed)) {
            return <PendingWorkRows message={pendingWorkMessage || 'Loading parts for work & labor…'} />
          }
          return (
            <div className="rounded-xl border border-dashed border-orange-200 bg-orange-50/40 px-4 py-6 text-center">
              <p className="font-semibold text-gray-900">Start by adding an operation, diagnostic or part.</p>
              <p className="mt-1 text-sm text-gray-500">The add bar above feeds this single work and labor list.</p>
            </div>
          )
        }

        return (
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="inline-flex items-center gap-2">
                <p className="font-['Barlow_Condensed',sans-serif] text-sm font-extrabold uppercase tracking-[0.16em] text-gray-500">Work & Labor</p>
                <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-bold text-gray-500">{lines.length + (orphanParts.length ? 1 : 0)} lines</span>
              </span>
              <SectionInfoTooltip text="Each card is one billable item. Service packages bundle labor with their required parts — edit hours, rate, or part quantity inline. Stock adjusts automatically." tooltipClassName="w-72" />
            </div>
            <div className="divide-y divide-gray-100 border-y border-gray-100">
              {lines.map((line) => {
                const groupedParts = groupedPartsForLine(line)
                const isOpen = openLineIds.has(line.id)
                const isAddingPartHere = isAddingPartToLine(line.id)
                const warningsForLine = lineWarnings[line.id] || []
                const partTotal = groupedParts.reduce((sum, part) => sum + (parseFloat(part.total_price || '0') || 0), 0)
                const partSavings = groupedParts.reduce((sum, part) => sum + (parseFloat(part.savings || '0') || 0), 0)
                const lineTotal = (parseFloat(line.total_cost || '0') || 0) + partTotal
                const Icon = line.source_service_id ? Wrench : line.line_type === 'flat_service' ? Gauge : Tag
                return (
                  <div key={line.id} className="py-1">
                    <button
                      type="button"
                      onClick={() => toggleLine(line.id)}
                      className="grid w-full grid-cols-[auto_auto_1fr_auto] items-center gap-3 rounded-xl px-2 py-3 text-left hover:bg-gray-50"
                    >
                      <ChevronRight className={`h-4 w-4 text-gray-400 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                      <span className={`inline-flex h-9 w-9 items-center justify-center rounded-lg ${
                        line.source_service_id ? 'bg-orange-50 text-orange-700' : 'bg-blue-50 text-blue-700'
                      }`}>
                        <Icon className="h-4 w-4" />
                      </span>
                      <span className="min-w-0">
                        <span className="flex min-w-0 flex-wrap items-center gap-2">
                          <span className="truncate font-semibold text-gray-900">{line.description || lineTypeLabel(line)}</span>
                          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-gray-500">{lineTypeLabel(line)}</span>
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-gray-500">
                          {formatHoursMinutes(line.hours)} labor · {groupedParts.length} parts{partSavings > 0 ? ` · saves ${money(partSavings)}` : ''}
                        </span>
                      </span>
                      <span className="text-right">
                        <span className="block font-['Barlow_Condensed',sans-serif] text-2xl font-extrabold leading-none text-gray-900">{money(lineTotal)}</span>
                        <span className="block font-['JetBrains_Mono',monospace] text-[10px] text-gray-400">
                          {money(line.total_cost)} labor · {money(partTotal)} parts
                        </span>
                      </span>
                    </button>
                    {isOpen && (
                      <div className="ml-[60px] space-y-3 pb-4 pr-2">
                        {warningsForLine.length > 0 && (
                          <div role="alert" className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                            {warningsForLine.map((warning) => (
                              <p key={`${warning.code}-${warning.message}`} className="flex items-start gap-1.5">
                                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
                                <span>{warning.message}</span>
                              </p>
                            ))}
                          </div>
                        )}
                        <div className="rounded-xl bg-gray-50 px-3 py-2">
                          <div className="mb-2 flex items-center justify-between gap-2">
                            <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-gray-400">Labor</span>
                            {canMutate && (
                              <button
                                type="button"
                                onClick={() => removeLine.mutate(line.id)}
                                disabled={removeLine.isPending}
                                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50"
                              >
                                <Trash2 className="h-3.5 w-3.5" /> Remove
                              </button>
                            )}
                          </div>
                          {renderLaborEditor(line)}
                        </div>
                        {groupedParts.length > 0 && renderPartsRows(groupedParts)}
                        {isAddingPartHere && <PendingWorkRows message="Adding part to this operation…" />}
                        <button
                          type="button"
                          disabled={!canMutate || addPart.isPending}
                          onClick={() => setOperationPartPickerLineId((current) => current === line.id ? null : line.id)}
                          className="inline-flex w-full items-center justify-center gap-1 rounded-xl border border-dashed border-gray-300 px-3 py-2 text-sm font-semibold text-gray-500 hover:border-orange-300 hover:bg-orange-50 hover:text-orange-700 disabled:hover:border-gray-300 disabled:hover:bg-transparent disabled:hover:text-gray-400 disabled:opacity-60"
                        >
                          {isAddingPartHere ? <Spinner size="xs" label="Adding part to this operation" /> : <Plus className="h-4 w-4" />}
                          {isAddingPartHere ? 'Adding part…' : 'Add part to this operation'}
                        </button>
                        {renderOperationPartPicker(line, groupedParts)}
                      </div>
                    )}
                  </div>
                )
              })}
              {orphanParts.length > 0 && (
                <div className="py-3">
                  <div className="mb-2 flex items-center gap-2 px-2">
                    <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
                      <Box className="h-4 w-4" />
                    </span>
                    <div>
                      <p className="font-semibold text-gray-900">Standalone parts</p>
                      <p className="text-xs text-gray-500">{orphanParts.length} parts · {money(orphanParts.reduce((sum, p) => sum + (parseFloat(p.total_price || '0') || 0), 0))}</p>
                    </div>
                  </div>
                  <div className="ml-[60px]">{renderPartsRows(orphanParts)}</div>
                </div>
              )}
              {isAddingStandalonePart && lines.length > 0 && (
                <div className="py-3">
                  <div className="mb-2 flex items-center gap-2 px-2">
                    <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
                      <Box className="h-4 w-4" />
                    </span>
                    <div>
                      <p className="font-semibold text-gray-900">Standalone parts</p>
                      <p className="text-xs text-gray-500">Adding a part…</p>
                    </div>
                  </div>
                  <div className="ml-[60px]"><PendingWorkRows message="Adding standalone part…" /></div>
                </div>
              )}
            </div>
          </div>
        )
      })()}

      <div className="space-y-1 pb-2">
        <button
          type="button"
          onClick={() => setCustomerOpen((open) => !open)}
          className="flex w-full items-center justify-between rounded-xl border-t border-gray-100 px-2 py-3 text-left hover:bg-gray-50"
        >
          <span className="inline-flex min-w-0 items-center gap-2 text-sm font-semibold text-gray-800">
            <Truck className="h-4 w-4 text-gray-400" />
            Customer & Vehicle
          </span>
          <span className="truncate px-3 text-right text-xs text-gray-500">
            {customerName || 'Customer'} · {vehicleUnit || 'Unit'} · {vehicleLabel || 'Vehicle'}{vehicleVin ? ` · VIN ${vehicleVin.slice(-6)}` : ''}
          </span>
          <ChevronRight className={`h-4 w-4 shrink-0 text-gray-400 transition-transform ${customerOpen ? 'rotate-90' : ''}`} />
        </button>
        {customerOpen && (
          <div className="grid gap-3 rounded-xl bg-gray-50 px-4 py-3 text-sm sm:grid-cols-2">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-wide text-gray-400">Customer</p>
              <p className="font-semibold text-gray-900">{customerName || 'Customer'}</p>
              {customerEmail && <p className="text-xs text-gray-500">{customerEmail}</p>}
              {customerPhone && <p className="text-xs text-gray-500">{customerPhone}</p>}
            </div>
            <div>
              <p className="text-[11px] font-bold uppercase tracking-wide text-gray-400">Vehicle</p>
              <p className="font-semibold text-gray-900">{[vehicleUnit, vehicleLabel].filter(Boolean).join(' · ') || 'Vehicle'}</p>
              {vehicleVin && <p className="text-xs text-gray-500">VIN: {vehicleVin}</p>}
              {vehiclePlate && <p className="text-xs text-gray-500">Plate: {vehiclePlate}</p>}
            </div>
            <div className="grid grid-cols-2 gap-2 border-t border-gray-200 pt-3 sm:col-span-2 sm:grid-cols-4">
              <div><p className="text-[11px] uppercase text-gray-400">Mileage In</p><p className="font-medium text-gray-800">{mileageIn ?? '—'}</p></div>
              <div><p className="text-[11px] uppercase text-gray-400">Mileage Out</p><p className="font-medium text-gray-800">{mileageOut ?? '—'}</p></div>
              <div><p className="text-[11px] uppercase text-gray-400">PO Number</p><p className="font-medium text-gray-800">{poNumber || '—'}</p></div>
              <div><p className="text-[11px] uppercase text-gray-400">Type</p><p className="font-medium text-gray-800">{orderTypeLabel || 'Standard'}</p></div>
            </div>
          </div>
        )}
        {showRecommendedServicesPanel && (
          <button
            type="button"
            onClick={() => setRecommendedOpen((open) => {
              const next = !open
              onRecommendedServicesOpenChange?.(next)
              return next
            })}
            className="flex w-full items-center justify-between rounded-xl border-t border-gray-100 px-2 py-3 text-left hover:bg-gray-50"
          >
            <span className="inline-flex items-center gap-2 text-sm font-semibold text-gray-800">
              <Wrench className="h-4 w-4 text-gray-400" />
              Recommended Services
              {!!recommendedServices?.filter((svc) => !svc.is_resolved).length && (
                <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-700">
                  {recommendedServices.filter((svc) => !svc.is_resolved).length}
                </span>
              )}
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="px-3 text-xs font-semibold text-orange-700">add from inspection</span>
              <ChevronRight className={`h-4 w-4 shrink-0 text-gray-400 transition-transform ${recommendedOpen ? 'rotate-90' : ''}`} />
            </span>
          </button>
        )}
        {showRecommendedServicesPanel && recommendedOpen && (
          <div className="rounded-xl bg-gray-50 p-3">
            <button
              type="button"
              onClick={onToggleAddRecommendedService}
              className="mb-3 inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-bold text-orange-700 ring-1 ring-gray-200"
            >
              <Plus className="h-3.5 w-3.5" /> Add recommended service
            </button>
            {showAddRecommendedService && recommendedServiceForm && onRecommendedServiceFormChange && (
              <div className="mb-3 space-y-2 rounded-xl border border-gray-200 bg-white p-3">
                <textarea
                  value={recommendedServiceForm.description}
                  onChange={(e) => onRecommendedServiceFormChange({ ...recommendedServiceForm, description: e.target.value })}
                  placeholder="Service description..."
                  rows={2}
                  className="w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-orange-200"
                />
                <div className="grid grid-cols-2 gap-2">
                  <select
                    value={recommendedServiceForm.priority}
                    onChange={(e) => onRecommendedServiceFormChange({ ...recommendedServiceForm, priority: e.target.value as RecommendedServicePriority })}
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  >
                    <option value="urgent">Urgent</option>
                    <option value="soon">Soon</option>
                    <option value="monitor">Monitor</option>
                  </select>
                  <input
                    type="number"
                    value={recommendedServiceForm.estimated_cost}
                    onChange={(e) => onRecommendedServiceFormChange({ ...recommendedServiceForm, estimated_cost: e.target.value })}
                    placeholder="Est. cost"
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </div>
                <div className="flex gap-2">
                  <button type="button" onClick={onToggleAddRecommendedService} className="flex-1 rounded-lg bg-gray-100 py-2 text-sm font-semibold text-gray-600">Cancel</button>
                  <button
                    type="button"
                    disabled={!recommendedServiceForm.description.trim() || addRecommendedPending}
                    onClick={onAddRecommendedService}
                    className="flex-1 rounded-lg bg-orange-500 py-2 text-sm font-bold text-white disabled:bg-gray-300"
                  >
                    Add
                  </button>
                </div>
              </div>
            )}
            {recommendedServicesLoading ? (
              <div className="flex items-center gap-2 rounded-xl bg-white px-3 py-3 text-sm text-gray-500">
                <Spinner size="xs" /> Loading recommended services…
              </div>
            ) : recommendedServices?.length ? (
              <ul className="divide-y divide-gray-200 rounded-xl bg-white">
                {recommendedServices.map((svc) => (
                  <li key={svc.id} className={`flex items-start gap-3 p-3 ${svc.is_resolved ? 'opacity-50' : ''}`}>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${
                          svc.priority === 'urgent' ? 'bg-red-100 text-red-700' :
                          svc.priority === 'soon' ? 'bg-yellow-100 text-yellow-700' :
                          'bg-gray-100 text-gray-600'
                        }`}>
                          {svc.priority.charAt(0).toUpperCase() + svc.priority.slice(1)}
                        </span>
                        {svc.estimated_cost && <span className="text-xs text-gray-500">{money(svc.estimated_cost)}</span>}
                        {svc.is_resolved && <span className="text-xs font-medium text-emerald-600">Resolved</span>}
                      </div>
                      <p className="mt-1 text-sm text-gray-800">{svc.description}</p>
                    </div>
                    {!svc.is_resolved && (
                      <div className="flex shrink-0 gap-1">
                        <button
                          type="button"
                          onClick={() => onResolveRecommendedService?.(svc.id)}
                          disabled={resolveRecommendedPending}
                          className="rounded-lg px-2 py-1 text-xs font-bold text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
                        >
                          Resolve
                        </button>
                        <button
                          type="button"
                          onClick={() => onDeleteRecommendedService?.(svc.id)}
                          disabled={deleteRecommendedPending}
                          className="rounded-lg p-1.5 text-red-500 hover:bg-red-50 disabled:opacity-50"
                          aria-label="Delete recommended service"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rounded-xl bg-white px-3 py-2 text-xs text-gray-400">No recommended services recorded.</p>
            )}
          </div>
        )}

        {/* Repair photos sit in the body (near Customer & Vehicle), above the
            Order Total footer. Adding is only allowed while the order is open;
            on a finalized order with no photos there's nothing to show, so the
            whole section is hidden. */}
        {!isDeleted && !(isFinalized && repairPhotosData !== undefined && repairPhotos.length === 0) && (
          <div className="mt-4 rounded-2xl border border-gray-200 bg-white p-3 shadow-sm">
            <button
              type="button"
              onClick={() => setPhotosOpen((open) => !open)}
              className="flex w-full flex-wrap items-center justify-between gap-3 text-left"
              aria-expanded={photosOpen}
            >
              <span className="min-w-0">
                <span className="block text-xs font-bold uppercase tracking-[0.16em] text-gray-400">Repair photos</span>
                <span className="mt-0.5 block text-sm font-semibold text-gray-900">
                  {repairPhotosData === undefined
                    ? 'Open to view repair photos'
                    : repairPhotos.length
                      ? `${repairPhotos.length} photo${repairPhotos.length === 1 ? '' : 's'} attached`
                      : 'No photos attached'}
                </span>
              </span>
              <span className="flex min-w-0 flex-1 items-center justify-end gap-2">
                {isUploadingRepairPhotos && (
                  <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-dashed border-orange-300 bg-orange-50">
                    <Spinner size="xs" />
                  </span>
                )}
                {visiblePhotoThumbs.length > 0 && (
                  <span className="flex min-w-0 items-center justify-end gap-1">
                    {visiblePhotoThumbs.map((photo) => (
                      <span key={photo.id} className="block h-10 w-10 shrink-0 overflow-hidden rounded-lg border border-gray-200 bg-gray-100">
                        <img src={photo.image_url} alt={photo.caption || 'Repair photo'} className="h-full w-full object-cover" />
                      </span>
                    ))}
                    {hiddenPhotoThumbCount > 0 && (
                      <span className="inline-flex h-10 min-w-10 shrink-0 items-center justify-center rounded-lg bg-gray-100 px-2 text-xs font-bold text-gray-600">
                        +{hiddenPhotoThumbCount}
                      </span>
                    )}
                  </span>
                )}
                <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-100 text-gray-500">
                  <ChevronDown className={`h-4 w-4 transition-transform ${photosOpen ? 'rotate-180' : ''}`} />
                </span>
              </span>
            </button>
            {photosOpen && (
              <div className="mt-3 border-t border-gray-100 pt-3">
                {/* Upload only while the order is open — a finalized order's photos
                    are a fixed record; they should have been added before closing. */}
                {!isFinalized && (
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <input
                      type="text"
                      value={photoCaption}
                      onChange={(event) => setPhotoCaption(event.target.value)}
                      maxLength={500}
                      placeholder="Optional photo note"
                      className="h-10 min-w-0 flex-1 rounded-xl border border-gray-200 bg-white px-3 text-sm outline-none focus:border-orange-300 focus:ring-2 focus:ring-orange-100"
                    />
                    <label className="inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-xl border border-gray-200 bg-gray-50 px-3 text-sm font-bold text-gray-700 transition hover:border-orange-300 hover:bg-orange-50">
                      <Camera className="h-4 w-4 text-orange-600" />
                      Upload photo
                      <input
                        type="file"
                        accept="image/*"
                        multiple
                        className="hidden"
                        disabled={isUploadingRepairPhotos}
                        onChange={handleRepairPhotoSelect}
                      />
                    </label>
                  </div>
                )}
                {repairPhotosFetching ? (
                  <div className="mt-3 inline-flex items-center gap-2 text-sm text-gray-500">
                    <Spinner size="xs" /> Loading repair photos…
                  </div>
                ) : (repairPhotos.length > 0 || photoUploadItems.length > 0) ? (
                  <div className={`grid grid-cols-2 gap-2 sm:grid-cols-3 ${isFinalized ? '' : 'mt-3'}`}>
                    {photoUploadItems.map((item) => (
                      <div key={item.id} className="relative aspect-[4/3] overflow-hidden rounded-xl border border-dashed border-orange-300 bg-orange-50">
                        <div className={`absolute inset-0 bg-gradient-to-br from-orange-100 via-white to-orange-50 ${item.status === 'error' ? '' : 'animate-pulse'}`} />
                        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-3 text-center">
                          {item.status === 'error' ? <AlertTriangle className="h-4 w-4 text-red-500" /> : <Spinner size="sm" />}
                          <p className="line-clamp-2 text-xs font-semibold text-orange-800">
                            {item.name}
                          </p>
                          <p className={`text-lg font-black ${item.status === 'error' ? 'text-red-500' : 'text-orange-600'}`}>
                            {item.progress}%
                          </p>
                          <p className="text-[10px] font-semibold text-gray-500">
                            {item.status === 'error' ? `Failed: ${item.error || 'Upload failed'}` : `${item.status} · ${formatFileSize(item.size)}`}
                          </p>
                          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white">
                            <div
                              className={`h-full rounded-full ${item.status === 'error' ? 'bg-red-500' : 'bg-orange-500'}`}
                              style={{ width: `${Math.max(6, item.progress)}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                    {repairPhotos.map((photo) => (
                      <div key={photo.id} className="group relative aspect-[4/3] overflow-hidden rounded-xl border border-gray-200 bg-gray-100">
                        <img src={photo.image_url} alt={photo.caption || 'Repair photo'} className="h-full w-full object-cover" />
                        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 to-transparent p-2 text-white opacity-100">
                          <p className="line-clamp-2 text-[11px] font-semibold">{photo.caption || 'Repair photo'}</p>
                          <p className="mt-0.5 text-[10px] text-white/75">{photo.uploader_name}</p>
                        </div>
                        {!isFinalized && (
                          <button
                            type="button"
                            onClick={() => deletePhotoMutation.mutate(photo.id)}
                            disabled={deletePhotoMutation.isPending}
                            className="absolute right-1.5 top-1.5 inline-flex h-7 w-7 items-center justify-center rounded-full bg-black/65 text-white opacity-0 transition hover:bg-red-600 disabled:opacity-50 group-hover:opacity-100"
                            aria-label="Delete repair photo"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3 rounded-xl border border-dashed border-gray-200 bg-gray-50 px-4 py-5 text-center">
                    <Camera className="mx-auto h-5 w-5 text-gray-400" />
                    <p className="mt-2 text-sm font-semibold text-gray-800">No repair photos yet.</p>
                    <p className="mt-0.5 text-xs text-gray-500">Add evidence photos for this repair order.</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
      </div>

      <div className="z-10 border-t border-gray-200 bg-white/95 px-5 py-4 shadow-[0_-10px_30px_rgba(20,25,35,.08)] backdrop-blur">
        <div ref={footerDetailsRef} className="relative mb-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => { setFooterDetailsOpen((open) => open === 'parts' ? null : 'parts'); setDiscountsOpen(false) }}
            className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700 hover:bg-blue-100"
          >
            Parts {isInitialSummaryLoad || summaryLoadFailed ? '…' : money(summary?.parts_total)}
          </button>
          <button
            type="button"
            onClick={() => { setFooterDetailsOpen((open) => open === 'labor' ? null : 'labor'); setDiscountsOpen(false) }}
            className="rounded-full bg-orange-50 px-3 py-1 text-xs font-bold text-orange-700 hover:bg-orange-100"
          >
            Labor {isInitialSummaryLoad || summaryLoadFailed ? '…' : money(effectiveLaborTotal)}
          </button>
          {/* Discounts / Customer saves add noise at $0 — only show them once
              they carry a value. While still loading, keep them (showing "…") so
              the footer doesn't reflow when the numbers land. */}
          {(isInitialSummaryLoad || summaryLoadFailed || discountTotal > 0.005) && (
            <button
              type="button"
              onClick={() => { setFooterDetailsOpen((open) => open === 'discounts' ? null : 'discounts'); setDiscountsOpen(false) }}
              className="rounded-full bg-red-50 px-3 py-1 text-xs font-bold text-red-700 hover:bg-red-100"
            >
              Discounts -{isInitialSummaryLoad || summaryLoadFailed ? '…' : money(discountTotal)}
            </button>
          )}
          {(isInitialSummaryLoad || summaryLoadFailed || customerSavesTotal > 0.005) && (
            <button
              type="button"
              onClick={() => { setFooterDetailsOpen((open) => open === 'savings' ? null : 'savings'); setDiscountsOpen(false) }}
              className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700 hover:bg-emerald-100"
            >
              Customer saves {isInitialSummaryLoad || summaryLoadFailed ? '…' : money(customerSavesTotal)}
            </button>
          )}
          {footerDetailsOpen && (
            <div className="absolute bottom-full left-0 z-20 mb-2 w-[min(380px,calc(100vw-40px))] rounded-[14px] border border-gray-200 bg-white p-4 shadow-[0_10px_30px_rgba(20,25,35,.10)]">
              {renderFooterDetails(footerDetailsOpen)}
            </div>
          )}
          <span className="ml-auto inline-flex" title={!canMutate ? lockContextMessage : undefined}>
            <button
              ref={discountsButtonRef}
              type="button"
              onClick={() => {
                setDiscountsOpen((open) => {
                  const next = !open
                  if (next) setDraftPartsPricingMode(partsPricingMode)
                  return next
                })
                setFooterDetailsOpen(null)
              }}
              disabled={!canMutate}
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-bold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              Discounts & pricing
            </button>
          </span>
          {discountsOpen && (
            <div
              ref={discountsPopoverRef}
              className="absolute bottom-full right-0 mb-2 w-[320px] rounded-[14px] border border-gray-200 bg-white p-4 shadow-[0_10px_30px_rgba(20,25,35,.10)]"
            >
              <div className="mb-3 flex items-center justify-between">
                <p className="font-semibold text-gray-900">Discounts & pricing</p>
                <button type="button" onClick={() => setDiscountsOpen(false)} className="rounded-md p-1 text-gray-400 hover:bg-gray-100">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <label className="mb-3 block text-sm">
                <span className="mb-1 block text-xs font-bold uppercase tracking-wide text-gray-400">Parts pricing</span>
                <select
                  value={draftPartsPricingMode}
                  disabled={discountsSaving}
                  onChange={(e) => {
                    const v = e.target.value
                    if (v === 'stock' || v === 'list') setDraftPartsPricingMode(v)
                  }}
                  className="h-10 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm disabled:opacity-60"
                >
                  <option value="stock">Stock price</option>
                  <option value="list">List price</option>
                </select>
              </label>
              <div className="mb-3 flex items-center justify-between gap-3 text-sm">
                <span className="font-medium text-gray-700">Labor discount</span>
                <span className="flex items-center gap-1.5">
                  <input
                    aria-label="Labor discount"
                    value={laborDiscount}
                    onChange={(e) => setLaborDiscount(e.target.value.replace(/[^0-9.]/g, ''))}
                    inputMode="decimal"
                    placeholder="0.00"
                    className="h-9 w-28 rounded-lg border border-gray-200 bg-white px-2 text-right font-['JetBrains_Mono',monospace] text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => setLaborDiscount('')}
                    disabled={!laborDiscount}
                    className="h-9 rounded-lg px-2 text-xs font-semibold text-gray-500 hover:bg-gray-100 hover:text-gray-800 disabled:opacity-40"
                  >
                    Reset
                  </button>
                </span>
              </div>
              <div className="mb-3 flex items-center justify-between gap-3 text-sm">
                <span className="font-medium text-gray-700">Order discount</span>
                <span className="flex items-center gap-1.5">
                  <input
                    aria-label="Order discount"
                    value={orderDiscount}
                    onChange={(e) => setOrderDiscount(e.target.value.replace(/[^0-9.]/g, ''))}
                    inputMode="decimal"
                    placeholder="0.00"
                    className="h-9 w-28 rounded-lg border border-gray-200 bg-white px-2 text-right font-['JetBrains_Mono',monospace] text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => setOrderDiscount('')}
                    disabled={!orderDiscount}
                    className="h-9 rounded-lg px-2 text-xs font-semibold text-gray-500 hover:bg-gray-100 hover:text-gray-800 disabled:opacity-40"
                  >
                    Reset
                  </button>
                </span>
              </div>
              <div className="flex items-center justify-between border-t border-gray-100 pt-3">
                <span className="text-xs font-semibold text-emerald-700">Customer saves {money(draftCustomerSavesTotal)}</span>
                <button
                  type="button"
                  disabled={discountsSaving}
                  onClick={async () => {
                    await savePricingAdjustments()
                    setDiscountsOpen(false)
                  }}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-orange-500 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-60"
                >
                  {discountsSaving && <Spinner size="xs" />}
                  {discountsSaving ? 'Applying…' : 'Apply'}
                </button>
              </div>
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="ml-auto flex items-center gap-3">
            <div className="text-right">
              <div className="flex items-center justify-end gap-2">
                <p className={`inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.18em] ${
                  summaryLoadFailed ? 'text-red-600' : totalMotionActive || isInitialSummaryLoad ? 'text-orange-700' : 'text-gray-400'
                }`}>
                  {(totalMotionActive || isInitialSummaryLoad) && <Spinner size="xs" />}
                  {summaryLoadFailed ? 'Failed to load' : isInitialSummaryLoad ? 'Loading' : totalMotionActive ? 'Calculating' : 'Order Total'}
                  {summaryLoadFailed && (
                    <button
                      type="button"
                      onClick={() => refetchSummary()}
                      className="ml-1 rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-bold text-red-700 hover:bg-red-200"
                    >
                      Retry
                    </button>
                  )}
                </p>
              </div>
              <p
                className={`price-total-amount font-['Barlow_Condensed',sans-serif] text-[34px] font-extrabold leading-none text-gray-950 ${
                  totalJustChanged ? 'price-total-amount--changed' : totalMotionActive ? 'price-total-amount--updating' : ''
                }`}
              >
                {isInitialSummaryLoad || summaryLoadFailed ? '…' : money(orderTotalValue)}
              </p>
            </div>
            {(!isInternalOrder || hasInvoice) && (
              canCreateInvoice ? (
                <div className="relative">
                  <button
                    type="button"
                    onClick={onToggleInvoiceCreateOptions}
                    disabled={invoiceCreatePending}
                    className="inline-flex h-11 items-center gap-2 rounded-xl bg-indigo-600 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(79,70,229,.26)] hover:bg-indigo-700 disabled:bg-gray-300"
                  >
                    {invoiceCreatePending ? <Spinner size="xs" /> : <FileText className="h-4 w-4" />}
                    {invoiceCreatePending ? 'Creating...' : 'Create Invoice'}
                  </button>
                  {showInvoiceCreateOptions && (
                    <div className="absolute bottom-full right-0 z-30 mb-2 w-[min(340px,calc(100vw-40px))] rounded-[14px] border border-gray-200 bg-white p-4 text-left shadow-[0_10px_30px_rgba(20,25,35,.14)]">
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-gray-950">Invoice due date</p>
                          <p className="text-xs text-gray-500">Create the invoice now, with the due date customers should see.</p>
                        </div>
                        <button
                          type="button"
                          onClick={onToggleInvoiceCreateOptions}
                          className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
                          aria-label="Close invoice due date options"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                      <div className="space-y-2">
                        <button
                          type="button"
                          onClick={() => onCreateInvoice?.(null)}
                          disabled={invoiceCreatePending}
                          className="flex w-full items-center justify-between rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-2.5 text-left hover:border-indigo-200 hover:bg-indigo-100 disabled:opacity-60"
                        >
                          <span>
                            <span className="block text-sm font-bold text-indigo-950">Due today</span>
                            <span className="block text-xs text-indigo-700">Create invoice immediately with today's due date.</span>
                          </span>
                          <FileText className="h-4 w-4 text-indigo-600" />
                        </button>
                        <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
                          <label className="block text-sm">
                            <span className="mb-1 block font-semibold text-gray-700">Choose due date</span>
                            <input
                              type="date"
                              value={invoiceDueDateValue}
                              onChange={(e) => onInvoiceDueDateChange?.(e.target.value)}
                              min={new Date().toISOString().split('T')[0]}
                              className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                            />
                          </label>
                          <button
                            type="button"
                            onClick={() => onCreateInvoice?.(invoiceDueDateValue || null)}
                            disabled={invoiceCreatePending || !invoiceDueDateValue}
                            className="mt-3 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 text-sm font-bold text-white hover:bg-indigo-700 disabled:bg-gray-300"
                          >
                            {invoiceCreatePending && <Spinner size="xs" />}
                            Create invoice with due date
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ) : hasInvoice && invoice ? (
                <div className="flex flex-wrap justify-end gap-2">
                  {orderStatus !== 'paid' && (
                    <button
                      type="button"
                      onClick={onRecordPayment}
                      disabled={invoiceActionPending || !onRecordPayment}
                      className="inline-flex h-11 items-center gap-2 rounded-xl bg-green-600 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(22,163,74,.28)] hover:bg-green-700 disabled:bg-gray-300"
                    >
                      <CreditCard className="h-4 w-4" />
                      {invoice.pending_zelle_confirmation ? 'Confirm Zelle payment' : 'Record payment'}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={onResendInvoice}
                    disabled={invoiceActionPending || !onResendInvoice}
                    className="inline-flex h-11 items-center gap-2 rounded-xl bg-purple-600 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(147,51,234,.24)] hover:bg-purple-700 disabled:bg-gray-300"
                  >
                    <Mail className="h-4 w-4" />
                    {orderStatus === 'paid' ? 'Resend copy' : 'Resend invoice'}
                  </button>
                  {orderStatus !== 'paid' && !invoice.pending_zelle_confirmation && onVoidInvoice && (
                    <button
                      type="button"
                      onClick={onVoidInvoice}
                      disabled={invoiceActionPending}
                      className="inline-flex h-11 items-center gap-2 rounded-xl border border-gray-300 bg-white px-4 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                      title="Preserve this invoice as voided and reopen the order for revision"
                    >
                      <RotateCcw className="h-4 w-4" />
                      Void &amp; revise
                    </button>
                  )}
                </div>
              ) : completionMode ? (
                <button
                  type="button"
                  onClick={onApproveCompletion}
                  disabled={completionPending || !onApproveCompletion}
                  className="inline-flex h-11 items-center gap-2 rounded-xl bg-green-600 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(22,163,74,.28)] hover:bg-green-700 disabled:bg-gray-300"
                >
                  {completionPending ? <Spinner size="xs" /> : <CheckCircle className="h-4 w-4" />}
                  {completionPending ? 'Finalizing...' : 'Finalize & Send Invoice'}
                </button>
              ) : (
                <span className="inline-flex h-11 items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 text-sm font-bold text-blue-800">
                  <CheckCircle className="h-4 w-4" />
                  {orderStatus === 'draft' ? 'Checked in · work order open' : 'Work order open'}
                </span>
              )
            )}
            {canAdminCompleteBypassedWork && !isDeleted && !armWoComplete && (
              <button
                type="button"
                onClick={() => setArmWoComplete(true)}
                className="inline-flex h-11 items-center gap-2 rounded-xl bg-yellow-500 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(234,179,8,.28)] hover:bg-yellow-600"
              >
                <CheckCircle className="h-4 w-4" />
                Mark Completed
              </button>
            )}
            {isInternalOrder && !isDeleted && (
              ['draft', 'assigned', 'acknowledged'].includes(orderStatus) ? (
                <button
                  type="button"
                  disabled={startWorkOrderPending || !onStartWorkOrder}
                  onClick={onStartWorkOrder}
                  className="inline-flex h-11 items-center gap-2 rounded-xl bg-amber-500 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(245,158,11,.28)] hover:bg-amber-600 disabled:bg-gray-300"
                >
                  {startWorkOrderPending ? <Spinner size="xs" /> : <Play className="h-4 w-4" />}
                  {startWorkOrderPending ? 'Starting...' : 'Start Work'}
                </button>
              ) : ['in_progress', 'pending_review'].includes(orderStatus) && !armWoComplete ? (
                <button
                  type="button"
                  onClick={() => { setWoMileageOut(mileageIn != null ? String(mileageIn) : ''); setArmWoComplete(true) }}
                  className="inline-flex h-11 items-center gap-2 rounded-xl bg-yellow-500 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(234,179,8,.28)] hover:bg-yellow-600"
                >
                  <CheckCircle className="h-4 w-4" />
                  Mark Completed
                </button>
              ) : orderStatus === 'completed' ? (
                <span className="inline-flex items-center gap-3">
                  <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-green-700">
                    <CheckCircle className="h-4 w-4" /> Completed
                  </span>
                  {/* Reopen an internal WO so more labor/parts can be added. */}
                  <button
                    type="button"
                    disabled={reopenPending || !onReopenWorkOrder}
                    onClick={onReopenWorkOrder}
                    className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-gray-300 px-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                  >
                    {reopenPending ? <Spinner size="xs" /> : <RotateCcw className="h-3.5 w-3.5" />}
                    {reopenPending ? 'Reopening…' : 'Reopen'}
                  </button>
                </span>
              ) : null
            )}
          </div>
        </div>
        <div className="-mx-5 -mb-4 mt-4 border-t border-red-100 bg-red-50/60">
          <button
            type="button"
            onClick={onToggleDangerActions}
            aria-expanded={showDangerActions}
            className="flex w-full items-center justify-between px-5 py-2.5 text-left text-xs font-semibold text-red-700"
          >
            <span className="inline-flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> Danger zone</span>
            <ChevronUp className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Danger actions open as a bottom sheet on top of the panel so the page
          geometry never shifts (no inline accordion pushing content down). */}
      {showDangerActions && (
        <div className="absolute inset-0 z-40 flex flex-col justify-end">
          <button
            type="button"
            aria-label="Close danger zone"
            onClick={onToggleDangerActions}
            className="absolute inset-0 bg-gray-900/40"
          />
          <div className="animate-slide-in-bottom relative flex max-h-[80%] flex-col rounded-t-2xl border-t border-red-100 bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-red-100 bg-red-50/60 px-5 py-3">
              <span className="inline-flex items-center gap-2 text-sm font-semibold text-red-700">
                <AlertTriangle className="h-4 w-4" /> Danger zone
              </span>
              <button
                type="button"
                onClick={onToggleDangerActions}
                aria-label="Close"
                className="flex h-8 w-8 items-center justify-center rounded-md text-red-600 hover:bg-red-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {isDeleted ? (
                <>
                  <p className="mb-4 text-sm text-red-700">
                    {(() => {
                      const when = deletedAt ? format(new Date(deletedAt), 'MMM d, yyyy h:mm a') : null
                      if (deletedByName && when) return `Deleted by ${deletedByName} on ${when}. Restore to bring it back.`
                      if (when) return `Deleted on ${when}. Restore to bring it back.`
                      return 'This order is deleted. Restore to bring it back.'
                    })()}
                  </p>
                  <button
                    type="button"
                    disabled={restorePending}
                    onClick={onRestoreOrder}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                  >
                    <RotateCcw className="h-4 w-4" />
                    {restorePending ? 'Restoring...' : 'Restore order'}
                  </button>
                </>
              ) : (
                <>
                  <p className="mb-4 text-sm text-red-700">
                    Delete removes this order from your active lists. Nothing is destroyed —
                    it can be restored later from the Deleted filter.
                  </p>
                  <button
                    type="button"
                    disabled={deletePending}
                    onClick={onDeleteOrder}
                    className="w-full rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                  >
                    {deletePending ? 'Deleting...' : 'Delete'}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
