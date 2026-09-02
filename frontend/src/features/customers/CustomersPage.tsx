import React, { useState, useMemo, useEffect, useRef } from 'react'
import { Spinner, LoadingLine, StaffSearchField } from '@/components/ui'
import { useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import api from '../../lib/api'
import { Customer, Vehicle, Contact, RepairOrder } from '../../types'
import { customerDisplayName, customerPersonalName } from '../../lib/customerName'
import { vehicleDisplayLabel } from '../../lib/vehicleName'
import { Combine, ArrowDown, ArrowRight, ArrowUp, ChevronDown, Mail, Pencil, Phone, Plus, Search, Star, Trash2, Truck, Wrench } from 'lucide-react'
import SlidePanel from '@/components/SlidePanel'
import CustomerDetailPanel from './CustomerDetailPanel'
import CustomerDetailFooter from './CustomerDetailFooter'
import CustomerFormModals, { type CustomerFormModalsHandle } from './CustomerFormModals'
import CustomerContactModals, { type CustomerContactModalsHandle } from './CustomerContactModals'
import CustomerVehicleModals, { type CustomerVehicleModalsHandle } from './CustomerVehicleModals'
import { useCustomerVehicleGroups } from './useCustomerVehicleGroups'
import {
  balanceAmountLabel,
  balanceLabel,
  balanceLabelClass,
  numericBalance,
  stripRegNumber,
} from './customerDetailFormat'
import type { CustomerHistoryResponse } from './customerDetailFormat'
import { formatUSPhone } from '@/utils/phone'
import ViewToggle from '@/components/ViewToggle'
import { useViewPreference } from '@/hooks/useViewPreference'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useTheme } from '../../contexts/ThemeContext'
import { useAuthStore } from '../../stores/authStore'
















// DOT/MC values may be stored bare ("107385") or, from the Easy Truck Shop
// import, with a redundant prefix ("MC-107385"). Strip a leading DOT/MC label
// so the UI's own "DOT "/"MC " prefix doesn't double up (e.g. "MC MC-107385").
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

function FleetMemberBadge({ variant = 'light' }: { variant?: 'dark' | 'light' | 'header' }) {
  const classes = {
    dark: 'bg-amber-300/15 text-amber-200 ring-amber-300/25',
    light: 'bg-amber-100 text-amber-900 ring-amber-300/70',
    header: 'bg-slate-950/20 text-white ring-white/25',
  }[variant]

  return (
    <span className={`inline-flex w-fit items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold leading-none ring-1 ring-inset ${classes}`}>
      <Star className="h-3.5 w-3.5 flex-none fill-current" aria-hidden="true" />
      Fleet member
    </span>
  )
}




export default function CustomersPage() {
  const { accentColors, presentationVariant } = useTheme()
  const currentUser = useAuthStore((state) => state.user)
  const navigate = useNavigate()
  const location = useLocation()
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
  const [viewMode, setViewMode] = useViewPreference('customers')
  const [isMobile, setIsMobile] = useState(false)
  
  // Detail panel state
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null)
  const [isDetailOpen, setIsDetailOpen] = useState(false)
  const [vehiclesViewMode, setVehiclesViewMode] = useViewPreference('customer-vehicles')
  const [vehicleRelationshipSearch, setVehicleRelationshipSearch] = useState('')
  const [vehicleRelationshipFilter, setVehicleRelationshipFilter] = useState<'all' | 'owned' | 'authority'>('all')
  const [selectedVehicleInPanel, setSelectedVehicleInPanel] = useState<Vehicle | null>(null)
  const [detailTab, setDetailTab] = useState<'overview' | 'history'>('overview')
  const [expandedHistoryId, setExpandedHistoryId] = useState<string | null>(null)
  const [workspaceFocusRequest, setWorkspaceFocusRequest] = useState(0)
  const [inspectedCustomerId, setInspectedCustomerId] = useState<string | null>(null)
  const customerRowRefs = useRef(new Map<string, HTMLElement>())
  const customerDetailsButtonRefs = useRef(new Map<string, HTMLButtonElement>())
  const selectionOriginRef = useRef<string | null>(null)
  const contactModalControls = useRef<CustomerContactModalsHandle | null>(null)
  const customerFormControls = useRef<CustomerFormModalsHandle | null>(null)
  const openCreateModal = () => customerFormControls.current?.openCreate()
  const handleEditFromDetail = () => selectedCustomer && customerFormControls.current?.openEdit(selectedCustomer)
  const handleDeleteClick = (customer: Customer) => customerFormControls.current?.requestDelete(customer)
  const vehicleModalControls = useRef<CustomerVehicleModalsHandle | null>(null)
  const openAddVehicleModal = () => vehicleModalControls.current?.openAdd()
  const openEditVehicleModal = (vehicle: Vehicle) => vehicleModalControls.current?.openEdit(vehicle)
  const handleDeleteVehicleClick = (vehicle: Vehicle) => vehicleModalControls.current?.requestDelete(vehicle)
  const openManageVehicleLinks = (vehicle: Vehicle) => vehicleModalControls.current?.openManageLinks(vehicle)
  const openVehicleMerge = () => vehicleModalControls.current?.openMerge()
  const openAddContactModal = () => contactModalControls.current?.openAdd()
  const openEditContactModal = (contact: Contact) => contactModalControls.current?.openEdit(contact)
  const handleDeleteContactClick = (contact: Contact) => contactModalControls.current?.requestDelete(contact)
  const selectedCustomerId = useMemo(() => {
    if (presentationVariant !== 'new') return null
    return new URLSearchParams(location.search).get('selected')
  }, [location.search, presentationVariant])

  // Mechanic lookup for vehicle history
  interface Mechanic {
    id: string
    first_name: string
    last_name: string
  }
  
  // Vehicle form state

  // Contact form state
  
  // Delete confirmation state

  // Merge customer state

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

  const customerOnCurrentPage = useMemo(
    () => customers?.find((customer) => customer.id === selectedCustomerId) ?? null,
    [customers, selectedCustomerId]
  )
  const {
    data: selectedCustomerRecord,
    isFetching: isFetchingSelectedCustomer,
    isError: isSelectedCustomerUnavailable,
  } = useQuery<Customer>({
    queryKey: ['customer', selectedCustomerId],
    queryFn: async () => (await api.get(`/customers/${selectedCustomerId}`)).data,
    enabled: presentationVariant === 'new' && !!selectedCustomerId && !customerOnCurrentPage,
    retry: false,
  })

  useEffect(() => {
    if (presentationVariant !== 'new') return
    if (!selectedCustomerId) {
      setIsDetailOpen(false)
      setSelectedCustomer(null)
      setSelectedVehicleInPanel(null)
      return
    }

    const customer = customerOnCurrentPage ?? selectedCustomerRecord
    if (!customer) return
    setSelectedCustomer(customer)
    setIsDetailOpen(true)
    setDetailTab('overview')
    setSelectedVehicleInPanel(null)
  }, [customerOnCurrentPage, presentationVariant, selectedCustomerId, selectedCustomerRecord])

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
    queryKey: ['customerVehicleRepairOrders', selectedVehicleInPanel?.id],
    queryFn: async () => {
      if (!selectedVehicleInPanel?.id) return []
      const response = await api.get('/repair-orders', {
        params: {
          vehicle_id: selectedVehicleInPanel.id,
        },
      })
      return response.data
    },
    // The overview already has a dedicated History tab. Fetch orders only
    // after a vehicle is opened, and only for that vehicle rather than every
    // order the customer has ever created.
    enabled: !!selectedVehicleInPanel?.id && isDetailOpen,
    staleTime: 30_000,
  })

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
  const vehicleRepairOrders = customerRepairOrders || []

  // Create mechanic lookup map
  const mechanicLookup = useMemo(() => {
    const map = new Map<string, Mechanic>()
    mechanics?.forEach(m => map.set(m.id, m))
    return map
  }, [mechanics])


  // VIN Decoder
  





  // Vehicle mutations






  const updateSelectedCustomerQuery = (customerId: string | null) => {
    const params = new URLSearchParams(location.search)
    if (customerId) params.set('selected', customerId)
    else params.delete('selected')
    const search = params.toString()
    navigate({ pathname: location.pathname, search: search ? `?${search}` : '' })
  }

  const openDetailPanel = (customer: Customer, moveFocus = false) => {
    selectionOriginRef.current = customer.id
    setSelectedCustomer(customer)
    setIsDetailOpen(true)
    setDetailTab('overview')
    setVehicleRelationshipSearch('')
    setVehicleRelationshipFilter('all')
    if (presentationVariant === 'new') {
      updateSelectedCustomerQuery(customer.id)
      if (moveFocus) setWorkspaceFocusRequest((request) => request + 1)
    }
  }

  const toggleCustomerInspection = (customerId: string) => {
    if (inspectedCustomerId === customerId) {
      closeCustomerInspection(customerId)
      return
    }
    setInspectedCustomerId(customerId)
  }

  const closeCustomerInspection = (customerId: string) => {
    customerDetailsButtonRefs.current.get(customerId)?.focus()
    setInspectedCustomerId(null)
  }

  const closeDetailPanel = () => {
    const restoreCustomerId = selectionOriginRef.current ?? selectedCustomer?.id ?? null
    setIsDetailOpen(false)
    setSelectedCustomer(null)
    setSelectedVehicleInPanel(null)
    setDetailTab('overview')
    setExpandedHistoryId(null)
    setVehicleRelationshipSearch('')
    setVehicleRelationshipFilter('all')
    if (presentationVariant === 'new') {
      updateSelectedCustomerQuery(null)
      window.requestAnimationFrame(() => {
        if (restoreCustomerId) customerRowRefs.current.get(restoreCustomerId)?.focus()
      })
    }
  }

  // Editing the company happens in the modal, the same way it does from the
  // list and from the repair-order workspace. It used to replace the detail
  // body in place, which meant the form could only ever live on this page.


  // Vehicle form helpers

  // Contact form helpers




  // ZIP code lookup for auto-filling city/state
  

  // Get states/provinces based on country



  const {
    vehicleCount,
    ownedVehicles,
    authorityVehicles,
    shouldShowVehicleSearch,
    visibleCustomerVehicleGroups,
    visibleVehicleCount,
    showVehicleUnitColumn,
    showVehicleVinColumn,
    showVehiclePlateColumn,
    vehicleTableColumnCount,
    vehicleRelationshipNote,
  } = useCustomerVehicleGroups({
    selectedCustomer,
    customerVehicles,
    vehicleRelationshipSearch,
    vehicleRelationshipFilter,
  })






  // Search, sort, and pagination are all done server-side now, so the rendered
  // list is simply the current page returned by the API.
  const filteredCustomers = customers

  const renderCustomerSearch = (disabled = false) => presentationVariant === 'new' ? (
    <StaffSearchField
      accessibleLabel="Search customers"
      className="db-customers-workspace__search mb-6 flex-shrink-0"
      placeholder="Search by name, email, or phone..."
    value={searchQuery}
      onChange={disabled ? undefined : (event) => setSearchQuery(event.target.value)}
      disabled={disabled}
    />
  ) : (
    <div className="mb-6 flex-shrink-0">
      <div className="relative">
        <Search aria-hidden="true" className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          aria-label="Search customers"
          placeholder="Search by name, email, or phone..."
        value={searchQuery}
          onChange={disabled ? undefined : (event) => setSearchQuery(event.target.value)}
          disabled={disabled}
          className="w-full rounded-lg bg-white py-2.5 pl-10 pr-4 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500 disabled:opacity-60"
        />
      </div>
    </div>
  )

  if (isLoading) {
    return (
      <div className="flex flex-col h-full min-h-0">
        <div className={`flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 sm:mb-6 flex-shrink-0${presentationVariant === 'new' ? ' db-operating-page-header' : ''}`}>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-white">Customers</h1>
            {presentationVariant === 'new' && <p>Find customers, their vehicles, and service history.</p>}
          </div>
          <button
            disabled
            className="mt-3 sm:mt-0 px-4 py-2 text-white font-medium rounded-lg opacity-60"
            style={{ backgroundColor: accentColors[500] }}
          >
            + Add Customer
          </button>
        </div>

        {/* Search Bar */}
        {renderCustomerSearch(true)}

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

  const renderCustomerInspectionBrief = (customer: Customer) => {
    const contacts = queryClient.getQueryData<Contact[]>(['customerContacts', customer.id])
    const vehicles = queryClient.getQueryData<Vehicle[]>(['customerVehicles', customer.id])
    const history = queryClient.getQueryData<CustomerHistoryResponse>(['customerHistory', customer.id])
    const primaryContact = contacts?.[0]
    const address = [
      customer.billing_address_line1,
      customer.billing_address_line2,
      [customer.billing_city, customer.billing_state, customer.billing_zip].filter(Boolean).join(', '),
      customer.billing_country,
    ].filter(Boolean).join(' · ')
    const accountIdentifiers = [
      customer.usdot_number ? `DOT ${stripRegNumber(customer.usdot_number)}` : null,
      customer.mc_number ? `MC ${stripRegNumber(customer.mc_number)}` : null,
    ].filter(Boolean).join(' · ')

    return (
      <section
        id={`customer-inspection-${customer.id}`}
        className="db-customer-inspection"
        aria-label={`${customerDisplayName(customer)} details`}
        onKeyDown={(event) => {
          if (event.key !== 'Escape') return
          event.stopPropagation()
          closeCustomerInspection(customer.id)
        }}
      >
        <div className="db-customer-inspection__facts">
          {(primaryContact || customerPersonalName(customer) || customer.email) && <div>
            <h3>Primary contact</h3>
            {(primaryContact || customerPersonalName(customer)) && <p>{primaryContact ? [primaryContact.first_name, primaryContact.last_name].filter(Boolean).join(' ') || customerPersonalName(customer) : customerPersonalName(customer)}</p>}
            {(primaryContact?.email || customer.email) && <p className="db-customer-inspection__meta">{primaryContact?.email || customer.email}</p>}
          </div>}
          {(address || accountIdentifiers || customer.source || customer.created_at) && <div>
            <h3>Account context</h3>
            {address && <p>{address}</p>}
            {accountIdentifiers && <p className="db-customer-inspection__meta">{accountIdentifiers}</p>}
            {(customer.source || customer.created_at) && <p className="db-customer-inspection__meta">
              {customer.source && `Source: ${customer.source}`}
              {customer.source && customer.created_at && ' · '}
              {customer.created_at && `Customer since ${new Date(customer.created_at).toLocaleDateString()}`}
            </p>}
          </div>}
          <div>
            <h3>Balance</h3>
            <p>{customer.balance !== undefined ? balanceLabel(customer.balance) : 'Not available'}</p>
          </div>
          <div>
            <h3>Vehicles &amp; relationships</h3>
            <p>{vehicles ? `${vehicles.length} connected vehicle${vehicles.length === 1 ? '' : 's'}` : `${customer.vehicle_count || 0} connected vehicle${customer.vehicle_count === 1 ? '' : 's'}`}</p>
            {customer.fleet_enabled && <p className="db-customer-inspection__meta">Fleet relationship enabled</p>}
          </div>
          <div>
            <h3>Service history</h3>
            {history ? (
              <p>{history.stats.total_orders} repair order{history.stats.total_orders === 1 ? '' : 's'} · {history.stats.completed_orders} completed</p>
            ) : (
              <p>Available in the customer workspace</p>
            )}
          </div>
        </div>
        <div className="db-customer-inspection__actions">
          <button
            type="button"
            className="db-customer-inspection__open"
            onClick={(event) => {
              event.stopPropagation()
              openDetailPanel(customer, true)
            }}
          >
            Open customer
            <ArrowRight aria-hidden="true" />
          </button>
        </div>
      </section>
    )
  }

  return (
    <div className={`db-customers-workspace flex flex-col h-full min-h-0${presentationVariant === 'new' && selectedCustomerId ? ' db-customers-workspace--detail-open' : ''}`}>
      <div className={`flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 sm:mb-6 flex-shrink-0${presentationVariant === 'new' ? ' db-operating-page-header' : ''}`}>
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-white">Customers</h1>
          {presentationVariant === 'new' && <p>Find customers, their vehicles, and service history.</p>}
        </div>
        <button
          onClick={openCreateModal}
          className="mt-3 sm:mt-0 px-4 py-2 text-white font-medium rounded-lg transition-colors"
          style={{ backgroundColor: accentColors[500] }}
        >
          + Add Customer
        </button>
      </div>

      {/* Search Bar */}
      {renderCustomerSearch()}

      <div className="db-customers-workspace__ledger db-operating-surface__frame">
        {/* Header with ViewToggle. Total count lives in the pagination footer. */}
        <div className={`${presentationVariant === 'new' ? 'hidden' : 'hidden lg:flex'} items-center justify-between px-4 py-3 border-b border-white/10 flex-shrink-0`}>
          <ViewToggle value={activeViewMode} onChange={setViewMode} disabled={isMobile} />
        </div>

        <div className="db-operating-surface__scroller">
        <div className="db-operating-surface__card relative">
          {/* Loading overlay for page/search/sort changes (first load uses the
              full skeleton below; this covers subsequent batch fetches). */}
          {isFetching && !isLoading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-blueNoir-900/40 backdrop-blur-[1px] pointer-events-none">
              <Spinner size="md" className="border-white/40 border-t-white" />
            </div>
          )}
          {presentationVariant === 'new' ? (
            <div className="db-customer-navigator" role="list" aria-label="Customers">
              {filteredCustomers?.map((customer) => {
                const isSelected = selectedCustomerId === customer.id
                const isInspected = inspectedCustomerId === customer.id
                return (
                  <article
                    key={customer.id}
                    className="db-customer-navigator__record"
                    role="listitem"
                    aria-label={`${customerDisplayName(customer)} customer record`}
                    data-selected={isSelected ? 'true' : undefined}
                    data-inspected={isInspected ? 'true' : undefined}
                  >
                    <div
                      className="db-customer-navigator__summary"
                      tabIndex={0}
                      aria-label={`Open ${customerDisplayName(customer)} customer workspace`}
                      onClick={() => openDetailPanel(customer, true)}
                      onKeyDown={(event) => {
                        if (event.target !== event.currentTarget || event.key !== 'Enter') return
                        event.preventDefault()
                        openDetailPanel(customer, true)
                      }}
                    >
                      <div className="db-customer-navigator__identity">
                        <div className="db-customer-navigator__name-line">
                          <button
                            type="button"
                            ref={(node) => {
                              if (node) customerRowRefs.current.set(customer.id, node)
                              else customerRowRefs.current.delete(customer.id)
                            }}
                            className="db-customer-navigator__name-action"
                            aria-current={isSelected ? 'true' : undefined}
                            aria-label={`Open ${customerDisplayName(customer)} customer workspace`}
                            onClick={(event) => {
                              event.stopPropagation()
                              openDetailPanel(customer, true)
                            }}
                          >
                            <span className="db-customer-navigator__name">
                              {customerDisplayName(customer)}
                            </span>
                            <ArrowRight aria-hidden="true" />
                          </button>
                          {customer.fleet_enabled && <FleetMemberBadge variant="dark" />}
                        </div>
                        <MatchBadges matchedFields={customer.matched_fields} />
                      </div>
                      <span className="db-customer-navigator__phone">
                        <Phone aria-hidden="true" />
                        {customer.phone ? formatUSPhone(customer.phone) : 'No phone on file'}
                      </span>
                      {/* The operational facts the previous customer table carried
                          and the navigator dropped: authority numbers, fleet size,
                          and what the company owes. */}
                      <span className="db-customer-navigator__facts">
                        {(customer.usdot_number || customer.mc_number) && (
                          <span className="db-customer-navigator__fact">
                            {customer.usdot_number ? `DOT ${customer.usdot_number}` : null}
                            {customer.usdot_number && customer.mc_number ? ' · ' : null}
                            {customer.mc_number ? `MC ${customer.mc_number}` : null}
                          </span>
                        )}
                        {typeof customer.vehicle_count === 'number' && (
                          <span className="db-customer-navigator__fact">
                            {customer.vehicle_count} {customer.vehicle_count === 1 ? 'truck' : 'trucks'}
                          </span>
                        )}
                        {customer.balance != null && Number(customer.balance) !== 0 && (
                          <span className={`db-customer-navigator__fact${Number(customer.balance) > 0 ? ' is-owing' : ''}`}>
                            {Number(customer.balance) > 0 ? `Owes $${Number(customer.balance).toFixed(2)}` : `Credit $${Math.abs(Number(customer.balance)).toFixed(2)}`}
                          </span>
                        )}
                      </span>
                      <button
                        type="button"
                        ref={(node) => {
                          if (node) customerDetailsButtonRefs.current.set(customer.id, node)
                          else customerDetailsButtonRefs.current.delete(customer.id)
                        }}
                        onClick={(event) => {
                          event.stopPropagation()
                          toggleCustomerInspection(customer.id)
                        }}
                        onKeyDown={(event) => event.stopPropagation()}
                        aria-expanded={isInspected}
                        aria-controls={`customer-inspection-${customer.id}`}
                        className="db-customer-details-control"
                      >
                        Details
                        <ChevronDown aria-hidden="true" />
                      </button>
                    </div>
                    {isInspected && renderCustomerInspectionBrief(customer)}
                  </article>
                )
              })}
            </div>
          ) : activeViewMode === 'list' ? (
            /* List View */
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-white/5 text-white/70 text-xs uppercase tracking-wider">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">
                      <button
                        onClick={() => toggleSort('name')}
                        className="db-customer-sort-control flex items-center gap-1 hover:text-white transition-colors"
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
                        className="db-customer-sort-control flex items-center gap-1 hover:text-white transition-colors whitespace-nowrap"
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
                        className="db-customer-sort-control flex items-center gap-1 ml-auto hover:text-white transition-colors"
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
                    <React.Fragment key={customer.id}>
                    <tr
                      onClick={() => openDetailPanel(customer)}
                      onKeyDown={(event) => {
                        if (event.target !== event.currentTarget) return
                        if (event.key !== 'Enter' && event.key !== ' ') return
                        event.preventDefault()
                        openDetailPanel(customer, true)
                      }}
                      ref={(node) => {
                        if (node) customerRowRefs.current.set(customer.id, node)
                        else customerRowRefs.current.delete(customer.id)
                      }}
                      tabIndex={0}
                      aria-selected={selectedCustomerId === customer.id}
                      className="db-customer-ledger-row hover:bg-white/5 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="db-customer-avatar w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0" style={{ backgroundColor: accentColors[500] }}>
                            <span className="text-white font-bold text-xs">
                              {customer.first_name.charAt(0)}{customer.last_name.charAt(0)}
                            </span>
                          </div>
                          <div className="flex flex-col gap-0.5 min-w-0">
                            <div className="flex min-w-0 items-center gap-2">
                              <span className="min-w-0 truncate text-white font-medium">{customerDisplayName(customer)}</span>
                              {customer.fleet_enabled && <FleetMemberBadge variant="dark" />}
                            </div>
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
                          <span className={balanceLabelClass(customer.balance, true)}>
                            {balanceLabel(customer.balance)}
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation()
                            openDetailPanel(customer)
                          }}
                          className="text-emerald-400 hover:text-emerald-300"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            /* Cards View */
            <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filteredCustomers?.map((customer) => (
                <article
                  key={customer.id}
                  className="db-customer-ledger-card-group"
                  data-selected={selectedCustomerId === customer.id ? 'true' : undefined}
                >
                <div
                  onClick={() => openDetailPanel(customer)}
                  onKeyDown={(event) => {
                    if (event.target !== event.currentTarget) return
                    if (event.key !== 'Enter' && event.key !== ' ') return
                    event.preventDefault()
                    openDetailPanel(customer, true)
                  }}
                  ref={(node) => {
                    if (node) customerRowRefs.current.set(customer.id, node)
                    else customerRowRefs.current.delete(customer.id)
                  }}
                  role="button"
                  tabIndex={0}
                  aria-pressed={selectedCustomerId === customer.id}
                  className="db-customer-ledger-card bg-gradient-to-br from-yellow-50 via-amber-100 to-yellow-200 p-4 sm:p-5 rounded-xl shadow-lg flex flex-col gap-3 hover:shadow-xl transition-shadow cursor-pointer"
                >
                  <div>
                    <div className="mb-3 flex items-start justify-between gap-3">
                      <div className="db-customer-avatar w-12 h-12 rounded-full flex items-center justify-center" style={{ backgroundColor: accentColors[500] }}>
                        <span className="text-white font-bold text-lg">
                          {customer.first_name.charAt(0)}{customer.last_name.charAt(0)}
                        </span>
                      </div>
                      {customer.fleet_enabled && <FleetMemberBadge />}
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
                      <p className="text-[11px] text-slate-500">
                        {numericBalance(customer.balance) > 0 ? 'Balance due' : numericBalance(customer.balance) < 0 ? 'Account credit' : 'Balance'}
                      </p>
                      <p className={`text-sm font-semibold ${balanceLabelClass(customer.balance)}`}>
                        {customer.balance !== undefined
                          ? balanceAmountLabel(customer.balance)
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
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation()
                        openDetailPanel(customer)
                      }}
                      className="w-full text-center font-medium text-amber-700"
                    >
                      View Details
                    </button>
                  </div>
                </div>
                </article>
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
        </div>

        {/* Pagination footer (also carries the total count) */}
        {totalCustomers > 0 && (
          <div className={`db-customers-workspace__pagination mt-3 flex items-center justify-between px-1 py-2 flex-shrink-0 text-sm text-white/70 ${isPlaceholderData ? 'opacity-60' : ''}`}>
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

      {/* Customer Detail Slide-out Panel */}
      <SlidePanel
        isOpen={isDetailOpen && !!selectedCustomer}
        layout={presentationVariant === 'new' ? 'workspace' : 'drawer'}
        workspaceFocusRequest={presentationVariant === 'new' && workspaceFocusRequest > 0 ? workspaceFocusRequest : undefined}
        onClose={closeDetailPanel}
        width="max-w-full xl:max-w-[80vw] 2xl:max-w-[max(50vw,_960px)]"
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
        headerVariant={presentationVariant === 'new' ? 'minimal' : selectedVehicleInPanel ? 'slate' : 'amber'}
        hideClose={presentationVariant === 'new'}
        panelClassName={presentationVariant === 'new' ? 'db-customer-detail-workspace' : ''}
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
        headerExtra={selectedVehicleInPanel ? (
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => openEditVehicleModal(selectedVehicleInPanel)}
              className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-white px-4 py-2.5 font-semibold text-slate-800 shadow-sm transition-colors hover:bg-slate-100"
            >
              <Pencil className="h-4 w-4" />
              Edit Vehicle
            </button>
          </div>
        ) : selectedCustomer?.fleet_enabled ? (
          <FleetMemberBadge variant="header" />
        ) : undefined}
        onBack={
          selectedVehicleInPanel
            ? () => setSelectedVehicleInPanel(null)
            : presentationVariant === 'new'
              ? closeDetailPanel
              : undefined
        }
        backLabel={
          selectedVehicleInPanel && selectedCustomer
            ? `Back to ${selectedCustomer.first_name}`
            : presentationVariant === 'new'
              ? 'Back to Customers'
              : undefined
        }
        footer={
          selectedVehicleInPanel ? (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => handleDeleteVehicleClick(selectedVehicleInPanel)}
                className="flex min-h-11 items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50"
              >
                <Trash2 className="h-4 w-4" />
                Delete Vehicle
              </button>
              <div className="flex flex-wrap items-center justify-end gap-2">
                {(currentUser?.role === 'garage_owner' || currentUser?.role === 'garage_admin') && (
                  <button
                    type="button"
                    onClick={openVehicleMerge}
                    disabled={!selectedVehicleInPanel.vin || selectedVehicleInPanel.vin.replace(/[\s-]/g, '').length !== 17}
                    title={!selectedVehicleInPanel.vin || selectedVehicleInPanel.vin.replace(/[\s-]/g, '').length !== 17 ? 'A complete VIN is required to find safe duplicates' : undefined}
                    className="flex min-h-11 items-center gap-2 rounded-lg bg-gray-100 px-4 py-2.5 font-medium text-gray-700 transition-colors hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    <Combine className="h-4 w-4" />
                    Merge duplicate
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => openManageVehicleLinks(selectedVehicleInPanel)}
                  className="flex min-h-11 items-center gap-2 rounded-lg bg-amber-50 px-4 py-2.5 font-medium text-amber-700 transition-colors hover:bg-amber-100"
                >
                  <Truck className="h-4 w-4" />
                  Manage Connections
                </button>
              </div>
            </div>
          ) : selectedCustomer ? (
            <CustomerDetailFooter
              selectedCustomer={selectedCustomer}
              handleDeleteClick={handleDeleteClick}
              onMerge={() => customerFormControls.current?.openMerge()}
              handleEditFromDetail={handleEditFromDetail}
            />
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
                Repair History{isLoadingOrders ? '' : ` (${vehicleRepairOrders.length})`}
              </h3>
              {isLoadingOrders ? (
                <div className="bg-gray-50 rounded-xl p-4 text-center">
                  <LoadingLine className="text-gray-400">Loading repair history…</LoadingLine>
                </div>
              ) : vehicleRepairOrders.length === 0 ? (
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

          </div>
              ) : (
                <CustomerDetailPanel
                  selectedCustomer={selectedCustomer}
                  detailTab={detailTab}
                  setDetailTab={setDetailTab}
                  expandedHistoryId={expandedHistoryId}
                  setExpandedHistoryId={setExpandedHistoryId}
                  HistoryRoDetail={HistoryRoDetail}
                  customerVehicles={customerVehicles}
                  customerContacts={customerContacts}
                  customerHistory={customerHistory}
                  isLoadingVehicles={isLoadingVehicles}
                  isLoadingContacts={isLoadingContacts}
                  isLoadingHistory={isLoadingHistory}
                  ownedVehicles={ownedVehicles}
                  authorityVehicles={authorityVehicles}
                  visibleCustomerVehicleGroups={visibleCustomerVehicleGroups}
                  vehicleCount={vehicleCount}
                  visibleVehicleCount={visibleVehicleCount}
                  vehicleTableColumnCount={vehicleTableColumnCount}
                  vehicleRelationshipNote={vehicleRelationshipNote}
                  shouldShowVehicleSearch={shouldShowVehicleSearch}
                  showVehicleUnitColumn={showVehicleUnitColumn}
                  showVehicleVinColumn={showVehicleVinColumn}
                  showVehiclePlateColumn={showVehiclePlateColumn}
                  vehiclesViewMode={vehiclesViewMode}
                  setVehiclesViewMode={setVehiclesViewMode}
                  vehicleRelationshipSearch={vehicleRelationshipSearch}
                  setVehicleRelationshipSearch={setVehicleRelationshipSearch}
                  vehicleRelationshipFilter={vehicleRelationshipFilter}
                  setVehicleRelationshipFilter={setVehicleRelationshipFilter}
                  setSelectedVehicleInPanel={setSelectedVehicleInPanel}
                  openAddContactModal={openAddContactModal}
                  openEditContactModal={openEditContactModal}
                  handleDeleteContactClick={handleDeleteContactClick}
                  openAddVehicleModal={openAddVehicleModal}
                  openEditVehicleModal={openEditVehicleModal}
                  handleDeleteVehicleClick={handleDeleteVehicleClick}
                />
              )}
      </SlidePanel>

      {presentationVariant === 'new' && selectedCustomerId && !selectedCustomer && (
        <section
          className="db-customer-detail-workspace db-customer-detail-workspace--unavailable"
          role="region"
          aria-label="Customer workspace"
        >
          {isFetchingSelectedCustomer ? (
            <LoadingLine>Loading customer workspace…</LoadingLine>
          ) : isSelectedCustomerUnavailable ? (
            <>
              <h2>Customer workspace unavailable</h2>
              <p>This customer cannot be opened with your current access.</p>
              <button type="button" onClick={closeDetailPanel}>Back to Customers</button>
            </>
          ) : null}
        </section>
      )}

      {/* Delete Confirmation Modal */}

      {/* Merge Customer Modal */}

      {/* Add/Edit Vehicle Modal */}

      {/* Safe duplicate vehicle merge */}

      {/* Delete Vehicle Confirmation Modal */}

      {/* Contacts: add, edit and delete live with the forms themselves, so the
          repair-order workspace can host the same editing without owning this
          page's modal stack. */}
      {selectedCustomer && (
        <>
          <CustomerContactModals customer={selectedCustomer} controlsRef={contactModalControls} />
          <CustomerVehicleModals
            customer={selectedCustomer}
            selectedVehicleInPanel={selectedVehicleInPanel}
            setSelectedVehicleInPanel={setSelectedVehicleInPanel}
            controlsRef={vehicleModalControls}
          />
        </>
      )}
      <CustomerFormModals
        selectedCustomer={selectedCustomer}
        controlsRef={customerFormControls}
        onUpdated={(customer) => setSelectedCustomer(customer)}
        onDeleted={() => { setSelectedCustomer(null); setIsDetailOpen(false) }}
      />
    </div>
  )
}
