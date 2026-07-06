import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  AlertTriangle,
  Box,
  Building2,
  ChevronDown,
  ChevronRight,
  Gauge,
  Minus,
  Pencil,
  Plane,
  Plus,
  RefreshCcw,
  Search,
  Tag,
  Trash2,
  Truck,
  Wrench,
  X,
} from 'lucide-react'

import api from '@/lib/api'
import BaseSelect from '@/components/BaseSelect'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'
import {
  PartsUsage,
  PriceBuildSummary,
  InventoryItem,
  RecommendedService,
  RecommendedServicePriority,
  RepairOperationCandidate,
  RepairOrderStatus,
  Service,
} from '@/types'

type Props = {
  orderId: string
  orderStatus: RepairOrderStatus
  services?: Service[]
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
  onClose?: () => void
  onPrev?: () => void
  onNext?: () => void
  prevDisabled?: boolean
  nextDisabled?: boolean
  showDangerActions?: boolean
  onToggleDangerActions?: () => void
  onCancelOrder?: () => void
  onDeleteOrder?: () => void
  cancelPending?: boolean
  deletePending?: boolean
  cancelDisabled?: boolean
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

const UNIT_ABBR: Record<string, string> = { each: '', gallon: 'gal', quart: 'qt', liter: 'L' }

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

  // part.quantity is a Decimal on the backend (fluids use fractional amounts),
  // so it arrives over the wire as a string — parse it once here so all local
  // state/arithmetic below works with real numbers.
  const currentQuantity = parseFloat(part.quantity) || 0

  // Optimistic local quantity so the number reacts instantly; the debounced
  // save reconciles with the server, and props re-sync it when data refetches.
  const [qty, setQty] = useState(currentQuantity)
  const [busy, setBusy] = useState(false)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastSaved = useRef(currentQuantity)

  // Re-sync from server after a refetch (unless a save is mid-flight).
  useEffect(() => {
    if (saveTimer.current == null && !busy) {
      setQty(currentQuantity)
      lastSaved.current = currentQuantity
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentQuantity])

  useEffect(() => () => { if (saveTimer.current) clearTimeout(saveTimer.current) }, [])

  const scheduleSave = (next: number) => {
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(async () => {
      saveTimer.current = null
      if (next === lastSaved.current) return
      setBusy(true)
      try {
        await onChangeQty(next)
        lastSaved.current = next
      } finally {
        setBusy(false)
      }
    }, 500)
  }

  const commit = (next: number) => {
    if (next < step) return
    const rounded = Math.round(next / step) * step
    setQty(rounded)
    setDraft(isFluid ? rounded.toFixed(2) : String(rounded))
    scheduleSave(rounded)
  }

  const bump = (delta: number) => commit(qty + delta)

  // Free-typed value while the input is focused; reconciled to a valid
  // stepped number on blur/Enter so partial input (e.g. "1.") isn't clobbered
  // by the formatted display on every keystroke.
  const [draft, setDraft] = useState(isFluid ? qty.toFixed(2) : String(qty))
  const [editing, setEditing] = useState(false)

  useEffect(() => {
    if (!editing) setDraft(isFluid ? qty.toFixed(2) : String(qty))
  }, [qty, isFluid, editing])

  const commitDraft = () => {
    setEditing(false)
    const parsed = parseFloat(draft)
    if (!Number.isFinite(parsed) || parsed < step) {
      setDraft(isFluid ? qty.toFixed(2) : String(qty))
      return
    }
    commit(parsed)
  }

  // Ctrl/Cmd+= and Ctrl/Cmd+- step the quantity even while the field has focus,
  // rather than triggering the browser's page zoom.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === '+' || e.key === '=' || e.key === '-' || e.key === '_')) {
      e.preventDefault()
      commit(qty + (e.key === '-' || e.key === '_' ? -step : step))
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      commitDraft()
      e.currentTarget.blur()
    } else if (e.key === 'Escape') {
      setEditing(false)
      setDraft(isFluid ? qty.toFixed(2) : String(qty))
      e.currentTarget.blur()
    }
  }

  const atMin = qty <= step

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-flex items-center rounded-lg border border-gray-200 bg-white shadow-sm">
        <button
          type="button"
          disabled={disabled}
          onClick={atMin ? onDelete : () => bump(-step)}
          aria-label={atMin ? `Remove ${part.inventory_name}` : `Decrease quantity of ${part.inventory_name}`}
          className={`flex h-8 w-8 items-center justify-center rounded-l-lg disabled:opacity-50 ${
            atMin ? 'text-red-500 hover:bg-red-50' : 'text-gray-500 hover:bg-gray-50'
          }`}
        >
          {atMin ? <Trash2 className="h-3.5 w-3.5" /> : <Minus className="h-3.5 w-3.5" />}
        </button>
        <input
          type="text"
          inputMode="decimal"
          disabled={disabled}
          value={draft}
          onFocus={() => setEditing(true)}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitDraft}
          onKeyDown={handleKeyDown}
          aria-label={`Quantity for ${part.inventory_name}`}
          title="Type a value, or use Ctrl/Cmd + and Ctrl/Cmd − to step"
          className={`h-8 border-x border-gray-200 bg-transparent text-center font-['JetBrains_Mono',monospace] text-sm tabular-nums text-gray-900 outline-none focus:bg-gray-50 disabled:opacity-50 ${isFluid ? 'w-14' : 'w-10'}`}
        />
        <button
          type="button"
          disabled={disabled}
          onClick={() => bump(step)}
          aria-label={`Increase quantity of ${part.inventory_name}`}
          className="flex h-8 w-8 items-center justify-center rounded-r-lg text-gray-500 hover:bg-gray-50 disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </span>
      {unitAbbr && <span className="text-xs text-gray-500">{unitAbbr}</span>}
    </span>
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
  const margin = stock != null && unit > 0 ? ((unit - stock) / unit) * 100 : null
  const isCustom = Number.isFinite(list) && Math.abs(unit - list) >= 0.005

  const computePosition = () => {
    if (!buttonRef.current) return
    const rect = buttonRef.current.getBoundingClientRect()
    const estimatedMenuHeight = 250
    const spaceBelow = window.innerHeight - rect.bottom
    const openUp = spaceBelow < estimatedMenuHeight && rect.top > estimatedMenuHeight
    setMenuPos({
      top: openUp ? rect.top - 4 : rect.bottom + 4,
      left: rect.right,
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
          className="z-[70] w-[280px] rounded-[14px] border border-gray-200 bg-white p-3 text-sm shadow-[0_10px_30px_rgba(20,25,35,.10)]"
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
            <label className="flex items-center justify-between gap-3 rounded-xl border border-orange-200 bg-orange-50/70 px-2.5 py-2">
              <span className="whitespace-nowrap font-medium text-gray-900">
                <span className="mr-2 inline-block h-2 w-2 rounded-full bg-orange-500" />Customer price
              </span>
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value.replace(/[^0-9.]/g, ''))}
                inputMode="decimal"
                className="h-9 w-24 rounded-lg border border-orange-200 bg-white px-2 text-right font-['JetBrains_Mono',monospace] text-sm outline-none focus:ring-2 focus:ring-orange-300"
              />
            </label>
          </div>
          <div className="mt-3 flex items-center justify-between gap-2 border-t border-gray-100 pt-3">
            <button
              type="button"
              disabled={saving || disabled}
              onClick={() => setDraft(list.toFixed(2))}
              className="rounded-lg px-2 py-1.5 text-xs font-semibold text-gray-600 hover:bg-gray-100 disabled:opacity-60"
            >
              Reset to list
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
  services,
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
  onClose,
  onPrev,
  onNext,
  prevDisabled,
  nextDisabled,
  showDangerActions,
  onToggleDangerActions,
  onCancelOrder,
  onDeleteOrder,
  cancelPending,
  deletePending,
  cancelDisabled,
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
  const [serviceId, setServiceId] = useState('')
  const [serviceHours, setServiceHours] = useState(1)
  const [searchTerm, setSearchTerm] = useState('')
  const [candidates, setCandidates] = useState<RepairOperationCandidate[]>([])
  const [searchWarnings, setSearchWarnings] = useState<{ code: string; message: string }[]>([])
  const [addType, setAddType] = useState<'operation' | 'saved_labor' | 'diagnostic' | 'part'>('operation')
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [openLineIds, setOpenLineIds] = useState<Set<string>>(new Set())
  const [discountsOpen, setDiscountsOpen] = useState(false)
  const [customerOpen, setCustomerOpen] = useState(false)
  const [recommendedOpen, setRecommendedOpen] = useState(false)
  const [partQuantity, setPartQuantity] = useState(1)
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
  const { data: summary, refetch, isLoading } = useQuery<PriceBuildSummary>({
    queryKey: ['price-build', orderId],
    queryFn: async () => {
      const response = await api.get(`/repair-orders/${orderId}/price-build`)
      return response.data
    },
    enabled: !!orderId,
  })

  const { data: partsUsed, refetch: refetchParts } = useQuery<PartsUsage[]>({
    queryKey: ['price-build-parts', orderId],
    queryFn: async () => {
      const response = await api.get(`/repair-orders/${orderId}/parts`)
      return response.data
    },
    enabled: !!orderId,
  })

  const { data: inventory } = useQuery<InventoryItem[]>({
    queryKey: ['inventory'],
    queryFn: async () => {
      const response = await api.get('/inventory')
      return response.data
    },
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

  type LaborField = 'hours' | 'rate'
  const [editingLabor, setEditingLabor] = useState<{ lineId: string; field: LaborField } | null>(null)
  const [editingLaborValue, setEditingLaborValue] = useState<string>('')
  const [editingLaborSaving, setEditingLaborSaving] = useState(false)

  const startEditLabor = (lineId: string, field: LaborField, current: string) => {
    setEditingLabor({ lineId, field })
    setEditingLaborValue(field === 'rate' ? parseFloat(current).toFixed(2) : current)
  }
  const cancelEditLabor = () => {
    setEditingLabor(null)
    setEditingLaborValue('')
  }
  const saveEditLabor = async (line: { id: string; hours: string; hourly_rate: string }) => {
    if (!editingLabor) return
    const { field } = editingLabor
    const value = parseFloat(editingLaborValue || '0')
    if (!Number.isFinite(value) || value < 0) {
      toast.error(field === 'hours' ? 'Hours must be 0 or more' : 'Rate must be 0 or more')
      return
    }
    const current = parseFloat(field === 'hours' ? line.hours : line.hourly_rate)
    if (Math.abs(value - current) < 0.0001) {
      cancelEditLabor()
      return
    }
    setEditingLaborSaving(true)
    try {
      await updateLine.mutateAsync({
        lineId: line.id,
        body: field === 'hours' ? { hours: value } : { hourly_rate: value },
      })
      toast.success(field === 'hours' ? `Hours updated to ${value}` : `Rate updated to $${value.toFixed(2)}`)
      cancelEditLabor()
    } catch {
      // error toast handled by mutation
    } finally {
      setEditingLaborSaving(false)
    }
  }

  const isLocked = !!summary?.pricing_locked
  const canMutate = canEdit && !isLocked && ['draft', 'quoted'].includes(orderStatus)

  const serviceOptions = useMemo(() => {
    const list = services || []
    return list
      .filter((svc) => svc.is_active !== false)
      .map((svc) => ({
        value: svc.id,
        label: svc.name,
      }))
  }, [services])

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['price-build', orderId] })
    await queryClient.invalidateQueries({ queryKey: ['price-build-parts', orderId] })
    await queryClient.invalidateQueries({ queryKey: ['repair-order-detail', orderId] })
    await queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
    await refetch()
    await refetchParts()
    onUpdated?.()
  }

  // --- Bulk parts pricing (Stock ⇄ List) + manager discounts ---
  const [laborDiscount, setLaborDiscount] = useState('')
  const [orderDiscount, setOrderDiscount] = useState('')
  const [pricingBusy, setPricingBusy] = useState(false)
  const [partsPricingMode, setPartsPricingMode] = useState<'stock' | 'list'>('list')
  useEffect(() => {
    const l = parseFloat(summary?.labor_discount_amount || '0')
    const o = parseFloat(summary?.order_discount_amount || '0')
    setLaborDiscount(l > 0 ? l.toFixed(2) : '')
    setOrderDiscount(o > 0 ? o.toFixed(2) : '')
  }, [summary?.labor_discount_amount, summary?.order_discount_amount])

  useEffect(() => {
    const parts = partsUsed || []
    if (!parts.length) return
    const isSameMoney = (a: string | number | null | undefined, b: string | number | null | undefined) => (
      Math.abs((parseFloat(String(a ?? '0')) || 0) - (parseFloat(String(b ?? '0')) || 0)) < 0.005
    )
    if (parts.every((part) => isSameMoney(part.unit_price, part.list_price ?? part.unit_price))) {
      setPartsPricingMode('list')
      return
    }
    if (parts.every((part) => part.unit_cost != null && isSameMoney(part.unit_price, part.unit_cost))) {
      setPartsPricingMode('stock')
    }
  }, [partsUsed])

  const applyPricingMode = async (mode: 'stock' | 'list') => {
    const previousMode = partsPricingMode
    setPartsPricingMode(mode)
    setPricingBusy(true)
    try {
      await api.post(`/repair-orders/${orderId}/parts/pricing-mode`, { mode })
      await invalidate()
      toast.success(mode === 'stock' ? 'Parts set to stock (cost) price' : 'Parts set to list price')
    } catch (err: unknown) {
      setPartsPricingMode(previousMode)
      toast.error(errorDetail(err, 'Failed to update pricing'))
    } finally {
      setPricingBusy(false)
    }
  }

  const saveDiscounts = async () => {
    try {
      await api.patch(`/repair-orders/${orderId}/discounts`, {
        labor_discount_amount: laborDiscount.trim() === '' ? '0' : laborDiscount,
        order_discount_amount: orderDiscount.trim() === '' ? '0' : orderDiscount,
      })
      await invalidate()
    } catch (err: unknown) {
      toast.error(errorDetail(err, 'Failed to apply discount'))
    }
  }

  const addServiceLaborLine = useMutation({
    mutationFn: async () => {
      await api.post(`/repair-orders/${orderId}/price-build/flat-service`, {
        service_id: serviceId,
        quantity: serviceHours,
      })
    },
    onSuccess: async () => {
      setServiceId('')
      setServiceHours(1)
      await invalidate()
      toast.success('Labor line added')
    },
    onError: () => toast.error('Unable to add labor line'),
  })

  const addPart = useMutation({
    mutationFn: async ({ inventoryId, quantity }: { inventoryId: string; quantity: number }) => {
      await api.post(`/repair-orders/${orderId}/parts`, {
        inventory_id: inventoryId,
        quantity,
      })
    },
    onSuccess: async () => {
      setSearchTerm('')
      setPartQuantity(1)
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
      await invalidate()
      toast.success('Repair operation applied')
    },
    onError: (err: unknown) => toast.error(err instanceof Error ? err.message : 'Unable to apply operation'),
  })

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
        toast.error(decoded.error_text)
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
      toast.success('VIN decoded into labor book time scope')
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : errorDetail(err, 'Failed to decode VIN'))
    },
  })

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

  const recalc = useMutation({
    mutationFn: async () => {
      await api.post(`/repair-orders/${orderId}/price-build/recalculate`)
    },
    onSuccess: async () => {
      await invalidate()
      toast.success('Price recalculated')
    },
    onError: () => toast.error('Recalculation failed'),
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

  useEffect(() => {
    if (!defaultLaborRate || !canMutate) return
    // No-op placeholder: keeps default labor rate available for future quick-add UX.
  }, [defaultLaborRate, canMutate])

  return (
    <div className="flex h-full min-h-full flex-col overflow-hidden bg-white">
      <div className="bg-[linear-gradient(100deg,#f7a823,#e07c05)] px-5 py-4 text-white">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-white/75">Repair Order</p>
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
        <div className="flex items-center justify-between gap-3 border-b border-orange-100 bg-orange-50/60 px-5 py-2.5 text-xs">
          <div className="flex min-w-0 items-center gap-2 overflow-x-auto whitespace-nowrap">
            <span className="rounded-full bg-emerald-100 px-2.5 py-1 font-semibold text-emerald-700">✓ Draft ready</span>
            <span className="text-gray-300">→</span>
            <span className="rounded-full bg-orange-500 px-2.5 py-1 font-semibold text-white">Send</span>
            <span className="text-gray-300">→</span>
            <span className="font-semibold text-gray-400">Approved</span>
            <span className="text-gray-300">→</span>
            <span className="font-semibold text-gray-400">Technician</span>
          </div>
          <span className="shrink-0 font-['JetBrains_Mono',monospace] text-[11px] font-semibold text-gray-500">
            {quoteNumber || 'Q-pending'}
          </span>
        </div>
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

      {isLocked && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Pricing locked{summary?.pricing_lock_reason ? ` (${summary.pricing_lock_reason})` : ''}. Edit is disabled.
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

      <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50/70 p-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="grid grid-cols-4 rounded-xl bg-white p-1 text-xs font-bold shadow-sm ring-1 ring-gray-200">
            {([
              ['operation', Wrench, 'Operation'],
              ['diagnostic', Gauge, 'Diagnostic'],
              ['part', Box, 'Part'],
              ['saved_labor', Tag, 'Labor Book Time'],
            ] as const).map(([key, Icon, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setAddType(key)
                  setPaletteOpen(true)
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
          <div className="relative min-w-0 flex-1">
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
                addType === 'operation' ? 'Add operation — search jobs, e.g. brake change, EGR…' :
                addType === 'saved_labor' ? 'Search labor book time — e.g. DPF filter replacement…' :
                addType === 'part' ? 'Add part — search inventory by name or SKU…' :
                'Select diagnostic service below…'
              }
              className="h-11 w-full rounded-xl border border-gray-200 bg-white pl-9 pr-3 text-sm outline-none focus:border-orange-300 focus:ring-2 focus:ring-orange-100"
            />
          </div>
        </div>

        {paletteOpen && (
          <div className="mt-3 rounded-[14px] border border-gray-200 bg-white p-2 shadow-[0_10px_30px_rgba(20,25,35,.10)]">
            <div className="mb-2 flex items-center justify-between border-b border-gray-100 px-2 pb-2">
              <span className="text-xs font-bold uppercase tracking-[0.16em] text-gray-400">
                {addType === 'diagnostic' ? 'Diagnostics · hourly' : addType === 'operation' ? 'Repair operations' : addType === 'saved_labor' ? 'Labor book time' : 'Parts'}
              </span>
              <span className="font-['JetBrains_Mono',monospace] text-[11px] text-gray-400">↵ to add</span>
            </div>
            {addType === 'diagnostic' ? (
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <BaseSelect
                    options={serviceOptions}
                    value={serviceId}
                    onChange={setServiceId}
                    placeholder="Select diagnostics or inspection service"
                    allowAddNew={false}
                  />
                </div>
                <input
                  type="number"
                  min={1}
                  value={serviceHours}
                  onChange={(e) => setServiceHours(Math.max(1, parseInt(e.target.value, 10) || 1))}
                  className="h-10 w-20 rounded-lg border border-gray-200 px-2 text-sm"
                  aria-label="Hours"
                />
                <button
                  type="button"
                  onClick={() => addServiceLaborLine.mutate()}
                  disabled={!canMutate || !serviceId || addServiceLaborLine.isPending}
                  className="inline-flex h-10 items-center justify-center gap-1 rounded-lg bg-orange-500 px-3 text-sm font-bold text-white disabled:bg-gray-300"
                >
                  <Plus className="h-4 w-4" /> Add
                </button>
              </div>
            ) : addType === 'operation' ? (
              <>
                {searchOps.isPending && <p className="px-2 py-3 text-xs text-gray-500">Searching…</p>}
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
                        <p className="truncate text-sm font-semibold text-gray-900">
                          {isAddNew ? `Add "${c.name}" as new operation` : c.name}
                        </p>
                        <p className="truncate font-['JetBrains_Mono',monospace] text-[11px] text-gray-500">
                          {isAddNew
                            ? 'enter book hours to save this time'
                            : `${parseFloat(c.estimated_hours || '0').toFixed(2)} hr book time`} · {c.description || c.operation_id}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {isAddNew ? (
                          <label className="flex items-center gap-1 text-xs font-semibold text-gray-600">
                            <span>Book hrs</span>
                            <input
                              type="number"
                              min="0.25"
                              step="0.25"
                              value={bookTimeHours}
                              onChange={(e) => setBookTimeHours(e.target.value)}
                              className="h-8 w-20 rounded-lg border border-orange-200 bg-white px-2 text-right font-['JetBrains_Mono',monospace] text-xs outline-none focus:ring-2 focus:ring-orange-200"
                              placeholder="0.00"
                            />
                          </label>
                        ) : (
                          <span className="hidden font-['JetBrains_Mono',monospace] text-xs font-semibold text-gray-600 sm:inline">
                            est. {parseFloat(c.estimated_hours || '0').toFixed(1)} hr
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
                {laborBookEntriesFetching && <p className="px-2 py-3 text-xs text-gray-500">Searching labor book time…</p>}
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
                          {parseFloat(entry.normalized_hours || '0').toFixed(2)} hr · {scope.primary} · {scope.secondary}
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
                    <div className="grid gap-2 sm:grid-cols-[minmax(0,1.4fr)_96px]">
                      <input
                        value={laborBookTimeForm.operation_name}
                        onChange={(e) => setLaborBookTimeForm((current) => ({ ...current, operation_name: e.target.value }))}
                        placeholder="Labor name"
                        className="h-9 rounded-lg border border-orange-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-orange-200"
                      />
                      <input
                        value={laborBookTimeForm.normalized_hours}
                        onChange={(e) => setLaborBookTimeForm((current) => ({ ...current, normalized_hours: e.target.value }))}
                        type="number"
                        min="0.25"
                        step="0.25"
                        placeholder="Book hrs"
                        className="h-9 rounded-lg border border-orange-200 bg-white px-3 text-right font-['JetBrains_Mono',monospace] text-sm outline-none focus:ring-2 focus:ring-orange-200"
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
                        onChange={(e) => setLaborBookTimeForm((current) => ({ ...current, vin_sample: e.target.value.toUpperCase() }))}
                        placeholder="Optional VIN helper"
                        className="h-9 min-w-0 flex-1 rounded-lg border border-orange-200 bg-white px-3 text-sm uppercase outline-none focus:ring-2 focus:ring-orange-200"
                      />
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
                {(() => {
                  const term = searchTerm.trim().toLowerCase()
                  const matches = (inventory || [])
                    .filter((item) => item.stock_quantity > 0)
                    .filter((item) => !term || item.name.toLowerCase().includes(term) || item.sku.toLowerCase().includes(term))
                    .slice(0, 8)
                  if (!matches.length) {
                    return <p className="px-2 py-3 text-sm text-gray-500">No in-stock parts match this search.</p>
                  }
                  return matches.map((item, index) => {
                    const isFluid = item.unit_type && item.unit_type !== 'each'
                    const step = isFluid ? 0.25 : 1
                    const unitAbbr = UNIT_ABBR[item.unit_type] || ''
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
                        <input
                          type="number"
                          min={step}
                          step={step}
                          value={partQuantity}
                          onChange={(e) => setPartQuantity(Math.max(step, parseFloat(e.target.value) || step))}
                          className="h-8 w-16 rounded-lg border border-gray-200 px-2 text-sm"
                          aria-label={`Quantity for ${item.name}`}
                        />
                        <button
                          type="button"
                          onClick={() => addPart.mutate({ inventoryId: item.id, quantity: partQuantity })}
                          disabled={!canMutate || addPart.isPending}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-gray-900 text-white disabled:bg-gray-300"
                          aria-label={`Add ${item.name}`}
                        >
                          <Plus className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                    )
                  })
                })()}
              </>
            ) : null}
          </div>
        )}
      </div>

      {(() => {
        const allParts = partsUsed || []
        const lines = summary?.lines || []
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
                            return `${isFluid ? qtyNum.toFixed(2) : qtyNum}${unitAbbr ? ` ${unitAbbr}` : ''}`
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

        const renderLaborEditor = (line: typeof lines[number]) => {
          const editingHours = editingLabor?.lineId === line.id && editingLabor.field === 'hours'
          const editingRate = editingLabor?.lineId === line.id && editingLabor.field === 'rate'
          return (
            <>
              <div className="mb-2 flex items-center gap-1.5">
                <input
                  defaultValue={line.description}
                  onBlur={(e) => {
                    const value = e.target.value.trim()
                    if (value !== line.description) {
                      updateLine.mutate({ lineId: line.id, body: { description: value } })
                    }
                  }}
                  disabled={!canMutate}
                  className="flex-1 rounded-md border border-gray-300 px-2 py-1.5 text-sm disabled:bg-gray-100"
                />
              </div>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-gray-700">
                {editingHours ? (
                  <span className="inline-flex items-center gap-1">
                    <input
                      type="number"
                      step="0.25"
                      min="0"
                      value={editingLaborValue}
                      onChange={(e) => setEditingLaborValue(e.target.value)}
                      className="w-20 h-8 px-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                      autoFocus
                    />
                    <span className="text-gray-500">hr</span>
                    <button
                      type="button"
                      disabled={editingLaborSaving}
                      onClick={() => saveEditLabor(line)}
                      className="h-8 px-2 text-xs font-semibold text-white bg-amber-600 rounded hover:bg-amber-700 disabled:opacity-60"
                    >
                      {editingLaborSaving ? '…' : 'Save'}
                    </button>
                    <button
                      type="button"
                      onClick={cancelEditLabor}
                      className="h-8 px-1.5 text-xs text-gray-600 hover:text-gray-900"
                    >
                      ✕
                    </button>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1">
                    <span className="font-medium">{parseFloat(line.hours).toFixed(2)} hr</span>
                    {canMutate && (
                      <button
                        type="button"
                        onClick={() => startEditLabor(line.id, 'hours', line.hours)}
                        className="text-amber-700 hover:text-amber-800"
                        aria-label="Edit hours"
                      >
                        <Pencil className="w-3 h-3" />
                      </button>
                    )}
                  </span>
                )}

                <span className="text-gray-400">×</span>

                {editingRate ? (
                  <span className="inline-flex items-center gap-1">
                    <span className="text-gray-500">$</span>
                    <input
                      type="text"
                      inputMode="decimal"
                      value={editingLaborValue}
                      onChange={(e) => setEditingLaborValue(e.target.value)}
                      className="w-20 h-8 px-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                      autoFocus
                    />
                    <span className="text-gray-500">/hr</span>
                    <button
                      type="button"
                      disabled={editingLaborSaving}
                      onClick={() => saveEditLabor(line)}
                      className="h-8 px-2 text-xs font-semibold text-white bg-amber-600 rounded hover:bg-amber-700 disabled:opacity-60"
                    >
                      {editingLaborSaving ? '…' : 'Save'}
                    </button>
                    <button
                      type="button"
                      onClick={cancelEditLabor}
                      className="h-8 px-1.5 text-xs text-gray-600 hover:text-gray-900"
                    >
                      ✕
                    </button>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1">
                    <span className="font-medium">${parseFloat(line.hourly_rate).toFixed(2)}/hr</span>
                    {canMutate && (
                      <button
                        type="button"
                        onClick={() => startEditLabor(line.id, 'rate', line.hourly_rate)}
                        className="text-amber-700 hover:text-amber-800"
                        aria-label="Edit hourly rate"
                      >
                        <Pencil className="w-3 h-3" />
                      </button>
                    )}
                  </span>
                )}

                <span className="text-gray-400">=</span>
                <span className="text-gray-500">${parseFloat(line.total_cost || '0').toFixed(2)}</span>
              </div>
            </>
          )
        }

        if (isLoading) {
          return <p className="text-sm text-gray-500">Loading…</p>
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
                          {parseFloat(line.hours).toFixed(2)} hr labor · {groupedParts.length} parts{partSavings > 0 ? ` · saves ${money(partSavings)}` : ''}
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
                          disabled
                          className="inline-flex w-full items-center justify-center gap-1 rounded-xl border border-dashed border-gray-300 px-3 py-2 text-sm font-semibold text-gray-400"
                        >
                          <Plus className="h-4 w-4" /> Add part to this operation
                        </button>
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
        {recommendedOpen && (
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
        <div className="relative mb-3 flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700">Parts {money(summary?.parts_total)}</span>
          <span className="rounded-full bg-orange-50 px-3 py-1 text-xs font-bold text-orange-700">Labor {money(summary?.labor_total)}</span>
          <span className="rounded-full bg-red-50 px-3 py-1 text-xs font-bold text-red-700">Discounts -{money(discountTotal)}</span>
          <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">Customer saves {money(customerSavesTotal)}</span>
          <button
            type="button"
            onClick={() => setDiscountsOpen((open) => !open)}
            disabled={!canMutate}
            className="ml-auto rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-bold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Discounts & pricing
          </button>
          {discountsOpen && (
            <div className="absolute bottom-full right-0 mb-2 w-[320px] rounded-[14px] border border-gray-200 bg-white p-4 shadow-[0_10px_30px_rgba(20,25,35,.10)]">
              <div className="mb-3 flex items-center justify-between">
                <p className="font-semibold text-gray-900">Discounts & pricing</p>
                <button type="button" onClick={() => setDiscountsOpen(false)} className="rounded-md p-1 text-gray-400 hover:bg-gray-100">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <label className="mb-3 block text-sm">
                <span className="mb-1 block text-xs font-bold uppercase tracking-wide text-gray-400">Parts pricing</span>
                <select
                  value={partsPricingMode}
                  disabled={pricingBusy}
                  onChange={(e) => { const v = e.target.value; if (v === 'stock' || v === 'list') applyPricingMode(v) }}
                  className="h-10 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm disabled:opacity-60"
                >
                  <option value="stock">Stock price</option>
                  <option value="list">List price</option>
                </select>
              </label>
              <label className="mb-3 flex items-center justify-between gap-3 text-sm">
                <span className="font-medium text-gray-700">Labor discount</span>
                <input
                  value={laborDiscount}
                  onChange={(e) => setLaborDiscount(e.target.value.replace(/[^0-9.]/g, ''))}
                  inputMode="decimal"
                  placeholder="0.00"
                  className="h-9 w-28 rounded-lg border border-gray-200 bg-white px-2 text-right font-['JetBrains_Mono',monospace] text-sm"
                />
              </label>
              <label className="mb-3 flex items-center justify-between gap-3 text-sm">
                <span className="font-medium text-gray-700">Order discount</span>
                <input
                  value={orderDiscount}
                  onChange={(e) => setOrderDiscount(e.target.value.replace(/[^0-9.]/g, ''))}
                  inputMode="decimal"
                  placeholder="0.00"
                  className="h-9 w-28 rounded-lg border border-gray-200 bg-white px-2 text-right font-['JetBrains_Mono',monospace] text-sm"
                />
              </label>
              <div className="flex items-center justify-between border-t border-gray-100 pt-3">
                <span className="text-xs font-semibold text-emerald-700">Customer saves {money(customerSavesTotal)}</span>
                <button
                  type="button"
                  onClick={async () => {
                    await saveDiscounts()
                    setDiscountsOpen(false)
                  }}
                  className="rounded-lg bg-orange-500 px-3 py-1.5 text-xs font-bold text-white"
                >
                  Apply
                </button>
              </div>
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => recalc.mutate()}
            disabled={!canMutate || recalc.isPending}
            className="inline-flex h-11 items-center gap-2 rounded-xl border border-gray-200 px-3 text-sm font-bold text-gray-700 disabled:opacity-50"
          >
            <RefreshCcw className="h-4 w-4" />
            Recalculate
          </button>
          <div className="ml-auto flex items-center gap-3">
            <div className="text-right">
              <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-gray-400">Order Total</p>
              <p className="font-['Barlow_Condensed',sans-serif] text-[34px] font-extrabold leading-none text-gray-950">{money(summary?.total_cost)}</p>
            </div>
            {!isInternalOrder && (
              <button
                type="button"
                disabled={!canMutate}
                className="inline-flex h-11 items-center gap-2 rounded-xl bg-orange-500 px-4 text-sm font-extrabold text-white shadow-[0_6px_16px_rgba(239,138,18,.32)] disabled:bg-gray-300"
              >
                <Plane className="h-4 w-4" />
                Send quote
              </button>
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
              <p className="mb-3 text-sm text-red-700">
                Cancel stops work without deleting history. Delete will permanently remove this order.
              </p>
              <div className="flex flex-wrap justify-end gap-2">
                <button
                  type="button"
                  disabled={cancelPending || deletePending || cancelDisabled}
                  onClick={onCancelOrder}
                  className="rounded-lg border border-red-200 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50"
                >
                  {cancelPending ? 'Cancelling...' : 'Cancel order'}
                </button>
                <button
                  type="button"
                  disabled={deletePending}
                  onClick={onDeleteOrder}
                  className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                >
                  {deletePending ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
