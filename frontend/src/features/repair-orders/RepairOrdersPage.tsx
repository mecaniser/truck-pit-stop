import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { Customer, RepairOrder, RepairOrderDetail, Service, Vehicle, PartsUsage, Labor, InventoryItem, Quote } from '../../types'
import { format } from 'date-fns'
import { ArrowRight, Plus, TriangleAlert, Trash2, OctagonX, Wrench, ChevronDown, ChevronUp, Pencil } from 'lucide-react'
import SlidePanel from '@/components/SlidePanel'
import YearPicker from '../../components/YearPicker'
import VehicleMakePicker from '../../components/VehicleMakePicker'
import CustomerSelect from '../../components/CustomerSelect'
import { formatUSPhone } from '@/utils/phone'
import BaseSelect from '../../components/BaseSelect'
import ViewToggle from '@/components/ViewToggle'
import { useViewPreference } from '@/hooks/useViewPreference'
import { useTheme } from '../../contexts/ThemeContext'
import { useWebSocket } from '../../hooks/useWebSocket'
import { useNotificationManager } from '../../hooks/useNotificationManager'
import NotificationBanner from '../../components/NotificationBanner'

interface NewCustomerForm {
  first_name: string
  last_name: string
  email: string
  phone: string
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

export default function RepairOrdersPage() {
  const { accentColors } = useTheme()
  const [searchParams, setSearchParams] = useSearchParams()
  
  // Notification manager for queued, deduplicated notifications
  const { notify, banners, dismissBanner, clearBanners } = useNotificationManager()
  
  // Connect to WebSocket for real-time updates
  useWebSocket({ onNotification: notify })
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('')
  const [selectedVehicleId, setSelectedVehicleId] = useState<string>('')
  const [showNewVehicleForm, setShowNewVehicleForm] = useState(false)
  const [description, setDescription] = useState('')
  const [serviceSearch, setServiceSearch] = useState('')
  const [selectedServiceIds, setSelectedServiceIds] = useState<string[]>([])
  const [isDetailOpen, setIsDetailOpen] = useState(false)
  const [selectedOrder, setSelectedOrder] = useState<RepairOrder | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showDangerActions, setShowDangerActions] = useState(false)
  const [viewMode, setViewMode] = useViewPreference('repair_orders')
  const [isMobile, setIsMobile] = useState(false)
  const [newCustomer, setNewCustomer] = useState<NewCustomerForm>({
    first_name: '',
    last_name: '',
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
  const [isEditingLaborRate, setIsEditingLaborRate] = useState(false)
  const [customerSectionExpanded, setCustomerSectionExpanded] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showResendInvoice, setShowResendInvoice] = useState(false)
  const [resendCustomEmail, setResendCustomEmail] = useState('')
  const [showDeleteInvoiceConfirm, setShowDeleteInvoiceConfirm] = useState(false)
  const [showReassignMechanic, setShowReassignMechanic] = useState(false)
  const [reviewNotes, setReviewNotes] = useState('')
  const [showReviewNotes, setShowReviewNotes] = useState(false)
  const [invoiceDueDate, setInvoiceDueDate] = useState('')
  const [showInvoicePaymentOptions, setShowInvoicePaymentOptions] = useState(false)
  const [selectedPaymentMethod, setSelectedPaymentMethod] = useState<string>('')
  const [showZelleQrModal, setShowZelleQrModal] = useState(false)

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 1024)
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  const activeViewMode = isMobile ? 'list' : viewMode

  const queryClient = useQueryClient()

  const { data: orders, isLoading } = useQuery<RepairOrder[]>({
    queryKey: ['repair-orders'],
    queryFn: async () => {
      const response = await api.get('/repair-orders')
      return response.data
    },
  })

  // Handle ?selected= query param to auto-open a repair order
  useEffect(() => {
    const selectedId = searchParams.get('selected')
    if (selectedId && orders) {
      const order = orders.find(o => o.id === selectedId)
      if (order) {
        setSelectedOrder(order)
        setIsDetailOpen(true)
        // Clear the query param after opening
        setSearchParams({}, { replace: true })
      }
    }
  }, [searchParams, orders, setSearchParams])

  // Handle ?new=true query param to auto-open create modal
  useEffect(() => {
    const newParam = searchParams.get('new')
    if (newParam === 'true') {
      setIsModalOpen(true)
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])

  const { data: customers } = useQuery<Customer[]>({
    queryKey: ['customers'],
    queryFn: async () => {
      const response = await api.get('/customers')
      return response.data
    },
  })

  const { data: vehicles } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: async () => {
      const response = await api.get('/vehicles')
      return response.data
    },
  })

  const { data: services } = useQuery<Service[]>({
    queryKey: ['services'],
    queryFn: async () => {
      const response = await api.get('/services')
      return response.data
    },
  })

  const { data: mechanics } = useQuery<{ mechanic_id: string; mechanic_name: string; assigned_count?: number; in_progress_count?: number }[]>({
    queryKey: ['mechanics'],
    queryFn: async () => {
      const response = await api.get('/dashboard/stats')
      return response.data?.mechanic_workload || []
    },
  })

  const { data: orderDetail, refetch: refetchOrderDetail } = useQuery<RepairOrderDetail>({
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
      const response = await api.get('/inventory')
      return response.data
    },
    enabled: isDetailOpen,
  })

  const { data: quoteForOrder, refetch: refetchQuote } = useQuery<Quote | null>({
    queryKey: ['quote', selectedOrder?.id],
    queryFn: async () => {
      const response = await api.get(`/quotes?repair_order_id=${selectedOrder!.id}`)
      return response.data
    },
    enabled: !!(selectedOrder?.id && isDetailOpen),
  })

  const { data: invoiceForOrder } = useQuery<{ id: string; invoice_number: string; total_amount: string; due_date: string | null } | null>({
    queryKey: ['invoice-for-order', selectedOrder?.id],
    queryFn: async () => {
      const response = await api.get(`/invoices?repair_order_id=${selectedOrder!.id}`)
      const invoices = response.data
      return invoices.length > 0 ? invoices[0] : null
    },
    enabled: !!(selectedOrder?.id && isDetailOpen && ['invoiced', 'paid'].includes(selectedOrder?.status || '')),
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

  const filteredVehicles = useMemo(() => {
    if (!vehicles) return []
    if (selectedCustomerId) {
      return vehicles.filter((v) => v.customer_id === selectedCustomerId)
    }
    return []
  }, [vehicles, selectedCustomerId])

  const customerLookup = useMemo(() => {
    const map = new Map<string, Customer>()
    customers?.forEach((c) => map.set(c.id, c))
    return map
  }, [customers])

  const vehicleLookup = useMemo(() => {
    const map = new Map<string, Vehicle>()
    vehicles?.forEach((v) => map.set(v.id, v))
    return map
  }, [vehicles])

  const mechanicLookup = useMemo(() => {
    const map = new Map<string, string>()
    mechanics?.forEach((m) => map.set(m.mechanic_id, m.mechanic_name))
    return map
  }, [mechanics])

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

  const createCustomerMutation = useMutation({
    mutationFn: async (payload: NewCustomerForm) => {
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
    }: { customer_id: string; vehicle_id: string; description: string; internal_notes?: string | null }) => {
      const response = await api.post('/repair-orders', {
        customer_id,
        vehicle_id,
        description: roDescription || null,
        internal_notes: internal_notes || null,
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

  const deleteRepairOrderMutation = useMutation({
    mutationFn: async (orderId: string) => {
      await api.delete(`/repair-orders/${orderId}`)
      return orderId
    },
    onSuccess: (orderId) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      if (selectedOrder?.id === orderId) {
        closeDetail()
      }
      toast.success('Repair order deleted')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to delete repair order'))
    },
  })

  const assignMechanicMutation = useMutation({
    mutationFn: async ({ orderId, mechanicId, orderStatus }: { orderId: string; mechanicId: string; orderStatus?: string }) => {
      // Use dedicated assign-mechanic endpoint for approved orders (sends email notification)
      if (orderStatus === 'approved' && mechanicId) {
        const response = await api.post(`/repair-orders/${orderId}/assign-mechanic`, { mechanic_id: mechanicId })
        return response.data as RepairOrder
      }
      // Fallback to generic update for other cases
      const response = await api.put(`/repair-orders/${orderId}`, { assigned_mechanic_id: mechanicId || null })
      return response.data as RepairOrder
    },
    onSuccess: (updated, variables) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.id] })
      queryClient.invalidateQueries({ queryKey: ['customerRepairOrders'] })
      setSelectedOrder(updated)
      // Show different message for first assignment vs reassignment
      const wasApproved = variables.orderStatus === 'approved'
      toast.success(wasApproved ? 'Mechanic assigned - Customer notified' : 'Mechanic reassigned')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to assign mechanic'))
    },
  })

  const approveCompletionMutation = useMutation({
    mutationFn: async ({ orderId, reviewNotes }: { orderId: string; reviewNotes?: string }) => {
      const response = await api.post(`/repair-orders/${orderId}/approve-completion`, {
        review_notes: reviewNotes || null,
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
    mutationFn: async ({ repairOrderId, dueDate }: { repairOrderId: string; dueDate?: string }) => {
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
      toast.success('Invoice created and sent to customer')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to create invoice'))
    },
  })

  const recordManualPaymentMutation = useMutation({
    mutationFn: async ({ invoiceId, method, notes }: { invoiceId: string; method: string; notes?: string }) => {
      const response = await api.post('/payments/record-manual', { 
        invoice_id: invoiceId,
        method,
        notes,
      })
      return response.data
    },
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      if (selectedOrder?.id) {
        queryClient.invalidateQueries({ queryKey: ['repair-order-detail', selectedOrder.id] })
        setSelectedOrder(prev => prev ? { ...prev, status: 'paid' } : null)
      }
      setShowInvoicePaymentOptions(false)
      setSelectedPaymentMethod('')
      toast.success('Payment recorded successfully')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to record payment'))
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
      setQuoteNeedsUpdate(true)
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
      setQuoteNeedsUpdate(true)
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
      setQuoteNeedsUpdate(true)
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
      setQuoteNeedsUpdate(true)
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
      setQuoteNeedsUpdate(true)
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
      setQuoteNeedsUpdate(false)
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
      toast.success('Quote sent — Awaiting customer approval')
    },
    onError: (error: unknown) => {
      toast.error(getErrorDetail(error, 'Failed to send quote'))
    },
  })

  const [quoteSent, setQuoteSent] = useState(false)
  const [quoteNeedsUpdate, setQuoteNeedsUpdate] = useState(false)

  const filteredOrders = useMemo(() => {
    if (!orders) return orders

    let filtered = orders

    // Filter by status
    if (statusFilter !== 'all') {
      filtered = filtered.filter((order) => order.status === statusFilter)
    }

    // Filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim()
      filtered = filtered.filter((order) => 
        order.order_number.toLowerCase().includes(query) ||
        order.description?.toLowerCase().includes(query)
      )
    }

    return filtered
  }, [orders, searchQuery, statusFilter])

  if (isLoading) {
    return <div className="text-white">Loading...</div>
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
      pending_review: { bg: 'bg-orange-100', text: 'text-orange-700', dot: 'bg-orange-500' },
      completed: { bg: 'bg-purple-100', text: 'text-purple-700', dot: 'bg-purple-500' },
      invoiced: { bg: 'bg-indigo-100', text: 'text-indigo-700', dot: 'bg-indigo-500' },
      paid: { bg: 'bg-emerald-100', text: 'text-emerald-700', dot: 'bg-emerald-500' },
      cancelled: { bg: 'bg-red-100', text: 'text-red-700', dot: 'bg-red-500' },
    }
    return styles[status] || styles.draft
  }

  const statusOptions = [
    { value: 'all', label: 'All' },
    { value: 'in_progress', label: 'In Progress' },
    { value: 'quoted', label: 'Quoted' },
    { value: 'declined', label: 'Declined' },
    { value: 'approved', label: 'Approved' },
    { value: 'completed', label: 'Completed' },
    { value: 'paid', label: 'Paid' },
  ]

  const resetModal = () => {
    setSelectedCustomerId('')
    setSelectedVehicleId('')
    setShowNewVehicleForm(false)
    setDescription('')
    setServiceSearch('')
    setSelectedServiceIds([])
    setNewCustomer({ first_name: '', last_name: '', email: '', phone: '' })
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

  const openDetail = (order: RepairOrder) => {
    setSelectedOrder(order)
    setIsDetailOpen(true)
    setQuoteSent(false)
    setShowReassignMechanic(false)
    setReviewNotes('')
    setShowReviewNotes(false)
    setQuoteNeedsUpdate(false)
    setShowDangerActions(false)
  }

  const closeDetail = () => {
    setSelectedOrder(null)
    setIsDetailOpen(false)
    setQuoteSent(false)
    setQuoteNeedsUpdate(false)
    setShowDangerActions(false)
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
          base_price: svc.base_price,
        })) || []

      const internalNotes = selectedServicePayload.length
        ? JSON.stringify({ selected_services: selectedServicePayload })
        : null

      const combinedDescription = [selectedServiceText, description.trim()].filter(Boolean).join(' — ')

      const createdOrder = await createRepairOrderMutation.mutateAsync({
        customer_id: finalCustomerId,
        vehicle_id: finalVehicleId,
        description: combinedDescription,
        internal_notes: internalNotes,
      })

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
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 sm:mb-6">
        <h1 className="text-xl sm:text-2xl font-bold text-white">Repair Orders</h1>
        <button 
          onClick={openModal}
          className="mt-3 sm:mt-0 px-4 py-2 text-white font-medium rounded-lg transition-colors"
          style={{ backgroundColor: accentColors[500] }}
        >
          + New Repair Order
        </button>
      </div>

      {/* Real-time notification banners */}
      <NotificationBanner
        banners={banners}
        onDismiss={dismissBanner}
        onDismissAll={clearBanners}
        autoDismissMs={10000}
      />

      {/* Search Bar */}
      <div className="mb-6 bg-white/10 backdrop-blur rounded-xl p-4">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex-1 relative">
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

          <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
            <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
              {statusOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setStatusFilter(option.value)}
                  className={`h-10 px-3 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
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
          </div>
        </div>

        {(searchQuery || statusFilter !== 'all') && (
          <div className="mt-3 text-sm text-white/70">
            Found {filteredOrders?.length || 0} order{filteredOrders?.length !== 1 ? 's' : ''}
          </div>
        )}
      </div>

      <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        {/* Header with ViewToggle */}
        <div className="hidden lg:flex items-center justify-start px-4 py-3 border-b border-white/10">
          <ViewToggle value={activeViewMode} onChange={setViewMode} disabled={isMobile} />
        </div>

        <div className="overflow-y-auto max-h-[calc(100vh-280px)]">
          {activeViewMode === 'list' ? (
            /* List View */
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
                    const isAwaitingApproval = order.status === 'quoted' && order.quote_sent
                    const statusStyle = isAwaitingApproval 
                      ? { bg: 'bg-amber-100', text: 'text-amber-700', dot: 'bg-amber-500' }
                      : getStatusStyle(order.status)
                    const displayStatus = isAwaitingApproval ? 'Awaiting Approval' : order.status.replace('_', ' ')
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
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${statusStyle.bg} ${statusStyle.text}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${statusStyle.dot}`}></span>
                            {displayStatus}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-white/70 hidden sm:table-cell max-w-xs truncate">
                          {order.description || '—'}
                        </td>
                        <td className="px-4 py-3 text-white/70 hidden md:table-cell">
                          {customer ? `${customer.first_name} ${customer.last_name}` : '—'}
                        </td>
                        <td className="px-4 py-3 text-white/70 hidden lg:table-cell">
                          {vehicle ? `${vehicle.year || ''} ${vehicle.make} ${vehicle.model}`.trim() : '—'}
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
                const isAwaitingApproval = order.status === 'quoted' && order.quote_sent
                const statusStyle = isAwaitingApproval 
                  ? { bg: 'bg-amber-100', text: 'text-amber-700', dot: 'bg-amber-500' }
                  : getStatusStyle(order.status)
                const displayStatus = isAwaitingApproval ? 'Awaiting Approval' : order.status.replace('_', ' ')
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
                        <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${statusStyle.bg} ${statusStyle.text}`}>
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
                            <span>{mechanicLookup.get(order.assigned_mechanic_id!) || 'Assigned mechanic'}</span>
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
                                  <div className="text-sm font-semibold text-slate-900">{vehicle.make} {vehicle.model}</div>
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
                        <label className="block text-sm font-medium text-gray-700 mb-1">Last Name / Company</label>
                        <input
                          name="last_name"
                          value={newCustomer.last_name}
                          onChange={(e) => setNewCustomer((prev) => ({ ...prev, last_name: e.target.value }))}
                          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                          placeholder="Logistics"
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
                      <input
                        type="text"
                        value={serviceSearch}
                        onChange={(e) => setServiceSearch(e.target.value)}
                        placeholder="Search services (e.g., oil change, brake, diagnostics)"
                        className="w-full pl-10 pr-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors text-gray-900 placeholder-gray-400"
                      />
                      <svg 
                        className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400"
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
                              return (
                                <button
                                  key={svc.id}
                                  type="button"
                                  onClick={() =>
                                    setSelectedServiceIds((prev) =>
                                      prev.includes(svc.id) ? prev.filter((id) => id !== svc.id) : [...prev, svc.id]
                                    )
                                  }
                                  className={`px-3 py-2 rounded-full text-sm font-medium border transition-colors ${
                                    active
                                      ? 'border-amber-500 bg-amber-50 text-amber-700'
                                      : 'border-gray-200 bg-white hover:border-amber-300 text-gray-700'
                                  }`}
                                >
                                  {svc.name}
                                </button>
                              )
                        })}

                      {services && services.length === 0 && (
                        <span className="text-sm text-gray-500">No services available yet</span>
                      )}
                    </div>

                    {selectedServiceIds.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {services
                          ?.filter((svc) => selectedServiceIds.includes(svc.id))
                          .map((svc) => (
                            <span
                              key={svc.id}
                              className="inline-flex items-center gap-1 text-xs bg-amber-100 text-amber-800 px-2 py-1 rounded-full"
                            >
                              {svc.name}
                              <button
                                type="button"
                                onClick={() =>
                                  setSelectedServiceIds((prev) => prev.filter((id) => id !== svc.id))
                                }
                                className="text-amber-700 hover:text-amber-900"
                                aria-label={`Remove ${svc.name}`}
                              >
                                ×
                              </button>
                            </span>
                          ))}
                      </div>
                    )}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Description / Work requested</label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                    className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors resize-none"
                    placeholder="Briefly describe the repair work or concern..."
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
        width="max-w-2xl"
        headerExtra={
          selectedOrder && (() => {
            const status = (orderDetail ?? selectedOrder).status
            const isAwaitingApproval = status === 'quoted' && (quoteForOrder?.sent_to_customer || quoteSent)
            const displayStatus = isAwaitingApproval ? 'Awaiting Approval' : status.replace('_', ' ')
            const statusStyle = isAwaitingApproval 
              ? { dot: 'bg-amber-500' } 
              : getStatusStyle(status)
            return (
              <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium whitespace-nowrap ${isAwaitingApproval ? 'bg-amber-500/30' : 'bg-white/20'}`}>
                <span className={`w-2 h-2 rounded-full ${statusStyle.dot}`}></span>
                {displayStatus}
              </div>
            )
          })()
        }
        footer={
          selectedOrder && (
            <div className="space-y-4 -mx-6 -my-4 px-6 py-6 bg-red-50">
              <button
                type="button"
                onClick={() => setShowDangerActions((prev) => !prev)}
                className="w-full flex items-center justify-between text-left"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-red-100 text-red-700">
                    <TriangleAlert className="w-5 h-5" />
                  </div>
                  <div className="text-sm font-semibold text-red-700 uppercase tracking-wide">
                    Danger Zone
                  </div>
                </div>
                <div className="p-2 text-red-700">
                  {showDangerActions ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </div>
              </button>
              {showDangerActions && (
                <div className="flex flex-wrap gap-2 justify-end">
                  <div className="w-full text-sm text-red-600">
                    Cancel stops work without deleting history. Delete will permanently remove this order.
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
              )}
            </div>
          )
        }
      >
        {selectedOrder && (
          <div className="p-6 space-y-6">
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
                      { id: svc.id, name: svc.name, base_price: svc.base_price },
                    ]
                    updateServicesMutation.mutate({ orderId: selectedOrder.id, selectedServices: newServices })
                  }

                  const handleRemoveService = (serviceId: string) => {
                    if (!selectedOrder.id) return
                    const newServices = detailServices.filter((s) => s.id !== serviceId)
                    updateServicesMutation.mutate({ orderId: selectedOrder.id, selectedServices: newServices })
                  }

                  return (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">Services</h3>
                      {detailServices.length > 0 && (
                        <p className="text-xs text-gray-500 mb-3">Price includes parts and labor</p>
                      )}
                      <div className="bg-gray-50 rounded-xl p-4 space-y-2 text-sm text-gray-800">
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
                                subLabel: `$${parseFloat(s.base_price).toLocaleString('en-US', { minimumFractionDigits: 2 })}`,
                              }))}
                              value=""
                              onChange={handleAddService}
                              placeholder="Add service..."
                              allowAddNew={false}
                            />
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })()}

                {/* Parts and labor: use detail when available */}
                {(() => {
                  const displayOrder = orderDetail ?? selectedOrder
                  const partsUsage = orderDetail?.parts_usage ?? []
                  const laborItems = orderDetail?.labor_items ?? []
                  const canEditLineItems = displayOrder && ['draft', 'quoted'].includes(displayOrder.status)
                  const hasSelectedServices = !!parseServiceNotes(selectedOrder?.internal_notes)?.length
                  return (
                    <>
                      <div>
                        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">Parts</h3>
                        <div className="bg-gray-50 rounded-xl p-4">
                          {partsUsage.length > 0 && (
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
                            <div className="flex items-center gap-2">
                              <div className="min-w-[200px] flex-1 max-w-xs">
                                <BaseSelect
                                  options={inventory
                                    .filter((i) => i.stock_quantity > 0)
                                    .map((i) => ({
                                      value: i.id,
                                      label: i.name,
                                      subLabel: `${i.sku} — ${i.stock_quantity} in stock`,
                                    }))}
                                  value={addPartInventoryId}
                                  onChange={setAddPartInventoryId}
                                  placeholder="Select part"
                                  allowAddNew={false}
                                />
                              </div>
                              <input
                                type="number"
                                min={1}
                                value={addPartQuantity}
                                onChange={(e) => setAddPartQuantity(Math.max(1, parseInt(e.target.value, 10) || 1))}
                                className="h-[42px] rounded-lg border border-gray-300 px-3 text-sm w-20"
                              />
                              <button
                                type="button"
                                disabled={!addPartInventoryId || addPartMutation.isPending}
                                onClick={() => {
                                  if (!selectedOrder?.id || !addPartInventoryId) return
                                  addPartMutation.mutate({ orderId: selectedOrder.id, inventory_id: addPartInventoryId, quantity: addPartQuantity })
                                  setAddPartInventoryId('')
                                  setAddPartQuantity(1)
                                }}
                                className="h-[42px] px-3 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 text-white text-sm font-medium rounded-lg"
                              >
                                Add
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                      {/* Labor/Services section */}
                      <div>
                        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
                          {hasSelectedServices ? 'Services (Labor)' : 'Labor'}
                        </h3>
                        <div className="bg-gray-50 rounded-xl p-4">
                          {/* Show services if selected */}
                          {hasSelectedServices && (() => {
                            const services = parseServiceNotes(selectedOrder?.internal_notes) || []
                            return (
                              <div className="space-y-2">
                                {services.map((svc, idx) => (
                                  <div key={idx} className="flex items-center justify-between text-sm text-gray-800">
                                    <span className="font-medium">{svc.name}</span>
                                    <span className="font-semibold">${parseFloat(svc.base_price || '0').toFixed(2)}</span>
                                  </div>
                                ))}
                              </div>
                            )
                          })()}
                          {/* Show manual labor items if no services */}
                          {!hasSelectedServices && (
                            <>
                              {laborItems.length > 0 && (
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
                                    {isEditingLaborRate ? (
                                      <input
                                        type="number"
                                        step={0.01}
                                        min={0}
                                        autoFocus
                                        value={addLaborRate}
                                        onChange={(e) => setAddLaborRate(e.target.value)}
                                        onBlur={() => setIsEditingLaborRate(false)}
                                        onKeyDown={(e) => e.key === 'Enter' && setIsEditingLaborRate(false)}
                                        className="rounded-lg border border-gray-300 px-3 py-2 text-sm w-24"
                                      />
                                    ) : (
                                      <button
                                        type="button"
                                        onClick={() => setIsEditingLaborRate(true)}
                                        className="inline-flex items-center gap-1 text-sm text-gray-700 hover:text-gray-900"
                                      >
                                        <span className="font-medium">${addLaborRate}/hr</span>
                                        <Pencil className="w-3 h-3 text-gray-400" />
                                      </button>
                                    )}
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
                                        setIsEditingLaborRate(false)
                                      }}
                                      className="px-3 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 text-white text-sm font-medium rounded-lg"
                                    >
                                      Add
                                    </button>
                                  </div>
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      </div>
                    </>
                  )
                })()}


                {/* Approve Completion Button for pending_review status */}
                {(orderDetail ?? selectedOrder).status === 'pending_review' && (
                  <div className="bg-orange-50 border border-orange-200 rounded-xl p-4">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-10 h-10 bg-orange-100 rounded-full flex items-center justify-center">
                        <svg className="w-5 h-5 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </div>
                      <div>
                        <p className="font-semibold text-orange-900">Mechanic Completed Work</p>
                        <p className="text-sm text-orange-700">Review and approve to notify customer</p>
                      </div>
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
                          approveCompletionMutation.mutate({ orderId: selectedOrder.id, reviewNotes: reviewNotes || undefined })
                          setReviewNotes('')
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

                {/* Create Invoice Button for completed orders */}
                {(orderDetail ?? selectedOrder).status === 'completed' && (
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
                    <div className="mb-3">
                      <label className="block text-sm font-medium text-indigo-700 mb-1">Due Date (optional)</label>
                      <input
                        type="date"
                        value={invoiceDueDate}
                        onChange={(e) => setInvoiceDueDate(e.target.value)}
                        min={new Date().toISOString().split('T')[0]}
                        className="w-full px-3 py-2 border border-indigo-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                      />
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
                {(orderDetail ?? selectedOrder).status === 'invoiced' && invoiceForOrder && (
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
                                  setShowZelleQrModal(true)
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
                            disabled={!selectedPaymentMethod || recordManualPaymentMutation.isPending}
                            className="flex-1 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                          >
                            {recordManualPaymentMutation.isPending ? (
                              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                              </svg>
                            ) : (
                              'Mark as Paid'
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
                {(orderDetail ?? selectedOrder).status === 'paid' && invoiceForOrder && (
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

                <div>
                  <button
                    type="button"
                    onClick={() => setCustomerSectionExpanded((prev) => !prev)}
                    className="w-full flex items-center justify-between text-left bg-gray-50 rounded-xl p-3 hover:bg-gray-100 transition-colors"
                  >
                    <span className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Customer & Vehicle</span>
                    <div className="flex items-center gap-2">
                      <span className="text-gray-900 font-medium truncate max-w-[200px]">
                        {customerLookup.get(selectedOrder.customer_id)
                          ? `${customerLookup.get(selectedOrder.customer_id)?.first_name} ${customerLookup.get(selectedOrder.customer_id)?.last_name}`
                          : 'Unknown'}
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
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center text-amber-700 font-bold">
                          {(customerLookup.get(selectedOrder.customer_id)?.first_name || 'C').charAt(0)}
                          {(customerLookup.get(selectedOrder.customer_id)?.last_name || 'U').charAt(0)}
                        </div>
                        <div>
                          <p className="text-gray-900 font-semibold">
                            {customerLookup.get(selectedOrder.customer_id)
                              ? `${customerLookup.get(selectedOrder.customer_id)?.first_name} ${customerLookup.get(selectedOrder.customer_id)?.last_name}`
                              : 'Unknown customer'}
                          </p>
                          <p className="text-sm text-gray-500">{customerLookup.get(selectedOrder.customer_id)?.email}</p>
                          {customerLookup.get(selectedOrder.customer_id)?.phone && (
                            <p className="text-sm text-gray-500">{customerLookup.get(selectedOrder.customer_id)?.phone}</p>
                          )}
                        </div>
                      </div>
                      <div className="border-t border-gray-200 pt-3 text-sm text-gray-700">
                        {vehicleLookup.get(selectedOrder.vehicle_id) ? (
                          <>
                            <p className="font-semibold text-gray-900">
                              {vehicleLookup.get(selectedOrder.vehicle_id)?.year || 'Year'}{' '}
                              {vehicleLookup.get(selectedOrder.vehicle_id)?.make}{' '}
                              {vehicleLookup.get(selectedOrder.vehicle_id)?.model}
                            </p>
                            <p className="text-gray-600 mt-1">
                              VIN: {vehicleLookup.get(selectedOrder.vehicle_id)?.vin || '—'}
                            </p>
                            <p className="text-gray-600">
                              Plate: {vehicleLookup.get(selectedOrder.vehicle_id)?.license_plate || '—'}
                            </p>
                          </>
                        ) : (
                          <p className="text-gray-500">Vehicle not found</p>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Work Requested</h3>
                  <div className="bg-gray-50 rounded-xl p-4">
                    <p className="text-gray-800 whitespace-pre-wrap">
                      {selectedOrder.description || 'No description provided'}
                    </p>
                  </div>
                </div>

                {(() => {
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
                    <div className="bg-gray-50 rounded-xl p-4">
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
                    </div>
                  )
                })()}

                {/* Quote Workflow */}
                {(() => {
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
                            <div className="flex justify-between">
                              <span className="text-gray-500">Amount</span>
                              <span className="font-semibold">${parseFloat(quoteForOrder.total_amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                            </div>
                          </div>
                        )}

                        {/* Workflow steps */}
                        <div className="flex items-center gap-1 flex-wrap">
                          {/* Step 1: Create/Update Quote Draft */}
                          {quoteNeedsUpdate && hasQuote ? (
                            <button
                              type="button"
                              onClick={() => quoteForOrder && updateQuoteMutation.mutate(quoteForOrder.id)}
                              disabled={updateQuoteMutation.isPending}
                              className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 text-white text-sm font-medium rounded-lg"
                            >
                              {updateQuoteMutation.isPending ? 'Updating...' : 'Update'}
                            </button>
                          ) : (
                            <span className={`px-3 py-1.5 text-sm font-medium rounded-lg ${
                              hasQuote 
                                ? 'bg-green-100 text-green-700' 
                                : 'bg-amber-500 text-white'
                            }`}>
                              {hasQuote ? (
                                <span className="flex items-center gap-1">✓ Draft Ready</span>
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

                          <ArrowRight className={`w-4 h-4 shrink-0 ${hasQuote && !quoteNeedsUpdate ? 'text-amber-500' : 'text-gray-300'}`} />

                          {/* Step 2: Send to Customer */}
                          {hasQuote && !isApproved && !quoteNeedsUpdate ? (
                            <button
                              type="button"
                              onClick={() => {
                                if (quoteForOrder) {
                                  sendQuoteMutation.mutate(quoteForOrder.id)
                                  setQuoteSent(true)
                                }
                              }}
                              disabled={sendQuoteMutation.isPending}
                              className={`px-3 py-1.5 text-sm font-medium rounded-lg ${
                                isSent 
                                  ? 'bg-blue-100 text-blue-700 hover:bg-blue-200' 
                                  : 'bg-amber-500 hover:bg-amber-600 text-white'
                              }`}
                            >
                              {sendQuoteMutation.isPending ? 'Sending...' : (isSent ? '⏳ Resend' : 'Send')}
                            </button>
                          ) : (
                            <span className={`px-3 py-1.5 text-sm font-medium rounded-lg ${
                              isApproved ? 'bg-green-100 text-green-700' : 'bg-gray-200 text-gray-400'
                            }`}>
                              {isApproved ? '✓ Sent' : 'Send'}
                            </span>
                          )}

                          <ArrowRight className={`w-4 h-4 shrink-0 ${isApproved ? 'text-amber-500' : 'text-gray-300'}`} />

                          {/* Step 3: Customer Approved */}
                          <span className={`px-3 py-1.5 text-sm font-medium rounded-lg ${
                            isApproved 
                              ? 'bg-green-100 text-green-700' 
                              : isSent 
                                ? 'bg-amber-100 text-amber-700 animate-pulse' 
                                : 'bg-gray-200 text-gray-400'
                          }`}>
                            {isApproved ? '✓ Approved' : isSent ? 'Awaiting Approval' : 'Approved'}
                          </span>

                          <ArrowRight className={`w-4 h-4 shrink-0 ${hasMechanic ? 'text-amber-500' : 'text-gray-300'}`} />

                          {/* Step 4: Mechanic Assigned */}
                          <span className={`px-3 py-1.5 text-sm font-medium rounded-lg ${
                            hasMechanic 
                              ? 'bg-green-100 text-green-700' 
                              : isApproved 
                                ? 'bg-amber-100 text-amber-700' 
                                : 'bg-gray-200 text-gray-400'
                          }`}>
                            {hasMechanic ? `✓ ${mechanicName}` : isApproved ? 'Assign ↓' : 'Mechanic'}
                          </span>
                        </div>

                        {/* Status messages */}
                        {quoteNeedsUpdate && hasQuote && (
                          <p className="text-sm text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                            Quote needs to be updated before sending.
                          </p>
                        )}
                        {isSent && !isApproved && !quoteNeedsUpdate && (orderDetail ?? selectedOrder).status !== 'declined' && (
                          <p className="text-sm text-blue-600 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
                            Waiting for customer approval...
                          </p>
                        )}
                        {isApproved && !hasMechanic && (
                          <p className="text-sm text-green-600 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                            Customer approved! Assign a mechanic to start work.
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
                            <p className="text-xs font-medium text-gray-500 uppercase">Available Mechanics</p>
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
                                Reassign Mechanic
                              </button>
                            ) : (
                              <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                  <p className="text-xs font-medium text-gray-500 uppercase">Select New Mechanic</p>
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
                Are you sure you want to delete this repair order? This will permanently remove:
              </p>
              
              <ul className="text-sm text-gray-600 mb-6 space-y-1 ml-4">
                <li className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-400"></span>
                  The repair order and all details
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
              
              <p className="text-sm text-red-600 font-medium mb-6">
                This action cannot be undone.
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
                  Delete permanently
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Invoice Confirmation Modal */}
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
                  <h3 className="text-lg font-semibold text-gray-900">Zelle Payment</h3>
                  <p className="text-sm text-gray-500">Show QR code to customer</p>
                </div>
              </div>

              {/* QR Code Display */}
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
                      Upload in Garage Settings → Zelle Payments
                    </p>
                  </div>
                )}
              </div>

              {/* Amount Display */}
              {invoiceForOrder && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-4">
                  <p className="text-sm text-green-800 text-center">
                    Amount due: <span className="font-bold">${parseFloat(invoiceForOrder.total_amount).toFixed(2)}</span>
                  </p>
                </div>
              )}

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setShowZelleQrModal(false)}
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
                      })
                    }
                  }}
                  disabled={recordManualPaymentMutation.isPending}
                  className="flex-1 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-medium rounded-lg transition-colors"
                >
                  {recordManualPaymentMutation.isPending ? 'Recording...' : 'Payment Received'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
