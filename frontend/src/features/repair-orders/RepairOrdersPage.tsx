import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { Customer, RepairOrder, RepairOrderDetail, Service, Vehicle, PartsUsage, Labor, InventoryItem, Quote } from '../../types'
import { format } from 'date-fns'
import { ArrowRight, Plus, TriangleAlert, Trash2, OctagonX, Wrench, ChevronDown, ChevronUp } from 'lucide-react'
import SlidePanel from '@/components/SlidePanel'
import YearPicker from '../../components/YearPicker'
import VehicleMakePicker from '../../components/VehicleMakePicker'
import CustomerSelect from '../../components/CustomerSelect'
import { formatUSPhone } from '@/utils/phone'
import BaseSelect from '../../components/BaseSelect'
import ViewToggle from '@/components/ViewToggle'
import { useViewPreference } from '@/hooks/useViewPreference'

interface NewCustomerForm {
  first_name: string
  last_name: string
  email: string
  phone: string
}

interface NewVehicleForm {
  make: string
  model: string
  year: string
  vin: string
  license_plate: string
  mileage: string
}

export default function RepairOrdersPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('')
  const [selectedVehicleId, setSelectedVehicleId] = useState<string>('')
  const [showNewVehicleForm, setShowNewVehicleForm] = useState(false)
  const [description, setDescription] = useState('')
  const [serviceSearch, setServiceSearch] = useState('')
  const [selectedServiceIds, setSelectedServiceIds] = useState<string[]>([])
  const [formError, setFormError] = useState<string | null>(null)
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
  const [customerSectionExpanded, setCustomerSectionExpanded] = useState(false)

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

  const createCustomerMutation = useMutation({
    mutationFn: async (payload: NewCustomerForm) => {
      const response = await api.post('/customers', payload)
      return response.data as Customer
    },
  })

  const createVehicleMutation = useMutation({
    mutationFn: async ({ customer_id, data }: { customer_id: string; data: NewVehicleForm }) => {
      const payload = {
        customer_id,
        make: data.make.trim(),
        model: data.model.trim(),
        year: data.year ? Number(data.year) : null,
        vin: data.vin.trim() || null,
        license_plate: data.license_plate.trim() || null,
        color: null,
        mileage: data.mileage ? Number(data.mileage) : null,
        notes: null,
      }
      const response = await api.post('/vehicles', payload)
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
    onError: (error: any) => {
      setFormError(error.response?.data?.detail || 'Failed to create repair order')
    },
  })

  const cancelRepairOrderMutation = useMutation({
    mutationFn: async (orderId: string) => {
      const response = await api.put(`/repair-orders/${orderId}`, { status: 'cancelled' })
      return response.data as RepairOrder
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      setSelectedOrder(updated)
    },
    onError: (error: any) => {
      setFormError(error.response?.data?.detail || 'Failed to cancel repair order')
    },
  })

  const deleteRepairOrderMutation = useMutation({
    mutationFn: async (orderId: string) => {
      await api.delete(`/repair-orders/${orderId}`)
      return orderId
    },
    onSuccess: (orderId) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      if (selectedOrder?.id === orderId) {
        closeDetail()
      }
    },
    onError: (error: any) => {
      setFormError(error.response?.data?.detail || 'Failed to delete repair order')
    },
  })

  const assignMechanicMutation = useMutation({
    mutationFn: async ({ orderId, mechanicId }: { orderId: string; mechanicId: string }) => {
      const response = await api.put(`/repair-orders/${orderId}`, { assigned_mechanic_id: mechanicId || null })
      return response.data as RepairOrder
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', updated.id] })
      setSelectedOrder(updated)
    },
    onError: (error: any) => {
      setFormError(error.response?.data?.detail || 'Failed to assign mechanic')
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
      refetchOrderDetail()
    },
  })

  const updateLaborMutation = useMutation({
    mutationFn: async ({
      orderId,
      laborId,
      description,
      hours,
      hourly_rate,
    }: { orderId: string; laborId: string; description?: string; hours?: number; hourly_rate?: number }) => {
      const payload: Record<string, unknown> = {}
      if (description !== undefined) payload.description = description
      if (hours !== undefined) payload.hours = hours
      if (hourly_rate !== undefined) payload.hourly_rate = hourly_rate
      const response = await api.put(`/repair-orders/${orderId}/labor/${laborId}`, payload)
      return response.data as Labor
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', vars.orderId] })
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
      refetchOrderDetail()
    },
  })

  const createQuoteMutation = useMutation({
    mutationFn: async (repair_order_id: string) => {
      const response = await api.post('/quotes', { repair_order_id })
      return response.data as Quote
    },
    onSuccess: (_, orderId) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['quote', orderId] })
      queryClient.invalidateQueries({ queryKey: ['repair-order-detail', orderId] })
      refetchQuote()
      refetchOrderDetail()
      setSelectedOrder((prev) => (prev && prev.id === orderId ? { ...prev, status: 'quoted' } : prev))
    },
  })

  const approveQuoteMutation = useMutation({
    mutationFn: async (quoteId: string) => {
      const response = await api.post(`/quotes/${quoteId}/approve`)
      return response.data as Quote
    },
    onSuccess: (_, __) => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      if (selectedOrder?.id) {
        queryClient.invalidateQueries({ queryKey: ['quote', selectedOrder.id] })
        refetchQuote()
        refetchOrderDetail()
      }
      closeDetail()
    },
  })

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
      approved: { bg: 'bg-green-100', text: 'text-green-700', dot: 'bg-green-500' },
      in_progress: { bg: 'bg-yellow-100', text: 'text-yellow-700', dot: 'bg-yellow-500' },
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
    setFormError(null)
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
  }

  const closeDetail = () => {
    setSelectedOrder(null)
    setIsDetailOpen(false)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setIsSubmitting(true)

    try {
      let finalCustomerId = selectedCustomerId
      let finalVehicleId = selectedVehicleId
      const isNewCustomer = selectedCustomerId === 'add_new'

      // New customer flow
      if (isNewCustomer) {
        if (!newCustomer.first_name.trim() || !newCustomer.last_name.trim() || !newCustomer.email.trim()) {
          setFormError('New customer requires first name, last name, and email.')
          return
        }
        const createdCustomer = await createCustomerMutation.mutateAsync({
          first_name: newCustomer.first_name.trim(),
          last_name: newCustomer.last_name.trim(),
          email: newCustomer.email.trim(),
          phone: newCustomer.phone.trim(),
        })
        finalCustomerId = createdCustomer.id
      } else if (!finalCustomerId) {
        setFormError('Select a customer or create a new one.')
        return
      }

      // Vehicle selection can override customer
      const shouldCreateVehicle = isNewCustomer || showNewVehicleForm || !selectedVehicleId

      if (shouldCreateVehicle) {
        if (!finalCustomerId) {
          setFormError('A customer is required to add a vehicle.')
          return
        }
        if (!newVehicle.make.trim() || !newVehicle.model.trim()) {
          setFormError('New vehicle requires make and model.')
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
          setFormError('Selected vehicle not found.')
          return
        }
        finalVehicleId = vehicle.id
        finalCustomerId = vehicle.customer_id
      }

      if (!finalCustomerId || !finalVehicleId) {
        setFormError('Customer and vehicle are required.')
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

      const quotedStatusPayload = { status: 'quoted' }

      const combinedDescription = [selectedServiceText, description.trim()].filter(Boolean).join(' — ')

      const createdOrder = await createRepairOrderMutation.mutateAsync({
        customer_id: finalCustomerId,
        vehicle_id: finalVehicleId,
        description: combinedDescription,
        internal_notes: internalNotes,
      })

      try {
        await api.put(`/repair-orders/${createdOrder.id}`, quotedStatusPayload)
      } catch (err: any) {
        console.error('Failed to set quoted status', err)
      }

      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['customers'] })
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      closeModal()
    } catch (err: any) {
      setFormError(err.response?.data?.detail || 'Failed to create repair order')
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
          className="mt-3 sm:mt-0 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors"
        >
          + New Repair Order
        </button>
      </div>

      {/* Search Bar */}
      <div className="mb-6 bg-white/10 backdrop-blur rounded-xl p-4">
        <div className="flex flex-col sm:flex-row gap-3">
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
              className="w-full pl-10 pr-4 py-2.5 bg-white rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>

          <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
            <div className="flex gap-2 min-w-max sm:min-w-0 sm:flex-wrap">
              {statusOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setStatusFilter(option.value)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                    statusFilter === option.value
                      ? 'bg-amber-500 text-white'
                      : 'bg-white/20 text-white hover:bg-white/30 active:bg-white/40'
                  }`}
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
                    const statusStyle = getStatusStyle(order.status)
                    const parsedServices = parseServiceNotes(order.internal_notes)
                    const estimatedTotal = parsedServices?.reduce(
                      (sum, svc) => sum + (parseFloat(svc.base_price || '0') || 0),
                      0
                    )
                    const backendTotal = parseFloat(order.total_cost) || 0
                    const displayTotal = backendTotal || estimatedTotal || 0
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
                            {order.status.replace('_', ' ')}
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
                            className="text-amber-400 hover:text-amber-300 text-sm font-medium"
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
                const statusStyle = getStatusStyle(order.status)
                const parsedServices = parseServiceNotes(order.internal_notes)
                const estimatedTotal = parsedServices?.reduce(
                  (sum, svc) => sum + (parseFloat(svc.base_price || '0') || 0),
                  0
                )
                const backendTotal = parseFloat(order.total_cost) || 0
                const showEstimate = backendTotal === 0 && estimatedTotal && estimatedTotal > 0
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
                          {order.status.replace('_', ' ')}
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
                        <div className="text-xs text-slate-500 mb-1">{showEstimate ? 'Est. from services' : 'Total Cost'}</div>
                        <div className="text-xl font-bold text-slate-800">
                          $
                          {(showEstimate ? estimatedTotal : backendTotal || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
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
                {formError && (
                  <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                    {formError}
                  </div>
                )}

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
                    className="px-5 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-300 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
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
        headerExtra={
          selectedOrder && (
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/20 text-sm font-medium">
              <span className={`w-2 h-2 rounded-full ${getStatusStyle((orderDetail ?? selectedOrder).status).dot}`}></span>
              {(orderDetail ?? selectedOrder).status.replace('_', ' ')}
            </div>
          )
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
                    disabled={cancelRepairOrderMutation.isPending || deleteRepairOrderMutation.isPending || selectedOrder.status === 'cancelled'}
                    onClick={() => selectedOrder.id && cancelRepairOrderMutation.mutate(selectedOrder.id)}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-700 border border-red-200 rounded-lg hover:bg-red-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <OctagonX className="w-4 h-4" />
                    {cancelRepairOrderMutation.isPending ? 'Cancelling...' : 'Cancel order'}
                  </button>
                  <button
                    type="button"
                    disabled={deleteRepairOrderMutation.isPending}
                    onClick={() => {
                      if (selectedOrder.id && window.confirm('Delete this repair order? This cannot be undone.')) {
                        deleteRepairOrderMutation.mutate(selectedOrder.id)
                      }
                    }}
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
                  const detailServices = parseServiceNotes(selectedOrder.internal_notes)
                  const detailEstimate = detailServices?.reduce(
                    (sum, svc) => sum + (parseFloat(svc.base_price || '0') || 0),
                    0
                  )
                  return detailServices && detailServices.length > 0 ? (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Selected Services</h3>
                      <div className="bg-gray-50 rounded-xl p-4 space-y-2 text-sm text-gray-800">
                        {detailServices.map((svc) => (
                          <div key={svc.id} className="flex items-center justify-between">
                            <span>{svc.name}</span>
                            <span className="font-semibold">${parseFloat(svc.base_price || '0').toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                          </div>
                        ))}
                        {detailEstimate ? (
                          <div className="pt-2 mt-2 border-t border-gray-200 flex items-center justify-between font-semibold">
                            <span>Estimated total</span>
                            <span>${detailEstimate.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ) : null
                })()}

                {/* Parts and labor: use detail when available */}
                {(() => {
                  const displayOrder = orderDetail ?? selectedOrder
                  const partsUsage = orderDetail?.parts_usage ?? []
                  const laborItems = orderDetail?.labor_items ?? []
                  const canEditLineItems = displayOrder && ['draft', 'quoted'].includes(displayOrder.status)
                  return (
                    <>
                      <div>
                        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Parts</h3>
                        <div className="bg-gray-50 rounded-xl p-4 space-y-2">
                          {partsUsage.length === 0 ? (
                            <p className="text-sm text-gray-500">No parts added</p>
                          ) : (
                            partsUsage.map((pu) => (
                              <div key={pu.id} className="flex items-center justify-between text-sm text-gray-800 py-1 border-b border-gray-200 last:border-0">
                                <div>
                                  <span className="font-medium">{pu.inventory_name}</span>
                                  <span className="text-gray-500 ml-2">({pu.inventory_sku}) × {pu.quantity}</span>
                                </div>
                                <div className="flex items-center gap-2">
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
                            ))
                          )}
                          {canEditLineItems && inventory && inventory.length > 0 && (
                            <div className="pt-3 mt-2 border-t border-gray-200 flex flex-wrap gap-2 items-end">
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
                                className="rounded-lg border border-gray-300 px-3 py-2 text-sm w-20"
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
                                className="px-3 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 text-white text-sm font-medium rounded-lg"
                              >
                                Add part
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                      <div>
                        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Labor</h3>
                        <div className="bg-gray-50 rounded-xl p-4 space-y-2">
                          {laborItems.length === 0 ? (
                            <p className="text-sm text-gray-500">No labor lines</p>
                          ) : (
                            laborItems.map((li) => (
                              <div key={li.id} className="flex items-center justify-between text-sm text-gray-800 py-1 border-b border-gray-200 last:border-0">
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
                            ))
                          )}
                          {canEditLineItems && (
                            <div className="pt-3 mt-2 border-t border-gray-200 flex flex-col gap-2">
                              <input
                                type="text"
                                placeholder="Description (optional)"
                                value={addLaborDescription}
                                onChange={(e) => setAddLaborDescription(e.target.value)}
                                className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
                              />
                              <div className="flex flex-wrap gap-2">
                                <input
                                  type="number"
                                  step={0.25}
                                  min={0}
                                  placeholder="Hours"
                                  value={addLaborHours}
                                  onChange={(e) => setAddLaborHours(e.target.value)}
                                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm w-24"
                                />
                                <input
                                  type="number"
                                  step={0.01}
                                  min={0}
                                  placeholder="Hourly rate"
                                  value={addLaborRate}
                                  onChange={(e) => setAddLaborRate(e.target.value)}
                                  className="rounded-lg border border-gray-300 px-3 py-2 text-sm w-28"
                                />
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
                                      description: addLaborDescription.trim() || undefined,
                                      hours,
                                      hourly_rate: rate,
                                    })
                                    setAddLaborDescription('')
                                    setAddLaborHours('')
                                    setAddLaborRate('100')
                                  }}
                                  className="px-3 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 text-white text-sm font-medium rounded-lg"
                                >
                                  Add labor
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </>
                  )
                })()}

                <div>
                  <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Assigned mechanic</h3>
                  <div className="bg-gray-50 rounded-xl p-4 space-y-3">
                    <div className="flex items-center gap-2 text-sm text-gray-800">
                      <Wrench className="w-4 h-4 text-amber-600" />
                      <span>
                        {selectedOrder.assigned_mechanic_id
                          ? mechanicLookup.get(selectedOrder.assigned_mechanic_id) || 'Assigned mechanic'
                          : 'Unassigned'}
                      </span>
                    </div>
                    <div className="space-y-3">
                      <BaseSelect
                        options={[
                          { value: '', label: 'Unassigned', subLabel: 'Keep this job unassigned for now' },
                          ...(mechanics || []).map((m) => {
                            const inProgress = m.in_progress_count ?? 0
                            const assigned = m.assigned_count ?? 0
                            const load = assigned > 0 ? Math.min((inProgress / assigned) * 100, 100) : 0
                            return {
                              value: m.mechanic_id,
                              label: m.mechanic_name,
                              subLabel: `${inProgress}/${assigned || '—'} in progress · Load ${load.toFixed(0)}%`,
                            }
                          }),
                        ]}
                        value={selectedOrder.assigned_mechanic_id || ''}
                        onChange={(val) =>
                          selectedOrder.id &&
                          assignMechanicMutation.mutate({ orderId: selectedOrder.id, mechanicId: val })
                        }
                        placeholder="Select mechanic"
                        allowAddNew={false}
                      />
                      {selectedOrder.assigned_mechanic_id && mechanics && (
                        (() => {
                          const mech = mechanics.find((m) => m.mechanic_id === selectedOrder.assigned_mechanic_id)
                          if (!mech) return null
                          const inProgress = mech.in_progress_count ?? 0
                          const assigned = mech.assigned_count ?? 0
                          const load = assigned > 0 ? Math.min((inProgress / assigned) * 100, 100) : 0
                          return (
                            <div className="bg-white/60 border border-amber-200 rounded-lg p-3">
                              <div className="flex items-center justify-between">
                                <p className="text-sm font-semibold text-gray-800">{mech.mechanic_name}</p>
                                <span className="text-xs text-gray-600">{inProgress}/{assigned || '—'} in progress</span>
                              </div>
                              <div className="mt-2 h-2 rounded-full bg-gray-200 overflow-hidden">
                                <div className="h-full bg-amber-500 transition-all" style={{ width: `${load}%` }} />
                              </div>
                              <p className="mt-1 text-xs text-gray-600">Load: {load.toFixed(0)}%</p>
                            </div>
                          )
                        })()
                      )}
                      <div className="text-xs text-gray-500">
                        Assigning is available for quoted or in-progress work. Paid orders stay read-only.
                      </div>
                    </div>
                  </div>
                </div>

                <div>
                  <button
                    type="button"
                    onClick={() => setCustomerSectionExpanded((prev) => !prev)}
                    className="w-full flex items-center justify-between text-left bg-gray-50 rounded-xl p-3 hover:bg-gray-100 transition-colors"
                  >
                    <span className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Customer</span>
                    <span className="text-gray-900 font-medium truncate max-w-[60%]">
                      {customerLookup.get(selectedOrder.customer_id)
                        ? `${customerLookup.get(selectedOrder.customer_id)?.first_name} ${customerLookup.get(selectedOrder.customer_id)?.last_name}`
                        : 'Unknown customer'}
                    </span>
                    {customerSectionExpanded ? (
                      <ChevronUp className="w-5 h-5 text-gray-500 shrink-0 ml-2" />
                    ) : (
                      <ChevronDown className="w-5 h-5 text-gray-500 shrink-0 ml-2" />
                    )}
                  </button>
                  {customerSectionExpanded && (
                    <div className="bg-gray-50 rounded-b-xl p-4 flex items-center gap-3 border-t border-gray-200 -mt-1 pt-4">
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
                      </div>
                    </div>
                  )}
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Vehicle</h3>
                  <div className="bg-gray-50 rounded-xl p-4 text-sm text-gray-700">
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
                  const backendTotal = parseFloat(totalsOrder?.total_cost ?? '0') || 0
                  const detailServices = parseServiceNotes(selectedOrder?.internal_notes)
                  const detailEstimate = detailServices?.reduce(
                    (sum, svc) => sum + (parseFloat(svc.base_price || '0') || 0),
                    0
                  )
                  const showEstimate = backendTotal === 0 && detailEstimate && detailEstimate > 0
                  const partsVal = showEstimate ? detailEstimate || 0 : backendParts
                  const laborVal = showEstimate ? 0 : backendLabor
                  const totalVal = showEstimate ? detailEstimate || 0 : backendTotal
                  const fmt = (n: number) => n.toLocaleString('en-US', { minimumFractionDigits: 2 })

                  return (
                    <div className="bg-gray-50 rounded-xl p-4">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                        <span className="text-gray-500">Parts</span>
                        <span className="font-semibold text-blue-700">${fmt(partsVal)}</span>
                        <span className="text-gray-400">·</span>
                        <span className="text-gray-500">Labor</span>
                        <span className="font-semibold text-amber-700">${fmt(laborVal)}</span>
                        <span className="text-gray-400">·</span>
                        <span className="text-gray-500">Total</span>
                        <span className="text-base font-bold text-gray-900">${fmt(totalVal)}</span>
                      </div>
                    </div>
                  )
                })()}

                {/* Quote — steps: Create → Approve */}
                <div>
                  <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Quote</h3>
                  <div className="bg-gray-50 rounded-xl p-4 space-y-3">
                    {!quoteForOrder && selectedOrder && ['draft', 'quoted'].includes(selectedOrder.status) && (
                      <>
                        <p className="text-sm text-gray-600"><span className="font-medium text-gray-800">1. Create quote</span> — Next step</p>
                        <button
                          type="button"
                          onClick={() => selectedOrder.id && createQuoteMutation.mutate(selectedOrder.id)}
                          disabled={createQuoteMutation.isPending}
                          className="px-3 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 text-white text-sm font-medium rounded-lg"
                        >
                          {createQuoteMutation.isPending ? 'Creating...' : 'Create quote'}
                        </button>
                      </>
                    )}
                    {quoteForOrder && !quoteForOrder.is_approved && (
                      <>
                        <p className="text-sm text-gray-600"><span className="font-medium text-gray-800">2. Approve quote</span> — Next step</p>
                        <div className="space-y-1 text-sm text-gray-800">
                          <div className="flex justify-between">
                            <span className="text-gray-500">Quote #</span>
                            <span className="font-mono font-medium">{quoteForOrder.quote_number}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-500">Amount</span>
                            <span className="font-semibold">${parseFloat(quoteForOrder.total_amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                          </div>
                          {quoteForOrder.expires_at && (
                            <div className="flex justify-between">
                              <span className="text-gray-500">Expires</span>
                              <span>{format(new Date(quoteForOrder.expires_at), 'PP')}</span>
                            </div>
                          )}
                        </div>
                        {selectedOrder?.id && (
                          <button
                            type="button"
                            onClick={() => approveQuoteMutation.mutate(quoteForOrder.id)}
                            disabled={approveQuoteMutation.isPending}
                            className="px-3 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-300 text-white text-sm font-medium rounded-lg"
                          >
                            {approveQuoteMutation.isPending ? 'Approving...' : 'Approve quote'}
                          </button>
                        )}
                      </>
                    )}
                    {quoteForOrder?.is_approved && (
                      <p className="text-sm font-medium text-green-600">Quote approved — you can close this panel and see the repair order in the list.</p>
                    )}
                    {selectedOrder && !['draft', 'quoted', 'approved'].includes(selectedOrder.status) && !quoteForOrder && (
                      <p className="text-sm text-gray-500">No quote for this order</p>
                    )}
                  </div>
                </div>
              </div>
            )}
      </SlidePanel>
    </div>
  )
}
