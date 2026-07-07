import { useQuery } from '@tanstack/react-query'
import { Truck } from 'lucide-react'
import api from '../../lib/api'

interface FleetInvoice {
  id: string
  invoice_number: string
  repair_order_id: string
  order_number?: string | null
  status: string
  total_amount: number
  created_at: string
  unit_number?: string | null
  vehicle_label?: string | null
}

export default function InternalInvoiceList() {
  const { data: fleetInvoices } = useQuery<FleetInvoice[]>({
    queryKey: ['fleet-invoices'],
    queryFn: async () => {
      const response = await api.get('/fleet/invoices')
      return response.data
    },
  })
  const invoices = fleetInvoices || []

  return (
    <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <Truck className="w-5 h-5 text-orange-400" />
          Internal Invoices ({invoices.length})
        </h2>
      </div>
      {invoices.length === 0 ? (
        <p className="text-sm text-gray-500">No internal invoices yet. Completing an internal work order records one here.</p>
      ) : (
        <div className="max-h-96 overflow-y-auto space-y-1">
          {invoices.map((inv) => (
            <div key={inv.id} className="flex items-start justify-between gap-3 p-3 bg-gray-700/30 border border-gray-700/40 rounded-lg">
              <div className="min-w-0">
                <p className="text-sm text-gray-100 truncate">
                  {inv.invoice_number}
                  {inv.unit_number ? ` · ${inv.unit_number}` : ''}
                </p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {inv.vehicle_label || 'Truck'}
                  <span className="mx-2">·</span>
                  {new Date(inv.created_at).toLocaleDateString()}
                </p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-sm text-gray-100">${inv.total_amount.toFixed(2)}</p>
                <p className="text-xs text-gray-500 capitalize">{inv.status}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
