import { useState, useEffect } from 'react'
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
import { Camera, CheckCircle, ClipboardList, Truck, Wrench, CreditCard, FileText, ArrowLeft, Home, User, History, Calendar, Download } from 'lucide-react'
import type { Stripe } from '@stripe/stripe-js'
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js'
import toast from 'react-hot-toast'
import { useTheme } from '../../contexts/ThemeContext'
import { useWebSocket } from '../../hooks/useWebSocket'
import { useNotificationManager } from '../../hooks/useNotificationManager'
import { usePlatformContact } from '../../hooks/usePlatformContact'
import NotificationBanner from '../../components/NotificationBanner'
import TenantBrandLogo from '../../components/brand/TenantBrandLogo'
import { getStripeForAccount } from '../../lib/stripe'
import { formatUSPhone } from '../../utils/phone'
import useTenantBranding from '@/hooks/useTenantBranding'
import CustomerZellePaymentPanel from './ZellePaymentPanel'

const STATUS_BADGE_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  quoted: 'bg-blue-100 text-blue-700',
  declined: 'bg-red-100 text-red-700',
  approved: 'bg-cyan-100 text-cyan-700',
  assigned: 'bg-amber-100 text-amber-700',
  acknowledged: 'bg-amber-100 text-amber-700',
  in_progress: 'bg-amber-100 text-amber-700',
  pending_review: 'bg-orange-100 text-orange-700',
  completed: 'bg-green-100 text-green-700',
  invoiced: 'bg-purple-100 text-purple-700',
  paid: 'bg-emerald-100 text-emerald-700',
  cancelled: 'bg-red-100 text-red-700',
}

const CUSTOMER_ACTIVE_REPAIR_STATUSES = [
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

interface ZelleInfoResponse {
  zelle_email: string | null
  zelle_phone: string | null
  zelle_qr_image: string | null
  garage_name: string
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
    (o.status === 'quoted' && o.quote_sent === true)
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
          o.status === 'invoiced' || (o.status === 'quoted' && o.quote_sent === true)
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
                        {order.status === 'invoiced' ? 'Pay Now' : 'Review Quote'}
                      </span>
                      <div className="text-sm font-bold text-white">
                        ${getOrderTotal(order).toFixed(2)}
                      </div>
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
                        <span className={`px-1.5 sm:px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium ${STATUS_BADGE_COLORS[order.status] || 'bg-gray-100 text-gray-700'}`}>
                          {order.status.replace('_', ' ')}
                        </span>
                        <div className="text-xs sm:text-sm font-medium text-white">
                          ${getOrderTotal(order).toFixed(2)}
                        </div>
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
                      <span className={`px-1.5 sm:px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium ${STATUS_BADGE_COLORS[order.status] || 'bg-gray-100 text-gray-700'}`}>
                        {order.status.replace('_', ' ')}
                      </span>
                      <div className="text-xs sm:text-sm font-medium text-white">
                        ${getOrderTotal(order).toFixed(2)}
                      </div>
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
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
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
        className="w-full py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white font-semibold rounded-lg flex items-center justify-center gap-2"
      >
        {isProcessing ? (
          <>
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
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
    enabled: !!selectedOrder && selectedOrder.status === 'quoted',
  })

  const approveQuoteMutation = useMutation({
    mutationFn: async (quoteId: string) => {
      const response = await api.post(`/quotes/${quoteId}/approve`)
      return response.data as Quote
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['quote'] })
      toast.success('Quote approved! Work will begin soon.')
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
      toast.success('Quote declined. The shop will contact you about revisions.')
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
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
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

    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => {
              setSelectedOrder(null)
              setShowPayment(false)
              setStripeOptions(null)
            }}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-gray-400" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-white">{selectedOrder.order_number}</h1>
            {getVehicleLabel(selectedOrder) && (
              <p className="text-amber-300 text-sm font-medium mt-0.5">{getVehicleLabel(selectedOrder)}</p>
            )}
            <p className="text-gray-400 text-sm">
              {format(new Date(selectedOrder.created_at), 'MMMM d, yyyy')}
            </p>
          </div>
          <span className={`ml-auto px-3 py-1 rounded-full text-sm font-medium ${STATUS_BADGE_COLORS[selectedOrder.status] || 'bg-gray-100 text-gray-700'}`}>
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
              <div className="flex justify-between items-center text-sm">
                <span className="text-gray-400">Total before savings</span>
                <span className="text-gray-200">${preSavingsTotal.toFixed(2)}</span>
              </div>
              {customerSavings > 0 && (
                <div className="flex justify-between items-center text-sm">
                  <span className="text-emerald-300">Best savings</span>
                  <span className="font-semibold text-emerald-300">-${customerSavings.toFixed(2)}</span>
                </div>
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
        </div>

        {/* Quote Approval Section */}
        {selectedOrder.status === 'quoted' && selectedQuote && !selectedQuote.is_approved && (
          <div className="bg-amber-500/10 rounded-xl border border-amber-500/30 p-4 sm:p-6">
            <div className="flex items-center gap-3 mb-4">
              <FileText className="w-6 h-6 text-amber-400" />
              <div>
                <h3 className="font-semibold text-white">Quote #{selectedQuote.quote_number}</h3>
                <p className="text-sm text-gray-400">Awaiting your approval</p>
              </div>
            </div>

            <div className="bg-white/5 rounded-lg p-4 mb-4">
              <div className="flex justify-between items-center">
                <span className="text-gray-400">Quote Total</span>
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
                  className="flex-1 px-4 py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-500 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  <CheckCircle className="w-5 h-5" />
                  {approveQuoteMutation.isPending ? 'Approving...' : 'Approve Quote'}
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
                  className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none"
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
                    className="flex-1 px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-500 text-white font-medium rounded-lg transition-colors"
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
                <span className="text-gray-400">Service Fee</span>
                <span className="text-white">${parseFloat(invoice.service_fee_amount || '0').toFixed(2)}</span>
              </div>
              <div className="flex justify-between mb-2">
                <span className="text-gray-400">Tax</span>
                <span className="text-white">${parseFloat(invoice.tax_amount || '0').toFixed(2)}</span>
              </div>
              <div className="flex justify-between mb-2">
                <span className="text-gray-400">Discount</span>
                <span className="text-green-400">-${parseFloat(invoice.discount_amount || '0').toFixed(2)}</span>
              </div>
              <div className="flex justify-between pt-2 border-t border-white/10">
                <span className="font-semibold text-white">Total Due</span>
                <span className="font-bold text-xl text-white">${parseFloat(invoice.total_amount).toFixed(2)}</span>
              </div>
            </div>

            <div className="mb-4">
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
            </div>

            {!invoice.pending_zelle_confirmation && (
            <div className="pt-1">
              <p className="text-xs uppercase tracking-wide text-gray-400 mb-2">Pay instantly by card</p>
              {!showPayment ? (
                <button
                  onClick={handlePayClick}
                  className="w-full py-3 bg-green-600 hover:bg-green-700 text-white font-semibold rounded-lg flex items-center justify-center gap-2"
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
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-green-500"></div>
                </div>
              )}
            </div>
            )}
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

  // List view - only finalized orders (paid, completed, cancelled, declined)
  const finalizedStatuses = ['paid', 'completed', 'cancelled', 'declined']
  const historyOrders = orders?.filter(o => finalizedStatuses.includes(o.status)) ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Repair History</h1>
        <p className="text-gray-400 mt-1">Completed and finalized repairs</p>
      </div>

      {/* Status Filter - only finalized statuses */}
      <div className="flex gap-2 overflow-x-auto pb-2 -mx-4 px-4 sm:mx-0 sm:px-0">
        {[
          { value: 'all', label: 'All' },
          { value: 'paid', label: 'Paid' },
          { value: 'completed', label: 'Completed' },
          { value: 'cancelled', label: 'Cancelled' },
          { value: 'declined', label: 'Declined' },
        ].map((option) => (
          <button
            key={option.value}
            onClick={() => setStatusFilter(option.value)}
            className={`px-3 py-1.5 rounded-full text-xs sm:text-sm font-medium whitespace-nowrap transition-colors ${
              statusFilter === option.value
                ? 'text-white'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
            style={statusFilter === option.value ? { backgroundColor: 'var(--accent-500)' } : undefined}
          >
            {option.label}
          </button>
        ))}
      </div>

      {/* History orders list */}
      <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
        {(() => {
          const filteredOrders = statusFilter === 'all' 
            ? historyOrders 
            : historyOrders.filter(o => o.status === statusFilter)
          
          return filteredOrders.length > 0 ? (
            <div className="divide-y divide-white/5">
              {filteredOrders.map((order) => (
                <button
                  key={order.id}
                  onClick={() => setSelectedOrder(order)}
                  className="w-full p-3 sm:p-6 hover:bg-white/5 active:bg-white/10 transition-colors text-left"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-white text-sm sm:text-base">{order.order_number}</h3>
                      {getVehicleLabel(order) && (
                        <p className="text-amber-300 text-xs font-medium mt-0.5">{getVehicleLabel(order)}</p>
                      )}
                      {order.description && (
                        <p className="text-gray-400 text-xs sm:text-sm mt-1 line-clamp-1">{order.description}</p>
                      )}
                      <p className="text-[10px] sm:text-xs text-gray-500 mt-1">
                        {format(new Date(order.created_at), 'MMM d, yyyy')}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 sm:gap-3 shrink-0">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium ${STATUS_BADGE_COLORS[order.status] || 'bg-gray-100 text-gray-700'}`}>
                        {order.status.replace('_', ' ')}
                      </span>
                      <div className="text-right">
                        <div className="text-sm sm:text-lg font-bold text-white">
                          ${getOrderTotal(order).toFixed(2)}
                        </div>
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="text-center py-12">
              <div className="flex justify-center mb-3">
                <ClipboardList className="w-10 h-10 text-purple-300" />
              </div>
              <p className="text-gray-400">
                {statusFilter === 'all' ? 'No repair history yet' : `No ${statusFilter.replace('_', ' ')} orders`}
              </p>
            </div>
          )
        })()}
      </div>
    </div>
  )
}

export default function CustomerPortalPage() {
  const location = useLocation()
  const { accentColors } = useTheme()
  const { data: tenantBranding } = useTenantBranding()
  const { user } = useAuthStore()

  const accentHex = accentColors[500]
  const profileNameParts = [user?.first_name, user?.last_name].filter(
    (part): part is string => Boolean(part?.trim()),
  )
  const profileDisplayName = profileNameParts.join(' ').trim() || user?.email || 'Profile Settings'
  const profileMonogram = (
    profileNameParts.map((part) => part.charAt(0)).join('') ||
    user?.email?.replace(/[^a-zA-Z0-9]/g, '').slice(0, 2) ||
    'ME'
  ).slice(0, 2).toUpperCase()
  const profileTileBorder = `${accentHex}55`
  const profileTileGlow = `${accentHex}26`
  const profileTileInset = `linear-gradient(180deg, ${accentHex}18, rgba(0,0,0,0.04))`
  
  // Notification manager for queued, deduplicated notifications
  const { notify, banners, dismissBanner, clearBanners } = useNotificationManager()
  
  // Connect to WebSocket for real-time updates
  useWebSocket({ onNotification: notify })

  const navLinks = [
    { to: '/portal', label: 'Dashboard', exact: true },
    { to: '/portal/services', label: 'Services' },
    { to: '/portal/appointments', label: 'Appointments' },
    { to: '/portal/vehicles', label: 'Vehicles' },
    { to: '/portal/repairs', label: 'History' },
  ]

  const isActive = (path: string, exact?: boolean) => 
    exact ? location.pathname === path : location.pathname === path

  const isOnSubPage = location.pathname !== '/portal'
  
  const getCurrentPageLabel = () => {
    if (location.pathname.startsWith('/portal/book/')) return 'Book Appointment'
    if (location.pathname.startsWith('/portal/invoices/')) return 'Invoice'
    if (location.pathname === '/portal/settings') return 'Profile Settings'
    const current = navLinks.find(link => location.pathname === link.to)
    return current?.label || ''
  }
  const portalBrandName = tenantBranding?.name || 'Diesel Bridge Network'

  return (
    <div className="min-h-screen">
      <nav className="bg-white/90 backdrop-blur shadow-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex justify-between h-14 sm:h-16">
            {/* Logo */}
            <div className="flex items-center">
              <Link to="/portal" className="inline-flex items-center py-1" aria-label={`${portalBrandName} customer portal`}>
                <TenantBrandLogo
                  tenantLogoUrl={tenantBranding?.logo_url}
                  tenantName={tenantBranding?.name}
                  fallbackVariant="admin"
                  className="h-8 sm:h-10 w-auto object-contain drop-shadow-[0_1px_1px_rgba(15,23,42,0.35)]"
                />
              </Link>
            </div>

            {/* Desktop nav */}
            <div className="hidden md:flex md:items-center md:space-x-6">
              {navLinks.map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`text-sm font-medium transition-colors ${
                    isActive(link.to, link.exact)
                      ? 'border-b-2'
                      : 'text-gray-600 hover:opacity-80'
                  }`}
                  style={isActive(link.to, link.exact) ? { color: accentColors[500], borderColor: accentColors[500] } : { color: undefined }}
                >
                  {link.label}
                </Link>
              ))}
              <Link
                to="/portal/settings"
                aria-label={`Open profile settings for ${profileDisplayName}`}
                className={`group relative flex h-11 w-11 items-center justify-center rounded-2xl border transition-all ${
                  location.pathname === '/portal/settings'
                    ? 'bg-white text-gray-800'
                    : 'border-gray-200 bg-gray-50 text-gray-500 hover:border-gray-300 hover:bg-white hover:text-gray-700'
                }`}
                style={{
                  borderColor: location.pathname === '/portal/settings' ? profileTileBorder : undefined,
                  boxShadow: `0 10px 24px ${profileTileGlow}`,
                  color: location.pathname === '/portal/settings' ? accentHex : undefined,
                }}
                title={profileDisplayName}
              >
                <div
                  className="absolute inset-[3px] rounded-[14px] border border-black/5"
                  style={{ background: location.pathname === '/portal/settings' ? profileTileInset : undefined }}
                />
                <div className="relative flex h-full w-full items-center justify-center rounded-[14px]">
                  <span className="text-[11px] font-semibold tracking-[0.18em]">
                    {profileMonogram}
                  </span>
                </div>
                <span
                  className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-white shadow-[0_0_10px_rgba(52,211,153,0.6)]"
                  style={{ backgroundColor: '#34d399' }}
                />
              </Link>
            </div>
          </div>
        </div>
      </nav>

      <main className="px-4 py-4 sm:py-6 max-w-7xl mx-auto pb-20 md:pb-6 overflow-x-hidden">
        {/* Real-time notification banners */}
        <NotificationBanner
          banners={banners}
          onDismiss={dismissBanner}
          onDismissAll={clearBanners}
          autoDismissMs={10000}
        />

        {/* Breadcrumb - only show on sub-pages */}
        {isOnSubPage && (
          <div className="mb-4 flex items-center gap-2 text-sm">
            <Link 
              to="/portal" 
              className="text-gray-400 hover:opacity-80 transition-colors flex items-center gap-1"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Dashboard
            </Link>
            <span className="text-gray-600">/</span>
            <span className="font-medium" style={{ color: accentColors[500] }}>{getCurrentPageLabel()}</span>
          </div>
        )}
        <Routes>
          <Route path="" element={<CustomerDashboard />} />
          <Route path="services" element={<ServicesPage />} />
          <Route path="book/:serviceId" element={<BookingPage />} />
          <Route path="appointments" element={<AppointmentsPage />} />
          <Route path="vehicles" element={<CustomerVehicles />} />
          <Route path="repairs" element={<CustomerRepairs />} />
          <Route path="invoices/:invoiceId" element={<CustomerInvoicePage />} />
          <Route path="settings" element={<ProfileSettingsPage />} />
        </Routes>
      </main>

      {/* Mobile Bottom Navigation */}
      <div className="fixed bottom-0 left-0 right-0 z-50 md:hidden">
        <div className="bg-white/95 backdrop-blur border-t border-gray-200 px-2 py-2 flex justify-around">
          <Link
            to="/portal"
            className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
              location.pathname !== '/portal' ? 'text-gray-500 hover:text-gray-700' : ''
            }`}
            style={location.pathname === '/portal' ? { color: accentColors[500] } : undefined}
          >
            <Home className="w-5 h-5" />
            <span className="text-[10px] font-medium">Home</span>
          </Link>
          <Link
            to="/portal/services"
            className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
              !(location.pathname === '/portal/services' || location.pathname.startsWith('/portal/book/'))
                ? 'text-gray-500 hover:text-gray-700'
                : ''
            }`}
            style={(location.pathname === '/portal/services' || location.pathname.startsWith('/portal/book/')) ? { color: accentColors[500] } : undefined}
          >
            <Wrench className="w-5 h-5" />
            <span className="text-[10px] font-medium">Services</span>
          </Link>
          <Link
            to="/portal/appointments"
            className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
              location.pathname !== '/portal/appointments' ? 'text-gray-500 hover:text-gray-700' : ''
            }`}
            style={location.pathname === '/portal/appointments' ? { color: accentColors[500] } : undefined}
          >
            <Calendar className="w-5 h-5" />
            <span className="text-[10px] font-medium">Appts</span>
          </Link>
          <Link
            to="/portal/vehicles"
            className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
              location.pathname !== '/portal/vehicles' ? 'text-gray-500 hover:text-gray-700' : ''
            }`}
            style={location.pathname === '/portal/vehicles' ? { color: accentColors[500] } : undefined}
          >
            <Truck className="w-5 h-5" />
            <span className="text-[10px] font-medium">Vehicles</span>
          </Link>
          <Link
            to="/portal/repairs"
            className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
              !(location.pathname === '/portal/repairs' || location.pathname.startsWith('/portal/invoices/'))
                ? 'text-gray-500 hover:text-gray-700'
                : ''
            }`}
            style={(location.pathname === '/portal/repairs' || location.pathname.startsWith('/portal/invoices/')) ? { color: accentColors[500] } : undefined}
          >
            <History className="w-5 h-5" />
            <span className="text-[10px] font-medium">History</span>
          </Link>
          <Link
            to="/portal/settings"
            className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
              location.pathname !== '/portal/settings' ? 'text-gray-500 hover:text-gray-700' : ''
            }`}
            style={location.pathname === '/portal/settings' ? { color: accentColors[500] } : undefined}
          >
            <User className="w-5 h-5" />
            <span className="text-[10px] font-medium">Profile</span>
          </Link>
        </div>
      </div>
    </div>
  )
}
