import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { ChevronRight, Plus, Truck } from 'lucide-react'
import { format, isValid } from 'date-fns'
import { Spinner } from '@/components/ui'
import { ControlButton } from '@/components/ui/Controls'
import { useAuthStore } from '@/stores/authStore'
import type { RepairOrder, Vehicle } from '@/types'
import { getPortalItems, resolveVehicleScope, scopedPortalPath, vehicleIdentity, vehicleIdentityCollisions } from './portal-context'
import PortalVehicleScope from './PortalVehicleScope'
export default function PortalVehiclesPage() {
  const user=useAuthStore(state=>state.user)
  const [params,setParams]=useSearchParams()
  const key=[user?.tenant_id,user?.customer_id]
  const vehicleQuery=useQuery({queryKey:['vehicles',...key],queryFn: ({ signal }) => getPortalItems<Vehicle>('/vehicles', {}, signal)})
  const orderQuery=useQuery({queryKey:['repair-orders',...key],queryFn: ({ signal }) => getPortalItems<RepairOrder>('/repair-orders', {}, signal)})
  if(vehicleQuery.isLoading||orderQuery.isLoading) return <Spinner size="xl"/>
  if(vehicleQuery.isError||orderQuery.isError) return <div className="cp-root" role="alert"><h1>Vehicles unavailable</h1><p>We couldn’t load your vehicles and service history.</p><ControlButton className="cp-secondary" onClick={()=>{void vehicleQuery.refetch();void orderQuery.refetch()}}>Try again</ControlButton></div>
  const vehicles=vehicleQuery.data || []
  const scope=resolveVehicleScope(vehicles,params.get('vehicle_id'))
  const collisions=vehicleIdentityCollisions(vehicles)
  const visible=scope.vehicle?[scope.vehicle]:vehicles
  return <div className="cp-root"><div className="cp-title"><div><h1>Your vehicles</h1>{!collisions.size&&<p>{vehicles.length} {vehicles.length===1?'vehicle':'vehicles'}</p>}</div><PortalVehicleScope vehicles={vehicles} requested={params.get('vehicle_id')} onChange={id=>setParams(id?{vehicle_id:id}:{})}/></div>{scope.invalid?<div className="cp-panel cp-empty" role="alert"><h2>Vehicle unavailable</h2><p>Choose one of your vehicles to continue.</p></div>:<><div className="cp-vehicle-list">{visible.map(vehicle=>{
    const orders=(orderQuery.data || []).filter(order=>order.vehicle_id===vehicle.id).sort((a,b)=>b.updated_at.localeCompare(a.updated_at))
    const latest=orders[0]
    return <article className="cp-panel" key={vehicle.id}><Truck/><div><h2>{vehicle.unit_number?`Unit #${vehicle.unit_number}`:'Vehicle'}</h2><p>{vehicleIdentity(vehicle)}</p><p>{vehicle.mileage!=null?`${vehicle.mileage.toLocaleString()} mi`:'Mileage not provided'} · {orders.length} service {orders.length===1?'entry':'entries'}</p>{latest&&isValid(new Date(latest.updated_at))&&<p>Latest activity {format(new Date(latest.updated_at),'MMM d, yyyy')}</p>}{collisions.has(vehicle.id)&&<p role="status">Vehicle details need review. Contact the shop before booking.</p>}</div><div className="cp-vehicle-actions">{!collisions.has(vehicle.id)&&<Link data-db-control="action" className="cp-secondary" to={scopedPortalPath('/portal/services',vehicle.id)}>Book service</Link>}<Link data-db-control="action" className="cp-text" to={scopedPortalPath('/portal/repairs',vehicle.id)}>View history<ChevronRight size={15}/></Link></div></article>
  })}</div>{vehicles.length===0&&<div className="cp-panel cp-empty"><Truck/><h2>No vehicles yet</h2><p>Add your vehicle to start booking service.</p></div>}<Link data-db-control="action" className="cp-secondary" to="/portal/settings?tab=vehicles"><Plus size={17}/>Add vehicle</Link></>}</div>
}
