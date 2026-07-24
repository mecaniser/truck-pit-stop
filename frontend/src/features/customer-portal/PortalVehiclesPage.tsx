import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Gauge, Plus, Truck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { format } from 'date-fns'

import { Spinner } from '@/components/ui'
import api from '@/lib/api'
import type { Invoice, RepairOrder, Vehicle } from '@/types'

import { Card, formatMoney, Money, SectionLabel, vehicleMeta, vehicleName } from './portal-ui'

async function getAll<T>(url: string) {
  const response = await api.get(url, { params: { paginated: true, skip: 0, limit: 100 } })
  return (Array.isArray(response.data) ? response.data : response.data.items) as T[]
}

export default function PortalVehiclesPage() {
  const { data: vehicles = [], isLoading } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: () => getAll<Vehicle>('/vehicles'),
  })
  const { data: orders = [] } = useQuery<RepairOrder[]>({
    queryKey: ['repair-orders'],
    queryFn: () => getAll<RepairOrder>('/repair-orders'),
  })
  const { data: invoices = [] } = useQuery<Invoice[]>({
    queryKey: ['customer-vehicle-invoices'],
    queryFn: async () => (await api.get('/invoices')).data,
  })

  const invoiceByOrder = useMemo(
    () => new Map(invoices.map(invoice => [invoice.repair_order_id, invoice])),
    [invoices],
  )

  if (isLoading) return <div className="flex min-h-[420px] items-center justify-center"><Spinner size="xl" /></div>

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-[-0.01em]">My fleet</h1>
          <p className="mt-1 text-[13px] text-[#8b92a5]">{vehicles.length} vehicle{vehicles.length === 1 ? '' : 's'} registered</p>
        </div>
        <Link
          to="/portal/settings?tab=vehicles"
          className="inline-flex h-10 items-center gap-1.5 rounded-[10px] border border-[#272d3d] bg-[#191d2a] px-3.5 text-[13px] font-bold text-[#c9cdd8]"
        >
          <Plus className="h-4 w-4" /> <span className="hidden sm:inline">Add vehicle</span>
        </Link>
      </header>

      {vehicles.map(vehicle => {
        const vehicleOrders = orders
          .filter(order => order.vehicle_id === vehicle.id)
          .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
        const unpaid = vehicleOrders
          .map(order => invoiceByOrder.get(order.id))
          .filter((invoice): invoice is Invoice => Boolean(invoice && !['paid', 'cancelled'].includes(invoice.status)))
        const balance = unpaid.reduce((sum, invoice) => sum + Number(invoice.total_amount || 0), 0)
        const lastService = vehicleOrders.find(order => ['paid', 'completed'].includes(order.status))
        const mileage = vehicle.mileage || 0
        const nextPm = mileage ? Math.ceil((mileage + 1) / 5000) * 5000 : 0
        const remaining = nextPm ? nextPm - mileage : 0
        const progress = mileage ? Math.min(100, ((mileage % 5000) / 5000) * 100) : 0

        return (
          <Card key={vehicle.id} className="overflow-hidden">
            <div className="flex flex-col gap-4 border-b border-[#1e2432] p-4 sm:flex-row sm:items-center sm:p-5">
              <div className="flex min-w-0 items-center gap-3.5 sm:gap-4">
                <div className="flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-xl border border-[#272d3d] bg-[#12161f] text-[#d9a521]">
                  <Truck className="h-6 w-6" />
                </div>
                <div className="min-w-0">
                  <h2 className="truncate text-lg font-extrabold">{vehicleName(vehicle)}</h2>
                  <p className="mt-1 truncate text-xs font-semibold text-[#d9a521]">{vehicleMeta(vehicle) || 'Vehicle details'}</p>
                </div>
              </div>
              <div className="ml-auto text-left sm:text-right">
                <Money className="text-xl font-extrabold">{mileage ? mileage.toLocaleString() : '—'} <span className="text-xs font-bold text-[#8b92a5]">mi</span></Money>
                <p className="mt-0.5 text-[11px] text-[#5c6375]">updated {format(new Date(vehicle.updated_at), 'MMM d, yyyy')}</p>
              </div>
            </div>

            <div className="grid gap-2.5 p-4 sm:grid-cols-3 sm:p-5">
              <div className="rounded-xl border border-[#1e2432] bg-[#12161f] p-3.5">
                <SectionLabel className="text-[10px]">Next PM due</SectionLabel>
                <p className="mt-1 text-base font-extrabold text-[#f0b959]">{remaining ? `in ${remaining.toLocaleString()} mi` : 'Mileage needed'}</p>
                <div className="mt-2 h-[5px] overflow-hidden rounded-full bg-[#1c2130]">
                  <div className="h-full rounded-full bg-[#f0b959]" style={{ width: `${progress}%` }} />
                </div>
              </div>
              <div className={`rounded-xl bg-[#12161f] p-3.5 ${balance > 0 ? 'border border-[#ff6b6e]/30' : 'border border-[#1e2432]'}`}>
                <SectionLabel className="text-[10px]">Open balance</SectionLabel>
                <Money className={`mt-1 block text-base font-extrabold ${balance > 0 ? 'text-[#ff8b8d]' : 'text-[#3ecf6f]'}`}>{formatMoney(balance)}</Money>
                <p className="mt-1 text-[11px] text-[#8b92a5]">{unpaid.length} unpaid invoice{unpaid.length === 1 ? '' : 's'}</p>
              </div>
              <div className="rounded-xl border border-[#1e2432] bg-[#12161f] p-3.5">
                <SectionLabel className="text-[10px]">Last service</SectionLabel>
                <p className="mt-1 text-base font-extrabold">{lastService ? format(new Date(lastService.updated_at), 'MMM d, yyyy') : 'No service yet'}</p>
                <p className="mt-1 truncate text-[11px] text-[#8b92a5]">{lastService?.description || 'Service history will appear here'}</p>
              </div>
            </div>

            <div className="flex flex-col gap-4 border-t border-[#1e2432] bg-[#12161f] p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
              <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-xs sm:flex sm:gap-7">
                <div><SectionLabel className="block text-[10px] text-[#5c6375]">VIN</SectionLabel><span className="mt-1 block max-w-[180px] truncate text-[#c9cdd8]">{vehicle.vin || 'Not provided'}</span></div>
                <div><SectionLabel className="block text-[10px] text-[#5c6375]">Color</SectionLabel><span className="mt-1 block text-[#c9cdd8]">{vehicle.color || 'Not provided'}</span></div>
                <div><SectionLabel className="block text-[10px] text-[#5c6375]">Orders</SectionLabel><span className="mt-1 block text-[#c9cdd8]">{vehicleOrders.length} all-time</span></div>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:flex">
                <Link to="/portal/services" className="flex h-10 items-center justify-center rounded-[10px] bg-[#8b7cf7] px-4 text-xs font-extrabold text-[#0e1118]">Book service</Link>
                <Link to="/portal/repairs" className="flex h-10 items-center justify-center rounded-[10px] border border-[#272d3d] bg-[#191d2a] px-4 text-xs font-bold text-[#c9cdd8]">Service history</Link>
              </div>
            </div>
          </Card>
        )
      })}

      {vehicles.length === 0 && (
        <Card className="p-10 text-center">
          <Gauge className="mx-auto h-9 w-9 text-[#5c6375]" />
          <h2 className="mt-3 font-extrabold">No vehicles registered</h2>
          <p className="mt-1 text-sm text-[#8b92a5]">Add your truck to book services and track maintenance.</p>
        </Card>
      )}
    </div>
  )
}
