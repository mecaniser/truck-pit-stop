import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import type { VisitRequestResult } from '@/features/booking/booking-contract'
import type { Invoice, Quote, RepairOrder, Vehicle } from '@/types'
const mocks=vi.hoisted(()=>({get:vi.fn()}))
vi.mock('@/lib/api',()=>({default:{get:mocks.get}}))
import PortalDashboardPage,{PortalInvoicesPage} from '../PortalDashboardPage'
const vehicle=(id='a')=>({id,tenant_id:'tenant',customer_id:'customer',unit_number:id,year:2020,make:'Volvo',model:'VNR',license_plate:`P-${id}`} as Vehicle)
const order=(overrides:Partial<RepairOrder>={})=>({id:'ro',vehicle_id:'a',status:'in_progress',description:'Additional brake work',quote_sent:true,quote_approved:false,updated_at:'2026-11-03T12:00:00Z',...overrides} as RepairOrder)
const quote=(overrides:Partial<Quote>={})=>({id:'q',revision:1,sent_to_customer:true,is_approved:false,is_declined:false,total_amount:'450.00',created_at:'2026-11-03T12:00:00Z',...overrides} as Quote)
const invoice=(overrides:Partial<Invoice>={})=>({id:'inv',invoice_number:'TPS-1687',repair_order_id:'ro',source:'native',status:'sent',total_amount:'100.00',payment_summary:{state:'unpaid',applied_amount:'0.00',balance_due:'100.00',pending_amount:'0.00',basis:'settlement',note:null},...overrides} as Invoice)
function show({invoices=[invoice()],orders=[] as RepairOrder[],vehicles=[] as Vehicle[],revisions=[] as Quote[],historyFails=false,invoiceFails=false,appointmentFails=false,requests=[] as VisitRequestResult[],query='',page='home'}={}){
  const state={invoices,invoiceFails}
  mocks.get.mockImplementation(async(url:string)=>{
    if(url==='/vehicles')return{data:vehicles}
    if(url==='/repair-orders')return{data:orders}
    if(url==='/invoices'){if(state.invoiceFails)throw new Error('Unavailable');return{data:state.invoices}}
    if(url==='/appointments/visit-requests')return{data:requests}
    if(url==='/appointments'){if(appointmentFails)throw new Error('Unavailable');return{data:[]}}
    if(url.includes('/history')){if(historyFails)throw new Error('Forbidden');return{data:{revisions,events:[]}}}
    throw new Error(`Unexpected request ${url}`)
  })
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/portal${query}`]}>{page==='invoices'?<PortalInvoicesPage/>:<PortalDashboardPage/>}</MemoryRouter></QueryClientProvider>)
  return{client,state}
}
beforeEach(()=>{mocks.get.mockReset();useAuthStore.setState({user:{id:'user',tenant_id:'tenant',customer_id:'customer',role:'customer'} as never,isAuthenticated:true})})
describe('actual task-first portal',()=>{
  it('shows exactly one invoice action and excludes historical imports',async()=>{
    show({invoices:[invoice(),invoice({id:'old',invoice_number:'ETSINV-1182',source:'easy_truck_shop_import',total_amount:'314.02'})]})
    expect(await screen.findByRole('link',{name:'Pay invoice'})).toHaveAttribute('href','/portal/invoices/inv')
    expect(screen.getAllByRole('link',{name:'Pay invoice'})).toHaveLength(1)
    expect(screen.queryByText(/314.02|ETSINV-1182/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button',{name:'Select & pay'})).not.toBeInTheDocument()
  })
  it.each([
    ['unpaid','sent','0.00','0.00','100.00'],['partially_paid','sent','40.00','0.00','60.00'],['payment_pending','sent','0.00','20.00','100.00'],['partially_paid_pending','paid','40.00','20.00','60.00'],['paid','sent','100.00','0.00','0.00'],
  ] as const)('uses authoritative %s balance rather than invoice face total',async(state,status,applied,pending,due)=>{
    show({invoices:[invoice({status,payment_summary:{state,applied_amount:applied,balance_due:due,pending_amount:pending,basis:'settlement',note:null}})]})
    await screen.findByRole('heading',{name:'Account balance'})
    if(state==='paid'){expect(await screen.findByRole('heading',{name:'Nothing needs your attention'})).toBeInTheDocument();expect(screen.queryByRole('link',{name:'Pay invoice'})).not.toBeInTheDocument()}
    else{expect(await screen.findByRole('link',{name:'Pay invoice'})).toBeInTheDocument();expect(screen.getAllByText(`$${due}`).length).toBeGreaterThanOrEqual(2)}
  })
  it.each([undefined,null,'NaN','-1.00','1.234'])('does not turn missing/invalid remaining amount %s into a payment request',async due=>{
    show({invoices:[invoice({payment_summary:due===undefined?undefined:{state:'unpaid',applied_amount:'0.00',balance_due:due,pending_amount:null,basis:'unknown',note:null}})]})
    expect(await screen.findByRole('link',{name:'View invoice'})).toBeInTheDocument()
    expect(screen.queryByRole('link',{name:'Pay invoice'})).not.toBeInTheDocument()
    expect(screen.queryByText('$100.00')).not.toBeInTheDocument()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
  })
  it('hides internal collection identity and keeps original canonical key untouched',async()=>{
    const item=invoice({invoice_number:'DBN-COL-INTERNAL',source:'ets_collection_handoff',source_collection:{state:'active',collection_enabled:true,display_invoice_number:'TPS-1687'} as never})
    show({invoices:[item]});await screen.findByRole('link',{name:'Pay invoice'});expect(screen.getByRole('heading',{name:'Invoice TPS-1687'})).toBeInTheDocument();expect(screen.queryByText(/DBN-COL/)).not.toBeInTheDocument();expect(item.invoice_number).toBe('DBN-COL-INTERNAL')
  })
  it('does not reuse stale amounts after a failed read and recovers through Retry',async()=>{
    const{client,state}=show()
    await screen.findByRole('link',{name:'Pay invoice'})
    state.invoiceFails=true
    await act(async()=>{await client.invalidateQueries({queryKey:['customer-dashboard-invoices']})})
    expect(await screen.findByRole('alert')).toHaveTextContent('Invoice balances couldn’t load')
    expect(screen.queryByRole('link',{name:'Pay invoice'})).not.toBeInTheDocument()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
    state.invoiceFails=false;fireEvent.click(screen.getByRole('button',{name:'Try again'}));expect(await screen.findByRole('link',{name:'Pay invoice'})).toBeInTheDocument()
  })
  it('does not claim no tasks when visits are unavailable',async()=>{
    show({invoices:[],appointmentFails:true});expect(await screen.findByRole('alert')).toHaveTextContent('Today’s visits couldn’t load');expect(screen.queryByRole('heading',{name:'Nothing needs your attention'})).not.toBeInTheDocument()
  })
  it('filters by exact authorized ID and retains unmapped account invoices without VIN inference',async()=>{
    show({query:'?vehicle_id=a',vehicles:[vehicle(),vehicle('b')],orders:[order({id:'other',vehicle_id:'b',quote_sent:false,status:'paid'})],invoices:[invoice({id:'unknown',repair_order_id:'archived'}),invoice({id:'other',repair_order_id:'other',invoice_number:'OTHER'})]})
    expect(await screen.findByRole('link',{name:'Pay invoice'})).toHaveAttribute('href','/portal/invoices/unknown?vehicle_id=a')
    expect(screen.getByText('Account invoice · Vehicle not specified')).toBeInTheDocument();expect(screen.queryByText('Invoice OTHER')).not.toBeInTheDocument()
  })
  it('does not fall back to another vehicle for a foreign URL ID',async()=>{
    show({query:'?vehicle_id=foreign',vehicles:[vehicle()]});expect(await screen.findByRole('heading',{name:'Vehicle unavailable'})).toBeInTheDocument();expect(screen.queryByRole('link',{name:'Pay invoice'})).not.toBeInTheDocument()
  })
  it('retains cent-exact multi-invoice selection only in the multiple-invoice view',async()=>{
    const item=(id:string,due:string)=>invoice({id,invoice_number:`TPS-${id}`,payment_summary:{state:'partially_paid',balance_due:due,applied_amount:'99.00',pending_amount:null,basis:'settlement',note:null}})
    const{client,state}=show({page:'invoices',invoices:[item('a','0.10'),item('b','0.20')]})
    fireEvent.click(await screen.findByRole('button',{name:'Select & pay'}));fireEvent.click(screen.getByRole('button',{name:'Select Invoice TPS-a'}));fireEvent.click(screen.getByRole('button',{name:'Select Invoice TPS-b'}));expect(screen.getByRole('link',{name:'Pay 2 · $0.30'})).toHaveAttribute('href','/portal/invoices/a')
    state.invoices=[item('b','0.20')];await act(async()=>{await client.invalidateQueries({queryKey:['customer-dashboard-invoices']})});await waitFor(()=>expect(screen.queryByRole('link',{name:/Pay 2/})).not.toBeInTheDocument());expect(screen.queryByRole('button',{name:'Select & pay'})).not.toBeInTheDocument()
  })
  it('keeps failed authorization reads out of the no-task state and avoids forbidden draft routes',async()=>{
    show({invoices:[],orders:[order()],historyFails:true});expect(await screen.findByRole('alert')).toHaveTextContent('approval requests couldn’t load');expect(screen.queryByRole('heading',{name:'Nothing needs your attention'})).not.toBeInTheDocument();expect(mocks.get.mock.calls.every(([url])=>!url.startsWith('/quotes?'))).toBe(true)
  })
  it('only offers the latest sent, undecided authorization',async()=>{
    show({invoices:[],vehicles:[vehicle()],orders:[order()],revisions:[quote(),quote({id:'draft',revision:2,sent_to_customer:false,is_declined:true})]});expect(await screen.findByRole('link',{name:'Review request'})).toHaveAttribute('href','/portal/repairs?view=active&vehicle_id=a')
  })
  it.each(['declined','approved','closed'] as const)('does not resurrect %s authorization as an action',async kind=>{
    show({invoices:[],orders:[order(kind==='closed'?{status:'invoiced'}:{})],revisions:[quote({is_declined:kind==='declined',is_approved:kind==='approved'})]});await screen.findByRole('heading',{name:'Account balance'});expect(screen.queryByRole('link',{name:'Review request'})).not.toBeInTheDocument()
  })
})

describe('Today visit request status',()=>{
  it('shows a shop-accepted arrival date without calling it a paid reservation',async()=>{
    show({invoices:[],vehicles:[vehicle()],requests:[{id:'request-a',booking_kind:'request',request_reference:'VR-A',status:'accepted',version:2,service_name:'Inspection',vehicle_id:'a',preferred_date:null,accepted_arrival_date:'2099-11-04'}]})
    expect(await screen.findByRole('heading',{name:'Visit accepted'})).toBeInTheDocument()
    expect(screen.getByText('Nov 4, 2099')).toHaveAttribute('datetime','2099-11-04')
    expect(screen.getByText(/The shop will start as availability allows/)).toBeInTheDocument()
    expect(screen.queryByText(/^Paid$|^Confirmed$|^Reserved$/)).not.toBeInTheDocument()
  })
})


describe('invoice due calendar dates', () => {
  it.each([['2026-11-03', 'Due Nov 3, 2026'], ['2026-11-03T00:00:00Z', 'Due Nov 3, 2026'], ['2026-11-03T00:00:00+00:00', 'Due Nov 3, 2026'], ['2026-11-03T00:00:00.000Z', 'Due Nov 3, 2026'], ['2026-11-03T00:00:00.000000+00:00', 'Due Nov 3, 2026'], ['2026-02-30T00:00:00Z', 'Due Unavailable'], ['2026-02-30', 'Due Unavailable'], ['invalid', 'Due Unavailable']])('renders %s without shifting the calendar day or crashing', async (date, label) => {
    show({ invoices: [invoice({ due_date: date })] })
    expect(await screen.findByText(label)).toBeInTheDocument()
    expect(screen.queryByText('Due Nov 2, 2026')).not.toBeInTheDocument()
  })
})


describe('overview section roles', () => {
  it('separates current actions from history and preserves their destinations', async () => {
    show({vehicles:[vehicle()],orders:[order({id:'done',status:'paid',quote_sent:false,description:'Completed inspection'})]})
    const attention=await screen.findByRole('region',{name:'Needs your attention'})
    expect(within(attention).getByRole('link',{name:'Pay invoice'})).toHaveAttribute('href','/portal/invoices/inv?vehicle_id=a')
    const history=screen.getByRole('region',{name:'Recent activity'})
    expect(within(history).getByRole('heading',{name:'Completed inspection'})).toBeInTheDocument()
    expect(within(history).getByRole('link',{name:'View details'})).toHaveAttribute('href','/portal/repairs?vehicle_id=a')
    expect(within(attention).queryByText('Completed inspection')).not.toBeInTheDocument()
  })
  it('distinguishes pending confirmation from the available portion of the total', async () => {
    show({invoices:[invoice({payment_summary:{state:'payment_pending',applied_amount:'0.00',balance_due:'268.44',pending_amount:'100.00',basis:'settlement',note:null}})]})
    await screen.findByRole('heading',{name:'Account balance'})
    const summary=screen.getByRole('heading',{name:'Account balance'}).closest('section')!
    expect(within(summary).getByText('Total outstanding')).toBeInTheDocument()
    expect(within(summary).getByText('Pending confirmation').nextElementSibling).toHaveTextContent('$100.00')
    expect(within(summary).getByText('Available to pay').nextElementSibling).toHaveTextContent('$168.44')
    expect(within(summary).getByText('$268.44')).toBeInTheDocument()
  })
  it('uses a vehicle count while preserving the shop review warning for ambiguous identities', async () => {
    show({vehicles:[vehicle('a'),{...vehicle('b'),unit_number:'a',license_plate:'P-a'}]})
    await screen.findByRole('heading',{name:'Your vehicles'})
    const summary=screen.getByRole('heading',{name:'Your vehicles'}).closest('section')!
    expect(within(summary).getByText('2 vehicles')).toBeInTheDocument()
    expect(within(summary).getByText('Some vehicle details need the shop’s review.')).toBeInTheDocument()
    expect(within(summary).getByRole('link',{name:'Browse all 2 vehicles'})).toHaveAttribute('href','/portal/vehicles')
  })
})


describe('overview vehicle directory', () => {
  it('shows three real vehicles and keeps the full count and exact ID destinations', async () => {
    show({vehicles:[vehicle('a'),vehicle('b'),vehicle('c'),vehicle('d')]})
    const directory=await screen.findByRole('region',{name:'Your vehicles'})
    expect(within(directory).getByText('4 vehicles')).toBeInTheDocument()
    expect(within(directory).getAllByRole('listitem')).toHaveLength(3)
    expect(within(directory).getByRole('link',{name:/Unit #b/})).toHaveAttribute('href','/portal/vehicles?vehicle_id=b')
    expect(within(directory).queryByText('Unit #d')).not.toBeInTheDocument()
    expect(within(directory).getByRole('link',{name:'Browse all 4 vehicles'})).toHaveAttribute('href','/portal/vehicles')
  })
  it('keeps the selected vehicle directory scoped while the financial statement opens all invoices', async () => {
    show({query:'?vehicle_id=b',vehicles:[vehicle('a'),vehicle('b')]})
    const directory=await screen.findByRole('region',{name:'Your vehicle'})
    expect(within(directory).getAllByRole('listitem')).toHaveLength(1)
    expect(within(directory).getByRole('link',{name:/Unit #b/})).toHaveAttribute('href','/portal/vehicles?vehicle_id=b')
    expect(within(directory).getByRole('link',{name:'Vehicle details'})).toHaveAttribute('href','/portal/vehicles?vehicle_id=b')
    expect(screen.getByRole('link',{name:'View all invoices'})).toHaveAttribute('href','/portal/invoices')
  })
  it('handles an empty vehicle account without inventing records', async () => {
    show({vehicles:[]})
    const directory=await screen.findByRole('region',{name:'Your vehicles'})
    expect(within(directory).getByText('No vehicles yet.')).toBeInTheDocument()
    expect(within(directory).queryByRole('listitem')).not.toBeInTheDocument()
    expect(within(directory).getByRole('link',{name:'Manage vehicles'})).toHaveAttribute('href','/portal/vehicles')
  })
})


describe('invoice overview grouping', () => {
  it('separates zero balances without changing pending, unknown or payable actions', async () => {
    show({page:'invoices', invoices:[invoice(),invoice({id:'settled',invoice_number:'PAID',payment_summary:{state:'paid',applied_amount:'100.00',balance_due:'0.00',pending_amount:'0.00',basis:'settlement',note:null}}),invoice({id:'unknown',invoice_number:'UNKNOWN',payment_summary:undefined}),invoice({id:'pending',invoice_number:'PENDING',payment_summary:{state:'payment_pending',applied_amount:'0.00',balance_due:'100.00',pending_amount:'100.00',basis:'settlement',note:null}})]})
    const outstanding = await screen.findByRole('region',{name:'Invoices to review'})
    const history = screen.getByRole('region',{name:'Invoice history'})
    expect(within(outstanding).getAllByRole('article')).toHaveLength(3)
    expect(within(outstanding).getByRole('link',{name:'Pay invoice'})).toHaveAttribute('href','/portal/invoices/inv')
    expect(within(outstanding).getAllByRole('link',{name:'View invoice'})).toHaveLength(2)
    expect(within(history).getByRole('heading',{name:'Invoice PAID'})).toBeInTheDocument()
    expect(within(history).queryByRole('link',{name:'Pay invoice'})).not.toBeInTheDocument()
    expect(within(history).getByText('$0.00')).toBeInTheDocument()
  })
})
