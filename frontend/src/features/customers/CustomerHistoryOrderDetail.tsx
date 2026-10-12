import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'

interface HistoryOrderDetail {
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
const money = (value: string | null) => value !== null && Number.isFinite(Number(value)) ? `$${Number(value).toFixed(2)}` : '—'
export default function CustomerHistoryOrderDetail({ customerId, orderId, onOpenOrder }: {
  customerId: string; orderId: string; onOpenOrder?: (orderId: string) => void
}) {
  const query = useQuery({
    queryKey: ['customerHistoryDetail', customerId, orderId],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<HistoryOrderDetail>(`/customers/${customerId}/history/${orderId}`, { signal })
      if (data.id !== orderId || !Array.isArray(data.labor) || !Array.isArray(data.parts)) throw new Error('Invalid history detail')
      return data
    },
    retry: false,
  })
  if (query.isLoading) return <p role="status">Loading repair details…</p>
  if (query.isError || !query.data) return <div role="alert">Could not load repair details. <button type="button" onClick={() => void query.refetch()}>Retry repair details</button></div>
  const data = query.data
  let internalNotes: string | null = null
  if (data.internal_notes) {
    try { JSON.parse(data.internal_notes) } catch { internalNotes = data.internal_notes }
  }
  return <section className="db-customer-history-detail" aria-label={`Repair details ${data.order_number}`}>
    <dl className="db-customer-record__facts">
      <div><dt>Mechanic</dt><dd>{data.mechanic_name || '—'}</dd></div>
      <div><dt>Amount paid</dt><dd>{money(data.amount_paid)}</dd></div>
      <div><dt>Order total</dt><dd>{money(data.total_cost)}</dd></div>
    </dl>
    <h4>Work performed</h4>
    {data.labor.length ? <ul>{data.labor.map(line => <li key={line.id}><span>{line.description || 'Labor'}</span><span>{Number(line.hours).toFixed(2)} hr × {money(line.hourly_rate)} = {money(line.total_cost)}</span></li>)}</ul> : <p>No labor recorded</p>}
    <h4>Parts used</h4>
    {data.parts.length ? <ul>{data.parts.map(part => <li key={part.id}><span>{part.name || 'Part'}{part.sku && ` · ${part.sku}`}</span><span>{part.quantity} × {money(part.unit_price)} = {money(part.total_price)}</span></li>)}</ul> : <p>No parts used</p>}
    {data.customer_notes && <p className="whitespace-pre-wrap">Customer: {data.customer_notes}</p>}
    {internalNotes && <p className="whitespace-pre-wrap">Internal: {internalNotes}</p>}
    {onOpenOrder && <button type="button" className="db-customer-history-detail__open" onClick={() => onOpenOrder(orderId)}>Open repair order {data.order_number}</button>}
  </section>
}
