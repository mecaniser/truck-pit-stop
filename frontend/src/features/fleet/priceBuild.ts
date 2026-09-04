/**
 * FleetBoard's client for the price-build API.
 *
 * The fleet price builder is a second *client* of the endpoints the shop's price
 * builder already uses — not a second implementation. All pricing lives in
 * PriceBuildService on the server, which prices an internal fleet order's parts
 * at cost and its labor at the internal rate (or the customer rate when the
 * truck is set to bill labor that way). Fleet managers are already authorized
 * for these routes; _check_ro_access scopes them to fleet and internal work.
 *
 * The one fleet-specific rule lives in the UI, not here: a fleet manager scopes
 * work and sees a single cost total, never per-line money.
 */
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'

import api from '@/lib/api'
import type {
  PartsUsage,
  PriceBuildSummary,
  RepairOperationCandidate,
} from '@/types'
import { invalidateFleetAndCockpit } from './FleetModals'
import type { PMServiceEntry } from './types'

export type FleetRepairOrderDetail = {
  id: string
  order_number: string
  status: string
  description: string | null
  is_internal: boolean
  is_fleet_work: boolean
  is_pm: boolean
  bill_labor_at_customer_rate: boolean
  vehicle_id: string
  assigned_mechanic_id: string | null
  mileage_in: number | null
  mileage_out: number | null
  customer_company_name: string | null
  customer_first_name: string | null
  customer_last_name: string | null
  vehicle_unit_number: string | null
  vehicle_year: number | null
  vehicle_make: string | null
  vehicle_model: string | null
  vehicle_vin: string | null
  history_events?: FleetHistoryEvent[]
  labor_items: unknown[]
  parts_usage: unknown[]
}

export type FleetHistoryEvent = {
  id: string
  event_type: string
  label: string
  detail: string | null
  actor_name: string | null
  created_at: string
}

/** What the part picker needs: identity and availability, never cost. */
export type FleetPartOption = {
  id: string
  sku: string
  name: string
  stock_quantity: number
  on_order_quantity: number
  unit_type: string
}

export type FleetMechanicOption = { id: string; name: string }

export type FleetSettings = { internal_labor_rate: number; labor_rate: number }

export const fleetPriceBuildKeys = {
  summary: (orderId: string) => ['fleet-price-build', orderId] as const,
  detail: (orderId: string) => ['fleet-ro-detail', orderId] as const,
  pmServices: (orderId: string) => ['fleet-wo-pm-services', orderId] as const,
  pmCatalog: ['fleet-pm-catalog'] as const,
  truckPmDefault: (vehicleId: string) => ['fleet-truck-pm-default', vehicleId] as const,
  partSearch: (term: string) => ['fleet-part-search', term] as const,
  mechanics: ['fleet-mechanics'] as const,
  settings: ['fleet-settings'] as const,
}

/**
 * A fleet edit changes a record the owner's cockpit also shows, so refresh both
 * shells plus this order's own views. PRODUCT.md: one repair_orders table.
 */
export function invalidateOrder(qc: QueryClient, orderId: string) {
  qc.invalidateQueries({ queryKey: fleetPriceBuildKeys.summary(orderId) })
  qc.invalidateQueries({ queryKey: fleetPriceBuildKeys.detail(orderId) })
  qc.invalidateQueries({ queryKey: fleetPriceBuildKeys.pmServices(orderId) })
  invalidateFleetAndCockpit(qc)
}

type ApiErrorDetail = string | { msg?: string }[] | undefined

/**
 * FastAPI reports a plain refusal as a string `detail`, but a validation
 * failure as an array of field errors. Reading only the string meant a 422
 * surfaced as nothing at all — the request failed and the panel said so
 * nowhere, which is how "add a custom operation" looked like a dead button.
 */
function errorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: ApiErrorDetail } } })
    ?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => item?.msg).filter(Boolean)
    if (messages.length) return messages.join('. ')
  }
  return fallback
}

/* ---------- reads ---------- */

export function usePriceBuildSummary(orderId: string) {
  return useQuery<PriceBuildSummary>({
    queryKey: fleetPriceBuildKeys.summary(orderId),
    queryFn: async () => (await api.get(`/repair-orders/${orderId}/price-build`)).data,
  })
}

export function useRepairOrderDetail(orderId: string) {
  return useQuery<FleetRepairOrderDetail>({
    queryKey: fleetPriceBuildKeys.detail(orderId),
    queryFn: async () => (await api.get(`/repair-orders/${orderId}/detail`)).data,
  })
}

export function usePmServices(orderId: string, enabled: boolean) {
  return useQuery<PMServiceEntry[]>({
    queryKey: fleetPriceBuildKeys.pmServices(orderId),
    queryFn: async () => (await api.get(`/fleet/work-orders/${orderId}/pm-services`)).data,
    enabled,
  })
}

/** Only PM-category services can scope a PM. */
export function usePmServiceCatalog(enabled: boolean) {
  return useQuery<PMServiceEntry[]>({
    queryKey: fleetPriceBuildKeys.pmCatalog,
    queryFn: async () => (await api.get('/fleet/pm-service-catalog')).data,
    enabled,
  })
}

/** The truck's standing PM package: what a PM defaults to when none is picked. */
export function useTruckPmDefault(vehicleId: string | null, enabled: boolean) {
  return useQuery<PMServiceEntry[]>({
    queryKey: fleetPriceBuildKeys.truckPmDefault(vehicleId ?? 'none'),
    queryFn: async () => (await api.get(`/fleet/trucks/${vehicleId}/pm-services`)).data,
    enabled: enabled && !!vehicleId,
  })
}

/**
 * Save this selection as the truck's standing PM package, so the next PM needs
 * no picking. Copies onto each PM as RepairOrderPMService, which stays
 * adjustable per visit without touching this default.
 */
export function useSaveTruckPmDefault(vehicleId: string | null) {
  const qc = useQueryClient()
  return useMutation<PMServiceEntry[], unknown, string[]>({
    mutationFn: async (serviceIds) =>
      (await api.put(`/fleet/trucks/${vehicleId}/pm-services`, { service_ids: serviceIds })).data,
    onSuccess: () => {
      toast.success("Saved as this truck's default PM")
      qc.invalidateQueries({ queryKey: fleetPriceBuildKeys.truckPmDefault(vehicleId ?? 'none') })
      invalidateFleetAndCockpit(qc)
    },
    onError: (error) => toast.error(errorMessage(error, 'Unable to save the default')),
  })
}

/**
 * Part search. `in_stock: false` keeps zero-stock parts in the results so the
 * manager can still add a part that has to be ordered — the count tells them
 * which it is.
 */
export function usePartSearch(term: string) {
  return useQuery<FleetPartOption[]>({
    queryKey: fleetPriceBuildKeys.partSearch(term),
    queryFn: async ({ signal }) => (await api.get('/inventory/typeahead', {
      signal,
      params: { q: term, limit: 20, in_stock: false },
    })).data,
    enabled: term.trim().length >= 2,
  })
}

export function useFleetMechanics() {
  return useQuery<FleetMechanicOption[]>({
    queryKey: fleetPriceBuildKeys.mechanics,
    queryFn: async () => (await api.get('/fleet/mechanics')).data,
  })
}

export function useFleetSettings() {
  return useQuery<FleetSettings>({
    queryKey: fleetPriceBuildKeys.settings,
    queryFn: async () => (await api.get('/fleet/settings')).data,
  })
}

/* ---------- work lines ---------- */

export function useOperationSearch(orderId: string) {
  return useMutation<{ candidates: RepairOperationCandidate[] }, unknown, string>({
    mutationFn: async (query) =>
      (await api.post(`/repair-orders/${orderId}/price-build/repair-ops/search`, { query })).data,
    onError: (error) => toast.error(errorMessage(error, 'Unable to search operations')),
  })
}

/**
 * Add an operation to the order.
 *
 * `hours` is passed explicitly rather than taken from the candidate: a custom
 * operation the shop has not done before comes back with estimated_hours 0.00,
 * and the server requires at least 0.01 — so the caller supplies what the
 * operator entered. Applying it also teaches the labor memory, which is why
 * the next matching job arrives with book time already filled in.
 */
export function useApplyOperation(orderId: string, onDone?: () => void) {
  const qc = useQueryClient()
  return useMutation<unknown, unknown, { candidate: RepairOperationCandidate; hours: number }>({
    mutationFn: async ({ candidate, hours }) =>
      (await api.post(`/repair-orders/${orderId}/price-build/repair-ops/apply`, {
        operation_id: candidate.operation_id,
        name: candidate.name,
        description: candidate.description,
        estimated_hours: hours,
        provider: candidate.provider,
        auto_recalc_enabled: true,
      })).data,
    onSuccess: () => { invalidateOrder(qc, orderId); onDone?.() },
    onError: (error) => toast.error(errorMessage(error, 'Unable to add this operation')),
  })
}

export function useAddFlatService(orderId: string, onDone?: () => void) {
  const qc = useQueryClient()
  return useMutation<unknown, unknown, { serviceId: string; quantity?: number }>({
    mutationFn: async ({ serviceId, quantity }) =>
      (await api.post(`/repair-orders/${orderId}/price-build/flat-service`, {
        service_id: serviceId,
        ...(quantity == null ? {} : { quantity }),
      })).data,
    onSuccess: () => { invalidateOrder(qc, orderId); onDone?.() },
    onError: (error) => toast.error(errorMessage(error, 'Unable to add this service')),
  })
}

export function useUpdateLine(orderId: string) {
  const qc = useQueryClient()
  return useMutation<unknown, unknown, {
    lineId: string
    description?: string
    hours?: number
    auto_recalc_enabled?: boolean
  }>({
    mutationFn: async ({ lineId, ...body }) =>
      (await api.patch(`/repair-orders/${orderId}/price-build/lines/${lineId}`, body)).data,
    onSuccess: () => invalidateOrder(qc, orderId),
    onError: (error) => toast.error(errorMessage(error, 'Unable to update this line')),
  })
}

export function useRemoveLine(orderId: string) {
  const qc = useQueryClient()
  return useMutation<unknown, unknown, string>({
    mutationFn: async (lineId) =>
      (await api.delete(`/repair-orders/${orderId}/price-build/lines/${lineId}`)).data,
    onSuccess: () => invalidateOrder(qc, orderId),
    onError: (error) => toast.error(errorMessage(error, 'Unable to remove this line')),
  })
}

/* ---------- parts ---------- */

export function useAddPart(orderId: string, onDone?: () => void) {
  const qc = useQueryClient()
  return useMutation<PartsUsage, unknown, {
    inventoryId: string
    quantity: number
    sourceLineId?: string | null
    allowStockShortage?: boolean
  }>({
    mutationFn: async ({ inventoryId, quantity, sourceLineId, allowStockShortage }) =>
      (await api.post(`/repair-orders/${orderId}/parts`, {
        inventory_id: inventoryId,
        quantity,
        source_line_id: sourceLineId ?? null,
        ...(allowStockShortage ? { allow_stock_shortage: true } : {}),
      })).data,
    onSuccess: () => { invalidateOrder(qc, orderId); onDone?.() },
    onError: (error) => toast.error(errorMessage(error, 'Unable to add this part')),
  })
}

/**
 * A part that was never in the catalogue — a hose from the parts store, or
 * something a tech carried in.
 *
 * `cost` is what the shop paid, and it is required rather than defaulted to
 * zero: this call creates a real placeholder catalogue row whose cost and
 * selling price come from what is sent here, so a zero would both understate
 * the truck's cost total and leave a zero-priced part in the catalogue for
 * whoever uses it next. Asking for the cost of a part is not asking a fleet
 * manager to set a price.
 */
export function useAddAdHocPart(orderId: string, onDone?: () => void) {
  const qc = useQueryClient()
  return useMutation<unknown, unknown, {
    name: string
    sku?: string | null
    quantity: number
    cost: number
    sourceLineId?: string | null
  }>({
    mutationFn: async ({ name, sku, quantity, cost, sourceLineId }) =>
      (await api.post(`/repair-orders/${orderId}/parts/ad-hoc`, {
        name: name.trim(),
        sku: sku?.trim() || null,
        quantity,
        // An internal order bills parts at cost, so both sides of the
        // placeholder start from the one number the manager actually knows.
        unit_price: cost,
        unit_cost: cost,
        source_line_id: sourceLineId ?? null,
      })).data,
    onSuccess: () => { invalidateOrder(qc, orderId); onDone?.() },
    onError: (error) => toast.error(errorMessage(error, 'Unable to add this part')),
  })
}

export function useUpdatePartQuantity(orderId: string) {
  const qc = useQueryClient()
  return useMutation<unknown, unknown, { partUsageId: string; quantity: number }>({
    mutationFn: async ({ partUsageId, quantity }) =>
      (await api.patch(`/repair-orders/${orderId}/parts/${partUsageId}`, { quantity })).data,
    onSuccess: () => invalidateOrder(qc, orderId),
    onError: (error) => toast.error(errorMessage(error, 'Unable to update this part')),
  })
}

export function useRemovePart(orderId: string) {
  const qc = useQueryClient()
  return useMutation<unknown, unknown, string>({
    mutationFn: async (partUsageId) =>
      (await api.delete(`/repair-orders/${orderId}/parts/${partUsageId}`)).data,
    onSuccess: () => invalidateOrder(qc, orderId),
    onError: (error) => toast.error(errorMessage(error, 'Unable to remove this part')),
  })
}

/* ---------- order-level actions ---------- */

export function useSaveDescription(orderId: string) {
  const qc = useQueryClient()
  return useMutation<unknown, unknown, string>({
    mutationFn: async (description) =>
      (await api.put(`/repair-orders/${orderId}`, { description: description.trim() })).data,
    onSuccess: () => invalidateOrder(qc, orderId),
    onError: (error) => toast.error(errorMessage(error, 'Unable to save')),
  })
}

export function useAssignMechanic(orderId: string) {
  const qc = useQueryClient()
  return useMutation<unknown, unknown, string>({
    mutationFn: async (mechanicId) => mechanicId
      ? (await api.post(`/repair-orders/${orderId}/assign-mechanic`, { mechanic_id: mechanicId })).data
      : (await api.put(`/repair-orders/${orderId}`, { assigned_mechanic_id: null })).data,
    onSuccess: (_data, mechanicId) => {
      toast.success(mechanicId ? 'Mechanic assigned' : 'Mechanic unassigned')
      invalidateOrder(qc, orderId)
    },
    onError: (error) => toast.error(errorMessage(error, 'Unable to assign')),
  })
}

/**
 * Start/complete stay on the fleet routes: they carry the PM odometer roll-
 * forward (advance_vehicle_pm) and mileage-out capture that the generic
 * repair-order transitions do not.
 */
export function useStartWork(orderId: string, onDone?: () => void) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => (await api.post(`/fleet/work-orders/${orderId}/start`)).data,
    onSuccess: () => {
      toast.success('Work started — the truck is in the bay')
      invalidateOrder(qc, orderId)
      onDone?.()
    },
    onError: (error) => toast.error(errorMessage(error, 'Unable to start work')),
  })
}

export function useCompleteWork(orderId: string, onDone?: () => void) {
  const qc = useQueryClient()
  return useMutation<unknown, unknown, number | null>({
    mutationFn: async (mileageOut) =>
      (await api.post(`/fleet/work-orders/${orderId}/complete`, {
        mileage_out: mileageOut ?? null,
      })).data,
    onSuccess: () => { toast.success('Repair order completed'); invalidateOrder(qc, orderId); onDone?.() },
    onError: (error) => toast.error(errorMessage(error, 'Unable to complete')),
  })
}

export function useSetPmServices(orderId: string) {
  const qc = useQueryClient()
  return useMutation<PMServiceEntry[], unknown, string[]>({
    mutationFn: async (serviceIds) =>
      (await api.put(`/fleet/work-orders/${orderId}/pm-services`, { service_ids: serviceIds })).data,
    onSuccess: () => invalidateOrder(qc, orderId),
    onError: (error) => toast.error(errorMessage(error, 'Unable to update PM services')),
  })
}
