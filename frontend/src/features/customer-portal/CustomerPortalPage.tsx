import { useState, useEffect, useRef, type MouseEvent as ReactMouseEvent, type TouchEvent } from 'react'
import { Spinner } from '@/components/ui'
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { Customer, Vehicle, RepairOrder, RepairOrderDetail, Quote, Invoice, RepairOrderPhoto } from '../../types'
import { format } from 'date-fns'
import ServicesPage from '../services/ServicesPage'
import BookingPage from '../booking/BookingPage'
import AppointmentsPage from '../appointments/AppointmentsPage'
import ProfileSettingsPage from './ProfileSettingsPage'
import CustomerInvoicePage from './CustomerInvoicePage'
import PortalDashboardPage from './PortalDashboardPage'
import PortalVehiclesPage from './PortalVehiclesPage'
import { Camera, CheckCircle, ChevronDown, ChevronUp, ClipboardList, Truck, Wrench, CreditCard, FileText, ArrowLeft, Calendar, Download, Home, User, History, MoreHorizontal, ChevronLeft } from 'lucide-react'
import type { Stripe } from '@stripe/stripe-js'
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js'
import toast from 'react-hot-toast'
import { useWebSocket } from '../../hooks/useWebSocket'
import { useNotificationManager } from '../../hooks/useNotificationManager'
import { usePlatformContact } from '../../hooks/usePlatformContact'
import NotificationBanner from '../../components/NotificationBanner'
import TenantBrandLogo from '../../components/brand/TenantBrandLogo'
import { getStripeForAccount } from '../../lib/stripe'
import { formatUSPhone } from '../../utils/phone'
import useTenantBranding from '@/hooks/useTenantBranding'
import CustomerZellePaymentPanel from './ZellePaymentPanel'
import QuickBooksPaymentPanel from './QuickBooksPaymentPanel'
import { DateBlock, formatMoney, isActiveRepair, Money, PaidBadge, Pill, repairStatusLabel } from './portal-ui'

const STATUS_BADGE_COLORS: Record<string, string> = {
  draft: 'border border-white/10 bg-white/5 text-gray-300',
  quoted: 'border border-violet-400/30 bg-violet-500/10 text-violet-200',
  declined: 'border border-red-400/30 bg-red-500/10 text-red-200',
  approved: 'border border-violet-400/30 bg-violet-500/10 text-violet-200',
  assigned: 'border border-amber-400/30 bg-amber-500/10 text-amber-200',
  acknowledged: 'border border-amber-400/30 bg-amber-500/10 text-amber-200',
  in_progress: 'border border-amber-400/30 bg-amber-500/10 text-amber-200',
  pending_review: 'border border-amber-400/30 bg-amber-500/10 text-amber-200',
  completed: 'border border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  invoiced: 'border border-violet-400/30 bg-violet-500/10 text-violet-200',
  paid: 'border border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  cancelled: 'border border-red-400/30 bg-red-500/10 text-red-200',
}

const CUSTOMER_ACTIVE_REPAIR_STATUSES = [
  'draft',
  'quoted',
  'declined',
  'approved',
  'assigned',
  'acknowledged',
  'in_progress',
  'pending_review',
  'completed',
]

const CUSTOMER_PHOTO_REPAIR_STATUSES = [
  'approved',
  'assigned',
  'acknowledged',
  'in_progress',
  'pending_review',
  'completed',
  'invoiced',
  'paid',
]

const isActiveRepairsSearch = (search: string) =>
  new URLSearchParams(search).get('view') === 'active'

interface ZelleInfoResponse {
  zelle_email: string | null
  zelle_phone: string | null
  zelle_qr_image: string | null
  garage_name: string
  stripe_payments_available: boolean
}

interface QuickBooksPaymentAvailability {
  available: boolean
  token_url: string | null
  message: string | null
}

function CustomerRepairPhotos({ photos }: { photos: RepairOrderPhoto[] }) {
  if (!photos.length) return null

  return (
    <div className="mb-4">
      <div className="mb-2 flex items-center gap-2">
        <Camera className="h-4 w-4 text-amber-300" />
        <h3 className="text-sm font-medium text-gray-300">Repair photos</h3>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {photos.map((photo) => (
          <a
            key={photo.id}
            href={photo.image_url}
            target="_blank"
            rel="noreferrer"
            className="group relative aspect-square overflow-hidden rounded-lg border border-white/10 bg-white/5"
          >
            <img src={photo.image_url} alt={photo.caption || 'Repair photo'} className="h-full w-full object-cover transition group-hover:scale-105" />
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 to-transparent p-2">
              <p className="line-clamp-2 text-[11px] font-semibold text-white">{photo.caption || 'Repair photo'}</p>
            </div>
          </a>
        ))}
      </div>
    </div>
  )
}

const getSelectedServicesTotal = (order: RepairOrder | RepairOrderDetail): number => {
  if (!order.internal_notes) return 0
  try {
    const notes = JSON.parse(order.internal_notes)
    const services = notes?.selected_services || []
    return services.reduce(
      (sum: number, svc: { base_price?: string }) => sum + (parseFloat(svc.base_price || '0') || 0),
      0
    )
  } catch {
    return 0
  }
}

// Customer-facing total is labor/services + parts.
const getOrderTotal = (order: RepairOrder | RepairOrderDetail): number => {
  const backendTotal = parseFloat(order.total_cost || '0') || 0
  if (backendTotal > 0) return backendTotal
  const selectedServicesTotal = getSelectedServicesTotal(order)
  const backendLabor = parseFloat(order.total_labor_cost || '0') || 0
  const backendParts = parseFloat(order.total_parts_cost || '0') || 0
  const labor = selectedServicesTotal > 0 ? selectedServicesTotal : backendLabor
  return labor + backendParts
}

const getOrderSavings = (order: RepairOrder | RepairOrderDetail): number => {
  const partSavings = 'parts_usage' in order
    ? order.parts_usage.reduce((sum, part) => sum + (parseFloat(part.savings || '0') || 0), 0)
    : 0
  const laborDiscount = parseFloat(order.labor_discount_amount || '0') || 0
  const orderDiscount = parseFloat(order.order_discount_amount || '0') || 0
  return partSavings + laborDiscount + orderDiscount
}

const getVehicleLabel = (order: { vehicle_year?: number | null; vehicle_make?: string; vehicle_model?: string; vehicle_unit_number?: string | null }): string => {
  const desc = [order.vehicle_year, order.vehicle_make, order.vehicle_model].filter(Boolean).join(' ')
  const unit = order.vehicle_unit_number ? `Unit #${order.vehicle_unit_number}` : ''
  return [desc, unit].filter(Boolean).join(' · ')
}

const copyText = async (value: string | null | undefined, label: string) => {
  if (!value) {
    toast.error(`${label} is not available`)
    return
  }
  try {
    await navigator.clipboard.writeText(value)
    toast.success(`${label} copied`)
  } catch {
    toast.error(`Unable to copy ${label.toLowerCase()}`)
  }
}

function CustomerDashboard() {
  const { user } = useAuthStore()
  const { data: customer } = useQuery<Customer>({
    queryKey: ['customer', user?.customer_id],
    queryFn: async () => {
      if (!user?.customer_id) return null
      const response = await api.get(`/customers/${user.customer_id}`)
      return response.data
    },
    enabled: !!user?.customer_id,
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
  })

  const { data: repairOrders } = useQuery<RepairOrder[]>({
    queryKey: ['repair-orders'],
    queryFn: async () => {
      const pageSize = 100
      let skip = 0
      const all: RepairOrder[] = []
      while (true) {
        const response = await api.get('/repair-orders', { params: { paginated: true, skip, limit: pageSize } })
        const data = response.data
        all.push(...data.items)
        if (!data.has_more || data.items.length === 0) break
        skip = data.skip + data.limit
      }
      return all
    },
  })

  const activeRepairs = repairOrders?.filter(o =>
    CUSTOMER_ACTIVE_REPAIR_STATUSES.includes(o.status) ||
    (o.quote_sent === true && !o.quote_approved)
  ).length || 0

  const completedRepairs = repairOrders?.filter(o => 
    ['paid'].includes(o.status)
  ).length || 0

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">
          Welcome back, {customer?.first_name || user?.email}
        </h1>
        <p className="text-gray-400 mt-1">Manage your vehicles and track repair status</p>
      </div>

      {/* KPI Cards - compact summary */}
      {/* Mobile: Single compact card */}
      <div className="sm:hidden bg-white/5 rounded-xl p-3.5 border border-white/10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-cyan-500/20 flex items-center justify-center">
              <Truck className="w-5 h-5 text-cyan-200" />
            </div>
            <div>
              <div className="text-xl font-bold text-white leading-none">{vehicles?.length || 0}</div>
              <div className="text-xs text-gray-400">Vehicles</div>
            </div>
          </div>
          <div className="flex gap-3">
            <div className="text-center">
              <div className="text-base font-bold text-amber-400 leading-none">{activeRepairs}</div>
              <div className="text-[10px] text-gray-500">Active</div>
            </div>
            <div className="text-center">
              <div className="text-base font-bold text-green-400 leading-none">{completedRepairs}</div>
              <div className="text-[10px] text-gray-500">Done</div>
            </div>
            <div className="text-center">
              <div className="text-base font-bold text-purple-400 leading-none">{repairOrders?.length || 0}</div>
              <div className="text-[10px] text-gray-500">Total</div>
            </div>
          </div>
        </div>
      </div>

      {/* Desktop: Inline KPI stat bar */}
      <div className="hidden sm:block">
        <div className="bg-white/5 rounded-xl border border-white/10 overflow-x-auto">
          <div className="flex min-w-[680px] divide-x divide-white/10">
            <div className="flex-1 px-4 py-3 bg-cyan-500/5">
              <div className="flex items-center gap-2 text-cyan-200">
                <Truck className="w-4 h-4" />
                <span className="text-xs text-gray-300">My Vehicles</span>
              </div>
              <div className="text-2xl font-bold text-white leading-none mt-2">{vehicles?.length || 0}</div>
            </div>
            <div className="flex-1 px-4 py-3 bg-amber-500/5">
              <div className="flex items-center gap-2 text-amber-200">
                <Wrench className="w-4 h-4" />
                <span className="text-xs text-gray-300">Active Repairs</span>
              </div>
              <div className="text-2xl font-bold text-white leading-none mt-2">{activeRepairs}</div>
            </div>
            <div className="flex-1 px-4 py-3 bg-green-500/5">
              <div className="flex items-center gap-2 text-green-200">
                <CheckCircle className="w-4 h-4" />
                <span className="text-xs text-gray-300">Completed</span>
              </div>
              <div className="text-2xl font-bold text-white leading-none mt-2">{completedRepairs}</div>
            </div>
            <div className="flex-1 px-4 py-3 bg-purple-500/5">
              <div className="flex items-center gap-2 text-purple-200">
                <ClipboardList className="w-4 h-4" />
                <span className="text-xs text-gray-300">Total Orders</span>
              </div>
              <div className="text-2xl font-bold text-white leading-none mt-2">{repairOrders?.length || 0}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Action Required - quoted+sent (needs approval) or invoiced (needs payment) */}
      {(() => {
        const actionRequired = repairOrders?.filter(o =>
          o.status === 'invoiced' || (o.quote_sent === true && !o.quote_approved)
        ) || []
        
        if (actionRequired.length === 0) return null
        
        return (
          <div className="bg-amber-500/10 rounded-xl p-4 sm:p-6 border border-amber-500/30">
            <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
              Action Required
            </h2>
            <div className="space-y-2">
              {actionRequired.map((order) => (
                <Link
                  key={order.id}
                  to="/portal/repairs"
                  state={{ selectedOrderId: order.id }}
                  className="block bg-white/10 rounded-lg p-3 border border-white/10 hover:bg-white/20 transition-colors"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-white text-sm">{order.order_number}</p>
                      {getVehicleLabel(order) && (
                        <p className="text-amber-300 text-xs font-medium mt-0.5">{getVehicleLabel(order)}</p>
                      )}
                      <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-gray-300">
                        <span className="inline-flex items-center gap-1">
                          <Calendar className="h-3.5 w-3.5 text-amber-300" />
                          {order.status === 'invoiced' ? 'Invoice sent' : 'Estimate sent'} {format(
                            new Date(order.status === 'invoiced' ? (order.invoice_created_at || order.updated_at) : (order.quote_sent_at || order.updated_at)),
                            'MMM d, yyyy h:mm a',
                          )}
                        </span>
                        {order.status === 'invoiced' && order.invoice_due_date && (
                          <span className="text-amber-200">Due {format(new Date(order.invoice_due_date), 'MMM d, yyyy')}</span>
                        )}
                      </p>
                      {order.description && (
                        <p className="text-gray-300 text-xs truncate mt-0.5">{order.description}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`px-2 py-1 rounded-lg text-xs font-medium ${
                        order.status === 'invoiced' 
                          ? 'bg-green-500 text-white' 
                          : 'bg-amber-500 text-white'
                      }`}>
                        {order.status === 'invoiced' ? 'Pay Now' : 'Review Estimate'}
                      </span>
                      {order.status === 'invoiced' ? (
                        <div className="text-sm font-bold text-white">
                          ${getOrderTotal(order).toFixed(2)}
                        </div>
                      ) : (
                        <span className="text-xs text-gray-300">Open to review amount</span>
                      )}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )
      })()}

      {/* Two Column Layout */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* My Vehicles */}
        <div className="bg-white/5 rounded-xl p-4 sm:p-6 border border-white/10 overflow-hidden">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">My Vehicles</h2>
            <Link to="/portal/vehicles" className="text-sm hover:opacity-80" style={{ color: 'var(--accent-500)' }}>
              View All
            </Link>
          </div>
          {vehicles && vehicles.length > 0 ? (
            <div className="space-y-2 sm:space-y-3">
              {vehicles.slice(0, 4).map((vehicle) => (
                <div
                  key={vehicle.id}
                  className="bg-white/5 rounded-lg p-2.5 sm:p-3 border border-white/5 hover:bg-white/10 active:bg-white/15 transition-colors"
                >
                  <div className="flex items-center gap-2 sm:gap-3">
                    <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-lg bg-cyan-500/20 flex items-center justify-center text-base sm:text-lg shrink-0">
                      <Truck className="w-5 h-5 sm:w-6 sm:h-6 text-cyan-200" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-white text-sm sm:text-base truncate">
                        {vehicle.year} {vehicle.make} {vehicle.model}
                      </p>
                      <p className="text-xs sm:text-sm text-gray-400 truncate">
                        {vehicle.license_plate ? `Plate: ${vehicle.license_plate}` : 'No plate'}
                        {vehicle.mileage && ` • ${vehicle.mileage.toLocaleString()} mi`}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <div className="flex justify-center mb-2">
                <Truck className="w-8 h-8 text-cyan-300" />
              </div>
              <p className="text-gray-400">No vehicles registered</p>
            </div>
          )}
        </div>

        {/* Active Repairs - approved through completion, plus assigned technician workflow */}
        <div className="bg-white/5 rounded-xl p-4 sm:p-6 border border-white/10 overflow-hidden">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Active Repairs</h2>
          </div>
          {(() => {
            const activeOrders = repairOrders?.filter(o => 
              CUSTOMER_ACTIVE_REPAIR_STATUSES.includes(o.status)
            ) || []
            
            return activeOrders.length > 0 ? (
              <div className="space-y-2 sm:space-y-3">
                {activeOrders.slice(0, 4).map((order) => (
                  <Link
                    key={order.id}
                    to="/portal/repairs"
                    state={{ selectedOrderId: order.id }}
                    className="block bg-white/5 rounded-lg p-2.5 sm:p-3 border border-white/5 hover:bg-white/10 active:bg-white/15 transition-colors overflow-hidden"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-white text-xs sm:text-sm">{order.order_number}</p>
                        {order.description && (
                          <p className="text-gray-400 text-[11px] sm:text-xs truncate mt-0.5">{order.description}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className={`px-1.5 sm:px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium whitespace-nowrap ${STATUS_BADGE_COLORS[order.status] || 'bg-gray-100 text-gray-700'}`}>
                          {order.status === 'draft' ? 'checked in' : order.status.replace('_', ' ')}
                        </span>
                        <span className="text-[10px] font-medium text-gray-400">No price published</span>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <div className="flex justify-center mb-2">
                  <Wrench className="w-8 h-8 text-amber-300" />
                </div>
                <p className="text-gray-400">No active repairs</p>
              </div>
            )
          })()}
        </div>
      </div>

      {/* Recent Activity - last few paid/declined */}
      {(() => {
        const recentCompleted = repairOrders?.filter(o => 
          ['paid', 'declined'].includes(o.status)
        ).slice(0, 3) || []
        
        if (recentCompleted.length === 0) return null
        
        return (
          <div className="bg-white/5 rounded-xl p-4 sm:p-6 border border-white/10 overflow-hidden">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Recent Activity</h2>
              <Link to="/portal/repairs" className="text-sm hover:opacity-80" style={{ color: 'var(--accent-500)' }}>
                View History
              </Link>
            </div>
            <div className="space-y-2 sm:space-y-3">
              {recentCompleted.map((order) => (
                <Link
                  key={order.id}
                  to="/portal/repairs"
                  state={{ selectedOrderId: order.id }}
                  className="block bg-white/5 rounded-lg p-2.5 sm:p-3 border border-white/5 hover:bg-white/10 active:bg-white/15 transition-colors overflow-hidden"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-white text-xs sm:text-sm">{order.order_number}</p>
                      {order.description && (
                        <p className="text-gray-400 text-[11px] sm:text-xs truncate mt-0.5">{order.description}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`px-1.5 sm:px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium whitespace-nowrap ${STATUS_BADGE_COLORS[order.status] || 'bg-gray-100 text-gray-700'}`}>
                          {order.status === 'draft' ? 'checked in' : order.status.replace('_', ' ')}
                      </span>
                      {['invoiced', 'paid'].includes(order.status) && (
                        <div className="text-xs sm:text-sm font-medium text-white">
                          ${getOrderTotal(order).toFixed(2)}
                        </div>
                      )}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )
      })()}
    </div>
  )
}

function CustomerVehicles() {
  const { data: vehicles, isLoading } = useQuery<Vehicle[]>({
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
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="xl" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">My Vehicles</h1>
        <p className="text-gray-400 mt-1">All vehicles registered to your account</p>
      </div>

      <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
        {vehicles && vehicles.length > 0 ? (
          <div className="divide-y divide-white/5">
            {vehicles.map((vehicle) => (
              <div key={vehicle.id} className="p-3 sm:p-6 hover:bg-white/5 active:bg-white/10 transition-colors">
                <div className="flex items-start gap-3 sm:gap-4">
                  <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-lg bg-cyan-500/20 flex items-center justify-center text-xl sm:text-2xl shrink-0">
                    <Truck className="w-6 h-6 sm:w-7 sm:h-7 text-cyan-200" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-white text-base sm:text-lg">
                      {vehicle.year} {vehicle.make} {vehicle.model}
                    </h3>
                    <div className="flex flex-wrap gap-x-4 sm:gap-x-6 gap-y-1 mt-1.5 sm:mt-2 text-xs sm:text-sm text-gray-400">
                      {vehicle.vin && <span className="truncate max-w-[150px] sm:max-w-none">VIN: {vehicle.vin}</span>}
                      {vehicle.license_plate && <span>Plate: {vehicle.license_plate}</span>}
                      {vehicle.mileage && <span>{vehicle.mileage.toLocaleString()} mi</span>}
                      {vehicle.color && <span>{vehicle.color}</span>}
                    </div>
                    {vehicle.notes && (
                      <p className="text-gray-500 text-xs sm:text-sm mt-2 line-clamp-2">{vehicle.notes}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="flex justify-center mb-3">
              <Truck className="w-10 h-10 text-cyan-300" />
            </div>
            <p className="text-gray-400">No vehicles registered yet</p>
          </div>
        )}
      </div>
    </div>
  )
}

// Retained temporarily for parity while the new route-level screens settle.
void CustomerDashboard
void CustomerVehicles

// Payment form component
function PaymentForm({ 
  invoiceId, 
  onSuccess 
}: { 
  invoiceId: string
  onSuccess: () => void 
}) {
  const { supportEmail, supportPhoneDisplay, mailtoHref, telHref } = usePlatformContact()
  const stripe = useStripe()
  const elements = useElements()
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!stripe || !elements) return

    setIsProcessing(true)
    setError(null)

    const { error: submitError, paymentIntent } = await stripe.confirmPayment({
      elements,
      confirmParams: {
        return_url: window.location.href,
      },
      redirect: 'if_required',
    })

    if (submitError) {
      setError(submitError.message || 'Payment failed')
      setIsProcessing(false)
      return
    }

    if (paymentIntent && paymentIntent.status === 'succeeded') {
      // Confirm payment on backend
      try {
        const response = await api.post('/payments/confirm-payment', {
          invoice_id: invoiceId,
          payment_intent_id: paymentIntent.id,
        })
        const paymentNote = response.data?.payment_note
        toast.success(paymentNote || 'Payment successful!')
        onSuccess()
      } catch {
        setError('Payment confirmed but failed to update records. Please contact support.')
      }
    }
    setIsProcessing(false)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <PaymentElement />
      {error && (
        <div className="text-red-400 text-sm bg-red-500/10 p-3 rounded-lg space-y-1">
          <p>{error}</p>
          {(supportPhoneDisplay || supportEmail) && (
            <p className="text-red-300/90 text-xs">
              Support:{' '}
              {supportPhoneDisplay && telHref && (
                <>
                  <a className="underline font-medium hover:text-red-200" href={telHref}>
                    {supportPhoneDisplay}
                  </a>
                </>
              )}
              {supportPhoneDisplay && supportEmail && ' • '}
              {supportEmail && mailtoHref && (
                <a className="underline font-medium hover:text-red-200" href={mailtoHref}>
                  {supportEmail}
                </a>
              )}
            </p>
          )}
        </div>
      )}
      <button
        type="submit"
        disabled={!stripe || isProcessing}
        className="w-full rounded-xl bg-violet-600 py-3 font-semibold text-white transition-colors hover:bg-violet-500 disabled:bg-gray-600"
      >
        {isProcessing ? (
          <>
            <Spinner size="sm" className="border-white/40 border-t-white" />
            Processing...
          </>
        ) : (
          <>
            <CreditCard className="w-5 h-5" />
            Pay Now
          </>
        )}
      </button>
    </form>
  )
}

function CustomerRepairs() {
  const { user } = useAuthStore()
  const queryClient = useQueryClient()
  const location = useLocation()
  const [selectedOrder, setSelectedOrder] = useState<RepairOrder | null>(null)
  const [showPayment, setShowPayment] = useState(false)
  const [stripeOptions, setStripeOptions] = useState<{ clientSecret: string; appearance: object } | null>(null)
  const [stripeInstance, setStripeInstance] = useState<Stripe | null>(null)
  const [declineNotes, setDeclineNotes] = useState('')
  const [showDeclineForm, setShowDeclineForm] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [zelleSenderEmail, setZelleSenderEmail] = useState('')
  const [zelleSenderPhone, setZelleSenderPhone] = useState('')
  const [zelleNotes, setZelleNotes] = useState('')
  const [isZelleSenderEditing, setIsZelleSenderEditing] = useState(false)
  const [showZelleDetails, setShowZelleDetails] = useState(false)
  const [showQuickBooksPayment, setShowQuickBooksPayment] = useState(false)
  const isActiveRepairsView = isActiveRepairsSearch(location.search)
  
  const { data: orders, isLoading } = useQuery<RepairOrder[]>({
    queryKey: ['repair-orders'],
    queryFn: async () => {
      const pageSize = 100
      let skip = 0
      const all: RepairOrder[] = []
      while (true) {
        const response = await api.get('/repair-orders', { params: { paginated: true, skip, limit: pageSize } })
        const data = response.data
        all.push(...data.items)
        if (!data.has_more || data.items.length === 0) break
        skip = data.skip + data.limit
      }
      return all
    },
  })

  const { data: allInvoices = [] } = useQuery<Invoice[]>({
    queryKey: ['customer-history-invoices'],
    queryFn: async () => (await api.get('/invoices')).data,
  })

  const { data: selectedOrderDetail } = useQuery<RepairOrderDetail>({
    queryKey: ['repair-order-detail-customer', selectedOrder?.id],
    queryFn: async () => {
      const response = await api.get(`/repair-orders/${selectedOrder!.id}/detail`)
      return response.data
    },
    enabled: !!selectedOrder?.id,
  })

  const { data: repairPhotos = [] } = useQuery<RepairOrderPhoto[]>({
    queryKey: ['repair-order-photos-customer', selectedOrder?.id],
    queryFn: async () => {
      const response = await api.get(`/repair-orders/${selectedOrder!.id}/photos`)
      return response.data
    },
    enabled: !!selectedOrder?.id && CUSTOMER_PHOTO_REPAIR_STATUSES.includes(selectedOrder.status),
  })

  // Handle navigation state to auto-select an order
  useEffect(() => {
    const state = location.state as { selectedOrderId?: string } | null
    if (state?.selectedOrderId && orders) {
      const order = orders.find(o => o.id === state.selectedOrderId)
      if (order) {
        setSelectedOrder(order)
        // Clear the state to prevent re-selection on refresh
        window.history.replaceState({}, document.title)
      }
    }
  }, [location.state, orders])

  // Fetch invoice for selected order if it's invoiced
  const { data: invoice } = useQuery<Invoice | null>({
    queryKey: ['invoice', selectedOrder?.id],
    queryFn: async () => {
      const response = await api.get('/invoices', {
        params: { repair_order_id: selectedOrder?.id }
      })
      const invoices = response.data as Invoice[]
      return invoices[0] || null
    },
    enabled: !!selectedOrder && ['invoiced', 'paid'].includes(selectedOrder.status),
  })

  const { data: zelleInfo } = useQuery<ZelleInfoResponse>({
    queryKey: ['customer-zelle-info', invoice?.id],
    queryFn: async () => {
      const response = await api.get(`/payments/zelle-info/${invoice!.id}`)
      return response.data as ZelleInfoResponse
    },
    enabled: !!invoice && selectedOrder?.status === 'invoiced',
  })

  const { data: quickBooksPayment, isLoading: isQuickBooksPaymentLoading } = useQuery<QuickBooksPaymentAvailability>({
    queryKey: ['quickbooks-payment-availability', invoice?.id],
    queryFn: async () => (await api.get(`/quickbooks/payments/availability/${invoice!.id}`)).data,
    enabled: !!invoice && selectedOrder?.status === 'invoiced',
  })

  const zelleAmount = invoice
    ? (parseFloat(invoice.total_amount) - parseFloat(invoice.service_fee_amount || '0')).toFixed(2)
    : '0.00'
  const zelleMemo = invoice ? `Invoice #${invoice.invoice_number}` : ''

  useEffect(() => {
    if (!user) return
    setZelleSenderEmail((current) => current || user.email || '')
    setZelleSenderPhone((current) => current || (user.phone ? formatUSPhone(user.phone) : ''))
  }, [user])

  useEffect(() => {
    if (!zelleMemo) return
    setZelleNotes(zelleMemo)
    setIsZelleSenderEditing(false)
  }, [invoice?.id, zelleMemo])

  useEffect(() => {
    setShowPayment(false)
    setStripeOptions(null)
    setStripeInstance(null)
    setShowQuickBooksPayment(false)
  }, [invoice?.id])

  const handleDownloadPdf = async () => {
    if (!invoice) return
    try {
      const response = await api.get(`/invoices/${invoice.id}/pdf`, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `Invoice-${invoice.invoice_number}.pdf`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch {
      toast.error('Failed to download PDF')
    }
  }

  // Fetch quote for selected order if it's quoted
  const { data: selectedQuote } = useQuery<Quote | null>({
    queryKey: ['quote', selectedOrder?.id],
    queryFn: async () => {
      const response = await api.get(`/quotes?repair_order_id=${selectedOrder?.id}`)
      return response.data as Quote | null
    },
    enabled: !!selectedOrder && selectedOrder.quote_sent === true,
  })

  const approveQuoteMutation = useMutation({
    mutationFn: async (quoteId: string) => {
      const response = await api.post(`/quotes/${quoteId}/approve`)
      return response.data as Quote
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['quote'] })
      toast.success('Estimate authorized. The shop has been notified.')
      setSelectedOrder(null)
    },
  })

  const declineQuoteMutation = useMutation({
    mutationFn: async ({ quoteId, notes }: { quoteId: string; notes?: string }) => {
      const response = await api.post(`/quotes/${quoteId}/decline`, { notes })
      return response.data as Quote
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['quote'] })
      toast.success('Changes requested. The shop will contact you about this estimate.')
      setSelectedOrder(null)
    },
  })

  const handlePayClick = async () => {
    if (!invoice) return
    try {
      // First create the payment intent to get the connected account ID
      const { data } = await api.post('/payments/create-payment-intent', {
        invoice_id: invoice.id,
      })
      
      // Load Stripe with the connected account if using Stripe Connect
      const stripe = await getStripeForAccount(data.stripe_account_id)
      setStripeInstance(stripe)
      
      setStripeOptions({ 
        clientSecret: data.client_secret,
        appearance: {
          theme: 'night',
          variables: {
            colorPrimary: '#22c55e',
            colorBackground: '#1e293b',
            colorText: '#f1f5f9',
            colorTextSecondary: '#94a3b8',
            colorDanger: '#ef4444',
            fontFamily: 'system-ui, sans-serif',
            borderRadius: '8px',
          },
          rules: {
            '.Input': {
              backgroundColor: '#334155',
              border: '1px solid #475569',
              color: '#f1f5f9',
            },
            '.Input:focus': {
              border: '1px solid #22c55e',
              boxShadow: '0 0 0 1px #22c55e',
            },
            '.Label': {
              color: '#e2e8f0',
            },
          },
        },
      })
      setShowPayment(true)
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail || 'Failed to initialize payment')
    }
  }

  const handlePaymentSuccess = () => {
    setShowPayment(false)
    setStripeOptions(null)
    queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
    queryClient.invalidateQueries({ queryKey: ['invoice'] })
    // Update local state
    if (selectedOrder) {
      setSelectedOrder({ ...selectedOrder, status: 'paid' })
    }
  }

  const submitZelleMutation = useMutation({
    mutationFn: async () => {
      if (!invoice) throw new Error('Invoice not found')
      const response = await api.post('/payments/submit-zelle', {
        invoice_id: invoice.id,
        sender_email: zelleSenderEmail.trim() || null,
        sender_phone: zelleSenderPhone.trim() || null,
        notes: zelleNotes.trim() || null,
      })
      return response.data as { status: string; message: string }
    },
    onSuccess: (data) => {
      toast.success(data.message || 'Zelle payment submitted')
      queryClient.invalidateQueries({ queryKey: ['invoice', selectedOrder?.id] })
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      setZelleNotes('')
      setIsZelleSenderEditing(false)
    },
    onError: (err: unknown) => {
      const error = err as { response?: { data?: { detail?: string } } }
      toast.error(error.response?.data?.detail || 'Unable to submit Zelle payment')
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="xl" />
      </div>
    )
  }

  // Detail view for selected order
  if (selectedOrder) {
    const displayOrder = selectedOrderDetail ?? selectedOrder
    const services = (() => {
      try {
        const notes = JSON.parse(displayOrder.internal_notes || '{}')
        return notes?.selected_services || []
      } catch {
        return []
      }
    })()
    const partsUsage = selectedOrderDetail?.parts_usage || []
    const laborFromServices = getSelectedServicesTotal(displayOrder)
    const backendLaborTotal = parseFloat(displayOrder.total_labor_cost || '0') || 0
    const laborTotal = laborFromServices > 0 ? laborFromServices : backendLaborTotal
    const partsTotal = parseFloat(displayOrder.total_parts_cost || '0') || 0
    const finalTotal = getOrderTotal(displayOrder)
    const customerSavings = getOrderSavings(displayOrder)
    const preSavingsTotal = finalTotal + customerSavings
    const financialsPublished = ['invoiced', 'paid'].includes(displayOrder.status)

    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
          <button
            onClick={() => {
              setSelectedOrder(null)
              setShowPayment(false)
              setStripeOptions(null)
            }}
            className="inline-flex h-9 items-center gap-1 rounded-full border border-[#272d3d] bg-[#191d2a] px-3.5 text-[13px] font-bold text-[#c9cdd8] hover:border-[#343b52]"
          >
            <ArrowLeft className="h-4 w-4" />
            {isActiveRepairsView ? 'Repairs' : 'History'}
          </button>
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-white">{selectedOrder.order_number}</h1>
            {getVehicleLabel(selectedOrder) && (
              <p className="text-amber-300 text-sm font-medium mt-0.5">{getVehicleLabel(selectedOrder)}</p>
            )}
            <p className="text-gray-400 text-sm">
              {format(new Date(selectedOrder.created_at), 'MMMM d, yyyy')}
            </p>
          </div>
          <span className={`sm:ml-auto px-3 py-1 rounded-full text-sm font-medium whitespace-nowrap ${STATUS_BADGE_COLORS[selectedOrder.status] || 'bg-gray-100 text-gray-700'}`}>
            {selectedOrder.status.replace('_', ' ')}
          </span>
        </div>

        {/* Order Details */}
        <div className="bg-white/5 rounded-xl border border-white/10 p-4 sm:p-6">
          {/* Customer Concerns - extract from description (after the — separator) */}
          {(() => {
            const desc = selectedOrder.description || ''
            // Description format: "Service A • Service B — Customer concerns text"
            const separatorIdx = desc.indexOf(' — ')
            const customerConcerns = separatorIdx !== -1 ? desc.slice(separatorIdx + 3).trim() : (services.length === 0 ? desc : '')
            
            return customerConcerns ? (
              <div className="mb-4">
                <h3 className="text-sm font-medium text-gray-400 mb-1">Customer Concerns</h3>
                <p className="text-white">{customerConcerns}</p>
              </div>
            ) : null
          })()}

          {services.length > 0 && (
            <div className="mb-4">
              <h3 className="text-sm font-medium text-gray-400 mb-2">Services / Labor</h3>
              <div className="space-y-2">
                {services.map((svc: { id: string; name: string; base_price?: string }, idx: number) => (
                  <div key={svc.id || idx} className="flex justify-between items-center bg-white/5 p-3 rounded-lg">
                    <span className="text-white">{svc.name}</span>
                    {svc.base_price && (
                      <span className="text-gray-400">${parseFloat(svc.base_price).toFixed(2)}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {partsUsage.length > 0 && (
            <div className="mb-4">
              <h3 className="text-sm font-medium text-gray-400 mb-2">Parts</h3>
              <div className="space-y-2">
                {partsUsage.map((part) => (
                  <div key={part.id} className="flex justify-between items-center bg-white/5 p-3 rounded-lg">
                    <div>
                      <div className="text-white">{part.inventory_name}</div>
                      <div className="text-xs text-gray-500">
                        {part.inventory_sku} · Qty {part.quantity}
                      </div>
                    </div>
                    <span className="text-gray-300">${parseFloat(part.total_price).toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Shop Comments */}
          {selectedOrder.customer_notes && (
            <div className="mb-4">
              <h3 className="text-sm font-medium text-gray-400 mb-1">Shop Comments</h3>
              <p className="text-white">{selectedOrder.customer_notes}</p>
            </div>
          )}

          <CustomerRepairPhotos photos={repairPhotos} />

          {financialsPublished ? (
          <div className="border-t border-white/10 pt-4 mt-4">
            <div className="space-y-2 mb-3">
              <div className="flex justify-between items-center text-sm">
                <span className="text-gray-400">Labor / Services</span>
                <span className="text-white">${laborTotal.toFixed(2)}</span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-gray-400">Parts</span>
                <span className="text-white">${partsTotal.toFixed(2)}</span>
              </div>
            </div>
            <div className="space-y-2 border-t border-white/10 pt-3">
              {customerSavings > 0 && (
                <>
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-gray-400">Total before savings</span>
                    <span className="text-gray-200">${preSavingsTotal.toFixed(2)}</span>
                  </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-emerald-300">Best savings</span>
                  <span className="font-semibold text-emerald-300">-${customerSavings.toFixed(2)}</span>
                </div>
                </>
              )}
              <div className="flex justify-between items-center text-lg border-t border-white/10 pt-3">
                <span className="font-medium text-white">
                  {invoice ? 'Subtotal' : 'Final total'}
                </span>
                <span className="font-bold text-white">${finalTotal.toFixed(2)}</span>
              </div>
            </div>
            {invoice && (
              <p className="text-xs text-gray-500 mt-1">Taxes & fees included in invoice below</p>
            )}
          </div>
          ) : (
            <div className="mt-4 rounded-lg border border-blue-400/20 bg-blue-400/10 p-3 text-sm text-blue-100">
              Work is in progress. Final itemized charges will appear here when the repair is finalized.
            </div>
          )}
        </div>

        {/* Quote Approval Section */}
        {selectedOrder.quote_sent === true && selectedQuote && !selectedQuote.is_approved && (
          <div className="bg-amber-500/10 rounded-xl border border-amber-500/30 p-4 sm:p-6">
            <div className="flex items-center gap-3 mb-4">
              <FileText className="w-6 h-6 text-amber-400" />
              <div>
                <h3 className="font-semibold text-white">Estimate #{selectedQuote.quote_number}</h3>
                <p className="text-sm text-gray-400">Authorization requested for this estimate</p>
              </div>
            </div>

            <div className="bg-white/5 rounded-lg p-4 mb-4">
              <div className="flex justify-between items-center">
                <span className="text-gray-400">Estimated Total</span>
                <span className="font-bold text-xl text-white">${parseFloat(selectedQuote.total_amount).toFixed(2)}</span>
              </div>
              {selectedQuote.expires_at && (
                <p className="text-xs text-gray-500 mt-2">
                  Valid until {format(new Date(selectedQuote.expires_at), 'MMMM d, yyyy')}
                </p>
              )}
            </div>

            {!showDeclineForm ? (
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => approveQuoteMutation.mutate(selectedQuote.id)}
                  disabled={approveQuoteMutation.isPending}
                  className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-3 font-medium text-white transition-colors hover:bg-violet-500 disabled:bg-gray-500"
                >
                  <CheckCircle className="w-5 h-5" />
                  {approveQuoteMutation.isPending ? 'Authorizing...' : 'Authorize Estimate'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowDeclineForm(true)}
                  className="flex-1 px-4 py-3 bg-white/10 hover:bg-white/20 border border-white/20 text-white font-medium rounded-lg transition-colors"
                >
                  Request Changes
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-gray-400">Let us know what changes you'd like:</p>
                <textarea
                  value={declineNotes}
                  onChange={(e) => setDeclineNotes(e.target.value)}
                  placeholder="e.g., Can we skip the brake fluid flush? Or is there a cheaper option for..."
                  className="w-full resize-none rounded-xl border border-[#30384b] bg-[#0d1118] px-3 py-2 text-base text-white placeholder-gray-500 focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
                  rows={3}
                />
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      declineQuoteMutation.mutate({ quoteId: selectedQuote.id, notes: declineNotes })
                      setDeclineNotes('')
                      setShowDeclineForm(false)
                    }}
                    disabled={declineQuoteMutation.isPending}
                    className="flex-1 rounded-xl bg-violet-600 px-4 py-2 font-medium text-white transition-colors hover:bg-violet-500 disabled:bg-gray-500"
                  >
                    {declineQuoteMutation.isPending ? 'Sending...' : 'Send Request'}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowDeclineForm(false)
                      setDeclineNotes('')
                    }}
                    className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white font-medium rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Invoice & Payment Section */}
        {selectedOrder.status === 'invoiced' && invoice && (
          <div className="bg-purple-500/10 rounded-xl border border-purple-500/30 p-4 sm:p-6">
            <div className="flex items-center gap-3 mb-4">
              <FileText className="w-6 h-6 text-purple-400" />
              <div className="flex-1">
                <h3 className="font-semibold text-white">Invoice {invoice.invoice_number}</h3>
                {getVehicleLabel(selectedOrder) && (
                  <p className="text-amber-300 text-xs font-medium">{getVehicleLabel(selectedOrder)}</p>
                )}
                <p className="text-sm text-gray-400">Ready for payment</p>
              </div>
              <button
                onClick={handleDownloadPdf}
                title="Download Invoice PDF"
                className="shrink-0 p-2 text-purple-300 hover:text-white transition-colors"
              >
                <Download className="w-5 h-5" />
              </button>
            </div>

            <div className="bg-white/5 rounded-lg p-4 mb-4">
              <div className="flex justify-between mb-2">
                <span className="text-gray-400">Subtotal</span>
                <span className="text-white">${parseFloat(invoice.subtotal).toFixed(2)}</span>
              </div>
              <div className="flex justify-between mb-2">
                <span className="text-gray-400">Shop Supplies</span>
                <span className="text-white">${parseFloat(invoice.shop_supplies_amount || '0').toFixed(2)}</span>
              </div>
              <div className="flex justify-between mb-2">
                <span className="text-gray-400">Card Processing Fee</span>
                <span className="text-white">${parseFloat(invoice.service_fee_amount || '0').toFixed(2)}</span>
              </div>
              <div className="flex justify-between mb-2">
                <span className="text-gray-400">Tax</span>
                <span className="text-white">${parseFloat(invoice.tax_amount || '0').toFixed(2)}</span>
              </div>
              {parseFloat(invoice.discount_amount || '0') > 0 && (
                <div className="flex justify-between mb-2">
                  <span className="text-gray-400">Discount</span>
                  <span className="text-green-400">-${parseFloat(invoice.discount_amount || '0').toFixed(2)}</span>
                </div>
              )}
              <div className="flex justify-between pt-2 border-t border-white/10">
                <span className="font-semibold text-white">Total Due</span>
                <span className="font-bold text-xl text-white">${parseFloat(invoice.total_amount).toFixed(2)}</span>
              </div>
            </div>

            <Link
              to={`/portal/invoices/${invoice.id}`}
              state={{ paymentOrigin: 'History' }}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#8b7cf7] px-4 py-3.5 text-sm font-extrabold text-[#0e1118] hover:brightness-110"
            >
              Review payment options
            </Link>

            <div className="hidden">
              <CustomerZellePaymentPanel
                garageName={zelleInfo?.garage_name}
                serviceFeeAmount={invoice.service_fee_amount}
                zelleAmount={zelleAmount}
                zelleMemo={zelleMemo}
                zelleEmail={zelleInfo?.zelle_email}
                zellePhone={zelleInfo?.zelle_phone}
                zelleQrImage={zelleInfo?.zelle_qr_image}
                pendingConfirmation={Boolean(invoice.pending_zelle_confirmation)}
                isOpen={showZelleDetails}
                isSenderEditing={isZelleSenderEditing}
                senderEmail={zelleSenderEmail}
                senderPhone={zelleSenderPhone}
                senderNotes={zelleNotes}
                isSubmitting={submitZelleMutation.isPending}
                onToggleOpen={() => setShowZelleDetails(prev => !prev)}
                onCopy={copyText}
                onToggleSenderEditing={() => setIsZelleSenderEditing(editing => !editing)}
                onSenderEmailChange={setZelleSenderEmail}
                onSenderPhoneChange={(value: string) => setZelleSenderPhone(formatUSPhone(value))}
                onSenderNotesChange={setZelleNotes}
                onSubmit={() => submitZelleMutation.mutate()}
              />

              {!invoice.pending_zelle_confirmation && zelleInfo?.stripe_payments_available && (
                <div>
                  <p className="text-xs uppercase tracking-wide text-gray-400 mb-2">Pay instantly by card</p>
                  {!showPayment ? (
                    <button
                      onClick={handlePayClick}
                      className="flex w-full items-center justify-center gap-2 rounded-xl bg-violet-600 py-3 font-semibold text-white transition-colors hover:bg-violet-500"
                    >
                      <CreditCard className="w-5 h-5" />
                      Pay Now
                    </button>
                  ) : stripeOptions && stripeInstance ? (
                    <Elements stripe={stripeInstance} options={stripeOptions}>
                      <PaymentForm invoiceId={invoice.id} onSuccess={handlePaymentSuccess} />
                    </Elements>
                  ) : (
                    <div className="flex items-center justify-center py-4">
                      <Spinner size="lg" />
                    </div>
                  )}
                </div>
              )}

              {!invoice.pending_zelle_confirmation && isQuickBooksPaymentLoading && (
                <div
                  role="status"
                  aria-label="Checking card payment availability"
                  className="animate-pulse overflow-hidden rounded-xl border border-gray-700 bg-slate-950/40"
                >
                  <div className="px-4 py-3">
                    <div className="h-4 w-40 rounded bg-gray-700/70" />
                    <div className="mt-2 h-3 w-28 rounded bg-gray-800" />
                  </div>
                  <span className="sr-only">Checking card payment availability…</span>
                </div>
              )}

              {!invoice.pending_zelle_confirmation && quickBooksPayment?.available && quickBooksPayment.token_url && (
                <div className="overflow-hidden rounded-xl border border-emerald-500/40 bg-slate-950/40">
                  <button
                    type="button"
                    aria-expanded={showQuickBooksPayment}
                    aria-controls="history-quickbooks-payment-panel"
                    onClick={() => setShowQuickBooksPayment(open => !open)}
                    className="flex w-full items-center justify-between gap-3 bg-emerald-500/10 px-4 py-3 text-left hover:bg-emerald-500/15"
                  >
                    <span>
                      <span className="block text-sm font-semibold text-emerald-200">Pay securely by card</span>
                      <span className="mt-1 block text-xs text-gray-400">Powered by QuickBooks</span>
                    </span>
                    {showQuickBooksPayment
                      ? <ChevronUp className="h-4 w-4 shrink-0 text-emerald-200" />
                      : <ChevronDown className="h-4 w-4 shrink-0 text-emerald-200" />}
                  </button>
                  {showQuickBooksPayment && (
                    <div id="history-quickbooks-payment-panel" className="border-t border-emerald-500/30 px-4 py-4">
                      <QuickBooksPaymentPanel
                        invoiceId={invoice.id}
                        tokenUrl={quickBooksPayment.token_url}
                        onSuccess={handlePaymentSuccess}
                      />
                    </div>
                  )}
                </div>
              )}

              {!invoice.pending_zelle_confirmation
                && zelleInfo
                && !zelleInfo.stripe_payments_available
                && !isQuickBooksPaymentLoading
                && !(quickBooksPayment?.available && quickBooksPayment.token_url) && (
                <p className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-3 py-2 text-sm text-amber-200">
                  Online card payment is currently unavailable for this shop.
                </p>
              )}
            </div>
          </div>
        )}

        {/* Paid confirmation */}
        {selectedOrder.status === 'paid' && (
          <div className="bg-green-500/10 rounded-xl border border-green-500/30 p-4 sm:p-6">
            <div className="flex items-center gap-3">
              <CheckCircle className="w-8 h-8 text-green-400" />
              <div className="flex-1">
                <h3 className="font-semibold text-white">Payment Complete</h3>
                <p className="text-sm text-gray-400">
                  Thank you for your payment{invoice?.paid_at ? ` on ${format(new Date(invoice.paid_at), 'MMM d, yyyy')}` : ''}
                </p>
              </div>
              {invoice && (
                <button
                  onClick={handleDownloadPdf}
                  className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 bg-green-700/40 hover:bg-green-700/60 text-green-200 text-sm font-medium rounded-lg transition-colors"
                >
                  <Download className="w-4 h-4" />
                  Receipt
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  if (isActiveRepairsView) {
    const activeOrders = (orders?.filter(isActiveRepair) ?? [])
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    const activeInvoiceByOrder = new Map(allInvoices.map(item => [item.repair_order_id, item]))
    const attentionCount = activeOrders.filter(order =>
      order.status === 'invoiced' || (order.quote_sent === true && order.quote_approved !== true),
    ).length

    return (
      <div className="space-y-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-extrabold tracking-[-0.01em]">Active repairs</h1>
            <p className="mt-1 text-[13px] text-[#8b92a5]">
              {activeOrders.length} open repair{activeOrders.length === 1 ? '' : 's'}
              {attentionCount > 0 ? ` · ${attentionCount} need${attentionCount === 1 ? 's' : ''} your attention` : ' · Everything is moving'}
            </p>
          </div>
          <Link
            to="/portal/repairs"
            className="inline-flex h-10 items-center justify-center rounded-[10px] border border-[#272d3d] bg-[#191d2a] px-4 text-xs font-bold text-[#c9cdd8] hover:border-[#343b52]"
          >
            View repair history
          </Link>
        </div>

        {activeOrders.length > 0 ? (
          <div className="space-y-2">
            {activeOrders.map(order => {
              const invoiceForOrder = activeInvoiceByOrder.get(order.id)
              const needsEstimateApproval = order.quote_sent === true && order.quote_approved !== true
              const needsPayment = order.status === 'invoiced' && invoiceForOrder?.status !== 'paid'
              const actionLabel = needsPayment
                ? 'Pay invoice'
                : needsEstimateApproval
                  ? 'Review estimate'
                  : 'View details'

              return (
                <button
                  key={order.id}
                  type="button"
                  onClick={() => setSelectedOrder(order)}
                  className={`grid w-full grid-cols-[52px_1fr_auto] items-center gap-3 rounded-xl border bg-[#161a26] p-3 text-left transition-colors hover:bg-[#1a1f2c] sm:grid-cols-[52px_1fr_auto_auto] sm:gap-4 sm:px-4 ${
                    needsPayment
                      ? 'border-[#ff6b6e]/30'
                      : needsEstimateApproval
                        ? 'border-[#f0b959]/30'
                        : 'border-[#232939] hover:border-[#343b52]'
                  }`}
                >
                  <DateBlock value={order.updated_at} />
                  <div className="min-w-0">
                    <h2 className="truncate text-[13px] font-extrabold">{order.description || 'Repair service'}</h2>
                    <p className="mt-1 truncate text-[11px] text-[#8b92a5]">
                      {order.order_number}{getVehicleLabel(order) ? ` · ${getVehicleLabel(order)}` : ''}
                    </p>
                    <p className="mt-1 text-[11px] text-[#5c6375]">Updated {format(new Date(order.updated_at), 'MMM d · h:mm a')}</p>
                  </div>
                  <span className={`rounded-md border px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.04em] ${
                    needsPayment
                      ? 'border-[#ff6b6e]/30 bg-[#ff6b6e]/10 text-[#ff8b8d]'
                      : needsEstimateApproval
                        ? 'border-[#f0b959]/30 bg-[#f0b959]/10 text-[#f0b959]'
                        : STATUS_BADGE_COLORS[order.status] || 'border border-white/10 bg-white/5 text-gray-300'
                  }`}>
                    {repairStatusLabel(order.status)}
                  </span>
                  <span className={`col-start-2 text-xs font-extrabold sm:col-start-auto ${
                    needsPayment ? 'text-[#ff8b8d]' : needsEstimateApproval ? 'text-[#f0b959]' : 'text-[#a78bfa]'
                  }`}>
                    {actionLabel} →
                  </span>
                </button>
              )
            })}
          </div>
        ) : (
          <div className="rounded-2xl border border-[#232939] bg-[#161a26] py-12 text-center">
            <CheckCircle className="mx-auto h-9 w-9 text-[#3ecf6f]" />
            <h2 className="mt-3 font-extrabold">No active repairs</h2>
            <p className="mt-1 text-sm text-[#8b92a5]">New repair work will appear here as soon as it is checked in.</p>
            <Link
              to="/portal/services"
              className="mt-5 inline-flex h-10 items-center justify-center rounded-[10px] bg-[#8b7cf7] px-4 text-xs font-extrabold text-[#0e1118]"
            >
              Book a service
            </Link>
          </div>
        )}
      </div>
    )
  }

  // List view - only finalized orders
  const finalizedStatuses = ['paid', 'completed', 'cancelled']
  const historyOrders = orders?.filter(o => finalizedStatuses.includes(o.status)) ?? []
  const invoiceByOrder = new Map(allInvoices.map(item => [item.repair_order_id, item]))
  const filteredHistory = statusFilter === 'all'
    ? historyOrders
    : historyOrders.filter(order => order.status === statusFilter)
  const historyGroups = filteredHistory
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    .reduce<Record<string, RepairOrder[]>>((groups, order) => {
      const key = format(new Date(order.updated_at), 'MMMM yyyy')
      groups[key] = [...(groups[key] || []), order]
      return groups
    }, {})
  const paidThisYear = historyOrders.filter(order =>
    order.status === 'paid' && new Date(order.updated_at).getFullYear() === new Date().getFullYear(),
  )
  const paidYtd = paidThisYear.reduce((sum, order) => {
    const invoiceForOrder = invoiceByOrder.get(order.id)
    return sum + Number(invoiceForOrder?.total_amount || getOrderTotal(order))
  }, 0)

  const downloadHistoryCsv = () => {
    const rows = [
      ['Date', 'Repair order', 'Services', 'Status', 'Amount'],
      ...historyOrders.map(order => {
        const invoiceForOrder = invoiceByOrder.get(order.id)
        return [
          format(new Date(order.updated_at), 'yyyy-MM-dd'),
          order.order_number,
          order.description || '',
          order.status,
          Number(invoiceForOrder?.total_amount || getOrderTotal(order)).toFixed(2),
        ]
      }),
    ]
    const csv = rows
      .map(row => row.map(value => `"${String(value).replace(/"/g, '""')}"`).join(','))
      .join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `repair-history-${format(new Date(), 'yyyy-MM-dd')}.csv`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-[-0.01em]">Repair history</h1>
          <p className="mt-1 text-[13px] text-[#8b92a5]">
            {paidThisYear.length} completed orders · <Money className="font-bold text-[#3ecf6f]">{formatMoney(paidYtd)} paid in {new Date().getFullYear()}</Money>
          </p>
        </div>
        {historyOrders.length > 12 && (
          <button type="button" onClick={downloadHistoryCsv} className="h-10 rounded-[10px] border border-[#272d3d] bg-[#191d2a] px-4 text-xs font-bold text-[#c9cdd8]">
            Download all (CSV)
          </button>
        )}
      </div>

      <div className="-mx-4 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
        <div className="flex min-w-max gap-2">
        {[
          { value: 'all', label: 'All' },
          { value: 'paid', label: 'Paid' },
          { value: 'completed', label: 'Completed' },
          { value: 'cancelled', label: 'Cancelled' },
        ].map((option) => (
          <Pill
            key={option.value}
            active={statusFilter === option.value}
            onClick={() => setStatusFilter(option.value)}
          >
            {option.label}
          </Pill>
        ))}
        </div>
      </div>

      {Object.keys(historyGroups).length > 0 ? (
        <div className="space-y-5">
          {Object.entries(historyGroups).map(([month, monthOrders]) => {
            const monthTotal = monthOrders.reduce((sum, order) => {
              const invoiceForOrder = invoiceByOrder.get(order.id)
              return sum + Number(invoiceForOrder?.total_amount || getOrderTotal(order))
            }, 0)
            return (
              <section key={month}>
                <div className="mb-2 flex items-center justify-between gap-4">
                  <h2 className="text-[11px] font-extrabold uppercase tracking-[0.1em]">{month}</h2>
                  <span className="text-[11px] font-bold text-[#5c6375]">{monthOrders.length} orders · {formatMoney(monthTotal)}</span>
                </div>
                <div className="space-y-2">
                  {monthOrders.map(order => {
                    const invoiceForOrder = invoiceByOrder.get(order.id)
                    const amount = Number(invoiceForOrder?.total_amount || getOrderTotal(order))
                    return (
                <button
                  key={order.id}
                  onClick={() => setSelectedOrder(order)}
                        className="grid w-full grid-cols-[52px_1fr_auto] items-center gap-3 rounded-xl border border-[#232939] bg-[#161a26] p-3 text-left hover:border-[#343b52] hover:bg-[#161b26] sm:grid-cols-[52px_1fr_auto_84px_auto] sm:gap-4 sm:px-4"
                >
                        <DateBlock value={order.updated_at} />
                        <div className="min-w-0">
                          <h3 className="truncate text-[13px] font-bold">{order.description || 'Repair service'}</h3>
                          <p className="mt-1 truncate text-[11px] text-[#8b92a5]">{order.order_number}{getVehicleLabel(order) ? ` · ${getVehicleLabel(order)}` : ''}</p>
                        </div>
                        {order.status === 'paid' ? (
                          <PaidBadge />
                        ) : (
                          <span className={`rounded-md border px-2 py-0.5 text-[10px] font-extrabold uppercase ${
                            order.status === 'cancelled'
                              ? 'border-[#ff6b6e]/30 bg-[#ff6b6e]/10 text-[#ff8b8d]'
                              : 'border-[#272d3d] bg-[#191d2a] text-[#8b92a5]'
                          }`}>{order.status}</span>
                        )}
                        <Money className="col-start-2 text-sm font-extrabold sm:col-start-auto sm:text-right">{formatMoney(amount)}</Money>
                        {invoiceForOrder && (
                          <a
                            href={`/api/v1/invoices/${invoiceForOrder.id}/pdf`}
                            download
                            onClick={event => event.stopPropagation()}
                            className="col-start-3 text-right text-xs font-bold text-[#a78bfa] hover:text-[#c4b1ff] sm:col-start-auto"
                          >
                            Invoice ↓
                          </a>
                        )}
                </button>
                    )
                  })}
                </div>
              </section>
            )
          })}
        </div>
      ) : (
        <div className="rounded-2xl border border-[#232939] bg-[#161a26] py-12 text-center">
          <ClipboardList className="mx-auto h-9 w-9 text-[#5c6375]" />
          <h2 className="mt-3 font-extrabold">No repair history yet</h2>
          <p className="mt-1 text-sm text-[#8b92a5]">
            {statusFilter === 'all' ? 'Completed repairs will appear here.' : `No ${statusFilter} orders found.`}
          </p>
              </div>
      )}
    </div>
  )
}

export default function CustomerPortalPage() {
  const location = useLocation()
  const portalScrollRef = useRef<HTMLElement>(null)
  const { user } = useAuthStore()
  const { data: tenantBranding } = useTenantBranding()
  const [mobileNavPage, setMobileNavPage] = useState<'primary' | 'secondary'>('primary')
  const mobileNavTouchStart = useRef<{ x: number; y: number } | null>(null)
  const suppressMobileNavClick = useRef(false)
  const profileNameParts = [user?.first_name, user?.last_name].filter(
    (part): part is string => Boolean(part?.trim()),
  )
  const profileDisplayName = profileNameParts.join(' ').trim() || user?.email || 'Account'
  const portalBrandName = tenantBranding?.name || user?.tenant_name || 'Diesel Bridge Network'
  const profileMonogram = (
    profileNameParts.map((part) => part.charAt(0)).join('') ||
    user?.email?.replace(/[^a-zA-Z0-9]/g, '').slice(0, 2) ||
    'ME'
  ).slice(0, 2).toUpperCase()
  
  // Notification manager for queued, deduplicated notifications
  const { notify, banners, dismissBanner, clearBanners } = useNotificationManager()
  
  // Connect to WebSocket for real-time updates
  useWebSocket({ onNotification: notify })

  useEffect(() => {
    const root = document.documentElement
    const previousScrollY = window.scrollY

    // Keep the document stationary; the portal's middle grid row owns scroll.
    window.scrollTo(0, 0)
    root.classList.add('customer-portal-active')

    return () => {
      root.classList.remove('customer-portal-active')
      window.scrollTo(0, previousScrollY)
    }
  }, [])

  useEffect(() => {
    portalScrollRef.current?.scrollTo({ top: 0 })
    const isOverflowRoute =
      location.pathname === '/portal/repairs' ||
      location.pathname.startsWith('/portal/invoices/') ||
      location.pathname === '/portal/settings'
    setMobileNavPage(isOverflowRoute ? 'secondary' : 'primary')
  }, [location.pathname])

  const navLinks = [
    { to: '/portal', label: 'Dashboard', mobileLabel: 'Home', exact: true, icon: Home },
    { to: '/portal/services', label: 'Services', mobileLabel: 'Services', icon: Wrench },
    { to: '/portal/appointments', label: 'Appointments', mobileLabel: 'Appts', icon: Calendar },
    { to: '/portal/vehicles', label: 'Vehicles', mobileLabel: 'Vehicles', icon: Truck },
    { to: '/portal/repairs', label: 'History', mobileLabel: 'History', icon: History },
  ]

  const isActive = (path: string, exact?: boolean) =>
    exact
      ? location.pathname === path
      : location.pathname === path || (path === '/portal/services' && location.pathname.startsWith('/portal/book/'))

  const isInvoicePage = location.pathname.startsWith('/portal/invoices/')
  const mobilePrimaryLinks = navLinks.slice(0, 4)
  const isMobileMoreActive =
    location.pathname === '/portal/settings' ||
    location.pathname === '/portal/repairs' ||
    isInvoicePage

  const handleMobileNavTouchStart = (event: TouchEvent<HTMLDivElement>) => {
    const touch = event.touches[0]
    if (touch) mobileNavTouchStart.current = { x: touch.clientX, y: touch.clientY }
  }

  const handleMobileNavTouchEnd = (event: TouchEvent<HTMLDivElement>) => {
    const start = mobileNavTouchStart.current
    const touch = event.changedTouches[0]
    mobileNavTouchStart.current = null
    if (!start || !touch) return

    const deltaX = touch.clientX - start.x
    const deltaY = touch.clientY - start.y
    if (Math.abs(deltaX) < 36 || Math.abs(deltaX) <= Math.abs(deltaY) * 1.2) return

    suppressMobileNavClick.current = true
    window.setTimeout(() => {
      suppressMobileNavClick.current = false
    }, 350)
    if (deltaX < 0 && mobileNavPage === 'primary') setMobileNavPage('secondary')
    if (deltaX > 0 && mobileNavPage === 'secondary') setMobileNavPage('primary')
  }

  const handleMobileNavClickCapture = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!suppressMobileNavClick.current) return
    suppressMobileNavClick.current = false
    event.preventDefault()
    event.stopPropagation()
  }

  return (
    <div className="fixed inset-0 grid min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden bg-[#0d1018] font-['Helvetica_Neue',Helvetica,Arial,sans-serif] text-[#eceef4]">
      <nav
        className="relative z-50 shrink-0 border-b border-[#1e2432] bg-[#0a0d14]"
        style={{ paddingTop: 'env(safe-area-inset-top)' }}
      >
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="flex h-14 items-center justify-between">
            <Link
              to="/portal"
              className="inline-flex min-w-0 items-center py-1"
              aria-label={`${portalBrandName} customer portal`}
            >
              <TenantBrandLogo
                tenantLogoUrl={tenantBranding?.logo_url}
                tenantName={portalBrandName}
                fallbackVariant="admin"
                className="h-8 max-w-[150px] object-contain object-left sm:h-9 sm:max-w-[190px]"
              />
            </Link>

            <div className="hidden items-center gap-1.5 md:flex">
              {!isInvoicePage && navLinks.map(link => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`flex h-[34px] items-center rounded-lg px-3 text-[13px] font-bold ${
                    isActive(link.to, link.exact)
                      ? 'bg-[#8b7cf7]/10 text-[#c9bfff]'
                      : 'text-[#8b92a5] hover:bg-[#161a26] hover:text-[#c9cdd8]'
                  }`}
                >
                  {link.label}
                </Link>
              ))}
              <Link
                to="/portal/settings"
                aria-label={`Open account for ${profileDisplayName}`}
                className={`ml-2 flex h-8 w-8 items-center justify-center rounded-full border text-[10px] font-extrabold ${
                  location.pathname === '/portal/settings'
                    ? 'border-[#c9bfff] bg-[#312a54] text-white'
                    : 'border-[#8b7cf7] bg-[#241f3d] text-[#c9bfff]'
                }`}
              >
                {profileMonogram}
              </Link>
            </div>

          </div>
        </div>
      </nav>

      <main
        ref={portalScrollRef}
        className={`min-h-0 w-full flex-1 overflow-x-hidden overflow-y-auto overscroll-none ${
          isInvoicePage ? 'max-w-none p-0' : 'mx-auto max-w-7xl px-4 pb-7 pt-5 sm:px-6 sm:pb-8 sm:pt-[22px]'
        }`}
        style={{
          WebkitOverflowScrolling: 'touch',
          paddingLeft: isInvoicePage ? undefined : 'max(1rem, env(safe-area-inset-left))',
          paddingRight: isInvoicePage ? undefined : 'max(1rem, env(safe-area-inset-right))',
          paddingBottom: isInvoicePage ? undefined : 'max(1.75rem, env(safe-area-inset-bottom))',
        }}
      >
        <NotificationBanner
          banners={banners}
          onDismiss={dismissBanner}
          onDismissAll={clearBanners}
          autoDismissMs={10000}
        />

        <Routes>
          <Route path="" element={<PortalDashboardPage />} />
          <Route path="services" element={<ServicesPage />} />
          <Route path="book/:serviceId" element={<BookingPage />} />
          <Route path="appointments" element={<AppointmentsPage />} />
          <Route path="vehicles" element={<PortalVehiclesPage />} />
          <Route path="repairs" element={<CustomerRepairs />} />
          <Route path="invoices/:invoiceId" element={<CustomerInvoicePage />} />
          <Route path="settings" element={<ProfileSettingsPage />} />
        </Routes>
      </main>

      <div className={`relative z-50 shrink-0 md:hidden ${isInvoicePage ? 'hidden' : ''}`}>
        <div
          className="overflow-hidden border-t border-[#232939] bg-[#0a0d14]/95 pt-1.5 shadow-[0_-12px_32px_rgba(0,0,0,0.28)] backdrop-blur-xl"
          style={{
            paddingBottom: 'max(0.5rem, env(safe-area-inset-bottom))',
            paddingLeft: 'max(0.25rem, env(safe-area-inset-left))',
            paddingRight: 'max(0.25rem, env(safe-area-inset-right))',
          }}
          onTouchStart={handleMobileNavTouchStart}
          onTouchEnd={handleMobileNavTouchEnd}
          onClickCapture={handleMobileNavClickCapture}
          aria-label="Customer portal mobile navigation"
        >
          <div
            className={`flex w-[200%] transform-gpu transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${
              mobileNavPage === 'secondary' ? '-translate-x-1/2' : 'translate-x-0'
            }`}
          >
            <div className="flex w-1/2 shrink-0 px-1" aria-hidden={mobileNavPage !== 'primary'}>
              {mobilePrimaryLinks.map(link => {
                const Icon = link.icon
                const isLinkActive = isActive(link.to, link.exact)
                return (
                  <Link
                    key={link.to}
                    to={link.to}
                    tabIndex={mobileNavPage === 'primary' ? 0 : -1}
                    className={`flex min-h-12 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-1 text-[10px] font-bold transition-colors ${
                      isLinkActive
                        ? 'bg-[#8b7cf7]/10 text-[#c9bfff]'
                        : 'text-[#737b8f] hover:text-[#c9cdd8]'
                    }`}
                  >
                    <Icon className="h-5 w-5" />
                    <span>{link.mobileLabel}</span>
                  </Link>
                )
              })}
              <button
                type="button"
                onClick={() => setMobileNavPage('secondary')}
                tabIndex={mobileNavPage === 'primary' ? 0 : -1}
                aria-expanded={mobileNavPage === 'secondary'}
                aria-controls="portal-mobile-secondary-navigation"
                className={`flex min-h-12 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-1 text-[10px] font-bold transition-colors ${
                  isMobileMoreActive
                    ? 'bg-[#8b7cf7]/10 text-[#c9bfff]'
                    : 'text-[#737b8f] hover:text-[#c9cdd8]'
                }`}
              >
                <MoreHorizontal className="h-5 w-5" />
                <span>More</span>
              </button>
            </div>

            <div
              id="portal-mobile-secondary-navigation"
              className="flex w-1/2 shrink-0 px-1"
              aria-hidden={mobileNavPage !== 'secondary'}
            >
              <button
                type="button"
                onClick={() => setMobileNavPage('primary')}
                tabIndex={mobileNavPage === 'secondary' ? 0 : -1}
                className="flex min-h-12 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-1 text-[10px] font-bold text-[#737b8f] transition-colors hover:text-[#c9cdd8]"
                aria-label="Back to primary navigation"
              >
                <ChevronLeft className="h-5 w-5" />
                <span>Back</span>
              </button>
              <Link
                to="/portal/repairs?view=active"
                tabIndex={mobileNavPage === 'secondary' ? 0 : -1}
                className={`flex min-h-12 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-1 text-[10px] font-bold transition-colors ${
                  location.pathname === '/portal/repairs' && isActiveRepairsSearch(location.search)
                    ? 'bg-[#8b7cf7]/10 text-[#c9bfff]'
                    : 'text-[#737b8f] hover:text-[#c9cdd8]'
                }`}
              >
                <Wrench className="h-5 w-5" />
                <span>Repairs</span>
              </Link>
              <Link
                to="/portal/repairs"
                tabIndex={mobileNavPage === 'secondary' ? 0 : -1}
                className={`flex min-h-12 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-1 text-[10px] font-bold transition-colors ${
                  location.pathname === '/portal/repairs' && !isActiveRepairsSearch(location.search)
                    ? 'bg-[#8b7cf7]/10 text-[#c9bfff]'
                    : 'text-[#737b8f] hover:text-[#c9cdd8]'
                }`}
              >
                <History className="h-5 w-5" />
                <span>History</span>
              </Link>
              <Link
                to="/portal/settings"
                tabIndex={mobileNavPage === 'secondary' ? 0 : -1}
                className={`flex min-h-12 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-1 text-[10px] font-bold transition-colors ${
                  location.pathname === '/portal/settings'
                    ? 'bg-[#8b7cf7]/10 text-[#c9bfff]'
                    : 'text-[#737b8f] hover:text-[#c9cdd8]'
                }`}
              >
                <User className="h-5 w-5" />
                <span>Account</span>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
