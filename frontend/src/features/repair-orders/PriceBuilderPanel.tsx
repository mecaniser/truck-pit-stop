import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import {
  AlertTriangle,
  Box,
  Building2,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  CreditCard,
  FileText,
  Gauge,
  History,
  Loader2,
  Mail,
  Plane,
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
import QuantityStepper from '@/components/QuantityStepper'
import DurationStepper from '@/components/DurationStepper'
import { formatHoursMinutes } from '@/lib/durationFormat'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'
import {
  PartsUsage,
  PartSuggestionsResponse,
  PriceBuildSummary,
  InventoryItem,
  Invoice,
  RecommendedService,
  RecommendedServicePriority,
  RepairOperationCandidate,
  RepairOrderStatus,
} from '@/types'

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
  onDeleteInvoice?: () => void
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
  onUpdated?: () => void
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
  part, disabled, onChangeQty, onDelete,
}: {
  part: PartsUsage
  disabled?: boolean
  onChangeQty: (next: number) => Promise<void>
  onDelete: () => Promise<void>
}) {
  const isFluid = part.unit_type && part.unit_type !== 'each'
  const step = isFluid ? 0.25 : 1
  const unitAbbr = UNIT_ABBR[part.unit_type] || ''
  const currentQuantity = parseFloat(part.quantity) || 0

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

  return (
    <>
      <div className="mb-2 flex items-center gap-1.5">
        <input
          defaultValue={line.description}
          onBlur={(e) => {
            const value = e.target.value.trim()
            if (value !== line.description) onUpdate({ description: value })
          }}
          disabled={!canMutate}
          className="flex-1 rounded-md border border-gray-300 px-2 py-1.5 text-sm disabled:bg-gray-100"
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
            disabled={!canMutate}
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
            disabled={!canMutate}
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
  quoteIsSent = false,
  quoteIsApproved = false,
  quoteActionLabel = 'Send quote',
  quoteActionPending = false,
  quoteActionDisabled = false,
  quoteDisabledReason,
  onQuoteAction,
  assignedTechnicianName,
  assignedTechnicianId,
  technicianOptions = [],
  technicianAssignmentPending = false,
  onAssignTechnician,
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
  onDeleteInvoice,
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
  onUpdated,
}: Props) {
  const queryClient = useQueryClient()
  const [searchTerm, setSearchTerm] = useState('')
  const [candidates, setCandidates] = useState<RepairOperationCandidate[]>([])
  const [searchWarnings, setSearchWarnings] = useState<{ code: string; message: string }[]>([])
  const [addType, setAddType] = useState<AddBarType>(() => (
    ['draft', 'quoted'].includes(orderStatus) ? 'operation' : 'history'
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
  const [armWoComplete, setArmWoComplete] = useState(false)
  const [woMileageOut, setWoMileageOut] = useState('')
  const [partQuantitiesByItemId, setPartQuantitiesByItemId] = useState<Record<string, number>>({})
  const [operationPartPickerLineId, setOperationPartPickerLineId] = useState<string | null>(null)
  const [operationPartSearchByLineId, setOperationPartSearchByLineId] = useState<Record<string, string>>({})
  const [bookTimeHours, setBookTimeHours] = useState('1')
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
  const { data: summary, refetch, isLoading, isError: summaryErrored, isFetching: summaryFetching } = useQuery<PriceBuildSummary>({
    queryKey: ['price-build', orderId],
    queryFn: async () => {
      const response = await api.get(`/repair-orders/${orderId}/price-build`)
      return response.data
    },
    // A soft-deleted order's work/labor endpoints 404 (the order is hidden from
    // them), so don't fetch when deleted — the panel shows the Restore state.
    enabled: !!orderId && !isDeleted,
  })

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

  const { data: partsUsed, refetch: refetchParts, isFetching: partsFetching } = useQuery<PartsUsage[]>({
    queryKey: ['price-build-parts', orderId],
    queryFn: async () => {
      const response = await api.get(`/repair-orders/${orderId}/parts`)
      return response.data
    },
    enabled: !!orderId && !isDeleted,
  })

  const { data: inventory, isFetching: inventoryFetching } = useQuery<InventoryItem[]>({
    queryKey: ['inventory'],
    queryFn: async () => {
      const pageSize = 100
      let skip = 0
      const all: InventoryItem[] = []
      while (true) {
        const response = await api.get('/inventory', { params: { paginated: true, skip, limit: pageSize } })
        const data = response.data
        all.push(...data.items)
        if (!data.has_more || data.items.length === 0) break
        skip = data.skip + data.limit
      }
      return all
    },
    // Shares the ['inventory'] cache entry with RepairOrdersPage's query — this
    // panel remounts on every drawer open, and with no staleTime here that was
    // forcing a full re-page of the catalog every time regardless of the
    // staleTime set on the other query sharing this key.
    staleTime: 60 * 1000,
  })

  const { data: partSuggestions, isFetching: partSuggestionsFetching } = useQuery<PartSuggestionsResponse>({
    queryKey: ['price-build-part-suggestions', orderId],
    queryFn: async () => {
      const response = await api.get(`/repair-orders/${orderId}/parts/suggestions`)
      return response.data
    },
    enabled: !!orderId && !isDeleted && addType === 'part',
  })

  const laborBookSearchTerm = searchTerm.trim()
  const { data: laborBookEntries = [], isFetching: laborBookEntriesFetching } = useQuery<LaborBookTimeEntry[]>({
    queryKey: ['labor-book-time', laborBookSearchTerm],
    queryFn: async () => {
      const response = await api.get('/labor-book-time', {
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
  const canCreateInvoice = !isInternalOrder && orderStatus === 'completed' && !!onCreateInvoice
  const showRecommendedServicesPanel = !['completed', 'invoiced', 'paid'].includes(orderStatus)
  // Internal fleet orders carry their work through active statuses (e.g. an
  // in-progress PM) and the owner bills labor at the customer's rate while parts
  // stay at cost — so labor (duration + rate) must stay editable until the order
  // freezes, not just in draft/quoted.
  const INTERNAL_FROZEN_STATUSES: RepairOrderStatus[] = ['completed', 'invoiced', 'paid', 'cancelled']
  const isEditableStatus = ['draft', 'quoted'].includes(orderStatus) ||
    (isInternalOrder && !INTERNAL_FROZEN_STATUSES.includes(orderStatus))
  const canMutate = canEdit && !isLocked && isEditableStatus
  // The add bar must follow the same editable-status rule as canMutate, or an
  // internal in-progress order shows "start by adding…" with no add controls.
  const addBarReadOnly = !canEdit || isLocked || !isEditableStatus || completionMode || hasInvoice || orderStatus === 'completed'
  const hasQuoteDraft = !!quoteNumber
  const hasAssignedTechnician = !!assignedTechnicianName
  const canManageTechnician = !isInternalOrder && quoteIsApproved && !['pending_review', 'completed', 'invoiced', 'paid', 'cancelled'].includes(orderStatus)
  const availableTechnicians = technicianOptions
    .filter((tech) => tech.mechanic_id !== assignedTechnicianId)
    .map((tech) => {
      const assigned = tech.assigned_count ?? 0
      const inProgress = tech.in_progress_count ?? 0
      const load = assigned > 0 ? Math.min((inProgress / assigned) * 100, 100) : 0
      return { ...tech, assigned, inProgress, load }
    })
    .sort((a, b) => a.load - b.load)
  const quoteButtonDisabledReason = quoteDisabledReason || (
    quoteIsApproved
      ? 'The customer has already approved this quote. Pricing and quote sending are locked so the team can complete the approved work.'
      : !canMutate
        ? 'Quote changes are only available before the customer approves the work.'
        : undefined
  )
  const lockContextMessage = quoteButtonDisabledReason || (
    quoteIsApproved
      ? 'The customer has already approved this quote. Continue through technician, completion, and invoice steps.'
      : 'Pricing and quote edits are locked for this repair order.'
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
    await queryClient.invalidateQueries({ queryKey: ['price-build', orderId] })
    await queryClient.invalidateQueries({ queryKey: ['price-build-parts', orderId] })
    await queryClient.invalidateQueries({ queryKey: ['price-build-part-suggestions', orderId] })
    await queryClient.invalidateQueries({ queryKey: ['repair-order-detail', orderId] })
    await queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
    await refetch()
    await refetchParts()
    onUpdated?.()
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
    }: {
      inventoryId: string
      quantity: number
      sourceServiceId?: string | null
      quantityKey?: string
    }) => {
      const inventoryItem = inventory?.find((item) => item.id === inventoryId)
      const body: {
        inventory_id: string
        quantity: number
        source_service_id: string | null
        unit_price?: string
      } = {
        inventory_id: inventoryId,
        quantity,
        source_service_id: sourceServiceId || null,
      }
      if (partsPricingMode === 'stock' && inventoryItem?.cost != null) {
        body.unit_price = inventoryItem.cost
      }
      await api.post(`/repair-orders/${orderId}/parts`, body)
    },
    onSuccess: async (_data, variables) => {
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
    onError: (err: unknown) => toast.error(errorDetail(err, 'Unable to add part')),
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
      await api.post(`/repair-orders/${orderId}/price-build/repair-ops/apply`, {
        operation_id: candidate.operation_id,
        name: candidate.name,
        description: candidate.description,
        estimated_hours: estimatedHours != null ? hours : candidate.estimated_hours,
        provider: candidate.provider,
        auto_recalc_enabled: true,
      })
    },
    onSuccess: async () => {
      setSearchTerm('')
      setBookTimeHours('1')
      setCandidates([])
      setSearchWarnings([])
      setPaletteOpen(false)
      await invalidate()
      toast.success('Repair operation applied')
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
    <div className="flex h-full min-h-full flex-col overflow-hidden bg-white">
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
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-white/75">
              {isInternalOrder ? 'Internal Fleet Order' : 'Repair Order'}
            </p>
            <h3 className="truncate font-['Barlow_Condensed',sans-serif] text-3xl font-extrabold leading-none tracking-wide">
              #{orderNumber || orderId.slice(0, 8)}
            </h3>
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
              <span className="rounded-full bg-white/14 px-3 py-1 font-['JetBrains_Mono',monospace] text-xs font-semibold text-white/90">
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
          <span className="rounded-full bg-white px-3 py-1.5 text-blue-700">{orderStatus.replace('_', ' ')}</span>
          <span className="inline-flex items-center gap-1 rounded-full bg-white/14 px-3 py-1.5 text-white ring-1 ring-white/20">
            <Building2 className="h-3.5 w-3.5" />
            {customerName || 'Customer'}
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-white/14 px-3 py-1.5 text-white ring-1 ring-white/20">
            <Truck className="h-3.5 w-3.5" />
            {[vehicleUnit, vehicleLabel].filter(Boolean).join(' · ') || 'Truck'}
          </span>
        </div>
      </div>

      {!isInternalOrder && (
        <>
        <div className="flex items-center justify-between gap-3 border-b border-orange-100 bg-orange-50/60 px-5 py-2.5 text-xs">
          <div className="flex min-w-0 items-center gap-2 overflow-x-auto whitespace-nowrap">
            <span className={`rounded-full px-2.5 py-1 font-semibold ${
              hasQuoteDraft ? 'bg-emerald-100 text-emerald-700' : 'bg-orange-500 text-white'
            }`}>
              {hasQuoteDraft ? '✓ Draft ready' : 'Create draft'}
            </span>
            <span className="text-gray-300">→</span>
            <span className={`rounded-full px-2.5 py-1 font-semibold ${
              quoteIsSent || quoteIsApproved
                ? 'bg-emerald-100 text-emerald-700'
                : hasQuoteDraft
                  ? 'bg-orange-500 text-white'
                  : 'bg-gray-200 text-gray-400'
            }`}>
              {quoteIsSent || quoteIsApproved ? '✓ Sent' : 'Send'}
            </span>
            <span className="text-gray-300">→</span>
            <span className={`rounded-full px-2.5 py-1 font-semibold ${
              quoteIsApproved
                ? 'bg-emerald-100 text-emerald-700'
                : quoteIsSent
                  ? 'bg-white text-amber-700 ring-1 ring-amber-200'
                  : 'bg-transparent text-gray-400'
            }`}>
              {quoteIsApproved ? '✓ Approved' : quoteIsSent ? 'Awaiting approval' : 'Approved'}
            </span>
            <span className="text-gray-300">→</span>
            <span className={`rounded-full px-2.5 py-1 font-semibold ${
              hasAssignedTechnician
                ? 'bg-emerald-100 text-emerald-700'
                : quoteIsApproved
                  ? 'bg-white text-amber-700 ring-1 ring-amber-200'
                  : 'bg-transparent text-gray-400'
            }`}>
              {hasAssignedTechnician ? `✓ ${assignedTechnicianName}` : quoteIsApproved ? 'Assign technician' : 'Technician'}
            </span>
          </div>
          <span className="shrink-0 font-['JetBrains_Mono',monospace] text-[11px] font-semibold text-gray-500">
            {quoteNumber || 'Q-pending'}
          </span>
        </div>
        {canManageTechnician && onAssignTechnician && availableTechnicians.length > 0 && (
          <div className="border-t border-orange-100 bg-white px-5 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-gray-500">
                {hasAssignedTechnician ? 'Reassign technician' : 'Assign technician'}
              </p>
              {hasAssignedTechnician && assignedTechnicianName && (
                <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                  Current: {assignedTechnicianName}
                </span>
              )}
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {availableTechnicians.map((tech) => (
                <button
                  key={tech.mechanic_id}
                  type="button"
                  onClick={() => onAssignTechnician(tech.mechanic_id)}
                  disabled={technicianAssignmentPending}
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

      {!!summary?.warnings?.length && (
        <div className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
          {summary.warnings.map((w) => (
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
                  {money(invoice.total_amount)}
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
            {parseFloat(invoice.service_fee_amount || '0') > 0 && (
              <div className="flex items-center justify-between">
                <span className="text-gray-500">Service fee</span>
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
              <span className="font-semibold text-purple-950">Invoice total</span>
              <span className="font-['Barlow_Condensed',sans-serif] text-2xl font-extrabold text-purple-950">{money(invoice.total_amount)}</span>
            </div>
          </div>
          )}
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
              {completeWorkOrderPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
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

      <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50/70 p-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className={`${addBarReadOnly ? 'grid grid-cols-1' : 'grid grid-cols-4'} shrink-0 rounded-xl bg-white p-1 text-xs font-bold shadow-sm ring-1 ring-gray-200`}>
            {(addBarReadOnly ? ([
              ['history', History, 'History'],
            ] as const) : ([
              ['operation', Wrench, 'Operation'],
              ['part', Box, 'Part'],
              ['saved_labor', Tag, 'Labor Book Time'],
              ['history', History, 'History'],
            ] as const)).map(([key, Icon, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setAddType(key)
                  setPaletteOpen(key !== 'history')
                }}
                className={`inline-flex items-center justify-center gap-1 rounded-lg px-2.5 py-2 ${
                  addType === key ? 'bg-orange-500 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">{label}</span>
              </button>
            ))}
          </div>
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
          <div className="mt-3 rounded-[14px] border border-gray-200 bg-white">
            <button
              type="button"
              onClick={() => {
                setHistoryOpen((open) => !open)
                setHistoryVisibleCount(5)
              }}
              className="flex w-full items-center justify-between gap-3 px-3 py-3 text-left"
              aria-expanded={historyOpen}
            >
              <span>
                <span className="block text-xs font-bold uppercase tracking-[0.16em] text-gray-400">
                  Repair order history
                </span>
                <span className="mt-0.5 block text-sm font-semibold text-gray-800">
                  {historyEvents.length ? `${historyEvents.length} recorded events` : 'No recorded events'}
                </span>
              </span>
              <span className="flex shrink-0 items-center gap-2">
                <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-bold text-gray-500">
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
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-orange-500" />
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
                          aria-label={isAddNew ? 'Add operation' : 'Apply operation'}
                        >
                          <Plus className="h-4 w-4" />
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
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-orange-500" />
                    Searching labor book time…
                  </p>
                )}
                {!laborBookEntriesFetching && laborBookEntries.length > 0 && laborBookEntries.slice(0, 8).map((entry, index) => {
                  const scope = laborBookTimeScope(entry)
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
                        aria-label={`Add ${entry.operation_name}`}
                      >
                        <Plus className="h-4 w-4" />
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
                              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Decoding…
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
                        className="h-9 rounded-lg bg-gray-900 px-3 text-xs font-bold text-white disabled:bg-gray-300"
                      >
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
                {(inventoryFetching || partSuggestionsFetching) && (
                  <p className="inline-flex items-center gap-2 px-2 py-3 text-xs font-semibold text-gray-500">
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-orange-500" />
                    Loading parts…
                  </p>
                )}
                {(() => {
                  const term = searchTerm.trim().toLowerCase()

                  const renderItemRow = (item: { id: string; name: string; sku: string; stock_quantity: number; unit_type: string; selling_price: string }, index: number) => {
                    const isFluid = item.unit_type && item.unit_type !== 'each'
                    const step = isFluid ? 0.25 : 1
                    const unitAbbr = UNIT_ABBR[item.unit_type] || ''
                    const rowQuantity = Math.max(step, partQuantitiesByItemId[item.id] ?? 1)
                    return (
                      <div
                        key={item.id}
                        className={`flex items-center justify-between gap-3 rounded-xl px-3 py-2.5 ${
                          index === 0 ? 'bg-orange-50 shadow-[inset_3px_0_0_#ef8a12]' : 'hover:bg-gray-50'
                        }`}
                      >
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
                            }}
                          />
                          <button
                            type="button"
                            onClick={() => addPart.mutate({ inventoryId: item.id, quantity: rowQuantity })}
                            disabled={!canMutate || addPart.isPending}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-gray-900 text-white disabled:bg-gray-300"
                            aria-label={`Add ${item.name}`}
                          >
                            <Plus className="h-4 w-4" />
                          </button>
                        </div>
                      </div>
                    )
                  }

                  if (!term) {
                    const forThisOrder = partSuggestions?.for_this_order || []
                    const mostUsed = (partSuggestions?.most_used || [])
                      .filter((s) => !forThisOrder.some((f) => f.inventory_id === s.inventory_id))

                    if (!forThisOrder.length && !mostUsed.length) {
                      const fallback = (inventory || []).filter((item) => item.stock_quantity > 0).slice(0, 8)
                      if (!fallback.length) {
                        return <p className="px-2 py-3 text-sm text-gray-500">No in-stock parts yet.</p>
                      }
                      return fallback.map((item, index) => renderItemRow(item, index))
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

                  const matches = (inventory || [])
                    .filter((item) => item.stock_quantity > 0)
                    .filter((item) => item.name.toLowerCase().includes(term) || item.sku.toLowerCase().includes(term))
                    .slice(0, 8)
                  if (!matches.length) {
                    return <p className="px-2 py-3 text-sm text-gray-500">No in-stock parts match this search.</p>
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
        const partsByService = new Map<string, typeof allParts>()
        const orphanParts: typeof allParts = []
        for (const pu of allParts) {
          if (pu.source_service_id) {
            const bucket = partsByService.get(pu.source_service_id) || []
            bucket.push(pu)
            partsByService.set(pu.source_service_id, bucket)
          } else {
            orphanParts.push(pu)
          }
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
                  return (
                    <tr key={pu.id} className="border-b border-gray-100 last:border-0">
                      <td className="py-1.5 px-2.5 text-gray-800">
                        <div className="font-medium">{pu.inventory_name}</div>
                        <div className="text-xs text-gray-500">{pu.inventory_sku}</div>
                      </td>
                      <td className="py-1.5 px-2.5 text-right text-gray-800">
                        {canMutate ? (
                          <span className="inline-flex justify-end">
                            <PartQtyStepper
                              part={pu}
                              disabled={editingPartsSaving || priceSavingId === pu.id}
                              onChangeQty={async (next) => {
                                try {
                                  await api.patch(`/repair-orders/${orderId}/parts/${pu.id}`, { quantity: next })
                                  await invalidate()
                                } catch (err: unknown) {
                                  toast.error(errorDetail(err, 'Failed to update quantity'))
                                  await invalidate()
                                }
                              }}
                              onDelete={async () => {
                                setEditingPartsSaving(true)
                                try {
                                  await api.delete(`/repair-orders/${orderId}/parts/${pu.id}`)
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
          if (!line.source_service_id || operationPartPickerLineId !== line.id) return null
          const term = (operationPartSearchByLineId[line.id] || '').trim().toLowerCase()
          const groupedInventoryIds = new Set(groupedParts.map((part) => part.inventory_id))
          const matches = (inventory || [])
            .filter((item) => item.stock_quantity > 0)
            .filter((item) => !groupedInventoryIds.has(item.id))
            .filter((item) => !term || item.name.toLowerCase().includes(term) || item.sku.toLowerCase().includes(term))
            .slice(0, 6)

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
              {!matches.length ? (
                <p className="px-1 py-2 text-sm text-gray-500">No available parts match this operation search.</p>
              ) : (
                <div className="space-y-1">
                  {matches.map((item) => {
                    const isFluid = item.unit_type && item.unit_type !== 'each'
                    const step = isFluid ? 0.25 : 1
                    const unitAbbr = UNIT_ABBR[item.unit_type] || ''
                    const quantityKey = `${line.id}:${item.id}`
                    const rowQuantity = Math.max(step, partQuantitiesByItemId[quantityKey] ?? 1)
                    return (
                      <div key={item.id} className="flex items-center justify-between gap-3 rounded-lg bg-white px-2.5 py-2">
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
                            }}
                          />
                          <button
                            type="button"
                            onClick={() => addPart.mutate({
                              inventoryId: item.id,
                              quantity: rowQuantity,
                              sourceServiceId: line.source_service_id,
                              quantityKey,
                            })}
                            disabled={!canMutate || addPart.isPending}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-gray-900 text-white disabled:bg-gray-300"
                            aria-label={`Add ${item.name} to ${line.description}`}
                          >
                            <Plus className="h-4 w-4" />
                          </button>
                        </div>
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
          return <p className="text-sm text-gray-500">Loading…</p>
        }
        if (summaryLoadFailed) {
          return (
            <div className="rounded-xl border border-dashed border-red-200 bg-red-50/40 px-4 py-6 text-center">
              <p className="font-semibold text-gray-900">Couldn't load this order's work &amp; labor.</p>
              <p className="mt-1 text-sm text-gray-500">This isn't necessarily an empty order — the request failed.</p>
              <button
                type="button"
                onClick={() => refetch()}
                className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-700"
              >
                Retry
              </button>
            </div>
          )
        }
        if (!lines.length && !orphanParts.length) {
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
                const groupedParts = line.source_service_id ? partsByService.get(line.source_service_id) || [] : []
                const isOpen = openLineIds.has(line.id)
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
                        <button
                          type="button"
                          disabled={!canMutate || !line.source_service_id}
                          onClick={() => setOperationPartPickerLineId((current) => current === line.id ? null : line.id)}
                          className="inline-flex w-full items-center justify-center gap-1 rounded-xl border border-dashed border-gray-300 px-3 py-2 text-sm font-semibold text-gray-500 hover:border-orange-300 hover:bg-orange-50 hover:text-orange-700 disabled:hover:border-gray-300 disabled:hover:bg-transparent disabled:hover:text-gray-400 disabled:opacity-60"
                        >
                          <Plus className="h-4 w-4" /> Add part to this operation
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
            onClick={() => setRecommendedOpen((open) => !open)}
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
            {recommendedServices?.length ? (
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
          <button
            type="button"
            onClick={() => { setFooterDetailsOpen((open) => open === 'discounts' ? null : 'discounts'); setDiscountsOpen(false) }}
            className="rounded-full bg-red-50 px-3 py-1 text-xs font-bold text-red-700 hover:bg-red-100"
          >
            Discounts -{isInitialSummaryLoad || summaryLoadFailed ? '…' : money(discountTotal)}
          </button>
          <button
            type="button"
            onClick={() => { setFooterDetailsOpen((open) => open === 'savings' ? null : 'savings'); setDiscountsOpen(false) }}
            className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700 hover:bg-emerald-100"
          >
            Customer saves {isInitialSummaryLoad || summaryLoadFailed ? '…' : money(customerSavesTotal)}
          </button>
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
                  {discountsSaving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
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
                  {(totalMotionActive || isInitialSummaryLoad) && <Loader2 className="h-3 w-3 animate-spin" />}
                  {summaryLoadFailed ? 'Failed to load' : isInitialSummaryLoad ? 'Loading' : totalMotionActive ? 'Calculating' : 'Order Total'}
                  {summaryLoadFailed && (
                    <button
                      type="button"
                      onClick={() => refetch()}
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
            {!isInternalOrder && (
              canCreateInvoice ? (
                <div className="relative">
                  <button
                    type="button"
                    onClick={onToggleInvoiceCreateOptions}
                    disabled={invoiceCreatePending}
                    className="inline-flex h-11 items-center gap-2 rounded-xl bg-indigo-600 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(79,70,229,.26)] hover:bg-indigo-700 disabled:bg-gray-300"
                  >
                    {invoiceCreatePending ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
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
                            {invoiceCreatePending && <Loader2 className="h-4 w-4 animate-spin" />}
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
                      Record payment
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
                  {orderStatus !== 'paid' && onDeleteInvoice && (
                    <button
                      type="button"
                      onClick={onDeleteInvoice}
                      disabled={invoiceActionPending}
                      className="inline-flex h-11 items-center justify-center rounded-xl border border-red-200 bg-red-50 px-3 text-red-700 hover:bg-red-100 disabled:opacity-50"
                      aria-label="Delete invoice"
                    >
                      <Trash2 className="h-4 w-4" />
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
                  {completionPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
                  {completionPending ? 'Approving...' : 'Approve Completion'}
                </button>
              ) : (
                <span
                  className="inline-flex"
                  title={quoteActionDisabled || !canMutate ? quoteButtonDisabledReason : undefined}
                >
                  <button
                    type="button"
                    onClick={onQuoteAction}
                    disabled={!canMutate || quoteActionDisabled || quoteActionPending || !onQuoteAction}
                    className="inline-flex h-11 items-center gap-2 rounded-xl bg-orange-500 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(239,138,18,.32)] disabled:bg-gray-300"
                  >
                    {quoteActionPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plane className="h-4 w-4" />}
                    {quoteActionPending ? 'Working...' : quoteActionLabel}
                  </button>
                </span>
              )
            )}
            {isInternalOrder && !isDeleted && (
              ['draft', 'assigned', 'acknowledged'].includes(orderStatus) ? (
                <button
                  type="button"
                  disabled={startWorkOrderPending || !onStartWorkOrder}
                  onClick={onStartWorkOrder}
                  className="inline-flex h-11 items-center gap-2 rounded-xl bg-amber-500 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(245,158,11,.28)] hover:bg-amber-600 disabled:bg-gray-300"
                >
                  {startWorkOrderPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
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
                    {reopenPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
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
            className="flex w-full items-center justify-between px-5 py-2.5 text-left text-xs font-semibold text-red-700"
          >
            <span className="inline-flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> Danger zone</span>
            <ChevronDown className={`h-4 w-4 transition-transform ${showDangerActions ? 'rotate-180' : ''}`} />
          </button>
          {showDangerActions && (
            <div className="border-t border-red-100 px-5 py-3">
              {isDeleted ? (
                <>
                  <p className="mb-3 text-sm text-red-700">
                    {(() => {
                      const when = deletedAt ? format(new Date(deletedAt), 'MMM d, yyyy h:mm a') : null
                      if (deletedByName && when) return `Deleted by ${deletedByName} on ${when}. Restore to bring it back.`
                      if (when) return `Deleted on ${when}. Restore to bring it back.`
                      return 'This order is deleted. Restore to bring it back.'
                    })()}
                  </p>
                  <div className="flex flex-wrap justify-end gap-2">
                    <button
                      type="button"
                      disabled={restorePending}
                      onClick={onRestoreOrder}
                      className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                    >
                      <RotateCcw className="h-4 w-4" />
                      {restorePending ? 'Restoring...' : 'Restore order'}
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <p className="mb-3 text-sm text-red-700">
                    Delete removes this order from your active lists. Nothing is destroyed —
                    it can be restored later from the Deleted filter.
                  </p>
                  <div className="flex flex-wrap justify-end gap-2">
                    <button
                      type="button"
                      disabled={deletePending}
                      onClick={onDeleteOrder}
                      className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                    >
                      {deletePending ? 'Deleting...' : 'Delete'}
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
