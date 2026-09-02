import React, { useCallback, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Search, Truck, X } from 'lucide-react'
import toast from 'react-hot-toast'

import api from '@/lib/api'
import { Spinner } from '@/components/ui'
import MapboxAddressInput from '@/components/MapboxAddressInput'
import { useTheme } from '@/contexts/ThemeContext'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { customerDisplayName } from '@/lib/customerName'
import { formatUSPhone } from '@/utils/phone'
import { stripRegNumber } from './customerDetailFormat'
import type { Customer, CustomerWithVehicles, VINDecodeResult } from '@/types'

interface CustomerFormData {
  first_name: string
  last_name: string
  company_name: string
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
  usdot_number: string
  mc_number: string
  fleet_enabled: boolean
  // Initial vehicle fields (for new customers)
  no_vehicle: boolean
  vehicle_vin: string
  vehicle_make: string
  vehicle_model: string
  vehicle_year: string
  vehicle_unit_number: string
  vehicle_license_plate: string
  vehicle_color: string
  vehicle_mileage: string
  vehicle_notes: string
}

const emptyForm: CustomerFormData = {
  first_name: '',
  last_name: '',
  company_name: '',
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
  usdot_number: '',
  mc_number: '',
  fleet_enabled: false,
  // Initial vehicle
  no_vehicle: false,
  vehicle_vin: '',
  vehicle_make: '',
  vehicle_model: '',
  vehicle_year: '',
  vehicle_unit_number: '',
  vehicle_license_plate: '',
  vehicle_color: '',
  vehicle_mileage: '',
  vehicle_notes: '',
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

  interface MergeResult {
    winner_id: string
    loser_id: string
    vehicles_moved: number
    repair_orders_moved: number
    contacts_moved: number
    appointments_moved: number
    sms_messages_moved: number
    message_thread_action: string
    user_link_action: string
  }

/**
 * Creating, editing, merging and deleting the customer record itself.
 *
 * The last piece of the customer workspace to move. The form is the biggest
 * single part of it, and while it lived here the repair-order panel could edit
 * a carrier's contacts and trucks but not the company's own name, address or
 * fleet settings — those sent the operator back to the Customers tab.
 *
 * The host passes the customer and a ref and gets four actions back. Selection
 * is the host's business, so an update or a delete calls back rather than
 * reaching into the page's state.
 */
export type CustomerFormModalsHandle = {
  openCreate: () => void
  openEdit: (customer: Customer) => void
  requestDelete: (customer: Customer) => void
  openMerge: () => void
}

export default function CustomerFormModals({
  selectedCustomer,
  controlsRef,
  onUpdated,
  onDeleted,
}: {
  selectedCustomer?: Customer | null
  controlsRef: React.MutableRefObject<CustomerFormModalsHandle | null>
  onUpdated?: (customer: Customer) => void
  onDeleted?: () => void
}) {
  const queryClient = useQueryClient()
  const { accentColors } = useTheme()

  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null)
  const [formData, setFormData] = useState<CustomerFormData>(emptyForm)
  const [deleteConfirmCustomer, setDeleteConfirmCustomer] = useState<Customer | null>(null)
  const [isMergeModalOpen, setIsMergeModalOpen] = useState(false)
  const [mergeSearchQuery, setMergeSearchQuery] = useState('')
  const [mergeTargetCustomer, setMergeTargetCustomer] = useState<Customer | null>(null)
  const [isLookingUpZip, setIsLookingUpZip] = useState(false)
  const debouncedMergeSearch = useDebouncedValue(mergeSearchQuery.trim(), 300)

const [isDecodingVin, setIsDecodingVin] = useState(false)
const lastDecodedInitialVehicleVin = useRef('')

const decodeVin = async (rawVin: string, options: { quiet?: boolean } = {}) => {
  const vin = rawVin.trim().toUpperCase()
  if (!vin || vin.length < 11) {
    if (!options.quiet) toast.error('VIN must be at least 11 characters')
    return
  }
  setIsDecodingVin(true)
  try {
    const response = await api.get<VINDecodeResult>(`/customers/vin/decode/${encodeURIComponent(vin)}`)
    const result = response.data
    
    if (result.error_code && result.error_code !== '0') {
      if (!options.quiet) toast.error(result.error_text || 'Failed to decode VIN')
      return
    }
    
    // Populate vehicle fields from decoded data
    setFormData(prev => ({
      ...prev,
      vehicle_vin: result.vin || vin || prev.vehicle_vin,
      vehicle_make: result.make || prev.vehicle_make,
      vehicle_model: result.model || prev.vehicle_model,
      vehicle_year: result.year?.toString() || prev.vehicle_year,
    }))
    lastDecodedInitialVehicleVin.current = vin
    
    const decodedLabel = [result.year, result.make, result.model].filter(Boolean).join(' ')
    toast.success(decodedLabel ? `VIN decoded: ${decodedLabel}` : 'VIN decoded')
  } catch (error: any) {
    if (!options.quiet) toast.error(error.response?.data?.detail || 'Failed to decode VIN')
  } finally {
    setIsDecodingVin(false)
  }
}

const { data: mergeCandidatePage } = useQuery<{ items: Customer[] }>({
  queryKey: ['customers', 'merge-search', debouncedMergeSearch],
  queryFn: async () => {
    const response = await api.get('/customers', {
      params: { paginated: true, skip: 0, limit: 20, search: debouncedMergeSearch },
    })
    return response.data
  },
  enabled: debouncedMergeSearch.length > 0,
  placeholderData: keepPreviousData,
})

const createMutation = useMutation({
  mutationFn: async (data: CustomerFormData) => {
    // Build payload with initial vehicle if provided
    const payload: Record<string, any> = {
      first_name: data.first_name,
      last_name: data.last_name,
      company_name: data.company_name || null,
      email: data.email,
      phone: data.phone || null,
      billing_address_line1: data.billing_address_line1 || null,
      billing_address_line2: data.billing_address_line2 || null,
      billing_city: data.billing_city || null,
      billing_state: data.billing_state || null,
      billing_zip: data.billing_zip || null,
      billing_country: data.billing_country,
      notes: data.notes || null,
      auto_approval_threshold: data.auto_approval_threshold ? parseFloat(data.auto_approval_threshold) : null,
      usdot_number: stripRegNumber(data.usdot_number) || null,
      mc_number: stripRegNumber(data.mc_number) || null,
      no_vehicle: data.no_vehicle,
    }

    // Add initial vehicle if not "no vehicle"
    if (!data.no_vehicle && data.vehicle_make && data.vehicle_model) {
      payload.initial_vehicle = {
        vin: data.vehicle_vin || null,
        make: data.vehicle_make,
        model: data.vehicle_model,
        year: data.vehicle_year ? parseInt(data.vehicle_year) : null,
        unit_number: data.vehicle_unit_number || null,
        license_plate: data.vehicle_license_plate || null,
        color: data.vehicle_color || null,
        mileage: data.vehicle_mileage ? parseInt(data.vehicle_mileage) : null,
        notes: data.vehicle_notes || null,
      }
    }
    
    const response = await api.post('/customers', payload)
    return response.data
  },
  onSuccess: (customer: CustomerWithVehicles) => {
    queryClient.invalidateQueries({ queryKey: ['customers'] })
    closeModal()
    const vehicleCount = customer.vehicles?.length || 0
    toast.success(`Customer ${customer.first_name} ${customer.last_name} created${vehicleCount > 0 ? ` with ${vehicleCount} vehicle` : ''}`)
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
    queryClient.invalidateQueries({ queryKey: ['fleet-board'] })
    queryClient.invalidateQueries({ queryKey: ['fleet-companies'] })
    onUpdated?.(updatedCustomer)
    closeModal()
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
    
    onDeleted?.()
    toast.success('Customer deleted')
  },
  onError: (error: any) => {
    toast.error(error.response?.data?.detail || 'Failed to delete customer')
  },
})

const mergeMutation = useMutation({
  mutationFn: async ({ winnerId, loserId }: { winnerId: string; loserId: string }) => {
    const response = await api.post<MergeResult>('/customers/merge', { winner_id: winnerId, loser_id: loserId })
    return response.data
  },
  onSuccess: (result) => {
    queryClient.invalidateQueries({ queryKey: ['customers'] })
    queryClient.invalidateQueries({ queryKey: ['customerVehicles', result.winner_id] })
    queryClient.invalidateQueries({ queryKey: ['customerContacts', result.winner_id] })
    setIsMergeModalOpen(false)
    setMergeTargetCustomer(null)
    setMergeSearchQuery('')
    toast.success(
      `Merged: ${result.vehicles_moved} vehicles, ${result.repair_orders_moved} repair orders, ${result.contacts_moved} contacts moved`
    )
  },
  onError: (error: any) => {
    toast.error(error.response?.data?.detail || 'Failed to merge customers')
  },
})

const resetForm = () => {
  setEditingCustomer(null)
  setFormData(emptyForm)
  lastDecodedInitialVehicleVin.current = ''
}

const openCreateModal = () => {
  resetForm()
  setIsModalOpen(true)
}

const populateFormFromCustomer = (customer: Customer) => {
  setEditingCustomer(customer)
  setFormData({
    ...emptyForm,
    first_name: customer.first_name,
    last_name: customer.last_name,
    company_name: customer.company_name || '',
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
    usdot_number: stripRegNumber(customer.usdot_number),
    mc_number: stripRegNumber(customer.mc_number),
    fleet_enabled: !!customer.fleet_enabled,
  })
}

const closeModal = () => {
  setIsModalOpen(false)
  resetForm()
}


const handleDeleteClick = (customer: Customer) => {
  setDeleteConfirmCustomer(customer)
}

const confirmDelete = () => {
  if (deleteConfirmCustomer) {
    deleteMutation.mutate(deleteConfirmCustomer.id)
  }
}

const handleSubmit = (e: React.FormEvent) => {
  e.preventDefault()

  if (!formData.company_name.trim() || !formData.first_name.trim() || !formData.last_name.trim() || !formData.email.trim()) {
    toast.error('Company name, first name, last name, and email are required')
    return
  }

  // For new customers, require vehicle or no_vehicle flag
  if (!editingCustomer && !formData.no_vehicle) {
    if (!formData.vehicle_make.trim() || !formData.vehicle_model.trim()) {
      toast.error('Vehicle make and model are required, or check "No truck available"')
      return
    }
  }

  if (editingCustomer) {
    // For updates, only send customer fields
    const payload = {
      first_name: formData.first_name,
      last_name: formData.last_name,
      company_name: formData.company_name || null,
      email: formData.email,
      phone: formData.phone || null,
      billing_address_line1: formData.billing_address_line1 || null,
      billing_address_line2: formData.billing_address_line2 || null,
      billing_city: formData.billing_city || null,
      billing_state: formData.billing_state || null,
      billing_zip: formData.billing_zip || null,
      billing_country: formData.billing_country,
      notes: formData.notes || null,
      auto_approval_threshold: formData.auto_approval_threshold ? parseFloat(formData.auto_approval_threshold) : null,
      usdot_number: stripRegNumber(formData.usdot_number) || null,
      mc_number: stripRegNumber(formData.mc_number) || null,
      fleet_enabled: formData.fleet_enabled,
    }
    updateMutation.mutate({ id: editingCustomer.id, data: payload as any })
  } else {
    createMutation.mutate(formData)
  }
}

const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
  const { name, value, type } = e.target

  if (type === 'checkbox') {
    setFormData((prev) => ({ ...prev, [name]: (e.target as HTMLInputElement).checked }))
    return
  }
  
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

  if (name === 'vehicle_vin') {
    const vin = value.toUpperCase()
    setFormData((prev) => ({ ...prev, vehicle_vin: vin }))
    const trimmedVin = vin.trim()
    if (trimmedVin.length === 17 && trimmedVin !== lastDecodedInitialVehicleVin.current) {
      void decodeVin(trimmedVin, { quiet: true })
    }
    return
  }
  
  setFormData((prev) => ({ ...prev, [name]: value }))
}

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
          Company Name <span className="text-red-500">*</span>
        </label>
        <input
          type="text"
          name="company_name"
          value={formData.company_name}
          onChange={handleInputChange}
          required
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
          placeholder="Acme Logistics"
        />
      </div>
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
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">US DOT #</label>
        <input
          type="text"
          name="usdot_number"
          value={formData.usdot_number}
          onChange={handleInputChange}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
          placeholder="3155331"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">MC #</label>
        <input
          type="text"
          name="mc_number"
          value={formData.mc_number}
          onChange={handleInputChange}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
          placeholder="107385"
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
                  <Spinner size="xs" />
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

    {editingCustomer && (
      <>
        <div className={`rounded-xl border p-4 ${formData.fleet_enabled ? 'border-amber-300 bg-amber-50' : 'border-gray-200 bg-gray-50'}`}>
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              name="fleet_enabled"
              checked={formData.fleet_enabled}
              onChange={handleInputChange}
              className="mt-1 h-4 w-4 rounded border-gray-300 text-amber-500 focus:ring-amber-500"
            />
            <span className="min-w-0">
              <span className="flex items-center gap-2 font-semibold text-gray-900">
                <Truck className="h-4 w-4 text-amber-600" />
                Add this customer to Fleet Board
              </span>
              <span className="mt-1 block text-sm text-gray-600">
                Enroll every truck this company owns or operates. If a truck still uses the internal House Account as payer, this customer becomes its default invoice recipient; an existing external payer is retained. Billing uses live customer contact data—no per-truck entry required.
              </span>
              {formData.fleet_enabled && (
                <span className="mt-2 block text-xs font-medium text-amber-700">
                  Fleet membership is enabled. New trucks added under this customer will join Fleet Board automatically.
                </span>
              )}
            </span>
          </label>
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
          <p className="text-xs text-gray-500 mt-1">Published initial estimates at or below this amount may be auto-approved. Additional work always requires customer approval.</p>
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
      </>
    )}

    {/* Initial Vehicle Section - Only for new customers */}
    {!editingCustomer && (
      <div className="border-t border-gray-200 pt-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
            <Truck className="w-4 h-4" />
            Initial Truck
          </h3>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={formData.no_vehicle}
              onChange={(e) => setFormData(prev => ({ ...prev, no_vehicle: e.target.checked }))}
              className="w-4 h-4 rounded border-gray-300 text-amber-500 focus:ring-amber-500"
            />
            <span className="text-gray-600">No truck available at this time</span>
          </label>
        </div>

        {!formData.no_vehicle && (
          <div className="space-y-4">
            {/* VIN with decode button */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                VIN
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  name="vehicle_vin"
                  value={formData.vehicle_vin}
                  onChange={handleInputChange}
                  className="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors uppercase"
                  placeholder="Enter VIN to auto-fill"
                  maxLength={17}
                />
                <button
                  type="button"
                  onClick={() => decodeVin(formData.vehicle_vin)}
                  disabled={isDecodingVin || formData.vehicle_vin.length < 11}
                  className="px-4 py-2.5 bg-gray-100 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed text-gray-700 font-medium rounded-lg transition-colors flex items-center gap-2"
                >
                  {isDecodingVin ? (
                    <Spinner size="xs" />
                  ) : (
                    <Search className="w-4 h-4" />
                  )}
                  Decode
                </button>
              </div>
              <p className="text-xs text-gray-500 mt-1">Enter or paste a full VIN to auto-fill make, model, and year.</p>
            </div>

            {/* Make & Model */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Make <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  name="vehicle_make"
                  value={formData.vehicle_make}
                  onChange={handleInputChange}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                  placeholder="Freightliner"
                  required={!formData.no_vehicle}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Model <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  name="vehicle_model"
                  value={formData.vehicle_model}
                  onChange={handleInputChange}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                  placeholder="Cascadia"
                  required={!formData.no_vehicle}
                />
              </div>
            </div>

            {/* Year & Unit Number */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Year
                </label>
                <input
                  type="number"
                  name="vehicle_year"
                  value={formData.vehicle_year}
                  onChange={handleInputChange}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                  placeholder="2024"
                  min="1900"
                  max="2100"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Unit Number
                </label>
                <input
                  type="text"
                  name="vehicle_unit_number"
                  value={formData.vehicle_unit_number}
                  onChange={handleInputChange}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                  placeholder="T-001"
                />
              </div>
            </div>

            {/* License Plate & Color */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  License Plate
                </label>
                <input
                  type="text"
                  name="vehicle_license_plate"
                  value={formData.vehicle_license_plate}
                  onChange={handleInputChange}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors uppercase"
                  placeholder="ABC-1234"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Color
                </label>
                <input
                  type="text"
                  name="vehicle_color"
                  value={formData.vehicle_color}
                  onChange={handleInputChange}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                  placeholder="White"
                />
              </div>
            </div>

            {/* Mileage */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Mileage
              </label>
              <input
                type="number"
                name="vehicle_mileage"
                value={formData.vehicle_mileage}
                onChange={handleInputChange}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                placeholder="150000"
                min="0"
              />
            </div>
          </div>
        )}
      </div>
    )}

    {!editingCustomer && (
      <div className="space-y-6 border-t border-gray-200 pt-6">
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
          <p className="text-xs text-gray-500 mt-1">Published initial estimates at or below this amount may be auto-approved. Additional work always requires customer approval.</p>
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
      </div>
    )}

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
        className="px-5 py-2.5 disabled:opacity-50 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
        style={{ backgroundColor: accentColors[500] }}
      >
        {(createMutation.isPending || updateMutation.isPending) && (
          <Spinner size="xs" className="border-white/40 border-t-white" />
        )}
        {editingCustomer ? 'Save Changes' : 'Add Customer'}
      </button>
    </div>
  </form>
)

  controlsRef.current = {
    openCreate: openCreateModal,
    openEdit: (customer: Customer) => {
      populateFormFromCustomer(customer)
      setEditingCustomer(customer)
      setIsModalOpen(true)
    },
    requestDelete: handleDeleteClick,
    openMerge: () => setIsMergeModalOpen(true),
  }

  // Rendered into <body>. The workspace panel that hosts these sets
  // clip-path on its scroll container, and a clip-path on an ancestor clips
  // position:fixed descendants — so a modal opened from inside the panel was
  // centred correctly and then cut to the panel's rounded rectangle.
  return createPortal(
    <>
      {isModalOpen && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {/* Backdrop */}
            <div 
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={closeModal}
            />
      
            {/* Modal */}
            <div className="db-customer-modal relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
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
      {deleteConfirmCustomer && (
        <div className="fixed inset-0 z-[80] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {/* Backdrop */}
            <div 
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setDeleteConfirmCustomer(null)}
            />
      
              {/* Modal */}
              <div className="db-customer-modal relative bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
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
                    <Spinner size="xs" className="border-white/40 border-t-white" />
                  )}
                  Delete Customer
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {isMergeModalOpen && selectedCustomer && (
        <div className="fixed inset-0 z-[80] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {/* Backdrop */}
            <div
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => {
                setIsMergeModalOpen(false)
                setMergeTargetCustomer(null)
                setMergeSearchQuery('')
              }}
            />

            {/* Modal */}
            <div className="db-customer-modal relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
              <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 rounded-t-2xl">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-gray-900">Merge Duplicate Customer</h2>
                    <p className="text-sm text-gray-500">
                      Combine another record into {customerDisplayName(selectedCustomer)}
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      setIsMergeModalOpen(false)
                      setMergeTargetCustomer(null)
                      setMergeSearchQuery('')
                    }}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <X className="w-5 h-5 text-gray-500" />
                  </button>
                </div>
              </div>

              <div className="p-6 space-y-4">
                {!mergeTargetCustomer ? (
                  <>
                    <p className="text-sm text-gray-600">
                      Search for the duplicate record to merge into this customer. Everything
                      from the duplicate (vehicles, repair orders, contacts) will move here, and
                      the duplicate will be deleted. This cannot be undone.
                    </p>
                    <input
                      type="text"
                      autoFocus
                      placeholder="Search by name, email, or phone..."
                      value={mergeSearchQuery}
                      onChange={(e) => setMergeSearchQuery(e.target.value)}
                      className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
                    />
                    <div className="max-h-72 overflow-y-auto divide-y divide-gray-100 border border-gray-100 rounded-xl">
                      {(() => {
                        const query = mergeSearchQuery.trim()
                        // Server-side search over all customers, minus the one being merged into.
                        const candidates = (mergeCandidatePage?.items || [])
                          .filter((c) => c.id !== selectedCustomer.id)
                        if (!query) {
                          return <p className="text-sm text-gray-400 text-center py-6">Start typing to search…</p>
                        }
                        if (candidates.length === 0) {
                          return <p className="text-sm text-gray-400 text-center py-6">No matches found</p>
                        }
                        return candidates.map((c) => (
                          <button
                            key={c.id}
                            onClick={() => setMergeTargetCustomer(c)}
                            className="w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors"
                          >
                            <p className="text-sm font-medium text-gray-900">{customerDisplayName(c)}</p>
                            <p className="text-xs text-gray-500">{c.email} {c.phone && `· ${formatUSPhone(c.phone)}`}</p>
                          </button>
                        ))
                      })()}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
                        <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wider mb-2">Keep (this record)</p>
                        <p className="font-semibold text-gray-900">{customerDisplayName(selectedCustomer)}</p>
                        <p className="text-sm text-gray-600 mt-1">{selectedCustomer.email}</p>
                        <p className="text-sm text-gray-600">{selectedCustomer.phone ? formatUSPhone(selectedCustomer.phone) : '—'}</p>
                      </div>
                      <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                        <p className="text-xs font-semibold text-red-700 uppercase tracking-wider mb-2">Merge & Delete</p>
                        <p className="font-semibold text-gray-900">{customerDisplayName(mergeTargetCustomer)}</p>
                        <p className="text-sm text-gray-600 mt-1">{mergeTargetCustomer.email}</p>
                        <p className="text-sm text-gray-600">{mergeTargetCustomer.phone ? formatUSPhone(mergeTargetCustomer.phone) : '—'}</p>
                      </div>
                    </div>
                    <p className="text-sm text-gray-600">
                      All vehicles, repair orders, contacts, and history from{' '}
                      <span className="font-medium">{customerDisplayName(mergeTargetCustomer)}</span> will move to{' '}
                      <span className="font-medium">{customerDisplayName(selectedCustomer)}</span>, then the duplicate
                      record will be permanently deleted. This cannot be undone.
                    </p>
                    <div className="flex items-center justify-between pt-2">
                      <button
                        onClick={() => setMergeTargetCustomer(null)}
                        className="px-4 py-2 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
                      >
                        Back
                      </button>
                      <button
                        onClick={() => mergeMutation.mutate({ winnerId: selectedCustomer.id, loserId: mergeTargetCustomer.id })}
                        disabled={mergeMutation.isPending}
                        className="px-5 py-2.5 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
                      >
                        {mergeMutation.isPending && (
                          <Spinner size="xs" className="border-white/40 border-t-white" />
                        )}
                        Merge Customers
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>,
    document.body,
  )
}
