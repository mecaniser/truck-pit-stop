import { useState, useEffect } from 'react'
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { Customer, Vehicle, RepairOrder, Quote, Invoice } from '../../types'
import { format } from 'date-fns'
import ServicesPage from '../services/ServicesPage'
import BookingPage from '../booking/BookingPage'
import AppointmentsPage from '../appointments/AppointmentsPage'
import ProfileSettingsPage from './ProfileSettingsPage'
import { CheckCircle, ClipboardList, Truck, Wrench, CreditCard, FileText, ArrowLeft, Home, User, History, Calendar } from 'lucide-react'
import { loadStripe } from '@stripe/stripe-js'
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js'
import toast from 'react-hot-toast'

const STATUS_BADGE_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  quoted: 'bg-blue-100 text-blue-700',
  approved: 'bg-cyan-100 text-cyan-700',
  in_progress: 'bg-amber-100 text-amber-700',
  completed: 'bg-green-100 text-green-700',
  invoiced: 'bg-purple-100 text-purple-700',
  paid: 'bg-emerald-100 text-emerald-700',
  cancelled: 'bg-red-100 text-red-700',
}

// Calculate total including service prices from internal_notes
const getOrderTotal = (order: RepairOrder): number => {
  const backendTotal = parseFloat(order.total_cost) || 0
  
  // Parse services from internal_notes
  let serviceTotal = 0
  if (order.internal_notes) {
    try {
      const notes = JSON.parse(order.internal_notes)
      const services = notes?.selected_services || []
      serviceTotal = services.reduce(
        (sum: number, svc: { base_price?: string }) => sum + (parseFloat(svc.base_price || '0') || 0),
        0
      )
    } catch {
      // ignore parse errors
    }
  }
  
  // If services selected, service total is all-in (includes parts)
  // Otherwise use backend total
  return serviceTotal > 0 ? serviceTotal : backendTotal
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
      const response = await api.get('/vehicles')
      return response.data
    },
  })

  const { data: repairOrders } = useQuery<RepairOrder[]>({
    queryKey: ['repair-orders'],
    queryFn: async () => {
      const response = await api.get('/repair-orders')
      return response.data
    },
  })

  const activeRepairs = repairOrders?.filter(o => 
    ['in_progress', 'approved', 'quoted'].includes(o.status)
  ).length || 0

  const completedRepairs = repairOrders?.filter(o => 
    ['completed', 'invoiced', 'paid'].includes(o.status)
  ).length || 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">
          Welcome back, {customer?.first_name || user?.email}
        </h1>
        <p className="text-gray-400 mt-1">Manage your vehicles and track repair status</p>
      </div>

      {/* KPI Cards - Compact on mobile, expanded on desktop */}
      {/* Mobile: Single compact card */}
      <div className="sm:hidden bg-white/5 rounded-xl p-4 border border-white/10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-cyan-500/20 flex items-center justify-center text-2xl">
              <Truck className="w-7 h-7 text-cyan-200" />
            </div>
            <div>
              <div className="text-2xl font-bold text-white">{vehicles?.length || 0}</div>
              <div className="text-xs text-gray-400">Vehicles</div>
            </div>
          </div>
          <div className="flex gap-4">
            <div className="text-center">
              <div className="text-lg font-bold text-amber-400">{activeRepairs}</div>
              <div className="text-[10px] text-gray-500">Active</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-green-400">{completedRepairs}</div>
              <div className="text-[10px] text-gray-500">Done</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-purple-400">{repairOrders?.length || 0}</div>
              <div className="text-[10px] text-gray-500">Total</div>
            </div>
          </div>
        </div>
      </div>

      {/* Desktop: Full KPI cards */}
      <div className="hidden sm:grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-gradient-to-br from-cyan-500/20 to-cyan-600/10 border-cyan-500/30 rounded-xl p-5 border">
          <Truck className="w-8 h-8 text-cyan-200" />
          <div className="mt-3">
            <div className="text-4xl font-bold text-white">{vehicles?.length || 0}</div>
            <div className="text-sm text-gray-400 mt-1">My Vehicles</div>
          </div>
        </div>
        <div className="bg-gradient-to-br from-amber-500/20 to-amber-600/10 border-amber-500/30 rounded-xl p-5 border">
          <Wrench className="w-8 h-8 text-amber-200" />
          <div className="mt-3">
            <div className="text-4xl font-bold text-white">{activeRepairs}</div>
            <div className="text-sm text-gray-400 mt-1">Active Repairs</div>
          </div>
        </div>
        <div className="bg-gradient-to-br from-green-500/20 to-green-600/10 border-green-500/30 rounded-xl p-5 border">
          <CheckCircle className="w-8 h-8 text-green-200" />
          <div className="mt-3">
            <div className="text-4xl font-bold text-white">{completedRepairs}</div>
            <div className="text-sm text-gray-400 mt-1">Completed</div>
          </div>
        </div>
        <div className="bg-gradient-to-br from-purple-500/20 to-purple-600/10 border-purple-500/30 rounded-xl p-5 border">
          <ClipboardList className="w-8 h-8 text-purple-200" />
          <div className="mt-3">
            <div className="text-4xl font-bold text-white">{repairOrders?.length || 0}</div>
            <div className="text-sm text-gray-400 mt-1">Total Orders</div>
          </div>
        </div>
      </div>

      {/* Two Column Layout */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* My Vehicles */}
        <div className="bg-white/5 rounded-xl p-4 sm:p-6 border border-white/10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">My Vehicles</h2>
            <Link to="/portal/vehicles" className="text-sm text-amber-500 hover:text-amber-400">
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

        {/* Recent Repairs */}
        <div className="bg-white/5 rounded-xl p-4 sm:p-6 border border-white/10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Recent Repairs</h2>
            <Link to="/portal/repairs" className="text-sm text-amber-500 hover:text-amber-400">
              View All
            </Link>
          </div>
          {repairOrders && repairOrders.length > 0 ? (
            <div className="space-y-2 sm:space-y-3">
              {repairOrders.slice(0, 5).map((order) => (
                <Link
                  key={order.id}
                  to="/portal/repairs"
                  state={{ selectedOrderId: order.id }}
                  className="block bg-white/5 rounded-lg p-2.5 sm:p-3 border border-white/5 hover:bg-white/10 active:bg-white/15 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                        <span className="font-medium text-white text-xs sm:text-sm">{order.order_number}</span>
                        <span className={`px-1.5 sm:px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium ${STATUS_BADGE_COLORS[order.status] || 'bg-gray-100 text-gray-700'}`}>
                          {order.status.replace('_', ' ')}
                        </span>
                        {order.status === 'invoiced' && (
                          <span className="px-1.5 sm:px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium bg-green-500 text-white">
                            Pay Now
                          </span>
                        )}
                      </div>
                      {order.description && (
                        <p className="text-gray-400 text-xs sm:text-sm truncate mt-1">{order.description}</p>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-xs sm:text-sm font-medium text-white">
                        ${getOrderTotal(order).toFixed(2)}
                      </div>
                      <div className="text-[10px] sm:text-xs text-gray-500">
                        {format(new Date(order.created_at), 'MMM d')}
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <div className="flex justify-center mb-2">
                <ClipboardList className="w-8 h-8 text-purple-300" />
              </div>
              <p className="text-gray-400">No repair history</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function CustomerVehicles() {
  const { data: vehicles, isLoading } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: async () => {
      const response = await api.get('/vehicles')
      return response.data
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

// Stripe promise cache - keyed by account (null for platform, account_id for connected)
const stripePromiseCache: Map<string | null, ReturnType<typeof loadStripe>> = new Map()

const getStripe = async (stripeAccountId?: string | null) => {
  const cacheKey = stripeAccountId || null
  
  if (!stripePromiseCache.has(cacheKey)) {
    const { data } = await api.get('/payments/config')
    const options = stripeAccountId ? { stripeAccount: stripeAccountId } : undefined
    stripePromiseCache.set(cacheKey, loadStripe(data.publishable_key, options))
  }
  return stripePromiseCache.get(cacheKey)!
}

// Payment form component
function PaymentForm({ 
  invoiceId, 
  onSuccess 
}: { 
  invoiceId: string
  onSuccess: () => void 
}) {
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
        await api.post('/payments/confirm-payment', {
          invoice_id: invoiceId,
          payment_intent_id: paymentIntent.id,
        })
        toast.success('Payment successful!')
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
        <div className="text-red-400 text-sm bg-red-500/10 p-3 rounded-lg">{error}</div>
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
  const queryClient = useQueryClient()
  const location = useLocation()
  const [selectedOrder, setSelectedOrder] = useState<RepairOrder | null>(null)
  const [showPayment, setShowPayment] = useState(false)
  const [stripeOptions, setStripeOptions] = useState<{ clientSecret: string; appearance: object } | null>(null)
  const [stripeInstance, setStripeInstance] = useState<Awaited<ReturnType<typeof loadStripe>> | null>(null)
  
  const { data: orders, isLoading } = useQuery<RepairOrder[]>({
    queryKey: ['repair-orders'],
    queryFn: async () => {
      const response = await api.get('/repair-orders')
      return response.data
    },
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

  const quotedOrders = orders?.filter((o) => o.status === 'quoted') ?? []
  const quoteQueries = useQueries({
    queries: quotedOrders.map((order) => ({
      queryKey: ['quote', order.id],
      queryFn: async () => {
        const response = await api.get(`/quotes?repair_order_id=${order.id}`)
        return response.data as Quote | null
      },
      enabled: true,
    })),
  })

  const approveQuoteMutation = useMutation({
    mutationFn: async (quoteId: string) => {
      const response = await api.post(`/quotes/${quoteId}/approve`)
      return response.data as Quote
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['quote'] })
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
      const stripe = await getStripe(data.stripe_account_id)
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  // Detail view for selected order
  if (selectedOrder) {
    const services = (() => {
      try {
        const notes = JSON.parse(selectedOrder.internal_notes || '{}')
        return notes?.selected_services || []
      } catch {
        return []
      }
    })()

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
            <p className="text-gray-400">
              {format(new Date(selectedOrder.created_at), 'MMMM d, yyyy')}
            </p>
          </div>
          <span className={`ml-auto px-3 py-1 rounded-full text-sm font-medium ${STATUS_BADGE_COLORS[selectedOrder.status] || 'bg-gray-100 text-gray-700'}`}>
            {selectedOrder.status.replace('_', ' ')}
          </span>
        </div>

        {/* Order Details */}
        <div className="bg-white/5 rounded-xl border border-white/10 p-4 sm:p-6">
          {selectedOrder.description && (
            <div className="mb-4">
              <h3 className="text-sm font-medium text-gray-400 mb-1">Description</h3>
              <p className="text-white">{selectedOrder.description}</p>
            </div>
          )}

          {services.length > 0 && (
            <div className="mb-4">
              <h3 className="text-sm font-medium text-gray-400 mb-2">Services</h3>
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

          <div className="border-t border-white/10 pt-4 mt-4">
            <div className="flex justify-between items-center text-lg">
              <span className="font-medium text-white">Total</span>
              <span className="font-bold text-white">${getOrderTotal(selectedOrder).toFixed(2)}</span>
            </div>
          </div>
        </div>

        {/* Invoice & Payment Section */}
        {selectedOrder.status === 'invoiced' && invoice && (
          <div className="bg-purple-500/10 rounded-xl border border-purple-500/30 p-4 sm:p-6">
            <div className="flex items-center gap-3 mb-4">
              <FileText className="w-6 h-6 text-purple-400" />
              <div>
                <h3 className="font-semibold text-white">Invoice {invoice.invoice_number}</h3>
                <p className="text-sm text-gray-400">Ready for payment</p>
              </div>
            </div>

            <div className="bg-white/5 rounded-lg p-4 mb-4">
              <div className="flex justify-between mb-2">
                <span className="text-gray-400">Subtotal</span>
                <span className="text-white">${parseFloat(invoice.subtotal).toFixed(2)}</span>
              </div>
              {parseFloat(invoice.tax_amount) > 0 && (
                <div className="flex justify-between mb-2">
                  <span className="text-gray-400">Tax</span>
                  <span className="text-white">${parseFloat(invoice.tax_amount).toFixed(2)}</span>
                </div>
              )}
              {parseFloat(invoice.discount_amount) > 0 && (
                <div className="flex justify-between mb-2">
                  <span className="text-gray-400">Discount</span>
                  <span className="text-green-400">-${parseFloat(invoice.discount_amount).toFixed(2)}</span>
                </div>
              )}
              <div className="flex justify-between pt-2 border-t border-white/10">
                <span className="font-semibold text-white">Total Due</span>
                <span className="font-bold text-xl text-white">${parseFloat(invoice.total_amount).toFixed(2)}</span>
              </div>
            </div>

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

        {/* Paid confirmation */}
        {selectedOrder.status === 'paid' && (
          <div className="bg-green-500/10 rounded-xl border border-green-500/30 p-4 sm:p-6">
            <div className="flex items-center gap-3">
              <CheckCircle className="w-8 h-8 text-green-400" />
              <div>
                <h3 className="font-semibold text-white">Payment Complete</h3>
                <p className="text-sm text-gray-400">
                  Thank you for your payment{invoice?.paid_at ? ` on ${format(new Date(invoice.paid_at), 'MMM d, yyyy')}` : ''}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  // List view
  const invoicedOrders = orders?.filter((o) => o.status === 'invoiced') ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Repair History</h1>
        <p className="text-gray-400 mt-1">Track all your past and current repairs</p>
      </div>

      {/* Invoices awaiting payment - prominent */}
      {invoicedOrders.length > 0 && (
        <div className="bg-purple-500/10 rounded-xl border border-purple-500/30 p-4 sm:p-6">
          <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
            <CreditCard className="w-5 h-5 text-purple-400" />
            Invoices Ready for Payment
          </h2>
          <div className="space-y-3">
            {invoicedOrders.map((order) => (
              <button
                key={order.id}
                onClick={() => setSelectedOrder(order)}
                className="w-full bg-white/5 rounded-lg p-3 sm:p-4 border border-white/10 hover:bg-white/10 transition-colors text-left"
              >
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-3">
                  <div className="min-w-0">
                    <span className="font-medium text-white">{order.order_number}</span>
                    <span className="text-gray-400 ml-2 hidden sm:inline">— {order.description || 'Repair'}</span>
                    {order.description && (
                      <p className="text-gray-400 text-sm truncate sm:hidden">{order.description}</p>
                    )}
                  </div>
                  <div className="flex items-center justify-between sm:justify-end gap-3">
                    <span className="font-bold text-white text-lg">${getOrderTotal(order).toFixed(2)}</span>
                    <span className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg whitespace-nowrap">
                      Pay Now
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Quotes pending approval */}
      {quotedOrders.length > 0 && (
        <div className="bg-amber-500/10 rounded-xl border border-amber-500/30 p-4 sm:p-6">
          <h2 className="text-lg font-semibold text-white mb-3">Quotes pending your approval</h2>
          <div className="space-y-3">
            {quotedOrders.map((order, idx) => {
              const quoteData = quoteQueries[idx]?.data as Quote | null | undefined
              const quoteLoading = quoteQueries[idx]?.isLoading
              return (
                <div key={order.id} className="bg-white/5 rounded-lg p-3 sm:p-4 border border-white/10 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <span className="font-medium text-white">{order.order_number}</span>
                    <span className="text-gray-400 ml-2">— {order.description || 'Repair'}</span>
                    {quoteData && (
                      <p className="text-sm text-gray-400 mt-1">
                        Quote #{quoteData.quote_number} · ${parseFloat(quoteData.total_amount).toFixed(2)}
                      </p>
                    )}
                  </div>
                  {quoteLoading ? (
                    <span className="text-gray-500 text-sm">Loading quote...</span>
                  ) : quoteData && !quoteData.is_approved ? (
                    <button
                      type="button"
                      onClick={() => approveQuoteMutation.mutate(quoteData.id)}
                      disabled={approveQuoteMutation.isPending}
                      className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-500 text-white text-sm font-medium rounded-lg"
                    >
                      {approveQuoteMutation.isPending ? 'Approving...' : 'Approve quote'}
                    </button>
                  ) : quoteData?.is_approved ? (
                    <span className="text-green-400 text-sm font-medium">Approved</span>
                  ) : null}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* All orders list */}
      <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
        {orders && orders.length > 0 ? (
          <div className="divide-y divide-white/5">
            {orders.map((order) => (
              <button
                key={order.id}
                onClick={() => setSelectedOrder(order)}
                className="w-full p-3 sm:p-6 hover:bg-white/5 active:bg-white/10 transition-colors text-left"
              >
                <div className="flex items-start justify-between gap-3 sm:gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
                      <h3 className="font-semibold text-white text-sm sm:text-base">{order.order_number}</h3>
                      <span className={`px-2 sm:px-2.5 py-0.5 sm:py-1 rounded-full text-[10px] sm:text-xs font-medium ${STATUS_BADGE_COLORS[order.status] || 'bg-gray-100 text-gray-700'}`}>
                        {order.status.replace('_', ' ')}
                      </span>
                    </div>
                    {order.description && (
                      <p className="text-gray-400 text-sm mt-1.5 sm:mt-2 line-clamp-2">{order.description}</p>
                    )}
                    <p className="text-xs sm:text-sm text-gray-500 mt-1.5 sm:mt-2">
                      {format(new Date(order.created_at), 'MMM d, yyyy')}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-lg sm:text-xl font-bold text-white">
                      ${getOrderTotal(order).toFixed(2)}
                    </div>
                    <div className="text-[10px] sm:text-xs text-gray-500 mt-0.5 sm:mt-1">Total</div>
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
            <p className="text-gray-400">No repair history yet</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default function CustomerPortalPage() {
  const location = useLocation()

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
    if (location.pathname === '/portal/settings') return 'Profile Settings'
    const current = navLinks.find(link => location.pathname === link.to)
    return current?.label || ''
  }

  return (
    <div className="min-h-screen">
      <nav className="bg-white/90 backdrop-blur shadow-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex justify-between h-14 sm:h-16">
            {/* Logo */}
            <div className="flex items-center">
              <Link to="/portal" className="relative text-lg sm:text-xl font-bold text-slate-800 py-1">
                <svg className="absolute inset-0 w-full h-full opacity-15" viewBox="0 0 100 32" preserveAspectRatio="none" fill="none">
                  <style>{`
                    @keyframes checker { 0%, 100% { fill: #1e293b } 50% { fill: #f59e0b } }
                    @keyframes checkerAlt { 0%, 100% { fill: #f59e0b } 50% { fill: #1e293b } }
                    .t1 { animation: checker 2.5s ease-in-out infinite }
                    .t2 { animation: checkerAlt 2.5s ease-in-out infinite }
                    .b1 { animation: checker 2.5s ease-in-out infinite; animation-delay: -0.8s }
                    .b2 { animation: checkerAlt 2.5s ease-in-out infinite; animation-delay: -0.8s }
                  `}</style>
                  <rect x="50" y="0" width="12.5" height="4" className="t1"/>
                  <rect x="62.5" y="0" width="12.5" height="4" className="t2"/>
                  <rect x="75" y="0" width="12.5" height="4" className="t1"/>
                  <rect x="87.5" y="0" width="12.5" height="4" className="t2"/>
                  <rect x="0" y="28" width="12.5" height="4" className="b2"/>
                  <rect x="12.5" y="28" width="12.5" height="4" className="b1"/>
                  <rect x="25" y="28" width="12.5" height="4" className="b2"/>
                  <rect x="37.5" y="28" width="12.5" height="4" className="b1"/>
                </svg>
                <span className="relative px-1">Truck Pit Stop</span>
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
                      ? 'text-amber-600 border-b-2 border-amber-500'
                      : 'text-gray-600 hover:text-amber-600'
                  }`}
                >
                  {link.label}
                </Link>
              ))}
              <Link
                to="/portal/settings"
                className={`relative p-2.5 rounded-full transition-colors ${
                  location.pathname === '/portal/settings'
                    ? 'bg-amber-100 text-amber-600'
                    : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
                }`}
                title="Profile Settings"
              >
                <svg className="absolute inset-0 w-full h-full" viewBox="0 0 40 40">
                  <style>{`
                    @keyframes ps1 { 0%, 100% { stroke: #1e293b } 50% { stroke: #f59e0b } }
                    @keyframes ps2 { 0%, 100% { stroke: #f59e0b } 50% { stroke: #1e293b } }
                    .ps1 { animation: ps1 2.5s ease-in-out infinite }
                    .ps2 { animation: ps2 2.5s ease-in-out infinite }
                  `}</style>
                  {[...Array(8)].map((_, i) => {
                    const startAngle = i * 45 - 90
                    const endAngle = startAngle + 45
                    const r = 17
                    const x1 = 20 + r * Math.cos(startAngle * Math.PI / 180)
                    const y1 = 20 + r * Math.sin(startAngle * Math.PI / 180)
                    const x2 = 20 + r * Math.cos(endAngle * Math.PI / 180)
                    const y2 = 20 + r * Math.sin(endAngle * Math.PI / 180)
                    return (
                      <path
                        key={i}
                        d={`M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`}
                        fill="none"
                        strokeWidth="3"
                        strokeLinecap="round"
                        className={i % 2 === 0 ? 'ps1' : 'ps2'}
                      />
                    )
                  })}
                </svg>
                <svg className="w-5 h-5 relative" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </Link>
            </div>
          </div>
        </div>
      </nav>

      <main className="px-4 py-4 sm:py-6 max-w-7xl mx-auto pb-20 md:pb-6">
        {/* Breadcrumb - only show on sub-pages */}
        {isOnSubPage && (
          <div className="mb-4 flex items-center gap-2 text-sm">
            <Link 
              to="/portal" 
              className="text-gray-400 hover:text-amber-500 transition-colors flex items-center gap-1"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Dashboard
            </Link>
            <span className="text-gray-600">/</span>
            <span className="text-white font-medium">{getCurrentPageLabel()}</span>
          </div>
        )}
        <Routes>
          <Route path="" element={<CustomerDashboard />} />
          <Route path="services" element={<ServicesPage />} />
          <Route path="book/:serviceId" element={<BookingPage />} />
          <Route path="appointments" element={<AppointmentsPage />} />
          <Route path="vehicles" element={<CustomerVehicles />} />
          <Route path="repairs" element={<CustomerRepairs />} />
          <Route path="settings" element={<ProfileSettingsPage />} />
        </Routes>
      </main>

      {/* Mobile Bottom Navigation */}
      <div className="fixed bottom-0 left-0 right-0 z-50 md:hidden">
        <div className="bg-white/95 backdrop-blur border-t border-gray-200 px-2 py-2 flex justify-around">
          <Link
            to="/portal"
            className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
              location.pathname === '/portal'
                ? 'text-amber-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <Home className="w-5 h-5" />
            <span className="text-[10px] font-medium">Home</span>
          </Link>
          <Link
            to="/portal/services"
            className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
              location.pathname === '/portal/services' || location.pathname.startsWith('/portal/book/')
                ? 'text-amber-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <Wrench className="w-5 h-5" />
            <span className="text-[10px] font-medium">Services</span>
          </Link>
          <Link
            to="/portal/appointments"
            className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
              location.pathname === '/portal/appointments'
                ? 'text-amber-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <Calendar className="w-5 h-5" />
            <span className="text-[10px] font-medium">Appts</span>
          </Link>
          <Link
            to="/portal/vehicles"
            className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
              location.pathname === '/portal/vehicles'
                ? 'text-amber-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <Truck className="w-5 h-5" />
            <span className="text-[10px] font-medium">Vehicles</span>
          </Link>
          <Link
            to="/portal/repairs"
            className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
              location.pathname === '/portal/repairs'
                ? 'text-amber-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <History className="w-5 h-5" />
            <span className="text-[10px] font-medium">History</span>
          </Link>
          <Link
            to="/portal/settings"
            className={`flex flex-col items-center gap-0.5 min-w-0 px-1 ${
              location.pathname === '/portal/settings'
                ? 'text-amber-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <User className="w-5 h-5" />
            <span className="text-[10px] font-medium">Profile</span>
          </Link>
        </div>
      </div>
    </div>
  )
}
