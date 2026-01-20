import { useCallback, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { Customer, Vehicle } from '../../types'
import { ArrowRight, Plus } from 'lucide-react'
import YearPicker from '../../components/YearPicker'
import VehicleMakePicker from '../../components/VehicleMakePicker'
import CustomerSelect from '../../components/CustomerSelect'

interface VehicleFormData {
  customer_id: string
  make: string
  model: string
  year: string
  vin: string
  license_plate: string
  color: string
  mileage: string
  notes: string
}

interface VehiclePayload {
  customer_id: string
  make: string
  model: string
  year: number | null
  vin: string | null
  license_plate: string | null
  color: string | null
  mileage: number | null
  notes: string | null
}

const emptyForm: VehicleFormData = {
  customer_id: '',
  make: '',
  model: '',
  year: '',
  vin: '',
  license_plate: '',
  color: '',
  mileage: '',
  notes: '',
}


export default function VehiclesPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchType, setSearchType] = useState<'all' | 'vin' | 'name' | 'plate'>('all')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isDetailOpen, setIsDetailOpen] = useState(false)
  const [isEditingInPanel, setIsEditingInPanel] = useState(false)
  const [editingVehicle, setEditingVehicle] = useState<Vehicle | null>(null)
  const [selectedVehicle, setSelectedVehicle] = useState<Vehicle | null>(null)
  const [formData, setFormData] = useState<VehicleFormData>(emptyForm)
  const [formError, setFormError] = useState<string | null>(null)

  const queryClient = useQueryClient()

  const { data: vehicles, isLoading: isLoadingVehicles } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: async () => {
      const response = await api.get('/vehicles')
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

  const customerLookup = useMemo(() => {
    const map = new Map<string, Customer>()
    customers?.forEach((c) => map.set(c.id, c))
    return map
  }, [customers])

  const resetForm = () => {
    setEditingVehicle(null)
    setFormData(emptyForm)
    setFormError(null)
  }

  const populateForm = (vehicle: Vehicle) => {
    setEditingVehicle(vehicle)
    setFormData({
      customer_id: vehicle.customer_id,
      make: vehicle.make || '',
      model: vehicle.model || '',
      year: vehicle.year?.toString() || '',
      vin: vehicle.vin || '',
      license_plate: vehicle.license_plate || '',
      color: vehicle.color || '',
      mileage: vehicle.mileage?.toString() || '',
      notes: vehicle.notes || '',
    })
    setFormError(null)
  }

  const openCreateModal = () => {
    resetForm()
    setIsEditingInPanel(false)
    setIsModalOpen(true)
  }

  const closeModal = () => {
    setIsModalOpen(false)
    resetForm()
  }

  const openDetailPanel = (vehicle: Vehicle) => {
    setSelectedVehicle(vehicle)
    setIsDetailOpen(true)
    setIsEditingInPanel(false)
  }

  const closeDetailPanel = () => {
    setIsDetailOpen(false)
    setSelectedVehicle(null)
    setIsEditingInPanel(false)
    resetForm()
  }

  const handleEditFromDetail = () => {
    if (selectedVehicle) {
      populateForm(selectedVehicle)
      setIsEditingInPanel(true)
    }
  }

  const cancelPanelEditing = () => {
    setIsEditingInPanel(false)
    resetForm()
  }

  const createMutation = useMutation({
    mutationFn: async (data: VehiclePayload) => {
      const response = await api.post('/vehicles', data)
      return response.data as Vehicle
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      closeModal()
    },
    onError: (error: any) => {
      setFormError(error.response?.data?.detail || 'Failed to create vehicle')
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: VehiclePayload }) => {
      const response = await api.put(`/vehicles/${id}`, data)
      return response.data as Vehicle
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      if (isEditingInPanel) {
        setSelectedVehicle(updated)
        setIsEditingInPanel(false)
        resetForm()
      } else {
        closeModal()
      }
    },
    onError: (error: any) => {
      setFormError(error.response?.data?.detail || 'Failed to update vehicle')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)

    if (!formData.make.trim() || !formData.model.trim()) {
      setFormError('Make and model are required')
      return
    }
    if (!formData.customer_id) {
      setFormError('Customer is required')
      return
    }

    const payload = {
      customer_id: formData.customer_id,
      make: formData.make.trim(),
      model: formData.model.trim(),
      year: formData.year ? Number(formData.year) : null,
      vin: formData.vin.trim() || null,
      license_plate: formData.license_plate.trim() || null,
      color: formData.color.trim() || null,
      mileage: formData.mileage ? Number(formData.mileage) : null,
      notes: formData.notes.trim() || null,
    } satisfies VehiclePayload

    if (editingVehicle) {
      updateMutation.mutate({ id: editingVehicle.id, data: payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }, [])

  const renderVehicleForm = (onCancel: () => void) => (
    <form onSubmit={handleSubmit} className="p-6 space-y-6">
      {formError && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {formError}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <VehicleMakePicker
          value={formData.make}
          onChange={(make) => {
            setFormData((prev) => ({ ...prev, make }))
          }}
        />
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Model <span className="text-red-500">*</span></label>
          <input
            name="model"
            value={formData.model}
            onChange={handleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="579, Cascadia, T680..."
            required
          />
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <YearPicker
          value={formData.year}
          onChange={(year) => setFormData((prev) => ({ ...prev, year }))}
        />
        <div className="sm:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-1">VIN</label>
          <input
            name="vin"
            value={formData.vin}
            onChange={handleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="1XPBDP9X8JD123456"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Plate</label>
          <input
            name="license_plate"
            value={formData.license_plate}
            onChange={handleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="TRK-1234"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Color</label>
          <input
            name="color"
            value={formData.color}
            onChange={handleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="Fleet white"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Mileage</label>
          <input
            type="number"
            name="mileage"
            value={formData.mileage}
            onChange={handleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="450000"
          />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Customer <span className="text-red-500">*</span></label>
        <CustomerSelect
          customers={customers || []}
          value={formData.customer_id}
          onChange={(id) => setFormData((prev) => ({ ...prev, customer_id: id }))}
          allowAddNew={false}
          placeholder="Select customer"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
        <textarea
          name="notes"
          value={formData.notes}
          onChange={handleInputChange}
          rows={3}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors resize-none"
          placeholder="Additional details or preferences..."
        />
      </div>

      <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200">
        <button
          type="button"
          onClick={onCancel}
          className="px-5 py-2.5 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={createMutation.isPending || updateMutation.isPending}
          className="px-5 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-300 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
        >
          {(createMutation.isPending || updateMutation.isPending) && (
            <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          )}
          {editingVehicle ? 'Save Changes' : 'Add Vehicle'}
        </button>
      </div>
    </form>
  )

  const filteredVehicles = useMemo(() => {
    if (!vehicles || !searchQuery.trim()) return vehicles

    const query = searchQuery.toLowerCase().trim()
    
    return vehicles.filter((vehicle) => {
      const vinMatch = vehicle.vin?.toLowerCase().includes(query)
      const nameMatch = `${vehicle.year || ''} ${vehicle.make} ${vehicle.model}`.toLowerCase().includes(query)
      const plateMatch = vehicle.license_plate?.toLowerCase().includes(query)

      switch (searchType) {
        case 'vin':
          return vinMatch
        case 'name':
          return nameMatch
        case 'plate':
          return plateMatch
        default:
          return vinMatch || nameMatch || plateMatch
      }
    })
  }, [vehicles, searchQuery, searchType])

  if (isLoadingVehicles) {
    return <div className="text-white">Loading...</div>
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 sm:mb-6">
        <h1 className="text-xl sm:text-2xl font-bold text-white">Vehicles</h1>
        <button 
          onClick={openCreateModal}
          className="mt-3 sm:mt-0 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors"
        >
          + Add Vehicle
        </button>
      </div>

      {/* Search Bar */}
      <div className="mb-6 bg-white/10 backdrop-blur rounded-xl p-4">
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Search Input */}
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
              placeholder="Search trucks..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-white rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>

          {/* Filter Buttons */}
          <div className="flex gap-2">
            {[
              { value: 'all', label: 'All' },
              { value: 'name', label: 'Name' },
              { value: 'vin', label: 'VIN' },
              { value: 'plate', label: 'Plate' },
            ].map((filter) => (
              <button
                key={filter.value}
                onClick={() => setSearchType(filter.value as typeof searchType)}
                className={`px-3 sm:px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  searchType === filter.value
                    ? 'bg-amber-500 text-white'
                    : 'bg-white/20 text-white hover:bg-white/30 active:bg-white/40'
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>

        {/* Search Results Count */}
        {searchQuery && (
          <div className="mt-3 text-sm text-white/70">
            Found {filteredVehicles?.length || 0} vehicle{filteredVehicles?.length !== 1 ? 's' : ''}
            {searchType !== 'all' && ` matching ${searchType.toUpperCase()}`}
          </div>
        )}
      </div>
      
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filteredVehicles?.map((vehicle) => (
          <div 
            key={vehicle.id}
            onClick={() => openDetailPanel(vehicle)}
            className="aspect-square bg-gradient-to-br from-yellow-50 via-amber-100 to-yellow-200 p-4 sm:p-5 rounded-xl shadow-lg flex flex-col justify-between hover:shadow-xl transition-shadow cursor-pointer"
          >
            <div>
              <div className="text-xs font-medium text-amber-600 uppercase tracking-wide mb-1">
                {vehicle.year || 'Year N/A'}
              </div>
              <h3 className="text-lg font-bold text-slate-800 leading-tight">
                {vehicle.make}
              </h3>
              <p className="text-slate-600 font-medium">{vehicle.model}</p>
              <p className="text-sm text-slate-500 mt-1">
                {customerLookup.get(vehicle.customer_id)
                  ? `${customerLookup.get(vehicle.customer_id)?.first_name} ${customerLookup.get(vehicle.customer_id)?.last_name}`
                  : 'Unknown customer'}
              </p>
            </div>
            
            <div className="space-y-2 text-sm">
              {vehicle.license_plate && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Plate</span>
                  <span className="font-semibold text-slate-700">{vehicle.license_plate}</span>
                </div>
              )}
              {typeof vehicle.mileage === 'number' && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Mileage</span>
                  <span className="font-semibold text-slate-700">{vehicle.mileage.toLocaleString()} mi</span>
                </div>
              )}
              {vehicle.color && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Color</span>
                  <span className="font-semibold text-slate-700">{vehicle.color}</span>
                </div>
              )}
              {vehicle.vin && (
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">VIN</span>
                  <span className="font-mono text-xs text-slate-600 truncate max-w-24">{vehicle.vin}</span>
                </div>
              )}
            </div>

            <div className="pt-3 border-t border-amber-200/50">
              <button 
                onClick={(e) => {
                  e.stopPropagation()
                  openDetailPanel(vehicle)
                }}
                className="w-full py-2 text-sm font-medium text-amber-700 hover:text-amber-900 hover:bg-amber-200/50 rounded-lg transition-colors inline-flex items-center justify-center gap-1"
              >
                View Details
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}

        {/* Add Vehicle Card */}
        <div 
          onClick={openCreateModal}
          className="aspect-square bg-white/20 border-2 border-dashed border-white/40 p-4 sm:p-5 rounded-xl flex flex-col items-center justify-center cursor-pointer hover:bg-white/30 hover:border-white/60 transition-all"
        >
          <div className="w-12 h-12 rounded-full bg-white/30 flex items-center justify-center mb-3">
            <Plus className="w-6 h-6 text-white" />
          </div>
          <span className="text-white font-medium">Add Vehicle</span>
        </div>
      </div>

      {filteredVehicles?.length === 0 && searchQuery && (
        <div className="text-center py-12 text-white/70">
          No vehicles match your search. Try a different term.
        </div>
      )}

      {(!vehicles || vehicles.length === 0) && !searchQuery && (
        <div className="text-center py-12 text-white/70">
          No vehicles found. Add your first vehicle to get started.
        </div>
      )}

      {/* Add Vehicle Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {/* Backdrop */}
            <div 
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={closeModal}
            />
            
            {/* Modal */}
            <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
              {/* Header */}
              <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 rounded-t-2xl">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-bold text-gray-900">
                    {editingVehicle ? 'Edit Vehicle' : 'Add New Vehicle'}
                  </h2>
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

              {/* Form */}
              {renderVehicleForm(closeModal)}
            </div>
          </div>
        </div>
      )}

      {/* Vehicle Detail Panel */}
      {isDetailOpen && selectedVehicle && (
        <div className="fixed inset-0 z-50 overflow-hidden">
          {/* Backdrop */}
          <div 
            className="absolute inset-0 bg-black/40 backdrop-blur-sm transition-opacity"
            onClick={closeDetailPanel}
          />
          
          {/* Panel */}
          <div className="absolute inset-y-0 right-0 w-full max-w-lg bg-white shadow-2xl flex flex-col animate-slide-in-right">
            {/* Header */}
            <div className="bg-gradient-to-r from-amber-500 to-amber-600 px-6 py-8 text-white">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm text-amber-100 uppercase tracking-wide">Vehicle</p>
                  <h2 className="text-2xl font-bold">
                    {selectedVehicle.year ? `${selectedVehicle.year} ` : ''}{selectedVehicle.make} {selectedVehicle.model}
                  </h2>
                  <p className="text-amber-100 text-sm mt-1">
                    Added {new Date(selectedVehicle.created_at).toLocaleDateString()}
                  </p>
                </div>
                <button
                  onClick={closeDetailPanel}
                  className="p-2 hover:bg-white/20 rounded-lg transition-colors"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto">
              {isEditingInPanel ? (
                <div className="p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wide">Editing</p>
                    <h3 className="text-xl font-bold text-gray-900">Vehicle Details</h3>
                  </div>
                  <button
                    onClick={cancelPanelEditing}
                    className="px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                </div>
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
                  {renderVehicleForm(cancelPanelEditing)}
                </div>
              </div>
            ) : (
                <div className="p-6 space-y-6">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Owner</h3>
                    <div className="bg-gray-50 rounded-xl p-4 flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center text-amber-700 font-bold">
                        {(customerLookup.get(selectedVehicle.customer_id)?.first_name || 'C').charAt(0)}
                        {(customerLookup.get(selectedVehicle.customer_id)?.last_name || 'U').charAt(0)}
                      </div>
                      <div>
                        <p className="text-gray-900 font-semibold">
                          {customerLookup.get(selectedVehicle.customer_id)
                            ? `${customerLookup.get(selectedVehicle.customer_id)?.first_name} ${customerLookup.get(selectedVehicle.customer_id)?.last_name}`
                            : 'Unknown Customer'}
                        </p>
                        <p className="text-sm text-gray-500">{customerLookup.get(selectedVehicle.customer_id)?.email}</p>
                      </div>
                    </div>
                  </div>

                  <div>
                    <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Key Details</h3>
                    <div className="grid grid-cols-2 gap-3 bg-gray-50 rounded-xl p-4 text-sm text-gray-700">
                      <div>
                        <p className="text-gray-500">VIN</p>
                        <p className="font-mono break-all">{selectedVehicle.vin || '—'}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Plate</p>
                        <p className="font-semibold">{selectedVehicle.license_plate || '—'}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Color</p>
                        <p className="font-semibold">{selectedVehicle.color || '—'}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Mileage</p>
                        <p className="font-semibold">
                          {typeof selectedVehicle.mileage === 'number'
                            ? `${selectedVehicle.mileage.toLocaleString()} mi`
                            : '—'}
                        </p>
                      </div>
                    </div>
                  </div>

                  {selectedVehicle.notes && (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Notes</h3>
                      <div className="bg-gray-50 rounded-xl p-4">
                        <p className="text-gray-700 whitespace-pre-wrap">{selectedVehicle.notes}</p>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {!isEditingInPanel && (
              <div className="border-t border-gray-200 px-6 py-4 bg-gray-50">
                <div className="flex items-center justify-end">
                  <button
                    onClick={handleEditFromDetail}
                    className="px-5 py-2.5 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                    Edit Vehicle
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
