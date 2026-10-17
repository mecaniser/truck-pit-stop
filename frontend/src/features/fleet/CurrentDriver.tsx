import DriverRecord from './DriverRecord'
import { currentDriverName, currentDriverRecord, type DriverTruck } from './driverIdentity'

/** Show the current driver and score; local contact snapshots stay out of read-only identity displays. */
export default function CurrentDriver({ truck, fallback = 'Unassigned' }: { truck: DriverTruck; fallback?: string }) {
  const record = currentDriverRecord(truck)
  return <span className="current-driver">
    <span className="current-driver-main"><span className="current-driver-name">{currentDriverName(truck) || fallback}</span><DriverRecord truck={truck} />{record && <small className="current-driver-source">Motive</small>}</span>
  </span>
}
