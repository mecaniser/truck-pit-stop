import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { Customer, RepairOrder, Vehicle } from '../../types'
import { format } from 'date-fns'
import { ArrowRight, Plus } from 'lucide-react'
import YearPicker from '../../components/YearPicker'
import VehicleMakePicker from '../../components/VehicleMakePicker'
import CustomerSelect from '../../components/CustomerSelect'

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
  const [formError, setFormError] = useState<string | null>(null)
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

  const filteredVehicles = useMemo(() => {
    if (!vehicles) return []
    if (selectedCustomerId) {
      return vehicles.filter((v) => v.customer_id === selectedCustomerId)
    }
    return []
  }, [vehicles, selectedCustomerId])

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
    mutationFn: async ({ customer_id, vehicle_id, description: roDescription }: { customer_id: string; vehicle_id: string; description: string }) => {
      const response = await api.post('/repair-orders', {
        customer_id,
        vehicle_id,
        description: roDescription || null,
      })
      return response.data as RepairOrder
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repair-orders'] })
      queryClient.invalidateQueries({ queryKey: ['customers'] })
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      closeModal()
    },
    onError: (error: any) => {
      setFormError(error.response?.data?.detail || 'Failed to create repair order')
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)

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

      await createRepairOrderMutation.mutateAsync({
        customer_id: finalCustomerId,
        vehicle_id: finalVehicleId,
        description,
      })
    } catch (err: any) {
      setFormError(err.response?.data?.detail || 'Failed to create repair order')
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

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filteredOrders?.map((order) => {
          const statusStyle = getStatusStyle(order.status)
          return (
            <div 
              key={order.id}
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
                
                <div className="bg-white/50 rounded-lg p-3">
                  <div className="text-xs text-slate-500 mb-1">Total Cost</div>
                  <div className="text-xl font-bold text-slate-800">
                    ${parseFloat(order.total_cost).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-amber-200/50">
                <button className="w-full py-2 text-sm font-medium text-amber-700 hover:text-amber-900 hover:bg-amber-200/50 rounded-lg transition-colors inline-flex items-center justify-center gap-1">
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
                          onChange={(e) => setNewCustomer((prev) => ({ ...prev, phone: e.target.value }))}
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
                    disabled={createRepairOrderMutation.isPending || createCustomerMutation.isPending || createVehicleMutation.isPending}
                    className="px-5 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-300 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
                  >
                    {(createRepairOrderMutation.isPending || createCustomerMutation.isPending || createVehicleMutation.isPending) && (
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
    </div>
  )
}
