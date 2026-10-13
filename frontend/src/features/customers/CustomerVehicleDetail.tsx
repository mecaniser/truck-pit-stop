import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Plus } from 'lucide-react'
import api from '@/lib/api'
import { customerDisplayName } from '@/lib/customerName'
import type { Customer, RepairOrder, Vehicle } from '@/types'
import './customer-workspace.css'

type Props = { customer: Customer; vehicle: Vehicle; onOpenOrder: (order: RepairOrder) => void; onCreateOrder?: () => void }
type HistoryPage = { items: RepairOrder[]; total: number; has_more: boolean }
function VehicleRecord({ customer, vehicle, onOpenOrder, onCreateOrder }: Props) {
  const [page, setPage] = useState(0)
  const history = useQuery({
    queryKey: ['customerVehicleRepairOrders', customer.id, vehicle.id, page],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<HistoryPage>('/repair-orders', { params: { vehicle_id: vehicle.id, paginated: true, skip: page * 25, limit: 25 }, signal })
      if (!Array.isArray(data.items) || typeof data.total !== 'number' || typeof data.has_more !== 'boolean' || data.items.some(order => order.vehicle_id !== vehicle.id)) throw new Error('Invalid vehicle history')
      return data
    },
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
    {onCreateOrder && <div className="db-customer-record__work-actions"><button type="button" onClick={onCreateOrder}><Plus aria-hidden="true" />New repair order</button></div>}
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
    <section aria-label="Vehicle repair history">
      <h3>Repair history{history.data && !history.isError ? ` (${history.data.total})` : ''}</h3>
      {history.isLoading ? <p role="status">Loading repair history…</p> : history.isError || !history.data ? <div role="alert">Could not load repair history. <button type="button" onClick={() => void history.refetch()}>Retry repair history</button></div> : <>
        {history.data.items.length === 0 ? <p>No repair orders for this vehicle yet.</p> : <ul className="db-customer-vehicle-history">{history.data.items.map(order => <li key={order.id}>
          <button type="button" aria-label={`Open repair order ${order.order_number}`} onClick={() => onOpenOrder(order)}>
            <span><strong>{order.order_number}</strong><span className="db-customer-vehicle-history__description">{order.description || 'No description'}</span><small>{new Date(order.created_at).toLocaleDateString()} · {order.status.replace(/_/g, ' ')}{order.assigned_mechanic_id && mechanicName(order.assigned_mechanic_id) && ` · ${mechanicName(order.assigned_mechanic_id)}`}</small></span>
            <span>${Number(order.total_cost).toFixed(2)}</span><ChevronRight aria-hidden="true" />
          </button>
        </li>)}</ul>}
        {(page > 0 || history.data.has_more) && <nav aria-label="Vehicle history pages" className="db-customer-vehicle-history__pages">
          <button type="button" disabled={page === 0 || history.isFetching} aria-label="Previous history page" onClick={() => setPage(value => value - 1)}>Previous</button>
          <span>Page {page + 1} of {Math.max(1, Math.ceil(history.data.total / 25))}</span>
          <button type="button" disabled={!history.data.has_more || history.isFetching} aria-label="Next history page" onClick={() => setPage(value => value + 1)}>Next</button>
        </nav>}
      </>}
    </section>
  </div>
}
export default function CustomerVehicleDetail(props: Props) {
  return <VehicleRecord key={`${props.customer.id}:${props.vehicle.id}`} {...props} />
}
