import React, { useEffect, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Combine, Search, Truck, X } from 'lucide-react'
import toast from 'react-hot-toast'

import api from '@/lib/api'

import { useTheme } from '@/contexts/ThemeContext'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { vehicleDisplayLabel } from '@/lib/vehicleName'
import { LoadingLine, Spinner } from '@/components/ui'
import type { Customer, Vehicle, VINDecodeResult } from '@/types'

interface DuplicateVinVehicleSummary {
  id: string
  vin?: string | null
  unit_number?: string | null
  year?: number | null
  make?: string | null
  model?: string | null
  license_plate?: string | null
  customer_id?: string | null
  customer_name?: string | null
  owner_lessor_name?: string | null
  operating_authority_name?: string | null
  default_invoice_recipient_name?: string | null
}

interface DuplicateVinConflict {
  message: string
  vehicle?: DuplicateVinVehicleSummary | null
}

interface VehicleMergeSummary {
  id: string
  customer_id: string
  customer_name: string
  vin: string
  unit_number: string | null
  make: string
  model: string
  year: number | null
  license_plate: string | null
  mileage: number | null
  source: string | null
  ets_external_id: string | null
  repair_order_count: number
  appointment_count: number
  inspection_count: number
  incident_count: number
  active_relationship_count: number
  active_fleet_membership_count: number
  repair_orders_by_source: Record<string, number>
}

interface VehicleMergePreview {
  canonical: VehicleMergeSummary
  duplicate: VehicleMergeSummary
  match_basis: 'vin' | 'unit_number'
  match_value: string
  recommended_canonical_id: string
  warnings: string[]
}

interface VehicleMergeResult {
  canonical_vehicle: Vehicle
  archived_vehicle_id: string
  merge_record_id: string
  moved: Record<string, number>
}

type VehicleRelationshipType = 'owner' | 'operator' | 'default_payer'

interface VehicleLinkCandidate {
  id: string
  customer_id: string
  make: string
  model: string
  year?: number | null
  unit_number?: string | null
  license_plate?: string | null
  vin?: string | null
}

interface VehicleAccountRelationship {
  id: string
  customer_id: string
  relationship_type: VehicleRelationshipType
  effective_to?: string | null
  is_primary: boolean
  customer_company_name?: string | null
}

const EMPTY_VEHICLE_RELATIONSHIPS: VehicleAccountRelationship[] = []

interface FleetCompanyOption {
  id: string
  company_name: string
  fleet_enabled: boolean
  is_internal_fleet: boolean
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



const duplicateVinFieldError = (error: any): DuplicateVinConflict | null => {
  const detail = error.response?.data?.detail
  if (error.response?.status !== 409) {
    return null
  }

  if (detail?.code === 'duplicate_vin') {
    return {
      message: typeof detail.message === 'string' ? detail.message : 'This VIN is already assigned to an existing truck.',
      vehicle: detail.vehicle || null,
    }
  }

  if (typeof detail === 'string' && /\bVIN\b/i.test(detail)) {
    return { message: 'This VIN is already assigned to an existing truck.' }
  }

  return null
}

/**
 * Adding, editing, linking, merging and removing a customer's trucks.
 *
 * All of it lived in CustomersPage, so the repair-order workspace could list a
 * carrier's trucks but not touch one — the operator had to leave the job to fix
 * a unit number. This is the larger half of that gap: five modes (new, link an
 * existing truck, edit, merge duplicates, delete) over fifteen pieces of state
 * and six mutations.
 *
 * The host supplies the customer and a ref; everything else stays in here, and
 * the mutations invalidate the same query keys both screens read.
 */
export type CustomerVehicleModalsHandle = {
  openAdd: () => void
  openEdit: (vehicle: Vehicle) => void
  requestDelete: (vehicle: Vehicle) => void
  openManageLinks: (vehicle: Vehicle) => void
  openMerge: () => void
}

export default function CustomerVehicleModals({
  customer,
  selectedVehicleInPanel,
  setSelectedVehicleInPanel = () => undefined,
  controlsRef,
}: {
  customer: Customer
  selectedVehicleInPanel?: Vehicle | null
  setSelectedVehicleInPanel?: (vehicle: Vehicle | null) => void
  controlsRef: React.MutableRefObject<CustomerVehicleModalsHandle | null>
}) {
  const queryClient = useQueryClient()
  const { accentColors } = useTheme()
  const selectedCustomer = customer

  const [isVehicleModalOpen, setIsVehicleModalOpen] = useState(false)
  const [editingVehicle, setEditingVehicle] = useState<Vehicle | null>(null)
  const [vehicleFormData, setVehicleFormData] = useState<VehicleFormData>(emptyVehicleForm)
  const [vehicleVinError, setVehicleVinError] = useState<DuplicateVinConflict | null>(null)
  const [vehicleModalMode, setVehicleModalMode] = useState<'new' | 'existing'>('new')
  const [vehicleLinkSearch, setVehicleLinkSearch] = useState('')
  const debouncedVehicleLinkSearch = useDebouncedValue(vehicleLinkSearch.trim(), 250)
  const [selectedLinkVehicle, setSelectedLinkVehicle] = useState<VehicleLinkCandidate | null>(null)
  const [vehicleRelationshipTypes, setVehicleRelationshipTypes] = useState<VehicleRelationshipType[]>([])
  const [vehicleLinkUnitNumber, setVehicleLinkUnitNumber] = useState('')
  const [operatingAuthorityCustomerId, setOperatingAuthorityCustomerId] = useState('')
  const [pendingFleetRemovalId, setPendingFleetRemovalId] = useState<string | null>(null)
  const [deleteConfirmVehicle, setDeleteConfirmVehicle] = useState<Vehicle | null>(null)
  const [isVehicleMergeOpen, setIsVehicleMergeOpen] = useState(false)
  const [mergeDuplicateVehicleId, setMergeDuplicateVehicleId] = useState<string | null>(null)
  const [mergeVinConfirmed, setMergeVinConfirmed] = useState(false)

  const { data: vehicleLinkCandidates = [], isFetching: isFetchingVehicleLinkCandidates } = useQuery<VehicleLinkCandidate[]>({
    queryKey: ['vehicle-link-candidates', debouncedVehicleLinkSearch],
    queryFn: async ({ signal }) => {
      const response = await api.get('/vehicles/typeahead', {
        signal,
        params: { q: debouncedVehicleLinkSearch || undefined, limit: 50 },
      })
      return response.data
    },
    enabled: isVehicleModalOpen && !editingVehicle && vehicleModalMode === 'existing',
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })

  // Include trucks already connected to this customer so the same picker can
  // review, unlink, and relink them instead of becoming a one-way operation.
  const availableVehicleLinkCandidates = vehicleLinkCandidates

  const { data: vehicleRelationships = EMPTY_VEHICLE_RELATIONSHIPS, isFetching: isFetchingVehicleRelationships } = useQuery<VehicleAccountRelationship[]>({
    queryKey: ['vehicle-account-relationships', selectedLinkVehicle?.id],
    queryFn: async () => (await api.get(`/vehicles/${selectedLinkVehicle!.id}/relationships`)).data,
    enabled: isVehicleModalOpen && vehicleModalMode === 'existing' && !!selectedLinkVehicle,
  })

  const { data: fleetCompanies = [] } = useQuery<FleetCompanyOption[]>({
    queryKey: ['fleet-companies'],
    queryFn: async () => (await api.get('/fleet/companies')).data,
    enabled: isVehicleModalOpen && vehicleModalMode === 'existing',
  })

  const { data: fleetSettings } = useQuery<{ default_fleet_authority_customer_id: string | null }>({
    queryKey: ['fleet-settings'],
    queryFn: async () => (await api.get('/fleet/settings')).data,
    enabled: isVehicleModalOpen && vehicleModalMode === 'existing',
  })

  useEffect(() => {
    if (!selectedLinkVehicle || !selectedCustomer) {
      setVehicleRelationshipTypes([])
      return
    }
    setVehicleRelationshipTypes(
      vehicleRelationships
        .filter((relationship) => !relationship.effective_to && relationship.customer_id === selectedCustomer.id)
        .map((relationship) => relationship.relationship_type),
    )
  }, [selectedCustomer, selectedLinkVehicle, vehicleRelationships])

  useEffect(() => {
    if (!selectedLinkVehicle) {
      setOperatingAuthorityCustomerId('')
      return
    }
    const activeOperators = vehicleRelationships.filter((relationship) => !relationship.effective_to && relationship.relationship_type === 'operator')
    const operator = activeOperators.find((relationship) => relationship.is_primary) || activeOperators[0]
    setOperatingAuthorityCustomerId((current) => operator?.customer_id || current || fleetSettings?.default_fleet_authority_customer_id || '')
  }, [selectedLinkVehicle, vehicleRelationships, fleetSettings?.default_fleet_authority_customer_id])


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
      const vinError = duplicateVinFieldError(error)
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
      const vinError = duplicateVinFieldError(error)
      if (vinError) {
        setVehicleVinError(vinError)
        return
      }
      toast.error(error.response?.data?.detail || 'Failed to update vehicle')
    },
  })

  const linkVehicleMutation = useMutation({
    mutationFn: async ({
      vehicleId,
      relationshipTypes,
      unitNumber,
    }: {
      vehicleId: string
      relationshipTypes: VehicleRelationshipType[]
      unitNumber: string
    }) => {
      if (!selectedCustomer) throw new Error('Select a customer before linking a truck')
      const response = await api.put(`/vehicles/${vehicleId}/relationships`, {
        customer_id: selectedCustomer.id,
        relationship_types: relationshipTypes.filter((relationshipType) => relationshipType !== 'operator'),
        operating_authority_customer_id: operatingAuthorityCustomerId || null,
        unit_number: unitNumber.trim() || null,
      })
      return response.data
    },
    onSuccess: (updatedVehicle: Vehicle) => {
      queryClient.invalidateQueries({ queryKey: ['customerVehicles', selectedCustomer?.id] })
      queryClient.invalidateQueries({ queryKey: ['vehicle-typeahead'] })
      queryClient.invalidateQueries({ queryKey: ['vehicle-link-candidates'] })
      queryClient.invalidateQueries({ queryKey: ['vehicle-account-relationships', updatedVehicle.id] })
      queryClient.invalidateQueries({ queryKey: ['fleet-board'] })
      if (selectedVehicleInPanel?.id === updatedVehicle.id) setSelectedVehicleInPanel(updatedVehicle)
      closeVehicleModal()
      toast.success('Truck roles updated')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || error.message || 'Failed to update truck roles')
    },
  })

  const removeFleetAssignmentMutation = useMutation({
    mutationFn: async ({ vehicleId, relationshipId }: { vehicleId: string; relationshipId: string; companyName: string }) => {
      await api.delete(`/vehicles/${vehicleId}/relationships/${relationshipId}`)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['customerVehicles'] })
      queryClient.invalidateQueries({ queryKey: ['vehicle-account-relationships', selectedLinkVehicle?.id] })
      queryClient.invalidateQueries({ queryKey: ['fleet-board'] })
      setPendingFleetRemovalId(null)
      toast.success(`Removed from ${variables.companyName} Fleet Board. Owner, payer, and service history were not changed.`)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to remove truck from Fleet Board')
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

  const mergeVehicleMutation = useMutation({
    mutationFn: async () => {
      if (!selectedVehicleInPanel || !mergeDuplicateVehicleId || !vehicleMergePreview) {
        throw new Error('Select a duplicate truck before merging')
      }
      const canonicalId = vehicleMergePreview.recommended_canonical_id
      const archivedId = canonicalId === selectedVehicleInPanel.id
        ? mergeDuplicateVehicleId
        : selectedVehicleInPanel.id
      const response = await api.post<VehicleMergeResult>(`/vehicles/${canonicalId}/merge`, {
        duplicate_vehicle_id: archivedId,
        confirm_vin: vehicleMergePreview.match_value,
      })
      return response.data
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['customerVehicles'] })
      queryClient.invalidateQueries({ queryKey: ['customerVehicleRepairOrders'] })
      queryClient.invalidateQueries({ queryKey: ['vehicle-link-candidates'] })
      queryClient.invalidateQueries({ queryKey: ['vehicle-merge-candidates'] })
      queryClient.invalidateQueries({ queryKey: ['fleet-board'] })
      setSelectedVehicleInPanel(result.canonical_vehicle)
      setIsVehicleMergeOpen(false)
      setMergeDuplicateVehicleId(null)
      setMergeVinConfirmed(false)
      const movedHistory = (result.moved.repair_orders || 0) + (result.moved.inspections || 0) + (result.moved.incidents || 0)
      toast.success(`Trucks merged. ${movedHistory} history record${movedHistory === 1 ? '' : 's'} moved to the kept truck.`)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || error.message || 'Failed to merge trucks')
    },
  })

  const openAddVehicleModal = () => {
    setEditingVehicle(null)
    setVehicleFormData(emptyVehicleForm)
    setVehicleVinError(null)
    setVehicleModalMode('new')
    setVehicleLinkSearch('')
    setSelectedLinkVehicle(null)
    setVehicleRelationshipTypes([])
    setVehicleLinkUnitNumber('')
    setOperatingAuthorityCustomerId('')
    setPendingFleetRemovalId(null)
    lastDecodedVehicleVin.current = ''
    setIsVehicleModalOpen(true)
  }

  const openEditVehicleModal = (vehicle: Vehicle) => {
    setEditingVehicle(vehicle)
    setVehicleVinError(null)
    setVehicleModalMode('new')
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
    setVehicleModalMode('new')
    setVehicleLinkSearch('')
    setSelectedLinkVehicle(null)
    setVehicleRelationshipTypes([])
    setOperatingAuthorityCustomerId('')
    setVehicleLinkUnitNumber('')
    lastDecodedVehicleVin.current = ''
  }

  const selectExistingTruckFromConflict = (vehicle: DuplicateVinVehicleSummary) => {
    setEditingVehicle(null)
    setVehicleVinError(null)
    setVehicleModalMode('existing')
    setVehicleLinkSearch(vehicle.vin || vehicle.unit_number || '')
    setSelectedLinkVehicle({
      id: vehicle.id,
      customer_id: vehicle.customer_id || '',
      make: vehicle.make || '',
      model: vehicle.model || '',
      year: vehicle.year,
      unit_number: vehicle.unit_number,
      license_plate: vehicle.license_plate,
      vin: vehicle.vin,
    })
    setVehicleLinkUnitNumber(vehicleFormData.unit_number.trim() || vehicle.unit_number || '')
    setVehicleRelationshipTypes([])
    setOperatingAuthorityCustomerId('')
  }

  const reviewDuplicateTruckConflict = (duplicate: DuplicateVinVehicleSummary) => {
    if (!editingVehicle) return
    const truckToKeep = editingVehicle
    closeVehicleModal()
    setSelectedVehicleInPanel(truckToKeep)
    setMergeDuplicateVehicleId(duplicate.id)
    setMergeVinConfirmed(false)
    setIsVehicleMergeOpen(true)
  }

  const openManageVehicleLinks = (vehicle: Vehicle) => {
    setEditingVehicle(null)
    setVehicleVinError(null)
    setVehicleModalMode('existing')
    setVehicleLinkSearch(vehicle.vin || vehicle.unit_number || '')
    setSelectedLinkVehicle({
      id: vehicle.id,
      customer_id: vehicle.customer_id,
      make: vehicle.make,
      model: vehicle.model,
      year: vehicle.year,
      unit_number: vehicle.unit_number,
      license_plate: vehicle.license_plate,
      vin: vehicle.vin,
    })
    setVehicleLinkUnitNumber(vehicle.unit_number || '')
    setVehicleRelationshipTypes([])
    setOperatingAuthorityCustomerId('')
    setIsVehicleModalOpen(true)
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

  const handleVehicleLinkSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedLinkVehicle) {
      toast.error('Select an existing truck to link')
      return
    }
    linkVehicleMutation.mutate({
      vehicleId: selectedLinkVehicle.id,
      relationshipTypes: vehicleRelationshipTypes,
      unitNumber: vehicleLinkUnitNumber,
    })
  }

  const handleDeleteVehicleClick = (vehicle: Vehicle) => {
    setDeleteConfirmVehicle(vehicle)
  }

  const openVehicleMerge = () => {
    setMergeDuplicateVehicleId(null)
    setMergeVinConfirmed(false)
    setIsVehicleMergeOpen(true)
  }

  const closeVehicleMerge = () => {
    if (mergeVehicleMutation.isPending) return
    setIsVehicleMergeOpen(false)
    setMergeDuplicateVehicleId(null)
    setMergeVinConfirmed(false)
  }

  const confirmDeleteVehicle = () => {
    if (deleteConfirmVehicle && selectedCustomer) {
      deleteVehicleMutation.mutate({
        customerId: selectedCustomer.id,
        vehicleId: deleteConfirmVehicle.id,
      })
    }
  }

const {
  data: vehicleMergeCandidates = [],
  isLoading: isLoadingVehicleMergeCandidates,
  isError: isVehicleMergeCandidatesError,
  refetch: refetchVehicleMergeCandidates,
} = useQuery<VehicleMergeSummary[]>({
  queryKey: ['vehicle-merge-candidates', selectedVehicleInPanel?.id],
  queryFn: async () => (
    await api.get(`/vehicles/${selectedVehicleInPanel!.id}/duplicate-candidates`)
  ).data,
  enabled: isVehicleMergeOpen && !!selectedVehicleInPanel,
})

useEffect(() => {
  if (!isVehicleMergeOpen) return
  if (vehicleMergeCandidates.length === 1 && !mergeDuplicateVehicleId) {
    setMergeDuplicateVehicleId(vehicleMergeCandidates[0].id)
  }
}, [isVehicleMergeOpen, mergeDuplicateVehicleId, vehicleMergeCandidates])

const {
  data: vehicleMergePreview,
  isLoading: isLoadingVehicleMergePreview,
  isError: isVehicleMergePreviewError,
} = useQuery<VehicleMergePreview>({
  queryKey: ['vehicle-merge-preview', selectedVehicleInPanel?.id, mergeDuplicateVehicleId],
  queryFn: async () => (
    await api.get(`/vehicles/${selectedVehicleInPanel!.id}/merge-preview/${mergeDuplicateVehicleId}`)
  ).data,
  enabled: isVehicleMergeOpen && !!selectedVehicleInPanel && !!mergeDuplicateVehicleId,
})

  controlsRef.current = {
    openAdd: openAddVehicleModal,
    openEdit: openEditVehicleModal,
    requestDelete: handleDeleteVehicleClick,
    openManageLinks: openManageVehicleLinks,
    openMerge: openVehicleMerge,
  }

  const renderVehicleModeTabs = () => (
    <div className="grid grid-cols-2 gap-2 rounded-xl bg-gray-100 p-1">
      <button
        type="button"
        onClick={() => setVehicleModalMode('new')}
        className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
          vehicleModalMode === 'new' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'
        }`}
      >
        New truck
      </button>
      <button
        type="button"
        onClick={() => setVehicleModalMode('existing')}
        className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
          vehicleModalMode === 'existing' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'
        }`}
      >
        Link / manage truck
      </button>
    </div>
  )

  const renderLinkVehicleForm = () => (
    <form onSubmit={handleVehicleLinkSubmit} className="p-6 space-y-5">
      {renderVehicleModeTabs()}

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Find the existing truck</label>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            value={vehicleLinkSearch}
            onChange={(event) => {
              setVehicleLinkSearch(event.target.value)
              setSelectedLinkVehicle(null)
              setVehicleLinkUnitNumber('')
            }}
            className="w-full rounded-lg border border-gray-300 py-2.5 pl-9 pr-4 focus:border-amber-500 focus:ring-2 focus:ring-amber-500"
            placeholder="Search VIN, unit, plate, make, or model…"
            autoFocus
          />
          {isFetchingVehicleLinkCandidates && (
            <Spinner size="xs" className="absolute right-3 top-1/2 -translate-y-1/2" />
          )}
        </div>
        <p className="mt-1 text-xs text-gray-500">This searches every truck in the shop, not only this customer.</p>
      </div>

      <div className="max-h-56 space-y-2 overflow-y-auto rounded-xl border border-gray-200 bg-gray-50 p-2">
        {selectedLinkVehicle && !availableVehicleLinkCandidates.some((vehicle) => vehicle.id === selectedLinkVehicle.id) && (
          <button
            type="button"
            className="w-full rounded-lg border border-amber-400 bg-amber-50 p-3 text-left"
          >
            <span className="block font-semibold text-gray-900">
              {[
                selectedLinkVehicle.unit_number ? `Unit ${selectedLinkVehicle.unit_number}` : null,
                selectedLinkVehicle.year,
                selectedLinkVehicle.make,
                selectedLinkVehicle.model,
              ].filter(Boolean).join(' · ') || 'Existing truck'}
            </span>
            <span className="mt-1 block text-xs text-gray-600">
              {[selectedLinkVehicle.license_plate ? `Plate ${selectedLinkVehicle.license_plate}` : null, selectedLinkVehicle.vin ? `VIN ${selectedLinkVehicle.vin}` : null].filter(Boolean).join(' · ')}
            </span>
          </button>
        )}
        {availableVehicleLinkCandidates.map((vehicle) => {
          const selected = selectedLinkVehicle?.id === vehicle.id
          return (
            <button
              key={vehicle.id}
              type="button"
              onClick={() => {
                setSelectedLinkVehicle(vehicle)
                setVehicleLinkUnitNumber(vehicle.unit_number || '')
              }}
              className={`w-full rounded-lg border p-3 text-left transition-colors ${
                selected ? 'border-amber-400 bg-amber-50' : 'border-gray-200 bg-white hover:border-amber-300 hover:bg-amber-50/50'
              }`}
            >
              <span className="block font-semibold text-gray-900">
                {[
                  vehicle.unit_number ? `Unit ${vehicle.unit_number}` : null,
                  vehicle.year,
                  vehicle.make,
                  vehicle.model,
                ].filter(Boolean).join(' · ') || 'Truck'}
              </span>
              <span className="mt-1 block text-xs text-gray-600">
                {[vehicle.license_plate ? `Plate ${vehicle.license_plate}` : null, vehicle.vin ? `VIN ${vehicle.vin}` : null].filter(Boolean).join(' · ') || 'No plate or VIN recorded'}
              </span>
            </button>
          )
        })}
        {!isFetchingVehicleLinkCandidates && availableVehicleLinkCandidates.length === 0 && !selectedLinkVehicle && (
          <p className="px-3 py-6 text-center text-sm text-gray-500">
            {vehicleLinkSearch.trim() ? 'No trucks match this search.' : 'Search to select a truck already in the shop.'}
          </p>
        )}
      </div>

      {selectedLinkVehicle && (
        <>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Canonical unit number</label>
            <input
              value={vehicleLinkUnitNumber}
              onChange={(event) => setVehicleLinkUnitNumber(event.target.value)}
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 focus:border-amber-500 focus:ring-2 focus:ring-amber-500"
              placeholder="603"
            />
            <p className="mt-1 text-xs text-gray-500">Enter only the truck’s unit, such as 603. The owner/lessor company prefix is added automatically.</p>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="text-sm font-medium text-gray-700">Current truck roles</label>
              {isFetchingVehicleRelationships && <Spinner size="xs" />}
            </div>
            <p className="mb-2 text-xs text-gray-500">Owner, operating authority, and invoice recipient are independent. Changing one does not rewrite the others or the truck’s service history.</p>
            <div className="space-y-2 rounded-xl border border-gray-200 bg-gray-50 p-2">
              {([
                ['owner', 'Truck owner / lessor', 'Controls the owner/lessor prefix shown with the unit number.'],
                ['operator', 'Operating authority / Fleet Board', 'Controls which authority’s Fleet Board contains this truck.'],
                ['default_payer', 'Default invoice recipient', 'Receives new service invoices and determines internal versus customer pricing.'],
              ] as const).map(([relationshipType, label, help]) => {
                const activeOfType = vehicleRelationships.filter((relationship) => !relationship.effective_to && relationship.relationship_type === relationshipType)
                const relationship = activeOfType.find((item) => item.is_primary) || activeOfType[0]
                const companyName = relationship?.customer_company_name || 'Not assigned'
                return (
                  <div key={relationshipType} className="rounded-lg bg-white px-3 py-2.5 text-sm">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <span className="block text-xs font-medium uppercase tracking-wide text-gray-500">{label}</span>
                        <span className="mt-0.5 block truncate font-semibold text-gray-900">{companyName}</span>
                        <span className="mt-0.5 block text-xs text-gray-500">{help}</span>
                      </div>
                      {relationshipType === 'operator' && relationship && pendingFleetRemovalId !== relationship.id && (
                        <button
                          type="button"
                          onClick={() => setPendingFleetRemovalId(relationship.id)}
                          className="shrink-0 rounded-lg px-2.5 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
                        >
                          Remove from Fleet Board
                        </button>
                      )}
                    </div>
                    {relationshipType === 'operator' && relationship && pendingFleetRemovalId === relationship.id && (
                      <div className="mt-2 rounded-lg border border-red-200 bg-red-50 p-2.5 text-xs text-red-800">
                        <p className="m-0">This only ends the {companyName} authority assignment. The owner, invoice recipient, and service history stay unchanged.</p>
                        <div className="mt-2 flex justify-end gap-2">
                          <button type="button" className="rounded-md px-2.5 py-1.5 font-medium text-gray-700 hover:bg-white" onClick={() => setPendingFleetRemovalId(null)}>Cancel</button>
                          <button
                            type="button"
                            disabled={removeFleetAssignmentMutation.isPending}
                            className="rounded-md bg-red-600 px-2.5 py-1.5 font-medium text-white disabled:opacity-50"
                            onClick={() => removeFleetAssignmentMutation.mutate({ vehicleId: selectedLinkVehicle.id, relationshipId: relationship.id, companyName })}
                          >
                            {removeFleetAssignmentMutation.isPending ? 'Removing…' : 'Confirm removal'}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Roles for {selectedCustomer?.company_name || selectedCustomer?.first_name}</label>
            <div className="space-y-2">
              {([
                ['owner', 'Truck owner / lessor', 'Use this company’s name as the Fleet Board unit prefix. This is the company that owns the truck and may lease it to the operating authority.'],
                ['default_payer', 'Default invoice recipient', 'Invoice this company for new work orders. External customers use customer pricing; the internal house account uses garage-cost rules.'],
              ] as const).map(([relationshipType, label, help]) => {
                const isCurrentlyAssigned = vehicleRelationships.some((relationship) => !relationship.effective_to
                  && relationship.customer_id === selectedCustomer?.id
                  && relationship.relationship_type === relationshipType)
                const roleLocked = isCurrentlyAssigned
                return (
                  <label key={relationshipType} className={`flex items-start gap-3 rounded-lg border p-3 text-sm ${vehicleRelationshipTypes.includes(relationshipType) ? 'border-amber-300 bg-amber-50/60 text-amber-950' : 'border-gray-200 bg-white text-blueNoir-800'}`}>
                    <input
                      type="checkbox"
                      checked={vehicleRelationshipTypes.includes(relationshipType)}
                      disabled={roleLocked}
                      onChange={(event) => setVehicleRelationshipTypes((current) => event.target.checked
                        ? [...new Set([...current, relationshipType])]
                        : current.filter((item) => item !== relationshipType))}
                      className="mt-0.5"
                    />
                    <span>
                      <strong className="block text-gray-900">{label}</strong>
                      <span className="text-xs text-gray-500">{help}</span>
                      {roleLocked && <span className="mt-1 block text-xs font-medium text-amber-700">To change this role, assign it from the replacement company.</span>}
                    </span>
                  </label>
                )
              })}
            </div>
            <div className="mt-3 rounded-lg border border-gray-200 bg-white p-3">
              <label className="block text-sm font-semibold text-gray-900" htmlFor="operating-authority">Operating authority / Fleet Board</label>
              <select
                id="operating-authority"
                value={operatingAuthorityCustomerId}
                onChange={(event) => setOperatingAuthorityCustomerId(event.target.value)}
                className="mt-2 w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-amber-500 focus:ring-2 focus:ring-amber-500"
              >
                <option value="">Select operating authority…</option>
                {fleetCompanies.map((company) => (
                  <option key={company.id} value={company.id}>
                    {company.company_name}{company.fleet_enabled ? ' · Fleet Board' : ''}{company.is_internal_fleet ? ' (internal)' : ''}
                  </option>
                ))}
              </select>
              <p className="mt-2 text-xs text-gray-500">Choose the authority this truck runs under. This records only the truck’s authority; the customer’s “Add this customer to Fleet Board” checkbox is the only control that places trucks on Fleet Board. Owner/lessor and invoice recipient stay independent.</p>
            </div>
            <p className="mt-2 text-xs text-gray-500">Assigning a replacement owner, authority, or payer safely closes the previous period. Completed work orders and the truck’s full service history remain unchanged.</p>
          </div>
        </>
      )}

      <div className="flex items-center justify-end gap-3 border-t border-gray-200 pt-4">
        <button
          type="button"
          onClick={closeVehicleModal}
          className="rounded-lg px-5 py-2.5 font-medium text-gray-700 hover:bg-gray-100"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={!selectedLinkVehicle || linkVehicleMutation.isPending}
          className="flex items-center gap-2 rounded-lg px-5 py-2.5 font-medium text-white disabled:opacity-50"
          style={{ backgroundColor: accentColors[500] }}
        >
          {linkVehicleMutation.isPending && <Spinner size="xs" className="border-white/40 border-t-white" />}
          Save truck roles
        </button>
      </div>
    </form>
  )

  const renderVehicleForm = () => (
    <form onSubmit={handleVehicleSubmit} className="p-6 space-y-4">
      {!editingVehicle && renderVehicleModeTabs()}
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
            <span className="min-w-0 flex-1">
              <span className="block font-medium">{vehicleVinError.message}</span>
              {vehicleVinError.vehicle && (
                <span className="mt-2 block rounded-lg border border-red-200 bg-white px-3 py-2 text-gray-700">
                  <span className="flex items-start gap-2">
                    <Truck className="mt-0.5 h-4 w-4 flex-none text-red-500" />
                    <span className="min-w-0">
                      <span className="block font-semibold text-gray-900">
                        {[
                          vehicleVinError.vehicle.unit_number ? `Unit ${vehicleVinError.vehicle.unit_number}` : null,
                          vehicleVinError.vehicle.year,
                          vehicleVinError.vehicle.make,
                          vehicleVinError.vehicle.model,
                        ].filter(Boolean).join(' · ') || 'Existing truck'}
                      </span>
                      {(vehicleVinError.vehicle.owner_lessor_name || vehicleVinError.vehicle.customer_name) && (
                        <span className="block text-xs text-gray-600">Truck owner / lessor: {vehicleVinError.vehicle.owner_lessor_name || vehicleVinError.vehicle.customer_name}</span>
                      )}
                      {vehicleVinError.vehicle.operating_authority_name && (
                        <span className="block text-xs text-gray-600">Operating authority: {vehicleVinError.vehicle.operating_authority_name}</span>
                      )}
                      {vehicleVinError.vehicle.default_invoice_recipient_name && (
                        <span className="block text-xs text-gray-600">Default invoice recipient: {vehicleVinError.vehicle.default_invoice_recipient_name}</span>
                      )}
                      {vehicleVinError.vehicle.license_plate && (
                        <span className="block text-xs text-gray-600">Plate: {vehicleVinError.vehicle.license_plate}</span>
                      )}
                      {vehicleVinError.vehicle.vin && (
                        <span className="block break-all font-mono text-xs text-gray-600">VIN: {vehicleVinError.vehicle.vin}</span>
                      )}
                    </span>
                  </span>
                </span>
              )}
              {vehicleVinError.vehicle && editingVehicle ? (
                <button
                  type="button"
                  onClick={() => reviewDuplicateTruckConflict(vehicleVinError.vehicle!)}
                  className="mt-2 inline-flex rounded-lg bg-red-600 px-3 py-2 text-xs font-semibold text-white hover:bg-red-700"
                >
                  Review and merge duplicate trucks
                </button>
              ) : vehicleVinError.vehicle ? (
                <button
                  type="button"
                  onClick={() => selectExistingTruckFromConflict(vehicleVinError.vehicle!)}
                  className="mt-2 inline-flex rounded-lg bg-red-600 px-3 py-2 text-xs font-semibold text-white hover:bg-red-700"
                >
                  Use this existing truck and manage its roles
                </button>
              ) : (
                <span className="mt-2 block text-xs">Switch to “Link existing truck” and search this VIN.</span>
              )}
            </span>
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

  return (
    <>
      {isVehicleModalOpen && selectedCustomer && (
        <div className="fixed inset-0 z-[80] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {/* Backdrop */}
            <div 
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={closeVehicleModal}
            />
      
            {/* Modal */}
            <div className="db-customer-modal relative bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
              {/* Header */}
              <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 rounded-t-2xl">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-gray-900">
                      {editingVehicle ? 'Edit Vehicle' : vehicleModalMode === 'existing' ? 'Truck Roles & Fleet Assignment' : 'Add Vehicle'}
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
              {!editingVehicle && vehicleModalMode === 'existing' ? renderLinkVehicleForm() : renderVehicleForm()}
            </div>
          </div>
        </div>
      )}
      {isVehicleMergeOpen && selectedVehicleInPanel && (
        <div className="fixed inset-0 z-[80] overflow-y-auto" role="dialog" aria-modal="true" aria-labelledby="vehicle-merge-title">
          <div className="flex min-h-full items-center justify-center p-4 sm:p-6">
            <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={closeVehicleMerge} />
            <div className="relative w-full max-w-3xl overflow-hidden rounded-2xl bg-white shadow-2xl">
              <div className="flex items-start justify-between gap-4 border-b border-gray-200 px-5 py-4 sm:px-6">
                <div className="min-w-0">
                  <h3 id="vehicle-merge-title" className="text-xl font-bold text-gray-900">Merge duplicate truck records</h3>
                  <p className="mt-1 text-sm text-gray-600">
                    Compare both records and keep the one with the strongest identity and service history.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={closeVehicleMerge}
                  disabled={mergeVehicleMutation.isPending}
                  className="flex h-11 w-11 flex-none items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-100 disabled:opacity-50"
                  aria-label="Close merge dialog"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="max-h-[70vh] overflow-y-auto px-5 py-5 sm:px-6">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-gray-200 pb-5">
                  <span className="font-semibold text-gray-900">Opened for cleanup:</span>
                  <span className="text-gray-800">{vehicleDisplayLabel(selectedVehicleInPanel)}</span>
                  <span className="font-mono text-sm text-gray-500">VIN {selectedVehicleInPanel.vin}</span>
                </div>

                <div className="py-5">
                  <h4 className="font-semibold text-gray-900">Choose the duplicate to archive</h4>
                  <p className="mt-1 text-sm text-gray-600">Only active records with this exact 17-character VIN are eligible.</p>

                  {isLoadingVehicleMergeCandidates ? (
                    <LoadingLine className="mt-4 text-gray-500">Checking for exact VIN matches…</LoadingLine>
                  ) : isVehicleMergeCandidatesError ? (
                    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-red-50 p-4 text-sm text-red-800">
                      <span>Duplicate records could not be loaded.</span>
                      <button type="button" onClick={() => refetchVehicleMergeCandidates()} className="font-semibold underline underline-offset-2">Try again</button>
                    </div>
                  ) : vehicleMergeCandidates.length === 0 ? (
                    <div className="mt-4 rounded-xl bg-gray-50 p-4 text-sm text-gray-700">
                      No other active truck uses VIN <span className="font-mono font-semibold">{selectedVehicleInPanel.vin}</span>. Nothing can be safely merged from this record.
                    </div>
                  ) : (
                    <div className="mt-4 space-y-2">
                      {vehicleMergeCandidates.map((candidate) => (
                        <label
                          key={candidate.id}
                          className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition-colors ${
                            mergeDuplicateVehicleId === candidate.id
                              ? 'border-amber-500 bg-amber-50'
                              : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                          }`}
                        >
                          <input
                            type="radio"
                            name="duplicate-vehicle"
                            value={candidate.id}
                            checked={mergeDuplicateVehicleId === candidate.id}
                            onChange={() => {
                              setMergeDuplicateVehicleId(candidate.id)
                              setMergeVinConfirmed(false)
                            }}
                            className="mt-1 h-5 w-5 accent-amber-500"
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block font-semibold text-gray-900">{candidate.customer_name} · Unit {candidate.unit_number || 'not set'}</span>
                            <span className="mt-1 block text-sm text-gray-600">
                              {[candidate.year, candidate.make, candidate.model].filter(Boolean).join(' ')} · {candidate.mileage?.toLocaleString() || '—'} mi
                            </span>
                            <span className="mt-1 block text-sm text-gray-500">
                              {candidate.repair_order_count} repair order{candidate.repair_order_count === 1 ? '' : 's'} · Source {candidate.source === 'easy_truck_shop_import' ? 'Easy Truck Shop' : 'DieselBridge'}
                            </span>
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>

                {mergeDuplicateVehicleId && (
                  <div className="border-t border-gray-200 pt-5">
                    {isLoadingVehicleMergePreview ? (
                      <LoadingLine className="text-gray-500">Building a safe merge preview…</LoadingLine>
                    ) : isVehicleMergePreviewError || !vehicleMergePreview ? (
                      <div className="rounded-xl bg-red-50 p-4 text-sm text-red-800">
                        This pair cannot be safely merged. Refresh the duplicate list and try again.
                      </div>
                    ) : (
                      <div className="space-y-5">
                        {(() => {
                          const recommended = vehicleMergePreview.recommended_canonical_id === vehicleMergePreview.canonical.id
                            ? vehicleMergePreview.canonical
                            : vehicleMergePreview.duplicate
                          return (
                            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-950">
                              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Recommended permanent truck</p>
                              <p className="mt-1 font-semibold">{recommended.customer_name} · Unit {recommended.unit_number || 'not set'}</p>
                              <p className="mt-1 text-sm text-emerald-800">
                                VIN {recommended.vin || 'not recorded'} · {recommended.mileage?.toLocaleString() || '—'} mi · {recommended.repair_order_count} repair order{recommended.repair_order_count === 1 ? '' : 's'}
                              </p>
                            </div>
                          )
                        })()}
                        <div>
                          <h4 className="font-semibold text-gray-900">What will move</h4>
                          <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
                            {[
                              ['Repair orders', vehicleMergePreview.duplicate.repair_order_count],
                              ['Appointments', vehicleMergePreview.duplicate.appointment_count],
                              ['Inspections', vehicleMergePreview.duplicate.inspection_count],
                              ['Incidents', vehicleMergePreview.duplicate.incident_count],
                            ].map(([label, count]) => (
                              <div key={String(label)}>
                                <p className="text-2xl font-bold text-gray-900">{count}</p>
                                <p className="text-sm text-gray-600">{label}</p>
                              </div>
                            ))}
                          </div>
                        </div>

                        <div className="rounded-xl bg-blue-50 p-4 text-sm text-blue-950">
                          <p className="font-semibold">History moves; billing history does not change.</p>
                          <p className="mt-1 leading-6">
                            Past repair orders keep the customer and invoice recipient originally recorded on that visit. Current owner, authority, payer, and Fleet Board settings stay with the truck you keep; non-conflicting history from the duplicate is retained.
                          </p>
                        </div>

                        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-gray-200 p-4">
                          <input
                            type="checkbox"
                            checked={mergeVinConfirmed}
                            onChange={(event) => setMergeVinConfirmed(event.target.checked)}
                            className="mt-0.5 h-5 w-5 flex-none accent-amber-500"
                          />
                          <span className="text-sm leading-6 text-gray-800">
                            I verified both records are the same physical truck with VIN <span className="font-mono font-semibold">{vehicleMergePreview.match_value}</span>. Keep the recommended record and archive the weaker duplicate after moving its history.
                          </span>
                        </label>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="flex flex-col-reverse gap-3 border-t border-gray-200 bg-gray-50 px-5 py-4 sm:flex-row sm:justify-end sm:px-6">
                <button type="button" onClick={closeVehicleMerge} disabled={mergeVehicleMutation.isPending} className="min-h-11 px-4 py-2 text-gray-700 font-medium hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50">
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => mergeVehicleMutation.mutate()}
                  disabled={!vehicleMergePreview || !mergeVinConfirmed || mergeVehicleMutation.isPending}
                  className="min-h-11 px-5 py-2.5 bg-red-600 hover:bg-red-700 disabled:bg-red-300 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  {mergeVehicleMutation.isPending ? <Spinner size="xs" className="border-white/40 border-t-white" /> : <Combine className="h-4 w-4" />}
                  Merge and archive duplicate
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {deleteConfirmVehicle && selectedCustomer && (
        <div className="fixed inset-0 z-[80] overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            {/* Backdrop */}
            <div 
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setDeleteConfirmVehicle(null)}
            />
      
            {/* Modal */}
            <div className="db-customer-modal relative bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
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
                ? Use <span className="font-semibold">Merge duplicate</span> instead when another record contains history for the same physical truck.
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
    </>
  )
}
