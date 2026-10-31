import PlatformSelect from '@/components/PlatformSelect'
import { useEffect, useRef, useState, type Ref } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Plus, Search } from 'lucide-react'
import api from '@/lib/api'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { customerDisplayName } from '@/lib/customerName'
import type { Customer, RepairOrder, Vehicle } from '@/types'
import { ExternalServiceHistory } from '@/features/external-services/ExternalServiceHistory'
import VehicleHistoryExport from './VehicleHistoryExport'
import './customer-workspace.css'
import MaintenanceSection from '@/features/maintenance/MaintenanceSection'
import VehicleIssuesPanel from '@/features/vehicle-issues/VehicleIssuesPanel'
import RecommendedWorkPanel from '@/features/repair-orders/RecommendedWorkPanel'
import { isPricingScopeCurrent, usePricingScope } from '@/features/parts-pricing/usePricingScope'

type Props = { customer: Customer; vehicle: Vehicle; onOpenOrder: (order: RepairOrder) => void; onCreateOrder?: () => void; createOrderButtonRef?: Ref<HTMLButtonElement> }
const historyStatuses = ['draft', 'quoted', 'approved', 'declined', 'assigned', 'acknowledged', 'in_progress', 'pending_review', 'completed', 'invoiced', 'paid', 'cancelled'] as const
const statusLabel = (value: string) => value.replace(/_/g, ' ').replace(/^./, character => character.toUpperCase())
type HistoryPage = { items: RepairOrder[]; total: number; has_more: boolean }
function VehicleRecord({ customer, vehicle, onOpenOrder, onCreateOrder, createOrderButtonRef }: Props) {
  const authScope = usePricingScope()
  const maintenanceNavigation = useRef(new AbortController()); const [maintenanceOpenError, setMaintenanceOpenError] = useState(false)
  useEffect(() => { const controller = new AbortController(); maintenanceNavigation.current = controller; setMaintenanceOpenError(false); return () => controller.abort() }, [authScope, vehicle.id])
  const openMaintenanceOrder = async (id: string) => { const signal = maintenanceNavigation.current.signal; setMaintenanceOpenError(false); try { const result = await api.get<RepairOrder>(`/repair-orders/${id}/workspace`, { signal }); if (signal.aborted || !isPricingScopeCurrent(authScope)) return; if (result.data.vehicle_id !== vehicle.id) throw new Error('Invalid maintenance order'); onOpenOrder(result.data) } catch { if (!signal.aborted && isPricingScopeCurrent(authScope)) setMaintenanceOpenError(true) } }
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  // Keep URL state exact to this customer/truck, separate from directory/queue filters.
  const scope = `${customer.id}:${vehicle.id}`
  const ownFilters = params.get('historyFor') === scope
  const search = ownFilters ? (params.get('historySearch') ?? '').slice(0, 200) : ''
  const rawStatus = ownFilters ? params.get('historyStatus') ?? '' : ''
  const status = historyStatuses.some(value => value === rawStatus) ? rawStatus : ''
  const rawPage = ownFilters ? Number(params.get('historyPage') ?? 0) : 0
  const page = Number.isSafeInteger(rawPage) && rawPage >= 0 && rawPage <= 1_000_000 ? rawPage : 0
  const debouncedSearch = useDebouncedValue(search.trim())
  const searchPending = search.trim() !== debouncedSearch
  const filtered = Boolean(search.trim() || status)
  const updateFilters = (next: { search?: string; status?: string; page?: number }) => {
    const values = { historySearch: next.search ?? search, historyStatus: next.status ?? status, historyPage: String(next.page ?? 0) }
    setParams(current => {
      const updated = new URLSearchParams(current)
      updated.set('historyFor', scope)
      for (const [key, value] of Object.entries(values)) {
        if (value && !(key === 'historyPage' && value === '0')) updated.set(key, value)
        else updated.delete(key)
      }
      return updated
    }, { replace: true, state: location.state?.restoreOrderOrigin
      ? { ...location.state, restoreOrderFocus: false }
      : location.state })
  }
  const history = useQuery({
    queryKey: ['customerVehicleRepairOrders', customer.id, vehicle.id, debouncedSearch, status, page],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<HistoryPage>('/repair-orders', { params: { vehicle_id: vehicle.id, paginated: true, skip: page * 25, limit: 25, ...(debouncedSearch ? { search: debouncedSearch } : {}), ...(status ? { status } : {}) }, signal })
      if (!Array.isArray(data.items) || typeof data.total !== 'number' || typeof data.has_more !== 'boolean' || data.items.some(order => order.vehicle_id !== vehicle.id)) throw new Error('Invalid vehicle history')
      return data
    },
    enabled: !searchPending,
    retry: false,
    staleTime: 30_000,
  })
  const mechanics = useQuery({
    queryKey: ['mechanics'],
    queryFn: async ({ signal }) => (await api.get<{ id: string; first_name: string; last_name: string }[]>('/mechanics', { signal })).data,
    enabled: Boolean(history.data?.items.some(order => order.assigned_mechanic_id)),
  })
  const mechanicName = (id: string | null) => {
    const mechanic = mechanics.data?.find(item => item.id === id)
    return mechanic ? `${mechanic.first_name} ${mechanic.last_name}` : null
  }
  return <div className="db-customer-record db-customer-vehicle-record">
    <VehicleHistoryExport vehicle={vehicle}>{onCreateOrder && <button ref={createOrderButtonRef} type="button" onClick={onCreateOrder}><Plus aria-hidden="true" />New repair order</button>}</VehicleHistoryExport>
    <dl className="db-customer-record__facts">
      <div><dt>Customer</dt><dd>{customerDisplayName(customer)}</dd></div>
      <div><dt>Unit</dt><dd>{vehicle.unit_number || '—'}</dd></div>
      <div><dt>Mileage</dt><dd>{typeof vehicle.mileage === 'number' ? `${vehicle.mileage.toLocaleString()} mi` : '—'}</dd></div>
      <div><dt>VIN</dt><dd>{vehicle.vin || '—'}</dd></div>
      <div><dt>Plate</dt><dd>{vehicle.license_plate || '—'}</dd></div>
      <div><dt>Color</dt><dd>{vehicle.color || '—'}</dd></div>
      {vehicle.owner_company_name && <div><dt>Owner</dt><dd>{vehicle.owner_company_name}</dd></div>}
      {vehicle.operating_authority_company_name && <div><dt>Operating authority</dt><dd>{vehicle.operating_authority_company_name}</dd></div>}
    </dl>
    {vehicle.notes && <div className="db-customer-record__notes"><h3>Notes</h3><p className="whitespace-pre-wrap">{vehicle.notes}</p></div>}
    <MaintenanceSection vehicleId={vehicle.id} customerId={customer.id} channel="shop" onOpenOrder={id => void openMaintenanceOrder(id)} />
    {maintenanceOpenError && <p role="alert">Could not open this visit. Try again.</p>}
    <VehicleIssuesPanel vehicleId={vehicle.id} customerId={customer.id} />
    <RecommendedWorkPanel vehicleId={vehicle.id} customerId={customer.id} canConvert={false} noCurrentOrder />
    <section aria-label="Vehicle repair history">
      <h3>Repair history{history.data && !history.isError && !searchPending ? ` (${history.data.total})` : ''}</h3>
      <div className="db-vehicle-history-filters">
        <label className="db-vehicle-history-filters__search">
          <Search aria-hidden="true" />
          <span className="sr-only">Search this truck’s repair history</span>
          <input type="search" value={search} maxLength={200} placeholder="Order number or work requested" onChange={event => updateFilters({ search: event.target.value })} />
        </label>
        <label>
          <span className="sr-only">Repair history status</span>
          <PlatformSelect value={status} onChange={event => updateFilters({ status: event.target.value })}>
            <option value="">All statuses</option>
            {historyStatuses.map(value => <option key={value} value={value}>{statusLabel(value)}</option>)}
          </PlatformSelect>
        </label>
        {filtered && <button type="button" onClick={() => updateFilters({ search: '', status: '' })}>Clear filters</button>}
      </div>
      {searchPending || history.isLoading ? <p role="status">Loading repair history…</p> : history.isError || !history.data ? <div role="alert">Could not load repair history. <button type="button" onClick={() => void history.refetch()}>Retry repair history</button></div> : <>
        {history.data.items.length === 0 ? <p role="status">{page > 0 ? <>This history page is no longer available. <button type="button" onClick={() => updateFilters({ page: 0 })}>First history page</button></> : filtered ? 'No repair orders match these filters for this truck.' : 'No repair orders for this vehicle yet.'}</p> : <ul className="db-customer-vehicle-history">{history.data.items.map(order => <li key={order.id}>
          <button type="button" aria-label={`Open repair order ${order.order_number}`} onClick={() => onOpenOrder(order)}>
            <span><strong>{order.order_number}</strong><span className="db-customer-vehicle-history__description">{order.description || 'No description'}</span><small>{new Date(order.created_at).toLocaleDateString()} · {order.status.replace(/_/g, ' ')}{order.assigned_mechanic_id && mechanicName(order.assigned_mechanic_id) && ` · ${mechanicName(order.assigned_mechanic_id)}`}</small></span>
            <span>${Number(order.total_cost).toFixed(2)}</span><ChevronRight aria-hidden="true" />
          </button>
        </li>)}</ul>}
        {(page > 0 || history.data.has_more) && <nav aria-label="Vehicle history pages" className="db-customer-vehicle-history__pages">
          <button type="button" disabled={page === 0 || history.isFetching} aria-label="Previous history page" onClick={() => updateFilters({ page: page - 1 })}>Previous</button>
          <span>Page {page + 1} of {Math.max(1, Math.ceil(history.data.total / 25))}</span>
          <button type="button" disabled={!history.data.has_more || history.isFetching} aria-label="Next history page" onClick={() => updateFilters({ page: page + 1 })}>Next</button>
        </nav>}
      </>}
    </section>
    <ExternalServiceHistory vehicleId={vehicle.id} />
  </div>
}
export default function CustomerVehicleDetail(props: Props) {
  return <VehicleRecord key={`${props.customer.id}:${props.vehicle.id}`} {...props} />
}
