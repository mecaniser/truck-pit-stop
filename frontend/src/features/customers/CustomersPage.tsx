import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { Spinner, LoadingLine } from '@/components/ui'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { Customer, Vehicle, Contact, RepairOrder, RepairOrderStatus, VINDecodeResult, CustomerWithVehicles } from '../../types'
import { customerDisplayName, customerPersonalName } from '../../lib/customerName'
import { vehicleDisplayLabel } from '../../lib/vehicleName'
import { AlertTriangle, ArrowDown, ArrowRight, ArrowUp, DollarSign, Mail, Pencil, Phone, Plus, Search, Star, Trash2, Truck, User, Wrench, X } from 'lucide-react'
import SlidePanel from '@/components/SlidePanel'
import MapboxAddressInput from '@/components/MapboxAddressInput'
import { formatUSPhone } from '@/utils/phone'
import ViewToggle from '@/components/ViewToggle'
import { useViewPreference } from '@/hooks/useViewPreference'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useTheme } from '../../contexts/ThemeContext'

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

const duplicateVinFieldMessage = (error: any): string | null => {
  const detail = error.response?.data?.detail
  if (error.response?.status !== 409 || typeof detail !== 'string' || !/\bVIN\b/i.test(detail)) {
    return null
  }

  return 'This VIN is already assigned to another truck. Keep the existing truck as the primary record, then use Fleet Board → Add truck → Link existing truck to connect it to this company.'
}

interface ContactFormData {
  first_name: string
  last_name: string
  role: string
  email: string
  phone: string
  notes: string
  is_primary: boolean
}

const emptyContactForm: ContactFormData = {
  first_name: '',
  last_name: '',
  role: '',
  email: '',
  phone: '',
  notes: '',
  is_primary: false,
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

// DOT/MC values may be stored bare ("107385") or, from the Easy Truck Shop
// import, with a redundant prefix ("MC-107385"). Strip a leading DOT/MC label
// so the UI's own "DOT "/"MC " prefix doesn't double up (e.g. "MC MC-107385").
const stripRegNumber = (value?: string | null): string =>
  (value || '').replace(/^\s*(us\s*dot|dot|mc)[\s#:-]*/i, '').trim()

// Short labels for the "matched via" badges shown next to a search result,
// so it's clear *why* a customer showed up (e.g. their phone matched, not
// their name) rather than just showing every field that happens to match.
const MATCH_FIELD_LABELS: Record<string, string> = {
  name: 'Name',
  company: 'Company',
  email: 'Email',
  phone: 'Phone',
  usdot: 'DOT',
  mc: 'MC',
  similar: 'Similar match',
}

function MatchBadges({ matchedFields, variant = 'dark' }: { matchedFields?: string[]; variant?: 'dark' | 'light' }) {
  if (!matchedFields || matchedFields.length === 0) return null
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {matchedFields.map((field) => (
        <span
          key={field}
          className={`whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-medium ${
            variant === 'dark' ? 'bg-white/10 text-white/70' : 'bg-black/10 text-slate-600'
          }`}
        >
          {MATCH_FIELD_LABELS[field] || field}
        </span>
      ))}
    </div>
  )
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
  const { accentColors } = useTheme()
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')
  const debouncedSearch = useDebouncedValue(searchQuery.trim(), 300)
  const PAGE_SIZE = 25
  const [page, setPage] = useState(0)
  type CustomerSortField = 'name' | 'balance' | 'vehicle_count'
  const [sortField, setSortField] = useState<CustomerSortField>('name')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')
  const toggleSort = (field: CustomerSortField) => {
    setPage(0)
    if (sortField === field) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDirection('asc')
    }
  }
  // Any new search term returns to the first page of results.
  useEffect(() => { setPage(0) }, [debouncedSearch])
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
  const [detailTab, setDetailTab] = useState<'overview' | 'history'>('overview')
  const [expandedHistoryId, setExpandedHistoryId] = useState<string | null>(null)

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
  const [vehicleVinError, setVehicleVinError] = useState<string | null>(null)
  const [deleteConfirmVehicle, setDeleteConfirmVehicle] = useState<Vehicle | null>(null)

  // Contact form state
  const [isContactModalOpen, setIsContactModalOpen] = useState(false)
  const [editingContact, setEditingContact] = useState<Contact | null>(null)
  const [contactFormData, setContactFormData] = useState<ContactFormData>(emptyContactForm)
  const [deleteConfirmContact, setDeleteConfirmContact] = useState<Contact | null>(null)
  
  // Delete confirmation state
  const [deleteConfirmCustomer, setDeleteConfirmCustomer] = useState<Customer | null>(null)

  // Merge customer state
  const [isMergeModalOpen, setIsMergeModalOpen] = useState(false)
  const [mergeSearchQuery, setMergeSearchQuery] = useState('')
  const [mergeTargetCustomer, setMergeTargetCustomer] = useState<Customer | null>(null)
  const debouncedMergeSearch = useDebouncedValue(mergeSearchQuery.trim(), 300)

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 1024)
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  const activeViewMode = isMobile ? 'list' : viewMode

  const queryClient = useQueryClient()

  // Server-side pagination: fetch one page at a time with search + sort pushed
  // to the API, instead of loading every customer and filtering in the browser.
  const customerPageKey = (p: number) =>
    ['customers', { page: p, search: debouncedSearch, sort: sortField, order: sortDirection }] as const
  const fetchCustomerPage = async (p: number) => {
    const response = await api.get('/customers', {
      params: {
        paginated: true,
        skip: p * PAGE_SIZE,
        limit: PAGE_SIZE,
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
        sort: sortField,
        order: sortDirection,
      },
    })
    return response.data as { items: Customer[]; total: number; has_more: boolean }
  }
  const { data: customerPage, isLoading, isPlaceholderData, isFetching } = useQuery({
    queryKey: customerPageKey(page),
    queryFn: () => fetchCustomerPage(page),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
  const customers = customerPage?.items
  const totalCustomers = customerPage?.total ?? 0

  // Prefetch the next page once the current one has settled, so paging forward
  // feels instant. Only when a next page exists and we're showing live data.
  useEffect(() => {
    if (customerPage?.has_more && !isPlaceholderData) {
      queryClient.prefetchQuery({
        queryKey: customerPageKey(page + 1),
        queryFn: () => fetchCustomerPage(page + 1),
        staleTime: 30_000,
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, debouncedSearch, sortField, sortDirection, customerPage?.has_more, isPlaceholderData])

  // The merge picker must search ALL customers, not just the current page, so it
  // has its own server-side search query (only runs while the merge modal input
  // has a term).
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
  
  const { data: customerVehicles, isLoading: isLoadingVehicles } = useQuery<Vehicle[]>({
    queryKey: ['customerVehicles', selectedCustomer?.id],
    queryFn: async () => {
      if (!selectedCustomer?.id) return []
      const response = await api.get(`/customers/${selectedCustomer.id}/vehicles`)
      return response.data
    },
    enabled: !!selectedCustomer?.id && isDetailOpen,
  })

  const { data: customerContacts, isLoading: isLoadingContacts } = useQuery<Contact[]>({
    queryKey: ['customerContacts', selectedCustomer?.id],
    queryFn: async () => {
      if (!selectedCustomer?.id) return []
      const response = await api.get(`/customers/${selectedCustomer.id}/contacts`)
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

  interface CustomerHistoryItem {
    id: string
    order_number: string
    status: string
    vehicle_make: string
    vehicle_model: string
    vehicle_year: number | null
    vehicle_unit_number: string | null
    total_cost: string
    savings: string
    created_at: string | null
    work_completed_at: string | null
  }
  interface CustomerHistoryResponse {
    items: CustomerHistoryItem[]
    stats: {
      total_orders: number
      completed_orders: number
      lifetime_spend: string
      lifetime_savings: string
    }
  }
  const { data: customerHistory, isLoading: isLoadingHistory } = useQuery<CustomerHistoryResponse>({
    queryKey: ['customerHistory', selectedCustomer?.id],
    queryFn: async () => {
      const response = await api.get(`/customers/${selectedCustomer!.id}/history`)
      return response.data
    },
    enabled: !!selectedCustomer?.id && isDetailOpen && detailTab === 'history',
  })

  interface HistoryRoDetailData {
    id: string
    order_number: string
    mechanic_name: string | null
    amount_paid: string | null
    total_cost: string
    customer_notes: string | null
    internal_notes: string | null
    labor: { id: string; description: string; hours: string; hourly_rate: string; total_cost: string }[]
    parts: { id: string; name: string | null; sku: string | null; quantity: number; unit_price: string; total_price: string }[]
  }

  const HistoryRoDetail = ({ customerId, orderId }: { customerId: string; orderId: string }) => {
    const { data, isLoading } = useQuery<HistoryRoDetailData>({
      queryKey: ['customerHistoryDetail', customerId, orderId],
      queryFn: async () => {
        const response = await api.get(`/customers/${customerId}/history/${orderId}`)
        return response.data
      },
    })
    if (isLoading) return <p className="text-xs text-gray-400">Loading…</p>
    if (!data) return <p className="text-xs text-gray-400">No details available</p>
    // Try to pull a human-readable internal-notes body if it's not JSON.
    let internalNotesDisplay: string | null = null
    if (data.internal_notes) {
      try {
        JSON.parse(data.internal_notes)
      } catch {
        internalNotesDisplay = data.internal_notes
      }
    }
    return (
      <div className="space-y-3 text-sm">
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs">
          <div>
            <span className="text-gray-500">Mechanic: </span>
            <span className="font-medium text-gray-800">{data.mechanic_name || '—'}</span>
          </div>
          <div>
            <span className="text-gray-500">Amount paid: </span>
            <span className="font-medium text-emerald-700">
              {data.amount_paid ? `$${parseFloat(data.amount_paid).toFixed(2)}` : 'Not paid'}
            </span>
          </div>
          <div>
            <span className="text-gray-500">RO total: </span>
            <span className="font-medium text-gray-800">${parseFloat(data.total_cost).toFixed(2)}</span>
          </div>
        </div>

        <div>
          <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1">Work performed</p>
          {data.labor.length === 0 ? (
            <p className="text-xs text-gray-400">No labor recorded</p>
          ) : (
            <ul className="space-y-1">
              {data.labor.map((li) => (
                <li key={li.id} className="flex items-baseline justify-between gap-3">
                  <span className="text-gray-800">{li.description || 'Labor'}</span>
                  <span className="text-xs text-gray-500 whitespace-nowrap">
                    {parseFloat(li.hours).toFixed(2)} hr × ${parseFloat(li.hourly_rate).toFixed(2)} ={' '}
                    <span className="font-medium text-gray-800">${parseFloat(li.total_cost).toFixed(2)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1">Parts used</p>
          {data.parts.length === 0 ? (
            <p className="text-xs text-gray-400">No parts used</p>
          ) : (
            <ul className="space-y-1">
              {data.parts.map((p) => (
                <li key={p.id} className="flex items-baseline justify-between gap-3">
                  <span className="text-gray-800">
                    {p.name || 'Part'}
                    {p.sku && <span className="text-xs text-gray-500 ml-1">· {p.sku}</span>}
                  </span>
                  <span className="text-xs text-gray-500 whitespace-nowrap">
                    {p.quantity} × ${parseFloat(p.unit_price).toFixed(2)} ={' '}
                    <span className="font-medium text-gray-800">${parseFloat(p.total_price).toFixed(2)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {(data.customer_notes || internalNotesDisplay) && (
          <div>
            <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1">Notes</p>
            {data.customer_notes && (
              <p className="text-xs text-gray-700 whitespace-pre-wrap"><span className="text-gray-500">Customer: </span>{data.customer_notes}</p>
            )}
            {internalNotesDisplay && (
              <p className="text-xs text-gray-700 whitespace-pre-wrap mt-1"><span className="text-gray-500">Internal: </span>{internalNotesDisplay}</p>
            )}
          </div>
        )}
      </div>
    )
  }

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

  // VIN Decoder
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
      const vinError = duplicateVinFieldMessage(error)
      if (vinError) {
        setVehicleVinError(vinError)
        return
      }
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
      const vinError = duplicateVinFieldMessage(error)
      if (vinError) {
        setVehicleVinError(vinError)
        return
      }
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

  const createContactMutation = useMutation({
    mutationFn: async ({ customerId, data }: { customerId: string; data: ContactFormData }) => {
      const payload = {
        first_name: data.first_name || null,
        last_name: data.last_name || null,
        role: data.role || null,
        email: data.email || null,
        phone: data.phone || null,
        notes: data.notes || null,
        is_primary: data.is_primary,
      }
      const response = await api.post(`/customers/${customerId}/contacts`, payload)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customerContacts', selectedCustomer?.id] })
      closeContactModal()
      toast.success('Contact added')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to add contact')
    },
  })

  const updateContactMutation = useMutation({
    mutationFn: async ({ customerId, contactId, data }: { customerId: string; contactId: string; data: ContactFormData }) => {
      const payload = {
        first_name: data.first_name || null,
        last_name: data.last_name || null,
        role: data.role || null,
        email: data.email || null,
        phone: data.phone || null,
        notes: data.notes || null,
        is_primary: data.is_primary,
      }
      const response = await api.put(`/customers/${customerId}/contacts/${contactId}`, payload)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customerContacts', selectedCustomer?.id] })
      closeContactModal()
      toast.success('Contact updated')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update contact')
    },
  })

  const deleteContactMutation = useMutation({
    mutationFn: async ({ customerId, contactId }: { customerId: string; contactId: string }) => {
      await api.delete(`/customers/${customerId}/contacts/${contactId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customerContacts', selectedCustomer?.id] })
      setDeleteConfirmContact(null)
      toast.success('Contact deleted')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete contact')
    },
  })

  const resetForm = () => {
    setEditingCustomer(null)
    setFormData(emptyForm)
    lastDecodedInitialVehicleVin.current = ''
  }

  const openCreateModal = () => {
    resetForm()
    setIsEditingInPanel(false)
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
    setDetailTab('overview')
  }

  const closeDetailPanel = () => {
    setIsDetailOpen(false)
    setSelectedCustomer(null)
    setIsEditingInPanel(false)
    setSelectedVehicleInPanel(null)
    setDetailTab('overview')
    setExpandedHistoryId(null)
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
    setVehicleVinError(null)
    lastDecodedVehicleVin.current = ''
    setIsVehicleModalOpen(true)
  }

  const openEditVehicleModal = (vehicle: Vehicle) => {
    setEditingVehicle(vehicle)
    setVehicleVinError(null)
    lastDecodedVehicleVin.current = (vehicle.vin || '').trim().toUpperCase()
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
    setVehicleVinError(null)
    lastDecodedVehicleVin.current = ''
  }

  const handleVehicleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    if (name === 'vin') {
      const vin = value.toUpperCase()
      setVehicleVinError(null)
      setVehicleFormData((prev) => ({ ...prev, vin }))
      const trimmedVin = vin.trim()
      if (trimmedVin.length === 17 && trimmedVin !== lastDecodedVehicleVin.current) {
        void decodeVehicleVin(trimmedVin, { quiet: true })
      }
      return
    }
    setVehicleFormData((prev) => ({ ...prev, [name]: value }))
  }

  // VIN decoder for vehicle form (separate from customer form)
  const [isDecodingVehicleVin, setIsDecodingVehicleVin] = useState(false)
  const lastDecodedVehicleVin = useRef('')
  
  const decodeVehicleVin = async (rawVin: string, options: { quiet?: boolean } = {}) => {
    const vin = rawVin.trim().toUpperCase()
    if (!vin || vin.length < 11) {
      if (!options.quiet) toast.error('VIN must be at least 11 characters')
      return
    }
    setIsDecodingVehicleVin(true)
    try {
      const response = await api.get<VINDecodeResult>(`/customers/vin/decode/${encodeURIComponent(vin)}`)
      const result = response.data
      
      if (result.error_code && result.error_code !== '0') {
        if (!options.quiet) toast.error(result.error_text || 'Failed to decode VIN')
        return
      }
      
      setVehicleFormData(prev => ({
        ...prev,
        vin: result.vin || vin || prev.vin,
        make: result.make || prev.make,
        model: result.model || prev.model,
        year: result.year?.toString() || prev.year,
      }))
      lastDecodedVehicleVin.current = vin
      
      const decodedLabel = [result.year, result.make, result.model].filter(Boolean).join(' ')
      toast.success(decodedLabel ? `VIN decoded: ${decodedLabel}` : 'VIN decoded')
    } catch (error: any) {
      if (!options.quiet) toast.error(error.response?.data?.detail || 'Failed to decode VIN')
    } finally {
      setIsDecodingVehicleVin(false)
    }
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

  // Contact form helpers
  const openAddContactModal = () => {
    setEditingContact(null)
    setContactFormData(emptyContactForm)
    setIsContactModalOpen(true)
  }

  const openEditContactModal = (contact: Contact) => {
    setEditingContact(contact)
    setContactFormData({
      first_name: contact.first_name || '',
      last_name: contact.last_name || '',
      role: contact.role || '',
      email: contact.email || '',
      phone: contact.phone || '',
      notes: contact.notes || '',
      is_primary: contact.is_primary,
    })
    setIsContactModalOpen(true)
  }

  const closeContactModal = () => {
    setIsContactModalOpen(false)
    setEditingContact(null)
    setContactFormData(emptyContactForm)
  }

  const handleContactInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value, type } = e.target
    const checked = (e.target as HTMLInputElement).checked
    setContactFormData((prev) => ({ ...prev, [name]: type === 'checkbox' ? checked : value }))
  }

  const handleContactSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedCustomer) return

    if (!contactFormData.first_name.trim() && !contactFormData.last_name.trim() && !contactFormData.email.trim() && !contactFormData.phone.trim()) {
      toast.error('Enter at least a name, email, or phone')
      return
    }

    if (editingContact) {
      updateContactMutation.mutate({
        customerId: selectedCustomer.id,
        contactId: editingContact.id,
        data: contactFormData,
      })
    } else {
      createContactMutation.mutate({
        customerId: selectedCustomer.id,
        data: contactFormData,
      })
    }
  }

  const handleDeleteContactClick = (contact: Contact) => {
    setDeleteConfirmContact(contact)
  }

  const confirmDeleteContact = () => {
    if (deleteConfirmContact && selectedCustomer) {
      deleteContactMutation.mutate({
        customerId: selectedCustomer.id,
        contactId: deleteConfirmContact.id,
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
      }
      updateMutation.mutate({ id: editingCustomer.id, data: payload as any })
    } else {
      createMutation.mutate(formData)
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

  const formatCustomerSource = (source?: string | null) => {
    if (!source) return null
    if (source === 'walk_in') return 'Walk-in'
    if (source === 'zelle') return 'Zelle'
    if (source === 'portal') return 'Portal'
    return source.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
  }

  const vehicleCount = customerVehicles?.length || 0
  const showVehicleUnitColumn = customerVehicles?.some((vehicle) => !!vehicle.unit_number?.trim()) ?? false
  const showVehicleVinColumn = customerVehicles?.some((vehicle) => !!vehicle.vin?.trim()) ?? false
  const showVehiclePlateColumn = customerVehicles?.some((vehicle) => !!vehicle.license_plate?.trim()) ?? false

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

      {/* VIN with decode */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">VIN</label>
        <div className="flex gap-2">
          <input
            type="text"
            name="vin"
            value={vehicleFormData.vin}
            onChange={handleVehicleInputChange}
            aria-invalid={vehicleVinError ? 'true' : undefined}
            aria-describedby={vehicleVinError ? 'vehicle-vin-error' : 'vehicle-vin-help'}
            className={`flex-1 px-4 py-2.5 border rounded-lg focus:ring-2 transition-colors font-mono uppercase ${
              vehicleVinError
                ? 'border-red-500 bg-red-50 focus:ring-red-200 focus:border-red-500'
                : 'border-gray-300 focus:ring-amber-500 focus:border-amber-500'
            }`}
            placeholder="Enter VIN to auto-fill"
            maxLength={17}
          />
          <button
            type="button"
            onClick={() => decodeVehicleVin(vehicleFormData.vin)}
            disabled={isDecodingVehicleVin || vehicleFormData.vin.length < 11}
            className="px-4 py-2.5 bg-gray-100 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed text-gray-700 font-medium rounded-lg transition-colors flex items-center gap-2"
          >
            {isDecodingVehicleVin ? (
              <Spinner size="xs" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            Decode
          </button>
        </div>
        {vehicleVinError ? (
          <p id="vehicle-vin-error" role="alert" className="mt-2 flex items-start gap-1.5 text-sm text-red-600">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" />
            <span>{vehicleVinError}</span>
          </p>
        ) : (
          <p id="vehicle-vin-help" className="text-xs text-gray-500 mt-1">Enter or paste a full VIN to auto-fill make, model, and year.</p>
        )}
      </div>

      {/* Unit Number */}
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
          className="px-5 py-2.5 disabled:opacity-50 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
          style={{ backgroundColor: accentColors[500] }}
        >
          {(createVehicleMutation.isPending || updateVehicleMutation.isPending) && (
            <Spinner size="xs" className="border-white/40 border-t-white" />
          )}
          {editingVehicle ? 'Save Changes' : 'Add Vehicle'}
        </button>
      </div>
    </form>
  )

  const renderContactForm = () => (
    <form onSubmit={handleContactSubmit} className="p-6 space-y-4">
      {/* First & Last Name */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
          <input
            type="text"
            name="first_name"
            value={contactFormData.first_name}
            onChange={handleContactInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="John"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
          <input
            type="text"
            name="last_name"
            value={contactFormData.last_name}
            onChange={handleContactInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="Doe"
          />
        </div>
      </div>

      {/* Role */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
        <input
          type="text"
          name="role"
          value={contactFormData.role}
          onChange={handleContactInputChange}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
          placeholder="Dispatcher, Owner, Driver..."
        />
      </div>

      {/* Email & Phone */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
          <input
            type="email"
            name="email"
            value={contactFormData.email}
            onChange={handleContactInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="john@example.com"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
          <input
            type="tel"
            name="phone"
            value={contactFormData.phone}
            onChange={handleContactInputChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors"
            placeholder="(555) 123-4567"
          />
        </div>
      </div>

      {/* Notes */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
        <textarea
          name="notes"
          value={contactFormData.notes}
          onChange={handleContactInputChange}
          rows={2}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-colors resize-none"
          placeholder="Any additional notes..."
        />
      </div>

      {/* Primary toggle */}
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          name="is_primary"
          checked={contactFormData.is_primary}
          onChange={handleContactInputChange}
          className="w-4 h-4 rounded border-gray-300 text-amber-600 focus:ring-amber-500"
        />
        <span className="text-sm font-medium text-gray-700">Set as primary contact</span>
      </label>

      {/* Actions */}
      <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200">
        <button
          type="button"
          onClick={closeContactModal}
          className="px-5 py-2.5 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={createContactMutation.isPending || updateContactMutation.isPending}
          className="px-5 py-2.5 disabled:opacity-50 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
          style={{ backgroundColor: accentColors[500] }}
        >
          {(createContactMutation.isPending || updateContactMutation.isPending) && (
            <Spinner size="xs" className="border-white/40 border-t-white" />
          )}
          {editingContact ? 'Save Changes' : 'Add Contact'}
        </button>
      </div>
    </form>
  )

  // Search, sort, and pagination are all done server-side now, so the rendered
  // list is simply the current page returned by the API.
  const filteredCustomers = customers

  if (isLoading) {
    return (
      <div className="flex flex-col h-full min-h-0">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 sm:mb-6 flex-shrink-0">
          <h1 className="text-xl sm:text-2xl font-bold text-white">Customers</h1>
          <button
            disabled
            className="mt-3 sm:mt-0 px-4 py-2 text-white font-medium rounded-lg opacity-60"
            style={{ backgroundColor: accentColors[500] }}
          >
            + Add Customer
          </button>
        </div>

        {/* Search Bar */}
        <div className="mb-6 flex-shrink-0">
          <div className="relative">
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
              placeholder="Search by name, email, or phone..."
              disabled
              className="w-full pl-10 pr-4 py-2.5 bg-white rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500 disabled:opacity-60"
            />
          </div>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden flex flex-col flex-1 min-h-0">
          <div className="hidden lg:flex items-center justify-between px-4 py-3 border-b border-white/10 flex-shrink-0">
            <div className="h-7 w-32 bg-white/10 rounded-lg animate-pulse" />
            <div className="flex items-center gap-2 text-sm text-white/50">
              <Spinner size="xs" />
              Loading customers…
            </div>
          </div>
          <div className="overflow-hidden flex-1">
            <table className="w-full text-sm">
              <thead className="bg-white/5 text-white/70 text-xs uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Customer</th>
                  <th className="px-4 py-3 text-left font-medium hidden sm:table-cell">Email</th>
                  <th className="px-4 py-3 text-left font-medium hidden sm:table-cell">Phone</th>
                  <th className="px-4 py-3 text-left font-medium hidden xl:table-cell">DOT / MC</th>
                  <th className="px-4 py-3 text-left font-medium hidden xl:table-cell">Vehicles</th>
                  <th className="px-4 py-3 text-right font-medium hidden md:table-cell">Balance</th>
                  <th className="px-4 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {[...Array(12)].map((_, i) => (
                  <tr key={i} className="animate-pulse">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-white/10 flex-shrink-0" />
                        <div className="h-4 bg-white/10 rounded w-32" />
                      </div>
                    </td>
                    <td className="px-4 py-3 hidden sm:table-cell"><div className="h-4 bg-white/10 rounded w-36" /></td>
                    <td className="px-4 py-3 hidden sm:table-cell"><div className="h-4 bg-white/10 rounded w-24" /></td>
                    <td className="px-4 py-3 hidden xl:table-cell"><div className="h-4 bg-white/10 rounded w-20" /></td>
                    <td className="px-4 py-3 hidden xl:table-cell"><div className="h-4 bg-white/10 rounded w-8" /></td>
                    <td className="px-4 py-3 hidden md:table-cell"><div className="h-4 bg-white/10 rounded w-16 ml-auto" /></td>
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

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 sm:mb-6 flex-shrink-0">
        <h1 className="text-xl sm:text-2xl font-bold text-white">Customers</h1>
        <button
          onClick={openCreateModal}
          className="mt-3 sm:mt-0 px-4 py-2 text-white font-medium rounded-lg transition-colors"
          style={{ backgroundColor: accentColors[500] }}
        >
          + Add Customer
        </button>
      </div>

      {/* Search Bar */}
      <div className="mb-6 flex-shrink-0">
        <div className="relative">
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
            placeholder="Search by name, email, or phone..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white rounded-lg text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500"
          />
        </div>
      </div>

      <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden flex flex-col flex-1 min-h-0">
        {/* Header with ViewToggle. Total count lives in the pagination footer. */}
        <div className="hidden lg:flex items-center justify-between px-4 py-3 border-b border-white/10 flex-shrink-0">
          <ViewToggle value={activeViewMode} onChange={setViewMode} disabled={isMobile} />
        </div>

        <div className="overflow-y-auto flex-1 min-h-0 relative">
          {/* Loading overlay for page/search/sort changes (first load uses the
              full skeleton below; this covers subsequent batch fetches). */}
          {isFetching && !isLoading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-blueNoir-900/40 backdrop-blur-[1px] pointer-events-none">
              <Spinner size="md" className="border-white/40 border-t-white" />
            </div>
          )}
          {activeViewMode === 'list' ? (
            /* List View */
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-white/5 text-white/70 text-xs uppercase tracking-wider">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">
                      <button
                        onClick={() => toggleSort('name')}
                        className="flex items-center gap-1 hover:text-white transition-colors"
                      >
                        Customer
                        {sortField === 'name' && (sortDirection === 'asc' ? (
                          <ArrowUp className="w-3 h-3" />
                        ) : (
                          <ArrowDown className="w-3 h-3" />
                        ))}
                      </button>
                    </th>
                    <th className="px-4 py-3 text-left font-medium hidden sm:table-cell">Email</th>
                    <th className="px-4 py-3 text-left font-medium hidden sm:table-cell whitespace-nowrap">Phone</th>
                    <th className="px-4 py-3 text-left font-medium hidden xl:table-cell">DOT / MC</th>
                    <th className="px-4 py-3 text-left font-medium hidden xl:table-cell">
                      <button
                        onClick={() => toggleSort('vehicle_count')}
                        className="flex items-center gap-1 hover:text-white transition-colors whitespace-nowrap"
                      >
                        Vehicles
                        {sortField === 'vehicle_count' && (sortDirection === 'asc' ? (
                          <ArrowUp className="w-3 h-3" />
                        ) : (
                          <ArrowDown className="w-3 h-3" />
                        ))}
                      </button>
                    </th>
                    <th className="px-4 py-3 text-right font-medium hidden md:table-cell">
                      <button
                        onClick={() => toggleSort('balance')}
                        className="flex items-center gap-1 ml-auto hover:text-white transition-colors"
                      >
                        Balance
                        {sortField === 'balance' && (sortDirection === 'asc' ? (
                          <ArrowUp className="w-3 h-3" />
                        ) : (
                          <ArrowDown className="w-3 h-3" />
                        ))}
                      </button>
                    </th>
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
                          <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0" style={{ backgroundColor: accentColors[500] }}>
                            <span className="text-white font-bold text-xs">
                              {customer.first_name.charAt(0)}{customer.last_name.charAt(0)}
                            </span>
                          </div>
                          <div className="flex flex-col gap-0.5 min-w-0">
                            <span className="text-white font-medium truncate">{customerDisplayName(customer)}</span>
                            <MatchBadges matchedFields={customer.matched_fields} />
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-white/70 hidden sm:table-cell">{customer.email}</td>
                      <td className="px-4 py-3 text-white/70 hidden sm:table-cell whitespace-nowrap">
                        {customer.phone ? formatUSPhone(customer.phone) : '—'}
                      </td>
                      <td className="px-4 py-3 text-white/70 hidden xl:table-cell text-xs">
                        {customer.usdot_number && <div>DOT {stripRegNumber(customer.usdot_number)}</div>}
                        {customer.mc_number && <div>MC {stripRegNumber(customer.mc_number)}</div>}
                        {!customer.usdot_number && !customer.mc_number && '—'}
                      </td>
                      <td className="px-4 py-3 text-white/70 hidden xl:table-cell">
                        {customer.vehicle_count || 0}
                      </td>
                      <td className="px-4 py-3 text-right hidden md:table-cell">
                        {customer.balance !== undefined ? (
                          <span className={parseFloat(customer.balance) > 0 ? 'text-amber-400' : 'text-white/70'}>
                            ${parseFloat(customer.balance).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            openDetailPanel(customer)
                          }}
                          className="text-sm font-medium hover:opacity-80"
                          style={{ color: accentColors[400] }}
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
                  className="bg-gradient-to-br from-yellow-50 via-amber-100 to-yellow-200 p-4 sm:p-5 rounded-xl shadow-lg flex flex-col gap-3 hover:shadow-xl transition-shadow cursor-pointer"
                >
                  <div>
                    <div className="w-12 h-12 rounded-full flex items-center justify-center mb-3" style={{ backgroundColor: accentColors[500] }}>
                      <span className="text-white font-bold text-lg">
                        {customer.first_name.charAt(0)}{customer.last_name.charAt(0)}
                      </span>
                    </div>
                    <h3 className="text-lg font-bold text-slate-800 leading-tight">
                      {customerDisplayName(customer)}
                    </h3>
                    <MatchBadges matchedFields={customer.matched_fields} variant="light" />
                  </div>

                  <div className="space-y-2 text-sm">
                    {customer.company_name && customerPersonalName(customer) && (
                      <div className="text-slate-500">{customerPersonalName(customer)}</div>
                    )}
                    <div className="flex items-center gap-2 text-slate-600">
                      <Mail className="w-4 h-4 flex-shrink-0" />
                      <span className="truncate">{customer.email}</span>
                    </div>
                    {customer.phone && (
                      <div className="flex items-center gap-2 text-slate-600 whitespace-nowrap">
                        <Phone className="w-4 h-4 flex-shrink-0" />
                        <span>{formatUSPhone(customer.phone)}</span>
                      </div>
                    )}
                    {(customer.usdot_number || customer.mc_number) && (
                      <div className="text-xs text-slate-500">
                        {customer.usdot_number && <span>DOT {stripRegNumber(customer.usdot_number)}</span>}
                        {customer.usdot_number && customer.mc_number && <span> · </span>}
                        {customer.mc_number && <span>MC {stripRegNumber(customer.mc_number)}</span>}
                      </div>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-2 pt-1">
                    <div className="bg-white/50 rounded-lg px-3 py-2">
                      <p className="text-[11px] text-slate-500">Balance</p>
                      <p className={`text-sm font-semibold ${customer.balance && parseFloat(customer.balance) > 0 ? 'text-amber-700' : 'text-slate-800'}`}>
                        {customer.balance !== undefined
                          ? `$${parseFloat(customer.balance).toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                          : '—'}
                      </p>
                    </div>
                    <div className="bg-white/50 rounded-lg px-3 py-2">
                      <p className="text-[11px] text-slate-500">Vehicles</p>
                      <p className="text-sm font-semibold text-slate-800">{customer.vehicle_count || 0}</p>
                    </div>
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
                className="bg-white/20 border-2 border-dashed border-white/40 p-4 sm:p-5 rounded-xl flex flex-col items-center justify-center cursor-pointer hover:bg-white/30 hover:border-white/60 transition-all min-h-[200px]"
              >
                <div className="w-12 h-12 rounded-full bg-white/30 flex items-center justify-center mb-3">
                  <Plus className="w-6 h-6 text-white" />
                </div>
                <span className="text-white font-medium">Add Customer</span>
              </div>
            </div>
          )}
        </div>

        {/* Pagination footer (also carries the total count) */}
        {totalCustomers > 0 && (
          <div className={`flex items-center justify-between px-4 py-3 border-t border-white/10 flex-shrink-0 text-sm text-white/70 ${isPlaceholderData ? 'opacity-60' : ''}`}>
            <span>
              {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, totalCustomers)} of {totalCustomers} customer{totalCustomers !== 1 ? 's' : ''}
            </span>
            {totalCustomers > PAGE_SIZE && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0 || isPlaceholderData}
                  className="px-3 py-1.5 rounded-lg border border-white/15 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage((p) => (customerPage?.has_more ? p + 1 : p))}
                  disabled={!customerPage?.has_more || isPlaceholderData}
                  className="px-3 py-1.5 rounded-lg border border-white/15 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Next
                </button>
              </div>
            )}
          </div>
        )}
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
        width="max-w-[max(50vw,_400px)]"
        title={
          selectedVehicleInPanel
            ? vehicleDisplayLabel(selectedVehicleInPanel)
            : selectedCustomer
            ? customerDisplayName(selectedCustomer, '')
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
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleDeleteClick(selectedCustomer)}
                  className="px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors text-sm font-medium flex items-center gap-2"
                >
                  <Trash2 className="w-4 h-4" />
                  Delete
                </button>
                <button
                  onClick={() => setIsMergeModalOpen(true)}
                  className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors text-sm font-medium flex items-center gap-2"
                >
                  <User className="w-4 h-4" />
                  Merge
                </button>
              </div>
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
                    {customerDisplayName(selectedCustomer)}
                  </p>
                  {selectedCustomer.company_name && customerPersonalName(selectedCustomer) && (
                    <p className="text-sm text-gray-500">{customerPersonalName(selectedCustomer)}</p>
                  )}
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
                          // Navigate to repair order (SPA nav, not a hard reload —
                          // a full page reload here would blow away the RO list's
                          // React Query cache and force the whole paginated fetch
                          // to run again just to open one panel)
                          navigate(`/dashboard/repair-orders?selected=${order.id}`)
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
                  {/* Tabs */}
                  <div className="flex border-b border-gray-200 -mt-2">
                    <button
                      type="button"
                      onClick={() => setDetailTab('overview')}
                      className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
                        detailTab === 'overview'
                          ? 'border-amber-500 text-amber-700'
                          : 'border-transparent text-gray-500 hover:text-gray-700'
                      }`}
                    >
                      Overview
                    </button>
                    <button
                      type="button"
                      onClick={() => setDetailTab('history')}
                      className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
                        detailTab === 'history'
                          ? 'border-amber-500 text-amber-700'
                          : 'border-transparent text-gray-500 hover:text-gray-700'
                      }`}
                    >
                      History
                    </button>
                  </div>

                  {detailTab === 'history' ? (
                    <div className="space-y-6">
                      {/* Lifetime stats */}
                      <div className="grid grid-cols-3 gap-3">
                        <div className="bg-gray-50 rounded-xl p-4 text-center">
                          <p className="text-2xl font-bold text-gray-900">
                            {isLoadingHistory ? '—' : customerHistory?.stats.completed_orders ?? 0}
                          </p>
                          <p className="text-xs text-gray-500">Completed ROs</p>
                        </div>
                        <div className="bg-gray-50 rounded-xl p-4 text-center">
                          <p className="text-2xl font-bold text-gray-900">
                            {isLoadingHistory ? '—' : `$${parseFloat(customerHistory?.stats.lifetime_spend || '0').toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
                          </p>
                          <p className="text-xs text-gray-500">Lifetime spend</p>
                        </div>
                        <div className="bg-emerald-50 rounded-xl p-4 text-center">
                          <p className="text-2xl font-bold text-emerald-700">
                            {isLoadingHistory ? '—' : `$${parseFloat(customerHistory?.stats.lifetime_savings || '0').toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
                          </p>
                          <p className="text-xs text-emerald-700/80">Total saved</p>
                        </div>
                      </div>

                      {/* RO list */}
                      <div>
                        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Repair Orders</h3>
                        {isLoadingHistory ? (
                          <LoadingLine className="text-gray-400">Loading…</LoadingLine>
                        ) : !customerHistory?.items.length ? (
                          <div className="bg-gray-50 rounded-xl p-6 text-center border border-gray-100">
                            <Wrench className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                            <p className="text-sm text-gray-500">No repair orders yet</p>
                          </div>
                        ) : (
                          <div className="bg-gray-50 rounded-xl border border-gray-100 overflow-hidden">
                            <table className="w-full text-sm">
                              <thead className="bg-gray-100 text-gray-600 text-xs uppercase tracking-wider">
                                <tr>
                                  <th className="px-3 py-2 text-left font-medium">RO</th>
                                  <th className="px-3 py-2 text-left font-medium">Vehicle</th>
                                  <th className="px-3 py-2 text-left font-medium">Status</th>
                                  <th className="px-3 py-2 text-right font-medium">Saved</th>
                                  <th className="px-3 py-2 text-right font-medium">Total</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-gray-100">
                                {customerHistory.items.map((ro) => {
                                  const dateStr = ro.work_completed_at || ro.created_at
                                  const dateFmt = dateStr ? new Date(dateStr).toLocaleDateString() : '—'
                                  const saving = parseFloat(ro.savings || '0')
                                  const isExpanded = expandedHistoryId === ro.id
                                  return (
                                    <React.Fragment key={ro.id}>
                                      <tr
                                        onClick={() => setExpandedHistoryId(isExpanded ? null : ro.id)}
                                        className={`hover:bg-gray-100/50 cursor-pointer ${isExpanded ? 'bg-amber-50/40' : ''}`}
                                      >
                                        <td className="px-3 py-2.5 text-gray-900 font-medium">
                                          <span className="inline-flex items-center gap-1">
                                            <span className={`text-gray-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`}>›</span>
                                            {ro.order_number}
                                          </span>
                                          <div className="text-[11px] text-gray-500 font-normal ml-3">{dateFmt}</div>
                                        </td>
                                        <td className="px-3 py-2.5 text-gray-700">
                                          {vehicleDisplayLabel({
                                            year: ro.vehicle_year,
                                            make: ro.vehicle_make,
                                            model: ro.vehicle_model,
                                            unit_number: ro.vehicle_unit_number,
                                          })}
                                          {ro.vehicle_unit_number && (
                                            <div className="text-[11px] text-gray-500">#{ro.vehicle_unit_number}</div>
                                          )}
                                        </td>
                                        <td className="px-3 py-2.5">
                                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-200 text-gray-700 capitalize">
                                            {ro.status.replace('_', ' ')}
                                          </span>
                                        </td>
                                        <td className="px-3 py-2.5 text-right">
                                          {saving > 0 ? (
                                            <span className="text-emerald-600 font-medium">−${saving.toFixed(2)}</span>
                                          ) : (
                                            <span className="text-gray-300">—</span>
                                          )}
                                        </td>
                                        <td className="px-3 py-2.5 text-right text-gray-900 font-semibold">
                                          ${parseFloat(ro.total_cost).toFixed(2)}
                                        </td>
                                      </tr>
                                      {isExpanded && selectedCustomer && (
                                        <tr className="bg-white">
                                          <td colSpan={5} className="px-4 py-3 border-t border-amber-100">
                                            <HistoryRoDetail customerId={selectedCustomer.id} orderId={ro.id} />
                                          </td>
                                        </tr>
                                      )}
                                    </React.Fragment>
                                  )
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                  <>
                  {/* Summary row: Contact, US DOT, MC Number, Address, Customer Since,
                      Balance — the at-a-glance facts about this company, laid out as a
                      row of small stat blocks (matches the source system's layout). */}
                  <div>
                    <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Summary</h3>
                    <div className="bg-gray-50 rounded-xl p-4 grid grid-cols-2 sm:grid-cols-3 gap-4">
                      {(() => {
                        const namedContacts = (customerContacts || []).filter((c) => c.first_name || c.last_name)
                        const askFor = namedContacts.find((c) => c.is_primary) || namedContacts[0]
                        const askForName = askFor ? [askFor.first_name, askFor.last_name].filter(Boolean).join(' ') : null
                        return (
                          <div>
                            <p className="text-xs text-gray-500">Contact</p>
                            {askForName ? (
                              <>
                                <p className="text-gray-900 font-medium">{askForName}</p>
                                {askFor?.phone && (
                                  <a href={`tel:${askFor.phone}`} className="text-xs text-gray-500 hover:text-amber-600 block">
                                    {formatUSPhone(askFor.phone)}
                                  </a>
                                )}
                              </>
                            ) : (
                              <>
                                {selectedCustomer.phone && (
                                  <a href={`tel:${selectedCustomer.phone}`} className="text-gray-900 hover:text-amber-600 font-medium block">
                                    {formatUSPhone(selectedCustomer.phone)}
                                  </a>
                                )}
                                <a href={`mailto:${selectedCustomer.email}`} className="text-xs text-gray-500 hover:text-amber-600 block">
                                  {selectedCustomer.email}
                                </a>
                              </>
                            )}
                          </div>
                        )
                      })()}

                      <div>
                        <p className="text-xs text-gray-500">US DOT</p>
                        <p className="text-gray-900 font-medium">{stripRegNumber(selectedCustomer.usdot_number) || '—'}</p>
                      </div>

                      <div>
                        <p className="text-xs text-gray-500">MC Number</p>
                        <p className="text-gray-900 font-medium">{stripRegNumber(selectedCustomer.mc_number) || '—'}</p>
                      </div>

                      <div>
                        <p className="text-xs text-gray-500">Address</p>
                        {selectedCustomer.billing_address_line1 || selectedCustomer.billing_city ? (
                          <div className="text-gray-900 text-sm">
                            {selectedCustomer.billing_address_line1 && <p>{selectedCustomer.billing_address_line1}</p>}
                            <p>
                              {[selectedCustomer.billing_city, selectedCustomer.billing_state, selectedCustomer.billing_zip]
                                .filter(Boolean)
                                .join(', ')}
                            </p>
                          </div>
                        ) : (
                          <p className="text-gray-900 font-medium">—</p>
                        )}
                      </div>

                      <div>
                        <p className="text-xs text-gray-500">Customer Since</p>
                        <p className="text-gray-900 font-medium">
                          {new Date(selectedCustomer.created_at).toLocaleDateString()}
                        </p>
                      </div>

                      <div>
                        <p className="text-xs text-gray-500">Balance</p>
                        <p className={`font-semibold ${selectedCustomer.balance && parseFloat(selectedCustomer.balance) > 0 ? 'text-amber-600' : 'text-gray-900'}`}>
                          {selectedCustomer.balance !== undefined
                            ? `$${parseFloat(selectedCustomer.balance).toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                            : '—'}
                        </p>
                      </div>

                      {selectedCustomer.source && (
                        <div>
                          <p className="text-xs text-gray-500">Source</p>
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">
                            {formatCustomerSource(selectedCustomer.source)}
                          </span>
                        </div>
                      )}

                      <div>
                        <p className="text-xs text-gray-500">QuickBooks</p>
                        {selectedCustomer.quickbooks_customer_id ? (
                          <span className="inline-flex items-center gap-1 text-emerald-700 text-sm font-medium">
                            ✓ Linked
                          </span>
                        ) : (
                          <span className="text-gray-400 text-sm">Not linked</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Contacts: named individuals at this company (dispatcher, owner,
                      driver). The auto-created "Main Line" placeholder (no name, just
                      mirrors the company's own email/phone shown above) is filtered out. */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Contacts</h3>
                      <div className="flex items-center gap-2">
                        {isLoadingContacts && <span className="text-xs text-gray-400">Loading...</span>}
                        <button
                          onClick={openAddContactModal}
                          className="px-3 py-1.5 text-xs font-medium text-amber-600 bg-amber-50 hover:bg-amber-100 rounded-lg transition-colors flex items-center gap-1"
                        >
                          <Plus className="w-3.5 h-3.5" />
                          Add Contact
                        </button>
                      </div>
                    </div>
                    {(() => {
                      const namedContacts = (customerContacts || []).filter((c) => c.first_name || c.last_name)
                      if (namedContacts.length === 0) {
                        return (
                          <div className="bg-gray-50 rounded-xl p-4 text-sm text-gray-500 text-center">
                            No named contacts yet — using the company's own email/phone above.
                          </div>
                        )
                      }
                      return (
                        <div className="bg-gray-50 rounded-xl border border-gray-100 overflow-hidden divide-y divide-gray-100">
                          {namedContacts.map((contact) => {
                            const name = [contact.first_name, contact.last_name].filter(Boolean).join(' ')
                            return (
                              <div key={contact.id} className="flex items-center justify-between gap-3 px-4 py-3 group">
                                <div className="flex items-center gap-3 min-w-0">
                                  <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                                    <User className="w-4 h-4 text-gray-500" />
                                  </div>
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-1.5">
                                      <p className="text-sm font-medium text-gray-900 truncate">{name}</p>
                                      {contact.is_primary && (
                                        <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500 flex-shrink-0" />
                                      )}
                                    </div>
                                    <div className="flex flex-wrap items-center gap-x-3 text-xs text-gray-500">
                                      {contact.role && <span>{contact.role}</span>}
                                      {contact.email && contact.email !== selectedCustomer.email && (
                                        <span className="flex items-center gap-1">
                                          <Mail className="w-3 h-3" />
                                          {contact.email}
                                        </span>
                                      )}
                                      {contact.phone && contact.phone !== selectedCustomer.phone && (
                                        <span className="flex items-center gap-1">
                                          <Phone className="w-3 h-3" />
                                          {formatUSPhone(contact.phone)}
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                </div>
                                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                                  <button
                                    onClick={() => openEditContactModal(contact)}
                                    className="p-1.5 text-gray-500 hover:text-amber-600 hover:bg-amber-50 rounded transition-colors"
                                    title="Edit"
                                  >
                                    <Pencil className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={() => handleDeleteContactClick(contact)}
                                    className="p-1.5 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                                    title="Delete"
                                  >
                                    <Trash2 className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      )
                    })()}
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
                        <div className="bg-gray-50 rounded-xl border border-gray-100 overflow-x-auto">
                          <table className="w-full min-w-[720px] text-sm">
                            <thead className="bg-gray-100 text-gray-600 text-xs uppercase tracking-wider">
                              <tr>
                                <th className="px-3 py-2 text-left font-medium">Vehicle</th>
                                {showVehicleUnitColumn && <th className="px-3 py-2 text-left font-medium">Unit</th>}
                                {showVehicleVinColumn && <th className="px-3 py-2 text-left font-medium">VIN</th>}
                                {showVehiclePlateColumn && <th className="px-3 py-2 text-left font-medium">Plate</th>}
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
                                    {vehicleDisplayLabel(vehicle)}
                                    {vehicle.color && <span className="text-gray-500 font-normal"> · {vehicle.color}</span>}
                                  </td>
                                  {showVehicleUnitColumn && (
                                    <td className="px-3 py-2.5">
                                      {vehicle.unit_number ? (
                                        <span className="text-xs font-medium text-slate-700 bg-slate-100 rounded px-1.5 py-0.5">
                                          {vehicle.unit_number}
                                        </span>
                                      ) : (
                                        <span className="text-gray-400">—</span>
                                      )}
                                    </td>
                                  )}
                                  {showVehicleVinColumn && (
                                    <td className="px-3 py-2.5">
                                      {vehicle.vin ? (
                                        <span className="font-mono text-xs text-gray-700">{vehicle.vin}</span>
                                      ) : (
                                        <span className="text-gray-400">—</span>
                                      )}
                                    </td>
                                  )}
                                  {showVehiclePlateColumn && (
                                    <td className="px-3 py-2.5">
                                      {vehicle.license_plate ? (
                                        <span className="text-xs font-medium text-amber-700 bg-amber-100 rounded px-1.5 py-0.5">
                                          {vehicle.license_plate}
                                        </span>
                                      ) : (
                                        <span className="text-gray-400">—</span>
                                      )}
                                    </td>
                                  )}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {customerVehicles.map((vehicle) => {
                            const displayLabel = vehicleDisplayLabel(vehicle)
                            const unitSuffix = vehicle.unit_number ? ` · Unit ${vehicle.unit_number}` : ''
                            const cardTitle = unitSuffix && displayLabel.endsWith(unitSuffix)
                              ? displayLabel.slice(0, -unitSuffix.length)
                              : displayLabel
                            return (
                              <div
                                key={vehicle.id}
                                className="bg-gray-50 rounded-xl p-4 pr-14 border border-gray-100 hover:bg-gray-100 hover:border-gray-200 transition-colors group relative"
                              >
                                <div
                                  onClick={() => setSelectedVehicleInPanel(vehicle)}
                                  className="cursor-pointer"
                                >
                                  <div className="flex items-start justify-between gap-4">
                                    <div className="min-w-0">
                                      <p className="truncate text-sm font-semibold text-gray-900">
                                        {cardTitle}
                                      </p>
                                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                                        {vehicle.color && <span>{vehicle.color}</span>}
                                        <span>{typeof vehicle.mileage === 'number' ? `${vehicle.mileage.toLocaleString()} mi` : 'No mileage'}</span>
                                      </div>
                                    </div>
                                    <div className="flex shrink-0 flex-col items-end gap-1 text-right">
                                      {vehicle.unit_number && (
                                        <span className="text-xs font-medium text-slate-700 bg-slate-100 rounded px-2 py-0.5">
                                          Unit {vehicle.unit_number}
                                        </span>
                                      )}
                                      {vehicle.license_plate && (
                                        <span className="text-xs font-medium text-amber-700 bg-amber-100 rounded px-2 py-0.5">
                                          {vehicle.license_plate}
                                        </span>
                                      )}
                                      {vehicle.vin && (
                                        <span className="font-mono text-[11px] text-gray-500">
                                          VIN {vehicle.vin}
                                        </span>
                                      )}
                                    </div>
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
                            )
                          })}
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
                  </>
                  )}
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
                    <Spinner size="xs" className="border-white/40 border-t-white" />
                  )}
                  Delete Customer
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Merge Customer Modal */}
      {isMergeModalOpen && selectedCustomer && (
        <div className="fixed inset-0 z-[60] overflow-y-auto">
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
            <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
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
                      for {selectedCustomer.company_name || `${selectedCustomer.first_name} ${selectedCustomer.last_name}`}
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
                    <Spinner size="xs" className="border-white/40 border-t-white" />
                  )}
                  Delete Vehicle
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Contact Modal (Add/Edit) */}
      {isContactModalOpen && selectedCustomer && (
        <div className="fixed inset-0 z-[60] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {/* Backdrop */}
            <div
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={closeContactModal}
            />

            {/* Modal */}
            <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
              {/* Header */}
              <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 rounded-t-2xl">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-gray-900">
                      {editingContact ? 'Edit Contact' : 'Add Contact'}
                    </h2>
                    <p className="text-sm text-gray-500">
                      for {selectedCustomer.company_name || `${selectedCustomer.first_name} ${selectedCustomer.last_name}`}
                    </p>
                  </div>
                  <button
                    onClick={closeContactModal}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <X className="w-5 h-5 text-gray-500" />
                  </button>
                </div>
              </div>

              {/* Form */}
              {renderContactForm()}
            </div>
          </div>
        </div>
      )}

      {/* Delete Contact Confirmation Modal */}
      {deleteConfirmContact && selectedCustomer && (
        <div className="fixed inset-0 z-[70] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {/* Backdrop */}
            <div
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setDeleteConfirmContact(null)}
            />

            {/* Modal */}
            <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
              <div className="flex items-center gap-4 mb-4">
                <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                  <AlertTriangle className="w-6 h-6 text-red-600" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-gray-900">Delete Contact</h3>
                  <p className="text-sm text-gray-500">This action cannot be undone</p>
                </div>
              </div>

              <p className="text-gray-700 mb-6">
                Are you sure you want to delete{' '}
                <span className="font-semibold">
                  {[deleteConfirmContact.first_name, deleteConfirmContact.last_name].filter(Boolean).join(' ') || 'this contact'}
                </span>
                ?
              </p>

              <div className="flex items-center justify-end gap-3">
                <button
                  onClick={() => setDeleteConfirmContact(null)}
                  className="px-4 py-2 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={confirmDeleteContact}
                  disabled={deleteContactMutation.isPending}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
                >
                  {deleteContactMutation.isPending && (
                    <Spinner size="xs" className="border-white/40 border-t-white" />
                  )}
                  Delete Contact
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
