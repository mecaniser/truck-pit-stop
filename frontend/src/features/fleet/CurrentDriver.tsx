import { formatUSPhone } from '@/utils/phone'
import DriverRecord from './DriverRecord'
import { currentDriverName, currentDriverRecord, type DriverTruck } from './driverIdentity'

export function LocalDriverContact({ truck }: { truck: DriverTruck }) {
  const record = currentDriverRecord(truck)
  if (!record) return truck.driver_phone ? <span className="driver-local-contact">{formatUSPhone(truck.driver_phone)}</span> : null
  const differentAlias = truck.driver_name && truck.driver_name.trim() !== record.driver_name.trim()
  if (!differentAlias && !truck.driver_phone) return null
  return <span className="driver-local-contact">Local contact{differentAlias ? ` · ${truck.driver_name}` : ''}{truck.driver_phone ? ` · ${formatUSPhone(truck.driver_phone)}` : ''}</span>
}

/** Provider identity and local contact remain separate, including managed custody. */
export default function CurrentDriver({ truck, fallback = 'Unassigned' }: { truck: DriverTruck; fallback?: string }) {
  const record = currentDriverRecord(truck)
  return <span className="current-driver">
    <span className="current-driver-main"><span className="current-driver-name">{currentDriverName(truck) || fallback}</span><DriverRecord truck={truck} />{record && <small className="current-driver-source">Motive</small>}</span>
    <LocalDriverContact truck={truck} />
  </span>
}
