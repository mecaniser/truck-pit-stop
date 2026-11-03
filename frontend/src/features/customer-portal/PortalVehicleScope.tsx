import { Truck } from 'lucide-react'
import BaseSelect from '@/components/BaseSelect'
import { ControlButton } from '@/components/ui/Controls'
import type { Vehicle } from '@/types'
import { resolveVehicleScope, vehicleIdentity, vehicleIdentityCollisions } from './portal-context'
export default function PortalVehicleScope({vehicles, requested, onChange}: {vehicles:Vehicle[];requested:string|null;onChange:(id:string|null)=>void}) {
  const scope=resolveVehicleScope(vehicles,requested)
  const collisions=vehicleIdentityCollisions(vehicles)
  if(vehicles.length===1 && !requested && !scope.ambiguous) return <span className="cp-vehicle-tag"><Truck size={17}/>{vehicleIdentity(vehicles[0])}</span>
  return <div className="cp-scope"><BaseSelect ariaLabel="Vehicle scope" variant="dark" searchable={vehicles.length>8} selectOnly options={[{value:'all',label:'All vehicles'},...vehicles.map(v=>({value:v.id,label:vehicleIdentity(v),flag:collisions.has(v.id)?{text:'Details need review',tone:'warning' as const}:undefined}))]} value={scope.invalid?'':scope.vehicleId || 'all'} placeholder="Choose a vehicle" onChange={value=>onChange(value==='all'?null:value)} heightClass="h-[44px]" optionHeightClass="min-h-[44px]"/>{requested && <ControlButton className="cp-text" onClick={()=>onChange(null)}>All vehicles</ControlButton>}</div>
}
