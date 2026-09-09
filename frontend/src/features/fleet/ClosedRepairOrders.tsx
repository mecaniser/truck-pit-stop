import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import type { BoardTruck, HistoryEntry } from './types'
import { fleetUnitLabel } from './helpers'

export default function ClosedRepairOrders({ trucks, onOpenRepairOrder }: {
  trucks: BoardTruck[]
  onOpenRepairOrder: (id: string) => void
}) {
  const [truckId, setTruckId] = useState('')
  const selected = trucks.find((truck) => truck.id === truckId)
  const history = useQuery<HistoryEntry[]>({
    queryKey: ['fleet-truck-history', truckId],
    queryFn: async () => (await api.get(`/fleet/trucks/${truckId}/history`)).data,
    enabled: Boolean(selected),
  })
  const orders = (history.data || []).filter((entry) => entry.kind === 'Repair' || entry.kind === 'PM')
  return <div>
    <label className="board-sort-lbl" htmlFor="closed-order-truck">Truck</label>
    <select id="closed-order-truck" className="fld-sel" value={selected ? truckId : ''} onChange={(event) => setTruckId(event.target.value)}>
      <option value="">Choose a truck…</option>
      {trucks.map((truck) => <option key={truck.id} value={truck.id}>{fleetUnitLabel(truck)}</option>)}
    </select>
    <p className="empty-note">Recent closed repair orders and PM from the selected truck’s service history.</p>
    {!selected ? <div className="tgrid-empty">Choose a truck to view its closed repair orders.</div>
      : history.isLoading ? <div role="status" className="tgrid-empty">Loading closed repair orders…</div>
      : history.isError ? <div role="alert" className="tgrid-empty">Closed repair orders could not be loaded. <button className="sbtn" onClick={() => { void history.refetch() }}>Retry</button></div>
      : !orders.length ? <div className="tgrid-empty">No closed repair orders in this truck’s recent service history.</div>
      : <div className="list-rows">{orders.map((order) => <button key={order.id} className="lrow" onClick={() => onOpenRepairOrder(order.id)}>
        <span>{order.kind} · {order.summary || 'Completed service'}</span>
        <span>{order.date ? new Date(order.date).toLocaleDateString() : ''} · Closed</span>
      </button>)}</div>}
  </div>
}
