import { useEffect, useMemo, useRef, useState } from 'react'
import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from '@headlessui/react'
import { Spinner, LoadingLine } from '@/components/ui'
import { useMutation, useQuery, useQueryClient, keepPreviousData, useInfiniteQuery,
} from '@tanstack/react-query'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { formatHoursMinutes } from '@/lib/durationFormat'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { Customer, RepairOrder, RepairOrderDetail, RepairOrderStatus, Vehicle, PartsUsage, Labor, InventoryItem, Quote, Invoice, RecommendedService, RecommendedServicePriority, VINDecodeResult, PriceBuildWarning } from '../../types'
import { format } from 'date-fns'
import { ArrowRight, FileText, Plus, TriangleAlert, Trash2, Wrench, ChevronDown, ChevronLeft, ChevronUp, RotateCcw, Search, X } from 'lucide-react'
import SlidePanel from '@/components/SlidePanel'
import YearPicker from '../../components/YearPicker'
import VehicleMakePicker from '../../components/VehicleMakePicker'
import CustomerSelect from '../../components/CustomerSelect'
import { customerDisplayName as customerNameOf, customerPersonalName } from '../../lib/customerName'
import { vehicleDisplayLabel } from '../../lib/vehicleName'
import { formatUSPhone } from '@/utils/phone'
import BaseSelect from '../../components/BaseSelect'
import QuantityStepper from '@/components/QuantityStepper'
import ViewToggle from '@/components/ViewToggle'
import { useViewPreference } from '@/hooks/useViewPreference'
import { useTheme } from '../../contexts/ThemeContext'
import { useWebSocket } from '../../hooks/useWebSocket'
import { useAuthStore } from '@/stores/authStore'
import PriceBuilderPanel from './PriceBuilderPanel'
import RepairOrdersLedger, { type RepairOrdersLedgerRow } from './RepairOrdersLedger'
import SectionInfoTooltip from '@/components/SectionInfoTooltip'
import SuggestingTextarea from '@/components/SuggestingTextarea'
import { buildPartHistoryEvents } from './repairOrderHistory'
import { REPAIR_ORDERS_QUEUE_LABEL } from './repairOrdersPresentation'
import type { ActionQueueOrder } from '../dashboard/ShopCockpitActionLedger'
import { AuthorizationSummary } from '@/features/quotes/AuthorizationSummary'
import {
  AUTHORIZATION_CONFLICT_MESSAGE,
  type AuthorizationHistory,
  canPublishAuthorization,
  canonicalizeAuthorizationHistoryEvents,
  formatAuthorizationEventDetail,
  isAuthorizationConflict,
} from '@/features/quotes/authorization'

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
  unit_number: string
  mileage: string
}

type CustomerTypeaheadItem = {
  id: string
  first_name: string
  last_name: string
  company_name: string | null
  email: string
  phone: string | null
}

type VehicleTypeaheadItem = {
  id: string
  customer_id: string
  make: string
  model: string
  year: number | null
  unit_number: string | null
  license_plate: string | null
  vin: string | null
  last_known_mileage?: number | null
}

type ServiceTypeaheadItem = {
  id: string
  name: string
  description: string | null
  duration_minutes: number
  base_price: string | null
  requires_vehicle: boolean
}

type CustomerLookupItem = Pick<CustomerTypeaheadItem, 'id' | 'first_name' | 'last_name' | 'company_name' | 'email' | 'phone'> & {
  source?: string | null
}

type VehicleLookupItem = VehicleTypeaheadItem

type ApiErrorLike = {
  response?: {
    data?: {
      detail?: string
    }
  }
}

type ZelleModalMode = 'collect' | 'confirm_pending'
type EvidencePaymentMethod = 'check' | 'ach' | 'fleet_payment'
type WorkQueueLane = 'needs_action' | 'on_floor' | 'ready_to_close' | 'closed_today'
type WorkbenchScope = 'all' | 'daily'

type WorkQueue = {
  orders_needing_action: ActionQueueOrder[]
  orders_needing_action_has_more: boolean
  orders_on_floor: ActionQueueOrder[]
  orders_on_floor_has_more: boolean
  orders_ready_to_close: ActionQueueOrder[]
  orders_ready_to_close_has_more: boolean
}

type DailyWorkbenchQueue = {
  items: ActionQueueOrder[]
  has_more: boolean
}

type DailyWorkbench = {
  timezone: string
  business_date: string
  next_reset_at: string
  needs_attention: DailyWorkbenchQueue
  on_floor: DailyWorkbenchQueue
  ready_to_close: DailyWorkbenchQueue
  closed_today: DailyWorkbenchQueue
}

type WorkQueueOrdersField =
  | 'orders_needing_action'
  | 'orders_on_floor'
  | 'orders_ready_to_close'

const WORK_QUEUE_FIELD: Record<Exclude<WorkQueueLane, 'closed_today'>, WorkQueueOrdersField> = {
  needs_action: 'orders_needing_action',
  on_floor: 'orders_on_floor',
  ready_to_close: 'orders_ready_to_close',
}

const DAILY_WORKBENCH_FIELD: Record<WorkQueueLane, keyof Pick<DailyWorkbench, 'needs_attention' | 'on_floor' | 'ready_to_close' | 'closed_today'>> = {
  needs_action: 'needs_attention',
  on_floor: 'on_floor',
  ready_to_close: 'ready_to_close',
  closed_today: 'closed_today',
}

const EVIDENCE_PAYMENT_METHODS: EvidencePaymentMethod[] = ['check', 'ach', 'fleet_payment']
const FLEET_PAYMENT_PROVIDERS = [
  { value: 'EFS', label: 'EFS / MoneyCode' },
  { value: 'Comchek', label: 'Comchek' },
  { value: 'T-Chek', label: 'T-Chek' },
  { value: 'Other', label: 'Other provider' },
]

type ManualPaymentResponse = {
  status: string
  message: string
  warning?: string | null
}

type RepairOrderFormErrors = Partial<Record<
  | 'customer'
  | 'customerFirstName'
  | 'customerLastName'
  | 'customerEmail'
  | 'vehicle'
  | 'vehicleMake'
  | 'vehicleModel'
  | 'vehicleVin'
  | 'root',
  string
>>

const isWalkInPlaceholderCustomer = (customer?: CustomerLookupItem | null): boolean => {
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
  'declined',
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
const EMPTY_ATTRIBUTION = { lead_source_channel: '', external_lead_id: '', callrail_call_id: '', google_click_id: '', gbraid: '', wbraid: '', landing_page_url: '', utm_source: '', utm_medium: '', utm_campaign: '', utm_term: '', utm_content: '' }

interface TruckInvoiceRecipientConnection {
  customer_id: string
  relationship_type: 'owner' | 'operator' | 'default_payer'
  effective_to?: string | null
  is_primary: boolean
  customer_company_name?: string | null
}

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
        <LoadingLine className="text-gray-500">Loading labor breakdown…</LoadingLine>
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

export default function RepairOrdersPage({ workbenchScope = 'all' }: { workbenchScope?: WorkbenchScope }) {
  const currentUser = useAuthStore((s) => s.user)
  const { accentColors, presentationVariant } = useTheme()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()

  // Connect to WebSocket for real-time updates (cache/status refresh only on this page).
  useWebSocket()
  const [searchQuery, setSearchQuery] = useState('')
  const debouncedSearch = useDebouncedValue(searchQuery.trim(), 300)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  // Counts for the status filters. Kept with the other hooks: this component
  // returns early for the legacy presentation, so a query declared beside
  // statusOptions further down runs on only some renders.
  const statusCountsQuery = useQuery<Record<string, number>>({
    queryKey: ['repair-orders', 'status-counts', debouncedSearch],
    queryFn: async () => (await api.get('/repair-orders/status-counts', {
      params: { ...(debouncedSearch ? { search: debouncedSearch } : {}) },
    })).data,
    staleTime: 15_000,
    retry: false,
  })
  const statusCounts = statusCountsQuery.data
  const queueParam = searchParams.get('queue')
  const workQueueLane: WorkQueueLane | null = queueParam && queueParam in DAILY_WORKBENCH_FIELD
    ? queueParam as WorkQueueLane
    : null
  const RO_PAGE_SIZE = 25
  type OrderPage = { items: RepairOrder[]; total: number; has_more: boolean }
  // No page state: the query key carries the search and status, so changing
  // either starts a fresh list rather than paging an existing one.
  // Set by the drawer's Next/Prev when it crosses a list-page boundary;
  // consumed once the new page's orders load to auto-open the right one.
  // Index the drawer should land on once a newly requested page arrives.
  const [pendingNavIndex, setPendingNavIndex] = useState<number | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('')
  const [selectedVehicleId, setSelectedVehicleId] = useState<string>('')
  const [customerQuery, setCustomerQuery] = useState('')
  const [vehicleQuery, setVehicleQuery] = useState('')
  const [selectedCustomerOption, setSelectedCustomerOption] = useState<CustomerTypeaheadItem | null>(null)
  const [selectedVehicleOption, setSelectedVehicleOption] = useState<VehicleTypeaheadItem | null>(null)
  const [showNewVehicleForm, setShowNewVehicleForm] = useState(false)
  const [description, setDescription] = useState('')
  const [mileageIn, setMileageIn] = useState('')
  // True only while the field still holds exactly the reading we offered. Any
  // edit makes it a fresh observation again.
  const [mileageInCarried, setMileageInCarried] = useState(false)
  const [attributionDraft, setAttributionDraft] = useState(EMPTY_ATTRIBUTION)
  const [detailAttributionDraft, setDetailAttributionDraft] = useState(EMPTY_ATTRIBUTION)
  const [serviceSearch, setServiceSearch] = useState('')
  const [selectedServiceIds, setSelectedServiceIds] = useState<string[]>([])
  const [selectedServiceOptions, setSelectedServiceOptions] = useState<ServiceTypeaheadItem[]>([])
  const [isDetailOpen, setIsDetailOpen] = useState(false)
  const [selectedOrder, setSelectedOrder] = useState<RepairOrder | null>(null)
  const [workspaceFocusRequest, setWorkspaceFocusRequest] = useState(0)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [initialPriceBuildWarningsByOrder, setInitialPriceBuildWarningsByOrder] = useState<Record<string, PriceBuildWarning[]>>({})
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
    unit_number: '',
    mileage: '',
  })
  const [formErrors, setFormErrors] = useState<RepairOrderFormErrors>({})
  const [isDecodingNewVehicleVin, setIsDecodingNewVehicleVin] = useState(false)
  const lastDecodedNewVehicleVin = useRef('')
  const [addPartInventoryId, setAddPartInventoryId] = useState('')
  const [addPartQuantity, setAddPartQuantity] = useState(1)
  const [addLaborDescription, setAddLaborDescription] = useState('')
  const [addLaborHours, setAddLaborHours] = useState('')
  const [addLaborRate, setAddLaborRate] = useState('100')
  const laborRateInitialized = useRef(false)
  const [showPartComposer, setShowPartComposer] = useState(false)
  const [customerSectionExpanded, setCustomerSectionExpanded] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  // The order currently being deleted — used to fade+collapse its list card on
  // the way out (kept briefly after success so the exit animation can play
  // before the refetch drops the row).
  const [deletingOrderId, setDeletingOrderId] = useState<string | null>(null)
  const [showResendInvoice, setShowResendInvoice] = useState(false)
  const [resendCustomEmail, setResendCustomEmail] = useState('')
  const [showVoidInvoiceConfirm, setShowVoidInvoiceConfirm] = useState(false)
  const [voidInvoiceReason, setVoidInvoiceReason] = useState('')
  const [showReassignMechanic, setShowReassignMechanic] = useState(false)
  const [assignMechanicOpen, setAssignMechanicOpen] = useState(true)
  const [reviewNotes, setReviewNotes] = useState('')
  const [mileageOut, setMileageOut] = useState('')
  const [showReviewNotes, setShowReviewNotes] = useState(false)
  const [invoiceDueDate, setInvoiceDueDate] = useState('')
  const [invoiceRecipientId, setInvoiceRecipientId] = useState('')
  const [showInvoiceCreateOptions, setShowInvoiceCreateOptions] = useState(false)
  const [showInvoicePaymentOptions, setShowInvoicePaymentOptions] = useState(false)
  const [selectedPaymentMethod, setSelectedPaymentMethod] = useState<string>('')
  const [showManualPaymentConfirmation, setShowManualPaymentConfirmation] = useState(false)
  const [manualPaymentReference, setManualPaymentReference] = useState('')
  const [manualPaymentAuthorization, setManualPaymentAuthorization] = useState('')
  const [manualPaymentProvider, setManualPaymentProvider] = useState('')
  const [manualPaymentCustomProvider, setManualPaymentCustomProvider] = useState('')
  const [manualPaymentNotes, setManualPaymentNotes] = useState('')
  const [showZelleQrModal, setShowZelleQrModal] = useState(false)
  const [zelleModalMode, setZelleModalMode] = useState<ZelleModalMode>('collect')
  const [zelleSenderEmail, setZelleSenderEmail] = useState('')
  const [zelleSenderPhone, setZelleSenderPhone] = useState('')
  const [captureZelleSender, setCaptureZelleSender] = useState(false)
  const [showAmountBreakdown, setShowAmountBreakdown] = useState(false)
  const [showAddRecService, setShowAddRecService] = useState(false)
  const [recommendedServicesOpen, setRecommendedServicesOpen] = useState(false)
  const [workspaceHistoryRequested, setWorkspaceHistoryRequested] = useState(false)
  const [recServiceForm, setRecServiceForm] = useState({ description: '', priority: 'soon' as RecommendedServicePriority, estimated_cost: '', notes: '' })
  const debouncedCustomerQuery = useDebouncedValue(customerQuery.trim(), 250)
  const debouncedVehicleQuery = useDebouncedValue(vehicleQuery.trim(), 250)
  const debouncedServiceSearch = useDebouncedValue(serviceSearch.trim(), 250)

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

  const resetManualPaymentConfirmation = () => {
    setShowManualPaymentConfirmation(false)
    setManualPaymentReference('')
    setManualPaymentAuthorization('')
    setManualPaymentProvider('')
    setManualPaymentCustomProvider('')
    setManualPaymentNotes('')
  }

  const openManualPaymentConfirmation = (method: EvidencePaymentMethod) => {
    setShowInvoicePaymentOptions(false)
    setSelectedPaymentMethod(method)
    setManualPaymentReference('')
    setManualPaymentAuthorization('')
    setManualPaymentProvider('')
    setManualPaymentCustomProvider('')
    setManualPaymentNotes('')
    setShowManualPaymentConfirmation(true)
  }

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 1024)
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])


  const activeViewMode = isMobile ? 'list' : viewMode

  const queryClient = useQueryClient()

  // Dashboard cards identify their originating lane in the URL. The focused
  // queue contract keeps workspace navigation from loading dashboard KPIs.
  const { data: workQueueStats, error: workQueueError } = useQuery<WorkQueue>({
    queryKey: ['dashboard-action-queue'],
    queryFn: async () => (await api.get('/dashboard/action-queue')).data,
    enabled: workbenchScope === 'all' && Boolean(workQueueLane && workQueueLane !== 'closed_today'),
    staleTime: 60 * 1000,
  })
  const {
    data: dailyWorkbench,
    error: dailyWorkbenchError,
    isLoading: isDailyWorkbenchLoading,
    isFetching: isDailyWorkbenchFetching,
  } = useQuery<DailyWorkbench>({
    queryKey: ['dashboard-daily-workset'],
    queryFn: async () => (await api.get('/dashboard/daily-workset')).data,
    enabled: workbenchScope === 'daily' && Boolean(workQueueLane),
    staleTime: 60 * 1000,
  })
  const workQueueErrorForScope = workbenchScope === 'daily' ? dailyWorkbenchError : workQueueError
  const workQueueOrders = (() => {
    if (!workQueueLane) return []
    if (workbenchScope === 'daily') {
      return dailyWorkbench?.[DAILY_WORKBENCH_FIELD[workQueueLane]].items ?? []
    }
    if (workQueueLane === 'closed_today') return []
    return workQueueStats?.[WORK_QUEUE_FIELD[workQueueLane]] ?? []
  })()
  const workQueueOrderIds = workQueueOrders.map((order) => order.id)
  // Server-side pagination: one page at a time, with search + status pushed to
  // the API instead of loading every order and filtering in the browser.
  const fetchOrderPage = async (p: number, signal?: AbortSignal) => {
    const response = await api.get('/repair-orders', {
      signal,
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
    return response.data as OrderPage
  }
  const ordersQuery = useInfiniteQuery({
    queryKey: ['repair-orders', 'infinite', { search: debouncedSearch, status: statusFilter }] as const,
    queryFn: ({ pageParam, signal }: { pageParam: number; signal: AbortSignal }) => fetchOrderPage(pageParam, signal),
    initialPageParam: 0,
    getNextPageParam: (last: OrderPage, all: OrderPage[]) => (last.has_more ? all.length : undefined),
    staleTime: 30_000,
    enabled: !workQueueLane,
  })
  const {
    isLoading,
    isFetching,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    error: orderPageError,
  } = ordersQuery
  // One list, not a window onto one. Every page the operator has pulled stays
  // rendered, so the row they were reading does not move under them and the
  // detail drawer can walk the whole loaded set without reloading anything.
  const orders = useMemo(
    () => (ordersQuery.data ? ordersQuery.data.pages.flatMap((chunk: OrderPage) => chunk.items) : undefined),
    [ordersQuery.data],
  )
  const totalOrders = ordersQuery.data?.pages[0]?.total ?? 0
  const loadedOrderCount = orders?.length ?? 0

  // Handle ?new=true query param to auto-open create modal
  useEffect(() => {
    const newParam = searchParams.get('new')
    if (newParam === 'true') {
      setIsModalOpen(true)
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])

  const applyDetailState = (order: RepairOrder) => {
    setWorkspaceHistoryRequested(false)
    setSelectedOrder(order)
    setIsDetailOpen(true)
    setQuoteSent(false)
    setShowReassignMechanic(false)
    setAssignMechanicOpen(true)
    setReviewNotes('')
    setShowReviewNotes(false)
    setShowDangerActions(false)
    setShowPartComposer(false)
    setAddPartInventoryId('')
    setAddPartQuantity(1)
  }

  const cancelOrderQueries = (orderId: string) => {
    queryClient.cancelQueries({ queryKey: ['repair-order-detail', orderId] })
    queryClient.cancelQueries({ queryKey: ['repair-order-workspace', orderId] })
    queryClient.cancelQueries({ queryKey: ['price-build', orderId] })
    queryClient.cancelQueries({ queryKey: ['repair-order-photos', orderId] })
    queryClient.cancelQueries({ queryKey: ['price-build-parts', orderId] })
    queryClient.cancelQueries({ queryKey: ['price-build-part-suggestions', orderId] })
    queryClient.cancelQueries({ queryKey: ['quote', orderId] })
    queryClient.cancelQueries({ queryKey: ['invoice-for-order', orderId] })
    queryClient.cancelQueries({ queryKey: ['recommended-services', orderId] })
  }

  const openDetail = (order: RepairOrder, options?: { focusWorkspace?: boolean }) => {
    // Rapid prev/next through the work queue (e.g. paging through 20+ orders
    // in a few seconds) was leaving every previous order's detail/price-build/
    // parts/quotes/invoices requests retrying in the background, each holding
    // its own rate-limit-budget-consuming backoff timer — that pile-up is what
    // tripped the 429s and left the panel stuck showing a loading placeholder
    // for the order actually on screen. Cancel the outgoing order's in-flight
    // queries so only the order you're actually looking at is still fetching.
    if (selectedOrder?.id && selectedOrder.id !== order.id) {
      cancelOrderQueries(selectedOrder.id)
    }
    applyDetailState(order)
    if (options?.focusWorkspace) setWorkspaceFocusRequest((request) => request + 1)
    // Keep the active Shop Work lane while an operator moves through its
    // workset. The explicit "All orders" control is the only way to drop this
    // navigation context; a ledger click must not silently turn a lane review
    // into the unrelated global list.
    const nextSearchParams: Record<string, string> = { selected: order.id }
    if (workQueueLane) nextSearchParams.queue = workQueueLane
    // Fresh open pushes ?selected= so Back/close return to the view underneath;
    // switching orders while open (prev/next, arrow keys) replaces the entry so
    // Back still exits to the origin instead of replaying every order viewed.
    setSearchParams(nextSearchParams, { replace: isDetailOpen })
  }

  const openWorkQueueOrder = (orderId: string, options?: { focusWorkspace?: boolean }) => {
    if (!workQueueLane) return
    if (selectedOrder?.id && selectedOrder.id !== orderId) {
      cancelOrderQueries(selectedOrder.id)
    }
    if (options?.focusWorkspace) setWorkspaceFocusRequest((request) => request + 1)
    setSearchParams({ selected: orderId, queue: workQueueLane }, { replace: true })
  }

  const clearDetailState = () => {
    if (selectedOrder?.id) cancelOrderQueries(selectedOrder.id)
    setSelectedOrder(null)
    setIsDetailOpen(false)
    setQuoteSent(false)
    setShowDangerActions(false)
    setShowPartComposer(false)
    setAddPartInventoryId('')
    setAddPartQuantity(1)
    setInvoiceDueDate('')
    setShowInvoiceCreateOptions(false)
    setWorkspaceHistoryRequested(false)
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

  const showAllOrders = () => {
    const selectedId = searchParams.get('selected')
    setSearchParams(selectedId ? { selected: selectedId } : {}, { replace: true })
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
    const controller = new AbortController()
    let cancelled = false
    // A selected order can come from the dashboard work queue and therefore be
    // outside this page of the list. Resolve its compact workspace projection
    // first; the full detail route stays reserved for History intent below.
    api.get(`/repair-orders/${selectedId}/workspace`, { signal: controller.signal })
      .then((response) => {
        if (cancelled) return
        queryClient.setQueryData(['repair-order-workspace', selectedId], response.data)
        applyDetailState(response.data as RepairOrder)
      })
      .catch(() => {
        if (cancelled) return
        toast.error("Couldn't open that repair order — it may have been deleted")
        setSearchParams({}, { replace: true })
      })
    return () => {
      cancelled = true
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, orders, isDetailOpen, selectedOrder?.id])

  // Picker data is only needed to create a repair order. Each lookup is a
  // capped, debounced server-side typeahead, so opening an existing order no
  // longer pages through every customer, vehicle, and service in the tenant.
  const { data: customerResults = [], isLoading: isLoadingCustomers, isFetching: isFetchingCustomers } = useQuery<CustomerTypeaheadItem[]>({
    queryKey: ['customer-typeahead', debouncedCustomerQuery],
    queryFn: async ({ signal }) => {
      const response = await api.get('/customers/typeahead', {
        signal,
        params: { q: debouncedCustomerQuery || undefined, limit: 20 },
      })
      return response.data
    },
    enabled: isModalOpen,
    // Keep the menu stable while a new debounced term is fetched. The spinner
    // in CustomerSelect signals that these are outgoing results until the
    // replacement arrives, avoiding an empty-panel flicker on every keystroke.
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })

  // Fleet company name, so internal fleet ROs show the fleet operator (e.g.
  // "77 Cargo") as the customer instead of the generic house account.
  const { data: fleetSettings } = useQuery<{ fleet_company_name: string | null }>({
    queryKey: ['fleet-settings'],
    queryFn: async ({ signal }) => {
      const response = await api.get('/fleet/settings', { signal })
      return response.data
    },
    // Only a new-order flow or an internal-fleet row needs the fleet company
    // label. Avoid a settings request on customer-only repair-order pages.
    enabled: isModalOpen || Boolean(
      selectedOrder?.is_internal || orders?.some((order) => order.is_internal),
    ),
  })

  const { data: vehicleResults = [], isLoading: isLoadingVehicles, isFetching: isFetchingVehicles } = useQuery<VehicleTypeaheadItem[]>({
    queryKey: ['vehicle-typeahead', selectedCustomerId, debouncedVehicleQuery],
    queryFn: async ({ signal }) => {
      const response = await api.get('/vehicles/typeahead', {
        signal,
        params: {
          customer_id: selectedCustomerId,
          q: debouncedVehicleQuery || undefined,
          // This is a single selected company's fleet, not the tenant-wide
          // catalog. Give the immediate vehicle grid enough choices while
          // retaining the capped, searchable endpoint for larger fleets.
          limit: 50,
        },
      })
      return response.data
    },
    enabled: isModalOpen && !!selectedCustomerId && selectedCustomerId !== 'add_new',
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })

  const { data: serviceResults = [], isLoading: isLoadingServices, isFetching: isFetchingServices } = useQuery<ServiceTypeaheadItem[]>({
    queryKey: ['service-typeahead', debouncedServiceSearch],
    queryFn: async ({ signal }) => {
      const response = await api.get('/services/typeahead', {
        signal,
        params: { q: debouncedServiceSearch || undefined, limit: 20 },
      })
      return response.data
    },
    enabled: isModalOpen,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })

  // Creating an order does not require the shop roster, but every state the
  // server will accept an assignment in does. POST /{id}/assign-mechanic moves
  // draft, quoted, declined, approved and acknowledged orders to assigned, so
  // omitting the first three left the pipeline showing "Assign technician" as
  // the live step with an empty list behind it — the shop's own drafts, which
  // this product calls Checked in, could only be started by overriding the step.
  const shouldLoadMechanics = !!(
    selectedOrder?.id
    && isDetailOpen
    && ['draft', 'quoted', 'declined', 'approved', 'assigned', 'acknowledged', 'in_progress', 'pending_review'].includes(selectedOrder.status)
  )

  const { data: mechanics } = useQuery<{ mechanic_id: string; mechanic_name: string; assigned_count?: number; in_progress_count?: number }[]>({
    queryKey: ['mechanics'],
    queryFn: async ({ signal }) => {
      const response = await api.get('/dashboard/mechanics/options', { signal })
      return response.data
    },
    enabled: shouldLoadMechanics,
    staleTime: 60_000,
  })
  // The panel derives its list with .filter, so a response that is not an array
  // takes the whole workspace down instead of showing an empty roster.
  const technicianRoster = Array.isArray(mechanics) ? mechanics : []

  const { data: orderDetail, refetch: refetchOrderDetail, isLoading: isOrderDetailLoading } = useQuery<RepairOrderDetail>({
    queryKey: ['repair-order-detail', selectedOrder?.id],
    queryFn: async ({ signal }) => {
      const response = await api.get(`/repair-orders/${selectedOrder!.id}/detail`, { signal })
      return response.data
    },
    // The list row and price-build summary are sufficient for the Workspace's
    // first render. The full detail endpoint includes parts, labor, PM scope,
    // and history, so only open it on explicit History intent for the active
    // Workspace flow. Older non-workspace detail states retain their existing
    // behavior until those screens receive their own focused contracts.
    enabled: !!(
      selectedOrder?.id
      && isDetailOpen
      && (
        workspaceHistoryRequested
        || !PRICE_BUILDER_STATUSES.includes(selectedOrder.status)
      )
    ),
  })

  // PriceBuilderPanel owns the part picker and fetches it only when the user
  // opens that control. The legacy inline editor is disabled; keep its empty
  // placeholder below solely so the dormant JSX remains type-safe without
  // triggering a catalog download whenever a drawer opens.
  const inventory: InventoryItem[] = []

  const { data: quoteForOrder, refetch: refetchQuote } = useQuery<Quote | null>({
    queryKey: ['quote', selectedOrder?.id],
    queryFn: async ({ signal }) => {
      const response = await api.get(`/quotes?repair_order_id=${selectedOrder!.id}`, { signal })
      return response.data
    },
    enabled: !!(selectedOrder?.id && isDetailOpen),
  })

  const { data: authorizationHistory, refetch: refetchAuthorizationHistory } = useQuery<AuthorizationHistory>({
    queryKey: ['authorization-history', selectedOrder?.id],
    queryFn: async ({ signal }) => {
      const response = await api.get(`/quotes/repair-order/${selectedOrder!.id}/history`, { signal })
      return response.data as AuthorizationHistory
    },
    enabled: !!(
      selectedOrder?.id
      && isDetailOpen
      && workspaceHistoryRequested
      && !selectedOrder.is_internal
    ),
  })

  const { data: invoiceForOrder } = useQuery<Invoice | null>({
    queryKey: ['invoice-for-order', selectedOrder?.id],
    queryFn: async ({ signal }) => {
      const response = await api.get(`/invoices?repair_order_id=${selectedOrder!.id}`, { signal })
      const invoices = response.data
      return invoices.length > 0 ? invoices[0] : null
    },
    enabled: !!(selectedOrder?.id && isDetailOpen && ['invoiced', 'paid'].includes(selectedOrder?.status || '')),
  })

  const { data: truckRecipientConnections = [] } = useQuery<TruckInvoiceRecipientConnection[]>({
    queryKey: ['vehicle-account-relationships', selectedOrder?.vehicle_id],
    queryFn: async () => (await api.get(`/vehicles/${selectedOrder!.vehicle_id}/relationships`)).data,
    // Connected bill-to companies matter only inside the invoice chooser. The
    // default customer remains available immediately, while this list loads on
    // the explicit "Create Invoice" intent instead of every workspace open.
    enabled: !!selectedOrder?.vehicle_id && isDetailOpen && showInvoiceCreateOptions,
  })

  const invoiceRecipientOptions = useMemo(() => {
    const active = truckRecipientConnections.filter((connection) => !connection.effective_to)
    const byCustomer = new Map<string, TruckInvoiceRecipientConnection>()
    const priority = (connection: TruckInvoiceRecipientConnection) =>
      connection.relationship_type === 'default_payer' && connection.is_primary ? 0
        : connection.relationship_type === 'default_payer' ? 1
          : connection.relationship_type === 'owner' ? 2 : 3
    for (const connection of active) {
      const existing = byCustomer.get(connection.customer_id)
      if (!existing || priority(connection) < priority(existing)) byCustomer.set(connection.customer_id, connection)
    }
    return [...byCustomer.values()]
      .sort((a, b) => priority(a) - priority(b))
      .map((connection) => ({
        id: connection.customer_id,
        company_name: connection.customer_company_name || 'Company',
        relationship_label: connection.relationship_type === 'default_payer'
          ? 'default payer'
          : connection.relationship_type === 'owner' ? 'owner / lessor' : 'operating authority',
      }))
  }, [truckRecipientConnections])

  useEffect(() => {
    if (!selectedOrder) {
      setInvoiceRecipientId('')
      return
    }
    setInvoiceRecipientId((current) => {
      if (invoiceRecipientOptions.some((option) => option.id === current)) return current
      return invoiceRecipientOptions.find((option) => option.relationship_label === 'default payer')?.id
        || invoiceRecipientOptions.find((option) => option.id === selectedOrder.customer_id)?.id
        || invoiceRecipientOptions[0]?.id
        || selectedOrder.customer_id
    })
  }, [selectedOrder?.id, selectedOrder?.customer_id, invoiceRecipientOptions])

  const { data: recommendedServices, refetch: refetchRecServices, isFetching: recommendedServicesFetching } = useQuery<RecommendedService[]>({
    queryKey: ['recommended-services', selectedOrder?.id],
    queryFn: async ({ signal }) => {
      const response = await api.get(`/repair-orders/${selectedOrder!.id}/recommended-services`, { signal })
      return response.data
    },
    // This is a collapsed optional panel in the active price-builder drawer.
    // Fetch it on intent, while retaining the existing behavior for the
    // non-price-builder legacy detail shell where the list is visible.
    enabled: !!(
      selectedOrder?.id
      && isDetailOpen
      && (
        recommendedServicesOpen
        || !PRICE_BUILDER_STATUSES.includes((orderDetail ?? selectedOrder).status)
      )
    ),
  })

  const addRecServiceMutation = useMutation({
    mutationFn: async (data: { description: string; priority: RecommendedServicePriority; estimated_cost?: number; notes?: string }) => {
      await api.post(`/repair-orders/${selectedOrder!.id}/recommended-services`, data)
    },
    onSuccess: () => {
      setQuoteToConfirm(null)
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

  // The note goes through the generic update. shop_notes is its own column
  // because internal_notes is a JSON envelope the pricer and portal parse —
  // prose there would zero the order's labour total.
  const saveOrderNotesMutation = useMutation({
    mutationFn: async (notes: { customer_notes?: string | null; shop_notes?: string | null }) => {
      const response = await api.put(`/repair-orders/${selectedOrder!.id}`, notes)
      return response.data as RepairOrder
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.id] })
      setSelectedOrder(updated)
      toast.success('Note saved')
    },
    onError: (error: unknown) => toast.error(getErrorDetail(error, 'Could not save the note')),
  })

  const deleteRecServiceMutation = useMutation({
    mutationFn: async (serviceId: string) => {
      await api.delete(`/repair-orders/${selectedOrder!.id}/recommended-services/${serviceId}`)
    },
    onSuccess: () => refetchRecServices(),
  })

  const { data: zelleSettings } = useQuery<{ zelle_email: string | null; zelle_phone: string | null; zelle_qr_image: string | null }>({
    queryKey: ['zelle-settings'],
    queryFn: async ({ signal }) => {
      const response = await api.get('/admin/zelle-settings', { signal })
      return response.data
    },
    enabled: showZelleQrModal,
  })

  const { data: taxFeeSettings } = useQuery<{ labor_rate: number }>({
    queryKey: ['tax-fee-settings'],
    queryFn: async ({ signal }) => {
      const response = await api.get('/admin/tax-fee-settings', { signal })
      return response.data
    },
    // The workspace summary already contains authoritative labor pricing. The
    // tenant default rate is needed to create an order or for the legacy detail
    // editor, neither of which should make every workspace open fetch settings.
    enabled: isModalOpen || Boolean(
      selectedOrder?.id
      && isDetailOpen
      && !PRICE_BUILDER_STATUSES.includes(selectedOrder.status),
    ),
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
    setRecommendedServicesOpen(false)
  }, [selectedOrder?.id])

  // Keep selected values in the option sets even after BaseSelect clears its
  // query or a new service search replaces the result page. This makes the
  // closed controls stable without keeping an entire tenant catalog in memory.
  const customerOptions = useMemo(() => {
    const byId = new Map<string, CustomerTypeaheadItem>()
    customerResults.forEach((item) => byId.set(item.id, item))
    if (selectedCustomerOption) byId.set(selectedCustomerOption.id, selectedCustomerOption)
    return [...byId.values()]
  }, [customerResults, selectedCustomerOption])

  const vehicleOptions = useMemo(() => {
    const byId = new Map<string, VehicleTypeaheadItem>()
    vehicleResults.forEach((item) => byId.set(item.id, item))
    if (selectedVehicleOption) byId.set(selectedVehicleOption.id, selectedVehicleOption)
    return [...byId.values()]
  }, [vehicleResults, selectedVehicleOption])

  const serviceOptions = useMemo(() => {
    const byId = new Map<string, ServiceTypeaheadItem>()
    serviceResults.forEach((item) => byId.set(item.id, item))
    selectedServiceOptions.forEach((item) => byId.set(item.id, item))
    return [...byId.values()]
  }, [serviceResults, selectedServiceOptions])
  const visibleServiceOptions = useMemo(() => {
    return [...serviceOptions].sort((a, b) => {
      const aSelected = selectedServiceIds.includes(a.id)
      const bSelected = selectedServiceIds.includes(b.id)
      if (aSelected === bSelected) return 0
      return aSelected ? -1 : 1
    })
  }, [serviceOptions, selectedServiceIds])

  // The highest reading the shop has for this truck, offered as a starting
  // point so intake is not a retype or a guess.
  const lastKnownMileage = useMemo(() => {
    if (!selectedVehicleId) return null
    const chosen = vehicleOptions.find((vehicle) => vehicle.id === selectedVehicleId)
    return chosen?.last_known_mileage ?? null
  }, [selectedVehicleId, vehicleOptions])

  const filteredVehicles = useMemo(
    () => vehicleOptions.filter((vehicle) => vehicle.customer_id === selectedCustomerId),
    [vehicleOptions, selectedCustomerId],
  )

  // Seed the lookups from each order's denormalized customer/vehicle summary so
  // list rows render without loading the full customer/vehicle tables. Include
  // the selected/detail order as well: a dashboard card can open an older
  // order that is outside the current paginated list page.
  const lookupOrders = [...(orders ?? []), selectedOrder, orderDetail].filter(
    (order): order is RepairOrder => Boolean(order),
  )
  const customerLookup = useMemo(() => {
    const map = new Map<string, CustomerLookupItem>()
    lookupOrders.forEach((o) => {
      if (o?.customer_id) {
        map.set(o.customer_id, {
          id: o.customer_id,
          first_name: o.customer_first_name ?? '',
          last_name: o.customer_last_name ?? '',
          company_name: o.customer_company_name ?? null,
          email: o.customer_email ?? '',
          phone: o.customer_phone ?? null,
        })
      }
    })
    customerOptions.forEach((customer) => map.set(customer.id, customer))
    return map
  }, [lookupOrders, customerOptions])

  const vehicleLookup = useMemo(() => {
    const map = new Map<string, VehicleLookupItem>()
    lookupOrders.forEach((o) => {
      if (o?.vehicle_id) {
        map.set(o.vehicle_id, {
          id: o.vehicle_id,
          customer_id: o.customer_id,
          make: o.vehicle_make || '',
          model: o.vehicle_model || '',
          year: o.vehicle_year,
          unit_number: o.vehicle_unit_number,
          vin: o.vehicle_vin,
          license_plate: null,
        })
      }
    })
    vehicleOptions.forEach((vehicle) => map.set(vehicle.id, vehicle))
    return map
  }, [lookupOrders, vehicleOptions])

  const mechanicLookup = useMemo(() => {
    const map = new Map<string, string>()
    technicianRoster.forEach((m) => map.set(m.mechanic_id, m.mechanic_name))
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

  // Display name for an order in a list row: fleet company for internal ROs,
  // else the customer's company name (primary) / personal name (fallback).
  const orderCustomerName = (order: RepairOrder, customer?: CustomerLookupItem | null, fallback = '—'): string =>
    order.is_internal
      ? (fleetSettings?.fleet_company_name || 'Internal Fleet')
      : customerNameOf(customer, fallback)
  const paymentCompanyName = selectedOrderCustomer?.company_name || 'No company on file'
  const paymentCompanyNameShort = truncateWithEllipsis(paymentCompanyName, 34)
  const paymentTruckUnit = selectedOrderVehicle?.unit_number || 'No unit number'
  const paymentVehicleLabel = selectedOrderVehicle
    ? vehicleDisplayLabel({ ...selectedOrderVehicle, unit_number: null })
    : 'Vehicle info unavailable'
  // Contact person behind the company (distinct from the company name), shown
  // in the Zelle "Payment For" block only when the company has a real contact.
  const paymentContactPerson = selectedOrder?.is_internal ? '' : customerPersonalName(selectedOrderCustomer)
  const paymentContactPhone = selectedOrder?.is_internal ? '' : (selectedOrderCustomer?.phone || '')
  const hasPaymentContact = Boolean(paymentContactPerson || paymentContactPhone)

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

  const clearFormError = (field: keyof RepairOrderFormErrors) => {
    setFormErrors((current) => {
      if (!current[field]) return current
      const next = { ...current }
      delete next[field]
      if (field !== 'root') delete next.root
      return next
    })
  }

  const clearFormErrors = (...fields: (keyof RepairOrderFormErrors)[]) => {
    setFormErrors((current) => {
      let changed = false
      const next = { ...current }
      for (const field of fields) {
        if (next[field]) {
          delete next[field]
          changed = true
        }
      }
      if (changed) delete next.root
      return changed ? next : current
    })
  }

  const fieldError = (message?: string) => (
    message ? <p className="mt-1 text-xs font-medium text-red-600">{message}</p> : null
  )

  const textInputClass = (hasError?: boolean) =>
    `w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors ${
      hasError ? 'border-red-400' : 'border-gray-300'
    }`

  const canEditPriceBuilderByRole = ['garage_owner', 'garage_admin', 'receptionist', 'mechanic'].includes(currentUser?.role || '')
  const canPublishCustomerAuthorization = canPublishAuthorization(currentUser?.role)
  const canVoidInvoices = ['garage_owner', 'garage_admin'].includes(currentUser?.role || '')
  const showLegacyPriceEditor = false
  const detailStatus = (orderDetail ?? selectedOrder)?.status ?? null
  const showPriceBuilder = detailStatus ? PRICE_BUILDER_STATUSES.includes(detailStatus) : false
  const priceBuilderOwnsShell = showPriceBuilder
  const showLaborBreakdown = detailStatus ? LABOR_BREAKDOWN_STATUSES.includes(detailStatus) : false
  const assignmentBypassedInDrawer = !(orderDetail ?? selectedOrder)?.assigned_mechanic_id &&
    detailStatus != null &&
    ['in_progress', 'pending_review', 'completed', 'invoiced', 'paid'].includes(detailStatus)
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

  useEffect(() => {
    setAssignMechanicOpen(!assignmentBypassedInDrawer)
  }, [selectedOrder?.id, assignmentBypassedInDrawer])

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
        unit_number: data.unit_number.trim() || null,
        license_plate: null,
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
      mileage_in_carried,
      attribution,
    }: { customer_id: string; vehicle_id: string; description: string; internal_notes?: string | null; mileage_in?: number | null; mileage_in_carried?: boolean | null; attribution: typeof EMPTY_ATTRIBUTION }) => {
      const response = await api.post('/repair-orders', {
        customer_id,
        vehicle_id,
        description: roDescription || null,
        internal_notes: internal_notes || null,
        mileage_in: mileage_in ?? null,
        mileage_in_carried: mileage_in_carried ?? false,
        ...Object.fromEntries(Object.entries(attribution).map(([key, value]) => [key, value.trim() || null])),
      })
      return response.data as RepairOrder
    },
    onError: (error: unknown) => {
      setFormErrors((current) => ({ ...current, root: getErrorDetail(error, 'Failed to create repair order') }))
    },
  })

  useEffect(() => {
    if (!selectedOrder) return
    setDetailAttributionDraft(Object.fromEntries(Object.keys(EMPTY_ATTRIBUTION).map((key) => [key, String(selectedOrder[key as keyof RepairOrder] ?? '')])) as typeof EMPTY_ATTRIBUTION)
  }, [selectedOrder])

  const saveAttributionMutation = useMutation({
    mutationFn: async () => {
      if (!selectedOrder) throw new Error('No repair order selected')
      const payload = Object.fromEntries(Object.entries(detailAttributionDraft).map(([key, value]) => [key, value.trim() || null]))
      const response = await api.put(`/repair-orders/${selectedOrder.id}`, payload)
      return response.data as RepairOrder
    },
    onSuccess: (order) => {
      setSelectedOrder((current) => current ? { ...current, ...order } : order)
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      toast.success('Attribution saved')
    },
    onError: (error: unknown) => toast.error(getErrorDetail(error, 'Failed to save attribution')),
  })

  const decodeNewVehicleVin = async (rawVin: string, options: { quiet?: boolean } = {}) => {
    const vin = rawVin.trim().toUpperCase()
    if (vin.length < 11) {
      if (!options.quiet) {
        setFormErrors((current) => ({ ...current, vehicleVin: 'VIN must be at least 11 characters.' }))
      }
      return
    }

    clearFormError('vehicleVin')
    setIsDecodingNewVehicleVin(true)
    try {
      const response = await api.get<VINDecodeResult>(`/customers/vin/decode/${encodeURIComponent(vin)}`)
      const result = response.data

      if (result.error_code && result.error_code !== '0') {
        setFormErrors((current) => ({
          ...current,
          vehicleVin: result.error_text || 'We could not decode that VIN. Check the VIN or enter truck details manually.',
        }))
        return
      }

      setNewVehicle((prev) => ({
        ...prev,
        vin: result.vin || vin || prev.vin,
        make: result.make || prev.make,
        model: result.model || prev.model,
        year: result.year?.toString() || prev.year,
      }))
      lastDecodedNewVehicleVin.current = vin

      const decodedLabel = [result.year, result.make, result.model].filter(Boolean).join(' ')
      toast.success(decodedLabel ? `VIN decoded: ${decodedLabel}` : 'VIN decoded')
    } catch (error: unknown) {
      setFormErrors((current) => ({
        ...current,
        vehicleVin: getErrorDetail(error, 'Failed to decode VIN. Check the VIN or enter truck details manually.'),
      }))
    } finally {
      setIsDecodingNewVehicleVin(false)
    }
  }

  const handleNewVehicleVinChange = (value: string) => {
    const vin = value.toUpperCase()
    setNewVehicle((prev) => ({ ...prev, vin }))
    clearFormError('vehicleVin')
    const trimmedVin = vin.trim()
    if (trimmedVin.length === 17 && trimmedVin !== lastDecodedNewVehicleVin.current) {
      void decodeNewVehicleVin(trimmedVin, { quiet: true })
    }
  }

  // Delete/restore/reopen change whether an order shows on the owner's floor
  // board and dashboard, not just the RO lists. The dashboard queue refetches
  // when revisited; the other boards preserve their eager refresh behavior.
  const invalidateOrderBoards = () => {
    queryClient.invalidateQueries({ queryKey: ['dashboard-action-queue'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard-daily-workset'] })
    for (const key of [
      'repair-orders',
      'customerRepairOrders',
      'mechanic-board-team',
      'mechanic-board-detail',
      'fleet-board-summary',
    ]) {
      queryClient.invalidateQueries({ queryKey: [key], refetchType: 'all' })
    }
  }

  const deleteRepairOrderMutation = useMutation({
    // Capture the order number up front — after the delete the order is gone from
    // the lists, so the toast has nothing to look it up from.
    mutationFn: async (orderId: string) => {
      const orderNumber =
        (orderDetail?.id === orderId ? orderDetail.order_number : undefined) ??
        (selectedOrder?.id === orderId ? selectedOrder.order_number : undefined)
      await api.delete(`/repair-orders/${orderId}`)
      return { orderId, orderNumber }
    },
    // Mark the card as deleting the moment the (possibly slow) request starts, so
    // the list shows a clear in-flight state instead of appearing frozen.
    onMutate: (orderId: string) => setDeletingOrderId(orderId),
    onSuccess: ({ orderId, orderNumber }) => {
      if (selectedOrder?.id === orderId) {
        closeDetail()
      }
      toast.success(orderNumber ? `Repair order ${orderNumber} deleted` : 'Repair order deleted')
      // Let the card play its fade+collapse exit before the refetch drops it.
      window.setTimeout(() => {
        setDeletingOrderId(null)
        invalidateOrderBoards()
      }, 320)
    },
    onError: (error: unknown) => {
      setDeletingOrderId(null)
      toast.error(getErrorDetail(error, 'Failed to delete repair order'))
    },
  })

  const restoreRepairOrderMutation = useMutation({
    mutationFn: async (orderId: string) => {
      const response = await api.post(`/repair-orders/${orderId}/restore`)
      return response.data as { order: RepairOrder; stock_shortages: string[] }
    },
    onSuccess: ({ order: updated, stock_shortages }) => {
      invalidateOrderBoards()
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.id] })
      queryClient.invalidateQueries({ queryKey: ['price-build', updated.id] })
      queryClient.invalidateQueries({ queryKey: ['inventory-typeahead'] })
      setSelectedOrder(updated)
      toast.success(`Repair order ${updated.order_number} restored`)
      // While the order sat deleted its parts went back on the shelf and may
      // have been used elsewhere — say so rather than letting stock go silently
      // short.
      if (stock_shortages?.length) {
        toast.error(
          `Restored, but these parts are no longer in stock: ${stock_shortages.join('; ')}`,
          { duration: 8000 },
        )
      }
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

  const overrideTechnicianAssignmentMutation = useMutation({
    mutationFn: async (orderId: string) => {
      const response = await api.post(`/repair-orders/${orderId}/override-start-work`)
      return response.data as RepairOrder
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.id] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      queryClient.invalidateQueries({ queryKey: ['price-build', updated.id] })
      setSelectedOrder(updated)
      toast.success('Work started without assigning a technician')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to start work without a technician'))
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
    mutationFn: async ({
      orderId,
      mileageOut: woOut,
      reviewNotes: managerNotes,
    }: {
      orderId: string
      mileageOut?: number | null
      reviewNotes?: string
    }) => {
      const response = await api.post(`/fleet/work-orders/${orderId}/complete`, {
        mileage_out: woOut ?? null,
        review_notes: managerNotes || null,
      })
      return response.data as { repair_order_id: string; raw_status: RepairOrderStatus }
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.repair_order_id] })
      queryClient.invalidateQueries({ queryKey: ['fleet-board'] })
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-for-order', updated.repair_order_id] })
      queryClient.invalidateQueries({ queryKey: ['price-build', updated.repair_order_id] })
      queryClient.setQueryData<RepairOrderDetail>(
        ['repair-order-detail', updated.repair_order_id],
        prev => prev ? { ...prev, status: updated.raw_status } : prev,
      )
      setSelectedOrder(prev => prev ? { ...prev, status: updated.raw_status } : null)
      setReviewNotes('')
      setMileageOut('')
      toast.success('Repair finalized — invoice created and fleet billing contact notified')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to complete work order'))
    },
  })

  const adminCompleteWorkMutation = useMutation({
    mutationFn: async (orderId: string) => {
      const response = await api.post(`/repair-orders/${orderId}/admin-complete-work`)
      return response.data as RepairOrder
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.id] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      queryClient.invalidateQueries({ queryKey: ['price-build', updated.id] })
      setSelectedOrder(updated)
      toast.success('Work marked complete - ready for review')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to mark work complete'))
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
      setReviewNotes('')
      setMileageOut('')
      if (updated.status === 'invoiced') {
        toast.success('Repair finalized — invoice created and customer notified')
      } else {
        toast('Repair finalized, but the invoice still needs to be created.', { icon: '⚠️' })
      }
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to finalize repair order'))
    },
  })

  const createInvoiceMutation = useMutation({
    mutationFn: async ({
      repairOrderId,
      dueDate,
      billToCustomerId,
    }: {
      repairOrderId: string
      dueDate?: string
      billToCustomerId?: string
    }) => {
      const response = await api.post('/invoices', { 
        repair_order_id: repairOrderId,
        due_date: dueDate || null,
        bill_to_customer_id: billToCustomerId || null,
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

  // Mirrors the server's _manual_collected_amount. The invoice stores the card
  // view (repairs + supplies + card fee + tax on all three, less any discount),
  // so a manual method drops the fee and the tax that fee attracted, and cash
  // drops tax altogether because the shop is tax exempt. Kept in step with
  // payments.py: what the operator is told is what gets recorded.
  const manualCollectedAmount = (invoice: Invoice | null | undefined, method: string | null) => {
    if (!invoice) return 0
    const base = parseMoney(invoice.subtotal) + parseMoney(invoice.shop_supplies_amount)
    const discount = parseMoney(invoice.discount_amount)
    if (method === 'cash') return Math.max(0, base - discount)
    const fee = parseMoney(invoice.service_fee_amount)
    const tax = parseMoney(invoice.tax_amount)
    const cardTaxable = base + fee
    const rate = cardTaxable > 0 ? tax / cardTaxable : 0
    return Math.max(0, Math.round(base * (1 + rate) * 100) / 100 - discount)
  }

  const recordManualPaymentMutation = useMutation({
    mutationFn: async ({
      invoiceId,
      method,
      notes,
      zelleSenderEmail,
      zelleSenderPhone,
      updateCustomerFromSender,
      paymentProvider,
      referenceNumber,
      authorizationNumber,
    }: {
      invoiceId: string
      method: string
      notes?: string
      zelleSenderEmail?: string
      zelleSenderPhone?: string
      updateCustomerFromSender?: boolean
      paymentProvider?: string
      referenceNumber?: string
      authorizationNumber?: string
    }) => {
      const response = await api.post('/payments/record-manual', { 
        invoice_id: invoiceId,
        method,
        notes,
        zelle_sender_email: zelleSenderEmail || null,
        zelle_sender_phone: zelleSenderPhone || null,
        update_customer_from_sender: !!updateCustomerFromSender,
        payment_provider: paymentProvider || null,
        reference_number: referenceNumber || null,
        authorization_number: authorizationNumber || null,
      })
      return response.data as ManualPaymentResponse
    },
    onSuccess: async (data) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['customer-typeahead'] })
      if (selectedOrder?.id) {
        queryClient.invalidateQueries({ queryKey: ['repair-order-detail', selectedOrder.id] })
        setSelectedOrder(prev => prev ? { ...prev, status: 'paid' } : null)
      }
      setShowInvoicePaymentOptions(false)
      setSelectedPaymentMethod('')
      resetManualPaymentConfirmation()
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

  const voidInvoiceMutation = useMutation({
    mutationFn: async ({ invoiceId, reason }: { invoiceId: string; reason: string }) => {
      const response = await api.post(`/invoices/${invoiceId}/void`, { reason })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-for-order'] })
      setSelectedOrder(prev => prev ? { ...prev, status: 'pending_review' } : null)
      setShowVoidInvoiceConfirm(false)
      setVoidInvoiceReason('')
      toast.success('Invoice voided and preserved. The order is open for revision.')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to void invoice'))
    },
  })

  const refundQuickBooksMutation = useMutation({
    mutationFn: async ({ paymentId, amount, reason }: { paymentId: string; amount?: string; reason: string }) => {
      const response = await api.post(`/quickbooks/payments/${paymentId}/refund`, {
        amount: amount ? Number(amount) : null,
        reason,
      })
      return response.data as { message?: string }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-for-order'] })
      setSelectedOrder(prev => prev ? { ...prev, status: 'invoiced' } : null)
      toast.success(data.message || 'QuickBooks refund submitted')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'QuickBooks refund failed'))
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

  const refreshAuthorizationState = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] }),
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] }),
      queryClient.invalidateQueries({ queryKey: ['quote', selectedOrder?.id] }),
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', selectedOrder?.id] }),
      queryClient.invalidateQueries({ queryKey: ['authorization-history', selectedOrder?.id] }),
      refetchQuote(),
      refetchOrderDetail(),
      workspaceHistoryRequested ? refetchAuthorizationHistory() : Promise.resolve(),
    ])
  }

  const createQuoteMutation = useMutation({
    mutationFn: async (repair_order_id: string) => {
      const response = await api.post('/quotes', { repair_order_id })
      return response.data as Quote
    },
    onSuccess: (quote, orderId) => {
      setQuoteSent(false)
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['quote', orderId] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', orderId] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      refetchQuote()
      refetchOrderDetail()
      toast.success(
        quote.authorization_type === 'additional_work'
          ? `Additional-work authorization ${quote.quote_number} draft ready`
          : `Estimate ${quote.quote_number} draft ready`
      )
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to create estimate'))
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
      toast.success(`Estimate ${quote.quote_number} updated — $${parseFloat(quote.total_amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}`)
    },
    onError: (error: unknown) => {
      if (isAuthorizationConflict(error)) {
        setQuoteToConfirm(null)
        void refreshAuthorizationState()
        toast.error(AUTHORIZATION_CONFLICT_MESSAGE)
        return
      }
      toast.error(getErrorDetail(error, 'Failed to update estimate'))
    },
  })

  const sendQuoteMutation = useMutation({
    mutationFn: async (quoteId: string) => {
      const response = await api.post(`/quotes/${quoteId}/send`)
      return response.data as Quote
    },
    onSuccess: (sentQuote) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      queryClient.invalidateQueries({ queryKey: ['authorization-history'] })
      if (selectedOrder?.id) {
        queryClient.invalidateQueries({ queryKey: ['quote', selectedOrder.id] })
        refetchQuote()
      }
      setQuoteSent(true)
      setQuoteToConfirm(null)
      toast.success(
        sentQuote.authorization_type === 'additional_work'
          ? 'Additional work sent — awaiting customer authorization'
          : sentQuote.is_approved
            ? 'Initial estimate published and authorized under the customer threshold'
            : 'Estimate sent — awaiting customer authorization'
      )
    },
    onError: (error: unknown) => {
      if (isAuthorizationConflict(error)) {
        setQuoteSent(false)
        setQuoteToConfirm(null)
        void refreshAuthorizationState()
        toast.error(AUTHORIZATION_CONFLICT_MESSAGE)
        return
      }
      toast.error(getErrorDetail(error, 'Failed to send estimate'))
    },
  })

  const [quoteSent, setQuoteSent] = useState(false)
  const [quoteToConfirm, setQuoteToConfirm] = useState<Quote | null>(null)
  const keepEditingButtonRef = useRef<HTMLButtonElement>(null)

  const closeQuoteConfirmation = () => {
    setQuoteToConfirm(null)
  }

  // Status filter and search are applied server-side now, so the rendered list
  // is simply the current page returned by the API.
  const filteredOrders = orders

  // Keyboard left/right arrow navigation between orders when detail panel is
  // open. Delegates to goToNextOrder/goToPrevOrder (defined below, but
  // already in scope by the time this effect runs post-render) so arrow keys
  // cross a list-page boundary the same way the drawer's Next/Prev buttons do.
  useEffect(() => {
    if (!isDetailOpen || !filteredOrders || !selectedOrder) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
      const target = e.target as HTMLElement
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable) return
      if (e.key === 'ArrowLeft') goToPrevOrder()
      if (e.key === 'ArrowRight') goToNextOrder()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDetailOpen, filteredOrders, selectedOrder])

  // Land on the row the drawer was walking towards once the page carrying it
  // has arrived. Placed before the loading early-return below so the hook order
  // stays identical across renders.
  useEffect(() => {
    if (pendingNavIndex === null || !orders) return
    const target = orders[pendingNavIndex]
    if (!target) return
    setPendingNavIndex(null)
    openDetail(target)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingNavIndex, orders])

  if (isLoading || (workbenchScope === 'daily' && Boolean(workQueueLane) && isDailyWorkbenchLoading)) {
    if (presentationVariant === 'new') {
      return (
        <RepairOrdersLedger
          rows={[]}
          totalOrders={0}
          searchQuery={searchQuery}
          statusFilter={statusFilter}
          statusOptions={[{ value: 'all', label: 'All' }]}
          selectedId={searchParams.get('selected')}
          queueOrigin={workbenchScope === 'daily' ? null : workQueueLane}
          isFetching={isFetching || isDailyWorkbenchFetching}
          loadedCount={0}
          hasMore={false}
          isLoadingMore={false}
          onSearchChange={setSearchQuery}
          onStatusChange={setStatusFilter}
          onOpenOrder={() => undefined}
          onCreateOrder={() => undefined}
          onShowAllOrders={showAllOrders}
          onLoadMore={() => undefined}
        />
      )
    }
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
                value={searchQuery}
                readOnly
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
              <Spinner size="xs" />
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

  // Dashboard-originated navigation follows its full ordered queue. Normal
  // list navigation retains the existing 25-row page/cross-page behavior.
  const workQueueNavIndex = selectedOrder
    ? workQueueOrderIds.indexOf(selectedOrder.id)
    : -1
  const isWorkQueueNavigation = workQueueNavIndex >= 0
  const navigationOrders = filteredOrders ?? []
  const currentNavIndex = selectedOrder
    ? navigationOrders.findIndex(o => o.id === selectedOrder.id)
    : -1
  const isAtLastLoaded = currentNavIndex >= 0 && currentNavIndex === navigationOrders.length - 1
  // Walking past the last loaded order pulls the next page instead of jumping a
  // window. Nothing above is ever unloaded, so there is no backwards equivalent.
  const canLoadMoreForNav = isAtLastLoaded && Boolean(hasNextPage)
  const showNavigation = isWorkQueueNavigation || (navigationOrders.length > 1 && currentNavIndex >= 0)
  const hasPrev = isWorkQueueNavigation
    ? workQueueNavIndex > 0
    : currentNavIndex > 0
  const hasNext = isWorkQueueNavigation
    ? workQueueNavIndex < workQueueOrderIds.length - 1
    : (currentNavIndex >= 0 && currentNavIndex < navigationOrders.length - 1) || canLoadMoreForNav
  // The loaded list is the list, so the index is already the true position and
  // needs no projection across pages.
  const globalNavPosition = isWorkQueueNavigation
    ? workQueueNavIndex + 1
    : currentNavIndex >= 0 ? currentNavIndex + 1 : 0
  const globalNavTotal = isWorkQueueNavigation
    ? workQueueOrderIds.length
    : totalOrders || navigationOrders.length

  const goToNextOrder = () => {
    if (isWorkQueueNavigation) {
      if (hasNext) openWorkQueueOrder(workQueueOrderIds[workQueueNavIndex + 1])
      return
    }
    if (currentNavIndex >= 0 && currentNavIndex < navigationOrders.length - 1) {
      openDetail(navigationOrders[currentNavIndex + 1])
      return
    }
    if (canLoadMoreForNav) {
      // Land on the first row that arrives, which is the one after the current
      // end of the list.
      setPendingNavIndex(navigationOrders.length)
      void fetchNextPage()
    }
  }

  const goToPrevOrder = () => {
    if (isWorkQueueNavigation) {
      if (hasPrev) openWorkQueueOrder(workQueueOrderIds[workQueueNavIndex - 1])
      return
    }
    if (currentNavIndex > 0) {
      openDetail(navigationOrders[currentNavIndex - 1])
      return
    }
  }

  const quoteActionPending = createQuoteMutation.isPending || updateQuoteMutation.isPending || sendQuoteMutation.isPending
  const quoteOrder = orderDetail ?? selectedOrder
  const quoteOrderStatus = quoteOrder?.status
  const quoteIsApproved = !!quoteForOrder?.is_approved
  const quoteIsDeclined = !!quoteForOrder?.is_declined
  const quoteIsSent = !!(quoteForOrder?.sent_to_customer || quoteSent)
  const quoteCanChange = !!quoteOrderStatus && !['completed', 'invoiced', 'paid', 'cancelled'].includes(quoteOrderStatus)
  const quoteTotalDelta = quoteForOrder && quoteOrder
    ? (parseFloat(quoteOrder.total_cost || '0') || 0) - (parseFloat(quoteForOrder.total_amount || '0') || 0)
    : 0
  const quoteTotalMismatch = !!quoteForOrder && !!quoteOrder && !quoteIsApproved && (
    Math.abs((parseFloat(quoteForOrder.total_amount || '0') || 0) - (parseFloat(quoteOrder.total_cost || '0') || 0)) > 0.005
  )
  const effectiveQuoteNeedsUpdate = !!quoteForOrder && !quoteIsApproved && quoteTotalMismatch
  const additionalAuthorizationRequired = quoteIsApproved && quoteTotalDelta > 0.005
  // A declined additional-work revision is closed. It must not block a new
  // revision when the live total still exceeds the last amount the customer
  // actually approved. Compare against that preserved baseline, not against
  // the declined revision's unchanged total.
  const declinedAuthorizationDelta = quoteForOrder && quoteOrder && quoteIsDeclined
    ? (parseFloat(quoteOrder.total_cost || '0') || 0) - (parseFloat(quoteForOrder.previously_authorized_amount || '0') || 0)
    : 0
  const declinedAdditionalAuthorizationRequired = !!quoteForOrder
    && quoteForOrder.authorization_type === 'additional_work'
    && quoteIsDeclined
    && declinedAuthorizationDelta > 0.005
  const quoteActionLabel = declinedAdditionalAuthorizationRequired
    ? 'Create revised authorization'
    : additionalAuthorizationRequired
    ? `Authorize +$${quoteTotalDelta.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : quoteIsApproved
    ? (quoteForOrder?.authorization_type === 'additional_work' ? 'Additional work authorized' : 'Estimate authorized')
    : quoteForOrder
      ? quoteIsSent
        ? (
          effectiveQuoteNeedsUpdate
            ? (quoteForOrder.authorization_type === 'additional_work' ? 'Revise additional work' : 'Revise estimate')
            : 'Awaiting authorization'
        )
        : (quoteForOrder.authorization_type === 'additional_work' ? 'Send additional work' : 'Send estimate')
        : 'Create estimate'
  const quoteActionDisabled = (quoteIsApproved && !additionalAuthorizationRequired)
    || !quoteCanChange
    || (quoteIsSent && !effectiveQuoteNeedsUpdate && !quoteIsApproved && !declinedAdditionalAuthorizationRequired)
  const quoteDisabledReason = quoteIsApproved && !additionalAuthorizationRequired
    ? 'This estimate is authorized. The live repair order remains editable until finalization.'
    : !quoteCanChange
      ? 'Estimates are unavailable after the repair order is finalized.'
      : quoteIsDeclined && !declinedAdditionalAuthorizationRequired
        ? 'This declined revision is closed. Add more work before creating another authorization.'
      : quoteIsSent && !effectiveQuoteNeedsUpdate
        ? 'The estimate has been sent. It can be resent if its amount changes.'
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
    const orderHistoryEvents = orderDetail?.history_events ?? []
    const nonAuthorizationHistoryEvents = orderHistoryEvents.filter(
      (event) => !event.event_type.startsWith('authorization_'),
    )
    const canonicalAuthorizationEvents = canonicalizeAuthorizationHistoryEvents(
      orderHistoryEvents,
      authorizationHistory?.events ?? [],
    )
    const persistedHistoryEvents = [
      ...nonAuthorizationHistoryEvents,
      ...canonicalAuthorizationEvents,
    ]
    const persistedHistoryEventTypes = new Set(persistedHistoryEvents.map((event) => event.event_type))

    push({
      id: 'created',
      label: 'Repair order created',
      at: order.created_at,
      detail: order.order_number,
      actor: customerActor,
    })
    events.push(...buildPartHistoryEvents(orderDetail?.parts_usage ?? [], nonAuthorizationHistoryEvents))
    events.push(...canonicalAuthorizationEvents
      .map((event) => ({
        id: event.id,
        label: event.label,
        at: event.created_at,
        detail: formatAuthorizationEventDetail(event.detail),
        actor: event.actor_name || undefined,
      })))
    push({
      id: 'quote-created',
      label: quoteForOrder?.authorization_type === 'additional_work'
        ? 'Additional-work draft created'
        : 'Estimate draft created',
      at: quoteForOrder?.created_at,
      detail: quoteForOrder?.quote_number,
    })
    if (!persistedHistoryEventTypes.has('authorization_published')) {
      push({
        id: 'quote-sent',
        label: quoteForOrder?.authorization_type === 'additional_work'
          ? 'Additional work sent to customer'
          : 'Estimate sent to customer',
        at: quoteForOrder?.sent_at,
        detail: quoteForOrder?.quote_number,
        actor: customerActor,
      })
    }
    if (
      !persistedHistoryEventTypes.has('authorization_customer_approved')
      && !persistedHistoryEventTypes.has('authorization_threshold_approved')
    ) {
      push({
        id: 'quote-approved',
        label: quoteForOrder?.authorization_type === 'additional_work'
          ? 'Additional work authorized'
          : 'Estimate authorized',
        at: quoteForOrder?.is_approved ? quoteForOrder.updated_at : null,
        detail: quoteForOrder?.quote_number,
        actor: customerActor,
      })
    }
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
    if (!persistedHistoryEventTypes.has('admin_override_started_work')) {
      push({
        id: 'started',
        label: assignedTechnician ? 'Work started' : 'Work started by admin override',
        at: order.work_started_at,
        detail: assignedTechnician ? undefined : 'Technician assignment was bypassed; work is being handled outside the mechanic portal.',
        actor: assignedTechnician,
      })
    }
    if (!persistedHistoryEventTypes.has('admin_completed_work')) {
      push({
        id: 'completed',
        label: assignedTechnician ? 'Technician completed work' : 'Work marked complete by admin',
        at: order.work_completed_at,
        detail: assignedTechnician ? undefined : 'Completed outside the mechanic portal.',
        actor: assignedTechnician,
      })
    }
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
    if (
      !canPublishCustomerAuthorization
      || !selectedOrder?.id
      || quoteActionPending
      || quoteActionDisabled
    ) return
    if (!quoteForOrder) {
      createQuoteMutation.mutate(selectedOrder.id)
      return
    }
    if (declinedAdditionalAuthorizationRequired) {
      createQuoteMutation.mutate(selectedOrder.id)
      return
    }
    if (additionalAuthorizationRequired) {
      createQuoteMutation.mutate(selectedOrder.id)
      return
    }
    try {
      if (quoteIsSent) {
        createQuoteMutation.mutate(selectedOrder.id)
        return
      }
      // Publication is deliberate and always follows a fresh server-side
      // recalculation. The send endpoint revalidates again and returns 409 if
      // another edit or publication wins the race.
      const refreshedQuote = await updateQuoteMutation.mutateAsync(quoteForOrder.id)
      setQuoteToConfirm(refreshedQuote)
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

  const resolveOrderDisplayStatus = (order: Pick<RepairOrder, 'status' | 'quote_sent' | 'quote_approved' | 'pending_zelle_confirmation' | 'hold_reason'>) => {
    const isAwaitingApproval = !!order.quote_sent && !order.quote_approved && order.status !== 'invoiced' && order.status !== 'paid'
    const isPendingZelle = !!order.pending_zelle_confirmation && order.status !== 'paid'
    const isOnHold = order.status === 'in_progress' && !!order.hold_reason
    if (isAwaitingApproval) {
      return {
        label: 'Estimate Pending',
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
      label: order.status === 'draft' ? 'Checked in' : order.status.replace(/_/g, ' '),
      style: getStatusStyle(order.status),
    }
  }

  const shortOrderNumber = (n?: string | null) => {
    if (!n) return '#—'
    const parts = n.split('-')
    return '#' + (parts[parts.length - 1] ?? n)
  }

  const statusDescriptions: Record<string, string> = {
    draft:          'Truck checked in — ready to build, assign, or start.',
    quoted:         'Legacy estimate state — the work order remains active.',
    declined:       'Estimate changes requested — unaffected work may continue.',
    approved:       'Estimate authorized — work may continue.',
    assigned:       'Technician has been assigned — awaiting their acknowledgment.',
    acknowledged:   'Technician acknowledged the job — starting work soon.',
    in_progress:    'Work is actively underway on the vehicle.',
    pending_review: 'Technician finished — waiting on admin to verify and approve the work.',
    completed:      'Work finalized — invoice needs to be sent to the customer.',
    invoiced:       'Invoice sent — waiting on payment from the customer.',
    paid:           'Payment received — order fully closed.',
    cancelled:      'Orders that were cancelled and are no longer active.',
    deleted:        'Deleted orders — restore to bring one back.',
  }

  const canViewDeletedOrders = ['garage_owner', 'garage_admin'].includes(currentUser?.role || '')

  // Show the canonical operational milestones. Legacy estimate outcome states
  // remain readable in order history but are not primary workflow filters.
  const statusOptions = [
    { value: 'all', label: 'All' },
    { value: 'draft', label: 'Checked In' },
    { value: 'assigned', label: 'Assigned' },
    { value: 'in_progress', label: 'In Progress' },
    { value: 'pending_review', label: 'Quality Review' },
    { value: 'completed', label: 'Completed' },
    { value: 'invoiced', label: 'Invoiced' },
    { value: 'paid', label: 'Paid' },
    ...(canViewDeletedOrders ? [{ value: 'deleted', label: 'Deleted' }] : []),
  ].map((option) => ({
    ...option,
    // undefined while the counts are loading, so the filter shows a label
    // rather than a zero it cannot yet stand behind. Deleted is deliberately
    // uncounted: the endpoint counts live rows, so a count here would read as
    // "no deleted orders" when there may be plenty.
    count: option.value === 'deleted' || !statusCounts
      ? undefined
      : statusCounts[option.value] ?? 0,
  }))

  const resetModal = () => {
    setSelectedCustomerId('')
    setSelectedVehicleId('')
    setCustomerQuery('')
    setVehicleQuery('')
    setSelectedCustomerOption(null)
    setSelectedVehicleOption(null)
    setShowNewVehicleForm(false)
    setDescription('')
    setMileageIn('')
    setAttributionDraft(EMPTY_ATTRIBUTION)
    setServiceSearch('')
    setSelectedServiceIds([])
    setSelectedServiceOptions([])
    setNewCustomer({ first_name: '', last_name: '', company_name: '', email: '', phone: '' })
    setNewVehicle({ make: '', model: '', year: '', vin: '', unit_number: '', mileage: '' })
    setFormErrors({})
    lastDecodedNewVehicleVin.current = ''
  }

  const openModal = () => {
    resetModal()
    setIsModalOpen(true)
  }

  const closeModal = () => {
    setIsModalOpen(false)
    resetModal()
  }

  const returnToCustomerSearch = () => {
    setSelectedCustomerId('')
    setSelectedCustomerOption(null)
    setSelectedVehicleId('')
    setSelectedVehicleOption(null)
    setShowNewVehicleForm(false)
    setNewCustomer({ first_name: '', last_name: '', company_name: '', email: '', phone: '' })
    setNewVehicle({ make: '', model: '', year: '', vin: '', unit_number: '', mileage: '' })
    setVehicleQuery('')
    setFormErrors((current) => {
      const next = { ...current }
      const customerDraftFields = [
        'customer',
        'customerFirstName',
        'customerLastName',
        'customerEmail',
        'vehicle',
        'vehicleMake',
        'vehicleModel',
        'vehicleVin',
        'root',
      ] as const
      customerDraftFields.forEach((field) => delete next[field])
      return next
    })
    lastDecodedNewVehicleVin.current = ''
  }

  const validateRepairOrderForm = () => {
    const errors: RepairOrderFormErrors = {}
    const isNewCustomer = selectedCustomerId === 'add_new'
    const shouldCreateVehicle = isNewCustomer || showNewVehicleForm

    if (isNewCustomer) {
      if (!newCustomer.first_name.trim()) errors.customerFirstName = 'First name is required.'
      if (!newCustomer.last_name.trim()) errors.customerLastName = 'Last name is required.'
      if (!newCustomer.email.trim()) errors.customerEmail = 'Email is required.'
      else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newCustomer.email.trim())) errors.customerEmail = 'Enter a valid email address.'
    } else if (!selectedCustomerId) {
      errors.customer = 'Select a customer or add a new one.'
    }

    if (shouldCreateVehicle) {
      if (!newVehicle.make.trim()) errors.vehicleMake = 'Make is required.'
      if (!newVehicle.model.trim()) errors.vehicleModel = 'Model is required.'
    } else if (!selectedVehicleId) {
      errors.vehicle = 'Select an available truck or add a new one.'
    }

    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validateRepairOrderForm()) return

    setIsSubmitting(true)

    try {
      let finalCustomerId = selectedCustomerId
      let finalVehicleId = selectedVehicleId
      const isNewCustomer = selectedCustomerId === 'add_new'

      // New customer flow
      if (isNewCustomer) {
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
        setFormErrors((current) => ({ ...current, customer: 'Select a customer or add a new one.' }))
        return
      }

      // The selected company is the bill-to account for this visit. Selecting
      // an existing truck must never replace it with the truck's current owner;
      // vehicle_id anchors service history while customer_id snapshots billing.
      const shouldCreateVehicle = isNewCustomer || showNewVehicleForm

      if (shouldCreateVehicle) {
        if (!finalCustomerId) {
          setFormErrors((current) => ({ ...current, customer: 'A customer is required before adding a truck.' }))
          return
        }
        if (!newVehicle.make.trim() || !newVehicle.model.trim()) {
          setFormErrors((current) => ({
            ...current,
            vehicleMake: !newVehicle.make.trim() ? 'Make is required.' : current.vehicleMake,
            vehicleModel: !newVehicle.model.trim() ? 'Model is required.' : current.vehicleModel,
          }))
          return
        }
        const createdVehicle = await createVehicleMutation.mutateAsync({
          customer_id: finalCustomerId,
          data: newVehicle,
        })
        finalVehicleId = createdVehicle.id
        finalCustomerId = createdVehicle.customer_id
      } else {
        const vehicle = vehicleOptions.find((item) => item.id === selectedVehicleId)
        if (!vehicle) {
          setFormErrors((current) => ({ ...current, vehicle: 'Selected truck was not found. Select another truck or add a new one.' }))
          return
        }
        finalVehicleId = vehicle.id
      }

      if (!finalCustomerId || !finalVehicleId) {
        setFormErrors((current) => ({ ...current, root: 'Customer and truck are required before creating a repair order.' }))
        return
      }

      const selectedServiceText = selectedServiceOptions
        .filter((svc) => selectedServiceIds.includes(svc.id))
        .map((svc) => svc.name)
        .join(' • ')

      const selectedServicePayload = selectedServiceOptions
        .filter((svc) => selectedServiceIds.includes(svc.id))
        .map((svc) => ({
          id: svc.id,
          name: svc.name,
        }))

      const combinedDescription = [selectedServiceText, description.trim()].filter(Boolean).join(' — ')

      const createdOrder = await createRepairOrderMutation.mutateAsync({
        customer_id: finalCustomerId,
        vehicle_id: finalVehicleId,
        description: combinedDescription,
        internal_notes: null,
        mileage_in: mileageIn.trim() === '' ? null : Number(mileageIn),
        mileage_in_carried: mileageInCarried && mileageIn.trim() !== '',
        attribution: attributionDraft,
      })

      if (selectedServicePayload.length > 0) {
        // Apply sequentially so a stock-failure on one service doesn't abort the rest,
        // and so we can surface a per-service reason to the user.
        const failures: { name: string; reason: string }[] = []
        const warnings: PriceBuildWarning[] = []
        for (const svc of selectedServicePayload) {
          try {
            const response = await api.post(`/repair-orders/${createdOrder.id}/price-build/flat-service`, {
              service_id: svc.id,
              quantity: 1,
            })
            warnings.push(...(response.data?.warnings || []))
          } catch (err) {
            console.error(`Failed to apply service "${svc.name}" to price builder`, err)
            failures.push({ name: svc.name, reason: getErrorDetail(err, 'could not be applied') })
          }
        }
        if (warnings.length > 0) {
          setInitialPriceBuildWarningsByOrder((current) => ({
            ...current,
            [createdOrder.id]: warnings,
          }))
        }
        if (failures.length > 0) {
          const detail = failures.map((f) => `${f.name}: ${f.reason}`).join('; ')
          toast.error(`Repair order created, but ${failures.length} service line${failures.length > 1 ? 's' : ''} failed — ${detail}`)
        }
      }

      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['customer-typeahead'] })
      queryClient.invalidateQueries({ queryKey: ['vehicle-typeahead'] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      toast.success(`Repair order ${createdOrder.order_number} checked in`)
      closeModal()
      // Drop the operator straight into the new order's drawer so they can start
      // building it, instead of hunting for it back in the list.
      openDetail(createdOrder)
    } catch (err: unknown) {
      setFormErrors((current) => ({ ...current, root: getErrorDetail(err, 'Failed to create repair order') }))
    } finally {
      setIsSubmitting(false)
    }
  }

  const newPresentationRows: RepairOrdersLedgerRow[] = (filteredOrders ?? []).map((order) => {
    const display = resolveOrderDisplayStatus(order)
    const parsedServices = parseServiceNotes(order.internal_notes)
    const serviceTotal = parsedServices?.reduce(
      (sum, service) => sum + (parseFloat(service.base_price || '0') || 0),
      0,
    ) || 0
    const partsTotal = parseFloat(order.total_parts_cost ?? '0') || 0
    const laborTotal = serviceTotal > 0 ? serviceTotal : (parseFloat(order.total_labor_cost ?? '0') || 0)
    const statusTone: RepairOrdersLedgerRow['statusTone'] = order.status === 'paid'
      ? 'success'
      : ['invoiced', 'completed'].includes(order.status)
        ? 'success'
        : ['pending_review', 'declined'].includes(order.status)
          ? 'warning'
          : ['assigned', 'acknowledged', 'in_progress'].includes(order.status)
            ? 'active'
            : ['cancelled'].includes(order.status) || Boolean(order.deleted_at)
              ? 'danger'
              : 'neutral'

    return {
      id: order.id,
      orderNumber: order.order_number,
      status: display.label,
      statusTone,
      description: order.description || 'No work description recorded',
      total: `$${(partsTotal + laborTotal).toLocaleString('en-US', { minimumFractionDigits: 2 })}`,
      updated: format(new Date(order.updated_at), 'MMM d, h:mm a'),
      internal: Boolean(order.is_internal),
      customerName: order.customer_company_name
        || [order.customer_first_name, order.customer_last_name].filter(Boolean).join(' ')
        || null,
      vehicleYear: order.vehicle_year ?? null,
      vehicleMake: order.vehicle_make ?? null,
      vehicleModel: order.vehicle_model ?? null,
      vehicleUnitNumber: order.vehicle_unit_number ?? null,
      technicianName: order.assigned_mechanic_id ? mechanicLookup.get(order.assigned_mechanic_id) ?? null : null,
      holdReason: order.hold_reason ?? null,
      quoteSent: order.quote_sent ?? null,
    }
  })

  // A Shop Work lane is a server-backed context, not a decorative label above
  // the global repair-order ledger. Reuse only its compact projection fields;
  // selecting a row still opens the canonical Repair Orders workspace and its
  // existing detail/mutation ownership.
  const workQueueRows: RepairOrdersLedgerRow[] = workQueueOrders
    .filter((order) => {
      const needle = searchQuery.trim().toLowerCase()
      const matchesSearch = !needle || [
        order.order_number,
        order.description,
        order.customer_name,
        order.vehicle_info,
        order.mechanic_name,
      ].some((value) => value?.toLowerCase().includes(needle))
      const matchesStatus = statusFilter === 'all' || order.status === statusFilter
      return matchesSearch && matchesStatus
    })
    .map((order) => {
      const statusTone: RepairOrdersLedgerRow['statusTone'] = order.status === 'paid'
        ? 'success'
        : ['invoiced', 'completed'].includes(order.status)
          ? 'success'
          : ['pending_review'].includes(order.status)
            ? 'warning'
            : ['assigned', 'acknowledged', 'in_progress'].includes(order.status)
              ? 'active'
              : 'neutral'

      return {
        id: order.id,
        orderNumber: order.order_number,
        status: order.status === 'draft'
          ? 'Checked In'
          : order.status.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()),
        statusTone,
        description: order.description || 'No work description recorded',
        total: order.total_cost,
        updated: format(new Date(order.updated_at), 'MMM d, h:mm a'),
        internal: false,
        customerName: order.customer_name,
        vehicleInfo: order.vehicle_info,
        technicianName: order.mechanic_name,
        holdReason: order.hold_reason,
        quoteSent: order.quote_sent,
      }
    })

  const isQueueWorkset = Boolean(workQueueLane)
  const displayedLedgerRows = isQueueWorkset ? workQueueRows : newPresentationRows
  const displayedLedgerTotal = isQueueWorkset ? workQueueOrders.length : totalOrders
  const ledgerStatusOptions = workbenchScope === 'daily'
    ? [{ value: 'all', label: 'All work' }]
    : statusOptions
  const ledgerTitle = workbenchScope === 'daily' ? 'Shop Work' : 'Repair Orders'
  const ledgerDescription = workbenchScope === 'daily'
    ? 'Today’s repair work, ready to operate.'
    : 'Review and update repair work from check-in through payment.'
  return (
    <div className={`db-repair-orders-workspace flex flex-col h-full ${presentationVariant === 'new' ? 'db-repair-orders-workspace--new' : ''} ${presentationVariant === 'new' && isDetailOpen && selectedOrder ? 'db-repair-orders-workspace--detail-open' : ''}`}>
      {presentationVariant === 'new' ? (
        <RepairOrdersLedger
          rows={displayedLedgerRows}
          totalOrders={displayedLedgerTotal}
          searchQuery={searchQuery}
          statusFilter={statusFilter}
          statusOptions={ledgerStatusOptions}
          selectedId={selectedOrder?.id ?? searchParams.get('selected')}
          queueOrigin={workbenchScope === 'daily' ? null : workQueueLane}
          isFetching={isQueueWorkset ? isDailyWorkbenchFetching || isFetching : isFetching}
          errorMessage={(isQueueWorkset ? workQueueErrorForScope : orderPageError) ? 'Check the connection and try again.' : null}
          loadedCount={isQueueWorkset ? displayedLedgerRows.length : loadedOrderCount}
          hasMore={isQueueWorkset ? false : Boolean(hasNextPage)}
          isLoadingMore={isFetchingNextPage}
          showPagination={!isQueueWorkset}
          onSearchChange={setSearchQuery}
          onStatusChange={setStatusFilter}
          onOpenOrder={(id, options) => {
            if (isQueueWorkset) {
              openWorkQueueOrder(id, options)
              return
            }
            const order = filteredOrders?.find((candidate) => candidate.id === id)
            if (order) openDetail(order, options)
          }}
          onCreateOrder={openModal}
          onShowAllOrders={showAllOrders}
          onLoadMore={() => void fetchNextPage()}
          pageTitle={ledgerTitle}
          pageDescription={ledgerDescription}
          sectionTitle={workbenchScope === 'daily' && workQueueLane
            ? `${REPAIR_ORDERS_QUEUE_LABEL[workQueueLane]} · today`
            : 'Order ledger'}
          compact={workbenchScope === 'daily'}
        />
      ) : (
        <>
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
              <Spinner size="md" className="border-white/40 border-t-white" />
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
                    className={`flex items-center gap-3 px-4 py-3 cursor-pointer active:bg-white/5 transition-colors overflow-hidden ${deletingOrderId === order.id ? 'ro-row-deleting' : ''}`}
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
                        className={`hover:bg-white/5 cursor-pointer transition-all duration-300 ${deletingOrderId === order.id ? 'opacity-30 pointer-events-none' : ''}`}
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
                    className={`aspect-square bg-gradient-to-br from-yellow-50 via-amber-100 to-yellow-200 p-4 sm:p-5 rounded-xl shadow-lg flex flex-col justify-between hover:shadow-xl transition-all duration-300 cursor-pointer ${deletingOrderId === order.id ? 'opacity-25 scale-95 pointer-events-none' : ''}`}
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

        {/* Footer: how much of the set is loaded, and one way to load more */}
        {totalOrders > 0 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-white/10 flex-shrink-0 text-sm text-white/70">
            <span>
              Showing {loadedOrderCount} of {totalOrders} order{totalOrders !== 1 ? 's' : ''}
            </span>
            {hasNextPage && (
              <button
                onClick={() => void fetchNextPage()}
                disabled={isFetchingNextPage}
                className="px-3 py-1.5 rounded-lg border border-white/15 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {isFetchingNextPage ? 'Loading…' : 'Load more'}
              </button>
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
        </>
      )}

      {/* New Repair Order Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 overflow-hidden">
          <div className="flex h-full h-[100dvh] items-stretch justify-center sm:items-center sm:p-4">
            <div 
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={closeModal}
            />
            
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="new-repair-order-title"
              className="relative flex h-full h-[100dvh] w-full max-w-4xl flex-col overflow-hidden bg-white shadow-2xl sm:h-auto sm:max-h-[90vh] sm:max-h-[90dvh] sm:rounded-2xl"
            >
              <div className="z-10 shrink-0 border-b border-gray-200 bg-white px-4 py-4 sm:rounded-t-2xl sm:px-6">
                <div className="flex items-center justify-between">
                  <h2 id="new-repair-order-title" className="text-xl font-bold text-gray-900">New Repair Order</h2>
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

              <form
                onSubmit={handleSubmit}
                className="min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain p-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] sm:p-6"
                data-testid="new-repair-order-scroll-region"
              >
                {/* Customer + Vehicle */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">Customer & Vehicle</h3>
                    {selectedCustomerId === 'add_new' && (
                      <button
                        type="button"
                        onClick={returnToCustomerSearch}
                        className="inline-flex min-h-10 shrink-0 items-center gap-1 rounded-lg px-2.5 text-sm font-semibold text-amber-700 transition-colors hover:bg-amber-50 focus:outline-none focus:ring-2 focus:ring-amber-500"
                        aria-label="Back to customer search"
                      >
                        <ChevronLeft className="h-4 w-4" />
                        Back to search
                      </button>
                    )}
                  </div>
                  {formErrors.root ? (
                    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
                      {formErrors.root}
                    </div>
                  ) : null}

                  {selectedCustomerId !== 'add_new' ? (
                    <div className="space-y-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Select Customer</label>
                        <div className="flex items-start gap-3">
                          <div className="flex-1">
                            <CustomerSelect
                              customers={customerOptions}
                              isLoading={isLoadingCustomers && customerOptions.length === 0}
                              searchLoading={isFetchingCustomers}
                              value={selectedCustomerId}
                              onQueryChange={setCustomerQuery}
                              onChange={(val) => {
                                clearFormErrors('customer', 'vehicle', 'root')
                                if (val === 'add_new') {
                                  clearFormErrors('customerFirstName', 'customerLastName', 'customerEmail', 'vehicleMake', 'vehicleModel', 'vehicleVin')
                                  setSelectedCustomerId('add_new')
                                  setSelectedCustomerOption(null)
                                  setSelectedVehicleId('')
                                  setSelectedVehicleOption(null)
                                  setShowNewVehicleForm(true)
                                  return
                                }
                                clearFormErrors('customerFirstName', 'customerLastName', 'customerEmail', 'vehicleMake', 'vehicleModel', 'vehicleVin')
                                setSelectedCustomerOption(customerOptions.find((customer) => customer.id === val) || null)
                                setSelectedCustomerId(val)
                                setSelectedVehicleId('')
                                setSelectedVehicleOption(null)
                                setVehicleQuery('')
                                setShowNewVehicleForm(false)
                              }}
                            />
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              clearFormErrors('customer', 'vehicle', 'root')
                              clearFormErrors('customerFirstName', 'customerLastName', 'customerEmail', 'vehicleMake', 'vehicleModel', 'vehicleVin')
                              setSelectedCustomerId('add_new')
                              setSelectedCustomerOption(null)
                              setSelectedVehicleId('')
                              setSelectedVehicleOption(null)
                              setShowNewVehicleForm(true)
                            }}
                            className="inline-flex h-[42px] items-center gap-1 px-3 text-sm font-medium text-amber-700 border border-amber-200 rounded-lg hover:bg-amber-50 transition-colors"
                          >
                            <Plus className="w-4 h-4" />
                            Add
                          </button>
                        </div>
                        {fieldError(formErrors.customer)}
                      </div>

                      {selectedCustomerId && selectedCustomerId !== 'add_new' && (
                        <div>
                          <div className="mb-2">
                            <h4 className="text-sm font-semibold text-gray-800">Available trucks</h4>
                          </div>
                          <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
                            <div className="relative flex-1">
                              <input
                                value={vehicleQuery}
                                onChange={(event) => setVehicleQuery(event.target.value)}
                                placeholder="Filter by unit, VIN, plate, make, or model"
                                className="h-[42px] w-full rounded-lg border border-gray-300 bg-white px-4 pr-10 text-sm text-gray-900 placeholder:text-gray-400 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500"
                              />
                              {isFetchingVehicles && <Spinner size="sm" className="absolute right-3 top-1/2 -translate-y-1/2" />}
                            </div>
                            <button
                              type="button"
                              onClick={() => {
                                clearFormErrors('vehicle', 'vehicleMake', 'vehicleModel', 'root')
                                setSelectedVehicleId('')
                                setSelectedVehicleOption(null)
                                setShowNewVehicleForm(true)
                              }}
                              className="inline-flex h-[42px] items-center gap-1 px-3 text-sm font-medium text-amber-700 border border-amber-200 rounded-lg hover:bg-amber-50 transition-colors"
                            >
                              <Plus className="w-4 h-4" />
                              Add
                            </button>
                          </div>
                          {isLoadingVehicles ? (
                            <div className="flex min-h-24 items-center justify-center rounded-lg border border-dashed border-gray-200 bg-gray-50 text-sm text-gray-500">
                              <Spinner size="sm" className="mr-2" /> Loading company trucks…
                            </div>
                          ) : filteredVehicles.length > 0 ? (
                            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                              {filteredVehicles.map((vehicle) => {
                                const selected = selectedVehicleId === vehicle.id
                                const vehicleName = vehicleDisplayLabel(vehicle, { includeYear: false })
                                const unitLabel = vehicle.unit_number ? `Unit ${vehicle.unit_number}` : 'Unit not assigned'
                                return (
                                  <button
                                    key={vehicle.id}
                                    type="button"
                                    aria-label={`Select ${vehicleName} · ${unitLabel}`}
                                    title={`${vehicleName} · ${unitLabel}`}
                                    onClick={() => {
                                      clearFormErrors('vehicle', 'vehicleMake', 'vehicleModel', 'root')
                                      setSelectedVehicleId(vehicle.id)
                                      setSelectedVehicleOption(vehicle)
                                      setShowNewVehicleForm(false)
                                    }}
                                    className={`min-w-0 rounded-md border px-3 py-2 text-left transition-all ${
                                      selected
                                        ? 'border-amber-500 bg-white ring-2 ring-amber-200'
                                        : 'border-gray-200 bg-white/60 hover:border-amber-300'
                                    }`}
                                  >
                                    <p className="truncate text-sm font-semibold leading-tight text-slate-900">
                                      {vehicleName}
                                    </p>
                                    <p className="mt-1 truncate text-xs font-medium uppercase tracking-wide text-slate-500">
                                      {unitLabel}
                                    </p>
                                  </button>
                                )
                              })}
                            </div>
                          ) : (
                            <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-4 py-5 text-center text-sm text-gray-500">
                              {vehicleQuery.trim() ? 'No company trucks match this search.' : 'No trucks are listed for this company yet.'}
                            </div>
                          )}
                          {fieldError(formErrors.vehicle)}
                        </div>
                      )}

                      {(showNewVehicleForm || selectedCustomerId === 'add_new') && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                          <VehicleMakePicker
                            value={newVehicle.make}
                            onChange={(make) => {
                              clearFormError('vehicleMake')
                              setNewVehicle((prev) => ({ ...prev, make }))
                            }}
                            error={formErrors.vehicleMake}
                          />
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                            <input
                              name="model"
                              value={newVehicle.model}
                              onChange={(e) => {
                                clearFormError('vehicleModel')
                                setNewVehicle((prev) => ({ ...prev, model: e.target.value }))
                              }}
                              className={textInputClass(!!formErrors.vehicleModel)}
                              placeholder="579, Cascadia..."
                            />
                            {fieldError(formErrors.vehicleModel)}
                          </div>
                          <YearPicker
                            value={newVehicle.year}
                            onChange={(year) => setNewVehicle((prev) => ({ ...prev, year }))}
                          />
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">VIN</label>
                            <div className="flex gap-2">
                              <input
                                name="vin"
                                value={newVehicle.vin}
                                onChange={(e) => handleNewVehicleVinChange(e.target.value)}
                                className={`min-w-0 flex-1 px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors uppercase ${formErrors.vehicleVin ? 'border-red-400' : 'border-gray-300'}`}
                                placeholder="1XPBDP9X8JD123456"
                                maxLength={17}
                              />
                              <button
                                type="button"
                                onClick={() => decodeNewVehicleVin(newVehicle.vin)}
                                disabled={isDecodingNewVehicleVin || newVehicle.vin.trim().length < 11}
                                className="inline-flex items-center gap-2 px-3 py-2.5 bg-gray-100 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed text-gray-700 font-medium rounded-lg transition-colors"
                              >
                                {isDecodingNewVehicleVin ? <Spinner size="xs" /> : <Search className="w-4 h-4" />}
                                Decode
                              </button>
                            </div>
                            {fieldError(formErrors.vehicleVin)}
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Unit number</label>
                            <input
                              name="unit_number"
                              value={newVehicle.unit_number}
                              onChange={(e) => setNewVehicle((prev) => ({ ...prev, unit_number: e.target.value }))}
                              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                              placeholder="369"
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
                          onChange={(e) => {
                            clearFormError('customerFirstName')
                            setNewCustomer((prev) => ({ ...prev, first_name: e.target.value }))
                          }}
                          className={textInputClass(!!formErrors.customerFirstName)}
                          placeholder="Acme"
                        />
                        {fieldError(formErrors.customerFirstName)}
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
                        <input
                          name="last_name"
                          value={newCustomer.last_name}
                          onChange={(e) => {
                            clearFormError('customerLastName')
                            setNewCustomer((prev) => ({ ...prev, last_name: e.target.value }))
                          }}
                          className={textInputClass(!!formErrors.customerLastName)}
                          placeholder="Doe"
                        />
                        {fieldError(formErrors.customerLastName)}
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
                          onChange={(e) => {
                            clearFormError('customerEmail')
                            setNewCustomer((prev) => ({ ...prev, email: e.target.value }))
                          }}
                          className={textInputClass(!!formErrors.customerEmail)}
                          placeholder="fleet@acme.com"
                        />
                        {fieldError(formErrors.customerEmail)}
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
                        onChange={(make) => {
                          clearFormError('vehicleMake')
                          setNewVehicle((prev) => ({ ...prev, make }))
                        }}
                        error={formErrors.vehicleMake}
                      />
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                        <input
                          name="model"
                          value={newVehicle.model}
                          onChange={(e) => {
                            clearFormError('vehicleModel')
                            setNewVehicle((prev) => ({ ...prev, model: e.target.value }))
                          }}
                          className={textInputClass(!!formErrors.vehicleModel)}
                          placeholder="579, Cascadia..."
                        />
                        {fieldError(formErrors.vehicleModel)}
                      </div>
                      <YearPicker
                        value={newVehicle.year}
                        onChange={(year) => setNewVehicle((prev) => ({ ...prev, year }))}
                      />
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">VIN</label>
                        <div className="flex gap-2">
                          <input
                            name="vin"
                            value={newVehicle.vin}
                            onChange={(e) => handleNewVehicleVinChange(e.target.value)}
                            className={`min-w-0 flex-1 px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors uppercase ${formErrors.vehicleVin ? 'border-red-400' : 'border-gray-300'}`}
                            placeholder="1XPBDP9X8JD123456"
                            maxLength={17}
                          />
                          <button
                            type="button"
                            onClick={() => decodeNewVehicleVin(newVehicle.vin)}
                            disabled={isDecodingNewVehicleVin || newVehicle.vin.trim().length < 11}
                            className="inline-flex items-center gap-2 px-3 py-2.5 bg-gray-100 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed text-gray-700 font-medium rounded-lg transition-colors"
                          >
                            {isDecodingNewVehicleVin ? <Spinner size="xs" /> : <Search className="w-4 h-4" />}
                            Decode
                          </button>
                        </div>
                        {fieldError(formErrors.vehicleVin)}
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Unit number</label>
                        <input
                          name="unit_number"
                          value={newVehicle.unit_number}
                          onChange={(e) => setNewVehicle((prev) => ({ ...prev, unit_number: e.target.value }))}
                          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                          placeholder="369"
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
                      <input
                        value={serviceSearch}
                        onChange={(event) => setServiceSearch(event.target.value)}
                        placeholder="Search services (e.g., oil change, brake, diagnostics)"
                        className="w-full pl-10 pr-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors text-gray-900 placeholder-gray-400"
                      />
                      {isFetchingServices && <Spinner size="sm" className="absolute right-3 top-1/2 -translate-y-1/2" />}
                      <svg
                        className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 pointer-events-none"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                      </svg>
                    </div>

                    <div className="db-service-quickpick flex min-h-[46px] flex-nowrap items-center gap-1.5 overflow-x-auto">
                      {visibleServiceOptions
                        .slice(0, 7)
                        .map((svc) => {
                          const active = selectedServiceIds.includes(svc.id)
                          return (
                            <span
                              key={svc.id}
                              className={`inline-flex shrink-0 items-center overflow-hidden rounded-full border pe-1.5 text-[11px] font-medium leading-4 transition-colors ${
                                active
                                  ? 'border-amber-500 bg-amber-50 text-amber-700'
                                  : 'border-gray-200 bg-white hover:border-amber-300 text-gray-700'
                              }`}
                            >
                              <button
                                type="button"
                                onClick={() => {
                                  if (active) {
                                    setSelectedServiceIds((prev) => prev.filter((id) => id !== svc.id))
                                    setSelectedServiceOptions((prev) => prev.filter((item) => item.id !== svc.id))
                                  } else {
                                    setSelectedServiceIds((prev) => [...prev, svc.id])
                                    setSelectedServiceOptions((prev) => [...prev.filter((item) => item.id !== svc.id), svc])
                                  }
                                }}
                                className="ps-2.5 pe-1.5 focus:outline-none"
                              >
                                {svc.name}
                              </button>
                              {active && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setSelectedServiceIds((prev) => prev.filter((id) => id !== svc.id))
                                    setSelectedServiceOptions((prev) => prev.filter((item) => item.id !== svc.id))
                                  }}
                                  className="inline-flex w-4 shrink-0 items-center justify-center self-stretch leading-none text-amber-700 hover:text-amber-900"
                                  aria-label={`Remove ${svc.name}`}
                                >
                                  <X aria-hidden="true" className="h-3 w-3" />
                                </button>
                              )}
                            </span>
                          )
                        })}

                      {!isFetchingServices && !isLoadingServices && serviceOptions.length === 0 && (
                        <span className="self-start text-xs text-gray-500">No matching services found</span>
                      )}
                    </div>

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
                  <div className="mb-1 flex min-h-[20px] items-baseline justify-between gap-3">
                    <label className="text-sm font-medium text-gray-700">Mileage In</label>
                    {lastKnownMileage !== null && (
                      mileageInCarried ? (
                        <span className="shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700 ring-1 ring-amber-200">
                          Carried from last visit
                        </span>
                      ) : (
                        <span className="shrink-0 text-xs text-gray-500">
                          Last on record: {lastKnownMileage.toLocaleString()}{' '}
                          <button
                            type="button"
                            onClick={() => { setMileageIn(String(lastKnownMileage)); setMileageInCarried(true) }}
                            className="db-inline-text-action font-semibold text-amber-700 underline-offset-2 hover:underline"
                          >
                            Use this
                          </button>
                        </span>
                      )
                    )}
                  </div>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={mileageIn}
                    onChange={(e) => { const v = e.target.value; if (v === '' || /^\d+$/.test(v)) { setMileageIn(v); setMileageInCarried(false) } }}
                    className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                    placeholder="Odometer reading when the vehicle arrived"
                  />
                </div>

                <details className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <summary className="cursor-pointer text-sm font-semibold text-gray-700">Marketing attribution</summary>
                  <p className="mt-2 text-xs text-gray-500">Optional IDs used to connect paid repair revenue to CallRail and advertising campaigns.</p>
                  <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {([
                      ['lead_source_channel', 'Lead source channel'], ['external_lead_id', 'External lead ID'],
                      ['callrail_call_id', 'CallRail call ID'], ['google_click_id', 'Google click ID (GCLID)'],
                      ['gbraid', 'GBRAID'], ['wbraid', 'WBRAID'], ['landing_page_url', 'Landing page URL'],
                      ['utm_source', 'UTM source'], ['utm_medium', 'UTM medium'], ['utm_campaign', 'UTM campaign'],
                      ['utm_term', 'UTM term'], ['utm_content', 'UTM content'],
                    ] as [keyof typeof attributionDraft, string][]).map(([key, label]) => (
                      <label key={key} className={key === 'landing_page_url' ? 'sm:col-span-2' : ''}>
                        <span className="mb-1 block text-xs font-medium text-gray-600">{label}</span>
                        <input value={attributionDraft[key]} onChange={(event) => setAttributionDraft((current) => ({ ...current, [key]: event.target.value }))} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-amber-500 focus:ring-2 focus:ring-amber-500" />
                      </label>
                    ))}
                  </div>
                </details>

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
                      <Spinner size="xs" className="border-white/40 border-t-white" />
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
        layout={presentationVariant === 'new' ? 'workspace' : 'drawer'}
        workspaceFocusRequest={presentationVariant === 'new' && workspaceFocusRequest > 0 ? workspaceFocusRequest : undefined}
        onClose={closeDetail}
        title={selectedOrder ? `#${selectedOrder.order_number}` : ''}
        subtitle="Repair Order"
        headerVariant={presentationVariant === 'new' ? 'minimal' : 'amber'}
        width={presentationVariant === 'new' ? 'max-w-full md:max-w-[84vw] xl:max-w-[76vw] 2xl:max-w-[1400px]' : 'max-w-full sm:max-w-[90vw] xl:max-w-[72vw] 2xl:max-w-[1400px]'}
        panelClassName={presentationVariant === 'new'
          ? `db-repair-order-detail-new${priceBuilderOwnsShell ? ' db-repair-order-detail-new--price-builder' : ''}`
          : ''}
        hideHeader={priceBuilderOwnsShell}
        onPrev={showNavigation || hasPrev ? goToPrevOrder : undefined}
        onNext={showNavigation || hasNext ? goToNextOrder : undefined}
        prevDisabled={!hasPrev}
        nextDisabled={!hasNext}
        navigationLabel={!priceBuilderOwnsShell && showNavigation ? `${globalNavPosition} / ${globalNavTotal}` : undefined}
        headerExtra={
          !priceBuilderOwnsShell && selectedOrder && (() => {
            const detailOrder = orderDetail ?? selectedOrder
            const display = resolveOrderDisplayStatus({
              status: detailOrder.status,
              hold_reason: detailOrder.hold_reason,
              pending_zelle_confirmation: detailOrder.pending_zelle_confirmation,
              quote_sent: quoteForOrder?.sent_to_customer || quoteSent || detailOrder.quote_sent,
              quote_approved: quoteForOrder?.is_approved || detailOrder.quote_approved,
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
                    Delete removes this order from your active lists. Nothing is destroyed —
                    it can be restored later from the Deleted filter.
                  </div>
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
              <Spinner size="xs" />
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
          <div className={priceBuilderOwnsShell
            ? `h-full min-h-0 ${presentationVariant === 'new' ? 'db-repair-order-price-shell-new' : ''}`
            : `p-6 space-y-6 ${presentationVariant === 'new' ? 'db-repair-order-detail-new__body' : ''}`}>

                {!priceBuilderOwnsShell && (
                  <details className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                    <summary className="cursor-pointer text-sm font-semibold text-gray-700">Marketing attribution</summary>
                    <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                      {([
                        ['lead_source_channel', 'Lead source channel'], ['external_lead_id', 'External lead ID'],
                        ['callrail_call_id', 'CallRail call ID'], ['google_click_id', 'Google click ID (GCLID)'],
                        ['gbraid', 'GBRAID'], ['wbraid', 'WBRAID'], ['landing_page_url', 'Landing page URL'],
                        ['utm_source', 'UTM source'], ['utm_medium', 'UTM medium'], ['utm_campaign', 'UTM campaign'],
                        ['utm_term', 'UTM term'], ['utm_content', 'UTM content'],
                      ] as [keyof typeof detailAttributionDraft, string][]).map(([key, label]) => (
                        <label key={key} className={key === 'landing_page_url' ? 'sm:col-span-2' : ''}>
                          <span className="mb-1 block text-xs font-medium text-gray-600">{label}</span>
                          <input value={detailAttributionDraft[key]} onChange={(event) => setDetailAttributionDraft((current) => ({ ...current, [key]: event.target.value }))} disabled={['invoiced', 'paid'].includes(selectedOrder.status)} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm disabled:bg-gray-100" />
                        </label>
                      ))}
                    </div>
                    {!['invoiced', 'paid'].includes(selectedOrder.status) && <button type="button" onClick={() => saveAttributionMutation.mutate()} disabled={saveAttributionMutation.isPending} className="mt-3 rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{saveAttributionMutation.isPending ? 'Saving…' : 'Save attribution'}</button>}
                    {['invoiced', 'paid'].includes(selectedOrder.status) && <p className="mt-3 text-xs text-gray-500">Attribution is locked after invoice finalization.</p>}
                  </details>
                )}

                {/* Quote Workflow — the customer quote/approval flow doesn't
                    apply to internal fleet ROs (the fleet manager runs them). */}
                {!priceBuilderOwnsShell && !selectedOrder.is_internal && (() => {
                  const hasQuote = !!quoteForOrder
                  const isApproved = quoteForOrder?.is_approved
                  const isSent = quoteForOrder?.sent_to_customer || quoteSent
                  const hasMechanic = !!selectedOrder.assigned_mechanic_id
                  const mechanicName = technicianRoster.find(m => m.mechanic_id === selectedOrder.assigned_mechanic_id)?.mechanic_name || 'Assigned'
                  const canAssignTechnicianInline = isApproved && !hasMechanic && (
                    (orderDetail ?? selectedOrder).status === 'approved' || assignmentBypassedInDrawer
                  )
                  const workflowPillClass = (tone: 'success' | 'neutral' | 'warning' | 'action') => ({
                    success: 'bg-emerald-100 text-emerald-800',
                    neutral: 'bg-slate-100 text-slate-700',
                    warning: 'bg-amber-100 text-amber-700',
                    action: 'bg-amber-500 text-white',
                  })[tone]

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
                            <span className={`shrink-0 px-2 py-1 text-xs font-medium rounded-md ${workflowPillClass(hasQuote ? 'success' : 'action')}`}>
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
                          {canPublishCustomerAuthorization && hasQuote && !isApproved && (!isSent || effectiveQuoteNeedsUpdate) ? (
                            <button
                              type="button"
                              onClick={() => handlePriceBuilderQuoteAction()}
                              disabled={sendQuoteMutation.isPending || updateQuoteMutation.isPending}
                              className={`shrink-0 px-2 py-1 text-xs font-medium rounded-md ${
                                isSent
                                  ? 'bg-blue-100 text-blue-700 hover:bg-blue-200'
                                  : 'bg-amber-500 hover:bg-amber-600 text-white'
                              }`}
                            >
                              {quoteActionPending ? 'Working...' : (isSent ? 'Prepare revision' : 'Review & publish')}
                            </button>
                          ) : (
                            <span className={`shrink-0 px-2 py-1 text-xs font-medium rounded-md ${workflowPillClass(isApproved ? 'success' : 'neutral')}`}>
                              {isApproved ? '✓ Sent' : isSent ? 'Awaiting approval' : canPublishCustomerAuthorization ? 'Publish' : 'Staff publication required'}
                            </span>
                          )}

                          <ArrowRight className={`w-3 h-3 shrink-0 ${isApproved ? 'text-amber-500' : 'text-gray-300'}`} />

                          {/* Step 3: Customer Approved */}
                          <span className={`shrink-0 px-2 py-1 text-xs font-medium rounded-md ${workflowPillClass(isApproved ? 'success' : isSent ? 'warning' : 'neutral')} ${isSent && !isApproved ? 'animate-pulse' : ''}`}>
                            {isApproved ? '✓ Approved' : isSent ? 'Awaiting…' : 'Approved'}
                          </span>

                          <ArrowRight className={`w-3 h-3 shrink-0 ${hasMechanic ? 'text-amber-500' : 'text-gray-300'}`} />

                          {/* Step 4: Mechanic Assigned */}
                          <span className={`shrink-0 px-2 py-1 text-xs font-medium rounded-md ${workflowPillClass(hasMechanic || assignmentBypassedInDrawer ? 'success' : isApproved ? 'warning' : 'neutral')}`}>
                            {hasMechanic ? `✓ ${mechanicName}` : assignmentBypassedInDrawer ? '✓ In progress' : isApproved ? 'Assign ↓' : 'Technician'}
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
                        {isApproved && !hasMechanic && (orderDetail ?? selectedOrder).status === 'approved' && (
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

                        {/* Mechanic Assignment - shown inline when approved, and collapsed by default after override-start */}
                        {canAssignTechnicianInline && (
                          <div className="pt-3 border-t border-gray-200 space-y-3">
                            <button
                              type="button"
                              onClick={() => setAssignMechanicOpen((open) => !open)}
                              className="flex w-full items-center justify-between gap-2 text-left"
                              aria-expanded={assignMechanicOpen}
                            >
                              <span className="text-xs font-medium text-gray-500 uppercase">Assign technician</span>
                              <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${assignMechanicOpen ? 'rotate-180' : ''}`} />
                            </button>
                            {assignMechanicOpen && (
                              <>
                                {technicianRoster.length > 0 && (
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
                                          disabled={assignMechanicMutation.isPending || overrideTechnicianAssignmentMutation.isPending}
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
                                )}
                                {(orderDetail ?? selectedOrder).status === 'approved' && (
                                  <div className="rounded-lg border border-dashed border-amber-300 bg-amber-50 px-3 py-2.5">
                                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                      <div>
                                        <p className="text-sm font-semibold text-amber-900">Start without assigning a technician</p>
                                        <p className="text-xs text-amber-700">Admin override for work assigned verbally or outside the mechanic portal.</p>
                                      </div>
                                      <button
                                        type="button"
                                        onClick={() => selectedOrder.id && overrideTechnicianAssignmentMutation.mutate(selectedOrder.id)}
                                        disabled={assignMechanicMutation.isPending || overrideTechnicianAssignmentMutation.isPending}
                                        className="inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-amber-600 px-3 text-sm font-bold text-white hover:bg-amber-700 disabled:bg-gray-300"
                                      >
                                        {overrideTechnicianAssignmentMutation.isPending ? 'Starting...' : 'Override & start'}
                                      </button>
                                    </div>
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        )}

                        {/* Reassign Mechanic - shown when mechanic is already assigned and work not yet done */}
                        {hasMechanic && technicianRoster.length > 1 && !['pending_review', 'completed', 'invoiced', 'paid'].includes((orderDetail ?? selectedOrder).status) && (
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
                    navigationLabel={showNavigation ? `${globalNavPosition} / ${globalNavTotal}` : undefined}
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
                    customerNotes={selectedOrder.customer_notes}
                    shopNotes={selectedOrder.shop_notes}
                    notesSaving={saveOrderNotesMutation.isPending}
                    onSaveNotes={async (notes) => { await saveOrderNotesMutation.mutateAsync(notes) }}
                    orderTypeLabel={selectedOrder.is_warranty_repair ? 'Warranty' : selectedOrder.parent_repair_order_id ? 'Comeback' : 'Standard'}
                    quoteNumber={quoteForOrder?.quote_number}
                    quoteIsSent={quoteIsSent}
                    quoteIsApproved={quoteIsApproved}
                    quoteActionLabel={quoteActionLabel}
                    quoteActionPending={quoteActionPending}
                    quoteActionDisabled={quoteActionDisabled}
                    quoteDisabledReason={quoteDisabledReason}
                    onQuoteAction={canPublishCustomerAuthorization ? handlePriceBuilderQuoteAction : undefined}
                    assignedTechnicianName={
                      selectedOrder.assigned_mechanic_id
                        ? mechanicLookup.get(selectedOrder.assigned_mechanic_id) || 'Assigned technician'
                        : null
                    }
                    assignedTechnicianId={selectedOrder.assigned_mechanic_id}
                    technicianOptions={technicianRoster}
                    technicianAssignmentPending={assignMechanicMutation.isPending}
                    onAssignTechnician={(mechanicId) =>
                      selectedOrder.id &&
                      assignMechanicMutation.mutate({
                        orderId: selectedOrder.id,
                        mechanicId,
                        orderStatus: (orderDetail ?? selectedOrder).status,
                      })
                    }
                    technicianOverridePending={overrideTechnicianAssignmentMutation.isPending}
                    onOverrideTechnicianAssignment={() =>
                      selectedOrder.id &&
                      overrideTechnicianAssignmentMutation.mutate(selectedOrder.id)
                    }
                    completionMode={(orderDetail ?? selectedOrder).status === 'pending_review'}
                    completionPending={
                      (orderDetail ?? selectedOrder).is_internal
                        ? completeWorkOrderMutation.isPending
                        : approveCompletionMutation.isPending
                    }
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
                        const completionPayload = {
                          orderId: selectedOrder.id,
                          reviewNotes: reviewNotes || undefined,
                          mileageOut: mileageOut.trim() === '' ? null : Number(mileageOut),
                        }
                        if ((orderDetail ?? selectedOrder).is_internal) {
                          completeWorkOrderMutation.mutate(completionPayload)
                        } else {
                          approveCompletionMutation.mutate(completionPayload)
                        }
                      }
                    }}
                    onStartWorkOrder={() => selectedOrder.id && startWorkOrderMutation.mutate(selectedOrder.id)}
                    startWorkOrderPending={startWorkOrderMutation.isPending}
                    onCompleteWorkOrder={(mileageOutVal) => selectedOrder.id && completeWorkOrderMutation.mutate({ orderId: selectedOrder.id, mileageOut: mileageOutVal })}
                    completeWorkOrderPending={completeWorkOrderMutation.isPending}
                    onAdminCompleteWork={() => selectedOrder.id && adminCompleteWorkMutation.mutate(selectedOrder.id)}
                    adminCompleteWorkPending={adminCompleteWorkMutation.isPending}
                    invoiceCreatePending={createInvoiceMutation.isPending}
                    invoiceDueDateValue={invoiceDueDate}
                    showInvoiceCreateOptions={showInvoiceCreateOptions}
                    onToggleInvoiceCreateOptions={() => setShowInvoiceCreateOptions((prev) => !prev)}
                    onInvoiceDueDateChange={setInvoiceDueDate}
                    invoiceRecipientOptions={invoiceRecipientOptions}
                    invoiceRecipientId={invoiceRecipientId}
                    onInvoiceRecipientChange={setInvoiceRecipientId}
                    onCreateInvoice={(dueDate, billToCustomerId) => selectedOrder.id && createInvoiceMutation.mutate({
                      repairOrderId: selectedOrder.id,
                      dueDate: dueDate || undefined,
                      billToCustomerId,
                    })}
                    invoice={invoiceForOrder ?? null}
                    invoiceActionPending={
                      resendInvoiceMutation.isPending ||
                      voidInvoiceMutation.isPending ||
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
                        return
                      }
                      setSelectedPaymentMethod('')
                      setShowInvoicePaymentOptions(true)
                    }}
                    onVoidInvoice={canVoidInvoices ? () => {
                      setVoidInvoiceReason('')
                      setShowVoidInvoiceConfirm(true)
                    } : undefined}
                    historyEvents={priceBuilderHistoryEvents}
                    onHistoryOpen={() => setWorkspaceHistoryRequested(true)}
                    onClose={closeDetail}
                    onPrev={showNavigation || hasPrev ? goToPrevOrder : undefined}
                    onNext={showNavigation || hasNext ? goToNextOrder : undefined}
                    prevDisabled={!hasPrev}
                    nextDisabled={!hasNext}
                    showDangerActions={showDangerActions}
                    onToggleDangerActions={() => setShowDangerActions((prev) => !prev)}
                    onDeleteOrder={() => setShowDeleteConfirm(true)}
                    deletePending={deleteRepairOrderMutation.isPending}
                    isDeleted={!!(orderDetail ?? selectedOrder).deleted_at}
                    deletedByName={(orderDetail ?? selectedOrder).deleted_by_name}
                    deletedAt={(orderDetail ?? selectedOrder).deleted_at}
                    onRestoreOrder={() => selectedOrder.id && restoreRepairOrderMutation.mutate(selectedOrder.id)}
                    restorePending={restoreRepairOrderMutation.isPending}
                    onReopenWorkOrder={() => selectedOrder.id && reopenWorkOrderMutation.mutate(selectedOrder.id)}
                    reopenPending={reopenWorkOrderMutation.isPending}
                    recommendedServices={['completed', 'invoiced', 'paid'].includes((orderDetail ?? selectedOrder).status) ? [] : recommendedServices}
                    recommendedServicesLoading={recommendedServicesFetching}
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
                    onRecommendedServicesOpenChange={setRecommendedServicesOpen}
                    initialLineWarnings={initialPriceBuildWarningsByOrder[selectedOrder.id] || []}
                    onUpdated={() => {
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
                  const availableServices = serviceOptions.filter(
                    (s) => !detailServices.some((ds) => ds.id === s.id)
                  )

                  const handleAddService = (serviceId: string) => {
                    const svc = serviceOptions.find((s) => s.id === serviceId)
                    if (!svc || !selectedOrder.id) return
                    const newServices = [
                      ...detailServices,
                      { id: svc.id, name: svc.name, base_price: svc.base_price || '0' },
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
                                subLabel: `$${parseFloat(s.base_price || '0').toLocaleString('en-US', { minimumFractionDigits: 2 })}`,
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
                        <Spinner size="sm" className="border-white/40 border-t-white" />
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
                        <Spinner size="sm" className="border-white/40 border-t-white" />
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
                            onClick={() => {
                              setSelectedPaymentMethod('')
                              setShowInvoicePaymentOptions(true)
                            }}
                            className="px-3 py-1.5 bg-white hover:bg-gray-50 border border-yellow-300 text-yellow-900 text-xs font-medium rounded-md transition-colors"
                          >
                            Use Another Method
                          </button>
                          <button
                            type="button"
                            onClick={() => clearPendingZelleMutation.mutate({ invoiceId: invoiceForOrder.id })}
                            disabled={clearPendingZelleMutation.isPending}
                            className="px-3 py-1.5 bg-yellow-100 hover:bg-yellow-200 text-yellow-900 text-xs font-medium rounded-md transition-colors disabled:opacity-60"
                          >
                            {clearPendingZelleMutation.isPending ? 'Clearing...' : 'Dismiss Zelle Claim'}
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
                          {canVoidInvoices && !invoiceForOrder.pending_zelle_confirmation && (
                            <button
                              type="button"
                              onClick={() => {
                                setVoidInvoiceReason('')
                                setShowVoidInvoiceConfirm(true)
                              }}
                              disabled={voidInvoiceMutation.isPending}
                              className="inline-flex items-center gap-2 px-3 py-2 border border-gray-300 bg-white hover:bg-gray-50 text-gray-700 font-medium rounded-lg transition-colors"
                              title="Preserve this invoice as voided and reopen the order for revision"
                            >
                              <RotateCcw className="w-4 h-4" />
                              Void &amp; revise
                            </button>
                          )}
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
                        {invoiceForOrder.pending_zelle_confirmation && (
                          <p className="text-xs leading-5 text-amber-800">
                            Recording any method below clears the customer&apos;s pending Zelle claim and marks the invoice paid with the method you select.
                          </p>
                        )}
                        <div className="grid grid-cols-2 gap-2">
                          {[
                            { value: 'cash', label: 'Cash', icon: '💵' },
                            { value: 'zelle', label: 'Zelle', icon: '📱' },
                            { value: 'check', label: 'Check', icon: '📝' },
                            { value: 'ach', label: 'ACH / Bank Transfer', icon: '🏦' },
                            { value: 'fleet_payment', label: 'Fleet Check / Code', icon: '🚛' },
                          ].map((method) => (
                            <button
                              key={method.value}
                              type="button"
                              onClick={() => {
                                setSelectedPaymentMethod(method.value)
                                if (method.value === 'zelle') {
                                  openZellePaymentModal(
                                    invoiceForOrder.pending_zelle_confirmation ? 'confirm_pending' : 'collect',
                                  )
                                }
                              }}
                              className={`py-2 px-3 rounded-lg border-2 transition-colors flex items-center justify-center gap-2 text-sm font-medium ${
                                method.value === 'fleet_payment' ? 'col-span-2 ' : ''
                              }${
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
                                if (EVIDENCE_PAYMENT_METHODS.includes(selectedPaymentMethod as EvidencePaymentMethod)) {
                                  openManualPaymentConfirmation(selectedPaymentMethod as EvidencePaymentMethod)
                                  return
                                }
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
                              <Spinner size="xs" className="border-white/40 border-t-white" />
                            ) : (
                              selectedPaymentMethod === 'zelle'
                                ? 'Use Zelle Modal'
                                : EVIDENCE_PAYMENT_METHODS.includes(selectedPaymentMethod as EvidencePaymentMethod)
                                  ? 'Continue'
                                  : 'Confirm cash received'
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
                              <Spinner size="xs" className="border-white/40 border-t-white" />
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
                      <div className="space-y-2">
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
                        {invoiceForOrder.payment?.method === 'quickbooks' && canVoidInvoices && (
                          <button
                            type="button"
                            disabled={refundQuickBooksMutation.isPending}
                            onClick={() => {
                              const amount = window.prompt(
                                `Refund amount (leave blank for full refund of $${parseFloat(invoiceForOrder.payment?.amount || '0').toFixed(2)}):`,
                                '',
                              )
                              if (amount === null) return
                              if (amount.trim() && (!Number.isFinite(Number(amount)) || Number(amount) <= 0)) {
                                toast.error('Enter a valid positive refund amount')
                                return
                              }
                              const reason = window.prompt('Reason for the QuickBooks refund:')
                              if (!reason || reason.trim().length < 3) {
                                toast.error('A refund reason of at least 3 characters is required')
                                return
                              }
                              refundQuickBooksMutation.mutate({
                                paymentId: invoiceForOrder.payment!.id,
                                amount: amount.trim() || undefined,
                                reason: reason.trim(),
                              })
                            }}
                            className="w-full rounded-lg border border-red-300 bg-white py-2 font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
                          >
                            {refundQuickBooksMutation.isPending ? 'Submitting refund…' : 'Refund QuickBooks payment'}
                          </button>
                        )}
                      </div>
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
                              <Spinner size="xs" className="border-white/40 border-t-white" />
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

      {/* Sending an authorization is a financial checkpoint. Make the
          consequence explicit before the shop creates a customer baseline. */}
      <Dialog
        open={!!quoteToConfirm}
        onClose={() => closeQuoteConfirmation()}
        initialFocus={keepEditingButtonRef}
        className="fixed inset-0 z-[70]"
      >
        <DialogBackdrop className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {quoteToConfirm && (
              <DialogPanel
                className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl"
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    event.preventDefault()
                    closeQuoteConfirmation()
                  }
                  event.stopPropagation()
                }}
              >
                <div className="mb-4 flex items-start gap-3">
                  <div className="rounded-full bg-amber-100 p-3">
                    <FileText className="h-6 w-6 text-amber-700" />
                  </div>
                  <div>
                    <DialogTitle className="text-lg font-semibold text-gray-900">
                      {quoteToConfirm.authorization_type === 'additional_work'
                        ? 'Send additional work?'
                        : 'Send estimate carefully'}
                    </DialogTitle>
                    <p className="mt-1 text-sm text-gray-500">{quoteToConfirm.quote_number}</p>
                  </div>
                </div>
                {quoteToConfirm.authorization_type === 'additional_work' ? (
                  <div className="mb-6 space-y-3">
                    <p className="text-sm text-gray-700">
                      The customer's original approval remains valid. This request asks them to authorize only the added amount.
                    </p>
                    <AuthorizationSummary quote={quoteToConfirm} theme="light" />
                  </div>
                ) : (
                  <div className="mb-6 space-y-3">
                    <p className="text-sm leading-6 text-gray-700">
                      Once authorized, this estimate becomes the customer's approved baseline. Any later increase in parts, labor, or services will require a separate additional-work authorization.
                    </p>
                    <AuthorizationSummary quote={quoteToConfirm} theme="light" />
                  </div>
                )}
                <div className="flex gap-3">
                  <button
                    ref={keepEditingButtonRef}
                    type="button"
                    onClick={() => closeQuoteConfirmation()}
                    className="flex-1 rounded-lg border border-gray-300 px-4 py-3 font-semibold text-gray-700 hover:bg-gray-50"
                  >
                    Keep editing
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      sendQuoteMutation.mutate(quoteToConfirm.id)
                    }}
                    disabled={sendQuoteMutation.isPending}
                    className="flex-1 rounded-lg bg-emerald-600 px-4 py-3 font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                  >
                    {sendQuoteMutation.isPending
                      ? 'Sending…'
                      : quoteToConfirm.authorization_type === 'additional_work'
                        ? 'Send authorization'
                        : 'Send estimate'}
                  </button>
                </div>
              </DialogPanel>
            )}
          </div>
        </div>
      </Dialog>

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
                    <Spinner size="xs" className="border-white/40 border-t-white" />
                  )}
                  Delete order
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Record payment method modal */}
      {showInvoicePaymentOptions && priceBuilderOwnsShell && invoiceForOrder && (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/40 p-4">
          <div className="relative w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl">
            <button
              type="button"
              aria-label="Close payment modal"
              onClick={() => {
                setShowInvoicePaymentOptions(false)
                setSelectedPaymentMethod('')
              }}
              className="absolute right-4 top-4 inline-flex h-9 w-9 items-center justify-center rounded-full text-gray-400 hover:bg-gray-100 hover:text-gray-700"
            >
              <X className="h-5 w-5" />
            </button>
            <div className="mb-4 pr-10">
              <p className="text-lg font-semibold text-gray-900">Record payment</p>
              <p className="text-sm text-gray-500">
                Invoice {invoiceForOrder.invoice_number} · {formatMoney(manualCollectedAmount(invoiceForOrder, selectedPaymentMethod))}
                {selectedPaymentMethod === 'cash' && <span className="ml-1 text-xs text-gray-400">(no tax on cash)</span>}
              </p>
              {invoiceForOrder.pending_zelle_confirmation && (
                <p className="mt-2 text-xs leading-5 text-amber-800">
                  The customer&apos;s Zelle payment is still unconfirmed. Selecting another method will clear that claim when the payment is recorded.
                </p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              {[
                { value: 'cash', label: 'Cash' },
                { value: 'zelle', label: 'Zelle' },
                { value: 'check', label: 'Check' },
                { value: 'ach', label: 'ACH / Bank Transfer' },
                { value: 'fleet_payment', label: 'Fleet Check / Code' },
              ].map((method) => (
                <button
                  key={method.value}
                  type="button"
                  onClick={() => setSelectedPaymentMethod(method.value)}
                  className={`rounded-xl border px-3 py-3 text-sm font-semibold transition ${
                    method.value === 'fleet_payment' ? 'col-span-2 ' : ''
                  }${
                    selectedPaymentMethod === method.value
                      ? 'border-green-500 bg-green-50 text-green-800'
                      : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  {method.label}
                </button>
              ))}
            </div>
            <div className="mt-5">
              <button
                type="button"
                disabled={!selectedPaymentMethod || recordManualPaymentMutation.isPending}
                onClick={() => {
                  if (!selectedPaymentMethod) return
                  if (selectedPaymentMethod === 'zelle') {
                    setShowInvoicePaymentOptions(false)
                    openZellePaymentModal(
                      invoiceForOrder.pending_zelle_confirmation ? 'confirm_pending' : 'collect',
                    )
                    return
                  }
                  if (EVIDENCE_PAYMENT_METHODS.includes(selectedPaymentMethod as EvidencePaymentMethod)) {
                    openManualPaymentConfirmation(selectedPaymentMethod as EvidencePaymentMethod)
                    return
                  }
                  recordManualPaymentMutation.mutate({
                    invoiceId: invoiceForOrder.id,
                    method: selectedPaymentMethod,
                  })
                }}
                className="inline-flex h-11 w-full items-center justify-center rounded-xl bg-green-600 px-4 text-sm font-semibold text-white hover:bg-green-700 disabled:bg-gray-300"
              >
                {recordManualPaymentMutation.isPending
                  ? 'Recording...'
                  : selectedPaymentMethod === 'zelle'
                    ? 'Continue'
                    : EVIDENCE_PAYMENT_METHODS.includes(selectedPaymentMethod as EvidencePaymentMethod)
                      ? 'Continue'
                      : 'Confirm cash received'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showManualPaymentConfirmation && invoiceForOrder && (() => {
        const method = selectedPaymentMethod as EvidencePaymentMethod
        const isFleetPayment = method === 'fleet_payment'
        const resolvedProvider = manualPaymentProvider === 'Other'
          ? manualPaymentCustomProvider.trim()
          : manualPaymentProvider
        const referenceLabel = method === 'ach'
          ? 'Bank trace or transfer reference'
          : method === 'check'
            ? 'Check number'
            : 'Fleet check or payment code'
        const title = method === 'ach'
          ? 'Confirm bank transfer'
          : method === 'check'
            ? 'Confirm check received'
            : 'Confirm fleet payment'
        const confirmationLabel = method === 'ach'
          ? 'Confirm transfer received'
          : method === 'check'
            ? 'Confirm check received'
            : 'Confirm fleet payment'
        const canConfirm = manualPaymentReference.trim().length > 0
          && (!isFleetPayment || (
            resolvedProvider.length > 0
            && manualPaymentAuthorization.trim().length > 0
          ))
        const manualAmount = manualCollectedAmount(invoiceForOrder, selectedPaymentMethod)

        return (
          <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/40 p-4">
            <div className="relative max-h-[calc(100vh-2rem)] w-full max-w-md overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl">
              <button
                type="button"
                aria-label="Close payment confirmation"
                onClick={() => {
                  resetManualPaymentConfirmation()
                  setSelectedPaymentMethod('')
                }}
                className="absolute right-4 top-4 inline-flex h-9 w-9 items-center justify-center rounded-full text-gray-400 hover:bg-gray-100 hover:text-gray-700"
              >
                <X className="h-5 w-5" />
              </button>

              <div className="mb-4 pr-10">
                <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
                <p className="text-sm text-gray-500">
                  Invoice {invoiceForOrder.invoice_number} · {formatMoney(manualAmount)}
                </p>
              </div>

              <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm leading-5 text-blue-900">
                {method === 'ach' && 'Verify that the funds appear in the shop bank account before confirming this transfer.'}
                {method === 'check' && 'Record the check identifier before marking the invoice paid. This confirms receipt, not bank clearance.'}
                {isFleetPayment && 'Authorize or redeem the fleet instrument with its provider before confirming the invoice as paid.'}
              </div>

              {invoiceForOrder.pending_zelle_confirmation && (
                <p className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900">
                  Confirming this payment will dismiss the customer&apos;s unconfirmed Zelle claim.
                </p>
              )}

              <div className="space-y-4">
                {isFleetPayment && (
                  <label className="block">
                    <span className="mb-1.5 block text-sm font-semibold text-gray-800">Provider</span>
                    <select
                      value={manualPaymentProvider}
                      onChange={(event) => setManualPaymentProvider(event.target.value)}
                      className="h-11 w-full rounded-xl border border-gray-300 bg-white px-3 text-sm text-gray-900 outline-none focus:border-green-500 focus:ring-2 focus:ring-green-100"
                    >
                      <option value="">Select provider</option>
                      {FLEET_PAYMENT_PROVIDERS.map((provider) => (
                        <option key={provider.value} value={provider.value}>{provider.label}</option>
                      ))}
                    </select>
                  </label>
                )}

                {isFleetPayment && manualPaymentProvider === 'Other' && (
                  <label className="block">
                    <span className="mb-1.5 block text-sm font-semibold text-gray-800">Provider name</span>
                    <input
                      type="text"
                      value={manualPaymentCustomProvider}
                      onChange={(event) => setManualPaymentCustomProvider(event.target.value)}
                      maxLength={100}
                      placeholder="Enter fleet payment provider"
                      className="h-11 w-full rounded-xl border border-gray-300 px-3 text-sm text-gray-900 outline-none focus:border-green-500 focus:ring-2 focus:ring-green-100"
                    />
                  </label>
                )}

                <label className="block">
                  <span className="mb-1.5 block text-sm font-semibold text-gray-800">{referenceLabel}</span>
                  <input
                    type="text"
                    value={manualPaymentReference}
                    onChange={(event) => setManualPaymentReference(event.target.value)}
                    maxLength={255}
                    placeholder={method === 'ach' ? 'ACH trace, wire reference, or bank confirmation' : method === 'check' ? 'Enter check number' : 'Enter EFS, Comchek, or T-Chek code'}
                    className="h-11 w-full rounded-xl border border-gray-300 px-3 text-sm text-gray-900 outline-none focus:border-green-500 focus:ring-2 focus:ring-green-100"
                  />
                </label>

                {isFleetPayment && (
                  <label className="block">
                    <span className="mb-1.5 block text-sm font-semibold text-gray-800">Authorization or approval number</span>
                    <input
                      type="text"
                      value={manualPaymentAuthorization}
                      onChange={(event) => setManualPaymentAuthorization(event.target.value)}
                      maxLength={255}
                      placeholder="Enter provider authorization"
                      className="h-11 w-full rounded-xl border border-gray-300 px-3 text-sm text-gray-900 outline-none focus:border-green-500 focus:ring-2 focus:ring-green-100"
                    />
                  </label>
                )}

                <label className="block">
                  <span className="mb-1.5 block text-sm font-semibold text-gray-800">Notes <span className="font-normal text-gray-400">(optional)</span></span>
                  <textarea
                    value={manualPaymentNotes}
                    onChange={(event) => setManualPaymentNotes(event.target.value)}
                    maxLength={1000}
                    rows={2}
                    placeholder="Add bank, payer, or verification details"
                    className="w-full resize-none rounded-xl border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none focus:border-green-500 focus:ring-2 focus:ring-green-100"
                  />
                </label>
              </div>

              <div className="mt-5 grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => {
                    resetManualPaymentConfirmation()
                    setSelectedPaymentMethod('')
                    setShowInvoicePaymentOptions(true)
                  }}
                  className="inline-flex h-11 min-w-0 items-center justify-center whitespace-nowrap rounded-xl border border-gray-300 bg-white px-3 text-sm font-semibold text-gray-700 hover:bg-gray-50"
                >
                  Use another method
                </button>
                <button
                  type="button"
                  disabled={!canConfirm || recordManualPaymentMutation.isPending}
                  onClick={() => {
                    recordManualPaymentMutation.mutate({
                      invoiceId: invoiceForOrder.id,
                      method,
                      notes: manualPaymentNotes.trim(),
                      paymentProvider: isFleetPayment ? resolvedProvider : undefined,
                      referenceNumber: manualPaymentReference.trim(),
                      authorizationNumber: isFleetPayment ? manualPaymentAuthorization.trim() : undefined,
                    })
                  }}
                  className="inline-flex h-11 min-w-0 items-center justify-center whitespace-nowrap rounded-xl bg-green-600 px-2 text-center text-xs font-semibold text-white hover:bg-green-700 disabled:bg-gray-300"
                >
                  {recordManualPaymentMutation.isPending ? 'Recording…' : confirmationLabel}
                </button>
              </div>
            </div>
          </div>
        )
      })()}

      {canVoidInvoices && showVoidInvoiceConfirm && invoiceForOrder && (
        <div className="fixed inset-0 z-[60] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <div 
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setShowVoidInvoiceConfirm(false)}
            />
            <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
              <div className="flex items-center gap-4 mb-4">
                <div className="p-3 rounded-full bg-amber-100">
                  <RotateCcw className="w-6 h-6 text-amber-600" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">Void &amp; revise invoice</h3>
                  <p className="text-sm text-gray-500">#{invoiceForOrder.invoice_number}</p>
                </div>
              </div>

              <p className="text-gray-600 mb-4">
                Preserve this invoice and reopen the repair order for correction.
              </p>

              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-6">
                <p className="text-sm text-amber-800">
                  The original invoice remains in financial history as <strong>voided</strong>. The order returns to manager review so labor, parts, and pricing can be revised before a replacement invoice is issued.
                </p>
              </div>

              <label className="mb-6 block">
                <span className="mb-1.5 block text-sm font-semibold text-gray-800">Reason for revision</span>
                <textarea
                  value={voidInvoiceReason}
                  onChange={(event) => setVoidInvoiceReason(event.target.value)}
                  rows={3}
                  maxLength={1000}
                  placeholder="Describe what needs to be corrected"
                  className="w-full resize-none rounded-xl border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-100"
                />
              </label>
              
              <div className="flex gap-3 justify-end">
                <button
                  type="button"
                  onClick={() => setShowVoidInvoiceConfirm(false)}
                  className="px-4 py-2 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={voidInvoiceMutation.isPending || voidInvoiceReason.trim().length < 3}
                  onClick={() => {
                    voidInvoiceMutation.mutate({
                      invoiceId: invoiceForOrder.id,
                      reason: voidInvoiceReason.trim(),
                    })
                  }}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-amber-300 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
                >
                  {voidInvoiceMutation.isPending && (
                    <Spinner size="xs" className="border-white/40 border-t-white" />
                  )}
                  Void &amp; reopen
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Zelle QR Code Modal */}
      {showZelleQrModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]">
          <div className="relative bg-white rounded-xl shadow-xl max-w-sm w-full mx-4 overflow-hidden">
              <button
                type="button"
                aria-label="Close payment modal"
                onClick={() => {
                  setShowAmountBreakdown(false)
                  setShowZelleQrModal(false)
                  setSelectedPaymentMethod('')
                }}
                className="absolute right-4 top-4 z-10 inline-flex h-9 w-9 items-center justify-center rounded-full text-gray-400 hover:bg-gray-100 hover:text-gray-700"
              >
                <X className="h-5 w-5" />
              </button>
              <div className="p-6">
              <div className="flex items-center gap-3 mb-4 pr-10">
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
                  <button
                    type="button"
                    onClick={() => {
                      if (!invoiceForOrder) return
                      setShowZelleQrModal(false)
                      clearPendingZelleMutation.mutate({ invoiceId: invoiceForOrder.id })
                    }}
                    disabled={clearPendingZelleMutation.isPending}
                    className="pt-1 text-left text-xs font-semibold text-blue-800 underline underline-offset-2 hover:text-blue-950 disabled:opacity-50"
                  >
                    {clearPendingZelleMutation.isPending ? 'Dismissing claim…' : 'Payment not received? Dismiss claim'}
                  </button>
                </div>
              )}

              {/* Amount Display — this is the Zelle registration, so the amount
                  excludes the card processing fee (Zelle has no card cost).
                  Matches the backend zelle_amount = total - service_fee. */}
              {invoiceForOrder && (() => {
                const cardFee = parseMoney(invoiceForOrder.service_fee_amount)
                const zelleTotal = parseMoney(invoiceForOrder.total_amount) - cardFee
                return (
                <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm text-green-800">
                      Amount due: <span className="font-bold">{formatMoney(zelleTotal)}</span>
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
                      {cardFee > 0 && (
                        <div className="flex items-center justify-between text-green-700">
                          <span>Card processing fee waived</span>
                          <span>-{formatMoney(cardFee)}</span>
                        </div>
                      )}
                      <div className="flex items-center justify-between pt-2 border-t border-green-200 font-semibold">
                        <span>Total</span>
                        <span>{formatMoney(zelleTotal)}</span>
                      </div>
                    </div>
                  )}
                </div>
                )
              })()}

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
                      <p className="text-[11px] text-slate-500 uppercase tracking-wide mb-1.5">Company / Truck Unit</p>
                      <p
                        className="text-sm font-semibold text-slate-900 truncate"
                        title={`${paymentCompanyName} \u00b7 Unit: ${paymentTruckUnit}`}
                      >
                        {paymentCompanyNameShort} &middot; Unit: {paymentTruckUnit}
                      </p>
                    </div>
                    {hasPaymentContact && (
                      <div className="bg-white border border-slate-200 rounded-lg px-3 py-2">
                        <p className="text-[11px] text-slate-500 uppercase tracking-wide mb-1.5">Contact</p>
                        <div className="flex items-center justify-between gap-2">
                          {paymentContactPerson && (
                            <p className="text-sm font-semibold text-slate-900 truncate">{paymentContactPerson}</p>
                          )}
                          {paymentContactPhone && (
                            <a
                              href={`tel:${paymentContactPhone}`}
                              className="text-sm font-semibold text-slate-700 whitespace-nowrap hover:text-slate-900"
                            >
                              {paymentContactPhone}
                            </a>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                  <p className="mt-2 text-xs text-slate-500 truncate">Vehicle: {paymentVehicleLabel}</p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setShowAmountBreakdown(false)
                    setShowZelleQrModal(false)
                    setSelectedPaymentMethod('')
                    setShowInvoicePaymentOptions(true)
                  }}
                  className="inline-flex h-11 min-w-0 items-center justify-center whitespace-nowrap rounded-lg border border-amber-300 bg-amber-50 px-3 text-sm font-semibold text-amber-900 transition-colors hover:bg-amber-100"
                >
                  Use another method
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
                  className="inline-flex h-11 min-w-0 items-center justify-center whitespace-nowrap rounded-lg bg-green-600 px-3 text-sm font-semibold text-white transition-colors hover:bg-green-700 disabled:bg-gray-400"
                >
                  {recordManualPaymentMutation.isPending
                    ? 'Recording...'
                    : zelleModalMode === 'confirm_pending'
                      ? 'Confirm received'
                      : 'Payment received'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
