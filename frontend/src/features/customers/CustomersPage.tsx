import { useState, useMemo, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { Customer, Vehicle, RepairOrder, RepairOrderStatus } from '../../types'
import { AlertTriangle, ArrowRight, DollarSign, Mail, MapPin, Pencil, Phone, Plus, Trash2, Truck, Wrench, X } from 'lucide-react'
import SlidePanel from '@/components/SlidePanel'
import MapboxAddressInput from '@/components/MapboxAddressInput'
import { formatUSPhone } from '@/utils/phone'
import ViewToggle from '@/components/ViewToggle'
import { useViewPreference } from '@/hooks/useViewPreference'

interface CustomerFormData {
  first_name: string
  last_name: string
  email: string
  phone: string
  billing_address_line1: string
  billing_address_line2: string
  billing_city: string
  billing_state: string
  billing_zip: string
  billing_country: string
  notes: string
  auto_approval_threshold: string
}

interface VehicleFormData {
  make: string
  model: string
  year: string
  vin: string
  unit_number: string
  license_plate: string
  color: string
  mileage: string
  notes: string
}

const emptyVehicleForm: VehicleFormData = {
  make: '',
  model: '',
  year: '',
  vin: '',
  unit_number: '',
  license_plate: '',
  color: '',
  mileage: '',
  notes: '',
}

const emptyForm: CustomerFormData = {
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  billing_address_line1: '',
  billing_address_line2: '',
  billing_city: '',
  billing_state: '',
  billing_zip: '',
  billing_country: 'USA',
  notes: '',
  auto_approval_threshold: '',
}

const US_STATES = [
  { code: '', name: 'Select State' },
  { code: 'AL', name: 'Alabama' },
  { code: 'AK', name: 'Alaska' },
  { code: 'AZ', name: 'Arizona' },
  { code: 'AR', name: 'Arkansas' },
  { code: 'CA', name: 'California' },
  { code: 'CO', name: 'Colorado' },
  { code: 'CT', name: 'Connecticut' },
  { code: 'DE', name: 'Delaware' },
  { code: 'FL', name: 'Florida' },
  { code: 'GA', name: 'Georgia' },
  { code: 'HI', name: 'Hawaii' },
  { code: 'ID', name: 'Idaho' },
  { code: 'IL', name: 'Illinois' },
  { code: 'IN', name: 'Indiana' },
  { code: 'IA', name: 'Iowa' },
  { code: 'KS', name: 'Kansas' },
  { code: 'KY', name: 'Kentucky' },
  { code: 'LA', name: 'Louisiana' },
  { code: 'ME', name: 'Maine' },
  { code: 'MD', name: 'Maryland' },
  { code: 'MA', name: 'Massachusetts' },
  { code: 'MI', name: 'Michigan' },
  { code: 'MN', name: 'Minnesota' },
  { code: 'MS', name: 'Mississippi' },
  { code: 'MO', name: 'Missouri' },
  { code: 'MT', name: 'Montana' },
  { code: 'NE', name: 'Nebraska' },
  { code: 'NV', name: 'Nevada' },
  { code: 'NH', name: 'New Hampshire' },
  { code: 'NJ', name: 'New Jersey' },
  { code: 'NM', name: 'New Mexico' },
  { code: 'NY', name: 'New York' },
  { code: 'NC', name: 'North Carolina' },
  { code: 'ND', name: 'North Dakota' },
  { code: 'OH', name: 'Ohio' },
  { code: 'OK', name: 'Oklahoma' },
  { code: 'OR', name: 'Oregon' },
  { code: 'PA', name: 'Pennsylvania' },
  { code: 'RI', name: 'Rhode Island' },
  { code: 'SC', name: 'South Carolina' },
  { code: 'SD', name: 'South Dakota' },
  { code: 'TN', name: 'Tennessee' },
  { code: 'TX', name: 'Texas' },
  { code: 'UT', name: 'Utah' },
  { code: 'VT', name: 'Vermont' },
  { code: 'VA', name: 'Virginia' },
  { code: 'WA', name: 'Washington' },
  { code: 'WV', name: 'West Virginia' },
  { code: 'WI', name: 'Wisconsin' },
  { code: 'WY', name: 'Wyoming' },
]

const CANADA_PROVINCES = [
  { code: '', name: 'Select Province' },
  { code: 'AB', name: 'Alberta' },
  { code: 'BC', name: 'British Columbia' },
  { code: 'MB', name: 'Manitoba' },
  { code: 'NB', name: 'New Brunswick' },
  { code: 'NL', name: 'Newfoundland and Labrador' },
  { code: 'NS', name: 'Nova Scotia' },
  { code: 'ON', name: 'Ontario' },
  { code: 'PE', name: 'Prince Edward Island' },
  { code: 'QC', name: 'Quebec' },
  { code: 'SK', name: 'Saskatchewan' },
]

const MEXICO_STATES = [
  { code: '', name: 'Select State' },
  { code: 'AGU', name: 'Aguascalientes' },
  { code: 'BCN', name: 'Baja California' },
  { code: 'BCS', name: 'Baja California Sur' },
  { code: 'CAM', name: 'Campeche' },
  { code: 'CHP', name: 'Chiapas' },
  { code: 'CHH', name: 'Chihuahua' },
  { code: 'COA', name: 'Coahuila' },
  { code: 'COL', name: 'Colima' },
  { code: 'DUR', name: 'Durango' },
  { code: 'GUA', name: 'Guanajuato' },
  { code: 'GRO', name: 'Guerrero' },
  { code: 'HID', name: 'Hidalgo' },
  { code: 'JAL', name: 'Jalisco' },
  { code: 'MEX', name: 'México' },
  { code: 'MIC', name: 'Michoacán' },
  { code: 'MOR', name: 'Morelos' },
  { code: 'NAY', name: 'Nayarit' },
  { code: 'NLE', name: 'Nuevo León' },
  { code: 'OAX', name: 'Oaxaca' },
  { code: 'PUE', name: 'Puebla' },
  { code: 'QUE', name: 'Querétaro' },
  { code: 'ROO', name: 'Quintana Roo' },
  { code: 'SLP', name: 'San Luis Potosí' },
  { code: 'SIN', name: 'Sinaloa' },
  { code: 'SON', name: 'Sonora' },
  { code: 'TAB', name: 'Tabasco' },
  { code: 'TAM', name: 'Tamaulipas' },
  { code: 'TLA', name: 'Tlaxcala' },
  { code: 'VER', name: 'Veracruz' },
  { code: 'YUC', name: 'Yucatán' },
  { code: 'ZAC', name: 'Zacatecas' },
]

export default function CustomersPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchType, setSearchType] = useState<'all' | 'name' | 'email' | 'phone'>('all')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null)
  const [formData, setFormData] = useState<CustomerFormData>(emptyForm)
  const [viewMode, setViewMode] = useViewPreference('customers')
  const [isMobile, setIsMobile] = useState(false)
  
  // Detail panel state
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null)
  const [isDetailOpen, setIsDetailOpen] = useState(false)
  const [isEditingInPanel, setIsEditingInPanel] = useState(false)
  const [vehiclesViewMode, setVehiclesViewMode] = useViewPreference('customer-vehicles')
  const [selectedVehicleInPanel, setSelectedVehicleInPanel] = useState<Vehicle | null>(null)

  // Mechanic lookup for vehicle history
  interface Mechanic {
    id: string
    first_name: string
    last_name: string
  }
  
  // Vehicle form state
  const [isVehicleModalOpen, setIsVehicleModalOpen] = useState(false)
  const [editingVehicle, setEditingVehicle] = useState<Vehicle | null>(null)
  const [vehicleFormData, setVehicleFormData] = useState<VehicleFormData>(emptyVehicleForm)
  const [deleteConfirmVehicle, setDeleteConfirmVehicle] = useState<Vehicle | null>(null)
  
  // Delete confirmation state
  const [deleteConfirmCustomer, setDeleteConfirmCustomer] = useState<Customer | null>(null)

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 1024)
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  const activeViewMode = isMobile ? 'list' : viewMode

  const queryClient = useQueryClient()

  const { data: customers, isLoading } = useQuery<Customer[]>({
    queryKey: ['customers'],
    queryFn: async () => {
      const response = await api.get('/customers')
      return response.data
    },
  })
  
  const { data: customerVehicles, isLoading: isLoadingVehicles } = useQuery<Vehicle[]>({
    queryKey: ['customerVehicles', selectedCustomer?.id],
    queryFn: async () => {
      if (!selectedCustomer?.id) return []
      const response = await api.get(`/customers/${selectedCustomer.id}/vehicles`)
      return response.data
    },
    enabled: !!selectedCustomer?.id && isDetailOpen,
  })

  const { data: customerRepairOrders, isLoading: isLoadingOrders } = useQuery<RepairOrder[]>({
    queryKey: ['customerRepairOrders', selectedCustomer?.id],
    queryFn: async () => {
      if (!selectedCustomer?.id) return []
      const response = await api.get('/repair-orders', { params: { customer_id: selectedCustomer.id } })
      return response.data
    },
    enabled: !!selectedCustomer?.id && isDetailOpen,
    staleTime: 0,
  })

  // Fetch mechanics for displaying who worked on the vehicle
  const { data: mechanics } = useQuery<Mechanic[]>({
    queryKey: ['mechanics'],
    queryFn: async () => {
      const response = await api.get('/mechanics')
      return response.data
    },
    enabled: !!selectedVehicleInPanel,
  })

  // Filter repair orders for the selected vehicle
  const vehicleRepairOrders = useMemo(() => {
    if (!selectedVehicleInPanel || !customerRepairOrders) return []
    return customerRepairOrders.filter(order => order.vehicle_id === selectedVehicleInPanel.id)
  }, [selectedVehicleInPanel, customerRepairOrders])

  // Create mechanic lookup map
  const mechanicLookup = useMemo(() => {
    const map = new Map<string, Mechanic>()
    mechanics?.forEach(m => map.set(m.id, m))
    return map
  }, [mechanics])

  const OPEN_ORDER_STATUSES: RepairOrderStatus[] = [
    'draft',
    'quoted',
    'approved',
    'in_progress',
  ]

  const createMutation = useMutation({
    mutationFn: async (data: CustomerFormData) => {
      const response = await api.post('/customers', data)
      return response.data
    },
    onSuccess: (customer: Customer) => {
      queryClient.invalidateQueries({ queryKey: ['customers'] })
      closeModal()
      toast.success(`Customer ${customer.first_name} ${customer.last_name} created`)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create customer')
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Partial<CustomerFormData> }) => {
      const response = await api.put(`/customers/${id}`, data)
      return response.data
    },
    onSuccess: (updatedCustomer: Customer) => {
      queryClient.invalidateQueries({ queryKey: ['customers'] })
      if (isEditingInPanel) {
        setSelectedCustomer(updatedCustomer)
        setIsEditingInPanel(false)
        resetForm()
      } else {
        closeModal()
      }
      toast.success('Customer updated')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update customer')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/customers/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] })
      setDeleteConfirmCustomer(null)
      setIsDetailOpen(false)
      setSelectedCustomer(null)
      toast.success('Customer deleted')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete customer')
    },
  })

  // Vehicle mutations
  const createVehicleMutation = useMutation({
    mutationFn: async ({ customerId, data }: { customerId: string; data: VehicleFormData }) => {
      const payload = {
        make: data.make,
        model: data.model,
        year: data.year ? parseInt(data.year) : null,
        vin: data.vin || null,
        unit_number: data.unit_number || null,
        license_plate: data.license_plate || null,
        color: data.color || null,
        mileage: data.mileage ? parseInt(data.mileage) : null,
        notes: data.notes || null,
      }
      const response = await api.post(`/customers/${customerId}/vehicles`, payload)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customerVehicles', selectedCustomer?.id] })
      closeVehicleModal()
      toast.success('Vehicle added')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to add vehicle')
    },
  })

  const updateVehicleMutation = useMutation({
    mutationFn: async ({ customerId, vehicleId, data }: { customerId: string; vehicleId: string; data: VehicleFormData }) => {
      const payload = {
        make: data.make,
        model: data.model,
        year: data.year ? parseInt(data.year) : null,
        vin: data.vin || null,
        unit_number: data.unit_number || null,
        license_plate: data.license_plate || null,
        color: data.color || null,
        mileage: data.mileage ? parseInt(data.mileage) : null,
        notes: data.notes || null,
      }
      const response = await api.put(`/customers/${customerId}/vehicles/${vehicleId}`, payload)
      return response.data
    },
    onSuccess: (updatedVehicle: Vehicle) => {
      queryClient.invalidateQueries({ queryKey: ['customerVehicles', selectedCustomer?.id] })
      if (selectedVehicleInPanel?.id === updatedVehicle.id) {
        setSelectedVehicleInPanel(updatedVehicle)
      }
      closeVehicleModal()
      toast.success('Vehicle updated')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update vehicle')
    },
  })

  const deleteVehicleMutation = useMutation({
    mutationFn: async ({ customerId, vehicleId }: { customerId: string; vehicleId: string }) => {
      await api.delete(`/customers/${customerId}/vehicles/${vehicleId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customerVehicles', selectedCustomer?.id] })
      setDeleteConfirmVehicle(null)
      if (selectedVehicleInPanel) {
        setSelectedVehicleInPanel(null)
      }
      toast.success('Vehicle deleted')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete vehicle')
    },
  })

  const resetForm = () => {
    setEditingCustomer(null)
    setFormData(emptyForm)
  }

  const openCreateModal = () => {
    resetForm()
    setIsEditingInPanel(false)
    setIsModalOpen(true)
  }

  const populateFormFromCustomer = (customer: Customer) => {
    setEditingCustomer(customer)
    setFormData({
      first_name: customer.first_name,
      last_name: customer.last_name,
      email: customer.email,
      phone: customer.phone || '',
      billing_address_line1: customer.billing_address_line1 || '',
      billing_address_line2: customer.billing_address_line2 || '',
      billing_city: customer.billing_city || '',
      billing_state: customer.billing_state || '',
      billing_zip: customer.billing_zip || '',
      billing_country: customer.billing_country || 'USA',
      notes: customer.notes || '',
      auto_approval_threshold: customer.auto_approval_threshold ? String(customer.auto_approval_threshold) : '',
    })
  }

  const closeModal = () => {
    setIsModalOpen(false)
    resetForm()
  }

  const openDetailPanel = (customer: Customer) => {
    setSelectedCustomer(customer)
    setIsDetailOpen(true)
    setIsEditingInPanel(false)
  }

  const closeDetailPanel = () => {
    setIsDetailOpen(false)
    setSelectedCustomer(null)
    setIsEditingInPanel(false)
    setSelectedVehicleInPanel(null)
    resetForm()
  }

  const handleEditFromDetail = () => {
    if (selectedCustomer) {
      populateFormFromCustomer(selectedCustomer)
      setIsEditingInPanel(true)
    }
  }

  const handleDeleteClick = (customer: Customer) => {
    setDeleteConfirmCustomer(customer)
  }

  // Vehicle form helpers
  const openAddVehicleModal = () => {
    setEditingVehicle(null)
    setVehicleFormData(emptyVehicleForm)
    setIsVehicleModalOpen(true)
  }

  const openEditVehicleModal = (vehicle: Vehicle) => {
    setEditingVehicle(vehicle)
    setVehicleFormData({
      make: vehicle.make,
      model: vehicle.model,
      year: vehicle.year?.toString() || '',
      vin: vehicle.vin || '',
      unit_number: vehicle.unit_number || '',
      license_plate: vehicle.license_plate || '',
      color: vehicle.color || '',
      mileage: vehicle.mileage?.toString() || '',
      notes: vehicle.notes || '',
    })
    setIsVehicleModalOpen(true)
  }

  const closeVehicleModal = () => {
    setIsVehicleModalOpen(false)
    setEditingVehicle(null)
    setVehicleFormData(emptyVehicleForm)
  }

  const handleVehicleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setVehicleFormData((prev) => ({ ...prev, [name]: value }))
  }

  const handleVehicleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedCustomer) return

    if (!vehicleFormData.make.trim() || !vehicleFormData.model.trim()) {
      toast.error('Make and model are required')
      return
    }

    if (editingVehicle) {
      updateVehicleMutation.mutate({
        customerId: selectedCustomer.id,
        vehicleId: editingVehicle.id,
        data: vehicleFormData,
      })
    } else {
      createVehicleMutation.mutate({
        customerId: selectedCustomer.id,
        data: vehicleFormData,
      })
    }
  }

  const handleDeleteVehicleClick = (vehicle: Vehicle) => {
    setDeleteConfirmVehicle(vehicle)
  }

  const confirmDeleteVehicle = () => {
    if (deleteConfirmVehicle && selectedCustomer) {
      deleteVehicleMutation.mutate({
        customerId: selectedCustomer.id,
        vehicleId: deleteConfirmVehicle.id,
      })
    }
  }

  const cancelPanelEditing = () => {
    setIsEditingInPanel(false)
    resetForm()
  }

  const confirmDelete = () => {
    if (deleteConfirmCustomer) {
      deleteMutation.mutate(deleteConfirmCustomer.id)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.first_name.trim() || !formData.last_name.trim() || !formData.email.trim()) {
      toast.error('First name, last name, and email are required')
      return
    }

    const payload = {
      ...formData,
      auto_approval_threshold: formData.auto_approval_threshold
        ? parseFloat(formData.auto_approval_threshold)
        : null,
    }

    if (editingCustomer) {
      updateMutation.mutate({ id: editingCustomer.id, data: payload as any })
    } else {
      createMutation.mutate(payload as any)
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    
    // Format phone number
    if (name === 'phone') {
      setFormData((prev) => ({ ...prev, [name]: formatUSPhone(value) }))
      return
    }
    
    // Reset state when country changes
    if (name === 'billing_country') {
      setFormData((prev) => ({ ...prev, [name]: value, billing_state: '' }))
      return
    }
    
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  // ZIP code lookup for auto-filling city/state
  const [isLookingUpZip, setIsLookingUpZip] = useState(false)
  
  const handleZipChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const zip = e.target.value.replace(/\D/g, '').slice(0, 5)
    setFormData((prev) => ({ ...prev, billing_zip: zip }))
    
    // Only lookup for US ZIP codes with 5 digits
    if (zip.length === 5 && formData.billing_country === 'USA') {
      setIsLookingUpZip(true)
      try {
        const response = await fetch(`https://api.zippopotam.us/us/${zip}`)
        if (response.ok) {
          const data = await response.json()
          if (data.places && data.places.length > 0) {
            const place = data.places[0]
            setFormData((prev) => ({
              ...prev,
              billing_city: place['place name'],
              billing_state: place['state abbreviation'],
            }))
          }
        }
      } catch {
        // Silently fail - user can still enter manually
      } finally {
        setIsLookingUpZip(false)
      }
    }
  }, [formData.billing_country])

  // Get states/provinces based on country
  const getRegions = () => {
    switch (formData.billing_country) {
      case 'Canada':
        return CANADA_PROVINCES
      case 'Mexico':
        return MEXICO_STATES
      default:
        return US_STATES
    }
  }

  const getRegionLabel = () => {
    switch (formData.billing_country) {
      case 'Canada':
        return 'Province'
      case 'Mexico':
        return 'State'
      default:
        return 'State'
    }
  }

  const getPostalLabel = () => {
    switch (formData.billing_country) {
      case 'Canada':
        return 'Postal Code'
      default:
        return 'ZIP'
    }
  }

  const vehicleCount = customerVehicles?.length || 0

  const repairOrderStats = useMemo(() => {
    const total = customerRepairOrders?.length || 0
    const open = customerRepairOrders?.filter((ro) => OPEN_ORDER_STATUSES.includes(ro.status)).length || 0
    const completed = customerRepairOrders?.filter((ro) => ro.status === 'completed' || ro.status === 'paid' || ro.status === 'invoiced').length || 0
    return { total, open, completed }
  }, [customerRepairOrders])

  const renderCustomerForm = (onCancel: () => void) => (
    <form onSubmit={handleSubmit} className="p-6 space-y-6">
      {/* Name Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            First Name <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            name="first_name"
            value={formData.first_name}
            onChange={handleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="John"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Last Name <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            name="last_name"
            value={formData.last_name}
            onChange={handleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="Doe"
            required
          />
        </div>
      </div>

      {/* Contact Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Email <span className="text-red-500">*</span>
          </label>
          <input
            type="email"
            name="email"
            value={formData.email}
            onChange={handleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="john@example.com"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Phone
          </label>
          <input
            type="tel"
            name="phone"
            value={formData.phone}
            onChange={handleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="(555) 123-4567"
          />
        </div>
      </div>

      {/* Address Section */}
      <div className="border-t border-gray-200 pt-6">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Billing Address</h3>
        
        <div className="space-y-4">
          {/* Country first - affects other fields */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Country
            </label>
            <select
              name="billing_country"
              value={formData.billing_country}
              onChange={handleInputChange}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            >
              <option value="USA">🇺🇸 United States</option>
              <option value="Canada">🇨🇦 Canada</option>
              <option value="Mexico">🇲🇽 Mexico</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Address Line 1
            </label>
            <MapboxAddressInput
              name="billing_address_line1"
              value={formData.billing_address_line1}
              onChange={(e) => setFormData((prev) => ({ ...prev, billing_address_line1: e.target.value }))}
              autoComplete="street-address"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
              placeholder="Start typing address..."
              options={{
                country: formData.billing_country === 'USA' ? 'US' : formData.billing_country === 'Canada' ? 'CA' : 'MX',
                language: 'en',
              }}
              onAddressSelect={({ feature, formatted }) => {
                if (feature?.properties) {
                  const props = feature.properties as Record<string, any>
                  setFormData((prev) => ({
                    ...prev,
                    billing_address_line1:
                      props.address_line1 ||
                      (typeof props.full_address === 'string' ? props.full_address.split(',')[0] : undefined) ||
                      formatted ||
                      prev.billing_address_line1,
                    billing_city: props.place || props.locality || props.place_name || prev.billing_city,
                    billing_state: props.region_code || props.region || prev.billing_state,
                    billing_zip: props.postcode || prev.billing_zip,
                  }))
                }
              }}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Address Line 2
            </label>
            <input
              type="text"
              name="billing_address_line2"
              value={formData.billing_address_line2}
              onChange={handleInputChange}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
              placeholder="Suite 100, Building A"
            />
          </div>

          {/* ZIP first for US - enables auto-fill */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {getPostalLabel()}
                {formData.billing_country === 'USA' && (
                  <span className="text-xs text-gray-400 ml-1">(auto-fills)</span>
                )}
              </label>
              <div className="relative">
                <input
                  type="text"
                  name="billing_zip"
                  value={formData.billing_zip}
                  onChange={handleZipChange}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                  placeholder={formData.billing_country === 'USA' ? '53202' : formData.billing_country === 'Canada' ? 'A1A 1A1' : '01000'}
                  maxLength={formData.billing_country === 'Canada' ? 7 : 5}
                />
                {isLookingUpZip && (
                  <div className="absolute right-3 top-1/2 -translate-y-1/2">
                    <svg className="animate-spin w-4 h-4 text-amber-500" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                  </div>
                )}
              </div>
            </div>
            <div className="col-span-2 sm:col-span-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                City
              </label>
              <input
                type="text"
                name="billing_city"
                value={formData.billing_city}
                onChange={handleInputChange}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                placeholder="Milwaukee"
              />
            </div>
            <div className="col-span-2 sm:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {getRegionLabel()}
              </label>
              <select
                name="billing_state"
                value={formData.billing_state}
                onChange={handleInputChange}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
              >
                {getRegions().map((region) => (
                  <option key={region.code} value={region.code}>
                    {region.code ? `${region.code} - ${region.name}` : region.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Auto-Approval Threshold */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Auto-Approve Threshold
        </label>
        <div className="relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
          <input
            type="number"
            name="auto_approval_threshold"
            value={formData.auto_approval_threshold}
            onChange={handleInputChange}
            step="0.01"
            min="0"
            className="w-full pl-7 pr-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="Leave empty to disable"
          />
        </div>
        <p className="text-xs text-gray-500 mt-1">Quotes at or below this amount will be auto-approved. Leave empty to require manual approval.</p>
      </div>

      {/* Notes */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Notes
        </label>
        <textarea
          name="notes"
          value={formData.notes}
          onChange={handleInputChange}
          rows={3}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors resize-none"
          placeholder="Any additional notes about this customer..."
        />
      </div>

      {/* Actions */}
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
          {editingCustomer ? 'Save Changes' : 'Add Customer'}
        </button>
      </div>
    </form>
  )

  const renderVehicleForm = () => (
    <form onSubmit={handleVehicleSubmit} className="p-6 space-y-4">
      {/* Make & Model */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Make <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            name="make"
            value={vehicleFormData.make}
            onChange={handleVehicleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="Ford"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Model <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            name="model"
            value={vehicleFormData.model}
            onChange={handleVehicleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="F-150"
            required
          />
        </div>
      </div>

      {/* Year & Color */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Year</label>
          <input
            type="number"
            name="year"
            value={vehicleFormData.year}
            onChange={handleVehicleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="2024"
            min="1900"
            max="2100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Color</label>
          <input
            type="text"
            name="color"
            value={vehicleFormData.color}
            onChange={handleVehicleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="White"
          />
        </div>
      </div>

      {/* VIN & Unit Number */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">VIN</label>
          <input
            type="text"
            name="vin"
            value={vehicleFormData.vin}
            onChange={handleVehicleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors font-mono"
            placeholder="1FTFW1E50MFA00000"
            maxLength={17}
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Unit Number</label>
          <input
            type="text"
            name="unit_number"
            value={vehicleFormData.unit_number}
            onChange={handleVehicleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors font-mono"
            placeholder="UNIT-001"
          />
        </div>
      </div>

      {/* License Plate & Mileage */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">License Plate</label>
          <input
            type="text"
            name="license_plate"
            value={vehicleFormData.license_plate}
            onChange={handleVehicleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors uppercase"
            placeholder="ABC-1234"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Mileage</label>
          <input
            type="number"
            name="mileage"
            value={vehicleFormData.mileage}
            onChange={handleVehicleInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="50000"
            min="0"
          />
        </div>
      </div>

      {/* Notes */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
        <textarea
          name="notes"
          value={vehicleFormData.notes}
          onChange={handleVehicleInputChange}
          rows={2}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors resize-none"
          placeholder="Any additional notes..."
        />
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200">
        <button
          type="button"
          onClick={closeVehicleModal}
          className="px-5 py-2.5 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={createVehicleMutation.isPending || updateVehicleMutation.isPending}
          className="px-5 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-300 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
        >
          {(createVehicleMutation.isPending || updateVehicleMutation.isPending) && (
            <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          {editingVehicle ? 'Save Changes' : 'Add Vehicle'}
        </button>
      </div>
    </form>
  )

  const filteredCustomers = useMemo(() => {
    if (!customers || !searchQuery.trim()) return customers

    const query = searchQuery.toLowerCase().trim()
    
    return customers.filter((customer) => {
      const nameMatch = `${customer.first_name} ${customer.last_name}`.toLowerCase().includes(query)
      const emailMatch = customer.email?.toLowerCase().includes(query)
      const phoneMatch = customer.phone?.toLowerCase().includes(query)

      switch (searchType) {
        case 'name':
          return nameMatch
        case 'email':
          return emailMatch
        case 'phone':
          return phoneMatch
        default:
          return nameMatch || emailMatch || phoneMatch
      }
    })
  }, [customers, searchQuery, searchType])

  if (isLoading) {
    return <div className="text-white">Loading...</div>
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 sm:mb-6">
        <h1 className="text-xl sm:text-2xl font-bold text-white">Customers</h1>
        <button 
          onClick={openCreateModal}
          className="mt-3 sm:mt-0 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors"
        >
          + Add Customer
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
              placeholder="Search customers..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-white rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>

          <div className="flex gap-2">
            {[
              { value: 'all', label: 'All' },
              { value: 'name', label: 'Name' },
              { value: 'email', label: 'Email' },
              { value: 'phone', label: 'Phone' },
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

        {searchQuery && (
          <div className="mt-3 text-sm text-white/70">
            Found {filteredCustomers?.length || 0} customer{filteredCustomers?.length !== 1 ? 's' : ''}
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
                    <th className="px-4 py-3 text-left font-medium">Customer</th>
                    <th className="px-4 py-3 text-left font-medium hidden sm:table-cell">Email</th>
                    <th className="px-4 py-3 text-left font-medium hidden md:table-cell">Phone</th>
                    <th className="px-4 py-3 text-left font-medium hidden lg:table-cell">Location</th>
                    <th className="px-4 py-3 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/10">
                  {filteredCustomers?.map((customer) => (
                    <tr
                      key={customer.id}
                      onClick={() => openDetailPanel(customer)}
                      className="hover:bg-white/5 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-amber-500 flex items-center justify-center flex-shrink-0">
                            <span className="text-white font-bold text-xs">
                              {customer.first_name.charAt(0)}{customer.last_name.charAt(0)}
                            </span>
                          </div>
                          <span className="text-white font-medium">{customer.first_name} {customer.last_name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-white/70 hidden sm:table-cell">{customer.email}</td>
                      <td className="px-4 py-3 text-white/70 hidden md:table-cell">{customer.phone || '—'}</td>
                      <td className="px-4 py-3 text-white/70 hidden lg:table-cell">
                        {customer.billing_city && customer.billing_state
                          ? `${customer.billing_city}, ${customer.billing_state}`
                          : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            openDetailPanel(customer)
                          }}
                          className="text-amber-400 hover:text-amber-300 text-sm font-medium"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            /* Cards View */
            <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filteredCustomers?.map((customer) => (
                <div 
                  key={customer.id}
                  onClick={() => openDetailPanel(customer)}
                  className="aspect-square bg-gradient-to-br from-yellow-50 via-amber-100 to-yellow-200 p-4 sm:p-5 rounded-xl shadow-lg flex flex-col justify-between hover:shadow-xl transition-shadow cursor-pointer"
                >
                  <div>
                    <div className="w-12 h-12 rounded-full bg-amber-500 flex items-center justify-center mb-3">
                      <span className="text-white font-bold text-lg">
                        {customer.first_name.charAt(0)}{customer.last_name.charAt(0)}
                      </span>
                    </div>
                    <h3 className="text-lg font-bold text-slate-800 leading-tight">
                      {customer.first_name} {customer.last_name}
                    </h3>
                  </div>
                  
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center gap-2 text-slate-600">
                      <Mail className="w-4 h-4 flex-shrink-0" />
                      <span className="truncate">{customer.email}</span>
                    </div>
                    {customer.phone && (
                      <div className="flex items-center gap-2 text-slate-600">
                        <Phone className="w-4 h-4 flex-shrink-0" />
                        <span>{customer.phone}</span>
                      </div>
                    )}
                    {customer.billing_city && customer.billing_state && (
                      <div className="flex items-center gap-2 text-slate-600">
                        <MapPin className="w-4 h-4 flex-shrink-0" />
                        <span>{customer.billing_city}, {customer.billing_state}</span>
                      </div>
                    )}
                  </div>

                  <div className="pt-3 border-t border-amber-200/50">
                    <button 
                      onClick={(e) => {
                        e.stopPropagation()
                        openDetailPanel(customer)
                      }}
                      className="w-full py-2 text-sm font-medium text-amber-700 hover:text-amber-900 hover:bg-amber-200/50 rounded-lg transition-colors inline-flex items-center justify-center gap-1"
                    >
                      View Details
                      <ArrowRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}

              <div 
                onClick={openCreateModal}
                className="aspect-square bg-white/20 border-2 border-dashed border-white/40 p-4 sm:p-5 rounded-xl flex flex-col items-center justify-center cursor-pointer hover:bg-white/30 hover:border-white/60 transition-all"
              >
                <div className="w-12 h-12 rounded-full bg-white/30 flex items-center justify-center mb-3">
                  <Plus className="w-6 h-6 text-white" />
                </div>
                <span className="text-white font-medium">Add Customer</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {filteredCustomers?.length === 0 && searchQuery && (
        <div className="text-center py-12 text-white/70">
          No customers match your search. Try a different term.
        </div>
      )}

      {(!customers || customers.length === 0) && !searchQuery && (
        <div className="text-center py-12 text-white/70">
          No customers found. Add your first customer to get started.
        </div>
      )}

      {/* Add/Edit Customer Modal */}
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
                    {editingCustomer ? 'Edit Customer' : 'Add New Customer'}
                  </h2>
                <button
                  onClick={closeModal}
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <X className="w-5 h-5 text-gray-500" />
                </button>
              </div>
              </div>

              {/* Form */}
              {renderCustomerForm(closeModal)}
            </div>
          </div>
        </div>
      )}

      {/* Customer Detail Slide-out Panel */}
      <SlidePanel
        isOpen={isDetailOpen && !!selectedCustomer}
        onClose={closeDetailPanel}
        title={
          selectedVehicleInPanel
            ? `${selectedVehicleInPanel.year ? `${selectedVehicleInPanel.year} ` : ''}${selectedVehicleInPanel.make} ${selectedVehicleInPanel.model}`
            : selectedCustomer
            ? `${selectedCustomer.first_name} ${selectedCustomer.last_name}`
            : ''
        }
        subtitle={
          selectedVehicleInPanel
            ? selectedVehicleInPanel.license_plate || undefined
            : selectedCustomer
            ? `Customer since ${new Date(selectedCustomer.created_at).toLocaleDateString()}`
            : undefined
        }
        headerVariant={selectedVehicleInPanel ? 'slate' : 'amber'}
        headerIcon={
          selectedVehicleInPanel ? (
            <div className="w-12 h-12 rounded-lg bg-white/20 flex items-center justify-center">
              <Truck className="w-6 h-6" />
            </div>
          ) : selectedCustomer ? (
            <div className="w-16 h-16 rounded-full bg-white/20 flex items-center justify-center">
              <span className="text-2xl font-bold">
                {selectedCustomer.first_name.charAt(0)}{selectedCustomer.last_name.charAt(0)}
              </span>
            </div>
          ) : null
        }
        onBack={selectedVehicleInPanel ? () => setSelectedVehicleInPanel(null) : undefined}
        backLabel={selectedVehicleInPanel && selectedCustomer ? `Back to ${selectedCustomer.first_name}` : undefined}
        footer={
          !isEditingInPanel && !selectedVehicleInPanel && selectedCustomer ? (
            <div className="flex items-center justify-between">
              <button
                onClick={() => handleDeleteClick(selectedCustomer)}
                className="px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors text-sm font-medium flex items-center gap-2"
              >
                <Trash2 className="w-4 h-4" />
                Delete
              </button>
              <button
                onClick={handleEditFromDetail}
                className="px-5 py-2.5 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
              >
                <Pencil className="w-4 h-4" />
                Edit Customer
              </button>
            </div>
          ) : undefined
        }
      >
        {!selectedCustomer ? null : selectedVehicleInPanel ? (
          /* Vehicle Detail Content */
          <div className="p-6 space-y-6">
            {/* Owner */}
            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Owner</h3>
              <div className="bg-gray-50 rounded-xl p-4 flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center text-amber-700 font-bold">
                  {selectedCustomer.first_name.charAt(0)}{selectedCustomer.last_name.charAt(0)}
                </div>
                <div>
                  <p className="text-gray-900 font-semibold">
                    {selectedCustomer.first_name} {selectedCustomer.last_name}
                  </p>
                  <p className="text-sm text-gray-500">{selectedCustomer.email}</p>
                </div>
              </div>
            </div>

            {/* Key Details */}
            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Key Details</h3>
              <div className="grid grid-cols-2 gap-3 bg-gray-50 rounded-xl p-4 text-sm text-gray-700">
                <div>
                  <p className="text-gray-500">VIN</p>
                  <p className="font-mono break-all">{selectedVehicleInPanel.vin || '—'}</p>
                </div>
                <div>
                  <p className="text-gray-500">Plate</p>
                  <p className="font-semibold">{selectedVehicleInPanel.license_plate || '—'}</p>
                </div>
                <div>
                  <p className="text-gray-500">Color</p>
                  <p className="font-semibold">{selectedVehicleInPanel.color || '—'}</p>
                </div>
                <div>
                  <p className="text-gray-500">Mileage</p>
                  <p className="font-semibold">
                    {typeof selectedVehicleInPanel.mileage === 'number'
                      ? `${selectedVehicleInPanel.mileage.toLocaleString()} mi`
                      : '—'}
                  </p>
                </div>
              </div>
            </div>

            {/* Unit Number */}
            {selectedVehicleInPanel.unit_number && (
              <div>
                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Unit Number</h3>
                <div className="bg-amber-50 rounded-xl p-4">
                  <p className="text-amber-800 font-mono font-semibold text-lg">{selectedVehicleInPanel.unit_number}</p>
                </div>
              </div>
            )}

            {/* Notes */}
            {selectedVehicleInPanel.notes && (
              <div>
                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Notes</h3>
                <div className="bg-gray-50 rounded-xl p-4">
                  <p className="text-gray-700 whitespace-pre-wrap">{selectedVehicleInPanel.notes}</p>
                </div>
              </div>
            )}

            {/* Repair History */}
            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
                Repair History ({vehicleRepairOrders.length})
              </h3>
              {vehicleRepairOrders.length === 0 ? (
                <div className="bg-gray-50 rounded-xl p-4 text-center">
                  <p className="text-gray-500 text-sm">No repair orders for this vehicle yet</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {vehicleRepairOrders.map((order) => {
                    const mechanic = order.assigned_mechanic_id ? mechanicLookup.get(order.assigned_mechanic_id) : null
                    const statusColors: Record<string, string> = {
                      draft: 'bg-gray-100 text-gray-700',
                      quoted: 'bg-blue-100 text-blue-700',
                      declined: 'bg-red-100 text-red-700',
                      approved: 'bg-cyan-100 text-cyan-700',
                      assigned: 'bg-amber-100 text-amber-700',
                      acknowledged: 'bg-amber-100 text-amber-700',
                      in_progress: 'bg-amber-100 text-amber-700',
                      pending_review: 'bg-purple-100 text-purple-700',
                      completed: 'bg-green-100 text-green-700',
                      invoiced: 'bg-indigo-100 text-indigo-700',
                      paid: 'bg-green-100 text-green-700',
                      cancelled: 'bg-gray-100 text-gray-500',
                    }
                    return (
                      <div
                        key={order.id}
                        className="bg-gray-50 rounded-xl p-3 hover:bg-gray-100 transition-colors cursor-pointer"
                        onClick={() => {
                          // Navigate to repair order
                          window.location.href = `/dashboard/repair-orders?selected=${order.id}`
                        }}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-mono text-sm font-semibold text-gray-900">#{order.order_number}</span>
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[order.status] || 'bg-gray-100 text-gray-700'}`}>
                            {order.status.replace(/_/g, ' ')}
                          </span>
                        </div>
                        <p className="text-sm text-gray-600 line-clamp-1">{order.description || 'No description'}</p>
                        <div className="flex items-center justify-between mt-2 text-xs text-gray-500">
                          <span>{new Date(order.created_at).toLocaleDateString()}</span>
                          {mechanic && (
                            <span className="flex items-center gap-1">
                              <Wrench className="w-3 h-3" />
                              {mechanic.first_name} {mechanic.last_name}
                            </span>
                          )}
                          <span className="font-semibold text-gray-700">${parseFloat(order.total_cost).toFixed(2)}</span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Vehicle Actions */}
            <div className="flex items-center justify-between pt-4 border-t border-gray-200">
              <button
                onClick={() => handleDeleteVehicleClick(selectedVehicleInPanel)}
                className="px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors text-sm font-medium flex items-center gap-2"
              >
                <Trash2 className="w-4 h-4" />
                Delete Vehicle
              </button>
              <button
                onClick={() => openEditVehicleModal(selectedVehicleInPanel)}
                className="px-5 py-2.5 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
              >
                <Pencil className="w-4 h-4" />
                Edit Vehicle
              </button>
            </div>
          </div>
        ) : isEditingInPanel ? (
                <div className="p-6 space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs text-gray-500 uppercase tracking-wide">Editing</p>
                      <h3 className="text-xl font-bold text-gray-900">Customer Details</h3>
                    </div>
                    <button
                      onClick={cancelPanelEditing}
                      className="px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                  <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
                    {renderCustomerForm(cancelPanelEditing)}
                  </div>
                </div>
              ) : (
                <div className="p-6 space-y-6">
                  {/* Contact Information */}
                  <div>
                    <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Contact Information</h3>
                    <div className="bg-gray-50 rounded-xl p-4 space-y-3">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                          <Mail className="w-5 h-5 text-amber-600" />
                        </div>
                        <div>
                          <p className="text-xs text-gray-500">Email</p>
                          <a href={`mailto:${selectedCustomer.email}`} className="text-gray-900 hover:text-amber-600 font-medium">
                            {selectedCustomer.email}
                          </a>
                        </div>
                      </div>
                      {selectedCustomer.phone && (
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                            <Phone className="w-5 h-5 text-green-600" />
                          </div>
                          <div>
                            <p className="text-xs text-gray-500">Phone</p>
                            <a href={`tel:${selectedCustomer.phone}`} className="text-gray-900 hover:text-amber-600 font-medium">
                              {selectedCustomer.phone}
                            </a>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Auto-Approval Threshold */}
                  {selectedCustomer.auto_approval_threshold && (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                          <DollarSign className="w-5 h-5 text-amber-600" />
                        </div>
                        <div>
                          <p className="text-xs text-amber-600 font-medium">Auto-Approve Threshold</p>
                          <p className="text-amber-900 font-bold text-lg">
                            ${parseFloat(selectedCustomer.auto_approval_threshold).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                          </p>
                        </div>
                      </div>
                      <p className="text-xs text-amber-600 mt-2">Quotes at or below this amount are approved automatically.</p>
                    </div>
                  )}

                  {/* Billing Address */}
                  {(selectedCustomer.billing_address_line1 || selectedCustomer.billing_city) && (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Billing Address</h3>
                      <div className="bg-gray-50 rounded-xl p-4">
                        <div className="flex items-start gap-3">
                          <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center flex-shrink-0">
                            <MapPin className="w-5 h-5 text-blue-600" />
                          </div>
                          <div className="text-gray-900">
                            {selectedCustomer.billing_address_line1 && <p>{selectedCustomer.billing_address_line1}</p>}
                            {selectedCustomer.billing_address_line2 && <p>{selectedCustomer.billing_address_line2}</p>}
                            <p>
                              {[selectedCustomer.billing_city, selectedCustomer.billing_state, selectedCustomer.billing_zip]
                                .filter(Boolean)
                                .join(', ')}
                            </p>
                            {selectedCustomer.billing_country && <p>{selectedCustomer.billing_country}</p>}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Notes */}
                  {selectedCustomer.notes && (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Notes</h3>
                      <div className="bg-gray-50 rounded-xl p-4">
                        <p className="text-gray-700 whitespace-pre-wrap">{selectedCustomer.notes}</p>
                      </div>
                    </div>
                  )}

                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Vehicles</h3>
                      <div className="flex items-center gap-2">
                        {isLoadingVehicles && <span className="text-xs text-gray-400">Loading...</span>}
                        {customerVehicles && customerVehicles.length > 1 && (
                          <ViewToggle 
                            value={vehiclesViewMode} 
                            onChange={setVehiclesViewMode}
                            variant="light"
                          />
                        )}
                        <button
                          onClick={openAddVehicleModal}
                          className="px-3 py-1.5 text-xs font-medium text-amber-600 bg-amber-50 hover:bg-amber-100 rounded-lg transition-colors flex items-center gap-1"
                        >
                          <Plus className="w-3.5 h-3.5" />
                          Add
                        </button>
                      </div>
                    </div>
                    {customerVehicles && customerVehicles.length > 0 ? (
                      vehiclesViewMode === 'list' ? (
                        <div className="bg-gray-50 rounded-xl border border-gray-100 overflow-hidden">
                          <table className="w-full text-sm">
                            <thead className="bg-gray-100 text-gray-600 text-xs uppercase tracking-wider">
                              <tr>
                                <th className="px-3 py-2 text-left font-medium">Vehicle</th>
                                <th className="px-3 py-2 text-left font-medium">Plate</th>
                                <th className="px-3 py-2 text-right font-medium">Actions</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {customerVehicles.map((vehicle) => (
                                <tr 
                                  key={vehicle.id} 
                                  onClick={() => setSelectedVehicleInPanel(vehicle)}
                                  className="hover:bg-gray-100/50 cursor-pointer group"
                                >
                                  <td className="px-3 py-2.5 text-gray-900 font-medium">
                                    {vehicle.year ? `${vehicle.year} ` : ''}{vehicle.make} {vehicle.model}
                                    {vehicle.color && <span className="text-gray-500 font-normal"> · {vehicle.color}</span>}
                                  </td>
                                  <td className="px-3 py-2.5">
                                    {vehicle.license_plate ? (
                                      <span className="text-xs font-medium text-amber-700 bg-amber-100 rounded px-1.5 py-0.5">
                                        {vehicle.license_plate}
                                      </span>
                                    ) : (
                                      <span className="text-gray-400">—</span>
                                    )}
                                  </td>
                                  <td className="px-3 py-2.5 text-right">
                                    <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          openEditVehicleModal(vehicle)
                                        }}
                                        className="p-1.5 text-gray-500 hover:text-amber-600 hover:bg-amber-50 rounded transition-colors"
                                        title="Edit"
                                      >
                                        <Pencil className="w-3.5 h-3.5" />
                                      </button>
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          handleDeleteVehicleClick(vehicle)
                                        }}
                                        className="p-1.5 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                                        title="Delete"
                                      >
                                        <Trash2 className="w-3.5 h-3.5" />
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {customerVehicles.map((vehicle) => (
                            <div 
                              key={vehicle.id} 
                              className="bg-gray-50 rounded-xl p-4 border border-gray-100 hover:bg-gray-100 hover:border-gray-200 transition-colors group relative"
                            >
                              <div 
                                onClick={() => setSelectedVehicleInPanel(vehicle)}
                                className="cursor-pointer"
                              >
                                <p className="text-sm font-semibold text-gray-900 mb-1">
                                  {vehicle.year ? `${vehicle.year} ` : ''}{vehicle.make} {vehicle.model}
                                </p>
                                {vehicle.license_plate && (
                                  <span className="inline-block text-xs font-medium text-amber-700 bg-amber-100 rounded px-2 py-0.5 mb-2">
                                    {vehicle.license_plate}
                                  </span>
                                )}
                                <div className="text-xs text-gray-500 space-y-0.5 mt-2">
                                  {vehicle.color && <p>{vehicle.color}</p>}
                                  <p>{typeof vehicle.mileage === 'number' ? `${vehicle.mileage.toLocaleString()} mi` : 'No mileage'}</p>
                                </div>
                              </div>
                              <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    openEditVehicleModal(vehicle)
                                  }}
                                  className="p-1.5 text-gray-500 hover:text-amber-600 bg-white hover:bg-amber-50 rounded shadow-sm transition-colors"
                                  title="Edit"
                                >
                                  <Pencil className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    handleDeleteVehicleClick(vehicle)
                                  }}
                                  className="p-1.5 text-gray-500 hover:text-red-600 bg-white hover:bg-red-50 rounded shadow-sm transition-colors"
                                  title="Delete"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )
                    ) : (
                      <div className="bg-gray-50 rounded-xl p-6 text-center border border-gray-100">
                        <Truck className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                        <p className="text-sm text-gray-500 mb-3">No vehicles on file</p>
                        <button
                          onClick={openAddVehicleModal}
                          className="px-4 py-2 text-sm font-medium text-amber-600 bg-amber-50 hover:bg-amber-100 rounded-lg transition-colors inline-flex items-center gap-1.5"
                        >
                          <Plus className="w-4 h-4" />
                          Add First Vehicle
                        </button>
                      </div>
                    )}
                  </div>

                  <div>
                    <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Activity</h3>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-gray-50 rounded-xl p-4 text-center">
                        <p className="text-2xl font-bold text-gray-900">
                          {isLoadingVehicles ? '—' : vehicleCount}
                        </p>
                        <p className="text-xs text-gray-500">Vehicles</p>
                      </div>
                      <div className="bg-gray-50 rounded-xl p-4 text-center space-y-1">
                        <p className="text-2xl font-bold text-gray-900">
                          {isLoadingOrders ? '—' : repairOrderStats.total}
                        </p>
                        <p className="text-xs text-gray-500">Repair Orders</p>
                        {!isLoadingOrders && (
                          <p className="text-[11px] text-gray-500">
                            {repairOrderStats.open} open · {repairOrderStats.completed} completed
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}
      </SlidePanel>

      {/* Delete Confirmation Modal */}
      {deleteConfirmCustomer && (
        <div className="fixed inset-0 z-[60] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {/* Backdrop */}
            <div 
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setDeleteConfirmCustomer(null)}
            />
            
              {/* Modal */}
              <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
                <div className="flex items-center gap-4 mb-4">
                  <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                    <AlertTriangle className="w-6 h-6 text-red-600" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-gray-900">Delete Customer</h3>
                    <p className="text-sm text-gray-500">This action cannot be undone</p>
                  </div>
              </div>
              
              <p className="text-gray-700 mb-6">
                Are you sure you want to delete <span className="font-semibold">{deleteConfirmCustomer.first_name} {deleteConfirmCustomer.last_name}</span>? 
                All associated data will be permanently removed.
              </p>

              <div className="flex items-center justify-end gap-3">
                <button
                  onClick={() => setDeleteConfirmCustomer(null)}
                  className="px-4 py-2 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmDelete}
                  disabled={deleteMutation.isPending}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
                >
                  {deleteMutation.isPending && (
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                  )}
                  Delete Customer
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add/Edit Vehicle Modal */}
      {isVehicleModalOpen && selectedCustomer && (
        <div className="fixed inset-0 z-[60] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {/* Backdrop */}
            <div 
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={closeVehicleModal}
            />
            
            {/* Modal */}
            <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
              {/* Header */}
              <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 rounded-t-2xl">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-gray-900">
                      {editingVehicle ? 'Edit Vehicle' : 'Add Vehicle'}
                    </h2>
                    <p className="text-sm text-gray-500">
                      for {selectedCustomer.first_name} {selectedCustomer.last_name}
                    </p>
                  </div>
                  <button
                    onClick={closeVehicleModal}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <X className="w-5 h-5 text-gray-500" />
                  </button>
                </div>
              </div>

              {/* Form */}
              {renderVehicleForm()}
            </div>
          </div>
        </div>
      )}

      {/* Delete Vehicle Confirmation Modal */}
      {deleteConfirmVehicle && selectedCustomer && (
        <div className="fixed inset-0 z-[70] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {/* Backdrop */}
            <div 
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setDeleteConfirmVehicle(null)}
            />
            
            {/* Modal */}
            <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
              <div className="flex items-center gap-4 mb-4">
                <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                  <AlertTriangle className="w-6 h-6 text-red-600" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-gray-900">Delete Vehicle</h3>
                  <p className="text-sm text-gray-500">This action cannot be undone</p>
                </div>
              </div>
              
              <p className="text-gray-700 mb-6">
                Are you sure you want to delete the{' '}
                <span className="font-semibold">
                  {deleteConfirmVehicle.year ? `${deleteConfirmVehicle.year} ` : ''}
                  {deleteConfirmVehicle.make} {deleteConfirmVehicle.model}
                </span>
                ? This will also remove any associated repair order history.
              </p>

              <div className="flex items-center justify-end gap-3">
                <button
                  onClick={() => setDeleteConfirmVehicle(null)}
                  className="px-4 py-2 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmDeleteVehicle}
                  disabled={deleteVehicleMutation.isPending}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
                >
                  {deleteVehicleMutation.isPending && (
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                  )}
                  Delete Vehicle
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
