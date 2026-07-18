import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { Download, Settings, Trash2, Wrench, Plus, X, Check, Loader2, Sparkles } from 'lucide-react'
import SearchAddBar from '@/components/SearchAddBar'
import ViewToggle from '@/components/ViewToggle'
import BaseSelect from '@/components/BaseSelect'
import CurrencyInput from '@/components/CurrencyInput'
import QuantityStepper from '@/components/QuantityStepper'
import SuggestingTextarea from '@/components/SuggestingTextarea'
import SuggestingInput from '@/components/SuggestingInput'
import { useViewPreference } from '@/hooks/useViewPreference'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { getServiceStockStatus } from '@/utils/serviceStock'

interface ServicePart {
  id: string
  inventory_id: string
  sku: string
  name: string
  // Decimal on the backend (fluids use fractional amounts), so it serializes
  // over the wire as a string, same as unit_price/line_total.
  quantity: string
  // each | gallon | quart | liter — fluids are ordered in fractional amounts.
  unit_type?: string
  unit_price: string
  line_total: string
  stock_quantity: number
}

interface Service {
  id: string
  category_id: string | null
  name: string
  description: string | null
  duration_minutes: number
  base_price: string | null
  icon: string | null
  sort_order: number
  is_active: boolean
  requires_vehicle: boolean
  parts: ServicePart[]
  labor_cost: string
  parts_cost: string
  computed_total_price: string
}

interface ServiceCategory {
  id: string
  name: string
  description: string | null
  icon: string | null
  sort_order: number
  is_active: boolean
  is_pm: boolean
}

interface InventoryOption {
  id: string
  sku: string
  name: string
  selling_price: string
  stock_quantity: number
  // "each" or a fluid unit (gallon/quart/liter) — drives the add-part
  // stepper's decimal step for fluids.
  unit_type?: string
}

const serviceSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  duration_minutes: z.coerce.number().min(5, 'Min 5 minutes'),
  base_price: z.string().optional(),
  icon: z.string().optional(),
  category_id: z.string().optional(),
  requires_vehicle: z.boolean(),
  is_active: z.boolean(),
})

type ServiceFormData = z.infer<typeof serviceSchema>

// Fluids are dispensed in fractional amounts, so their quantity steppers move
// in quarter-unit increments and show the unit; discrete parts step by whole
// "each".
const FLUID_UNITS = new Set(['gallon', 'quart', 'liter'])
function unitStepConfig(unitType?: string): { step: number; min: number; unitLabel: string } {
  const u = (unitType || 'each').toLowerCase()
  if (FLUID_UNITS.has(u)) return { step: 0.25, min: 0.25, unitLabel: u === 'gallon' ? 'gal' : u === 'quart' ? 'qt' : 'L' }
  return { step: 1, min: 1, unitLabel: 'ea' }
}

export default function ServicesManagementPage() {
  const queryClient = useQueryClient()
  const [editingService, setEditingService] = useState<Service | null>(null)
  const [isAddingNew, setIsAddingNew] = useState(false)
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [showMenu, setShowMenu] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!showMenu) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false)
        setShowClearConfirm(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showMenu])
  const [viewMode, setViewMode] = useViewPreference('services')
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < 640 : false
  )
  const [searchQuery, setSearchQuery] = useState('')

  const formOpen = isAddingNew || !!editingService
  const iconOptions = ['🛠️', '🔧', '🧽', '🛢️', '🚗', '🚚', '🔋', '🧰', '⚙️', '✅']
  const [addingCategory, setAddingCategory] = useState(false)
  const [newCategoryName, setNewCategoryName] = useState('')
  const [newCategoryIsPm, setNewCategoryIsPm] = useState(false)
  const [categoryError, setCategoryError] = useState<string | null>(null)

  // Parts picker state (for editing an existing service)
  const [partPickerInventoryId, setPartPickerInventoryId] = useState('')
  // Snapshot of the chosen part: once the search resets, the refetched
  // (unsearched) inventory page may no longer contain it, so the select and
  // the add-part toast need a copy that outlives the current options page.
  const [pickedPart, setPickedPart] = useState<InventoryOption | null>(null)
  const [partPickerQty, setPartPickerQty] = useState(1)
  const [partError, setPartError] = useState<string | null>(null)

  // Server-side service search: typo-tolerant + relevance-ranked (shared
  // backend search semantics), debounced per keystroke.
  const debouncedServiceSearch = useDebouncedValue(searchQuery.trim(), 300)
  const { data: services, isLoading } = useQuery<Service[]>({
    queryKey: ['admin-services', debouncedServiceSearch],
    queryFn: async () => {
      const response = await api.get('/services', {
        params: {
          active_only: false,
          ...(debouncedServiceSearch ? { search: debouncedServiceSearch } : {}),
        },
      })
      return response.data
    },
    placeholderData: keepPreviousData,
  })

  const { data: categories } = useQuery<ServiceCategory[]>({
    queryKey: ['service-categories'],
    queryFn: async () => {
      const response = await api.get('/services/categories')
      return response.data
    },
  })

  // Server-side part search: the catalog can be far larger than one page
  // (limit is capped at 100), so the typed query must go to the backend —
  // client-side filtering of a truncated first page silently hides parts.
  const [partSearch, setPartSearch] = useState('')
  const debouncedPartSearch = useDebouncedValue(partSearch.trim(), 300)
  const { data: inventoryItems, isFetching: inventoryFetching } = useQuery<InventoryOption[]>({
    queryKey: ['inventory-options', debouncedPartSearch],
    queryFn: async () => {
      const response = await api.get('/inventory', {
        params: { limit: 100, ...(debouncedPartSearch ? { search: debouncedPartSearch } : {}) },
      })
      return response.data
    },
    placeholderData: keepPreviousData,
  })
  // Loading covers the debounce gap too — the moment the user types, before
  // the request even fires, results on screen are already stale.
  const partSearchLoading = partSearch.trim() !== debouncedPartSearch || inventoryFetching

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    getValues,
    trigger,
    formState: { errors },
  } = useForm<ServiceFormData>({
    resolver: zodResolver(serviceSchema),
    defaultValues: {
      duration_minutes: 60,
      base_price: '',
      requires_vehicle: true,
      is_active: true,
    },
  })
  const selectedIcon = watch('icon')

  const buildPayload = (data: ServiceFormData) => {
    const trimmedBase = (data.base_price || '').trim()
    const base_price_num = trimmedBase === '' ? null : Number(trimmedBase)
    return {
      name: data.name,
      description: data.description || null,
      duration_minutes: data.duration_minutes,
      icon: data.icon || null,
      category_id: data.category_id || null,
      requires_vehicle: data.requires_vehicle,
      is_active: data.is_active,
      base_price:
        base_price_num === null || Number.isNaN(base_price_num)
          ? null
          : base_price_num,
    }
  }

  const createMutation = useMutation({
    mutationFn: async (data: ServiceFormData) => {
      const response = await api.post('/services', buildPayload(data))
      return response.data as Service
    },
    onSuccess: (svc) => {
      queryClient.invalidateQueries({ queryKey: ['admin-services'] })
      // Transition into edit mode so the user can immediately add parts.
      setIsAddingNew(false)
      setEditingService(svc)
      toast.success(`${svc.name} created — add parts below if needed`)
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || 'Failed to create service')
    },
  })

  // Silent auto-save used while editing an existing service — persists the top
  // fields (name/labor/duration/etc.) as they change, like the parts already
  // do, so the panel has one consistent "just save it" model and no button.
  // It never closes the drawer or resets the form.
  const [autoSaveState, setAutoSaveState] = useState<'idle' | 'saving' | 'saved'>('idle')
  // After a save the green "saved" check lingers briefly then settles back to
  // the quiet "Changes save automatically" resting state.
  const savedRevertTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (savedRevertTimer.current) clearTimeout(savedRevertTimer.current) }, [])
  const autoSave = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: ServiceFormData }) => {
      const payload = buildPayload(data)
      const response = await api.put(`/services/${id}`, { ...payload, clear_base_price: payload.base_price === null })
      return response.data as Service
    },
    onMutate: () => {
      if (savedRevertTimer.current) clearTimeout(savedRevertTimer.current)
      setAutoSaveState('saving')
    },
    onSuccess: (svc) => {
      queryClient.invalidateQueries({ queryKey: ['admin-services'] })
      // Keep parts_cost / labor recompute in sync, but don't disturb the form.
      setEditingService((prev) => (prev && prev.id === svc.id ? svc : prev))
      setAutoSaveState('saved')
      savedRevertTimer.current = setTimeout(() => setAutoSaveState('idle'), 2500)
    },
    onError: (err: any) => {
      setAutoSaveState('idle')
      toast.error(err?.response?.data?.detail || 'Failed to save service')
    },
  })

  // Debounced field-level auto-save (edit mode only). Save on any single-field
  // change — whether from a registered input (info.type === 'change') or a
  // custom control that calls setValue (info.type is undefined but info.name is
  // still the field). The programmatic reset() that populates the form on open
  // fires with info.name === undefined, so opening a service never saves.
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!editingService) return
    const sub = watch((_value, info) => {
      if (!info?.name) return // ignore programmatic reset / initial population
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
      autoSaveTimer.current = setTimeout(async () => {
        if (!(await trigger())) return // don't persist invalid state (e.g. empty name)
        autoSave.mutate({ id: editingService.id, data: getValues() })
      }, 700)
    })
    return () => {
      sub.unsubscribe()
      if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
      // NB: don't clear savedRevertTimer here — onSuccess replaces editingService
      // with a fresh object, re-running this effect; clearing here would cancel
      // the fade-back before it fires. Its timer is cancelled on the next save
      // (onMutate) and on panel open instead.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingService])

  const preloadMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/services/preload')
      return response.data as { categories_added: number; services_added: number }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['admin-services'] })
      queryClient.invalidateQueries({ queryKey: ['service-categories'] })
      if (data.services_added === 0) {
        toast('Already up to date — no new services added')
      } else {
        toast.success(
          `Loaded ${data.services_added} service${data.services_added !== 1 ? 's' : ''} across ${data.categories_added} categor${data.categories_added !== 1 ? 'ies' : 'y'}`
        )
      }
    },
    onError: () => toast.error('Failed to load default services'),
  })

  const createCategoryMutation = useMutation({
    mutationFn: async (name: string) => {
      const trimmed = name.trim()
      if (!trimmed) throw new Error('Category name is required')
      const response = await api.post('/services/categories', {
        name: trimmed,
        sort_order: (categories?.length ?? 0) + 1,
        is_pm: newCategoryIsPm,
      })
      return response.data as ServiceCategory
    },
    onSuccess: (cat) => {
      queryClient.invalidateQueries({ queryKey: ['service-categories'] })
      setValue('category_id', cat.id, { shouldValidate: true })
      setNewCategoryName('')
      setNewCategoryIsPm(false)
      setAddingCategory(false)
      setCategoryError(null)
    },
    onError: (err: any) => {
      const message = err?.message || err?.response?.data?.detail || 'Failed to create category'
      setCategoryError(Array.isArray(message) ? message.join(', ') : message)
    },
  })

  const clearMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/services/clear')
      return response.data as { categories_deleted: number; services_deleted: number }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['admin-services'] })
      queryClient.invalidateQueries({ queryKey: ['service-categories'] })
      setShowClearConfirm(false)
      toast.success(`Cleared ${data.services_deleted} service${data.services_deleted !== 1 ? 's' : ''}`)
    },
    onError: () => toast.error('Failed to clear services'),
  })

  // AI-cleaned canonical version of this shop's repair-order description
  // history — powers the autocomplete suggestions in the RO work/complaint
  // field. Not part of the services catalog itself, but lives in the same
  // "catalog options" menu since it's a shop-owned reference list too.
  const regenerateDescriptionLibraryMutation = useMutation({
    mutationFn: async () => {
      await api.post('/repair-orders/description-library/regenerate')
    },
    onSuccess: () => {
      setShowMenu(false)
      toast.success('Refreshing RO suggestions in the background — this can take a few minutes for shops with a lot of history')
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || 'Failed to queue suggestion library refresh'),
  })

  const addPartMutation = useMutation({
    mutationFn: async (vars: { serviceId: string; inventoryId: string; quantity: number; partName: string }) => {
      const response = await api.post(`/services/${vars.serviceId}/parts`, {
        inventory_id: vars.inventoryId,
        quantity: vars.quantity,
      })
      return response.data as Service
    },
    onSuccess: (svc, vars) => {
      queryClient.invalidateQueries({ queryKey: ['admin-services'] })
      setEditingService(svc)
      setPartPickerInventoryId('')
      setPickedPart(null)
      setPartPickerQty(1)
      setPartError(null)
      toast.success(`Added ${vars.quantity}× ${vars.partName}`)
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || 'Failed to add part'
      setPartError(msg)
      toast.error(msg)
    },
  })

  const updatePartMutation = useMutation({
    mutationFn: async (vars: { serviceId: string; partId: string; quantity: number; partName: string }) => {
      const response = await api.put(`/services/${vars.serviceId}/parts/${vars.partId}`, { quantity: vars.quantity })
      return response.data as Service
    },
    onSuccess: (svc, vars) => {
      queryClient.invalidateQueries({ queryKey: ['admin-services'] })
      setEditingService(svc)
      toast.success(`${vars.partName} set to ${vars.quantity}×`)
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || 'Failed to update part'),
  })

  const deletePartMutation = useMutation({
    mutationFn: async (vars: { serviceId: string; partId: string; partName: string }) => {
      const response = await api.delete(`/services/${vars.serviceId}/parts/${vars.partId}`)
      return response.data as Service
    },
    onSuccess: (svc, vars) => {
      queryClient.invalidateQueries({ queryKey: ['admin-services'] })
      setEditingService(svc)
      toast.success(`Removed ${vars.partName}`)
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || 'Failed to remove part'),
  })

  const startEdit = (service: Service) => {
    setEditingService(service)
    setIsAddingNew(false)
    if (savedRevertTimer.current) clearTimeout(savedRevertTimer.current)
    setAutoSaveState('idle') // fresh panel — don't carry over the last service's "saved" check
    setPartError(null)
    setPartPickerInventoryId('')
    setPickedPart(null)
    setPartPickerQty(1)
    reset({
      name: service.name,
      description: service.description || '',
      duration_minutes: service.duration_minutes,
      base_price: service.base_price ?? '',
      icon: service.icon || '',
      category_id: service.category_id || '',
      requires_vehicle: service.requires_vehicle,
      is_active: service.is_active,
    })
  }

  const startAdd = () => {
    setIsAddingNew(true)
    setEditingService(null)
    setPartError(null)
    reset({
      name: '',
      description: '',
      duration_minutes: 60,
      base_price: '',
      icon: '',
      category_id: '',
      requires_vehicle: true,
      is_active: true,
    })
  }

  const cancelEdit = () => {
    setEditingService(null)
    setIsAddingNew(false)
    setPartError(null)
    reset()
  }

  const onSubmit = (data: ServiceFormData) => {
    // Editing auto-saves; a stray Enter just flushes the current values silently
    // (no drawer close). Only the create flow has an explicit submit.
    if (editingService) {
      autoSave.mutate({ id: editingService.id, data })
    } else {
      createMutation.mutate(data)
    }
  }

  useEffect(() => {
    if (typeof window === 'undefined') return
    const handleResize = () => setIsMobile(window.innerWidth < 640)
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Single-line inputs get a fixed 42px height to match BaseSelect's trigger, so
  // an input paired beside a dropdown lines up exactly. Multi-line (textarea)
  // fields pass includeHeight=false to keep their rows-based height.
  const drawerInputClasses = (hasError: boolean, includeHeight = true) => {
    const base =
      `w-full ${includeHeight ? 'h-[42px]' : ''} px-3 py-2 bg-white border rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 text-sm`
    return hasError ? `${base} border-red-500 focus:ring-red-500` : `${base} border-gray-200 focus:ring-amber-500`
  }

  const inventoryOptions = useMemo(() => {
    if (!inventoryItems) return []
    const attachedIds = new Set(editingService?.parts.map((p) => p.inventory_id) ?? [])
    const toOption = (item: InventoryOption) => ({
      value: item.id,
      label: `${item.name} (${item.sku})`,
      subLabel:
        item.stock_quantity === 0
          ? `$${Number(item.selling_price).toFixed(2)} ·`
          : `$${Number(item.selling_price).toFixed(2)} · ${item.stock_quantity} in stock`,
      // Zero-stock parts stay selectable (the bundle is a recipe, not a
      // reservation) but get called out so nobody is surprised later.
      ...(item.stock_quantity === 0
        ? { flag: { text: 'Out of stock', tone: 'danger' as const } }
        : {}),
    })
    const options = inventoryItems
      .filter((item) => !attachedIds.has(item.id))
      .map(toOption)
    // Keep the picked part visible even when the current (unsearched) page
    // no longer includes it, so the closed select can still show its label.
    // Skip while the user is actively searching for something else — the
    // injected row must not pollute unrelated search results.
    if (
      pickedPart &&
      !partSearch &&
      !attachedIds.has(pickedPart.id) &&
      !options.some((opt) => opt.value === pickedPart.id)
    ) {
      options.unshift(toOption(pickedPart))
    }
    return options
  }, [inventoryItems, editingService, pickedPart, partSearch])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  const activeViewMode = isMobile ? 'cards' : viewMode

  // Search happens server-side (typo-tolerant, relevance-ranked); a local
  // substring filter here would reject the server's fuzzy matches.
  const filteredServices = services

  const displayedPrice = (svc: Service) => Number(svc.computed_total_price)

  return (
    <div className="space-y-6 lg:flex lg:h-full lg:min-h-0 lg:flex-col lg:gap-4 lg:space-y-0">
      {/* Header */}
      <div className="mb-4 flex flex-row items-center gap-3 lg:mb-0 lg:flex-shrink-0">
        <div className="flex-1 min-w-0">
          <SearchAddBar
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Search services..."
            onAdd={startAdd}
            addLabel="Add Service"
            addLabelMobile="Add"
            className=""
            inputWidthClass="sm:min-w-[260px] md:max-w-lg"
            showAddButton={!isAddingNew && !editingService}
          />
        </div>
        <div className="relative shrink-0" ref={menuRef}>
          <button
            onClick={() => setShowMenu((v) => !v)}
            className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-gray-400 hover:text-gray-200 border border-white/15 transition-colors"
            title="Catalog options"
          >
            <Settings className="w-4 h-4" />
          </button>
          {showMenu && (
            <div className="absolute right-0 top-full mt-1 w-56 bg-[#1a2030] border border-white/15 rounded-lg shadow-xl z-50 overflow-hidden">
              {showClearConfirm ? (
                <div className="p-2 space-y-1">
                  <p className="text-xs text-gray-400 px-2 py-1">Clear all services?</p>
                  <button
                    onClick={() => clearMutation.mutate()}
                    disabled={clearMutation.isPending}
                    className="w-full text-left px-3 py-2 text-sm text-red-400 hover:bg-white/10 rounded-md disabled:opacity-50"
                  >
                    {clearMutation.isPending ? 'Clearing…' : 'Yes, clear all'}
                  </button>
                  <button
                    onClick={() => setShowClearConfirm(false)}
                    className="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-white/10 rounded-md"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <>
                  <button
                    onClick={() => {
                      preloadMutation.mutate()
                      setShowMenu(false)
                    }}
                    disabled={preloadMutation.isPending}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 disabled:opacity-50 whitespace-nowrap"
                  >
                    <Download className="w-3.5 h-3.5 shrink-0" />
                    {preloadMutation.isPending ? 'Loading…' : 'Load defaults'}
                  </button>
                  <button
                    onClick={() => regenerateDescriptionLibraryMutation.mutate()}
                    disabled={regenerateDescriptionLibraryMutation.isPending}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 disabled:opacity-50 whitespace-nowrap"
                    title="Rebuild repair-order description suggestions from your work-order history"
                  >
                    <Sparkles className="w-3.5 h-3.5 shrink-0" />
                    {regenerateDescriptionLibraryMutation.isPending ? 'Queuing…' : 'Refresh RO suggestions'}
                  </button>
                  <button
                    onClick={() => setShowClearConfirm(true)}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-red-400 hover:bg-white/10"
                  >
                    <Trash2 className="w-3.5 h-3.5 shrink-0" />
                    Clear all
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Services Table / Cards */}
      <div className="overflow-hidden rounded-xl border border-white/10 bg-white/5 lg:flex lg:min-h-0 lg:flex-1 lg:flex-col">
        <div className="hidden items-center justify-start border-b border-white/10 px-4 py-3 sm:flex lg:flex-shrink-0">
          <ViewToggle value={activeViewMode} onChange={setViewMode} disabled={isMobile} />
        </div>
        <div className="max-h-[calc(100vh-240px)] overflow-y-auto lg:min-h-0 lg:flex-1 lg:max-h-none">
          {activeViewMode === 'list' ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-white/5 border-b border-white/10">
                  <tr>
                    <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">Service</th>
                    <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3 hidden sm:table-cell">Category</th>
                    <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">Price</th>
                    <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3 hidden md:table-cell">Duration</th>
                    <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">Status</th>
                    <th className="text-right text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {filteredServices?.map((service) => {
                    const category = categories?.find((c) => c.id === service.category_id)
                    const stockStatus = getServiceStockStatus(service)
                    return (
                      <tr key={service.id} className="hover:bg-white/5">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span className="text-xl text-amber-200">
                              {service.icon ? <span>{service.icon}</span> : <Wrench className="w-5 h-5" />}
                            </span>
                            <div>
                              <div className="text-sm font-medium text-white flex items-center gap-2">
                                {stockStatus.dotClass && (
                                  <span
                                    className={`w-2 h-2 rounded-full ${stockStatus.dotClass} flex-shrink-0`}
                                    title={stockStatus.tooltip}
                                    aria-label={stockStatus.tooltip}
                                  />
                                )}
                                {service.name}
                              </div>
                              {service.description && (
                                <div className="text-xs text-gray-500 line-clamp-1">{service.description}</div>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 hidden sm:table-cell">
                          <span className="text-sm text-gray-400">{category?.name || '—'}</span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-col leading-tight">
                            <span className="text-sm font-medium text-amber-400">
                              ${displayedPrice(service).toFixed(2)}
                            </span>
                            {service.parts.length > 0 && (
                              <span className="text-[10px] uppercase tracking-wider text-gray-500">
                                labor + {service.parts.length} part{service.parts.length !== 1 ? 's' : ''}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 hidden md:table-cell">
                          <span className="text-sm text-gray-400">{service.duration_minutes} min</span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full ${
                              service.is_active
                                ? 'bg-green-500/20 text-green-400'
                                : 'bg-gray-500/20 text-gray-400'
                            }`}
                          >
                            <span className={`w-1.5 h-1.5 rounded-full ${service.is_active ? 'bg-green-400' : 'bg-gray-400'}`} />
                            {service.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => startEdit(service)}
                            className="text-amber-400 hover:text-amber-300 text-sm font-medium"
                          >
                            Edit
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                  {(!filteredServices || filteredServices.length === 0) && (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                        No services found. Add your first service above.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
              {filteredServices?.map((service) => {
                const category = categories?.find((c) => c.id === service.category_id)
                const stockStatus = getServiceStockStatus(service)
                return (
                  <div key={service.id} className="bg-white/10 border border-white/15 rounded-xl p-4 space-y-3">
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="text-xs uppercase text-gray-400">{category?.name || 'Uncategorized'}</div>
                        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                          <span className="text-xl">{service.icon || '🛠️'}</span>
                          {stockStatus.dotClass && (
                            <span
                              className={`w-2 h-2 rounded-full ${stockStatus.dotClass} flex-shrink-0`}
                              title={stockStatus.tooltip}
                              aria-label={stockStatus.tooltip}
                            />
                          )}
                          {service.name}
                        </h3>
                        <p className="text-xs text-gray-400 mt-1">{service.description || 'No description'}</p>
                      </div>
                      <span
                        className={`px-2 py-1 rounded-full text-xs font-semibold ${
                          service.is_active ? 'bg-green-500/20 text-green-300' : 'bg-gray-500/20 text-gray-300'
                        }`}
                      >
                        {service.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-sm text-gray-200">
                      <div>
                        <p className="text-gray-400 text-xs">Duration</p>
                        <p className="font-semibold">{service.duration_minutes} min</p>
                      </div>
                      <div>
                        <p className="text-gray-400 text-xs">Price</p>
                        <p className="font-semibold">${displayedPrice(service).toFixed(2)}</p>
                        {service.parts.length > 0 && (
                          <p className="text-[10px] uppercase tracking-wider text-gray-500">
                            labor + {service.parts.length} part{service.parts.length !== 1 ? 's' : ''}
                          </p>
                        )}
                      </div>
                      {service.parts.length > 0 && (
                        <div className="col-span-2">
                          <p className="text-gray-400 text-xs">Parts included</p>
                          <p className="text-xs text-gray-200">
                            {service.parts.map((p) => `${p.quantity}× ${p.name}`).join(', ')}
                          </p>
                        </div>
                      )}
                      <div className="col-span-2 flex items-center justify-between">
                        <span className="text-xs text-gray-400">Requires vehicle</span>
                        <span className="text-xs font-semibold text-gray-100">
                          {service.requires_vehicle ? 'Yes' : 'No'}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() => startEdit(service)}
                      className="w-full px-3 py-2 text-sm font-medium text-amber-200 bg-amber-500/10 border border-amber-400/40 rounded-lg hover:bg-amber-500/20 transition"
                    >
                      Edit
                    </button>
                  </div>
                )
              })}
              {(!filteredServices || filteredServices.length === 0) && (
                <div className="text-gray-400 text-sm col-span-full text-center">
                  No services found. Add your first service above.
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Slide-out Add/Edit Form */}
      {formOpen && (
        <div
          className={`fixed inset-0 z-[60] transition ${formOpen ? 'pointer-events-auto' : 'pointer-events-none'}`}
          aria-hidden={!formOpen}
        >
          <div
            className={`absolute inset-0 bg-black/50 transition-opacity ${formOpen ? 'opacity-100' : 'opacity-0'}`}
            onClick={cancelEdit}
          />
          <aside
            className={`absolute top-0 right-0 h-full w-full sm:w-[560px] bg-white/95 backdrop-blur border-l border-gray-200 shadow-xl transform transition-transform ${
              formOpen ? 'translate-x-0' : 'translate-x-full'
            }`}
            role="dialog"
            aria-label={editingService ? 'Edit Service' : 'Add Service'}
          >
            <form onSubmit={handleSubmit(onSubmit)} className="h-full flex flex-col">
              <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase text-gray-500 font-semibold">
                    {editingService ? 'Edit Service' : 'Add Service'}
                  </p>
                  <p className="text-lg font-semibold text-slate-800">
                    {editingService ? editingService.name : 'Create a new service'}
                  </p>
                  {editingService && (
                    <p className="text-sm font-semibold text-amber-600 mt-1">
                      ${Number(editingService.computed_total_price).toFixed(2)}
                      <span className="ml-2 text-xs font-normal text-gray-500">
                        labor ${Number(editingService.labor_cost).toFixed(2)}
                        {editingService.base_price !== null && (
                          <span className="text-amber-500"> (flat)</span>
                        )}
                        {' + '}parts ${Number(editingService.parts_cost).toFixed(2)}
                      </span>
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={cancelEdit}
                  className="p-2 text-gray-500 hover:text-amber-600 rounded-full hover:bg-amber-50"
                  aria-label="Close service form"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="p-5 space-y-5 overflow-y-auto flex-1">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Name</label>
                    <SuggestingInput
                      value={watch('name') || ''}
                      onChange={(val) => setValue('name', val, { shouldValidate: true })}
                      suggestUrl="/services/name-suggestions"
                      className={drawerInputClasses(!!errors.name)}
                      placeholder="Battery Test & Replacement"
                    />
                    {errors.name && <p className="mt-1 text-xs text-red-500">{errors.name.message}</p>}
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Category</label>
                    <input type="hidden" {...register('category_id')} />
                    <BaseSelect
                      options={(categories || []).map((c) => ({
                        value: c.id,
                        label: c.name,
                        subLabel: c.description || undefined,
                      }))}
                      value={watch('category_id') || ''}
                      onChange={(val) => setValue('category_id', val, { shouldValidate: true })}
                      placeholder="No Category"
                      allowAddNew
                      addNewLabel="+ New category"
                      onAddNew={() => {
                        setAddingCategory(true)
                        setCategoryError(null)
                      }}
                    />
                    {addingCategory && (
                      <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-2">
                        <p className="text-xs font-semibold text-gray-600 uppercase">New Category</p>
                        <input
                          type="text"
                          value={newCategoryName}
                          onChange={(e) => setNewCategoryName(e.target.value)}
                          placeholder="e.g. Electrical"
                          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                          autoFocus
                        />
                        {categoryError && (
                          <p className="text-xs text-red-600">{categoryError}</p>
                        )}
                        <label className="flex items-center gap-2 text-xs text-gray-700 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={newCategoryIsPm}
                            onChange={(e) => setNewCategoryIsPm(e.target.checked)}
                            className="rounded border-gray-300 text-amber-600 focus:ring-amber-500"
                          />
                          Preventive maintenance category (services here are offered on fleet PM work orders)
                        </label>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => createCategoryMutation.mutate(newCategoryName)}
                            disabled={!newCategoryName.trim() || createCategoryMutation.isPending}
                            className="px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-50"
                          >
                            {createCategoryMutation.isPending ? 'Adding…' : 'Add Category'}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setAddingCategory(false)
                              setNewCategoryName('')
                              setNewCategoryIsPm(false)
                              setCategoryError(null)
                            }}
                            className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-700 hover:bg-gray-100"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      Flat labor price ($)
                    </label>
                    <input type="hidden" {...register('base_price')} />
                    <CurrencyInput
                      value={watch('base_price') || ''}
                      onChange={(val) => setValue('base_price', val, { shouldValidate: true })}
                      placeholder="Leave empty to auto-calc"
                      step={1}
                    />
                    <p className="mt-1 text-[11px] text-gray-500">
                      Blank → labor = shop rate × duration. Bundled parts are always added on top.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Duration (minutes)</label>
                    <input type="hidden" {...register('duration_minutes')} />
                    <div className="pt-0.5">
                      <QuantityStepper
                        ariaLabel="Duration in minutes"
                        value={Number(watch('duration_minutes')) || 0}
                        onChange={(n) => setValue('duration_minutes', n, { shouldValidate: true })}
                        min={5}
                        step={15}
                        unitLabel="min"
                        align="start"
                      />
                    </div>
                    {errors.duration_minutes && (
                      <p className="mt-1 text-xs text-red-500">{errors.duration_minutes.message}</p>
                    )}
                  </div>

                  <div className="md:col-span-2">
                    <label className="block text-xs font-medium text-gray-500 mb-1">Icon (emoji)</label>
                    <input type="hidden" {...register('icon')} />
                    <div className="grid grid-cols-6 gap-2">
                      <button
                        type="button"
                        onClick={() => setValue('icon', '', { shouldValidate: true })}
                        className={`py-2 text-sm font-semibold rounded-lg border transition ${
                          !selectedIcon ? 'border-amber-400 bg-amber-50 text-amber-700' : 'border-gray-200 hover:border-amber-300'
                        }`}
                      >
                        None
                      </button>
                      {iconOptions.map((opt) => (
                        <button
                          key={opt}
                          type="button"
                          onClick={() => setValue('icon', opt, { shouldValidate: true })}
                          className={`py-2 text-lg rounded-lg border transition ${
                            selectedIcon === opt
                              ? 'border-amber-500 bg-amber-50 shadow-sm'
                              : 'border-gray-200 hover:border-amber-300'
                          }`}
                          aria-pressed={selectedIcon === opt}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Description</label>
                  <SuggestingTextarea
                    value={watch('description') || ''}
                    onChange={(val) => setValue('description', val, { shouldValidate: true })}
                    variant="light"
                    rows={2}
                    className={drawerInputClasses(false, false)}
                    placeholder="Service description..."
                  />
                </div>

                <div className="flex items-center gap-6">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      {...register('requires_vehicle')}
                      type="checkbox"
                      className="w-4 h-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
                    />
                    <span className="text-sm text-gray-600">Requires vehicle</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      {...register('is_active')}
                      type="checkbox"
                      className="w-4 h-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
                    />
                    <span className="text-sm text-gray-600">Active</span>
                  </label>
                </div>

                {/* Parts section — only enabled once service has an id */}
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold uppercase text-gray-600">Parts included</p>
                    {editingService && editingService.parts.length > 0 && (
                      <span className="text-xs font-semibold text-gray-700">
                        ${Number(editingService.parts_cost).toFixed(2)}
                      </span>
                    )}
                  </div>

                  {!editingService && (
                    <p className="text-xs text-gray-500">
                      Save the service first, then add bundled parts from inventory.
                    </p>
                  )}

                  {editingService && (
                    <>
                      {editingService.parts.length === 0 ? (
                        <p className="text-xs text-gray-500">No parts attached. Add batteries, filters, etc. below.</p>
                      ) : (
                        <div className="space-y-2">
                          {editingService.parts.map((part) => {
                            const unit = unitStepConfig(part.unit_type)
                            return (
                            <div
                              key={part.id}
                              className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-3 py-2"
                            >
                              <div className="min-w-0 flex-1">
                                <p className="text-sm font-medium text-gray-800 truncate">{part.name}</p>
                                <p className="text-xs text-gray-500">
                                  {part.sku} · ${Number(part.unit_price).toFixed(2)}/{unit.unitLabel}
                                  {part.stock_quantity === 0 ? (
                                    <span className="ml-1.5 font-semibold text-red-600">Out of stock</span>
                                  ) : part.stock_quantity < (parseFloat(part.quantity) || 0) ? (
                                    <span className="ml-1.5 font-semibold text-amber-600">
                                      Only {part.stock_quantity} in stock
                                    </span>
                                  ) : null}
                                </p>
                              </div>
                              <QuantityStepper
                                ariaLabel={`Quantity for ${part.name}`}
                                value={Number(part.quantity) || unit.min}
                                min={unit.min}
                                step={unit.step}
                                unitLabel={unit.unitLabel}
                                onChange={(qty) => {
                                  if (qty !== Number(part.quantity)) {
                                    updatePartMutation.mutate({
                                      serviceId: editingService.id,
                                      partId: part.id,
                                      quantity: qty,
                                      partName: part.name,
                                    })
                                  }
                                }}
                              />
                              <span className="w-20 text-right text-sm font-semibold text-gray-700">
                                ${Number(part.line_total).toFixed(2)}
                              </span>
                              <button
                                type="button"
                                onClick={() =>
                                  deletePartMutation.mutate({
                                    serviceId: editingService.id,
                                    partId: part.id,
                                    partName: part.name,
                                  })
                                }
                                className="p-1 text-gray-400 hover:text-red-600 rounded"
                                aria-label={`Remove ${part.name}`}
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                            )
                          })}
                        </div>
                      )}

                      <div className="rounded-lg border border-dashed border-gray-300 bg-white p-3 space-y-2">
                        <p className="text-xs font-semibold uppercase text-gray-600">Add part</p>
                        <BaseSelect
                          options={inventoryOptions}
                          value={partPickerInventoryId}
                          onChange={(val) => {
                            setPartPickerInventoryId(val)
                            // Re-selecting the snapshot-only entry must not wipe the
                            // snapshot: it may be absent from the current page.
                            const next =
                              inventoryItems?.find((i) => i.id === val) ??
                              (pickedPart?.id === val ? pickedPart : null)
                            setPickedPart(next)
                            // A fractional qty (fluid) doesn't fit a discrete part —
                            // snap it to a whole number when switching to "each".
                            const nextUnit = unitStepConfig(next?.unit_type)
                            if (nextUnit.step === 1 && !Number.isInteger(partPickerQty)) {
                              setPartPickerQty(Math.max(1, Math.round(partPickerQty)))
                            }
                          }}
                          onQueryChange={setPartSearch}
                          hideSelectedOption
                          loading={partSearchLoading}
                          placeholder={inventoryOptions.length || partSearch ? 'Pick from inventory…' : 'No parts left to add'}
                          disabled={inventoryOptions.length === 0 && !partSearch}
                        />
                        <div className="flex items-center gap-2">
                          <label className="text-xs text-gray-600">Qty</label>
                          {(() => {
                            // Fluids (gallon/quart/liter) step by 0.25 and accept typed
                            // decimals like 9.2; discrete parts stay whole-numbered.
                            const pickerUnit = unitStepConfig(pickedPart?.unit_type)
                            return (
                              <QuantityStepper
                                ariaLabel="Part quantity"
                                value={partPickerQty}
                                onChange={(n) => setPartPickerQty(Math.max(pickerUnit.min, n))}
                                min={pickerUnit.min}
                                step={pickerUnit.step}
                                unitLabel={pickedPart ? pickerUnit.unitLabel : ''}
                                align="start"
                              />
                            )
                          })()}
                          <button
                            type="button"
                            onClick={() => {
                              if (!partPickerInventoryId) return
                              const picked =
                                pickedPart?.id === partPickerInventoryId
                                  ? pickedPart
                                  : inventoryItems?.find((i) => i.id === partPickerInventoryId)
                              addPartMutation.mutate({
                                serviceId: editingService.id,
                                inventoryId: partPickerInventoryId,
                                quantity: partPickerQty,
                                partName: picked?.name || 'part',
                              })
                            }}
                            disabled={!partPickerInventoryId || addPartMutation.isPending}
                            className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-50"
                          >
                            <Plus className="w-3.5 h-3.5" />
                            Add
                          </button>
                        </div>
                        {partError && <p className="text-xs text-red-600">{partError}</p>}
                      </div>
                    </>
                  )}
                </div>
              </div>

              <div className="px-5 py-4 border-t border-gray-200 flex items-center justify-between gap-3">
                {/* Editing auto-saves — show a quiet status instead of a Save button.
                    Keyed by state so each swap replays the cross-fade. */}
                {editingService ? (
                  autoSaveState === 'saving' ? (
                    <span key="saving" className="animate-status-swap flex items-center gap-1.5 text-xs text-gray-500">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Saving…
                    </span>
                  ) : autoSaveState === 'saved' ? (
                    <span key="saved" className="animate-status-swap flex items-center gap-1.5 text-xs text-green-600">
                      <Check className="w-3.5 h-3.5" />
                      All changes saved
                    </span>
                  ) : (
                    <span key="idle" className="animate-status-swap text-xs text-gray-400">
                      Changes save automatically
                    </span>
                  )
                ) : (
                  <span />
                )}
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={cancelEdit}
                    className="px-5 py-2 bg-white/10 hover:bg-white/20 text-gray-700 rounded-lg text-sm font-medium"
                  >
                    {editingService ? 'Done' : 'Cancel'}
                  </button>
                  {!editingService && (
                    <button
                      type="submit"
                      disabled={createMutation.isPending}
                      className="px-5 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-400 text-white font-semibold rounded-lg text-sm"
                    >
                      {createMutation.isPending ? 'Creating…' : 'Create Service'}
                    </button>
                  )}
                </div>
              </div>
            </form>
          </aside>
        </div>
      )}
    </div>
  )
}
