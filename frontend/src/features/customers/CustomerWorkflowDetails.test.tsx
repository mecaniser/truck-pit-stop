import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
import CustomerHistoryOrderDetail from './CustomerHistoryOrderDetail'
import CustomerVehicleDetail from './CustomerVehicleDetail'
import type { Customer, Vehicle } from '@/types'
const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
const customer = { id: 'c1', company_name: 'Northline', first_name: 'Nora', last_name: 'North' } as Customer
const vehicle = { id: 'v1', customer_id: 'c1', make: 'Freightliner', model: 'Cascadia', unit_number: 'C-001', vin: '1FUJGLDR4DLAA0001' } as Vehicle
const order = { id: 'o1', order_number: 'RO-1', customer_id: 'c1', vehicle_id: 'v1', status: 'completed', total_cost: '145', created_at: '2026-10-12', description: 'Replace fan belt' }
function show(child: React.ReactNode) { return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{child}</QueryClientProvider>) }
beforeEach(() => { api.get.mockReset() })
it('retries the exact customer and order without pretending failure is empty work', async () => {
  api.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({data:{...order, labor:[], parts:[], amount_paid:null}})
  show(<CustomerHistoryOrderDetail customerId="c1" orderId="o1" />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load repair details')
  expect(screen.queryByText('No labor recorded')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Retry repair details'}))
  expect(await screen.findByText('No labor recorded')).toBeVisible()
  expect(api.get.mock.calls.every(call=>call[0]==='/customers/c1/history/o1')).toBe(true)
})
it('opens the exact historical order', async () => {
  api.get.mockResolvedValue({data:{...order,labor:[],parts:[],amount_paid:null}})
  const open=vi.fn()
  show(<CustomerHistoryOrderDetail customerId="c1" orderId="o1" onOpenOrder={open}/>)
  fireEvent.click(await screen.findByRole('button',{name:'Open repair order RO-1'}))
  expect(open).toHaveBeenCalledWith('o1')
})
it('paginates bounded truck history and opens its selected order', async () => {
  api.get.mockResolvedValueOnce({data:{items:[order],total:26,has_more:true}}).mockResolvedValue({data:{items:[{...order,id:'o26',order_number:'RO-26'}],total:26,has_more:false}})
  const open=vi.fn()
  show(<CustomerVehicleDetail customer={customer} vehicle={vehicle} onOpenOrder={open}/>)
  expect(await screen.findByRole('button',{name:/Open repair order RO-1/})).toBeVisible()
  expect(api.get).toHaveBeenCalledWith('/repair-orders',expect.objectContaining({params:{vehicle_id:'v1',paginated:true,skip:0,limit:25}}))
  fireEvent.click(screen.getByRole('button',{name:'Next history page'}))
  fireEvent.click(await screen.findByRole('button',{name:/Open repair order RO-26/}))
  expect(open).toHaveBeenCalledWith(expect.objectContaining({id:'o26'}))
  expect(api.get).toHaveBeenLastCalledWith('/repair-orders',expect.objectContaining({params:{vehicle_id:'v1',paginated:true,skip:25,limit:25}}))
})
it('does not show empty truck history on a failed request', async () => {
  api.get.mockRejectedValue(new Error('unavailable'))
  show(<CustomerVehicleDetail customer={customer} vehicle={vehicle} onOpenOrder={vi.fn()}/>)
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load repair history')
  expect(screen.queryByText(/No repair orders/)).not.toBeInTheDocument()
})
it('does not reuse another truck history while loading', async () => {
  const client=new QueryClient({defaultOptions:{queries:{retry:false}}})
  api.get.mockResolvedValueOnce({data:{items:[order],total:1,has_more:false}})
  const child=(v: Vehicle)=><QueryClientProvider client={client}><CustomerVehicleDetail customer={customer} vehicle={v} onOpenOrder={vi.fn()}/></QueryClientProvider>
  const view=render(child(vehicle))
  await screen.findByRole('button',{name:/Open repair order RO-1/})
  api.get.mockImplementation(()=>new Promise(()=>{}))
  view.rerender(child({...vehicle,id:'v2'}))
  expect(screen.queryByRole('button',{name:/Open repair order RO-1/})).not.toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Loading repair history')
})

it('preserves the assigned mechanic in vehicle repair history', async () => {
  api.get.mockImplementation((url: string)=>Promise.resolve({data:url==='/mechanics' ? [{id:'m1',first_name:'Alex',last_name:'Lee'}] : {items:[{...order,assigned_mechanic_id:'m1'}],total:1,has_more:false}}))
  show(<CustomerVehicleDetail customer={customer} vehicle={vehicle} onOpenOrder={vi.fn()}/>)
  expect(await screen.findByText(/Alex Lee/)).toBeVisible()
})
