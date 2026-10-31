import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
import CustomerHistoryOrderDetail from './CustomerHistoryOrderDetail'
import CustomerVehicleDetail from './CustomerVehicleDetail'
import type { Customer, Vehicle } from '@/types'
const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 400: '#b45309', 500: '#d97706', 600: '#b45309' } }) }))
const customer = { id: 'c1', company_name: 'Northline', first_name: 'Nora', last_name: 'North' } as Customer
const vehicle = { id: 'v1', customer_id: 'c1', make: 'Freightliner', model: 'Cascadia', unit_number: 'C-001', vin: '1FUJGLDR4DLAA0001' } as Vehicle
const order = { id: 'o1', order_number: 'RO-1', customer_id: 'c1', vehicle_id: 'v1', status: 'completed', total_cost: '145', created_at: '2026-10-12', description: 'Replace fan belt' }
function LocationProbe() { const location = useLocation(); return <output data-testid="location">{location.search}</output> }
function show(child: React.ReactNode, entry = '/') { return render(<MemoryRouter initialEntries={[entry]}><QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{child}<LocationProbe /></QueryClientProvider></MemoryRouter>) }
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
  const child=(v: Vehicle)=><MemoryRouter><QueryClientProvider client={client}><CustomerVehicleDetail customer={customer} vehicle={v} onOpenOrder={vi.fn()}/></QueryClientProvider></MemoryRouter>
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

it('searches all truck history on the server and resets pagination without touching queue filters', async () => {
  api.get.mockImplementation((_url, config) => Promise.resolve({data:{items:[{...order, order_number: config.params.search ? 'FOUND-99' : 'RO-1'}],total:26,has_more:true}}))
  show(<CustomerVehicleDetail customer={customer} vehicle={vehicle} onOpenOrder={vi.fn()}/>, '/?queue=on_floor&search=directory&historyFor=c1%3Av1&historyPage=2')
  await screen.findByRole('button', {name:'Open repair order RO-1'})
  expect(screen.getByRole('searchbox', { name: 'Search this truck’s repair history' })).toBeEnabled()
  expect(screen.getByLabelText('Repair history status')).toBeEnabled()
  expect(api.get).toHaveBeenLastCalledWith('/repair-orders', expect.objectContaining({params:expect.objectContaining({skip:50})}))
  fireEvent.change(screen.getByRole('searchbox'), {target:{value:'  fan belt  '}})
  expect(screen.queryByRole('button', {name:'Open repair order RO-1'})).not.toBeInTheDocument()
  await screen.findByRole('button', {name:'Open repair order FOUND-99'})
  expect(api.get).toHaveBeenLastCalledWith('/repair-orders', expect.objectContaining({params:{vehicle_id:'v1',paginated:true,skip:0,limit:25,search:'fan belt'},signal:expect.any(AbortSignal)}))
  const params = new URLSearchParams(screen.getByTestId('location').textContent ?? '')
  expect(params.get('queue')).toBe('on_floor')
  expect(params.get('search')).toBe('directory')
  expect(params.has('historyPage')).toBe(false)
  fireEvent.click(screen.getByLabelText('Repair history status'))
  fireEvent.mouseDown(screen.getByRole('option', {name:'Completed',exact:true}))
  await waitFor(()=>expect(api.get).toHaveBeenLastCalledWith('/repair-orders',expect.objectContaining({params:expect.objectContaining({search:'fan belt',status:'completed',skip:0})})))
  fireEvent.click(await screen.findByRole('button',{name:'Next history page'}))
  await waitFor(()=>expect(api.get).toHaveBeenLastCalledWith('/repair-orders',expect.objectContaining({params:expect.objectContaining({search:'fan belt',status:'completed',skip:25})})))
})

it('restores filter/page state from the URL and clears to the full first page', async () => {
  api.get.mockResolvedValue({data:{items:[],total:0,has_more:false}})
  show(<CustomerVehicleDetail customer={customer} vehicle={vehicle} onOpenOrder={vi.fn()}/>, '/?historyFor=c1%3Av1&historySearch=belts&historyStatus=paid&historyPage=1')
  expect(screen.getByRole('searchbox')).toHaveValue('belts')
  expect(screen.getByLabelText('Repair history status')).toHaveTextContent('Paid')
  expect(await screen.findByRole('button', { name: 'First history page' })).toBeVisible()
  expect(api.get).toHaveBeenLastCalledWith('/repair-orders',expect.objectContaining({params:{vehicle_id:'v1',paginated:true,skip:25,limit:25,search:'belts',status:'paid'}}))
  fireEvent.click(screen.getByRole('button',{name:'Clear filters'}))
  expect(await screen.findByText('No repair orders for this vehicle yet.')).toBeVisible()
  expect(api.get).toHaveBeenLastCalledWith('/repair-orders',expect.objectContaining({params:{vehicle_id:'v1',paginated:true,skip:0,limit:25}}))
  expect(screen.getByRole('searchbox')).toHaveValue('')
  expect(screen.getByLabelText('Repair history status')).toHaveTextContent('All statuses')
})

it('retries with the current filters and never labels failure as no matches', async () => {
  api.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({data:{items:[order],total:1,has_more:false}})
  show(<CustomerVehicleDetail customer={customer} vehicle={vehicle} onOpenOrder={vi.fn()}/>, '/?historyFor=c1%3Av1&historySearch=belt&historyStatus=completed')
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load repair history')
  expect(screen.queryByText(/No repair orders/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Retry repair history'}))
  expect(await screen.findByRole('button',{name:'Open repair order RO-1'})).toBeVisible()
  expect(api.get.mock.calls.every(([,config])=>config.params.vehicle_id === 'v1' && config.params.search === 'belt' && config.params.status === 'completed')).toBe(true)
})

it.each(['c2:v1','c1:v2'])('ignores filters belonging to another customer/truck %s', async scope => {
  api.get.mockResolvedValue({data:{items:[order],total:1,has_more:false}})
  show(<CustomerVehicleDetail customer={customer} vehicle={vehicle} onOpenOrder={vi.fn()}/>, `/?historyFor=${scope}&historySearch=private&historyStatus=paid&historyPage=8`)
  await screen.findByRole('button',{name:'Open repair order RO-1'})
  expect(screen.getByRole('searchbox')).toHaveValue('')
  expect(api.get).toHaveBeenLastCalledWith('/repair-orders',expect.objectContaining({params:{vehicle_id:'v1',paginated:true,skip:0,limit:25}}))
})

it('rejects a mismatched truck response even when filters match', async () => {
  api.get.mockResolvedValue({data:{items:[{...order,vehicle_id:'v2'}],total:1,has_more:false}})
  show(<CustomerVehicleDetail customer={customer} vehicle={vehicle} onOpenOrder={vi.fn()}/>, '/?historyFor=c1%3Av1&historySearch=belt')
  await screen.findByRole('alert')
  expect(screen.queryByRole('button',{name:'Open repair order RO-1'})).not.toBeInTheDocument()
})

it('bounds malformed URL paging and ignores unknown statuses', async () => {
  api.get.mockResolvedValue({data:{items:[],total:0,has_more:false}})
  show(<CustomerVehicleDetail customer={customer} vehicle={vehicle} onOpenOrder={vi.fn()}/>, '/?historyFor=c1%3Av1&historyStatus=invalid&historyPage=-1')
  await screen.findByText('No repair orders for this vehicle yet.')
  expect(api.get).toHaveBeenLastCalledWith('/repair-orders',expect.objectContaining({params:{vehicle_id:'v1',paginated:true,skip:0,limit:25}}))
})

it('distinguishes an empty filtered first page from an unavailable later page', async () => {
  api.get.mockResolvedValue({data:{items:[],total:0,has_more:false}})
  show(<CustomerVehicleDetail customer={customer} vehicle={vehicle} onOpenOrder={vi.fn()}/>, '/?historyFor=c1%3Av1&historySearch=missing&historyPage=9')
  fireEvent.click(await screen.findByRole('button', {name:'First history page'}))
  expect(await screen.findByText('No repair orders match these filters for this truck.')).toBeVisible()
  expect(api.get).toHaveBeenLastCalledWith('/repair-orders',expect.objectContaining({params:expect.objectContaining({search:'missing',skip:0})}))
})
