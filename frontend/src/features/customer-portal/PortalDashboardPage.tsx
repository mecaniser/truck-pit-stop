import { formatCalendarDate } from '@/lib/calendarDate'
import { useEffect, useMemo, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { format, isToday, isValid } from 'date-fns'
import { AlertCircle, CalendarDays, Check, ChevronRight, ClipboardCheck, FileText, Truck, Wrench } from 'lucide-react'
import { ControlButton } from '@/components/ui/Controls'
import { Spinner } from '@/components/ui'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import type { Appointment, Invoice, RepairOrder, Vehicle } from '@/types'
import { centsToMoney, moneyToCents } from '@/features/payments/money'
import { latestCustomerVisibleAuthorization, type AuthorizationHistory } from '@/features/quotes/authorization'
import { customerInvoiceLabel } from '@/lib/invoiceIdentity'
import { getPortalItems, resolveVehicleScope, scopedPortalPath, vehicleIdentity, vehicleIdentityCollisions } from './portal-context'
import { portalInvoiceBalance, canPayPortalInvoice, currentPortalInvoices } from './portal-invoices'
import PortalVehicleScope from './PortalVehicleScope'
import CustomerVisitRequestCard from '@/features/appointments/CustomerVisitRequestCard'
import type { VisitRequestResult } from '@/features/booking/booking-contract'
import { formatMoney, repairStatusLabel } from './portal-ui'
import './portal-task-flow.css'

const actionableOrder = (order: RepairOrder) => order.quote_sent === true && order.quote_approved !== true && !['paid', 'cancelled', 'declined', 'completed', 'invoiced'].includes(order.status)
const openOrder = (order: RepairOrder) => !['paid', 'cancelled', 'declined', 'completed', 'invoiced'].includes(order.status)
function usePortalData() {
  const user = useAuthStore(state => state.user)
  const key = [user?.tenant_id, user?.customer_id]
  const vehicles = useQuery({ queryKey: ['vehicles', ...key], queryFn: ({ signal }) => getPortalItems<Vehicle>('/vehicles', {}, signal) })
  const orders = useQuery({ queryKey: ['repair-orders', ...key], queryFn: ({ signal }) => getPortalItems<RepairOrder>('/repair-orders', {}, signal) })
  const invoices = useQuery({ queryKey: ['customer-dashboard-invoices', ...key], queryFn: ({ signal }) => getPortalItems<Invoice>('/invoices', {}, signal) })
  return { user, key, vehicles, orders, invoices }
}
function ResourceError({ message, retry }: {message: string; retry: () => void}) {
  return <div className="cp-panel cp-error" role="alert"><AlertCircle/><div><h2>{message}</h2><p>Please try again. Information is unavailable until it loads.</p></div><ControlButton className="cp-secondary" onClick={retry}>Try again</ControlButton></div>
}
function InvoiceRows({invoices, orders, vehicles, scope, origin='Today', selecting=false, selectedIds=[], toggle}: {origin?:'Today'|'Invoices';selecting?:boolean;selectedIds?:string[];toggle?:(id:string)=>void;invoices: Invoice[]; orders: RepairOrder[]; vehicles: Vehicle[]; scope: string|null}) {
  const orderById = new Map(orders.map(order => [order.id, order]))
  const vehicleById = new Map(vehicles.map(vehicle => [vehicle.id, vehicle]))
  return <div className="cp-task-list">{invoices.map(invoice => {
    const order = orderById.get(invoice.repair_order_id)
    const vehicle = order ? vehicleById.get(order.vehicle_id) : null
    const balance = portalInvoiceBalance(invoice)
    const pending = moneyToCents(invoice.payment_summary?.pending_amount ?? '0.00')
    const available = balance !== null && pending !== null && pending >= 0n && pending <= balance ? balance - pending : null
    const canPay = canPayPortalInvoice(invoice)
    return <article className="cp-task" key={invoice.id}><span className="cp-task-icon"><FileText size={22}/></span><div className="cp-task-copy"><span className="cp-unit">{vehicle ? vehicleIdentity(vehicle) : 'Account invoice · Vehicle not specified'}</span><h3>{customerInvoiceLabel(invoice)}</h3><p>{pending !== null && pending > 0n ? `${formatMoney(centsToMoney(pending))} awaiting confirmation${available !== null ? ` · ${formatMoney(centsToMoney(available))} available to pay` : ''}` : invoice.due_date ? `Due ${formatCalendarDate(invoice.due_date)}` : 'No due date listed'}</p></div><div className="cp-task-end"><strong>{balance === null ? 'Unavailable' : formatMoney(centsToMoney(balance))}</strong><span className="cp-state">{balance === null ? 'Contact the shop before paying' : balance===0n ? 'No balance due' : pending !== null && pending > 0n ? 'Payment pending' : invoice.payment_summary?.state === 'overdue' ? 'Past due' : 'Invoice due'}</span></div><>{selecting && canPay ? <ControlButton className="cp-secondary" aria-pressed={selectedIds.includes(invoice.id)} aria-label={`${selectedIds.includes(invoice.id)?'Deselect':'Select'} ${customerInvoiceLabel(invoice)}`} onClick={()=>toggle?.(invoice.id)}>{selectedIds.includes(invoice.id)?'Selected':'Select'}</ControlButton> : <Link data-db-control="action" className={origin === 'Today' && canPay ? 'cp-primary' : 'cp-secondary'} to={scopedPortalPath(`/portal/invoices/${invoice.id}`,scope)} state={{paymentOrigin: origin, returnTo: scopedPortalPath(origin==='Invoices'?'/portal/invoices':'/portal',scope)}}>{canPay ? 'Pay invoice' : 'View invoice'}<ChevronRight size={15}/></Link>}</></article>
  })}</div>
}
export function PortalInvoicesPage() {
  const data = usePortalData()
  const [params,setParams] = useSearchParams()
  const [selecting,setSelecting]=useState(false)
  const [selectedIds,setSelectedIds]=useState<string[]>([])
  const scopeKey=params.toString()
  useEffect(()=>{setSelecting(false);setSelectedIds([])},[scopeKey])
  if(data.vehicles.isLoading || data.orders.isLoading || data.invoices.isLoading) return <Spinner size="xl"/>
  if(data.vehicles.isError || data.orders.isError || data.invoices.isError) return <ResourceError message="Invoices couldn’t load" retry={()=>{void data.vehicles.refetch();void data.orders.refetch();void data.invoices.refetch()}}/>
  const scope = resolveVehicleScope(data.vehicles.data || [],params.get('vehicle_id'))
  const orderMap = new Map((data.orders.data || []).map(o=>[o.id,o]))
  const invoices=currentPortalInvoices(data.invoices.data || []).filter(i=>!scope.vehicleId || !orderMap.get(i.repair_order_id) || orderMap.get(i.repair_order_id)?.vehicle_id === scope.vehicleId)
  const eligible=invoices.filter(canPayPortalInvoice)
  const selected=eligible.filter(i=>selectedIds.includes(i.id))
  const total=selected.reduce((sum,i)=>sum+portalInvoiceBalance(i)!-moneyToCents(i.payment_summary?.pending_amount ?? '0.00')!,0n)
  return <div className="cp-root"><div className="cp-title"><h1>Invoices</h1><PortalVehicleScope vehicles={data.vehicles.data || []} requested={params.get('vehicle_id')} onChange={id=>setParams(id?{vehicle_id:id}:{})}/></div>{!scope.invalid&&eligible.length>1&&<div className="mb-4 flex flex-wrap gap-3">{selecting&&selected.length>0&&<Link data-db-control="action" className="cp-primary" to={scopedPortalPath(`/portal/invoices/${selected[0].id}`,scope.vehicleId)} state={{paymentOrigin:'Invoices',invoiceQueue:selected.map(i=>i.id)}}>Pay {selected.length} · {formatMoney(centsToMoney(total))}</Link>}<ControlButton className="cp-secondary" onClick={()=>{setSelecting(!selecting);setSelectedIds([])}}>{selecting?'Done':'Select & pay'}</ControlButton></div>}{scope.invalid ? <div role="alert" className="cp-panel cp-empty"><h2>Vehicle unavailable</h2><p>Choose one of your vehicles to continue.</p></div> : invoices.length ? <InvoiceRows invoices={invoices} orders={data.orders.data || []} vehicles={data.vehicles.data || []} scope={scope.vehicleId} origin="Invoices" selecting={selecting&&eligible.length>1} selectedIds={selected.map(i=>i.id)} toggle={id=>setSelectedIds(current=>current.includes(id)?current.filter(v=>v!==id):[...current,id])}/> : <div className="cp-panel cp-empty"><Check/><h2>No invoices to show</h2></div>}</div>
}
export default function PortalDashboardPage() {
  const data = usePortalData()
  const [params,setParams] = useSearchParams()
  const vehicles = data.vehicles.data || []
  const orders = useMemo(()=>data.orders.data || [],[data.orders.data])
  const allInvoices = currentPortalInvoices(data.invoices.data || [])
  const scope = resolveVehicleScope(vehicles,params.get('vehicle_id'))
  const appointments = useQuery({queryKey:['appointments',...data.key],queryFn: ({ signal }) => getPortalItems<Appointment>('/appointments', {}, signal)})
  const requests = useQuery({ queryKey: ['visit-requests', ...data.key], queryFn: ({ signal }) => getPortalItems<VisitRequestResult>('/appointments/visit-requests', {}, signal) })
  const candidates = orders.filter(actionableOrder)
  const authQueries = useQueries({queries:candidates.map(order=>({queryKey:['authorization-history',order.id,...data.key],queryFn:async()=> (await api.get(`/quotes/repair-order/${order.id}/history`)).data as AuthorizationHistory}))})
  const approvals = candidates.flatMap((order,index)=>{
    if(authQueries[index]?.isError) return []
    const revision=latestCustomerVisibleAuthorization(authQueries[index]?.data?.revisions)
    return revision && !revision.is_approved && !revision.is_declined ? [{order,revision}] : []
  }).filter(({order})=>!scope.vehicleId || order.vehicle_id===scope.vehicleId)
  const orderById = useMemo(()=>new Map(orders.map(order=>[order.id,order])),[orders])
  const invoices = (data.invoices.isError?[]:allInvoices).filter(invoice=>!scope.vehicleId || !orderById.get(invoice.repair_order_id) || orderById.get(invoice.repair_order_id)?.vehicle_id===scope.vehicleId).filter(invoice=>{const value=portalInvoiceBalance(invoice);return value===null || value>0n})
  const accountBalances=allInvoices.map(invoice=>({invoice,balance:portalInvoiceBalance(invoice)}))
  const unknown=accountBalances.some(item=>item.balance===null)
  const balance=accountBalances.reduce((total,item)=>total+(item.balance ?? 0n),0n)
  const pendingValues=accountBalances.filter(item=>item.balance!==null&&item.balance>0n).map(item=>moneyToCents(item.invoice.payment_summary?.pending_amount ?? '0.00'))
  const pendingKnown=pendingValues.every(amount=>amount!==null&&amount>=0n)
  const pending=pendingKnown ? pendingValues.reduce<bigint>((total,amount)=>total+amount!,0n) : null
  const visits=(appointments.isError?[]:appointments.data || []).filter(visit=>!['completed','cancelled','no_show'].includes(visit.status)&&isValid(new Date(visit.scheduled_at))&&isToday(new Date(visit.scheduled_at))&&(!scope.vehicleId||!visit.vehicle_id||visit.vehicle_id===scope.vehicleId)).sort((a,b)=>a.scheduled_at.localeCompare(b.scheduled_at))
  const work=orders.filter(order=>openOrder(order)&&!candidates.some(candidate=>candidate.id===order.id)&&(!scope.vehicleId||scope.vehicleId===order.vehicle_id))
  const recent=orders.filter(order=>['paid','completed'].includes(order.status)&&(!scope.vehicleId||scope.vehicleId===order.vehicle_id)).sort((a,b)=>b.updated_at.localeCompare(a.updated_at)).slice(0,3)
  const visibleRequests = (requests.isError ? [] : requests.data || []).filter(request => !scope.vehicleId || !request.vehicle_id || request.vehicle_id === scope.vehicleId).slice(0, 3)
  const hasReadError=requests.isLoading||requests.isError||data.vehicles.isError||data.orders.isError||data.invoices.isError||appointments.isError||authQueries.some(query=>query.isError)
  const loading=data.vehicles.isLoading||data.orders.isLoading||data.invoices.isLoading||appointments.isLoading||authQueries.some(query=>query.isLoading)
  if(loading) return <div className="flex min-h-[420px] items-center justify-center"><Spinner size="xl"/></div>
  if(data.vehicles.isError || data.orders.isError) return <ResourceError message="Today’s information couldn’t load" retry={()=>{void data.vehicles.refetch();void data.orders.refetch()}}/>
  const count=approvals.length+invoices.length+visits.length+visibleRequests.filter(request=>request.status==='accepted').length
  const setScope=(id:string|null)=>setParams(id?{vehicle_id:id}:{})
  const book=scopedPortalPath('/portal/services',scope.vehicleId)
  const unitFor=(id:string|null)=>{const vehicle=vehicles.find(v=>v.id===id);return vehicle?vehicleIdentity(vehicle):'Vehicle not specified'}
  return <div className="cp-root cp-overview"><div className="cp-title"><div><h1>Today</h1><p>{scope.vehicle ? `Tasks for ${vehicleIdentity(scope.vehicle)}` : 'Across your vehicles'} · {format(new Date(),'EEEE, MMMM d')}</p></div><div className="cp-title-actions"><PortalVehicleScope vehicles={vehicles} requested={params.get('vehicle_id')} onChange={setScope}/><Link data-db-control="action" className="cp-secondary" to={book}><CalendarDays size={17}/>Book a service</Link></div></div>{scope.invalid ? <div className="cp-panel cp-empty" role="alert"><AlertCircle/><h2>Vehicle unavailable</h2><p>Choose one of your vehicles to view its tasks.</p></div> : <div className="cp-home-grid"><div className="cp-today"><section className={count ? "cp-attention cp-attention-required" : "cp-attention"} aria-labelledby="portal-attention-heading"><div className="cp-list-heading"><h2 id="portal-attention-heading">{count ? 'Needs your attention' : hasReadError ? 'Today’s information is incomplete' : 'Nothing needs your attention'}</h2>{count>0&&<span className="cp-count">{count}</span>}</div>{count>0&&<p className="cp-section-description">Review requests, payments and today’s visits here.</p>}{data.invoices.isError&&<ResourceError message="Invoice balances couldn’t load" retry={()=>{void data.invoices.refetch()}}/>}{authQueries.some(q=>q.isError)&&<ResourceError message="Some approval requests couldn’t load" retry={()=>authQueries.forEach(q=>{void q.refetch()})}/>}{appointments.isError&&<ResourceError message="Today’s visits couldn’t load" retry={()=>{void appointments.refetch()}}/>}{requests.isLoading&&<p role="status">Loading visit requests…</p>}{requests.isError&&<ResourceError message="Visit requests couldn’t load" retry={()=>{void requests.refetch()}}/>}{visibleRequests.length>0&&<section className="space-y-3 mb-6" aria-label="Visit requests"><h2>Visit requests</h2>{visibleRequests.map(request=><CustomerVisitRequestCard key={`${request.id}:${request.version}`} request={request} vehicleLabel={unitFor(request.vehicle_id || null)}/>)}</section>}{approvals.length>0&&<div className="cp-task-list">{approvals.map(({order,revision})=><article className="cp-task" key={revision.id}><span className="cp-task-icon cp-approval"><ClipboardCheck size={22}/></span><div className="cp-task-copy"><span className="cp-unit">{unitFor(order.vehicle_id)}</span><h3>{order.description || 'Repair authorization'}</h3><p>Approval needed before work can continue</p></div><div className="cp-task-end"><strong>{formatMoney(revision.total_amount)}</strong><span className="cp-state">Awaiting your review</span></div><Link className="cp-primary" data-db-control="action" to={scopedPortalPath('/portal/repairs?view=active',scope.vehicleId)} state={{selectedOrderId:order.id}}>Review request<ChevronRight size={15}/></Link></article>)}</div>}{!data.invoices.isError&&invoices.length>0&&<InvoiceRows invoices={invoices} orders={orders} vehicles={vehicles} scope={scope.vehicleId}/>}{visits.length>0&&<div className="cp-task-list">{visits.map(visit=><article className="cp-task" key={visit.id}><span className="cp-task-icon"><CalendarDays size={22}/></span><div className="cp-task-copy"><span className="cp-unit">{unitFor(visit.vehicle_id)}</span><h3>{visit.service_name}</h3><p>Today at {format(new Date(visit.scheduled_at),'h:mm a')}</p></div><span className="cp-task-end cp-state">{visit.status==='pending'?'Awaiting payment confirmation':visit.status.replace('_',' ')}</span><Link data-db-control="action" className="cp-secondary" to={scopedPortalPath(`/portal/appointments?appointment_id=${visit.id}`,scope.vehicleId)}>View visit<ChevronRight size={15}/></Link></article>)}</div>}{count===0&&!hasReadError&&<div className="cp-panel cp-empty"><Check/><h3>You’re up to date</h3><p>New requests and invoices will appear here.</p></div>}</section>{work.length>0&&<><div className="cp-list-heading cp-later"><h2>In progress</h2></div><div className="cp-task-list">{work.map(order=><article className="cp-task" key={order.id}><span className="cp-task-icon"><Wrench/></span><div className="cp-task-copy"><span className="cp-unit">{unitFor(order.vehicle_id)}</span><h3>{order.description||order.order_number}</h3><p>{repairStatusLabel(order.status)}</p></div><Link data-db-control="action" className="cp-secondary" to={scopedPortalPath('/portal/repairs?view=active',scope.vehicleId)} state={{selectedOrderId:order.id}}>View repair<ChevronRight size={15}/></Link></article>)}</div></>}{recent.length>0&&<section className="cp-history" aria-labelledby="portal-activity-heading"><div className="cp-list-heading"><h2 id="portal-activity-heading">Recent activity</h2><Link data-db-control="action" className="cp-text" to={scopedPortalPath('/portal/repairs',scope.vehicleId)}>View history<ChevronRight size={15}/></Link></div><p className="cp-section-description">Your latest completed services.</p>{recent.map(order=><div className="cp-activity" key={order.id}><span className="cp-paid"><Check size={16}/></span><div><span className="cp-unit">{unitFor(order.vehicle_id)}</span><h3>{order.description || 'Service completed'}</h3><p>{format(new Date(order.updated_at),'MMM d, yyyy')}</p></div><Link className="cp-text" data-db-control="action" to={scopedPortalPath('/portal/repairs',scope.vehicleId)} state={{selectedOrderId:order.id}}>View details<ChevronRight size={15}/></Link></div>)}</section>}</div><aside className="cp-context" aria-label="Account and vehicle summaries"><section className="cp-panel cp-balance"><h2>Account balance</h2>{data.invoices.isError?<p role="status">Unavailable until invoices load</p>:<><strong className="cp-balance-total">{unknown&&balance===0n?'Unavailable':formatMoney(centsToMoney(balance))}</strong><p className="cp-balance-caption">Total outstanding</p><p>{scope.vehicleId&&vehicles.length>1?'Across all vehicles · ':''}{unknown?'Some balances need shop verification':`${accountBalances.filter(i=>i.balance!==null&&i.balance>0n).length} outstanding ${accountBalances.filter(i=>i.balance!==null&&i.balance>0n).length===1?'invoice':'invoices'}`}</p>{!unknown&&pending!==null&&pending>0n&&pending<=balance&&<dl><div><dt>Pending confirmation</dt><dd>{formatMoney(centsToMoney(pending))}</dd></div><div><dt>Available to pay</dt><dd>{formatMoney(centsToMoney(balance-pending))}</dd></div></dl>}</>}</section><section className="cp-panel cp-vehicle-overview"><div className="cp-list-heading"><h2>{scope.vehicle?'Your vehicle':'Your vehicles'}</h2><Truck size={18}/></div>{scope.vehicle?<><strong>{scope.vehicle.unit_number?`Unit #${scope.vehicle.unit_number}`:'Vehicle'}</strong><p>{vehicleIdentity(scope.vehicle)}</p>{scope.vehicle.mileage!=null&&<p>{scope.vehicle.mileage.toLocaleString()} mi</p>}</>:<><strong>{`${vehicles.length} ${vehicles.length===1?'vehicle':'vehicles'}`}</strong><p>{vehicleIdentityCollisions(vehicles).size?'Some vehicle details need the shop’s review.':'View service history and book by vehicle.'}</p></>}<Link data-db-control="action" className="cp-text" to={scopedPortalPath('/portal/vehicles',scope.vehicleId)}>{scope.vehicle?'Vehicle details':'Browse vehicles'}<ChevronRight size={15}/></Link></section></aside></div>}</div>
}
