import { useAdHocPartCommand } from '@/features/parts-pricing/useAdHocPartCommand'
import { usePricingCommand } from '@/features/parts-pricing/usePricingCommand'
import { usePricingScope } from '@/features/parts-pricing/usePricingScope'
import { PricingCancelled, parsePricingPreview, pricingError, pricingMoney, priceSourceLabel } from '@/features/parts-pricing/contract'
import { enteredMoney } from '@/features/parts-pricing/configuration'
import RepairOrderScheduleControl from './RepairOrderScheduleControl'
import type { OrderScheduleSummary } from './repairOrderSchedule'
import RepairOrderActivity from './RepairOrderActivity'
import { OperationExecutionControls, OperationExecutionFeedback, OperationExecutionStatus } from '@/features/operation-execution/OperationExecution'
import { useOperationExecution } from '@/features/operation-execution/queries'
import { OperationNotes } from '@/features/operation-execution/OperationNotes'
import OrderChecklist from '@/features/service-checklists/OrderChecklist'
import { type ReactNode, type ChangeEvent, type MouseEvent as ReactMouseEvent, useEffect, useRef, useState } from 'react'
import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import WorkspaceActionOverflow from '@/components/WorkspaceActionOverflow'
import { useCompactWorkspace } from '@/hooks/useCompactWorkspace'
import DatePicker from '@/components/DatePicker'
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
  X, StickyNote, Pencil, Star } from 'lucide-react'

import api from '@/lib/api'
import { ConversionLink, type ConversionContext } from './RecommendationConversionAction'
import RecommendationSourceLink from './RecommendationSourceLink'
import { revealWorkspaceContent } from './recommendationConversion'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import QuantityStepper from '@/components/QuantityStepper'
import StartWorkAction from './StartWorkAction'
import StaffHoldDialog from './StaffHoldDialog'
import { canManageWorkHold, type WorkHoldOrder } from './staffHold'
import { useAuthStore } from '@/stores/authStore'
import OrderIntakeDetails, { type OrderIntakePatch } from './OrderIntakeDetails'
import { holdReasonLabel } from './holdReason'
import DiscountAmountInput from './DiscountAmountInput'
import WorkflowInfoStep, { WorkflowInfoGroup, type WorkflowInfo } from './WorkflowInfoStep'
import DurationStepper from '@/components/DurationStepper'
import { formatHoursMinutes } from '@/lib/durationFormat'
import { formatFileSize, isSupportedPhotoFile, runPhotoUploadQueue, uploadDirectPhoto, type PhotoUploadStatus } from '@/lib/photoUpload'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'
import { SettlementSummaryCard, type InvoiceSettlementSummary } from '@/features/payments'
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

export type PriceBuilderNote = {
  id: string
  body: string
  audience: 'customer' | 'shop'
  at: string
  actor?: string
  /** Whether this viewer may remove it — their own note, or any if they run the shop. */
  canDelete: boolean
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
  workspaceNotice?: ReactNode
  orderId: string
  orderStatus: RepairOrderStatus
  canEdit: boolean
  schedule?: OrderScheduleSummary
  workHoldOrder?: WorkHoldOrder
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
  mileageInCarried?: boolean
  onSaveIntake?: (patch: OrderIntakePatch) => Promise<void>
  mileageIn?: number | null
  mileageOut?: number | null
  poNumber?: string | null
  orderTypeLabel?: string
  /** The carrier is on a fleet plan — distinct from isInternalOrder, which is
      the shop's own trucks. A customer can be one, both, or neither. */
  isFleetMember?: boolean
  onOpenCustomer?: () => void
  onOpenVehicleHistory?: () => void
  onSaveDescription?: (description: string | null) => Promise<void> | void
  descriptionSaving?: boolean
  notes?: PriceBuilderNote[]
  onAddNote?: (note: { body: string; audience: 'customer' | 'shop' }) => Promise<void> | void
  onDeleteNote?: (noteId: string) => Promise<void> | void
  notesSaving?: boolean
  quoteNumber?: string | null
  quoteIsSent?: boolean
  quoteIsApproved?: boolean
  quoteActionLabel?: string
  quoteActionPending?: boolean
  quoteActionDisabled?: boolean
  quoteDisabledReason?: string
  onQuoteAction?: (trigger?: HTMLButtonElement) => void
  workflowInfo?: WorkflowInfo
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
  invoiceRecipientOptions?: Array<{ id: string; company_name: string; relationship_label: string }>
  invoiceRecipientId?: string
  onInvoiceRecipientChange?: (value: string) => void
  onCreateInvoice?: (dueDate?: string | null, billToCustomerId?: string) => void
  invoice?: Invoice | null
  invoiceSettlement?: InvoiceSettlementSummary | null
  invoiceActionPending?: boolean
  onResendInvoice?: () => void
  onRecordPayment?: () => void
  onVoidInvoice?: () => void
  historyEvents?: PriceBuilderHistoryEvent[]
  onHistoryOpen?: () => void
  historyLoading?: boolean
  historyError?: boolean
  onHistoryRetry?: () => void
  onClose?: () => void
  onPrev?: () => void
  onNext?: () => void
  prevDisabled?: boolean
  nextDisabled?: boolean
  showDangerActions?: boolean
  onToggleDangerActions?: () => void
  onDeleteOrder?: () => void
  deletePending?: boolean
  /** Shown only when the financial-record guard is what blocks deleting. */
  canForceVoid?: boolean
  onForceVoidOrder?: (args: { reason: string; password: string }) => Promise<void> | void
  forceVoidPending?: boolean
  isDeleted?: boolean
  deletedByName?: string | null
  deletedAt?: string | null
  onRestoreOrder?: () => void
  restorePending?: boolean
  onReopenWorkOrder?: () => void
  reopenPending?: boolean
  recommendedWorkPanel?: ReactNode | ((context: ConversionContext) => ReactNode)
  focusedOperationId?: string | null
  focusedRecommendationId?: string | null
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
  return pricingError(error, fallback)
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
      className="db-part-quantity"
      align="start"
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
  line: { id: string; description: string; hours: string; hourly_rate: string; total_cost: string; pricing?: SafeLaborPricing }
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
          {line.pricing && <small>{laborSourceLabel(line.pricing)}</small>}
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
          aria-label="Labor description"
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
          <span className="text-[11px] font-medium uppercase tracking-wide text-slate-600">Duration</span>
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
          <span className="text-[11px] font-medium uppercase tracking-wide text-slate-600">Rate</span>
          <span className="text-gray-500">$</span>
          {line.pricing?.can_override === false ? <span className="tabular-nums">{lineRate.toFixed(2)}/hr</span> : <QuantityStepper
            value={lineRate}
            onChange={(r) => onUpdate({ hourly_rate: r })}
            onLocalChange={(r) => onLocalChange({ hourly_rate: r })}
            min={0}
            step={25}
            unitLabel="/hr"
            ariaLabel="Labor hourly rate"
            align="start"
            commitDebounceMs={STEPPER_COMMIT_DEBOUNCE_MS}
          />}
        </label>
        {line.pricing && <small className="text-slate-600">{laborSourceLabel(line.pricing)}</small>}
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
        className={`truncate font-['Barlow_Condensed',sans-serif] !text-white text-3xl font-extrabold leading-none tracking-wide${
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

type PartPriceChange = { price_action: 'manual' | 'list' | 'stock'; unit_price?: string; price_override_reason?: string }
function PartPricePopover({ part, disabled, saving, onApply }: { part: PartsUsage; disabled?: boolean; saving?: boolean; onApply: (change: PartPriceChange) => Promise<void> }) {
  const [draft, setDraft] = useState(part.unit_price)
  const [reason, setReason] = useState('')
  const [action, setAction] = useState<PartPriceChange['price_action']>('manual')
  const [error, setError] = useState<string | null>(null)
  const [opened, setOpened] = useState(false)
  const scope = usePricingScope()
  const role = useAuthStore(state => state.user?.role)
  const manager = role === 'garage_owner' || role === 'garage_admin'
  const details = useQuery({ queryKey: ['saved-part-pricing', scope, part.repair_order_id, part.id, part.pricing?.pricing_version], enabled: opened && manager, gcTime: 0, retry: false, queryFn: async ({ signal }) => {
    const request = { context: { kind: 'repair_order' as const, repair_order_id: part.repair_order_id }, plan: { kind: 'parts_add' as const, lines: [] }, include_management_details: true }
    const preview = parsePricingPreview((await api.post('/parts-pricing/resolve', request, { signal })).data, request, role)
    if (preview.projection !== 'shop') throw new Error('Invalid pricing projection')
    const line = preview.lines.find(item => item.parts_usage_id === part.id)
    return preview.management?.lines.find(item => item.line_key === line?.line_key) ?? null
  } })
  const editable = !disabled && (part.pricing?.can_override ?? ['garage_owner', 'garage_admin', 'receptionist'].includes(role ?? ''))
  return <Popover as="span" className="inline-block">{({ close }) => <>
    <PopoverButton type="button" onClick={() => { setDraft(Number(part.unit_price).toFixed(2)); setReason(''); setAction('manual'); setError(null); setOpened(true) }} className="db-part-price h-8 min-w-[84px] whitespace-nowrap rounded-lg border bg-white px-2 text-right font-['JetBrains_Mono',monospace] text-xs text-gray-900 shadow-sm border-gray-200">{money(part.unit_price)} <ChevronDown className="ml-1 inline h-3 w-3 text-gray-400" /></PopoverButton>
    <PopoverPanel anchor="bottom end" focus aria-label={`Part pricing for ${part.inventory_name}`} className="db-part-price-panel db-parts-pricing z-[70] w-[min(340px,calc(100vw-32px))] max-h-[calc(100dvh-32px)] overflow-y-auto rounded-[14px] border border-gray-200 p-3 text-sm shadow-xl [--anchor-gap:4px] [--anchor-padding:16px]">
      <div className="db-parts-pricing__toolbar"><strong>{part.inventory_name}</strong><button type="button" aria-label="Close part pricing" onClick={() => { setOpened(false); close() }}><X size={16} /></button></div>
      <p className="db-parts-pricing__muted">Saved charge {pricingMoney(part.unit_price)} · {priceSourceLabel(part.pricing?.current_source, part.pricing?.policy_source)} · Saved default {pricingMoney(part.pricing?.default_unit_price ?? part.list_price)}</p>
      {manager && <><p className="db-parts-pricing__muted">Actual cost {details.data ? details.data.actual_cost_known ? pricingMoney(details.data.actual_unit_cost) : 'Unknown' : '—'}</p>{details.isError && <p role="alert">Saved pricing details unavailable.</p>}{!details.isError && details.data && <p className="db-parts-pricing__muted">{details.data.matrix ? `${details.data.matrix.name} · Revision ${details.data.matrix.revision} · ${details.data.matrix.band.markup_percent}% markup` : details.data.fixed_catalog_price ? 'Fixed catalog price' : 'No saved matrix'} · Basis {pricingMoney(details.data.pricing_basis)} · Minimum {pricingMoney(details.data.effective_minimum)}{details.data.override && <> · {details.data.override.reason} · {new Date(details.data.override.occurred_at).toLocaleString()}</>}</p>}</>}
      {editable && <><label>Customer price<input inputMode="decimal" value={draft} disabled={saving} onChange={event => { setDraft(event.target.value); setAction('manual') }} /></label>{action === 'manual' && <label>Override reason<input value={reason} maxLength={500} disabled={saving} onChange={event => setReason(event.target.value)} placeholder="Required for a price change" /></label>}
      <div className="db-parts-pricing__actions"><button type="button" disabled={saving} onClick={() => { setDraft(part.pricing?.default_unit_price ?? part.list_price ?? part.unit_price); setAction('list') }}>List</button><button type="button" disabled={saving || part.unit_cost === null} onClick={() => { setDraft(part.unit_cost ?? ''); setAction('stock') }}>Stock</button><button type="button" disabled={saving} onClick={async () => {
        try { const amount = enteredMoney(draft); if (amount === null) throw new Error('Enter a customer price.'); if (action === 'manual' && amount === part.unit_price) { setOpened(false); close(); return } if (action === 'manual' && reason.trim().length < 3) throw new Error('Enter an override reason of at least 3 characters.'); await onApply({ price_action: action, ...(action === 'manual' ? { unit_price: amount, price_override_reason: reason.trim() } : {}) }); setOpened(false); close() } catch (cause) { setError(pricingError(cause, cause instanceof Error ? cause.message : 'Price could not be saved.')) }
      }}>{saving ? 'Applying…' : 'Apply'}</button></div></>}
      {error && <p role="alert">{error}</p>}
    </PopoverPanel>
  </>}</Popover>
}

export default function PriceBuilderPanel({
  orderId,
  orderStatus,
  canEdit,
  workHoldOrder,
  schedule,
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
  mileageInCarried,
  onSaveIntake,
  mileageOut,
  poNumber,
  orderTypeLabel,
  isFleetMember = false,
  onOpenCustomer,
  onOpenVehicleHistory,
  onSaveDescription,
  descriptionSaving = false,
  notes = [],
  onAddNote,
  onDeleteNote,
  notesSaving = false,
  quoteNumber,
  quoteIsApproved = false,
  quoteActionLabel = 'Create estimate',
  quoteActionPending = false,
  quoteActionDisabled = false,
  quoteDisabledReason,
  onQuoteAction,
  workflowInfo,
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
  invoiceRecipientOptions = [],
  invoiceRecipientId = '',
  onInvoiceRecipientChange,
  onCreateInvoice,
  invoice,
  invoiceSettlement = null,
  invoiceActionPending = false,
  onResendInvoice,
  onRecordPayment,
  onVoidInvoice,
  historyEvents = [],
  onHistoryOpen,
  historyLoading = false,
  historyError = false,
  onHistoryRetry,
  onClose,
  onPrev,
  onNext,
  prevDisabled,
  nextDisabled,
  showDangerActions,
  onToggleDangerActions,
  onDeleteOrder,
  deletePending,
  canForceVoid = false,
  onForceVoidOrder,
  forceVoidPending = false,
  isDeleted = false,
  deletedByName,
  deletedAt,
  onRestoreOrder,
  restorePending = false,
  onReopenWorkOrder,
  reopenPending = false,
  workspaceNotice,
  recommendedWorkPanel,
  focusedOperationId,
  focusedRecommendationId,
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
  const staffRole = useAuthStore(state => state.user?.role)
  const pricingScope = usePricingScope()
  const pricingCommand = usePricingCommand(`repair-order:${orderId}`)
  const adHocPricing = useAdHocPartCommand(orderId, 'shop', isInternalOrder)
  const [holdDialogOrderId, setHoldDialogOrderId] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [candidates, setCandidates] = useState<RepairOperationCandidate[]>([])
  const [searchWarnings, setSearchWarnings] = useState<{ code: string; message: string }[]>([])
  const [addType, setAddType] = useState<AddBarType>(() => (
    !['completed', 'invoiced', 'paid', 'cancelled'].includes(orderStatus) ? 'operation' : 'history'
  ))
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [invoiceDetailsOpen, setInvoiceDetailsOpen] = useState(false)
  const [openLineIds, setOpenLineIds] = useState<Set<string>>(new Set())
  const focusedLink = useRef<string | null>(null)
  const openLinkedOperation = (id: string) => {
    setOpenLineIds((current) => new Set([...current, id]))
    requestAnimationFrame(() => {
      const trigger = document.getElementById(`operation-trigger-${id}`)
      trigger?.focus({ preventScroll: true })
      if (trigger) revealWorkspaceContent(trigger)
    })
  }
  const [discountsOpen, setDiscountsOpen] = useState(false)
  const [footerDetailsOpen, setFooterDetailsOpen] = useState<'parts' | 'labor' | 'discounts' | 'savings' | null>(null)
  const [totalJustChanged, setTotalJustChanged] = useState(false)
  const [totalMotionActive, setTotalMotionActive] = useState(false)
  const previousTotalRef = useRef<string | null>(null)
  const totalMotionTimerRef = useRef<number | null>(null)
  const [secondaryPanel, setSecondaryPanel] = useState<'recommended' | 'notes' | 'photos' | null>(null)
  const recommendedOpen = secondaryPanel === 'recommended'
  const notesOpen = secondaryPanel === 'notes'
  const photosOpen = secondaryPanel === 'photos'
  const openSecondaryPanel = (panel: typeof secondaryPanel) => {
    setSecondaryPanel(panel)
    onRecommendedServicesOpenChange?.(panel === 'recommended')
  }
  const toggleSecondaryPanel = (panel: NonNullable<typeof secondaryPanel>) => {
    openSecondaryPanel(secondaryPanel === panel ? null : panel)
  }
  // A note belongs to the order, not to a service on it, so it lives beside
  // Customer & Vehicle rather than inside the work list. Notes accumulate:
  // each one is signed and timed and never overwrites the last, because the
  // question a note answers later is "who said this, and when".
  // Forcing past the financial-record guard. Two fields, because the password
  // is what makes this different from every other button in the danger zone.
  // Work requested was read-only, and the whole block was hidden when empty —
  // so an order that came in without one could never be given one.
  const [descriptionEditing, setDescriptionEditing] = useState(false)
  const [descriptionDraft, setDescriptionDraft] = useState('')
  const descriptionRef = useRef<HTMLTextAreaElement | null>(null)
  const descriptionWasEditing = useRef(false)
  useEffect(() => {
    if (descriptionEditing && !descriptionWasEditing.current) descriptionRef.current?.focus()
    descriptionWasEditing.current = descriptionEditing
  }, [descriptionEditing])
  const [forceVoidOpen, setForceVoidOpen] = useState(false)
  const [forceVoidReason, setForceVoidReason] = useState('')
  const [forceVoidPassword, setForceVoidPassword] = useState('')
  const [noteComposerOpen, setNoteComposerOpen] = useState(false)
  const [noteAudience, setNoteAudience] = useState<'customer' | 'shop'>('shop')
  const [noteDraft, setNoteDraft] = useState('')
  const noteInputRef = useRef<HTMLTextAreaElement | null>(null)
  const noteComposerWasOpen = useRef(false)
  // Focus on the open transition only — not on every render, which is what
  // made autoFocus steal the caret in the ad-hoc part form.
  useEffect(() => {
    if (noteComposerOpen && !noteComposerWasOpen.current) noteInputRef.current?.focus()
    noteComposerWasOpen.current = noteComposerOpen
  }, [noteComposerOpen])
  const notesNewestFirst = [...notes].sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime())
  // Closed by default: the pipeline row above already names this step, and the
  // pill there opens this when the operator actually wants it. Open on load, it
  // cost ~140px above the work list on every order.
  // The unlisted part a tech is holding: name is what they know, the rest is
  // what the bill needs.
  const [adHocDraft, setAdHocDraft] = useState<{ name: string; sku: string; price: string; cost: string; quantity: string } | null>(null)
  const adHocNameRef = useRef<HTMLInputElement | null>(null)
  const adHocWasOpen = useRef(false)
  // Until the operator types in the name field, the search box is still the
  // thing they are naming the part with — keep the name following it. The
  // moment they edit the name directly, it stops following: the field they
  // touched last is the one that means it.
  const adHocNameClaimed = useRef(false)
  // Focus the name once, when the form opens — not on every render of it. The
  // form is rebuilt each time the search query settles, so autoFocus here pulled
  // the caret back out of the search field on every keystroke and the typed
  // characters went nowhere.
  useEffect(() => {
    const open = adHocDraft !== null
    if (open && !adHocWasOpen.current) {
      adHocNameClaimed.current = false
      adHocNameRef.current?.focus()
    }
    adHocWasOpen.current = open
  }, [adHocDraft])
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
  // Escape backs out of adding a part — first the form, then the panel — so the
  // operator never has to find the close control to abandon the attempt.
  useEffect(() => {
    if (!operationPartPickerLineId && !adHocDraft) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (adHocDraft) setAdHocDraft(null)
      else setOperationPartPickerLineId(null)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [operationPartPickerLineId, adHocDraft])
  const [operationPartSearchByLineId, setOperationPartSearchByLineId] = useState<Record<string, string>>({})
  const [bookTimeHours, setBookTimeHours] = useState('1')
  const desktopQuoteActionRef = useRef<HTMLButtonElement>(null)
  const mobileQuoteActionRef = useRef<HTMLButtonElement>(null)
  const restoreQuoteActionFocusRef = useRef(false)

  const handleQuoteActionClick = (event: ReactMouseEvent<HTMLButtonElement>) => {
    restoreQuoteActionFocusRef.current = document.activeElement === event.currentTarget
    onQuoteAction?.(event.currentTarget)
  }

  // Publishing mutations temporarily disable the focused action. Browsers move
  // focus to <body> when that happens, so explicitly return keyboard users to
  // the successor action once the create/update transition has settled.
  useEffect(() => {
    if (quoteActionPending || !restoreQuoteActionFocusRef.current) return

    const frame = window.requestAnimationFrame(() => {
      const candidates = [desktopQuoteActionRef.current, mobileQuoteActionRef.current]
        .filter((candidate): candidate is HTMLButtonElement => !!candidate && !candidate.disabled)
      const visibleCandidate = candidates.find((candidate) => {
        const style = window.getComputedStyle(candidate)
        return style.display !== 'none' && style.visibility !== 'hidden' && candidate.getClientRects().length > 0
      })
      const candidate = visibleCandidate ?? candidates[0]
      candidate?.focus({ preventScroll: true })
      restoreQuoteActionFocusRef.current = false
    })

    return () => window.cancelAnimationFrame(frame)
  }, [quoteActionLabel, quoteActionPending])

  // Accordions belong to the selected order. Resetting them on navigation
  // prevents a panel opened for one order from silently triggering optional
  // reads for the next order in the work queue.
  useEffect(() => {
    setSecondaryPanel(focusedRecommendationId ? 'recommended' : null)
    setArmWoComplete(false)
    onRecommendedServicesOpenChange?.(!!focusedRecommendationId)
    focusedLink.current = null
  }, [orderId, focusedRecommendationId, onRecommendedServicesOpenChange])

  useEffect(() => {
    if (!focusedRecommendationId || !recommendedServices?.some((item) => item.id === focusedRecommendationId)) return
    const key = `recommendation-${focusedRecommendationId}`
    if (focusedLink.current === key) return
    const frame = requestAnimationFrame(() => {
      const row = document.getElementById(key)
      row?.focus({ preventScroll: true })
      if (row) revealWorkspaceContent(row)
      if (row) focusedLink.current = key
    })
    return () => cancelAnimationFrame(frame)
  }, [focusedRecommendationId, recommendedServices])

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
    queryKey: ['price-build', orderId, pricingScope],
    gcTime: 0,
    queryFn: async ({ signal }) => {
      const response = await api.get(`/repair-orders/${orderId}/price-build`, { signal })
      return response.data
    },
    // A soft-deleted order's work/labor endpoints 404 (the order is hidden from
    // them), so don't fetch when deleted — the panel shows the Restore state.
    enabled: !!orderId && !isDeleted,
  })

  const operationExecution = useOperationExecution(orderId, summary, !isDeleted)

  const isFinalizedOrder = ['completed', 'invoiced', 'paid', 'cancelled'].includes(orderStatus)
  const { data: repairPhotosData, isFetching: repairPhotosFetching } = useQuery<RepairOrderPhoto[]>({
    queryKey: ['repair-order-photos', orderId],
    queryFn: async ({ signal }) => {
      const response = await api.get(`/repair-orders/${orderId}/photos`, { signal })
      return response.data
    },
    // Load attachment metadata up front for the collapsed count. Image elements
    // remain in the expanded gallery, so the trigger never loads thumbnails.
    enabled: !!orderId && !isDeleted,
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
    openSecondaryPanel('photos')

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

  const partsUsed = summary?.parts
  const partsFetching = summaryFetching

  const partSearchTerm = useDebouncedValue(searchTerm.trim(), 250)
  const operationPartSearchTerm = useDebouncedValue(
    operationPartPickerLineId ? (operationPartSearchByLineId[operationPartPickerLineId] || '').trim() : '',
    250,
  )
  const inventorySearchTerm = addType === 'part' ? partSearchTerm : operationPartSearchTerm

  // Whichever search box opened the new-part form is still the one the operator
  // is typing the part's name into. Track it raw, not debounced — the name
  // should follow the keystrokes, not lag a beat behind them.
  const adHocSourceSearch = operationPartPickerLineId
    ? operationPartSearchByLineId[operationPartPickerLineId] || ''
    : searchTerm
  useEffect(() => {
    if (!adHocDraft || adHocNameClaimed.current) return
    const next = adHocSourceSearch.trim()
    setAdHocDraft((current) => (current && current.name !== next ? { ...current, name: next } : current))
  }, [adHocSourceSearch, adHocDraft])
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

  // What this operation actually consumes, from the shop's own history. Asked
  // per line rather than per order: someone adding a part to a tire change
  // should be offered what tire changes use, not everything else on the order.
  const { data: operationSuggestionData } = useQuery<PartSuggestionsResponse>({
    queryKey: ['price-build-part-suggestions', orderId, operationPartPickerLineId],
    queryFn: async ({ signal }) => {
      const response = await api.get(`/repair-orders/${orderId}/parts/suggestions`, {
        signal,
        params: { line_id: operationPartPickerLineId },
      })
      return response.data
    },
    enabled: !!orderId && !isDeleted && !!operationPartPickerLineId && operationPartSearchTerm.length === 0,
  })
  const operationSuggestions = (operationSuggestionData?.for_this_order ?? []).slice(0, 6)

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
    enabled: !isDeleted && addType === 'saved_labor',
  })

  const [editingPartsSaving, setEditingPartsSaving] = useState(false)
  const [priceSavingId, setPriceSavingId] = useState<string | null>(null)


  const isOnHold = orderStatus === 'in_progress' && !!workflowInfo?.hold_reason
  useEffect(() => {
    if (isOnHold) setArmWoComplete(false)
  }, [isOnHold])
  const holdLabel = isOnHold ? holdReasonLabel(workflowInfo!.hold_reason!) : ''
  useEffect(() => {
    if (isDeleted) {
      setDescriptionEditing(false)
      setArmWoComplete(false)
      setHoldDialogOrderId(null)
    }
  }, [isDeleted])
  const isLocked = !!summary?.pricing_locked
  const hasInvoice = !!invoice && ['invoiced', 'paid'].includes(orderStatus)
  const invoiceDisplayTotal = invoiceSettlement
    ? parseFloat(invoiceSettlement.allocatable_balance || '0')
    : invoice
    ? Math.max(
        0,
        parseFloat(invoice.total_amount || '0')
          - (invoice.pending_zelle_confirmation ? parseFloat(invoice.service_fee_amount || '0') : 0),
      )
    : 0
  const invoiceFinanciallyPaid = invoiceSettlement
    ? invoiceSettlement.state === 'paid'
    : orderStatus === 'paid'
  const canCreateInvoice = !isInternalOrder && orderStatus === 'completed' && !!onCreateInvoice
  const recommendationsReadOnly = isDeleted || ['completed', 'invoiced', 'paid', 'cancelled'].includes(orderStatus)
  const showRecommendedServicesPanel = !recommendationsReadOnly || !!focusedRecommendationId
  // Work-first: the repair order is editable throughout active shop work. The
  // server capability is authoritative; the fallback supports older responses.
  const INTERNAL_FROZEN_STATUSES: RepairOrderStatus[] = ['completed', 'invoiced', 'paid', 'cancelled']
  const isEditableStatus = summary?.can_edit_work ?? !INTERNAL_FROZEN_STATUSES.includes(orderStatus)
  const canMutate = canEdit && !isDeleted && !isLocked && isEditableStatus
  const canManageHold = !!workHoldOrder && canMutate && !isDeleted && !hasInvoice && canManageWorkHold(staffRole, workHoldOrder)
  const holdAction = (beforeOpen?: () => void) => canManageHold && <button type="button" onClick={() => { beforeOpen?.(); setHoldDialogOrderId(orderId) }} className="db-stage-action inline-flex min-h-11 items-center justify-center whitespace-nowrap rounded-lg border border-gray-300 px-3 text-sm font-semibold text-gray-700 hover:bg-gray-50">{isOnHold ? 'Release hold' : 'Put on hold'}</button>
  useEffect(() => {
    if (!focusedOperationId || !summary?.lines.some((line) => line.id === focusedOperationId)) return
    const key = `operation-${focusedOperationId}`
    if (focusedLink.current === key) return
    focusedLink.current = key
    openLinkedOperation(focusedOperationId)
  }, [focusedOperationId, summary?.lines])
  // The add bar must follow the same editable-status rule as canMutate, or an
  // internal in-progress order shows "start by adding…" with no add controls.
  // Quality review is still pre-finalization: managers may discover another
  // operation, part, or labor adjustment while reviewing the completed work.
  // The invoice/pricing lock remains the boundary that makes this read-only.
  const addBarReadOnly = !canEdit || isLocked || !isEditableStatus || hasInvoice || orderStatus === 'completed'
  // An empty work order has nothing to estimate.
  const isEmptyOrder = effectiveLaborLines.length === 0 && (partsUsed?.length ?? 0) === 0
  const hasAssignedTechnician = !!assignedTechnicianName
  const technicianAssignmentBypassed = !hasAssignedTechnician && ['in_progress', 'pending_review', 'completed', 'invoiced', 'paid'].includes(orderStatus)
  const canAdminCompleteBypassedWork = !isInternalOrder && technicianAssignmentBypassed && orderStatus === 'in_progress' && !!onAdminCompleteWork
  // A finalized order is closed: the work is done and billed/settled. No more
  // photo uploads; the informational pipeline remains available for history.
  const isFinalized = isFinalizedOrder
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
  // A completed draft estimate is ready for the customer-facing send action.
  // Give that one actionable state a clear, calm success treatment without
  // implying that create, resend, or disabled states are equally ready.
  const quoteActionReadyToSend = ['Send estimate', 'Send additional work'].includes(quoteActionLabel) && !quoteActionBlocked
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
  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['price-build', orderId] }),
      queryClient.invalidateQueries({ queryKey: ['price-build-part-suggestions', orderId] }),
      queryClient.invalidateQueries({ queryKey: ['inventory-typeahead'] }),
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', orderId] }),
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] }),
      queryClient.invalidateQueries({ queryKey: ['recommended-work'] }),
      queryClient.invalidateQueries({ queryKey: ['recommended-services'] }),
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
        expected_pricing_version: part.pricing?.pricing_version,
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

  const nextLaborDiscount = laborDiscount.trim() === '' ? '0' : laborDiscount
  const nextOrderDiscount = orderDiscount.trim() === '' ? '0' : orderDiscount
  const discountsChanged = (
    Math.abs((parseFloat(nextLaborDiscount) || 0) - (parseFloat(summary?.labor_discount_amount || '0') || 0)) >= 0.005
    || Math.abs((parseFloat(nextOrderDiscount) || 0) - (parseFloat(summary?.order_discount_amount || '0') || 0)) >= 0.005
  )
  const pricingAdjustmentsChanged = draftPartsPricingMode !== partsPricingMode || discountsChanged
  type DiscountCapacity = {
    labor_discount_max: string | number
    combined_discount_max: string | number
    labor_discount_block_reason: string | null
    order_discount_block_reason: string | null
  }
  const { data: discountLimits, isError: discountLimitsError } = useQuery({
    queryKey: ['discount-limits', orderId, summary],
    queryFn: async () => (await api.get<Record<'current' | 'stock' | 'list', DiscountCapacity>>(`/repair-orders/${orderId}/discount-limits`)).data,
    enabled: !isDeleted && discountsOpen && canEdit,
    retry: false,
  })
  const discountCapacity = discountLimits?.[draftPartsPricingMode === partsPricingMode ? 'current' : draftPartsPricingMode]
  const maxLaborDiscount = Number(discountCapacity?.labor_discount_max ?? 0)
  // Compare currency in cents: 198.89 - 187.50 is slightly below 11.39 in binary.
  const discountCents = (value: string | number) => Math.round(Number(value) * 100)
  const maxOrderDiscount = discountCapacity?.order_discount_block_reason ? 0 : Math.max(0, discountCents(discountCapacity?.combined_discount_max ?? 0) - discountCents(nextLaborDiscount || 0)) / 100
  const discountValidation = !discountCapacity
    ? (discountLimitsError ? 'Discount limits could not be loaded. Reopen pricing to retry.' : 'Checking available discounts…')
    : !Number.isFinite(Number(nextLaborDiscount)) || !Number.isFinite(Number(nextOrderDiscount))
      ? 'Enter valid dollar amounts for discounts.'
    : discountCents(nextLaborDiscount) > discountCents(maxLaborDiscount)
      ? (discountCapacity.labor_discount_block_reason || `Labor discount is limited to ${money(maxLaborDiscount)} to protect shop cost.`)
      : discountCents(nextOrderDiscount) > discountCents(maxOrderDiscount)
        ? (discountCapacity.order_discount_block_reason || `Order discount is limited to ${money(maxOrderDiscount)} after the labor discount.`)
        : null

  const savePricingAdjustments = async () => {
    if (discountsSaving || !pricingAdjustmentsChanged || discountValidation) return false
    setDiscountsSaving(true)
    try {
      const response = await api.patch<PriceBuildSummary>(`/repair-orders/${orderId}/discounts`, {
        labor_discount_amount: nextLaborDiscount,
        order_discount_amount: nextOrderDiscount,
        ...(draftPartsPricingMode !== partsPricingMode ? { parts_pricing_mode: draftPartsPricingMode, expected_parts_fingerprint: summary?.parts_pricing_fingerprint } : {}),
      })
      setPartsPricingMode(draftPartsPricingMode)
      queryClient.setQueryData<PriceBuildSummary>(['price-build', orderId, pricingScope], response.data)
      void queryClient.invalidateQueries({ queryKey: ['discount-limits', orderId] })
      onUpdated?.()
      return true
    } catch (err: unknown) {
      toast.error(errorDetail(err, 'Failed to apply pricing adjustments'))
      void queryClient.invalidateQueries({ queryKey: ['price-build', orderId] })
      void queryClient.invalidateQueries({ queryKey: ['discount-limits', orderId] })
      return false
    } finally {
      setDiscountsSaving(false)
    }
  }

  const addAdHocPart = useMutation({
    mutationFn: async (draft: { name: string; sku: string; price: string; cost: string; quantity: string; sourceLineId?: string | null }) => {
      await adHocPricing.execute({
        name: draft.name.trim(),
        sku: draft.sku.trim() || null,
        quantity: Number(draft.quantity || '1'),
        unit_price: Number(draft.price || '0'),
        unit_cost: draft.cost.trim() === '' ? null : Number(draft.cost),
        source_line_id: draft.sourceLineId ?? null,
      })
    },
    onSuccess: async () => {
      setAdHocDraft(null)
      setSearchTerm('')
      setPaletteOpen(false)
      await invalidate()
      // The part is on the order and in the catalogue, so the next job can find
      // it by name instead of inventing it again.
      queryClient.invalidateQueries({ queryKey: ['inventory-typeahead'] })
      toast.success('Part added and saved to the catalogue')
    },
    onError: (cause) => { if (!(cause instanceof PricingCancelled)) toast.error(pricingError(cause, 'Could not add that part')) },
  })

  // One form, wherever the operator finds the part missing: the Part tab,
  // or the operation that needs it. sourceLineId decides what it attaches to.
  const renderAdHocForm = (sourceLineId: string | null) => {
    if (!adHocDraft) return null
    const draft = adHocDraft
    return (
                  <form
                    className="space-y-2 px-2 py-3"
                    onSubmit={(event) => { event.preventDefault(); addAdHocPart.mutate({ ...draft, sourceLineId }) }}
                  >
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-gray-500">New part</p>
                    <input
                      ref={adHocNameRef}
                      value={draft.name}
                      onChange={(e) => { adHocNameClaimed.current = true; setAdHocDraft({ ...draft, name: e.target.value }) }}
                      placeholder="Part name"
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:ring-2 focus:ring-orange-500"
                    />
                    <div className="grid grid-cols-2 gap-2">
                      <input
                        value={draft.sku}
                        onChange={(e) => setAdHocDraft({ ...draft, sku: e.target.value })}
                        placeholder="Part number (optional)"
                        className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:ring-2 focus:ring-orange-500"
                      />
                      <input
                        value={draft.quantity}
                        inputMode="decimal"
                        onChange={(e) => setAdHocDraft({ ...draft, quantity: e.target.value })}
                        placeholder="Qty"
                        className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:ring-2 focus:ring-orange-500"
                      />
                      <input
                        value={draft.cost}
                        inputMode="decimal"
                        onChange={(e) => setAdHocDraft({ ...draft, cost: e.target.value })}
                        placeholder="Unit cost"
                        className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:ring-2 focus:ring-orange-500"
                      />
                      <input
                        value={draft.price}
                        inputMode="decimal"
                        onChange={(e) => setAdHocDraft({ ...draft, price: e.target.value })}
                        placeholder="Selling price"
                        className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:ring-2 focus:ring-orange-500"
                      />
                    </div>
                    <p className="text-[11px] text-gray-500">Saved to the catalogue as a placeholder, so the next job can find it.</p>
                    <div className="flex items-center gap-2">
                      <button
                        type="submit"
                        disabled={!draft.name.trim() || !draft.price.trim() || addAdHocPart.isPending}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-orange-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
                      >
                        {addAdHocPart.isPending ? <Spinner size="xs" /> : null}
                        {addAdHocPart.isPending ? 'Adding…' : 'Add to order'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setAdHocDraft(null)}
                        className="rounded-lg px-2 py-2 text-sm font-semibold text-gray-500 hover:text-gray-700"
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
    )
  }

  const addPart = useMutation({
    mutationFn: async ({
      inventoryId,
      quantity,
      sourceServiceId,
      sourceLineId,
      allowStockShortage = false,
    }: PartAddRequest) => {
      const body = { client_key: partAddKey(inventoryId, sourceLineId), inventory_id: inventoryId, quantity, source_service_id: sourceServiceId || null, source_line_id: sourceLineId || null, allow_stock_shortage: allowStockShortage, pricing_intent: partsPricingMode === 'stock' ? 'stock' as const : 'default' as const }
      await pricingCommand.execute({ context: { kind: 'repair_order', repair_order_id: orderId }, plan: { kind: 'parts_add', lines: [{ client_key: partAddKey(inventoryId, sourceLineId), inventory_id: inventoryId, quantity: String(quantity), source_service_id: sourceServiceId || null, source_line_id: sourceLineId || null, pricing_intent: body.pricing_intent }] } }, async (confirmation, options) => (await api.post(`/repair-orders/${orderId}/parts`, { ...body, ...confirmation }, options)).data, body)
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
      if (err instanceof PricingCancelled) return
      const shortage = stockShortageFromError(err)
      if (shortage && shortage.inventoryId === variables.inventoryId) {
        pricingCommand.clearError()
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

  const applyOperationCandidate = async (candidate: RepairOperationCandidate, estimatedHours?: number | string): Promise<PriceBuildSummary> => {
    // Catalog search results attach the complete service, including its parts.
    // Keep this identical to flat-service previews and retain the labor-only adapter.
    if (candidate.operation_id.startsWith('service:')) {
      const serviceId = candidate.operation_id.slice('service:'.length)
      return pricingCommand.execute<PriceBuildSummary>({
        context: { kind: 'repair_order', repair_order_id: orderId },
        plan: { kind: 'service_apply', service_id: serviceId, quantity: '1' },
      }, async (confirmation, options) => (await api.post(`/repair-orders/${orderId}/price-build/flat-service`, {
        service_id: serviceId, quantity: 1, ...confirmation,
      }, options)).data)
    }
    return (await api.post(`/repair-orders/${orderId}/price-build/repair-ops/apply`, {
      operation_id: candidate.operation_id,
      name: candidate.name,
      description: candidate.description,
      estimated_hours: estimatedHours ?? candidate.estimated_hours,
      provider: candidate.provider,
      auto_recalc_enabled: true,
    })).data
  }

  const applyRepairOp = useMutation({
    mutationFn: async ({ candidate, estimatedHours }: { candidate: RepairOperationCandidate; estimatedHours?: string }) => {
      const hours = estimatedHours != null ? parseFloat(estimatedHours || '0') : parseFloat(candidate.estimated_hours || '0')
      if (estimatedHours != null && (!Number.isFinite(hours) || hours <= 0)) {
        throw new Error('Book time hours must be greater than 0')
      }
      return applyOperationCandidate(candidate, estimatedHours != null ? hours : undefined)
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
    onError: (err: unknown) => { if (!(err instanceof PricingCancelled)) toast.error(errorDetail(err, err instanceof Error ? err.message : 'Unable to apply operation')) },
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
      await applyOperationCandidate(candidate)
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
      await applyOperationCandidate(candidate)
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

  // Removing a line does not remove the parts an operator added to it: those
  // are kept on the order as standalone parts, and only a Service's own
  // bundled parts go with it. That is deliberate — a tech's parts should not
  // vanish with a labor line — but silently moving them left the operator to
  // discover them loose later, so say what happened.
  const removeLine = useMutation({
    mutationFn: async ({ lineId }: { lineId: string; keptParts: number }) => {
      await api.delete(`/repair-orders/${orderId}/price-build/lines/${lineId}`)
    },
    onSuccess: async (_data, variables) => {
      await invalidate()
      toast.success(
        variables.keptParts
          ? `Service removed · ${variables.keptParts} part${variables.keptParts === 1 ? '' : 's'} kept on this order`
          : 'Line removed',
      )
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

  const compactWorkspace = useCompactWorkspace()
  const pricingControls = (
        <details key={orderId} className="db-workspace-pricing">
          <summary className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-gray-200 px-2 py-1.5 text-xs font-semibold">Pricing <ChevronUp className="h-3.5 w-3.5" /></summary>
        <div ref={footerDetailsRef} className="relative mb-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => { setFooterDetailsOpen((open) => open === 'parts' ? null : 'parts'); setDiscountsOpen(false) }}
            className="db-summary-pill rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700 hover:bg-blue-100"
          >
            Parts {isInitialSummaryLoad || summaryLoadFailed ? '…' : money(summary?.parts_total)}
          </button>
          <button
            type="button"
            onClick={() => { setFooterDetailsOpen((open) => open === 'labor' ? null : 'labor'); setDiscountsOpen(false) }}
            className="db-summary-pill rounded-full bg-orange-50 px-3 py-1 text-xs font-bold text-orange-700 hover:bg-orange-100"
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
              className="db-summary-pill rounded-full bg-red-50 px-3 py-1 text-xs font-bold text-red-700 hover:bg-red-100"
            >
              Discounts -{isInitialSummaryLoad || summaryLoadFailed ? '…' : money(discountTotal)}
            </button>
          )}
          {(isInitialSummaryLoad || summaryLoadFailed || customerSavesTotal > 0.005) && (
            <button
              type="button"
              onClick={() => { setFooterDetailsOpen((open) => open === 'savings' ? null : 'savings'); setDiscountsOpen(false) }}
              className="db-summary-pill rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700 hover:bg-emerald-100"
            >
              Customer saves {isInitialSummaryLoad || summaryLoadFailed ? '…' : money(customerSavesTotal)}
            </button>
          )}
          {footerDetailsOpen && (
            <div className="absolute bottom-full left-0 z-20 mb-2 w-[min(380px,calc(100vw-40px))] rounded-[14px] border border-gray-200 bg-white p-4 shadow-[0_10px_30px_rgba(20,25,35,.10)]">
              {renderFooterDetails(footerDetailsOpen)}
            </div>
          )}
          {!hasInvoice && (
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
          )}
          {!hasInvoice && discountsOpen && (
            <div
              ref={discountsPopoverRef}
              className="absolute bottom-full right-0 mb-2 w-[320px] rounded-[14px] border border-gray-200 bg-white p-4 shadow-[0_10px_30px_rgba(20,25,35,.10)]"
            >
              <div className="mb-3 flex items-center justify-between">
                <p className="font-semibold text-gray-900">Discounts & pricing</p>
                <button type="button" aria-label="Close discounts and pricing" onClick={() => setDiscountsOpen(false)} className="rounded-md p-1 text-slate-600 hover:bg-gray-100">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <fieldset className="mb-3" disabled={discountsSaving}>
                <legend className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-600">Parts pricing</legend>
                <div className="grid grid-cols-2 gap-1 rounded-lg bg-gray-100 p-1">
                  {(['stock', 'list'] as const).map((mode) => (
                    <label
                      key={mode}
                      className="relative cursor-pointer"
                      onMouseDown={(event) => {
                        if (event.button !== 0 || discountsSaving) return
                        // Focus the radio before the label's default click forwards
                        // to it. Otherwise the focusable order panel briefly gains
                        // focus and dismisses this popover before selection occurs.
                        event.preventDefault()
                        event.currentTarget.querySelector('input')?.focus()
                      }}
                    >
                      <input
                        type="radio"
                        name={`parts-pricing-${orderId}`}
                        value={mode}
                        checked={draftPartsPricingMode === mode}
                        onChange={() => setDraftPartsPricingMode(mode)}
                        className="peer absolute inset-0 z-10 m-0 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
                      />
                      <span className="flex min-h-8 items-center justify-center rounded-md px-3 py-1.5 text-xs font-semibold text-slate-600 peer-checked:bg-white peer-checked:text-slate-950 peer-checked:shadow-sm peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-slate-500 peer-disabled:cursor-not-allowed peer-disabled:opacity-60 [@media(pointer:coarse)]:min-h-11">
                        {mode === 'stock' ? 'Stock price' : 'List price'}
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="mb-3 flex items-center justify-between gap-3 text-sm">
                <span className="font-medium text-gray-700">Labor discount</span>
                <span className="flex items-center gap-1.5">
                  <DiscountAmountInput
                    label="Labor discount"
                    value={laborDiscount}
                    onChange={setLaborDiscount}
                    disabled={discountsSaving}
                  />
                  <button
                    type="button"
                    onClick={() => setLaborDiscount('')}
                    disabled={!laborDiscount}
                    className="h-9 rounded-lg px-2 text-xs font-semibold text-slate-600 hover:bg-gray-100 hover:text-gray-900 disabled:text-slate-600 disabled:opacity-100"
                  >
                    Reset
                  </button>
                </span>
              </div>
              <div className="mb-3 flex items-center justify-between gap-3 text-sm">
                <span className="font-medium text-gray-700">Order discount</span>
                <span className="flex items-center gap-1.5">
                  <DiscountAmountInput
                    label="Order discount"
                    value={orderDiscount}
                    onChange={setOrderDiscount}
                    disabled={discountsSaving}
                  />
                  <button
                    type="button"
                    onClick={() => setOrderDiscount('')}
                    disabled={!orderDiscount}
                    className="h-9 rounded-lg px-2 text-xs font-semibold text-slate-600 hover:bg-gray-100 hover:text-gray-900 disabled:text-slate-600 disabled:opacity-100"
                  >
                    Reset
                  </button>
                </span>
              </div>
              <p className="mb-2 text-[11px] text-slate-500">Available discount: labor {money(maxLaborDiscount)} · order {money(maxOrderDiscount)}</p>
              {discountValidation && <p role="alert" className="mb-2 text-xs text-amber-800">{discountValidation}</p>}
              <div className="flex items-center justify-between border-t border-gray-100 pt-3">
                <span className="text-xs font-semibold text-emerald-700">Customer saves {draftCustomerSavesTotal.toLocaleString('en-US', { style: 'currency', currency: 'USD' })}</span>
                <button
                  type="button"
                  disabled={discountsSaving || !pricingAdjustmentsChanged || !!discountValidation}
                  onClick={async () => {
                    if (await savePricingAdjustments()) setDiscountsOpen(false)
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
        </details>
  )
  const operationProgress = <>
            {!isFinalizedOrder && operationExecution.allowed && (operationExecution.isError ? <span className="text-xs text-red-700">Operation status unverified</span> : operationExecution.data && operationExecution.data.summary.tracked > 0 ? (
              <button type="button" className="min-h-8 max-w-44 text-left text-xs font-medium text-slate-600 underline decoration-dotted underline-offset-2" onClick={() => {
                const next = operationExecution.data.items.find(item => item.status === 'pending') || operationExecution.data.items[0]
                if (next) openLinkedOperation(next.labor_id)
              }}>{operationExecution.data.summary.remaining > 0 ? `${operationExecution.data.summary.remaining} operation${operationExecution.data.summary.remaining === 1 ? '' : 's'} remaining` : `Operations ${operationExecution.data.summary.completed}/${operationExecution.data.summary.tracked} complete`}</button>
            ) : null)}
  </>
  const invoiceSecondaryActions = <>
                  <button
                    type="button"
                    onClick={() => onResendInvoice?.()}
                    disabled={invoiceActionPending || !onResendInvoice}
                    className="db-stage-action db-stage-action--secondary"
                    aria-label={invoiceFinanciallyPaid ? 'Resend copy' : 'Resend invoice'}
                  >
                    <Mail className="h-4 w-4 shrink-0" />
                    <span>{invoiceFinanciallyPaid ? 'Resend copy' : 'Resend invoice'}</span>
                  </button>
                  {!invoiceFinanciallyPaid && !invoice?.pending_zelle_confirmation && onVoidInvoice && (
                    <button
                      type="button"
                      onClick={onVoidInvoice}
                      disabled={invoiceActionPending}
                      className="db-stage-action db-stage-action--secondary"
                      title="Preserve this invoice as voided and reopen the order for revision"
                      aria-label="Void & revise"
                    >
                      <RotateCcw className="h-4 w-4 shrink-0" />
                      <span>Void &amp; revise</span>
                    </button>
                  )}
  </>
  const technicianActions = <>
            {canEdit && !isDeleted && canManageTechnician && onAssignTechnician && availableTechnicians.length > 0
              && (hasAssignedTechnician || orderStatus === 'in_progress') && (
              <StartWorkAction
                key={`technician-${orderId}`}
                mode={hasAssignedTechnician ? 'reassign' : 'assign'}
                compact={canManageHold && !compactWorkspace}
                technicians={availableTechnicians}
                onAssign={onAssignTechnician}
                assignmentPending={technicianAssignmentPending}
                startPending={false}
              />
            )}
  </>
  const customerIdentity = <>
              {onOpenCustomer ? (
                <button
                  type="button"
                  onClick={onOpenCustomer}
                  title={`Open ${customerName || 'customer'}`}
                  className="db-order-customer-pill inline-flex items-center gap-1 rounded-full bg-white/14 px-3 py-1.5 text-white ring-1 ring-white/20 transition-colors hover:bg-white/24"
                >
                  <Building2 className="h-3.5 w-3.5" />
                  {customerName || 'Customer'}
                  {isFleetMember && <Star className="h-3.5 w-3.5 flex-none fill-current text-amber-300" aria-label="Fleet member" />}
                </button>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full bg-white/14 px-3 py-1.5 text-white ring-1 ring-white/20">
                  <Building2 className="h-3.5 w-3.5" />
                  {customerName || 'Customer'}
                  {isFleetMember && <Star className="h-3.5 w-3.5 flex-none fill-current text-amber-300" aria-label="Fleet member" />}
                </span>
              )}
  </>
  const orderNavigation = <>
            <button type="button" onClick={onToggleDangerActions} aria-expanded={showDangerActions} aria-label="Order actions" title="Order actions" className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-white/14 text-white ring-1 ring-white/20">⋯</button>
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
  </>

  return (
    <div className="db-price-builder relative flex h-full min-h-full flex-col overflow-hidden bg-white">
      {pricingCommand.dialog}
      {adHocPricing.dialog}
      <div
        className="db-workspace-header px-5 py-4 text-white"
        style={{
          background: isInternalOrder
            ? 'linear-gradient(100deg,#1e3a8a,#0f172a)'
            : 'linear-gradient(100deg,#9a4416,#75340f)',
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <Popover key={`vehicle-${orderId}`} className="db-job-identity">
              {({ open, close }) => <>
                <h2 className="db-job-title">
                  <PopoverButton title="Customer and vehicle details" className="db-job-vehicle">
                    <Truck className="h-5 w-5 shrink-0" />
                    <span>{[vehicleUnit, vehicleLabel].filter(Boolean).join(' · ') || 'Truck'}</span>
                    <ChevronDown className={`h-4 w-4 shrink-0 ${open ? 'rotate-180' : ''}`} />
                  </PopoverButton>
                </h2>
                <PopoverPanel anchor="bottom start" focus aria-label="Truck and customer details" className="db-job-details z-[100] w-[min(560px,calc(100vw-32px))] max-h-[min(480px,calc(100dvh-100px))] overflow-y-auto rounded-xl bg-white p-4 text-gray-900 shadow-lg ring-1 ring-gray-200 [--anchor-gap:8px] [--anchor-padding:16px]">
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <h3 tabIndex={0} data-autofocus className="font-semibold outline-none">Truck and customer</h3>
                    <button type="button" onClick={() => close()} aria-label="Close truck and customer details" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg hover:bg-gray-100"><X className="h-4 w-4" /></button>
                  </div>
                  <div className="grid gap-3 text-sm sm:grid-cols-2">
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
                    <OrderIntakeDetails key={orderId} mileageIn={mileageIn} mileageOut={mileageOut} mileageInCarried={mileageInCarried} poNumber={poNumber} orderTypeLabel={orderTypeLabel} canEdit={canMutate && !isDeleted && !['completed', 'invoiced', 'paid', 'cancelled'].includes(orderStatus)} onSave={onSaveIntake} />
                  </div>
                  {onOpenVehicleHistory && !isDeleted && <button type="button" className="mt-3 inline-flex min-h-11 items-center gap-2 whitespace-nowrap rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700 hover:bg-slate-50" onClick={() => { close(); onOpenVehicleHistory() }}><History className="h-4 w-4" aria-hidden="true" />View vehicle history</button>}
                </PopoverPanel>
              </>}
            </Popover>
            <div className="db-job-reference">
              <OrderNumberHeader value={`#${orderNumber || orderId.slice(0, 8)}`} />
              <span className="db-job-stage">{isDeleted ? 'Deleted' : isOnHold ? 'On hold' : orderStatus.replace(/_/g, ' ')}</span>
              {/* The company is the way into the customer's record — from here you
                  can see their other trucks and what they owe without hunting for
                  them in the ledger. The star marks a fleet-plan carrier, which is
                  a different question from whose truck this is: the shop's own
                  fleet is isInternalOrder, and a paying carrier can be on a fleet
                  plan too. */}
              {!isDeleted && <RepairOrderScheduleControl key={orderId} orderId={orderId} schedule={schedule} onUpdated={onUpdated} />}
              {!compactWorkspace && customerIdentity}
              {isInternalOrder && (
                <span className="inline-flex items-center gap-1 rounded-full bg-white/24 px-2.5 py-1.5 text-[11px] uppercase tracking-[0.08em] text-white ring-1 ring-white/30">
                  <Truck className="h-3.5 w-3.5" />
                  Shop fleet
                </span>
              )}

            </div>
            {quoteNumber && (
              <p className="mt-1 truncate font-['JetBrains_Mono',monospace] text-[11px] font-semibold text-white/70">
                {quoteNumber}
              </p>
            )}
          </div>
          <div className="db-job-navigation flex flex-wrap items-center justify-end gap-2">
            {!compactWorkspace && orderNavigation}
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

      </div>

      <div className="db-workspace-scroll">
      {workspaceNotice}
      {compactWorkspace && <div className="db-job-customer-mobile">{customerIdentity}</div>}
      {isOnHold && <p role="status" className="break-words border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-[#78350f]"><strong>On hold</strong> · {holdLabel}</p>}
      {/* Operational workflow is primary. Estimates are optional authorization
          records and appear as a secondary action, never as a work gate. */}
      {!isInternalOrder && !isDeleted && (
        <>
        <div className="db-job-workflow flex items-center border-b border-gray-100 bg-white px-5 py-1.5 text-xs">
          <WorkflowInfoGroup className="db-job-stages flex w-full min-w-0 flex-wrap items-center gap-2">
            <WorkflowInfoStep key={`intake-${orderId}`} stage="intake" label={orderStatus === 'draft' ? 'Checked in' : '✓ Checked in'} className={orderStatus === 'draft' ? 'bg-orange-500 text-white' : 'bg-emerald-100 text-emerald-700'} info={workflowInfo} status={orderStatus} description={description} mileage={mileageIn} />
            <span className="text-gray-300" aria-hidden="true">→</span>
            <WorkflowInfoStep key={`tech-${orderId}`} stage="technician" label={hasAssignedTechnician ? assignedTechnicianName || 'Technician assigned' : technicianAssignmentBypassed ? 'Shop-managed · no technician' : 'No technician assigned'} className={hasAssignedTechnician || technicianAssignmentBypassed ? 'bg-emerald-100 text-emerald-700' : 'text-gray-500'} info={workflowInfo} status={orderStatus} technician={assignedTechnicianName} />
            <span className="text-gray-300" aria-hidden="true">→</span>
            <WorkflowInfoStep key={`bay-${orderId}`} stage="bay" label={isOnHold ? 'On hold' : ['pending_review', 'completed', 'invoiced', 'paid'].includes(orderStatus) ? '✓ Work complete' : 'In the bay'} className={isOnHold ? 'bg-amber-100 text-amber-800' : ['in_progress', 'pending_review', 'completed', 'invoiced', 'paid'].includes(orderStatus) ? 'bg-emerald-100 text-emerald-700' : 'text-gray-500'} info={workflowInfo} status={orderStatus} operationCount={summary?.lines.length} />
            <span className="text-gray-300" aria-hidden="true">→</span>
            <WorkflowInfoStep key={`review-${orderId}`} stage="review" label="Quality review" className={orderStatus === 'pending_review' ? 'bg-orange-500 text-white' : ['completed', 'invoiced', 'paid'].includes(orderStatus) ? 'bg-emerald-100 text-emerald-700' : 'text-gray-500'} info={workflowInfo} status={orderStatus} reviewDraft={reviewNotesValue} />
            {onQuoteAction && canMutate && (
              <button
                ref={desktopQuoteActionRef}
                type="button"
                onClick={handleQuoteActionClick}
                data-authorization-quote-action="true"
                disabled={quoteActionBlocked || quoteActionPending}
                title={quoteButtonDisabledReason}
                className={`ml-auto hidden h-8 items-center gap-1.5 rounded-lg border px-2.5 font-semibold transition-colors disabled:opacity-50 sm:inline-flex ${
                  quoteActionReadyToSend
                    ? 'border-emerald-600 bg-emerald-600 text-white shadow-sm hover:bg-emerald-700'
                    : 'border-amber-200 bg-white text-amber-800 hover:bg-amber-50'
                }`}
              >
                {quoteActionPending ? <Spinner size="xs" /> : <FileText className="h-3.5 w-3.5" />}
                {quoteActionPending ? 'Working…' : quoteActionLabel}
              </button>
            )}
          </WorkflowInfoGroup>
        </div>
        {onQuoteAction && canMutate && (
          <div className="border-b border-gray-100 bg-white px-5 pb-2 pt-0 sm:hidden">
            <button
              ref={mobileQuoteActionRef}
              type="button"
              onClick={handleQuoteActionClick}
              data-authorization-quote-action="true"
              disabled={quoteActionBlocked || quoteActionPending}
              title={quoteButtonDisabledReason}
              className={`inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-xl border px-4 font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 focus-visible:ring-offset-2 disabled:opacity-50 ${
                quoteActionReadyToSend
                  ? 'border-emerald-600 bg-emerald-600 text-white shadow-sm hover:bg-emerald-700'
                  : 'border-amber-200 bg-white text-amber-800 hover:bg-amber-50'
              }`}
            >
              {quoteActionPending ? <Spinner size="xs" /> : <FileText className="h-4 w-4" />}
              {quoteActionPending ? 'Working…' : quoteActionLabel}
            </button>
          </div>
        )}
        </>
      )}

      <div className="db-workspace-body min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5 pb-4">
      {compactWorkspace && operationExecution.isError && operationProgress}

      {(onSaveDescription || (description && description.trim())) && (
        <div className="db-intake" data-editing={descriptionEditing}>
          <div className="db-intake-heading mb-1 flex items-center justify-between gap-2">
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Work Requested</p>
            {onSaveDescription && !isDeleted && !descriptionEditing && (
              <button
                type="button"
                onClick={() => { setDescriptionDraft(description || ''); setDescriptionEditing(true) }}
                aria-label={description && description.trim() ? 'Edit work requested' : 'Add work requested'}
                className="db-inline-text-action inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs font-semibold text-orange-700 hover:bg-orange-50"
              >
                <Pencil className="h-3.5 w-3.5" />
                {description && description.trim() ? 'Edit' : 'Add'}
              </button>
            )}
          </div>
          {descriptionEditing ? (
            <div className="space-y-2">
              <textarea
                ref={descriptionRef}
                value={descriptionDraft}
                onChange={(e) => setDescriptionDraft(e.target.value)}
                rows={3}
                placeholder="What the customer asked for…"
                className="w-full resize-none rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-orange-200"
              />
              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => { setDescriptionEditing(false); setDescriptionDraft('') }}
                  className="db-inline-text-action rounded-lg px-3 py-1.5 text-xs font-semibold text-gray-500 hover:text-gray-700"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={descriptionSaving || descriptionDraft.trim() === (description || '').trim()}
                  onClick={async () => {
                    await onSaveDescription?.(descriptionDraft.trim() || null)
                    setDescriptionEditing(false)
                  }}
                  className="db-inline-text-action rounded-lg bg-orange-600 px-3 py-1.5 text-xs font-bold text-white disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400"
                >
                  {descriptionSaving ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          ) : description && description.trim() ? (
            <div className="db-intake-description text-sm text-gray-800 whitespace-pre-wrap">
              {description}
            </div>
          ) : (
            <p className="db-intake-description text-sm text-gray-400">No work requested recorded.</p>
          )}
        </div>
      )}

      {isDeleted ? (
        <section aria-label="Deleted repair order" className="rounded-xl border border-gray-200 bg-gray-50 p-4">
          <h3 className="font-semibold text-gray-900">This order is deleted.</h3>
          {deletedAt && <p className="mt-1 text-sm text-slate-600">
            {deletedByName ? `Deleted by ${deletedByName}` : 'Deleted'} on {format(new Date(deletedAt), 'MMM d, yyyy h:mm a')}.
          </p>}
          <p className="mt-2 text-sm text-slate-600">Restore the order to view its work, checklist, notes and history. All records are preserved.</p>
        </section>
      ) : <>
      <OrderChecklist orderId={orderId} orderStatus={orderStatus} refreshToken={summary} />

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
                  {invoiceSettlement
                    ? invoiceSettlement.state.replace(/_/g, ' ')
                    : orderStatus === 'paid'
                      ? 'Paid'
                      : invoice.pending_zelle_confirmation
                        ? 'Pending Zelle confirmation'
                        : 'Awaiting payment'}
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

          {!invoiceSettlement && invoice.pending_zelle_confirmation && (
            <div className="mt-3 rounded-xl border border-yellow-200 bg-yellow-50 px-3 py-2 text-sm text-yellow-900">
              Customer marked this invoice as paid via Zelle. Confirm receipt from the footer payment action.
            </div>
          )}

          {invoiceDetailsOpen && (
          <div className="mt-3 space-y-3 rounded-xl bg-white p-3 text-sm ring-1 ring-purple-100">
            {invoiceSettlement && (
              <SettlementSummaryCard summary={invoiceSettlement} tone="light" compact />
            )}
            <div className="space-y-2">
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
                {invoiceSettlement ? 'Remaining payable' : invoice.pending_zelle_confirmation ? 'Zelle total' : 'Invoice total'}
              </span>
              <span className="font-['Barlow_Condensed',sans-serif] text-2xl font-extrabold text-purple-950">{money(invoiceDisplayTotal)}</span>
            </div>
            </div>
            {!invoiceSettlement && invoice.payment && (
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

      {canAdminCompleteBypassedWork && armWoComplete && !isOnHold && (
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

      {isInternalOrder && armWoComplete && !completionMode && !isOnHold && (
        <div className="rounded-2xl border border-yellow-200 bg-yellow-50/70 p-4">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-yellow-100 text-yellow-700">
              <CheckCircle className="h-4 w-4" />
            </div>
            <div>
              <p className="font-semibold text-yellow-950">Finalize work order</p>
              <p className="text-sm text-yellow-700">Enter the truck's odometer, then finalize and send the invoice to the fleet billing contact.</p>
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
              {completeWorkOrderPending ? 'Finalizing…' : 'Finalize & Send Invoice'}
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
              <p className="text-sm text-orange-700">
                {isInternalOrder
                  ? 'Review the final work and approve to send the invoice to the fleet billing contact.'
                  : 'Review the final work and approve to send the invoice to the customer.'}
              </p>
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

      {/* Tools share one flat row; only the search field needs a boundary. */}
      <div className="db-workspace-add">
        <div className="db-workspace-tool-row flex flex-wrap items-center gap-3 border-b border-gray-200 pb-2">
          {/* Read-only orders only have History — the single tab switches to
              nothing, and on mobile it wraps above the panel wasting a row. Drop
              the tab strip entirely; the History panel below carries its own
              header. */}
          {!addBarReadOnly && (
          <div className="db-workspace-tool-tabs grid w-full grid-cols-4 shrink-0 gap-1 text-xs font-bold sm:w-auto">
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
                  setSearchTerm('')
                  setPaletteOpen(key !== 'history')
                  if (key === 'history') onHistoryOpen?.()
                }}
                aria-pressed={addType === key}
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
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
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
              className="db-workspace-search h-11 w-full rounded-lg border border-gray-100 bg-gray-50 pl-9 pr-10 text-sm text-slate-950 placeholder:text-slate-500 outline-none focus-visible:border-slate-400 focus-visible:ring-1 focus-visible:ring-slate-300"
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
          <RepairOrderActivity
            key={orderId}
            events={historyEvents}
            initiallyOpen={!addBarReadOnly}
            loading={historyLoading}
            error={historyError}
            onOpen={onHistoryOpen}
            onRetry={onHistoryRetry}
          />
        )}

        {paletteOpen && addType !== 'history' && (addType !== 'operation' || searchTerm.trim().length > 0) && (
          <div className={`db-workspace-picker mt-2 border-b border-gray-200 bg-white py-2 ${searchTerm.trim() ? 'max-h-64 overflow-y-auto' : ''}`}>
            <div className="mb-2 flex items-center justify-between border-b border-gray-100 px-2 pb-2">
              <span className="text-xs font-bold uppercase tracking-[0.16em] text-slate-600">
                {addType === 'operation' ? 'Repair operations & services' : addType === 'saved_labor' ? 'Labor book time' : searchTerm.trim() ? 'Parts' : 'Most used parts'}
              </span>
              <span className="font-['JetBrains_Mono',monospace] text-[11px] text-slate-600">↵ to add</span>
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
                  <p className="px-2 py-3 text-sm text-slate-600">
                    Start by typing an operation name. Saved operations reuse learned labor hours when available.
                  </p>
                )}
                {!searchOps.isPending && candidates.map((c, index) => {
                  const isAddNew = isNoMatchCandidate && candidates.length === 1
                  const isAddingThisOperation = isApplyingOperationCandidate(c)
                  return (
                    <div
                      key={c.operation_id}
                      className={`db-workspace-pick-row flex items-center justify-between gap-3 rounded-xl px-3 py-2.5 ${
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
                          className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-orange-600 text-white shadow-sm transition-colors hover:bg-orange-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600 disabled:bg-slate-300"
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
                {!laborBookEntriesFetching && laborBookEntries.length > 0 && (laborBookSearchTerm
                  ? laborBookEntries.slice(0, 8)
                  : [...laborBookEntries].sort((a, b) => b.usage_count - a.usage_count).slice(0, 3)
                ).map((entry, index) => {
                  const scope = laborBookTimeScope(entry)
                  const isAddingThisLaborBookEntry = isApplyingLaborBookEntry(entry)
                  return (
                    <div
                      key={entry.id}
                      className={`db-workspace-pick-row flex items-center justify-between gap-3 rounded-xl px-3 py-2.5 ${
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
                        className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-orange-600 text-white shadow-sm transition-colors hover:bg-orange-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600 disabled:bg-slate-300"
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
                        className={`db-workspace-pick-row rounded-xl px-3 py-2.5 ${
                          index === 0 ? 'bg-orange-50 shadow-[inset_3px_0_0_#ef8a12]' : 'hover:bg-gray-50'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-gray-900">{item.name}</p>
                            <p className="truncate font-['JetBrains_Mono',monospace] text-[11px] text-slate-600">
                              {item.sku} · {item.stock_quantity} in stock{unitAbbr ? ` (${unitAbbr})` : ''} · catalog estimate {money(item.selling_price)}
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
                              className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-orange-600 text-white shadow-sm transition-colors hover:bg-orange-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600 disabled:bg-slate-300"
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
                    const forThisOrder: NonNullable<typeof partSuggestions>['for_this_order'] = []
                    const mostUsed = (partSuggestions?.most_used || [])
                      .slice(0, 3)

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
                            <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-600">
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
                  if (adHocDraft) return renderAdHocForm(null)
                  return (
                    <>
                      <div className="px-2 py-3">
                        {!matches.length && <p className="text-sm text-gray-500">No parts match this search.</p>}
                        {canMutate && (
                          <button
                            type="button"
                            onClick={() => setAdHocDraft({ name: searchTerm.trim(), sku: '', price: '', cost: '', quantity: '1' })}
                            className="text-sm font-semibold text-orange-700 underline-offset-2 hover:underline"
                          >
                            Add &ldquo;{searchTerm.trim()}&rdquo; as a new part
                          </button>
                        )}
                      </div>
                      {matches.map((item, index) => renderItemRow(item, index))}
                    </>
                  )
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

        const renderPartsRows = (parts: typeof allParts) => {
          const hasSavings = parts.some((part) => parseFloat(part.savings || '0') > 0)
          return (
          <div className="db-parts-table overflow-x-auto">
            <table role="table" aria-label="Parts" className="w-full text-sm">
              <thead role="rowgroup">
                <tr role="row" className="text-left text-[11px] text-slate-600 border-b border-gray-200">
                  <th role="columnheader" scope="col" className="py-1.5 px-2.5 font-medium">Part</th>
                  <th role="columnheader" scope="col" className="py-1.5 px-2.5 font-medium text-right">Qty</th>
                  <th role="columnheader" scope="col" className="py-1.5 px-2.5 font-medium text-right">Unit price</th>
                  {hasSavings && <th role="columnheader" scope="col" className="py-1.5 px-2.5 font-medium text-right">Savings</th>}
                  <th role="columnheader" scope="col" className="py-1.5 px-2.5 font-medium text-right">Line total</th>
                </tr>
              </thead>
              <tbody role="rowgroup">
                {parts.map((pu) => {
                  const shortageKey = partQuantityKey(pu.id)
                  const shortage = stockShortages[shortageKey]
                  const quantityOverride = partQuantityOverrides[shortageKey]
                  const retryQuantity = quantityOverride ?? (shortage ? Number(shortage.requestedQuantity) : parseFloat(pu.quantity) || 0)
                  const quantityUpdatePending = partQuantitySavingKey === shortageKey
                  return (
                    <tr role="row" key={pu.id} className="border-b border-gray-100 last:border-0">
                      <td role="cell" className="db-part-name py-1.5 px-2.5 text-gray-800">
                        <div className="font-medium">{pu.inventory_name}</div>
                        <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-600">
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
                      <td role="cell" className="db-part-qty py-1.5 px-2.5 text-right text-gray-800">
                        <span aria-hidden="true" className="db-part-mobile-label">Qty</span>
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
                      <td role="cell" className="db-part-unit-price py-1.5 px-2.5 text-right text-gray-600">
                        <span aria-hidden="true" className="db-part-mobile-label">Unit price</span>
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
                                    await api.patch(`/repair-orders/${orderId}/parts/${pu.id}`, { ...next, expected_pricing_version: pu.pricing?.pricing_version })
                                    await invalidate()
                                    toast.success(`${pu.inventory_name} price updated`)
                                  } catch (err: unknown) {
                                    await invalidate()
                                    throw err
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
                        {pu.pricing && <span className="db-parts-pricing__source ml-1">{priceSourceLabel(pu.pricing.current_source, pu.pricing.policy_source)}</span>}
                      </td>
                      {hasSavings && <td role="cell" className="db-part-savings py-1.5 px-2.5 text-right">
                        <span aria-hidden="true" className="db-part-mobile-label">Savings</span>
                        {parseFloat(pu.savings || '0') > 0 ? (
                          <span className="text-emerald-600 font-medium">
                            −${parseFloat(pu.savings).toFixed(2)}
                          </span>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>}
                      <td role="cell" className="db-part-total py-1.5 px-2.5 text-right text-gray-900 font-medium"><span aria-hidden="true" className="db-part-mobile-label">Line total</span>${parseFloat(pu.total_price).toFixed(2)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          )
        }

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
            <div className="db-op-part-panel rounded-xl border border-dashed border-orange-300 bg-orange-50/60 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-orange-700">
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  Add part to this operation
                </span>
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
                  placeholder="Search parts, or type a name to add a new one"
                  className="h-10 w-full rounded-lg border border-orange-200 bg-white pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-orange-200"
                />
              </div>
              {!hasSearchTerm ? (
                (
                  operationSuggestions.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5 px-1 pb-1">
                      {operationSuggestions.map((suggestion) => (
                        <button
                          key={suggestion.inventory_id}
                          type="button"
                          disabled={!canMutate || addPart.isPending}
                          onClick={() => addPart.mutate({
                            inventoryId: suggestion.inventory_id,
                            quantity: 1,
                            sourceLineId: operationPartPickerLineId,
                            quantityKey: `op:${suggestion.inventory_id}`,
                          })}
                          className="db-inline-text-action inline-flex items-center gap-1 rounded-full border border-orange-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-gray-700 hover:border-orange-400 disabled:opacity-50"
                        >
                          <Plus className="h-3 w-3 text-orange-600" aria-hidden="true" />
                          {suggestion.name}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="px-1 pb-1 text-xs text-gray-500">Search by name or part number.</p>
                  )
                )
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
              ) : adHocDraft ? renderAdHocForm(operationPartPickerLineId) : (
                <div className="space-y-1">
                  <div className="px-1 py-2">
                    {!matches.length && <p className="text-sm text-gray-500">No parts match this search.</p>}
                    {canMutate && (
                      <button
                        type="button"
                        onClick={() => setAdHocDraft({ name: (operationPartSearchByLineId[line.id] || '').trim(), sku: '', price: '', cost: '', quantity: '1' })}
                        className="db-inline-text-action text-sm font-semibold text-orange-700 underline-offset-2 hover:underline"
                      >
                        Add &ldquo;{(operationPartSearchByLineId[line.id] || '').trim()}&rdquo; as a new part
                      </button>
                    )}
                  </div>
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
                              {item.sku} · {item.stock_quantity} in stock ({unitAbbr}) · catalog estimate {money(item.selling_price)}
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
                              className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-orange-600 text-white shadow-sm transition-colors hover:bg-orange-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-600 disabled:bg-slate-300"
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

        if (isLoading) {
          // Skeleton that mirrors the Services & Parts list, so a slow fetch (prod)
          // reads as "loading" in the open drawer rather than an empty panel.
          return (
            <div className="animate-pulse">
              <div className="mb-1 flex items-center justify-between">
                <span className="inline-flex items-center gap-2">
                  <div className="h-3 w-24 rounded bg-gray-200" />
                  <div className="h-4 w-12 rounded-full bg-gray-100" />
                </span>
              </div>
              <div className="db-service-list divide-y divide-gray-100 border-y border-gray-100">
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
            <div className="py-2 text-sm text-gray-500">
              <p>Add an operation, labor or part to begin.</p>
            </div>
          )
        }

        return (
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="inline-flex items-center gap-2">
                <p className="font-['Barlow_Condensed',sans-serif] text-sm font-extrabold uppercase tracking-[0.16em] text-slate-700">Services & Parts</p>
                <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-bold text-slate-600">{lines.length + (orphanParts.length ? 1 : 0)} lines</span>
              </span>
              <SectionInfoTooltip text="Each card is one billable item. Service packages bundle labor with their required parts — edit hours, rate, or part quantity inline. Stock adjusts automatically." tooltipClassName="w-72" />
            </div>
            <OperationExecutionFeedback query={operationExecution} />
            <div className="db-service-list divide-y divide-gray-100 border-y border-gray-100">
              {lines.map((line) => {
                const groupedParts = groupedPartsForLine(line)
                const isOpen = openLineIds.has(line.id)
                const execution = operationExecution.data?.items.find(item => item.labor_id === line.id)
                const isAddingPartHere = isAddingPartToLine(line.id)
                const warningsForLine = lineWarnings[line.id] || []
                const partTotal = groupedParts.reduce((sum, part) => sum + (parseFloat(part.total_price || '0') || 0), 0)
                const partSavings = groupedParts.reduce((sum, part) => sum + (parseFloat(part.savings || '0') || 0), 0)
                const lineTotal = (parseFloat(line.total_cost || '0') || 0) + partTotal
                const Icon = line.source_service_id ? Wrench : line.line_type === 'flat_service' ? Gauge : Tag
                return (
                  <div key={line.id} className="py-1">
                    <button
                      id={`operation-trigger-${line.id}`}
                      type="button"
                      onClick={() => toggleLine(line.id)}
                      aria-expanded={isOpen}
                      aria-controls={`service-line-${line.id}`}
                      className="db-workspace-line-trigger grid w-full grid-cols-[auto_auto_1fr_auto] items-center gap-3 rounded-xl px-2 py-2 text-left hover:bg-gray-50"
                    >
                      <ChevronRight className={`h-4 w-4 text-gray-400 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                      <span className={`inline-flex h-9 w-9 items-center justify-center rounded-lg ${
                        line.source_service_id ? 'bg-orange-50 text-orange-700' : 'bg-blue-50 text-blue-700'
                      }`}>
                        <Icon className="h-4 w-4" />
                      </span>
                      <span className="db-service-label min-w-0">
                        <span className="flex min-w-0 flex-wrap items-center gap-2">
                          <span className="truncate font-semibold text-gray-900">{line.description || lineTypeLabel(line)}</span>
                          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-600">{lineTypeLabel(line)}</span>
                        </span>
                        <span className="db-service-execution-meta mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-600">
                          <span className="min-w-0">{formatHoursMinutes(line.hours)} booked{groupedParts.length > 0 ? ` · ${groupedParts.length} parts` : ''}{partSavings > 0 ? ` · saves ${money(partSavings)}` : ''}</span>
                          {execution && <OperationExecutionStatus item={execution} />}
                        </span>
                      </span>
                      <span className="text-right">
                        <span className="db-service-total block text-base font-bold tabular-nums text-gray-900">{money(lineTotal)}</span>
                        <span className="db-service-breakdown block text-[11px] text-slate-600">
                          {money(line.total_cost)} labor · {money(partTotal)} parts
                        </span>
                      </span>
                    </button>
                    {line.recommendation_source && <RecommendationSourceLink source={line.recommendation_source} currentDescription={line.description} />}
                    {isOpen && (
                      <div id={`service-line-${line.id}`} className="db-workspace-line-details ml-3 space-y-2 pb-2 pr-2">
                        {execution && <OperationExecutionControls key={`${orderId}:${line.id}`} orderId={orderId} item={execution} technicians={technicianOptions} disabled={operationExecution.isError || operationExecution.isFetching} onUpdated={onUpdated} /> }
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
                            <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-600">Labor</span>
                            {canMutate && (
                              <button
                                type="button"
                                onClick={() => removeLine.mutate({
                                  lineId: line.id,
                                  // Parts linked to the line survive it; a Service's
                                  // bundled parts go with it and are not counted.
                                  keptParts: (partsByLine.get(line.id) || []).length,
                                })}
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
                        {operationPartPickerLineId !== line.id && (
                          <button
                            type="button"
                            disabled={!canMutate || addPart.isPending}
                            onClick={() => setOperationPartPickerLineId(line.id)}
                            className="db-op-part-trigger inline-flex w-full items-center justify-center gap-1 rounded-xl border border-dashed border-gray-300 px-3 py-2.5 text-sm font-semibold text-gray-600 hover:border-orange-300 hover:text-orange-700 disabled:opacity-50"
                          >
                            {isAddingPartHere ? <Spinner size="xs" label="Adding part to this operation" /> : <Plus className="h-4 w-4" />}
                            {isAddingPartHere ? 'Adding part…' : 'Add part to this operation'}
                          </button>
                        )}
                        {renderOperationPartPicker(line, groupedParts)}
                      </div>
                    )}
                    <OperationNotes orderId={orderId} laborId={line.id} description={line.description || lineTypeLabel(line)} expanded={isOpen} orderStatus={orderStatus} assignmentId={execution?.mechanic_id} />
                  </div>
                )
              })}
              {orphanParts.length > 0 && (
                <div className="db-standalone-parts py-3">
                  <div className="db-standalone-heading mb-2 flex items-center gap-2 px-2">
                    <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
                      <Box className="h-4 w-4" />
                    </span>
                    <div>
                      <p className="font-semibold text-gray-900">Standalone parts</p>
                      <p className="text-xs text-gray-500">{orphanParts.length} parts · {money(orphanParts.reduce((sum, p) => sum + (parseFloat(p.total_price || '0') || 0), 0))}</p>
                    </div>
                  </div>
                  <div className="db-standalone-table">{renderPartsRows(orphanParts)}</div>
                </div>
              )}
              {isAddingStandalonePart && lines.length > 0 && (
                <div className="db-standalone-parts py-3">
                  <div className="db-standalone-heading mb-2 flex items-center gap-2 px-2">
                    <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
                      <Box className="h-4 w-4" />
                    </span>
                    <div>
                      <p className="font-semibold text-gray-900">Standalone parts</p>
                      <p className="text-xs text-gray-500">Adding a part…</p>
                    </div>
                  </div>
                  <div className="db-standalone-table"><PendingWorkRows message="Adding standalone part…" /></div>
                </div>
              )}
            </div>
          </div>
        )
      })()}

      <div className="db-workspace-secondary pb-2">

        {typeof recommendedWorkPanel === 'function' ? recommendedWorkPanel({
          canConvert: canMutate && !isDeleted && summary?.can_convert_recommendations === true,
          hourlyRate: summary?.recommendation_hourly_rate != null ? Number(summary.recommendation_hourly_rate) : undefined,
          rateReadOnly: isInternalOrder,
          onOpenOperation: openLinkedOperation,
        }) : recommendedWorkPanel}
        {showRecommendedServicesPanel && (
          <button
            type="button"
            onClick={() => toggleSecondaryPanel('recommended')}
            aria-expanded={recommendedOpen}
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
            {!recommendationsReadOnly && <button
              type="button"
              onClick={onToggleAddRecommendedService}
              className="mb-3 inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-bold text-orange-700 ring-1 ring-gray-200"
            >
              <Plus className="h-3.5 w-3.5" /> Add recommended service
            </button>}
            {!recommendationsReadOnly && showAddRecommendedService && recommendedServiceForm && onRecommendedServiceFormChange && (
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
                  <li key={svc.id} id={`recommendation-${svc.id}`} tabIndex={-1} className="flex flex-wrap items-start gap-3 p-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500">
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
                        {svc.is_resolved && <span className="db-recommendation-resolved rounded bg-emerald-50 px-1.5 py-0.5 text-xs font-medium">Resolved</span>}
                      </div>
                      <p className="mt-1 text-sm text-gray-800">{svc.description}</p>
                      {svc.conversion && <ConversionLink conversion={svc.conversion} contextOrderId={orderId} onOpenOperation={openLinkedOperation} />}
                    </div>
                    {!svc.is_resolved && (!recommendationsReadOnly || svc.conversion?.can_resolve) && (
                      <div className="flex shrink-0 gap-1">
                        <button
                          type="button"
                          onClick={() => onResolveRecommendedService?.(svc.id)}
                          disabled={resolveRecommendedPending || (!!svc.conversion && !svc.conversion.can_resolve)}
                          title={svc.conversion && !svc.conversion.can_resolve ? 'Complete the linked work before resolving this recommendation.' : undefined}
                          className="rounded-lg px-2 py-1 text-xs font-bold text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
                        >
                          Resolve
                        </button>
                        {!svc.conversion && <button
                          type="button"
                          onClick={() => onDeleteRecommendedService?.(svc.id)}
                          disabled={deleteRecommendedPending}
                          className="rounded-lg p-1.5 text-red-500 hover:bg-red-50 disabled:opacity-50"
                          aria-label="Delete recommended service"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>}
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

        {onAddNote && (
          <button
            type="button"
            onClick={() => toggleSecondaryPanel('notes')}
            aria-expanded={notesOpen}
            className="flex w-full items-center justify-between rounded-xl border-t border-gray-100 px-2 py-3 text-left hover:bg-gray-50"
          >
            <span className="inline-flex items-center gap-2 text-sm font-semibold text-gray-800">
              <StickyNote className="h-4 w-4 text-gray-400" />
              Notes
              {notes.length > 0 && (
                <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-600">{notes.length}</span>
              )}
            </span>
            <span className="inline-flex min-w-0 items-center gap-2">
              <span className="truncate px-3 text-right text-xs text-gray-500">
                {notes.length
                  ? `Last by ${notesNewestFirst[0].actor || 'Unknown'}`
                  : 'None yet'}
              </span>
              <ChevronRight className={`h-4 w-4 shrink-0 text-gray-400 transition-transform ${notesOpen ? 'rotate-90' : ''}`} />
            </span>
          </button>
        )}
        {onAddNote && notesOpen && (
          <div className="space-y-2 rounded-xl bg-gray-50 p-3">
            {notesNewestFirst.length > 0 && (
              <ul className="space-y-2">
                {notesNewestFirst.map((note) => (
                  <li key={note.id} className="db-order-note rounded-xl bg-white p-3 ring-1 ring-gray-200">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="min-w-0 truncate text-xs font-semibold text-gray-700">
                        {note.actor || 'Unknown'}
                        <span className="ml-2 font-normal text-gray-400">
                          {new Date(note.at).toLocaleString(undefined, {
                            month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
                          })}
                        </span>
                      </span>
                      <span className="inline-flex shrink-0 items-center gap-2">
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                          note.audience === 'customer' ? 'bg-orange-50 text-orange-700' : 'bg-gray-100 text-gray-500'
                        }`}>
                          {note.audience === 'customer' ? 'On invoice' : 'Shop only'}
                        </span>
                        {note.canDelete && onDeleteNote && (
                          <button
                            type="button"
                            onClick={() => onDeleteNote(note.id)}
                            aria-label="Delete this note"
                            className="db-notes-action rounded-md p-1 text-gray-300 transition-colors hover:bg-gray-100 hover:text-gray-600"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </span>
                    </div>
                    <p className="mt-1 whitespace-pre-wrap break-words text-sm text-gray-800">{note.body}</p>
                  </li>
                ))}
              </ul>
            )}

            {!noteComposerOpen ? (
              <button
                type="button"
                onClick={() => setNoteComposerOpen(true)}
                className="db-notes-action inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-bold text-orange-700 ring-1 ring-gray-200"
              >
                <Plus className="h-3.5 w-3.5" /> Add note
              </button>
            ) : (
              <div className="space-y-2 rounded-xl bg-white p-3 ring-1 ring-gray-200">
                <div className="inline-flex rounded-lg bg-gray-50 p-0.5 ring-1 ring-gray-200" role="tablist">
                  {([['shop', 'Shop only'], ['customer', 'On the invoice']] as const).map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      role="tab"
                      aria-selected={noteAudience === key}
                      onClick={() => setNoteAudience(key)}
                      className={`db-notes-tab rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                        noteAudience === key ? 'bg-white text-orange-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <textarea
                  ref={noteInputRef}
                  value={noteDraft}
                  onChange={(e) => setNoteDraft(e.target.value)}
                  rows={3}
                  placeholder={noteAudience === 'customer'
                    ? 'Note the customer will see on the invoice…'
                    : 'Note for the shop — never shown to the customer…'}
                  className="w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-orange-200"
                />
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[11px] text-gray-500">
                    {noteAudience === 'customer' ? 'Appears on the invoice.' : 'Shop only — the customer never sees this.'}
                  </p>
                  <span className="inline-flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => { setNoteComposerOpen(false); setNoteDraft('') }}
                      className="db-notes-action rounded-lg px-3 py-1.5 text-xs font-semibold text-gray-500 hover:text-gray-700"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={!noteDraft.trim() || notesSaving}
                      onClick={async () => {
                        const body = noteDraft.trim()
                        if (!body) return
                        await onAddNote({ body, audience: noteAudience })
                        setNoteDraft('')
                        setNoteComposerOpen(false)
                      }}
                      className="db-notes-action rounded-lg bg-orange-600 px-3 py-1.5 text-xs font-bold text-white disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400"
                    >
                      {notesSaving ? 'Posting…' : 'Post note'}
                    </button>
                  </span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Repair photos sit in the body (near Customer & Vehicle), above the
            Order Total footer. Adding is only allowed while the order is open;
            on a finalized order with no photos there's nothing to show, so the
            whole section is hidden. */}
        {!isDeleted && (!isFinalized || (repairPhotosData !== undefined && repairPhotos.length > 0)) && (
          <div className="db-workspace-photos">
            <button
              type="button"
              onClick={() => toggleSecondaryPanel('photos')}
              className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap text-left"
              aria-expanded={photosOpen}
            >
              <span className="min-w-0">
                <span className="inline-flex items-center gap-2 text-sm font-semibold text-gray-800">
                  <Camera className="h-4 w-4" />
                  <span>
                    Photos{repairPhotosData !== undefined && (
                      <span
                        aria-hidden="true"
                        className={`ml-1 inline-flex items-center justify-center align-baseline normal-nums ${repairPhotos.length > 0 ? 'h-5 min-w-5 rounded-full bg-emerald-50 px-1 text-center text-emerald-700 ring-1 ring-inset ring-emerald-300' : ''}`}
                      >{repairPhotos.length}</span>
                    )}
                  </span>
                </span>
                <span className="sr-only">
                  {repairPhotosData === undefined
                    ? 'Open to view repair photos'
                    : repairPhotos.length
                      ? `${repairPhotos.length} photo${repairPhotos.length === 1 ? '' : 's'} attached`
                      : 'No photos attached'}
                </span>
              </span>
              <span className="flex min-w-0 flex-1 items-center justify-end gap-2">
                {isUploadingRepairPhotos && (
                  <span role="status" aria-label="Uploading photos" className="inline-flex h-4 w-4 shrink-0 items-center justify-center">
                    <Spinner size="xs" />
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
      </>}
      </div>
      </div>

      <div className="db-workspace-footer z-10 border-t border-gray-200 bg-white/95 px-3 py-4 shadow-[0_-10px_30px_rgba(20,25,35,.08)] backdrop-blur sm:px-5">
        {isDeleted ? <div className="db-workspace-actions flex items-center justify-between gap-3">
          <span className="text-sm font-medium text-slate-600">Deleted order</span>
          {onRestoreOrder && <button type="button" onClick={onRestoreOrder} disabled={restorePending} className="db-stage-action db-stage-action--primary min-h-11">
            {restorePending ? <Spinner size="xs" /> : <RotateCcw className="h-4 w-4" />}
            {restorePending ? 'Restoring…' : 'Restore order'}
          </button>}
        </div> : <>
        {!compactWorkspace && pricingControls}
        <div className="db-workspace-actions flex flex-wrap items-center justify-between gap-3">
          <div className={hasInvoice
            ? 'flex w-full min-w-0 items-end justify-between gap-2'
            : 'ml-auto flex min-w-0 flex-wrap items-center justify-end gap-3'
          }>
            <div className={`db-workspace-total ${hasInvoice ? 'shrink-0 text-left' : 'text-right'}`}>
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
                className={`price-total-amount font-['Barlow_Condensed',sans-serif] text-[30px] font-extrabold leading-none text-gray-950 sm:text-[34px] ${
                  totalJustChanged ? 'price-total-amount--changed' : totalMotionActive ? 'price-total-amount--updating' : ''
                }`}
              >
                {isInitialSummaryLoad || summaryLoadFailed ? '…' : money(orderTotalValue)}
              </p>
            </div>
            {!compactWorkspace && operationProgress}
            {(!isInternalOrder || hasInvoice || completionMode) && (
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
                          <p className="font-semibold text-gray-950">Invoice recipient and due date</p>
                          <p className="text-xs text-gray-500">Choose which connected company receives this invoice.</p>
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
                        {invoiceRecipientOptions.length > 0 && (
                          <label className="block rounded-xl border border-gray-200 bg-gray-50 p-3 text-sm">
                            <span className="mb-1 block font-semibold text-gray-700">Invoice this visit to</span>
                            <select
                              value={invoiceRecipientId}
                              onChange={(e) => onInvoiceRecipientChange?.(e.target.value)}
                              className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-gray-900 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                            >
                              {invoiceRecipientOptions.map((recipient) => (
                                <option key={recipient.id} value={recipient.id}>{recipient.company_name} · {recipient.relationship_label}</option>
                              ))}
                            </select>
                          </label>
                        )}
                        <button
                          type="button"
                          onClick={() => onCreateInvoice?.(null, invoiceRecipientId || undefined)}
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
                          <DatePicker
                            surface="light"
                            label="Choose due date"
                            value={invoiceDueDateValue}
                            onChange={(day) => onInvoiceDueDateChange?.(day)}
                            min={new Date().toISOString().split('T')[0]}
                          />
                          <button
                            type="button"
                            onClick={() => onCreateInvoice?.(invoiceDueDateValue || null, invoiceRecipientId || undefined)}
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
                <div className="db-invoice-actions">
                  {!invoiceFinanciallyPaid && (
                    <button
                      type="button"
                      onClick={() => onRecordPayment?.()}
                      disabled={invoiceActionPending || !onRecordPayment}
                      className="db-stage-action db-stage-action--primary"
                      aria-label={invoice.pending_zelle_confirmation ? 'Confirm Zelle payment' : 'Record payment'}
                    >
                      <CreditCard className="h-4 w-4 shrink-0" />
                      <span>{invoice.pending_zelle_confirmation ? compactWorkspace ? 'Confirm Zelle' : 'Confirm Zelle payment' : 'Record payment'}</span>
                    </button>
                  )}
                  {!compactWorkspace ? invoiceSecondaryActions : invoiceFinanciallyPaid && (
                    <button type="button" onClick={() => onResendInvoice?.()} disabled={invoiceActionPending || !onResendInvoice} className="db-stage-action db-stage-action--primary"><Mail className="h-4 w-4 shrink-0" />Resend copy</button>
                  )}
                </div>
              ) : completionMode ? (
                <button
                  type="button"
                  onClick={onApproveCompletion}
                  aria-label="Finalize & Send Invoice"
                  disabled={completionPending || !onApproveCompletion}
                  className="inline-flex h-11 items-center gap-2 rounded-xl bg-green-600 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(22,163,74,.28)] hover:bg-green-700 disabled:bg-gray-300"
                >
                  {completionPending ? <Spinner size="xs" /> : <CheckCircle className="h-4 w-4" />}
                  {completionPending ? 'Finalizing...' : compactWorkspace ? 'Finalize' : 'Finalize & Send Invoice'}
                </button>
              ) : canEdit && !isDeleted && canManageTechnician && !hasAssignedTechnician
                && ['draft', 'quoted', 'declined', 'approved'].includes(orderStatus)
                && ((onAssignTechnician && availableTechnicians.length > 0) || canOverrideTechnicianAssignment) ? (
                <StartWorkAction
                  key={orderId}
                  technicians={availableTechnicians}
                  onAssign={onAssignTechnician}
                  onStartWithoutTechnician={canOverrideTechnicianAssignment ? onOverrideTechnicianAssignment : undefined}
                  assignmentPending={technicianAssignmentPending}
                  startPending={technicianOverridePending}
                />
              ) : canManageHold ? null : (
                <span className="db-workspace-stage-caption max-w-64 text-right text-sm font-medium text-gray-600" role="status">
                  {hasAssignedTechnician && ['draft', 'quoted', 'declined', 'approved', 'assigned', 'acknowledged'].includes(orderStatus)
                    ? `Waiting for ${assignedTechnicianName} to start`
                    : isOnHold ? `On hold · ${holdLabel}`
                    : orderStatus === 'in_progress' ? 'Work in progress'
                    : orderStatus === 'pending_review' ? 'Awaiting quality review'
                    : orderStatus === 'completed' ? 'Work complete'
                    : orderStatus === 'invoiced' ? 'Invoiced'
                    : orderStatus === 'paid' ? 'Paid'
                    : orderStatus === 'cancelled' ? 'Cancelled'
                    : orderStatus === 'draft' ? 'Checked in · work order open' : 'Work order open'}
                </span>
              )
            )}
            {(!compactWorkspace || isOnHold) && holdAction()}
            {!compactWorkspace && technicianActions}
            {canAdminCompleteBypassedWork && !isDeleted && !isOnHold && !armWoComplete && (
              <button
                type="button"
                onClick={() => setArmWoComplete(true)}
                className="inline-flex h-11 items-center gap-2 rounded-xl bg-yellow-500 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(234,179,8,.28)] hover:bg-yellow-600"
              >
                <CheckCircle className="h-4 w-4" />
                {compactWorkspace ? 'Complete' : 'Mark Completed'}
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
              ) : orderStatus === 'in_progress' && !isOnHold && !armWoComplete ? (
                <button
                  type="button"
                  onClick={() => { setWoMileageOut(mileageIn != null ? String(mileageIn) : ''); setArmWoComplete(true) }}
                  className="inline-flex h-11 items-center gap-2 rounded-xl bg-yellow-500 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(234,179,8,.28)] hover:bg-yellow-600"
                >
                  <CheckCircle className="h-4 w-4" />
                  {compactWorkspace ? 'Finalize' : 'Finalize & Invoice'}
                </button>
              ) : orderStatus === 'completed' ? (
                <span className="db-internal-complete-state inline-flex items-center gap-3">
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
          {compactWorkspace && <WorkspaceActionOverflow label="Repair order actions">{close => <>
            <div className="db-workspace-order-navigation" onClick={() => close()}>{orderNavigation}</div>
            {!isOnHold && holdAction(close)}
            {!operationExecution.isError && operationProgress}
            {technicianActions}
            {hasInvoice && invoice && !invoiceFinanciallyPaid && <div className="db-workspace-secondary-actions" onClick={() => close()}>{invoiceSecondaryActions}</div>}
            {pricingControls}
          </>}</WorkspaceActionOverflow>}
        </div>
        </>}
      </div>

      {holdDialogOrderId === orderId && workHoldOrder && <StaffHoldDialog key={orderId} order={workHoldOrder} onClose={() => setHoldDialogOrderId(null)} onUpdated={onUpdated} />}

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
                    disabled={restorePending || !onRestoreOrder}
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

                  {canForceVoid && onForceVoidOrder && (
                    <div className="mt-5 border-t border-red-100 pt-4">
                      <p className="text-sm text-red-700">
                        This order is invoiced or paid, so deleting it is blocked — it counts as a
                        financial record. Voiding keeps the record and marks it void, with your
                        reason attached.
                      </p>
                      {!forceVoidOpen ? (
                        <button
                          type="button"
                          onClick={() => setForceVoidOpen(true)}
                          className="mt-3 w-full rounded-lg border border-red-300 px-4 py-2.5 text-sm font-semibold text-red-700 hover:bg-red-50"
                        >
                          Void this order…
                        </button>
                      ) : (
                        <div className="mt-3 space-y-2">
                          <textarea
                            value={forceVoidReason}
                            onChange={(e) => setForceVoidReason(e.target.value)}
                            rows={2}
                            placeholder="Why is this being voided? (recorded)"
                            className="w-full resize-none rounded-lg border border-red-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-red-200"
                          />
                          <input
                            type="password"
                            value={forceVoidPassword}
                            onChange={(e) => setForceVoidPassword(e.target.value)}
                            placeholder="Your password"
                            autoComplete="current-password"
                            className="w-full rounded-lg border border-red-200 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-red-200"
                          />
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => { setForceVoidOpen(false); setForceVoidReason(''); setForceVoidPassword('') }}
                              className="rounded-lg px-3 py-2 text-sm font-semibold text-gray-500 hover:text-gray-700"
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              disabled={forceVoidPending || forceVoidReason.trim().length < 3 || !forceVoidPassword}
                              onClick={async () => {
                                try {
                                  await onForceVoidOrder({
                                    reason: forceVoidReason.trim(),
                                    password: forceVoidPassword,
                                  })
                                  setForceVoidOpen(false)
                                  setForceVoidReason('')
                                } catch {
                                  // The parent reports the error; retain the reason for retry.
                                } finally {
                                  setForceVoidPassword('')
                                }
                              }}
                              className="flex-1 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                            >
                              {forceVoidPending ? 'Voiding…' : 'Void order'}
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
import { laborSourceLabel, type SafeLaborPricing } from '@/features/customer-pricing/contract'
