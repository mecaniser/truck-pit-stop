import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { formatHoursMinutes } from '@/lib/durationFormat'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { Customer, RepairOrder, RepairOrderDetail, RepairOrderStatus, Service, Vehicle, PartsUsage, Labor, InventoryItem, Quote, Invoice, RecommendedService, RecommendedServicePriority } from '../../types'
import { format } from 'date-fns'
import { ArrowRight, Loader2, Plus, TriangleAlert, Trash2, OctagonX, Wrench, ChevronDown, ChevronUp, RotateCcw } from 'lucide-react'
import SlidePanel from '@/components/SlidePanel'
import YearPicker from '../../components/YearPicker'
import VehicleMakePicker from '../../components/VehicleMakePicker'
import CustomerSelect from '../../components/CustomerSelect'
import { customerDisplayName as customerNameOf } from '../../lib/customerName'
import { vehicleDisplayLabel } from '../../lib/vehicleName'
import { formatUSPhone } from '@/utils/phone'
import { getServiceStockStatus } from '@/utils/serviceStock'
import BaseSelect from '../../components/BaseSelect'
import QuantityStepper from '@/components/QuantityStepper'
import ViewToggle from '@/components/ViewToggle'
import { useViewPreference } from '@/hooks/useViewPreference'
import { useTheme } from '../../contexts/ThemeContext'
import { useWebSocket } from '../../hooks/useWebSocket'
import { useAuthStore } from '@/stores/authStore'
import PriceBuilderPanel from './PriceBuilderPanel'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'
import SuggestingInput from '@/components/SuggestingInput'
import SuggestingTextarea from '@/components/SuggestingTextarea'

interface NewCustomerForm {
  first_name: string
  last_name: string
  company_name: string
  email: string
  phone: string
  no_vehicle?: boolean
}

interface CreateCustomerPayload {
  first_name: string
  last_name: string
  company_name?: string | null
  email: string
  phone?: string | null
  no_vehicle?: boolean
}

interface NewVehicleForm {
  make: string
  model: string
  year: string
  vin: string
  license_plate: string
  mileage: string
}

type ApiErrorLike = {
  response?: {
    data?: {
      detail?: string
    }
  }
}

type ZelleModalMode = 'collect' | 'confirm_pending'

type ManualPaymentResponse = {
  status: string
  message: string
  warning?: string | null
}

const isWalkInPlaceholderCustomer = (customer?: Customer | null): boolean => {
  if (!customer) return false
  const email = (customer.email || '').toLowerCase()
  const firstName = (customer.first_name || '').toLowerCase()
  const source = (customer.source || '').toLowerCase()
  return firstName === 'walk-in' || email.includes('@placeholder.dieselbridge.network') || source === 'walk_in'
}

const truncateWithEllipsis = (value: string, maxLength = 36): string => {
  if (value.length <= maxLength) return value
  return `${value.slice(0, Math.max(0, maxLength - 3))}...`
}

const PRICE_BUILDER_STATUSES: RepairOrderStatus[] = [
  'draft',
  'quoted',
  'approved',
  'assigned',
  'acknowledged',
  'in_progress',
  'pending_review',
  'completed',
  'invoiced',
  'paid',
]
const LABOR_BREAKDOWN_STATUSES: RepairOrderStatus[] = ['pending_review', 'completed']
// Once invoiced/paid the order is a financial record — it can't be cancelled or
// deleted. Every other status can. (Mirror of the backend rule.)
const FINANCIALLY_PROTECTED_STATUSES: RepairOrderStatus[] = ['invoiced', 'paid']

function RepairOrderLaborBreakdown({
  laborItems,
  laborTotal,
  isLoading,
}: {
  laborItems: Labor[]
  laborTotal: string
  isLoading: boolean
}) {
  const formatMoney = (value: string) => (parseFloat(value || '0') || 0).toFixed(2)
  const formatHours = (value: string) => formatHoursMinutes(value)
  const formatLineType = (line: Labor) => {
    if (line.source_service_id) return 'service labor'
    return line.line_type.replace('_', ' ')
  }

  return (
    <div className="space-y-4 rounded-xl border border-gray-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">Labor Breakdown</h3>
          <p className="mt-1 text-xs text-gray-500">Recorded labor for this repair order.</p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-right">
          <p className="text-[11px] font-medium uppercase tracking-wide text-gray-400">Labor Total</p>
          <p className="text-base font-bold text-gray-900">${formatMoney(laborTotal)}</p>
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-500">Loading labor breakdown…</p>
      ) : laborItems.length > 0 ? (
        <div className="space-y-2">
          {laborItems.map((line) => (
            <div key={line.id} className="rounded-lg border border-gray-200 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900">{line.description || 'Labor line'}</p>
                  <p className="mt-1 text-xs text-gray-500">
                    {formatLineType(line)} · {formatHours(line.hours)} × ${formatMoney(line.hourly_rate)}/hr
                  </p>
                </div>
                <p className="text-sm font-semibold text-gray-900">${formatMoney(line.total_cost)}</p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-gray-500">No labor items recorded.</p>
      )}
    </div>
  )
}

export default function RepairOrdersPage() {
  const currentUser = useAuthStore((s) => s.user)
  const { accentColors } = useTheme()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()

  // Connect to WebSocket for real-time updates (cache/status refresh only on this page).
  useWebSocket()
  const [searchQuery, setSearchQuery] = useState('')
  const debouncedSearch = useDebouncedValue(searchQuery.trim(), 300)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const RO_PAGE_SIZE = 25
  const [page, setPage] = useState(0)
  // Reset to the first page whenever the search term or status filter changes.
  useEffect(() => { setPage(0) }, [debouncedSearch, statusFilter])
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('')
  const [selectedVehicleId, setSelectedVehicleId] = useState<string>('')
  const [showNewVehicleForm, setShowNewVehicleForm] = useState(false)
  const [description, setDescription] = useState('')
  const [mileageIn, setMileageIn] = useState('')
  const [serviceSearch, setServiceSearch] = useState('')
  const [selectedServiceIds, setSelectedServiceIds] = useState<string[]>([])
  // Inline stock-replenish state (keyed by inventory_id) for the new-RO modal's warning panel.
  const [replenishingId, setReplenishingId] = useState<string | null>(null)
  const [replenishValue, setReplenishValue] = useState<string>('')
  const [replenishSaving, setReplenishSaving] = useState(false)
  const [isDetailOpen, setIsDetailOpen] = useState(false)
  const [selectedOrder, setSelectedOrder] = useState<RepairOrder | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showDangerActions, setShowDangerActions] = useState(false)
  const [viewMode, setViewMode] = useViewPreference('repair_orders')
  const [isMobile, setIsMobile] = useState(false)
  const [newCustomer, setNewCustomer] = useState<NewCustomerForm>({
    first_name: '',
    last_name: '',
    company_name: '',
    email: '',
    phone: '',
  })
  const [newVehicle, setNewVehicle] = useState<NewVehicleForm>({
    make: '',
    model: '',
    year: '',
    vin: '',
    license_plate: '',
    mileage: '',
  })
  const [addPartInventoryId, setAddPartInventoryId] = useState('')
  const [addPartQuantity, setAddPartQuantity] = useState(1)
  const [addLaborDescription, setAddLaborDescription] = useState('')
  const [addLaborHours, setAddLaborHours] = useState('')
  const [addLaborRate, setAddLaborRate] = useState('100')
  const laborRateInitialized = useRef(false)
  const [showPartComposer, setShowPartComposer] = useState(false)
  const [customerSectionExpanded, setCustomerSectionExpanded] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showResendInvoice, setShowResendInvoice] = useState(false)
  const [resendCustomEmail, setResendCustomEmail] = useState('')
  const [showDeleteInvoiceConfirm, setShowDeleteInvoiceConfirm] = useState(false)
  const [showReassignMechanic, setShowReassignMechanic] = useState(false)
  const [reviewNotes, setReviewNotes] = useState('')
  const [mileageOut, setMileageOut] = useState('')
  const [showReviewNotes, setShowReviewNotes] = useState(false)
  const [invoiceDueDate, setInvoiceDueDate] = useState('')
  const [showInvoiceCreateOptions, setShowInvoiceCreateOptions] = useState(false)
  const [showInvoicePaymentOptions, setShowInvoicePaymentOptions] = useState(false)
  const [selectedPaymentMethod, setSelectedPaymentMethod] = useState<string>('')
  const [showZelleQrModal, setShowZelleQrModal] = useState(false)
  const [zelleModalMode, setZelleModalMode] = useState<ZelleModalMode>('collect')
  const [zelleSenderEmail, setZelleSenderEmail] = useState('')
  const [zelleSenderPhone, setZelleSenderPhone] = useState('')
  const [captureZelleSender, setCaptureZelleSender] = useState(false)
  const [showAmountBreakdown, setShowAmountBreakdown] = useState(false)
  const [showAddRecService, setShowAddRecService] = useState(false)
  const [recServiceForm, setRecServiceForm] = useState({ description: '', priority: 'soon' as RecommendedServicePriority, estimated_cost: '', notes: '' })

  const openZellePaymentModal = (mode: ZelleModalMode = 'collect') => {
    setShowInvoicePaymentOptions(false)
    setSelectedPaymentMethod('zelle')
    setZelleModalMode(mode)
    setCaptureZelleSender(mode === 'collect' ? isSelectedOrderWalkIn : false)
    setZelleSenderEmail('')
    setZelleSenderPhone('')
    setShowAmountBreakdown(false)
    setShowZelleQrModal(true)
  }

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 1024)
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])


  const activeViewMode = isMobile ? 'list' : viewMode

  const queryClient = useQueryClient()

  // Server-side pagination: one page at a time, with search + status pushed to
  // the API instead of loading every order and filtering in the browser.
  const orderPageKey = (p: number) =>
    ['repair-orders', { page: p, search: debouncedSearch, status: statusFilter }] as const
  const fetchOrderPage = async (p: number) => {
    const response = await api.get('/repair-orders', {
      params: {
        paginated: true,
        skip: p * RO_PAGE_SIZE,
        limit: RO_PAGE_SIZE,
        ...(statusFilter === 'deleted'
          ? { deleted: true }
          : statusFilter !== 'all'
            ? { status: statusFilter }
            : {}),
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
      },
    })
    return response.data as { items: RepairOrder[]; total: number; has_more: boolean }
  }
  const { data: orderPage, isLoading, isPlaceholderData, isFetching } = useQuery({
    queryKey: orderPageKey(page),
    queryFn: () => fetchOrderPage(page),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
  const orders = orderPage?.items
  const totalOrders = orderPage?.total ?? 0

  // Prefetch the next page once the current one settles, so paging forward feels
  // instant. Only when a next page exists and we're showing live (non-placeholder) data.
  useEffect(() => {
    if (orderPage?.has_more && !isPlaceholderData) {
      queryClient.prefetchQuery({
        queryKey: orderPageKey(page + 1),
        queryFn: () => fetchOrderPage(page + 1),
        staleTime: 30_000,
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, debouncedSearch, statusFilter, orderPage?.has_more, isPlaceholderData])

  // Handle ?new=true query param to auto-open create modal
  useEffect(() => {
    const newParam = searchParams.get('new')
    if (newParam === 'true') {
      setIsModalOpen(true)
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])

  const applyDetailState = (order: RepairOrder) => {
    setSelectedOrder(order)
    setIsDetailOpen(true)
    setQuoteSent(false)
    setShowReassignMechanic(false)
    setReviewNotes('')
    setShowReviewNotes(false)
    setShowDangerActions(false)
    setShowPartComposer(false)
    setAddPartInventoryId('')
    setAddPartQuantity(1)
  }

  const openDetail = (order: RepairOrder) => {
    // Rapid prev/next through the work queue (e.g. paging through 20+ orders
    // in a few seconds) was leaving every previous order's detail/price-build/
    // parts/quotes/invoices requests retrying in the background, each holding
    // its own rate-limit-budget-consuming backoff timer — that pile-up is what
    // tripped the 429s and left the panel stuck showing a loading placeholder
    // for the order actually on screen. Cancel the outgoing order's in-flight
    // queries so only the order you're actually looking at is still fetching.
    if (selectedOrder?.id && selectedOrder.id !== order.id) {
      queryClient.cancelQueries({ queryKey: ['repair-order-detail', selectedOrder.id] })
      queryClient.cancelQueries({ queryKey: ['price-build', selectedOrder.id] })
      queryClient.cancelQueries({ queryKey: ['price-build-parts', selectedOrder.id] })
      queryClient.cancelQueries({ queryKey: ['price-build-part-suggestions', selectedOrder.id] })
      queryClient.cancelQueries({ queryKey: ['quote', selectedOrder.id] })
      queryClient.cancelQueries({ queryKey: ['invoice-for-order', selectedOrder.id] })
      queryClient.cancelQueries({ queryKey: ['recommended-services', selectedOrder.id] })
    }
    applyDetailState(order)
    // Fresh open pushes ?selected= so Back/close return to the view underneath;
    // switching orders while open (prev/next, arrow keys) replaces the entry so
    // Back still exits to the origin instead of replaying every order viewed.
    setSearchParams({ selected: order.id }, { replace: isDetailOpen })
  }

  const clearDetailState = () => {
    setSelectedOrder(null)
    setIsDetailOpen(false)
    setQuoteSent(false)
    setShowDangerActions(false)
    setShowPartComposer(false)
    setAddPartInventoryId('')
    setAddPartQuantity(1)
    setInvoiceDueDate('')
    setShowInvoiceCreateOptions(false)
  }

  const closeDetail = () => {
    clearDetailState()
    if (!searchParams.get('selected')) return
    // Opened via in-app navigation: going back lands on whatever view launched
    // the panel (dashboard work queue or this list). A deep link / fresh tab
    // has no in-app history entry, so just strip the param and stay here.
    if (location.key !== 'default') {
      navigate(-1)
    } else {
      setSearchParams({}, { replace: true })
    }
  }

  // The ?selected= URL param is the source of truth for the detail panel: it
  // survives refresh, makes orders deep-linkable, and lets the dashboard work
  // queue open any order here. Resolve it from the loaded page when possible,
  // otherwise fetch directly — the order may be outside the current page
  // (e.g. an older completed order from the Ready to Close lane).
  useEffect(() => {
    const selectedId = searchParams.get('selected')
    if (!selectedId) {
      if (isDetailOpen) clearDetailState()
      return
    }
    if (selectedOrder?.id === selectedId) return
    const order = orders?.find(o => o.id === selectedId)
    if (order) {
      applyDetailState(order)
      return
    }
    let cancelled = false
    api.get(`/repair-orders/${selectedId}/detail`)
      .then((response) => {
        if (cancelled) return
        queryClient.setQueryData(['repair-order-detail', selectedId], response.data)
        applyDetailState(response.data as RepairOrder)
      })
      .catch(() => {
        if (cancelled) return
        toast.error("Couldn't open that repair order — it may have been deleted")
        setSearchParams({}, { replace: true })
      })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, orders, isDetailOpen, selectedOrder?.id])

  // The full customer / vehicle / service lists are only needed by the create
  // and edit forms — not to render the paginated list, which carries its own
  // denormalized customer/vehicle summaries. Load them lazily when a form opens.
  const needsFormData = isModalOpen || isDetailOpen

  const { data: customers, isLoading: isLoadingCustomers } = useQuery<Customer[]>({
    queryKey: ['customers'],
    queryFn: async () => {
      const pageSize = 100
      let skip = 0
      const all: Customer[] = []
      while (true) {
        const response = await api.get('/customers', { params: { paginated: true, skip, limit: pageSize } })
        const data = response.data
        all.push(...data.items)
        if (!data.has_more || data.items.length === 0) break
        skip = data.skip + data.limit
      }
      return all
    },
    enabled: needsFormData,
    // This pages through the whole tenant's customer list, so it's expensive
    // to redo on every drawer open. Mutations that add/edit a customer
    // explicitly invalidate this key, so a resting cache here is safe.
    staleTime: 5 * 60 * 1000,
  })

  // Fleet company name, so internal fleet ROs show the fleet operator (e.g.
  // "77 Cargo") as the customer instead of the generic house account.
  const { data: fleetSettings } = useQuery<{ fleet_company_name: string | null }>({
    queryKey: ['fleet-settings'],
    queryFn: async () => {
      const response = await api.get('/fleet/settings')
      return response.data
    },
  })

  const { data: vehicles } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: async () => {
      const pageSize = 100
      let skip = 0
      const all: Vehicle[] = []
      while (true) {
        const response = await api.get('/vehicles', { params: { paginated: true, skip, limit: pageSize } })
        const data = response.data
        all.push(...data.items)
        if (!data.has_more || data.items.length === 0) break
        skip = data.skip + data.limit
      }
      return all
    },
    enabled: needsFormData,
    // Same rationale as the customers query above — full-table fetch, so
    // avoid redoing it on every drawer open. Vehicle mutations invalidate it.
    staleTime: 5 * 60 * 1000,
  })

  const { data: services, refetch: refetchServices } = useQuery<Service[]>({
    queryKey: ['services'],
    queryFn: async () => {
      const pageSize = 100
      let skip = 0
      const all: Service[] = []
      while (true) {
        const response = await api.get('/services', { params: { paginated: true, skip, limit: pageSize } })
        const data = response.data
        all.push(...data.items)
        if (!data.has_more || data.items.length === 0) break
        skip = data.skip + data.limit
      }
      return all
    },
    // Stock can change in another tab (e.g. user replenished from the warning panel),
    // so refresh when the user comes back to this tab.
    refetchOnWindowFocus: true,
    enabled: needsFormData,
    staleTime: 60 * 1000,
  })

  const { data: mechanics } = useQuery<{ mechanic_id: string; mechanic_name: string; assigned_count?: number; in_progress_count?: number }[]>({
    queryKey: ['mechanics'],
    queryFn: async () => {
      const response = await api.get('/dashboard/stats')
      return response.data?.mechanic_workload || []
    },
  })

  const { data: orderDetail, refetch: refetchOrderDetail, isLoading: isOrderDetailLoading } = useQuery<RepairOrderDetail>({
    queryKey: ['repair-order-detail', selectedOrder?.id],
    queryFn: async () => {
      const response = await api.get(`/repair-orders/${selectedOrder!.id}/detail`)
      return response.data
    },
    enabled: !!(selectedOrder?.id && isDetailOpen),
  })

  const { data: inventory } = useQuery<InventoryItem[]>({
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
    enabled: isDetailOpen,
    // Stock levels move during a shift (parts added to other orders), so a
    // shorter window than customers/vehicles — but still avoids re-paging
    // the whole catalog every time a different order's drawer is opened.
    staleTime: 60 * 1000,
  })

  const { data: quoteForOrder, refetch: refetchQuote } = useQuery<Quote | null>({
    queryKey: ['quote', selectedOrder?.id],
    queryFn: async () => {
      const response = await api.get(`/quotes?repair_order_id=${selectedOrder!.id}`)
      return response.data
    },
    enabled: !!(selectedOrder?.id && isDetailOpen),
  })

  const { data: invoiceForOrder } = useQuery<Invoice | null>({
    queryKey: ['invoice-for-order', selectedOrder?.id],
    queryFn: async () => {
      const response = await api.get(`/invoices?repair_order_id=${selectedOrder!.id}`)
      const invoices = response.data
      return invoices.length > 0 ? invoices[0] : null
    },
    enabled: !!(selectedOrder?.id && isDetailOpen && ['invoiced', 'paid'].includes(selectedOrder?.status || '')),
  })

  const { data: recommendedServices, refetch: refetchRecServices } = useQuery<RecommendedService[]>({
    queryKey: ['recommended-services', selectedOrder?.id],
    queryFn: async () => {
      const response = await api.get(`/repair-orders/${selectedOrder!.id}/recommended-services`)
      return response.data
    },
    enabled: !!(selectedOrder?.id && isDetailOpen),
  })

  const addRecServiceMutation = useMutation({
    mutationFn: async (data: { description: string; priority: RecommendedServicePriority; estimated_cost?: number; notes?: string }) => {
      await api.post(`/repair-orders/${selectedOrder!.id}/recommended-services`, data)
    },
    onSuccess: () => {
      refetchRecServices()
      setShowAddRecService(false)
      setRecServiceForm({ description: '', priority: 'soon', estimated_cost: '', notes: '' })
    },
  })

  const resolveRecServiceMutation = useMutation({
    mutationFn: async (serviceId: string) => {
      await api.patch(`/repair-orders/${selectedOrder!.id}/recommended-services/${serviceId}`, { is_resolved: true })
    },
    onSuccess: () => refetchRecServices(),
  })

  const deleteRecServiceMutation = useMutation({
    mutationFn: async (serviceId: string) => {
      await api.delete(`/repair-orders/${selectedOrder!.id}/recommended-services/${serviceId}`)
    },
    onSuccess: () => refetchRecServices(),
  })

  const { data: zelleSettings } = useQuery<{ zelle_email: string | null; zelle_phone: string | null; zelle_qr_image: string | null }>({
    queryKey: ['zelle-settings'],
    queryFn: async () => {
      const response = await api.get('/admin/zelle-settings')
      return response.data
    },
    enabled: showZelleQrModal,
  })

  const { data: taxFeeSettings } = useQuery<{ labor_rate: number }>({
    queryKey: ['tax-fee-settings'],
    queryFn: async () => {
      const response = await api.get('/admin/tax-fee-settings')
      return response.data
    },
  })

  // Set default labor rate from tenant settings (only on initial load)
  useEffect(() => {
    if (taxFeeSettings?.labor_rate !== undefined && !laborRateInitialized.current) {
      setAddLaborRate(taxFeeSettings.labor_rate.toString())
      laborRateInitialized.current = true
    }
  }, [taxFeeSettings])

  useEffect(() => {
    setInvoiceDueDate('')
    setShowInvoiceCreateOptions(false)
  }, [selectedOrder?.id])

  const filteredVehicles = useMemo(() => {
    if (!vehicles) return []
    if (selectedCustomerId) {
      return vehicles.filter((v) => v.customer_id === selectedCustomerId)
    }
    return []
  }, [vehicles, selectedCustomerId])

  // Seed the lookups from each order's denormalized customer/vehicle summary so
  // list rows render without loading the full customer/vehicle tables. When the
  // full lists are loaded (e.g. the create/edit modal is open) those richer
  // objects take precedence.
  const customerLookup = useMemo(() => {
    const map = new Map<string, Partial<Customer>>()
    orders?.forEach((o) => {
      if (o.customer_id && !map.has(o.customer_id)) {
        map.set(o.customer_id, {
          id: o.customer_id,
          first_name: o.customer_first_name ?? '',
          last_name: o.customer_last_name ?? '',
          company_name: o.customer_company_name ?? null,
          email: o.customer_email ?? null,
          phone: o.customer_phone ?? null,
        } as Partial<Customer>)
      }
    })
    customers?.forEach((c) => map.set(c.id, c))
    return map as Map<string, Customer>
  }, [orders, customers])

  const vehicleLookup = useMemo(() => {
    const map = new Map<string, Partial<Vehicle>>()
    orders?.forEach((o) => {
      if (o.vehicle_id && !map.has(o.vehicle_id)) {
        map.set(o.vehicle_id, {
          id: o.vehicle_id,
          make: o.vehicle_make,
          model: o.vehicle_model,
          year: o.vehicle_year,
          unit_number: o.vehicle_unit_number,
          vin: o.vehicle_vin,
        } as Partial<Vehicle>)
      }
    })
    vehicles?.forEach((v) => map.set(v.id, v))
    return map as Map<string, Vehicle>
  }, [orders, vehicles])

  const mechanicLookup = useMemo(() => {
    const map = new Map<string, string>()
    mechanics?.forEach((m) => map.set(m.mechanic_id, m.mechanic_name))
    return map
  }, [mechanics])

  const selectedOrderCustomer = selectedOrder ? customerLookup.get(selectedOrder.customer_id) : undefined
  const selectedOrderVehicle = selectedOrder ? vehicleLookup.get(selectedOrder.vehicle_id) : undefined
  const isSelectedOrderWalkIn = isWalkInPlaceholderCustomer(selectedOrderCustomer)
  // Display name for the selected order's customer. Internal fleet ROs resolve
  // to the fleet company name; otherwise the customer's company name (primary),
  // falling back to their personal name.
  const customerDisplayName = selectedOrder?.is_internal
    ? (fleetSettings?.fleet_company_name || 'Internal Fleet')
    : customerNameOf(selectedOrderCustomer)
  const paymentCustomerName = customerDisplayName

  // Display name for an order in a list row: fleet company for internal ROs,
  // else the customer's company name (primary) / personal name (fallback).
  const orderCustomerName = (order: RepairOrder, customer?: Customer | null, fallback = '—'): string =>
    order.is_internal
      ? (fleetSettings?.fleet_company_name || 'Internal Fleet')
      : customerNameOf(customer, fallback)
  const paymentCompanyName = selectedOrderCustomer?.company_name || 'No company on file'
  const paymentCompanyNameShort = truncateWithEllipsis(paymentCompanyName, 34)
  const paymentTruckUnit = selectedOrderVehicle?.unit_number || 'No unit number'
  const paymentVehicleLabel = selectedOrderVehicle
    ? vehicleDisplayLabel({ ...selectedOrderVehicle, unit_number: null })
    : 'Vehicle info unavailable'

  const parseServiceNotes = (notes?: string | null) => {
    if (!notes) return null
    try {
      const parsed = JSON.parse(notes)
      if (Array.isArray(parsed?.selected_services)) {
        return parsed.selected_services as { id: string; name: string; base_price: string }[]
      }
    } catch (err) {
      console.warn('Failed to parse service notes', err)
    }
    return null
  }

  const getErrorDetail = (error: unknown, fallback: string) => {
    const detail = (error as ApiErrorLike)?.response?.data?.detail
    return typeof detail === 'string' && detail.trim() ? detail : fallback
  }

  const parseMoney = (value: string | number | null | undefined): number => {
    if (typeof value === 'number') return Number.isFinite(value) ? value : 0
    const parsed = Number(value ?? 0)
    return Number.isFinite(parsed) ? parsed : 0
  }

  const formatMoney = (value: string | number | null | undefined): string => {
    return `$${parseMoney(value).toFixed(2)}`
  }

  const canEditPriceBuilderByRole = ['garage_owner', 'garage_admin', 'receptionist'].includes(currentUser?.role || '')
  const showLegacyPriceEditor = false
  const detailStatus = (orderDetail ?? selectedOrder)?.status ?? null
  const showPriceBuilder = detailStatus ? PRICE_BUILDER_STATUSES.includes(detailStatus) : false
  const priceBuilderOwnsShell = showPriceBuilder
  const showLaborBreakdown = detailStatus ? LABOR_BREAKDOWN_STATUSES.includes(detailStatus) : false
  // Internal fleet work orders (e.g. PMs) carry their parts & labor throughout
  // the job, not just in draft/quoted. Surface — and keep editable — the line
  // items for internal orders across active statuses so the owner can see and
  // adjust the work (oil, filters, labor) while it's in progress. Internal ROs
  // freeze only once completed/invoiced/paid/cancelled.
  const isInternalOrder = !!(orderDetail ?? selectedOrder)?.is_internal
  const INTERNAL_FROZEN_STATUSES: RepairOrderStatus[] = ['completed', 'invoiced', 'paid', 'cancelled']
  const showInternalLineItems = isInternalOrder && detailStatus != null && !INTERNAL_FROZEN_STATUSES.includes(detailStatus)
  // An order can be cancelled/deleted at any status except once it's a financial
  // record (invoiced/paid), which must stay in history. So the danger zone is
  // available everywhere except those two states (internal orders never reach them).
  const showDangerZone = detailStatus != null && !FINANCIALLY_PROTECTED_STATUSES.includes(detailStatus)
  const invoiceOptionSummary = useMemo(() => {
    if (invoiceDueDate) {
      const parsed = new Date(`${invoiceDueDate}T00:00:00`)
      return Number.isNaN(parsed.getTime()) ? `Due ${invoiceDueDate}` : `Due ${format(parsed, 'MMM d, yyyy')}`
    }
    return 'Defaults: due today.'
  }, [invoiceDueDate])

  const createCustomerMutation = useMutation({
    mutationFn: async (payload: CreateCustomerPayload) => {
      const response = await api.post('/customers', payload)
      return response.data as Customer
    },
  })

  const createVehicleMutation = useMutation({
    mutationFn: async ({ customer_id, data }: { customer_id: string; data: NewVehicleForm }) => {
      const payload = {
        make: data.make.trim(),
        model: data.model.trim(),
        year: data.year ? Number(data.year) : null,
        vin: data.vin.trim() || null,
        license_plate: data.license_plate.trim() || null,
        color: null,
        mileage: data.mileage ? Number(data.mileage) : null,
        notes: null,
      }
      // Use nested endpoint under customer
      const response = await api.post(`/customers/${customer_id}/vehicles`, payload)
      return response.data as Vehicle
    },
  })

  const createRepairOrderMutation = useMutation({
    mutationFn: async ({
      customer_id,
      vehicle_id,
      description: roDescription,
      internal_notes,
      mileage_in,
    }: { customer_id: string; vehicle_id: string; description: string; internal_notes?: string | null; mileage_in?: number | null }) => {
      const response = await api.post('/repair-orders', {
        customer_id,
        vehicle_id,
        description: roDescription || null,
        internal_notes: internal_notes || null,
        mileage_in: mileage_in ?? null,
      })
      return response.data as RepairOrder
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to create repair order'))
    },
  })

  const cancelRepairOrderMutation = useMutation({
    mutationFn: async (orderId: string) => {
      const response = await api.put(`/repair-orders/${orderId}`, { status: 'cancelled' })
      return response.data as RepairOrder
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      setSelectedOrder(updated)
      toast.success(`Repair order ${updated.order_number} — Status: Cancelled`)
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to cancel repair order'))
    },
  })

  // Delete/restore/reopen change whether an order shows on the owner's floor
  // board and dashboard, not just the RO lists — invalidate those too so the
  // board updates without a manual reload.
  //
  // refetchType: 'all' is essential here. The cockpit (DashboardHome) is
  // *unmounted* while the RO drawer is open, so its ['dashboard-stats'] query is
  // inactive — and a default invalidate only refetches *active* queries. It would
  // just mark the data stale, and because that query sets refetchOnMount:false it
  // would then serve the stale cache on the way back, still showing the order we
  // just deleted. Forcing a refetch of inactive queries too keeps the board honest.
  const invalidateOrderBoards = () => {
    for (const key of [
      'repair-orders',
      'customerRepairOrders',
      'dashboard-stats',
      'mechanic-board-team',
      'mechanic-board-detail',
      'fleet-board-summary',
    ]) {
      queryClient.invalidateQueries({ queryKey: [key], refetchType: 'all' })
    }
  }

  const deleteRepairOrderMutation = useMutation({
    mutationFn: async (orderId: string) => {
      await api.delete(`/repair-orders/${orderId}`)
      return orderId
    },
    onSuccess: (orderId) => {
      invalidateOrderBoards()
      if (selectedOrder?.id === orderId) {
        closeDetail()
      }
      toast.success('Repair order deleted')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to delete repair order'))
    },
  })

  const restoreRepairOrderMutation = useMutation({
    mutationFn: async (orderId: string) => {
      const response = await api.post(`/repair-orders/${orderId}/restore`)
      return response.data as RepairOrder
    },
    onSuccess: (updated) => {
      invalidateOrderBoards()
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.id] })
      queryClient.invalidateQueries({ queryKey: ['price-build', updated.id] })
      setSelectedOrder(updated)
      toast.success(`Repair order ${updated.order_number} restored`)
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to restore repair order'))
    },
  })

  // Reopen a completed internal fleet WO back to in_progress so more work can be added.
  const reopenWorkOrderMutation = useMutation({
    mutationFn: async (orderId: string) => {
      const response = await api.post(`/repair-orders/${orderId}/reopen`)
      return response.data as RepairOrder
    },
    onSuccess: (updated) => {
      invalidateOrderBoards()
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.id] })
      queryClient.invalidateQueries({ queryKey: ['price-build', updated.id] })
      setSelectedOrder(updated)
      toast.success(`Reopened ${updated.order_number} — add work below`)
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to reopen work order'))
    },
  })

  const assignMechanicMutation = useMutation({
    mutationFn: async ({ orderId, mechanicId }: { orderId: string; mechanicId: string; orderStatus?: string }) => {
      // Use dedicated endpoint for all assignment/reassignment actions so mechanic notifications are sent.
      if (mechanicId) {
        const response = await api.post(`/repair-orders/${orderId}/assign-mechanic`, { mechanic_id: mechanicId })
        return response.data as RepairOrder
      }
      // Fallback to generic update only for unassigning.
      const response = await api.put(`/repair-orders/${orderId}`, { assigned_mechanic_id: mechanicId || null })
      return response.data as RepairOrder
    },
    onSuccess: (updated, variables) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.id] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      setSelectedOrder(updated)
      toast.success(variables.mechanicId ? 'Technician assigned and notified' : 'Technician unassigned')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to assign technician'))
    },
  })

  const startWorkOrderMutation = useMutation({
    mutationFn: async (orderId: string) => {
      const response = await api.post(`/fleet/work-orders/${orderId}/start`)
      return response.data as RepairOrder
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.id] })
      queryClient.invalidateQueries({ queryKey: ['fleet-board'] })
      setSelectedOrder(updated)
      toast.success('Work order in progress')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to start work order'))
    },
  })

  const completeWorkOrderMutation = useMutation({
    mutationFn: async ({ orderId, mileageOut: woOut }: { orderId: string; mileageOut?: number | null }) => {
      const response = await api.post(`/fleet/work-orders/${orderId}/complete`, { mileage_out: woOut ?? null })
      return response.data as RepairOrder
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.id] })
      queryClient.invalidateQueries({ queryKey: ['fleet-board'] })
      setSelectedOrder(updated)
      toast.success('Work order completed')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to complete work order'))
    },
  })

  const approveCompletionMutation = useMutation({
    mutationFn: async ({ orderId, reviewNotes, mileageOut }: { orderId: string; reviewNotes?: string; mileageOut?: number | null }) => {
      const response = await api.post(`/repair-orders/${orderId}/approve-completion`, {
        review_notes: reviewNotes || null,
        mileage_out: mileageOut ?? null,
      })
      return response.data as RepairOrder
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.id] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      setSelectedOrder(updated)
      toast.success('Work approved - Customer notified')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to approve completion'))
    },
  })

  const createInvoiceMutation = useMutation({
    mutationFn: async ({
      repairOrderId,
      dueDate,
    }: {
      repairOrderId: string
      dueDate?: string
    }) => {
      const response = await api.post('/invoices', { 
        repair_order_id: repairOrderId,
        due_date: dueDate || null,
      })
      return response.data
    },
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      // Refetch the order to get updated status
      if (selectedOrder?.id) {
        queryClient.invalidateQueries({ queryKey: ['repair-order-detail', selectedOrder.id] })
        // Update local state to reflect new status
        setSelectedOrder(prev => prev ? { ...prev, status: 'invoiced' } : null)
      }
      setInvoiceDueDate('')
      setShowInvoiceCreateOptions(false)
      toast.success('Invoice created and sent to customer')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to create invoice'))
    },
  })

  const recordManualPaymentMutation = useMutation({
    mutationFn: async ({
      invoiceId,
      method,
      notes,
      zelleSenderEmail,
      zelleSenderPhone,
      updateCustomerFromSender,
    }: {
      invoiceId: string
      method: string
      notes?: string
      zelleSenderEmail?: string
      zelleSenderPhone?: string
      updateCustomerFromSender?: boolean
    }) => {
      const response = await api.post('/payments/record-manual', { 
        invoice_id: invoiceId,
        method,
        notes,
        zelle_sender_email: zelleSenderEmail || null,
        zelle_sender_phone: zelleSenderPhone || null,
        update_customer_from_sender: !!updateCustomerFromSender,
      })
      return response.data as ManualPaymentResponse
    },
    onSuccess: async (data) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['customers'] })
      if (selectedOrder?.id) {
        queryClient.invalidateQueries({ queryKey: ['repair-order-detail', selectedOrder.id] })
        setSelectedOrder(prev => prev ? { ...prev, status: 'paid' } : null)
      }
      setShowInvoicePaymentOptions(false)
      setSelectedPaymentMethod('')
      setShowZelleQrModal(false)
      setZelleSenderEmail('')
      setZelleSenderPhone('')
      setCaptureZelleSender(false)
      toast.success('Payment recorded successfully')
      if (data?.warning) {
        toast(data.warning, { icon: '⚠️' })
      }
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to record payment'))
    },
  })

  const clearPendingZelleMutation = useMutation({
    mutationFn: async ({ invoiceId }: { invoiceId: string }) => {
      const response = await api.post('/payments/zelle-pending/revert', {
        invoice_id: invoiceId,
      })
      return response.data as { status: string; message: string }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-for-order', selectedOrder?.id] })
      toast.success(data.message || 'Pending Zelle status cleared')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to clear pending Zelle status'))
    },
  })

  const resendInvoiceMutation = useMutation({
    mutationFn: async ({ invoiceId, customEmail }: { invoiceId: string; customEmail?: string }) => {
      const response = await api.post(`/invoices/${invoiceId}/resend`, { 
        custom_email: customEmail || null 
      })
      return response.data
    },
    onSuccess: (data) => {
      toast.success(data.message || 'Invoice resent successfully')
      setShowResendInvoice(false)
      setResendCustomEmail('')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to resend invoice'))
    },
  })

  const deleteInvoiceMutation = useMutation({
    mutationFn: async (invoiceId: string) => {
      await api.delete(`/invoices/${invoiceId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-for-order'] })
      setSelectedOrder(prev => prev ? { ...prev, status: 'completed' } : null)
      toast.success('Invoice deleted. You can now recreate it.')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to delete invoice'))
    },
  })

  const updateServicesMutation = useMutation({
    mutationFn: async ({ orderId, selectedServices }: { orderId: string; selectedServices: { id: string; name: string; base_price: string }[] }) => {
      const internal_notes = selectedServices.length > 0
        ? JSON.stringify({ selected_services: selectedServices })
        : null
      const response = await api.put(`/repair-orders/${orderId}`, { internal_notes })
      return response.data as RepairOrder
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.id] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      setSelectedOrder(updated)
    },
  })

  const addPartMutation = useMutation({
    mutationFn: async ({ orderId, inventory_id, quantity }: { orderId: string; inventory_id: string; quantity: number }) => {
      const response = await api.post(`/repair-orders/${orderId}/parts`, { inventory_id, quantity })
      return response.data as PartsUsage
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', vars.orderId] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      refetchOrderDetail()
    },
  })

  const removePartMutation = useMutation({
    mutationFn: async ({ orderId, partsUsageId }: { orderId: string; partsUsageId: string }) => {
      await api.delete(`/repair-orders/${orderId}/parts/${partsUsageId}`)
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', vars.orderId] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      refetchOrderDetail()
    },
  })

  const addLaborMutation = useMutation({
    mutationFn: async ({
      orderId,
      description,
      hours,
      hourly_rate,
    }: { orderId: string; description: string; hours: number; hourly_rate: number }) => {
      const response = await api.post(`/repair-orders/${orderId}/labor`, { description, hours, hourly_rate })
      return response.data as Labor
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', vars.orderId] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      refetchOrderDetail()
    },
  })

  const removeLaborMutation = useMutation({
    mutationFn: async ({ orderId, laborId }: { orderId: string; laborId: string }) => {
      await api.delete(`/repair-orders/${orderId}/labor/${laborId}`)
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', vars.orderId] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      refetchOrderDetail()
    },
  })

  const createQuoteMutation = useMutation({
    mutationFn: async (repair_order_id: string) => {
      const response = await api.post('/quotes', { repair_order_id })
      return response.data as Quote
    },
    onSuccess: (quote, orderId) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['quote', orderId] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', orderId] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      refetchQuote()
      refetchOrderDetail()
      setSelectedOrder((prev) => (prev && prev.id === orderId ? { ...prev, status: 'quoted' } : prev))
      toast.success(`Quote ${quote.quote_number} draft ready`)
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to create quote'))
    },
  })

  const updateQuoteMutation = useMutation({
    mutationFn: async (quoteId: string) => {
      const response = await api.put(`/quotes/${quoteId}`)
      return response.data as Quote
    },
    onSuccess: (quote) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      if (selectedOrder?.id) {
        queryClient.invalidateQueries({ queryKey: ['quote', selectedOrder.id] })
        queryClient.invalidateQueries({ queryKey: ['repair-order-detail', selectedOrder.id] })
        refetchQuote()
        refetchOrderDetail()
      }
      toast.success(`Quote ${quote.quote_number} updated — $${parseFloat(quote.total_amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}`)
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to update quote'))
    },
  })

  const sendQuoteMutation = useMutation({
    mutationFn: async (quoteId: string) => {
      const response = await api.post(`/quotes/${quoteId}/send`)
      return response.data as Quote
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      if (selectedOrder?.id) {
        queryClient.invalidateQueries({ queryKey: ['quote', selectedOrder.id] })
        refetchQuote()
      }
      setQuoteSent(true)
      toast.success('Quote sent — Awaiting customer approval')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to send quote'))
    },
  })

  const [quoteSent, setQuoteSent] = useState(false)

  // Status filter and search are applied server-side now, so the rendered list
  // is simply the current page returned by the API.
  const filteredOrders = orders

  // Keyboard left/right arrow navigation between orders when detail panel is open
  useEffect(() => {
    if (!isDetailOpen || !filteredOrders || !selectedOrder) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
      const target = e.target as HTMLElement
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable) return
      const idx = filteredOrders.findIndex(o => o.id === selectedOrder.id)
      let next: RepairOrder | null = null
      if (e.key === 'ArrowLeft' && idx > 0) next = filteredOrders[idx - 1]
      if (e.key === 'ArrowRight' && idx >= 0 && idx < filteredOrders.length - 1) next = filteredOrders[idx + 1]
      if (next) {
        openDetail(next)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDetailOpen, filteredOrders, selectedOrder])

  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <h1 className="text-xl sm:text-2xl font-bold text-white mb-4 flex-shrink-0">Repair Orders</h1>

        <div className="mb-4 flex-shrink-0 bg-white/10 backdrop-blur rounded-xl p-4">
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="relative flex-1 min-w-0">
              <svg
                className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                placeholder="Search by order # or description..."
                disabled
                className="w-full h-10 pl-10 pr-4 bg-white rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none disabled:opacity-60"
              />
            </div>
            <button
              type="button"
              disabled
              className="inline-flex items-center gap-2 h-10 px-4 rounded-lg text-sm font-semibold text-white opacity-60 shrink-0"
              style={{ backgroundColor: accentColors[600] }}
            >
              <Plus className="w-4 h-4" />
              <span className="hidden sm:inline">Add Repair Order</span>
              <span className="sm:hidden">Add</span>
            </button>
          </div>
        </div>

        <div className="flex-1 min-h-0 flex flex-col bg-white/5 border border-white/10 rounded-xl overflow-hidden">
          <div className="hidden lg:flex flex-shrink-0 items-center justify-between gap-4 px-4 py-3 border-b border-white/10">
            <div className="h-7 w-32 bg-white/10 rounded-lg animate-pulse" />
            <div className="flex items-center gap-2 text-sm text-white/50">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading repair orders…
            </div>
          </div>
          <div className="flex-1 min-h-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-white/5 text-white/70 text-xs uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Order #</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3 text-left font-medium hidden sm:table-cell">Description</th>
                  <th className="px-4 py-3 text-left font-medium hidden md:table-cell">Customer</th>
                  <th className="px-4 py-3 text-left font-medium hidden lg:table-cell">Vehicle</th>
                  <th className="px-4 py-3 text-right font-medium hidden xl:table-cell">Total</th>
                  <th className="px-4 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {[...Array(12)].map((_, i) => (
                  <tr key={i} className="animate-pulse">
                    <td className="px-4 py-3"><div className="h-4 bg-white/10 rounded w-20" /></td>
                    <td className="px-4 py-3"><div className="h-5 bg-white/10 rounded-full w-20" /></td>
                    <td className="px-4 py-3 hidden sm:table-cell"><div className="h-4 bg-white/10 rounded w-40" /></td>
                    <td className="px-4 py-3 hidden md:table-cell"><div className="h-4 bg-white/10 rounded w-32" /></td>
                    <td className="px-4 py-3 hidden lg:table-cell"><div className="h-4 bg-white/10 rounded w-28" /></td>
                    <td className="px-4 py-3 hidden xl:table-cell"><div className="h-4 bg-white/10 rounded w-16 ml-auto" /></td>
                    <td className="px-4 py-3"><div className="h-4 bg-white/10 rounded w-10 ml-auto" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    )
  }

  // Navigation state for prev/next browsing in the detail panel
  const navigationOrders = filteredOrders ?? []
  const currentNavIndex = selectedOrder
    ? navigationOrders.findIndex(o => o.id === selectedOrder.id)
    : -1
  const showNavigation = navigationOrders.length > 1 && currentNavIndex >= 0
  const hasPrev = currentNavIndex > 0
  const hasNext = currentNavIndex >= 0 && currentNavIndex < navigationOrders.length - 1
  const quoteActionPending = createQuoteMutation.isPending || updateQuoteMutation.isPending || sendQuoteMutation.isPending
  const quoteOrder = orderDetail ?? selectedOrder
  const quoteOrderStatus = quoteOrder?.status
  const quoteIsApproved = !!quoteForOrder?.is_approved
  const quoteIsSent = !!(quoteForOrder?.sent_to_customer || quoteSent)
  const quoteCanChange = !!quoteOrderStatus && ['draft', 'quoted'].includes(quoteOrderStatus)
  const quoteTotalMismatch = !!quoteForOrder && !!quoteOrder && !quoteIsApproved && (
    Math.abs((parseFloat(quoteForOrder.total_amount || '0') || 0) - (parseFloat(quoteOrder.total_cost || '0') || 0)) > 0.005
  )
  const effectiveQuoteNeedsUpdate = !!quoteForOrder && !quoteIsApproved && quoteTotalMismatch
  const quoteActionLabel = quoteIsApproved
    ? 'Quote approved'
    : quoteForOrder
      ? quoteIsSent
        ? (effectiveQuoteNeedsUpdate ? 'Resend quote' : 'Awaiting approval')
        : 'Send quote'
        : 'Create quote'
  const quoteActionDisabled = quoteIsApproved || !quoteCanChange || (quoteIsSent && !effectiveQuoteNeedsUpdate)
  const quoteDisabledReason = quoteIsApproved
    ? 'The customer has already approved this quote. Pricing and quote sending are locked so the team can complete the approved work.'
    : !quoteCanChange
      ? 'Quote changes are only available before the customer approves the work.'
      : quoteIsSent && !effectiveQuoteNeedsUpdate
        ? 'The quote has been sent to the customer. The button will re-enable if pricing changes require a resend.'
        : undefined
  const priceBuilderHistoryEvents = (() => {
    const order = orderDetail ?? selectedOrder
    if (!order) return []
    const events: Array<{ id: string; label: string; at: string; detail?: string; actor?: string }> = []
    const push = (event: { id: string; label: string; at?: string | null; detail?: string; actor?: string }) => {
      if (!event.at) return
      events.push({ id: event.id, label: event.label, at: event.at, detail: event.detail, actor: event.actor })
    }
    const customerActor = customerDisplayName || selectedOrderCustomer?.company_name || selectedOrderCustomer?.email || undefined
    const assignedTechnician = order.assigned_mechanic_id
      ? mechanicLookup.get(order.assigned_mechanic_id) || 'Assigned technician'
      : undefined

    push({
      id: 'created',
      label: 'Repair order created',
      at: order.created_at,
      detail: order.order_number,
      actor: customerActor,
    })
    push({
      id: 'quote-created',
      label: 'Quote draft created',
      at: quoteForOrder?.created_at,
      detail: quoteForOrder?.quote_number,
    })
    push({
      id: 'quote-sent',
      label: 'Quote sent to customer',
      at: quoteForOrder?.sent_at,
      detail: quoteForOrder?.quote_number,
      actor: customerActor,
    })
    push({
      id: 'quote-approved',
      label: 'Quote approved',
      at: quoteForOrder?.is_approved ? quoteForOrder.updated_at : null,
      detail: quoteForOrder?.quote_number,
      actor: customerActor,
    })
    push({
      id: 'assigned',
      label: 'Technician assigned',
      at: order.assigned_at,
      actor: assignedTechnician,
    })
    push({
      id: 'acknowledged',
      label: 'Technician acknowledged work',
      at: order.acknowledged_at,
      actor: assignedTechnician,
    })
    push({
      id: 'started',
      label: 'Work started',
      at: order.work_started_at,
      actor: assignedTechnician,
    })
    push({
      id: 'completed',
      label: 'Technician completed work',
      at: order.work_completed_at,
      actor: assignedTechnician,
    })
    push({
      id: 'invoiced',
      label: 'Invoice created',
      at: invoiceForOrder?.created_at,
      detail: invoiceForOrder?.invoice_number,
    })
    push({
      id: 'zelle-pending',
      label: 'Customer marked Zelle payment sent',
      at: invoiceForOrder?.zelle_pending_submitted_at,
      detail: invoiceForOrder?.invoice_number,
      actor: customerActor,
    })
    push({
      id: 'paid',
      label: 'Payment recorded',
      at: invoiceForOrder?.paid_at,
      detail: invoiceForOrder?.invoice_number,
    })
    push({
      id: 'cancelled',
      label: 'Order cancelled',
      at: order.cancelled_at,
      actor: order.cancelled_by_name || undefined,
    })
    push({
      id: 'deleted',
      label: 'Order deleted',
      at: order.deleted_at,
      actor: order.deleted_by_name || undefined,
    })

    return events.sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime())
  })()
  const handlePriceBuilderQuoteAction = async () => {
    if (!selectedOrder?.id || quoteActionPending || quoteActionDisabled) return
    if (!quoteForOrder) {
      createQuoteMutation.mutate(selectedOrder.id)
      return
    }
    try {
      if (effectiveQuoteNeedsUpdate) {
        const updatedQuote = await updateQuoteMutation.mutateAsync(quoteForOrder.id)
        if (quoteIsSent) {
          await sendQuoteMutation.mutateAsync(updatedQuote.id)
        } else {
          await sendQuoteMutation.mutateAsync(updatedQuote.id)
          setQuoteSent(true)
        }
        return
      }
      sendQuoteMutation.mutate(quoteForOrder.id)
      setQuoteSent(true)
    } catch {
      // Mutation handlers surface the error toast; keep the click handler from throwing.
    }
  }

  const getStatusStyle = (status: string) => {
    const styles: Record<string, { bg: string; text: string; dot: string }> = {
      draft: { bg: 'bg-gray-100', text: 'text-gray-700', dot: 'bg-gray-400' },
      quoted: { bg: 'bg-blue-100', text: 'text-blue-700', dot: 'bg-blue-500' },
      declined: { bg: 'bg-red-100', text: 'text-red-700', dot: 'bg-red-500' },
      approved: { bg: 'bg-green-100', text: 'text-green-700', dot: 'bg-green-500' },
      assigned: { bg: 'bg-amber-100', text: 'text-amber-700', dot: 'bg-amber-500' },
      acknowledged: { bg: 'bg-cyan-100', text: 'text-cyan-700', dot: 'bg-cyan-500' },
      in_progress: { bg: 'bg-yellow-100', text: 'text-yellow-700', dot: 'bg-yellow-500' },
      on_hold: { bg: 'bg-orange-100', text: 'text-orange-700', dot: 'bg-orange-500' },
      pending_review: { bg: 'bg-orange-100', text: 'text-orange-700', dot: 'bg-orange-500' },
      completed: { bg: 'bg-purple-100', text: 'text-purple-700', dot: 'bg-purple-500' },
      invoiced: { bg: 'bg-indigo-100', text: 'text-indigo-700', dot: 'bg-indigo-500' },
      paid: { bg: 'bg-emerald-100', text: 'text-emerald-700', dot: 'bg-emerald-500' },
      cancelled: { bg: 'bg-red-100', text: 'text-red-700', dot: 'bg-red-500' },
    }
    return styles[status] || styles.draft
  }

  const resolveOrderDisplayStatus = (order: Pick<RepairOrder, 'status' | 'quote_sent' | 'pending_zelle_confirmation' | 'hold_reason'>) => {
    const isAwaitingApproval = order.status === 'quoted' && !!order.quote_sent
    const isPendingZelle = !!order.pending_zelle_confirmation && order.status !== 'paid'
    const isOnHold = order.status === 'in_progress' && !!order.hold_reason
    if (isAwaitingApproval) {
      return {
        label: 'Awaiting Approval',
        style: { bg: 'bg-amber-100', text: 'text-amber-700', dot: 'bg-amber-500' },
      }
    }
    if (isPendingZelle) {
      return {
        label: 'Pending Zelle',
        style: { bg: 'bg-yellow-100', text: 'text-yellow-800', dot: 'bg-yellow-500' },
      }
    }
    if (isOnHold) {
      return {
        label: 'On Hold',
        style: getStatusStyle('on_hold'),
      }
    }
    return {
      label: order.status.replace(/_/g, ' '),
      style: getStatusStyle(order.status),
    }
  }

  const shortOrderNumber = (n?: string | null) => {
    if (!n) return '#—'
    const parts = n.split('-')
    return '#' + (parts[parts.length - 1] ?? n)
  }

  const statusDescriptions: Record<string, string> = {
    draft:          'New orders that have not been quoted yet.',
    quoted:         'Quote sent to the customer — awaiting their approval.',
    declined:       'Customer declined the quote — needs revision before resending.',
    approved:       'Customer approved the quote — ready to assign a technician.',
    assigned:       'Technician has been assigned — awaiting their acknowledgment.',
    acknowledged:   'Technician acknowledged the job — starting work soon.',
    in_progress:    'Work is actively underway on the vehicle.',
    pending_review: 'Technician finished — waiting on admin to verify and approve the work.',
    completed:      'Work approved — invoice needs to be sent to the customer.',
    invoiced:       'Invoice sent — waiting on payment from the customer.',
    paid:           'Payment received — order fully closed.',
    cancelled:      'Orders that were cancelled and are no longer active.',
    deleted:        'Deleted orders — restore to bring one back.',
  }

  const canViewDeletedOrders = ['garage_owner', 'garage_admin'].includes(currentUser?.role || '')

  const statusOptions = [
    { value: 'all', label: 'All' },
    { value: 'draft', label: 'Draft' },
    { value: 'quoted', label: 'Quoted' },
    { value: 'declined', label: 'Declined' },
    { value: 'approved', label: 'Approved' },
    { value: 'assigned', label: 'Assigned' },
    { value: 'acknowledged', label: 'Acknowledged' },
    { value: 'in_progress', label: 'In Progress' },
    { value: 'pending_review', label: 'Pending Review' },
    { value: 'completed', label: 'Completed' },
    { value: 'invoiced', label: 'Invoiced' },
    { value: 'paid', label: 'Paid' },
    { value: 'cancelled', label: 'Cancelled' },
    ...(canViewDeletedOrders ? [{ value: 'deleted', label: 'Deleted' }] : []),
  ]

  const resetModal = () => {
    setSelectedCustomerId('')
    setSelectedVehicleId('')
    setShowNewVehicleForm(false)
    setDescription('')
    setMileageIn('')
    setServiceSearch('')
    setSelectedServiceIds([])
    setNewCustomer({ first_name: '', last_name: '', company_name: '', email: '', phone: '' })
    setNewVehicle({ make: '', model: '', year: '', vin: '', license_plate: '', mileage: '' })
  }

  const openModal = () => {
    resetModal()
    setIsModalOpen(true)
  }

  const closeModal = () => {
    setIsModalOpen(false)
    resetModal()
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)

    try {
      let finalCustomerId = selectedCustomerId
      let finalVehicleId = selectedVehicleId
      const isNewCustomer = selectedCustomerId === 'add_new'

      // New customer flow
      if (isNewCustomer) {
        if (!newCustomer.first_name.trim() || !newCustomer.last_name.trim() || !newCustomer.email.trim()) {
          toast.error('New customer requires first name, last name, and email')
          return
        }
        const createdCustomer = await createCustomerMutation.mutateAsync({
          first_name: newCustomer.first_name.trim(),
          last_name: newCustomer.last_name.trim(),
          company_name: newCustomer.company_name.trim() || null,
          email: newCustomer.email.trim(),
          phone: newCustomer.phone.trim(),
          // Customer is created before vehicle in this flow.
          // Explicitly allow customer creation without an inline initial_vehicle payload.
          no_vehicle: true,
        })
        finalCustomerId = createdCustomer.id
      } else if (!finalCustomerId) {
        toast.error('Select a customer or create a new one')
        return
      }

      // Vehicle selection can override customer
      const shouldCreateVehicle = isNewCustomer || showNewVehicleForm || !selectedVehicleId

      if (shouldCreateVehicle) {
        if (!finalCustomerId) {
          toast.error('A customer is required to add a vehicle')
          return
        }
        if (!newVehicle.make.trim() || !newVehicle.model.trim()) {
          toast.error('New vehicle requires make and model')
          return
        }
        const createdVehicle = await createVehicleMutation.mutateAsync({
          customer_id: finalCustomerId,
          data: newVehicle,
        })
        finalVehicleId = createdVehicle.id
        finalCustomerId = createdVehicle.customer_id
      } else {
        const vehicle = vehicles?.find((v) => v.id === selectedVehicleId)
        if (!vehicle) {
          toast.error('Selected vehicle not found')
          return
        }
        finalVehicleId = vehicle.id
        finalCustomerId = vehicle.customer_id
      }

      if (!finalCustomerId || !finalVehicleId) {
        toast.error('Customer and vehicle are required')
        return
      }

      const selectedServiceText = services
        ?.filter((svc) => selectedServiceIds.includes(svc.id))
        .map((svc) => svc.name)
        .join(' • ')

      const selectedServicePayload = services
        ?.filter((svc) => selectedServiceIds.includes(svc.id))
        .map((svc) => ({
          id: svc.id,
          name: svc.name,
        })) || []

      const combinedDescription = [selectedServiceText, description.trim()].filter(Boolean).join(' — ')

      const createdOrder = await createRepairOrderMutation.mutateAsync({
        customer_id: finalCustomerId,
        vehicle_id: finalVehicleId,
        description: combinedDescription,
        internal_notes: null,
        mileage_in: mileageIn.trim() === '' ? null : Number(mileageIn),
      })

      if (selectedServicePayload.length > 0) {
        // Apply sequentially so a stock-failure on one service doesn't abort the rest,
        // and so we can surface a per-service reason to the user.
        const failures: { name: string; reason: string }[] = []
        for (const svc of selectedServicePayload) {
          try {
            await api.post(`/repair-orders/${createdOrder.id}/price-build/flat-service`, {
              service_id: svc.id,
              quantity: 1,
            })
          } catch (err) {
            console.error(`Failed to apply service "${svc.name}" to price builder`, err)
            failures.push({ name: svc.name, reason: getErrorDetail(err, 'could not be applied') })
          }
        }
        if (failures.length > 0) {
          const detail = failures.map((f) => `${f.name}: ${f.reason}`).join('; ')
          toast.error(`Repair order created, but ${failures.length} service line${failures.length > 1 ? 's' : ''} failed — ${detail}`)
        }
      }

      let createdQuoteNumber: string | null = null
      try {
        const quoteResponse = await api.post('/quotes', { repair_order_id: createdOrder.id })
        createdQuoteNumber = quoteResponse.data?.quote_number || null
      } catch (err: unknown) {
        // Keep order creation successful even if quote draft creation fails.
        console.error('Failed to auto-create quote draft', err)
      }

      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['quote', createdOrder.id] })
      queryClient.invalidateQueries({ queryKey: ['customers'] })
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      if (createdQuoteNumber) {
        toast.success(`Repair order ${createdOrder.order_number} created — Quote ${createdQuoteNumber} ready to send`)
      } else {
        toast.success(`Repair order ${createdOrder.order_number} created`)
      }
      closeModal()
    } catch (err: unknown) {
      toast.error(getErrorDetail(err, 'Failed to create repair order'))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <h1 className="text-xl sm:text-2xl font-bold text-white mb-4 flex-shrink-0">Repair Orders</h1>

      {/* Search + Filters */}
      <div className="mb-4 flex-shrink-0 bg-white/10 backdrop-blur rounded-xl p-4">
        {/* Search + Add — inline */}
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="relative flex-1 min-w-0">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search by order # or description..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full h-10 pl-10 pr-4 bg-white rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>
          <button
            type="button"
            onClick={openModal}
            className="inline-flex items-center gap-2 h-10 px-4 rounded-lg text-sm font-semibold text-white transition-colors shrink-0"
            style={{ backgroundColor: accentColors[600] }}
          >
            <Plus className="w-4 h-4" />
            <span className="hidden sm:inline">Add Repair Order</span>
            <span className="sm:hidden">Add</span>
          </button>
        </div>

        {/* Filters — below search on all sizes */}
        {/* < sm: compact select */}
        <select
          className="sm:hidden mt-3 h-10 px-3 rounded-lg text-sm font-medium bg-white/20 text-white w-full border-0 outline-none"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          {statusOptions.map((option) => (
            <option key={option.value} value={option.value} className="text-gray-900 bg-white">
              {option.label}
            </option>
          ))}
        </select>

        {/* sm+: single-row horizontal scroll pills */}
        <div className="hidden sm:flex mt-3 overflow-x-auto gap-2 scrollbar-hide pb-0.5">
          {statusOptions.map((option) => (
            <button
              key={option.value}
              onClick={() => setStatusFilter(option.value)}
              className={`h-9 px-3 rounded-lg text-sm font-medium transition-colors whitespace-nowrap flex-shrink-0 ${
                statusFilter === option.value
                  ? 'text-white'
                  : 'bg-white/20 text-white hover:bg-white/30 active:bg-white/40'
              }`}
              style={statusFilter === option.value ? { backgroundColor: accentColors[500] } : undefined}
            >
              {option.label}
            </button>
          ))}
        </div>

        {(searchQuery || statusFilter !== 'all') && (
          <div className="mt-2 text-sm text-white/70">
            Found {totalOrders} order{totalOrders !== 1 ? 's' : ''}
          </div>
        )}
      </div>

      <div className="flex-1 min-h-0 flex flex-col bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        {/* Header with ViewToggle */}
        <div className="hidden lg:flex flex-shrink-0 items-center justify-between gap-4 px-4 py-3 border-b border-white/10">
          <div className="flex items-center gap-4">
            <ViewToggle value={activeViewMode} onChange={setViewMode} disabled={isMobile} />
            {statusFilter !== 'all' && statusDescriptions[statusFilter] && (
              <p className="text-xs text-white/50 italic">{statusDescriptions[statusFilter]}</p>
            )}
          </div>
        </div>

        <div className="flex-1 min-h-0 scrollbar-dark relative" style={{ overflowY: isDetailOpen ? 'hidden' : 'auto' }}>
          {/* Loading overlay for page/search/filter changes (first load uses the
              skeleton; this covers subsequent batch fetches). */}
          {isFetching && !isLoading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-blueNoir-900/40 backdrop-blur-[1px] pointer-events-none">
              <Loader2 className="w-6 h-6 text-white/80 animate-spin" />
            </div>
          )}
          {isMobile ? (
            /* Mobile: compact list cards */
            <div className="divide-y divide-white/10">
              {filteredOrders?.map((order) => {
                const { label: displayStatus, style: statusStyle } = resolveOrderDisplayStatus(order)
                const parsedServices = parseServiceNotes(order.internal_notes)
                const serviceTotal = parsedServices?.reduce(
                  (sum, svc) => sum + (parseFloat(svc.base_price || '0') || 0),
                  0
                ) || 0
                const backendParts = parseFloat(order.total_parts_cost ?? '0') || 0
                const backendLabor = parseFloat(order.total_labor_cost ?? '0') || 0
                const laborTotal = serviceTotal > 0 ? serviceTotal : backendLabor
                const displayTotal = backendParts + laborTotal
                const customer = customerLookup.get(order.customer_id)
                const vehicle = vehicleLookup.get(order.vehicle_id)
                return (
                  <div
                    key={order.id}
                    onClick={() => openDetail(order)}
                    className="flex items-center gap-3 px-4 py-3 cursor-pointer active:bg-white/5 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-white font-mono text-xs font-semibold">{shortOrderNumber(order.order_number)}</span>
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${statusStyle.bg} ${statusStyle.text}`}>
                          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${statusStyle.dot}`}></span>
                          {displayStatus}
                        </span>
                      </div>
                      <p className="text-white/50 text-xs truncate">
                        {orderCustomerName(order, customer, '')}
                        {vehicle && ` · ${vehicleDisplayLabel(vehicle)}`}
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-white text-sm font-semibold">
                        ${displayTotal.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                      </div>
                      <div className="text-white/40 text-xs">{format(new Date(order.created_at), 'MMM d')}</div>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : activeViewMode === 'list' ? (
            /* Desktop List View */
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-white/5 text-white/70 text-xs uppercase tracking-wider">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">Order #</th>
                    <th className="px-4 py-3 text-left font-medium">Status</th>
                    <th className="px-4 py-3 text-left font-medium hidden sm:table-cell">Description</th>
                    <th className="px-4 py-3 text-left font-medium hidden md:table-cell">Customer</th>
                    <th className="px-4 py-3 text-left font-medium hidden lg:table-cell">Vehicle</th>
                    <th className="px-4 py-3 text-right font-medium hidden xl:table-cell">Total</th>
                    <th className="px-4 py-3 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/10">
                  {filteredOrders?.map((order) => {
                    const { label: displayStatus, style: statusStyle } = resolveOrderDisplayStatus(order)
                    const parsedServices = parseServiceNotes(order.internal_notes)
                    const serviceTotal = parsedServices?.reduce(
                      (sum, svc) => sum + (parseFloat(svc.base_price || '0') || 0),
                      0
                    ) || 0
                    const backendParts = parseFloat(order.total_parts_cost ?? '0') || 0
                    const backendLabor = parseFloat(order.total_labor_cost ?? '0') || 0
                    const laborTotal = serviceTotal > 0 ? serviceTotal : backendLabor
                    const displayTotal = backendParts + laborTotal
                    const customer = customerLookup.get(order.customer_id)
                    const vehicle = vehicleLookup.get(order.vehicle_id)

                    return (
                      <tr
                        key={order.id}
                        onClick={() => openDetail(order)}
                        className="hover:bg-white/5 cursor-pointer transition-colors"
                      >
                        <td className="px-4 py-3">
                          <span className="text-white font-mono text-xs">{order.order_number}</span>
                          {order.is_internal && (
                            <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide bg-amber-500/15 text-amber-300">
                              Internal
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium whitespace-nowrap ${statusStyle.bg} ${statusStyle.text}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${statusStyle.dot}`}></span>
                            {displayStatus}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-white/70 hidden sm:table-cell max-w-xs truncate">
                          {order.description || '—'}
                        </td>
                        <td className="px-4 py-3 text-white/70 hidden md:table-cell">
                          {orderCustomerName(order, customer)}
                        </td>
                        <td className="px-4 py-3 text-white/70 hidden lg:table-cell">
                          {vehicle ? vehicleDisplayLabel(vehicle) : '—'}
                        </td>
                        <td className="px-4 py-3 text-right text-white font-medium hidden xl:table-cell">
                          ${displayTotal.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              openDetail(order)
                            }}
                            className="text-sm font-medium hover:opacity-80"
                            style={{ color: accentColors[400] }}
                          >
                            View
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            /* Cards View */
            <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filteredOrders?.map((order) => {
                const { label: displayStatus, style: statusStyle } = resolveOrderDisplayStatus(order)
                const parsedServices = parseServiceNotes(order.internal_notes)
                const serviceTotal = parsedServices?.reduce(
                  (sum, svc) => sum + (parseFloat(svc.base_price || '0') || 0),
                  0
                ) || 0
                const backendParts = parseFloat(order.total_parts_cost ?? '0') || 0
                const backendLabor = parseFloat(order.total_labor_cost ?? '0') || 0
                const laborTotal = serviceTotal > 0 ? serviceTotal : backendLabor
                const displayTotal = backendParts + laborTotal
                const showEstimate = serviceTotal > 0
                const showMechanic = ['quoted', 'in_progress', 'paid'].includes(order.status) && order.assigned_mechanic_id
                return (
                  <div 
                    key={order.id}
                    onClick={() => openDetail(order)}
                    className="aspect-square bg-gradient-to-br from-yellow-50 via-amber-100 to-yellow-200 p-4 sm:p-5 rounded-xl shadow-lg flex flex-col justify-between hover:shadow-xl transition-shadow cursor-pointer"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-mono text-slate-500">
                          {order.order_number}
                        </span>
                        <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium whitespace-nowrap ${statusStyle.bg} ${statusStyle.text}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${statusStyle.dot}`}></span>
                          {displayStatus}
                        </span>
                      </div>
                      <p className="text-sm text-slate-700 line-clamp-3 leading-relaxed">
                        {order.description}
                      </p>
                    </div>
                    
                    <div className="space-y-3">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-slate-500">
                          {format(new Date(order.created_at), 'MMM d, yyyy')}
                        </span>
                      </div>

                      <div className="bg-white/50 rounded-lg p-3 space-y-2">
                        <div className="text-xs text-slate-500 mb-1">{showEstimate ? 'Services + Parts' : 'Total Cost'}</div>
                        <div className="text-xl font-bold text-slate-800">
                          $
                          {displayTotal.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                        </div>
                        {showMechanic && (
                          <div className="flex items-center gap-2 text-xs text-slate-600">
                            <Wrench className="w-4 h-4 text-amber-600" />
                            <span>{mechanicLookup.get(order.assigned_mechanic_id!) || 'Assigned technician'}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="pt-3 border-t border-amber-200/50">
                      <button 
                        onClick={(e) => {
                          e.stopPropagation()
                          openDetail(order)
                        }}
                        className="w-full py-2 text-sm font-medium text-amber-700 hover:text-amber-900 hover:bg-amber-200/50 rounded-lg transition-colors inline-flex items-center justify-center gap-1"
                      >
                        View Details
                        <ArrowRight className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )
              })}

              <div 
                onClick={openModal}
                className="aspect-square bg-white/20 border-2 border-dashed border-white/40 p-4 sm:p-5 rounded-xl flex flex-col items-center justify-center cursor-pointer hover:bg-white/30 hover:border-white/60 transition-all"
              >
                <div className="w-12 h-12 rounded-full bg-white/30 flex items-center justify-center mb-3">
                  <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                </div>
                <span className="text-white font-medium">New Repair Order</span>
              </div>
            </div>
          )}
        </div>

        {/* Pagination footer (also carries the total count) */}
        {totalOrders > 0 && (
          <div className={`flex items-center justify-between px-4 py-3 border-t border-white/10 flex-shrink-0 text-sm text-white/70 ${isPlaceholderData ? 'opacity-60' : ''}`}>
            <span>
              {page * RO_PAGE_SIZE + 1}–{Math.min((page + 1) * RO_PAGE_SIZE, totalOrders)} of {totalOrders} order{totalOrders !== 1 ? 's' : ''}
            </span>
            {totalOrders > RO_PAGE_SIZE && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0 || isPlaceholderData}
                  className="px-3 py-1.5 rounded-lg border border-white/15 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage((p) => (orderPage?.has_more ? p + 1 : p))}
                  disabled={!orderPage?.has_more || isPlaceholderData}
                  className="px-3 py-1.5 rounded-lg border border-white/15 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Next
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {filteredOrders?.length === 0 && (searchQuery || statusFilter !== 'all') && (
        <div className="text-center py-12 text-white/70">
          No repair orders match your filters. Try adjusting your search.
        </div>
      )}

      {(!orders || orders.length === 0) && !searchQuery && statusFilter === 'all' && (
        <div className="text-center py-12 text-white/70">
          No repair orders found. Create your first repair order to get started.
        </div>
      )}

      {/* New Repair Order Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <div 
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={closeModal}
            />
            
            <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto">
              <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 rounded-t-2xl">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-bold text-gray-900">New Repair Order</h2>
                  <button
                    onClick={closeModal}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>

              <form onSubmit={handleSubmit} className="p-6 space-y-6">
                {/* Customer + Vehicle */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">Customer & Vehicle</h3>
                  </div>

                  {selectedCustomerId !== 'add_new' ? (
                    <div className="space-y-4">
                      <div className="flex items-end gap-3">
                        <div className="flex-1">
                          <label className="block text-sm font-medium text-gray-700 mb-1">Select Customer</label>
                          <CustomerSelect
                            customers={customers || []}
                            isLoading={isLoadingCustomers}
                            value={selectedCustomerId}
                            onChange={(val) => {
                              if (val === 'add_new') {
                                setSelectedCustomerId('add_new')
                                setSelectedVehicleId('')
                                setShowNewVehicleForm(true)
                                return
                              }
                              setSelectedCustomerId(val)
                              setSelectedVehicleId('')
                              setShowNewVehicleForm(false)
                            }}
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedCustomerId('add_new')
                            setSelectedVehicleId('')
                            setShowNewVehicleForm(true)
                          }}
                          className="inline-flex items-center gap-1 px-3 py-2 text-sm font-medium text-amber-700 border border-amber-200 rounded-lg hover:bg-amber-50 transition-colors"
                        >
                          <Plus className="w-4 h-4" />
                          Add customer
                        </button>
                      </div>

                      {selectedCustomerId && selectedCustomerId !== 'add_new' && (
                        <div>
                          <h4 className="text-sm font-semibold text-gray-800 mb-2">Vehicles for this customer</h4>
                          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                            {filteredVehicles.map((vehicle) => {
                              const selected = selectedVehicleId === vehicle.id
                              return (
                                <button
                                  key={vehicle.id}
                                  type="button"
                                  onClick={() => {
                                    setSelectedVehicleId(vehicle.id)
                                    setShowNewVehicleForm(false)
                                  }}
                                  className={`w-full text-left p-4 rounded-lg border transition-all ${
                                    selected
                                      ? 'border-amber-500 ring-2 ring-amber-200 bg-white'
                                      : 'border-gray-200 bg-white/60 hover:border-amber-300'
                                  }`}
                                >
                                  <div className="text-xs text-slate-500 mb-1">{vehicle.year || 'Year'}</div>
                                  <div className="text-sm font-semibold text-slate-900">
                                    {vehicleDisplayLabel(vehicle, { includeYear: false })}
                                  </div>
                                  <div className="text-xs text-slate-600 mt-1">{vehicle.license_plate || 'No plate'}</div>
                                </button>
                              )
                            })}

                            <button
                              type="button"
                              onClick={() => {
                                setSelectedVehicleId('')
                                setShowNewVehicleForm(true)
                              }}
                              className="w-full p-4 rounded-lg border-2 border-dashed border-gray-300 text-center text-sm text-amber-600 hover:border-amber-400 hover:bg-amber-50 transition-colors"
                            >
                              + Add new vehicle
                            </button>
                          </div>
                        </div>
                      )}

                      {(showNewVehicleForm || selectedCustomerId === 'add_new') && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                          <VehicleMakePicker
                            value={newVehicle.make}
                            onChange={(make) => setNewVehicle((prev) => ({ ...prev, make }))}
                          />
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                            <input
                              name="model"
                              value={newVehicle.model}
                              onChange={(e) => setNewVehicle((prev) => ({ ...prev, model: e.target.value }))}
                              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                              placeholder="579, Cascadia..."
                            />
                          </div>
                          <YearPicker
                            value={newVehicle.year}
                            onChange={(year) => setNewVehicle((prev) => ({ ...prev, year }))}
                          />
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">VIN</label>
                            <input
                              name="vin"
                              value={newVehicle.vin}
                              onChange={(e) => setNewVehicle((prev) => ({ ...prev, vin: e.target.value }))}
                              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                              placeholder="1XPBDP9X8JD123456"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Plate</label>
                            <input
                              name="license_plate"
                              value={newVehicle.license_plate}
                              onChange={(e) => setNewVehicle((prev) => ({ ...prev, license_plate: e.target.value }))}
                              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                              placeholder="TRK-1234"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Mileage</label>
                            <input
                              type="number"
                              name="mileage"
                              value={newVehicle.mileage}
                              onChange={(e) => setNewVehicle((prev) => ({ ...prev, mileage: e.target.value }))}
                              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                              placeholder="450000"
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
                        <input
                          name="first_name"
                          value={newCustomer.first_name}
                          onChange={(e) => setNewCustomer((prev) => ({ ...prev, first_name: e.target.value }))}
                          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                          placeholder="Acme"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
                        <input
                          name="last_name"
                          value={newCustomer.last_name}
                          onChange={(e) => setNewCustomer((prev) => ({ ...prev, last_name: e.target.value }))}
                          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                          placeholder="Doe"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Company Name</label>
                        <input
                          name="company_name"
                          value={newCustomer.company_name}
                          onChange={(e) => setNewCustomer((prev) => ({ ...prev, company_name: e.target.value }))}
                          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                          placeholder="Acme Logistics"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                        <input
                          type="email"
                          name="email"
                          value={newCustomer.email}
                          onChange={(e) => setNewCustomer((prev) => ({ ...prev, email: e.target.value }))}
                          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                          placeholder="fleet@acme.com"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
                        <input
                          name="phone"
                          value={newCustomer.phone}
                          onChange={(e) => setNewCustomer((prev) => ({ ...prev, phone: formatUSPhone(e.target.value) }))}
                          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                          placeholder="(555) 123-4567"
                        />
                      </div>

                      <VehicleMakePicker
                        value={newVehicle.make}
                        onChange={(make) => setNewVehicle((prev) => ({ ...prev, make }))}
                      />
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                        <input
                          name="model"
                          value={newVehicle.model}
                          onChange={(e) => setNewVehicle((prev) => ({ ...prev, model: e.target.value }))}
                          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                          placeholder="579, Cascadia..."
                        />
                      </div>
                      <YearPicker
                        value={newVehicle.year}
                        onChange={(year) => setNewVehicle((prev) => ({ ...prev, year }))}
                      />
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">VIN</label>
                        <input
                          name="vin"
                          value={newVehicle.vin}
                          onChange={(e) => setNewVehicle((prev) => ({ ...prev, vin: e.target.value }))}
                          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                          placeholder="1XPBDP9X8JD123456"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Plate</label>
                        <input
                          name="license_plate"
                          value={newVehicle.license_plate}
                          onChange={(e) => setNewVehicle((prev) => ({ ...prev, license_plate: e.target.value }))}
                          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                          placeholder="TRK-1234"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Mileage</label>
                        <input
                          type="number"
                          name="mileage"
                          value={newVehicle.mileage}
                          onChange={(e) => setNewVehicle((prev) => ({ ...prev, mileage: e.target.value }))}
                          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                          placeholder="450000"
                        />
                      </div>
                    </div>
                  )}
                </div>

                {/* Order details */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">Services (optional)</h3>
                      <p className="text-xs text-gray-500">Quick pick common jobs or search services</p>
                    </div>
                    {selectedServiceIds.length > 0 && (
                      <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2.5 py-1 rounded-full">
                        {selectedServiceIds.length} selected
                      </span>
                    )}
                  </div>

                  <div className="space-y-3">
                    <div className="relative">
                      <SuggestingInput
                        value={serviceSearch}
                        onChange={setServiceSearch}
                        onSelect={(text) => {
                          // A picked suggestion is a canonical service name from
                          // history — it may not be a bookable Service yet, so
                          // there's nothing to "select" here. Drop it straight
                          // into the work description instead, and clear the
                          // search box back to filtering the chips below.
                          setDescription((prev) => (prev ? `${prev}\n${text}` : text))
                          setServiceSearch('')
                        }}
                        suggestUrl="/services/name-suggestions"
                        placeholder="Search services (e.g., oil change, brake, diagnostics)"
                        className="w-full pl-10 pr-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors text-gray-900 placeholder-gray-400"
                      />
                      <svg
                        className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 pointer-events-none"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                      </svg>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      {(services || [])
                        .filter((svc) => !serviceSearch || svc.name.toLowerCase().includes(serviceSearch.toLowerCase()))
                        .slice(0, 8)
                        .map((svc) => {
                          const active = selectedServiceIds.includes(svc.id)
                          const stockStatus = getServiceStockStatus(svc)
                          return (
                            <span
                              key={svc.id}
                              className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-full text-sm font-medium border transition-colors ${
                                active
                                  ? 'border-amber-500 bg-amber-50 text-amber-700'
                                  : 'border-gray-200 bg-white hover:border-amber-300 text-gray-700'
                              }`}
                              title={stockStatus.tooltip}
                            >
                              {stockStatus.dotClass && (
                                <span className={`w-2 h-2 rounded-full ${stockStatus.dotClass}`} aria-hidden="true" />
                              )}
                              <button
                                type="button"
                                onClick={() =>
                                  setSelectedServiceIds((prev) =>
                                    prev.includes(svc.id) ? prev.filter((id) => id !== svc.id) : [...prev, svc.id]
                                  )
                                }
                                className="focus:outline-none"
                              >
                                {svc.name}
                              </button>
                              {active && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    setSelectedServiceIds((prev) => prev.filter((id) => id !== svc.id))
                                  }
                                  className="inline-flex items-center justify-center w-4 h-4 -mr-0.5 leading-none text-amber-700 hover:text-amber-900"
                                  aria-label={`Remove ${svc.name}`}
                                >
                                  <span className="block -mt-px text-base">×</span>
                                </button>
                              )}
                            </span>
                          )
                        })}

                      {services && services.length === 0 && (
                        <span className="text-sm text-gray-500">No services available yet</span>
                      )}
                    </div>

                    {(() => {
                      const shortages = (services || [])
                        .filter((svc) => selectedServiceIds.includes(svc.id))
                        .flatMap((svc) =>
                          (svc.parts || [])
                            .filter((p) => (p.stock_quantity ?? 0) < (parseFloat(p.quantity) || 0))
                            .map((p) => ({
                              serviceName: svc.name,
                              partName: p.name,
                              inventoryId: p.inventory_id,
                              have: p.stock_quantity ?? 0,
                              need: parseFloat(p.quantity) || 0,
                            }))
                        )
                      if (shortages.length === 0) return null
                      return (
                        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3">
                          <div className="flex items-start gap-2">
                            <TriangleAlert className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-semibold text-amber-900">
                                Parts stock warning
                              </p>
                              <p className="text-xs text-amber-800 mt-0.5">
                                The order can still be created, but these parts won't be auto-attached until stock is replenished:
                              </p>
                              <ul className="mt-2 space-y-2 text-xs text-amber-900">
                                {shortages.map((s) => {
                                  const open = replenishingId === s.inventoryId
                                  return (
                                    <li key={s.inventoryId} className="rounded border border-amber-200 bg-white/60 p-2">
                                      <div className="flex items-center justify-between gap-2">
                                        <span>
                                          <span className="font-medium">{s.serviceName}:</span>{' '}
                                          {s.partName} — have {s.have}, need {s.need}
                                        </span>
                                        {!open && (
                                          <button
                                            type="button"
                                            onClick={() => {
                                              setReplenishingId(s.inventoryId)
                                              setReplenishValue(String(s.need))
                                            }}
                                            className="text-amber-800 underline hover:text-amber-900 whitespace-nowrap font-medium"
                                          >
                                            Replenish stock
                                          </button>
                                        )}
                                      </div>
                                      {open && (
                                        <div className="mt-2 flex items-center gap-2">
                                          <label className="text-[11px] text-amber-900 font-medium">
                                            New stock qty:
                                          </label>
                                          <input
                                            type="number"
                                            min={0}
                                            value={replenishValue}
                                            onChange={(e) => setReplenishValue(e.target.value)}
                                            className="w-24 h-8 px-2 rounded border border-amber-300 bg-white text-gray-900 text-xs focus:outline-none focus:ring-2 focus:ring-amber-500"
                                            autoFocus
                                          />
                                          <button
                                            type="button"
                                            disabled={replenishSaving}
                                            onClick={async () => {
                                              const num = Number(replenishValue)
                                              if (!Number.isFinite(num) || num < 0) {
                                                toast.error('Enter a valid quantity')
                                                return
                                              }
                                              setReplenishSaving(true)
                                              try {
                                                await api.put(`/inventory/${s.inventoryId}`, { stock_quantity: num })
                                                await refetchServices()
                                                toast.success(`${s.partName} stock updated to ${num}`)
                                                setReplenishingId(null)
                                                setReplenishValue('')
                                              } catch (err) {
                                                toast.error(getErrorDetail(err, 'Failed to update stock'))
                                              } finally {
                                                setReplenishSaving(false)
                                              }
                                            }}
                                            className="h-8 px-3 rounded bg-amber-600 text-white text-xs font-semibold hover:bg-amber-700 disabled:opacity-60"
                                          >
                                            {replenishSaving ? 'Saving…' : 'Save'}
                                          </button>
                                          <button
                                            type="button"
                                            onClick={() => {
                                              setReplenishingId(null)
                                              setReplenishValue('')
                                            }}
                                            className="h-8 px-2 text-amber-800 hover:text-amber-900 text-xs"
                                          >
                                            Cancel
                                          </button>
                                        </div>
                                      )}
                                    </li>
                                  )
                                })}
                              </ul>
                            </div>
                          </div>
                        </div>
                      )
                    })()}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Description / Work requested</label>
                  <SuggestingTextarea
                    value={description}
                    onChange={setDescription}
                    suggestUrl="/repair-orders/description-suggestions"
                    variant="light"
                    rows={3}
                    className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors resize-none"
                    placeholder="Briefly describe the repair work or concern..."
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Mileage In</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={mileageIn}
                    onChange={(e) => { const v = e.target.value; if (v === '' || /^\d+$/.test(v)) setMileageIn(v) }}
                    className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                    placeholder="Odometer reading when the vehicle arrived"
                  />
                </div>

                <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="px-5 py-2.5 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={
                      isSubmitting ||
                      createRepairOrderMutation.isPending ||
                      createCustomerMutation.isPending ||
                      createVehicleMutation.isPending
                    }
                    className="px-5 py-2.5 disabled:opacity-50 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
                    style={{ backgroundColor: accentColors[500] }}
                  >
                    {(isSubmitting ||
                      createRepairOrderMutation.isPending ||
                      createCustomerMutation.isPending ||
                      createVehicleMutation.isPending) && (
                      <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                    )}
                    Create Repair Order
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Repair Order Detail Panel */}
      <SlidePanel
        isOpen={isDetailOpen && !!selectedOrder}
        onClose={closeDetail}
        title={selectedOrder ? `#${selectedOrder.order_number}` : ''}
        subtitle="Repair Order"
        width="max-w-full sm:max-w-[90vw] xl:max-w-[72vw] 2xl:max-w-[1400px]"
        hideHeader={priceBuilderOwnsShell}
        onPrev={!priceBuilderOwnsShell && showNavigation ? () => openDetail(navigationOrders[currentNavIndex - 1]) : undefined}
        onNext={!priceBuilderOwnsShell && showNavigation ? () => openDetail(navigationOrders[currentNavIndex + 1]) : undefined}
        prevDisabled={!hasPrev}
        nextDisabled={!hasNext}
        navigationLabel={!priceBuilderOwnsShell && showNavigation ? `${currentNavIndex + 1} / ${navigationOrders.length}` : undefined}
        headerExtra={
          !priceBuilderOwnsShell && selectedOrder && (() => {
            const detailOrder = orderDetail ?? selectedOrder
            const display = resolveOrderDisplayStatus({
              status: detailOrder.status,
              hold_reason: detailOrder.hold_reason,
              pending_zelle_confirmation: detailOrder.pending_zelle_confirmation,
              quote_sent: detailOrder.status === 'quoted'
                ? (quoteForOrder?.sent_to_customer || quoteSent || detailOrder.quote_sent)
                : detailOrder.quote_sent,
            })
            return (
              <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium whitespace-nowrap ${display.style.bg} ${display.style.text}`}>
                <span className={`w-2 h-2 rounded-full ${display.style.dot}`}></span>
                {display.label}
              </div>
            )
          })()
        }
        footer={
          !priceBuilderOwnsShell && selectedOrder && showDangerZone && (
            <div className="-mx-6 -my-4 space-y-2 bg-red-50 px-6 py-3">
              <button
                type="button"
                onClick={() => setShowDangerActions((prev) => !prev)}
                className="flex w-full items-center justify-between gap-4 text-left"
              >
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-red-100 p-1.5 text-red-700">
                    <TriangleAlert className="h-4 w-4" />
                  </div>
                  <div className="text-sm font-semibold text-red-700 uppercase tracking-wide">
                    Danger Zone
                  </div>
                </div>
                <div className="p-1 text-red-700">
                  {showDangerActions ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </div>
              </button>
              {showDangerActions && (
                (orderDetail ?? selectedOrder).deleted_at ? (
                  <div className="flex flex-wrap gap-2 justify-end">
                    <div className="w-full text-sm leading-5 text-red-600">
                      {(() => {
                        const d = orderDetail ?? selectedOrder
                        const when = format(new Date(d.deleted_at as string), 'MMM d, yyyy h:mm a')
                        return d.deleted_by_name
                          ? `Deleted by ${d.deleted_by_name} on ${when}. Restore to bring it back.`
                          : `Deleted on ${when}. Restore to bring it back.`
                      })()}
                    </div>
                    <button
                      type="button"
                      disabled={restoreRepairOrderMutation.isPending}
                      onClick={() => selectedOrder.id && restoreRepairOrderMutation.mutate(selectedOrder.id)}
                      className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      <RotateCcw className="h-4 w-4" />
                      {restoreRepairOrderMutation.isPending ? 'Restoring...' : 'Restore order'}
                    </button>
                  </div>
                ) : (
                <div className="flex flex-wrap gap-2 justify-end">
                  <div className="w-full text-sm leading-5 text-red-600">
                    Cancel stops work without deleting history. Delete removes it from your active list — it can be restored later from the Deleted filter.
                  </div>
                  <button
                    type="button"
                    disabled={cancelRepairOrderMutation.isPending || deleteRepairOrderMutation.isPending || (orderDetail ?? selectedOrder).status === 'cancelled'}
                    onClick={() => selectedOrder.id && cancelRepairOrderMutation.mutate(selectedOrder.id)}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-700 border border-red-200 rounded-lg hover:bg-red-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <OctagonX className="w-4 h-4" />
                    {cancelRepairOrderMutation.isPending ? 'Cancelling...' : 'Cancel order'}
                  </button>
                  <button
                    type="button"
                    disabled={deleteRepairOrderMutation.isPending}
                    onClick={() => setShowDeleteConfirm(true)}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                    {deleteRepairOrderMutation.isPending ? 'Deleting...' : 'Delete'}
                  </button>
                </div>
                )
              )}
            </div>
          )
        }
      >
        {selectedOrder && isOrderDetailLoading && !orderDetail && !priceBuilderOwnsShell && (
          <div className="p-6 space-y-6 animate-pulse">
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading repair order…
            </div>
            <div>
              <div className="h-3 w-24 bg-gray-200 rounded mb-3" />
              <div className="bg-gray-50 rounded-xl p-4 space-y-3">
                <div className="h-4 bg-gray-200 rounded w-3/4" />
                <div className="h-4 bg-gray-200 rounded w-1/2" />
                <div className="h-4 bg-gray-200 rounded w-2/3" />
              </div>
            </div>
            <div>
              <div className="h-3 w-32 bg-gray-200 rounded mb-3" />
              <div className="bg-gray-50 rounded-xl p-4 space-y-2">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="h-8 bg-gray-200 rounded" />
                ))}
              </div>
            </div>
            <div>
              <div className="h-3 w-28 bg-gray-200 rounded mb-3" />
              <div className="bg-gray-50 rounded-xl p-4 space-y-2">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="h-8 bg-gray-200 rounded" />
                ))}
              </div>
            </div>
          </div>
        )}
        {selectedOrder && (!isOrderDetailLoading || !!orderDetail || priceBuilderOwnsShell) && (
          <div className={priceBuilderOwnsShell ? 'h-full min-h-0' : 'p-6 space-y-6'}>

                {/* Quote Workflow — the customer quote/approval flow doesn't
                    apply to internal fleet ROs (the fleet manager runs them). */}
                {!priceBuilderOwnsShell && !selectedOrder.is_internal && (() => {
                  const hasQuote = !!quoteForOrder
                  const isApproved = quoteForOrder?.is_approved
                  const isSent = quoteForOrder?.sent_to_customer || quoteSent
                  const hasMechanic = !!selectedOrder.assigned_mechanic_id
                  const mechanicName = mechanics?.find(m => m.mechanic_id === selectedOrder.assigned_mechanic_id)?.mechanic_name || 'Assigned'

                  return (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Workflow</h3>
                      <div className="bg-gray-50 rounded-xl p-4 space-y-4">
                        {/* Quote details if exists */}
                        {quoteForOrder && (
                          <div className="space-y-1 text-sm text-gray-800 pb-3 border-b border-gray-200">
                            <div className="flex justify-between">
                              <span className="text-gray-500">Quote #</span>
                              <span className="font-mono font-medium">{quoteForOrder.quote_number}</span>
                            </div>
                          </div>
                        )}

                        {/* Workflow steps */}
                        <div className="flex items-center gap-0.5 overflow-x-auto pb-0.5 -mb-0.5">
                          {/* Step 1: Create/Update Quote Draft */}
                          {effectiveQuoteNeedsUpdate && hasQuote && isSent ? (
                            <button
                              type="button"
                              onClick={() => quoteForOrder && updateQuoteMutation.mutate(quoteForOrder.id)}
                              disabled={updateQuoteMutation.isPending}
                              className="shrink-0 px-2 py-1 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 text-white text-xs font-medium rounded-md"
                            >
                              {updateQuoteMutation.isPending ? 'Updating...' : 'Update'}
                            </button>
                          ) : (
                            <span className={`shrink-0 px-2 py-1 text-xs font-medium rounded-md ${
                              hasQuote
                                ? 'bg-green-100 text-green-700'
                                : 'bg-amber-500 text-white'
                            }`}>
                              {hasQuote ? (
                                <span className="flex items-center gap-0.5">✓ Draft Ready</span>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => selectedOrder.id && createQuoteMutation.mutate(selectedOrder.id)}
                                  disabled={createQuoteMutation.isPending}
                                  className="bg-transparent"
                                >
                                  {createQuoteMutation.isPending ? 'Creating...' : 'Create Draft'}
                                </button>
                              )}
                            </span>
                          )}

                          <ArrowRight className={`w-3 h-3 shrink-0 ${hasQuote ? 'text-amber-500' : 'text-gray-300'}`} />

                          {/* Step 2: Send to Customer */}
                          {hasQuote && !isApproved && (!isSent || effectiveQuoteNeedsUpdate) ? (
                            <button
                              type="button"
                              onClick={async () => {
                                if (quoteForOrder) {
                                  try {
                                    const quoteToSend = effectiveQuoteNeedsUpdate
                                      ? await updateQuoteMutation.mutateAsync(quoteForOrder.id)
                                      : quoteForOrder
                                    await sendQuoteMutation.mutateAsync(quoteToSend.id)
                                  } catch {
                                    // Mutation handlers surface the error toast; keep the click handler from throwing.
                                  }
                                }
                              }}
                              disabled={sendQuoteMutation.isPending || updateQuoteMutation.isPending}
                              className={`shrink-0 px-2 py-1 text-xs font-medium rounded-md ${
                                isSent
                                  ? 'bg-blue-100 text-blue-700 hover:bg-blue-200'
                                  : 'bg-amber-500 hover:bg-amber-600 text-white'
                              }`}
                            >
                              {quoteActionPending ? 'Working...' : (isSent ? '⏳ Resend' : 'Send')}
                            </button>
                          ) : (
                            <span className={`shrink-0 px-2 py-1 text-xs font-medium rounded-md ${
                              isApproved ? 'bg-green-100 text-green-700' : 'bg-gray-200 text-gray-400'
                            }`}>
                              {isApproved ? '✓ Sent' : isSent ? 'Awaiting approval' : 'Send'}
                            </span>
                          )}

                          <ArrowRight className={`w-3 h-3 shrink-0 ${isApproved ? 'text-amber-500' : 'text-gray-300'}`} />

                          {/* Step 3: Customer Approved */}
                          <span className={`shrink-0 px-2 py-1 text-xs font-medium rounded-md ${
                            isApproved
                              ? 'bg-green-100 text-green-700'
                              : isSent
                                ? 'bg-amber-100 text-amber-700 animate-pulse'
                                : 'bg-gray-200 text-gray-400'
                          }`}>
                            {isApproved ? '✓ Approved' : isSent ? 'Awaiting…' : 'Approved'}
                          </span>

                          <ArrowRight className={`w-3 h-3 shrink-0 ${hasMechanic ? 'text-amber-500' : 'text-gray-300'}`} />

                          {/* Step 4: Mechanic Assigned */}
                          <span className={`shrink-0 px-2 py-1 text-xs font-medium rounded-md ${
                            hasMechanic
                              ? 'bg-green-100 text-green-700'
                              : isApproved
                                ? 'bg-amber-100 text-amber-700'
                                : 'bg-gray-200 text-gray-400'
                          }`}>
                            {hasMechanic ? `✓ ${mechanicName}` : isApproved ? 'Assign ↓' : 'Technician'}
                          </span>
                        </div>

                        {/* Status messages */}
                        {effectiveQuoteNeedsUpdate && hasQuote && (
                          <p className="text-sm text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                            Quote changed. Resend it before waiting on customer approval.
                          </p>
                        )}
                        {isSent && !isApproved && !effectiveQuoteNeedsUpdate && (orderDetail ?? selectedOrder).status !== 'declined' && (
                          <p className="text-sm text-blue-600 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
                            Waiting for customer approval...
                          </p>
                        )}
                        {isApproved && !hasMechanic && (
                          <p className="text-sm text-green-600 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                            Customer approved! Assign a technician to start work.
                          </p>
                        )}
                        {/* Declined quote alert */}
                        {(orderDetail ?? selectedOrder).status === 'declined' && quoteForOrder?.is_declined && (
                          <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 space-y-1">
                            <p className="text-sm font-medium text-red-700">Customer Declined Quote</p>
                            {quoteForOrder.decline_notes && (
                              <p className="text-sm text-red-600">
                                <span className="font-medium">Reason:</span> {quoteForOrder.decline_notes}
                              </p>
                            )}
                            <p className="text-xs text-red-500">Update the quote and resend to customer.</p>
                          </div>
                        )}

                        {/* Mechanic Assignment - shown inline when approved but no mechanic */}
                        {isApproved && !hasMechanic && mechanics && mechanics.length > 0 && (
                          <div className="pt-3 border-t border-gray-200 space-y-3">
                            <p className="text-xs font-medium text-gray-500 uppercase">Available Technicians</p>
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                              {[...(mechanics || [])]
                                .map((m) => {
                                  const inProgress = m.in_progress_count ?? 0
                                  const assigned = m.assigned_count ?? 0
                                  const load = assigned > 0 ? Math.min((inProgress / assigned) * 100, 100) : 0
                                  return { ...m, load, inProgress, assigned }
                                })
                                .sort((a, b) => a.load - b.load)
                                .map((m) => (
                                  <button
                                    key={m.mechanic_id}
                                    type="button"
                                    onClick={() =>
                                      selectedOrder.id &&
                                      assignMechanicMutation.mutate({ orderId: selectedOrder.id, mechanicId: m.mechanic_id, orderStatus: (orderDetail ?? selectedOrder).status })
                                    }
                                    disabled={assignMechanicMutation.isPending}
                                    className="w-full text-left p-2.5 rounded-lg border border-gray-200 bg-white hover:border-amber-400 hover:bg-amber-50 transition-all disabled:opacity-50"
                                  >
                                    <div className="flex items-center justify-between">
                                      <span className="text-sm font-medium text-gray-800">{m.mechanic_name}</span>
                                      <span className={`text-xs font-medium ${m.load < 50 ? 'text-green-600' : m.load < 80 ? 'text-amber-600' : 'text-red-600'}`}>
                                        {m.load.toFixed(0)}%
                                      </span>
                                    </div>
                                    <div className="mt-1.5 h-1.5 rounded-full bg-gray-200 overflow-hidden">
                                      <div
                                        className={`h-full transition-all ${m.load < 50 ? 'bg-green-500' : m.load < 80 ? 'bg-amber-500' : 'bg-red-500'}`}
                                        style={{ width: `${m.load}%` }}
                                      />
                                    </div>
                                  </button>
                                ))}
                            </div>
                          </div>
                        )}

                        {/* Reassign Mechanic - shown when mechanic is already assigned and work not yet done */}
                        {hasMechanic && mechanics && mechanics.length > 1 && !['pending_review', 'completed', 'invoiced', 'paid'].includes((orderDetail ?? selectedOrder).status) && (
                          <div className="pt-3 border-t border-gray-200">
                            {!showReassignMechanic ? (
                              <button
                                type="button"
                                onClick={() => setShowReassignMechanic(true)}
                                className="text-sm text-amber-600 hover:text-amber-700 font-medium flex items-center gap-1.5"
                              >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                                </svg>
                                Reassign Technician
                              </button>
                            ) : (
                              <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                  <p className="text-xs font-medium text-gray-500 uppercase">Select New Technician</p>
                                  <button
                                    type="button"
                                    onClick={() => setShowReassignMechanic(false)}
                                    className="text-xs text-gray-500 hover:text-gray-700"
                                  >
                                    Cancel
                                  </button>
                                </div>
                                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                                  {[...(mechanics || [])]
                                    .filter(m => m.mechanic_id !== selectedOrder.assigned_mechanic_id)
                                    .map((m) => {
                                      const inProgress = m.in_progress_count ?? 0
                                      const assigned = m.assigned_count ?? 0
                                      const load = assigned > 0 ? Math.min((inProgress / assigned) * 100, 100) : 0
                                      return { ...m, load, inProgress, assigned }
                                    })
                                    .sort((a, b) => a.load - b.load)
                                    .map((m) => (
                                      <button
                                        key={m.mechanic_id}
                                        type="button"
                                        onClick={() => {
                                          if (selectedOrder.id) {
                                            assignMechanicMutation.mutate({ orderId: selectedOrder.id, mechanicId: m.mechanic_id, orderStatus: (orderDetail ?? selectedOrder).status })
                                            setShowReassignMechanic(false)
                                          }
                                        }}
                                        disabled={assignMechanicMutation.isPending}
                                        className="w-full text-left p-2.5 rounded-lg border border-gray-200 bg-white hover:border-amber-400 hover:bg-amber-50 transition-all disabled:opacity-50"
                                      >
                                        <div className="flex items-center justify-between">
                                          <span className="text-sm font-medium text-gray-800">{m.mechanic_name}</span>
                                          <span className={`text-xs font-medium ${m.load < 50 ? 'text-green-600' : m.load < 80 ? 'text-amber-600' : 'text-red-600'}`}>
                                            {m.load.toFixed(0)}%
                                          </span>
                                        </div>
                                        <div className="mt-1.5 h-1.5 rounded-full bg-gray-200 overflow-hidden">
                                          <div
                                            className={`h-full transition-all ${m.load < 50 ? 'bg-green-500' : m.load < 80 ? 'bg-amber-500' : 'bg-red-500'}`}
                                            style={{ width: `${m.load}%` }}
                                          />
                                        </div>
                                      </button>
                                    ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })()}

                {/* Time Metrics & Transition Timeline (V1.4) — only for completed+ ROs */}
                {(() => {
                  const o = orderDetail ?? selectedOrder
                  if (priceBuilderOwnsShell) return null
                  const showStatuses = ['pending_review', 'completed', 'invoiced', 'paid']
                  if (!showStatuses.includes(o.status)) return null
                  const fmtMin = (m: number | null | undefined) => {
                    if (m == null) return '—'
                    const h = Math.floor(m / 60)
                    const r = m % 60
                    return h > 0 ? `${h}h ${r}m` : `${r}m`
                  }
                  const hasTimeData = o.estimated_labor_minutes != null || o.actual_tracked_minutes != null
                  const hasTimeline = o.assigned_at || o.acknowledged_at || o.work_started_at || o.work_completed_at

                  if (!hasTimeData && !hasTimeline) return null

                  // Compute deltas between steps
                  const diffMin = (a?: string | null, b?: string | null) => {
                    if (!a || !b) return null
                    const ms = new Date(b).getTime() - new Date(a).getTime()
                    return ms > 0 ? Math.round(ms / 60000) : null
                  }

                  const mechanic = selectedOrder.assigned_mechanic_id
                    ? mechanicLookup.get(selectedOrder.assigned_mechanic_id)
                    : null

                  return (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Time Tracking</h3>
                      <div className="bg-gray-50 rounded-xl p-4 space-y-3">
                        {mechanic && (
                          <div className="flex items-center gap-2 text-sm">
                            <Wrench className="w-4 h-4 text-amber-500 shrink-0" />
                            <span className="text-gray-500">Technician:</span>
                            <span className="font-medium text-gray-800">{mechanic}</span>
                          </div>
                        )}
                        {hasTimeData && (
                          <div className="flex flex-wrap gap-4 text-sm">
                            <div>
                              <span className="text-gray-500">Est:</span>{' '}
                              <span className="font-medium text-gray-800">{fmtMin(o.estimated_labor_minutes)}</span>
                            </div>
                            <div>
                              <span className="text-gray-500">Actual:</span>{' '}
                              <span className="font-medium text-gray-800">{fmtMin(o.actual_tracked_minutes)}</span>
                            </div>
                            <div>
                              <span className="text-gray-500">Non-work:</span>{' '}
                              <span className="font-medium text-gray-800">{fmtMin(o.total_hold_minutes)}</span>
                            </div>
                          </div>
                        )}
                        {hasTimeline && (
                          <div className="flex items-center gap-1 flex-wrap text-xs text-gray-600">
                            {o.assigned_at && (
                              <>
                                <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded font-medium">Assigned</span>
                                {(() => {
                                  const d = diffMin(o.assigned_at, o.acknowledged_at)
                                  return d != null ? <span className="text-gray-400">{fmtMin(d)} →</span> : <span className="text-gray-300">→</span>
                                })()}
                              </>
                            )}
                            {o.acknowledged_at && (
                              <>
                                <span className="px-2 py-1 bg-indigo-100 text-indigo-700 rounded font-medium">Acknowledged</span>
                                {(() => {
                                  const d = diffMin(o.acknowledged_at, o.work_started_at)
                                  return d != null ? <span className="text-gray-400">{fmtMin(d)} →</span> : <span className="text-gray-300">→</span>
                                })()}
                              </>
                            )}
                            {o.work_started_at && (
                              <>
                                <span className="px-2 py-1 bg-amber-100 text-amber-700 rounded font-medium">Started</span>
                                {(() => {
                                  const d = diffMin(o.work_started_at, o.work_completed_at)
                                  return d != null ? <span className="text-gray-400">{fmtMin(d)} →</span> : <span className="text-gray-300">→</span>
                                })()}
                              </>
                            )}
                            {o.work_completed_at && (
                              <span className="px-2 py-1 bg-green-100 text-green-700 rounded font-medium">Completed</span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })()}

                {showPriceBuilder && (
                  <PriceBuilderPanel
                    orderId={selectedOrder.id}
                    orderStatus={(orderDetail ?? selectedOrder).status}
                    canEdit={canEditPriceBuilderByRole}
                    isInternalOrder={!!(orderDetail ?? selectedOrder).is_internal}
                    defaultLaborRate={taxFeeSettings?.labor_rate}
                    description={selectedOrder.description}
                    orderNumber={selectedOrder.order_number}
                    navigationLabel={showNavigation ? `${currentNavIndex + 1} / ${navigationOrders.length}` : undefined}
                    customerName={customerDisplayName}
                    vehicleLabel={paymentVehicleLabel}
                    vehicleUnit={selectedOrderVehicle?.unit_number}
                    vehicleVin={selectedOrderVehicle?.vin}
                    vehicleYear={selectedOrderVehicle?.year}
                    vehicleMake={selectedOrderVehicle?.make}
                    vehicleModel={selectedOrderVehicle?.model}
                    customerEmail={selectedOrderCustomer?.email}
                    customerPhone={selectedOrderCustomer?.phone}
                    vehiclePlate={selectedOrderVehicle?.license_plate}
                    mileageIn={selectedOrder.mileage_in}
                    mileageOut={selectedOrder.mileage_out}
                    poNumber={selectedOrder.po_number}
                    orderTypeLabel={selectedOrder.is_warranty_repair ? 'Warranty' : selectedOrder.parent_repair_order_id ? 'Comeback' : 'Standard'}
                    quoteNumber={quoteForOrder?.quote_number}
                    quoteIsSent={quoteIsSent}
                    quoteIsApproved={quoteIsApproved}
                    quoteActionLabel={quoteActionLabel}
                    quoteActionPending={quoteActionPending}
                    quoteActionDisabled={quoteActionDisabled}
                    quoteDisabledReason={quoteDisabledReason}
                    onQuoteAction={handlePriceBuilderQuoteAction}
                    assignedTechnicianName={
                      selectedOrder.assigned_mechanic_id
                        ? mechanicLookup.get(selectedOrder.assigned_mechanic_id) || 'Assigned technician'
                        : null
                    }
                    assignedTechnicianId={selectedOrder.assigned_mechanic_id}
                    technicianOptions={mechanics || []}
                    technicianAssignmentPending={assignMechanicMutation.isPending}
                    onAssignTechnician={(mechanicId) =>
                      selectedOrder.id &&
                      assignMechanicMutation.mutate({
                        orderId: selectedOrder.id,
                        mechanicId,
                        orderStatus: (orderDetail ?? selectedOrder).status,
                      })
                    }
                    completionMode={(orderDetail ?? selectedOrder).status === 'pending_review'}
                    completionPending={approveCompletionMutation.isPending}
                    mileageOutValue={mileageOut}
                    onMileageOutChange={(value) => {
                      if (value === '' || /^\d+$/.test(value)) setMileageOut(value)
                    }}
                    reviewNotesValue={reviewNotes}
                    onReviewNotesChange={setReviewNotes}
                    showReviewNotes={showReviewNotes}
                    onToggleReviewNotes={() => setShowReviewNotes((prev) => !prev)}
                    onApproveCompletion={() => {
                      if (selectedOrder.id) {
                        approveCompletionMutation.mutate({
                          orderId: selectedOrder.id,
                          reviewNotes: reviewNotes || undefined,
                          mileageOut: mileageOut.trim() === '' ? null : Number(mileageOut),
                        })
                        setReviewNotes('')
                        setMileageOut('')
                      }
                    }}
                    onStartWorkOrder={() => selectedOrder.id && startWorkOrderMutation.mutate(selectedOrder.id)}
                    startWorkOrderPending={startWorkOrderMutation.isPending}
                    onCompleteWorkOrder={(mileageOutVal) => selectedOrder.id && completeWorkOrderMutation.mutate({ orderId: selectedOrder.id, mileageOut: mileageOutVal })}
                    completeWorkOrderPending={completeWorkOrderMutation.isPending}
                    invoiceCreatePending={createInvoiceMutation.isPending}
                    invoiceDueDateValue={invoiceDueDate}
                    showInvoiceCreateOptions={showInvoiceCreateOptions}
                    onToggleInvoiceCreateOptions={() => setShowInvoiceCreateOptions((prev) => !prev)}
                    onInvoiceDueDateChange={setInvoiceDueDate}
                    onCreateInvoice={(dueDate) => selectedOrder.id && createInvoiceMutation.mutate({
                      repairOrderId: selectedOrder.id,
                      dueDate: dueDate || undefined,
                    })}
                    invoice={invoiceForOrder ?? null}
                    invoiceActionPending={
                      resendInvoiceMutation.isPending ||
                      deleteInvoiceMutation.isPending ||
                      recordManualPaymentMutation.isPending ||
                      clearPendingZelleMutation.isPending
                    }
                    onResendInvoice={() => {
                      if (invoiceForOrder) {
                        resendInvoiceMutation.mutate({ invoiceId: invoiceForOrder.id })
                      }
                    }}
                    onRecordPayment={() => {
                      if (invoiceForOrder?.pending_zelle_confirmation) {
                        openZellePaymentModal('confirm_pending')
                      } else {
                        setShowInvoicePaymentOptions(true)
                      }
                    }}
                    onDeleteInvoice={() => setShowDeleteInvoiceConfirm(true)}
                    historyEvents={priceBuilderHistoryEvents}
                    onClose={closeDetail}
                    onPrev={showNavigation ? () => openDetail(navigationOrders[currentNavIndex - 1]) : undefined}
                    onNext={showNavigation ? () => openDetail(navigationOrders[currentNavIndex + 1]) : undefined}
                    prevDisabled={!hasPrev}
                    nextDisabled={!hasNext}
                    showDangerActions={showDangerActions}
                    onToggleDangerActions={() => setShowDangerActions((prev) => !prev)}
                    onCancelOrder={() => selectedOrder.id && cancelRepairOrderMutation.mutate(selectedOrder.id)}
                    onDeleteOrder={() => setShowDeleteConfirm(true)}
                    cancelPending={cancelRepairOrderMutation.isPending}
                    deletePending={deleteRepairOrderMutation.isPending}
                    cancelDisabled={(orderDetail ?? selectedOrder).status === 'cancelled'}
                    isDeleted={!!(orderDetail ?? selectedOrder).deleted_at}
                    deletedByName={(orderDetail ?? selectedOrder).deleted_by_name}
                    deletedAt={(orderDetail ?? selectedOrder).deleted_at}
                    onRestoreOrder={() => selectedOrder.id && restoreRepairOrderMutation.mutate(selectedOrder.id)}
                    restorePending={restoreRepairOrderMutation.isPending}
                    onReopenWorkOrder={() => selectedOrder.id && reopenWorkOrderMutation.mutate(selectedOrder.id)}
                    reopenPending={reopenWorkOrderMutation.isPending}
                    recommendedServices={['completed', 'invoiced', 'paid'].includes((orderDetail ?? selectedOrder).status) ? [] : recommendedServices}
                    showAddRecommendedService={showAddRecService}
                    recommendedServiceForm={recServiceForm}
                    onToggleAddRecommendedService={() => setShowAddRecService((prev) => !prev)}
                    onRecommendedServiceFormChange={setRecServiceForm}
                    onAddRecommendedService={() => addRecServiceMutation.mutate({
                      description: recServiceForm.description.trim(),
                      priority: recServiceForm.priority,
                      estimated_cost: recServiceForm.estimated_cost ? parseFloat(recServiceForm.estimated_cost) : undefined,
                      notes: recServiceForm.notes || undefined,
                    })}
                    onResolveRecommendedService={(serviceId) => resolveRecServiceMutation.mutate(serviceId)}
                    onDeleteRecommendedService={(serviceId) => deleteRecServiceMutation.mutate(serviceId)}
                    addRecommendedPending={addRecServiceMutation.isPending}
                    resolveRecommendedPending={resolveRecServiceMutation.isPending}
                    deleteRecommendedPending={deleteRecServiceMutation.isPending}
                    onUpdated={() => {
                      refetchOrderDetail()
                      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
                    }}
                  />
                )}

                {showLaborBreakdown && !priceBuilderOwnsShell && (
                  <RepairOrderLaborBreakdown
                    laborItems={orderDetail?.labor_items ?? []}
                    laborTotal={(orderDetail ?? selectedOrder)?.total_labor_cost ?? '0'}
                    isLoading={isOrderDetailLoading}
                  />
                )}

                {showPriceBuilder && showLegacyPriceEditor && !priceBuilderOwnsShell && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">Estimate</h3>
                  <div className="bg-gray-50 rounded-xl">
                {(() => {
                  const detailServices = parseServiceNotes(selectedOrder.internal_notes) || []
                  const laborFromServices = detailServices.reduce(
                    (sum, svc) => sum + (parseFloat(svc.base_price || '0') || 0),
                    0
                  )
                  const canEditServices = ['draft', 'quoted'].includes((orderDetail ?? selectedOrder).status)
                  const availableServices = services?.filter(
                    (s) => !detailServices.some((ds) => ds.id === s.id)
                  ) || []

                  const handleAddService = (serviceId: string) => {
                    const svc = services?.find((s) => s.id === serviceId)
                    if (!svc || !selectedOrder.id) return
                    const newServices = [
                      ...detailServices,
                      { id: svc.id, name: svc.name, base_price: svc.computed_total_price },
                    ]
                    updateServicesMutation.mutate({ orderId: selectedOrder.id, selectedServices: newServices })
                  }

                  const handleRemoveService = (serviceId: string) => {
                    if (!selectedOrder.id) return
                    const newServices = detailServices.filter((s) => s.id !== serviceId)
                    updateServicesMutation.mutate({ orderId: selectedOrder.id, selectedServices: newServices })
                  }

                  return (
                    <div className="p-4 space-y-2 text-sm text-gray-800">
                      <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Services</p>
                        {detailServices.length > 0 ? (
                          <>
                            {detailServices.map((svc) => (
                              <div key={svc.id} className="flex items-center justify-between">
                                <span>{svc.name}</span>
                                <div className="flex items-center gap-2">
                                  <span className="font-semibold">${parseFloat(svc.base_price || '0').toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                                  {canEditServices && (
                                    <button
                                      type="button"
                                      onClick={() => handleRemoveService(svc.id)}
                                      className="p-1 text-red-600 hover:bg-red-50 rounded"
                                      aria-label="Remove service"
                                    >
                                      <Trash2 className="w-4 h-4" />
                                    </button>
                                  )}
                                </div>
                              </div>
                            ))}
                            {detailServices.length > 1 && (
                              <div className="pt-2 mt-2 border-t border-gray-200 flex items-center justify-between font-semibold">
                                <span>Total</span>
                                <span>${laborFromServices.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                              </div>
                            )}
                          </>
                        ) : (
                          <p className="text-gray-500">No services selected</p>
                        )}
                        {canEditServices && availableServices.length > 0 && (
                          <div className={detailServices.length > 0 ? 'pt-3 mt-2 border-t border-gray-200' : ''}>
                            <BaseSelect
                              options={availableServices.map((s) => ({
                                value: s.id,
                                label: s.name,
                                subLabel: `$${parseFloat(s.computed_total_price).toLocaleString('en-US', { minimumFractionDigits: 2 })}`,
                              }))}
                              value=""
                              onChange={handleAddService}
                              placeholder="Add service..."
                              allowAddNew={false}
                            />
                          </div>
                        )}
                    </div>
                  )
                })()}

                {/* PM services: the scope of a fleet PM work order (which
                    services it covers). The seeded parts & labor appear below. */}
                {(orderDetail?.pm_services?.length ?? 0) > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">PM Services</h3>
                    <div className="bg-gray-50 rounded-xl divide-y divide-gray-200">
                      {orderDetail!.pm_services!.map((s) => (
                        <div key={s.service_id} className="flex items-center justify-between gap-2 px-4 py-2.5 text-sm">
                          <span className="font-medium text-gray-800">{s.name}</span>
                          {s.duration_minutes ? (
                            <span className="text-xs text-gray-500 shrink-0">{s.duration_minutes} min</span>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Parts and labor: use detail when available. Shown for draft/
                    quoted (price builder) and for internal orders through their
                    active statuses (e.g. an in-progress PM). */}
                {(showPriceBuilder || showInternalLineItems) && (() => {
                  const displayOrder = orderDetail ?? selectedOrder
                  const partsUsage = orderDetail?.parts_usage ?? []
                  const laborItems = orderDetail?.labor_items ?? []
                  // Line items stay editable in draft/quoted, and — for internal
                  // orders — through their active statuses until they freeze.
                  const canEditLineItems = !!displayOrder && (
                    ['draft', 'quoted'].includes(displayOrder.status) ||
                    (isInternalOrder && showInternalLineItems)
                  )
                  const hasSelectedServices = !!parseServiceNotes(selectedOrder?.internal_notes)?.length
                  const hasPartsUsage = partsUsage.length > 0
                  const showLaborSection = !hasSelectedServices || laborItems.length > 0
                  return (
                    <>
                      {canEditLineItems && !hasPartsUsage && !showPartComposer && (
                        <div className="px-4 py-3 border-t border-gray-200">
                          <button
                            type="button"
                            onClick={() => setShowPartComposer(true)}
                            className="text-sm font-medium text-amber-700 hover:text-amber-800"
                          >
                            + Add part
                          </button>
                        </div>
                      )}

                      {(hasPartsUsage || showPartComposer) && (
                        <div className="p-4 border-t border-gray-200">
                          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">Parts</p>
                            {hasPartsUsage && (
                              <div className="space-y-2 mb-3">
                                {partsUsage.map((pu) => (
                                  <div key={pu.id} className="flex items-center justify-between gap-2 text-sm text-gray-800">
                                    <div className="flex-1 min-w-0" title={`${pu.inventory_name} (${pu.inventory_sku}) × ${pu.quantity}`}>
                                      <span className="font-medium truncate block">{pu.inventory_name}</span>
                                      <span className="text-gray-500 text-xs">({pu.inventory_sku}) × {pu.quantity}</span>
                                    </div>
                                    <div className="flex items-center gap-2 shrink-0">
                                      <span className="font-semibold">${parseFloat(pu.total_price).toFixed(2)}</span>
                                      {canEditLineItems && (
                                        <button
                                          type="button"
                                          onClick={() => selectedOrder?.id && removePartMutation.mutate({ orderId: selectedOrder.id, partsUsageId: pu.id })}
                                          className="p-1 text-red-600 hover:bg-red-50 rounded"
                                          aria-label="Remove part"
                                        >
                                          <Trash2 className="w-4 h-4" />
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                            {canEditLineItems && inventory && inventory.length > 0 && (
                              <div className="space-y-3">
                                {!hasPartsUsage && (
                                  <div className="flex items-center justify-between text-xs text-gray-500">
                                    <span>No parts added</span>
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setShowPartComposer(false)
                                        setAddPartInventoryId('')
                                        setAddPartQuantity(1)
                                      }}
                                      className="font-medium text-gray-600 hover:text-gray-800"
                                    >
                                      Hide
                                    </button>
                                  </div>
                                )}
                                <div className="flex items-center gap-2">
                                  <div className="flex-1 min-w-0">
                                    <BaseSelect
                                      options={inventory
                                        .filter((i) => i.stock_quantity > 0)
                                        .map((i) => ({
                                          value: i.id,
                                          label: i.name,
                                          subLabel: `${i.sku} — ${i.stock_quantity} in stock${i.on_order_quantity > 0 ? ` (${i.on_order_quantity} on order)` : ''}`,
                                        }))}
                                      value={addPartInventoryId}
                                      onChange={setAddPartInventoryId}
                                      placeholder="Select part"
                                      allowAddNew={false}
                                    />
                                  </div>
                                  <div className="shrink-0">
                                    <QuantityStepper
                                      value={addPartQuantity}
                                      onChange={(n) => setAddPartQuantity(Math.max(1, n))}
                                      min={1}
                                      step={1}
                                      unitLabel=""
                                      ariaLabel="Part quantity"
                                      align="start"
                                    />
                                  </div>
                                  <button
                                    type="button"
                                    disabled={!addPartInventoryId || addPartMutation.isPending}
                                    onClick={() => {
                                      if (!selectedOrder?.id || !addPartInventoryId) return
                                      addPartMutation.mutate({ orderId: selectedOrder.id, inventory_id: addPartInventoryId, quantity: addPartQuantity })
                                      setAddPartInventoryId('')
                                      setAddPartQuantity(1)
                                    }}
                                    className="h-[42px] px-3 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 text-white text-sm font-medium rounded-lg shrink-0"
                                  >
                                    Add
                                  </button>
                                </div>
                              </div>
                            )}
                        </div>
                      )}

                      {showLaborSection && (
                        <div className="p-4 border-t border-gray-200">
                          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">
                            {hasSelectedServices ? 'Additional Labor' : 'Labor'}
                          </p>
                            <>
                              {laborItems.length > 0 ? (
                                <div className="space-y-2 mb-3">
                                  {laborItems.map((li) => (
                                    <div key={li.id} className="flex items-center justify-between text-sm text-gray-800">
                                      <div>
                                        {li.description ? (
                                          <><span className="font-medium">{li.description}</span><span className="text-gray-500 ml-2">{parseFloat(li.hours)}h × ${parseFloat(li.hourly_rate).toFixed(2)}</span></>
                                        ) : (
                                          <span className="text-gray-600">{parseFloat(li.hours)}h × ${parseFloat(li.hourly_rate).toFixed(2)}</span>
                                        )}
                                      </div>
                                      <div className="flex items-center gap-2">
                                        <span className="font-semibold">${parseFloat(li.total_cost).toFixed(2)}</span>
                                        {canEditLineItems && (
                                          <button
                                            type="button"
                                            onClick={() => selectedOrder?.id && removeLaborMutation.mutate({ orderId: selectedOrder.id, laborId: li.id })}
                                            className="p-1 text-red-600 hover:bg-red-50 rounded"
                                            aria-label="Remove labor"
                                          >
                                            <Trash2 className="w-4 h-4" />
                                          </button>
                                        )}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                !canEditLineItems && <p className="text-sm text-gray-500">No labor items added</p>
                              )}
                              {canEditLineItems && (
                                <div className="flex flex-col gap-2">
                                  <input
                                    type="text"
                                    placeholder="Description (optional)"
                                    value={addLaborDescription}
                                    onChange={(e) => setAddLaborDescription(e.target.value)}
                                    className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
                                  />
                                  <div className="flex flex-wrap items-center gap-2">
                                    <input
                                      type="number"
                                      step={0.25}
                                      min={0}
                                      placeholder="Hours"
                                      value={addLaborHours}
                                      onChange={(e) => setAddLaborHours(e.target.value)}
                                      className="rounded-lg border border-gray-300 px-3 py-2 text-sm w-24"
                                    />
                                    <span className="text-gray-500 text-sm">×</span>
                                    <span className="inline-flex items-center gap-1 text-sm text-gray-500">
                                      <span>$</span>
                                      <QuantityStepper
                                        value={parseFloat(addLaborRate) || 0}
                                        onChange={(n) => setAddLaborRate(String(n))}
                                        min={0}
                                        step={1}
                                        unitLabel="/hr"
                                        ariaLabel="Labor rate per hour"
                                        align="start"
                                      />
                                    </span>
                                    <button
                                      type="button"
                                      disabled={!addLaborHours || !addLaborRate || addLaborMutation.isPending}
                                      onClick={() => {
                                        if (!selectedOrder?.id) return
                                        const hours = parseFloat(addLaborHours)
                                        const rate = parseFloat(addLaborRate)
                                        if (Number.isNaN(hours) || Number.isNaN(rate) || hours <= 0 || rate < 0) return
                                        addLaborMutation.mutate({
                                          orderId: selectedOrder.id,
                                          description: addLaborDescription.trim() || '',
                                          hours,
                                          hourly_rate: rate,
                                        })
                                        setAddLaborDescription('')
                                        setAddLaborHours('')
                                        setAddLaborRate(taxFeeSettings?.labor_rate?.toString() || '100')
                                      }}
                                      className="px-3 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 text-white text-sm font-medium rounded-lg"
                                    >
                                      Add
                                    </button>
                                  </div>
                                </div>
                              )}
                            </>
                        </div>
                      )}
                    </>
                  )
                })()}

                {showPriceBuilder && (() => {
                  const totalsOrder = orderDetail ?? selectedOrder
                  const backendParts = parseFloat(totalsOrder?.total_parts_cost ?? '0') || 0
                  const backendLabor = parseFloat(totalsOrder?.total_labor_cost ?? '0') || 0
                  const detailServices = parseServiceNotes(selectedOrder?.internal_notes)
                  const hasServices = detailServices && detailServices.length > 0
                  const serviceTotal = detailServices?.reduce(
                    (sum, svc) => sum + (parseFloat(svc.base_price || '0') || 0),
                    0
                  ) || 0
                  
                  // Services = Labor (service prices are labor costs)
                  // Parts = Separate (always from backend, priced individually)
                  // Total = Services/Labor + Parts
                  const partsVal = backendParts
                  const laborVal = hasServices ? serviceTotal : backendLabor
                  const totalVal = partsVal + laborVal
                  const fmt = (n: number) => n.toLocaleString('en-US', { minimumFractionDigits: 2 })

                  return (
                    <div className="px-4 py-3 border-t-2 border-gray-200">
                      {partsVal > 0 ? (
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                          <span className="text-gray-500">Parts</span>
                          <span className="font-semibold text-blue-700">${fmt(partsVal)}</span>
                          <span className="text-gray-400">·</span>
                          <span className="text-gray-500">{hasServices ? 'Services' : 'Labor'}</span>
                          <span className="font-semibold text-amber-700">${fmt(laborVal)}</span>
                          <span className="text-gray-400">·</span>
                          <span className="text-gray-500">Total</span>
                          <span className="text-base font-bold text-gray-900">${fmt(totalVal)}</span>
                        </div>
                      ) : (
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-500">Total</span>
                          <span className="text-base font-bold text-gray-900">${fmt(totalVal)}</span>
                        </div>
                      )}
                    </div>
                  )
                })()}
                  </div>
                </div>
                )}

                {!priceBuilderOwnsShell && (
                <div>
                  <button
                    type="button"
                    onClick={() => setCustomerSectionExpanded((prev) => !prev)}
                    className="w-full flex items-center justify-between text-left bg-gray-50 rounded-xl p-3 hover:bg-gray-100 transition-colors"
                  >
                    <span className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Customer & Vehicle</span>
                    <div className="flex items-center gap-2">
                      <span className="text-gray-900 font-medium truncate max-w-[200px]">
                        {customerDisplayName}
                      </span>
                      {customerSectionExpanded ? (
                        <ChevronUp className="w-5 h-5 text-gray-500 shrink-0" />
                      ) : (
                        <ChevronDown className="w-5 h-5 text-gray-500 shrink-0" />
                      )}
                    </div>
                  </button>
                  {customerSectionExpanded && (
                    <div className="bg-gray-50 rounded-b-xl p-4 border-t border-gray-200 -mt-1 pt-4 space-y-4">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="flex items-start gap-3">
                          <div className="w-9 h-9 rounded-lg bg-amber-100 flex items-center justify-center text-amber-700 font-bold text-sm shrink-0">
                            {(customerLookup.get(selectedOrder.customer_id)?.first_name || 'C').charAt(0)}
                            {(customerLookup.get(selectedOrder.customer_id)?.last_name || 'U').charAt(0)}
                          </div>
                          <div className="min-w-0">
                            <p className="text-gray-900 font-semibold text-sm truncate">
                              {customerDisplayName}
                            </p>
                            <p className="text-xs text-gray-500 truncate">{customerLookup.get(selectedOrder.customer_id)?.email}</p>
                            {customerLookup.get(selectedOrder.customer_id)?.phone && (
                              <p className="text-xs text-gray-500">{customerLookup.get(selectedOrder.customer_id)?.phone}</p>
                            )}
                          </div>
                        </div>
                        <div className="text-sm text-gray-700 sm:border-l sm:border-gray-200 sm:pl-4">
                          {vehicleLookup.get(selectedOrder.vehicle_id) ? (
                            <>
                              <p className="font-semibold text-gray-900 text-sm">
                                {vehicleLookup.get(selectedOrder.vehicle_id)?.year || 'Year'}{' '}
                                {vehicleLookup.get(selectedOrder.vehicle_id)?.make}{' '}
                                {vehicleLookup.get(selectedOrder.vehicle_id)?.model}
                              </p>
                              <p className="text-xs text-gray-600 mt-0.5">
                                VIN: {vehicleLookup.get(selectedOrder.vehicle_id)?.vin || '—'}
                              </p>
                              <p className="text-xs text-gray-600">
                                Plate: {vehicleLookup.get(selectedOrder.vehicle_id)?.license_plate || '—'}
                              </p>
                            </>
                          ) : (
                            <p className="text-gray-500 text-sm">Vehicle not found</p>
                          )}
                        </div>
                      </div>

                      {/* Mileage, PO, warranty/comeback row */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm border-t border-gray-200 pt-3">
                        <div>
                          <span className="inline-flex items-center gap-1 mb-0.5">
                            <p className="text-xs text-gray-400 uppercase tracking-wide">Mileage In</p>
                            <SectionInfoTooltip text="Odometer reading recorded when the vehicle was checked in. Used for service history tracking." />
                          </span>
                          <p className="font-medium text-gray-800">{selectedOrder.mileage_in ?? '—'}</p>
                        </div>
                        <div>
                          <span className="inline-flex items-center gap-1 mb-0.5">
                            <p className="text-xs text-gray-400 uppercase tracking-wide">Mileage Out</p>
                            <SectionInfoTooltip text="Odometer reading at vehicle return. The difference from Mileage In shows how much was driven during the repair process." />
                          </span>
                          <p className="font-medium text-gray-800">{selectedOrder.mileage_out ?? '—'}</p>
                        </div>
                        <div>
                          <span className="inline-flex items-center gap-1 mb-0.5">
                            <p className="text-xs text-gray-400 uppercase tracking-wide">PO Number</p>
                            <SectionInfoTooltip text="Purchase Order number provided by fleet or corporate customers for billing purposes. Appears on the invoice for their accounting records." />
                          </span>
                          <p className="font-medium text-gray-800">{selectedOrder.po_number || '—'}</p>
                        </div>
                        <div>
                          <span className="inline-flex items-center gap-1 mb-0.5">
                            <p className="text-xs text-gray-400 uppercase tracking-wide">Type</p>
                            <SectionInfoTooltip text="Standard: normal billable repair. Warranty: a repeat repair covered under a prior job's guarantee — typically not charged to the customer. Comeback: vehicle returned for the same issue, linked to the original order." tooltipClassName="w-72 -translate-x-[85%]" />
                          </span>
                          {selectedOrder.is_warranty_repair ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-700">
                              Warranty
                            </span>
                          ) : selectedOrder.parent_repair_order_id ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-orange-100 text-orange-700">
                              Comeback
                            </span>
                          ) : (
                            <span className="text-gray-500 text-sm">Standard</span>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
                )}


                {/* Approve Completion Button for pending_review status */}
                {!priceBuilderOwnsShell && (orderDetail ?? selectedOrder).status === 'pending_review' && (
                  <div className="bg-orange-50 border border-orange-200 rounded-xl p-4">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-10 h-10 bg-orange-100 rounded-full flex items-center justify-center shrink-0">
                        <svg className="w-5 h-5 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </div>
                      <div>
                        <p className="font-semibold text-orange-900">Technician Completed Work</p>
                        <p className="text-sm text-orange-700">Review and approve to notify customer</p>
                      </div>
                    </div>

                    <div className="mb-3">
                      <label className="block text-sm font-medium text-orange-800 mb-1">Mileage Out</label>
                      <input
                        type="text"
                        inputMode="numeric"
                        value={mileageOut}
                        onChange={(e) => { const v = e.target.value; if (v === '' || /^\d+$/.test(v)) setMileageOut(v) }}
                        placeholder={selectedOrder.mileage_in != null ? `Odometer at return (in: ${selectedOrder.mileage_in.toLocaleString()} mi)` : 'Odometer reading at vehicle return'}
                        className="w-full px-3 py-2 border border-orange-200 rounded-lg text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-orange-400 text-sm"
                      />
                    </div>

                    <div className="mb-3">
                      <button
                        type="button"
                        onClick={() => setShowReviewNotes(!showReviewNotes)}
                        className="flex items-center gap-2 text-sm font-medium text-orange-800 hover:text-orange-900"
                      >
                        <svg 
                          className={`w-4 h-4 transition-transform ${showReviewNotes ? 'rotate-90' : ''}`} 
                          fill="none" 
                          stroke="currentColor" 
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                        Add Review Notes <span className="text-orange-500 font-normal">(optional)</span>
                      </button>
                      {showReviewNotes && (
                        <textarea
                          value={reviewNotes}
                          onChange={(e) => setReviewNotes(e.target.value)}
                          placeholder="Add any notes about the review, additional work needed, quality observations..."
                          rows={3}
                          className="mt-2 w-full px-3 py-2 border border-orange-200 rounded-lg text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-orange-400 text-sm resize-none"
                        />
                      )}
                    </div>
                    
                    <button
                      type="button"
                      onClick={() => {
                        if (selectedOrder.id) {
                          approveCompletionMutation.mutate({
                            orderId: selectedOrder.id,
                            reviewNotes: reviewNotes || undefined,
                            mileageOut: mileageOut.trim() === '' ? null : Number(mileageOut),
                          })
                          setReviewNotes('')
                          setMileageOut('')
                        }
                      }}
                      disabled={approveCompletionMutation.isPending}
                      className="w-full py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
                    >
                      {approveCompletionMutation.isPending ? (
                        <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                      ) : (
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                      Approve Completion
                    </button>
                  </div>
                )}

                {/* Internal fleet cost summary — internal ROs are not invoiced to
                    a customer; completing one records an internal cost only. */}
                {!priceBuilderOwnsShell && (orderDetail ?? selectedOrder).status === 'completed' && selectedOrder.is_internal && (() => {
                  const o = orderDetail ?? selectedOrder
                  const labor = parseFloat(o.total_labor_cost ?? '0') || 0
                  const parts = parseFloat(o.total_parts_cost ?? '0') || 0
                  const total = parseFloat(o.total_cost ?? '0') || (labor + parts)
                  return (
                    <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
                      <div className="flex items-center gap-3 mb-3">
                        <div className="w-10 h-10 bg-slate-100 rounded-full flex items-center justify-center">
                          <Wrench className="w-5 h-5 text-slate-600" />
                        </div>
                        <div>
                          <p className="font-semibold text-slate-900">Internal Repair — Cost Record</p>
                          <p className="text-sm text-slate-600">In-house fleet repair. No customer invoice.</p>
                        </div>
                      </div>
                      <div className="space-y-1 text-sm">
                        <div className="flex justify-between text-slate-600"><span>Labor</span><span>{formatMoney(o.total_labor_cost ?? '0')}</span></div>
                        <div className="flex justify-between text-slate-600"><span>Parts</span><span>{formatMoney(o.total_parts_cost ?? '0')}</span></div>
                        <div className="flex justify-between font-semibold text-slate-900 pt-1 border-t border-slate-200 mt-1"><span>Internal cost</span><span>{formatMoney(String(total))}</span></div>
                      </div>
                    </div>
                  )
                })()}

                {/* Create Invoice Button for completed customer orders */}
                {!priceBuilderOwnsShell && (orderDetail ?? selectedOrder).status === 'completed' && !selectedOrder.is_internal && (
                  <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-10 h-10 bg-indigo-100 rounded-full flex items-center justify-center">
                        <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                      </div>
                      <div>
                        <p className="font-semibold text-indigo-900">Work Completed</p>
                        <p className="text-sm text-indigo-700">Create invoice to send to customer for payment</p>
                      </div>
                    </div>
                    <div className="mb-3 rounded-xl border border-indigo-200 bg-white/70">
                      <button
                        type="button"
                        onClick={() => setShowInvoiceCreateOptions((prev) => !prev)}
                        className="flex w-full items-center justify-between gap-3 px-3 py-3 text-left"
                      >
                        <div>
                          <p className="text-sm font-medium text-indigo-900">Optional invoice settings</p>
                          <p className="mt-0.5 text-xs text-indigo-700">{invoiceOptionSummary}</p>
                        </div>
                        <div className="p-1 text-indigo-600">
                          {showInvoiceCreateOptions ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                        </div>
                      </button>
                      {showInvoiceCreateOptions && (
                        <div className="border-t border-indigo-200 px-3 py-3">
                          <label className="mb-1 block text-sm font-medium text-indigo-700">Due Date (optional)</label>
                          <input
                            type="date"
                            value={invoiceDueDate}
                            onChange={(e) => setInvoiceDueDate(e.target.value)}
                            min={new Date().toISOString().split('T')[0]}
                            className="w-full rounded-lg border border-indigo-200 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500"
                          />
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => selectedOrder.id && createInvoiceMutation.mutate({ 
                        repairOrderId: selectedOrder.id,
                        dueDate: invoiceDueDate || undefined,
                      })}
                      disabled={createInvoiceMutation.isPending}
                      className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-400 text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
                    >
                      {createInvoiceMutation.isPending ? (
                        <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                      ) : (
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                      )}
                      Create Invoice
                    </button>
                  </div>
                )}

                {/* Invoice section for invoiced orders */}
                {!priceBuilderOwnsShell && (orderDetail ?? selectedOrder).status === 'invoiced' && invoiceForOrder && (
                  <div className="bg-purple-50 border border-purple-200 rounded-xl p-4">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-10 h-10 bg-purple-100 rounded-full flex items-center justify-center">
                        <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                      </div>
                      <div className="flex-1">
                        <p className="font-semibold text-purple-900">Invoice {invoiceForOrder.invoice_number}</p>
                        <p className="text-sm text-purple-700">
                          Total: ${parseFloat(invoiceForOrder.total_amount).toFixed(2)} — Awaiting payment
                        </p>
                      </div>
                    </div>
                    
                    {invoiceForOrder.due_date && (
                      <p className="text-xs text-purple-600 mb-2">
                        Due: {format(new Date(invoiceForOrder.due_date), 'MMM d, yyyy')}
                      </p>
                    )}

                    {invoiceForOrder.pending_zelle_confirmation && (
                      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 mb-3">
                        <p className="text-sm font-medium text-yellow-900">Pending Zelle confirmation</p>
                        <p className="text-xs text-yellow-800 mt-1">
                          Customer marked this invoice as paid via Zelle. Confirm receipt or clear pending status.
                        </p>
                        <div className="flex gap-2 mt-3">
                          <button
                            type="button"
                            onClick={() => openZellePaymentModal('confirm_pending')}
                            className="px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white text-xs font-medium rounded-md transition-colors"
                          >
                            Confirm Payment
                          </button>
                          <button
                            type="button"
                            onClick={() => clearPendingZelleMutation.mutate({ invoiceId: invoiceForOrder.id })}
                            disabled={clearPendingZelleMutation.isPending}
                            className="px-3 py-1.5 bg-yellow-100 hover:bg-yellow-200 text-yellow-900 text-xs font-medium rounded-md transition-colors disabled:opacity-60"
                          >
                            {clearPendingZelleMutation.isPending ? 'Clearing...' : 'Clear Pending'}
                          </button>
                        </div>
                      </div>
                    )}
                    
                    {!showResendInvoice && !showInvoicePaymentOptions ? (
                      <div className="space-y-2">
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => setShowResendInvoice(true)}
                            className="flex-1 py-2 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                            </svg>
                            Resend Invoice
                          </button>
                          <button
                            type="button"
                            onClick={() => setShowDeleteInvoiceConfirm(true)}
                            disabled={deleteInvoiceMutation.isPending}
                            className="px-3 py-2 bg-red-100 hover:bg-red-200 text-red-700 font-medium rounded-lg transition-colors"
                            title="Delete invoice"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </div>
                        <button
                          type="button"
                          onClick={() => setShowInvoicePaymentOptions(true)}
                          className="w-full py-2 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" />
                          </svg>
                          Record Payment
                        </button>
                      </div>
                    ) : showInvoicePaymentOptions ? (
                      <div className="space-y-3">
                        <p className="text-sm font-medium text-purple-800">Select payment method:</p>
                        <div className="grid grid-cols-2 gap-2">
                          {[
                            { value: 'cash', label: 'Cash', icon: '💵' },
                            { value: 'zelle', label: 'Zelle', icon: '📱' },
                            { value: 'check', label: 'Check', icon: '📝' },
                            { value: 'ach', label: 'ACH', icon: '🏦' },
                          ].map((method) => (
                            <button
                              key={method.value}
                              type="button"
                              onClick={() => {
                                setSelectedPaymentMethod(method.value)
                                if (method.value === 'zelle') {
                                  openZellePaymentModal()
                                }
                              }}
                              className={`py-2 px-3 rounded-lg border-2 transition-colors flex items-center justify-center gap-2 text-sm font-medium ${
                                selectedPaymentMethod === method.value
                                  ? 'border-green-500 bg-green-50 text-green-700'
                                  : 'border-gray-200 hover:border-gray-300 text-gray-700'
                              }`}
                            >
                              <span>{method.icon}</span>
                              {method.label}
                            </button>
                          ))}
                        </div>
                        <div className="flex gap-2 pt-2">
                          <button
                            type="button"
                            onClick={() => {
                              setShowInvoicePaymentOptions(false)
                              setSelectedPaymentMethod('')
                            }}
                            className="flex-1 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 font-medium rounded-lg transition-colors"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              if (selectedPaymentMethod && invoiceForOrder) {
                                recordManualPaymentMutation.mutate({
                                  invoiceId: invoiceForOrder.id,
                                  method: selectedPaymentMethod,
                                })
                              }
                            }}
                            disabled={!selectedPaymentMethod || selectedPaymentMethod === 'zelle' || recordManualPaymentMutation.isPending}
                            className="flex-1 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                          >
                            {recordManualPaymentMutation.isPending ? (
                              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                              </svg>
                            ) : (
                              selectedPaymentMethod === 'zelle' ? 'Use Zelle Modal' : 'Mark as Paid'
                            )}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div>
                          <label className="block text-sm font-medium text-purple-800 mb-1">
                            Send to different email (optional)
                          </label>
                          <input
                            type="email"
                            value={resendCustomEmail}
                            onChange={(e) => setResendCustomEmail(e.target.value)}
                            placeholder={customerLookup.get(selectedOrder.customer_id)?.email || 'customer@email.com'}
                            className="w-full px-3 py-2 border border-purple-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
                          />
                          <p className="text-xs text-purple-600 mt-1">
                            Leave empty to send to customer's default email
                          </p>
                        </div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setShowResendInvoice(false)
                              setResendCustomEmail('')
                            }}
                            className="flex-1 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 font-medium rounded-lg transition-colors"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={() => resendInvoiceMutation.mutate({
                              invoiceId: invoiceForOrder.id,
                              customEmail: resendCustomEmail || undefined,
                            })}
                            disabled={resendInvoiceMutation.isPending}
                            className="flex-1 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                          >
                            {resendInvoiceMutation.isPending ? (
                              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                              </svg>
                            ) : (
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                              </svg>
                            )}
                            Send
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Paid confirmation for paid orders */}
                {!priceBuilderOwnsShell && (orderDetail ?? selectedOrder).status === 'paid' && invoiceForOrder && (
                  <div className="bg-green-50 border border-green-200 rounded-xl p-4 space-y-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
                        <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      </div>
                      <div>
                        <p className="font-semibold text-green-900">Payment Complete</p>
                        <p className="text-sm text-green-700">
                          Invoice {invoiceForOrder.invoice_number} — ${parseFloat(invoiceForOrder.total_amount).toFixed(2)}
                        </p>
                      </div>
                    </div>

                    {!showResendInvoice ? (
                      <button
                        type="button"
                        onClick={() => setShowResendInvoice(true)}
                        className="w-full py-2 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                        Resend Invoice Copy
                      </button>
                    ) : (
                      <div className="space-y-3">
                        <div>
                          <label className="block text-sm font-medium text-green-800 mb-1">
                            Send to different email (optional)
                          </label>
                          <input
                            type="email"
                            value={resendCustomEmail}
                            onChange={(e) => setResendCustomEmail(e.target.value)}
                            placeholder={customerLookup.get(selectedOrder?.customer_id || '')?.email || 'customer@email.com'}
                            className="w-full px-3 py-2 border border-green-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                          />
                          <p className="text-xs text-green-700 mt-1">
                            Leave empty to send to customer's default email
                          </p>
                        </div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setShowResendInvoice(false)
                              setResendCustomEmail('')
                            }}
                            className="flex-1 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 font-medium rounded-lg transition-colors"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={() => resendInvoiceMutation.mutate({
                              invoiceId: invoiceForOrder.id,
                              customEmail: resendCustomEmail || undefined,
                            })}
                            disabled={resendInvoiceMutation.isPending}
                            className="flex-1 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                          >
                            {resendInvoiceMutation.isPending ? (
                              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                              </svg>
                            ) : (
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                              </svg>
                            )}
                            Send
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Recommended / Deferred Services */}
                {!priceBuilderOwnsShell && (
                <div className="rounded-xl border border-gray-200 overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setShowAddRecService((prev) => !prev)}
                    className="w-full flex items-center justify-between text-left bg-gray-50 p-3 hover:bg-gray-100 transition-colors"
                  >
                    <span className="inline-flex items-center gap-1.5">
                      <span className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
                        Recommended Services
                      </span>
                      {recommendedServices && recommendedServices.filter(s => !s.is_resolved).length > 0 && (
                        <span className="px-1.5 py-0.5 rounded-full text-xs bg-amber-100 text-amber-700 font-semibold">
                          {recommendedServices.filter(s => !s.is_resolved).length}
                        </span>
                      )}
                      <SectionInfoTooltip
                        text="Additional work noticed during the repair that the customer chose to defer. Use Urgent / Soon / Monitor to prioritize. Mark as Resolved when completed in a future visit — this builds a service history for the vehicle."
                        tooltipClassName="w-72 -translate-x-[80%]"
                      />
                    </span>
                    <Plus className="w-4 h-4 text-gray-400" />
                  </button>

                  {showAddRecService && (
                    <div className="p-3 border-t border-gray-200 bg-white space-y-2">
                      <textarea
                        value={recServiceForm.description}
                        onChange={(e) => setRecServiceForm(p => ({ ...p, description: e.target.value }))}
                        placeholder="Service description..."
                        rows={2}
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-amber-500"
                      />
                      <div className="grid grid-cols-2 gap-2">
                        <select
                          value={recServiceForm.priority}
                          onChange={(e) => setRecServiceForm(p => ({ ...p, priority: e.target.value as RecommendedServicePriority }))}
                          className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                        >
                          <option value="urgent">Urgent</option>
                          <option value="soon">Soon</option>
                          <option value="monitor">Monitor</option>
                        </select>
                        <input
                          type="number"
                          value={recServiceForm.estimated_cost}
                          onChange={(e) => setRecServiceForm(p => ({ ...p, estimated_cost: e.target.value }))}
                          placeholder="Est. cost"
                          className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                        />
                      </div>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => { setShowAddRecService(false); setRecServiceForm({ description: '', priority: 'soon', estimated_cost: '', notes: '' }) }}
                          className="flex-1 py-2 text-sm text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          disabled={!recServiceForm.description.trim() || addRecServiceMutation.isPending}
                          onClick={() => addRecServiceMutation.mutate({
                            description: recServiceForm.description.trim(),
                            priority: recServiceForm.priority,
                            estimated_cost: recServiceForm.estimated_cost ? parseFloat(recServiceForm.estimated_cost) : undefined,
                            notes: recServiceForm.notes || undefined,
                          })}
                          className="flex-1 py-2 text-sm text-white bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 rounded-lg font-medium"
                        >
                          Add
                        </button>
                      </div>
                    </div>
                  )}

                  {recommendedServices && recommendedServices.length > 0 && (
                    <ul className="divide-y divide-gray-100">
                      {recommendedServices.map((svc) => (
                        <li key={svc.id} className={`flex items-start gap-3 p-3 ${svc.is_resolved ? 'opacity-50' : ''}`}>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className={`px-1.5 py-0.5 rounded text-[11px] font-semibold ${
                                svc.priority === 'urgent' ? 'bg-red-100 text-red-700' :
                                svc.priority === 'soon' ? 'bg-yellow-100 text-yellow-700' :
                                'bg-gray-100 text-gray-600'
                              }`}>
                                {svc.priority.charAt(0).toUpperCase() + svc.priority.slice(1)}
                              </span>
                              {svc.estimated_cost && (
                                <span className="text-xs text-gray-500">${parseFloat(svc.estimated_cost).toFixed(2)}</span>
                              )}
                              {svc.is_resolved && <span className="text-xs text-green-600 font-medium">Resolved</span>}
                            </div>
                            <p className="text-sm text-gray-800 mt-0.5">{svc.description}</p>
                          </div>
                          {!svc.is_resolved && (
                            <div className="flex gap-1 shrink-0">
                              <button
                                type="button"
                                onClick={() => resolveRecServiceMutation.mutate(svc.id)}
                                disabled={resolveRecServiceMutation.isPending}
                                className="p-1.5 rounded-lg text-green-600 hover:bg-green-50"
                                title="Mark resolved"
                              >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                              </button>
                              <button
                                type="button"
                                onClick={() => deleteRecServiceMutation.mutate(svc.id)}
                                disabled={deleteRecServiceMutation.isPending}
                                className="p-1.5 rounded-lg text-red-400 hover:bg-red-50"
                                title="Delete"
                              >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                              </button>
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                  {(!recommendedServices || recommendedServices.length === 0) && !showAddRecService && (
                    <p className="text-xs text-gray-400 px-3 py-2">No recommended services recorded.</p>
                  )}
                </div>
                )}
              </div>
            )}
      </SlidePanel>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && selectedOrder && (
        <div className="fixed inset-0 z-[60] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <div 
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setShowDeleteConfirm(false)}
            />
            <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
              <div className="flex items-center gap-4 mb-4">
                <div className="p-3 rounded-full bg-red-100">
                  <Trash2 className="w-6 h-6 text-red-600" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">Delete Repair Order</h3>
                  <p className="text-sm text-gray-500">#{selectedOrder.order_number}</p>
                </div>
              </div>
              
              <p className="text-gray-600 mb-6">
                Remove this repair order from your active list? It's hidden from the
                board along with its:
              </p>

              <ul className="text-sm text-gray-600 mb-6 space-y-1 ml-4">
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-400"></span>
                  Order details and history
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-400"></span>
                  Associated quote (if any)
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-400"></span>
                  Parts and labor records
                </li>
              </ul>

              <p className="text-sm text-gray-500 mb-6">
                Nothing is destroyed — you can bring it back anytime from the
                <span className="font-medium text-gray-700"> Deleted</span> filter.
              </p>
              
              <div className="flex gap-3 justify-end">
                <button
                  type="button"
                  onClick={() => setShowDeleteConfirm(false)}
                  className="px-4 py-2 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={deleteRepairOrderMutation.isPending}
                  onClick={() => {
                    if (selectedOrder.id) {
                      deleteRepairOrderMutation.mutate(selectedOrder.id)
                      setShowDeleteConfirm(false)
                    }
                  }}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
                >
                  {deleteRepairOrderMutation.isPending && (
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                  )}
                  Delete order
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Invoice Confirmation Modal */}
      {showInvoicePaymentOptions && priceBuilderOwnsShell && invoiceForOrder && (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl">
            <div className="mb-4">
              <p className="text-lg font-semibold text-gray-900">Record payment</p>
              <p className="text-sm text-gray-500">
                Invoice {invoiceForOrder.invoice_number} · {formatMoney(invoiceForOrder.total_amount)}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {[
                { value: 'cash', label: 'Cash' },
                { value: 'zelle', label: 'Zelle' },
                { value: 'check', label: 'Check' },
                { value: 'ach', label: 'ACH' },
              ].map((method) => (
                <button
                  key={method.value}
                  type="button"
                  onClick={() => setSelectedPaymentMethod(method.value)}
                  className={`rounded-xl border px-3 py-3 text-sm font-semibold transition ${
                    selectedPaymentMethod === method.value
                      ? 'border-green-500 bg-green-50 text-green-800'
                      : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  {method.label}
                </button>
              ))}
            </div>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowInvoicePaymentOptions(false)
                  setSelectedPaymentMethod('')
                }}
                className="flex-1 rounded-xl bg-gray-100 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!selectedPaymentMethod || recordManualPaymentMutation.isPending}
                onClick={() => {
                  if (!selectedPaymentMethod) return
                  if (selectedPaymentMethod === 'zelle') {
                    setShowInvoicePaymentOptions(false)
                    openZellePaymentModal()
                    return
                  }
                  recordManualPaymentMutation.mutate({
                    invoiceId: invoiceForOrder.id,
                    method: selectedPaymentMethod,
                  })
                }}
                className="flex-1 rounded-xl bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:bg-gray-300"
              >
                {recordManualPaymentMutation.isPending ? 'Recording...' : selectedPaymentMethod === 'zelle' ? 'Continue' : 'Mark paid'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showDeleteInvoiceConfirm && invoiceForOrder && (
        <div className="fixed inset-0 z-[60] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <div 
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setShowDeleteInvoiceConfirm(false)}
            />
            <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
              <div className="flex items-center gap-4 mb-4">
                <div className="p-3 rounded-full bg-amber-100">
                  <Trash2 className="w-6 h-6 text-amber-600" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">Delete Invoice</h3>
                  <p className="text-sm text-gray-500">#{invoiceForOrder.invoice_number}</p>
                </div>
              </div>
              
              <p className="text-gray-600 mb-4">
                Are you sure you want to delete this invoice?
              </p>
              
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-6">
                <p className="text-sm text-amber-800">
                  The repair order will return to <strong>"completed"</strong> status and you can create a new invoice.
                </p>
              </div>
              
              <div className="flex gap-3 justify-end">
                <button
                  type="button"
                  onClick={() => setShowDeleteInvoiceConfirm(false)}
                  className="px-4 py-2 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={deleteInvoiceMutation.isPending}
                  onClick={() => {
                    deleteInvoiceMutation.mutate(invoiceForOrder.id)
                    setShowDeleteInvoiceConfirm(false)
                  }}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-amber-300 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
                >
                  {deleteInvoiceMutation.isPending && (
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                  )}
                  Delete Invoice
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Zelle QR Code Modal */}
      {showZelleQrModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]">
          <div className="bg-white rounded-xl shadow-xl max-w-sm w-full mx-4 overflow-hidden">
              <div className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 bg-purple-100 rounded-full flex items-center justify-center">
                  <span className="text-xl">📱</span>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">
                    {zelleModalMode === 'confirm_pending' ? 'Confirm Zelle Payment' : 'Zelle Payment'}
                  </h3>
                  <p className="text-sm text-gray-500">
                    {zelleModalMode === 'confirm_pending'
                      ? 'Customer already submitted payment from the portal'
                      : 'Show QR code to customer'}
                  </p>
                </div>
              </div>

              {zelleModalMode === 'collect' ? (
                <div className="bg-gray-50 rounded-lg p-4 mb-4">
                  {zelleSettings?.zelle_qr_image ? (
                    <div className="flex flex-col items-center">
                      <img
                        src={zelleSettings.zelle_qr_image}
                        alt="Zelle QR Code"
                        className="w-48 h-48 object-contain bg-white rounded-lg border"
                      />
                      <p className="text-sm text-gray-600 mt-3 text-center">
                        Customer scans this QR code with their Zelle app
                      </p>
                    </div>
                  ) : (
                    <div className="text-center py-4">
                      <p className="text-gray-500 text-sm">
                        No Zelle QR code uploaded.
                      </p>
                      <p className="text-gray-400 text-xs mt-1">
                        Upload in Shop Settings → Zelle Payments
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4 space-y-2">
                  <p className="text-sm text-blue-900 font-medium">
                    Customer marked this invoice as paid through the customer portal.
                  </p>
                  {invoiceForOrder?.zelle_pending_submitted_at && (
                    <p className="text-xs text-blue-800">
                      Submitted:{' '}
                      {format(new Date(invoiceForOrder.zelle_pending_submitted_at), 'MMM d, yyyy h:mm a')}
                    </p>
                  )}
                  {invoiceForOrder?.zelle_pending_sender_email && (
                    <p className="text-xs text-blue-800">
                      Sender email: {invoiceForOrder.zelle_pending_sender_email}
                    </p>
                  )}
                  {invoiceForOrder?.zelle_pending_sender_phone && (
                    <p className="text-xs text-blue-800">
                      Sender phone: {invoiceForOrder.zelle_pending_sender_phone}
                    </p>
                  )}
                </div>
              )}

              {/* Amount Display */}
              {invoiceForOrder && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm text-green-800">
                      Amount due: <span className="font-bold">{formatMoney(invoiceForOrder.total_amount)}</span>
                    </p>
                    <button
                      type="button"
                      onClick={() => setShowAmountBreakdown((prev) => !prev)}
                      className="text-xs font-medium text-green-800 hover:text-green-900 underline"
                    >
                      {showAmountBreakdown ? 'Hide breakdown' : 'Show breakdown'}
                    </button>
                  </div>
                  {showAmountBreakdown && (
                    <div className="mt-3 pt-3 border-t border-green-200 space-y-1 text-xs text-green-900">
                      <div className="flex items-center justify-between">
                        <span>Subtotal</span>
                        <span>{formatMoney(invoiceForOrder.subtotal)}</span>
                      </div>
                      {parseMoney(invoiceForOrder.shop_supplies_amount) > 0 && (
                        <div className="flex items-center justify-between">
                          <span>Shop supplies</span>
                          <span>{formatMoney(invoiceForOrder.shop_supplies_amount)}</span>
                        </div>
                      )}
                      {parseMoney(invoiceForOrder.service_fee_amount) > 0 && (
                        <div className="flex items-center justify-between">
                          <span>Service fee</span>
                          <span>{formatMoney(invoiceForOrder.service_fee_amount)}</span>
                        </div>
                      )}
                      {parseMoney(invoiceForOrder.tax_amount) > 0 && (
                        <div className="flex items-center justify-between">
                          <span>Tax</span>
                          <span>{formatMoney(invoiceForOrder.tax_amount)}</span>
                        </div>
                      )}
                      {parseMoney(invoiceForOrder.discount_amount) > 0 && (
                        <div className="flex items-center justify-between">
                          <span>Discount</span>
                          <span>-{formatMoney(invoiceForOrder.discount_amount)}</span>
                        </div>
                      )}
                      <div className="flex items-center justify-between pt-2 border-t border-green-200 font-semibold">
                        <span>Total</span>
                        <span>{formatMoney(invoiceForOrder.total_amount)}</span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {zelleModalMode === 'collect' && isSelectedOrderWalkIn ? (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4 space-y-3">
                  <label className="flex items-start gap-2 text-sm text-amber-900 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={captureZelleSender}
                      onChange={(e) => setCaptureZelleSender(e.target.checked)}
                      className="mt-0.5"
                    />
                    <span>
                      Capture sender info and update customer profile
                      <span className="font-medium"> (recommended for walk-in customers)</span>
                    </span>
                  </label>

                  {captureZelleSender && (
                    <div className="space-y-2">
                      <input
                        type="email"
                        value={zelleSenderEmail}
                        onChange={(e) => setZelleSenderEmail(e.target.value)}
                        placeholder="Sender Zelle email (optional)"
                        className="w-full px-3 py-2 border border-amber-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                      />
                      <input
                        type="tel"
                        value={zelleSenderPhone}
                        onChange={(e) => setZelleSenderPhone(formatUSPhone(e.target.value))}
                        placeholder="Sender Zelle phone (optional)"
                        className="w-full px-3 py-2 border border-amber-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                      />
                      <p className="text-xs text-amber-700">
                        Enter what you received from the bank notification to enrich walk-in customer records.
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 mb-4">
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Payment For</p>
                    {invoiceForOrder?.invoice_number && (
                      <span className="text-[11px] font-semibold text-slate-700 bg-slate-200 px-2 py-1 rounded-md">
                        {invoiceForOrder.invoice_number}
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-1 gap-2">
                    <div className="bg-white border border-slate-200 rounded-lg px-3 py-2">
                      <p className="text-[11px] text-slate-500 uppercase tracking-wide">Customer</p>
                      <p className="text-sm font-semibold text-slate-900 truncate">{paymentCustomerName}</p>
                    </div>
                    <div className="bg-white border border-slate-200 rounded-lg px-3 py-2">
                      <p className="text-[11px] text-slate-500 uppercase tracking-wide mb-1.5">Company / Truck Unit</p>
                      <p
                        className="text-sm font-semibold text-slate-900 truncate"
                        title={`${paymentCompanyName} \u00b7 Unit: ${paymentTruckUnit}`}
                      >
                        {paymentCompanyNameShort} &middot; Unit: {paymentTruckUnit}
                      </p>
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-slate-500 truncate">Vehicle: {paymentVehicleLabel}</p>
                </div>
              )}

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setShowAmountBreakdown(false)
                    setShowZelleQrModal(false)
                  }}
                  className="flex-1 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 font-medium rounded-lg transition-colors"
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowZelleQrModal(false)
                    if (invoiceForOrder) {
                      recordManualPaymentMutation.mutate({
                        invoiceId: invoiceForOrder.id,
                        method: 'zelle',
                        zelleSenderEmail: zelleSenderEmail,
                        zelleSenderPhone: zelleSenderPhone,
                        updateCustomerFromSender: captureZelleSender,
                      })
                    }
                  }}
                  disabled={recordManualPaymentMutation.isPending}
                  className="flex-1 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-medium rounded-lg transition-colors"
                >
                  {recordManualPaymentMutation.isPending
                    ? 'Recording...'
                    : zelleModalMode === 'confirm_pending'
                      ? 'Confirm Received'
                      : 'Payment Received'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
